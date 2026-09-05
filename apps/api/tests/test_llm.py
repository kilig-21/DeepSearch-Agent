"""LLMClient 薄协议测试(计划书 §2.2:单模型 + 薄接口, 不做多厂商网关)。

工程约束(Phase 0 探针教训):glm-5.3 为推理型模型, max_tokens=100 时 content
为空(思考即耗尽)→ max_tokens 必须显式给足, 设为必填参数。
"""
import pytest

from orca import llm


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


OK_PAYLOAD = {
    "choices": [{"message": {"content": "摘要内容", "reasoning_content": "思考..."}}],
    "usage": {"prompt_tokens": 171, "completion_tokens": 2586, "total_tokens": 2757},
}


def make_post(responses):
    """注入的 post 函数:依次返回 responses, 记录收到的 payload。"""
    calls = []

    def post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json,
                      "timeout": timeout})
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    post.calls = calls
    return post


def make_client(post, **kw):
    return llm.LLMClient(api_key="k-test", url="https://example/chat", post=post,
                         **kw)


def test_chat_returns_content_and_usage():
    post = make_post([FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)

    r = client.chat([{"role": "user", "content": "hi"}], max_tokens=4096)

    assert r.content == "摘要内容"
    assert r.usage["total_tokens"] == 2757
    body = post.calls[0]["json"]
    assert body["max_tokens"] == 4096          # 5.3 推理模型必须给足输出上限
    assert body["model"] == llm.LLM_DAILY_MODEL
    assert post.calls[0]["headers"]["Authorization"] == "Bearer k-test"


def test_max_tokens_is_required():
    post = make_post([])
    client = make_client(post)
    with pytest.raises(TypeError):
        client.chat([{"role": "user", "content": "hi"}])  # type: ignore[call-arg]


def test_tier_maps_to_models():
    post = make_post([FakeResponse(200, OK_PAYLOAD), FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)
    client.chat([{"role": "user", "content": "a"}], max_tokens=100, tier="daily")
    client.chat([{"role": "user", "content": "a"}], max_tokens=100,
                tier="high_quality")
    assert post.calls[0]["json"]["model"] == llm.LLM_DAILY_MODEL
    assert post.calls[1]["json"]["model"] == llm.LLM_HIGH_QUALITY_MODEL


def test_retries_on_5xx_then_succeeds():
    post = make_post([FakeResponse(500, {"error": "boom"}),
                      FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)
    r = client.chat([{"role": "user", "content": "hi"}], max_tokens=1024)
    assert r.content == "摘要内容"
    assert len(post.calls) == 2


def test_raises_after_retries_exhausted():
    post = make_post([FakeResponse(500, {}), FakeResponse(500, {}),
                      FakeResponse(500, {})])
    client = make_client(post)
    with pytest.raises(llm.LLMError):
        client.chat([{"role": "user", "content": "hi"}], max_tokens=1024)
    assert len(post.calls) == 3  # 1 次原始 + ≤2 次重试(§3.6)


def test_does_not_retry_on_4xx():
    post = make_post([FakeResponse(401, {"error": "bad key"})])
    client = make_client(post)
    with pytest.raises(llm.LLMError):
        client.chat([{"role": "user", "content": "hi"}], max_tokens=1024)
    assert len(post.calls) == 1


def test_retries_on_network_error():
    post = make_post([llm.LLMError("network"), FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)
    r = client.chat([{"role": "user", "content": "hi"}], max_tokens=1024)
    assert r.content == "摘要内容"


def test_reasoning_tokens_counted_in_usage():
    """思考 token 计入计费与预算分账(probe_results.md 定版变更)。"""
    post = make_post([FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)
    r = client.chat([{"role": "user", "content": "hi"}], max_tokens=4096)
    assert r.usage["completion_tokens"] == 2586  # 含思考段, 原样上报
    assert r.usage["total_tokens"] == 2757


def test_default_timeout_covers_reasoning_models():
    """5.3 推理型模型思考段远超 4 系列的 4~6s, 30s 会 ReadTimeout
    (Phase 1A 冒烟实测)。默认超时须按推理型模型校准。"""
    post = make_post([FakeResponse(200, OK_PAYLOAD)])
    client = llm.LLMClient(api_key="k", url="u", post=post)
    client.chat([{"role": "user", "content": "hi"}], max_tokens=1024)
    assert post.calls[0]["timeout"] >= 180


def test_no_reasoning_effort_field_by_default():
    """默认不传 reasoning_effort:writer 保留模型默认思考(推理任务需要)。"""
    post = make_post([FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)
    client.chat([{"role": "user", "content": "hi"}], max_tokens=8192)
    assert "reasoning_effort" not in post.calls[0]["json"]
    assert "thinking" not in post.calls[0]["json"]  # 5.3 不接受 thinking.type 值


def test_reasoning_effort_low_disables_thinking():
    """reader/planner 等机械任务压制思考:思考段曾吃满 4096 输出配额
    导致 content 为空(Phase 1A 诊断), 且思考 token 计费。

    实测(2026-09-05):glm-5.3-flash 始终思考, thinking.type 不接受
    disabled/low/high/max;顶层 reasoning_effort="low" 是唯一实测能将
    思考压到 0 的方式(OpenAI 风格兼容参数)。
    """
    post = make_post([FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)
    client.chat([{"role": "user", "content": "hi"}], max_tokens=2048,
                reasoning_effort="low")
    assert post.calls[0]["json"]["reasoning_effort"] == "low"


def test_reasoning_effort_value_passthrough():
    post = make_post([FakeResponse(200, OK_PAYLOAD)])
    client = make_client(post)
    client.chat([{"role": "user", "content": "hi"}], max_tokens=2048,
                reasoning_effort="high")
    assert post.calls[0]["json"]["reasoning_effort"] == "high"
