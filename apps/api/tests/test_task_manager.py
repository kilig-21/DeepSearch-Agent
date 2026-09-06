"""TaskManager 测试(fake 工具链 + 临时 DB, 不联网)。

验收口径(§3.4/§4 Phase 1B):
- 单 worker 同一时刻最多 1 个活动任务
- 每条事件含 task_id / 服务端递增 id / ts
- 报告落库与 tasks 终态同事务, 提交后才发 done
- writer 执行中取消 → cancelled, 不产生半截正式报告
- 终态唯一, 后到者丢弃
"""
import json
import threading
import time

import pytest

from orca import db
from orca.llm import LLMResult
from orca.persist import persist_task_results
from orca.task_manager import ActiveTaskExists, TaskManager
from tests.test_graph import (
    PLANNER_JSON,
    WRITER_REPORT,
    default_search_results,
    happy_llm_sides,
    make_budget,
    make_tools,
)

USAGE = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}


def _writer_block_tools(gate: threading.Event, release: threading.Event):
    """planner/reader 走原 fake 侧写;writer 档(high_quality)先 set gate 再阻塞等 release。"""
    tools, events, calls = make_tools(happy_llm_sides(),
                                      search_results=default_search_results())
    orig_llm_chat = tools.llm_chat

    def llm_chat(messages, *, max_tokens, tier, reasoning_effort=None):
        if tier == "high_quality":
            gate.set()
            release.wait(timeout=10)
        return orig_llm_chat(messages, max_tokens=max_tokens, tier=tier,
                             reasoning_effort=reasoning_effort)

    tools.llm_chat = llm_chat
    return tools


def _done_builder(tools):
    def _build(budget):
        tools.budget = budget
        return tools
    return _build


def _make_manager(engine, builder, **kw):
    return TaskManager(engine, tools_builder=builder,
                       budget_builder=make_budget, **kw)


# ---- 创建与单活动约束 --------------------------------------------------------

def test_create_persists_running_task(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_block_tools(gate, release)))
    try:
        task_id = mgr.create("Q")
        assert task_id.startswith("t_")
        assert db.get_task(engine, task_id)["status"] == "running"
    finally:
        release.set()
        mgr.wait(task_id, timeout=10)


def test_create_rejects_second_active_task(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_block_tools(gate, release)))
    try:
        first = mgr.create("Q1")
        with pytest.raises(ActiveTaskExists):
            mgr.create("Q2")
    finally:
        release.set()
        mgr.wait(first, timeout=10)
    # 终态后槽位释放, 可再创建
    second = mgr.create("Q2")
    mgr.wait(second, timeout=10)


# ---- 完成路径: 同事务落库 → 才发 done ---------------------------------------

def test_run_completes_persists_report_and_emits_done(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    mgr = _make_manager(engine, builder)
    task_id = mgr.create("Python 3.13 新特性?")
    assert mgr.wait(task_id, timeout=10)

    task = db.get_task(engine, task_id)
    assert task["status"] == "completed"
    assert task["stop_reason"] == "single_pass"
    assert task["report_id"] is not None
    report = db.get_report(engine, task["report_id"])
    assert "自由线程" in report["final_md"]

    events = mgr.events_after(task_id, 0)
    assert events[-1].event == "done"
    assert events[-1].payload["report_id"] == task["report_id"]
    assert events[-1].payload["stop_reason"] == "single_pass"


def test_done_marks_over_budget_and_warns_when_actual_exceeds_limit(tmp_path):
    """R1b 落库前终检: 实耗超总额上限 → done.usage.over_budget 如实标记
    + warning 事件(禁止静默);settle 语义不变(usage 是事实总是记账)。
    构造: builder 预烧超 total=100 的账, 模拟"prompt 实际 tokens 超出
    调用前估算"的越限事实(_control_stop 即拦, 任务 completed 程序说明)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)

    def builder(budget):
        budget.settle_llm(200, for_writer=False)   # 200 > total 100
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    mgr = TaskManager(engine, tools_builder=builder,
                      budget_builder=lambda: make_budget(total_llm=100,
                                                         reserve=50))
    task_id = mgr.create("Q")
    assert mgr.wait(task_id, timeout=10)

    task = db.get_task(engine, task_id)
    assert task["status"] == "completed"
    usage_json = task["usage_json"]
    assert usage_json["llm_tokens"] == 200          # 事实入账(settle 语义不变)
    assert usage_json["over_budget"] is True        # DB 路: 如实标记

    events = mgr.events_after(task_id, 0)
    done = events[-1]
    assert done.event == "done"
    assert done.payload["usage"]["over_budget"] is True   # 事件路: 同一标记
    assert any(e.event == "warning" and "超" in e.payload.get("detail", "")
               for e in events)                     # 警告不静默


def test_done_not_emitted_when_persist_fails(tmp_path):
    """persist(同事务提交)失败 → 任务 failed, 且不得出现 done 事件(§3.4)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    def broken_persist(engine, task_id, state, budget):
        raise RuntimeError("DB 写失败")

    mgr = _make_manager(engine, builder, persist_fn=broken_persist)
    task_id = mgr.create("Q")
    assert mgr.wait(task_id, timeout=10)

    task = db.get_task(engine, task_id)
    assert task["status"] == "failed"
    assert task["stop_reason"] == "execution_error"
    events = mgr.events_after(task_id, 0)
    assert events[-1].event == "task_failed"
    assert not any(e.event == "done" for e in events)


# ---- 取消路径 ---------------------------------------------------------------

def _writer_stream_tools(gate: threading.Event, release: threading.Event):
    """writer 走流式:前 2 个片段正常发出后阻塞等 release——片段间取消窗口。"""
    tools, _e, _c = make_tools(
        happy_llm_sides()[:3],  # planner + 2 页 reader(writer 不走一次性 llm_chat)
        search_results=default_search_results())
    chunks = ["# 标题\n", "正文 [1]。\n", "更多 [2]。\n"]

    def llm_chat_stream(messages, *, max_tokens, tier):
        usage_box: dict = {}

        def gen():
            yield chunks[0]
            yield chunks[1]
            gate.set()
            release.wait(timeout=10)  # 取消窗口: 主线程在此请求取消
            yield chunks[2]           # emit 该片段时取消检查点生效
            usage_box.update(USAGE)

        return gen(), usage_box

    tools.llm_chat_stream = llm_chat_stream
    return tools


def test_cancel_during_writer_yields_cancelled_without_report(tmp_path):
    """验收①: writer 执行中取消 → cancelled, 不产生半截正式报告。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_block_tools(gate, release)))
    task_id = mgr.create("Q")
    assert gate.wait(5), "writer 未开始"
    assert mgr.request_cancel(task_id) is True
    release.set()
    assert mgr.wait(task_id, timeout=10)

    task = db.get_task(engine, task_id)
    assert task["status"] == "cancelled"
    assert task["stop_reason"] == "user_cancelled"
    assert task["report_id"] is None
    with engine.connect() as conn:
        count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM reports WHERE task_id = ?",
            (task_id,)).scalar()
    assert count == 0

    events = mgr.events_after(task_id, 0)
    assert not any(e.event == "done" for e in events)
    assert events[-1].event == "cancelled"
    assert events[-1].payload["stop_reason"] == "user_cancelled"


def test_cancel_during_writer_stream_receives_deltas_then_no_report(tmp_path):
    """测试类1(评审补齐):writer 未结束时已收到多个正文片段,取消后
    不落正式报告——片段 emit 即取消检查点,流式过程中取消即时生效。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_stream_tools(gate, release)))
    task_id = mgr.create("Q")
    try:
        assert gate.wait(5), "writer 流式未开始"
        assert mgr.request_cancel(task_id) is True
    finally:
        release.set()
    assert mgr.wait(task_id, timeout=10)

    task = db.get_task(engine, task_id)
    assert task["status"] == "cancelled"
    assert task["stop_reason"] == "user_cancelled"
    assert task["report_id"] is None
    with engine.connect() as conn:
        count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM reports WHERE task_id = ?",
            (task_id,)).scalar()
    assert count == 0

    events = mgr.events_after(task_id, 0)
    deltas = [e for e in events if e.event == "report_delta"]
    assert len(deltas) >= 2  # 取消前已收到多个正文片段
    assert "".join(e.payload["md"] for e in deltas) == "# 标题\n正文 [1]。\n"
    assert all(e.payload.get("draft") is True for e in deltas)
    assert not any(e.event == "done" for e in events)
    assert events[-1].event == "cancelled"


def test_cancel_after_terminal_is_rejected(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    mgr = _make_manager(engine, builder)
    task_id = mgr.create("Q")
    assert mgr.wait(task_id, timeout=10)
    assert mgr.request_cancel(task_id) is False  # 终态后不可取消
    assert db.get_task(engine, task_id)["status"] == "completed"


def test_writer_stream_closed_on_cancel(tmp_path):
    """取消发生时(writer 片段 emit 抛 TaskCancelled), writer 的 finally
    必须显式 gen.close() 关闭流生成器——进而关闭底层 HTTP 流上下文
    (第五轮评审 R4④)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    closed = {"flag": False}

    def builder(budget):
        tools = _writer_stream_tools(gate, release)
        tools.budget = budget
        inner = tools.llm_chat_stream

        def tracked_stream(messages, *, max_tokens, tier):
            gen, box = inner(messages, max_tokens=max_tokens, tier=tier)

            def tracked():
                try:
                    yield from gen
                finally:
                    closed["flag"] = True  # close 链最终关闭底层流
            return tracked(), box

        tools.llm_chat_stream = tracked_stream
        return tools

    mgr = _make_manager(engine, builder)
    task_id = mgr.create("Q")
    try:
        assert gate.wait(5)
        assert mgr.request_cancel(task_id) is True
    finally:
        release.set()
    assert mgr.wait(task_id, timeout=10)
    assert db.get_task(engine, task_id)["status"] == "cancelled"
    assert closed["flag"] is True, "取消后 writer 必须显式关闭流生成器"


def test_terminal_event_recorded_only_once(tmp_path):
    """终态唯一, 后到者丢弃(§3.4)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_x", topic="Q")
    mgr._record_terminal(runtime, "cancelled", {"stop_reason": "user_cancelled"})
    mgr._record_terminal(runtime, "done", {"report_id": 1})
    events = mgr.events_after("t_x", 0)
    assert [e.event for e in events] == ["cancelled"]
    assert runtime.status == "cancelled"


# ---- 事件结构与快照 ---------------------------------------------------------

def test_events_carry_task_id_increasing_seq_and_ts(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    mgr = _make_manager(engine, builder)
    task_id = mgr.create("Q")
    assert mgr.wait(task_id, timeout=10)

    events = mgr.events_after(task_id, 0)
    assert [e.seq for e in events] == sorted(e.seq for e in events)
    assert events[0].seq == 1  # 服务端从 1 递增
    for e in events:
        assert e.payload["task_id"] == task_id
        assert e.payload["ts"]
    names = [e.event for e in events]
    assert names[0] == "plan"
    assert "search" in names and "reading" in names and "note" in names


def test_snapshot_running_and_completed(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_block_tools(gate, release)))
    task_id = mgr.create("Q")
    try:
        assert gate.wait(5)
        snap = mgr.snapshot(task_id)
        assert snap["task_id"] == task_id
        assert snap["status"] == "running"
        assert snap["stop_reason"] is None
        assert snap["sub_questions"]  # planner 已完成
        assert snap["round_no"] >= 1
        assert snap["progress"]["sources_read"] >= 1
        assert snap["seq"] > 0
    finally:
        release.set()
        mgr.wait(task_id, timeout=10)

    snap = mgr.snapshot(task_id)
    assert snap["status"] == "completed"
    assert snap["report_id"] is not None
    assert "自由线程" in snap["report_md"]
    assert snap["citation_map"] == {"1": "ev_001", "2": "ev_002"}


def test_snapshot_after_cancel_hides_draft(tmp_path):
    """取消后草稿不作为正式内容暴露(不可恢复, 如实返回)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_block_tools(gate, release)))
    task_id = mgr.create("Q")
    assert gate.wait(5)
    mgr.request_cancel(task_id)
    release.set()
    assert mgr.wait(task_id, timeout=10)
    snap = mgr.snapshot(task_id)
    assert snap["status"] == "cancelled"
    assert snap["stop_reason"] == "user_cancelled"
    assert snap["report_md"] == ""


# ---- R1: SSE 关闭判断锁内化(drain) -------------------------------------------

def test_drain_never_sees_flag_without_terminal_event(tmp_path):
    """R1 竞争(受控暂停注入写端临界区):写端在 _record_terminal 置标志
    之后、事件入缓冲之前挂起(即评审指认的 309→316 窗口), 并发 drain
    必须等待锁——读端永远观察不到"标志可见但终态事件未取到"的中间态。
    同时自检:此窗口内锁外裸读 runtime 字段确实会误判可关闭(证明
    测试窗口真实存在, 而非"先完成发布再读"的假竞争)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_r1", topic="Q")
    mgr._record(runtime, "progress", {"n": 1})  # seq=1, 读者游标从此追

    # 受控暂停:_record_terminal 已置 terminal_recorded=True、尚未 seq+=1
    gate, release = threading.Event(), threading.Event()
    orig_record_locked = mgr._record_locked

    def slow_record_locked(rt, event, payload):
        gate.set()
        release.wait(timeout=5)  # 仍持锁——模拟 309→316 中间态窗口
        orig_record_locked(rt, event, payload)

    mgr._record_locked = slow_record_locked
    writer = threading.Thread(
        target=lambda: mgr._record_terminal(runtime, "cancelled",
                                            {"stop_reason": "user_cancelled"}),
        daemon=True)
    writer.start()
    assert gate.wait(5), "写端未进入终态临界区"

    # 自检:窗口内裸读确实可见"标志=True、seq 仍旧值"——旧代码会误关
    assert runtime.terminal_recorded is True and runtime.seq == 1

    # 并发读者此刻调 drain:必须阻塞等锁, 不得返回中间态
    reader_done = threading.Event()
    reader_result: dict = {}

    def reader():
        reader_result["events"], reader_result["tv"], _ = mgr.drain("t_r1", 1)
        reader_done.set()

    threading.Thread(target=reader, daemon=True).start()
    time.sleep(0.05)
    assert not reader_done.is_set(), "写端持锁窗口内读者不得观察到中间态"

    release.set()
    writer.join(5)
    assert reader_done.wait(5)
    events, tv = reader_result["events"], reader_result["tv"]
    # 锁内一致读:要么终态事件在本批可取(tv=False),要么已追上且事件必空
    if tv:
        assert events == []            # tv=True ⇒ 无未取事件(不会漏发终态)
    else:
        assert any(e.event == "cancelled" for e in events)

    # 追平后 drain:终态已入缓冲, tv=True 且事件空——安全关闭
    events2, tv2, _gap = mgr.drain("t_r1", 2)
    assert events2 == [] and tv2 is True and _gap is False


# ---- R2: 恢复判定与取数合并临界区 + 每批缺口检测 -------------------------------

def test_resume_replay_atomic_against_buffer_eviction(tmp_path):
    """R2 恢复竞争:resume 的游标判定与首批事件复制在同一锁临界区完成,
    返回的副本必然从 last_id+1 连续开始——即使随后生产者推进把游标挤出
    环形缓冲, 也不会重现旧实现"判定 replay 后再取数只拿到剩余尾部"的
    丢帧窗口(副本先于挤出已在锁内复制完毕)。"""
    from collections import deque
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_r2", topic="Q")
    runtime.buffer = deque(maxlen=3)  # 小缓冲放大挤出效应
    for i in range(3):
        mgr._record(runtime, "progress", {"n": i + 1})  # seq 1..3

    # 游标 1 在覆盖范围内 → replay, 首批副本 = 2、3(判定与取数同临界区)
    mode, from_seq, events = mgr.resume("t_r2", 1)
    assert (mode, from_seq) == ("replay", 1)
    assert [e.seq for e in events] == [2, 3]

    # 生产者推进 4..6:环形缓冲把 1、2、3 全部挤出(游标已不在覆盖范围)
    for i in range(3):
        mgr._record(runtime, "progress", {"n": i + 4})
    assert [e.seq for e in runtime.buffer] == [4, 5, 6]

    # 已返回的副本仍是完整的 2、3 —— 不存在"判定后取数"的丢帧窗口
    assert [e.seq for e in events] == [2, 3]

    # 而此刻再以游标 1 恢复:超出覆盖范围 → snapshot 对齐(另一路正确)
    mode2, seq2, fields = mgr.resume("t_r2", 1)
    assert mode2 == "snapshot" and seq2 == 6
    assert fields["seq"] == 6 and fields["task_id"] == "t_r2"


def test_drain_reports_gap_when_cursor_evicted(tmp_path):
    """R2 每批缺口检测:游标被环形缓冲挤出后 drain 必须报告 gap=True
    (调用方须转 snapshot 重对齐), 不得把跳过缺口的尾部事件当正常
    补发返回;重对齐后继续增量不受影响(回归)。"""
    from collections import deque
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_r2g", topic="Q")
    runtime.buffer = deque(maxlen=3)
    for i in range(3):
        mgr._record(runtime, "progress", {"n": i + 1})  # seq 1..3

    # 游标 1 仍在覆盖范围 → 无缺口, 正常补发 2、3(回归: 正常补发不受影响)
    events, tv, gap = mgr.drain("t_r2g", 1)
    assert ([e.seq for e in events], tv, gap) == ([2, 3], False, False)

    # 生产者推进 4..6:seq 1..3 全部被挤出, 游标 1 落到覆盖范围之前
    for i in range(3):
        mgr._record(runtime, "progress", {"n": i + 4})

    # 缺口必须被检出;此时返回的事件若直接补发将从 4 跳帧
    events, tv, gap = mgr.drain("t_r2g", 1)
    assert gap is True
    assert events and events[0].seq == 4 and tv is False

    # snapshot 重对齐(sent=6)后继续增量:无缺口、无回退
    snap = mgr.snapshot("t_r2g")
    assert snap["seq"] == 6
    events, tv, gap = mgr.drain("t_r2g", snap["seq"])
    assert (events, tv, gap) == ([], False, False)
    mgr._record(runtime, "progress", {"n": 7})
    events, tv, gap = mgr.drain("t_r2g", 6)
    assert ([e.seq for e in events], tv, gap) == ([7], False, False)


def test_drain_no_gap_for_snapshot_aligned_cursor(tmp_path):
    """snapshot 对齐后的游标(sent=snap.seq)与空缓冲不得误报缺口。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_r2s", topic="Q")
    mgr._record(runtime, "progress", {"n": 1})  # seq=1
    snap = mgr.snapshot("t_r2s")
    events, tv, gap = mgr.drain("t_r2s", snap["seq"])
    assert (events, tv, gap) == ([], False, False)  # 对齐游标 → 无缺口
    runtime.buffer.clear()  # 极端: 缓冲被清空(如自定义小 maxlen 挤空)
    events, tv, gap = mgr.drain("t_r2s", 0)
    assert (events, tv, gap) == ([], False, False)  # 空缓冲 → 无缺口、不误报


# ---- P3: 运行中 snapshot 带正文(测试类2) ------------------------------------

def test_snapshot_running_includes_draft_consistent_with_seq(tmp_path):
    """P3:running snapshot 的 report_md 必须是已生成正文(非空串),
    且正文/进度/seq 与事件流对应同一时点。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_stream_tools(gate, release)))
    task_id = mgr.create("Q")
    try:
        assert gate.wait(5), "writer 流式未开始"
        snap = mgr.snapshot(task_id)
        events = mgr.events_after(task_id, 0)
        deltas = [e for e in events if e.event == "report_delta"]
        assert snap["status"] == "running"
        assert snap["report_md"] == "# 标题\n正文 [1]。\n"   # 已生成正文
        assert snap["report_md"] == "".join(
            e.payload["md"] for e in deltas)                # 与事件流一致
        assert snap["seq"] == events[-1].seq                # 同一时点
        assert snap["progress"]["sources_read"] >= 1
    finally:
        release.set()
        mgr.wait(task_id, timeout=10)


def test_refresh_recovery_draft_plus_deltas_verbatim(tmp_path):
    """测试类2:刷新恢复逐字无丢失无重复——snapshot 草稿 + 后续片段
    拼接 == 完整正文, snapshot 草稿是全文前缀(不重不漏)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    gate, release = threading.Event(), threading.Event()
    mgr = _make_manager(engine, _done_builder(
        _writer_stream_tools(gate, release)))
    task_id = mgr.create("Q")
    assert gate.wait(5)
    snap = mgr.snapshot(task_id)
    snap_md = snap["report_md"]
    snap_seq = snap["seq"]
    release.set()
    assert mgr.wait(task_id, timeout=10)

    later = [e for e in mgr.events_after(task_id, snap_seq)
             if e.event == "report_delta" and not e.payload.get("replace")]
    full = snap_md + "".join(e.payload["md"] for e in later)
    assert full == "# 标题\n正文 [1]。\n更多 [2]。\n"   # 无丢失无重复
    # 完成后正式版与草稿链路逐字一致
    final_snap = mgr.snapshot(task_id)
    assert final_snap["status"] == "completed"
    assert final_snap["report_md"] == full


def test_report_delta_replace_frame_replaces_draft(tmp_path):
    """replace 帧(修订)整体替换草稿而非追加, snapshot 草稿即修订版。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_rep", topic="Q")
    mgr._record(runtime, "report_delta", {"md": "草稿", "draft": True})
    mgr._record(runtime, "report_delta",
                {"md": "修订版", "draft": True, "replace": True})
    assert runtime.draft_md == "修订版"


# ---- P5/P6: 终态发布窗口与取消/完成竞争(测试类5) ----------------------------

def test_completed_persist_loses_race_to_cancel(tmp_path):
    """P6:取消侧先提交终态 → persist 条件更新未命中, 报告一并回滚、
    后到结果丢弃、不发 done;"cancelled 后 completed 覆盖"必须消失。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    def racing_persist(engine_, task_id, state, budget, **kw):
        # 模拟取消侧在 worker 提交 completed 之前已落库 cancelled
        db.cancel_task(engine_, task_id, stop_reason="user_cancelled")
        return persist_task_results(engine_, task_id, state, budget, **kw)

    mgr = _make_manager(engine, builder, persist_fn=racing_persist)
    task_id = mgr.create("Q")
    assert mgr.wait(task_id, timeout=10)

    task = db.get_task(engine, task_id)
    assert task["status"] == "cancelled"          # completed 不得覆盖
    assert task["stop_reason"] == "user_cancelled"
    assert task["report_id"] is None
    with engine.connect() as conn:
        count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM reports WHERE task_id = ?",
            (task_id,)).scalar()
    assert count == 0                             # 报告写入已回滚
    events = mgr.events_after(task_id, 0)
    assert not any(e.event == "done" for e in events)  # 后到结果不发 done
    assert events[-1].event == "cancelled"


def test_terminal_record_atomic_under_concurrent_events(tmp_path):
    """P5:终态提交(标志+状态+seq+缓冲)同一临界区——并发事件线程下
    seq 连续无交错、终态事件恰一条且可读(旧实现锁外 _record 会丢号)。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_p5", topic="Q")
    stop = threading.Event()

    def spam():
        i = 0
        while not stop.is_set():
            mgr._record(runtime, "progress", {"n": i})
            i += 1

    t = threading.Thread(target=spam, daemon=True)
    t.start()
    try:
        time.sleep(0.02)
        mgr._record_terminal(runtime, "cancelled",
                             {"stop_reason": "user_cancelled"})
    finally:
        stop.set()
        t.join(5)

    events = mgr.events_after("t_p5", 0)
    seqs = [e.seq for e in events]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))  # 连续无交错丢号
    assert [e.event for e in events].count("cancelled") == 1  # 终态恰一条
    assert runtime.terminal_recorded is True
    assert runtime.status == "cancelled"
    cancelled = [e for e in events if e.event == "cancelled"][0]
    # 标志可见时终态事件已可读;终态 seq 之后的序号只可能属于并发 in-flight
    assert cancelled.seq <= runtime.seq
    assert runtime.buffer[-1].seq == runtime.seq  # 缓冲与 seq 一致


def test_terminal_event_visible_before_flag_when_subscribed(tmp_path):
    """P5:订阅者在终态提交后必须能读到终态事件——标志先行可见导致
    SSE 提前关闭丢事件的窗口不存在。"""
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    mgr = _make_manager(engine, lambda budget: None)
    runtime = mgr._runtime_for_test(task_id="t_p5b", topic="Q")

    # 借真实锁读路径模拟 SSE drain:标志可见后 events_after 必含终态事件
    mgr._record_terminal(runtime, "done", {"report_id": 1,
                                           "stop_reason": "single_pass"})
    assert runtime.terminal_recorded is True
    events = mgr.events_after("t_p5b", 0)
    assert events, "终态事件必须可读"
    assert events[-1].event == "done"
    assert events[-1].seq == runtime.seq


def test_recover_interrupted_delegates_to_db(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    stale = db.create_task(engine, topic="遗留")
    mgr = _make_manager(engine, lambda budget: None)
    assert mgr.recover_interrupted() == 1
    assert db.get_task(engine, stale)["status"] == "interrupted"
