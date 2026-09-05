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
