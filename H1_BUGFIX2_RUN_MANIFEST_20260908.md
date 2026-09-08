# H1 P3-4 第三轮运行清单

依据：`apps/api/eval/H1_PREREGISTRATION.md`（commit `6101de9`，未修改）。

本轮第二轮修复 commit：`e62e4a1c2c7d856b17d2f3aee333f309656cc0a8`。修复为适配器索引抓取显式使用 `INDEX_MAX_BYTES = 8_000_000`，未修改 `fetch.py` 默认正文上限或正文抓取路径。前一轮 objects.inv 修复 commit 为 `b0093d0678ee60fa01e695b77ec8063b1573e7e0`。

两组使用同一 HEAD `e62e4a1`、同一 prompt `phase2-v1`、同一模型配置、同一预算默认值与 `reflect` strategy。两次均为独立命令行/独立 Python 进程；未使用 `--compare`；qid 集合与预登记 §2 完全一致且顺序一致。

| 组名 | 文件名 | 环境变量 | 命令 | 起止时间 | git commit |
|---|---|---|---|---|---|
| pure_web（组 A） | `apps/api/eval/baselines/run_20260908_180742.json` / `table_20260908_180742.md` | `ORCA_SOURCE_ADAPTER` 未设置（进程值为空） | `cd apps/api; python -m orca.eval --only fact_freethread,noanswer_pep,fact_gil,fact_venv,compare_logging_print,timely_maint,timely_status,noanswer_ml` | 2026-09-08 18:07:02.0548725 +08:00 → 18:07:42.4340649 +08:00 | `e62e4a1` |
| adapter（组 B） | `apps/api/eval/baselines/run_20260908_180841.json` / `table_20260908_180841.md` | `ORCA_SOURCE_ADAPTER=python_zh_docs` | `cd apps/api; ORCA_SOURCE_ADAPTER=python_zh_docs python -m orca.eval --only fact_freethread,noanswer_pep,fact_gil,fact_venv,compare_logging_print,timely_maint,timely_status,noanswer_ml` | 2026-09-08 18:08:05.5393527 +08:00 → 18:08:42.2332590 +08:00 | `e62e4a1` |

## 成本与事件核验

- pure_web：0 credits / 0 tokens。
- adapter：0 credits / 0 tokens。
- 本轮合计：0 credits / 0 tokens。
- 两组 8/8 均记录 `stop_reason=execution_error`，具体 warning 原文均为：`规划失败: 重试耗尽(3 次尝试): HTTP 429: 可重试`。
- 两组均未产生 `search`、`reading` 或 `source_adapter` 事件；adapter 组真实 `search.payload.adapter` 命中为 0/8。
- 本轮不是适配器回落样本：B 组所有题均在 planner 阶段结束，不能计入适配器生效或 pure_web 回落样本。

## 标注与对照产物

- 双轮标注：`apps/api/eval/baselines/H1_BUGFIX2_ANNOTATIONS_20260908.json`
- 对照表与机械判定记录：`apps/api/eval/baselines/H1_BUGFIX2_COMPARISON_20260908.md`

未修改预登记、`PLAN.md` 或 `README.md`，未 push。正式收尾措辞不写入上述正式计划文件。
