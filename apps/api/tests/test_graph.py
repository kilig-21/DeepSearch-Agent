"""LangGraph 线性链路测试(planner→searcher→reader→merger→writer, §3.2)。

全部工具层用 fake 注入, 离线验证编排、预算熔断、warning 路径与 stop_reason。
"""
import asyncio
import json

import pytest

from orca import graph
from orca.budget import Budget
from orca.evidence import CandidateEvidence
from orca.extract import ExtractedPage
from orca.llm import LLMError, LLMResult
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
               budget=None, search_error=None, llm_stream_chunks=None,
               *, reflect=False, reflect_sides=None, search_sides=None,
               pages=None, max_rounds=3, llm_usage=None,
               llm_stream_error=None):
    """llm_sides: 按调用序返回的 content 列表;fetch_failures: {url: Exception};
    llm_stream_chunks: writer 流式片段列表(提供时 writer 走流式);
    llm_stream_error: 流式 gen 在 usage 帧落账后抛出的异常(复现 R2 空流
    时序: usage 先于异常到达)。
    reflect: 反思循环开关。**本文件与 1B 既有测试默认 False(线性链路回归,
    与 Phase 1 行为一致)**;循环行为测试(test_reflector.py)必须显式传
    reflect=True —— 忘传时 reflect_sides 不会被消费, 断言显式失败不假绿。
    reflect_sides: reflector 专用输出队列(按 prompt 含"研究反思器"分派)。
    search_sides: 按搜索调用序返回的结果列表(多轮测试用);pages: URL→正文映射;
    llm_usage: 自定义 fake usage(默认每次 total 150)。"""
    calls = {"llm": [], "fetch": [], "search": []}
    usage = llm_usage or {"prompt_tokens": 100, "completion_tokens": 50,
                          "total_tokens": 150}
    reflect_sides = list(reflect_sides or [])

    def llm_chat(messages, *, max_tokens, tier, reasoning_effort=None):
        calls["llm"].append({"tier": tier, "max_tokens": max_tokens,
                             "messages": messages})
        prompt = messages[-1]["content"]
        if "研究反思器" in prompt:
            content = reflect_sides.pop(0)
        else:
            content = llm_sides.pop(0)
        if isinstance(content, Exception):
            raise content
        return LLMResult(content=content, usage=dict(usage))

    def llm_chat_stream(messages, *, max_tokens, tier):
        calls["llm"].append({"tier": tier, "max_tokens": max_tokens,
                             "messages": messages, "stream": True})
        usage_box: dict = {}
        chunks = list(llm_stream_chunks or [])

        def gen():
            yield from chunks
            usage_box.update(dict(usage))
            if llm_stream_error is not None:
                raise llm_stream_error

        return gen(), usage_box

    search_sides = list(search_sides) if search_sides is not None else None

    def search_fn(query, *, limit):
        calls["search"].append(query)
        if search_error is not None:
            raise search_error
        if search_sides is not None:
            return (search_sides.pop(0), 1)
        return (search_results or [], 1)

    async def fetch_async(url, *, allowed_domains=None, proxy=None):
        calls["fetch"].append(url)
        if fetch_failures and url in fetch_failures:
            raise fetch_failures[url]
        page_map = pages if pages is not None else {
            "https://docs.python.org/a": PAGE_A,
            "https://docs.python.org/b": PAGE_B}
        return ExtractedPage(url=url, final_url=url, text=page_map[url])

    events = []
    return graph.GraphTools(
        llm_chat=llm_chat,
        llm_chat_stream=llm_chat_stream
        if (llm_stream_chunks is not None or llm_stream_error is not None)
        else None,
        search_fn=search_fn, fetch_async=fetch_async,
        budget=budget or make_budget(), emit=lambda e, p: events.append((e, p)),
        allowed_domains=ALLOWED, reflect=reflect, max_rounds=max_rounds,
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
    # R1 调用前约束后 total 须盖过一次最小调用(planner prompt 估算+1024);
    # 研究额度 150 = total 2000 − reserve 1850, 仍 < fake usage 150 后续
    b = make_budget(total_llm=2000, reserve=1850)
    tools, events, calls = make_tools([PLANNER_JSON], budget=b)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test4"))

    assert state["stop_reason"] == "budget_exhausted"
    assert len(calls["llm"]) == 1               # searcher/reader 未调 LLM
    # §3.4: 程序说明必须说明真实原因(额度耗尽), 不得写成"未找到证据"
    assert "额度" in state["report_md"]
    assert state["citation_map"] == {}


def test_total_budget_exhausted_skips_writer_llm():
    """R1 后更强: 总额度 150 连 planner 一次最小调用的估算成本都盖不住,
    调用前即拦截(planner 不发起调用), 控制类终态直达。"""
    b = make_budget(total_llm=150, reserve=0)   # planner 前即拦截
    tools, _e, calls = make_tools([PLANNER_JSON], budget=b)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_test5"))

    assert state["stop_reason"] == "total_budget_exhausted"
    assert len(calls["llm"]) == 0               # 任何模型调用都未发生
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


# ---- P1:reader 循环内逐篇/摘要前重查预算(第四轮评审) -----------------------

PAGES_4 = {
    "https://docs.python.org/a": PAGE_A,
    "https://docs.python.org/b": PAGE_B,
    "https://docs.python.org/c": "页面 C:PEP 703 相关内容。",
    "https://docs.python.org/d": "页面 D:PEP 669 相关内容。",
}


def _results_4():
    return [SearchResult(url=u, title=f"T{i}", snippet="s")
            for i, u in enumerate(PAGES_4)]


def _make_tools_multi(llm_sides, *, budget=None, clock=None):
    """4 个可抓页面;clock 可选(供 out_of_time 在抓取/摘要间推进)。"""
    calls = {"llm": [], "fetch": []}
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    def llm_chat(messages, *, max_tokens, tier, reasoning_effort=None):
        calls["llm"].append(tier)
        content = llm_sides.pop(0)
        if isinstance(content, Exception):
            raise content
        return LLMResult(content=content, usage=dict(usage))

    def search_fn(query, *, limit):
        return (_results_4(), 1)

    async def fetch_async(url, *, allowed_domains=None, proxy=None):
        calls["fetch"].append(url)
        if clock is not None:
            clock[0] += 100.0  # 抓取耗时: 每页后推进时钟
        return ExtractedPage(url=url, final_url=url, text=PAGES_4[url])

    events = []
    tools = graph.GraphTools(
        llm_chat=llm_chat, search_fn=search_fn, fetch_async=fetch_async,
        budget=budget or make_budget(), emit=lambda e, p: events.append((e, p)),
        allowed_domains=ALLOWED)
    return tools, events, calls


def test_reader_rechecks_research_budget_between_pages():
    """多页任务中途研究额度耗尽 → 剩余页不再抓取/调模型(实际调用次数
    不超预算),已有候选证据保留并走 writer 预留出报告(P1)。"""
    # R1 后 total 须盖过 planner 一次最小调用;研究额度 450(= planner 150
    # + 2 页摘要 300)不变: total 2650 − reserve 2200 = 450
    b = make_budget(total_llm=2650, reserve=2200)
    tools, events, calls = _make_tools_multi(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁"]),
         reader_json(["错误消息更加友好"]),
         WRITER_REPORT],
        budget=b)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_p1a"))

    # 页 3 抓取前已耗尽: 不再抓取, 不再调研究类 LLM
    assert len(calls["fetch"]) == 2
    assert calls["llm"].count("daily") == 3      # planner + 2 页摘要
    assert calls["llm"][-1] == "high_quality"    # 第 4 次 = writer(预留)
    assert b.used_llm_tokens <= b.total_llm_tokens  # 研究未越研究额度(450)
    # 已有候选证据保留, 走 writer(预留)出正式报告
    assert state["stop_reason"] == "budget_exhausted"
    assert len(state["evidence"]) == 2
    assert "自由线程" in state["report_md"]
    assert state["citation_map"]
    assert b.usage_snapshot()["llm_tokens"] == 600  # writer 用预留 150


# ---- P2:writer 流式输出(第四轮评审) ----------------------------------------

def test_writer_streams_delta_chunks_and_usage_settled():
    """writer 走流式:逐片段 emit report_delta(draft=true),片段之和即草稿;
    usage 按流结束的 usage 结算(评审 P2)。"""
    chunks = ["# Python 3.13 研究报告\n\n", "自由线程是本版核心特性 [1]。\n\n",
              "错误消息改进同样显著 [2]。\n"]
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"])],
        search_results=default_search_results(),
        llm_stream_chunks=chunks)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_p2a"))

    deltas = [p for e, p in events if e == "report_delta"]
    assert len(deltas) == len(chunks)               # 逐片段, 每片段一帧
    assert all(p["draft"] is True for p in deltas)
    assert "".join(p["md"] for p in deltas) == WRITER_REPORT  # 片段之和 = 正文
    assert state["report_md"] == WRITER_REPORT
    assert calls["llm"][-1]["stream"] is True
    assert tools.budget.usage_snapshot()["llm_tokens"] == 600  # 4×150, 流 usage 已入账


def test_writer_stream_max_tokens_leaves_room_for_reasoning():
    """glm-5.3 推理型: 思考段与正文共享 max_tokens 配额——在线实测
    (2026-09-06, conflict_typing 题 3/3 复现)8192 被思考吃穿
    (reasoning_tokens=8163、finish_reason=length、content 0 片段),
    流"正常"结束但正文为空。writer 必须给足输出配额(probe T9 同型:
    reader 曾在 4096 上栽过;probe 结论即"调用必须给足 max_tokens")。"""
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"])],
        search_results=default_search_results(),
        llm_stream_chunks=["# 报告\n", "正文 [1]。"])
    asyncio.run(graph.run_research(tools, "Q", task_id="t_writer_mt"))

    writer_calls = [c for c in calls["llm"] if c.get("stream")]
    assert writer_calls, "writer 应走流式"
    assert writer_calls[0]["tier"] == "high_quality"
    assert writer_calls[0]["max_tokens"] >= 16384


def test_writer_stream_revision_replaces_draft():
    """流式草稿校验失败 → 修订后 emit replace 帧(前端整体替换草稿)。"""
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         WRITER_REPORT],                            # 第 4 次 = 修订调用
        search_results=default_search_results(),
        llm_stream_chunks=["草稿片段(含越界 [5])"])
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_p2b"))

    deltas = [p for e, p in events if e == "report_delta"]
    assert deltas[-1]["replace"] is True            # 修订结果替换草稿
    assert deltas[-1]["md"] == WRITER_REPORT
    assert state["report_md"] == WRITER_REPORT


def test_reader_rechecks_time_before_summarize():
    """抓取后、摘要前超时(out_of_time)→ 不调模型, 已抓证据保留(P1)。"""
    t = [0.0]
    b = make_budget(time_s=350.0, clock=lambda: t[0])
    tools, events, calls = _make_tools_multi(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁"]),
         reader_json(["错误消息更加友好"]),
         reader_json(["PEP 703"])],
        budget=b, clock=t)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_p1b"))

    # 页 1 摘要后 t=200;页 2 抓取后 t=300 仍够, 页 3 抓取后 t=400 超时?
    # 每页抓取后 +100: 页1 抓取后 100(摘要前 100<350 → 摘要), 页2 抓取后 200,
    # 页3 抓取后 300, 页4 抓取后 400 → 摘要前 400 > 350 → 停, 证据保留
    assert state["stop_reason"] == "timeout"
    assert len(calls["fetch"]) == 4
    assert len(calls["llm"]) == 4          # planner + 3 页摘要, 第 4 页摘要前停
    assert len(state["evidence"]) == 3


# ---- R3:引用修订不得绕过总预算(第五轮评审) -----------------------------------

def test_revision_skips_llm_when_total_budget_exhausted():
    """修订也是模型调用(R1 调用前约束): writer 后剩余额度不足以完成
    一次最小有效修订 → 引用修订不调模型, 走 degrade_citations 确定性
    降级 + warning 事件;实耗不越上限, stop_reason 保持研究类真实值
    (第五轮评审 R3;原"总额度恰打穿"路径在 R1 clamp 下不可达——writer
    合法调用后必剩 prompt 估算+边际, 故以额度不足触发同一降级分支)。
    llm_sides 只提供 4 侧: 修订若意外调模型将 pop 空列表报错。"""
    b = make_budget(total_llm=3300, reserve=0)  # fake usage 400/次
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"]),
         "结论 [5] 来自外部。"],                    # writer 主调用输出无效引用
        search_results=default_search_results(),
        budget=b, llm_usage={"prompt_tokens": 250,
                             "completion_tokens": 150,
                             "total_tokens": 400})
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_r3a"))

    assert len(calls["llm"]) == 4                   # 修订未调模型(无第 5 侧)
    assert "[5]" not in state["report_md"]
    assert "未经正文核实" in state["report_md"]      # degrade_citations 结果
    assert "结论" in state["report_md"]              # 断言未被删除
    warnings = [p for e, p in events if e == "warning"]
    assert any(p.get("stage") == "writer" and "额度" in p.get("detail", "")
               for p in warnings)
    assert b.usage_snapshot()["llm_tokens"] <= 3300  # 实耗不越总上限
    assert state["stop_reason"] == "single_pass"    # 研究类真实值保持不变


# ---- 修复轮 R1:预算从"事后记账"升级为"调用前约束" ---------------------------

def _ev(n=1, quote="自由线程模式,可禁用全局解释器锁", point="自由线程定义"):
    return CandidateEvidence(
        url=f"https://docs.python.org/p{n}", title=f"来源{n}",
        domain="docs.python.org", source_type="doc", quote=quote,
        point=point, content_hash="h", evidence_id=f"ev_{n:03d}")


def test_planner_not_called_when_total_below_min_usable():
    """R1c 复现 budget_total(上限 160):总额度连一次最小有效调用的
    prompt 估算都盖不住 → planner 不发起调用, 直接控制类终态, 实耗 0。"""
    b = make_budget(total_llm=160, reserve=80)
    tools, events, calls = make_tools([PLANNER_JSON], budget=b)
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_r1a"))

    assert calls["llm"] == []                       # 调用前拦截
    assert b.used_llm_tokens == 0
    assert state["stop_reason"] == "total_budget_exhausted"
    assert "总额度" in state["report_md"]            # 程序说明
    assert any(e == "warning" and "剩余额度" in p.get("detail", "")
               for e, p in events)


def test_writer_max_tokens_clamped_to_remaining():
    """R1c 复现场景:研究已耗 38000,研究侧 3 次调用(fake 每次 1500)
    后 42500;writer 请求 16384 被 clamp 到剩余可容纳值, 全程 ≤ 50000。"""
    b = make_budget(total_llm=50_000, reserve=8_000)
    b.settle_llm(38_000, for_writer=False)          # 模拟研究前期已耗
    tools, events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"])],
        search_results=default_search_results(),
        llm_stream_chunks=["# 报告\n", "正文 [1]。"],
        budget=b, llm_usage={"prompt_tokens": 1000,
                             "completion_tokens": 500,
                             "total_tokens": 1500})
    state = asyncio.run(graph.run_research(tools, "Q", task_id="t_r1b"))

    wc = [c for c in calls["llm"] if c.get("stream")]
    assert wc, "writer 应走流式"
    wp = wc[0]["messages"][-1]["content"]
    # 42500 = 预充 38000 + 研究侧 3 次调用(planner+reader×2)×1500
    assert wc[0]["max_tokens"] == 50_000 - 42_500 - len(wp) - 512
    assert b.used_llm_tokens <= 50_000              # 总账不越限
    assert state["report_md"].startswith("# 报告")   # 正常出报告


def test_writer_node_skips_call_when_remaining_below_min():
    """节点级:剩余额度不足以完成一次最小有效调用 → writer 不调模型,
    程序说明, 控制类终态(防御纵深:全链路下该情形多被研究侧提前拦截)。"""
    b = make_budget(total_llm=2_000, reserve=1_000)
    b.settle_llm(1_900, for_writer=False)           # 剩余 100
    tools, events, calls = make_tools([], budget=b)
    w = graph.make_writer(tools)
    out = w({"topic": "Q", "evidence": [_ev()], "stop_reason": None})

    assert calls["llm"] == []
    assert out["stop_reason"] == "total_budget_exhausted"
    assert "程序生成" in out["report_md"]


def test_reader_skips_summary_when_remaining_below_min():
    """节点级:页面已抓取但剩余额度不足以摘要 → 不调用, warning 跳页,
    已有候选证据保留。"""
    b = make_budget(total_llm=2_600, reserve=200)
    b.settle_llm(2_200, for_writer=False)           # 剩余 400
    tools, events, calls = make_tools([PLANNER_JSON], budget=b)
    reader = graph.make_reader(tools)
    state = {"topic": "Q", "sub_questions": ["q1"], "planned_query": "q",
             "search_results": [SearchResult(
                 url="https://docs.python.org/a", title="A", snippet="s")],
             "seen_urls": [], "candidate_evidence": [_ev(9)],
             "round_no": 1, "stop_reason": None}
    out = reader(state)

    assert calls["llm"] == []                       # 摘要未调用
    assert calls["fetch"] == ["https://docs.python.org/a"]  # 页面已抓
    assert any("剩余额度" in p.get("detail", "") for e, p in events
               if e == "warning")
    assert out["candidate_evidence"] == [_ev(9)]    # 已有候选保留


def test_reflector_degrades_without_call_when_remaining_below_min():
    """节点级:剩余额度不足以反思 → 不调用模型, 退化单轮收尾(writer
    兜底 stop_reason), 与反思失败路径同构。"""
    b = make_budget(total_llm=2_000, reserve=200)
    b.settle_llm(1_700, for_writer=False)           # 剩余 300(未熔断研究额度)
    tools, events, calls = make_tools([], budget=b)
    r = graph.make_reflector(tools)
    out = r({"topic": "Q", "sub_questions": ["q1"], "round_no": 1,
             "search_rounds": [{"query": "q"}], "evidence": [_ev()],
             "last_added_count": 1, "stop_reason": None})

    assert calls["llm"] == []
    assert out == {"next_queries": []}
    assert any("剩余额度" in p.get("detail", "") for e, p in events
               if e == "warning")


def test_citation_revision_degrades_when_remaining_below_min():
    """节点级:writer 调用后剩余额度不足以修订(修订 prompt 含报告全文,
    越长越贵)→ 程序化降级处理引用, 不再调模型(修订也是模型调用,
    R1 同口径约束)。"""
    b = make_budget(total_llm=4_000, reserve=200)
    b.settle_llm(2_000, for_writer=False)           # writer 剩余可调用
    long_bad_report = "结论 [5] 来自外部。" + "正文内容。" * 833  # ≈5000 字
    tools, events, calls = make_tools(
        [long_bad_report],                          # 越界引用 → 触发修订
        budget=b)
    w = graph.make_writer(tools)
    out = w({"topic": "Q", "evidence": [_ev()], "stop_reason": None})

    assert len(calls["llm"]) == 1                   # 仅 writer 本体, 修订未调
    assert "[5]" not in out["report_md"]
    assert "未经正文核实" in out["report_md"]        # 程序化降级标记
    assert any("额度" in p.get("detail", "") for e, p in events
               if e == "warning")


# ---- 修复轮 R2:失败/取消路径分账 ---------------------------------------------

def test_writer_stream_settles_known_usage_on_llm_error():
    """R2 复现空流丢账:chat_stream 先收 usage 帧再发现 0 正文片段
    (c76a8b8 显式 LLMError)→ writer 流式迭代抛错时 usage_box 已有
    已知成本, 须先 settle 再传播(usage 是事实, 禁止丢账)。"""
    b = make_budget()
    tools, _events, calls = make_tools(
        [PLANNER_JSON,
         reader_json(["自由线程模式,可禁用全局解释器锁",
                      "交互式解释器支持多行编辑与彩色提示"]),
         reader_json(["错误消息更加友好"])],
        llm_stream_chunks=[],                       # 空流: 无正文片段
        llm_stream_error=LLMError("流式响应空内容: 收到 [DONE] 但无正文片段"),
        budget=b, llm_usage={"prompt_tokens": 6000,
                             "completion_tokens": 2200,
                             "total_tokens": 8200})
    w = graph.make_writer(tools)
    with pytest.raises(LLMError):
        w({"topic": "Q", "evidence": [_ev()], "stop_reason": None})

    assert b.usage_snapshot()["llm_tokens"] == 8200  # 已知成本入账, 不丢
