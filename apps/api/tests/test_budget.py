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
    assert b.settle_llm(8_000, for_writer=False) is True
    # 超过研究额度(挤占 writer 预留):记账(事实)但返回超限, 后续不再调
    assert b.settle_llm(1, for_writer=False) is False
    assert b.used_llm_tokens == 8_001         # 实际 usage 必须如实入账


def test_writer_calls_may_use_reserve():
    b = make_b(total_llm=10_000, reserve=2_000)
    b.settle_llm(8_000, for_writer=False)
    assert b.settle_llm(2_000, for_writer=True) is True
    assert b.used_llm_tokens == 10_000


def test_research_exhausted_but_total_still_has_writer_room():
    b = make_b(total_llm=10_000, reserve=2_000)
    b.settle_llm(8_000, for_writer=False)
    assert b.research_exhausted() is True    # → stop_reason=budget_exhausted, 走 writer
    assert b.total_exhausted() is False      # 仍可调模型写报告


def test_total_exhausted_blocks_even_writer():
    b = make_b(total_llm=10_000, reserve=2_000)
    b.settle_llm(8_000, for_writer=False)
    b.settle_llm(2_000, for_writer=True)
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
    b.settle_llm(2_757, for_writer=False)
    b.charge_credits(1)
    assert b.usage_snapshot() == {
        "llm_tokens": 2_757, "llm_research_tokens": 2_757,
        "llm_writer_tokens": 0, "tavily_credits": 1, "jina_tokens": 0,
        "over_budget": False,
    }


# ---- 成本分账(块 2): tokens 按研究/writer 分列入账 -------------------------

def test_settle_splits_research_and_writer():
    """研究/writer tokens 分列记账, 总数恒为两者之和(§4 块 2)。"""
    b = make_b()
    b.settle_llm(1_000, for_writer=False)
    b.settle_llm(2_000, for_writer=False)
    b.settle_llm(750, for_writer=True)
    assert b.used_llm_research == 3_000
    assert b.used_llm_writer == 750
    assert b.used_llm_tokens == 3_750            # 总账 = 分账之和
    assert b.usage_snapshot()["llm_research_tokens"] == 3_000
    assert b.usage_snapshot()["llm_writer_tokens"] == 750


def test_split_accounts_do_not_change_budget_checks():
    """分账只是观测口径: 两级额度检查仍用总账, 行为不变(§3.6)。"""
    b = make_b(total_llm=10_000, reserve=2_000)
    b.settle_llm(8_000, for_writer=False)
    assert b.research_exhausted() is True
    assert b.settle_llm(2_000, for_writer=True) is True
    assert b.total_exhausted() is True


# ---- 调用前约束(修复轮 R1): max_tokens 按剩余总额度 clamp -------------------

def test_max_output_tokens_passes_through_when_rich():
    """额度充裕 → 按请求值放行, 不改变既有调用形态。"""
    b = make_b()
    assert b.max_output_tokens(16_384, prompt_estimate=1_000) == 16_384


def test_max_output_tokens_clamps_to_remaining():
    """修复轮评审复现场景: 研究 41000/50000 时请求 16384 输出会被
    clamp 到剩余额度可容纳值, 总账不再越限。"""
    b = make_b(total_llm=50_000, reserve=8_000)
    b.settle_llm(41_000, for_writer=False)
    # 剩余 9000, prompt 保守估算 1000 + 边际 512 → 输出上限 7488
    assert b.max_output_tokens(16_384, prompt_estimate=1_000) == 7_488


def test_max_output_tokens_negative_when_prompt_alone_exceeds():
    """budget_total 场景: 总额度 160 连 prompt 估算都盖不住 → 负值,
    调用方判 < MIN_USABLE_OUTPUT 后不得发起调用。"""
    b = make_b(total_llm=160, reserve=80)
    assert b.max_output_tokens(4_096, prompt_estimate=572) < 0


def test_min_usable_output_threshold_exported():
    """阈值自定并说明: glm-5.3 推理型输出配额低于 1024 时连最小思考+正文
    都放不下(实测思考动辄数千 token), 调用大概率空响应/残缺 → 不值得发起。
    作为库级常量导出, 调用方统一判定。"""
    assert budget.MIN_USABLE_OUTPUT == 1_024
    assert budget.PROMPT_MARGIN == 512


def test_usage_snapshot_includes_over_budget():
    """落库前终检口径: usage 是已发生的事实总是记账(settle 语义不变),
    超限事实以 over_budget 如实标记, 禁止静默(修复轮 R1b)。"""
    b = make_b(total_llm=100, reserve=0)
    b.settle_llm(150, for_writer=False)
    snap = b.usage_snapshot()
    assert snap["over_budget"] is True
    b2 = make_b()
    assert b2.usage_snapshot()["over_budget"] is False
