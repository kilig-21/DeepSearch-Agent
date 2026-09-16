# 演示录屏脚本(v1.0,约 6 分钟)

> **录制前准备**
> - 后端(8000)与前端(3000)已启动;终端开在 `apps/api`;`.env` 已配置。
> - 清库:`apps/api/.venv/Scripts/python -m orca cleanup`(须先停后端)。
> - **命令一律用 `.venv/Scripts/python`,不要用裸 `python`**——系统 Python
>   没装 sqlalchemy,会直接 import 失败。
> - 分辨率 1920×1080,终端字体放大,全程中文界面。

## 场景 1:一次可核实的研究(约 2.5 分钟)

1. **[终端]** `.venv/Scripts/python -m orca research "Python 3.13 的自由线程模式是什么?默认是否启用?"`
   - 旁白:全链路时间线——规划、检索、逐页阅读、证据合并、反思、写作。
     `[reflection]` 一行之后要么继续搜,要么收尾;这里判证据够用,直接进写作。
2. **[前端]** 回到浏览器 `localhost:3000`,发起同一问题。
   - 旁白:SSE 流式——检索、阅读进度、报告草稿逐段出现;这是同一链路的 Web 形态。
3. **[前端]** 报告完成后,点击报告里的 `[1]` 引用编号(直达来源 URL)。
   - 旁白:每条引用在运行快照里对应一段原文 quote、一个来源 URL、一次抓取时间
     ——结论逐条可追溯。
4. **[前端]** 点开"来源"列表。
   - 旁白:正文全部来自白名单站点(docs.python.org);集合外结果只列为"待核实链接",
     不作为证据。

## 场景 2:超限即停 + 成本分账(约 1.5 分钟)

5. **[终端]** 光标停在场景 1 的收尾行:
   `[done] report_id=… stop_reason=evidence_sufficient tokens=… (研究 N + writer M) credits=… 耗时=…s`
   - 旁白:每个任务都带 `stop_reason` 与预算记账;研究阶段与 writer 阶段的 token
     分列,搜索 credits 独立计账。
6. **[终端]** `.venv/Scripts/python -m orca cost --last`
   - 旁白:一条命令回看单任务成本小结;同样的数据也在任务终态事件和数据库里。
7. **[终端(可选)]** `.venv/Scripts/python -m orca.eval --only budget_total`
   - 旁白:这是离线注入题,总额度被覆盖成 160 tokens。额度打穿时链路**一次模型
     调用都不发**,`stop_reason` 记为 `total_budget_exhausted`,报告是程序生成的说明
     ——超限即停,停止原因如实入账。这一题实耗 0 token、0 credit。

## 场景 3:评测一条命令(约 1.5 分钟)

8. **[终端]** `.venv/Scripts/python -m orca.eval --only fact_freethread,fetch_fail,no_results`
   - 旁白:评测集 27 题、八类题型。离线题注入固定材料——检索不联网,LLM 仍是真实
     调用,所以可复现;在线题是时点快照。
9. **[终端]** 用 IDE 打开刚生成的 `eval/baselines/table_<ts>.md`。
   - 旁白:结果表直出——状态、`stop_reason`、tokens、credits、引用有效率;失败率
     分母是全部任务;标注类指标不静默出分,分歧清单与裁定一并留档。
10. **[终端(可选)]** `.venv/Scripts/python -m orca.eval --compare --only compare_http`
    - 旁白:同一题、同一资源上限,单轮 vs 反思循环配对执行;题序交替先后抵消时间漂移。

## 场景 4:取消(约 0.5 分钟,录屏节选)

11. **[前端]** 发起一个问题,流式过程中点"取消"。
    - 旁白:任务即时进入取消终态,writer 不再产出;`stop_reason=user_cancelled`,
      草稿不作为内容暴露。

## 录屏清单核对

- [ ] 时间线可见:plan / search / reading / note / reflection / 报告草稿事件
- [ ] `[reflection]` 之后出现「要么继续搜、要么收尾」的分叉
- [ ] 引用编号可点击直达来源 URL
- [ ] `[done]` 行含 tokens 分账(研究 / writer)与 credits
- [ ] `orca cost --last` 输出小结
- [ ] 熔断题实耗 0、`stop_reason=total_budget_exhausted`
- [ ] 评测结果表 `table_<ts>.md` 打开展示
- [ ] 取消路径:SSE 终态为 cancelled

## 口播数字速查(照这个念,别记错)

| 项 | 值 | 出处 |
|---|---|---|
| 评测集 | **27 题**(18 在线 + 9 离线),八类题型 | `apps/api/orca/eval/questions.py` |
| 当前基线 | 27 题**全部完成,失败率 0.0%** | `run_20260912_195950.json` |
| 断言引用支持率 | **0.8777**(122/139,严格口径,外部终审定版) | `annotations_20260912_v1.json` |
| 答案覆盖率 | **0.9113**(56.5/62) | 同上 |
| 引用有效率 | 有报告的 21 行**全部 1.0** | `run_20260912_195950.json` |
| 安全题 | 3 道注入题**自动判定全 pass** | 同上(safety 字段) |
| 全量消耗 | 708,953 tokens / 55 credits | 同上 |
| 单题峰值 | 70,012 tokens | 同上 |
| stop_reason 分布 | evidence_sufficient 9 / no_new_evidence 9 / max_rounds 7 / total_budget_exhausted 2 | 同上 |
| 后端测试 | **301 个用例全绿** | `cd apps/api && .venv/Scripts/python -m pytest -q` |

⚠️ **别在录屏里说**「DeepSeek 比 glm 强」——跨模型优劣方向会随标注口径翻转,
文档立场是只报绝对值。详见 README 里那段口径警告。
