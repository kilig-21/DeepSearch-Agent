"""探针 T3: 验证 Tavily 搜索(主)+ ddgs(备胎)。

运行: python scripts/probe_search.py  (项目根目录)
输出: 两者的延迟/结果数/示例; Tavily 消耗 1 credit(Basic)。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402

from orca.config import TAVILY_API_KEY, TAVILY_SEARCH_URL  # noqa: E402

QUERY = "Python 3.13 新特性 摘要"


def probe_tavily() -> None:
    print("=" * 60)
    print("Tavily Basic Search(计 1 credit)")
    t0 = time.perf_counter()
    resp = httpx.post(
        TAVILY_SEARCH_URL,
        headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
        json={"query": QUERY, "search_depth": "basic", "max_results": 5},
        timeout=30,
    )
    dt = time.perf_counter() - t0
    print(f"HTTP {resp.status_code}, 耗时 {dt:.2f}s")
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    print(f"结果数: {len(results)}, 服务端耗时 {data.get('response_time')}s")
    for r in results[:5]:
        print(f"  - [{r.get('score', 0):.2f}] {r['title'][:50]} | {r['url'][:80]}")


def probe_ddgs() -> None:
    print("=" * 60)
    print("ddgs(DuckDuckGo 备胎, 0 credits)")
    try:
        from ddgs import DDGS

        t0 = time.perf_counter()
        rows = list(DDGS().text(QUERY, max_results=5))
        dt = time.perf_counter() - t0
        print(f"结果数: {len(rows)}, 耗时 {dt:.2f}s")
        for r in rows[:5]:
            print(f"  - {r.get('title', '')[:50]} | {r.get('href', '')[:80]}")
    except Exception as e:  # noqa: BLE001
        print(f"ddgs 失败(预期内, 备胎不保证可用): {type(e).__name__}: {e}")


if __name__ == "__main__":
    probe_tavily()
    probe_ddgs()
