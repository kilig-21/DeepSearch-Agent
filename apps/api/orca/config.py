"""集中读取配置:所有密钥只经环境变量进入,不落代码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根 = apps/api 的上两级
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

ZHIPU_CHAT_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Phase 0 默认模型(实测后定版,回填 PLAN.md §8)
LLM_DAILY_MODEL = "glm-4-flash"      # 日常迭代/跑量
LLM_PROBE_MODELS = ["glm-4-flash", "glm-4.5-flash", "glm-4.6"]
