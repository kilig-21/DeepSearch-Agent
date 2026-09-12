"""CLI 时间线呈现测试(events.py, 计划书 §4 Phase 1A)。

草稿帧口径:writer 流式逐片段 emit `report_delta`,片段粒度由上游决定
(实测 DeepSeek 返回粒度细, 可达逐字)。CLI 必须把连续片段**累加成一段
草稿**呈现——每帧打一次标题框会把时间线彻底刷屏, 且评测 runner 的
_tee_emit 也走本模块, 27 题(对比模式 45 行)日志将不可读。
"""
from __future__ import annotations

from orca.events import ConsoleTimeline


def _run(capsys, events: list[tuple[str, dict]]) -> str:
    """按序 emit 一组事件, 返回控制台输出。"""
    timeline = ConsoleTimeline()
    for name, payload in events:
        timeline.emit(name, payload)
    return capsys.readouterr().out


def test_draft_stream_prints_single_frame(capsys):
    """连续多帧草稿 → 只打一个标题框, 片段按序无缝拼接。"""
    out = _run(capsys, [
        ("report_delta", {"md": "第一段", "draft": True}),
        ("report_delta", {"md": "第二段", "draft": True}),
        ("report_delta", {"md": "第三段", "draft": True}),
    ])
    assert out.count("报告(草稿)") == 1
    assert "第一段第二段第三段" in out


def test_terminal_event_closes_open_draft_frame(capsys):
    """草稿框由终态事件收尾: 连续多帧只收尾一次, [done] 不黏在草稿正文末尾。"""
    out = _run(capsys, [
        ("report_delta", {"md": "草稿上半", "draft": True}),
        ("report_delta", {"md": "草稿下半", "draft": True}),
        ("done", {"report_id": 1, "stop_reason": "single_pass"}),
    ])
    assert out.count("======================") == 1
    assert out.index("======================") < out.index("[done]")
    assert out.rstrip().splitlines()[-1].startswith("[done]")


def test_replace_frame_starts_revised_section(capsys):
    """修订帧是整体替换语义: 收尾草稿框后按修订版整体打印, 不追加尾部。"""
    out = _run(capsys, [
        ("report_delta", {"md": "旧草稿", "draft": True}),
        ("report_delta", {"md": "修订后的全文", "draft": True, "replace": True}),
    ])
    assert "报告(修订版)" in out
    assert out.index("旧草稿") < out.index("报告(修订版)")
    assert "修订后的全文" in out


def test_other_events_keep_existing_format(capsys):
    """非草稿事件格式不变(回归保护)。"""
    out = _run(capsys, [
        ("plan", {"sub_questions": ["子问题一"]}),
        ("search", {"round": 1, "query": "查询", "results": [], "credits_used": 1}),
        ("warning", {"stage": "reader", "detail": "抓取失败"}),
    ])
    assert "[plan] 拆解子问题:" in out
    assert "1. 子问题一" in out
    assert '[search] 第1轮 "查询" → 0 条结果, 1 credits' in out
    assert "[warning] reader: 抓取失败" in out
    assert "报告(草稿)" not in out
