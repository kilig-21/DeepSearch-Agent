"""SSE 事件流测试(§3.4 恢复语义, fake 工具链 + 临时 DB, 不联网)。

- 新建连接(刷新/视图丢失)→ 第一帧必为完整 snapshot(含 report_md 前半段)
- 普通断线(Last-Event-ID)→ 从环形缓冲补发, 不重复不遗漏
- Last-Event-ID 超出缓冲 → 发 snapshot 对齐
- ?after= URL 参数等价 Last-Event-ID(头优先)
- 心跳 ": ping";终态事件后关闭;终态快照(如 interrupted)也发送后关闭

流式读取用 httpx ASGITransport 直连 app(事件循环内), 避免 TestClient
portal 的线程绑定问题;非流式请求仍用 TestClient。
"""
import asyncio
import json
import threading

from fastapi.testclient import TestClient

from orca import db
from tests.test_graph import (
    default_search_results,
    happy_llm_sides,
    make_tools,
)
from tests.test_task_manager import _done_builder, _writer_block_tools

HB = 0.2  # 测试心跳间隔(秒), 生产 20s


def _happy_builder():
    def _build(budget):
        tools, _e, _c = make_tools(happy_llm_sides(),
                                   search_results=default_search_results())
        tools.budget = budget
        return tools
    return _build


def _make_client(tmp_path, name="o.db", builder=None, **kw):
    from orca.api import create_app
    db_path = tmp_path / name
    app = create_app(db_path=db_path, tools_builder=builder or _happy_builder(),
                     heartbeat_interval=HB, **kw)
    client = TestClient(app)
    client.app_state = app.state
    client.app_obj = app
    client.db_path = db_path
    return client


def _run_to_completion(client, topic="Python 3.13 新特性?") -> str:
    task_id = client.post("/api/research", json={"topic": topic}).json()["task_id"]
    assert client.app_state.manager.wait(task_id, timeout=15)
    return task_id


def parse_sse(lines):
    frames = []
    cur = {}
    for line in lines:
        if line == "":
            if cur:
                frames.append(cur)
                cur = {}
        elif line.startswith("id: "):
            cur["id"] = int(line[4:])
        elif line.startswith("event: "):
            cur["event"] = line[7:]
        elif line.startswith("data: "):
            cur["data"] = json.loads(line[6:])
        elif line.startswith(": "):
            cur["comment"] = line[2:]
    if cur:
        frames.append(cur)
    return frames


def collect(client, path, *, headers=None, stop=None):
    """主线程读流;stop(lines) 返回 True 时主动断开(模拟浏览者关闭页面)。

    仅在终态后或 stop 条件必然满足时使用, 否则主线程会阻塞到流关闭。
    """
    lines = []
    with client.stream("GET", path, headers=headers) as resp:
        for line in resp.iter_lines():
            lines.append(line)
            if stop is not None and stop(lines):
                break
    return lines


def _stop_after_frames(n):
    def _stop(lines):
        complete, started = 0, False
        for line in lines:  # 只数以空行结尾的完整帧
            if line == "":
                if started:
                    complete += 1
                    started = False
            else:
                started = True
        return complete >= n
    return _stop


# ---- 帧格式 -------------------------------------------------------------------

def test_unknown_task_404(tmp_path):
    with _make_client(tmp_path) as client:
        with client.stream("GET", "/api/research/t_nope/events") as resp:
            assert resp.status_code == 404


def test_frames_carry_id_event_data_with_task_id_and_ts(tmp_path):
    with _make_client(tmp_path) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events")
    assert lines is not None  # 流自然关闭(终态后), 未超时
    frames = parse_sse(lines)
    assert frames, "应至少有一帧"
    for f in frames:
        if "comment" in f:
            continue
        assert isinstance(f["id"], int)
        assert f["event"]
        assert f["data"]["task_id"] == task_id
        assert f["data"]["ts"]
    seqs = [f["id"] for f in frames if "id" in f]
    assert seqs == sorted(seqs)
    assert seqs[0] >= 1


# ---- 刷新路径: 新建连接先完整 snapshot ------------------------------------------

def test_new_connection_gets_snapshot_first_then_terminal_close(tmp_path):
    with _make_client(tmp_path) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events")
    assert lines is not None
    frames = parse_sse(lines)
    first = frames[0]
    assert first["event"] == "snapshot"
    snap = first["data"]
    for key in ("status", "stop_reason", "report_id", "round_no", "sub_questions",
                "progress", "report_md", "citation_map", "seq", "task_id"):
        assert key in snap
    assert snap["status"] == "completed"
    assert "自由线程" in snap["report_md"]
    assert snap["citation_map"] == {"1": "ev_001", "2": "ev_002"}
    assert snap["report_id"] is not None
    # snapshot 已呈现终态(§3.4: 客户端据此 close);若仍有补发帧, 不重复
    rest = [f for f in frames[1:] if "id" in f]
    assert all(f["id"] > first["id"] for f in rest)
    # 终态快照之后流关闭(collect 返回即已确认, 不会无限挂着)


def test_running_task_snapshot_has_draft_progress(tmp_path):
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_block_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        assert gate.wait(5)
        lines = collect(client, f"/api/research/{task_id}/events",
                        stop=_stop_after_frames(1))
        assert lines is not None
        frames = parse_sse(lines)
        assert frames[0]["event"] == "snapshot"
        snap = frames[0]["data"]
        assert snap["status"] == "running"
        assert snap["stop_reason"] is None
        assert snap["sub_questions"]
        assert snap["progress"]["sources_read"] >= 1
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)


# ---- 普通断线路径: Last-Event-ID 补发 -------------------------------------------

def test_last_event_id_resumes_from_buffer_without_duplicates(tmp_path):
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_block_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        # 连接1: after=0 从事件开头读(模拟已收到若干事件的页面), 读 4 帧断开
        lines = collect(client, f"/api/research/{task_id}/events?after=0",
                        stop=_stop_after_frames(4))
        frames = parse_sse(lines)
        assert frames and all(f["event"] != "snapshot" for f in frames), \
            "after=0 的普通断线恢复应直接补发, 不发 snapshot"
        last_id = frames[-1]["id"]
        gate.wait(5)
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)

        # 连接2: Last-Event-ID=last_id → 缓冲内补发
        lines2 = collect(client, f"/api/research/{task_id}/events",
                         headers={"Last-Event-ID": str(last_id)})
    assert lines2 is not None
    resumed = parse_sse(lines2)
    assert resumed[0]["event"] != "snapshot"  # 缓冲内直接补发
    assert all(f["id"] > last_id for f in resumed if "id" in f)
    assert resumed[-1]["event"] == "done"


def test_stale_last_event_id_falls_back_to_snapshot(tmp_path):
    with _make_client(tmp_path, buffer_size=3) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events",
                        headers={"Last-Event-ID": "1"})
    assert lines is not None
    frames = parse_sse(lines)
    assert frames[0]["event"] == "snapshot"  # 超出缓冲 → snapshot 对齐
    assert all(f["id"] > frames[0]["id"] for f in frames[1:] if "id" in f)


def test_after_query_param_equals_last_event_id(tmp_path):
    with _make_client(tmp_path) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events?after=1")
    assert lines is not None
    frames = parse_sse(lines)
    ids = [f["id"] for f in frames if "id" in f]
    assert ids and min(ids) > 1


def test_last_event_id_header_takes_precedence_over_after(tmp_path):
    with _make_client(tmp_path) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events?after=1",
                        headers={"Last-Event-ID": "999999"})
    assert lines is not None
    frames = parse_sse(lines)
    # 999999 超前于服务端 seq → snapshot 对齐(头优先于 after)
    assert frames[0]["event"] == "snapshot"


# ---- 终态与心跳 ----------------------------------------------------------------

def test_heartbeat_sent_when_idle(tmp_path):
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_block_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        assert gate.wait(5)
        lines = collect(
            client, f"/api/research/{task_id}/events",
            stop=lambda ls: any(l.startswith(": ") for l in ls))
        assert lines is not None and \
            any(l.startswith(": ") for l in lines), "空闲期间应有心跳注释帧"
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)


def test_interrupted_task_snapshot_then_close(tmp_path):
    """进程重启后: interrupted 任务 → 终态快照发送后关闭(不无限重连)。"""
    from orca import db as db_mod
    db_path = tmp_path / "o.db"
    eng = db_mod.make_engine(db_path)
    db_mod.init_db(eng)
    stale = db_mod.create_task(eng, topic="遗留")

    with _make_client(tmp_path, name="o.db") as client:
        lines = collect(client, f"/api/research/{stale}/events")
    assert lines is not None
    frames = parse_sse(lines)
    assert len(frames) == 1
    assert frames[0]["event"] == "snapshot"
    assert frames[0]["data"]["status"] == "interrupted"
    assert frames[0]["data"]["stop_reason"] == "process_interrupted"
