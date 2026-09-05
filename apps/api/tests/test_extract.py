"""提取层测试(trafilatura 主力, Phase 0 定版;单页 ≤100k 字符 §3.6)。"""
import asyncio

import pytest

from orca import extract


SAMPLE_HTML = """
<html><head><title>Python 3.13</title></head><body>
<nav>导航 链接 链接</nav>
<article>
<h1>Python 3.13 新特性</h1>
<p>交互式解释器全面升级,支持多行编辑与彩色提示。</p>
<p>实验性的自由线程模式允许禁用全局解释器锁。</p>
</article>
<footer>版权信息</footer>
</body></html>
"""


def test_extract_main_text_pulls_body_copy():
    text = extract.extract_main_text(SAMPLE_HTML)
    assert "自由线程" in text
    assert "交互式解释器" in text


def test_extract_main_text_truncates_to_max_chars():
    long_html = "<html><body><p>" + "长" * 300_000 + "</p></body></html>"
    text = extract.extract_main_text(long_html, max_chars=100_000)
    assert len(text) <= 100_000


def test_extract_main_text_raises_on_empty():
    with pytest.raises(extract.ExtractError):
        extract.extract_main_text("<html><body></body></html>")


def test_fetch_and_extract_end_to_end():
    """safe_fetch + trafilatura 全链(注入 client, 不出网络)。"""
    from tests.test_fetch import FakeClient, FakeResp

    client = FakeClient({
        "https://docs.python.org/a": FakeResp(200, SAMPLE_HTML),
    })
    page = extract.fetch_and_extract(
        "https://docs.python.org/a", allowed_domains={"docs.python.org"},
        client_factory=client)
    assert page.final_url == "https://docs.python.org/a"
    assert "自由线程" in page.text


def test_fetch_and_extract_wraps_block_as_extract_error():
    from tests.test_fetch import FakeClient

    client = FakeClient({})
    with pytest.raises(extract.ExtractError):
        extract.fetch_and_extract(
            "https://evil.example.com/x",
            allowed_domains={"docs.python.org"},
            client_factory=client)


def test_fetch_and_extract_async_end_to_end():
    from tests.test_fetch import FakeClient, FakeResp

    class FakeAsyncClient(FakeClient):
        async def get(self, url):
            return FakeClient.get(self, url)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    client = FakeAsyncClient({
        "https://docs.python.org/a": FakeResp(200, SAMPLE_HTML),
    })
    page = asyncio.run(extract.fetch_and_extract_async(
        "https://docs.python.org/a", allowed_domains={"docs.python.org"},
        client_factory=client))
    assert "自由线程" in page.text
