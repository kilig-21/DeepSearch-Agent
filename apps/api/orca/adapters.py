"""来源适配器：Python 官方中文文档（Phase 3）。

检索路径严格为版本化 ``objects.inv`` + 本地 ``searchindex.js``，再定向抓取；
本模块不导入、更不调用 Tavily 或其他通用 Web 搜索。索引下载统一经过
``safe_fetch``，继承其 scheme、白名单、DNS/重定向与响应大小防线。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from .fetch import FetchResult, safe_fetch
from .search import SearchResult, dedup

PYTHON_ZH_ROOT = "https://docs.python.org/zh-cn/3/"
PYTHON_ZH_HOST = "docs.python.org"
_CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]+")
_TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


class AdapterUnavailable(Exception):
    """索引不能安全使用或本地索引无匹配；调用者应可见地回退纯 Web。"""


@dataclass(frozen=True)
class AdapterSearchResult:
    results: list[SearchResult]
    metadata: dict[str, str]


def _query_tokens(query: str) -> set[str]:
    """轻量本地分词：ASCII 符号和中文连续片段/二元片段均可命中索引。"""
    q = query.lower()
    tokens = {t for t in _TOKEN_RE.findall(q) if len(t) >= 2}
    for run in _CJK_RUN_RE.findall(q):
        if len(run) >= 2:
            tokens.add(run)
            tokens.update(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def _inventory_entries(raw: bytes) -> tuple[str, str, dict[str, str]]:
    """解析 Sphinx inventory v2；只保留对象名到相对 URI 的确定映射。"""
    header_end = -1
    for _ in range(4):
        header_end = raw.find(b"\n", header_end + 1)
        if header_end == -1:
            raise AdapterUnavailable("objects.inv 缺失或不是 Sphinx inventory v2")
    header_lines = raw[:header_end].split(b"\n")
    if not header_lines[0].startswith(b"# Sphinx inventory version 2"):
        raise AdapterUnavailable("objects.inv 缺失或不是 Sphinx inventory v2")
    try:
        project = header_lines[1].decode("utf-8").split(":", 1)[1].strip()
        version = header_lines[2].decode("utf-8").split(":", 1)[1].strip()
        payload = zlib.decompress(raw[header_end + 1:]).decode("utf-8")
    except (UnicodeDecodeError, ValueError, zlib.error) as e:
        raise AdapterUnavailable(f"objects.inv 损坏: {type(e).__name__}") from e

    entries: dict[str, str] = {}
    for line in payload.splitlines():
        parts = line.split(None, 4)
        if len(parts) != 5:
            continue
        name, _role, _priority, uri, _display = parts
        entries.setdefault(name.lower(), uri)
    if not entries:
        raise AdapterUnavailable("objects.inv 不含可用对象条目")
    return project, version, entries


def _search_index(raw: bytes) -> dict:
    """解析 Sphinx 生成的 ``Search.setIndex({...})`` 静态索引。"""
    try:
        text = raw.decode("utf-8")
        start = text.index("Search.setIndex(") + len("Search.setIndex(")
        end = text.rindex(")")
        value = json.loads(text[start:end].strip().rstrip(";"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as e:
        raise AdapterUnavailable(f"searchindex.js 缺失或损坏: {type(e).__name__}") from e
    if not isinstance(value, dict) or not isinstance(value.get("docnames"), list):
        raise AdapterUnavailable("searchindex.js 缺少 docnames")
    return value


def _doc_ids(value: object) -> list[int]:
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, int)]
    return []


class PythonZhDocsAdapter:
    """只检索 docs.python.org/zh-cn 的 Sphinx 静态索引。

    ``fetch_index`` 是依赖注入点，单测传入离线替身；默认实现通过 safe_fetch
    取原始字节，且强制 host 与 ``/zh-cn/`` 前缀，防止索引重定向放宽边界。
    """

    def __init__(self, *, root: str = PYTHON_ZH_ROOT,
                 fetch_index: Callable[[str], FetchResult] | None = None,
                 min_interval_s: float = 0.2,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        normalized = root.rstrip("/") + "/"
        parsed = urlparse(normalized)
        if parsed.scheme != "https" or parsed.hostname != PYTHON_ZH_HOST or not parsed.path.startswith("/zh-cn/"):
            raise ValueError("Python 中文文档适配器只允许 https://docs.python.org/zh-cn/ 路径")
        self.root = normalized
        if min_interval_s < 0:
            raise ValueError("索引限速间隔不能为负数")
        self._fetch_index = fetch_index or self._safe_fetch_index
        self._min_interval_s = min_interval_s  # 默认至多 5 次索引请求/秒
        self._clock = clock
        self._sleep = sleep
        self._last_fetch_at: float | None = None
        self._loaded: tuple[dict[str, str], dict, dict[str, str]] | None = None

    def _safe_fetch_index(self, url: str) -> FetchResult:
        return safe_fetch(url, allowed_domains={PYTHON_ZH_HOST})

    def _read_index(self, name: str) -> bytes:
        url = urljoin(self.root, name)
        if self._last_fetch_at is not None:
            wait = self._min_interval_s - (self._clock() - self._last_fetch_at)
            if wait > 0:
                self._sleep(wait)
        self._last_fetch_at = self._clock()
        try:
            result = self._fetch_index(url)
        except Exception as e:  # 传输/TLS/DNS 等均必须走显式 Web 回落
            raise AdapterUnavailable(f"索引拉取失败 {url}: {e}") from e
        if result.status_code != 200 or result.body_bytes is None:
            raise AdapterUnavailable(f"索引拉取失败 {url}: HTTP {result.status_code}")
        return result.body_bytes

    def _load(self) -> tuple[dict[str, str], dict, dict[str, str]]:
        if self._loaded is not None:
            return self._loaded
        inv_raw = self._read_index("objects.inv")
        index_raw = self._read_index("searchindex.js")
        project, version, inventory = _inventory_entries(inv_raw)
        search_index = _search_index(index_raw)
        metadata = {
            "adapter": "python_zh_docs",
            "index_root": self.root,
            "inventory_project": project,
            "inventory_version": version,
            "objects_inv_sha256": hashlib.sha256(inv_raw).hexdigest(),
            "searchindex_sha256": hashlib.sha256(index_raw).hexdigest(),
        }
        self._loaded = inventory, search_index, metadata
        return self._loaded

    def _url(self, relative: str, *, object_name: str | None = None) -> str | None:
        rel = relative.replace("$", object_name or "")
        url = urljoin(self.root, rel)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != PYTHON_ZH_HOST or not parsed.path.startswith("/zh-cn/"):
            return None
        return url

    def search(self, query: str, *, limit: int = 8) -> AdapterSearchResult:
        inventory, index, metadata = self._load()
        tokens = _query_tokens(query)
        if not tokens:
            raise AdapterUnavailable("本地索引无可检索查询词")

        scored: dict[str, tuple[float, str]] = {}
        for name, relative in inventory.items():
            score = sum(8.0 for token in tokens if token in name)
            if score and (url := self._url(relative, object_name=name)):
                scored[url] = max(scored.get(url, (0.0, "")), (score, name))

        docnames = index.get("docnames", [])
        titles = index.get("titles", [])
        terms = index.get("terms", {})
        titleterms = index.get("titleterms", {})
        doc_scores: dict[int, float] = {}
        if isinstance(terms, dict) and isinstance(titleterms, dict):
            for token in tokens:
                for term, ids in terms.items():
                    if token in str(term).lower():
                        for doc_id in _doc_ids(ids):
                            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + 2.0
                for term, ids in titleterms.items():
                    if token in str(term).lower():
                        for doc_id in _doc_ids(ids):
                            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + 4.0
        for doc_id, score in doc_scores.items():
            if not 0 <= doc_id < len(docnames):
                continue
            name = str(docnames[doc_id])
            title = str(titles[doc_id]) if doc_id < len(titles) else name
            if url := self._url(name if name.endswith(".html") else name + ".html"):
                old_score = scored.get(url, (0.0, title))[0]
                scored[url] = (max(old_score, score), title)

        results = [SearchResult(url=url, title=title,
                                snippet="Python 官方中文文档本地索引命中",
                                score=score)
                   for url, (score, title) in scored.items()]
        results.sort(key=lambda item: (-item.score, item.url))
        results = dedup(results)[:limit]
        if not results:
            raise AdapterUnavailable("本地索引无匹配条目")
        return AdapterSearchResult(results=results, metadata=metadata)
