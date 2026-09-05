"""FastAPI 应用(计划书 §6, Phase 1B)。

- POST /api/research        创建任务 → 202 {task_id}(落库 tasks)
- GET  /api/research/{id}   状态快照(§3.4 结构;runtime 丢失时由 DB 构造)
- POST /api/research/{id}/cancel  取消 → 202;实际停止后事件流发终态
- GET  /api/health
- 启动时: init_db + 遗留 running → interrupted(§3.4)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db
from .config import DB_PATH
from .task_manager import ActiveTaskExists, TaskManager

# 前端 dev 服务器(apps/web, Next.js 15)本地直连 API
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class ResearchCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=500)


def create_app(*, db_path=None, tools_builder=None, budget_builder=None) -> FastAPI:
    from .cli import _make_budget, default_tools_builder

    engine = db.make_engine(db_path or DB_PATH)
    db.init_db(engine)  # 幂等; 使任何请求前表已就绪
    manager = TaskManager(
        engine,
        tools_builder=tools_builder or default_tools_builder,
        budget_builder=budget_builder or _make_budget)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager.recover_interrupted()  # 启动时遗留 running → interrupted(§3.4)
        yield

    app = FastAPI(title="Orca Research", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=CORS_ORIGINS,
        allow_methods=["*"], allow_headers=["*"])
    app.state.engine = engine
    app.state.manager = manager

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/research", status_code=202)
    def create_research(body: ResearchCreate) -> dict:
        try:
            task_id = manager.create(body.topic)
        except ActiveTaskExists as e:
            return JSONResponse(status_code=409, content={
                "detail": str(e), "active_task_id": e.active_task_id})
        return {"task_id": task_id}

    @app.get("/api/research/{task_id}")
    def get_research(task_id: str) -> dict:
        snap = _snapshot(manager, engine, task_id)
        if snap is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return snap

    @app.post("/api/research/{task_id}/cancel", status_code=202)
    def cancel_research(task_id: str) -> dict:
        if db.get_task(engine, task_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        if not manager.request_cancel(task_id):
            raise HTTPException(status_code=409, detail="任务已终态, 不可取消")
        return {"task_id": task_id, "cancelling": True}

    return app


def _snapshot(manager: TaskManager, engine, task_id: str) -> dict | None:
    """快照:优先内存 runtime;runtime 丢失(重启)由 DB 构造, 草稿如实为空。"""
    snap = manager.snapshot(task_id)
    if snap is not None:
        return snap
    task = db.get_task(engine, task_id)
    if task is None:
        return None
    report_md, citation_map = "", {}
    if task["report_id"] is not None:
        report = db.get_report(engine, task["report_id"])
        if report:
            report_md = report["final_md"]
            citation_map = report["citation_map_json"]
    return {
        "task_id": task_id,
        "status": task["status"],
        "stop_reason": task["stop_reason"],
        "report_id": task["report_id"],
        "round_no": 0,
        "sub_questions": [],
        "progress": {"sources_read": 0, "evidence_count": 0},
        "report_md": report_md,
        "citation_map": citation_map,
        "seq": 0,
    }
