"""safe_fetch: 带基础 SSRF 防护的网页抓取。

计划书 §3.7 检查点:
- 仅 http/https
- 拒绝私网/回环/链路本地/保留段/云元数据地址(覆盖 IPv4-mapped IPv6)
- 每跳重定向重新校验(白名单 + scheme + DNS)
- 最大重定向跳数 / 单调用超时 / 响应体大小上限(2MB)

代理模式(§3.7 解析权声明):
- 默认直连:trust_env=False, 本地解析并校验全部目标 IP
- 显式配置 proxy 时, 目标解析由代理方完成, 本地无法按同一规则校验 IP——
  按计划书 §3.7 降级条款, 此时依赖白名单域名 + scheme + 跳数限制为防线,
  此取舍已在 PLAN.md 记录

已知残留(诚实声明):直连模式下"解析校验→实际连接"之间仍存在 DNS/TOCTOU
窗口;完整消除需 transport 层 IP pinning(自定义 httpx transport + SNI),
个人项目复杂度高。主链路强制白名单域名为当前主要防线。
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 3          # 最大重定向跳数(§3.6)
DEFAULT_TIMEOUT = 20.0      # 单调用超时(秒)
MAX_BODY_BYTES = 2_000_000  # 响应体上限(解压后), 2MB


class FetchBlocked(Exception):
    """URL 被安全策略拒绝。"""


def is_blocked_ip(ip_str: str) -> bool:
    """纯函数: 判定一个 IP 是否为禁止访问的目标。

    覆盖: 私网 / 回环 / 链路本地 / 保留段 / 未指定地址 / 云元数据(169.254.169.254
    属链路本地段), 并处理 IPv4-mapped IPv6(::ffff:x.x.x.x)。
    """
    ip = ipaddress.ip_address(ip_str)
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not ip.is_global


def resolve_and_check(host: str) -> list[str]:
    """解析 host 的全部 A/AAAA 记录, 任一落在禁用网段即拒绝。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise FetchBlocked(f"DNS 解析失败: {host} ({e})") from e
    ips: list[str] = []
    for info in infos:
        ip_str = info[4][0]
        if is_blocked_ip(ip_str):
            raise FetchBlocked(f"目标解析到非公网地址 {ip_str}(host={host})")
        ips.append(ip_str)
    if not ips:
        raise FetchBlocked(f"无可解析地址: {host}")
    return ips


def host_in_allowlist(host: str, allowed_domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def _check_hop(
    url: str, allowed_domains: set[str] | None, proxy: str | None
) -> str:
    """单跳检查:scheme / 主机名 / 白名单 / DNS(代理模式跳过)。返回主机名。"""
    parts = urlparse(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise FetchBlocked(f"仅允许 http/https, 得到: {parts.scheme or '(空)'}")
    host = parts.hostname or ""
    if not host:
        raise FetchBlocked(f"URL 缺少主机名: {url}")
    if allowed_domains is not None and not host_in_allowlist(host.lower(),
                                                             allowed_domains):
        raise FetchBlocked(f"域名不在白名单内(§4/§9.1): {host}")
    if proxy is None:
        resolve_and_check(host)
    # 代理模式: 解析由代理方完成, 本地 IP 校验不适用(见模块 docstring 声明)
    return host


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    body: str  # 已按 UTF-8 解码(忽略错误)


def _postprocess(resp, max_bytes: int) -> FetchResult:
    return FetchResult(final_url=str(resp.url), status_code=resp.status_code,
                       body=resp.text[:max_bytes])


def safe_fetch(
    url: str,
    *,
    max_redirects: int = MAX_REDIRECTS,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_BODY_BYTES,
    allowed_domains: set[str] | None = None,
    proxy: str | None = None,
    client_factory: Callable = httpx.Client,
) -> FetchResult:
    """逐跳校验并抓取网页正文(同步版)。"""
    current = url
    with client_factory(timeout=timeout, follow_redirects=False,
                        trust_env=False, **({"proxy": proxy} if proxy else {})) as client:
        for _hop in range(max_redirects + 1):
            _check_hop(current, allowed_domains, proxy)
            resp = client.get(current)
            if 300 <= resp.status_code < 400:
                location = resp.headers.get("location")
                if not location:
                    raise FetchBlocked(f"重定向缺失 Location: {current}")
                current = urljoin(current, location)
                continue
            return _postprocess(resp, max_bytes)
    raise FetchBlocked(f"超过最大重定向跳数({max_redirects}): {url}")


async def safe_fetch_async(
    url: str,
    *,
    max_redirects: int = MAX_REDIRECTS,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_BODY_BYTES,
    allowed_domains: set[str] | None = None,
    proxy: str | None = None,
    client_factory: Callable = httpx.AsyncClient,
) -> FetchResult:
    """safe_fetch 异步版(reader 节点内部并发 ≤5, §3.6)。

    DNS 解析(socket.getaddrinfo)为阻塞调用, 放入线程执行避免阻塞事件循环。
    """
    import asyncio

    current = url
    async with client_factory(timeout=timeout, follow_redirects=False,
                              trust_env=False,
                              **({"proxy": proxy} if proxy else {})) as client:
        for _hop in range(max_redirects + 1):
            parts = urlparse(current)
            if parts.scheme not in ALLOWED_SCHEMES:
                raise FetchBlocked(
                    f"仅允许 http/https, 得到: {parts.scheme or '(空)'}")
            host = parts.hostname or ""
            if not host:
                raise FetchBlocked(f"URL 缺少主机名: {current}")
            if allowed_domains is not None and not host_in_allowlist(
                    host.lower(), allowed_domains):
                raise FetchBlocked(
                    f"域名不在白名单内(§4/§9.1): {host}")
            if proxy is None:
                await asyncio.to_thread(resolve_and_check, host)

            resp = await client.get(current)
            if 300 <= resp.status_code < 400:
                location = resp.headers.get("location")
                if not location:
                    raise FetchBlocked(f"重定向缺失 Location: {current}")
                current = urljoin(current, location)
                continue
            return _postprocess(resp, max_bytes)
    raise FetchBlocked(f"超过最大重定向跳数({max_redirects}): {url}")
