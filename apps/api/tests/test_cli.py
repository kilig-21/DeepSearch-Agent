"""CLI 测试(fake 工具链 + 临时 DB, 不联网)。

验收口径(§4 Phase 1A):报告与 tasks 同事务落库、时间线日志输出、
失败路径落库、cleanup 清空。
"""
import asyncio

import pytest

from orca import cli
from tests.test_graph import make_tools, happy_llm_sides, default_search_results


def builder():
    def _build(budget):
        tools, events, calls = make_tools(happy_llm_sides(),
                                          search_results=default_search_results())
        return tools
    return _build


def test_cmd_research_persists_everything(tmp_path, capsys):
    db_path = tmp_path / "o.db"
    rc = cli.cmd_research("Python 3.13 新特性?", db_path=db_path,
                          tools_builder=builder())
    assert rc == 0

    from orca import db
    eng = db.make_engine(db_path)
    # 找到任务: 单任务库
    tasks = db.list_tasks(eng)
    assert len(tasks) == 1
    task = tasks[0]
    assert task["status"] == "completed"
    assert task["stop_reason"] == "single_pass"
    assert task["report_id"] is not None

    report = db.get_report(eng, task["report_id"])
    assert "自由线程" in report["final_md"]
    assert report["citation_map_json"] == {"1": "ev_001", "2": "ev_002"}

    evidences = db.list_evidences(eng, task["id"])
    assert [e["evidence_id"] for e in evidences] == \
        ["ev_001", "ev_002", "ev_003"]
    assert all(e["validated"] for e in evidences)

    sources = db.list_sources(eng, task["id"])
    assert {s["url"] for s in sources} == {
        "https://docs.python.org/a", "https://docs.python.org/b"}

    assert len(db.list_search_rounds(eng, task["id"])) == 1

    out = capsys.readouterr().out
    assert "[done]" in out or "[完成]" in out


def test_cmd_research_error_marks_task_failed(tmp_path, capsys):
    db_path = tmp_path / "o.db"

    def bad_builder(budget):
        raise RuntimeError("组件初始化失败")

    rc = cli.cmd_research("Q", db_path=db_path, tools_builder=bad_builder)
    assert rc == 1

    from orca import db
    eng = db.make_engine(db_path)
    task = db.list_tasks(eng)[0]
    assert task["status"] == "failed"
    assert task["stop_reason"] == "execution_error"


def test_cleanup_command_clears_db(tmp_path, capsys):
    db_path = tmp_path / "o.db"
    cli.cmd_research("Q", db_path=db_path, tools_builder=builder())
    rc = cli.cmd_cleanup(db_path=db_path, assume_yes=True)
    assert rc == 0

    from orca import db
    eng = db.make_engine(db_path)
    assert db.list_tasks(eng) == []
    assert db.list_sources(eng, "any") == []


def test_stale_running_marked_interrupted_on_start(tmp_path):
    db_path = tmp_path / "o.db"

    from orca import db
    eng = db.make_engine(db_path)
    db.init_db(eng)
    stale = db.create_task(eng, topic="上次没跑完")

    cli.cmd_research("Q", db_path=db_path, tools_builder=builder())

    assert db.get_task(eng, stale)["status"] == "interrupted"
