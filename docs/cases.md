# 代表性案例(四类终态 + 两侧补充)

> 素材全部取自当前基线快照
> `apps/api/eval/baselines/run_20260912_195950.json`(DeepSeek 时代,2026-09-12,27 题)。
> 离线注入题检索不联网、LLM 为真实调用,可复现;在线题为该时点的快照。
> 下列每个数字都能在快照里逐条复核:预算记账在行内 `tokens`/`credits`/`usage`,
> 证据在 `evidences`,全过程在 `events` 轨迹。

## 案例 1:正常完成 —— 反思循环收尾(evidence_sufficient)

- 题目:`fact_freethread` — Python 3.13 的自由线程模式是什么?默认是否启用?
- 行为:首轮检索 → 阅读 2 页 → 记入 6 条证据(`ev_001~ev_006`)→ 1 轮反思判定
  证据已充分 → 进入 writer;报告引用有效率 1.0(6 条 `[n]` 全部落在 `citation_map` 内)。
- 预算:11,970 tokens(研究 9,074 + writer 2,896)/ 1 credit / 64.6 秒。
- 关键点:反思循环的停止由确定性条件与反思判定共同收敛——LLM 判"够了"才
  停止,且预算/轮次/无新增证据三项检查一律在其之前(翻不了案)。
- 快照:`run_20260912_195950.json`,qid=`fact_freethread`。

## 案例 2:来源部分失败 —— 失败如实记录,可用页照常出报告(fetch_partial)

- 题目:Python 虚拟环境如何创建与激活?(离线注入:1 页正常 + 1 页必然抓取失败)
- 行为:
  - 正常页证据照常入账:`ev_001~ev_003` 引自注入材料原文,引用有效率 1.0;
  - 失败页发出 warning,快照里的原文是
    `抓取/提取失败 https://docs.python.org/3/library/venv-2.html: 评测注入: 模拟抓取失败`,
    **不编造失败页内容**;
  - writer 用可用证据产出正式报告(创建/激活/退出要点覆盖)。
- 预算:5,571 tokens(研究 3,354 + writer 2,217)/ 2 credits / 48.3 秒。
- stop_reason = `no_new_evidence`(第 2 轮补搜无新增证据后收尾——不是失败,
  是"没有更多可查的了")。
- 快照:`run_20260912_195950.json`,qid=`fetch_partial`。

## 案例 3:预算耗尽 —— 调用前约束下的入口即停(§3.6)

两级预算都是**调用前约束**:每次模型调用前按剩余额度收紧 `max_tokens`,
剩余不足**最小可用输出**即不调用、走程序降级;实耗真的越限会在终检中如实
标记 `over_budget`,不静默。

**3a 研究额度打穿**:`budget_fuse`——该题覆盖 `total_llm_tokens=350` 且
`writer_reserve_tokens=250`,研究额度只剩 **100 tokens**。入口检查即不调用,
**实耗 0 tokens**,报告是 88 字符的程序说明。

**3b 总额度打穿**:`budget_total`——该题覆盖总额度 **160 tokens**
(writer 预留 80)。同样入口即停,`stop_reason=total_budget_exhausted`,实耗 0:

> 针对问题「Python 3.13 有什么新特性?」,任务总额度已耗尽,为控制成本
> 未再调用模型。……本说明由程序生成,未经模型撰写。

两条 warning 的原文(可直接在快照里搜到):

```
剩余额度不足(可用输出 -286 < 最小阈值 4096), 不调用模型
剩余额度不足(可用输出 -476 < 最小阈值 4096), 不调用模型
```

- 关键点:修复前该题曾出现 planner 实耗 175 越过 160 上限(事后记账);
  调用前约束后实耗 0,守门测试 `test_latest_baseline_all_rows_within_budget_cap`
  对快照**逐行**断言 tokens ≤ 行上限。
- 口径提示:**最小可用输出 4096 是 DeepSeek 重校准后的值**——glm 时代为
  1024,当时的快照里写的就是 1024。跨时代读旧快照时别把这当成回退
  (依据见 `apps/api/docs/probe_results.md` T12)。
- 快照:`run_20260912_195950.json`,qid=`budget_fuse` / `budget_total`。

## 案例 4:搜索无结果 —— 诚实拒答(no_new_evidence)

- 题目:`no_results`(离线注入:搜索恒返回 0 结果)。
- 行为:反思的确定性条件直接判定(本轮无新增证据,**不调反思模型**)→
  writer 无证据可写 → 程序说明。报告 103 字符:

> 针对问题「…」,未能获取到任何可核实的证据,无法生成有依据的报告。

- 预算:1,592 tokens **全部花在 planner**,writer 为 0;耗时 9.2 秒。
- 关键点:"无答案"是显式终态而非编造;评测口径下此类题记 N/A,不静默进
  质量分母(§10.1)。
- 快照:`run_20260912_195950.json`,qid=`no_results`。

## 案例 5(补充):用户取消 —— 控制类终态(user_cancelled)

- 行为:取消请求受理后、persist 前做最后一次取消标志检查;writer 流式被
  中断时显式关闭上游 HTTP 流;`cancelled` 终态后草稿不作为内容暴露;重复
  取消与终态后取消被拒绝。
- 依据:SSE 与取消路径验收测试(`test_acceptance_1b.py` /
  `test_task_manager.py`);操作演示见 `docs/demo.md` 场景 4。

## 案例 6(补充):反思循环的两种结局 —— 有增量与无增量

反思的价值不是"再搜一遍",而是**针对证据缺口的定向追问**。但它**不是每题
都有增量**,当前基线里两种结局都能找到实例——两个都列出来。

**6a 有增量并成功收尾**:`compare_http` —— 比较 Python 官方文档中
`urllib.request` 与 `http.client` 两个模块的定位差异。

| 轮次 | 检索式 | 累计证据 |
|---|---|---|
| 第 1 轮 | `Python 官方文档 urllib.request http.client 模块定位 差异` | 3 条 |
| 反思判定 | 缺 `http.client` 的官方定义原句 | — |
| 第 2 轮 | `Python 官方文档 http.client 模块 定义 低层 HTTP 协议客户端` | **9 条(+6)** |

第 2 轮判定证据充分 → `stop_reason=evidence_sufficient`;9 条引用全部有效
(引用有效率 1.0);耗时 107.9 秒 / 28,863 tokens / 2 credits。

**6b 无增量、如实收尾**:`timely_latest` —— 截至 2026 年 docs.python.org
记录的最新 Python 稳定版本是什么?

第 1 轮拿到 9 条证据后反思判定需要"最新版本"的直接声明,追加检索式
`site:python.org/downloads "Python 3.14.7" release date stable`;
**该轮未带来任何新证据**,确定性条件(本轮无新增证据)判定收尾,
`stop_reason=no_new_evidence`。报告仍以既有 9 条证据产出,引用有效率 1.0。

- 关键点:**"反思没拿到新东西"不是异常,而是一个被如实记录的终态**。
  6a 与 6b 走的是同一条链路、同一套停止条件,只是证据缺口是否被填上不同。
- 当前基线中,第 1 次反思后仍有新增证据的题共 **9 道**(`fact_mdn401` /
  `compare_http` / `conflict_ft` / `fact_venv` / `compare_fetch_xhr` /
  `compare_logging_print` / `conflict_typing` / `timely_maint` / `noanswer_ml`)。
  其余题要么反思一轮无增量即收尾,要么因确定性条件直接收尾(根本没调用反思模型,
  如本页案例 4)。
- 一个能对上的数字:上述 9 道里,有 7 道一直找到轮次上限才停,`stop_reason=max_rounds`
  的 7 题**正是这 7 道**;另外 2 道(`compare_http` / `compare_logging_print`)
  在某一轮判定充分后正常收尾。也就是说 `max_rounds` 在本轮从 glm 时代的 2 题涨到
  7 题,不是链路卡住,而是**反思确实在持续拿到新证据、直到撞上轮次上限**。
