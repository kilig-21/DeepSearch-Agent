# H1 P3-4 第四轮对照表与机械判定

## 口径

本文件对应锁定的 `apps/api/eval/H1_PREREGISTRATION.md`（commit `6101de9`）。样本固定为 8 题，策略均为 `reflect`，唯一计划变量为适配器环境开关。A/B 均使用同一代码 HEAD `ce30e72`，无代码改动。

- 断言引用支持率只采用 pass2 严格 quote-only；`support=1`、`partial=0.5`、`not_support=0`。
- 答案覆盖率按 `questions.py` 预定义必答点；`covered=1`、`partial=0.5`、`not_covered=0`，分母为全部 8 题的 22 个必答点。
- 证据命中数为结果行 `evidences` 数组长度。
- 获取成功率为事件轨迹中的 `reading / (reading + reader warning)`；没有读取尝试为 N/A。
- `Δ` 均为“adapter − pure_web”；主指标 Δ 用百分点，成本/耗时用原始差值。

## 组 B 适配器命中核验

| qid | 真实 `search.payload.adapter` 次数 | `source_adapter` warning | 结论 |
|---|---:|---:|---|
| fact_freethread | 1 | 0 | 真实 adapter 命中 |
| noanswer_pep | 1 | 0 | 真实 adapter 命中 |
| fact_gil | 1 | 0 | 真实 adapter 命中 |
| fact_venv | 3 | 0 | 3 次真实 adapter 命中 |
| compare_logging_print | 3 | 0 | 3 次真实 adapter 命中 |
| timely_maint | 3 | 0 | 3 次真实 adapter 命中 |
| timely_status | 2 | 0 | 2 次真实 adapter 命中 |
| noanswer_ml | 0 | 0 | 未进入 search；planner warning：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试` |

适配器真实命中样本为 **7/8**；未发现 `source_adapter` 回落。7 个命中 qid 的 payload 均记录：`adapter=python_zh_docs`、`index_root=https://docs.python.org/zh-cn/3/`、`inventory_project=Python`、`inventory_version=3.14`、`objects_inv_sha256=dbf0668939087b0f9930ea2d3c95ff8189e05aa53383fe36c613424cdc9a687d`、`searchindex_sha256=229d48855da2234ee9db02abf8a25d970fec8c606bcc4ec5d2509389ed07a054`。

## 逐题完整对照表

| qid | A 状态 | B 状态 | A 严格支持率 | B 严格支持率 | Δpp | A 覆盖率 | B 覆盖率 | Δpp | A 证据 | B 证据 | Δ | A 获取 | B 获取 | Δpp | A tokens | B tokens | Δ | A credits | B credits | Δ | A 秒 | B 秒 | Δ秒 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fact_freethread | completed/evidence_sufficient | completed/evidence_sufficient | 50.00% | 75.00% | +25.00 | 66.67% | 83.33% | +16.67 | 3 | 10 | +7 | 66.7% | 100.0% | +33.3 | 6,108 | 32,207 | +26,099 | 1 | 0 | -1 | 81.8 | 143.6 | +61.8 |
| noanswer_pep | completed/no_new_evidence | completed/evidence_sufficient | N/A | 100.00% | N/A | 0.00% | 100.00% | +100.00 | 0 | 9 | +9 | 50.0% | 80.0% | +30.0 | 160 | 29,524 | +29,364 | 1 | 0 | -1 | 32.6 | 101.0 | +68.4 |
| fact_gil | completed/no_new_evidence | completed/evidence_sufficient | N/A | 87.50% | N/A | 0.00% | 83.33% | +83.33 | 0 | 12 | +12 | 50.0% | 100.0% | +50.0 | 193 | 36,638 | +36,445 | 1 | 0 | -1 | 30.5 | 172.5 | +142.0 |
| fact_venv | completed/execution_error | completed/no_new_evidence | N/A | 50.00% | N/A | 0.00% | 50.00% | +50.00 | 0 | 6 | +6 | N/A | 66.7% | N/A | 0 | 44,044 | +44,044 | 0 | 0 | 0 | 6.2 | 134.9 | +128.7 |
| compare_logging_print | completed/execution_error | completed/no_new_evidence | N/A | N/A | N/A | 0.00% | 0.00% | 0.00 | 0 | 6 | +6 | N/A | 69.2% | N/A | 0 | 45,300 | +45,300 | 0 | 0 | 0 | 6.4 | 180.2 | +173.8 |
| timely_maint | completed/no_new_evidence | completed/no_new_evidence | 87.50% | 50.00% | -37.50 | 66.67% | 16.67% | -50.00 | 3 | 11 | +8 | 100.0% | 77.8% | -22.2 | 9,065 | 29,712 | +20,647 | 2 | 0 | -2 | 93.6 | 133.2 | +39.6 |
| timely_status | completed/evidence_sufficient | completed/evidence_sufficient | 100.00% | 50.00% | -50.00 | 83.33% | 16.67% | -66.67 | 7 | 12 | +5 | 80.0% | 77.8% | -2.2 | 15,287 | 42,658 | +27,371 | 1 | 0 | -1 | 84.0 | 156.3 | +72.3 |
| noanswer_ml | completed/evidence_sufficient | completed/execution_error | 62.50% | N/A | N/A | 75.00% | 0.00% | -75.00 | 8 | 0 | -8 | 80.0% | N/A | N/A | 9,082 | 0 | -9,082 | 1 | 0 | -1 | 130.4 | 4.6 | -125.8 |

## 组级汇总

| 指标 | pure_web | adapter | Δ |
|---|---:|---:|---:|
| 严格断言支持率 | 10.5/14 = 75.00% | 13.0/20 = 65.00% | -10.00pp |
| 答案覆盖率（全部 22 个必答点） | 7.5/22 = 34.09% | 9.5/22 = 43.18% | +9.09pp |
| 总证据命中数 | 21 | 66 | +45 |
| 总获取成功率（逐题事件值，含 N/A） | 5/7 题有值 | 7/8 题有值 | 不作汇总平均 |
| 总 LLM tokens | 39,895 | 260,083 | +220,188（+552.17%） |
| 总搜索 credits | 7 | 0 | -7 |
| 总耗时 | 465.5s | 1,026.3s | +560.8s（+120.47%） |
| `status=failed` 失败率 | 0/8 = 0.0% | 0/8 = 0.0% | 0pp |
| `stop_reason=execution_error` | 2/8 | 1/8 | -1 题 |

成本条件核验：adapter 平均 credits 为 pure_web 的 0.00%，但平均 LLM tokens 为 pure_web 的约 652.18%，超过预登记 120% 成本条件。`noanswer_ml` 的 B 组在 planner 阶段 HTTP 429 失败，未形成 adapter 命中样本。

## 预登记规则机械判定记录

1. 收缩方向优先检查：严格断言引用支持率组级 Δ 为 **-10.00pp**，达到下降至少 5pp；因此机械收缩阈值被触发。
2. 改善方向不再覆盖收缩方向；同时成本条件中的平均 tokens 超过 120%。
3. 由于 N=8<10，以上只作为预登记机械规则的方向性/定性观察记录，不构成统计证明；最终表述留待核验，不写入 PLAN.md 或 README.md。
