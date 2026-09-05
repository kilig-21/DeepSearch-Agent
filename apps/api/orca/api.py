"""FastAPI 应用(计划书 §6, Phase 1B)。

- POST /api/research        创建任务 → 202 {task_id}(落库 tasks)
- GET  /api/research/{id}   状态快照(§3.4 结构;runtime 丢失时由 DB 构造)
- POST /api/research/{id}/cancel  取消 → 202;实际停止后事件流发终态
- GET  /api/health
- 启动时: init_db + 遗留 running → interrupted(§3.4)
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import db
from .config import DB_PATH
from .task_manager import ActiveTaskExists, TaskManager

# 前端 dev 服务器(apps/web, Next.js 15)本地直连 API
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class ResearchCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=500)


def create_app(*, db_path=None, tools_builder=None, budget_builder=None,
               heartbeat_interval: float = 20.0,
               buffer_size: int = 1000) -> FastAPI:
    from .cli import _make_budget, default_tools_builder

    engine = db.make_engine(db_path or DB_PATH)
    db.init_db(engine)  # 幂等; 使任何请求前表已就绪
    manager = TaskManager(
        engine,
        tools_builder=tools_builder or default_tools_builder,
        budget_builder=budget_builder or _make_budget,
        buffer_size=buffer_size)

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

    @app.get("/api/research/{task_id}/events")
    async def research_events(
        task_id: str,
        request: Request,
        after: int | None = None,
    ):
        if db.get_task(engine, task_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        last_id = _parse_last_event_id(request, after)
        return StreamingResponse(
            _event_stream(manager, engine, task_id, last_id,
                          heartbeat_interval),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache",
                     "X-Accel-Buffering": "no",
                     "Connection": "keep-alive"})

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


# ---- SSE(§3.4) --------------------------------------------------------------

def _parse_last_event_id(request: Request, after: int | None) -> int | None:
    """Last-Event-ID 头优先(浏览器自动重连携带);否则用 ?after= URL 参数。"""
    raw = request.headers.get("last-event-id")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            return None
    return after


def _sse_frame(seq: int, event: str, payload: dict) -> str:
    from .task_manager import iso_now
    data = json.dumps({**payload, "ts": iso_now()}, ensure_ascii=False)
    return f"id: {seq}\nevent: {event}\ndata: {data}\n\n"


async def _event_stream(manager: TaskManager, engine, task_id: str,
                        last_id: int | None, heartbeat_interval: float):
    """SSE 事件流(§3.4 两路恢复):

    - 新建连接无 last_id(刷新/视图丢失)→ 先发完整 snapshot 再接增量
    - last_id 在环形缓冲内(普通断线)→ 从缓冲补发, 不重复不遗漏
    - last_id 超出缓冲/超前 → 发 snapshot 对齐
    - 终态事件发完即关闭;interrupted 等 DB 终态快照发送后关闭
    - 断开只取消订阅, 不取消研究任务
    """
    runtime = manager.get_runtime(task_id)
    if runtime is None:
        # runtime 丢失(进程重启): DB 快照(终态或如实说明), 发完即关
        snap = _snapshot(manager, engine, task_id)
        yield _sse_frame(snap["seq"], "snapshot", snap)
        return

    queue: asyncio.Queue = asyncio.Queue()
    sub_id = manager.subscribe(task_id, queue)
    try:
        # 恢复起点: after=0 / Last-Event-ID 落在环形缓冲内 → 直接补发;
        # 无 last_id(刷新)或超出/超前缓冲 → 先发完整 snapshot 对齐(§3.4)
        buffer_first = next(iter(runtime.buffer), None)
        if last_id == 0:
            in_buffer = True
        elif last_id is None:
            in_buffer = False
        elif buffer_first is not None:
            in_buffer = buffer_first.seq <= last_id <= runtime.seq
        else:
            in_buffer = last_id == runtime.seq
        if in_buffer:
            sent = last_id or 0
        else:
            snap = manager.snapshot(task_id)
            sent = snap["seq"]
            yield _sse_frame(sent, "snapshot", snap)

        while True:
            for record in manager.events_after(task_id, sent):
                yield _sse_frame(record.seq, record.event, record.payload)
                sent = record.seq
            if runtime.terminal_recorded and sent >= runtime.seq:
                return  # 终态帧已发出, 关闭流
            try:
                await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        manager.unsubscribe(task_id, sub_id)
