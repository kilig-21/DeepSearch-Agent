"""任务结果落库(CLI 与 TaskManager 共用, 计划书 §3.4)。

evidences/sources/search_rounds 落库 + 报告与 tasks 终态同事务提交;
提交前不发任何终态事件。
"""
from __future__ import annotations

from . import db
from .budget import Budget


def persist_task_results(engine, task_id: str, state: dict, budget: Budget | None,
                         *, allowed_domains: set[str], proxy: bool) -> int | None:
    """返回 report_id;任务已被取消/失败抢先终态时返回 None(后到结果丢弃,
    第四轮评审 P6),调用方不得再发 done。"""
    source_id_by_url: dict[str, int] = {}
    for ev in state.get("evidence", []):
        if ev.url not in source_id_by_url:
            source_id_by_url[ev.url] = db.record_source(
                engine, task_id, url=ev.url, title=ev.title, domain=ev.domain,
                source_type=ev.source_type, content_hash=ev.content_hash,
                origin_group_id=ev.origin_group_id)
        db.record_evidence(engine, task_id, evidence_id=ev.evidence_id,
                           source_id=source_id_by_url[ev.url],
                           origin_group_id=ev.origin_group_id,
                           source_type=ev.source_type, quote=ev.quote,
                           validated=True)
    for r in state.get("search_rounds", []):
        db.record_search_round(engine, task_id, round_no=r["round_no"],
                               query=r["query"],
                               result_count=r["result_count"],
                               credits_used=r["credits_used"])

    usage = budget.usage_snapshot() if budget else {
        "llm_tokens": 0, "llm_research_tokens": 0, "llm_writer_tokens": 0,
        "tavily_credits": 0, "jina_tokens": 0}
    return db.complete_task_with_report(
        engine, task_id,
        final_md=state.get("report_md", ""),
        citation_map=state.get("citation_map", {}),
        stop_reason=state.get("stop_reason") or "single_pass",
        config_json={"allowed_domains": sorted(allowed_domains),
                     "proxy": proxy},
        token_cost=usage["llm_tokens"],
        credits_cost=usage["tavily_credits"],
        duration_s=state.get("duration_s", 0.0),
        usage=usage,
    )
