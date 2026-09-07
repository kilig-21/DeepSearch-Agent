# Orca Research

白名单来源、逐条引用可核实、超限即熔断且停止原因可追溯的 Deep Search 研究助手。

LangGraph 状态图驱动:规划 → 检索 → 阅读 → 证据合并 → 反思循环(可多轮)→ 写作,全程 SSE 流式输出,任务与证据同事务落库,事后逐条追溯。

> 当前版本:v0.9(Phase 2)。本文档只声称已实现并经测试验证的能力;未实现项一律列入路线图。

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
docs       来源白名单(SOURCES.md)、演示脚本
```

链路:`planner → searcher → reader → merger → reflector ─(条件边)→ searcher|writer`;`reflect=False` 时退化为单轮线性链(对比模式)。

## 快速开始

环境:Python ≥ 3.12,Node.js ≥ 20。

```bash
# 1. 后端
cd apps/api
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Windows;Unix 用 .venv/bin/pip
# 配置 .env(至少两项):
#   ZHIPU_API_KEY=...     GLM 模型(智谱开放平台)
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

预算上限可用环境变量覆盖(`ORCA_BUDGET_*`):默认 tokens 50k、Tavily credits 16、页数 12、总时长 8 分钟。

## 评测

```bash
cd apps/api
.venv/Scripts/python -m orca.eval --compare   # 全部 27 题;在线题单轮/反思循环配对对比
```

- 结果:`eval/baselines/run_<ts>.json`(全量轨迹与证据快照)+ `table_<ts>.md`(结果表)
- 口径:断言引用支持率(支持 1 / 部分 0.5 / 不支持 0)、答案覆盖率、失败率(**分母=全部任务**)、安全题单列;失败与无答案题不静默出分母(记 N/A)
- 标注类指标由 AI 初标 + 人工复核产生,复核清单见 `eval/baselines/`(不静默出分)

最近一次全量评测(`run_20260907_010146.json`,Phase 2 修复后基线,生产默认反思模式):27 任务(18 道在线题 + 9 道离线题),26 完成 + 1 失败(writer 阶段 LLM 读超时,记录 `execution_error`;该行生成于失败分账修复 `bfd4dd0` 之前,**成本未知**——修复后的失败落账路径由测试与守门证明);stop_reason 分布:evidence_sufficient 13 / no_new_evidence 9 / max_rounds 2 / total_budget_exhausted 2 / execution_error 1。预算口径:26 行有数值实耗均 ≤ 各自行上限(守门测试逐行断言,含熔断演示题入口即停、实耗 0),1 行失败成本未知。消耗分列:在线 tokens 223,703 / credits 25;离线(检索不联网)tokens 21,410 / credits 10。有报告的 20 行引用有效率全部 1.0。逐条证据与事件轨迹见快照文件。

单轮 vs 反思循环的配对对比(`run_20260906_final.json`,45 行)为**初步观察**,不构成策略等效或反思无效的统计证明:该快照跨提示词/参数版本且含 3 行补跑,预算行为为修复前口径,仅作方向性参考;严谨配对需同参数版本重跑(口径见 PLAN.md §10.4)。

## 安全边界

- 来源白名单硬约束:集合外域名不抓正文(代理与 DNS 异常环境下的局限见 docs/SOURCES.md)
- 网页注入防护三条件自动判定 + 人工复核清单;防线路径有离线固定材料评测覆盖
- 搜索摘要不作为已读证据;一切结论必须溯源到抓取正文中的 quote

## 路线图(未实现)

- **MCP 接入**:外部工具/数据源协议(未实现)
- **Memory**:跨任务记忆(未实现)
- 来源集合扩展、多模态、并行搜索分支

## 文档索引

- `PLAN.md` — 计划书(§0 决策链 / §3 架构 / §10 评测口径)
- `docs/SOURCES.md` — 来源白名单与许可
- `apps/api/docs/probe_results.md` — 组件实测记录
- `apps/api/eval/baselines/` — 评测运行快照、标注与复核清单
