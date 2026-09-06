"""LLM 薄协议(计划书 §2.2:默认单模型 + 薄接口, 不做多厂商统一网关)。

- 定版模型(2026-09-05):日常 glm-5.3-flash / 高质量 glm-5.3
- glm-5.3 为推理型模型:思考段耗尽输出配额 → max_tokens 为必填且须给足
- usage 原样上报, 思考 token 计入预算分账(probe_results.md 定版变更)
- 重试 ≤2(§3.6), 仅对可重试错误(网络/429/5xx);单调用超时 180s(推理型校准)
- chat_stream(第四轮评审 P2):SSE 流式, 逐片段产出正文;
  usage 经 include_usage 在流末尾返回;流式不做重试(草稿可中断)
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from .config import (
    LLM_DAILY_MODEL,
    LLM_HIGH_QUALITY_MODEL,
    ZHIPU_API_KEY,
    ZHIPU_CHAT_URL,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2       # 每调用重试上限(§3.6)
# §3.6 原回填 30s 基于 4 系列(4~6s);glm-5.3 推理型思考段远超此值,
# Phase 1A 冒烟实测 30s ReadTimeout, 校准为 180s(计划书值将在验收后回填)
DEFAULT_TIMEOUT = 180.0

Tier = str  # "daily" | "high_quality"


@dataclass
class LLMResult:
    content: str
    usage: dict  # {"prompt_tokens", "completion_tokens", "total_tokens"}


class LLMError(Exception):
    """LLM 调用失败(重试耗尽或不可重试错误)。"""


PostFn = Callable[..., object]


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str = ZHIPU_API_KEY,
        url: str = ZHIPU_CHAT_URL,
        post: PostFn | None = None,
        timeout_s: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if post is not None:
            self._post = post
        else:
            import httpx

            self._post = lambda **kw: httpx.post(**kw)  # noqa: E731
        self._api_key = api_key
        self._url = url
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._sleep = sleep

    def _model_for(self, tier: Tier) -> str:
        if tier == "daily":
            return LLM_DAILY_MODEL
        if tier == "high_quality":
            return LLM_HIGH_QUALITY_MODEL
        raise ValueError(f"未知模型档位: {tier}")

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int,  # 必填:5.3 推理模型思考段占用输出配额, 禁止静默默认小值
        tier: Tier = "daily",
        temperature: float = 0.2,
        reasoning_effort: str | None = None,
    ) -> LLMResult:
        payload = {
            "model": self._model_for(tier),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # 思考控制(实测 2026-09-05):5.3 系列始终思考, thinking.type 不接受
        # disabled/low/high/max(智谱 1210 错误);顶层 reasoning_effort="low"
        # 是唯一实测将思考压到 0 的方式(OpenAI 风格兼容参数)。
        # None = 不传字段 = 模型默认思考(writer 推理任务保留)。
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._post(url=self._url, headers=headers, json=payload,
                                  timeout=self._timeout_s)
            except Exception as e:  # noqa: BLE001 — 网络/传输错误统一包装为可重试
                last_err = LLMError(f"网络错误: {type(e).__name__}: {e}")
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    return LLMResult(content=(msg.get("content") or "").strip(),
                                     usage=dict(data.get("usage", {})))
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_err = LLMError(f"HTTP {resp.status_code}: 可重试")
                else:
                    raise LLMError(f"HTTP {resp.status_code}: 不可重试: "
                                   f"{str(resp.json())[:200]}")
            if attempt < self._max_retries:
                self._sleep(0.5 * (2**attempt))  # 指数退避
        raise LLMError(f"重试耗尽({self._max_retries + 1} 次尝试): {last_err}")

    def chat_stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        tier: Tier = "daily",
        temperature: float = 0.2,
        reasoning_effort: str | None = None,
    ) -> tuple[Iterator[str], dict]:
        """流式调用:返回 (正文片段迭代器, usage 容器)。

        片段逐个产出, 调用方可逐片段 emit(取消检查点在 emit 侧);
        流耗尽后 usage 容器被填充(智谱 OpenAI 风格 include_usage)。
        流式不做重试:草稿可被取消中断, 失败走 execution_error 兜底。
        """
        payload = {
            "model": self._model_for(tier),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        headers = {"Authorization": f"Bearer {self._api_key}"}
        usage_box: dict = {}

        def gen() -> Iterator[str]:
            import httpx

            with httpx.stream("POST", self._url, headers=headers,
                              json=payload, timeout=self._timeout_s) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")
                    raise LLMError(f"HTTP {resp.status_code}: {body[:200]}")
                seen_done = False
                emitted = 0
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        seen_done = True
                        break
                    obj = json.loads(data)
                    if obj.get("error"):
                        # 上游错误帧(第五轮评审 R4):不得当成功静默跳过,
                        # 显式失败交由 TaskManager 转 task_failed
                        raise LLMError(
                            f"流式上游错误: {str(obj['error'])[:200]}")
                    if obj.get("usage"):
                        usage_box.update(obj["usage"])
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        emitted += 1
                        yield delta
                if not seen_done:
                    # 正常走完但未收到 [DONE](第五轮评审 R4):半截流当
                    # 成功会落半截报告, 显式失败
                    raise LLMError("流式响应提前终止: 未收到 [DONE]")
                if emitted == 0:
                    # 有 [DONE] 但 0 正文片段(在线实测 GLM 偶发空响应):
                    # 静默返回会让空报告以 completed 落库, 显式失败
                    raise LLMError("流式响应空内容: 收到 [DONE] 但无正文片段")
            if not usage_box:
                # usage 缺失显式处理(第五轮评审 R4):此时正文已完整交付,
                # 报错会浪费已完成计算 → 告警并按 0 记账(低估但可审计),
                # 不静默
                logger.warning("流式响应未返回 usage, 按 0 token 记账")
                usage_box.update({"prompt_tokens": 0, "completion_tokens": 0,
                                  "total_tokens": 0})

        return gen(), usage_box
