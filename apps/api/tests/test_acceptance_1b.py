"""Phase 1B 验收四场景(PLAN.md §4, fake 工具链, 全部走 HTTP 层)。

① writer 执行中取消 → 终态 cancelled, 不产生半截正式报告
② 额度耗尽 → 研究额度耗尽仍出报告 / 总额度耗尽不再调模型
③ 刷新后恢复完整正文(snapshot 含前半段, 不丢字)
④ 进程重启后显示 interrupted 且历史报告可取
另验: 断线自动重连补发、报告与 tasks 状态同事务。

块 8 将用真实 uvicorn + 前端再逐个演示。
"""
import json
import threading

import pytest
from fastapi.testclient import TestClient

from orca import db
from tests.test_graph import (
    WRITER_REPORT,
    default_search_results,
    happy_llm_sides,
    make_budget,
    make_tools,
)
from tests.test_task_manager import _done_builder, _writer_block_tools


def _happy_builder():
    def _build(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools
    return _build


def _make_client(tmp_path, name="o.db", tools_builder=None, budget_builder=None):
    from orca.api import create_app
    app = create_app(db_path=tmp_path / name,
                     tools_builder=tools_builder or _happy_builder(),
                     budget_builder=budget_builder, heartbeat_interval=0.2)
    client = TestClient(app)
    client.app_state = app.state
    client.db_path = tmp_path / name
    return client


# ---- ① writer 执行中取消 ------------------------------------------------------

def test_scenario_1_cancel_during_writer(tmp_path):
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_block_tools(gate, release))(budget)

    client = _make_client(tmp_path, tools_builder=builder)
    with client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        assert gate.wait(5), "writer 应已开始"
        assert client.post(f"/api/research/{task_id}/cancel").status_code == 202
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)

        # 终态 cancelled
        snap = client.get(f"/api/research/{task_id}").json()
        assert snap["status"] == "cancelled"
        assert snap["stop_reason"] == "user_cancelled"
        # 不产生半截正式报告
        assert snap["report_id"] is None
        assert snap["report_md"] == ""
        with client.app_state.engine.connect() as conn:
            n = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM reports WHERE task_id = ?",
                (task_id,)).scalar()
        assert n == 0
        # 事件流补发路径: 缓冲内事件含 cancelled 终态帧, 无 done/task_failed
        # (P4: 无游标连接只发 snapshot 即关闭——snapshot 已呈现终态;
        #  用缓冲内游标走补发路径验证事件帧)
        lines2 = []
        with client.stream("GET", f"/api/research/{task_id}/events",
                           headers={"Last-Event-ID": "1"}) as resp:
            for line in resp.iter_lines():
                lines2.append(line)
        events = [l.split(": ", 1)[1] for l in lines2
                  if l.startswith("event: ") and l != "event: snapshot"]
        assert events[-1] == "cancelled"
        assert "done" not in events
        assert "task_failed" not in events


# ---- ② 额度耗尽两路 -----------------------------------------------------------

def test_scenario_2a_research_budget_exhausted_still_reports(tmp_path):
    """研究额度耗尽 → 停止研究走 writer 预留路径, 任务仍 completed 且有报告。

    构造: 研究额度 100 < planner 实测用量(150), 总额度 200 不爆 →
    searcher 入口 budget_exhausted(研究类);writer 不调模型(无证据 →
    程序生成说明), 报告落库, 任务 completed。
    """
    calls = {"n": 0}

    def budget_builder():
        return make_budget(total_llm=200, reserve=100)

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        orig = tools.llm_chat

        def llm_chat(*a, **kw):
            calls["n"] += 1
            return orig(*a, **kw)
        tools.llm_chat = llm_chat
        tools.budget = budget
        return tools

    client = _make_client(tmp_path, tools_builder=builder,
                          budget_builder=budget_builder)
    with client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        client.app_state.manager.wait(task_id, timeout=10)
        snap = client.get(f"/api/research/{task_id}").json()
        assert snap["status"] == "completed"
        assert snap["stop_reason"] == "budget_exhausted"
        assert snap["report_id"] is not None
        assert snap["report_md"]  # 程序说明照常落库
        assert "额度" in snap["report_md"]
        # writer 预留规则: 研究额度耗尽后不再发生研究类调用
        assert calls["n"] == 1  # 仅 planner; searcher/reader 全部短路


def test_scenario_2b_total_budget_exhausted_no_more_llm(tmp_path):
    """总额度耗尽 → 不再调用任何模型, 程序生成说明收尾(total_budget_exhausted)。"""
    calls = {"n": 0}

    def budget_builder():
        return make_budget(total_llm=150, reserve=100)

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        orig = tools.llm_chat

        def llm_chat(*a, **kw):
            calls["n"] += 1
            return orig(*a, **kw)
        tools.llm_chat = llm_chat
        tools.budget = budget
        return tools

    client = _make_client(tmp_path, tools_builder=builder,
                          budget_builder=budget_builder)
    with client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        client.app_state.manager.wait(task_id, timeout=10)
        snap = client.get(f"/api/research/{task_id}").json()
        assert snap["status"] == "completed"
        assert snap["stop_reason"] == "total_budget_exhausted"
        # planner 已耗尽总额度 → 后续任何节点不再调用模型
        assert calls["n"] == 1


# ---- ③ 刷新后恢复完整正文 ------------------------------------------------------

def test_scenario_3_refresh_restores_full_report(tmp_path):
    client = _make_client(tmp_path)
    with client:
        task_id = client.post("/api/research",
                              json={"topic": "Python 3.13 新特性?"}).json()["task_id"]
        client.app_state.manager.wait(task_id, timeout=10)
        detail = client.get(
            f"/api/reports/{client.get(f'/api/research/{task_id}').json()['report_id']}").json()
        # "刷新" = 丢弃全部页面状态后新建 EventSource 连接(无 Last-Event-ID)
        lines = []
        with client.stream("GET", f"/api/research/{task_id}/events") as resp:
            for line in resp.iter_lines():
                lines.append(line)
        frames = [f for f in lines if f.startswith("data: ")]
        snap = json.loads(frames[0][6:])
    # snapshot 完整正文, 不丢字: 与落库正式版逐字一致
    assert snap["status"] == "completed"
    assert snap["report_md"] == detail["final_md"]
    assert "自由线程" in snap["report_md"]
    assert snap["citation_map"] == detail["citation_map_json"] == \
        {"1": "ev_001", "2": "ev_002"}


# ---- ④ 进程重启 → interrupted + 历史报告可取 -------------------------------------

def test_scenario_4_restart_interrupted_and_history(tmp_path):
    client1 = _make_client(tmp_path)
    with client1:
        done_id = client1.post("/api/research",
                               json={"topic": "Q"}).json()["task_id"]
        client1.app_state.manager.wait(done_id, timeout=10)
        report_id = client1.get(f"/api/research/{done_id}").json()["report_id"]
        # 模拟崩溃: 任务仍在 running 时进程消失
        eng = db.make_engine(client1.db_path)
        ghost = db.create_task(eng, topic="没跑完就重启")

    client2 = _make_client(tmp_path)  # 同 DB 新 app = 重启
    with client2:
        snap = client2.get(f"/api/research/{ghost}").json()
        assert snap["status"] == "interrupted"
        assert snap["stop_reason"] == "process_interrupted"
        assert snap["report_md"] == ""  # 草稿不可恢复, 如实返回
        # 历史报告可取
        detail = client2.get(f"/api/reports/{report_id}")
        assert detail.status_code == 200
        assert "自由线程" in detail.json()["final_md"]
        assert client2.get(f"/api/reports/{report_id}.md").status_code == 200
        assert client2.get("/api/reports").json()
        # SSE 也应给出终态快照后关闭(不无限重连)
        lines = []
        with client2.stream("GET", f"/api/research/{ghost}/events") as resp:
            for line in resp.iter_lines():
                lines.append(line)
        snap_frames = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
        assert len(snap_frames) == 1
        assert snap_frames[0]["status"] == "interrupted"


# ---- 另验: 报告与 tasks 状态同事务 -----------------------------------------------

def test_extra_report_and_task_status_same_transaction(tmp_path):
    """persist 失败 → 报告与 completed 状态都不存在(同事务回滚), 任务 failed,
    且 done 事件不发出(提交后才发)。"""
    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    def broken_persist(engine, task_id, state, budget, **kw):
        raise RuntimeError("DB 写失败")

    from orca.api import create_app
    app = create_app(db_path=tmp_path / "o.db", tools_builder=builder)
    client = TestClient(app)
    client.app_state = app.state
    with client:
        # 注入 persist 失败: 直接用 manager 层
        client.app_state.manager._persist_fn = broken_persist
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        client.app_state.manager.wait(task_id, timeout=10)

        task = db.get_task(client.app_state.engine, task_id)
        assert task["status"] == "failed"
        with client.app_state.engine.connect() as conn:
            n = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM reports WHERE task_id = ?",
                (task_id,)).scalar()
        assert n == 0  # 报告与 completed 状态同进同退
        lines = []
        with client.stream("GET", f"/api/research/{task_id}/events",
                           headers={"Last-Event-ID": "1"}) as resp:
            for line in resp.iter_lines():
                lines.append(line)
        events = [l.split(": ", 1)[1] for l in lines
                  if l.startswith("event: ") and l != "event: snapshot"]
        assert events[-1] == "task_failed"
        assert "done" not in events
