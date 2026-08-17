"""T2: eval LLM 客户端测试（mock httpx，零真实调用）"""
from unittest.mock import MagicMock, patch

import pytest

from arknights_wiki.eval import llm

MODEL = "doubao-seed-1-6-flash-250828"


def _fake_response(content: str, tin: int = 10, tout: int = 5) -> MagicMock:
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": tin, "completion_tokens": tout},
    }
    return fake


class TestComputeCost:
    def test_known_price(self):
        # pricing.json: in=0.3/1M, out=0.6/1M → 1M in + 0.5M out = 0.6 元
        assert llm.compute_cost(MODEL, 1_000_000, 500_000) == pytest.approx(0.6)

    def test_unknown_model_zero(self):
        assert llm.compute_cost("no-such-model", 1000, 1000) == 0.0


class TestChat:
    @patch("arknights_wiki.eval.config.get_opencode_go_key", return_value="sk-x")
    @patch("arknights_wiki.eval.llm.httpx.post")
    def test_success(self, mock_post, _):
        mock_post.return_value = _fake_response("你好", tin=10, tout=5)
        r = llm.chat(MODEL, [{"role": "user", "content": "hi"}])
        assert r["content"] == "你好"
        assert r["tokens_in"] == 10
        assert r["tokens_out"] == 5
        assert r["cost"] > 0
        assert r["latency_ms"] >= 0
        assert r["model"] == MODEL

    @patch("arknights_wiki.eval.config.get_opencode_go_key", return_value="sk-x")
    @patch("arknights_wiki.eval.llm.httpx.post")
    def test_retry_then_success(self, mock_post, _):
        import httpx

        def side_effect(*a, **kw):
            if mock_post.call_count == 1:
                raise httpx.ConnectError("boom")
            return _fake_response("ok")

        mock_post.side_effect = side_effect
        r = llm.chat(MODEL, [{"role": "user", "content": "hi"}], max_retries=2)
        assert r["content"] == "ok"
        assert mock_post.call_count == 2

    @patch("arknights_wiki.eval.config.get_opencode_go_key", return_value="sk-x")
    @patch("arknights_wiki.eval.llm.httpx.post")
    def test_all_fail_raises(self, mock_post, _):
        import httpx

        mock_post.side_effect = httpx.ConnectError("boom")
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            llm.chat(MODEL, [{"role": "user", "content": "hi"}], max_retries=1)

    @patch("arknights_wiki.eval.config.get_opencode_go_key", return_value="")
    def test_missing_key_raises(self, _):
        with pytest.raises(RuntimeError, match="opencode_go_api"):
            llm.chat(MODEL, [])


class TestParseAndChatJson:
    def test_parse_json_block(self):
        raw = "```json\n{\"a\": 1}\n```"
        assert llm.parse_llm_json(raw) == {"a": 1}

    def test_parse_plain_json(self):
        assert llm.parse_llm_json('{"a": 2}') == {"a": 2}

    def test_parse_think_tags_stripped(self):
        raw = "<think>思考</think>{\"a\": 3}"
        assert llm.parse_llm_json(raw) == {"a": 3}

    def test_parse_fail_returns_none(self):
        assert llm.parse_llm_json("不是 JSON") is None

    @patch("arknights_wiki.eval.config.get_ark_api_key", return_value="sk-x")
    @patch("arknights_wiki.eval.llm.httpx.post")
    def test_chat_json_success(self, mock_post, _):
        mock_post.return_value = _fake_response('{"answer": 42}')
        out = llm.chat_json(MODEL, "sys", "usr")
        assert out["answer"] == 42
        assert "_stats" in out

    @patch("arknights_wiki.eval.config.get_ark_api_key", return_value="sk-x")
    @patch("arknights_wiki.eval.llm.httpx.post")
    def test_chat_json_parse_fail_raises(self, mock_post, _):
        mock_post.return_value = _fake_response("not json at all")
        with pytest.raises(RuntimeError, match="JSON 解析失败"):
            llm.chat_json(MODEL, "sys", "usr", max_retries=1)
