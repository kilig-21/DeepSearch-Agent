// useTask hook 测试(第四轮评审 F2/F3/F4;测试类6:真实 SSE 事件 ID 驱动
// 的去重与时间线完整性)
// - 序号一律读 MessageEvent.lastEventId(服务端 id: 字段), 重复/过期帧
//   在任何视图更新前被统一过滤:不重复渲染、时间线不缺项
// - completed snapshot 自带正文 → 直接作正式版(F4);详情失败有重试入口
// - 引用 [n] 经 evidences.source_id → sources 联查真实 URL(F3)
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTask } from "@/lib/use-task";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  closed = false;
  listeners = new Map<string, ((ev: MessageEvent) => void)[]>();
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(name: string, cb: (ev: MessageEvent) => void) {
    const arr = this.listeners.get(name) ?? [];
    arr.push(cb);
    this.listeners.set(name, arr);
  }
  close() {
    this.closed = true;
  }
  // 服务端帧:id: 行 → lastEventId, data: 行 → ev.data(与真实协议一致)
  emit(name: string, id: number | string, data: unknown) {
    const ev = {
      data: JSON.stringify(data),
      lastEventId: String(id),
    } as MessageEvent;
    for (const cb of this.listeners.get(name) ?? []) cb(ev);
  }
  get closedByHook() {
    return this.closed;
  }
}

function lastEs(): MockEventSource {
  return MockEventSource.instances[MockEventSource.instances.length - 1];
}

const REPORT_DETAIL = {
  id: 9,
  task_id: "t_test",
  topic: "Q",
  final_md: "# 正式报告\n",
  citation_map_json: { "1": "ev_001" },
  stop_reason: "single_pass",
  token_cost: 100,
  credits_cost: 1,
  duration_s: 3.2,
  created_at: "2026-09-06T00:00:00+00:00",
  evidences: [
    { evidence_id: "ev_001", source_id: 77, quote: "q", origin_group_id: null, source_type: "official_docs" },
  ],
  sources: [{ id: 77, url: "https://real.example/a", title: "A", domain: "real.example" }],
};

function okJson(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

describe("useTask(F2 去重与时间线完整性)", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/research")) {
          return okJson({ task_id: "t_test" });
        }
        if (url.includes("/api/reports/")) {
          return okJson(REPORT_DETAIL);
        }
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    sessionStorage.clear();
  });

  it("真实 SSE 事件 ID 驱动:重复帧过滤不重复渲染, 时间线不缺项", async () => {
    const { result } = renderHook(() => useTask());
    await act(async () => {
      await result.current.start("Q");
    });
    const es = lastEs();

    // 按服务端序号正常投递(id: 1..5)
    act(() => {
      es.emit("plan", 1, { sub_questions: ["Q1", "Q2"], ts: "t1" });
      es.emit("search", 2, { round: 1, query: "q", results: [], ts: "t2" });
      es.emit("reading", 3, { url: "u", title: "T", n: 1, N: 1, ts: "t3" });
      es.emit("note", 4, { point: "要点", title: "T", ts: "t4" });
      es.emit("report_delta", 5, { md: "片段", draft: true, ts: "t5" });
    });

    expect(result.current.view.timeline.map((i) => i.kind)).toEqual([
      "plan", "search", "reading", "note",        // 不缺项
    ]);
    expect(result.current.view.progress.sources_read).toBe(1);
    expect(result.current.view.progress.evidence_count).toBe(1);
    expect(result.current.view.draftReport).toBe("片段");

    // 断线重连补发:重复序号(3/2/1)一律忽略 → 视图零变化
    act(() => {
      es.emit("reading", 3, { url: "u", title: "T", n: 1, N: 1, ts: "t3" });
      es.emit("search", 2, { round: 1, query: "q", results: [], ts: "t2" });
      es.emit("plan", 1, { sub_questions: ["Q1", "Q2"], ts: "t1" });
    });
    expect(result.current.view.timeline.map((i) => i.kind)).toEqual([
      "plan", "search", "reading", "note",
    ]);
    expect(result.current.view.progress.sources_read).toBe(1);  // 不重复计数
    expect(result.current.view.draftReport).toBe("片段");        // 不重复拼接
  });

  it("序号只认 lastEventId:payload 携带伪造 seq 也不影响去重", async () => {
    const { result } = renderHook(() => useTask());
    await act(async () => {
      await result.current.start("Q");
    });
    const es = lastEs();
    act(() => {
      es.emit("plan", 1, { sub_questions: ["Q1"], ts: "t1" });
      // 攻击/坏帧:payload 塞超大 seq, 但 id: 行是重复的 1
      es.emit("plan", 1, { sub_questions: ["注入"], seq: 999, ts: "t2" });
    });
    expect(result.current.view.subQuestions).toEqual(["Q1"]);
    expect(result.current.view.timeline).toHaveLength(1);
  });

  it("report_delta replace 帧(修订)整体替换草稿", async () => {
    const { result } = renderHook(() => useTask());
    await act(async () => {
      await result.current.start("Q");
    });
    const es = lastEs();
    act(() => {
      es.emit("report_delta", 1, { md: "草稿一", draft: true });
      es.emit("report_delta", 2, { md: "草稿二", draft: true });
      es.emit("report_delta", 3, { md: "修订版", draft: true, replace: true });
    });
    expect(result.current.view.draftReport).toBe("修订版");
  });

  it("done 后拉详情:[n]→evidence_id→source_id→URL 联查, 契约保留", async () => {
    const { result } = renderHook(() => useTask());
    await act(async () => {
      await result.current.start("Q");
    });
    const es = lastEs();
    act(() => {
      es.emit("done", 6, { report_id: 9, stop_reason: "single_pass", ts: "t6" });
    });
    await waitFor(() => {
      expect(result.current.view.citationUrls).toEqual({
        "1": "https://real.example/a",   // 真实 URL(F3)
      });
    });
    expect(result.current.view.citationMap).toEqual({ "1": "ev_001" }); // 契约保留
    expect(result.current.view.finalReport).toBe("# 正式报告\n");
    expect(lastEs().closed).toBe(true);  // 业务终态 → 主动 close
  });

  it("F4:completed snapshot 自带正文优先使用;详情失败显示重试入口", async () => {
    // 详情请求持续失败
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/research")) return okJson({ task_id: "t_test" });
        throw new Error("boom");
      }),
    );
    const { result } = renderHook(() => useTask());
    await act(async () => {
      await result.current.start("Q");
    });
    const es = lastEs();
    act(() => {
      es.emit("snapshot", 10, {
        task_id: "t_test", status: "completed", stop_reason: "single_pass",
        report_id: 9, round_no: 1, sub_questions: ["Q1"],
        progress: { sources_read: 2, evidence_count: 2 },
        report_md: "# 任务自带正文", citation_map: { "1": "ev_001" }, seq: 10,
      });
    });
    // snapshot 正文直接作为正式版, 不静默停留草稿
    expect(result.current.view.finalReport).toBe("# 任务自带正文");
    expect(result.current.view.draftReport).toBe("");
    await waitFor(() => {
      expect(result.current.view.finalLoadFailed).toBe(true); // 重试入口出现
    });

    // 用户点重试 → fetch 恢复 → 补齐引用链接, 重试入口消失
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/reports/")) return okJson(REPORT_DETAIL);
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    await act(async () => {
      await result.current.retryFinalReport();
    });
    await waitFor(() => {
      expect(result.current.view.finalLoadFailed).toBe(false);
      expect(result.current.view.citationUrls).toEqual({
        "1": "https://real.example/a",
      });
      expect(result.current.view.finalReport).toBe("# 正式报告\n");
    });
  });

  it("详情失败且无 snapshot 正文 → finalLoadFailed=true 且草稿不被误删", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/research")) return okJson({ task_id: "t_test" });
        throw new Error("boom");
      }),
    );
    const { result } = renderHook(() => useTask());
    await act(async () => {
      await result.current.start("Q");
    });
    const es = lastEs();
    act(() => {
      es.emit("report_delta", 1, { md: "流式草稿", draft: true });
      // 终态快照但 runtime 已丢失(无正文, 仅 report_id)
      es.emit("snapshot", 2, {
        task_id: "t_test", status: "completed", stop_reason: "single_pass",
        report_id: 9, round_no: 1, sub_questions: [],
        progress: { sources_read: 1, evidence_count: 1 },
        report_md: "", citation_map: {}, seq: 2,
      });
    });
    await waitFor(() => {
      expect(result.current.view.finalLoadFailed).toBe(true);
    });
    // 详情成功后正式版替换(重试路径)
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => okJson(REPORT_DETAIL)),
    );
    await act(async () => {
      await result.current.retryFinalReport();
    });
    await waitFor(() => {
      expect(result.current.view.finalReport).toBe("# 正式报告\n");
    });
  });

  it("创建任务断网时结束连接状态并显示错误", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    const { result } = renderHook(() => useTask());

    let taskId: string | null = "placeholder";
    await act(async () => {
      taskId = await result.current.start("Q");
    });

    expect(taskId).toBeNull();
    expect(result.current.view.connecting).toBe(false);
    expect(result.current.view.error).toContain("创建失败");
    expect(result.current.view.error).toContain("Failed to fetch");
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("刷新后在首帧前保留任务与题目，终态快照解除连接状态", async () => {
    sessionStorage.setItem("orca.task_id", "t_saved");
    sessionStorage.setItem("orca.task_topic", "刷新后应保留的问题");
    const { result } = renderHook(() => useTask());
    expect(result.current.view.taskId).toBe("t_saved");
    expect(result.current.view.topic).toBe("刷新后应保留的问题");
    expect(result.current.view.connecting).toBe(true);
    act(() => lastEs().emit("snapshot", 1, {
      status: "interrupted", stop_reason: "interrupted", report_id: null,
      round_no: 1, sub_questions: [], progress: { sources_read: 1, evidence_count: 0 },
      report_md: "", citation_map: {}, seq: 1,
    }));
    expect(result.current.view.connecting).toBe(false);
    act(() => result.current.reset());
    expect(result.current.view.taskId).toBeNull();
    expect(sessionStorage.getItem("orca.task_topic")).toBeNull();
  });

  it("离开的旧 SSE 连接晚到的事件不会把新界面改回旧任务", async () => {
    const { result } = renderHook(() => useTask());
    await act(async () => { await result.current.start("Q"); });
    const oldConnection = lastEs();
    act(() => oldConnection.emit("cancelled", 1, { stop_reason: "cancelled" }));
    act(() => result.current.reset());
    act(() => {
      oldConnection.emit("note", 2, { point: "旧资料", title: "旧标题" });
      oldConnection.onerror?.();
    });
    expect(result.current.view.taskId).toBeNull();
    expect(result.current.view.timeline).toEqual([]);
    expect(result.current.view.connecting).toBe(false);
  });

  it("POST 成功后立即锁定为运行中，不等待 SSE 首帧", async () => {
    const { result } = renderHook(() => useTask());

    await act(async () => {
      await result.current.start("Q");
    });

    expect(result.current.view.taskId).toBe("t_test");
    expect(result.current.view.status).toBe("running");
    expect(result.current.view.connecting).toBe(true);
    expect(sessionStorage.getItem("orca.task_id")).toBe("t_test");
  });

  it("终态任务可以清空并开始下一项研究", async () => {
    const { result } = renderHook(() => useTask());
    await act(async () => { await result.current.start("Q"); });
    act(() => {
      lastEs().emit("cancelled", 1, {
        stop_reason: "cancelled_by_user",
        ts: "t1",
      });
    });

    act(() => result.current.reset());

    expect(result.current.view.taskId).toBeNull();
    expect(result.current.view.status).toBeNull();
    expect(result.current.view.timeline).toEqual([]);
    expect(sessionStorage.getItem("orca.task_id")).toBeNull();
  });

  it("旧任务的报告详情晚到时不会覆盖新任务", async () => {
    let createCount = 0;
    let resolveOldDetail!: (response: Response) => void;
    const oldDetail = new Promise<Response>((resolve) => {
      resolveOldDetail = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/research")) {
          createCount += 1;
          return okJson({ task_id: createCount === 1 ? "task_a" : "task_b" });
        }
        if (url.includes("/api/reports/9")) return await oldDetail;
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    const { result } = renderHook(() => useTask());

    await act(async () => { await result.current.start("A"); });
    act(() => {
      lastEs().emit("done", 1, {
        report_id: 9, stop_reason: "single_pass", ts: "t1",
      });
    });
    await act(async () => { await result.current.start("B"); });
    act(() => {
      lastEs().emit("snapshot", 0, {
        task_id: "task_b", status: "running", stop_reason: null,
        report_id: null, round_no: 0, sub_questions: [],
        progress: { sources_read: 0, evidence_count: 0 },
        report_md: "", citation_map: {}, seq: 0,
      });
    });
    await act(async () => {
      resolveOldDetail(okJson(REPORT_DETAIL));
      await oldDetail;
    });

    expect(result.current.view.taskId).toBe("task_b");
    expect(result.current.view.status).toBe("running");
    expect(result.current.view.finalReport).toBeNull();
  });

  it("取消请求断网时返回失败并显示错误", async () => {
    const { result } = renderHook(() => useTask());
    await act(async () => { await result.current.start("Q"); });
    act(() => {
      lastEs().emit("snapshot", 0, {
        task_id: "t_test", status: "running", stop_reason: null,
        report_id: null, round_no: 0, sub_questions: [],
        progress: { sources_read: 0, evidence_count: 0 },
        report_md: "", citation_map: {}, seq: 0,
      });
    });
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));

    let cancelled = true;
    await act(async () => { cancelled = await result.current.cancel(); });

    expect(cancelled).toBe(false);
    expect(result.current.view.error).toContain("取消失败");
    expect(result.current.view.error).toContain("Failed to fetch");
  });
});
