"""SQLite 持久层(计划书 §5)。

要点:
- sources 按任务存不可变快照,不设全局 url UNIQUE(§5 v1.2)
- evidences UNIQUE(task_id, evidence_id) 引用映射契约(§3.3)
- 报告写入与 tasks 状态更新在同一事务提交(§3.4)
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import ForeignKey, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    # topic 属任务元数据:创建时已知,报告尚不存在(§5 概要模型的必要补充)
    topic: Mapped[str]
    status: Mapped[str]  # running|completed|failed|cancelled|interrupted
    stop_reason: Mapped[str | None]
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"))
    usage_json: Mapped[str] = mapped_column(default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    topic: Mapped[str]
    final_md: Mapped[str]
    citation_map_json: Mapped[str] = mapped_column(default="{}")
    stop_reason: Mapped[str]
    config_json: Mapped[str] = mapped_column(default="{}")
    token_cost: Mapped[int] = mapped_column(default=0)
    credits_cost: Mapped[int] = mapped_column(default=0)
    duration_s: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    url: Mapped[str]
    title: Mapped[str]
    domain: Mapped[str]
    source_type: Mapped[str]  # official|media|blog|ugc|paper
    origin_group_id: Mapped[str | None]
    content_hash: Mapped[str]
    fetched_at: Mapped[datetime] = mapped_column(default=_now)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Evidence(Base):
    __tablename__ = "evidences"
    __table_args__ = (UniqueConstraint("task_id", "evidence_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    evidence_id: Mapped[str]
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    origin_group_id: Mapped[str | None]
    source_type: Mapped[str]
    quote: Mapped[str]
    validated: Mapped[bool] = mapped_column(default=False)


class SearchRound(Base):
    __tablename__ = "search_rounds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    round_no: Mapped[int]
    query: Mapped[str]
    result_count: Mapped[int]
    credits_used: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)


def make_engine(db_path: Path | str):
    p = Path(db_path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{p}")


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def _task_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "topic": t.topic,
        "status": t.status,
        "stop_reason": t.stop_reason,
        "report_id": t.report_id,
        "usage_json": json.loads(t.usage_json),
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


def create_task(engine, topic: str) -> str:
    task_id = f"t_{uuid.uuid4().hex[:12]}"
    with Session(engine) as session, session.begin():
        session.add(Task(id=task_id, topic=topic, status="running"))
    return task_id


def get_task(engine, task_id: str) -> dict | None:
    with Session(engine) as session:
        t = session.get(Task, task_id)
        return _task_dict(t) if t else None


def complete_task_with_report(
    engine,
    task_id: str,
    *,
    final_md: str,
    citation_map: dict,
    stop_reason: str,
    config_json: dict,
    token_cost: int,
    credits_cost: int,
    duration_s: float,
    usage: dict,
) -> int:
    """报告与 tasks 终态在同一个事务内提交(§3.4);提交前不发任何终态事件。"""
    with Session(engine) as session, session.begin():
        report = Report(
            task_id=task_id,
            topic="",
            final_md=final_md,
            citation_map_json=json.dumps(citation_map, ensure_ascii=False),
            stop_reason=stop_reason,
            config_json=json.dumps(config_json, ensure_ascii=False),
            token_cost=token_cost,
            credits_cost=credits_cost,
            duration_s=duration_s,
        )
        session.add(report)
        session.flush()  # 取 report.id
        task = session.get(Task, task_id)
        report.topic = task.topic
        task.status = "completed"
        task.stop_reason = stop_reason
        task.report_id = report.id
        task.usage_json = json.dumps(usage, ensure_ascii=False)
        return report.id


def fail_task(engine, task_id: str, *, stop_reason: str) -> None:
    _set_terminal(engine, task_id, status="failed", stop_reason=stop_reason)


def cancel_task(engine, task_id: str, *, stop_reason: str = "user_cancelled") -> None:
    _set_terminal(engine, task_id, status="cancelled", stop_reason=stop_reason)


def _set_terminal(engine, task_id: str, *, status: str, stop_reason: str) -> None:
    """终态转移:仅 running 可流转, 最终状态一旦提交不得覆盖(§3.4)。"""
    with Session(engine) as session, session.begin():
        task = session.get(Task, task_id)
        if task and task.status == "running":
            task.status = status
            task.stop_reason = stop_reason


def mark_stale_interrupted(engine) -> int:
    """进程启动时把遗留 running 任务标为 interrupted(§3.4)。"""
    with Session(engine) as session, session.begin():
        rows = session.scalars(select(Task).where(Task.status == "running")).all()
        for t in rows:
            t.status = "interrupted"
            t.stop_reason = "process_interrupted"
        return len(rows)


def cleanup(engine) -> None:
    """本地数据清理(§6:`python -m orca cleanup`,后端停止后执行)。"""
    with Session(engine) as session, session.begin():
        for model in (SearchRound, Evidence, Source, Report, Task):
            session.query(model).delete()


def get_report(engine, report_id: int) -> dict | None:
    with Session(engine) as session:
        r = session.get(Report, report_id)
        if not r:
            return None
        return {
            "id": r.id,
            "task_id": r.task_id,
            "topic": r.topic,
            "final_md": r.final_md,
            "citation_map_json": json.loads(r.citation_map_json),
            "stop_reason": r.stop_reason,
            "config_json": json.loads(r.config_json),
            "token_cost": r.token_cost,
            "credits_cost": r.credits_cost,
            "duration_s": r.duration_s,
            "created_at": r.created_at,
        }


def record_source(engine, task_id: str, *, url: str, title: str, domain: str,
                  source_type: str, content_hash: str,
                  origin_group_id: str | None = None) -> int:
    with Session(engine) as session, session.begin():
        s = Source(task_id=task_id, url=url, title=title, domain=domain,
                   source_type=source_type, content_hash=content_hash,
                   origin_group_id=origin_group_id)
        session.add(s)
        session.flush()
        return s.id


def list_sources(engine, task_id: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(select(Source).where(Source.task_id == task_id)).all()
        return [{"id": s.id, "url": s.url, "title": s.title, "domain": s.domain,
                 "source_type": s.source_type, "content_hash": s.content_hash,
                 "origin_group_id": s.origin_group_id} for s in rows]


def record_evidence(engine, task_id: str, *, evidence_id: str, source_id: int,
                    origin_group_id: str | None, source_type: str, quote: str,
                    validated: bool) -> None:
    with Session(engine) as session, session.begin():
        session.add(Evidence(task_id=task_id, evidence_id=evidence_id,
                             source_id=source_id, origin_group_id=origin_group_id,
                             source_type=source_type, quote=quote,
                             validated=validated))


def record_search_round(engine, task_id: str, *, round_no: int, query: str,
                        result_count: int, credits_used: int) -> None:
    with Session(engine) as session, session.begin():
        session.add(SearchRound(task_id=task_id, round_no=round_no, query=query,
                                result_count=result_count, credits_used=credits_used))


def list_search_rounds(engine, task_id: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(
            select(SearchRound).where(SearchRound.task_id == task_id)
        ).all()
        return [{"round_no": r.round_no, "query": r.query,
                 "result_count": r.result_count, "credits_used": r.credits_used}
                for r in rows]


def list_tasks(engine) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(select(Task).order_by(Task.created_at)).all()
        return [_task_dict(t) for t in rows]


def list_evidences(engine, task_id: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(select(Evidence).where(
            Evidence.task_id == task_id)).all()
        return [{"evidence_id": e.evidence_id, "source_id": e.source_id,
                 "quote": e.quote, "validated": e.validated,
                 "origin_group_id": e.origin_group_id,
                 "source_type": e.source_type} for e in rows]
