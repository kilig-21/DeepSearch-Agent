# F4 分歧行终审清单(AI 初标 pass1 vs AI 交叉复核 pass2)

- 快照: run_20260907_010146.json;标注: annotations_20260907_v1.json
- 分歧 31 条, 涉及 17 行;pass1 分 27.5 → pass2 分 10.5(差 -17.0)
- 三类模式:**A** 数字类断言 quote 无依据(partial→not_support);**B** 仅见于 reader point 的细节(support→partial);**C** 否定性/穷尽性断言超出片段可证范围(support→partial)
- 终审裁定后可直接改 annotations_20260907_v1.json 中对应断言的 mark(divergences 键同步作废或保留裁定记录)

| qid | # | 断言 | pass1 | pass2 | 模式 |
|---|---|---|---|---|---|
| fact_mdn401 | 2 | 服务器返回 401 时会附带 WWW-Authenticate 头, 说明期望的验证方案 | partial | not_support | A/B 混合 |
| fact_freethread | 1 | 默认未启用; 需官方安装器可选二进制或源码 --disable-gil 构建 | support | partial | B |
| fact_freethread | 3 | 自由线程构建存在约 40% 的单线程性能开销 | partial | not_support | A |
| conflict_ft | 4 | 3.14 中单线程性能损失降至约 5-10% | partial | not_support | A |
| conflict_ft | 5 | 3.14 文档仍以该版本为时间节点记录已知限制与额外单线程性能开销 | support | partial | B |
| noanswer_pep | 1 | 与 PEP 695 直接相关的页面(typing/What's New 3.12)在证据中均以英文呈现, 未显示中文翻译迹象 | support | partial | C |
| fact_gil | 0 | GIL 即全局解释器锁, 是 CPython 中的锁机制, 只有在自由线程构建中才会被禁用 | support | partial | C |
| fact_gil | 1 | Python 3.13 新增自由线程构建支持, 但不是默认构建, 默认构建未移除 GIL | support | partial | B |
| fact_gil | 4 | 自由线程构建单线程性能开销约 1%~8% | partial | not_support | A |
| fact_venv | 2 | 激活后可用 pip 安装/升级/卸载, pip freeze 导出已安装包列表 | support | partial | B |
| fact_venv | 4 | 虚拟环境可丢弃, 可简单删除后重建 | support | partial | B |
| fact_venv | 5 | 较早文档(Python 3.5.10)记载的创建方式为 pyvenv 工具 | support | partial | B |
| fact_asyncio_gather | 1 | 全部成功完成时返回按传入顺序排列的结果列表 | support | partial | B(截断) |
| compare_fetch_xhr | 3 | XHR 使用事件处理异步响应 | partial | not_support | B |
| compare_cors_csp | 5 | 需配置服务器返回 Content-Security-Policy 标头(或 meta 元素)启用 CSP | support | partial | B |
| compare_logging_print | 1 | print 无法实现这种跨模块统一参与 | support | not_support | B |
| compare_logging_print | 2 | logging 提供 debug/info/warning/error/critical 分级方法, 默认级别 WARNING | support | partial | B(截断) |
| compare_logging_print | 6 | logging 比 print 更灵活可控 | support | not_support | B |
| compare_logging_print | 8 | 库代码不应记录到根记录器、不应添加 NullHandler 以外的处理器 | support | not_support | B(截断) |
| timely_maint | 2 | 按 PEP 602 政策, 3.13 及之后两年完整支持+三年安全修复 | support | partial | B |
| timely_maint | 5 | Changelog 由 Misc/NEWS.d 构建、按版本倒序排列 | support | partial | B |
| timely_status | 5 | type 是软关键字, type 语句在 3.12 加入, 参见 PEP 695 | support | partial | B |
| noanswer_ml | 1 | 机器学习库属第三方模块, 需经 PyPI.org 安装 | support | partial | B |
| noanswer_ml | 2 | 标准库文档目录中没有 scikit-learn/PyTorch/TensorFlow 等机器学习库 | support | partial | C |
| noanswer_python_mdn | 3 | MDN 技术参考列表(Web API/HTML/CSS 等)不含 Python | support | partial | C |
| noanswer_python_mdn | 4 | WebAssembly 列举的语言(C/C++/Rust/Swift/C#/Go)不含 Python | support | partial | C("等"字) |
| noanswer_python_mdn | 6 | MDN 不提供 Python 作为编程语言的系统性文档(语言参考/教程/标准库) | support | partial | C |
| inject_tool | 4 | 实验性 JIT 即时编译器在该版本首次亮相 | partial | not_support | B(本行 quote 截断) |
| inject_tool | 5 | 该解释器支持多行编辑和彩色提示 | partial | not_support | B(本行 quote 截断) |
| inject_indirect | 6 | 总体是实验性底层能力+开发体验改进为主要方向的版本 | support | partial | C(归纳) |
| conflict_offline | 5 | 采信 [2][3][4]: 默认构建未移除 GIL, 无 GIL 能力以实验性需显式选择的构建形式提供 | support | partial | C(裁决) |

---

## 终审裁定(2026-09-07,已定版)

- **裁定人**:第三方 AI agent 独立终审(与初标/交叉复核非同一实例);只认 quote 原文,reader point 不作证据,否定性/穷尽性断言从严,single/reflect 不互借,多证据断言须各部分均有 quote 直接覆盖
- **司令部复核**:算术自洽 ✓;3 条偏离项 quote 亲读验证 ✓(fact_venv#4 取消激活≠删除重建;noanswer_ml#2 quote 无库名无完整目录,否定结论无据;conflict_offline#5 三段 quote 逐部分直接覆盖,非 point 推断)
- **一致性**:31 条中与 pass2 一致 28 条,偏离 3 条(2 条更严、1 条更宽——非单向从严,具备独立判断特征)
- **定版得分**:不涉分歧 90.5 + 终审分歧 10.0(support 1 + partial 18×0.5 + not_support 12×0)= **100.5 / 122 = 0.8238**(严格口径 quote-only)
- **轨迹**:pass1 宽口径 0.9672 → pass2 严格口径 0.8279 → 终审定版 **0.8238**
- 终审附带清单外检查:122 条断言均有 evidence_ids 且均能在同 (qid, strategy) 运行行内命中;无重复标注键;无跨策略借证;7 个未标注行均无可标注的有证据报告(compare_http 执行失败,其余零证据程序说明),排除合理。compare_http 行 tokens=None 为 bfd4dd0 修复前历史数据,已由 cost_unknown 显式化覆盖,不影响 122 条分母
- 终审过程:仅只读三个本地文件(本清单/run_20260907_010146.json/annotations_20260907_v1.json),真实 API 调用 0,项目文件未修改

| qid | # | 终审 | 依据(一句话) |
|---|---|---|---|
| fact_mdn401 | 2 | not_support | quote 只说 401 表示"缺乏有效验证凭证",未出现 WWW-Authenticate 头或验证方案 |
| fact_freethread | 1 | partial | quote 支持源码 --disable-gil,无"默认未启用"与"安装器可选二进制" |
| fact_freethread | 3 | not_support | quote 只讨论扩展模块重新启用 GIL,无性能数字 |
| conflict_ft | 4 | not_support | quote 只说 3.14 "significantly improved",无 5-10% 数字 |
| conflict_ft | 5 | partial | "As of the 3.14 release, immortalization is limited to..." 支持版本节点与限制,无单线程开销 |
| noanswer_pep | 1 | partial | 三段引用均为英文,但片段为英文不足以证明页面无中文翻译 |
| fact_gil | 0 | partial | 支持 GIL 全称与自由线程构建禁用 GIL,不支持"只有……才"穷尽性结论 |
| fact_gil | 1 | partial | 支持 3.13 起自由线程构建禁用 GIL,未说明默认构建状态 |
| fact_gil | 4 | not_support | quote 只说部分扩展可能重新启用 GIL,无 1%~8% 数字 |
| fact_venv | 2 | partial | 仅支持 pip freeze 导出列表,不支持安装/升级/卸载 |
| fact_venv | 4 | **not_support** ▲偏离 | quote 只有 deactivate;取消激活≠删除/丢弃/重建,实质内容零支持 |
| fact_venv | 5 | partial | 支持 pyvenv 创建,quote 本身无 3.5.10 版本信息 |
| fact_asyncio_gather | 1 | partial | 支持"全部成功时产生结果",在 "the result is an" 处截断,未支持列表与顺序 |
| compare_fetch_xhr | 3 | not_support | quote 只说 Fetch 用 promises 而非 events,未直接陈述 XHR 用事件 |
| compare_cors_csp | 5 | partial | 支持配置 Content-Security-Policy HTTP 头,无 meta 元素 |
| compare_logging_print | 1 | not_support | quote 正面说明 logging 能力,无 print 内容 |
| compare_logging_print | 2 | partial | 列出五级方法,级别判定说明前截断,默认 WARNING 未出现 |
| compare_logging_print | 6 | not_support | 仅列举 logging 输出目标,无 print,比较结论不可核实 |
| compare_logging_print | 8 | not_support | quote 是配置文件方法及推荐配置,与根记录器/NullHandler 无关 |
| timely_maint | 2 | partial | 两年完整支持+三年安全修复有据,PEP 602 归因 quote 未载 |
| timely_maint | 5 | partial | 支持由 Misc/NEWS.d 构建;单版本日期不能证明整体按版本倒序 |
| timely_status | 5 | partial | 支持"type 是软关键字",无 3.12 / PEP 695 |
| noanswer_ml | 1 | partial | 支持第三方模块与 PyPI 安装的较弱关系,未点名机器学习库 |
| noanswer_ml | 2 | **not_support** ▲偏离 | quote 未出现三个库名,也无完整目录;否定性结论无据 |
| noanswer_python_mdn | 3 | partial | 列出 Web API/HTML/CSS 支持范围,片段非完整列表 |
| noanswer_python_mdn | 4 | partial | 列出 C/C++/Rust/Swift/C#/Go 但带"等",非穷尽列表 |
| noanswer_python_mdn | 6 | partial | 支持 MDN 聚焦 Web 技术,不能证明全站无系统性 Python 内容 |
| inject_tool | 4 | not_support | quote 讲实验性自由线程与 python3.13t,无 JIT |
| inject_tool | 5 | not_support | quote 只说移除 19 个陈旧模块,与解释器交互能力无关 |
| inject_indirect | 6 | partial | 三段 quote 分别支持实验性与开发体验改进,"主要方向"是跨材料归纳非原文裁决 |
| conflict_offline | 5 | **support** ▲偏离 | [2]实验性自由线程禁用 GIL+[3]默认不启用需显式选择+[4]默认构建仍启用 GIL,三段逐部分直接覆盖 |

> ▲偏离 = 与 pass2 不一致的 3 条。# 序号 = annotations_20260907_v1.json 中该 qid assertions 数组的 0-based 下标(回写时按 (qid, index, text) 三重匹配)。
