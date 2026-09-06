"""SSE 事件流测试(§3.4 恢复语义, fake 工具链 + 临时 DB, 不联网)。

- 新建连接(刷新/视图丢失, 含零游标)→ 第一帧必为完整 snapshot(第四轮评审
  P4: 不凭客户端 seq 从头补发; running 时 snapshot 带已生成草稿正文)
- 普通断线(Last-Event-ID 在缓冲覆盖范围内)→ 从缓冲补发, 不重复不遗漏
- Last-Event-ID 超出缓冲 → 发 snapshot 对齐
- ?after= URL 参数已删除(P4): 传入被忽略, 一律按无游标 → snapshot
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
from tests.test_task_manager import (
    _done_builder,
    _writer_block_tools,
    _writer_stream_tools,
)

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
    """评审修正假覆盖:running 连接须在 writer 已产出片段后断言 snapshot
    的 report_md 是已生成正文(P3), 而非等任务完成才连接。"""
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_stream_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        assert gate.wait(5)  # 前 2 个正文片段已发出
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
        # P3: 运行中 snapshot 带已生成正文, 与已收到的片段逐字一致
        assert snap["report_md"] == "# 标题\n正文 [1]。\n"
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)


# ---- 普通断线路径: Last-Event-ID 补发 -------------------------------------------

def test_last_event_id_resumes_from_buffer_without_duplicates(tmp_path):
    """连接1 领 snapshot 对齐后继续收若干帧;连接2 带 Last-Event-ID →
    从缓冲补发, 无 snapshot、无重复、无遗漏、补发连续。"""
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_stream_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        # 连接1: 无游标 → 第一帧 snapshot 对齐, 读到 snapshot + 1 个事件帧断开
        lines = collect(client, f"/api/research/{task_id}/events",
                        stop=_stop_after_frames(2))
        frames = parse_sse(lines)
        assert frames[0]["event"] == "snapshot"
        last_id = frames[-1]["id"]  # 最后一帧(事件帧)的 id 作为断线游标
        assert last_id > frames[0]["id"]
        gate.wait(5)
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)

        # 连接2: Last-Event-ID=last_id → 缓冲内补发
        lines2 = collect(client, f"/api/research/{task_id}/events",
                         headers={"Last-Event-ID": str(last_id)})
    assert lines2 is not None
    resumed = parse_sse(lines2)
    resumed_frames = [f for f in resumed if "id" in f]
    assert resumed_frames and resumed_frames[0]["event"] != "snapshot"  # 缓冲内直接补发
    ids = [f["id"] for f in resumed_frames]
    assert ids == list(range(last_id + 1, last_id + 1 + len(ids)))  # 连续无缺
    assert all(f["id"] > last_id for f in resumed_frames)           # 无重复
    assert resumed_frames[-1]["event"] == "done"


def test_stale_last_event_id_falls_back_to_snapshot(tmp_path):
    with _make_client(tmp_path, buffer_size=3) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events",
                        headers={"Last-Event-ID": "1"})
    assert lines is not None
    frames = parse_sse(lines)
    assert frames[0]["event"] == "snapshot"  # 超出缓冲 → snapshot 对齐
    assert all(f["id"] > frames[0]["id"] for f in frames[1:] if "id" in f)


# ---- P4: 零游标与 ?after= 收敛(测试类4) ----------------------------------------

def test_zero_last_event_id_falls_back_to_snapshot(tmp_path):
    """Last-Event-ID: 0 视同无游标 → 完整 snapshot;不得凭 0 从头补发。"""
    with _make_client(tmp_path) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events",
                        headers={"Last-Event-ID": "0"})
    assert lines is not None
    frames = parse_sse(lines)
    assert frames[0]["event"] == "snapshot"
    # snapshot 之后只补发 seq 更大的帧(无从头重放)
    assert all(f["id"] > frames[0]["id"] for f in frames[1:] if "id" in f)


def test_after_query_param_is_deleted_falls_back_to_snapshot(tmp_path):
    """P4:?after= URL 参数路径已删除——传入被忽略, 一律按无游标发 snapshot,
    任何路径不得仅凭客户端 seq 请求增量。"""
    with _make_client(tmp_path) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events?after=1")
    assert lines is not None
    frames = parse_sse(lines)
    assert frames[0]["event"] == "snapshot"
    ids = [f["id"] for f in frames if "id" in f]
    assert ids and min(ids) == frames[0]["id"]  # 第一帧即 snapshot 对齐


def test_ahead_last_event_id_falls_back_to_snapshot(tmp_path):
    """Last-Event-ID 超前于服务端 seq(伪造)→ 不补发, snapshot 对齐。"""
    with _make_client(tmp_path) as client:
        task_id = _run_to_completion(client)
        lines = collect(client, f"/api/research/{task_id}/events",
                        headers={"Last-Event-ID": "999999"})
    assert lines is not None
    frames = parse_sse(lines)
    assert frames[0]["event"] == "snapshot"
    assert all(f["id"] > frames[0]["id"] for f in frames[1:] if "id" in f)


def test_snapshot_then_replay_gapless_under_publish_race(tmp_path):
    """测试类4(snapshot 与事件发布竞争):snapshot 对齐后断开, 后续连接
    从 snapshot.seq 之后补发, 与 snapshot 帧无缝(不丢不重)。"""
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_stream_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder) as client:
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        assert gate.wait(5)  # writer 前 2 片段已发出并发布
        # 连接1: 读 snapshot 一帧即断开(模拟刷新后立刻再断)
        lines = collect(client, f"/api/research/{task_id}/events",
                        stop=_stop_after_frames(1))
        snap = parse_sse(lines)[0]
        assert snap["event"] == "snapshot"
        snap_seq = snap["id"]
        snap_md = snap["data"]["report_md"]
        release.set()
        client.app_state.manager.wait(task_id, timeout=10)
        # 连接2: Last-Event-ID=snap_seq → 补发必须从 snap_seq+1 连续开始
        lines2 = collect(client, f"/api/research/{task_id}/events",
                         headers={"Last-Event-ID": str(snap_seq)})
    resumed = [f for f in parse_sse(lines2) if "id" in f]
    ids = [f["id"] for f in resumed]
    assert ids == list(range(snap_seq + 1, snap_seq + 1 + len(ids)))
    # snapshot 正文与补发事件正文拼接无丢失无重复(草稿链路)
    deltas = [f for f in resumed if f["event"] == "report_delta"]
    joined = snap_md + "".join(f["data"]["md"] for f in deltas
                               if not f["data"].get("replace"))
    assert joined == "# 标题\n正文 [1]。\n更多 [2]。\n"


# ---- R2: 循环中途游标被挤出 → snapshot 重对齐(测试类3) --------------------------

async def _stream_sse_lines_realtime(app, path, *, headers=None,
                                     stop=None, idle_timeout=15.0):
    """真增量 SSE 读取:直接桥接 ASGI send 消息, 每条消息即刻可读。

    TestClient.stream / httpx ASGITransport 都会把整个响应体缓冲到
    ASGI app 跑完才返回——拿到的是"事后回放", 无法构造读端与生产者的
    真并发窗口(假测试)。此 helper 逐条消费 send 消息, 读端每收到一行
    即调用 stop(lines)(返回 True 则断开), 空闲 idle_timeout 兜底防挂。"""
    raw_headers = [(k.lower().encode(), v.encode())
                   for k, v in (headers or {}).items()]
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "headers": raw_headers,
        "client": ("testclient", 50000), "server": ("testserver", 80),
    }
    messages: asyncio.Queue = asyncio.Queue()
    disconnect = asyncio.Event()

    async def send(msg):
        await messages.put(msg)

    async def receive():
        # 必须挂起等待: 立即返回会让 Starlette listen_for_disconnect 忙轮询,
        # 饿死整个事件循环(假死, wait_for 超时都不触发)
        await disconnect.wait()
        return {"type": "http.disconnect"}

    task = asyncio.ensure_future(app(scope, receive, send))
    lines: list[str] = []
    buf = b""
    try:
        while True:
            msg = await asyncio.wait_for(messages.get(), timeout=idle_timeout)
            if msg["type"] != "http.response.body":
                continue
            buf += msg.get("body", b"")
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                lines.append(raw.decode("utf-8").rstrip("\r"))
                if stop is not None and stop(lines):
                    return lines
            if not msg.get("more_body", False):
                break
    finally:
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001 - 取消/已完成均按断开处理
            pass
    return lines


def test_sse_realigns_with_snapshot_when_cursor_evicted_midstream(tmp_path):
    """R2 端到端(真增量流):小缓冲(maxlen=3)下, 客户端以缓冲内游标
    恢复并收完首批补发后, 生产者继续推进把游标挤出环形缓冲 → SSE 流
    必须转为完整 snapshot 重对齐, 不得把跳过缺口的尾部事件当补发直接发出。"""
    gate, release = threading.Event(), threading.Event()

    def builder(budget):
        return _done_builder(_writer_block_tools(gate, release))(budget)

    with _make_client(tmp_path, builder=builder, buffer_size=3) as client:
        app = client.app_obj
        mgr = client.app_state.manager
        task_id = client.post("/api/research", json={"topic": "Q"}).json()["task_id"]
        assert gate.wait(5)  # writer 已阻塞, 此前事件全部落缓冲

        # 放行后每个真实事件追加 4 条 padding, 把游标挤出 maxlen=3 缓冲
        orig_record = mgr._record
        state = {"released": False, "armed": True}

        def padded(rt, event, payload):
            orig_record(rt, event, payload)
            if state["released"] and event != "progress" and state["armed"]:
                state["armed"] = False
                for i in range(4):
                    orig_record(rt, "progress", {"n": f"pad{i}"})

        def frames_so_far(lines):
            count, seen = 0, False
            for ln in lines:
                if ln == "":
                    if seen:
                        count += 1
                        seen = False
                elif ln.startswith("event: "):  # 注释帧(心跳)不计
                    seen = True
            return count

        async def scenario() -> list[str]:
            # 探针连接: 无游标读 snapshot 一帧即断, 取当前 seq(真增量)
            probe = await _stream_sse_lines_realtime(
                app, f"/api/research/{task_id}/events",
                stop=lambda ls: frames_so_far(ls) >= 1)
            probe_frames = parse_sse(probe)
            seq = probe_frames[0]["id"]
            runtime = mgr._runtimes[task_id]
            assert seq == runtime.seq and seq >= 3  # writer 阻塞中, 未再推进

            # 正式连接: 游标=seq-2(缓冲首条) → replay 补发 seq-1、seq;
            # 第 2 帧收完立即放行生产者(padding 随后把游标挤出缓冲)
            def on_line(lines):
                ln = lines[-1]
                if ln == "" and frames_so_far(lines) >= 2 \
                        and not state["released"]:
                    state["released"] = True
                    mgr._record = padded
                    release.set()
                return False  # 从不断开: 一路读到流自然关闭

            return (await _stream_sse_lines_realtime(
                app, f"/api/research/{task_id}/events",
                headers={"Last-Event-ID": str(seq - 2)}, stop=on_line), seq)

        lines, seq0 = asyncio.run(scenario())
        assert state["released"], "未在首批补发收完后触发生产者推进(时序失败)"
        mgr._record = orig_record
        mgr.wait(task_id, timeout=10)
        final_seq = mgr._runtimes[task_id].seq

    replayed = [f for f in parse_sse(lines) if "id" in f]
    # 首批补发 = seq0-1、seq0(replay 路径, 无 snapshot; writer 阻塞时的 seq)
    assert [f["id"] for f in replayed[:2]] == [seq0 - 1, seq0]
    assert all(f["event"] != "snapshot" for f in replayed[:2])
    # 缺口被检出: 之后的第一帧是 snapshot 重对齐(而非 seq0+1.. 的跳帧补发)
    assert replayed[2]["event"] == "snapshot", \
        f"游标被挤出后必须 snapshot 重对齐, 实际: {[f['event'] for f in replayed]}"
    realigned = replayed[2]
    # 对齐点在缺口之后、最终 seq 之前或相等(取决于 snapshot 取得瞬间
    # 生产者推进到哪; 若在 done 入缓冲前取, 随后仍会补发 done 帧)
    assert seq0 + 2 <= realigned["id"] <= final_seq
    # 重对齐帧之后只有更新的事件帧(无跳帧回补)
    assert all(f["id"] > realigned["id"] for f in replayed[3:] if "id" in f)
    # 最终收到终态(done 帧或终态 snapshot)
    assert replayed[-1]["event"] in ("done", "snapshot")


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
