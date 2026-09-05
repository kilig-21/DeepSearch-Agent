"""safe_fetch SSRF 防护单测(纯函数部分, 不出网络)。"""
import pytest

from orca.fetch import FetchBlocked, is_blocked_ip


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",            # 回环
        "10.0.0.5",             # 私网
        "192.168.1.1",          # 私网
        "172.16.0.9",           # 私网
        "169.254.169.254",      # 云元数据(链路本地)
        "0.0.0.0",              # 未指定
        "100.64.0.1",           # CGNAT 保留段
        "::1",                  # IPv6 回环
        "fe80::1",              # IPv6 链路本地
        "fc00::1",              # IPv6 ULA
        "::ffff:192.168.1.1",   # IPv4-mapped IPv6 私网
        "::ffff:169.254.169.254",  # IPv4-mapped 元数据
    ],
)
def test_blocked_ips(ip: str) -> None:
    assert is_blocked_ip(ip) is True, f"{ip} 应被拒绝"


@pytest.mark.parametrize(
    "ip",
    ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "114.114.114.114"],
)
def test_public_ips_allowed(ip: str) -> None:
    assert is_blocked_ip(ip) is False, f"{ip} 是公网地址, 不应被拒"


def test_scheme_check_blocks_file_url() -> None:
    from orca.fetch import safe_fetch

    with pytest.raises(FetchBlocked, match="仅允许"):
        safe_fetch("file:///etc/passwd")


def test_scheme_check_blocks_ftp() -> None:
    from orca.fetch import safe_fetch

    with pytest.raises(FetchBlocked, match="仅允许"):
        safe_fetch("ftp://example.com/pub")


# ---- Phase 1A 增强:白名单 / 代理模式 / async -------------------------------

class FakeResp:
    def __init__(self, status_code=200, text="body", headers=None, url=""):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.url = url


class FakeClient:
    """httpx.Client 桩:routes[url] → FakeResp;记录构造参数。"""

    def __init__(self, routes):
        self.routes = routes
        self.init_kwargs = None
        self.get_urls = []

    def __call__(self, **kwargs):
        self.init_kwargs = kwargs
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        self.get_urls.append(url)
        resp = self.routes[url]
        if isinstance(resp, Exception):
            raise resp
        resp.url = url  # 模拟 httpx 行为: resp.url 为实际请求地址
        return resp


def test_allowlist_blocks_outside_domain():
    from orca.fetch import safe_fetch

    client = FakeClient({})  # 不应发起任何请求
    with pytest.raises(FetchBlocked, match="白名单"):
        safe_fetch("https://evil.example.com/x",
                   allowed_domains={"docs.python.org"},
                   client_factory=client)


def test_allowlist_checked_per_redirect_hop():
    from orca.fetch import safe_fetch

    client = FakeClient({
        "https://docs.python.org/a": FakeResp(
            302, headers={"location": "https://evil.example.com/x"}),
    })
    with pytest.raises(FetchBlocked, match="白名单"):
        safe_fetch("https://docs.python.org/a",
                   allowed_domains={"docs.python.org"},
                   client_factory=client)


def test_proxy_mode_skips_local_dns_but_keeps_other_checks():
    """代理模式下由代理方解析目标(§3.7):跳过本地 IP 校验,
    但 scheme / 白名单 / 跳数 / 大小限制照常执行。"""
    import orca.fetch as fetch_mod

    client = FakeClient({"https://docs.python.org/a": FakeResp(200, "正文")})
    calls = []
    orig = fetch_mod.resolve_and_check
    fetch_mod.resolve_and_check = lambda host: calls.append(host) or []

    try:
        r = fetch_mod.safe_fetch(
            "https://docs.python.org/a", allowed_domains={"docs.python.org"},
            proxy="http://127.0.0.1:7890", client_factory=client)
    finally:
        fetch_mod.resolve_and_check = orig

    assert calls == []           # 代理模式不做本地 DNS 校验
    assert r.body == "正文"
    assert client.init_kwargs["proxy"] == "http://127.0.0.1:7890"


def test_client_ignores_env_proxy_by_default():
    """默认直连:trust_env=False, 不读环境代理(Phase 0 实测行为)。"""
    from orca.fetch import safe_fetch

    client = FakeClient({"https://docs.python.org/a": FakeResp(200, "b")})
    safe_fetch("https://docs.python.org/a", client_factory=client)
    assert client.init_kwargs["trust_env"] is False
    assert "proxy" not in client.init_kwargs


def test_async_fetch_returns_body():
    import asyncio

    from orca.fetch import safe_fetch_async

    class FakeAsyncClient(FakeClient):
        async def get(self, url):
            return FakeClient.get(self, url)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    client = FakeAsyncClient({"https://docs.python.org/a": FakeResp(200, "异步正文")})
    r = asyncio.run(safe_fetch_async("https://docs.python.org/a",
                                     client_factory=client))
    assert r.body == "异步正文"
    assert client.init_kwargs["trust_env"] is False


def test_async_fetch_follows_redirects_with_checks():
    import asyncio

    from orca.fetch import safe_fetch_async

    class FakeAsyncClient(FakeClient):
        async def get(self, url):
            return FakeClient.get(self, url)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    client = FakeAsyncClient({
        "https://docs.python.org/a": FakeResp(
            302, headers={"location": "/b"}),
        "https://docs.python.org/b": FakeResp(200, "跳转后"),
    })
    r = asyncio.run(safe_fetch_async("https://docs.python.org/a",
                                     client_factory=client))
    assert r.body == "跳转后"
    assert r.final_url == "https://docs.python.org/b"
