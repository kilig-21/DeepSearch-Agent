"""探针 T5: GLM 模型对比(延迟/token/质量)→ 模型定版依据。

运行: python scripts/probe_llm.py  (项目根目录)
同一摘要任务跑三个候选模型, 输出耗时与 usage; 单价回填见 PLAN.md §8。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402

from orca.config import LLM_PROBE_MODELS, ZHIPU_API_KEY, ZHIPU_CHAT_URL  # noqa: E402

SAMPLE = (
    "2026年以来,多家厂商加速大模型端侧部署。Qwen3 系列推出 0.6B~4B 的端侧版本,"
    "官方数据显示在主流手机 SoC 上推理速度可达每秒 20 tokens 以上。GLM 团队发布"
    "面向手机的轻量模型,强调INT4量化后内存占用低于 2GB。行业分析认为,端侧部署的"
    "三大挑战是内存墙、功耗和长文本支持。多家手机厂商已在新机型中内置本地 AI 助手,"
    "支持离线摘要与翻译。不过,端侧模型在复杂推理任务上仍明显落后于云端旗舰模型,"
    "混合云-端架构成为当前主流方案。"
)

PROMPT = f"请把下面的资料压缩成 3 句话的中文摘要,不要编造资料外的内容:\n\n{SAMPLE}"


def probe(model: str) -> None:
    t0 = time.perf_counter()
    try:
        resp = httpx.post(
            ZHIPU_CHAT_URL,
            headers={"Authorization": f"Bearer {ZHIPU_API_KEY}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": PROMPT}],
                "temperature": 0.2,
                "max_tokens": 300,
            },
            timeout=60,
        )
        dt = time.perf_counter() - t0
        if resp.status_code != 200:
            print(f"[{model:<15}] HTTP {resp.status_code}: {resp.text[:150]}")
            return
        data = resp.json()
        usage = data.get("usage", {})
        text = data["choices"][0]["message"]["content"].strip()
        print(f"[{model:<15}] {dt:5.2f}s | prompt={usage.get('prompt_tokens')}"
              f" completion={usage.get('completion_tokens')} tokens")
        print(f"{'':<17}输出: {text[:100]}...")
    except Exception as e:  # noqa: BLE001
        print(f"[{model:<15}] 异常: {type(e).__name__}: {e}")


if __name__ == "__main__":
    print(f"GLM 探针, {len(SAMPLE)} 字样本, 任务: 3 句话摘要")
    for m in LLM_PROBE_MODELS:
        probe(m)
