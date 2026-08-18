"""W1 Observability 层测试：开关三态 / traced no-op / cost 计算 / LLM usage 记录"""
from __future__ import annotations

import pytest

from arknights_wiki.observability import (
    compute_cost_rmb,
    flush,
    is_enabled,
    record_llm_usage,
    traced,
)


class TestIsEnabled:
    def test_disabled_no_keys(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
        monkeypatch.delenv("ARKNIGHTS_TRACING", raising=False)
        assert is_enabled() is False

    def test_disabled_missing_one_key(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
        assert is_enabled() is False

    def test_enabled_all_keys(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
        monkeypatch.delenv("ARKNIGHTS_TRACING", raising=False)
        assert is_enabled() is True

    def test_forced_off_by_env(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
        monkeypatch.setenv("ARKNIGHTS_TRACING", "0")
        assert is_enabled() is False


class TestTraced:
    def test_disabled_passthrough(self, monkeypatch):
        """关闭态：原函数直通，结果与元数据完全一致，无任何 langfuse 副作用"""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

        calls = []

        @traced(name="demo", as_type="span")
        def add(a, b):
            calls.append((a, b))
            return a + b

        assert add(1, 2) == 3
        assert add(10, 20) == 30
        assert calls == [(1, 2), (10, 20)]  # 原函数正常执行两次

    def test_disabled_preserves_identity(self, monkeypatch):
        """关闭态返回原函数引用（零开销断言）"""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

        def raw():
            return "ok"

        wrapped = traced(name="x")(raw)
        assert wrapped is raw

    def test_enabled_uses_langfuse_observe(self, monkeypatch):
        """开启态：调用 langfuse observe 包装（mock 避免真实网络）"""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")

        observed_calls = []

        def fake_observe(*, name, as_type, capture_input, capture_output):
            def deco(func):
                def wrapper(*args, **kwargs):
                    observed_calls.append((name, as_type, args, kwargs))
                    return func(*args, **kwargs)

                return wrapper

            return deco

        import langfuse

        monkeypatch.setattr(langfuse, "observe", fake_observe)

        @traced(name="demo", as_type="generation")
        def echo(x):
            return x

        assert echo("hi") == "hi"
        assert observed_calls and observed_calls[0][0] == "demo"
        assert observed_calls[0][1] == "generation"

    def test_enabled_metadata_fn(self, monkeypatch):
        """开启态：metadata_fn 返回值写入 span metadata"""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")

        def fake_observe(*, name, as_type, capture_input, capture_output):
            def deco(func):
                def wrapper(*args, **kwargs):
                    return func(*args, **kwargs)

                return wrapper

            return deco

        class FakeClient:
            def __init__(self):
                self.updated = []

            def update_current_span(self, *, metadata=None, **kwargs):
                self.updated.append(metadata)

        fake_client = FakeClient()

        import langfuse
        from arknights_wiki.observability import client as obs_client

        monkeypatch.setattr(langfuse, "observe", fake_observe)
        monkeypatch.setattr(obs_client, "_client", fake_client)

        @traced(name="demo", metadata_fn=lambda args, kwargs, result: {"value": result})
        def double(x):
            return x * 2

        assert double(21) == 42
        assert fake_client.updated == [{"value": 42}]


class TestCost:
    def test_compute_cost_known_model(self):
        """deepseek-4-flash 单价：in 2.0 / out 8.0 每百万 tokens（pricing.json 实际值）"""
        cost = compute_cost_rmb("deepseek-4-flash", 1000, 2000)
        assert cost == pytest.approx(1000 / 1e6 * 2.0 + 2000 / 1e6 * 8.0)  # 0.018

    def test_compute_cost_unknown_model_zero(self):
        assert compute_cost_rmb("no-such-model", 1000, 1000) == 0.0


class TestRecordLLMUsage:
    def test_disabled_noop(self, monkeypatch):
        """关闭态 record_llm_usage 无副作用（不抛异常）"""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        record_llm_usage("deepseek-v4-flash", 100, 200, 0.5)
        assert True

    def test_enabled_calls_update(self, monkeypatch):
        """开启态：client.update_current_span 写入 usage/cost"""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")

        class FakeClient:
            def __init__(self):
                self.captured = {}

            def update_current_generation(self, **kwargs):
                self.captured.update(kwargs)

            def update_current_span(self, **kwargs):
                self.captured.update(kwargs)

        fake_client = FakeClient()
        from arknights_wiki.observability import client as obs_client

        monkeypatch.setattr(obs_client, "_client", fake_client)

        record_llm_usage("deepseek-4-flash", 100, 200, 0.42, extra={"retry": 1})
        assert fake_client.captured["usage_details"] == {"input": 100, "output": 200}
        assert fake_client.captured["cost_details"] == {"total": 0.42}
        assert fake_client.captured["metadata"]["model"] == "deepseek-4-flash"
        assert fake_client.captured["metadata"]["retry"] == 1


class TestFlush:
    def test_disabled_flush_noop(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        flush()  # 不应抛异常
        assert True
