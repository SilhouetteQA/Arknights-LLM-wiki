"""LLM chat_completion 重试测试（W2 Failure Recovery）

验证: 网络/限流异常指数退避重试；4xx 业务错误不重试；耗尽后抛异常。
"""
from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, BadRequestError

from arknights_wiki.extraction.llm_client import chat_completion

_MODEL_CFG = {"model": "test-model", "max_tokens": 100}


def _conn_error():
    return APIConnectionError(message="connection reset", request=MagicMock())


def _ok_response(text: str = "ok"):
    r = MagicMock()
    r.choices[0].message.content = text
    r.choices[0].message.tool_calls = None
    r.usage.prompt_tokens = 10
    r.usage.completion_tokens = 5
    return r


class TestChatCompletionRetry:
    def test_retries_connection_error_then_success(self):
        """APIConnectionError 前 2 次 → 第 3 次成功（默认 max_retries=2）"""
        client = MagicMock()
        calls = {"n": 0}

        def _flaky_create(**kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise _conn_error()
            return _ok_response()

        client.chat.completions.create.side_effect = _flaky_create
        with patch("arknights_wiki.extraction.llm_client.create_client", return_value=client):
            with patch("arknights_wiki.extraction.llm_client._get_model_config", return_value=_MODEL_CFG):
                content, _msg = chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert content == "ok"
        assert calls["n"] == 3

    def test_exhausted_raises(self):
        """重试耗尽后抛最后一次异常"""
        client = MagicMock()
        client.chat.completions.create.side_effect = _conn_error()
        with patch("arknights_wiki.extraction.llm_client.create_client", return_value=client):
            with patch("arknights_wiki.extraction.llm_client._get_model_config", return_value=_MODEL_CFG):
                with pytest.raises(APIConnectionError):
                    chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert client.chat.completions.create.call_count == 3  # 1 + 2 次重试

    def test_bad_request_not_retried(self):
        """4xx 业务错误不重试（立即抛出）"""
        client = MagicMock()
        client.chat.completions.create.side_effect = BadRequestError(
            "bad", response=MagicMock(status_code=400), body=None
        )
        with patch("arknights_wiki.extraction.llm_client.create_client", return_value=client):
            with patch("arknights_wiki.extraction.llm_client._get_model_config", return_value=_MODEL_CFG):
                with pytest.raises(BadRequestError):
                    chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert client.chat.completions.create.call_count == 1
