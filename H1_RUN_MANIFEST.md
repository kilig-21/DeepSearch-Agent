# H1 P3-4 运行清单

依据：`apps/api/eval/H1_PREREGISTRATION.md`（commit `6101de9`，未修改）。

候选适配器实现：`apps/api/orca/adapters.py`（commit `27e1457`）。两组均使用同一 HEAD `27e1457`、同一 prompt `phase2-v1`、同一模型配置、同一预算默认值与 `reflect` strategy。

| 组名 | 文件名 | 环境变量 | 命令 | 起止时间 | git commit |
|---|---|---|---|---|---|
| pure_web（组 A） | `apps/api/eval/baselines/run_20260908_134704.json` / `table_20260908_134704.md` | `ORCA_SOURCE_ADAPTER` 未设置（进程值为空） | `cd apps/api; python -m orca.eval --only fact_freethread,noanswer_pep,fact_gil,fact_venv,compare_logging_print,timely_maint,timely_status,noanswer_ml` | 2026-09-08 13:35:00 +08:00 → 13:47:04 +08:00 | `27e1457` |
| adapter（组 B） | `apps/api/eval/baselines/run_20260908_140441.json` / `table_20260908_140441.md` | `ORCA_SOURCE_ADAPTER=python_zh_docs` | `cd apps/api; ORCA_SOURCE_ADAPTER=python_zh_docs python -m orca.eval --only fact_freethread,noanswer_pep,fact_gil,fact_venv,compare_logging_print,timely_maint,timely_status,noanswer_ml` | 2026-09-08 13:47:43 +08:00 → 14:04:41 +08:00 | `27e1457` |

执行纪律：两次为独立命令行/独立 Python 进程；未使用 `--compare`；qid 集合与预登记 §2 完全一致，顺序一致；组 A 先于组 B，间隔约 43 秒。

标注产物：`apps/api/eval/baselines/H1_ANNOTATIONS_20260908.json`。
对照表与机械判定：`apps/api/eval/baselines/H1_COMPARISON_20260908.md`。

运行成本：pure_web 12 credits / 113,381 tokens；adapter 12 credits / 115,691 tokens；合计 24 credits / 229,072 tokens，处于预估 15–25 credits 范围内。

偏差与异常：组 B 8/8 题均出现 `source_adapter` warning 并以 `fallback=pure_web` 继续；0/8 题出现含 `payload.adapter` 的 search 事件。`noanswer_pep` 两组均 `execution_error`；组 B 另有一次 searchindex 连接被远端关闭。未修改预登记、PLAN 或 README，未 push。
