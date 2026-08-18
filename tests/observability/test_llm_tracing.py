"""W1 Observability：LLM 调用（chat_completion / _llm_intent_rewrite / simple_search 回答）埋点测试

验证：开启态正确记录 model/tokens/cost；关闭态零副作用；返回值与未埋点一致。
"""
from __future__ import annotations

import pytest


class FakeUsage:
    prompt_tokens = 123
    completion_tokens = 45


class FakeMessage:
    content = "测试回答"
    tool_calls = None


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]
    usage = FakeUsage()


class FakeCompletions:
    def create(self, **kwargs):
        return FakeResponse()


class FakeChat:
    completions = FakeCompletions()


class FakeOpenAIClient:
    def __init__(self):
        self.chat = FakeChat()


class FakeLangfuseClient:
    """捕获 update_current_generation 的 fake（替代 observability.client._client）"""

    def __init__(self):
        self.updates: list[dict] = []

    def update_current_generation(self, **kwargs):
        self.updates.append(kwargs)

    def update_current_span(self, **kwargs):
        self.updates.append(kwargs)


def _enable_tracing(monkeypatch) -> FakeLangfuseClient:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
    fake = FakeLangfuseClient()
    from arknights_wiki.observability import client as obs_client

    monkeypatch.setattr(obs_client, "_client", fake)
    return fake


def _disable_tracing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)


class TestChatCompletion:
    def test_disabled_no_side_effect(self, monkeypatch):
        """关闭态：chat_completion 行为与未埋点一致，不触碰 langfuse"""
        _disable_tracing(monkeypatch)
        from arknights_wiki.extraction import llm_client

        monkeypatch.setattr(llm_client, "create_client", lambda: FakeOpenAIClient())
        content, message = llm_client.chat_completion(
            [{"role": "user", "content": "hi"}]
        )
        assert content == "测试回答"
        assert message.content == "测试回答"

    def test_enabled_records_usage(self, monkeypatch):
        """开启态：response 后记录 usage/cost 到当前 span"""
        fake_lf = _enable_tracing(monkeypatch)
        from arknights_wiki.extraction import llm_client

        monkeypatch.setattr(llm_client, "create_client", lambda: FakeOpenAIClient())
        content, _ = llm_client.chat_completion(
            [{"role": "user", "content": "hi"}], tools=[{"type": "function"}]
        )
        assert content == "测试回答"
        assert fake_lf.updates, "应调用 update_current_span 记录 usage"
        update = fake_lf.updates[-1]
        assert update["usage_details"] == {"input": 123, "output": 45}
        assert update["cost_details"]["total"] > 0  # 按 pricing 计算
        assert update["metadata"]["model"]  # 非空
        assert update["metadata"]["n_tools"] == 1


class TestRouterIntentRewrite:
    def test_enabled_records_generation(self, monkeypatch):
        """_llm_intent_rewrite 开启态记录 LLM usage（通过 record_llm_usage）"""
        fake_lf = _enable_tracing(monkeypatch)
        from arknights_wiki.agent import router
        from arknights_wiki.extraction import llm_client

        # mock create_client（_llm_intent_rewrite 内部 from extraction.llm_client import）
        class FakeJSONMessage(FakeMessage):
            content = '{"intent":"fact_lookup","canonical_entities":[],"expansion_hints":[],"rewritten_question":"测试回答","disambiguation_note":""}'

        class FakeJSONChoice:
            message = FakeJSONMessage()

        class FakeJSONResponse:
            choices = [FakeJSONChoice()]
            usage = FakeUsage()

        class FakeJSONCompletions:
            def create(self, **kwargs):
                return FakeJSONResponse()

        class FakeJSONChat:
            completions = FakeJSONCompletions()

        class FakeJSONClient:
            def __init__(self):
                self.chat = FakeJSONChat()

        monkeypatch.setattr(llm_client, "create_client", lambda: FakeJSONClient())
        result = router._llm_intent_rewrite("测试问题")
        assert result is not None
        assert fake_lf.updates, "应记录 LLM usage"
        update = fake_lf.updates[-1]
        assert update["usage_details"] == {"input": 123, "output": 45}
        assert update["metadata"]["model"]
        assert "latency_ms" in update["metadata"]
