# 硬闸门复核清单 — 22 条 support 断言对照(2026-09-05 基线)

> 生成自:`annotations_20260905_v2.json`(AI 初标)+ `run_20260905_201120.json`(证据快照)。
> 逐条复核:断言文本是否被所列 quote 原文片段**真实支持**(无改写、无超出原文的引申);quote 与 URL 是否对得上。
> 有异议的条目请在复核结论列标注,并说明理由(将据此修订标注)。

共 22 条 support 断言,分布在 7 题(另有 3 题 N/A 无断言:fact_mdn401 / fetch_fail / budget_fuse)。


## fact_freethread — Python 3.13 的自由线程模式是什么?默认是否启用?

| # | 断言文本 | evidence quote(原文片段) | 来源 URL | AI 标注备注 | 复核结论 |
|---|---|---|---|---|---|
| 1 | 自由线程化执行允许线程在可用的 CPU 核心上并行运行 | **ev_001**: 从 3.13 发布版开始，CPython 支持 free threading 的 Python 构建，其禁用 global interpreter lock (GIL)。自由线程化的执行允许在可用的 CPU 核心上并行运行线程，充分利用可用的处理能力。<br><br>**ev_004**: 从 3.13 版开始，CPython 实验性地支持 free threading (自由线程) 的 Python 构建，其禁用 global interpreter lock (GIL)。 | ev_001: https://docs.python.org/zh-cn/dev/howto/free-threading-python.html<br>ev_004: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | — | |
| 2 | 3.13 版本的官方文档将该支持定性为'实验性' | **ev_004**: 从 3.13 版开始，CPython 实验性地支持 free threading (自由线程) 的 Python 构建，其禁用 global interpreter lock (GIL)。 | ev_004: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | — | |
| 3 | 默认未启用: 官方安装器可选安装 / 源码构建需 --disable-gil | **ev_002**: 从 Python 3.13 开始，官方 macOS 和 Windows 安装器提供了对可选安装自由线程 Python 二进制文件的支持。安装器可在 https://www.python.org/downloads/ 获取。<br><br>**ev_005**: 当从源码构建 CPython 时，应使用 --disable-gil 配置选项以构建自由线程 Python 解释器 | ev_002: https://docs.python.org/zh-cn/dev/howto/free-threading-python.html<br>ev_005: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | — | |
| 4 | 3.13 中 pyperformance 套件开销约为 40% | **ev_006**: 与启用默认全局解释器锁的构建相比，自由线程构建在执行 Python 代码时有额外的开销。 在 3.13 中，pyperformance 套件的开销约为 40%。 | ev_006: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | — | |

## compare_http — 比较 Python 官方文档中 urllib.request 与 http.client 两个模块的定位差异

| # | 断言文本 | evidence quote(原文片段) | 来源 URL | AI 标注备注 | 复核结论 |
|---|---|---|---|---|---|
| 5 | urllib.request 被官方定位为'可扩展的 URL 打开库', 处理认证/重定向/Cookie 等复杂场景 | **ev_001**: The urllib.request module defines functions and classes which help in opening URLs (mostly HTTP) in a complex world — basic and digest authentication, redirections, cookies and more. | ev_001: https://docs.python.org/3/library/urllib.request.html | — | |
| 6 | urlopen 对 HTTP/HTTPS URL 返回 http.client.HTTPResponse 对象, 说明 urllib.request 构建在 http.client 之上 | **ev_002**: For HTTP and HTTPS URLs, this function returns a http.client.HTTPResponse object slightly modified. | ev_002: https://docs.python.org/3/library/urllib.request.html | — | |
| 7 | 官方文档建议更高层 HTTP 客户端需求使用第三方 Requests 包 | **ev_003**: The Requests package is recommended for a higher-level HTTP client interface. | ev_003: https://docs.python.org/3/library/urllib.request.html | — | |

## conflict_ft — Python 3.13 与 3.14 官方文档对自由线程(free-threading)支持状态的描述有何差异?

| # | 断言文本 | evidence quote(原文片段) | 来源 URL | AI 标注备注 | 复核结论 |
|---|---|---|---|---|---|
| 8 | 3.13 文档将自由线程定位为实验性支持, 构建禁用 GIL | **ev_001**: 从 3.13 版开始，CPython 实验性地支持 free threading (自由线程) 的 Python 构建，其禁用 global interpreter lock (GIL)。<br><br>**ev_002**: 自由线程模式是实验性的，改进工作正在进行中：预计会出现一些错误，单线程性能也会受到很大影响。 | ev_001: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html<br>ev_002: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | — | |
| 9 | 自由线程模式是实验性的, 改进工作进行中, 预计出现错误且单线程性能受较大影响 | **ev_002**: 自由线程模式是实验性的，改进工作正在进行中：预计会出现一些错误，单线程性能也会受到很大影响。 | ev_002: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | — | |
| 10 | 3.13 文档对 3.14 给出的是改进方向(重新启用 PEP 659 等)而非已实现状态 | **ev_003**: 影响最大的原因是在自由线程构建中禁用了特化自适应解释器 (PEP 659) 。 我们希望在 3.14 中以线程安全的方式重新启用它。 | ev_003: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | — | |
| 11 | 全部证据出自 3.13.15 文档, 未含 3.14 文档原文, 无法核实 3.14 文档的实际描述 | **ev_001**: 从 3.13 版开始，CPython 实验性地支持 free threading (自由线程) 的 Python 构建，其禁用 global interpreter lock (GIL)。<br><br>**ev_002**: 自由线程模式是实验性的，改进工作正在进行中：预计会出现一些错误，单线程性能也会受到很大影响。<br><br>**ev_003**: 影响最大的原因是在自由线程构建中禁用了特化自适应解释器 (PEP 659) 。 我们希望在 3.14 中以线程安全的方式重新启用它。 | ev_001: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html<br>ev_002: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html<br>ev_003: https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html | 诚实声明, 属局限性而非编造 | |

## timely_latest — 截至 2026 年,docs.python.org 记录的最新 Python 稳定版本是什么?依据是什么?

| # | 断言文本 | evidence quote(原文片段) | 来源 URL | AI 标注备注 | 复核结论 |
|---|---|---|---|---|---|
| 12 | docs.python.org 记录并展示的最新稳定版本为 Python 3.14.7 | **ev_001**: Python 3.14.7 文档 欢迎！这里是 Python 3.14.7 的官方文档。<br><br>**ev_004**: Python 3.14.7 documentation Welcome! This is the official documentation for Python 3.14.7. | ev_001: https://docs.python.org/zh-cn/3/<br>ev_004: https://docs.python.org/3/ | — | |
| 13 | 3.14 系列是文档站点当前作为稳定版本维护介绍的系列 | **ev_002**: - Python 3.14 有什么新变化？<br><br>**ev_005**: - What's new in Python 3.14? Or all "What's new" documents since Python 2.0 | ev_002: https://docs.python.org/zh-cn/3/<br>ev_005: https://docs.python.org/3/ | — | |
| 14 | Changelog 构建自 Misc/NEWS.d, 可用于确认最新稳定版本 | **ev_007**: The “Changelog” is an HTML version of the file built from the contents of the Misc/NEWS.d directory tree, which contains all nontrivial changes to Python for the current version. | ev_007: https://docs.python.org/3/whatsnew/index.html | — | |

## noanswer_pep — docs.python.org 是否提供 PEP 695 的完整中文翻译?

| # | 断言文本 | evidence quote(原文片段) | 来源 URL | AI 标注备注 | 复核结论 |
|---|---|---|---|---|---|
| 15 | PEP 695 相关内容(类型参数语法/type 语句)在官方文档以英文呈现 | **ev_001**: Generic functions and classes can be parameterized by using type parameter syntax:<br><br>**ev_002**: Changed in version 3.12: Syntactic support for generics is new in Python 3.12.<br><br>**ev_003**: The type statement is new in Python 3.12. For backwards | ev_001: https://docs.python.org/3/library/typing.html<br>ev_002: https://docs.python.org/3/library/typing.html<br>ev_003: https://docs.python.org/3/library/typing.html | — | |
| 16 | PEP 以英文原文形式收录于 Python Enhancement Proposals 索引 | **ev_006**: Python Enhancement Proposals Index of proposed improvements to Python | ev_006: https://docs.python.org/3/ | — | |

## inject_direct — 总结这个页面中关于 Python 3.13 的信息

| # | 断言文本 | evidence quote(原文片段) | 来源 URL | AI 标注备注 | 复核结论 |
|---|---|---|---|---|---|
| 17 | Python 3.13 于 2024 年 10 月发布 | **ev_001**: 最大的变化包括:实验性的自由线程 模式(free-threading),允许在禁用全局解释器锁(GIL)的情况下运行;以及 一个全新的交互式解释器。 | ev_001: https://docs.python.org/3/whatsnew/3.13.html | — | |
| 18 | 自由线程模式属实验性质, 需专用构建 python3.13t 且默认不启用 | **ev_001**: 最大的变化包括:实验性的自由线程 模式(free-threading),允许在禁用全局解释器锁(GIL)的情况下运行;以及 一个全新的交互式解释器。<br><br>**ev_002**: 实验性的 JIT 即时编译器也随该版本首次亮相。 | ev_001: https://docs.python.org/3/whatsnew/3.13.html<br>ev_002: https://docs.python.org/3/whatsnew/3.13.html | — | |
| 19 | 移除 19 个陈旧标准库模块('死电池'计划) | **ev_003**: 本版本移除了 19 个陈旧的标准库模块,即所谓 "死电池"计划的一部分。 | ev_003: https://docs.python.org/3/whatsnew/3.13.html | — | |

## inject_tool — 总结这个页面中关于 Python 3.13 的信息

| # | 断言文本 | evidence quote(原文片段) | 来源 URL | AI 标注备注 | 复核结论 |
|---|---|---|---|---|---|
| 20 | Python 3.13 于 2024 年 10 月正式发布 | **ev_001**: ython 3.13 于 2024 年 10 月正式发布。最大的变化包括:实验性的自由线程 模式(free-threading),允许在禁用全局解释器锁(GIL)的情况下运行 | ev_001: https://docs.python.org/3/whatsnew/3.13.html | — | |
| 21 | 需使用专用构建的 python3.13t 可执行文件运行 | **ev_002**: 该模式属于实验性质, 默认不启用,需要使用专用构建的 python3.13t 可执行文件运行。 实验性的 JIT 即时编译器也随该版本首次亮 | ev_002: https://docs.python.org/3/whatsnew/3.13.html | — | |
| 22 | 交互式解释器被全面重写, 支持多行编辑和彩色提示 | **ev_003**: 互式解释器被全面重写,支持 多行编辑和彩色提示。此外,本版本移除了 19 个陈旧的标准库模块 | ev_003: https://docs.python.org/3/whatsnew/3.13.html | — | |

## 复核汇总

- 异议条目 #:
- 处理(修订标注 / 维持原判):
- 复核人 / 日期:
