"""搜索层测试:Tavily 主 + ddgs 备胎 + 去重(计划书 §2.2 可插拔搜索)。"""
import pytest

from orca import search
from orca.search import SearchResult


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


TAVILY_OK = {
    "results": [
        {"title": "Python 3.13 发布", "url": "https://docs.python.org/3/whatsnew/",
         "content": "摘要文本", "score": 0.9},
        {"title": "另一页", "url": "https://docs.python.org/3/whatsnew/?utm_source=x",
         "content": "重复页摘要", "score": 0.8},
    ],
}


def make_post(responses):
    calls = []

    def post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json,
                      "timeout": timeout})
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    post.calls = calls
    return post


def test_tavily_search_returns_results_and_one_credit():
    post = make_post([FakeResponse(200, TAVILY_OK)])
    backend = search.TavilySearch(api_key="tvly-test", post=post)

    results, credits = backend.search("Python 3.13 新特性", limit=5)

    assert credits == 1  # Basic 1 credit/次(§3.6)
    assert len(results) == 2
    assert results[0].url == "https://docs.python.org/3/whatsnew/"
    assert post.calls[0]["json"]["query"] == "Python 3.13 新特性"
    assert post.calls[0]["json"]["max_results"] == 5


def test_tavily_error_raises_search_error():
    post = make_post([FakeResponse(500, {})])
    backend = search.TavilySearch(api_key="k", post=post)
    with pytest.raises(search.SearchError):
        backend.search("q", limit=5)


def test_dedup_removes_normally_identical_urls():
    results = [
        SearchResult(url="https://docs.python.org/a/", title="t1", snippet="s1"),
        SearchResult(url="http://docs.python.org/a?utm_source=n", title="t2",
                     snippet="s2"),
        SearchResult(url="https://developer.mozilla.org/b", title="t3", snippet="s3"),
    ]
    out = search.dedup(results)
    assert len(out) == 2
    assert {r.url for r in out} == {"https://docs.python.org/a",
                                    "https://developer.mozilla.org/b"}


def test_ddgs_backend_returns_zero_credits():
    class FakeDdgs:
        def text(self, query, max_results=5):
            return [{"title": "t", "href": "https://docs.python.org/x",
                     "body": "b"}]

    backend = search.DdgsSearch(ddgs_factory=lambda: FakeDdgs())
    results, credits = backend.search("q", limit=5)
    assert credits == 0
    assert results[0].url == "https://docs.python.org/x"
    assert results[0].snippet == "b"


def test_split_by_allowlist():
    """§4 Phase 1A:集合外站点不抓正文, 仅列为待核实链接。"""
    results = [
        SearchResult(url="https://docs.python.org/a", title="t", snippet="s"),
        SearchResult(url="https://evil.example.com/x", title="t", snippet="s"),
    ]
    allowed, outside = search.split_by_allowlist(
        results, {"docs.python.org", "developer.mozilla.org"})
    assert [r.url for r in allowed] == ["https://docs.python.org/a"]
    assert [r.url for r in outside] == ["https://evil.example.com/x"]


OUTSIDE_ONLY = {
    "results": [
        {"title": "CSDN 教程", "url": "https://blog.csdn.net/x/1",
         "content": "s", "score": 0.9},
        {"title": "知乎专栏", "url": "https://zhuanlan.zhihu.com/p/1",
         "content": "s", "score": 0.8},
    ],
}

SCOPED_HITS = {
    "results": [
        {"title": "venv 文档", "url": "https://docs.python.org/3/library/venv.html",
         "content": "s", "score": 0.7},
    ],
}


def test_tavily_search_passes_include_domains_when_given():
    """来源集合限定:Tavily 支持 include_domains, 是打空补搜的实现基础。"""
    post = make_post([FakeResponse(200, TAVILY_OK)])
    backend = search.TavilySearch(api_key="k", post=post)

    backend.search("q", limit=5, include_domains=["docs.python.org"])

    assert post.calls[0]["json"]["include_domains"] == ["docs.python.org"]


def test_tavily_search_omits_include_domains_by_default():
    """默认不限定域名:主搜索仍是全网检索, 集合外结果供"待核实链接"。"""
    post = make_post([FakeResponse(200, TAVILY_OK)])
    backend = search.TavilySearch(api_key="k", post=post)

    backend.search("q", limit=5)

    assert "include_domains" not in post.calls[0]["json"]


def test_whitelist_retry_skipped_when_whitelist_hit_present():
    post = make_post([FakeResponse(200, TAVILY_OK)])
    backend = search.WhitelistRetrySearch(
        search.TavilySearch(api_key="k", post=post),
        allowed_domains={"docs.python.org"})

    results, credits = backend.search("q", limit=5)

    assert len(post.calls) == 1, "已有白名单命中, 不应补搜"
    assert credits == 1
    assert results


def test_whitelist_retry_fires_when_all_results_outside_whitelist():
    """白名单打空的修复:主搜索全落在集合外时, 补一次限定域名搜索。

    实测背景(probe T12 补充, 2026-09-12 真实 8 题试点):fact_mdn401 /
    fact_venv 两题的搜索结果 100% 落在集合外(CSDN/知乎/菜鸟教程),
    整轮 0 证据、报告退化为程序生成的"研究未能完成"。
    """
    post = make_post([FakeResponse(200, OUTSIDE_ONLY),
                      FakeResponse(200, SCOPED_HITS)])
    backend = search.WhitelistRetrySearch(
        search.TavilySearch(api_key="k", post=post),
        allowed_domains={"docs.python.org"})

    results, credits = backend.search("q", limit=5)

    assert len(post.calls) == 2, "应补搜一次"
    assert post.calls[1]["json"]["include_domains"] == ["docs.python.org"]
    assert credits == 2, "补搜照常计 credit(§3.6 如实入账)"
    urls = [r.url for r in results]
    # 限定域名命中排在最前:reader 只读白名单内 top-N (§3.2)
    assert urls[0] == "https://docs.python.org/3/library/venv.html"
    # 集合外结果照旧保留 → "待核实链接"一节语义不变 (§9.1)
    assert "https://blog.csdn.net/x/1" in urls


def test_whitelist_retry_skipped_when_search_returned_nothing():
    """搜索本就 0 结果时不补搜:无证据表明域名限定能救, 不白花 credit。"""
    post = make_post([FakeResponse(200, {"results": []})])
    backend = search.WhitelistRetrySearch(
        search.TavilySearch(api_key="k", post=post),
        allowed_domains={"docs.python.org"})

    results, credits = backend.search("q", limit=5)

    assert len(post.calls) == 1
    assert results == []
    assert credits == 1
