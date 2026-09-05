"""预算账本(计划书 §3.6 两级规则)。

分账:LLM tokens / Tavily credits / Jina tokens 分别计账。
计账范围:planner、reader、reflector、writer、引用修订——全部入账。

两级规则:
- 研究额度 = 总 LLM 额度 - writer 预留;耗尽 → budget_exhausted, 用已有证据走 writer
- 总额度/总时限耗尽 → 不再调用任何模型 → total_budget_exhausted / timeout
- writer 预留每任务建立一次, 各调用原子预占, 完成后按实际 usage 结算
"""
from __future__ import annotations

import time


class ReserveError(RuntimeError):
    """writer 预留重复建立。"""


class Budget:
    def __init__(
        self,
        *,
        total_llm_tokens: int,
        writer_reserve_tokens: int,
        max_tavily_credits: int,
        max_pages: int,
        time_budget_s: float,
        max_jina_tokens: int = 0,  # 默认关闭(§3.6);>0 时启用并计账
        clock=time.monotonic,
    ) -> None:
        if writer_reserve_tokens > total_llm_tokens:
            raise ValueError("writer 预留不得超过总额度")
        self.total_llm_tokens = total_llm_tokens
        self.writer_reserve_tokens = writer_reserve_tokens
        self.max_tavily_credits = max_tavily_credits
        self.max_jina_tokens = max_jina_tokens
        self.max_pages = max_pages
        self.time_budget_s = time_budget_s
        self._clock = clock
        self._started_at = clock()

        self.used_llm_tokens = 0
        self.used_credits = 0
        self.used_jina_tokens = 0
        self.used_pages = 0
        self._writer_reserved = False

    # ---- writer 预留 ----------------------------------------------------
    def reserve_writer(self) -> bool:
        if self._writer_reserved:
            raise ReserveError("writer 预留已建立, 不随轮次重复扣留")
        self._writer_reserved = True
        return True

    @property
    def writer_reserved(self) -> bool:
        return self._writer_reserved

    # ---- LLM 账 ----------------------------------------------------------
    def charge_llm(self, tokens: int, *, for_writer: bool) -> bool:
        """按调用实际 usage 入账;writer 调用可用预留, 研究调用不可。"""
        if tokens < 0:
            raise ValueError("tokens 不能为负")
        limit = self.total_llm_tokens if for_writer else self.research_llm_limit()
        if self.used_llm_tokens + tokens > limit:
            return False
        self.used_llm_tokens += tokens
        return True

    def research_llm_limit(self) -> int:
        return self.total_llm_tokens - self.writer_reserve_tokens

    def research_llm_remaining(self) -> int:
        return max(0, self.research_llm_limit() - self.used_llm_tokens)

    def research_exhausted(self) -> bool:
        """研究额度耗尽(writer 预留与总时限仍充足)→ 停止研究走 writer。"""
        return self.used_llm_tokens >= self.research_llm_limit()

    def total_exhausted(self) -> bool:
        """任务总额度耗尽 → 不再调用任何模型(§3.6)。"""
        return self.used_llm_tokens >= self.total_llm_tokens

    # ---- 其他账 ----------------------------------------------------------
    def charge_credits(self, n: int) -> bool:
        if self.used_credits + n > self.max_tavily_credits:
            return False
        self.used_credits += n
        return True

    def charge_jina(self, tokens: int) -> bool:
        if self.max_jina_tokens <= 0:
            return False  # Jina 兜底默认关闭
        if self.used_jina_tokens + tokens > self.max_jina_tokens:
            return False
        self.used_jina_tokens += tokens
        return True

    def start_page(self) -> bool:
        """抓取页数熔断(≤12, §3.6);调用方负责页完成后自行计数 or 在此预占。"""
        if self.used_pages >= self.max_pages:
            return False
        self.used_pages += 1
        return True

    def out_of_time(self) -> bool:
        return (self._clock() - self._started_at) > self.time_budget_s

    # ---- 快照 ------------------------------------------------------------
    def usage_snapshot(self) -> dict:
        return {
            "llm_tokens": self.used_llm_tokens,
            "tavily_credits": self.used_credits,
            "jina_tokens": self.used_jina_tokens,
        }
