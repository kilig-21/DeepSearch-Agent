"""LLM 薄协议(计划书 §2.2:默认单模型 + 薄接口, 不做多厂商统一网关)。

- 定版模型(2026-09-05):日常 glm-5.3-flash / 高质量 glm-5.3
- glm-5.3 为推理型模型:思考段耗尽输出配额 → max_tokens 为必填且须给足
- usage 原样上报, 思考 token 计入预算分账(probe_results.md 定版变更)
- 重试 ≤2(§3.6), 仅对可重试错误(网络/429/5xx);单调用超时 30s
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .config import (
    LLM_DAILY_MODEL,
    LLM_HIGH_QUALITY_MODEL,
    ZHIPU_API_KEY,
    ZHIPU_CHAT_URL,
)

MAX_RETRIES = 2       # 每调用重试上限(§3.6)
DEFAULT_TIMEOUT = 30.0

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
    ) -> LLMResult:
        payload = {
            "model": self._model_for(tier),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
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
