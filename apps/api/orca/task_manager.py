"""进程内 TaskManager(计划书 §2.1/§3.4 Phase 1B)。

- 单 worker:同一时刻最多 1 个活动任务;终态后槽位释放
- 事件:服务端递增 seq + 环形缓冲(仅补发用, 权威状态在 tasks 表)
- emit 是研究链路的取消检查点:取消请求后任何 emit 抛 TaskCancelled
- 终态路径:正常完成 → 同事务落库 → 才发 done;取消 → 不落报告;
  异常 → failed。终态唯一, 后到者丢弃
- 取消不打断阻塞中的 LLM 调用, 在下一个检查点(emit 或 persist 前)生效
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from . import db
from .budget import Budget
from .config import ALLOWED_DOMAINS, FETCH_PROXY
from .graph import GraphTools, run_research
from .persist import persist_task_results

_TERMINAL_EVENTS = {"done", "task_failed", "cancelled"}


class ActiveTaskExists(RuntimeError):
    def __init__(self, active_task_id: str) -> None:
        super().__init__(f"已有活动任务: {active_task_id}")
        self.active_task_id = active_task_id


class TaskCancelled(Exception):
    """取消请求已生效, 研究链路中止(不走 execution_error 路径)。"""


@dataclass
class EventRecord:
    seq: int
    event: str
    payload: dict


@dataclass
class Subscriber:
    id: int
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


@dataclass
class TaskRuntime:
    task_id: str
    topic: str
    status: str = "running"
    stop_reason: str | None = None
    report_id: int | None = None
    seq: int = 0
    buffer: deque = field(default_factory=lambda: deque(maxlen=1000))
    subscribers: dict = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)
    terminal_recorded: bool = False
    # 运行进度(snapshot 用)
    sub_questions: list = field(default_factory=list)
    round_no: int = 0
    sources_read: int = 0
    evidence_count: int = 0
    draft_md: str = ""


class TaskManager:
    def __init__(self, engine, *, tools_builder, budget_builder,
                 persist_fn=persist_task_results, buffer_size: int = 1000) -> None:
        self._engine = engine
        self._tools_builder = tools_builder
        self._budget_builder = budget_builder
        self._persist_fn = persist_fn
        self._buffer_size = buffer_size
        self._lock = threading.Lock()
        self._active_task_id: str | None = None
        self._runtimes: dict[str, TaskRuntime] = {}
        self._sub_seq = 0

    # ---- 创建与查询 -------------------------------------------------------

    def create(self, topic: str) -> str:
        with self._lock:
            if self._active_task_id is not None:
                raise ActiveTaskExists(self._active_task_id)
            task_id = db.create_task(self._engine, topic=topic)
            self._active_task_id = task_id
        runtime = TaskRuntime(
            task_id=task_id, topic=topic,
            buffer=deque(maxlen=self._buffer_size))
        self._runtimes[task_id] = runtime
        threading.Thread(target=self._run_task, args=(runtime, topic),
                         daemon=True, name=f"orca-task-{task_id}").start()
        return task_id

    def is_active(self, task_id: str) -> bool:
        with self._lock:
            return self._active_task_id == task_id

    def get_runtime(self, task_id: str) -> TaskRuntime | None:
        return self._runtimes.get(task_id)

    def recover_interrupted(self) -> int:
        """进程启动时把遗留 running 标 interrupted(§3.4; 草稿不可恢复)。"""
        return db.mark_stale_interrupted(self._engine)

    # ---- 取消 -------------------------------------------------------------

    def request_cancel(self, task_id: str) -> bool:
        """仅活动中的任务可取消;终态后拒绝。"""
        with self._lock:
            if self._active_task_id != task_id:
                return False
        runtime = self._runtimes.get(task_id)
        if runtime is None or runtime.terminal_recorded:
            return False
        runtime.cancel_event.set()
        return True

    # ---- 订阅(供 SSE 端点使用) -------------------------------------------

    def subscribe(self, task_id: str, queue: asyncio.Queue) -> int:
        runtime = self._runtimes[task_id]
        with self._lock:
            self._sub_seq += 1
            sub = Subscriber(id=self._sub_seq, queue=queue,
                             loop=asyncio.get_running_loop())
            runtime.subscribers[sub.id] = sub
        return sub.id

    def unsubscribe(self, task_id: str, sub_id: int) -> None:
        runtime = self._runtimes.get(task_id)
        if runtime:
            runtime.subscribers.pop(sub_id, None)

    def events_after(self, task_id: str, last_seq: int) -> list[EventRecord]:
        runtime = self._runtimes.get(task_id)
        if runtime is None:
            return []
        with self._lock:  # 与写入端同一临界区: 读到的 seq/缓冲一致(P4)
            return [e for e in runtime.buffer if e.seq > last_seq]

    def drain(self, task_id: str, sent: int) -> tuple[list[EventRecord], bool]:
        """SSE 循环取数(第五轮评审 R1):事件副本、终态标志、seq 在**同一
        锁临界区**内读取, 返回 (sent 之后的事件, terminal_visible)。

        terminal_visible 仅当"终态标志已置且 sent 已追上当前 seq"——
        此时缓冲中不可能再有未取的终态事件, SSE 端可安全关闭。
        SSE 端不得再锁外裸读 runtime 字段判断关闭(裸读可见
        "标志=True、seq 仍旧值"的中间态, 会漏发终态帧)。"""
        runtime = self._runtimes.get(task_id)
        if runtime is None:
            return ([], True)  # runtime 已消失: 不会有更多事件
        with self._lock:
            events = [e for e in runtime.buffer if e.seq > sent]
            terminal_visible = runtime.terminal_recorded and sent >= runtime.seq
            return (events, terminal_visible)

    def resume_plan(self, task_id: str,
                    last_id: int | None) -> tuple[str, int]:
        """SSE 恢复决策(§3.4 两路恢复; 第四轮评审 P4, 同一临界区原子判定):

        - ("snapshot", seq):无游标(含 0/负数)或游标超出缓冲覆盖范围 →
          客户端须先收完整 snapshot 对齐到当前 seq
        - ("replay", last_id):游标落在缓冲覆盖范围内 → 从缓冲补发增量

        任何路径都不允许"仅凭客户端 seq 请求增量"。"""
        runtime = self._runtimes.get(task_id)
        if runtime is None:
            return ("missing", 0)
        with self._lock:
            seq = runtime.seq
            buffer_first = next(iter(runtime.buffer), None)
            if last_id is None or last_id <= 0:      # 无游标(0 视同无游标)
                return ("snapshot", seq)
            if buffer_first is not None and \
                    buffer_first.seq <= last_id <= seq:  # 覆盖范围内 → 补发
                return ("replay", last_id)
            return ("snapshot", seq)                 # 超出/超前 → 对齐

    # ---- 快照(§3.4 v1.3 扩充结构) -----------------------------------------

    def snapshot(self, task_id: str) -> dict | None:
        """状态快照(§3.4 v1.3; 第四轮评审 P3):正文/进度/seq 在同一锁
        临界区内一次取全, 三者对应同一时点;running 且有草稿时 report_md
        必须是已生成正文(刷新恢复不丢草稿)。DB 读在锁外(锁内不做 IO)。"""
        with self._lock:
            runtime = self._runtimes.get(task_id)
            if runtime is None:
                return None
            status = runtime.status
            report_id = runtime.report_id
            report_md = runtime.draft_md
            citation_map: dict = {}
            progress = {"sources_read": runtime.sources_read,
                        "evidence_count": runtime.evidence_count}
            sub_questions = list(runtime.sub_questions)
            round_no = runtime.round_no
            stop_reason = runtime.stop_reason
            seq = runtime.seq
        if status == "completed" and report_id is not None:
            report = db.get_report(self._engine, report_id)
            if report:
                report_md = report["final_md"]
                citation_map = report["citation_map_json"]
        # cancelled/failed/interrupted: 草稿已在终态临界区清空 → 如实为空
        return {
            "task_id": task_id,
            "status": status,
            "stop_reason": stop_reason,
            "report_id": report_id,
            "round_no": round_no,
            "sub_questions": sub_questions,
            "progress": progress,
            "report_md": report_md,
            "citation_map": citation_map,
            "seq": seq,
        }

    # ---- worker 线程 -------------------------------------------------------

    def _run_task(self, runtime: TaskRuntime, topic: str) -> None:
        task_id = runtime.task_id
        budget: Budget | None = None
        t0 = time.monotonic()
        try:
            budget = self._budget_builder()
            tools: GraphTools = self._tools_builder(budget)
            tools.emit = self._wrap_emit(runtime)
            state = asyncio.run(run_research(tools, topic, task_id=task_id))
            state["duration_s"] = time.monotonic() - t0
            if runtime.cancel_event.is_set():  # persist 前最后检查(§3.4)
                raise TaskCancelled
            usage = budget.usage_snapshot()
            report_id = self._persist_fn(
                self._engine, task_id, state, budget,
                allowed_domains=tools.allowed_domains,
                proxy=tools.proxy is not None)
            if report_id is None:
                # 未抢到终态提交权(已被取消/失败抢先)→ 后到结果丢弃,
                # 不发 done(P6);取消侧负责 cancelled 收尾
                raise TaskCancelled
            runtime.report_id = report_id
            self._record_terminal(runtime, "done", {
                "report_id": report_id,
                "stop_reason": state.get("stop_reason") or "single_pass",
                "token_cost": usage["llm_tokens"],
                "credits_cost": usage["tavily_credits"],
                "duration_s": state["duration_s"],
            })
        except TaskCancelled:
            self._finish_cancelled(runtime)
        except Exception as e:  # noqa: BLE001
            db.fail_task(self._engine, task_id, stop_reason="execution_error")
            self._record_terminal(runtime, "task_failed", {
                "detail": f"{type(e).__name__}: {e}",
                "stop_reason": "execution_error"})
        finally:
            runtime.finished.set()
            with self._lock:
                if self._active_task_id == task_id:
                    self._active_task_id = None

    def _finish_cancelled(self, runtime: TaskRuntime) -> None:
        db.cancel_task(self._engine, runtime.task_id,
                       stop_reason="user_cancelled")
        self._record_terminal(runtime, "cancelled",
                              {"stop_reason": "user_cancelled"})

    # ---- emit 包装(取消检查点 + 进度跟踪 + 发布) ------------------------------

    def _wrap_emit(self, runtime: TaskRuntime):
        def emit(event: str, payload: dict) -> None:
            if runtime.cancel_event.is_set():
                raise TaskCancelled
            self._record(runtime, event, payload)
        return emit

    def _record(self, runtime: TaskRuntime, event: str, payload: dict) -> None:
        with self._lock:
            self._record_locked(runtime, event, payload)

    def _record_locked(self, runtime: TaskRuntime, event: str,
                       payload: dict) -> None:
        """须持 self._lock 调用:seq/缓冲/进度/订阅推送一次临界区完成(P5)。"""
        self._track_progress(runtime, event, payload)
        runtime.seq += 1
        record = EventRecord(
            seq=runtime.seq, event=event,
            payload={**payload, "task_id": runtime.task_id,
                     "ts": iso_now()})
        runtime.buffer.append(record)
        self._publish(runtime, record)

    def _track_progress(self, runtime: TaskRuntime, event: str,
                        payload: dict) -> None:
        if event == "plan":
            runtime.sub_questions = list(payload.get("sub_questions", []))
        elif event == "search":
            runtime.round_no = max(runtime.round_no,
                                   int(payload.get("round", 0)))
        elif event == "reading":
            runtime.sources_read += 1
        elif event == "note":
            runtime.evidence_count += 1
        elif event == "report_delta":
            if payload.get("replace"):
                runtime.draft_md = str(payload.get("md", ""))  # 修订整体替换
            else:
                runtime.draft_md += str(payload.get("md", ""))

    def _record_terminal(self, runtime: TaskRuntime, event: str,
                         payload: dict) -> None:
        """终态唯一 + 原子发布(§3.4; 第四轮评审 P5):terminal 标志、
        状态、seq、缓冲事件、订阅推送在同一锁临界区内一次完成——
        终态事件可被读到之前, terminal 标志不可能先行可见。"""
        with self._lock:
            if runtime.terminal_recorded:
                return
            runtime.terminal_recorded = True
            status = {"done": "completed", "task_failed": "failed",
                      "cancelled": "cancelled"}[event]
            runtime.status = status
            runtime.stop_reason = payload.get("stop_reason") or runtime.stop_reason
            if event != "done":
                runtime.draft_md = ""  # 非完成终态: 草稿不作为内容暴露
            self._record_locked(runtime, event, payload)

    def _publish(self, runtime: TaskRuntime, record: EventRecord) -> None:
        for sub in list(runtime.subscribers.values()):
            try:
                sub.loop.call_soon_threadsafe(sub.queue.put_nowait, record)
            except RuntimeError:
                pass  # 事件循环已关闭(客户端断开), 忽略

    def _runtime_for_test(self, task_id: str, topic: str) -> TaskRuntime:
        runtime = TaskRuntime(task_id=task_id, topic=topic)
        self._runtimes[task_id] = runtime
        return runtime

    def wait(self, task_id: str, timeout: float) -> bool:
        runtime = self._runtimes.get(task_id)
        return runtime is not None and runtime.finished.wait(timeout)


def iso_now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat(timespec="milliseconds")
