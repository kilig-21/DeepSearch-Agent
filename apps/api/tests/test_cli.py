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
        # budget 必须是 cmd_research 传入的同一实例: 记账走它, persist 落库也走它
        tools, events, calls = make_tools(happy_llm_sides(),
                                          search_results=default_search_results(),
                                          budget=budget)
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


def test_cmd_research_out_fills_task_id_and_state(tmp_path, capsys):
    """评测 runner 依赖 out 回传 task_id/state 取回本次任务结果,
    不用 list_tasks()[-1](并发写入同一 DB 时会拿错行)。"""
    db_path = tmp_path / "o.db"
    out: dict = {}
    rc = cli.cmd_research("Q", db_path=db_path, tools_builder=builder(),
                          out=out)
    assert rc == 0
    assert out["task_id"]
    assert out["report_id"]
    assert out["state"]["report_md"]
    assert out["state"]["stop_reason"] == "single_pass"

    from orca import db
    eng = db.make_engine(db_path)
    task = [t for t in db.list_tasks(eng) if t["id"] == out["task_id"]][0]
    assert task["status"] == "completed"


def test_cmd_research_out_fills_task_id_on_failure(tmp_path, capsys):
    db_path = tmp_path / "o.db"

    def bad_builder(budget):
        raise RuntimeError("boom")

    out: dict = {}
    rc = cli.cmd_research("Q", db_path=db_path, tools_builder=bad_builder,
                          out=out)
    assert rc == 1
    assert out["task_id"]  # 失败任务也能定位到行


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


# ---- 成本分账(块 2): 终态事件/落库/一条命令均可查 ---------------------------

def test_usage_breakdown_persisted_and_in_done_event(tmp_path, monkeypatch):
    """分账三路可达: done 事件 payload、tasks.usage_json、cost 命令输出。"""
    payloads: list = []
    monkeypatch.setattr(cli, "console_emit",
                        lambda e, p: payloads.append((e, p)))
    db_path = tmp_path / "o.db"
    rc = cli.cmd_research("Q", db_path=db_path, tools_builder=builder())
    assert rc == 0

    from orca import db
    eng = db.make_engine(db_path)
    task = db.list_tasks(eng)[0]
    usage = task["usage_json"]
    # happy 链路: planner+2页 reader 走研究账, writer 走预留
    assert usage["llm_research_tokens"] == 450
    assert usage["llm_writer_tokens"] == 150
    assert usage["llm_tokens"] == 600

    done = [p for e, p in payloads if e == "done"][-1]
    assert done["usage"] == usage   # 终态事件带完整分账


def test_cmd_cost_prints_breakdown(tmp_path, capsys):
    """一条命令输出单任务成本小结(块 2)。"""
    db_path = tmp_path / "o.db"
    cli.cmd_research("Q", db_path=db_path, tools_builder=builder())
    capsys.readouterr()

    rc = cli.cmd_cost(None, last=True, db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "LLM tokens: 600" in out
    assert "研究 450" in out and "writer 150" in out
    assert "Tavily credits" in out and "Jina" in out
    assert "stop_reason" in out


def test_cmd_cost_by_task_id(tmp_path, capsys):
    db_path = tmp_path / "o.db"
    out: dict = {}
    cli.cmd_research("Q", db_path=db_path, tools_builder=builder(), out=out)
    capsys.readouterr()

    rc = cli.cmd_cost(out["task_id"], db_path=db_path)
    assert rc == 0
    assert out["task_id"] in capsys.readouterr().out


def test_cmd_cost_unknown_task_fails(tmp_path, capsys):
    rc = cli.cmd_cost("no_such_task", db_path=tmp_path / "empty.db")
    assert rc == 1
