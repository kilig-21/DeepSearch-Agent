"use client";

// 时间线组件(计划书 §7):plan/search/reading/note/reflection/warning 六类事件
import type { TaskStatus, TimelineItem } from "@/lib/types";

const KIND_LABEL: Record<TimelineItem["kind"], string> = {
  plan: "规划",
  search: "搜索",
  reading: "阅读",
  note: "要点",
  reflection: "反思",
  warning: "警告",
};

const KIND_STYLE: Record<TimelineItem["kind"], string> = {
  plan: "bg-blue-100 text-blue-800",
  search: "bg-cyan-100 text-cyan-800",
  reading: "bg-emerald-100 text-emerald-800",
  note: "bg-amber-100 text-amber-900",
  reflection: "bg-violet-100 text-violet-800",
  warning: "bg-red-100 text-red-800",
};

const STATUS_LABEL: Record<TaskStatus, string> = {
  running: "进行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

export function StatusBadge({ status }: { status: TaskStatus | null }) {
  if (!status) return null;
  const style =
    status === "running"
      ? "bg-yellow-100 text-yellow-900 border-yellow-300"
      : status === "completed"
        ? "bg-green-100 text-green-900 border-green-300"
        : "bg-red-100 text-red-900 border-red-300";
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-sm font-medium ${style}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-gray-500">尚未开始。</p>;
  }
  return (
    <ol className="space-y-2">
      {items.map((it) => (
        <li key={it.seq} className="flex items-start gap-3">
          <span
            className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${KIND_STYLE[it.kind]}`}
          >
            {KIND_LABEL[it.kind]}
          </span>
          <div className="min-w-0 text-sm">
            <p className="break-words">{it.text}</p>
            {it.detail ? (
              <p className="break-all whitespace-pre-wrap text-xs text-gray-500">
                {it.detail}
              </p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
