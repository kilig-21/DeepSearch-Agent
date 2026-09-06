"""reflector 反思循环测试(计划书 §3.2/§3.5, Phase 2 块 1)。

- 单元:make_reflector 节点函数直接喂 state, §3.5 确定性停止条件逐条覆盖
  (预算/无新增证据/轮次上限/查询重复/控制类优先), 0 真实调用
- 集成:LangGraph 条件边流转(next_queries → searcher)、多轮 evidence_id
  稳定、循环内预算重查、reflect=False 单轮开关

确定性原则(§3.5): LLM 的"我觉得还不够"只能建议继续, 不能越过确定性条件;
确定性条件不满足时根本不调用反思模型。
"""
import asyncio
import json

from orca import graph
from orca.evidence import CandidateEvidence
from orca.llm import LLMResult
from orca.search import SearchResult

from test_graph import (ALLOWED, PAGE_A, PAGE_B, PLANNER_JSON,
                        WRITER_REPORT, default_search_results,
                        make_budget, make_tools, reader_json)

USAGE = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

PAGE_C = "PEP 703 计划移除 GIL,相关进展见后续版本说明。"


def _dummy_evidence(n=1):
    return [CandidateEvidence(url=f"https://docs.python.org/x{i}",
                              title="T", domain="docs.python.org",
                              source_type="official", quote="q", point="p",
                              content_hash=f"h{i}") for i in range(n)]


def reflector_json(sufficient, queries):
    return json.dumps({"sufficient": sufficient, "next_queries": queries},
                      ensure_ascii=False)


NEW_QUERY = "自由线程实验标签何时移除"


# ---- 单元:直接调用 reflector 节点 --------------------------------------------

def reflector_node(llm_sides=None, *, budget=None, max_rounds=3):
    """构造 reflector 节点与其调用记录。llm_sides 仅反思调用消费。"""
    sides = list(llm_sides or [])
    calls = {"llm": []}
    events = []

    def llm_chat(messages, *, max_tokens, tier, reasoning_effort=None):
        calls["llm"].append(messages[-1]["content"])
        content = sides.pop(0)
        if isinstance(content, Exception):
            raise content
        return LLMResult(content=content, usage=dict(USAGE))

    tools = graph.GraphTools(
        llm_chat=llm_chat,
        search_fn=lambda q, *, limit: ([], 0),
        fetch_async=None,
        budget=budget or make_budget(),
        emit=lambda e, p: events.append((e, p)),
        allowed_domains=ALLOWED, reflect=True, max_rounds=max_rounds,
    )
    return graph.make_reflector(tools), tools, events, calls


def rstate(**over):
    """round 1 正常结束的 state:有 1 条历史查询、本轮有新增证据。"""
    s = {
        "topic": "Q", "task_id": "t", "sub_questions": ["Q1"],
        "planned_query": "固定查询", "search_results": [], "pending_links": [],
        "search_rounds": [{"round_no": 1, "query": "固定查询",
                           "result_count": 3, "credits_used": 1}],
        "candidate_evidence": [], "evidence": _dummy_evidence(),
        "last_added_count": 2, "round_no": 1, "stop_reason": None,
        "report_md": "", "citation_map": {}, "next_queries": [],
    }
    s.update(over)
    return s


def reflection_events(events):
    return [p for e, p in events if e == "reflection"]


def test_u1_control_stop_passthrough_no_llm():
    """控制类 stop(已设 timeout)→ reflector 原样透传, 不调反思模型(§3.4)。"""
    node, _tools, events, calls = reflector_node(
        llm_sides=[reflector_json(True, [])])  # 若被消费即失败
    res = node(rstate(stop_reason="timeout"))
    assert res["stop_reason"] == "timeout"
    assert res["next_queries"] == []
    assert calls["llm"] == []
    assert reflection_events(events) == []


def test_u1b_total_exhausted_passthrough_no_llm():
    """总额度打穿(时钟正常)→ 控制类 total_budget_exhausted 透传。"""
    b = make_budget(total_llm=300, reserve=100)
    b.settle_llm(300, for_writer=False)   # 打穿总额度
    node, _tools, events, calls = reflector_node(
        llm_sides=[reflector_json(True, [])], budget=b)
    res = node(rstate())
    assert res["stop_reason"] == "total_budget_exhausted"
    assert calls["llm"] == []


def test_u2_research_exhausted_stops_without_llm():
    """研究额度耗尽(两级规则)→ budget_exhausted 收尾, 不调反思模型(§3.6)。"""
    b = make_budget(total_llm=300, reserve=150)   # 研究额度 150
    b.settle_llm(150, for_writer=False)
    node, _tools, events, calls = reflector_node(
        llm_sides=[reflector_json(True, [])], budget=b)
    res = node(rstate())
    assert res["stop_reason"] == "budget_exhausted"
    assert res["next_queries"] == []
    assert calls["llm"] == []


def test_u3_no_new_evidence_stops_without_llm():
    """本轮无新增有效证据 → no_new_evidence, LLM 不能翻案(§3.5 确定性)。"""
    node, _tools, events, calls = reflector_node(
        llm_sides=[reflector_json(False, [NEW_QUERY])])
    res = node(rstate(last_added_count=0))
    assert res["stop_reason"] == "no_new_evidence"
    assert res["next_queries"] == []
    assert calls["llm"] == []


def test_u4_max_rounds_stops_without_llm():
    """已达轮次上限 → max_rounds, 不调反思模型(§3.5)。"""
    node, _tools, _events, calls = reflector_node(
        llm_sides=[reflector_json(False, [NEW_QUERY])], max_rounds=3)
    res = node(rstate(round_no=3))
    assert res["stop_reason"] == "max_rounds"
    assert res["next_queries"] == []
    assert calls["llm"] == []


def test_u5_sufficient_sets_evidence_sufficient_and_emits():
    """LLM 判充分(确定性条件全满足时才问到它)→ evidence_sufficient。"""
    node, _tools, events, calls = reflector_node(
        llm_sides=[reflector_json(True, [])])
    res = node(rstate())
    assert res["stop_reason"] == "evidence_sufficient"
    assert res["next_queries"] == []
    assert len(calls["llm"]) == 1
    ref = reflection_events(events)
    assert len(ref) == 1
    assert ref[0]["decision"] == "stop"
    assert ref[0]["sufficient"] is True


def test_u6_insufficient_continues_with_next_queries():
    """LLM 判不足且确定性条件全满足 → 产出 next_queries、round_no+1、
    reflection 事件(continue);不写 stop_reason。"""
    node, _tools, events, calls = reflector_node(
        llm_sides=[reflector_json(False, [NEW_QUERY])])
    res = node(rstate())
    assert "stop_reason" not in res
    assert res["next_queries"] == [NEW_QUERY]
    assert res["round_no"] == 2
    assert len(calls["llm"]) == 1
    ref = reflection_events(events)
    assert ref[0]["decision"] == "continue"
    assert ref[0]["next_queries"] == [NEW_QUERY]


def test_u7_duplicate_query_stops():
    """新查询与历史近似重复(仅大小写/标点/空白差异)→ duplicate_queries。"""
    node, _tools, _events, calls = reflector_node(
        llm_sides=[reflector_json(False, ["固定查询?"])])
    res = node(rstate())
    assert res["stop_reason"] == "duplicate_queries"
    assert res["next_queries"] == []
    assert len(calls["llm"]) == 1   # 重复判定在 LLM 产出之后(确定性过滤)


def test_u8_llm_failure_degrades_without_stop():
    """反思模型调用失败 → warning, 退化单轮收尾(不设研究类 stop,
    writer 兜底 single_pass;不冒用 evidence_sufficient)。"""
    node, _tools, events, _calls = reflector_node(
        llm_sides=[Exception("llm down")])
    res = node(rstate())
    assert res == {"next_queries": []}
    warns = [p for e, p in events if e == "warning"]
    assert any(p.get("stage") == "reflector" for p in warns)


def test_u9_invalid_json_degrades():
    node, _tools, events, _calls = reflector_node(
        llm_sides=["抱歉,我无法输出 JSON。"])
    res = node(rstate())
    assert res == {"next_queries": []}
    warns = [p for e, p in events if e == "warning"]
    assert any(p.get("stage") == "reflector" for p in warns)


def test_u10_insufficient_without_queries_degrades():
    """LLM 说不足却给不出查询 → 无处可搜, 退化单轮 + warning。"""
    node, _tools, events, _calls = reflector_node(
        llm_sides=[reflector_json(False, [])])
    res = node(rstate())
    assert res == {"next_queries": []}
    warns = [p for e, p in events if e == "warning"]
    assert any(p.get("stage") == "reflector" for p in warns)


def test_u11_queries_capped_to_3_and_truncated():
    """next_queries 受条数(≤3)与长度(≤200 字)约束(§3.7)。"""
    queries = ["长" * 250, "q1", "q2", "q3", "q4"]
    node, _tools, _events, _calls = reflector_node(
        llm_sides=[reflector_json(False, queries)])
    res = node(rstate())
    assert res["next_queries"] == ["长" * 200, "q1", "q2"]
    assert res["round_no"] == 2


def test_u12_out_of_time_passthrough_no_llm():
    """总时限超限 → timeout 透传(控制类优先, §3.4)。"""
    tick = {"n": 0}

    def clk():
        tick["n"] += 1
        return 0.0 if tick["n"] == 1 else 999.0   # 首次=起点, 其后已超时

    b = make_budget(time_s=10.0, clock=clk)
    node, _tools, _events, calls = reflector_node(
        llm_sides=[reflector_json(True, [])], budget=b)
    res = node(rstate())
    assert res["stop_reason"] == "timeout"
    assert calls["llm"] == []


# ---- 集成:LangGraph 条件边与多轮循环 ------------------------------------------

SEARCH_1 = default_search_results()          # a, b, evil(集合外)
SEARCH_2 = [SearchResult(url="https://docs.python.org/c", title="PEP 703",
                         snippet="s"),
            SEARCH_1[0]]                     # 新页 c + 重复页 a
PAGES = {"https://docs.python.org/a": PAGE_A,
         "https://docs.python.org/b": PAGE_B,
         "https://docs.python.org/c": PAGE_C}


def test_i1_sufficient_single_round_stops_with_report():
    """反思判充分 → evidence_sufficient, 正式报告(非程序说明),
    reflector 调用入账(§3.6 计账范围含 reflector)。"""
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         WRITER_REPORT],
        search_results=SEARCH_1,
        reflect=True,
        reflect_sides=[reflector_json(True, [])])
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_ref1"))

    assert state["stop_reason"] == "evidence_sufficient"
    assert state["report_md"] == WRITER_REPORT
    assert state["citation_map"] == {"1": "ev_001", "2": "ev_002"}
    reflect_calls = [c for c in calls["llm"] if "研究反思器" in
                     c["messages"][-1]["content"]]
    assert len(reflect_calls) == 1
    # planner150 + 2页300 + reflector150 + writer150 = 750(全部入账)
    assert tools.budget.usage_snapshot()["llm_tokens"] == 750
    ref = [p for e, p in events if e == "reflection"]
    assert len(ref) == 1 and ref[0]["decision"] == "stop"


def test_i2_insufficient_loops_back_to_searcher():
    """反思不足 → 条件边回 searcher(消费 next_queries[0])→ 第二轮只抓
    新发现页 → 判充分收尾;evidence_id 跨轮连续不重排(§3.3)。"""
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         reader_json(["PEP 703"]),      # 第 2 轮只抓新页 c(已抓页不重抓)
         WRITER_REPORT],
        search_sides=[SEARCH_1, SEARCH_2],
        pages=PAGES,
        reflect=True,
        reflect_sides=[reflector_json(False, [NEW_QUERY]),
                       reflector_json(True, [])])
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_ref2"))

    # 第二轮搜索使用反思产出的查询
    assert calls["search"] == ["Python 3.13 新特性", NEW_QUERY]
    assert state["round_no"] == 2
    assert [r["round_no"] for r in state["search_rounds"]] == [1, 2]
    # 跨轮 evidence_id 连续: 首轮 3 条 + 第二轮新页 1 条
    assert [e.evidence_id for e in state["evidence"]] == \
        ["ev_001", "ev_002", "ev_003", "ev_004"]
    assert state["stop_reason"] == "evidence_sufficient"
    ref = [p for e, p in events if e == "reflection"]
    assert [r["decision"] for r in ref] == ["continue", "stop"]
    assert ref[0]["next_queries"] == [NEW_QUERY]
    names = [e for e, _ in events]
    assert names.count("search") == 2


def test_i3_max_rounds_stops_loop_without_second_reflection():
    """max_rounds=2:第二轮结束的反思不再调用模型 → max_rounds,
    即便 LLM 想继续也不能越过确定性条件(§3.5)。"""
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         reader_json(["PEP 703"]),
         WRITER_REPORT],
        search_sides=[SEARCH_1, SEARCH_2],
        pages=PAGES,
        reflect=True,
        reflect_sides=[reflector_json(False, [NEW_QUERY])],
        max_rounds=2)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_ref3"))

    assert state["stop_reason"] == "max_rounds"
    assert state["report_md"] == WRITER_REPORT     # 已有证据正常出报告
    reflect_calls = [c for c in calls["llm"] if "研究反思器" in
                     c["messages"][-1]["content"]]
    assert len(reflect_calls) == 1                 # 第二轮反思未调模型
    ref = [p for e, p in events if e == "reflection"]
    assert len(ref) == 1                           # 只有首轮 continue 事件


def test_i4_no_new_evidence_stops_before_second_reflection():
    """第二轮搜索全部命中已见 URL(无新页可抓)→ 本轮无新增证据,
    reflector 不调模型直接 no_new_evidence(§3.5 确定性, LLM 翻不了案)。"""
    dup_search = [SEARCH_1[0], SEARCH_1[1]]        # a, b 全部已见
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         WRITER_REPORT],                           # 第 2 轮无新页, 无摘要调用
        search_sides=[SEARCH_1, dup_search],
        pages=PAGES,
        reflect=True,
        reflect_sides=[reflector_json(False, [NEW_QUERY]),
                       reflector_json(True, [])])   # 第 2 项不应被消费
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_ref4"))

    assert state["stop_reason"] == "no_new_evidence"
    assert calls["search"] == ["Python 3.13 新特性", NEW_QUERY]
    reflect_calls = [c for c in calls["llm"] if "研究反思器" in
                     c["messages"][-1]["content"]]
    assert len(reflect_calls) == 1
    assert [e.evidence_id for e in state["evidence"]] == \
        ["ev_001", "ev_002", "ev_003"]
    assert state["report_md"] == WRITER_REPORT


def test_i5_research_exhausted_at_reflector():
    """第一轮结束时研究额度恰耗尽 → reflector 不调模型,
    budget_exhausted, 已有证据走 writer 预留(§3.6 两级规则)。"""
    # R1 后 total 须盖过 planner 一次最小调用;研究额度 450(= planner 150
    # + 2 页 300)不变: total 2650 − reserve 2200 = 450
    b = make_budget(total_llm=2650, reserve=2200)
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         WRITER_REPORT],
        search_results=SEARCH_1,
        budget=b,
        reflect=True,
        reflect_sides=[reflector_json(True, [])])   # 不应被消费
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_ref5"))

    assert state["stop_reason"] == "budget_exhausted"
    reflect_calls = [c for c in calls["llm"] if "研究反思器" in
                     c["messages"][-1]["content"]]
    assert reflect_calls == []
    assert b.usage_snapshot()["llm_tokens"] == 600   # 研究收尾未越总额度
    assert state["report_md"] == WRITER_REPORT


def test_i6_reflector_llm_failure_degrades_to_single_pass():
    """反思模型故障 → warning + 用已有证据正常出报告,
    stop_reason 兜底 single_pass(不冒用 evidence_sufficient)。"""
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         WRITER_REPORT],
        search_results=SEARCH_1,
        reflect=True,
        reflect_sides=[Exception("llm down")])
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_ref6"))

    assert state["stop_reason"] == "single_pass"
    assert state["report_md"] == WRITER_REPORT
    warns = [p for e, p in events if e == "warning"]
    assert any(p.get("stage") == "reflector" for p in warns)


def test_i7_reflect_false_keeps_linear_graph():
    """reflect=False(单轮对比模式)→ 无反思调用, 行为与 Phase 1 一致。"""
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         WRITER_REPORT],
        search_results=SEARCH_1,
        reflect=False)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_ref7"))

    assert state["stop_reason"] == "single_pass"
    reflect_calls = [c for c in calls["llm"] if "研究反思器" in
                     c["messages"][-1]["content"]]
    assert reflect_calls == []
    assert all(e != "reflection" for e, _ in events)
