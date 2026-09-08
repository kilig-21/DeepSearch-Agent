"""命令行入口(计划书 §6):`python -m orca <subcommand>`。

- research <topic>:创建任务 → 线性链路 → 报告与任务同事务落库 → done
- cleanup:本地数据清理(须在后端停止后执行, §6/§9.1)
"""
from __future__ import annotations

import argparse
import sys
import time

from . import db
from .budget import Budget
from .config import (
    ALLOWED_DOMAINS,
    BUDGET_MAX_PAGES,
    BUDGET_MAX_TAVILY_CREDITS,
    BUDGET_TIME_S,
    BUDGET_TOTAL_LLM_TOKENS,
    BUDGET_WRITER_RESERVE_TOKENS,
    DB_PATH,
    FETCH_PROXY,
    SOURCE_ADAPTER,
)
from .events import console_emit
from .graph import GraphTools, run_research
from .persist import persist_task_results


def _make_budget() -> Budget:
    return Budget(
        total_llm_tokens=BUDGET_TOTAL_LLM_TOKENS,
        writer_reserve_tokens=BUDGET_WRITER_RESERVE_TOKENS,
        max_tavily_credits=BUDGET_MAX_TAVILY_CREDITS,
        max_pages=BUDGET_MAX_PAGES,
        time_budget_s=BUDGET_TIME_S,
        max_jina_tokens=0,  # Jina 兜底默认关闭(§3.6)
    )


def default_tools_builder(budget: Budget) -> GraphTools:
    """真实组件组装;测试注入替代 builder。"""
    from .extract import fetch_and_extract_async
    from .llm import LLMClient
    from .search import TavilySearch
    from .adapters import PythonZhDocsAdapter

    llm = LLMClient()
    tavily = TavilySearch()

    def search_fn(query: str, *, limit: int):
        return tavily.search(query, limit=limit)

    async def fetch_async(url: str, *, allowed_domains=None, proxy=None):
        return await fetch_and_extract_async(
            url, allowed_domains=allowed_domains or ALLOWED_DOMAINS,
            proxy=proxy or FETCH_PROXY)

    if SOURCE_ADAPTER not in {"", "python_zh_docs"}:
        raise ValueError(f"未知 ORCA_SOURCE_ADAPTER: {SOURCE_ADAPTER}")
    adapter = PythonZhDocsAdapter() if SOURCE_ADAPTER == "python_zh_docs" else None

    return GraphTools(
        llm_chat=llm.chat, llm_chat_stream=llm.chat_stream,
        search_fn=search_fn, fetch_async=fetch_async,
        budget=budget, emit=console_emit,
        allowed_domains=set(ALLOWED_DOMAINS), proxy=FETCH_PROXY,
        source_adapter=adapter,
    )


def cmd_research(topic: str, *, db_path=None, tools_builder=default_tools_builder,
                 budget_builder=_make_budget, out: dict | None = None) -> int:
    engine = db.make_engine(db_path or DB_PATH)
    db.init_db(engine)
    db.mark_stale_interrupted(engine)  # 启动时遗留 running → interrupted(§3.4)

    task_id = db.create_task(engine, topic=topic)
    budget = budget_builder()

    t0 = time.monotonic()
    try:
        tools = tools_builder(budget)
        state = _run(tools, topic, task_id)
        state["duration_s"] = time.monotonic() - t0
        report_id = persist_task_results(
            engine, task_id, state, budget,
            allowed_domains=set(ALLOWED_DOMAINS), proxy=FETCH_PROXY is not None)
        if report_id is None:
            # CLI 无并发取消源, 理论不可达;防御: 终态已被抢先时按取消收尾(P6)
            db.cancel_task(engine, task_id, usage=budget.usage_snapshot())
            if out is not None:
                out.update(task_id=task_id)
            console_emit("cancelled", {})
            return 130
        if out is not None:
            # 评测 runner 经此取回本次任务结果; 禁止用 list_tasks()[-1]
            # (并发写入同一 DB 时会拿错行)
            out.update(task_id=task_id, report_id=report_id, state=state)
        usage = budget.usage_snapshot()
        console_emit("done", {
            "report_id": report_id, "stop_reason": state.get("stop_reason"),
            "token_cost": usage["llm_tokens"],
            "credits_cost": usage["tavily_credits"],
            "duration_s": state["duration_s"],
            "usage": usage,   # 成本分账(块 2): 研究/writer tokens 全量随终态下发
        })
        return 0
    except KeyboardInterrupt:
        # R2 分账: 已耗成本是事实, 取消终态同样落库(与 TaskManager 路径同构)
        db.cancel_task(engine, task_id, usage=budget.usage_snapshot())
        if out is not None:
            out.update(task_id=task_id)
        console_emit("cancelled", {})
        return 130
    except Exception as e:  # noqa: BLE001
        # R2 分账: 评测 runner 走本路径, 失败(如 writer 流式 ReadTimeout)
        # 时 budget 里已 settle 的成本随 task_failed 落库, 禁止丢账
        db.fail_task(engine, task_id, stop_reason="execution_error",
                     usage=budget.usage_snapshot())
        if out is not None:
            out.update(task_id=task_id)
        console_emit("task_failed", {
            "detail": f"{type(e).__name__}: {e}",
            "stop_reason": "execution_error",
            "usage": budget.usage_snapshot()})
        return 1


def _run(tools: GraphTools, topic: str, task_id: str) -> dict:
    import asyncio
    return asyncio.run(run_research(tools, topic, task_id=task_id))


def cmd_cost(task_id: str | None = None, *, last: bool = False,
             db_path=None) -> int:
    """单任务成本小结(块 2): 分账数据取自 tasks.usage_json(终态落库)。"""
    engine = db.make_engine(db_path or DB_PATH)
    db.init_db(engine)
    tasks = db.list_tasks(engine)
    if not tasks:
        print("库中暂无任务")
        return 1
    if task_id is not None:
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task is None:
            print(f"查无任务 {task_id}")
            return 1
    else:
        task = tasks[-1]   # created_at 升序, 末位最新(--last 为显式声明)

    u = task["usage_json"]
    research = u.get("llm_research_tokens", 0)
    writer = u.get("llm_writer_tokens", 0)
    print(f"任务 {task['id']}: {task['topic']}")
    print(f"状态: {task['status']} (stop_reason: {task['stop_reason']})")
    print(f"LLM tokens: {u.get('llm_tokens', 0)} "
          f"(研究 {research} + writer {writer})")
    print(f"Tavily credits: {u.get('tavily_credits', 0)}")
    print(f"Jina tokens: {u.get('jina_tokens', 0)}")
    if task["report_id"]:
        print(f"报告: #{task['report_id']}")
    return 0


def cmd_cleanup(*, db_path=None, assume_yes: bool = False) -> int:
    path = db_path or DB_PATH
    if not assume_yes:
        answer = input(f"将清空 {path} 中 tasks/reports/sources/evidences/"
                       "search_rounds 全部数据, 确认? [y/N] ")
        if answer.strip().lower() != "y":
            print("已取消")
            return 1
    engine = db.make_engine(path)
    db.init_db(engine)
    db.cleanup(engine)
    print(f"已清空 {path}")
    return 0


def main(argv=None) -> int:
    # Windows 控制台默认 GBK, 中文时间线会 UnicodeEncodeError/probe_results.md 同类坑
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="orca",
                                     description="Orca Research(Deep Search 研究助手)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_research = sub.add_parser("research", help="执行一次研究任务")
    p_research.add_argument("topic", help="研究问题")

    p_cost = sub.add_parser("cost", help="输出单任务成本小结(分账)")
    p_cost.add_argument("task_id", nargs="?", default=None,
                        help="任务 ID(缺省取最新任务)")
    p_cost.add_argument("--last", action="store_true",
                        help="取最新一条任务(与缺省行为一致, 显式声明)")

    sub.add_parser("cleanup", help="清空本地研究数据(后端停止后执行)")

    args = parser.parse_args(argv)
    if args.command == "research":
        return cmd_research(args.topic)
    if args.command == "cost":
        return cmd_cost(args.task_id, last=args.last)
    if args.command == "cleanup":
        return cmd_cleanup()
    return 2


if __name__ == "__main__":
    sys.exit(main())
