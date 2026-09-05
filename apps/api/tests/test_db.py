"""db 层测试:计划书 §5 数据模型 + §3.4 同事务提交语义。"""
import pytest

from orca import db


@pytest.fixture()
def engine(tmp_path):
    eng = db.make_engine(tmp_path / "test.db")
    db.init_db(eng)
    return eng


def test_create_task_returns_running_task(engine):
    task_id = db.create_task(engine, topic="Python 3.13 新特性")

    assert task_id.startswith("t_")
    row = db.get_task(engine, task_id)
    assert row["topic"] == "Python 3.13 新特性"
    assert row["status"] == "running"
    assert row["stop_reason"] is None
    assert row["report_id"] is None
    assert row["created_at"] is not None


def test_complete_task_with_report_writes_both_atomically(engine):
    task_id = db.create_task(engine, topic="Python 3.13 新特性")

    report_id = db.complete_task_with_report(
        engine,
        task_id,
        final_md="# 报告\n正文 [1]",
        citation_map={"1": "ev_001"},
        stop_reason="single_pass",
        config_json={"models": {"writer": "glm-5.3"}},
        token_cost=2757,
        credits_cost=1,
        duration_s=15.2,
        usage={"llm_tokens": 2757, "tavily_credits": 1, "jina_tokens": 0},
    )

    task = db.get_task(engine, task_id)
    assert task["status"] == "completed"
    assert task["report_id"] == report_id
    assert task["stop_reason"] == "single_pass"
    assert task["usage_json"]["llm_tokens"] == 2757

    report = db.get_report(engine, report_id)
    assert report["task_id"] == task_id
    assert report["topic"] == "Python 3.13 新特性"
    assert report["citation_map_json"] == {"1": "ev_001"}
    assert report["final_md"].startswith("# 报告")


def test_fail_task_records_terminal_state(engine):
    task_id = db.create_task(engine, topic="x")
    db.fail_task(engine, task_id, stop_reason="execution_error")

    task = db.get_task(engine, task_id)
    assert task["status"] == "failed"
    assert task["stop_reason"] == "execution_error"


def test_mark_stale_interrupted_only_touches_running(engine):
    keep_running = db.create_task(engine, topic="遗留任务")
    done = db.create_task(engine, topic="已完成")
    db.fail_task(engine, done, stop_reason="timeout")

    n = db.mark_stale_interrupted(engine)

    assert n == 1
    assert db.get_task(engine, keep_running)["status"] == "interrupted"
    assert db.get_task(engine, keep_running)["stop_reason"] == "process_interrupted"
    assert db.get_task(engine, done)["status"] == "failed"


def test_cleanup_clears_all_tables(engine):
    task_id = db.create_task(engine, topic="x")
    report_id = db.complete_task_with_report(
        engine, task_id, final_md="m", citation_map={},
        stop_reason="single_pass", config_json={}, token_cost=0,
        credits_cost=0, duration_s=0.0,
        usage={"llm_tokens": 0, "tavily_credits": 0, "jina_tokens": 0},
    )
    db.record_source(engine, task_id, url="https://docs.python.org/",
                     title="t", domain="docs.python.org", source_type="official",
                     content_hash="h1")

    db.cleanup(engine)

    assert db.get_task(engine, task_id) is None
    assert db.get_report(engine, report_id) is None
    assert db.list_sources(engine, task_id) == []


def test_evidence_unique_per_task(engine):
    task_id = db.create_task(engine, topic="x")
    source_id = db.record_source(engine, task_id, url="https://docs.python.org/a",
                                 title="t", domain="docs.python.org",
                                 source_type="official", content_hash="h")
    db.record_evidence(engine, task_id, evidence_id="ev_001", source_id=source_id,
                       origin_group_id="g1", source_type="official",
                       quote="原文", validated=True)

    with pytest.raises(Exception):
        db.record_evidence(engine, task_id, evidence_id="ev_001", source_id=source_id,
                           origin_group_id="g1", source_type="official",
                           quote="重复 ID", validated=True)


def test_record_search_round(engine):
    task_id = db.create_task(engine, topic="x")
    db.record_search_round(engine, task_id, round_no=1, query="Python 3.13",
                           result_count=5, credits_used=1)

    rounds = db.list_search_rounds(engine, task_id)
    assert len(rounds) == 1
    assert rounds[0]["query"] == "Python 3.13"
    assert rounds[0]["result_count"] == 5
