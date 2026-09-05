"""测试公共 LLM 桩:按 prompt 特征分派 planner/reader/writer 语义。

quote 从 prompt 内嵌正文直接截取, 保证 locate_quote 定位成功。
"""
import json

from orca.llm import LLMResult

USG = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}


def fake_llm_chat(messages, *, max_tokens, tier, reasoning_effort=None):
    content = messages[-1]["content"]
    if "研究规划器" in content:
        payload = {"sub_questions": ["子问题一"], "query": "固定查询"}
        return LLMResult(content=json.dumps(payload, ensure_ascii=False),
                         usage=dict(USG))
    if "正文:" in content:  # reader: 从 prompt 正文截取 quote(必可定位)
        body = content.split("正文:")[-1].strip()
        quote = body[:60]
        payload = {"points": [{"point": "一个要点", "quote": quote}]}
        return LLMResult(content=json.dumps(payload, ensure_ascii=False),
                         usage=dict(USG))
    return LLMResult(content="# 报告\n\n结论: 相关要点成立 [1]。\n",
                     usage=dict(USG))
