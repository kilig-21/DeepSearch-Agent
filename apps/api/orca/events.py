"""事件 → CLI 日志时间线(计划书 §4 Phase 1A:时间线可暂为日志输出)。

事件名与 §3.4 协议一致;Phase 1B 的 TaskManager 将把这些事件推给 SSE,
本模块仅做控制台呈现, 不承载协议逻辑。
"""
from __future__ import annotations


def console_emit(event: str, payload: dict) -> None:
    if event == "plan":
        print("[plan] 拆解子问题:")
        for i, q in enumerate(payload.get("sub_questions", []), 1):
            print(f"  {i}. {q}")
    elif event == "search":
        results = payload.get("results", [])
        print(f"[search] 第{payload.get('round')}轮 \"{payload.get('query')}\" "
              f"→ {len(results)} 条结果, {payload.get('credits_used', 0)} credits")
    elif event == "reading":
        print(f"[reading] ({payload.get('n')}/{payload.get('N')}) "
              f"{payload.get('title')} — {payload.get('url')}")
    elif event == "note":
        print(f"[note] {payload.get('evidence_id')} "
              f"(组 {payload.get('origin_group_id')}) {payload.get('point')[:60]}"
              f" — {payload.get('title')}")
    elif event == "warning":
        print(f"[warning] {payload.get('stage')}: {payload.get('detail')}")
    elif event == "reflection":
        print(f"[reflection] {payload}")
    elif event == "report_delta":
        print("\n===== 报告(草稿)=====\n")
        print(payload.get("md", ""))
        print("\n======================\n")
    elif event == "done":
        usage = payload.get("usage") or {}
        split = (f"(研究 {usage.get('llm_research_tokens', 0)} + "
                 f"writer {usage.get('llm_writer_tokens', 0)})"
                 if usage else "")
        print(f"[done] report_id={payload.get('report_id')} "
              f"stop_reason={payload.get('stop_reason')} "
              f"tokens={payload.get('token_cost')} {split} "
              f"credits={payload.get('credits_cost')} "
              f"耗时={payload.get('duration_s', 0):.1f}s")
    elif event == "task_failed":
        print(f"[task_failed] {payload.get('detail')}")
    elif event == "cancelled":
        print("[cancelled] 用户取消")
    else:
        print(f"[{event}] {payload}")
