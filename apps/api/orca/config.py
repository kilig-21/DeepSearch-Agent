"""集中读取配置:所有密钥只经环境变量进入,不落代码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根 = Orca/(config.py 位于 Orca/apps/api/orca/ 下, 上溯 3 级)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

ZHIPU_CHAT_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# LLM 定版(2026-09-05 用户定版: 5.3 系列; 详见 PLAN.md §8)
LLM_DAILY_MODEL = "glm-5.3-flash"    # 日常迭代/跑量
LLM_HIGH_QUALITY_MODEL = "glm-5.3"   # 高质量模式(最终报告)
LLM_PROBE_MODELS = ["glm-5.3-flash", "glm-5.3"]

# 数据库(本地自用; data/ 不进版本库)
DB_PATH = PROJECT_ROOT / "data" / "orca.db"

# 允许抓取的来源集合(docs/SOURCES.md 逐站核对; 集合外不抓正文, §4/§9.1)
ALLOWED_DOMAINS = {"docs.python.org", "developer.mozilla.org",
                   "zh.wikipedia.org"}

# 抓取代理(§3.7):默认直连;显式设置 FETCH_PROXY 环境变量启用代理模式
# (代理模式下由代理方解析目标, 本地 IP 校验不适用, 依赖白名单防线)
FETCH_PROXY = os.environ.get("FETCH_PROXY") or None

# 预算初始值(§3.6, Phase 0 实测回填; Phase 1A 实测后校准)。
# 支持环境变量覆盖(ORCA_* 前缀), 供演示/评测构造小预算, 默认值不变。
BUDGET_TOTAL_LLM_TOKENS = int(os.environ.get("ORCA_BUDGET_TOTAL_LLM_TOKENS", 50_000))
BUDGET_WRITER_RESERVE_TOKENS = int(
    os.environ.get("ORCA_BUDGET_WRITER_RESERVE_TOKENS", 8_000))
BUDGET_MAX_TAVILY_CREDITS = int(
    os.environ.get("ORCA_BUDGET_MAX_TAVILY_CREDITS", 16))
BUDGET_MAX_PAGES = int(os.environ.get("ORCA_BUDGET_MAX_PAGES", 12))
BUDGET_TIME_S = float(os.environ.get("ORCA_BUDGET_TIME_S", 480.0))  # 总时长 ≤8 分钟
