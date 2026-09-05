"use client";

// 研究页(计划书 §7):输入 → 时间线 → 报告区(草稿流式 → 正式版替换)。
// 逻辑正确优先, 不追求美观。
import { useState } from "react";
import Link from "next/link";
import { StatusBadge, Timeline } from "@/components/research/timeline";
import { ReportView } from "@/components/research/report-view";
import { useTask } from "@/lib/use-task";
import { isTerminal } from "@/lib/types";

export default function ResearchPage() {
  const { view, start, cancel, retryFinalReport } = useTask();
  const [topic, setTopic] = useState("");

  const taskActive =
    view.taskId !== null && (view.status === null || !isTerminal(view.status));
  const canCancel = view.status === "running" || (view.status === null && view.taskId !== null);

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Orca Research</h1>
        <Link className="text-sm text-blue-600 hover:underline" href="/history">
          历史报告
        </Link>
      </header>

      {/* 输入区 */}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const t = topic.trim();
          if (t) void start(t);
        }}
      >
        <input
          className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
          placeholder="输入研究问题, 例如: Python 3.13 有哪些新特性?"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          disabled={taskActive}
        />
        <button
          type="submit"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={!topic.trim() || taskActive}
        >
          开始研究
        </button>
        <button
          type="button"
          className="rounded border border-red-300 bg-red-50 px-4 py-2 text-sm font-medium text-red-700 disabled:opacity-40"
          disabled={!canCancel}
          onClick={() => void cancel()}
        >
          取消
        </button>
      </form>

      {view.error ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {view.error}
        </p>
      ) : null}
      {view.connecting ? (
        <p className="text-xs text-gray-500">连接事件流中…(断线自动重连)</p>
      ) : null}

      {/* 进度概览 */}
      {view.taskId ? (
        <section className="space-y-2 rounded border border-gray-200 p-4">
          <div className="flex items-center gap-3 text-sm">
            <StatusBadge status={view.status} />
            <span className="text-gray-500">task {view.taskId.slice(0, 8)}…</span>
            {view.stopReason ? (
              <span className="text-gray-500">stop: {view.stopReason}</span>
            ) : null}
          </div>
          <p className="text-sm text-gray-600">
            第 {view.roundNo} 轮 · 读过 {view.progress.sources_read} 个来源 · 沉淀{" "}
            {view.progress.evidence_count} 条要点
          </p>
          <Timeline items={view.timeline} />
        </section>
      ) : null}

      {/* 报告区: 落库后取正式版替换草稿 */}
      {view.finalReport !== null ? (
        <section className="rounded border border-green-200 p-4">
          {view.finalLoadFailed ? (
            <p className="mb-2 flex items-center gap-2 text-xs text-amber-700">
              报告详情(引用链接)获取失败, 当前展示任务自带正文。
              <button
                type="button"
                className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 font-medium hover:bg-amber-100"
                onClick={() => void retryFinalReport()}
              >
                重试
              </button>
            </p>
          ) : null}
          <ReportView
            markdown={view.finalReport}
            citationUrls={view.citationUrls}
            title="研究报告"
          />
        </section>
      ) : view.finalLoadFailed ? (
        <section className="rounded border border-amber-300 bg-amber-50 p-4">
          <p className="flex items-center gap-2 text-sm text-amber-800">
            正式报告获取失败。
            <button
              type="button"
              className="rounded border border-amber-400 bg-white px-2 py-0.5 font-medium hover:bg-amber-100"
              onClick={() => void retryFinalReport()}
            >
              重试
            </button>
          </p>
        </section>
      ) : view.draftReport ? (
        <section className="rounded border border-dashed border-gray-300 p-4">
          <p className="mb-2 text-xs text-gray-500">草稿(流式生成中…)</p>
          <ReportView markdown={view.draftReport} citationUrls={view.citationUrls} />
        </section>
      ) : null}
    </main>
  );
}
