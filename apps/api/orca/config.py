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
