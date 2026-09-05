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

import pytest

from orca import db
from orca.llm import LLMResult
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


def test_recover_interrupted_delegates_to_db(tmp_path):
    engine = db.make_engine(tmp_path / "o.db")
    db.init_db(engine)
    stale = db.create_task(engine, topic="遗留")
    mgr = _make_manager(engine, lambda budget: None)
    assert mgr.recover_interrupted() == 1
    assert db.get_task(engine, stale)["status"] == "interrupted"
