"""引用校验器测试(§3.3):[n] → citation_map 确定性映射;
失败处理 = 修订 / 删除 / 降级, 不能只删脚注留下无证据结论。
"""
from orca import evidence
from orca.citations import check_report, degrade_citations, revise_report


def ev(n):
    return evidence.CandidateEvidence(
        url=f"https://docs.python.org/{n}", title=f"来源{n}",
        domain="docs.python.org", source_type="official",
        quote=f"片段{n}", point=f"要点{n}", content_hash=f"h{n}",
        evidence_id=f"ev_{n:03d}", origin_group_id=f"og_{n}")


GOOD = "Python 3.13 引入自由线程 [1]。解释器支持彩色提示 [2]。"
BAD = "Python 3.13 引入自由线程 [1]。解释器支持彩色提示 [5]。"


def test_check_report_builds_citation_map():
    r = check_report(GOOD, [ev(1), ev(2)])
    assert r.citation_map == {"1": "ev_001", "2": "ev_002"}
    assert r.issues == []


def test_check_report_flags_out_of_range():
    r = check_report(BAD, [ev(1), ev(2)])
    assert "5" not in r.citation_map
    assert any(i.n == "5" for i in r.issues)


def test_check_report_flags_zero_and_ignores_non_numeric():
    r = check_report("标记 [0] 与 [x] 与 [12]", [ev(1)])
    assert any(i.n == "0" for i in r.issues)
    assert "x" not in r.citation_map          # [x] 不是数字引用
    assert "12" not in r.citation_map          # [12] 越界
    assert any(i.n == "12" for i in r.issues)


def test_check_report_empty_body_not_valid():
    """R3: 空正文不得判 valid —— 空报告落库 completed 是事故口径
    (与 c76a8b8 流式空内容显式失败同源), 校验器层面显式标记 empty。"""
    for body in ("", "   \n  "):
        r = check_report(body, [ev(1)])
        assert not r.valid
        assert r.issues[0].kind == "empty"


def test_uncited_evidence_not_in_map():
    r = check_report("只有一条引用 [2]", [ev(1), ev(2)])
    assert r.citation_map == {"2": "ev_002"}


def test_degrade_replaces_invalid_citation_without_deleting_claim():
    """降级:改写为"据来源标题, 未经正文核实"——不是只删脚注。"""
    out = degrade_citations(BAD, [ev(1), ev(2)])
    assert "[5]" not in out
    assert "未经正文核实" in out
    assert "解释器支持彩色提示" in out          # 断言保留但降级标注
    assert "[1]" in out                        # 有效引用不动


def test_revise_report_uses_llm_once_then_validates():
    calls = []

    def fake_chat(messages, *, max_tokens, tier, reasoning_effort=None):
        calls.append((messages, max_tokens, tier))
        return type("R", (), {"content": GOOD, "usage": {
            "prompt_tokens": 100, "completion_tokens": 50,
            "total_tokens": 150}})()

    out, usage = revise_report(BAD, [ev(1), ev(2)], fake_chat)
    assert len(calls) == 1
    assert "[5]" not in out
    assert usage["total_tokens"] == 150


def test_revise_report_falls_back_to_degrade():
    def bad_chat(messages, *, max_tokens, tier, reasoning_effort=None):
        return type("R", (), {"content": "仍含 [7] 的坏报告", "usage": {
            "prompt_tokens": 100, "completion_tokens": 50,
            "total_tokens": 150}})()

    out, usage = revise_report(BAD, [ev(1), ev(2)], bad_chat)
    assert "[7]" not in out and "[5]" not in out
    assert "未经正文核实" in out
    assert usage["total_tokens"] == 150        # 修订调用也入账(§3.6)
