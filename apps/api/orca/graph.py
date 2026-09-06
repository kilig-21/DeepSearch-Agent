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
import re
from datetime import UTC, datetime
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict
from urllib.parse import urlparse

from langgraph.graph import END, START, StateGraph

from .budget import Budget, MIN_USABLE_OUTPUT, PROMPT_MARGIN
from .citations import check_report, degrade_citations, revise_report
from .llm import LLMError
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
# glm-5.3 推理型: 思考段与正文共享 max_tokens(probe T9);在线实测
# (2026-09-06 conflict_typing 题 3/3)8192 会被思考吃穿(length 截断、
# content 0 片段)→ 提高一倍给思考留余量(probe 结论: 调用必须给足)
_WRITER_MAX_TOKENS = 16384
_REVISE_MAX_TOKENS = 8192   # 引用修订(citations.revise_report 原默认值)


def _below_min_output(tools: GraphTools, requested: int,
                      prompt_text: str) -> int:
    """调用前约束(R1): 返回 clamp 后的输出配额;额度不足以完成一次
    最小有效调用(< MIN_USABLE_OUTPUT, 可为负)时调用方不得发起调用。
    prompt 估算按 len(text)(中文 1 字 ≈ 1 token 持平, 英文高估),
    边际由 Budget.max_output_tokens 内的 PROMPT_MARGIN 统一加。"""
    return tools.budget.max_output_tokens(requested, len(prompt_text))


class ResearchState(TypedDict):
    topic: str
    task_id: str
    sub_questions: list[str]
    planned_query: str
    search_results: list[SearchResult]   # 白名单内(可抓正文)
    pending_links: list[SearchResult]    # 集合外待核实链接(不抓)
    seen_urls: list[str]                 # 跨轮已见 URL(循环不重复抓取)
    search_rounds: list[dict]
    candidate_evidence: list[CandidateEvidence]
    evidence: list[CandidateEvidence]    # merger 整体写回(§3.1)
    last_added_count: int                # 本轮 merger 新增证据数(§3.5 判定用)
    next_queries: list[str]              # reflector 产出的下一轮查询(§3.1)
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
    # (messages, *, max_tokens, tier) -> (片段迭代器, usage 容器);writer 流式
    llm_chat_stream: Callable | None = None
    max_pages_per_round: int = _TOP_N
    reflect: bool = True        # Phase 2 反思循环开关(§3.2);False=单轮对比模式
    max_rounds: int = 3         # 轮次上限(§3.1)
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
        prompt = (
            f"你是研究规划器。把用户问题拆解为 2~4 个可搜索的中文子问题,"
            f"并给出 1 个首轮搜索查询。只输出 JSON:"
            f'{{"sub_questions": ["..."], "query": "..."}}\n\n'
            f"用户问题: {state['topic']}")
        allowed = _below_min_output(tools, _READER_MAX_TOKENS, prompt)
        if allowed < MIN_USABLE_OUTPUT:
            # R1 调用前约束: 总额度连一次最小有效调用的估算成本都盖不住
            tools.emit("warning", {
                "stage": "planner",
                "detail": f"剩余额度不足(可用输出 {allowed} < 最小阈值 "
                          f"{MIN_USABLE_OUTPUT}), 不调用模型"})
            return {"stop_reason": "total_budget_exhausted"}
        try:
            result = tools.llm_chat(
                [{"role": "user", "content": prompt}],
                max_tokens=allowed, tier="daily",
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

        # 反思循环轮次消费 reflector 产出的查询(§3.2);首轮用 planner 查询
        nq = state.get("next_queries") or []
        query = nq[0] if nq else (state.get("planned_query") or state["topic"])
        try:
            results, credits = tools.search_fn(query, limit=8)
        except Exception as e:  # noqa: BLE001
            tools.emit("warning", {"stage": "searcher",
                                   "detail": f"搜索失败: {e}"})
            return {"stop_reason": "no_new_evidence"}

        # 循环模式跨轮去重(§3.2):仅本轮新发现的 URL 喂 reader——已抓页
        # 不重复抓取/摘要(控制 token);事件与轮记录只展示本轮结果
        seen = set(state.get("seen_urls", []))
        fresh = [r for r in results if r.url not in seen]
        seen.update(r.url for r in results)
        allowed, outside = split_by_allowlist(fresh, tools.allowed_domains)
        tools.emit("search", {"round": state["round_no"], "query": query,
                              "results": [{"url": r.url, "title": r.title}
                                          for r in dedup(results)],
                              "credits_used": credits})
        rounds = list(state.get("search_rounds", [])) + [{
            "round_no": state["round_no"], "query": query,
            "result_count": len(dedup(results)), "credits_used": credits}]
        pending = list(state.get("pending_links", [])) + outside
        return {"search_results": allowed, "pending_links": dedup(pending),
                "search_rounds": rounds, "seen_urls": sorted(seen)}
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

        def _budget_stop() -> str | None:
            """篇间/摘要前重查(§3.6):控制类即时终止, 研究耗尽收尾保留证据。"""
            if budget_stop := _control_stop(state, tools.budget):
                return budget_stop
            if tools.budget.research_exhausted():
                return "budget_exhausted"
            return None

        for n, result in enumerate(pages, start=1):
            if (s := _budget_stop()) is not None:
                return {"candidate_evidence": candidates, "stop_reason": s}
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

            # 抓取可能耗时: 摘要(模型调用)前再查一次预算/时限(第四轮评审 P1)
            if (s := _budget_stop()) is not None:
                return {"candidate_evidence": candidates, "stop_reason": s}

            prompt = (
                f"研究主题: {state['topic']}\n"
                f"子问题: {state.get('sub_questions', [])}\n\n"
                "以下是网页正文。提取 1~3 条与主题相关的要点;每条要点必须附带"
                "一条**逐字摘自正文**的原文片段(quote, ≤100 字, 不得改写任何字,"
                "只能整段摘录)。只输出 JSON: "
                '{"points": [{"point": "...", "quote": "..."}]}\n\n正文:\n'
                f"{page.text[:_MAX_PROMPT_CHARS]}")
            allowed = _below_min_output(tools, _READER_MAX_TOKENS, prompt)
            if allowed < MIN_USABLE_OUTPUT:
                # R1 调用前约束: 剩余额度不足以摘要(剩余不会回升)→ 停止
                # 摘要, 已有候选证据保留, 后续交 reflector 确定性判定
                tools.emit("warning", {
                    "stage": "reader",
                    "detail": f"剩余额度不足(可用输出 {allowed} < 最小阈值 "
                              f"{MIN_USABLE_OUTPUT}), 停止本页起的摘要"})
                break
            try:
                result_llm = tools.llm_chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=allowed, tier="daily",
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
                    content_hash=_hash_text(page.text),
                    fetched_at=datetime.now(UTC).isoformat(timespec="seconds")))
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
        return {"evidence": existing + added, "last_added_count": len(added)}
    return merger


# ---- reflector(Phase 2, §3.2/§3.5)------------------------------------------

_QUERY_NOISE_RE = re.compile(
    r"[\s?？!！,，.。;；:：'\"“”‘’()（）\[\]【】]+")


def _norm_query(q: str) -> str:
    """查询近似重复判定用规范化:去空白/常见中英标点 + 小写。"""
    return _QUERY_NOISE_RE.sub("", q).lower()


_MAX_NEXT_QUERIES = 3     # reflector 产出的下一轮查询条数上限(§3.7)
_MAX_QUERY_CHARS = 200


def make_reflector(tools: GraphTools):
    """merger 后评估证据覆盖度, 决定继续检索或收尾(§3.5)。

    确定性停止条件(全部满足才进入下一轮):预算未耗尽、本轮有新增有效
    证据、未达轮次上限、新查询与历史不近似重复——任一不满足即按对应
    stop_reason 终止,**不调用反思模型**;LLM 的"我觉得还不够"只能建议,
    不能越过这些条件。控制类 stop(§3.4)优先透传。
    """
    def reflector(state: ResearchState) -> dict:
        # 1. 控制类优先(§3.4):取消/超时/总额度直接决定终态
        stop = _control_stop(state, tools.budget)
        if stop:
            return {"stop_reason": stop, "next_queries": []}
        # 2. 研究额度耗尽(两级规则 §3.6)→ 停止研究走 writer, 不调模型
        if tools.budget.research_exhausted():
            return {"stop_reason": "budget_exhausted", "next_queries": []}
        # 3. 本轮无新增有效证据 → 再搜同类查询无意义(确定性, LLM 翻不了案)
        if not state.get("last_added_count"):
            return {"stop_reason": "no_new_evidence", "next_queries": []}
        # 4. 轮次上限(§3.1)——只表示停止, 不代表证据充分
        if state["round_no"] >= tools.max_rounds:
            return {"stop_reason": "max_rounds", "next_queries": []}

        ev_lines = [f"- {e.point[:120]}({e.domain})"
                    for e in state.get("evidence", [])]
        used = [r.get("query", "") for r in state.get("search_rounds", [])]
        prompt = (
            "你是研究反思器。评估已有证据是否足以回答用户问题;若不足,"
            "给出 1~3 条**下一轮搜索查询**用于补齐证据缺口(不得与已执行"
            "查询近似重复)。只输出 JSON:\n"
            '{"sufficient": true/false, "next_queries": ["..."]}\n\n'
            f"用户问题: {state['topic']}\n"
            f"子问题: {state.get('sub_questions', [])}\n"
            f"已执行查询: {used}\n"
            f"证据池({len(state.get('evidence', []))} 条要点):\n"
            + ("\n".join(ev_lines) or "(空)"))
        allowed = _below_min_output(tools, _READER_MAX_TOKENS, prompt)
        if allowed < MIN_USABLE_OUTPUT:
            # R1 调用前约束: 剩余额度不足以反思 → 退化单轮收尾, 不调模型
            tools.emit("warning", {
                "stage": "reflector",
                "detail": f"剩余额度不足(可用输出 {allowed} < 最小阈值 "
                          f"{MIN_USABLE_OUTPUT}), 不调用反思模型"})
            return {"next_queries": []}
        try:
            result = tools.llm_chat(
                [{"role": "user", "content": prompt}],
                max_tokens=allowed, tier="daily",
                reasoning_effort="low")  # 机械评估任务, 压制思考省配额
        except Exception as e:  # noqa: BLE001
            tools.emit("warning", {"stage": "reflector",
                                   "detail": f"反思失败: {e}"})
            return {"next_queries": []}   # 退化单轮收尾, writer 兜底 stop_reason
        tools.budget.settle_llm(result.usage.get("total_tokens", 0),
                                for_writer=False)

        obj = _json_obj(result.content)
        if obj is None:
            tools.emit("warning", {"stage": "reflector",
                                   "detail": "反思输出无法解析, 停止研究"})
            return {"next_queries": []}

        if obj.get("sufficient"):
            tools.emit("reflection", {
                "round": state["round_no"], "decision": "stop",
                "sufficient": True, "next_queries": []})
            return {"stop_reason": "evidence_sufficient", "next_queries": []}

        queries, seen = [], {_norm_query(q) for q in used}
        raw = [q for q in (str(x).strip()[:_MAX_QUERY_CHARS]
                           for x in obj.get("next_queries", [])) if q]
        for q in raw[:_MAX_NEXT_QUERIES]:
            if _norm_query(q) not in seen:
                seen.add(_norm_query(q))
                queries.append(q)
        if not queries:
            if raw:
                # 给出的查询全部与历史近似重复 → 无新信息可搜(§3.4)
                return {"stop_reason": "duplicate_queries", "next_queries": []}
            # 判不足却给不出查询 → 无处可搜, 退化单轮收尾
            tools.emit("warning", {"stage": "reflector",
                                   "detail": "反思未产出有效新查询, 停止研究"})
            return {"next_queries": []}
        tools.emit("reflection", {
            "round": state["round_no"], "decision": "continue",
            "sufficient": False, "next_queries": queries})
        return {"next_queries": queries, "round_no": state["round_no"] + 1}
    return reflector


def _route_after_reflection(state: ResearchState) -> str:
    """条件边(§3.2):有 next_queries → searcher 继续;否则 → writer 收尾。"""
    return "searcher" if state.get("next_queries") else "writer"


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
    "budget_exhausted": "研究额度已耗尽(§3.6 两级预算规则),研究阶段停止。",
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
        allowed = _below_min_output(tools, _WRITER_MAX_TOKENS, prompt)
        if allowed < MIN_USABLE_OUTPUT:
            # R1 调用前约束: 剩余额度不足以完成一次最小有效写作 → 不调用,
            # 程序说明(防御纵深:全链路下多被研究侧/两级规则提前拦截)
            note = _program_note(
                state, "剩余额度不足以完成一次最小模型调用,为控制成本"
                       "未再调用模型。")
            tools.emit("warning", {
                "stage": "writer",
                "detail": f"剩余额度不足(可用输出 {allowed} < 最小阈值 "
                          f"{MIN_USABLE_OUTPUT}), 不调用模型写报告"})
            tools.emit("report_delta", {"md": note, "draft": True})
            return {"report_md": note, "citation_map": {},
                    "stop_reason": "total_budget_exhausted"}
        messages = [{"role": "user", "content": prompt}]
        streamed = False
        if tools.llm_chat_stream is not None:
            # 流式(§3.4 草稿):逐片段 emit, 片段间经过取消检查点——
            # 取消在流式过程中即可生效(第四轮评审 P2)
            gen, usage_box = tools.llm_chat_stream(
                messages, max_tokens=allowed, tier="high_quality")
            pieces: list[str] = []
            try:
                for piece in gen:
                    pieces.append(piece)
                    tools.emit("report_delta", {"md": piece, "draft": True})
            except Exception:
                # R2 分账: usage 帧先于正文到达(空流/上游错误), 取消检查点
                # 也可能在流中抛出——usage_box 已有值即已知成本, 先 settle
                # 再传播(usage 是事实, 禁止丢账; settle 语义不变)
                if usage_box:
                    tools.budget.settle_llm(
                        usage_box.get("total_tokens", 0), for_writer=True)
                raise
            finally:
                # 提前退出(取消等)时显式关闭生成器, 关闭底层 HTTP 流
                # 上下文(第五轮评审 R4)
                gen.close()
            tools.budget.settle_llm(usage_box.get("total_tokens", 0),
                                    for_writer=True)
            content = "".join(pieces)
            streamed = True
        else:
            result = tools.llm_chat(messages, max_tokens=allowed,
                                    tier="high_quality")
            tools.budget.settle_llm(result.usage.get("total_tokens", 0),
                                    for_writer=True)
            if not result.content.strip():
                # R3: 非流式空正文与流式空内容同口径显式失败(c76a8b8),
                # 交由 TaskManager 转 task_failed, 不允许空报告落库;
                # 该次调用的成本已在上方入账
                raise LLMError("非流式响应空内容: 正文为空")
            content = result.content
            streamed = False

        check = check_report(content, evidence)
        if check.valid:
            final, usage_extra = content, {}
            if not streamed:  # 非流式: 一次性草稿帧(现状行为)
                tools.emit("report_delta", {"md": final, "draft": True})
        else:
            # 修订要再调一次模型(第五轮评审 R3;R1 调用前约束):总额度/
            # 时限已耗尽,或剩余额度不足以完成一次最小有效修订时,不得调
            # 模型——直接走确定性降级(移除无效引用+句尾标注), 不调模型;
            # stop_reason 保持研究类真实值不变。revise prompt ≈ 报告全文
            # + 固定说明与证据列表(保守 +800 字)
            rev_allowed = tools.budget.max_output_tokens(
                _REVISE_MAX_TOKENS, len(content) + 800)
            if (tools.budget.total_exhausted() or tools.budget.out_of_time()
                    or rev_allowed < MIN_USABLE_OUTPUT):
                tools.emit("warning", {
                    "stage": "writer",
                    "detail": "总额度/时限已耗尽或剩余额度不足, 引用修订"
                              "不调模型, 按程序化降级处理引用"})
                final = degrade_citations(content, evidence)
            else:
                final, usage_extra = revise_report(content, evidence,
                                                   tools.llm_chat,
                                                   max_tokens=rev_allowed)
                if usage_extra:
                    tools.budget.settle_llm(
                        usage_extra.get("total_tokens", 0), for_writer=True)
            # 修订正文与已发草稿不一致 → replace 帧让前端整体替换草稿
            tools.emit("report_delta",
                       {"md": final, "draft": True, "replace": True})

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
    if tools.reflect:   # Phase 2 反思循环(§3.2):merger → reflector → 条件边
        g.add_node("reflector", make_reflector(tools))
        g.add_edge("merger", "reflector")
        g.add_conditional_edges("reflector", _route_after_reflection,
                                {"searcher": "searcher", "writer": "writer"})
    else:               # 单轮对比模式(§10.4), 与 Phase 1 线性链一致
        g.add_edge("merger", "writer")
    g.add_edge("writer", END)
    return g.compile()


async def run_research(tools: GraphTools, topic: str, *, task_id: str) -> dict:
    tools.budget.reserve_writer()  # writer 预留每任务一次(§3.6)
    app = build_graph(tools)
    init: ResearchState = {
        "topic": topic, "task_id": task_id, "sub_questions": [],
        "planned_query": "", "search_results": [], "pending_links": [],
        "seen_urls": [], "search_rounds": [], "candidate_evidence": [],
        "evidence": [],
        "last_added_count": 0, "next_queries": [],
        "round_no": 1, "stop_reason": None, "report_md": "",
        "citation_map": {},
    }
    return dict(await app.ainvoke(init))
