# Phase 0 探针实测记录(2026-09-05)

## ⭐ 定版变更(2026-09-05,用户决定)

- 日常模型:glm-4-flash → **glm-5.3-flash**;高质量:glm-4.6 → **glm-5.3**
- 实测:两模型均可调,延迟 **3.13~3.59s**
- ⚠️ 关键工程发现:**5.3 为推理型模型**——max_tokens=100 时 content 为空(token 全部用于思考)。Phase 1A 的 LLM 调用必须给足 max_tokens(或配置思考预算),且**思考 token 计入计费与预算分账**
- 价格未实测:以 [open.bigmodel.cn/pricing](https://open.bigmodel.cn/pricing) 为准,Phase 1A 成本日志上线后校准
- 下方为 Phase 0 探针历史数据(4 系列),保留作回归参照



> 环境:Windows 11 / Python 3.13.14 / Node v24.16.0 / 用户全局代理开启

## T3 搜索(Tavily Basic + ddgs 备胎)

| 后端 | 延迟 | 结果数 | 成本 | 备注 |
|---|---|---|---|---|
| Tavily Basic | 3.75~5.54s(含代理) | 5 | 1 credit | 中文查询质量好,docs.python.org 官方页排第 2 |
| ddgs 备胎 | 6.98s | 5 | 0 | 本次可用;按计划仍仅作开发备胎 |

## T4 正文提取(同一批 URL 对比)

| 页面 | Defuddle CLI | trafilatura(经 safe_fetch) | 结论 |
|---|---|---|---|
| docs.python.org/3/whatsnew/3.13 | 228k 字符 / 2.27s | **108k 字符 / 5.57s** | trafilatura 更干净 |
| developer.mozilla.org(JS 页) | 9.1k(含翻译横幅) / 2.02s | **2.3k / 2.96s** | trafilatura 明显更净 |
| zh.wikipedia.org | 超时(10s) | FetchBlocked(DNS 污染,见下) | 均不可用 |

**主力结论:trafilatura 为提取主力**(Python 侧、走统一 SSRF 防护、输出最干净);
Defuddle 为次选(对结构复杂页仍有价值);Jina 保持兜底(默认关闭)。

**真实发现(已记录到计划书):**`zh.wikipedia.org` 在直连环境被 DNS 污染解析出
`2001::1`,被 safe_fetch 的公网校验**按设计拦截**——计划书 §3.7 预留的
"代理模式下由谁解析"问题在 Phase 0 实际出现。Phase 1A 按计划处理(代理模式
解析权归属);此前 wikipedia 降为"需代理环境"备注来源。

**工程坑:** Windows 下 subprocess 读子进程 UTF-8 输出必须显式
`encoding="utf-8"`(默认 GBK 会 UnicodeDecodeError)。

## T5 GLM 模型对比(231 字样本 → 3 句话摘要)

| 模型 | 延迟 | tokens(prompt+completion) | 结论 |
|---|---|---|---|
| **glm-4-flash** | **3.95s** | 171+70 | ✅ **日常定版**:快、精炼、免费 |
| glm-4.5-flash | 22.01s | 171+300(撞上限截断) | ❌ 不采用:过慢且啰嗦 |
| glm-4.6 | 5.71s | 171+300(撞上限截断) | 高质量备选:延迟可接受,单价以官网定价页为准 |

探针 max_tokens=300 偏小导致两个模型截断,属探针参数问题,不影响定版结论。

## T8 验收全链路(问题:"Python 3.13 有什么新特性?")

```
[1 搜索] 5 条, 5.54s, 1 credit(Tavily Basic)
[2 抓取] docs.python.org/zh-cn/dev/whatsnew/3.13.html → 提取 69,946 字符, 5.07s(trafilatura + safe_fetch)
[3 摘要] glm-4-flash, 4.64s, 2,757 tokens
```

摘要三句话全部来自原文、无编造;总耗时 ~15s,总成本 **1 credit + 2,757 tokens(¥0,免费模型)**。

---

## T9 LLM 思考控制(Phase 1A 回填,2026-09-05;定版 glm-5.3 系列)

Phase 0 定版的 glm-4-flash 已按用户决定更换为 **glm-5.3-flash(日常)/ glm-5.3(高质量)**。
推理型模型实测(探针逐项验证):

| 实测项 | 结果 |
|---|---|
| 思考段吃满输出配额 | reader 任务 max_tokens=4096 → completion_tokens=4096、reasoning_tokens=4094,**content 为空** |
| `thinking.type` 取值 | `disabled` / `low` / `high` / `max` **全部被拒**:HTTP 400 code=1210「该模型始终思考，不支持关闭思考」 |
| 顶层 `reasoning_effort="low"`(OpenAI 风格兼容) | **唯一实测将思考压到 0 的方式**:同一任务 382 tokens 完成(此前爆 4096),3 条 quote 全部定位成功 |
| `thinking:{"effort":"low"}` / `thinking_budget` | 200 被接受但思考段照常消耗(388/617 tokens),无压制效果 |
| 单调用超时 | §3.6 原回填 30s(基于 4 系列 4~6s)实测 ReadTimeout,**校准 180s** |

**落库结论**:`LLMClient.chat(reasoning_effort=...)`;机械任务(planner / reader / 引用修订)
传 `"low"`,writer 保留默认思考(推理任务需要)。思考 token 计入 usage 与预算分账。

## T10 端到端冒烟(Phase 1A 线性链路)

- 问题:「Python 3.13 有什么新特性?」→ `single_pass`,**14,475 tokens + 1 credit,46s**
- 6 条证据(docs.python.org 中英文档各 3),全部通过 quote 原文定位校验,citation_map 完整,
  报告引用编号全部有效
- **预算熔断演示**:研究额度 100 tokens(< planner 单次实测 155)→ searcher 入口即
  `budget_exhausted`,writer 以程序说明收尾,全程 **2.5s**;程序说明如实写「研究额度已耗尽」
  而非误导性的「未找到证据」

## T11 10 题基线(评测集,详见 `apps/api/eval/baselines/`)

> 基线对 `run_20260905_201120.json` + `annotations_20260905_v2.json`(v2:结果行带
> evidences 快照,quote 经 run 文件或 orca.db 可回溯;旧版 185400 缺快照已删除)。

| 指标 | 值(计分规则经 `orca/eval/annotate.py`,可复核) |
|---|---|
| 断言引用支持率(AI 初标,待人工复核) | **0.958**(支持 22 / 部分支持 2 / 不支持 0) |
| 答案覆盖率(预定义必答要点) | **0.889**(covered 14 / partial 4 / missed 0) |
| 失败率(分母 = 全部任务) | **0/10** |
| 引用 ID 有效率 | **1.0**(7 道有报告题;校验器 + 降级兜底强制) |
| 恶意注入安全判定(单列,不与质量分平均) | **2/2 通过**(越权调用=0 / canary 未泄露 / 指令未入结论) |
| 冲突处理(单列) | 识别 1(自由线程性能数据 40% vs 1~8%) / 解释 1 / 错误合并 0 |
| 每任务成本 | 在线题 4.6k~13.4k tokens + 1 credit(6 credits);离线注入 2.8k~3.6k tokens |

N/A 3 题(不静默出分母,§10.1):fact_mdn401(白名单约束下正确拒答,程序说明列出
集合外待核实链接)、fetch_fail(注入抓取全失败)、budget_fuse(熔断演示)。

## T12 DeepSeek 重校准(2026-09-12;定版由 glm-5.3 系列换为 deepseek-v4-flash/pro)

背景:换 DeepSeek(commit `dc43cdd`)后,config 的 budget/timeout 与 graph 的
`max_tokens` 仍是 glm 时代的回填值,故重新探针。探针脚本:`scripts/probe_llm.py`
(A 档位基线 / B `reasoning_effort` 对照 / C 小 `max_tokens` 行为);
形态探针为临时脚本,均按 `graph.py` 的 reader/writer prompt 结构照抄。

**A 结论:DeepSeek v4 是推理型,思考段与正文共享 `max_tokens`(与 glm 同型)**

| 形态 | 模型 | effort | 上限 | reasoning | completion | finish | 延迟 |
|---|---|---|---|---|---|---|---|
| reader(构造小页) | flash | low | 4096 | 3554 / 2591 / 2180 | 3831 / 2787 / 2336 | stop ×3 | 17.1 / 13.4 / 11.5s |
| writer(8 条证据) | pro | 不传 | 16384 | 3084 / 4690 | 3550 / 5257 | stop ×2 | 60.6 / 77.4s |
| 构造小 `max_tokens=100` | flash | 不传 | 100 | — | 100 | length | 正文 **0 字符** |

**B 结论:`reasoning_effort="low"` 生效,但压制幅度远小于 glm**

同 prompt、`max_tokens=3000`(两组都自然收尾,避免配额截断污染对照):

| 组 | reasoning_tokens | 均值 |
|---|---|---|
| 不传 | 1300 / 1537 / 1617 | 1485 |
| 传 `"low"` | 775 / 698 / 1389 | 954(**-36%**) |

⚠️ 方法论记录:首次对照用 `max_tokens=1200`,两组均 `finish=length`——**截断下
reasoning 由配额封顶而非模型自主选择,该对照无效**,差点得出"参数不生效"的错误
结论。改用 3000 让两组自然收尾后结论反转。glm 时代"传 low 即压到 0"(382 tokens
完成)的结论**不能迁移到 DeepSeek**。

**C 关键实测:真实白名单页上 4096 会被思考吃穿(直接复现 glm 的教训)**

`safe_fetch` 直连抓取(不走 Tavily,0 credit),正文截断到 `_MAX_PROMPT_CHARS`
=15000 字符后按 reader prompt 结构组装:

| 页面 | prompt | reasoning | completion | finish | 正文 | 单页合计 |
|---|---|---|---|---|---|---|
| `docs.python.org/zh-cn/3/whatsnew/3.13.html` | 7053 | 3409 | 3639 | stop | 506 字符 | **10692** |
| `docs.python.org/zh-cn/3/using/cmdline.html` | 7454 | 4096 | 4096 | **length** | **0 字符** | 11550 |

→ 上限 4096 时 **1/2 页被吃穿**(与 glm 时代 `_WRITER_MAX_TOKENS` 8192 被吃穿同型)。

**D prompt 估算的保守度实测**:`_below_min_output` 用 `len(prompt文本)` 估 tokens
(设计上刻意保守)。真实页 prompt 15303 字符 → 实际 7053 tokens,**高估约 2.2x**
(中文网页含 URL/代码/标点等 ASCII,约 2.2 字符/token)。此为**有意的安全边际**
(§3.6 调用前约束),本次不改;但它意味着额度利用率约 54%,调预算时须知。

**落库结论(回填 `config.py` / `budget.py` / `graph.py` / `llm.py`)**

| 参数 | glm 值 | DeepSeek 值 | 依据 |
|---|---|---|---|
| `MIN_USABLE_OUTPUT` | 1024 | **4096** | C 表:成功那页 completion=3639;失败那页烧掉 4096 配额、正文 0 |
| `_READER_MAX_TOKENS` | 4096 | **8192** | C 表:4096 在真实页被吃穿(与 glm writer 8192→16384 同一处置) |
| `_WRITER_MAX_TOKENS` | 16384 | **16384(不变)** | A 表:completion 3550~5257 即 stop,余量 >3x |
| `DEFAULT_TIMEOUT` | 180s | **180s(不变)** | A 表:最大一次 77.4s,余量 ~2.3x |
| `PROMPT_MARGIN` | 512 | **512(不变)** | D:估算已有 2.2x 保守度 |
| `BUDGET_TOTAL_LLM_TOKENS` | 50000 | **100000** | 真实页单次 reader ≈10.7k(glm 同型 ≈7.6k);glm 全量基线单题实耗 26976~47868 且停轮**从未**由预算触发 → 按 ~1.5x 折算 DeepSeek 约 40k~72k |
| `BUDGET_WRITER_RESERVE_TOKENS` | 8000 | **20000** | glm 基线 writer 实耗 7981 已用满;A 表 DeepSeek 小证据池即 4234~5941 |

**未决**:① DeepSeek 单价/免费档**未核**官方定价页,§8 成本结论仍按旧口径;
② 上述预算值由"glm 全量基线 × 折算系数"推得,**尚未经一次真实 DeepSeek 全链路
任务验证**(需 Tavily credits);③ 现有 `eval/baselines/` 产物均为 glm 时代,
与重校准后的 config 已不一致,守门快照测试据此报警。

### T12 补充:2 题真实全链路验证(2026-09-12,`--only fact_freethread,fact_gil`)

用重校准后的配置跑 2 道在线题(用户授权,共 4 credits),验证上述预算推算。

| qid | DeepSeek tokens | glm 基线 | stop_reason | 证据 | 报告 | 耗时 |
|---|---|---|---|---|---|---|
| fact_freethread | **8517**(研究 3919 + writer 4598) | 33243 | evidence_sufficient | 3 | 692 字符 | 84.2s |
| fact_gil | **23205**(研究 18214 + writer 4991) | 47506 | max_rounds | 6 | 1157 字符 | 141.5s |

⚠️ **本表推翻了本节的预算推算,如实记录**:"按 glm 基线 ×1.5 折算 DeepSeek 单题
40k~72k"是**错的**。真实两题均远低于旧 50k 上限。按单位工作量还原:

| 口径 | DeepSeek | glm | 比值 |
|---|---|---|---|
| 报告字符 / 条证据 | 231 / 193 | 214 / 200 | ≈1.0 |
| token / 条证据 | 2839 / 3868 | 3694 / 3959 | ≈0.8 |

即 **DeepSeek 的写作产出效率与 glm 基本一致(甚至略优)**,两题 token 变少是
因为**拿到的证据更少**(3/6 条 vs glm 的 9/12 条),而上游原因是本轮搜索返回的
结果大多在来源集合之外、白名单内只剩 1~3 页可抓(reader `reading` 事件 = 1 / 3,
glm 为 4 / 5)。reader 的抽取密度正常(约 3 条/页,与 glm 相同)。

**对预算的影响**:证据**不支持** 50k→100k 的上调——但也不构成"必须回退"的证明
(n=2,且两题都受网络故障影响);`100k/20k` 作为**不成为约束的上限**保留,代价仅
在"失控任务可花更多",而实测两题分别只用了 8.5%/23.2%。

**本轮另一发现(环境,非代码)**:
- 首轮 2 题**全部失败**:`fact_gil` = `DNS 解析失败 docs.python.org(getaddrinfo failed)`,
  `fact_freethread` = `ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]`;重跑前
  单独探针 DNS/抓取/DeepSeek 调用均正常 → **瞬时网络故障**(用户常开代理,SSL EOF
  是代理中断连接的典型症状),非配置问题。重跑即恢复。
- 重跑中 `fact_gil` 仍有 **2 次搜索因 SSL EOF 失败**,靠 `max_rounds` 兜底 → 该题
  的轮次是被网络耗尽而非策略耗尽。
- DeepSeek `usage` 额外返回 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`
  (**上下文缓存**)。本节两次调用分别为 `cached_tokens: 0` / 命中 0,尚未受益;核价
  时须知该字段会影响实际单价。

### T12 补充二:白名单打空的修复与验证(2026-09-12)

**根因**:`TavilySearch.search()` 只发 `query`/`max_results`/`search_depth`,
**不传 `include_domains`** —— 即向 Tavily 要整个互联网的结果,再在本地用
`split_by_allowlist` 过滤。中文技术主题下 Tavily 常返回 CSDN/知乎/菜鸟教程等
集合外站点,于是**一整轮 0 页可抓 → 0 证据 → 报告退化为程序生成的"研究未能
完成"**。8 题试点中命中 2 题(`fact_mdn401` / `fact_venv`;同两题在 9-07 的
glm 基线下是 `evidence_sufficient`)。与换 DeepSeek 无关,是既有脆弱性。

**修法**(`WhitelistRetrySearch`,已接入 `cli.default_tools_builder`,覆盖 CLI
与在线评测):主搜索保持全网(集合外结果照旧进"待核实链接",§9.1 语义不变);
仅当"主搜索有结果、但无一落在来源集合内"时,补一次 `include_domains=<白名单>`
的搜索,命中排在返回列表最前使 reader 优先读可抓页面。

**真实验证**(真实 Tavily,非构造样本):

| qid | 修前白名单命中 | 修后 | 该题搜索 credits |
|---|---|---|---|
| fact_mdn401 | 0 | **7**(首条 `developer.mozilla.org/.../Status/401`) | 2 |
| fact_venv | 0 | **2**(首条 `docs.python.org/zh-cn/3.9/library/venv.html`) | 2 |

**验证过程中的两个坑(重要,勿重复踩)**:

1. **一次被网络污染的读数差点得出错误结论**。首轮探针报 `fact_mdn401` 补搜后
   仍为 0;随后单独复测同一查询获得 8 条 MDN 结果,再复测 wrapper 得 7 条。
   期间出现了 `ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]` —— 与首轮 2 题
   全失败同源。**结论:单次被污染的运行会给出方向性错误的读数;成批异常时先
   复测网络,不要据此改代码或下结论。**
2. **`zh.wikipedia.org` 的 DNS 解析在两次体检中分别给出 `31.13.94.37`
   (Facebook 段,污染)与 `103.102.166.224`(正常)** —— 该域名需代理环境访问
   (与 SOURCES.md 既有备注一致)。

**顺带修掉一个自引入的记账缺陷**(TDD,`tests/test_graph.py:test_searcher_
reconciles_extra_search_credits`):searcher 在调用前按"预期一次调用"预扣 1
credit,而打空补搜会让一次搜索实际发生 **2** 次调用;返回的 `credits` 原先只进
事件载荷、**从未回灌预算**。后果:credits 熔断(≤16)被系统性低算,且终端事件的
`credits_used` 与 DB / `orca cost` 的 `tavily_credits` 三路口径不一致。
新增 `Budget.record_credits()` 事后如实补记(与 tokens 的落库前终检同旨:
尽力预防在前,实耗以事实入账)。单轮越限最多 1 credit,且下一轮闸门看到真值。
