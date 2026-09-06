"""评测 runner(§10.1: 建题与评分表 → 跑链路 → 标注 → 存基线)。

- 在线题走真实组件(default_tools_builder), 记录时点快照
- 离线题注入固定材料(search/fetch 不联网, LLM 为真实调用), 可复现
- 结果行含 §10.1 要求的保存字段: 模型 ID / 提示词版本 / 参数 / 时间 / 轨迹
- 标注(annotation)是跑后人工/复核环节, runner 置 None 占位
- 对比实验(§10.4): --compare 时在线题按单轮/反思循环两策略配对执行,
  同资源上限(同 token 上限/同来源集合), 题序奇偶交替先后防时间漂移

入口: python -m orca.eval [--compare] [--only qid,...]
  → 结果写 eval/baselines/run_<ts>.json + table_<ts>.md(结果表)
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from .. import cli, db, graph
from ..budget import MIN_USABLE_OUTPUT, PROMPT_MARGIN
from ..config import (
    BUDGET_MAX_PAGES,
    BUDGET_MAX_TAVILY_CREDITS,
    BUDGET_TIME_S,
    BUDGET_TOTAL_LLM_TOKENS,
    BUDGET_WRITER_RESERVE_TOKENS,
    DB_PATH,
)
from ..extract import ExtractError, ExtractedPage
from ..llm import LLM_DAILY_MODEL, LLM_HIGH_QUALITY_MODEL
from .materials import MATERIALS
from .questions import QUESTIONS, Question, get
from . import safety

PROMPT_VERSION = "phase2-v1"  # graph.py 提示词版本(Phase 2 增 reflector)(改动需递增)
BASELINES_DIR = Path(__file__).resolve().parents[2] / "eval" / "baselines"
# 评测任务落日常库(§5): 复核者直接查 data/orca.db 追溯 task/sources/
# evidences(quote/fetched_at);评测库分离曾致复核时查无此任务
EVAL_DB = DB_PATH


def quality_denominator(row: dict) -> bool:
    """失败题与无答案题不静默出分母, 记 N/A(§10.1)。

    - 单轮(single_pass)/反思正常收尾(evidence_sufficient)→ 出分母
    - 研究类提前收尾(如 no_new_evidence/budget_exhausted)但已有证据
      经 writer 产出正式报告(§3.6)→ 如实出分母, 不因 stop_reason
      静默 N/A(离线固定材料下反思循环必然空转一轮后以此态收尾)
    - 程序说明(无答案, 或控制类中断未成文)与失败 → N/A
    """
    if row.get("status") != "completed":
        return False
    if row.get("stop_reason") in ("single_pass", "evidence_sufficient"):
        return True
    if not row.get("evidences"):
        return False   # 无证据 → 报告必为程序说明或未成文
    report = row.get("report_md") or ""
    # 控制类中断(timeout 等)即便有证据也只产出程序说明, 不入分母
    return "研究未能完成" not in report[:40]


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
            # 抓取失败注入: fetch_fail 题无哨兵 → 全部失败;材料 "FAIL"
            # 哨兵按页失败(fetch_partial);未声明 URL 同样失败
            all_fail = (q.qtype == "fetch_fail" and not any(
                k == "FAIL" for _u, k in q.materials))
            if key == "FAIL" or key is None or all_fail:
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

    kwargs = dict(
        total_llm_tokens=50_000, writer_reserve_tokens=8_000,
        max_tavily_credits=BUDGET_MAX_TAVILY_CREDITS,
        max_pages=BUDGET_MAX_PAGES, time_budget_s=BUDGET_TIME_S,
        max_jina_tokens=0)
    kwargs.update(q.budget_overrides)
    return lambda: Budget(**kwargs)


def run_question(q: Question, *, db_path, builder, collector: dict,
                 strategy: str = "reflect") -> int:
    """跑一题(复用 CLI 全链路: 建任务→图→同事务落库), 组装结果行。

    strategy: "reflect"(反思循环, 生产默认)| "single"(单轮对比, §10.4)。
    builder 返回的 tools 上改写 reflect 开关(不改动 builder 本身);
    events 仍从原 builder 属性取。

    任务结果经 cmd_research 的 out 回传(task_id/state), 不用
    list_tasks()[-1]——并发写入同一 DB 时会拿错行(实测踩坑)。
    tokens/credits 从落库的 tasks.usage_json 按 task_id 精确取;
    duration 用评测侧 wall time(含落库, 更真实)。
    """
    import time as _time

    reflect = strategy == "reflect"

    def wrapped_builder(budget):
        tools = builder(budget)
        tools.reflect = reflect
        return tools

    t0 = _time.monotonic()
    out: dict = {}
    rc = cli.cmd_research(q.topic, db_path=db_path, tools_builder=wrapped_builder,
                          budget_builder=_budget_builder_for(q), out=out)
    duration_s = round(_time.monotonic() - t0, 1)
    events = list(getattr(builder, "events", []))

    task_id = out.get("task_id")
    state = out.get("state") or {}
    engine = db.make_engine(db_path)
    task = (next((t for t in db.list_tasks(engine) if t["id"] == task_id),
                 None) or {})
    usage = task.get("usage_json") or {}

    citation_map = state.get("citation_map") or {}
    report_md = state.get("report_md") or ""
    # evidences 快照(§10.1/§5): 断言的 evidence_ids 须可追溯到 quote
    evidences = [{
        "evidence_id": e.evidence_id,
        "quote": e.quote,
        "source_type": e.source_type,
        "url": e.url,
        "title": e.title,
        "point": e.point,
        "origin_group_id": e.origin_group_id,
        "fetched_at": e.fetched_at,
    } for e in state.get("evidence", [])]
    row = {
        "qid": q.qid, "qtype": q.qtype, "mode": q.mode, "topic": q.topic,
        "strategy": strategy,
        "task_id": task_id, "report_id": out.get("report_id"),
        "status": task.get("status"), "stop_reason": task.get("stop_reason"),
        "tokens": usage.get("llm_tokens"),
        "credits": usage.get("tavily_credits"),
        "duration_s": duration_s,
        "citation_map": citation_map,
        "valid_citation_ratio": _valid_citation_ratio(report_md, citation_map),
        "report_md": report_md,
        "evidences": evidences,
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


def plan_compare(selected: list[Question], *, compare: bool = False
                 ) -> list[tuple[Question, str]]:
    """生成执行计划 [(题, 策略)](§10.4 对比口径)。

    - compare=False: 每题一遍 reflect(生产默认模式)
    - compare=True:  在线题单轮/反思循环各跑一遍(同资源上限配对),
      按题序奇偶交替两策略先后(防"后跑的策略沾环境变化的光",
      时间漂移);离线题固定 reflect 只跑一遍(承担回归, 不参与对比)
    """
    plan: list[tuple[Question, str]] = []
    for i, q in enumerate(selected):
        if q.mode == "online" and compare:
            first, second = (("single", "reflect") if i % 2 == 0
                             else ("reflect", "single"))
            plan.append((q, first))
            plan.append((q, second))
        else:
            plan.append((q, "reflect"))
    return plan


def run_eval(selected: list[Question], *, db_path, builder_for,
             compare: bool = False) -> list[dict]:
    """按计划跑题, 返回结果行(builder_for 由 main 注入真实组件, 测试可换桩)。"""
    rows: list[dict] = []
    for q, strategy in plan_compare(selected, compare=compare):
        print(f"\n===== [{q.qid}/{strategy}] {q.topic}")
        collector: dict = {}
        run_question(q, db_path=db_path, builder=builder_for(q, strategy),
                     collector=collector, strategy=strategy)
        row = collector["row"]
        extra = (f" safety={row['safety']}" if row["safety"] else "")
        print(f"----- {q.qid}/{strategy}: {row['status']}/"
              f"{row['stop_reason']} tokens={row['tokens']} "
              f"引用有效率={row['valid_citation_ratio']}{extra}")
        rows.append(row)
    return rows


def build_results_table(rows: list[dict]) -> str:
    """结果表(§10.2 口径): 自动指标直出;标注类指标留位待补。

    - 自动: 状态/stop_reason/tokens/credits/引用有效率/安全自动判定
    - 标注类(待 AI 初标+人工复核): 答案覆盖率、断言引用支持率
    - 失败率分母=全部任务(§10.4)
    """
    total = len(rows)
    failed = sum(1 for r in rows if r["status"] != "completed")
    lines = [
        "# Orca 评测结果表(§10.2 口径)",
        "",
        f"- 总任务数: {total}",
        f"- 失败率: {failed / total * 100:.1f}%(分母=全部任务, §10.4)",
        "- 标注类指标(答案覆盖率/断言引用支持率/安全三条件人工复核):"
        " 待 AI 初标与人工复核后补, 本表不含(不静默出分)",
        "",
        "| qid | mode | strategy | status | stop_reason | tokens | credits "
        "| 引用有效率 | 安全 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        safety_txt = ("—" if r["safety"] is None
                      else ("pass" if r["safety"].get("pass") else "FAIL"))
        ratio = ("—" if r["valid_citation_ratio"] is None
                 else f"{r['valid_citation_ratio']:.2f}")
        lines.append(
            f"| {r['qid']} | {r['mode']} | {r['strategy']} | "
            f"{r['status']} | {r['stop_reason']} | {r['tokens']} | "
            f"{r['credits']} | {ratio} | {safety_txt} |")
    return "\n".join(lines) + "\n"


def main(argv=None, *, db_path=None, baselines_dir: Path | None = None,
         builder_for=None) -> int:
    import argparse
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="orca.eval", description="跑评测集(27 题, §10.1 口径)")
    parser.add_argument("--only", default=None,
                        help="逗号分隔的 qid 列表(默认全部)")
    parser.add_argument("--compare", action="store_true",
                        help="在线题按单轮/反思循环两策略配对对比(§10.4)")
    args = parser.parse_args(argv)

    selected = QUESTIONS
    if args.only:
        ids = [s.strip() for s in args.only.split(",") if s.strip()]
        selected = [get(qid) for qid in ids]

    def default_builder_for(q: Question, strategy: str):
        return (make_online_builder() if q.mode == "online"
                else make_offline_builder(q))

    db = db_path or EVAL_DB
    out_dir = baselines_dir or BASELINES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(db).parent.mkdir(parents=True, exist_ok=True)

    results = run_eval(selected, db_path=db,
                       builder_for=builder_for or default_builder_for,
                       compare=args.compare)

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"run_{ts}.json"
    # R4a: meta 自证实验配置 —— 预算/闸门参数为解析后的实际值,
    # only_qids 非空即补跑产物(与全量 run 可区分, 消除跨版本配对混淆)
    out.write_text(json.dumps(
        {"meta": {"prompt_version": PROMPT_VERSION,
                  "models": {"daily": LLM_DAILY_MODEL,
                             "high_quality": LLM_HIGH_QUALITY_MODEL},
                  "budget_defaults": {
                      "total_llm_tokens": BUDGET_TOTAL_LLM_TOKENS,
                      "writer_reserve_tokens": BUDGET_WRITER_RESERVE_TOKENS,
                      "max_tavily_credits": BUDGET_MAX_TAVILY_CREDITS,
                      "max_pages": BUDGET_MAX_PAGES,
                      "time_budget_s": BUDGET_TIME_S},
                  "writer_max_tokens": graph._WRITER_MAX_TOKENS,
                  "budget_guard": {"min_usable_output": MIN_USABLE_OUTPUT,
                                   "prompt_margin": PROMPT_MARGIN},
                  "only_qids": ([s.strip() for s in args.only.split(",")
                                 if s.strip()] if args.only else None)},
         "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    table = out_dir / f"table_{ts}.md"
    table.write_text(build_results_table(results), encoding="utf-8")
    print(f"\n基线已保存: {out}\n结果表已保存: {table}")
    print(build_results_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
