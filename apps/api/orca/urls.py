"""URL 归一化:产出**规范形式**用于去重比较与证据标识。

规则:域名小写、路径保留大小写、剥 utm_* 与 fragment、去尾部斜杠、
http 按 https 归一(同一资源几乎必然同内容)。
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PREFIXES = ("utm_",)


def norm_url(url: str) -> str:
    parts = urlparse(url)
    if not parts.scheme or not parts.hostname:
        raise ValueError(f"无法解析的 URL: {url!r}")

    host = parts.hostname.lower()
    scheme = "https"  # http 按 https 归一, 用于比较
    path = parts.path.rstrip("/") or "/"

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith(_TRACKING_PREFIXES)]
    query = urlencode(kept)

    if path == "/" and not query:
        return urlunparse((scheme, host, "", "", "", ""))
    return urlunparse((scheme, host, path, "", query, ""))
