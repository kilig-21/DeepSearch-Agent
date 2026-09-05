"""LangGraph 线性链路(计划书 §3.2 Phase 1A):planner → searcher → reader
→ merger → writer,无循环(循环在 Phase 2)。

- 工具层全部依赖注入(GraphTools), 离线可测
- 控制类 stop_reason 优先(§3.4):timeout/total_budget_exhausted/
  execution_error 短路后续 LLM 调用;研究类只决定何时结束研究
- 集合外站点不抓正文, 仅列待核实链接;搜索摘要不作为已读证据(§4)
- writer 产物先经引用校验 → 一次修订 → 程序化降级兜底(§3.3)
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict
from urllib.parse import urlparse

from langgraph.graph import END, START, StateGraph

from .budget import Budget
from .citations import check_report, revise_report
from .evidence import CandidateEvidence, locate_quote, source_type_for_domain
from .extract import ExtractedPage, ExtractError
from .merger import merge_candidates
from .search import SearchResult, dedup, split_by_allowlist

# 控制类 stop_reason(§3.4):直接决定终态, 任何 LLM 调用不再发生
CONTROL_STOPS = {"total_budget_exhausted", "timeout", "execution_error",
                 "user_cancelled", "process_interrupted"}

_TOP_N = 4               # searcher 每轮选 top-N(§3.2)
_MAX_PROMPT_CHARS = 15_000   # reader 喂给 LLM 的正文截断(抓取上限仍 100k)
_READER_MAX_TOKENS = 4096
_WRITER_MAX_TOKENS = 8192    # glm-5.3 推理型: 必须给足覆盖思考段


class ResearchState(TypedDict):
    topic: str
    task_id: str
    sub_questions: list[str]
    planned_query: str
    search_results: list[SearchResult]   # 白名单内(可抓正文)
    pending_links: list[SearchResult]    # 集合外待核实链接(不抓)
    search_rounds: list[dict]
    candidate_evidence: list[CandidateEvidence]
    evidence: list[CandidateEvidence]    # merger 整体写回(§3.1)
    round_no: int
    stop_reason: str | None
    report_md: str
    citation_map: dict[str, str]


@dataclass
class GraphTools:
    llm_chat: Callable          # (messages, *, max_tokens, tier) -> LLMResult
    search_fn: Callable         # (query, *, limit) -> (results, credits)
    fetch_async: Callable       # async (url, *, allowed_domains, proxy) -> ExtractedPage
    budget: Budget
    emit: Callable              # (event: str, payload: dict) -> None
    allowed_domains: set[str]
    proxy: str | None = None
    max_pages_per_round: int = _TOP_N
    events: list = field(default_factory=list)  # 仅供工具调试


def _control_stop(state: ResearchState, budget: Budget) -> str | None:
    """控制类优先(§3.4):已有控制态保持;超时/总额度打穿即时判定。"""
    sr = state.get("stop_reason")
    if sr in CONTROL_STOPS:
        return sr
    if budget.out_of_time():
        return "timeout"
    if budget.total_exhausted():
        return "total_budget_exhausted"
    return None


def _domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _json_obj(text: str) -> dict | None:
    """从模型输出提取 JSON 对象(容忍代码围栏)。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# ---- 节点 -------------------------------------------------------------------

def make_planner(tools: GraphTools):
    def planner(state: ResearchState) -> dict:
        stop = _control_stop(state, tools.budget)
        if stop:
            return {"stop_reason": stop}
        try:
            result = tools.llm_chat(
                [{"role": "user", "content":
                  f"你是研究规划器。把用户问题拆解为 2~4 个可搜索的中文子问题,"
                  f"并给出 1 个首轮搜索查询。只输出 JSON:"
                  f'{{"sub_questions": ["..."], "query": "..."}}\n\n'
                  f"用户问题: {state['topic']}"}],
                max_tokens=_READER_MAX_TOKENS, tier="daily",
                reasoning_effort="low")  # 机械拆解任务, 压制思考省配额
        except Exception as e:  # noqa: BLE001
            tools.emit("warning", {"stage": "planner",
                                   "detail": f"规划失败: {e}"})
            return {"stop_reason": "execution_error"}
        tools.budget.settle_llm(result.usage.get("total_tokens", 0),
                                for_writer=False)
        obj = _json_obj(result.content) or {}
        sub_qs = [str(q) for q in obj.get("sub_questions", [])][:4]
        query = str(obj.get("query") or state["topic"])[:200]
        if not sub_qs:
            tools.emit("warning", {"stage": "planner", "detail": "拆解为空"})
            return {"stop_reason": "execution_error"}
        tools.emit("plan", {"sub_questions": sub_qs})
        return {"sub_questions": sub_qs, "planned_query": query}
    return planner


def make_searcher(tools: GraphTools):
    def searcher(state: ResearchState) -> dict:
        stop = _control_stop(state, tools.budget)
        if stop:
            return {"stop_reason": stop}
        if tools.budget.research_exhausted():
            return {"stop_reason": "budget_exhausted"}
        if not tools.budget.charge_credits(1):  # 预占 1 credit, 失败不出手
            return {"stop_reason": "budget_exhausted"}

        query = state.get("planned_query") or state["topic"]
        try:
            results, credits = tools.search_fn(query, limit=8)
        except Exception as e:  # noqa: BLE001
            tools.emit("warning", {"stage": "searcher",
                                   "detail": f"搜索失败: {e}"})
            return {"stop_reason": "no_new_evidence"}

        merged = dedup(list(state.get("search_results", [])) + results)
        allowed, outside = split_by_allowlist(merged, tools.allowed_domains)
        tools.emit("search", {"round": state["round_no"], "query": query,
                              "results": [{"url": r.url, "title": r.title}
                                          for r in merged],
                              "credits_used": credits})
        rounds = list(state.get("search_rounds", [])) + [{
            "round_no": state["round_no"], "query": query,
            "result_count": len(merged), "credits_used": credits}]
        return {"search_results": allowed, "pending_links": outside,
                "search_rounds": rounds}
    return searcher


def make_reader(tools: GraphTools):
    def reader(state: ResearchState) -> dict:
        stop = _control_stop(state, tools.budget)
        if stop:
            return {"stop_reason": stop}
        if tools.budget.research_exhausted():
            return {"stop_reason": "budget_exhausted"}

        pages = state.get("search_results", [])[:tools.max_pages_per_round]
        total = len(pages)
        candidates: list[CandidateEvidence] = list(
            state.get("candidate_evidence", []))

        for n, result in enumerate(pages, start=1):
            if not tools.budget.start_page():   # 抓取页数熔断(§3.6 ≤12)
                tools.emit("warning", {"stage": "reader",
                                       "detail": "页数上限, 停止抓取"})
                break
            tools.emit("reading", {"url": result.url, "title": result.title,
                                   "n": n, "N": total})
            try:
                page: ExtractedPage = asyncio.run(tools.fetch_async(
                    result.url, allowed_domains=tools.allowed_domains,
                    proxy=tools.proxy))
            except Exception as e:  # noqa: BLE001
                tools.emit("warning", {"stage": "reader",
                                       "detail": f"抓取/提取失败 {result.url}: {e}"})
                continue

            prompt = (
                f"研究主题: {state['topic']}\n"
                f"子问题: {state.get('sub_questions', [])}\n\n"
                "以下是网页正文。提取 1~3 条与主题相关的要点;每条要点必须附带"
                "一条**逐字摘自正文**的原文片段(quote, ≤100 字, 不得改写任何字,"
                "只能整段摘录)。只输出 JSON: "
                '{"points": [{"point": "...", "quote": "..."}]}\n\n正文:\n'
                f"{page.text[:_MAX_PROMPT_CHARS]}")
            try:
                result_llm = tools.llm_chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=_READER_MAX_TOKENS, tier="daily",
                    reasoning_effort="low")  # 机械摘录任务, 压制思考省配额
            except Exception as e:  # noqa: BLE001
                tools.emit("warning", {"stage": "reader",
                                       "detail": f"摘要失败 {result.url}: {e}"})
                continue
            tools.budget.settle_llm(result_llm.usage.get("total_tokens", 0),
                                    for_writer=False)

            obj = _json_obj(result_llm.content) or {}
            added_for_page = 0
            domain = _domain_of(page.url)
            try:
                stype = source_type_for_domain(domain)
            except ValueError:
                continue  # 不在来源类型登记表内(不应发生: 白名单已过滤)
            for p in obj.get("points", [])[:3]:
                locate = locate_quote(str(p.get("quote", "")), page.text)
                if not locate.validated:
                    continue  # quote 无法定位 → 不入候选(§3.3)
                candidates.append(CandidateEvidence(
                    url=page.url, title=result.title, domain=domain,
                    source_type=stype, quote=locate.quote,
                    point=str(p.get("point", ""))[:500],
                    content_hash=_hash_text(page.text)))
                added_for_page += 1
            if added_for_page == 0:
                tools.emit("warning", {"stage": "reader",
                                       "detail": f"该页无有效证据 {result.url}"})
        return {"candidate_evidence": candidates}
    return reader


def _hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_merger(tools: GraphTools):
    def merger(state: ResearchState) -> dict:
        existing = list(state.get("evidence", []))
        added = merge_candidates(existing,
                                 state.get("candidate_evidence", []))
        for e in added:  # note 事件由 merger 编号后发送(§3.4)
            tools.emit("note", {"evidence_id": e.evidence_id,
                                "origin_group_id": e.origin_group_id,
                                "url": e.url, "title": e.title,
                                "point": e.point})
        return {"evidence": existing + added}
    return merger


def _program_note(state: ResearchState, reason: str) -> str:
    """程序生成的说明(§3.4:总额度/超时/无证据时不再调用模型)。"""
    lines = [f"# 研究未能完成", "",
             f"针对问题「{state['topic']}」,{reason}", "",
             "本说明由程序生成,未经模型撰写,不包含未经核实的研究结论。"]
    pending = state.get("pending_links", [])
    if pending:
        lines += ["", "以下来源未核实(集合外, 仅供人工参考):"]
        lines += [f"- {r.title} {r.url}" for r in pending]
    return "\n".join(lines)


_REASON_TEXT = {
    "total_budget_exhausted": "任务总额度已耗尽,为控制成本未再调用模型。",
    "timeout": "任务超出总时限,研究被强制停止。",
    "execution_error": "研究过程发生程序异常。",
    "no_new_evidence": "未能获取到任何可核实的证据,无法生成有依据的报告。",
}


def make_writer(tools: GraphTools):
    def writer(state: ResearchState) -> dict:
        stop = _control_stop(state, tools.budget)
        evidence = state.get("evidence", [])
        if stop:
            note = _program_note(state, _REASON_TEXT.get(stop, "研究被终止。"))
            tools.emit("report_delta", {"md": note, "draft": True})
            return {"report_md": note, "citation_map": {},
                    "stop_reason": stop}
        if not evidence:
            # 已有研究类 stop_reason(如 budget_exhausted)保持, 不被覆盖
            sr = state.get("stop_reason") or "no_new_evidence"
            note = _program_note(state, _REASON_TEXT.get(
                sr, "未能获取到任何可核实的证据,无法生成有依据的报告。"))
            tools.emit("report_delta", {"md": note, "draft": True})
            return {"report_md": note, "citation_map": {}, "stop_reason": sr}

        lines = []
        for i, e in enumerate(evidence, start=1):
            lines.append(f"[{i}] {e.evidence_id} | {e.title} | "
                         f"{e.domain} | {e.source_type}\n"
                         f"    原文片段: {e.quote}\n    要点: {e.point}")
        prompt = (
            f"根据下列已核实证据写一份中文研究报告,回答: {state['topic']}\n\n"
            "硬性规则:\n"
            "1. 只能引用给出的证据编号,形式为 [1] [2];禁止编造编号;"
            "禁止输出任何 Markdown 链接或 URL。\n"
            "2. 每条实质性断言都要有对应引用;无证据支持的猜测不得写入。\n"
            "3. 结构:# 标题、结论段、详情段、局限性段(说明证据覆盖的不足)。\n\n"
            "证据池:\n" + "\n".join(lines))
        result = tools.llm_chat([{"role": "user", "content": prompt}],
                                max_tokens=_WRITER_MAX_TOKENS,
                                tier="high_quality")
        tools.budget.settle_llm(result.usage.get("total_tokens", 0),
                                for_writer=True)

        check = check_report(result.content, evidence)
        if check.valid:
            final, usage_extra = result.content, {}
        else:
            final, usage_extra = revise_report(result.content, evidence,
                                               tools.llm_chat)
            if usage_extra:
                tools.budget.settle_llm(
                    usage_extra.get("total_tokens", 0), for_writer=True)

        tools.emit("report_delta", {"md": final, "draft": True})
        final_map = check_report(final, evidence).citation_map
        sr = state.get("stop_reason") or "single_pass"
        return {"report_md": final, "citation_map": final_map,
                "stop_reason": sr}
    return writer


def build_graph(tools: GraphTools):
    g = StateGraph(ResearchState)
    g.add_node("planner", make_planner(tools))
    g.add_node("searcher", make_searcher(tools))
    g.add_node("reader", make_reader(tools))
    g.add_node("merger", make_merger(tools))
    g.add_node("writer", make_writer(tools))
    g.add_edge(START, "planner")
    g.add_edge("planner", "searcher")
    g.add_edge("searcher", "reader")
    g.add_edge("reader", "merger")
    g.add_edge("merger", "writer")
    g.add_edge("writer", END)
    return g.compile()


async def run_research(tools: GraphTools, topic: str, *, task_id: str) -> dict:
    tools.budget.reserve_writer()  # writer 预留每任务一次(§3.6)
    app = build_graph(tools)
    init: ResearchState = {
        "topic": topic, "task_id": task_id, "sub_questions": [],
        "planned_query": "", "search_results": [], "pending_links": [],
        "search_rounds": [], "candidate_evidence": [], "evidence": [],
        "round_no": 1, "stop_reason": None, "report_md": "",
        "citation_map": {},
    }
    return dict(await app.ainvoke(init))
