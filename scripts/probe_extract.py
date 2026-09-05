"""探针 T4: 正文提取链对比(Defuddle CLI vs trafilatura)。

运行: python scripts/probe_extract.py  (项目根目录)
提取输入统一经 safe_fetch(SSRF 防护雏形)获取 HTML。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import trafilatura  # noqa: E402

from orca.fetch import safe_fetch  # noqa: E402

URLS = [
    "https://zh.wikipedia.org/wiki/Python",
    "https://docs.python.org/3/whatsnew/3.13.html",
    "https://developer.mozilla.org/zh-CN/docs/Web/JavaScript",
]


def via_defuddle(url: str) -> tuple[str, float]:
    exe = shutil.which("defuddle")
    if not exe:
        return "(defuddle 未找到)", 0.0
    t0 = time.perf_counter()
    proc = subprocess.run(
        [exe, "parse", url, "--md"], capture_output=True, timeout=60, shell=False,
        encoding="utf-8", errors="replace",  # Windows 默认 GBK 会炸 UTF-8 输出
    )
    dt = time.perf_counter() - t0
    return (proc.stdout.strip() if proc.returncode == 0 else f"(失败 rc={proc.returncode}: {proc.stderr[:120]})", dt)


def via_trafilatura(url: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    html = safe_fetch(url).body  # 统一走 SSRF 防护雏形
    text = trafilatura.extract(html, include_comments=False) or "(提取为空)"
    return text.strip(), time.perf_counter() - t0


if __name__ == "__main__":
    for url in URLS:
        print("=" * 70)
        print(url)
        for name, fn in [("defuddle", via_defuddle), ("trafilatura", via_trafilatura)]:
            try:
                text, dt = fn(url)
                head = text[:120].replace("\n", " ")
                print(f"[{name:>11}] {len(text):>7} 字符 | {dt:5.2f}s | {head}")
            except Exception as e:  # noqa: BLE001
                print(f"[{name:>11}] 异常: {type(e).__name__}: {e}")
