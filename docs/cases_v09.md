# v0.9 代表性案例(四类终态)

> 素材均来自真实运行(离线注入题检索不联网、LLM 为真实调用,可复现;在线题为时点快照)。
> 运行快照含全量事件轨迹与证据(quote/URL/抓取时间),位于
> `apps/api/eval/baselines/run_*.json`,可逐条复核。

## 案例 1:正常完成 —— 反思循环收尾(evidence_sufficient)

- 题目:`fact_freethread` — Python 3.13 的自由线程模式是什么?默认是否启用?
- 行为:首轮检索 → 逐页阅读 → 证据合并;反思模型判定证据已充分 → 停止
  研究,进入 writer;报告引用有效率 1.0(全部 `[n]` 落在 citation_map 内)。
- 关键点:反思循环的停止由确定性条件与反思判定共同收敛——LLM 判"够了"
  才停止,且预算/轮次/无新增证据检查在其之前(翻不了案)。
- 结果行:`completed / evidence_sufficient / 引用有效率 1.0`
- 快照:`run_20260907_010146.json`(qid=fact_freethread, strategy=reflect)。

## 案例 2:来源部分失败 —— 失败如实记录,可用页照常出报告(fetch_partial)

- 题目:Python 虚拟环境如何创建与激活?(离线注入:1 页正常 + 1 页必然抓取失败)
- 行为:
  - 正常页证据照常入账:`ev_001~ev_003` 引自注入材料原文;
  - 失败页发出 warning(`抓取/提取失败 ... 评测注入: 模拟抓取失败`),
    不编造失败页内容;
  - writer 用可用证据产出正式报告(创建/激活/退出全要点覆盖)。
- 结果行:`completed / 引用有效率 1.0 / 事件含 1 条抓取失败 warning`
- 快照:`run_20260907_010146.json`(qid=fetch_partial)。

## 案例 3:预算耗尽 —— 调用前约束下的入口即停(§3.6,R1 后行为)

两级预算均升级为**调用前约束**:每次模型调用前按剩余额度收紧
`max_tokens`,剩余不足最小可用输出(1024)即不调用、走程序降级;
实耗超限会在终检中如实标记 `over_budget`,不静默。

**3a 研究额度打穿**:`budget_fuse` 题(研究额度 100 tokens)——入口
检查即不调用,实耗 0 tokens,报告为程序说明。

**3b 总额度打穿**:`budget_total` 题(总额度 160 tokens)——同样入口
即停,`total_budget_exhausted`,实耗 0 tokens:

> 针对问题「Python 3.13 有什么新特性?」,任务总额度已耗尽,为控制成本
> 未再调用模型。……本说明由程序生成,未经模型撰写。

- 关键点:修复前该题曾出现 planner 实耗 175 越过 160 上限(事后记账);
  调用前约束后实耗 0,守门测试对快照逐行断言 tokens ≤ 行上限。
- 快照:`run_20260907_010146.json`(qid=budget_fuse / budget_total)。

## 案例 4:搜索无结果 / 全部抓取失败 —— 诚实拒答(no_new_evidence)

- 题目:`no_results`(离线注入:搜索恒返回 0 结果)。
- 行为:反思的确定性条件直接判定(本轮无新增证据,不调反思模型)→
  writer 无证据可写 → 程序说明,全文 281 tokens(planner 之外零模型调用):

> 针对问题「…」,未能获取到任何可核实的证据,无法生成有依据的报告。

- 关键点:"无答案"是显式终态而非编造;评测口径下此类题记 N/A,不静默
  出质量分母(§10.1)。
- 快照:`run_20260907_010146.json`(qid=no_results)。

## 案例 5(补充):用户取消 —— 控制类终态(user_cancelled)

- 行为:取消请求受理后 persist 前最后检查取消标志;writer 流式被中断时
  显式关闭上游 HTTP 流;`cancelled` 终态后草稿不作为内容暴露;重复取消
  与终态后取消被拒绝。
- 依据:SSE 与取消路径验收测试(test_acceptance_1b / test_task_manager);
  操作演示见 `docs/demo_v09.md` 场景 4。

## 案例 6(补充):反思循环带来证据增量 —— 时效题的追问(timely_latest)

- 题目:`timely_latest` — 截至今天,Python 官方文档对应的最新的稳定版本是哪个?
- 行为:第 1 轮检索文档主页等 7 条证据;反思模型判定"最新版本"需要
  直接版本声明,追加 3 条查询定向补搜(What's new in 3.14 / 发布公告 /
  PEP 745)→ 新增 `ev_012/ev_013/ev_014` 三条关键证据(分别对应
  "3.14 is the latest stable release" 直述、2025-10-07 发布日期、
  PEP 745 发布计划)→ writer 报告核心断言直接引用 `[12][13][14]`。
- 关键点:反思的增量不是重搜同题,而是针对证据缺口的定向追问;该题
  stop_reason=evidence_sufficient(第 2 轮判定充分后收尾)。
- 局限:反思并非每题都有增量——同批 conflict_ft/reflect 第 2 轮 3 条
  查询均无新增证据,以 no_new_evidence 收尾(快照内轨迹可查)。
- 快照:`run_20260906_final.json`(qid=timely_latest, strategy=reflect;
  2026-09-07 基线快照中该题反思一轮即收尾,无增量案例,故引用本快照)。
