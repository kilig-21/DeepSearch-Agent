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
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
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
    async def research_events(task_id: str, request: Request):
        if db.get_task(engine, task_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        last_id = _parse_last_event_id(request)
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

    @app.get("/api/reports")
    def list_reports() -> list[dict]:
        return db.list_reports(engine)

    # .md 路由须先于 {report_id} 注册, 否则 "5.md" 被吞进 int 转换报 422
    @app.get("/api/reports/{report_id}.md")
    def report_markdown(report_id: int):
        report = db.get_report(engine, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        return PlainTextResponse(report["final_md"],
                                 media_type="text/markdown; charset=utf-8")

    @app.get("/api/reports/{report_id}")
    def report_detail(report_id: int) -> dict:
        report = db.get_report(engine, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        return {**report,
                "evidences": db.list_evidences(engine, report["task_id"]),
                "sources": db.list_sources(engine, report["task_id"])}

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

def _parse_last_event_id(request: Request) -> int | None:
    """游标只来自 Last-Event-ID 头(浏览器 EventSource 自动重连携带;
    第四轮评审 P4:?after= URL 参数路径已删除, 不得仅凭客户端 seq 请求增量)。"""
    raw = request.headers.get("last-event-id")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _sse_frame(seq: int, event: str, payload: dict) -> str:
    from .task_manager import iso_now
    data = json.dumps({**payload, "ts": iso_now()}, ensure_ascii=False)
    return f"id: {seq}\nevent: {event}\ndata: {data}\n\n"


async def _event_stream(manager: TaskManager, engine, task_id: str,
                        last_id: int | None, heartbeat_interval: float):
    """SSE 事件流(§3.4 两路恢复; 第四轮评审 P4 游标收敛):

    - 新建连接无游标(刷新/视图丢失, 含 Last-Event-ID: 0)→ 先发完整
      snapshot 对齐, 再接增量——不凭客户端 seq 从头补发
    - Last-Event-ID 落在环形缓冲覆盖范围内(普通断线)→ 从缓冲补发增量
    - 超出/超前缓冲覆盖 → 回退完整 snapshot 对齐
    - 恢复决策与 seq/缓冲读取同一临界区(manager.resume_plan),
      消除 snapshot 与事件发布的竞争
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
        mode, from_seq = manager.resume_plan(task_id, last_id)
        if mode == "snapshot":
            snap = manager.snapshot(task_id)
            sent = snap["seq"]
            yield _sse_frame(sent, "snapshot", snap)
        else:  # replay: 缓冲覆盖范围内, 从游标之后补发
            sent = from_seq

        while True:
            # R1: 事件副本与终态可见性同一临界区取得, 不再裸读 runtime 字段
            events, terminal_visible = manager.drain(task_id, sent)
            for record in events:
                yield _sse_frame(record.seq, record.event, record.payload)
                sent = record.seq
            if terminal_visible:
                return  # 终态帧已发出且 sent 追上 seq, 关闭流
            try:
                await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        manager.unsubscribe(task_id, sub_id)
