# H1 P3-4 对照表与机械判定

## 口径

本文件对应预登记 `H1_PREREGISTRATION.md`，样本固定为 8 题，策略均为 `reflect`，唯一计划变量为适配器环境开关。标注见 `H1_ANNOTATIONS_20260908.json`。

- 断言引用支持率只采用 pass2 严格 quote-only；`support=1`、`partial=0.5`、`not_support=0`。
- 答案覆盖率按 `questions.py` 的预定义必答点；`covered=1`、`partial=0.5`、`missed=0`。
- 证据命中数为 `evidences` 数组长度。
- 获取成功率为事件轨迹中的 `reading / (reading + reader warning)`；没有读取尝试为 N/A。该指标是对预登记辅助指标的事件级可审计呈现。
- `Δ` 均为“adapter − pure_web”；主指标 Δ 用百分点，成本/耗时用原始差值。

## 组 B 适配器命中核验

| qid | 真实 `search.payload.adapter` | `source_adapter` warning | 结论 |
|---|---:|---:|---|
| fact_freethread | 0 | 1（objects.inv 损坏） | 回落 pure_web，不计命中 |
| noanswer_pep | 0 | 3（objects.inv 损坏；searchindex 连接被远端关闭；objects.inv 损坏） | 回落 pure_web，不计命中 |
| fact_gil | 0 | 2（objects.inv 损坏） | 回落 pure_web，不计命中 |
| fact_venv | 0 | 1（objects.inv 损坏） | 回落 pure_web，不计命中 |
| compare_logging_print | 0 | 1（objects.inv 损坏） | 回落 pure_web，不计命中 |
| timely_maint | 0 | 2（objects.inv 损坏） | 回落 pure_web，不计命中 |
| timely_status | 0 | 1（objects.inv 损坏） | 回落 pure_web，不计命中 |
| noanswer_ml | 0 | 1（objects.inv 损坏） | 回落 pure_web，不计命中 |

适配器真实命中样本为 **0/8**。8/8 题均有可见的 source-adapter 回落 warning；未发现“无 adapter 键且无 source-adapter warning”的异常行。完整原始轨迹在两份 `run_*.json` 中。

## 逐题完整对照表

| qid | A 状态 | B 状态 | A 严格支持率 | B 严格支持率 | Δpp | A 覆盖率 | B 覆盖率 | Δpp | A 证据 | B 证据 | Δ | A 获取 | B 获取 | Δpp | A tokens | B tokens | Δ | A credits | B credits | Δ | A 秒 | B 秒 | Δ秒 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fact_freethread | completed/evidence_sufficient | completed/evidence_sufficient | 50.00% | 70.00% | +20.00 | 66.67% | 100.00% | +33.33 | 3 | 6 | +3 | 100.0% | 100.0% | 0.0 | 5,697 | 9,317 | +3,620 | 1 | 1 | 0 | 46.3 | 73.3 | +27.0 |
| noanswer_pep | failed/execution_error | failed/execution_error | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | 100.0% | 90.0% | -10.0 | 46,644 | 46,304 | -340 | 3 | 3 | 0 | 160.7 | 249.8 | +89.1 |
| fact_gil | completed/no_new_evidence | completed/no_new_evidence | 66.67% | 50.00% | -16.67 | 83.33% | 83.33% | 0.00 | 9 | 3 | -6 | 100.0% | 66.7% | -33.3 | 15,399 | 12,952 | -2,447 | 1 | 2 | +1 | 116.3 | 200.6 | +84.3 |
| fact_venv | completed/no_new_evidence | completed/no_new_evidence | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 0 | 0 | N/A | N/A | N/A | 162 | 168 | +6 | 1 | 1 | 0 | 6.3 | 31.9 | +25.6 |
| compare_logging_print | completed/evidence_sufficient | completed/evidence_sufficient | 70.00% | 83.33% | +13.33 | 66.67% | 66.67% | 0.00 | 6 | 6 | 0 | 100.0% | 100.0% | 0.0 | 18,318 | 19,702 | +1,384 | 2 | 1 | -1 | 128.3 | 110.0 | -18.3 |
| timely_maint | completed/no_new_evidence | completed/no_new_evidence | 70.00% | 70.00% | 0.00 | 66.67% | 66.67% | 0.00 | 3 | 5 | +2 | 100.0% | 100.0% | 0.0 | 10,152 | 13,801 | +3,649 | 2 | 2 | 0 | 110.3 | 179.4 | +69.1 |
| timely_status | completed/evidence_sufficient | completed/evidence_sufficient | 100.00% | 100.00% | 0.00 | 100.00% | 100.00% | 0.00 | 4 | 6 | +2 | 100.0% | 100.0% | 0.0 | 10,383 | 7,747 | -2,636 | 1 | 1 | 0 | 84.4 | 80.0 | -4.4 |
| noanswer_ml | completed/evidence_sufficient | completed/evidence_sufficient | 37.50% | 37.50% | 0.00 | 100.00% | 100.00% | 0.00 | 9 | 6 | -3 | 100.0% | 100.0% | 0.0 | 6,626 | 5,700 | -926 | 1 | 1 | 0 | 71.0 | 93.0 | +22.0 |

注：`noanswer_pep` 的读取成功率为 100%/90%，表示页面读取事件本身，不代表任务成功；该题两组任务均失败，故支持率 N/A，失败率仍计入全部 8 题分母。`fact_venv` 两组都没有 reading 事件，获取成功率为 N/A，不按零计。

## 组级汇总

| 指标 | pure_web | adapter | Δ |
|---|---:|---:|---:|
| 严格断言支持率 | 14.5/23 = 63.04% | 17.0/25 = 68.00% | +4.96pp |
| 答案覆盖率（全部 22 个必答点） | 14.0/22 = 63.64% | 14.5/22 = 65.91% | +2.27pp |
| 总证据命中数 | 34 | 32 | -2 |
| 总获取成功率（逐题事件值，含 N/A） | 7/7 题有值，均 100% | 7/7 题有值，5×100%、90%、66.7% | 不作汇总平均 |
| 总 LLM tokens | 113,381 | 115,691 | +2,310（+2.04%） |
| 总搜索 credits | 12 | 12 | 0（组均 1.50） |
| 总耗时 | 723.6s | 1,018.0s | +294.4s（+40.69%） |
| 失败率 | 1/8 = 12.5% | 1/8 = 12.5% | 0pp |

成本条件核验：adapter 平均 credits 为 pure_web 的 100.0%，平均 tokens 为 102.04%，均未超过预登记的 120% 上限。耗时不是改善规则的成本闸门，但作为辅助指标报告。

## 预登记规则机械判定

1. 收缩方向：未触发。两个主指标的组级 Δ 分别为 +4.96pp、+2.27pp，均非下降 ≥5pp。
2. 改善方向：未触发。严格断言支持率提升 +4.96pp、覆盖率提升 +2.27pp，均未达到任一主指标提升 ≥5pp；成本条件虽满足，但不足以改变该判定。
3. 机械结果：**不确定方向**。

由于 N=8<10，以上只能表述为**方向性/定性观察**，不构成“改善”或“收缩”的统计证明，也不进行显著性宣称。另因组 B 真实适配器命中为 0/8、全部回落 pure_web，本次运行没有形成适配器实际生效样本；任何差异不得归因于适配器。
