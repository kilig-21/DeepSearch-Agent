"""标注与计分测试(§10.2 计分规则写进脚本, 可复核)。

- 支持=1 / 部分支持=0.5 / 不支持=0;三档原始分布一并报告
- 答案覆盖率按全部题报告(covered=1 / partial=0.5 / missed=0)
- 失败/无答案题记 N/A, 豁免质量分母但不豁免失败率
- 恶意题安全判定不与质量分平均
"""
import json

import pytest

from orca.eval import annotate


def _run_row(qid="q1", stop="single_pass", qtype="fact"):
    return {"qid": qid, "qtype": qtype, "status": "completed",
            "stop_reason": stop, "report_md": "报告",
            "required_points": ["要点一", "要点二"]}


def _annotation_row(qid="q1", stop="single_pass", qtype="fact"):
    return {
        "qid": qid, "qtype": qtype, "stop_reason": stop,
        "coverage": [
            {"point": "要点一", "mark": "covered", "note": ""},
            {"point": "要点二", "mark": "partial", "note": "仅提其一"},
        ],
        "assertions": [
            {"text": "断言 A", "mark": "support", "evidence_ids": ["ev_001"],
             "note": ""},
            {"text": "断言 B", "mark": "partial", "evidence_ids": ["ev_002"],
             "note": "仅覆盖一半"},
            {"text": "断言 C", "mark": "not_support", "evidence_ids": [],
             "note": "证据不含此信息"},
        ],
    }


# ---- schema 校验 ------------------------------------------------------------

def test_validate_ok():
    ann = {"questions": [_annotation_row()]}
    run = {"results": [_run_row()]}
    assert annotate.validate(ann, run) == []


def test_validate_rejects_bad_mark():
    row = _annotation_row()
    row["assertions"][0]["mark"] = "great"
    ann = {"questions": [row]}
    run = {"results": [_run_row()]}
    errs = annotate.validate(ann, run)
    assert errs and "great" in errs[0]


def test_validate_rejects_qid_mismatch():
    ann = {"questions": [_annotation_row(qid="other")]}
    run = {"results": [_run_row()]}
    errs = annotate.validate(ann, run)
    assert errs


# ---- 计分 -------------------------------------------------------------------

def test_scores_assertion_support():
    ann = {"questions": [_annotation_row()]}
    run = {"results": [_run_row()]}
    s = annotate.score(ann, run)
    # 支持 1 + 部分 0.5 + 不支持 0 = 1.5 / 3 = 0.5
    assert s["assertion_support"]["score"] == pytest.approx(0.5)
    assert s["assertion_support"]["numerator"] == pytest.approx(1.5)
    assert s["assertion_support"]["denominator"] == 3
    dist = s["assertion_support"]["distribution"]
    assert dist == {"support": 1, "partial": 1, "not_support": 1}


def test_scores_answer_coverage_over_all_questions():
    ann = {"questions": [_annotation_row()]}
    run = {"results": [_run_row()]}
    s = annotate.score(ann, run)
    # covered 1 + partial 0.5 = 1.5 / 2 = 0.75
    assert s["answer_coverage"]["score"] == pytest.approx(0.75)
    dist = s["answer_coverage"]["distribution"]
    assert dist == {"covered": 1, "partial": 1, "missed": 0}


def test_na_question_excluded_from_quality_not_failure_rate():
    rows = [
        _annotation_row(qid="ok", stop="single_pass"),
        _annotation_row(qid="na", stop="no_new_evidence"),
    ]
    rows[1]["coverage"] = []
    rows[1]["assertions"] = []
    run = {"results": [
        _run_row(qid="ok", stop="single_pass"),
        _run_row(qid="na", stop="no_new_evidence"),
    ]}
    s = annotate.score({"questions": rows}, run)
    # N/A 题不入质量分母
    assert [q["qid"] for q in s["quality_denominator_rows"]] == ["ok"]
    # 失败率分母 = 全部任务(§10.2)
    assert s["failure_rate"]["denominator"] == 2
    assert s["failure_rate"]["numerator"] == 0  # 无执行失败(completed)


def test_safety_reported_separately():
    run = {"results": [
        _run_row(qid="inject_direct", qtype="inject"),
    ]}
    run["results"][0]["safety"] = {"pass": True}
    s = annotate.score({"questions": []}, run)
    assert s["safety"] == {"inject_direct": True}
