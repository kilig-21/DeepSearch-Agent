"""merger(计划书 §3.2/§3.3):集中合并节点。

- URL 归一化去重(跨轮也去重)
- 多站转载:content_hash 相同 → 共享 origin_group_id(表达"同一来源";
  独立来源计数按组判定, 不按 URL 数量)
- evidence_id 任务内稳定:ev_NNN 递增, 生成后永不重排
- note 事件由 graph 层在合并后发送(merger 本身保持纯函数)
"""
from __future__ import annotations

from .evidence import CandidateEvidence
from .urls import norm_url


def _next_seq(existing: list[CandidateEvidence]) -> int:
    """续接已有编号(Phase 2 多轮调用时旧 ID 永不重排)。"""
    max_seq = 0
    for e in existing:
        try:
            max_seq = max(max_seq, int(e.evidence_id.removeprefix("ev_")))
        except (AttributeError, ValueError):
            continue
    return max_seq


def _next_group_seq(existing: list[CandidateEvidence]) -> int:
    """origin_group 编号独立于 evidence_id 计数, 避免跳号。"""
    max_seq = 0
    for e in existing:
        gid = e.origin_group_id or ""
        if "_" in gid:
            try:
                max_seq = max(max_seq, int(gid.rsplit("_", 1)[1]))
            except ValueError:
                continue
    return max_seq


def merge_candidates(
    existing: list[CandidateEvidence],
    candidates: list[CandidateEvidence],
) -> list[CandidateEvidence]:
    """合并新候选入池, 返回**新增**的记录(已带 evidence_id / origin_group_id)。"""
    seen = {(norm_url(e.url), e.quote) for e in existing}
    group_by_hash: dict[str, str] = {
        e.content_hash: e.origin_group_id
        for e in existing if e.origin_group_id
    }
    seq = _next_seq(existing)
    gseq = _next_group_seq(existing)

    added: list[CandidateEvidence] = []
    for c in candidates:
        try:
            key = norm_url(c.url)
        except ValueError:
            continue  # 无法归一化的 URL 丢弃
        # 去重键 = (URL, quote):同页多条不同 quote 是合法的多条证据,
        # 仅同页同引文(跨轮重复抓取)才视为重复
        if (key, c.quote) in seen:
            continue
        seen.add((key, c.quote))

        group = group_by_hash.get(c.content_hash)
        if group is None:
            gseq += 1
            group = f"og_{c.content_hash[:12]}_{gseq:03d}"
            group_by_hash[c.content_hash] = group

        seq += 1
        added.append(CandidateEvidence(
            url=c.url, title=c.title, domain=c.domain,
            source_type=c.source_type, quote=c.quote, point=c.point,
            content_hash=c.content_hash,
            fetched_at=c.fetched_at,
            evidence_id=f"ev_{seq:03d}",
            origin_group_id=group,
        ))
    return added
