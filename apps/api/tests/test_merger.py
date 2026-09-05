"""merger 测试(§3.2/§3.3):集中合并、URL 归一化去重、origin_group_id、
任务内稳定 evidence_id(生成后永不重排)。
"""
from orca import evidence
from orca.merger import merge_candidates


def cand(url, title="标题", quote="q", point="p", content_hash="h1",
         domain="docs.python.org"):
    return evidence.CandidateEvidence(
        url=url, title=title, domain=domain,
        source_type=evidence.source_type_for_domain(domain),
        quote=quote, point=point, content_hash=content_hash)


def test_dedup_by_normalized_url():
    out = merge_candidates([], [
        cand("https://docs.python.org/a/?utm_source=x", title="A"),
        cand("https://docs.python.org/a", title="B"),
    ])
    assert len(out) == 1
    assert out[0].title == "A"          # 保留先出现者


def test_same_url_different_quotes_both_kept():
    """一页可产出多条证据(不同 quote);URL 去重只针对重复引文。"""
    out = merge_candidates([], [
        cand("https://docs.python.org/a", quote="片段一"),
        cand("https://docs.python.org/a", quote="片段二"),
    ])
    assert len(out) == 2
    assert out[0].origin_group_id == out[1].origin_group_id  # 同页同组


def test_same_content_different_urls_share_origin_group():
    out = merge_candidates([], [
        cand("https://docs.python.org/a", content_hash="abc123"),
        cand("https://developer.mozilla.org/b", domain="developer.mozilla.org",
             content_hash="abc123"),
    ])
    assert out[0].origin_group_id is not None
    assert out[0].origin_group_id == out[1].origin_group_id


def test_different_content_different_groups():
    out = merge_candidates([], [
        cand("https://docs.python.org/a", content_hash="h1"),
        cand("https://docs.python.org/b", content_hash="h2"),
    ])
    assert out[0].origin_group_id != out[1].origin_group_id


def test_evidence_ids_stable_and_incremental():
    first = merge_candidates([], [cand("https://docs.python.org/a"),
                                  cand("https://docs.python.org/b")])
    assert [e.evidence_id for e in first] == ["ev_001", "ev_002"]

    # Phase 2 多轮:传入已有池, 新编号接续, 旧 ID 永不重排
    second = merge_candidates(first, [cand("https://docs.python.org/c")])
    assert [e.evidence_id for e in second] == ["ev_003"]
    assert first[0].evidence_id == "ev_001"


def test_same_url_across_rounds_not_duplicated():
    first = merge_candidates([], [cand("https://docs.python.org/a")])
    second = merge_candidates(first,
                              [cand("https://docs.python.org/a?utm_source=1")])
    assert second == []


def test_empty_quote_pool_ok():
    assert merge_candidates([], []) == []
