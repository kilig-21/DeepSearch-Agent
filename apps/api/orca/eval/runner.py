"""评测 runner(§10.1: 建题与评分表 → 跑链路 → 标注 → 存基线)。

- 在线题走真实组件(default_tools_builder), 记录时点快照
- 离线题注入固定材料(search/fetch 不联网, LLM 为真实调用), 可复现
- 结果行含 §10.1 要求的保存字段: 模型 ID / 提示词版本 / 参数 / 时间 / 轨迹
- 标注(annotation)是跑后人工/复核环节, runner 置 None 占位

入口: python -m orca.eval  → 跑全部 10 题, 结果写 eval/baselines/run_<ts>.json
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from .. import cli, db
from ..extract import ExtractError, ExtractedPage
from ..llm import LLM_DAILY_MODEL, LLM_HIGH_QUALITY_MODEL
from .materials import MATERIALS
from .questions import QUESTIONS, Question, get
from . import safety

PROMPT_VERSION = "phase1a-v1"  # graph.py 内各节点提示词版本(改动需递增)
BASELINES_DIR = Path(__file__).resolve().parents[2] / "eval" / "baselines"
EVAL_DB = Path(__file__).resolve().parents[2] / "data" / "eval.db"


def quality_denominator(row: dict) -> bool:
    """失败题与无答案题不静默出分母, 记 N/A(§10.1)。"""
    if row.get("status") != "completed":
        return False
    return row.get("stop_reason") == "single_pass"


def _tee_emit(events: list):
    """既照常打印时间线, 又把事件收集为轨迹(§10.1 原始任务轨迹)。"""
    from ..events import console_emit

    def emit(event: str, payload: dict) -> None:
        console_emit(event, payload)
        events.append({"event": event, "payload": payload})
    return emit


def make_offline_builder(q: Question, *, llm_chat=None):
    """离线注入: search 固定结果, fetch 按材料返回/抛错;LLM 可注入(单测)。

    事件列表挂在 builder.events 属性上, run_question 跑完读取。
    """
    events: list = []

    def builder(budget) -> cli.GraphTools:
        from ..llm import LLMClient

        chat = llm_chat if llm_chat is not None else LLMClient().chat

        def search_fn(query: str, *, limit: int):
            from ..search import SearchResult

            return ([SearchResult(url=u, title=f"固定材料 {key}", snippet="")
                     for u, key in q.materials], 1)

        async def fetch_async(url: str, *, allowed_domains=None, proxy=None):
            key = dict(q.materials).get(url)
            if q.qtype == "fetch_fail" or key is None:
                raise ExtractError("评测注入: 模拟抓取失败")
            return ExtractedPage(url=url, final_url=url,
                                 text=MATERIALS[key])

        return cli.GraphTools(
            llm_chat=chat, search_fn=search_fn, fetch_async=fetch_async,
            budget=budget, emit=_tee_emit(events),
            allowed_domains=set(cli.ALLOWED_DOMAINS), proxy=None,
            events=events)
    builder.events = events
    return builder


def make_online_builder():
    """在线: 真实组件 + 事件 tee(时间线照常打印, 同时收集为轨迹)。"""
    events: list = []

    def builder(budget) -> cli.GraphTools:
        tools = cli.default_tools_builder(budget)
        inner = tools.emit

        def emit(event: str, payload: dict) -> None:
            inner(event, payload)
            events.append({"event": event, "payload": payload})
        tools.emit = emit
        return tools
    builder.events = events
    return builder


def _valid_citation_ratio(report_md: str, citation_map: dict) -> float | None:
    """验收①复核: 报告 [n] 引用编号落在 citation_map 内的比例。

    校验器+降级兜底下恒 1.0;若跌破说明校验链被绕过, 评测必须暴露。
    """
    cited = set(re.findall(r"\[(\d{1,3})\]", report_md))
    if not cited:
        return None
    return round(sum(1 for n in cited if n in citation_map) / len(cited), 4)


def _budget_builder_for(q: Question):
    if not q.budget_overrides:
        return cli._make_budget  # 默认全预算
    from ..budget import Budget
    from ..config import (
        BUDGET_MAX_PAGES, BUDGET_MAX_TAVILY_CREDITS, BUDGET_TIME_S,
    )

    kwargs = dict(
        total_llm_tokens=50_000, writer_reserve_tokens=8_000,
        max_tavily_credits=BUDGET_MAX_TAVILY_CREDITS,
        max_pages=BUDGET_MAX_PAGES, time_budget_s=BUDGET_TIME_S,
        max_jina_tokens=0)
    kwargs.update(q.budget_overrides)
    return lambda: Budget(**kwargs)


def run_question(q: Question, *, db_path, builder, collector: dict) -> int:
    """跑一题(复用 CLI 全链路: 建任务→图→同事务落库), 组装结果行。

    tokens/credits 从落库的 tasks.usage_json 取(done 事件是 CLI 呈现层,
    不经过 collector);duration 用评测侧 wall time(含落库, 更真实)。
    """
    import time as _time

    t0 = _time.monotonic()
    rc = cli.cmd_research(q.topic, db_path=db_path, tools_builder=builder,
                          budget_builder=_budget_builder_for(q))
    duration_s = round(_time.monotonic() - t0, 1)
    events = list(getattr(builder, "events", []))

    engine = db.make_engine(db_path)
    task = db.list_tasks(engine)[-1]
    report = db.get_report(engine, task["report_id"]) \
        if task["report_id"] else None
    usage = task["usage_json"] or {}

    citation_map = (report["citation_map_json"] if report else {}) or {}
    report_md = (report["final_md"] if report else "") or ""
    row = {
        "qid": q.qid, "qtype": q.qtype, "mode": q.mode, "topic": q.topic,
        "task_id": task["id"], "report_id": task["report_id"],
        "status": task["status"], "stop_reason": task["stop_reason"],
        "tokens": usage.get("llm_tokens"),
        "credits": usage.get("tavily_credits"),
        "duration_s": duration_s,
        "citation_map": citation_map,
        "valid_citation_ratio": _valid_citation_ratio(report_md, citation_map),
        "report_md": report_md,
        "events": events,
        "eval_time": _dt.datetime.now().isoformat(timespec="seconds"),
        "models": {"daily": LLM_DAILY_MODEL,
                   "high_quality": LLM_HIGH_QUALITY_MODEL,
                   "max_tokens_policy": "必填, 覆盖推理型思考段"},
        "prompt_version": PROMPT_VERSION,
        "budget_overrides": q.budget_overrides,
        "required_points": q.required_points,
        "annotation": None,   # 跑后标注(§10.1 顺序: 先跑链路后标注)
        "safety": safety.check(report_md, q) if q.qtype == "inject" else None,
    }
    collector["row"] = row
    return rc


def main(argv=None) -> int:
    import argparse
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="orca.eval",
                                     description="跑 10 题评测集")
    parser.add_argument("--only", default=None,
                        help="逗号分隔的 qid 列表(默认全部)")
    args = parser.parse_args(argv)

    selected = QUESTIONS
    if args.only:
        ids = [s.strip() for s in args.only.split(",") if s.strip()]
        selected = [get(qid) for qid in ids]

    EVAL_DB.parent.mkdir(parents=True, exist_ok=True)
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for q in selected:
        print(f"\n===== [{q.qid}] {q.topic}")
        builder = (make_online_builder() if q.mode == "online"
                   else make_offline_builder(q))
        collector: dict = {}
        run_question(q, db_path=EVAL_DB, builder=builder, collector=collector)
        row = collector["row"]
        extra = (f" safety={row['safety']}" if row["safety"] else "")
        print(f"----- {q.qid}: {row['status']}/{row['stop_reason']} "
              f"tokens={row['tokens']} 引用有效率={row['valid_citation_ratio']}"
              f"{extra}")
        results.append(row)

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BASELINES_DIR / f"run_{ts}.json"
    out.write_text(json.dumps(
        {"meta": {"prompt_version": PROMPT_VERSION,
                  "models": {"daily": LLM_DAILY_MODEL,
                             "high_quality": LLM_HIGH_QUALITY_MODEL}},
         "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n基线已保存: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
