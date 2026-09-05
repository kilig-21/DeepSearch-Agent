// 引用联查(第四轮评审 F3):citation_map 是 [n] → evidence_id;
// 经详情数据 evidences.source_id → sources 联查真实 URL。
// 绝不把 evidence_id 当 href, 联查不到的编号不伪造链接。
import type { ReportDetail } from "./types";

export function resolveCitationUrls(detail: ReportDetail): Record<string, string> {
  const sourceByEvidence = new Map(
    (detail.evidences ?? []).map((e) => [e.evidence_id, e.source_id]),
  );
  const urlById = new Map((detail.sources ?? []).map((s) => [s.id, s.url]));
  const urls: Record<string, string> = {};
  for (const [n, evidenceId] of Object.entries(detail.citation_map_json ?? {})) {
    const sourceId = sourceByEvidence.get(evidenceId);
    const url = sourceId !== undefined ? urlById.get(sourceId) : undefined;
    if (url) urls[n] = url;
  }
  return urls;
}
