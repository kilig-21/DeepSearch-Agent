"""Phase 0 验收: 命令行跑通「搜索 → 抓取 → 摘要」全链路。

运行: python scripts/probe_pipeline.py "Python 3.13 有什么新特性?"  (项目根目录)
记录各步耗时与成本(Tavily 1 credit + GLM tokens), 结果回填 PLAN.md §3.6/§8。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402
import trafilatura  # noqa: E402

from orca.config import (  # noqa: E402
    LLM_DAILY_MODEL,
    TAVILY_API_KEY,
    TAVILY_SEARCH_URL,
    ZHIPU_API_KEY,
    ZHIPU_CHAT_URL,
)
from orca.fetch import FetchBlocked, safe_fetch  # noqa: E402

# Phase 0 允许抓取的已核对来源集合(docs/SOURCES.md)
ALLOWED_DOMAINS = {"zh.wikipedia.org", "docs.python.org", "developer.mozilla.org"}


def main(topic: str) -> None:
    total_tokens = 0

    # 1) 搜索(Tavily Basic, 1 credit)
    t0 = time.perf_counter()
    resp = httpx.post(
        TAVILY_SEARCH_URL,
        headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
        json={"query": topic, "search_depth": "basic", "max_results": 5},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    print(f"[1 搜索] {len(results)} 条, {time.perf_counter() - t0:.2f}s, 1 credit")

    # 2) 选第一个属于已核对来源集合的结果并抓取(SSRF 防护)
    picked = next((r for r in results
                   if any(d in r["url"] for d in ALLOWED_DOMAINS)), None)
    if picked is None:
        print("[2 抓取] 搜索结果不在已核对来源集合内 → 按计划只列为链接, 不抓正文")
        for r in results:
            print(f"  链接候选: {r['url']}")
        return
    t0 = time.perf_counter()
    try:
        html = safe_fetch(picked["url"]).body
    except FetchBlocked as e:
        print(f"[2 抓取] 被安全策略拒绝: {e}")
        return
    text = trafilatura.extract(html, include_comments=False) or ""
    print(f"[2 抓取] {picked['url'][:70]}")
    print(f"         提取 {len(text)} 字符, {time.perf_counter() - t0:.2f}s")

    # 3) 摘要(GLM 日常模型)
    t0 = time.perf_counter()
    resp = httpx.post(
        ZHIPU_CHAT_URL,
        headers={"Authorization": f"Bearer {ZHIPU_API_KEY}"},
        json={
            "model": LLM_DAILY_MODEL,
            "messages": [{
                "role": "user",
                "content": f"基于以下资料,用 3 句话中文回答「{topic}」。"
                           f"资料中没有的内容不要编造:\n\n{text[:6000]}",
            }],
            "temperature": 0.2,
            "max_tokens": 400,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    print(f"[3 摘要] {LLM_DAILY_MODEL}, {time.perf_counter() - t0:.2f}s, "
          f"{total_tokens} tokens")
    print("-" * 70)
    print(data["choices"][0]["message"]["content"].strip())
    print("-" * 70)
    print(f"来源: {picked['url']}")
    print(f"总成本: Tavily 1 credit + GLM {total_tokens} tokens({LLM_DAILY_MODEL})")


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "Python 3.13 有什么新特性?"
    main(topic)
