# H1 P3-4 第四轮运行清单

依据：`apps/api/eval/H1_PREREGISTRATION.md`（commit `6101de9`，未修改）。

本轮为纯重跑，无代码改动。两个适配器修复已在当前 HEAD `ce30e72` 中：objects.inv 字节偏移解析（`b0093d0`）和索引抓取单独放宽至 8MB（`e62e4a1`）。两组使用同一 HEAD、同一 prompt `phase2-v1`、同一模型配置、同一预算默认值与 `reflect` strategy。

两次为独立命令行/独立 Python 进程；未使用 `--compare`；qid 集合与预登记 §2 完全一致且顺序一致。A 完成后先检查到 6/8 题进入 search、5/8 题进入 reading，再等待 5 分钟后启动 B。

| 组名 | 文件名 | 环境变量 | 命令 | 起止时间 | git commit |
|---|---|---|---|---|---|
| pure_web（组 A） | `apps/api/eval/baselines/run_20260908_184204.json` / `table_20260908_184204.md` | `ORCA_SOURCE_ADAPTER` 未设置（进程值为空） | `cd apps/api; python -m orca.eval --only fact_freethread,noanswer_pep,fact_gil,fact_venv,compare_logging_print,timely_maint,timely_status,noanswer_ml` | 2026-09-08 18:34:16.3722354 +08:00 → 18:42:05.0034801 +08:00 | `ce30e72` |
| adapter（组 B） | `apps/api/eval/baselines/run_20260908_190521.json` / `table_20260908_190521.md` | `ORCA_SOURCE_ADAPTER=python_zh_docs` | `cd apps/api; ORCA_SOURCE_ADAPTER=python_zh_docs python -m orca.eval --only fact_freethread,noanswer_pep,fact_gil,fact_venv,compare_logging_print,timely_maint,timely_status,noanswer_ml` | 2026-09-08 18:48:12.6336575 +08:00 → 19:05:22.1299998 +08:00 | `ce30e72` |

组间等待：A 结束后等待约 5 分钟，再启动 B。

## 成本与适配器核验

- pure_web：7 credits / 39,895 tokens。
- adapter：0 credits / 260,083 tokens。
- 本轮合计：7 credits / 299,978 tokens。
- B 组真实 `search.payload.adapter` 命中：7/8；未发现 `source_adapter` fallback warning。
- 7 个命中 qid 的 payload 均包含 `adapter=python_zh_docs`、`inventory_version=3.14` 以及 objects.inv/searchindex SHA-256 元数据。
- `noanswer_ml` 未进入 search，具体 planner warning 为：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试`。
- A 组 `fact_venv`、`compare_logging_print` 同样在 planner 阶段记录该 HTTP 429；其余 A 组题进入了 search/reading 或完成证据流程。

## 标注与对照产物

- 双轮标注：`apps/api/eval/baselines/H1_ROUND4_ANNOTATIONS_20260908.json`
- 对照表与机械判定：`apps/api/eval/baselines/H1_ROUND4_COMPARISON_20260908.md`

未修改预登记、`PLAN.md` 或 `README.md`，未 push。最终结论措辞留待司令部核验。
