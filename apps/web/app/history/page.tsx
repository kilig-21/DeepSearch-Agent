"use client";

// 历史报告页(计划书 §6 GET /api/reports + §7):列表 → 详情(final_md 渲染)
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ReportView } from "@/components/research/report-view";
import type { ReportDetail } from "@/lib/types";

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

export default function HistoryPage() {
  const [reports, setReports] = useState<ReportCard[] | null>(null);
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/reports`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setReports(await resp.json());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const open = useCallback(async (id: number) => {
    setError(null);
    try {
      const resp = await fetch(`${API}/api/reports/${id}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setDetail(await resp.json());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">历史报告</h1>
        <div className="flex gap-3 text-sm">
          <Link className="text-blue-600 hover:underline" href="/">
            新研究
          </Link>
          <button
            className="text-blue-600 hover:underline"
            onClick={() => void loadList()}
          >
            刷新
          </button>
        </div>
      </header>

      {error ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      {detail ? (
        <section className="space-y-3 rounded border border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <button
              className="text-sm text-blue-600 hover:underline"
              onClick={() => setDetail(null)}
            >
              ← 返回列表
            </button>
            <a
              className="text-sm text-blue-600 hover:underline"
              href={`${API}/api/reports/${detail.id}.md`}
              target="_blank"
              rel="noopener noreferrer"
            >
              导出 .md
            </a>
          </div>
          <p className="text-xs text-gray-500">
            {detail.topic} · stop: {detail.stop_reason} · tokens {detail.token_cost} ·
            credits {detail.credits_cost} · {detail.duration_s}s
          </p>
          <ReportView
            markdown={detail.final_md}
            citationMap={detail.citation_map_json}
            title="研究报告"
          />
        </section>
      ) : (
        <section className="space-y-2">
          {reports === null ? (
            <p className="text-sm text-gray-500">加载中…</p>
          ) : reports.length === 0 ? (
            <p className="text-sm text-gray-500">还没有已完成的报告。</p>
          ) : (
            reports.map((r) => (
              <button
                key={r.id}
                className="block w-full rounded border border-gray-200 p-3 text-left hover:bg-gray-50"
                onClick={() => void open(r.id)}
              >
                <p className="font-medium">{r.topic}</p>
                <p className="text-xs text-gray-500">
                  #{r.id} · {r.stop_reason} · {r.created_at} · tokens {r.token_cost} ·
                  credits {r.credits_cost} · {r.duration_s}s
                </p>
              </button>
            ))
          )}
        </section>
      )}
    </main>
  );
}
