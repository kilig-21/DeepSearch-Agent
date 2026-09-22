"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ReportView } from "@/components/research/report-view";
import { resolveCitationUrls } from "@/lib/citations";
import type { ReportDetail } from "@/lib/types";
import { stopReasonLabel } from "@/lib/display";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

interface ReportCard {
  id: number;
  task_id: string;
  topic: string;
  stop_reason: string;
  token_cost: number;
  credits_cost: number;
  duration_s: number;
  created_at: string;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function HistoryPage() {
  const [reports, setReports] = useState<ReportCard[]>([]);
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [failedReportId, setFailedReportId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(20);
  const listRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const filteredReports = reports.filter((report) => report.topic.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));

  const loadList = useCallback(async () => {
    listRequest.current?.abort();
    const controller = new AbortController();
    listRequest.current = controller;
    setLoading(true);
    setListError(null);
    try {
      const response = await fetch(`${API}/api/reports`, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const items: ReportCard[] = await response.json();
      if (!controller.signal.aborted) setReports(items);
    } catch {
      if (!controller.signal.aborted) setListError("暂时无法读取报告列表，请检查服务连接后重试。");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  const open = useCallback(async (id: number, updateAddress = true) => {
    detailRequest.current?.abort();
    const controller = new AbortController();
    detailRequest.current = controller;
    setDetail(null);
    setOpeningId(id);
    setError(null);
    setFailedReportId(null);
    try {
      const response = await fetch(`${API}/api/reports/${id}`, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const report: ReportDetail = await response.json();
      if (controller.signal.aborted) return;
      setDetail(report);
      if (updateAddress) window.history.pushState(null, "", `/history?report=${id}`);
    } catch {
      if (controller.signal.aborted) return;
      setFailedReportId(id);
      setError("这份报告暂时无法打开，请稍后重试。");
    } finally {
      if (!controller.signal.aborted) setOpeningId(null);
    }
  }, []);

  useEffect(() => {
    const restoreAddress = () => {
      const reportId = Number(new URLSearchParams(window.location.search).get("report"));
      if (Number.isInteger(reportId) && reportId > 0) {
        void open(reportId, false);
      } else {
        detailRequest.current?.abort();
        setDetail(null);
        setOpeningId(null);
        setError(null);
        setFailedReportId(null);
      }
    };
    void loadList();
    restoreAddress();
    window.addEventListener("popstate", restoreAddress);
    return () => {
      listRequest.current?.abort();
      detailRequest.current?.abort();
      window.removeEventListener("popstate", restoreAddress);
    };
  }, [loadList, open]);

  return (
    <main className="history-page">
      <header className="history-header">
        <div>
          <p className="eyebrow">DeepSearch</p>
          <h1>{detail ? "报告详情" : "历史报告"}</h1>
        </div>
        <div className="history-actions">
          <Link href="/">返回工作台</Link>
          {!detail ? <button onClick={() => void loadList()} disabled={loading || openingId !== null}>刷新列表</button> : null}
        </div>
      </header>

      {error || (!detail && listError) ? (
        <div className="history-error" role="alert">
          <p>{error ?? listError}</p>
          <button disabled={loading || openingId !== null} onClick={() => void (failedReportId != null ? open(failedReportId) : loadList())}>重试</button>
        </div>
      ) : null}

      {detail ? (
        <section className="history-detail">
          <div className="history-detail-top">
            <button onClick={() => { setDetail(null); setError(null); setFailedReportId(null); window.history.pushState(null, "", "/history"); }}>返回列表</button>
            <a href={`${API}/api/reports/${detail.id}.md`} target="_blank" rel="noopener noreferrer">导出 Markdown</a>
          </div>
          <dl className="history-summary">
            <div><dt>完成时间</dt><dd>{formatDate(detail.created_at)}</dd></div>
            <div><dt>停止原因</dt><dd title={detail.stop_reason}>{stopReasonLabel(detail.stop_reason)}</dd></div>
            <div><dt>消耗</dt><dd>{detail.token_cost.toLocaleString()} tokens · {detail.credits_cost} credits</dd></div>
            <div><dt>耗时</dt><dd>{Math.round(detail.duration_s)} 秒</dd></div>
          </dl>
          <ReportView key={detail.id} markdown={detail.final_md} citationUrls={resolveCitationUrls(detail)} sources={detail.sources} title="研究报告" />
        </section>
      ) : (
        <section className="history-list" aria-busy={loading || openingId !== null}>
          <div className="history-filters"><label htmlFor="report-search">搜索报告</label><input id="report-search" type="search" placeholder="按研究问题搜索" value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(20); }} /><span>{filteredReports.length} 份报告</span></div>
          {openingId !== null ? <p className="history-state" role="status">正在打开报告…</p> : null}
          {loading ? <p className="history-state">正在读取报告…</p> : reports.length === 0 ? (error || listError || openingId !== null ? null : <p className="history-state">还没有完成的报告。<Link href="/">新建研究</Link></p>) : filteredReports.length === 0 ? <p className="history-state">没有找到匹配的报告，试试其他关键词。</p> : filteredReports.slice(0, visibleCount).map((report) => (
            <button key={report.id} onClick={() => void open(report.id)} className="history-row" disabled={openingId !== null}>
              <span className="history-row-number">{String(report.id).padStart(2, "0")}</span>
              <span className="history-row-main"><strong>{report.topic}</strong><small>{formatDate(report.created_at)} · {stopReasonLabel(report.stop_reason)}</small></span>
              <span className="history-row-cost">{openingId === report.id ? "正在打开…" : <>{report.token_cost.toLocaleString()} tokens<br />{Math.round(report.duration_s)} 秒</>}</span>
            </button>
          ))}
          {!loading && filteredReports.length > visibleCount ? <div className="history-load-more">
            <span>已显示 {visibleCount} / {filteredReports.length} 份报告</span>
            <button type="button" className="quiet-action" disabled={openingId !== null} onClick={() => setVisibleCount((count) => count + 20)}>加载更多</button>
          </div> : null}
        </section>
      )}
    </main>
  );
}
