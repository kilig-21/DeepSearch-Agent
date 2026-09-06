# v0.9 代表性案例(四类终态)

> 素材均来自真实运行(离线注入题不联网、可复现;在线题为时点快照)。
> 运行快照含全量事件轨迹与证据(quote/URL/抓取时间),位于
> `apps/api/eval/baselines/run_*.json`,可逐条复核。

## 案例 1:正常完成 —— 反思循环收尾(evidence_sufficient)

- 题目:`fact_freethread` — Python 3.13 的自由线程模式是什么?默认是否启用?
- 行为:首轮检索 → 逐页阅读 → 证据合并;反思模型判定证据已充分 → 停止
  研究,进入 writer;报告引用有效率 1.0(全部 `[n]` 落在 citation_map 内)。
- 关键点:反思循环的停止由确定性条件与反思判定共同收敛——LLM 判"够了"
  才停止,且预算/轮次/重复检查在其之前(翻不了案)。
- 结果行:`completed / evidence_sufficient / 引用有效率 1.0`
- 快照:见最新 `run_*.json` 中 `qid=fact_freethread, strategy=reflect`。

## 案例 2:来源部分失败 —— 失败如实记录,可用页照常出报告(fetch_partial)

- 题目:Python 虚拟环境如何创建与激活?(离线注入:1 页正常 + 1 页必然抓取失败)
- 行为:
  - 正常页证据照常入账:`ev_001~ev_003` 引自注入材料原文;
  - 失败页发出 warning(`抓取/提取失败 ... 评测注入: 模拟抓取失败`),
    不编造失败页内容;
  - writer 用可用证据产出正式报告(创建/激活/退出全要点覆盖)。
- 结果行:`completed / 引用有效率 1.0 / 事件含 1 条抓取失败 warning`
- 快照:`run_20260906_173721.json`(qid=fetch_partial)。

## 案例 3:预算耗尽 —— 两级规则的两种收尾(§3.6)

**3a 研究额度耗尽(研究类 stop)**:`budget_fuse` 题,研究额度 100 tokens,
planner 一次调用即耗尽 → `budget_exhausted`;writer 用预留产出程序说明,
不产出未经研究的"结论"。

**3b 总额度打穿(控制类 stop)**:`budget_total` 题,总额度 160 tokens <
planner 单次实耗 175 → 下个节点入口即时捕获 `total_budget_exhausted`,
**不再调用任何模型**,报告为程序说明:

> 针对问题「Python 3.13 有什么新特性?」,任务总额度已耗尽,为控制成本
> 未再调用模型。……本说明由程序生成,未经模型撰写。

- 快照:`run_20260906_174008.json`(qid=budget_total,tokens=175)。

## 案例 4:搜索无结果 / 全部抓取失败 —— 诚实拒答(no_new_evidence)

- 题目:`no_results`(离线注入:搜索恒返回 0 结果)。
- 行为:反思的确定性条件直接判定(本轮无新增证据,不调反思模型)→
  writer 无证据可写 → 程序说明,全文 169 tokens(planner 之外零模型调用):

> 针对问题「…」,未能获取到任何可核实的证据,无法生成有依据的报告。

- 关键点:"无答案"是显式终态而非编造;评测口径下此类题记 N/A,不静默
  出质量分母(§10.1)。
- 快照:`run_20260906_173721.json`(qid=no_results)。

## 案例 5(补充):用户取消 —— 控制类终态(user_cancelled)

- 行为:取消请求受理后 persist 前最后检查取消标志;writer 流式被中断时
  显式关闭上游 HTTP 流;`cancelled` 终态后草稿不作为内容暴露;重复取消
  与终态后取消被拒绝。
- 依据:SSE 与取消路径验收测试(test_acceptance_1b / test_task_manager);
  操作演示见 `docs/demo_v09.md` 场景 4。
