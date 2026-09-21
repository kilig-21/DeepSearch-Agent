"""搜索层(计划书 §2.2):Tavily 主 + ddgs 备胎, 可插拔接口。

- Tavily Basic 1 credit/次(§3.6 口径);计账由调用方按返回的 credits_used 入账
- ddgs 备胎免费无 key, 仅限开发调试, 非官方随时可能失效
- 集合外站点不抓正文, 仅列为待核实链接(§4 Phase 1A):split_by_allowlist
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx

from .config import TAVILY_API_KEY, TAVILY_SEARCH_URL
from .urls import norm_url

DEFAULT_TIMEOUT = 20.0  # 单调用超时(§3.6)


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str  # 搜索摘要——不得作为"已阅读全文"的证据(§4 Phase 1A)
    score: float = 0.0


class SearchError(Exception):
    """搜索后端失败(调用方转 warning 或终止)。"""


def dedup(results: list[SearchResult]) -> list[SearchResult]:
    """按归一化 URL 去重, 保留先出现者;输出统一为规范化 URL(规范形式)。"""
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        try:
            key = norm_url(r.url)
        except ValueError:
            continue  # 无法解析的 URL 直接丢弃
        if key in seen:
            continue
        seen.add(key)
        out.append(SearchResult(url=key, title=r.title, snippet=r.snippet,
                                score=r.score))
    return out


def split_by_allowlist(
    results: list[SearchResult], allowed_domains: set[str]
) -> tuple[list[SearchResult], list[SearchResult]]:
    """白名单内(可抓正文)/ 集合外(仅列待核实链接)分组。"""
    allowed: list[SearchResult] = []
    outside: list[SearchResult] = []
    for r in results:
        host = (httpx.URL(r.url).host or "").lower()
        if any(host == d or host.endswith("." + d) for d in allowed_domains):
            allowed.append(r)
        else:
            outside.append(r)
    return allowed, outside


class TavilySearch:
    def __init__(self, *, api_key: str = TAVILY_API_KEY,
                 url: str = TAVILY_SEARCH_URL,
                 post: Callable | None = None,
                 timeout_s: float = DEFAULT_TIMEOUT) -> None:
        if post is not None:
            self._post = post
        else:
            self._post = httpx.post
        self._api_key = api_key
        self._url = url
        self._timeout_s = timeout_s

    def search(self, query: str, *, limit: int = 5,
               include_domains: Sequence[str] | None = None,
               ) -> tuple[list[SearchResult], int]:
        payload: dict = {"query": query, "max_results": limit,
                         "search_depth": "basic"}
        # 限定域名搜索(可选):把检索面收缩到来源集合内。默认不发该参数——
        # 主搜索保持全网检索, 集合外结果供"待核实链接"(§9.1)。
        if include_domains:
            payload["include_domains"] = list(include_domains)
        try:
            resp = self._post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout_s,
            )
        except Exception as e:  # noqa: BLE001
            raise SearchError(f"网络错误: {type(e).__name__}: {e}") from e
        if resp.status_code != 200:
            raise SearchError(f"HTTP {resp.status_code}: {str(resp.text)[:150]}")
        data = resp.json()
        results = [
            SearchResult(url=item.get("url", ""), title=item.get("title", ""),
                         snippet=item.get("content", ""),
                         score=float(item.get("score", 0.0)))
            for item in data.get("results", [])
        ]
        return results, 1  # Basic 固定 1 credit/次


class WhitelistRetrySearch:
    """打空补搜(§9.1 语义不变):主搜索全落在集合外时补一次限定域名搜索。

    背景(probe T12 补充, 2026-09-12 真实 8 题试点):Tavily 主搜索不限定
    域名, 在中文技术主题上常返回 CSDN/知乎/菜鸟教程等集合外站点, 白名单
    过滤后整轮 0 页可抓 → 0 证据 → 报告退化为程序生成的"研究未能完成"。
    实测 8 题命中 2 题(fact_mdn401 / fact_venv, 结论为 0 证据)。

    只在"主搜索有结果、但无一落在集合内"时补搜:
    - 主搜索结果照旧原样保留 —— 集合外结果仍是"待核实链接"的来源(§9.1)
    - 限定域名命中排在返回列表最前, 使 reader 优先读可抓页面(§3.2)
    - 补搜照常消耗 1 credit, 由调用方按返回的 credits 如实入账(§3.6)
    - 主搜索本就 0 结果时不补搜:无证据表明域名限定能救, 不白花 credit
    """

    def __init__(self, base, *, allowed_domains) -> None:
        self._base = base
        self._allowed = set(allowed_domains)

    def search(self, query: str, *, limit: int = 5,
               allow_extra_credit: Callable[[], bool] | None = None,
               ) -> tuple[list[SearchResult], int]:
        results, credits = self._base.search(query, limit=limit)
        if not results:
            return results, credits
        allowed, _outside = split_by_allowlist(results, self._allowed)
        if allowed:
            return results, credits
        # 主搜索的 credit 已由上层预占。补搜是真实的第二次计费调用，必须
        # 在发出请求前再检查剩余额度；None 保留搜索层独立使用时的旧行为。
        if allow_extra_credit is not None and not allow_extra_credit():
            return results, credits
        scoped, scoped_credits = self._base.search(
            query, limit=limit, include_domains=sorted(self._allowed))
        return dedup(scoped + results), credits + scoped_credits


class DdgsSearch:
    """备胎:免费无 key, 非官方、随时可能失效, 仅限开发调试。"""

    def __init__(self, ddgs_factory: Callable | None = None) -> None:
        if ddgs_factory is not None:
            self._factory = ddgs_factory
        else:
            def _default():
                from ddgs import DDGS
                return DDGS()
            self._factory = _default

    def search(self, query: str, *, limit: int = 5) -> tuple[list[SearchResult], int]:
        try:
            raw = self._factory().text(query, max_results=limit)
        except Exception as e:  # noqa: BLE001
            raise SearchError(f"ddgs 失败: {type(e).__name__}: {e}") from e
        results = [
            SearchResult(url=item.get("href", ""), title=item.get("title", ""),
                         snippet=item.get("body", ""))
            for item in raw
        ]
        return results, 0
