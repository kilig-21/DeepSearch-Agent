"""探针 T5(2026-09-12 DeepSeek 重校准): 模型延迟/token 结构与思考控制。

运行: apps/api/.venv/Scripts/python.exe scripts/probe_llm.py

换 DeepSeek 后原始 glm 时代的回填值(config.py 的 budget/timeout、
graph.py 的 _WRITER_MAX_TOKENS、budget.py 的 MIN_USABLE_OUTPUT)需重新
校准。本探针回答三个问题, 结果回填 PLAN.md §3.6/§8 与 config.py:

  A 两个档位(flash/pro)的延迟与 token 结构 —— 定 DEFAULT_TIMEOUT
  B reasoning_effort="low" 是否**真的生效** —— 同 prompt 传/不传对照
    (glm 时代实测:传 low 可把思考 token 压到 0;DeepSeek 是否吃这个参数
     决定 planner/reader/reflector 的"压制思考省配额"前提是否成立)
  C max_tokens 收紧到 100 时正文是否被思考吃穿 —— 定 MIN_USABLE_OUTPUT
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402

from orca.config import (  # noqa: E402
    DEEPSEEK_API_KEY,
    DEEPSEEK_CHAT_URL,
    LLM_DAILY_MODEL,
    LLM_HIGH_QUALITY_MODEL,
)

SAMPLE = (
    "2026年以来,多家厂商加速大模型端侧部署。Qwen3 系列推出 0.6B~4B 的端侧版本,"
    "官方数据显示在主流手机 SoC 上推理速度可达每秒 20 tokens 以上。GLM 团队发布"
    "面向手机的轻量模型,强调INT4量化后内存占用低于 2GB。行业分析认为,端侧部署的"
    "三大挑战是内存墙、功耗和长文本支持。多家手机厂商已在新机型中内置本地 AI 助手,"
    "支持离线摘要与翻译。不过,端侧模型在复杂推理任务上仍明显落后于云端旗舰模型,"
    "混合云-端架构成为当前主流方案。"
)

PROMPT = f"请把下面的资料压缩成 3 句话的中文摘要,不要编造资料外的内容:\n\n{SAMPLE}"

# 硬性思考任务(prompt 要求先推理), 用于 B 节放大 reasoning_effort 的差异
REASONING_PROMPT = (
    "一个水池有甲、乙两根进水管。单开甲管 6 小时注满,单开乙管 4 小时注满。"
    "两管同时开,但甲管每注水 1 小时需停 0.5 小时(停时乙管继续)。"
    "问:注满水池共需多少小时?请先逐步推理再给出结论。"
)


def call(model: str, prompt: str, *, max_tokens: int,
         reasoning_effort: str | None = None) -> dict:
    """单次调用, 返回 {dt, usage, content, finish_reason} 或 {error}。"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    t0 = time.perf_counter()
    try:
        resp = httpx.post(DEEPSEEK_CHAT_URL,
                          headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                          json=payload, timeout=180)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}",
                "dt": time.perf_counter() - t0}
    dt = time.perf_counter() - t0
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "dt": dt}
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    return {
        "dt": dt,
        "usage": dict(data.get("usage") or {}),
        "content": (choice.get("message") or {}).get("content") or "",
        "finish_reason": choice.get("finish_reason"),
    }


def _usage_brief(usage: dict) -> str:
    """usage 关键字段;DeepSeek 若给出思考 token 分项则一并显示。"""
    parts = [f"prompt={usage.get('prompt_tokens')}",
             f"completion={usage.get('completion_tokens')}",
             f"total={usage.get('total_tokens')}"]
    details = usage.get("completion_tokens_details") or {}
    if details:
        parts.append(f"details={json.dumps(details, ensure_ascii=False)}")
    return " ".join(parts)


def section_a() -> None:
    print("\n===== A 模型基线(max_tokens=400, 摘要任务)=====")
    for model in (LLM_DAILY_MODEL, LLM_HIGH_QUALITY_MODEL):
        r = call(model, PROMPT, max_tokens=400)
        if "error" in r:
            print(f"[{model}] 失败: {r['error']} ({r['dt']:.2f}s)")
            continue
        print(f"[{model}] {r['dt']:.2f}s | {_usage_brief(r['usage'])} | "
              f"finish={r['finish_reason']}")
        print(f"    输出: {r['content'][:120]}...")


def section_b() -> None:
    print("\n===== B reasoning_effort 是否生效(同 prompt 对照, max_tokens=1200)=====")
    print("判据: 若 completion/total tokens 与耗时显著不同 → 参数被上游采纳;")
    print("      若两者一致 → 参数被忽略(glm 时代'压制思考省配额'的前提不成立)")
    for label, effort in (("不传(None)", None), ('传 "low"', "low")):
        r = call(LLM_DAILY_MODEL, REASONING_PROMPT, max_tokens=1200,
                 reasoning_effort=effort)
        if "error" in r:
            print(f"[{label}] 失败: {r['error']} ({r['dt']:.2f}s)")
            continue
        print(f"[{label}] {r['dt']:.2f}s | {_usage_brief(r['usage'])} | "
              f"finish={r['finish_reason']}")
        print(f"    输出: {r['content'][:120]}...")


def section_c() -> None:
    print("\n===== C 小 max_tokens 行为(max_tokens=100)=====")
    print("判据: content 为空 / finish=length → 输出配额被思考吃穿, "
          "MIN_USABLE_OUTPUT 门槛需相应调整")
    r = call(LLM_DAILY_MODEL, PROMPT, max_tokens=100)
    if "error" in r:
        print(f"失败: {r['error']} ({r['dt']:.2f}s)")
        return
    print(f"[{LLM_DAILY_MODEL}] {r['dt']:.2f}s | {_usage_brief(r['usage'])} | "
          f"finish={r['finish_reason']}")
    print(f"    content 长度={len(r['content'])} 字符 | 输出: {r['content'][:120]}...")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    print(f"DeepSeek 探针, {len(SAMPLE)} 字样本;端点 {DEEPSEEK_CHAT_URL}")
    print(f"档位: daily={LLM_DAILY_MODEL} / high_quality={LLM_HIGH_QUALITY_MODEL}")
    section_a()
    section_b()
    section_c()
    print("\n完成。将上述数值回填 config.py / PLAN.md §3.6 / §8。")
