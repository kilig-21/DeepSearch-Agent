// SSE 事件与快照类型(与后端 §3.4 协议一一对应)

export type TaskStatus =
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface Snapshot {
  task_id: string;
  status: TaskStatus;
  stop_reason: string | null;
  report_id: number | null;
  round_no: number;
  sub_questions: string[];
  progress: { sources_read: number; evidence_count: number };
  report_md: string;
  citation_map: Record<string, string>;
  seq: number;
  ts?: string;
}

export interface PlanPayload {
  sub_questions: string[];
}

export interface SearchPayload {
  round: number;
  query: string;
  results: { url: string; title: string }[];
  credits_used?: number;
}

export interface ReadingPayload {
  url: string;
  title: string;
  n: number;
  N: number;
}

export interface NotePayload {
  evidence_id: string;
  origin_group_id: string | null;
  url: string;
  title: string;
  point: string;
}

export interface WarningPayload {
  stage: string;
  detail: string;
}

export interface ReportDeltaPayload {
  md: string;
  draft: boolean;
  replace?: boolean; // 修订帧: 整体替换草稿(第四轮评审 P2/P3)
}

export interface DonePayload {
  report_id: number;
  stop_reason: string;
  token_cost: number;
  credits_cost: number;
  duration_s: number;
}

export interface FailedPayload {
  detail: string;
  stop_reason: string;
}

export type CancelledPayload = { stop_reason: string };

// 时间线条目(前端聚合后)
export interface TimelineItem {
  seq: number;
  kind: "plan" | "search" | "reading" | "note" | "reflection" | "warning";
  text: string;
  detail?: string;
  ts: string;
}

export interface ReportDetail {
  id: number;
  task_id: string;
  topic: string;
  final_md: string;
  citation_map_json: Record<string, string>;
  stop_reason: string;
  token_cost: number;
  credits_cost: number;
  duration_s: number;
  created_at: string;
  evidences: {
    evidence_id: string;
    source_id: number; // → sources 联查真实 URL(F3 引用链接契约)
    quote: string;
    origin_group_id: string | null;
    source_type: string;
  }[];
  sources: { id: number; url: string; title: string; domain: string }[];
}

export function isTerminal(status: TaskStatus): boolean {
  return status !== "running";
}
