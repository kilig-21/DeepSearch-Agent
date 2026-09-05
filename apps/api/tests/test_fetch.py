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
