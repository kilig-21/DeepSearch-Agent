"""Phase 3 Python 中文文档适配器：全离线索引与回落路径测试。"""
from __future__ import annotations

import json
import zlib

import pytest

from orca.adapters import AdapterUnavailable, PythonZhDocsAdapter
from orca import db
from orca.budget import Budget
from orca.fetch import FetchResult
from orca import graph
from orca.persist import persist_task_results
from test_graph import ALLOWED, PLANNER_JSON, default_search_results, make_tools


def _inventory() -> bytes:
    payload = (
        "venv py:module 1 library/venv.html -\n"
        "asyncio.gather py:function 1 library/asyncio-task.html#gather -\n"
    ).encode()
    return (b"# Sphinx inventory version 2\n# Project: Python\n"
            b"# Version: 3.14.7\n# The remainder of this file is compressed\n"
            + zlib.compress(payload))


def _searchindex() -> bytes:
    value = {
        "docnames": ["library/venv", "library/asyncio-task"],
        "titles": ["venv — 创建虚拟环境", "asyncio 任务"],
        "terms": {"venv": [0], "虚拟": [0], "asyncio": [1]},
        "titleterms": {"虚拟": [0]},
    }
    return ("Search.setIndex(" + json.dumps(value, ensure_ascii=False) + ");").encode()


def _offline_fetcher(*, inventory: bytes | None = None,
                     searchindex: bytes | None = None):
    calls: list[str] = []
    routes = {
        "https://docs.python.org/zh-cn/3/objects.inv": inventory if inventory is not None else _inventory(),
        "https://docs.python.org/zh-cn/3/searchindex.js": searchindex if searchindex is not None else _searchindex(),
    }

    def fetch(url: str) -> FetchResult:
        calls.append(url)
        raw = routes.get(url)
        if raw is None:
            return FetchResult(url, 404, "", b"")
        return FetchResult(url, 200, raw.decode("utf-8", "ignore"), raw)

    return fetch, calls


def test_python_zh_adapter_uses_local_sphinx_indices_without_web_search():
    """正常路径只读两份离线索引，返回严格 /zh-cn/ 定向 URL 与可复现元数据。"""
    fetch, calls = _offline_fetcher()
    adapter = PythonZhDocsAdapter(fetch_index=fetch, min_interval_s=0)

    outcome = adapter.search("如何创建 venv 虚拟环境", limit=3)

    assert calls == [
        "https://docs.python.org/zh-cn/3/objects.inv",
        "https://docs.python.org/zh-cn/3/searchindex.js",
    ]
    assert outcome.results
    assert all(r.url.startswith("https://docs.python.org/zh-cn/")
               for r in outcome.results)
    assert any("library/venv.html" in r.url for r in outcome.results)
    assert outcome.metadata["inventory_version"] == "3.14.7"
    assert len(outcome.metadata["objects_inv_sha256"]) == 64
    assert len(outcome.metadata["searchindex_sha256"]) == 64


@pytest.mark.parametrize(
    ("inventory", "searchindex", "error"),
    [
        (b"not an inventory", None, "objects.inv"),
        (None, b"not javascript", "searchindex.js"),
    ],
)
def test_python_zh_adapter_rejects_missing_or_corrupt_indices(
    inventory, searchindex, error,
):
    """损坏/缺失索引在适配器层失败，不能产生伪造候选 URL。"""
    fetch, _calls = _offline_fetcher(inventory=inventory, searchindex=searchindex)
    adapter = PythonZhDocsAdapter(fetch_index=fetch, min_interval_s=0)

    with pytest.raises(AdapterUnavailable, match=error):
        adapter.search("venv")


def test_searcher_visible_fallback_to_pure_web_when_adapter_unavailable():
    """先让适配器真实被调用并失败，再断言才调用纯 Web，避免假覆盖。"""
    calls_to_index: list[str] = []

    def broken_fetch(url: str) -> FetchResult:
        calls_to_index.append(url)
        raise OSError("离线替身模拟 TLS 失败")

    tools, events, calls = make_tools([PLANNER_JSON],
                                      search_results=default_search_results())
    broken = PythonZhDocsAdapter(fetch_index=broken_fetch, min_interval_s=0)
    tools.source_adapter = broken
    state = {
        "topic": "Q", "planned_query": "venv", "next_queries": [],
        "round_no": 1, "seen_urls": [], "pending_links": [],
        "search_rounds": [], "stop_reason": None,
    }

    out = graph.make_searcher(tools)(state)

    assert calls_to_index == ["https://docs.python.org/zh-cn/3/objects.inv"]
    assert calls["search"] == ["venv"]
    warnings = [p for event, p in events if event == "warning"]
    assert any(p.get("stage") == "source_adapter"
               and p.get("fallback") == "pure_web" for p in warnings)
    assert "adapter" not in out["search_rounds"][0]
    assert out["search_rounds"][0]["credits_used"] == 1
    assert out["source_adapter_fallbacks"] == [{
        "round_no": 1, "query": "venv", "adapter": "python_zh_docs",
        "fallback": "pure_web", "reason": "索引拉取失败 https://docs.python.org/zh-cn/3/objects.inv: 离线替身模拟 TLS 失败",
    }]
    assert any(event == "search" and "adapter" not in payload
               for event, payload in events)


def test_adapter_index_metadata_is_persisted_with_report(tmp_path):
    """真实持久化路径保留索引版本/哈希，事后可复现实验而非只留在内存事件。"""
    fetch, _calls = _offline_fetcher()
    metadata = PythonZhDocsAdapter(fetch_index=fetch, min_interval_s=0).search("venv").metadata
    engine = db.make_engine(tmp_path / "orca.db")
    db.init_db(engine)
    task_id = db.create_task(engine, topic="venv")
    budget = Budget(total_llm_tokens=10_000, writer_reserve_tokens=1_000,
                    max_tavily_credits=16, max_pages=12, time_budget_s=480)
    state = {
        "evidence": [], "search_rounds": [{
            "round_no": 1, "query": "venv", "result_count": 1,
            "credits_used": 0, "adapter": metadata,
        }],
        "report_md": "# 离线测试报告", "citation_map": {},
        "stop_reason": "single_pass", "duration_s": 0.1,
    }

    report_id = persist_task_results(engine, task_id, state, budget,
                                     allowed_domains=ALLOWED, proxy=False)

    saved = db.get_report(engine, report_id)
    assert saved["config_json"]["source_adapter_indices"] == [metadata]
