# v0.9 演示录屏脚本(约 6 分钟)

> 录屏前准备:后端(8000)与前端(3000)已启动;终端开在 `apps/api`;
> `.env` 已配置;数据目录 `data/orca.db` 为空或已清理(`python -m orca cleanup`)。
> 分辨率 1920×1080,全程中文界面,终端字体放大。

## 场景 1:一次可核实的研究(约 2.5 分钟)

1. **[终端]** `python -m orca research "Python 3.13 的自由线程模式是什么?默认是否启用?"`
   - 旁白:全链路时间线——规划、检索、逐页阅读、证据合并、反思、写作。
2. **[前端]** 回到浏览器 `localhost:3000`,发起同一问题。
   - 旁白:SSE 流式——检索结果、阅读进度、报告草稿逐段出现;这是同一链路的 Web 形态。
3. **[前端]** 报告完成后,点击报告中的 `[1]` 引用编号(直达来源 URL)。
   - 旁白:每条引用在运行快照里对应一段原文 quote、一个来源 URL、一次抓取时间——结论逐条可追溯。
4. **[前端]** 点开"来源"列表。
   - 旁白:所有正文均来自白名单站点(docs.python.org 等);集合外结果只列为待核实,不进入证据。

## 场景 2:超限即停 + 成本分账(约 1.5 分钟)

5. **[终端]** 场景 1 的 CLI 运行已结束,光标停在 `[done] ... tokens=... (研究 N + writer M) credits=...`。
   - 旁白:每个任务都有 stop_reason 与预算记账;研究阶段与 writer 阶段的 token 分列,搜索 credits 独立计账。
6. **[终端]** `python -m orca cost --last`
   - 旁白:一条命令回看单任务成本小结;同样的数据也在任务终态事件和数据库里。
7. **[终端(可选)]** 演示熔断:`python -m orca.eval --only budget_total`(离线注入题,总额度打穿)
   - 旁白:额度打穿时链路不再调用任何模型,stop_reason 记为 total_budget_exhausted,报告为程序说明——超限即停,停止原因如实入账。

## 场景 3:评测一条命令(约 1.5 分钟)

8. **[终端]** `python -m orca.eval --only fact_freethread,fetch_fail,no_results`
   - 旁白:评测集 27 题,八类题型;离线题注入固定材料——检索不联网,LLM 为真实调用,可复现。
9. **[终端]** 展示生成的 `eval/baselines/table_<ts>.md`(IDE 打开)。
   - 旁白:结果表自动指标直出——状态、stop_reason、tokens、credits、引用有效率;失败率分母为全部任务;标注类指标(AI 初标 + 人工复核)不静默出分。
10. **[终端(可选)]** `python -m orca.eval --compare --only compare_http`(两策略配对)
    - 旁白:同一题、同一资源上限,单轮 vs 反思循环对照执行;题序交替先后抵消时间漂移。

## 场景 4:取消(约 0.5 分钟,录屏节选)

11. **[前端]** 发起一个问题,流式过程中点击"取消"。
    - 旁白:任务即时进入取消终态,writer 不再产出;stop_reason=user_cancelled,草稿不作为内容暴露。

## 录屏清单核对

- [ ] 时间线可见:plan/search/reading/reflection/报告草稿事件
- [ ] 引用编号可点击直达来源 URL(quote 与抓取时间在快照/数据库逐条可查;UI 内逐层展开为路线图)
- [ ] `[done]` 行含 tokens 分账(研究/writer)与 credits
- [ ] `orca cost --last` 输出小结
- [ ] 评测结果表 `table_<ts>.md` 打开展示
- [ ] 取消路径:SSE 终态为 cancelled
