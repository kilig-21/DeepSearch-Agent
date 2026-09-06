# Orca Research 项目计划书

> **版本**: v1.5(2026-09-06)
> **修订记录**: v1.0 初稿 → v1.1 第一轮评审 → v1.2 第二轮评审 → v1.2.1 阅读层改本地 Defuddle → v1.3 落实第三轮评审(终止原因双路径、预算两级规则、SSE 恢复语义、Phase 1A 依赖修正、quote 严格化)→ **v1.4 第四轮验收评审打回后修复 P1-P7/F1-F4** → **v1.5 第五轮复验仍打回,第二轮修复 R1-R4 后三验通过,Phase 1B 正式闭环**(均见 §11)
> **状态**: 计划书冻结(三轮评审通过)。**Phase 0、1A、1B 已完成**(1B 于 2026-09-06 经外部评审两轮打回 + 修复 + 三验通过闭环,全过程见 §11)。**当前阶段:Phase 2**(开工前硬闸门:22 条 support 断言全量人工复核,§10.1;新执行会话从 §4 Phase 2 开始,遵守 §0 全部约束)
> **作者**: 用户 + Claude(实时 GitHub 数据调研 + 两轮交叉评审)

---

## 0. 给 Review Agent 的说明(必读)

### 0.1 本文档的来源

基于用户与 Claude 的方向调研对话写成,数据为 **2026-09-04 GitHub API 实时拉取**,非训练回忆。已经过两轮独立 Agent 评审(记录见 §11)。

### 0.2 用户背景(评审时请代入)

- 中文开发者,**Java / Python 双语言均可用**,前端 React + Next.js(用户自选)
- **尚未确定自己最擅长的领域**,首要目的:**积累完整的 AI 应用项目经验,作为求职/简历项目**
- 个人开发者,**一人业余开发(约每周 10~15 小时)**,第一个系统性 AI 应用项目
- 评审第一原则:**警惕过度设计**。要求是"完整、有讲头、能跑起来",不是"生产级"

### 0.3 已确认的决策链(除非有强数据理由,请勿整体推翻)

| # | 决策 | 依据 |
|---|------|------|
| D1 | 做 **Deep Search 信息研究助手**(AI 应用),不做 agent 框架 | 2026 年新爆款项目调研(见 §1.2) |
| D2 | 不做传统 RAG 知识库作为主体 | RAG 知识库赛道已固化;Deep Search 与 RAG 是不同赛道 |
| D3 | 后端 **Python**(FastAPI + LangGraph) | 用户在"求职价值 + 生态丰富度"权衡后选定 |
| D4 | 前端 **Next.js (React)** | 用户自选 |
| D5 | 副产品:**中文信息源 MCP Server** — 待验证假设 **H1**:在明确的中文研究场景下,提供少量稳定、授权清晰的来源 + 统一证据结构 + 可测量的检索质量,即可形成差异化。**验证方式(v1.2 收敛)**:先做 **1 个**适配器,固定研究流程与模型,与**纯 Web 基线**对照,比较相关证据命中、关键事实覆盖、引用支持、成本与获取成功率;改善则扩展,不改善则保留纯 Web,不先建成 3~5 个 | 第一轮评审证伪"中文生态空位"后重构 |
| D6 | 阶段化交付,MVP 最小化优先 | 防止个人项目烂尾 |

### 0.4 请重点评审的问题

见 **§11 评审记录**。第三轮评审(如发起)请核对:第二轮 [阻断] 项是否闭合(§11 第二轮落实表)、有无新引入的问题。

---

## 1. 项目背景与市场依据

### 1.1 一句话定义

**Orca Research**:输入一个问题,Agent 自动进行多轮网络搜索、网页阅读、交叉验证,最终产出一份**带证据链引用的中文研究报告**。对标 Perplexity Deep Research / Gemini Deep Research 的开源自建版。

### 1.2 数据依据(2026-09-04 GitHub 实时数据,分类已经两轮评审修正)

**(a) 框架层已红海,不做框架**

| 项目 | Stars | 备注 |
|---|---|---|
| CrewAI | 58.1k | |
| AutoGen (微软) | 60.8k | ⚠️ 2026-04 停更,转向 agent-framework |
| LangGraph | 41k | 生产编排主流,本项目采用 |
| OpenAI Agents SDK | 29.2k | 模型厂商下场,框架层受压 |
| Spring AI | 9.4k | Java 路线,本次不选 |

**(b) 2026 年新建爆款项目(验证"不过时";分类已修正)**

| 项目 | Stars | 创建 | 类型 |
|---|---|---|---|
| ponytail | 124k | 2026-06 | agent 技能/行为优化 |
| karpathy/autoresearch | 95k | 2026-03 | ⚠️ 修正:agent 自动修改训练代码、运行实验、比较指标,属**自动化实验 agent**,不能作为网络信息研究产品热度证据 |
| Agent-Reach | 77.9k | 2026-02 | agent 信息接入工具。⚠️ 修正:已覆盖部分中文平台(B站、小红书,发布记录含微信公众号) |
| last30days-skill | 61.2k | 2026-01 | 跨平台话题研究 skill |
| agent-browser (vercel) | 41.9k | 2026-01 | 浏览器自动化 CLI |
| OpenViking (字节) | 35.4k | 2026-01 | agent 记忆/上下文数据库 |
| TencentDB-Agent-Memory (腾讯) | 25.9k | 2026-04 | 团队级 agent 记忆 |

结论:2026 年新爆款集中于 **agent 工具/技能、长任务自动化、agent 记忆系统** 三类。Deep Research **产品形态**需求以 Perplexity / Gemini Deep Research 的产品成功 + `dzhng/deep-research`(19.6k★,单人极简实现)为准。

**(c) 反向验证(避开的赛道)**

- RAG 知识库:anything-llm 65.6k / quivr 39.5k / onyx 31.9k,头部固化,2026 年无新爆款 → 不做
- 简历匹配:头部 Resume-Matcher 28.3k 为 2020 年项目,天花板低 → 不做

**(d) 差异化:待验证假设(替代 v1.0"中文生态空位"说法)**

> **H1**:在明确的中文研究场景下,少量稳定、授权清晰的来源 + 统一证据结构 + 可测量的检索质量,即可形成差异化——以**来源质量与证据规范**取胜,而非平台覆盖数量。
> **验证方式(v1.2)**:先实现 **1 个**适配器,固定研究流程与模型,与纯 Web 基线对照(指标见 §10);判定规则在实验前预登记(§4 Phase 3),允许"不确定"结论;改善则逐个扩展,**逐个验证、逐个决定是否继续**。

### 1.3 个人目标(项目成功的定义)

1. 端到端跑通并**真实可用**(自己日常会用)
2. **分阶段积累并展示已验证能力**(v1.2 修订):简历呈现以已实现并经评测的部分为准,不以实现全部进阶功能(MCP/Memory)作为项目成功条件
3. 开源可展示:README + 评测结果 + 演示(录屏或在线)+ **可运行评测入口**(§10.4)

---

## 2. 整体架构

### 2.1 架构图

```
┌──────────────────────────────────────────────────┐
│                 浏览器(用户)                      │
│   Next.js 15 (App Router) + shadcn/ui + Tailwind │
│   自定义 useTask hook(POST 创建 + EventSource 订阅)│
└───────────┬──────────────────────▲───────────────┘
            │ POST 创建/取消         │ GET SSE 事件流(含 snapshot)
┌───────────▼──────────────────────┴───────────────┐
│               后端 FastAPI (Python 3.12)          │
│  ┌────────────────────────────────────────────┐  │
│  │  TaskManager(进程内, 单 worker)            │  │
│  │   task_id → 状态 / 事件环形缓冲 / 取消信号    │  │
│  │   任务元数据同步落库 tasks 表(v1.2)          │  │
│  └──────────────┬─────────────────────────────┘  │
│  ┌──────────────▼─────────────────────────────┐  │
│  │        LangGraph Agent 编排核心             │  │
│  │  planner → searcher → reader → merger      │  │
│  │        → reflector ─(条件边)→ searcher     │  │
│  │                     └──────────→ writer    │  │
│  └──────┬──────────┬──────────┬────────────────┘  │
│         ▼          ▼          ▼                   │
│   搜索工具      抓取工具     来源适配器(Phase 3)     │
│  (Tavily)    (read_url,   (RSS/官方文档/开放接口,   │
│               SSRF 防护)    先 1 个验证 H1)          │
│         │                                        │
│         ▼                                        │
│   LLM 适配:默认单模型 + 薄接口                    │
│                                                  │
│  存储: SQLite(tasks / reports / sources /        │
│        evidences / search_rounds)                │
│  记忆: 本地向量检索(P4, 可选)                     │
└──────────────────────────────────────────────────┘
```

### 2.2 技术栈明细

| 层 | 选型 | 理由 |
|---|---|---|
| 前端框架 | Next.js 15 + TypeScript | 用户选择 |
| UI 组件 | shadcn/ui + Tailwind | 快速搭出体面界面 |
| 流式渲染 | **自定义 SSE hook**(fetch POST 创建任务 + EventSource GET 订阅) | POST 返回 202 JSON(task_id),读取事件只用 EventSource;不引入 Vercel AI SDK,避免两套流式实现并存 |
| 后端框架 | FastAPI + uvicorn | 异步原生,适合 SSE 与并发抓取 |
| **执行模型** | **单 worker、同一时刻最多 1 个活动研究任务**(v1.2) | 多进程会各自持有 TaskManager,创建/订阅/取消可能落到不同进程;个人项目无并发需求,不为多任务引入队列 |
| Agent 编排 | LangGraph | 状态机/条件边/循环;Phase 1 线性图,Phase 2 加循环。注意默认更新语义是**覆盖**而非列表追加,跨轮累积字段由 merger 节点整体写回(§3.2) |
| HTTP 客户端 | httpx (async) | 并发抓取 |
| 网页转文本 | Jina Reader 免费档(配额限制见 §8)+ 自建兜底 | 省去自写解析 |
| 搜索 API | Tavily 免费档(计费规则见 §8);**备胎:`ddgs`**(DuckDuckGo,免费无 key 但非官方、随时可能失效,仅限开发调试) | 免费额度够个人开发;搜索为可插拔接口 |
| 网页转文本 | **Defuddle(本地 CLI,主力,v1.2.1)**;兜底分层:Python 侧 httpx+trafilatura → Jina Reader(云服务)→ 动态页 Playwright(重,按需引入,不进 MVP 主链路) | 本地提取**内容不出机器**(合规友好,见 §9.1)、无配额、已验证安装(0.19.3);Jina 仅在本地提取失败时兜底 |
| LLM | **日常 glm-5.3-flash / 高质量 glm-5.3(用户定版 2026-09-05)** + `LLMClient` 薄协议;两者实测可调(3.1~3.6s);⚠️ 5.3 为推理型模型,max_tokens 须覆盖思考段;价格以 [open.bigmodel.cn/pricing](https://open.bigmodel.cn/pricing) 为准 | 不做多厂商统一网关 |
| 数据库 | SQLite + SQLAlchemy | 零运维;任务/报告/来源/证据全部落库 |
| 部署 | 前端 Vercel / 后端本地或一台轻量 VPS | 成本≈0 |

### 2.3 关键设计决策及理由

| 决策 | 理由 |
|---|---|
| 前后端分离,AI 能力全在 Python | Agent 生态在 Python;Next.js 只做展示 |
| 任务接口:POST 创建 → GET 订阅 SSE | 原生 EventSource 只能用 URL 建连;研究任务持续数分钟,必须 task_id 支持重连/状态查询/取消 |
| **任务元数据持久化(tasks 表)(v1.2)** | 进程重启后才能把遗留 running 任务标为 interrupted 并关联回报告;内存环形缓冲只做事件补发,不做权威状态 |
| **单 worker + 单活动任务**(v1.2) | 见 §2.2;避免分布式任务管理问题 |
| SSE 而非 WebSocket | 单向推送流,自带重连语义,HTTP 友好 |
| LLM 单模型 + 薄接口 | 多厂商统一网关属过早设计 |
| 事件分发用进程内回调/队列 | 不引入独立事件总线 |
| MCP Server 独立包,先只做 stdio 单传输 | 一个客户端(Claude Desktop)验收即可;HTTP 后置 |
| 应用不强制绕行 MCP 进程 | 工具核心与 MCP 包装共享;应用直连,MCP 保留一条真实调用链做协议验证 |
| 来源"类型标签"而非"可信度分数" | 域名白名单打分制造虚假权威;透明标签 official/media/blog/ugc/paper |
| 抓取限速 + robots.txt + 完整合规边界 | 见 §9(robots.txt 不构成使用授权) |
| SQLite 起步 | 个人项目零运维 |

---

## 3. 核心流程设计(Agent 编排)

### 3.1 LangGraph 状态定义

```python
class ResearchState(TypedDict):
    topic: str                        # 用户原始问题
    task_id: str                      # 关联 tasks 表
    sub_questions: list[str]          # planner 拆解的子问题
    search_rounds: list[SearchRound]  # 每轮: query + 结果列表(去重)
    evidence: list[Evidence]          # 已确认证据池(merger 写回)
    candidate_evidence: list[Evidence]  # 本轮 reader 候选(v1.2)
    next_queries: list[str]           # reflector 产出(v1.2)
    round_no: int                     # 当前轮次, 首轮=1, 上限=3(v1.2, 替代 loop_count)
    stop_reason: StopReason | None    # 运行中为 None, 终态必有(§3.4)
    report_md: str                    # 最终报告(只引用 evidence_id)
    budget: Budget                    # 预算账户(§3.6, 分账)
```

> LangGraph 注意(v1.3 修正表述):同一 channel 的**顺序更新**默认是覆盖不是追加;**同一步内多个节点并行写入普通单值 channel 会触发 `INVALID_CONCURRENT_GRAPH_UPDATE` 错误**(而非静默覆盖),需先定义 reducer([官方说明](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE))。当前单 reader、单 merger 的顺序方案不受影响;`evidence` 池只由 merger 节点整体写回。

### 3.2 节点与流转

```
planner(拆解 2~4 个子问题, 生成首轮查询)
   → searcher(搜索 → 去重 → 选 top-N)
   → reader(单节点, 节点内部有限并发抓取+摘要,
        返回 candidate_evidence; 不直接发 note 事件,
        也不直接写 evidence 池)
   → merger(集中合并: URL 归一化去重; 多站转载保留各 URL,
        用 origin_group_id 标注共同来源; 分配任务内稳定
        evidence_id, 已有 ID 永不重排; 此节点发送 note 事件)
   → reflector(评估覆盖度/矛盾; 返回 next_queries 或放行)
        条件边: 有 next_queries 且满足 §3.5 → searcher
                否则 → writer
   → writer(只能引用 evidence_id; 后处理校验)
```

### 3.3 证据结构(核心)

> 评审要点:**URL 存在只能证明来源存在,不能证明它支持报告中的结论**。引用必须绑定到原文片段,并保证编号契约清晰。

```python
Evidence = {
    "evidence_id": "ev_001",     # 任务内稳定标识, 生成后永不重排
    "source_id":  "src_01",
    "url": "...", "title": "...", "domain": "...",
    "source_type": "official | media | blog | ugc | paper",
    "quote": "原文片段(≤200字, 供核对)",
    "origin_group_id": "...",    # 多站转载共用, 表达'同一来源'(v1.2)
}
```

**ID 与显示映射契约(v1.2)**:
- `evidence_id` 是任务内稳定标识;数据库约束 `UNIQUE(task_id, evidence_id)`
- 报告中的 `[n]` 由**确定性 `citation_map`** 映射到 evidence_id(`{"1": "ev_003", ...}`),n 只在展示层有意义
- 时间字段(`fetched_at`/`published_at`)只存在 `sources` 表,通过 source_id 联查,不在 evidences 重复

**来源快照不可变性(v1.2)**:
- `sources` 按**任务**保存抓取快照(URL+标题+哈希+时间),不再做全局 url UNIQUE——网页更新后新任务的快照是新记录,旧报告引用的快照永不改写
- 同一内容多站转载:各 URL 各自保留 source 记录(可溯源),共享 `origin_group_id`;**交叉验证的"独立来源 ≥2"按 origin_group_id 判定**,不按 URL 数量

**quote 真实性校验(v1.3 收紧)**:
- quote 必须能**定位到确定性清洗后的原文片段**;只允许预定义的空白/换行规范化,**不允许任何字符级改写**——防"该功能~~不~~支持离线"这类高相似度反义篡改(数字/百分比/版本号同风险)
- 近似匹配仅用于**定位候选位置**;最终入库必须**取回实际原文片段**,不保留模型改写的引文

**引用校验与收尾(v1.2)**:
- 报告生成后跑引用校验器:`[n]` 必须映射到存在且 quote 校验通过的 evidence
- 校验失败的处理是**修订、删除或降级对应断言**(降级=改写为"据来源 A 的标题,未经正文核实"并标注),**不能只删脚注留下无证据结论**
- `report_delta` 流式输出视为**草稿**;校验通过并落库后,前端用正式版本替换草稿

### 3.4 SSE 事件协议(任务生命周期 + 恢复语义,v1.2 闭合)

**接口契约**

```
POST /api/research {"topic": "..."}           → 202 {"task_id": "t_xxx"}
GET  /api/research/{task_id}/events           → SSE 事件流(Last-Event-ID 重连)
GET  /api/research/{task_id}                  → 状态快照(结构见下)
POST /api/research/{task_id}/cancel           → 202;后端实际停止后事件流发送终态
```

**状态机**:`running → completed | failed | cancelled`;进程重启后,启动时把 tasks 表中遗留 running 任务标为 `interrupted`(**草稿内容不可恢复,如实返回**;已落库报告可取)。

**两类判断分离(v1.3,修正 v1.2 的优先级错误)**:stop_reason 枚举表**不表示执行优先级**,按下述两类路径判断:
- **任务控制路径**(优先,直接决定终态):`user_cancelled` / `timeout` / `total_budget_exhausted` / `execution_error` / `process_interrupted`
- **研究路径**(只决定是否结束研究并尝试收尾):`evidence_sufficient` / `single_pass` / `budget_exhausted`(研究额度) / `max_rounds` / `duplicate_queries` / `no_new_evidence`
- **只有正式结果提交成功才标记 `completed`**;writer 执行失败时,即使此前证据充分也标 `execution_error`
- **报告写入与 tasks 的 completed/report_id 更新在同一个数据库事务内提交,提交后才发送 done**;最终状态一旦提交,后续事件不得覆盖

**状态快照结构(v1.2 补;v1.4 修正口径:进度为嵌套 `progress` 结构,与实现一致)**:

```json
{"task_id": "...", "status": "running|completed|failed|cancelled|interrupted",
 "round_no": 2, "sub_questions": [...],
 "progress": {"sources_read": 5, "evidence_count": 3},
 "stop_reason": null, "report_id": null, "report_md": "", "citation_map": {},
 "seq": 42}
```

> v1.4 补充:运行中且 writer 已产出片段时,`report_md` 为**已生成草稿正文**(非空串),与 `seq`/`progress` 对应同一时点(同一锁临界区内取全);cancelled/failed/interrupted 时草稿如实为空。

**事件格式**(每条含 `task_id`、服务端递增 `id`、`ts`):

```
id: 42
event: search
data: {"task_id":"t_xxx","ts":"...","round":1,"query":"...","results":[...]}
```

| 事件 | 说明 |
|---|---|
| `plan` | 拆解的子问题 |
| `search` | 每轮搜索的 query 与结果 |
| `reading` | 正在抓取哪篇(进度 n/N) |
| `note` | 单篇要点 + evidence_id(**由 merger 编号后发送**,v1.2) |
| `warning` | 局部失败:某篇抓取/摘要失败但任务继续 |
| `reflection` | 反思结论与下一轮查询 |
| `report_delta` | 报告正文流式片段(**草稿**) |
| `snapshot` | **(v1.3 扩充)** 恢复用完整快照:`{status, stop_reason, report_id, round_no, sub_questions, progress, report_md, citation_map, seq}` — 内容与 `seq` 对应**同一时点**;SSE 连接**不能**降级返回普通 JSON;刷新/缓冲失效时发送,客户端整体替换视图后**只应用更大 seq 的增量**,重复事件忽略 |
| `done` | 报告落库后发送;携 report_id、duration、token 成本、stop_reason |
| `task_failed` / `cancelled` | 业务终态(**不用 `error` 命名**,避免与 EventSource 网络错误事件混淆,v1.2) |

**stop_reason 枚举(v1.2 补全)** — 运行中为 `null`,终态必有:

| stop_reason | 类别 | 含义 |
|---|---|---|
| `evidence_sufficient` | 研究 | reflector 判定证据充分(仅 Phase 2 起可能出现) |
| `single_pass` | 研究 | Phase 1 单轮链路正常结束(**不冒用 evidence_sufficient**) |
| `budget_exhausted` | 研究 | **研究额度**耗尽(writer 预留与总时限仍充足)→ 停止研究,用已有证据走 writer |
| `total_budget_exhausted` | 控制(v1.3) | **任务总额度**耗尽 → 不再调用模型,返回已保存内容或程序生成的说明 |
| `max_rounds` | 研究 | 到达轮次上限——**只表示停止,不代表证据充分**,报告"局限性"必须说明 |
| `duplicate_queries` | 研究 | 新查询与历史近似重复,无新信息可搜 |
| `no_new_evidence` | 研究 | 本轮无新增有效证据 |
| `timeout` | 控制 | 总时长超限(初始 ≤8 分钟,§3.6) |
| `user_cancelled` | 控制 | 用户取消 |
| `execution_error` | 控制 | 程序异常(含 writer 失败) |
| `process_interrupted` | 控制 | 进程重启遗留 |

> 优先级语义(v1.3):**控制类优先于研究类**——取消/超时/异常走任务控制路径直接决定终态,不被"证据充分"覆盖;研究类只决定何时结束研究并尝试收尾。取消与完成竞争时**只允许提交一个最终状态**(原子状态转移,后到者丢弃)。

**心跳与缓冲**:
- 心跳注释帧为 `": ping\n\n"`(标准 SSE 注释行,客户端不可见),每 15~30 秒;心跳**缓解空闲超时,不代替关闭代理缓冲**——部署 nginx 时须配 `proxy_buffering off` / `X-Accel-Buffering: no`
- 业务事件以空行(`\n\n`)结束

**重连与恢复语义(v1.4 收敛游标口径;v1.3 统一"刷新丢前半段")**:
- **游标唯一来源:HTTP `Last-Event-ID` 请求头**(EventSource 自动重连时浏览器自动携带已接收的最大事件 id);**不存在 `?after=` 之类 URL 游标参数**——任何路径都不得"仅凭客户端 seq 请求增量"(v1.4)
- **普通断线(页面状态仍在)**:EventSource 自动重连携带 `Last-Event-ID` → 服务端校验其落在环形缓冲覆盖范围内(缓冲首事件 seq ≤ id ≤ 当前 seq)→ 从缓冲补发;无游标、零游标(`Last-Event-ID: 0`)或超出/超前缓冲覆盖 → **一律回退完整 `snapshot` 对齐**(v1.4)
- **刷新/视图丢失(页面正文已清空)**:新建连接**不带任何游标** → 服务端直接先发完整 `snapshot` 替换视图后再接增量——**不得仅凭 sessionStorage 保存的 seq 请求增量**(否则报告前半段丢失)。原生 EventSource 无自定义请求接口,新连接本就不携带 `Last-Event-ID`,服务端按"无游标"处理(v1.4 删除 v1.3 的 `?after=` URL 参数示例,与实现口径统一)
- **MVP 不持久化 token 级事件**;进程重启后草稿文本不可恢复,如实告知
- 客户端收到业务终态(`done`/`task_failed`/`cancelled`)**或显示终态的 snapshot**(completed/failed/cancelled/**interrupted**,v1.3)后主动 `close()`——防止重启后对 interrupted 快照无限重连;**断开 SSE 只取消订阅,不取消研究任务**(两者语义分离)

### 3.5 reflector 的确定性停止条件

进入下一轮搜索必须同时满足:预算未耗尽、未达轮次上限、新查询与历史**不近似重复**、上一轮**有新增有效证据**。任一不满足 → 按对应 stop_reason 终止。LLM 的"我觉得还不够"只能**建议**继续,不能越过确定性条件。

### 3.6 预算与并发控制(v1.2 闭合)

**分账制度(v1.3)**:LLM tokens(研究 + writer)/ Tavily credits / Jina tokens **分别计账**,不混算。**计账范围**:planner、reader、reflector、writer、引用修订——全部入账。

**初始限制值(v1.3 恢复 v1.2 缺失项;标注"待回填"的必须 Phase 0 回填,其余实测后可调)**:

| 限制 | 初始值(**Phase 0 实测回填,2026-09-05**;探针记录见 `apps/api/docs/probe_results.md`) |
|---|---|
| 总时长 | **≤ 8 分钟**(实测单任务全链路 ~15s,余量充足) |
| 抓取页数 | **≤ 12** |
| 每调用重试 | **≤ 2 次** |
| 单任务 LLM tokens | **≤ 50k**(**Phase 1A 实测校准**:线性链路在线题 7.8k~13.7k,余量充足;50k 上限保留给 Phase 2 反思循环) |
| 单页字符 | **≤ 100k**(实测最大单页 70k) |
| Jina 兜底单任务 token 上限 | 默认关闭;启用时 ≤ 500k 并校准 |
| 单调用超时 | LLM **180s**(**Phase 1A 校准,2026-09-05**:定版 glm-5.3 系列为推理型,思考段远超 4 系列的 4~6s,30s 实测 ReadTimeout)/ 抓取 **20s** |
| 最大重定向次数 | **3**(已在 `orca/fetch.py` 实现) |
| Tavily credits | ≤ 16 硬上限(含计费重试) |

**Tavily 口径**:默认 **Basic**(1 credit/次),3 轮 × 4 查询计划消耗 12 credits;**Advanced**(2 credit/次)入同一账户,16 上限下最多 8 次,**不保证完成 12 查询**;Reader/Jina/本地抓取不消耗 Tavily credits;MVP 不用 Tavily Extract(启用须单独入账)。

**两级预算规则(v1.3,消除"耗尽还能写报告"的矛盾)**:
- **研究额度耗尽**(搜索/摘要账空,但 writer 预留 + 总时限仍充足)→ 停止研究,用已有证据走 writer(`budget_exhausted`)
- **总额度或总时限耗尽** → **不再调用模型**,返回已保存内容或程序生成的说明(`total_budget_exhausted` / `timeout`)
- **writer 预留:每任务建立一次**,不随研究轮次重复扣留;各调用原子预占,完成后按实际 usage 结算

**并发与限速**:抓取并发 ≤5、搜索 ≤3;Jina 无 key 模式 **20 RPM**,按服务限速并处理 429(指数退避)——并发数 ≠ 满足 RPM。

### 3.7 不可信输入防护

- **SSRF**(`read_url`):
  - 仅 http/https;拒绝私网/回环/链路本地/**云元数据地址**(169.254.169.254 等);限制响应体大小与超时(**含解压后大小**)
  - **(v1.2)每跳重定向重新执行全套检查;连接使用已验证的地址**(检查后不再二次解析),保持正确 Host/TLS SNI/证书校验,防 DNS 检查与连接之间的 TOCTOU 绕过;禁止不受控自动重定向,设最大跳数
  - 覆盖 IPv6 与 IPv4 映射地址(`::ffff:x.x.x.x`);代理模式下明确由哪一方解析目标并按同一规则校验
  - **实现优先级(v1.2,诚实声明)**:若无法可靠实现上述任意 URL 抓取,则**先限制来源范围(白名单域名)或后置本地抓取兜底**,不以"有防护清单"宣称已解决
- **提示注入(可执行约束,v1.2)**:
  1. reader/writer 的模型调用**不授予任何工具**(网络/文件/代码执行);配置与密钥不进入提示词
  2. reflector 输出受 **schema + 条数 + 长度**约束的 `next_queries`;**Python 固定代码**决定调用哪个工具与目标策略,不交给模型自由发挥
  3. "资料不是指令"仅作辅助提示,**不作为保证**;评测集恶意网页题的通过条件单列:**越权工具调用数 = 0、测试标记未泄露、网页指令未被写成研究结论**
- **渲染安全**:报告 Markdown 清理危险 HTML;**MVP 禁止加载远程图片**(减少网页借图片 URL 触发额外请求的通道)

---

## 4. 功能规划与迭代路线(v1.2 重排)

> 原则:每期结束都有可演示产物。**工期(v1.3 两口径注明)**:**总工时预算 ≈ 120~180h**(Phase 0~1B 约 60~90h + Phase 2~3 约 60~90h);各阶段标题周数合计(约 10~15 周)为**典型排期**——两者口径不同(预算 vs 排期),按每周 10~15h 约 2~4 个月,非承诺,以 Phase 1A 实际进度校准。若求职时间线紧张,裁剪顺序见 Phase 3 说明。

### Phase 0 — 准备期(约 1 周)

- Monorepo:`apps/web`、`apps/api`、`packages/orca-mcp`(占位)
- 普通函数验证三依赖:搜索 API(Tavily + ddgs 备胎)、正文提取(Defuddle → trafilatura → Jina 兜底链,含 SSRF 防护雏形)、LLM 调用
- **确定允许抓取的来源集合(v1.3 前移)**:选定一小组普通 Web 来源(如官方文档站、维基百科等),逐站核对条款记入记录表——此集合供 Phase 1~2 主链路抓取,Phase 3 才增加专用适配器
- LLM 模型定版(实测价格与质量,回填 §8);**回填 §3.6 全部占位值**(LLM token/单页字符/Jina token 上限/单调用超时/最大重定向次数)
- **建立外部服务条款记录表(v1.2)**:实际采用的服务(Jina/Tavily/LLM)逐个记录条款链接、核验日期、发送内容、保留/训练设置、缓存与再发布限制(模板见 §9.1)
- **验收**:命令行跑通"搜索→抓一篇→摘要",记录实测成本;§3.6 与 §8 无占位符
- **结果(2026-09-05,已完成)**:✅ 全链路验收通过(~15s,1 credit + 2,757 tokens 免费模型);LLM 定版 **glm-4-flash**;提取主力定版 **trafilatura**(比 Defuddle 更干净);SSRF 单测 18/18;实测数据见 `apps/api/docs/probe_results.md`;来源集合见 `docs/SOURCES.md`

### Phase 1A — 线性链路 + 质量与安全基线(约 3~5 周,v1.2 拆分)

- **建立 tasks 表与最小任务记录(v1.3 前移)**:由 CLI 创建/完成任务——reports/sources/evidences/search_rounds 的 `task_id` 外键依赖它,不能等到 1B(TaskManager/HTTP/SSE 仍在 1B)
- 线性 LangGraph(无循环):planner → searcher → reader → merger → writer
- 证据链落地:Evidence 结构、**quote 原文片段定位校验(v1.3,§3.3)**、citation_map、引用校验器(断言修订/删除/降级)、来源类型标签
- 预算/超时/并发上限(§3.6 两级规则)+ 失败/警告路径(warning)
- **抓取范围约束(v1.3)**:仅抓取 Phase 0 确定的已核对来源集合;集合外站点**不抓正文,仅列为待核实链接**;搜索摘要**不得**作为"已阅读全文"的证据(引用时标注"据搜索摘要")
- 报告落库(SQLite,**报告写入与 tasks 状态更新同事务**,§3.4)+ 最简报告页(时间线可暂为日志输出)
- **10 题评测集**建立与离线基线(建题与评分表 → 跑链路 → 标注 → 存基线,顺序见 §10.1)
- **验收(可测口径,v1.3)**:① 引用 ID 有效率 100%(校验器强制);② 对关键事实断言标注 支持/部分支持/不支持,记录分子分母(部分支持计分规则见 §10.2);③ 无证据拒答与运行失败题**不静默出分母**,记 N/A 并记录任务结果;④ 预算熔断演示(把预算调小触发)
- **结果(2026-09-05,已完成)**:✅ 验收四条全过——① 全部有报告题引用 ID 有效率 1.0;② 断言引用支持率 **0.938**(支持 21/部分 3/不支持 0,AI 初标注明待人工复核);③ 3 题记 N/A 不静默出分母(白名单约束下诚实拒答 1 题、注入抓取失败 1 题、熔断演示 1 题);④ 熔断稳定触发(研究额度 100 < planner 实测 155 tokens → budget_exhausted,程序说明收尾)。**LLM 校准**:glm-5.3 系列始终思考(`thinking.type` 不支持 disabled,1210 错误),以顶层 `reasoning_effort="low"` 压制思考(实测 0 思考 token);单调用超时校准 180s;思考 token 计入分账。**10 题基线**:断言引用支持率 0.938 / 答案覆盖率 0.917 / 失败率 0/10 / 恶意注入安全 2/2 通过(单列)。136 tests。实测记录见 `apps/api/docs/probe_results.md`(T9~T11),评测产物见 `apps/api/eval/baselines/`

### Phase 1B — 任务接口与前端(约 2~3 周)

- TaskManager + tasks 表同步(**表与 CLI 记录已在 1A 建立**,v1.3);启动时遗留 running → interrupted
- 任务生命周期:POST 创建 → GET 订阅 SSE → 状态快照 → 取消;snapshot 事件;心跳;**两路恢复语义(§3.4 v1.3)**:Last-Event-ID 补发 / 刷新先完整 snapshot
- 前端:输入框 + 时间线(**事件归属映射**:plan/search/reading/note/reflection/warning → 时间线;report_delta → 报告区;done/task_failed/cancelled → 任务状态;snapshot → 恢复视图)+ 报告流式渲染(引用可点击)+ Markdown 清理 + 禁远程图片
- **验收(四个具体场景,v1.3)**:① **writer 执行中取消** → 终态 cancelled,不产生半截正式报告;② **额度耗尽** → 研究额度耗尽仍出报告 / 总额度耗尽不再调模型;③ **刷新后恢复完整正文**(snapshot 含前半段,不丢字);④ **进程重启后显示 interrupted** 且历史报告可取;另验:断线自动重连补发、报告与 tasks 状态同事务
- **结果(2026-09-06,已完成)**:✅ 四场景全部 PASS,经外部评审**两轮打回 → 修复 → 三验通过**正式闭环。并发正确性收口:终态发布/恢复判定/快照字段同一锁临界区;完成路径同事务条件提交防后到覆盖;`chat_stream` 传输层显式失败(error 帧/提前 EOF 不落半截报告);引用修订受总预算约束(耗尽走确定性降级)。**213 tests**(后端 pytest)+ 前端 vitest 9 + `tsc` 通过。评审全过程见 §11 第四/五/六轮。**遗留硬闸门**:22 条 support 断言全量人工复核 → Phase 2 开工前完成(§10.1)

### Phase 2 — 反思循环 + 首次发布(约 2~3 周)

- LangGraph 条件边:reflector 循环 + 确定性停止条件(§3.5);next_queries 流转
- 并发优化;成本日志(分账展示:tokens/credits/Jina)
- **评测扩到 20~30 题**;同资源上限对比"单轮 vs 反思循环"(口径见 §10.4);**评测入口:一条命令复现评测并输出结果表**
- **完成后发布 v0.9**:README、评测结果表、演示录屏、代表性案例(正常/取消/预算耗尽/来源失败);发布物只声称已实现能力,MCP/Memory 标为路线图
- **验收(可测口径,v1.2)**:至少一题因新增证据改善答案;**所有**运行均在预算内停止并记录 stop_reason(停止≠充分);"收敛"不作为验收词

### Phase 3 — 来源适配器 + MCP(约 2~3 周)

- `orca-mcp` 包(FastMCP,**仅 stdio**),工具:`web_search`、`read_url`、适配器
- **适配器策略(v1.2)**:第一批候选=授权清晰的 RSS、官方中文文档、机构公告、明确开放数据接口;**先做 1 个**,按 §1.2(d) 与纯 Web 基线对照验证 H1(判定规则预登记:在评测集上,关键事实覆盖与断言引用支持率的提升阈值,允许"不确定")
- **B站 = 待验证可选**:启用前核实具体接口、权限与条款;未通过则不实现;仅元数据不视为已读内容,字幕获取另算工作量
- MCP 验收:Claude Desktop 成功调用一条完整链路;应用保留直连
- **时间线紧张时的裁剪顺序(v1.2)**:若需提前交付,MCP 降级为路线图项(应用价值不依赖它),但**证据链与预算不可裁**
- **验收**:MCP 单客户端跑通;H1 有预登记判定下的数据结论(改善/不确定/收缩)

### Phase 4 — 记忆沉淀(独立排期,可选进阶)

- **首版只做资料缓存**(v1.2 收敛):抓取过的页面切片入库(`fetched_at`/`published_at`/`content_hash`/embedding 模型版本);**历史报告继续普通查阅,报告摘要的向量检索后置**;经验统计(域名抓取成功率等)仅作运营日志,不建第三条记忆流程
- 检索策略:先查本地记忆 → 判定增量缺口 → 只补搜增量
- 时效防线:"最新进展"类问题命中记忆仍须新鲜度核查;旧报告摘要只作背景上下文,不冒充新独立证据
- 缓存全文再分发边界:本地自用 ≠ 随开源仓库发布,发布前按许可清理
- **验收(口径,v1.2)**:同题**冷/热缓存对比**(记录缓存年龄),在质量指标不降低前提下,搜索量或 token 下降 ≥30%;迁移向量库依据实测指标(延迟/内存/过滤需求),无固定条数阈值
- 技术路线:SQLite 存 embedding,批量加载缓存矩阵再算相似度(避免逐行解码 BLOB);**裸向量体积 10k×1024维 float32 ≈ 41 MB(约 39.06 MiB)是下界**,实际内存含文本与对象开销

### 明确不做(Non-Goals)

- ❌ 多用户/账号系统、移动端、微服务、消息队列、独立事件总线
- ❌ 多任务并发执行与任务队列(单 worker 单活动任务)
- ❌ token 级事件持久化与逐字回放
- ❌ 多厂商 LLM 统一网关(只留薄接口)
- ❌ MCP HTTP 传输、多客户端同时适配(先 stdio + Claude Desktop)
- ❌ 应用强制绕行独立 MCP 进程
- ❌ 自托管搜索(SearXNG 仅未来备选——上游可能验证码/封锁,非零维护)
- ❌ 多平台适配器并行推进(先 1 个验证 H1,逐个决定)
- ❌ 报告远程图片自动加载
- ❌ 登录态平台数据爬取(合规红线)

---

## 5. 数据模型(概要,v1.2 修订)

```sql
-- Phase 1B
tasks(id PK, status,        -- running|completed|failed|cancelled|interrupted
      stop_reason NULL, report_id NULL,
      usage_json,           -- 分账: llm_tokens / tavily_credits / jina_tokens
      created_at, updated_at)

reports(id PK, task_id FK, topic, final_md, citation_map_json,
        stop_reason, config_json, token_cost, credits_cost,
        duration_s, created_at)

sources(id PK, task_id FK, url, title, domain, source_type,
        origin_group_id,    -- 多站转载分组
        content_hash, fetched_at, published_at)
        -- 注意: 不设全局 url UNIQUE(v1.2)——按任务存不可变快照,
        -- 网页更新产生新记录, 旧报告引用的快照永不改写

evidences(id PK, task_id FK, evidence_id, source_id FK,
          origin_group_id, source_type, quote, validated BOOL,
          UNIQUE(task_id, evidence_id))   -- 引用映射契约(v1.2)

search_rounds(id PK, task_id FK, round_no, query,
              result_count, credits_used, created_at)

-- Phase 4 追加(仅资料缓存)
memory_chunks(id PK, kind,              -- 仅 'material'(v1.2)
              content, embedding BLOB, embedding_model,
              source_id FK, created_at)
```

> 事件不持久化 token 级数据;TaskManager 内存环形缓冲仅用于补发,权威状态在 tasks 表。

## 6. API 设计(概要)

```
POST /api/research                     # 创建任务 → 202 {task_id}(落库 tasks)
GET  /api/research/{task_id}           # 状态快照(§3.4 结构)
GET  /api/research/{task_id}/events    # SSE 事件流(Last-Event-ID 重连; 心跳;
                                       #   缓冲失效发 snapshot 事件, 不降级返回 JSON)
POST /api/research/{task_id}/cancel    # 取消 → 202;实际停止后事件流发终态
GET  /api/reports                      # 历史报告列表
GET  /api/reports/{id}                 # 报告详情(evidences + sources 联查)
GET  /api/reports/{id}.md              # 导出 Markdown
# 本地数据清理:CLI 命令 `python -m orca cleanup`(v1.3: 不做 HTTP 接口;
#   须在后端停止后执行,避免清理中任务写回;范围: tasks/reports/sources/evidences/search_rounds/memory_chunks)
GET  /api/health
# Phase 3: MCP server 独立进程(stdio), 不走本 API
# 若未来公开部署: 加访问限制与费用上限, 重新评估对外合规(§9.1)
```

## 7. 前端页面规划

两个路由:

- **`/` 研究页**:大输入框(示例 chips)→ 时间线(事件归属:plan/search/reading/note/reflection/warning)→ 报告区(report_delta 草稿流式 → 落库后取正式版替换;引用 `[n]` 点击跳原文,悬停卡片后移 Phase 2 后)→ 任务状态(done/task_failed/cancelled);取消按钮;断线自动重连;刷新经 snapshot 恢复
- **`/history` 历史页**:报告卡片(标题/时间/stop_reason/分账成本);**v1.2 后移项**:美化、引用悬停来源卡片、逐字打字机效果——时间线保留阶段事件与最终报告即可
- 技术要点:自定义 `useTask` hook(fetch POST + EventSource GET);**恢复分两路(v1.3,§3.4)**:普通断线靠浏览器自动携带的 Last-Event-ID 补发;刷新/视图丢失时新建连接由服务端**先发完整 snapshot**——不得仅凭 sessionStorage 的 seq 请求增量;收到业务终态**或显示终态的 snapshot** 主动 close()(断开 ≠ 取消);Markdown 经 rehype-sanitize 清理;**禁远程图片自动加载**
- 复用 shadcn/ui:Accordion(时间线)、Card(报告)、Skeleton(加载)

## 8. 成本估算(v1.2:数据已核验 + 口径明确)

**公式**:`月成本 = 正式任务数 × 平均任务成本 + 开发/评测重跑成本 + 托管成本`

已核验数据(**核验日期 2026-09-05**,出处链接):

| 项 | 核验结果 | 出处 |
|---|---|---|
| Defuddle | 本地 npm CLI,免费无配额;本机已验证:v0.19.3(Node v24.16.0) | 本机实测(Phase 0 前置) |
| Tavily | 免费档 1000 credits/月;Basic Search 1 credit/次、Advanced 2 credits/次;Search 与 Extract 分开计费 | [docs.tavily.com/documentation/api-credits](https://docs.tavily.com/documentation/api-credits) |
| 任务耗用算例 | Basic:3轮×4查询=12 credits → `floor(1000/12)=83` 任务/月;Advanced 24 credits **超出 16 上限,不适用**。预算分账:若给开发/评测预留 500 credits,正式任务容量 `floor(500/12)=41` 个 | 自算(公式附 §3.6) |
| Jina Reader(v1.2.1 降为兜底) | 新 key **一次性** 10M 免费 tokens(非每月重赠);无 key Reader 20 RPM;兜底用量小,可不注册,需要时再办 | [jina.ai/reader](https://jina.ai/reader/) |
| Claude Sonnet 5 | 输入 $2/M、输出 $10/M;算例:每任务输入 10 万+输出 1 万 ≈ **$0.30/任务**(未含搜索抓取) | [platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| LLM(定版 2026-09-05) | **日常 glm-5.3-flash / 高质量 glm-5.3(用户定版)** — 实测可调,延迟 3.1~3.6s;⚠️ 5.3 为推理型模型,max_tokens=100 时 content 为空(思考即耗尽),接入时须给足输出上限;早期探针:glm-4-flash 3.9s/70 tokens(已被替换)、glm-4.5-flash 不采用(22s);价格以 [open.bigmodel.cn/pricing](https://open.bigmodel.cn/pricing) 为准 | 实测(apps/api/docs/probe_results.md) |
| VPS | ¥20~40/月为**预算假设**(未指定商家/规格/续费条件) | — |

**预算结论(2026-09-05,模型定版 glm-5.3 系列后)**:LLM 费用取决于 5.3 系列定价(**待核定价页**;若 flash 档免费则 ≈ ¥0,另注意推理型模型思考 token 也计费,单任务 token 消耗高于 4 系列);30~50 正式任务 + 等量重跑的搜索量 720~1200 credits **可能超 Tavily 免费档**,需分账预留。**月成本目标 ≈ ¥0~40**(仅托管/超额 credits),Phase 1A 成本日志上线后以实测校准。

配套:调用上限熔断 Phase 1A 实现;Jina 20 RPM 需限速 + 429 退避;三账分开(LLM/Tavily/Jina)。

## 9. 风险与合规

### 9.1 合规边界(四条 + 服务条款记录,v1.2 修订)

| 边界 | 说明 |
|---|---|
| **robots.txt ≠ 使用授权** | robots 只表达爬虫访问规则(RFC 9309),不能替代平台条款、API 授权与内容许可 |
| **执行机制(v1.3 明确)**:不笼统"逐站核对" | Phase 0 **确定一小组已核对来源集合**供 Phase 1~2 抓取;集合外站点**不抓正文,仅列为待核实链接**(不是"允许抓单篇");Phase 3 适配器逐站核条款后扩充;搜索摘要不得冒充"已阅读全文"的证据 |
| **引用 ≠ 再分发授权(v1.2 措辞修正)** | 总结与短摘录**需结合引用目的、比例、署名及对原作正常使用的影响判断**(《著作权法》第二十四条附适用条件);**链接与字数限制本身不构成授权或免责**;缓存全文长期保存、随仓库发布需按许可单独判断 |
| **个人信息处理** | 减少采集无关个人信息;**本地清理 CLI**(`python -m orca cleanup`,后端停止后执行,§6)代替"一键删除后台";**数据流向(v1.2.1 收敛)**:正文提取本地完成(Defuddle),内容仅在 LLM API 调用时出机器,Jina 兜底须在 README 明示且默认关闭 |
| **本地自用 ≠ 公开服务** | 求职展示优先录屏/只读报告;若开放实时接口,加访问限制与费用上限,并重新评估对外义务 |

**外部服务条款记录表(v1.2 新增)**:对实际采用的服务逐个记录——条款链接、核验日期、发送内容、保留/训练设置、缓存与再发布限制。已知要点(核验日期 2026-09-05):

| 服务 | 条款要点 | 链接 |
|---|---|---|
| Jina(兜底) | 要求用户对输入材料拥有处理权利,不替用户核实来源合法性 | [jina.ai/legal](https://jina.ai/legal/) |
| Tavily | 平台条款涉及第三方条款遵守、输入权利、敏感信息限制、部分输入/输出使用安排 | [tavily.com/terms](https://www.tavily.com/terms) |
| LLM(Claude 等) | 具体账号/服务区域/使用政策;**价格可核实 ≠ 本账号可合法使用该服务** | [anthropic.com/legal/commercial-terms](https://www.anthropic.com/legal/commercial-terms) |

默认评测只用公开且许可合适的非敏感材料。**本地 LLM 只消除发送给 LLM 服务商的环节,不自动解决原始抓取、复制与再发布问题。**

### 9.2 技术风险

| 风险 | 等级 | 应对 |
|---|---|---|
| SSRF(含 DNS 检查与连接之间的 TOCTOU) | **高** | §3.7 全套防护 + **诚实降级路径**(实现不可靠→限制来源范围/后置本地抓取) |
| 网页提示注入 | **高** | §3.7 三条可执行约束;评测集恶意网页题单列通过条件(越权调用=0) |
| 单人项目烂尾 | **高** | 阶段化交付(1A/1B 拆分);Phase 2 后先发布;Phase 4 可选;时间线紧时 MCP 降路线图 |
| 搜索 API 免费额度不足 | 中 | 预算分账熔断(1A);开发期备胎 ddgs(免费但非官方,失效不意外);SearXNG 仅未来备选 |
| LLM 幻觉/引用错位 | 中 | §3.3 证据链 + quote 原文匹配 + 校验器(修断言不只删脚注) |
| 报告引用失效 | 中 | sources 不可变快照保存来源元数据与哈希,**quote 存于 evidences 表**(v1.3 修正措辞),失效仍可展示 |
| LangGraph 学习曲线 | 中 | Phase 1 线性图(节点即普通函数);注意 channel 覆盖语义 |
| token 成本失控 | 低 | §3.6 分账预算 + 成本日志 |
| DNS 污染/代理环境(**Phase 0 实测发现**) | 中 | 直连下 wikipedia 解析出假地址 `2001::1`,safe_fetch 公网校验**按设计拦截**;Phase 1A 落实 §3.7 代理模式解析权;来源集合标注可达性(docs/SOURCES.md) |
| Jina/搜索 429 限速 | 低 | 限速 + 指数退避(§3.6) |

---

## 10. 评测与展示(v1.2 补口径)

### 10.1 评测集

- 规模:Phase 1A 建 10 题(基线)→ Phase 2 扩至 20~30 题
- 题型:事实查询、多来源比较、冲突信息、时效性、无答案、抓取失败、恶意网页指令
- **建立顺序**:建题与评分表 → 实现 Evidence 与 citation_map → 跑完整链路 → 标注 → 存基线(引用支持类指标依赖证据链,先建题不先标注)
- 失败题与无答案题**不静默出分母**:记 N/A 并记录任务结果
- **保存**:模型 ID、提示词版本、参数、评测时间、原始任务轨迹

### 10.2 核心指标(v1.2 采用标准名称 + 自定义口径)

| 指标 | 自定义口径(写进评测脚本,可复核) |
|---|---|
| **断言引用支持率(v1.3 改名)** | 本指标按**断言**统计而非逐条引用,故不称"引用精确率":每条关键事实断言标注 支持/部分支持/不支持;**计分:支持=1、部分支持=0.5、不支持=0**(写进脚本),同时报告三档原始分布 |
| **引用完整性 Citation completeness** | 需要**外部证据**的关键断言中,得到充分引用支持的比例(断言清单预定义) |
| **答案覆盖率 Answer coverage** | 对**预先定义的必答要点**评分,按**全部题目**报告(v1.3),不按模型自生成的子问题评分 |
| 冲突处理 | 单列统计:正确识别数、解释口径差异数、错误合并数(不并入总分平均掉) |
| 成本与耗时 | 每任务输入/输出 tokens、Tavily credits、Jina tokens、费用、端到端耗时;**失败率分母 = 全部任务**(v1.3),N/A 只豁免对应指标、不豁免失败率 |

> 概念注记:Groundedness 指"答案是否受提供证据支持",**不等于事实正确率**(错误来源也可被忠实引用)。评测思路参考 ALCE([arxiv.org/abs/2305.14627](https://arxiv.org/abs/2305.14627)),采用其引用评测思想 + 本文的人工简化口径。
> **安全题单独判定**(恶意网页题:越权工具调用数=0、测试标记未泄露、指令未入结论),**不与质量分平均**。

### 10.3 求职展示的"杀手级案例"

带明确时间截点的问题(如比较某产品不同版本的限制变化),展示链条:

> 问题与截止时间 → 单轮漏掉的事实 → 补搜查询及原因 → 新旧证据片段 → 报告结论变化 → 增量成本与耗时

**简历模板(数字必须来自实测)**:

> 在 N 道中文研究题上,以相同模型和资源上限对比单轮检索与反思循环,断言引用支持率由 A 提升至 B,平均成本变化 C;支持证据溯源、预算停止及取消恢复。

**至少保留一个"继续搜索未改善,因此停止"的案例**——展示停止条件,不只展示成功。

### 10.4 评测有效性控制(v1.2 新增)

- **混淆变量控制**:搜索结果与正文版本、语言/地区、排序参数;**冷缓存 vs 热缓存**(是否复用摘要);缓存键包含查询与相关参数,**未命中不得伪装成"搜索无结果"**
- **"同预算"定义 = 相同资源上限、各自分配资源**(如均 ≤16 credits);单轮固定 4 次 vs 循环 12 次的对比属于"产品默认模式对比",**不得解释为纯粹的反思效果**
- 两种结果分开保存:**离线固定材料**(回归与编排验证)+ **在线配对实验**(真实搜索收益,交替执行两种策略并保存工具结果)

---

## 11. 评审记录

### 第一轮评审(2026-09-05,评审 Agent ①)

**总体结论:修改后通过。** 五项修改(修正事实归类、统一任务契约、质量前移 Phase 1、B站降级、工期费用重算)已在 v1.1 落实——第二轮评审确认"主要要求已纳入正文",其中任务契约类要求经第二轮深化。

### 第二轮评审(2026-09-05,评审 Agent ②)

**总体结论:修改后通过。** 核心发现:任务恢复缺持久化依据、stop_reason 不覆盖全部执行路径、证据编号与数据模型未统一、预算耗尽收尾矛盾、SSRF 存在 TOCTOU 缺口、合规表述过度确定、Phase 1 超载。

**v1.2 落实状态**:

| # | 第二轮发现 | 落实位置 | 状态 |
|---|---|---|---|
| 1 | 任务恢复缺持久化(tasks 表)、单 worker 限制 | §2.1/2.2、§3.4、§5 tasks 表 | ✅ |
| 2 | stop_reason 补全(single_pass/duplicate_queries/timeout/user_cancelled/execution_error/process_interrupted)+ 判定顺序 + 终态唯一 | §3.4 | ✅ |
| 3 | snapshot 事件(不降级返回 JSON)+ 刷新不继承游标 + task_failed 命名 + 断开≠取消 | §3.4、§7 | ✅ |
| 4 | 证据 ID 映射契约(任务内稳定 ID + UNIQUE(task_id,evidence_id) + citation_map)+ 来源不可变快照 + origin_group_id | §3.3、§5 | ✅ |
| 5 | quote 原文匹配校验;无效引用→修断言而非只删脚注;report_delta 为草稿 | §3.3 | ✅ |
| 6 | 预算:Basic 12/上限16 口径统一、分账、writer 预留、预算耗尽不再调模型、占位值回填机制 | §3.6、§4 Phase 0、§8 | ✅ |
| 7 | SSRF TOCTOU(每跳重验证、已验证地址连接、IPv6/映射)+ 诚实降级路径 | §3.7 | ✅ |
| 8 | 提示注入三约束可执行化 + 恶意题单列判定 | §3.7、§10.2 | ✅ |
| 9 | 合规:引用表述按法定条件修正、外部服务条款记录表、已核对来源集合机制、清理命令 | §9.1、§6 | ✅ |
| 10 | Phase 1 拆 1A/1B + 展示美化后移 + 工时口径统一(120~180h ≈ 8~18 周) | §4 | ✅ |
| 11 | Phase 4 收敛为首版仅资料缓存 | §4 Phase 4、§5 | ✅ |
| 12 | H1 先 1 个来源对照 + 判定规则预登记 | §1.2(d)、§4 Phase 3 | ✅ |
| 13 | 指标标准化(citation precision 等)+ 口径可复核 + 混淆变量控制 | §10.2/10.4 | ✅ |
| 14 | 评测入口一条命令 + 轨迹保存 | §4 Phase 2、§10.1 | ✅ |
| 15 | §3.4 快照结构补齐、§8 补官方链接与核验日期 | §3.4、§8 | ✅ |

第二轮评审确认的正确项(v1.1 已对,无需改):POST+GET 不存在读流混用;`: ping` 注释帧语法;裸向量 41 MB 计算;merger 节点设计成立;章节交叉引用全部正确。

### v1.2.1 修订(2026-09-05,非评审驱动)

- 用户指出其机器已装有 **Defuddle CLI**(0.19.3,网页正文提取,本地运行,输出 Markdown)——与 Jina Reader 同层工具但**内容不出本机**
- 阅读层主力改为 **Defuddle(本地)**,兜底链:trafilatura → Jina(云,默认关闭,README 明示)→ Playwright(动态页)
- 收益:§9.1"内容出本地"的合规顾虑在主力链路上消除;无 Jina 配额压力
- **用户注册清单从 3 个 key 减为 2 个**(Tavily、DeepSeek);Jina key 变为可选项(兜底需要时再办)
- 涉及:§2.2、§8、§9.1、Phase 0

### 第三轮评审(2026-09-05,评审 Agent ③)

**总体结论:修改后通过,可开始 Phase 0。** 确认 v1.2 主要架构可定案(任务表、单 worker、证据 ID 映射、不可变快照、预算分账、writer 预留、评测对照);发现 5 项 [必须修改](集中在**异常路径与阶段依赖**,不需要新架构)+ 5 项非阻断建议。

**v1.3 落实状态**:

| # | 发现 | 落实位置 | 状态 |
|---|---|---|---|
| 1 | stop_reason 优先级写反(取消会被"证据充分"覆盖)→ 拆分**任务控制路径/研究路径**两类判断 + 报告与状态同事务提交 + 最终状态不可覆盖 | §3.4 | ✅ |
| 2 | 预算矛盾(研究额度 vs 总额度未分)+ v1.2 丢失的三项限制(8 分钟/12 页/重试 2 次)恢复 + 回填清单扩充(Jina token/单调用超时/最大重定向)+ writer 预留每任务一次 | §3.6、§3.4、Phase 0 | ✅ |
| 3 | SSE 刷新恢复丢报告前半段 → 两类恢复语义(断线补发/刷新先 snapshot)+ 删"首条事件补发"(EventSource 无业务上行)+ snapshot 字段扩充 + 终态快照也 close + seq 衔接规则 | §3.4、§7 | ✅ |
| 4 | Phase 1A 依赖倒置 → tasks 表与最小任务记录前移 1A(CLI);已核对来源集合前移 Phase 0;集合外"不抓正文仅列链接";搜索摘要不得冒充全文证据 | §4 Phase 0/1A/1B、§9.1 | ✅ |
| 5 | quote"近似匹配"可放过反义篡改(不支持→支持)→ 仅允许空白规范化,入库取**实际原文片段** | §3.3 | ✅ |
| 6 | [建议] 评测口径:失败率分母=全部任务、部分支持计分(1/0.5/0)、按断言统计改名"断言引用支持率"、答案覆盖率按全部题 | §10.2 | ✅ |
| 7 | [建议] `DELETE /api/data` 改 CLI + 后端停止后执行 | §6、§9.1 | ✅ |
| 8 | [建议] 工时"总工时预算 vs 阶段排期"两口径注明 | §4 | ✅ |
| 9 | [建议] "sources 保存 quote"措辞修正(quote 实际在 evidences) | §9.2 | ✅ |
| 10 | [建议+评审员自我纠正] LangGraph 并行写单值 channel 触发 `INVALID_CONCURRENT_GRAPH_UPDATE` 而非静默覆盖 | §3.1 | ✅ |

**Phase 1B 契约验证场景**(评审建议,已写入 §4 Phase 1B 验收):writer 执行中取消 / 额度耗尽 / 刷新后恢复完整正文 / 进程重启 interrupted——**用运行结果证明落地,不再扩展抽象设计条款**。

### 第四轮验收评审(2026-09-06,评审方人工;**结论:打回**)

Phase 1B 交付物(后端 API/SSE/前端 + 测试)经评审确认 11 项发现,其中 7 项后端(P1-P7)、4 项前端(F1-F4),全部确认为有效缺陷。核心问题:**预算检查滞后于抓取动作、取消无法在流式过程中生效、运行中 snapshot 不带正文、SSE 游标路径过多且可"仅凭客户端 seq 请求增量"、终态发布非原子、完成路径可被后到的 completed 覆盖已取消任务、前端 sanitize schema 传参崩溃且把 evidence_id 当 href**;另有 8 类测试覆盖缺口(含既有验收测试"等任务完成才连接"的假覆盖)。

**v1.4 修复记录(2026-09-06)**:

| # | 评审发现 | 修复 | 落实位置 | 状态 |
|---|---|---|---|---|
| P1 | 预算检查滞后:reader 循环内逐篇抓取/摘要前不重查预算 | 篇间与摘要前双重检查(控制类即时终止;研究额度耗尽→保留已有候选证据走 writer 收尾);测试断言多页任务中途耗尽后实际模型调用次数不超预算 | `graph.py` reader、`test_graph.py` | ✅ |
| P2 | writer 非流式,取消只能等整段生成完 | `llm.chat_stream`(httpx SSE + include_usage,流式不重试)→ writer 逐片段 emit `report_delta(draft=true)`,片段间经取消检查点;保留"校验→落库→正式版"阶段;校验失败修订后发 replace 帧 | `llm.py`、`graph.py` writer、`cli.py` | ✅ |
| P3 | 运行中 snapshot `report_md` 恒空串 | snapshot 在同一锁临界区内一次取全 `draft_md`/进度/`seq`(同一时点);running 且有草稿时 `report_md` 为已生成正文;修订 replace 帧整体替换草稿而非追加 | `task_manager.py` snapshot、`_track_progress` | ✅ |
| P4 | SSE 游标路径过多:`?after=` URL 参数、`Last-Event-ID: 0` 可凭客户端 seq 从头补发 | 删除 `?after=` 路径,游标唯一来源 `Last-Event-ID` 头;零游标/无游标一律先发完整 snapshot;带游标须落在缓冲覆盖范围内否则回退 snapshot;`resume_plan` 决策与 seq/缓冲读取同一锁临界区;`events_after` 读加锁 | `api.py`、`task_manager.py` | ✅ |
| P5 | 终态提交(标志/状态/seq/缓冲)分散,终态事件可读前标志已可见(SSE 可能提前关闭丢帧) | `_record_terminal` 全程持锁:terminal 标志+状态+seq+缓冲+订阅推送同一临界区一次完成 | `task_manager.py` | ✅ |
| P6 | 完成路径无条件提交,"cancelled 后 completed 覆盖"可复现 | `complete_task_with_report` 改同事务条件更新(`UPDATE ... WHERE status='running'`,原子防 TOCTOU);未抢到终态提交权→报告随事务回滚返回 None,worker 丢弃后到结果不发 done | `db.py`、`task_manager.py`、`cli.py` | ✅ |
| P7 | §3.4 两处口径与实现不符(快照示例扁平 `sources_read`;`?after=` URL 参数示例) | §3.4 快照示例改嵌套 `progress` 并补 `report_md` 同一时点说明;重连语义删 `?after=` 示例,游标唯一来源 `Last-Event-ID` | PLAN.md §3.4(v1.4) | ✅ |
| F1 | 前端 sanitize schema 传参错误(`tagNames: {img: null}` 类型错误)→ 渲染抛 TypeError | schema 基于 `defaultSchema` 改写(`tagNames` 允许列表剔除 `img`);组件测试:普通 Markdown/危险 HTML/img 三路径,断言 img 剔除且零网络请求 | `report-view.tsx`、`tests/report-view.test.tsx` | ✅ |
| F2 | hook 按 payload seq 去重,不读服务端 `id:` 字段 | 序号一律读 `MessageEvent.lastEventId`,任何视图更新前统一过滤重复/过期序号(snapshot 除外);hook 测试:真实事件 ID 驱动,重复帧零渲染变化、时间线不缺项、伪造 payload seq 无效 | `use-task.ts`、`tests/use-task.test.tsx` | ✅ |
| F3 | report-view 把 evidence_id 当 href | `[n]` 经详情数据 `evidences.source_id → sources` 联查真实 URL(`lib/citations.ts`);`[n]→evidence_id` 数据契约保留 | `report-view.tsx`、`use-task.ts`、`history/page.tsx` | ✅ |
| F4 | completed snapshot 自带正文不被利用;详情失败静默停留草稿 | completed snapshot 自带正文直接作正式版;详情失败显示重试入口(`retryFinalReport`),不静默 | `use-task.ts`、`app/page.tsx` | ✅ |

**测试补齐情况**(评审列 8 类,1-6 全覆盖 + 7 组件级):

| 类 | 场景 | 测试 |
|---|---|---|
| 1 | writer 流式中已收到多个片段,取消后不落正式报告 | `test_cancel_during_writer_stream_receives_deltas_then_no_report` |
| 2 | running snapshot 正文与 seq 一致;刷新后逐字无丢失无重复 | `test_snapshot_running_includes_draft_consistent_with_seq`、`test_refresh_recovery_draft_plus_deltas_verbatim` |
| 3 | reader 中途研究/总额度耗尽,断言后续模型调用次数 | `test_reader_rechecks_research_budget_between_pages`、`test_reader_rechecks_time_before_summarize` |
| 4 | 零游标、缓冲溢出、snapshot 与事件发布竞争 | `test_zero_last_event_id_falls_back_to_snapshot`、`test_after_query_param_is_deleted_falls_back_to_snapshot`、`test_ahead_last_event_id_falls_back_to_snapshot`、`test_snapshot_then_replay_gapless_under_publish_race` |
| 5 | 终态发布窗口与取消/完成竞争(数据库状态与事件一致性) | `test_completed_persist_loses_race_to_cancel`、`test_terminal_record_atomic_under_concurrent_events`、`test_terminal_event_visible_before_flag_when_subscribed` |
| 6 | 真实 SSE 事件 ID 驱动的 hook 去重与时间线完整性 | `tests/use-task.test.tsx`(6 用例) |
| 7 | Markdown 实际渲染三路径 + 远程图片零请求 | `tests/report-view.test.tsx`(3 用例) |
| 8 | 真实进程强杀重启 interrupted | Phase 1B 块 8 已用真实 uvicorn 演示(`test_scenario_4_restart_interrupted_and_history` 覆盖逻辑路径) |

**假覆盖修正**:场景①事件流断言改为缓冲内游标走补发路径(原 `?after=0` 路径已删);`test_running_task_snapshot_has_draft_progress` 改为 writer 已产出片段时连接并断言 snapshot 正文非空(原实现等价于"未断言草稿正文")。

**自验结果**:后端 pytest 202 passed(含新增 P1-P6 与测试类 1-5);前端 vitest 9 passed(F1-F4 与测试类 6-7)+ `tsc --noEmit` 通过。

### 第五轮复验评审(2026-09-06,外部强模型评审;**结论:仍打回**)

对 v1.4 修复轮复验(真实 uvicorn + HTTP/SSE + SQLite + 离线替身,0 真实 API 调用):11 项中 7 CLOSED(P3/P6/P7/F1-F4)、**3 NOT_CLOSED(P1/P4/P5)、1 REGRESSION(P2)**;四个主场景全部 PASS,但完整契约下复现四个阻断:

| # | 机制 | 复现证据 |
|---|---|---|
| R1(P5 未闭合) | 写端 `_record_terminal` 原子,但 SSE 端**锁外裸读** `terminal_recorded`/`seq`——worker 在"置标志→事件入缓冲"之间被 GIL 切出时,读者可见中间态 → `frames=[]` 提前关流漏发终态帧 | 受控调度:terminal_recorded=true、seq=1 时 SSE 已关闭,终态随后才成为 seq=2 |
| R2(P4 未闭合) | `resume_plan` 判定与 `events_after` 取数分属两个临界区,间隙生产者把游标挤出环形缓冲 → 补发跳帧,无检测无兜底 | 容量 3 缓冲,游标 2 实收 6/7/8,丢 3-5 且无 snapshot |
| R3(P1 未闭合) | writer 引用修订在 settle 之后调用,无任何预算检查 → 总额度耗尽仍调模型 | 上限 600 实耗 750(研究 450 + writer 150 + 修订 150) |
| R4(P2 回归) | `chat_stream` 不识别上游 `error` 帧、正常 EOF(无 `[DONE]`)不校验、usage 缺失静默按 0 → 半截/空报告以 completed 落库 | error 帧落库空报告;提前 EOF 落库半截报告,均 completed |

测试质量批评:`test_terminal_event_visible_before_flag_when_subscribed` 为"先完成发布再读"的假并发测试;`chat_stream` 传输解析零测试(writer 测试直接替换迭代器绕过解析层)。

### 第二轮修复(v1.5,2026-09-06)与第六轮三验(**通过,Phase 1B 正式闭环**)

| # | 修复 | 落实位置 | 三验证据 |
|---|---|---|---|
| R1 | 新增 `drain(task_id, sent)`:事件副本+终态标志+seq+缺口判定**同一锁临界区**返回;api.py 循环消费 drain,删除全部 runtime 裸读 | `task_manager.py` drain、`api.py` SSE 循环(e3d32ed) | 受控暂停精确注入"标志已置/事件未入"窗口:窗口内 0 帧 0 EOF,释放后 done 帧收全才关 ✅ |
| R2 | `resume()` 判定与首批取数同临界区;`drain` 每批缺口检测(缓冲首条 seq > sent+1 → gap)→ SSE 转**完整 snapshot 重对齐**后继续,不跳帧补发;快照字段抽取共用避免嵌套锁 | `task_manager.py` resume/drain、`api.py` gap 分支(9ed3ea2) | maxlen=3 注入真挤出 → 下一帧即 snapshot 重对齐,后续 id 递增无跳帧 ✅ |
| R3 | 修订前检查 `total_exhausted() or out_of_time()` → 耗尽走 `degrade_citations` 确定性降级 + warning 事件,不调模型;五类 LLM 调用点预算前置全部盘点确认 | `graph.py` writer 修订分支(cb00c22) | 600/600 恰打穿 → 修订零模型调用、无效引用降级"(未经正文核实)"、token_cost=600≤600、stop_reason 保持 ✅ |
| R4 | `error` 帧 → `LLMError`;无 `[DONE]` → `LLMError`;usage 缺失 → warning+按 0 记账(不静默);writer `finally: gen.close()` 关底层 HTTP 流 | `llm.py` chat_stream、`graph.py` writer 流式(1da05c8) | 集成五路径:error 帧/提前 EOF → task_failed 且 reports 0 行;正常流分账正确;usage 缺失告警记账;取消触发上下文关闭 ✅ |

**回归**:四场景(流式中取消/两级预算耗尽/中途刷新拼接/真进程强杀重启)+ Last-Event-ID 补发/零/过期/超前/409/心跳 + 事务回滚/条件提交全部 PASS。

**测试**:213 passed(202 + 11);新增测试经假覆盖标准逐条审查——`test_drain_never_sees_flag_without_terminal_event` 先自检裸读窗口真实存在再断言修复;`test_sse_realigns_...` 用 ASGI send 消息桥实现真增量流(绕开 TestClient/ASGITransport 整体缓冲的"事后回放"陷阱)。

**三验遗留(不阻断,纳入 Phase 2 开工收尾)**:① 端到端重对齐测试 docstring 注明"R2 并发防线依赖此测试";② 前端文档补"重对齐点可能不含缺口内中间进度"语义;③ 手工 curl 类测试注意 httpx `trust_env`(系统代理会截胡 127.0.0.1;项目代码已 `trust_env=False`,不受影响)。

---

## 12. 附录:对话中确认的关键事实

- 用户语言能力:Java、Python 均可;前端自选 React + Next.js
- 用户诉求:"做一个 AI 应用拓宽项目能力 + 有项目经验",接受"应用 + MCP 工具并行"
- 用户担心:"做了一堆结果是过时的、不适用的" → 方向判断附实时数据,并经两轮评审修正
- 项目名:Orca(工作目录 `C:\Users\Lenovo\Desktop\ALLCODE\Orca`)
- 投入:业余,约每周 10~15 小时;预期总工期 2~4 个月(Phase 0~3)
- 评审:两轮均"修改后通过";v1.2 闭合第二轮全部 [阻断] 项
