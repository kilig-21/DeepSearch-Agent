# H1 P3-4 第三轮对照表与机械判定

## 口径

本文件对应锁定的 `apps/api/eval/H1_PREREGISTRATION.md`（commit `6101de9`）。样本固定为 8 题，策略均为 `reflect`，唯一计划变量为适配器环境开关。第三轮两组均在 planner 阶段失败，未进入搜索、阅读或适配器逻辑。

- 断言引用支持率只采用 pass2 严格 quote-only；本轮两组均无报告/quote，按预登记对失败任务记为 N/A。
- 答案覆盖率按 `questions.py` 预定义必答点，分母为全部 8 题的 22 个必答点；无答案记 0。
- 证据命中数为 `evidences` 数组长度；获取成功率按事件轨迹计算，无 reading 且无 reader warning 为 N/A。
- `Δ` 为“adapter − pure_web”；主指标 Δ 用百分点，成本/耗时用原始差值。

## 组 B 适配器命中核验

| qid | `search.payload.adapter` | `source_adapter` warning | 具体状态 |
|---|---:|---:|---|
| fact_freethread | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |
| noanswer_pep | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |
| fact_gil | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |
| fact_venv | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |
| compare_logging_print | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |
| timely_maint | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |
| timely_status | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |
| noanswer_ml | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |

适配器真实命中样本为 **0/8**。本轮 B 组 8/8 题均属于“无 adapter 键且无 source_adapter warning”的前置失败异常；不能计作适配器回落或适配器命中。

## 逐题完整对照表

| qid | A 状态 | B 状态 | A 严格支持率 | B 严格支持率 | Δpp | A 覆盖率 | B 覆盖率 | Δpp | A 证据 | B 证据 | Δ | A 获取 | B 获取 | Δpp | A tokens | B tokens | Δ | A credits | B credits | Δ | A 秒 | B 秒 | Δ秒 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fact_freethread | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 4.6 | 4.2 | -0.4 |
| noanswer_pep | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 4.4 | 4.1 | -0.3 |
| fact_gil | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 4.5 | 4.4 | -0.1 |
| fact_venv | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 5.2 | 4.6 | -0.6 |
| compare_logging_print | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 4.5 | 4.4 | -0.1 |
| timely_maint | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 4.7 | 4.2 | -0.5 |
| timely_status | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 4.6 | 4.0 | -0.6 |
| noanswer_ml | completed/execution_error | completed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 | 0 | 4.6 | 4.5 | -0.1 |

## 组级汇总

| 指标 | pure_web | adapter | Δ |
|---|---:|---:|---:|
| 严格断言支持率 | N/A（0 条可评估断言） | N/A（0 条可评估断言） | N/A |
| 答案覆盖率（全部 22 个必答点） | 0/22 = 0.00% | 0/22 = 0.00% | 0.00pp |
| 总证据命中数 | 0 | 0 | 0 |
| 总获取成功率 | N/A（无 reading） | N/A（无 reading） | N/A |
| 总 LLM tokens | 0 | 0 | 0 |
| 总搜索 credits | 0 | 0 | 0 |
| 总耗时 | 37.1s | 34.4s | -2.7s |
| `status=failed` 失败率 | 0/8 = 0.0% | 0/8 = 0.0% | 0pp |
| `stop_reason=execution_error` | 8/8 | 8/8 | — |

## 预登记规则机械判定记录

1. 收缩方向：未触发；可计算的覆盖率 Δ 为 0.00pp，严格断言支持率为 N/A。
2. 改善方向：未触发；严格断言支持率不可评估，覆盖率未提升，成本条件不改变这一点。
3. 机械输出：未触发前两项阈值；按预登记兜底记为不确定方向，且本轮因两组均在 planner 阶段 HTTP 429 失败，不形成可解释的适配器效果样本。

由于 N=8 且本轮主指标不可评估，以上仅为机械记录，不构成统计证明；不据此归因于适配器。
