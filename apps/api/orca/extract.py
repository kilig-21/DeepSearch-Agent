"""正文提取(计划书 §2.2):trafilatura 为主力(Phase 0 实测定版)。

- 本地提取, 内容不出机器(§9.1);LLM 调用时才有片段出机器
- 单页字符 ≤100k(§3.6), 超出截断
- 抓取/提取失败 → ExtractError, 由 reader 转 warning 事件(任务继续)
"""
from __future__ import annotations

from dataclasses import dataclass

from trafilatura import extract as _trafilatura_extract

from .fetch import FetchBlocked, FetchResult, safe_fetch, safe_fetch_async

MAX_PAGE_CHARS = 100_000  # 单页字符上限(§3.6, Phase 0 实测最大单页 70k)


class ExtractError(Exception):
    """抓取或正文提取失败(调用方转 warning, 不终止任务)。"""


@dataclass
class ExtractedPage:
    url: str
    final_url: str
    text: str  # 确定性清洗后的正文(quote 校验的基准文本, §3.3)


def extract_main_text(html: str, *, max_chars: int = MAX_PAGE_CHARS) -> str:
    """确定性正文提取 + 长度截断。空结果抛 ExtractError。"""
    if not html or not html.strip():
        raise ExtractError("空响应体")
    text = _trafilatura_extract(html, include_comments=False,
                                include_tables=False) or ""
    text = text.strip()
    if not text:
        raise ExtractError("未能提取到正文")
    return text[:max_chars]


def _from_result(result: FetchResult) -> ExtractedPage:
    if result.status_code != 200:
        raise ExtractError(f"HTTP {result.status_code}: {result.final_url}")
    text = extract_main_text(result.body)
    return ExtractedPage(url=result.final_url, final_url=result.final_url,
                         text=text)


def fetch_and_extract(
    url: str,
    *,
    allowed_domains: set[str] | None = None,
    proxy: str | None = None,
    client_factory=None,
) -> ExtractedPage:
    """同步:抓取 + 提取(CLI/脚本用)。"""
    try:
        kwargs = {"allowed_domains": allowed_domains, "proxy": proxy}
        if client_factory is not None:
            kwargs["client_factory"] = client_factory
        result = safe_fetch(url, **kwargs)
    except FetchBlocked as e:
        raise ExtractError(f"抓取被安全策略拒绝: {e}") from e
    return _from_result(result)


async def fetch_and_extract_async(
    url: str,
    *,
    allowed_domains: set[str] | None = None,
    proxy: str | None = None,
    client_factory=None,
) -> ExtractedPage:
    """异步:reader 节点内部并发抓取用。"""
    kwargs = {"allowed_domains": allowed_domains, "proxy": proxy}
    if client_factory is not None:
        kwargs["client_factory"] = client_factory
    try:
        result = await safe_fetch_async(url, **kwargs)
    except FetchBlocked as e:
        raise ExtractError(f"抓取被安全策略拒绝: {e}") from e
    return _from_result(result)
