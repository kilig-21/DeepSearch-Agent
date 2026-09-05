"""FastAPI 任务接口测试(fake 工具链 + 临时 DB, 不联网)。

接口契约(§6/§3.4):
- POST /api/research → 202 {task_id};已有活动任务 → 409
- GET /api/research/{task_id} → 状态快照;未知 → 404
- POST /api/research/{task_id}/cancel → 202;终态后 → 409;未知 → 404
- 启动时遗留 running → interrupted
"""
import threading

from fastapi.testclient import TestClient

from orca import db
from tests.test_task_manager import _done_builder, _writer_block_tools
from tests.test_graph import make_tools, happy_llm_sides, default_search_results


def _happy_builder():
    def _build(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools
    return _build


def _make_client(tmp_path, name="o.db", builder=None):
    from orca.api import create_app
    db_path = tmp_path / name
    app = create_app(db_path=db_path,
                     tools_builder=builder or _happy_builder())
    client = TestClient(app)
    client.app_state = app.state  # 便于测试取 manager
    client.db_path = db_path
    return client


# ---- 基础 -------------------------------------------------------------------

def test_health(tmp_path):
    with _make_client(tmp_path) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_create_returns_202_with_task_id(tmp_path):
    with _make_client(tmp_path) as client:
        resp = client.post("/api/research", json={"topic": "Python 3.13 新特性?"})
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]
        assert task_id.startswith("t_")
        client.app_state.manager.wait(task_id, timeout=10)
        assert db.get_task(client.app_state.engine, task_id)["status"] == "completed"


def test_create_rejects_empty_topic(tmp_path):
    with _make_client(tmp_path) as client:
        assert client.post("/api/research", json={"topic": ""}).status_code == 422
        assert client.post("/api/research", json={}).status_code == 422


def test_create_conflicts_while_active(tmp_path):
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_block_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        first = client.post("/api/research", json={"topic": "Q1"}).json()["task_id"]
        resp = client.post("/api/research", json={"topic": "Q2"})
        assert resp.status_code == 409
        assert resp.json()["active_task_id"] == first
        release.set()
        client.app_state.manager.wait(first, timeout=10)


# ---- 状态快照 ----------------------------------------------------------------

def test_get_snapshot_404_unknown(tmp_path):
    with _make_client(tmp_path) as client:
        assert client.get("/api/research/t_nope").status_code == 404


def test_get_snapshot_completed(tmp_path):
    with _make_client(tmp_path) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        client.app_state.manager.wait(task_id, timeout=10)
        resp = client.get(f"/api/research/{task_id}")
        assert resp.status_code == 200
        snap = resp.json()
        assert snap["status"] == "completed"
        assert snap["stop_reason"] == "single_pass"
        assert snap["report_id"] is not None
        assert "自由线程" in snap["report_md"]
        assert snap["citation_map"] == {"1": "ev_001", "2": "ev_002"}
        assert snap["seq"] > 0


def test_get_snapshot_from_db_without_runtime(tmp_path):
    """进程重启(runtime 丢失)→ 从 DB 构造快照: 正式报告可取, 草稿如实为空。"""
    client1 = _make_client(tmp_path, name="o.db")
    task_id = client1.post("/api/research", json={"topic": "Q"}).json()["task_id"]
    client1.app_state.manager.wait(task_id, timeout=10)
    client1.close()

    client2 = _make_client(tmp_path, name="o.db")  # 同 DB 新 app = 重启
    with client2:
        resp = client2.get(f"/api/research/{task_id}")
        assert resp.status_code == 200
        snap = resp.json()
        assert snap["status"] == "completed"
        assert "自由线程" in snap["report_md"]


def test_startup_marks_stale_running_interrupted(tmp_path):
    from orca import db as db_mod
    db_path = tmp_path / "o.db"
    eng = db_mod.make_engine(db_path)
    db_mod.init_db(eng)
    stale = db_mod.create_task(eng, topic="上次没跑完")

    with _make_client(tmp_path, name="o.db") as client:
        assert db_mod.get_task(client.app_state.engine, stale)["status"] == \
            "interrupted"
        snap = client.get(f"/api/research/{stale}").json()
        assert snap["status"] == "interrupted"
        assert snap["stop_reason"] == "process_interrupted"
        assert snap["report_md"] == ""  # 草稿不可恢复, 如实返回


# ---- 取消 --------------------------------------------------------------------

def test_cancel_running_task_returns_202(tmp_path):
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_block_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        assert gate.wait(5)
        resp = client.post(f"/api/research/{task_id}/cancel")
        assert resp.status_code == 202
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)
        assert db.get_task(client.app_state.engine, task_id)["status"] == "cancelled"


def test_cancel_unknown_404(tmp_path):
    with _make_client(tmp_path) as client:
        assert client.post("/api/research/t_nope/cancel").status_code == 404


def test_cancel_terminal_409(tmp_path):
    with _make_client(tmp_path) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        client.app_state.manager.wait(task_id, timeout=10)
        resp = client.post(f"/api/research/{task_id}/cancel")
        assert resp.status_code == 409
