"""LangGraph 线性链路测试(planner→searcher→reader→merger→writer, §3.2)。

全部工具层用 fake 注入, 离线验证编排、预算熔断、warning 路径与 stop_reason。
"""
import asyncio
import json

from orca import graph
from orca.budget import Budget
from orca.extract import ExtractedPage
from orca.llm import LLMResult
from orca.search import SearchResult

ALLOWED = {"docs.python.org", "developer.mozilla.org"}

PLANNER_JSON = json.dumps({"sub_questions": ["Q1", "Q2"],
                           "query": "Python 3.13 新特性"}, ensure_ascii=False)

PAGE_A = ("Python 3.13 引入了实验性的自由线程模式,可禁用全局解释器锁。"
          "交互式解释器支持多行编辑与彩色提示。")
PAGE_B = ("错误消息更加友好,会指出常见的拼写错误并给出修正建议。")


def reader_json(quotes):
    return json.dumps({"points": [{"point": f"要点{i}", "quote": q}
                                  for i, q in enumerate(quotes)]},
                      ensure_ascii=False)


WRITER_REPORT = ("# Python 3.13 研究报告\n\n"
                 "自由线程是本版核心特性 [1]。\n\n"
                 "错误消息改进同样显著 [2]。\n")


def make_budget(total_llm=200_000, reserve=8_000, credits=16, pages=12,
                time_s=480.0, clock=lambda: 0.0):
    return Budget(total_llm_tokens=total_llm,
                  writer_reserve_tokens=reserve,
                  max_tavily_credits=credits, max_pages=pages,
                  time_budget_s=time_s, clock=clock)


def make_tools(llm_sides, search_results=None, fetch_failures=None,
               budget=None, search_error=None):
    """llm_sides: 按调用序返回的 content 列表;fetch_failures: {url: Exception}。"""
    calls = {"llm": [], "fetch": [], "search": []}
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    def llm_chat(messages, *, max_tokens, tier, reasoning_effort=None):
        calls["llm"].append({"tier": tier, "max_tokens": max_tokens,
                             "messages": messages})
        content = llm_sides.pop(0)
        if isinstance(content, Exception):
            raise content
        return LLMResult(content=content, usage=dict(usage))

    def search_fn(query, *, limit):
        calls["search"].append(query)
        if search_error is not None:
            raise search_error
        return (search_results or [], 1)

    async def fetch_async(url, *, allowed_domains=None, proxy=None):
        calls["fetch"].append(url)
        if fetch_failures and url in fetch_failures:
            raise fetch_failures[url]
        text = {"https://docs.python.org/a": PAGE_A,
                "https://docs.python.org/b": PAGE_B}[url]
        return ExtractedPage(url=url, final_url=url, text=text)

    events = []
    return graph.GraphTools(
        llm_chat=llm_chat, search_fn=search_fn, fetch_async=fetch_async,
        budget=budget or make_budget(), emit=lambda e, p: events.append((e, p)),
        allowed_domains=ALLOWED,
    ), events, calls


def default_search_results():
    return [
        SearchResult(url="https://docs.python.org/a", title="What's New",
                     snippet="s1"),
        SearchResult(url="https://docs.python.org/b", title="Error messages",
                     snippet="s2"),
        SearchResult(url="https://evil.example.com/x", title="外部页",
                     snippet="s3"),
    ]


def happy_llm_sides():
    return [PLANNER_JSON,
            reader_json(["自由线程模式,可禁用全局解释器锁",
                         "交互式解释器支持多行编辑与彩色提示"]),
            reader_json(["错误消息更加友好"]),
            WRITER_REPORT]


def test_evidence_carries_fetched_at():
    """reader 产出的证据带抓取时间戳(§10.1 轨迹可追溯: 断言的
    evidence_ids 须能经 run 快照/落库追溯 quote 与抓取时间)。"""
    tools, _e, _c = make_tools(happy_llm_sides(),
                               search_results=default_search_results())
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_fat"))
    assert state["evidence"]
    for ev in state["evidence"]:
        assert ev.fetched_at  # ISO 时间戳
        assert ev.fetched_at.endswith("+00:00")  # 与 db._now 一致用 UTC


def test_happy_path_single_pass():
    tools, events, calls = make_tools(happy_llm_sides(),
                                      search_results=default_search_results())
    state = asyncio.run(graph.run_research(tools, "Python 3.13 新特性?",
                                           task_id="t_test1"))

    assert state["stop_reason"] == "single_pass"
    assert [e.evidence_id for e in state["evidence"]] == \
        ["ev_001", "ev_002", "ev_003"]
    assert state["citation_map"] == {"1": "ev_001", "2": "ev_002"}
    assert state["sub_questions"] == ["Q1", "Q2"]
    names = [e for e, _ in events]
    assert names[:2] == ["plan", "search"]
    assert names.count("reading") == 2
    assert names.count("note") == 3
    assert names[-1] == "report_delta"
    # 集合外不抓正文
    assert "https://evil.example.com/x" not in calls["fetch"]
    # writer 用高质量模型
    assert calls["llm"][-1]["tier"] == "high_quality"
    # LLM usage 已入账(planner+2页 reader+writer = 4 × 150)
    assert tools.budget.usage_snapshot()["llm_tokens"] == 600


def test_out_of_allowlist_listed_as_pending():
    tools, _events, calls = make_tools(happy_llm_sides(),
                                       search_results=default_search_results())
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test2"))
    assert any(l.url == "https://evil.example.com/x"
               for l in state["pending_links"])
    assert len(calls["fetch"]) == 2


def test_fetch_failure_emits_warning_and_continues():
    tools, events, _ = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         WRITER_REPORT],
        search_results=default_search_results(),
        fetch_failures={"https://docs.python.org/b": Exception("超时")})
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test3"))

    assert any(e == "warning" for e, _ in events)
    assert [e.evidence_id for e in state["evidence"]] == ["ev_001", "ev_002"]
    assert state["stop_reason"] == "single_pass"
    assert "自由线程" in state["report_md"]


def test_research_budget_fuse_stops_research_but_writes_program_note():
    """研究额度耗尽 → budget_exhausted;证据为空时 writer 不调 LLM,
    生成程序说明(§3.6 两级规则)。"""
    b = make_budget(total_llm=200, reserve=100)  # 研究额度仅 100 < fake usage 150
    tools, events, calls = make_tools([PLANNER_JSON], budget=b)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test4"))

    assert state["stop_reason"] == "budget_exhausted"
    assert len(calls["llm"]) == 1               # searcher/reader 未调 LLM
    # §3.4: 程序说明必须说明真实原因(额度耗尽), 不得写成"未找到证据"
    assert "额度" in state["report_md"]
    assert state["citation_map"] == {}


def test_total_budget_exhausted_skips_writer_llm():
    b = make_budget(total_llm=150, reserve=0)   # planner 一次即打穿总额度
    tools, _e, calls = make_tools([PLANNER_JSON], budget=b)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test5"))

    assert state["stop_reason"] == "total_budget_exhausted"
    assert len(calls["llm"]) == 1               # writer 未调用模型
    assert "未能" in state["report_md"]


def test_timeout_short_circuits():
    t = [0.0]
    b = make_budget(time_s=10.0, clock=lambda: t[0])
    tools, _e, calls = make_tools([PLANNER_JSON], budget=b)
    t[0] = 11.0                                  # planner 前即超时
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test6"))

    assert state["stop_reason"] == "timeout"
    assert calls["llm"] == []


def test_invalid_citation_revised_then_valid():
    """writer 报告含越界 [5] → 一次修订成功 → 引用 ID 有效率 100%。"""
    bad_report = "结论 [5] 来自外部。"
    tools, _e, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         bad_report,
         WRITER_REPORT],                      # 第 5 次调用 = 修订
        search_results=default_search_results())
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test7"))

    assert "[5]" not in state["report_md"]
    assert state["citation_map"] == {"1": "ev_001", "2": "ev_002"}
    assert len(calls["llm"]) == 5


def test_invalid_citation_degraded_after_failed_revision():
    """修订仍失败 → 程序化降级(断言保留 + "未经正文核实")。"""
    tools, _e, _c = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁"]),
         "结论 [5] 来自外部。",
         "结论 [9]。"],                        # 修订仍无效
        search_results=default_search_results(),
        fetch_failures={"https://docs.python.org/b": Exception("超时")})
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test8"))

    assert "[5]" not in state["report_md"] and "[9]" not in state["report_md"]
    assert "未经正文核实" in state["report_md"]
    assert "结论" in state["report_md"]          # 断言未被删除


def test_total_search_failure_yields_no_new_evidence():
    tools, events, calls = make_tools([PLANNER_JSON], search_error=Exception("net"))
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test9"))

    assert any(e == "warning" for e, _ in events)
    assert state["stop_reason"] == "no_new_evidence"
    assert state["evidence"] == []
    assert "未能" in state["report_md"]


def test_planner_failure_is_execution_error():
    tools, _e, calls = make_tools([ValueError("bad json")])
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test10"))

    assert state["stop_reason"] == "execution_error"
    assert len(calls["llm"]) == 1


def test_writer_reserved_once():
    tools, _e, _c = make_tools(happy_llm_sides(),
                               search_results=default_search_results())
    asyncio.run(graph.run_research(tools, "Q", task_id="t_test11"))
    assert tools.budget.writer_reserved is True


def test_search_rounds_recorded():
    tools, _e, _c = make_tools(happy_llm_sides(),
                               search_results=default_search_results())
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test12"))
    assert state["search_rounds"] == [
        {"round_no": 1, "query": "Python 3.13 新特性", "result_count": 3,
         "credits_used": 1}]
