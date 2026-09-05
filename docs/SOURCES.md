# 已核对来源集合(允许抓取正文)

> 计划书 §9.1 执行机制:Phase 1~2 主链路**只抓取本清单内**的来源;集合外站点**不抓正文,仅列为待核实链接**。
> 扩充流程:逐站核对条款 → 填入下表 → 才能进入 ALLOWED_DOMAINS。
> 提醒:条款链接可能随时间变化,以站点页脚声明的最新许可为准。

| 来源 | 域名 | 内容许可 | 条款/许可链接 | 核验日期 | 允许范围与备注 |
|---|---|---|---|---|---|
| 维基百科(中文) | `zh.wikipedia.org` | CC BY-SA 4.0(内容重用需署名+相同方式共享) | [Wikimedia Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) | 2026-09-05 | 允许程序化访问与引用;报告引用时给出来源链接与作者署名 |
| Python 官方文档 | `docs.python.org` | PSF License Version 2(允许再分发,保留声明) | [Python License](https://docs.python.org/3/license.html) | 2026-09-05 | 允许引用与摘录;无需抓取频率说明,仍遵守限速(≤5 并发) |
| MDN Web Docs(中文) | `developer.mozilla.org` | CC BY-SA 2.5(内容重用需署名+相同方式共享) | [MDN 内容许可](https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Attribution_copyright_license) | 2026-09-05 | 允许引用与摘录;以页面页脚许可声明为准 |

## 待核实候选(Phase 3 适配器前逐站核对)

| 来源 | 域名 | 状态 |
|---|---|---|
| B站 | `bilibili.com` | 待核实(计划书 Phase 3:区分"无需登录可访问"≠"官方授权";仅元数据不视为已读) |
| 各官方博客/机构公告 RSS | 逐个添加 | 待核实 |

## 数据流向说明(README 同步用)

- 正文提取:本地完成(Defuddle CLI / trafilatura),内容不出本机
- LLM 调用:截取的正文片段会发送至智谱 API(见其[用户协议](https://open.bigmodel.cn/dev/api));不要把含个人敏感信息的页面加入来源集合
- 搜索:Tavily API(见其 [Terms](https://www.tavily.com/terms))
- 本地清理:`python -m orca cleanup`(后端停止后执行)
