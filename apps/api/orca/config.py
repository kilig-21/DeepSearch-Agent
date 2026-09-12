"""集中读取配置:所有密钥只经环境变量进入,不落代码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根 = Orca/(config.py 位于 Orca/apps/api/orca/ 下, 上溯 3 级)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# LLM 定版(2026-09-09 换 DeepSeek): 简单/机械任务 flash, 难任务(最终报告) pro
# 注: budget/timeout 等 probe 回填值已于 2026-09-12 按 DeepSeek 重校准
# (probe T12);下列预算常量的取值依据见各自注释
LLM_DAILY_MODEL = "deepseek-v4-flash"      # 日常迭代/跑量/机械任务
LLM_HIGH_QUALITY_MODEL = "deepseek-v4-pro"  # 高质量模式(最终报告/难任务)
LLM_PROBE_MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]

# 数据库(本地自用; data/ 不进版本库)
DB_PATH = PROJECT_ROOT / "data" / "orca.db"

# 允许抓取的来源集合(docs/SOURCES.md 逐站核对; 集合外不抓正文, §4/§9.1)
ALLOWED_DOMAINS = {"docs.python.org", "developer.mozilla.org",
                   "zh.wikipedia.org"}

# 抓取代理(§3.7):默认直连;显式设置 FETCH_PROXY 环境变量启用代理模式
# (代理模式下由代理方解析目标, 本地 IP 校验不适用, 依赖白名单防线)
FETCH_PROXY = os.environ.get("FETCH_PROXY") or None

# Phase 3：默认关闭，避免既有应用链路隐式改变。H1 对照/显式使用时只接受
# 已预登记的中文 Python 文档适配器，其他值在组装时拒绝。
SOURCE_ADAPTER = os.environ.get("ORCA_SOURCE_ADAPTER", "").strip()

# 预算初始值(§3.6, Phase 0 实测回填; Phase 1A glm 校准 → 2026-09-12 换
# DeepSeek 后重校准)。
# 支持环境变量覆盖(ORCA_* 前缀), 供演示/评测构造小预算, 默认值不变。
#
# 取值依据(probe T12, 2026-09-12): 定值 100k 是**不成为约束的上限**, 而非
# 实测所需。依据分两部分, 如实记录:
#  (1) 修的是"单调用形态": DeepSeek 推理 token 远高于 glm —— 真实白名单页
#      单次 reader 实测 prompt 7053 + completion 3639 ≈ 10692 tokens(glm 同型
#      约 7600), 故 MIN_USABLE_OUTPUT / _READER_MAX_TOKENS 必须上调(硬证据)。
#  (2) 总额度本身**未被证明需要上调**: glm 时代全量基线单题实耗
#      26976~47868(中位 36768), 停轮由确定性条件(evidence_sufficient /
#      no_new_evidence / max_rounds)决定、从未触发 budget_exhausted, 即原
#      50000 已接近不成为约束, 但对最大题只剩 ~4% 余量; 换 DeepSeek 后重跑
#      2 题实测仅 8517 / 23205(见 T12 补充), 远低于旧上限。故维持 100k 是
#      "给最大题留足余量"的保守选择, 上限不消耗, 但**不要**据此声称
#      "DeepSeek 单题需要 40k~72k" —— 该折算已被实测证伪。
BUDGET_TOTAL_LLM_TOKENS = int(
    os.environ.get("ORCA_BUDGET_TOTAL_LLM_TOKENS", 100_000))
# writer 预留: glm 时代基线里 writer 实耗 7981(预留 8000 几乎用满), 是该值
# 偏紧的实证; DeepSeek writer 实测 4234~5941(小证据池)与 4598~4991(真实题)。
# 上调到 20k 是为保住"研究额度不得侵占写作"的两级规则(§3.6)并留余量, 同样
# 属保守选择而非实测所需 —— 预留越大, 研究额度越宽(100k-20k=80k)。
BUDGET_WRITER_RESERVE_TOKENS = int(
    os.environ.get("ORCA_BUDGET_WRITER_RESERVE_TOKENS", 20_000))
BUDGET_MAX_TAVILY_CREDITS = int(
    os.environ.get("ORCA_BUDGET_MAX_TAVILY_CREDITS", 16))
BUDGET_MAX_PAGES = int(os.environ.get("ORCA_BUDGET_MAX_PAGES", 12))
BUDGET_TIME_S = float(os.environ.get("ORCA_BUDGET_TIME_S", 480.0))  # 总时长 ≤8 分钟
