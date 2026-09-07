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
