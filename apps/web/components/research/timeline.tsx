"use client";

import type { TaskStatus, TimelineItem } from "@/lib/types";

const KIND_LABEL: Record<TimelineItem["kind"], string> = {
  plan: "研究计划", search: "搜索", reading: "阅读", note: "证据", reflection: "检查资料", warning: "提示",
};
const STATUS_LABEL: Record<TaskStatus, string> = {
  running: "进行中", completed: "已完成", failed: "未完成", cancelled: "已停止", interrupted: "已中断",
};

export function StatusBadge({ status }: { status: TaskStatus | null }) {
  if (!status) return null;
  const tone = status === "running" ? "status-running" : status === "completed" ? "status-complete" : "status-stopped";
  return <span className={`status-badge ${tone}`}>{STATUS_LABEL[status]}</span>;
}

export function Timeline({ items, active = false }: { items: TimelineItem[]; active?: boolean }) {
  if (items.length === 0) return <p className="timeline-empty">{active ? "正在准备研究计划…" : "没有可显示的过程记录。"}</p>;

  return <ol className="research-timeline">{items.map((item, index) => {
    const date = new Date(item.ts);
    const time = Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    const sourceUrl = item.kind === "reading" && /^https?:\/\//i.test(item.detail ?? "") ? item.detail : null;
    return <li className="timeline-entry" key={item.seq}>
      <div className={`timeline-node timeline-${item.kind}`} aria-hidden="true" />
      {index < items.length - 1 ? <div className="timeline-line" aria-hidden="true" /> : null}
      <div className="timeline-copy">
        <div className="timeline-meta"><span>{KIND_LABEL[item.kind]}</span><time dateTime={item.ts}>{time}</time></div>
        <p>{item.text}</p>
        {sourceUrl ? <a className="timeline-source" href={sourceUrl} target="_blank" rel="noopener noreferrer">查看来源 ↗</a>
          : item.detail ? <p className="timeline-detail">{item.detail}</p> : null}
      </div>
    </li>;
  })}</ol>;
}
