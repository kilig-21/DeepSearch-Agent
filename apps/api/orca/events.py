"""事件 → CLI 日志时间线(计划书 §4 Phase 1A:时间线可暂为日志输出)。

事件名与 §3.4 协议一致;Phase 1B 的 TaskManager 将把这些事件推给 SSE,
本模块仅做控制台呈现, 不承载协议逻辑。
"""
from __future__ import annotations


class ConsoleTimeline:
    """控制台时间线呈现(CLI 与评测 runner 共用;console_emit 为默认实例)。

    草稿帧(report_delta)由 writer 流式逐片段发出, 片段粒度由上游决定
    (可达逐字):连续片段累加为**一段**打印, 只在首帧打标题、由下一个
    非草稿事件(终态或其它事件)收尾。逐帧独立打框会把时间线刷屏, 评测
    runner 的 _tee_emit 同样走本模块, 27 题日志将不可读。
    """

    def __init__(self) -> None:
        self._draft_open = False

    def emit(self, event: str, payload: dict) -> None:
        if event == "report_delta":
            self._emit_draft(payload)
            return
        # 任何非草稿事件都先收尾未闭合的草稿段(终态行不得黏在正文末尾)
        self._close_draft()
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

    def _emit_draft(self, payload: dict) -> None:
        """草稿/修订帧:首帧打标题, 后续片段无缝追加(不换行、不加框)。"""
        md = payload.get("md", "")
        if payload.get("replace"):
            # 修订帧是整体替换语义(§3.3):收尾草稿段, 修订版另起一段整篇打印
            self._close_draft()
            print("\n===== 报告(修订版)=====\n")
            self._draft_open = True
            print(md, end="")
            return
        if not self._draft_open:
            print("\n===== 报告(草稿)=====\n")
            self._draft_open = True
        print(md, end="")

    def _close_draft(self) -> None:
        if self._draft_open:
            print("\n======================\n")
            self._draft_open = False


# CLI(cli.py 的 GraphTools.emit)与评测 runner 的 _tee_emit 直接引用本名字
console_emit = ConsoleTimeline().emit
