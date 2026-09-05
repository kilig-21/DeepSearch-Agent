"""预算账本测试(计划书 §3.6 两级规则)。

两级语义:
- 研究额度耗尽(搜索/摘要账空, writer 预留+总时限充足)→ budget_exhausted, 用已有证据走 writer
- 总额度/总时限耗尽 → 不再调模型 → total_budget_exhausted / timeout
- writer 预留每任务建立一次, 不随轮次重复扣留
"""
import pytest

from orca import budget


def make_b(total_llm=50_000, reserve=8_000, credits=16, pages=12, time_s=480.0,
           jina=0, clock=lambda: 0.0):
    return budget.Budget(
        total_llm_tokens=total_llm, writer_reserve_tokens=reserve,
        max_tavily_credits=credits, max_pages=pages, time_budget_s=time_s,
        max_jina_tokens=jina, clock=clock,
    )


def test_writer_reserve_established_once():
    b = make_b()
    assert b.reserve_writer() is True
    with pytest.raises(budget.ReserveError):
        b.reserve_writer()  # 每任务只建立一次


def test_research_calls_cannot_touch_writer_reserve():
    b = make_b(total_llm=10_000, reserve=2_000)
    assert b.charge_llm(8_000, for_writer=False) is True
    # 第 8001 个 token 起将挤占 writer 预留 → 拒绝
    assert b.charge_llm(1, for_writer=False) is False
    assert b.used_llm_tokens == 8_000


def test_writer_calls_may_use_reserve():
    b = make_b(total_llm=10_000, reserve=2_000)
    b.charge_llm(8_000, for_writer=False)
    assert b.charge_llm(2_000, for_writer=True) is True
    assert b.used_llm_tokens == 10_000


def test_research_exhausted_but_total_still_has_writer_room():
    b = make_b(total_llm=10_000, reserve=2_000)
    b.charge_llm(8_000, for_writer=False)
    assert b.research_exhausted() is True    # → stop_reason=budget_exhausted, 走 writer
    assert b.total_exhausted() is False      # 仍可调模型写报告


def test_total_exhausted_blocks_even_writer():
    b = make_b(total_llm=10_000, reserve=2_000)
    b.charge_llm(8_000, for_writer=False)
    b.charge_llm(2_000, for_writer=True)
    assert b.total_exhausted() is True       # → 不再调用任何模型


def test_three_accounts_are_independent():
    b = make_b(jina=500_000)                 # 显式启用 Jina(§3.6 默认关闭)
    assert b.charge_credits(16) is True
    assert b.charge_credits(1) is False      # credits 账不影响 llm 账
    assert b.charge_jina(1_000) is True
    assert b.used_llm_tokens == 0
    assert b.used_credits == 16
    assert b.used_jina_tokens == 1_000


def test_jina_disabled_by_default():
    b = make_b()
    assert b.charge_jina(1) is False


def test_page_budget_fuse():
    b = make_b(pages=2)
    assert b.start_page() is True
    assert b.start_page() is True
    assert b.start_page() is False           # 第 13 页(此处第 3 页)被拒


def test_timeout_by_injected_clock():
    t = [0.0]
    b = make_b(time_s=10.0, clock=lambda: t[0])
    assert b.out_of_time() is False
    t[0] = 10.1
    assert b.out_of_time() is True


def test_usage_snapshot_for_db():
    b = make_b()
    b.charge_llm(2_757, for_writer=False)
    b.charge_credits(1)
    assert b.usage_snapshot() == {
        "llm_tokens": 2_757, "tavily_credits": 1, "jina_tokens": 0,
    }
