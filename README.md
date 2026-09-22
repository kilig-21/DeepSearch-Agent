# DeepSearch

白名单来源、逐条引用可核实、超限即熔断且停止原因可追溯的 Deep Search 研究助手。

LangGraph 状态图驱动:规划 → 检索 → 阅读 → 证据合并 → 反思循环(可多轮)→ 写作,全程 SSE 流式输出,任务与证据同事务落库,事后逐条追溯。

> 当前版本:v1.0(Phase 0-3 已闭环)。本文档只声称已实现并经测试验证的能力;未实现项一律列入路线图。

## 已实现能力

- **引用可核实**:报告中每条 `[n]` 引用对应一条证据(quote 原文片段 + 来源 URL + 抓取时间);引用校验 → 一次修订 → 程序化降级兜底,编号越界在链路上被拦截
- **反思循环**(Phase 2):证据合并后由 reflector 决定继续检索或收尾;停止条件是**确定性的**(预算/轮次/无新增证据在调用反思模型之前判定,候选查询的近似重复在生成后比对),LLM 只能建议、不能越过
- **两级预算**(尽力预防 + 终检如实标记):研究额度 = 总 LLM 额度 − writer 预留;每次模型调用前按剩余额度收紧 `max_tokens`,剩余不足最小可用输出即不调用、走程序降级;总额度/总时限/页数/credits 各自熔断。预算约束是**尽力预防**而非 tokenization 级硬上限——prompt 实际 tokens 以字符数估算,单调用边界可能存在极小越限,由落库前终检如实标记(`over_budget`),不静默。每个任务以 `stop_reason` 如实记录停止原因(控制类与研究类两档,§3.4)
- **白名单来源**:仅抓取来源集合内站点正文(docs/SOURCES.md);集合外结果只列为"待核实链接",不作为证据
- **恶意网页防护**:网页内指令不执行;canary + 指令特征自动判定(未泄露/未执行/未越权调用),评测安全题单列
- **SSE 流式与断线恢复**:游标续传 + 环形缓冲;游标被挤出时服务端转完整 snapshot 重对齐
- **成本分账**:LLM tokens 按研究/writer 分列,Tavily credits、Jina tokens 独立入账;终态事件、数据库、`orca cost` 一条命令三路可查
- **评测集 27 题**:事实/比较/冲突/时效/无答案/抓取失败/注入/预算熔断八类;离线注入固定材料可复现;`python -m orca.eval --compare` 一条命令跑单轮 vs 反思循环对比

## 架构

```
apps/api   FastAPI + LangGraph 后端(orca 包:graph/eval/task_manager/cli)
apps/web   Next.js 15 + React 19 前端(SSE 消费、报告渲染)
docs       来源白名单(SOURCES.md)、代表性案例(cases.md)、演示录屏脚本(demo.md)
```

链路:`planner → searcher → reader → merger → reflector ─(条件边)→ searcher|writer`;`reflect=False` 时退化为单轮线性链(对比模式)。

## 快速开始

环境:Python ≥ 3.12,Node.js ≥ 20。

```bash
# 1. 后端
cd apps/api
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Windows;Unix 用 .venv/bin/pip
# 配置 .env(至少两项):
#   DEEPSEEK_API_KEY=...  DeepSeek 模型(OpenAI 兼容端点)
#   TAVILY_API_KEY=...    网页搜索(Tavily)
#   FETCH_PROXY=http://...  可选,网络代理
.venv/Scripts/python -m uvicorn --factory orca.api:create_app --port 8000

# 2. 前端(另开终端)
cd apps/web
npm install && npm run dev        # http://localhost:3000

# 3. 或仅用 CLI 跑一次研究(无需前端)
.venv/Scripts/python -m orca research "Python 3.13 有什么新特性?"
.venv/Scripts/python -m orca cost --last   # 单任务成本小结(分账)
```

预算上限可用环境变量覆盖(`ORCA_BUDGET_*`):默认 tokens 100k(其中 writer 预留 20k,研究额度 80k)、Tavily credits 16、页数 12、总时长 8 分钟。取值依据见 `PLAN.md` §3.6 与 `apps/api/docs/probe_results.md` T12。

## 评测

```bash
cd apps/api
.venv/Scripts/python -m orca.eval --compare   # 全部 27 题;在线题单轮/反思循环配对对比
```

- 结果:`eval/baselines/run_<ts>.json`(全量轨迹与证据快照)+ `table_<ts>.md`(结果表)
- 口径:断言引用支持率(支持 1 / 部分 0.5 / 不支持 0)、答案覆盖率、失败率(**分母=全部任务**)、安全题单列;失败与无答案题不静默出分母(记 N/A)
- 标注类指标由 AI 双轮标注 + 第三方独立终审产生(未经人工全量复核),分歧清单与裁定见 `eval/baselines/`(不静默出分)

最近一次全量评测(`run_20260912_195950.json`,**DeepSeek 时代基线**,生产默认反思模式):27 任务(18 道在线题 + 9 道离线题)**全部完成、失败率 0.0%**;stop_reason 分布:evidence_sufficient 9 / no_new_evidence 9 / max_rounds 7 / total_budget_exhausted 2。预算口径:27 行可查实耗(含两题熔断演示入口即停、实耗 0)均 ≤ 各自行上限(守门测试逐行断言)。消耗分列:在线 tokens 667,931 / credits 43;离线(检索不联网)tokens 41,022 / credits 12;合计 708,953 tokens / 55 credits,单题最大 70,012。有报告的 21 行引用有效率全部 1.0;3 道注入题自动判定全 pass(未泄露 canary / 未执行网页指令 / 无越权工具调用)。逐条证据与事件轨迹见快照文件。

**标注类指标(DeepSeek 时代,2026-09-16 标注)**:答案覆盖率 **0.9113**(56.5/62);断言引用支持率(严格口径 quote-only,AI 双轮独立标注 + 第三方外部强模型终审)= **0.8777**(122/139)。标注流程与分歧裁定见 `eval/baselines/annotations_20260912_v1.json` 与 `divergences_20260912_v1.md`。

> ⚠️ **不要据此声称"DeepSeek 优于 glm-5.3"**:在两者共有的 20 道题上,宽口径 **glm 0.9672 > DeepSeek 0.9202**,严格口径 **DeepSeek 0.8571 > glm 0.8279** —— **优劣方向随标注口径翻转**;且两版标注者不同(glm 版为 AI(GLM),本版为 Claude Code agent)、报告平均长度差 38%(977 vs 1568 字符),差异中混有标注者效应与产出风格差异。本档只报当前口径下的绝对值,不做跨模型优劣结论。
>
> 下方 **0.8238 是 glm 时代(2026-09-07)口径**,作为历史记录保留,不代表当前模型。

Phase 2 基线(**glm-5.3 时代**,`run_20260907_010146.json`,2026-09-07):27 任务,26 完成 + 1 失败(writer 阶段 LLM 读超时,记录 `execution_error`;该行生成于失败分账修复 `bfd4dd0` 之前,**成本未知**——修复后的失败落账路径由测试与守门证明);stop_reason 分布:evidence_sufficient 13 / no_new_evidence 9 / max_rounds 2 / total_budget_exhausted 2 / execution_error 1。消耗分列:在线 tokens 223,703 / credits 25;离线(检索不联网)tokens 21,410 / credits 10。有报告的 20 行引用有效率全部 1.0。断言引用支持率(严格口径 quote-only,AI 双轮标注 + 第三方独立终审,未经人工全量复核)= **0.8238**(100.5/122);pass1 宽口径初标 0.9672 仅为初标参考,定版以终审为准(分歧行清单与裁定表见 `eval/baselines/`)。

单轮 vs 反思循环的配对对比(`run_20260906_final.json`,45 行)为**初步观察**,不构成策略等效或反思无效的统计证明:该快照跨提示词/参数版本且含 3 行补跑,预算行为为修复前口径,仅作方向性参考;严谨配对需同参数版本重跑(口径见 PLAN.md §10.4)。

Phase 3 来源适配器对照实验(H1,预登记 `apps/api/eval/H1_PREREGISTRATION.md`,N=8 严格口径 quote-only):在 docs.python.org/zh-cn/ 做 1 个来源适配器与纯 Web 基线对照。结论**收缩方向**——断言引用支持率 79.55%→76.19%、答案覆盖率 68.18%→38.64%、证据命中 49→74、平均 LLM tokens +163.6%;核心缺陷=适配器检索相关性不达标(token 子串匹配无 IDF,高频词命中无关页面)。三面定性:零 credits/白名单域名/补纯 Web 盲区为正面,成本劣化与无关证据为负面(N=8 不构成统计证明)。MCP 按裁剪条款降级为路线图。详见 PLAN.md §11 第十轮。

## 测试与验证

后端 `apps/api/tests/`:**23 个测试文件 / 5,622 行 / 281 个测试函数**(pytest 参数化后 **301 个用例**),对应 `orca/` 的 4,380 行源码;前端 `apps/web/tests/`:2 个文件 / 9 个用例(vitest)。

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest -q   # 301 passed
cd apps/web && npm test                                # 9 passed
```

测试比源码多,在这里是**刻意的**——上面"已实现能力"里每一条,都是"没有测试就等于没有"的类型:

| 对外声称 | 由什么证明(节选) |
|---|---|
| 引用可核实 | `test_check_report_flags_out_of_range`(编号越界)、`test_degrade_replaces_invalid_citation_without_deleting_claim`(降级不删论点)、`test_revise_report_falls_back_to_degrade`(修订失败兜底)、`test_uncited_evidence_not_in_map` |
| 两级预算与熔断 | `test_research_calls_cannot_touch_writer_reserve`(研究调用碰不到 writer 预留)、`test_page_budget_fuse`、`test_timeout_by_injected_clock`(注入时钟,不真等 8 分钟)、`test_max_output_tokens_clamps_to_remaining`、`test_min_usable_output_threshold_exported` |
| 预算"如实标记"而非静默 | `test_usage_snapshot_includes_over_budget`、`test_runner_failed_row_records_nonempty_usage`、`test_writer_stream_settles_known_usage_on_llm_error`(LLM 出错也落账) |
| 网页注入防护 | `test_safety_flags_canary_leak` / `..._directive_written_as_conclusion` / `..._unauthorized_tool_intent` 三条自动判定,外加 `test_offline_inject_question_runs_and_checks_safety` 走完整链路(离线固定材料,不联网) |

**守门测试**:`tests/test_eval.py` 里有一组测试直接对 `eval/baselines/` 的冻结产物逐字段断言——`test_latest_baseline_full_coverage`(27 题全部完成)、`test_latest_baseline_all_rows_within_budget_cap`(逐行实耗 ≤ 行上限)、`test_final_adjudicated_annotation_score`(glm 时代口径)与 `test_final_adjudicated_annotation_score_deepseek`(当前口径)。**本文档与 PLAN 里的评测数字都能从这些测试复算**:只改产物不改测试会红,只改数字不改产物也会红。

这组守门测试本身做过**变异检验**(人为篡改冻结产物,确认测试确实会失败);其中一个覆盖缺口正是这样被发现的,并已补上 pass2 汇总断言。

## 安全边界

- 来源白名单硬约束:集合外域名不抓正文(代理与 DNS 异常环境下的局限见 docs/SOURCES.md)
- 网页注入防护三条件自动判定 + 人工复核清单;防线路径有离线固定材料评测覆盖
- 搜索摘要不作为已读证据;一切结论必须溯源到抓取正文中的 quote

## 路线图(未实现)

- **MCP 接入**:外部工具/数据源协议(已评估——H1 对照后按裁剪条款降级,应用价值不依赖 MCP)
- **Memory**:跨任务记忆(未实现)
- 来源集合扩展、多模态、并行搜索分支

## 文档索引

- `PLAN.md` — 计划书(§0 决策链 / §3 架构 / §10 评测口径)
- `docs/SOURCES.md` — 来源白名单与许可
- `docs/cases.md` — 代表性案例:四类终态各一组真实数据,可在快照里逐条复核
- `docs/demo.md` — 演示录屏脚本(含口播数字速查)
- `apps/api/docs/probe_results.md` — 组件实测记录
- `apps/api/eval/baselines/` — 评测运行快照、标注与复核清单
