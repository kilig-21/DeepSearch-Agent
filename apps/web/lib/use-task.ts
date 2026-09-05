"use client";

// useTask hook(计划书 §7):POST 创建 + EventSource 订阅 + 两路恢复。
//
// 恢复语义(§3.4 v1.3;第四轮评审 F2/F3/F4):
// - 普通断线(页面在):EventSource 自动重连,浏览器带 Last-Event-ID,
//   服务端从环形缓冲补发
// - 刷新/视图丢失:新 EventSource 连接(不带任何游标参数——不得仅凭
//   sessionStorage 的 seq 请求增量),服务端先发完整 snapshot 整体替换视图
// - F2:序号一律读 MessageEvent.lastEventId(服务端 id: 字段),在任何
//   正文/进度/时间线更新之前统一过滤重复与过期序号(snapshot 除外:
//   整体替换视图)
// - F3:引用 [n] → 真实 URL 经详情数据 evidences.source_id → sources
//   联查;[n]→evidence_id 的数据契约保留在 citationMap,不伪造 href
// - F4:completed snapshot 自带正文时直接作正式版;详情请求失败显示
//   重试入口,不静默停留草稿
// - 收到业务终态(done/task_failed/cancelled)或显示终态的 snapshot
//   (completed/failed/cancelled/interrupted)后主动 close()(断开 ≠ 取消)

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CancelledPayload,
  DonePayload,
  FailedPayload,
  PlanPayload,
  ReadingPayload,
  ReportDeltaPayload,
  ReportDetail,
  SearchPayload,
  Snapshot,
  TaskStatus,
  TimelineItem,
} from "./types";
import { isTerminal } from "./types";
import { resolveCitationUrls } from "./citations";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TASK_KEY = "orca.task_id";

export interface TaskView {
  taskId: string | null;
  status: TaskStatus | null;
  stopReason: string | null;
  reportId: number | null;
  roundNo: number;
  subQuestions: string[];
  progress: { sources_read: number; evidence_count: number };
  timeline: TimelineItem[];
  draftReport: string;      // report_delta 草稿累积
  finalReport: string | null; // 落库正式版(替换草稿)
  citationMap: Record<string, string>;   // [n] → evidence_id(数据契约)
  citationUrls: Record<string, string>;  // [n] → 真实 URL(F3 联查结果)
  sources: { url: string; title: string }[];
  error: string | null;
  connecting: boolean;
  finalLoadFailed: boolean; // F4:正式报告详情拉取失败 → 显示重试入口
}

function appendTimeline(
  items: TimelineItem[],
  item: TimelineItem,
): TimelineItem[] {
  // 快照恢复后只应用更大 seq 的增量, 重复事件忽略(§3.4;F2 双保险)
  if (items.length > 0 && item.seq <= items[items.length - 1].seq) {
    return items;
  }
  return [...items, item];
}

// F3:citation_map 是 [n] → evidence_id;经 evidences.source_id → sources
// 联查真实 URL, 绝不把 evidence_id 当 href
const EMPTY: TaskView = {
  taskId: null,
  status: null,
  stopReason: null,
  reportId: null,
  roundNo: 0,
  subQuestions: [],
  progress: { sources_read: 0, evidence_count: 0 },
  timeline: [],
  draftReport: "",
  finalReport: null,
  citationMap: {},
  citationUrls: {},
  sources: [],
  error: null,
  connecting: false,
  finalLoadFailed: false,
};

export function useTask() {
  const [view, setView] = useState<TaskView>(EMPTY);

  const esRef = useRef<EventSource | null>(null);
  const maxSeqRef = useRef(0);
  const closedRef = useRef(false);

  const close = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const fetchFinalReport = useCallback(async (reportId: number) => {
    try {
      const resp = await fetch(`${API}/api/reports/${reportId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const detail: ReportDetail = await resp.json();
      setView((v) => ({
        ...v,
        finalReport: detail.final_md,
        citationMap: detail.citation_map_json ?? {},
        citationUrls: resolveCitationUrls(detail),
        finalLoadFailed: false,
        status: "completed",
        stopReason: detail.stop_reason,
      }));
    } catch {
      // F4:详情拉取失败 → 显示重试入口, 不静默。snapshot 自带正文时
      // 正文仍在(finalReport 非 null), 仅提示引用链接未加载
      setView((v) => ({ ...v, finalLoadFailed: true }));
    }
  }, []);

  const subscribe = useCallback(
    (taskId: string) => {
      close();
      closedRef.current = false;
      const es = new EventSource(`${API}/api/research/${taskId}/events`);
      esRef.current = es;

      const handleEvent = (name: string, ev: MessageEvent) => {
        // F2:序号一律读 lastEventId(服务端 id: 字段), 不信任 payload;
        // 在任何视图更新之前统一过滤重复/过期序号。
        const seq = Number.parseInt(ev.lastEventId ?? "", 10);
        if (name === "snapshot") {
          if (!Number.isNaN(seq)) {
            maxSeqRef.current = Math.max(maxSeqRef.current, seq);
          }
        } else {
          if (Number.isNaN(seq)) return;      // 无有效 id 的帧不处理
          if (seq <= maxSeqRef.current) return; // 重复/过期 → 忽略
          maxSeqRef.current = seq;
        }
        const data = JSON.parse(ev.data as string);
        const ts: string = data.ts ?? new Date().toISOString();

        setView((v) => {
          const next = { ...v, taskId };
          switch (name) {
            case "snapshot": {
              const snap = data as Snapshot;
              // 刷新恢复: 整体替换视图; 时间线历史明细不可恢复, 显示概要
              next.status = snap.status;
              next.stopReason = snap.stop_reason;
              next.reportId = snap.report_id;
              next.roundNo = snap.round_no;
              next.subQuestions = snap.sub_questions;
              next.progress = snap.progress;
              next.citationMap = snap.citation_map;
              next.citationUrls = {}; // 真实 URL 待详情联查
              next.sources = [];
              if (snap.status === "running") {
                next.draftReport = snap.report_md || v.draftReport;
                next.timeline = [
                  {
                    seq: snap.seq,
                    kind: "plan",
                    text: `快照恢复: 已进行到第 ${snap.round_no} 轮,` +
                      `读过 ${snap.progress.sources_read} 个来源,` +
                      `沉淀 ${snap.progress.evidence_count} 条要点`,
                    ts: snap.ts ?? ts,
                  },
                ];
              } else if (snap.status === "completed" && snap.report_md) {
                // F4:completed snapshot 自带正文 → 直接作正式版,
                // 不必等详情请求(详情仅用于补引用链接)
                next.finalReport = snap.report_md;
                next.draftReport = "";
                next.finalLoadFailed = false;
                if (snap.report_id != null) void fetchFinalReport(snap.report_id);
              } else if (snap.report_id != null) {
                // 终态快照但无正文(如重启后 DB 快照): 拉详情替换
                void fetchFinalReport(snap.report_id);
              } else {
                next.draftReport = "";
              }
              break;
            }
            case "plan": {
              const p = data as PlanPayload;
              next.subQuestions = p.sub_questions;
              next.timeline = appendTimeline(v.timeline, {
                seq, kind: "plan", ts,
                text: `拆解 ${p.sub_questions.length} 个子问题`,
                detail: p.sub_questions.join("\n"),
              });
              break;
            }
            case "search": {
              const p = data as SearchPayload;
              next.roundNo = Math.max(v.roundNo, p.round);
              next.sources = p.results;
              next.timeline = appendTimeline(v.timeline, {
                seq, kind: "search", ts,
                text: `第 ${p.round} 轮搜索「${p.query}」→ ${p.results.length} 条结果`,
              });
              break;
            }
            case "reading": {
              const p = data as ReadingPayload;
              next.progress = {
                ...v.progress,
                sources_read: v.progress.sources_read + 1,
              };
              next.timeline = appendTimeline(v.timeline, {
                seq, kind: "reading", ts,
                text: `阅读 (${p.n}/${p.N}) ${p.title}`,
                detail: p.url,
              });
              break;
            }
            case "note": {
              next.progress = {
                ...v.progress,
                evidence_count: v.progress.evidence_count + 1,
              };
              next.timeline = appendTimeline(v.timeline, {
                seq, kind: "note", ts,
                text: data.point as string,
                detail: data.title as string,
              });
              break;
            }
            case "reflection": {
              next.timeline = appendTimeline(v.timeline, {
                seq, kind: "reflection", ts,
                text: "反思: " + JSON.stringify(data),
              });
              break;
            }
            case "warning": {
              next.timeline = appendTimeline(v.timeline, {
                seq, kind: "warning", ts,
                text: `局部失败(${data.stage}): ${data.detail}`,
              });
              break;
            }
            case "report_delta": {
              const p = data as ReportDeltaPayload;
              // 修订帧整体替换草稿, 其余逐片段追加(评审 P2/P3)
              next.draftReport = p.replace ? p.md : v.draftReport + p.md;
              break;
            }
            case "done": {
              const p = data as DonePayload;
              next.status = "completed";
              next.stopReason = p.stop_reason;
              next.reportId = p.report_id;
              void fetchFinalReport(p.report_id);
              break;
            }
            case "task_failed": {
              const p = data as FailedPayload;
              next.status = "failed";
              next.stopReason = p.stop_reason;
              next.error = p.detail;
              next.draftReport = "";
              break;
            }
            case "cancelled": {
              const p = data as CancelledPayload;
              next.status = "cancelled";
              next.stopReason = p.stop_reason;
              next.draftReport = "";
              break;
            }
            default:
              break;
          }
          return next;
        });

        // 业务终态或显示终态的 snapshot → 主动 close(§3.4)
        const terminalEvents = new Set(["done", "task_failed", "cancelled"]);
        if (terminalEvents.has(name)) {
          closedRef.current = true;
          close();
        } else if (name === "snapshot" && isTerminal(data.status)) {
          closedRef.current = true;
          close();
        }
      };

      // 服务端以具名事件发送, EventSource 默认 message 监听不到具名事件,
      // 必须按事件名注册
      for (const name of [
        "snapshot", "plan", "search", "reading", "note", "reflection",
        "warning", "report_delta", "done", "task_failed", "cancelled",
      ]) {
        es.addEventListener(name, (ev) => handleEvent(name, ev as MessageEvent));
      }
      es.onerror = () => {
        // 浏览器自动重连(带 Last-Event-ID); 断开只影响订阅, 不取消任务
        if (!closedRef.current) {
          setView((v) => ({ ...v, connecting: true }));
        }
      };
      es.onopen = () => setView((v) => ({ ...v, connecting: false }));
    },
    [close, fetchFinalReport],
  );

  const start = useCallback(
    async (topic: string): Promise<string | null> => {
      setView({ ...EMPTY, connecting: true });
      maxSeqRef.current = 0;
      sessionStorage.removeItem(TASK_KEY);
      const resp = await fetch(`${API}/api/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic }),
      });
      if (resp.status === 409) {
        const err = await resp.json();
        setView((v) => ({
          ...v,
          connecting: false,
          error: `已有进行中的任务(${err.active_task_id}), 同一时刻只能运行一个`,
        }));
        return null;
      }
      if (!resp.ok) {
        setView((v) => ({
          ...v, connecting: false, error: `创建失败: ${resp.status}`,
        }));
        return null;
      }
      const { task_id } = await resp.json();
      sessionStorage.setItem(TASK_KEY, task_id);
      subscribe(task_id);
      return task_id;
    },
    [subscribe],
  );

  const cancel = useCallback(async (): Promise<boolean> => {
    const taskId = view.taskId;
    if (!taskId) return false;
    const resp = await fetch(`${API}/api/research/${taskId}/cancel`, {
      method: "POST",
    });
    if (resp.status === 202) {
      setView((v) => ({ ...v, error: null }));
      return true;
    }
    if (resp.status === 409) {
      setView((v) => ({ ...v, error: "任务已结束, 无需取消" }));
      return false;
    }
    return false;
  }, [view.taskId]);

  // F4:正式报告详情重试入口(首次失败后由用户触发)
  const retryFinalReport = useCallback(async (): Promise<void> => {
    const taskId = view.taskId;
    if (!taskId) return;
    setView((v) => ({ ...v, finalLoadFailed: false }));
    if (view.reportId != null) {
      await fetchFinalReport(view.reportId);
    }
  }, [view.taskId, view.reportId, fetchFinalReport]);

  // 刷新/重开页面恢复: 有 task_id 则重新订阅; 服务端会先发完整 snapshot
  // (不传 after/seq 参数 —— §3.4/P4 禁止仅凭 seq 请求增量)
  useEffect(() => {
    const saved = sessionStorage.getItem(TASK_KEY);
    if (saved && !esRef.current) {
      setView((v) => ({ ...v, connecting: true }));
      subscribe(saved);
    }
    return () => close();
  }, [subscribe, close]);

  return { view, start, cancel, close, retryFinalReport };
}
