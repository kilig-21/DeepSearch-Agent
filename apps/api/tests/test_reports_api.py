"""reports 查询/导出 API 测试(§6, fake 工具链 + 临时 DB)。"""
from fastapi.testclient import TestClient

from orca import db
from tests.test_graph import default_search_results, happy_llm_sides, make_tools


def _client(tmp_path):
    from orca.api import create_app

    def builder(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools

    app = create_app(db_path=tmp_path / "o.db", tools_builder=builder)
    client = TestClient(app)
    client.app_state = app.state
    with client:
        task_id = client.post("/api/research",
                              json={"topic": "Q"}).json()["task_id"]
        client.app_state.manager.wait(task_id, timeout=10)
        task = db.get_task(client.app_state.engine, task_id)
    client.report_id = task["report_id"]
    return client


def test_list_reports_empty(tmp_path):
    from orca.api import create_app
    app = create_app(db_path=tmp_path / "empty.db")
    client = TestClient(app)
    with client:
        assert client.get("/api/reports").json() == []


def test_list_reports_returns_card_fields(tmp_path):
    client = _client(tmp_path)
    with client:
        reports = client.get("/api/reports").json()
    assert len(reports) == 1
    card = reports[0]
    for key in ("id", "task_id", "topic", "stop_reason", "token_cost",
                "credits_cost", "duration_s", "created_at"):
        assert key in card
    assert card["stop_reason"] == "single_pass"


def test_report_detail_joins_evidences_and_sources(tmp_path):
    client = _client(tmp_path)
    with client:
        resp = client.get(f"/api/reports/{client.report_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert "自由线程" in detail["final_md"]
    assert detail["citation_map_json"] == {"1": "ev_001", "2": "ev_002"}
    assert {e["evidence_id"] for e in detail["evidences"]} == \
        {"ev_001", "ev_002", "ev_003"}
    assert all("url" in s for s in detail["sources"])


def test_report_detail_404(tmp_path):
    from orca.api import create_app
    app = create_app(db_path=tmp_path / "empty.db")
    client = TestClient(app)
    with client:
        assert client.get("/api/reports/999").status_code == 404


def test_report_md_export(tmp_path):
    client = _client(tmp_path)
    with client:
        resp = client.get(f"/api/reports/{client.report_id}.md")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "自由线程" in resp.text
