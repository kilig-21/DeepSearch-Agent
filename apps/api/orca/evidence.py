"""证据结构与 quote 定位校验(计划书 §3.3,v1.3 收紧)。

- quote 必须能定位到确定性清洗后的原文片段;只允许空白/换行规范化,
  不允许任何字符级改写
- 近似匹配仅用于**定位候选位置**;最终入库取回**实际原文片段**,
  不保留模型改写的引文(防"该功能~~不~~支持离线"式反义篡改——
  相似度无法验证语义, 机制保证才是防线)
- 来源"类型标签"而非"可信度分数"(§2.3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

SOURCE_TYPES = {"official", "media", "blog", "ugc", "paper"}

# 白名单来源的透明类型标签(docs/SOURCES.md);诚实优先:维基百科是
# 社区协作内容, 标 ugc 而非 official
SOURCE_TYPE_BY_DOMAIN = {
    "docs.python.org": "official",
    "developer.mozilla.org": "official",
    "zh.wikipedia.org": "ugc",
}

MAX_QUOTE_CHARS = 200   # §3.3: quote ≤200 字, 供核对
MIN_LOCATE_RATIO = 0.85  # 仅用于判定定位成功, 入库永远是实际原文

_WS_RE = re.compile(r"\s+")


def normalize_ws(text: str) -> str:
    """预定义规范化:任意空白序列(含换行/制表/全角空格)→ 单个半角空格。"""
    return _WS_RE.sub(" ", text).strip()


def source_type_for_domain(domain: str) -> str:
    if domain not in SOURCE_TYPE_BY_DOMAIN:
        raise ValueError(f"未登记来源类型(不在已核对来源集合内): {domain}")
    return SOURCE_TYPE_BY_DOMAIN[domain]


@dataclass
class LocateResult:
    validated: bool
    quote: str | None  # None = 校验失败;否则为实际原文片段(空白规范化)


@dataclass
class CandidateEvidence:
    """reader 产出的候选证据(quote 已通过 locate_quote 校验, §3.2)。

    不直接写 evidence 池、不发 note 事件——由 merger 集中合并编号。
    """
    url: str
    title: str
    domain: str
    source_type: str
    quote: str         # 实际原文片段(空白规范化)
    point: str         # 该页要点(报告素材)
    content_hash: str  # 抓取正文哈希(多站转载分组判定)
    # 以下由 merger 赋值;reader 产出时为 None(§3.2)
    evidence_id: str | None = None
    origin_group_id: str | None = None


def _anchors_of(nq: str, size: int = 10) -> list[str]:
    if len(nq) <= size:
        return [nq]
    positions = [0, len(nq) // 4, len(nq) // 2, (3 * len(nq)) // 4]
    anchors = [nq[p:p + size] for p in positions]
    anchors.append(nq[-size:])  # 尾部锚
    return [a for a in anchors if len(a) >= 4]


def _best_in_window(nq: str, window: str) -> tuple[float, str]:
    """窗口内与 nq 等长滑窗对齐的最高相似度及其对应片段。"""
    best_ratio, best_seg = 0.0, ""
    step = max(4, len(nq) // 8)
    for s in range(0, max(1, len(window) - len(nq) + 1), step):
        seg = window[s:s + len(nq)]
        sm = SequenceMatcher(None, nq, seg)
        if sm.real_quick_ratio() < MIN_LOCATE_RATIO:
            continue
        if sm.quick_ratio() < MIN_LOCATE_RATIO:
            continue
        r = sm.ratio()
        if r > best_ratio:
            best_ratio, best_seg = r, seg
    # 末尾对齐点(滑窗步长可能跳过)
    seg = window[-len(nq):]
    if seg:
        r = SequenceMatcher(None, nq, seg).ratio()
        if r > best_ratio:
            best_ratio, best_seg = r, seg
    return best_ratio, best_seg


def locate_quote(
    quote: str, cleaned_text: str, *,
    min_ratio: float = MIN_LOCATE_RATIO,
    max_chars: int = MAX_QUOTE_CHARS,
) -> LocateResult:
    """在清洗后正文中定位 quote;入库永远取实际原文片段(空白规范化)。"""
    nq = normalize_ws(quote)
    nt = normalize_ws(cleaned_text)
    if not nq:
        return LocateResult(False, None)

    # 1) 精确匹配(规范化后子串):入库即命中的片段本身
    idx = nt.find(nq)
    if idx >= 0:
        return LocateResult(True, nq[:max_chars])

    best = (0.0, "")  # (ratio, 片段)

    # 2) 锚点定位:quote 的短子串在原文中精确命中 → 扩展窗口评估
    margin = 24
    for anchor in _anchors_of(nq):
        start = 0
        while True:
            i = nt.find(anchor, start)
            if i < 0:
                break
            lo = max(0, i - margin)
            hi = min(len(nt), i + len(anchor) + len(nq) + margin)
            r, seg = _best_in_window(nq, nt[lo:hi])
            if r > best[0]:
                best = (r, seg)
            start = i + 1

    # 3) 全文滑窗兜底(锚点全部失效, 如改写密集)
    if best[0] < min_ratio:
        step = max(10, len(nq) // 8)
        for s in range(0, max(1, len(nt) - len(nq) + 1), step):
            seg = nt[s:s + len(nq)]
            sm = SequenceMatcher(None, nq, seg)
            if sm.real_quick_ratio() < min_ratio:
                continue
            if sm.quick_ratio() < min_ratio:
                continue
            r = sm.ratio()
            if r > best[0]:
                best = (r, seg)

    if best[0] >= min_ratio and best[1]:
        return LocateResult(True, best[1][:max_chars])
    return LocateResult(False, None)
