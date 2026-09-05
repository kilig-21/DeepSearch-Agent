"""safe_fetch: 带基础 SSRF 防护的网页抓取(Phase 0 雏形)。

计划书 §3.7 要求的检查点(雏形覆盖 * 标记项,Phase 1A 完善):
* 仅 http/https
* 拒绝私网/回环/链路本地/保留段/云元数据地址(覆盖 IPv4-mapped IPv6)
* 每次重定向重新解析并校验(缓解 DNS 检查与连接间的 TOCTOU;
  TODO Phase 1A: 连接复用已验证地址, 彻底消除二次解析)
* 最大重定向跳数 / 单调用超时 / 响应体大小上限
TODO Phase 1A: 明确代理模式下由哪一方解析目标并按同一规则校验
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 3          # 最大重定向跳数(Phase 0 初始值, 计划书 §3.6)
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
    """解析 host 的全部 A/AAAA 记录, 任一落在禁用网段即拒绝。

    返回解析到的公网 IP 列表(Phase 1A 将用返回值直连, 消除二次解析)。
    """
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


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    body: str  # 已按 UTF-8 解码(忽略错误)


def safe_fetch(
    url: str,
    *,
    max_redirects: int = MAX_REDIRECTS,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_BODY_BYTES,
) -> FetchResult:
    """逐跳校验并抓取网页正文(不解压限制见 max_bytes)。"""
    current = url
    for _hop in range(max_redirects + 1):
        parts = urlparse(current)
        if parts.scheme not in ALLOWED_SCHEMES:
            raise FetchBlocked(f"仅允许 http/https, 得到: {parts.scheme or '(空)'}")
        if not parts.hostname:
            raise FetchBlocked(f"URL 缺少主机名: {current}")
        resolve_and_check(parts.hostname)

        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.get(current)
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("location")
            if not location:
                raise FetchBlocked(f"重定向缺失 Location: {current}")
            current = urljoin(current, location)
            continue
        body = resp.text[:max_bytes]
        return FetchResult(final_url=str(resp.url), status_code=resp.status_code, body=body)
    raise FetchBlocked(f"超过最大重定向跳数({max_redirects}): {url}")
