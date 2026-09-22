"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { StatusBadge, Timeline } from "@/components/research/timeline";
import { ReportView } from "@/components/research/report-view";
import { FadeContent } from "@/components/ui/fade-content";
import { useTask } from "@/lib/use-task";
import { isTerminal } from "@/lib/types";
import { stopReasonLabel } from "@/lib/display";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

interface RecentReport {
  id: number;
  topic: string;
  created_at: string;
  duration_s: number;
}

const quickPrompts = [
  "Python 3.13 相比 3.12 有哪些关键变化？",
  "Python 的 asyncio 与多线程分别适合什么场景？",
  "浏览器的 localStorage 与 IndexedDB 有什么区别？",
];

function formatReportDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function ResearchPage() {
  const { view, start, cancel, retryFinalReport, reset } = useTask();
  const [topic, setTopic] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submitLock = useRef(false);
  const [cancelling, setCancelling] = useState(false);
  const [recentReports, setRecentReports] = useState<RecentReport[]>([]);
  const taskActive = view.taskId !== null && (view.status === null || !isTerminal(view.status));
  const canCancel = view.status === "running" || (view.status === null && view.taskId !== null);
  const hasResearch = view.taskId !== null;
  const report = view.finalReport ?? view.draftReport;
  const busy = taskActive || submitting || view.connecting;
  const reportState = view.finalReport !== null ? "已完成" : view.finalLoadFailed ? "加载失败" : view.status === "completed" ? "正在加载" : !taskActive ? "未生成报告" : view.draftReport ? "正在撰写" : "正在收集资料";
  const heading = !hasResearch ? "新建研究" : taskActive ? "研究进行中" : view.status === "completed" ? "研究已完成" : "研究已结束";

  const submit = async () => {
    const value = topic.trim();
    if (!value || busy || submitLock.current) return;
    submitLock.current = true;
    setSubmitting(true);
    setCancelling(false);
    try { await start(value); }
    finally { submitLock.current = false; setSubmitting(false); }
  };

  const newResearch = () => {
    if (busy) return;
    reset();
    setTopic("");
    requestAnimationFrame(() => document.getElementById("research-topic")?.focus());
  };

  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${API}/api/reports`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((items: RecentReport[]) => setRecentReports(items.slice(0, 3)))
      .catch(() => undefined);
    return () => controller.abort();
  }, [view.reportId]);

  const choosePrompt = (prompt: string) => {
    setTopic(prompt);
    requestAnimationFrame(() => document.getElementById("research-topic")?.focus());
  };

  return <main className={`workbench-shell ${hasResearch ? "workbench-running" : "workbench-ready"}`}>
    <aside className="app-rail">
      <Link href="/" className="brand-lockup" aria-label="Orca Research 首页">Orca Research</Link>
      <button type="button" className="new-research" disabled={busy} onClick={newResearch}>新建研究</button>
      <nav className="rail-nav" aria-label="主导航"><Link className="rail-link rail-link-active" href="/" aria-current="page">研究工作台</Link><Link className="rail-link" href="/history">历史报告</Link></nav>
      <div className="rail-context"><p className="rail-label">研究范围</p><p>仅抓取白名单来源<br />预算由服务端配置</p></div>
      <p className="rail-footer">本地研究工具</p>
    </aside>

    <section className="research-stage">
      <header className="stage-header"><div><p className="eyebrow">研究工作台</p><h1>{heading}</h1><p className="stage-description">{hasResearch ? (taskActive ? "正在搜索、阅读并整理资料。" : "查看研究过程与报告，或新建下一项研究。") : "输入问题，搜索资料，生成带引用的报告。"}</p></div>{hasResearch ? <div className="task-health"><StatusBadge status={view.status} />{taskActive && view.connecting ? <span>连接中，断线后自动重连</span> : null}</div> : null}</header>
      {!hasResearch ? <form className="question-composer" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <label htmlFor="research-topic">研究问题</label>
        <textarea id="research-topic" rows={4} maxLength={500} placeholder="描述你想了解的问题，可以补充比较范围、时间或关注点。" value={topic} onChange={(event) => setTopic(event.target.value)} onKeyDown={(event) => { if (!event.nativeEvent.isComposing && (event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} disabled={busy} />
        <div className="composer-footer"><div className="composer-meta"><span>{topic.length}/500</span><span>Ctrl/⌘ + Enter 提交</span></div><div className="composer-actions"><button className="start-action" type="submit" disabled={!topic.trim() || busy}>{busy ? "正在连接…" : "开始研究"}</button></div></div>
      </form> : <div className="task-actions">{canCancel ? <button className="quiet-action" disabled={cancelling} onClick={async () => { setCancelling(true); if (!(await cancel())) setCancelling(false); }}>{cancelling ? "正在停止…" : "停止研究"}</button> : <button className="quiet-action" onClick={newResearch}>新建研究</button>}<a className="task-report-link" href="#research-report">查看报告 ↓</a></div>}
      {view.error ? <p className="notice notice-error" role="alert">{view.error}</p> : null}
      {hasResearch ? <FadeContent key={`run-${view.taskId}`} className="run-ledger" role="region" aria-label="研究进程"><div className="ledger-heading"><div><p className="eyebrow">研究进程</p><h2>{view.topic || "已恢复的研究任务"}</h2></div><dl className="research-counts"><div><dt>轮次</dt><dd>{view.roundNo || "—"}</dd></div><div><dt>来源</dt><dd>{view.progress.sources_read}</dd></div><div><dt>证据</dt><dd>{view.progress.evidence_count}</dd></div></dl></div>{view.stopReason ? <p className="stop-reason">停止原因：{stopReasonLabel(view.stopReason)}</p> : null}<Timeline items={view.timeline} active={taskActive} /></FadeContent> : <FadeContent className="quick-start" role="region" aria-label="快速开始"><div><p className="eyebrow">快速开始</p><h2>试试这些问题</h2></div><div className="quick-prompt-list">{quickPrompts.map((prompt) => <button type="button" key={prompt} disabled={busy} onClick={() => choosePrompt(prompt)}>{prompt}</button>)}</div>{recentReports.length > 0 ? <div className="recent-reports"><div className="section-row"><h2>最近完成</h2><Link href="/history">查看全部</Link></div><div className="recent-report-list">{recentReports.map((report) => <Link key={report.id} href={`/history?report=${report.id}`}><span>{report.topic}</span><small>{formatReportDate(report.created_at)} · {Math.round(report.duration_s)} 秒</small></Link>)}</div></div> : null}<dl className="research-limits"><div><dt>来源</dt><dd>白名单站点正文</dd></div><div><dt>输出</dt><dd>Markdown 报告与引用链接</dd></div><div><dt>中止</dt><dd>预算、页数或时长达到上限</dd></div></dl></FadeContent>}
    </section>

    {hasResearch ? <FadeContent key={`report-${view.taskId}`} className="report-desk" id="research-report" role="region" aria-label="研究报告" delay={60}>
      <header className="report-toolbar" aria-live="polite"><div><p className="eyebrow">研究报告</p><p className="report-status">{reportState}</p></div>{view.reportId !== null ? <a className="report-export" href={`${API}/api/reports/${view.reportId}.md`} target="_blank" rel="noopener noreferrer">导出 Markdown</a> : null}</header>
      <div className={`report-paper ${report ? "report-paper-live" : ""}`}>
        {view.finalLoadFailed ? <div className="report-message"><p>{report ? "报告详情加载失败，以下保留已收到的正文。" : "报告暂时无法加载，请重试。"}</p><button type="button" onClick={() => void retryFinalReport()}>重新加载引用</button></div> : null}
        {report ? <ReportView markdown={report} citationUrls={view.citationUrls} sources={view.sources} copyable={!taskActive} title={view.finalReport ? "研究结论" : "报告草稿"} /> : <div className="report-pending"><p className="eyebrow">{reportState}</p><p>{taskActive ? `第 ${view.roundNo} 轮 · 已阅读 ${view.progress.sources_read} 个来源 · 已收集 ${view.progress.evidence_count} 条证据` : view.status === "completed" ? "正在获取正式报告。" : "本次研究未生成报告。可查看左侧记录，或新建研究。"}</p></div>}
      </div>
    </FadeContent> : null}
  </main>;
}
