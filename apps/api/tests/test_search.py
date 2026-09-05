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
