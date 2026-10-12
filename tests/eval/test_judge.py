"""T5: judge 与规则指标测试（mock LLM）"""
from unittest.mock import patch

import pytest

from arknights_wiki.eval.judge import _validate, judge_answer


class TestValidate:
    def test_valid(self):
        ok = _validate(
            {
                "answer_correctness": 0.8,
                "faithfulness": 0.9,
                "citation_accuracy": None,
                "hallucination": 0,
                "reason": "ok",
            }
        )
        assert ok is not None

    def test_missing_field(self):
        assert _validate({"answer_correctness": 0.5}) is None

    def test_out_of_range(self):
        assert _validate({"answer_correctness": 1.5, "faithfulness": 0.5, "hallucination": 0, "reason": "x"}) is None

    def test_bad_hallucination(self):
        assert _validate({"answer_correctness": 0.5, "faithfulness": 0.5, "hallucination": 2, "reason": "x"}) is None


class TestJudgeAnswer:
    @patch("arknights_wiki.eval.judge.chat_json")
    def test_success(self, mock_chat):
        mock_chat.return_value = {
            "answer_correctness": 0.7,
            "faithfulness": 0.8,
            "citation_accuracy": 1.0,
            "hallucination": 0,
            "reason": "基本正确",
            "_stats": {"tokens_in": 100, "tokens_out": 50, "cost": 0.001},
        }
        out = judge_answer("q", "a", {"summary": "s", "evidence": ["e"]}, [], [], "simple")
        assert out["answer_correctness"] == 0.7
        assert out["_stats"]["tokens_in"] == 100

    @patch("arknights_wiki.eval.judge.chat_json")
    def test_invalid_then_retry(self, mock_chat):
        mock_chat.side_effect = [
            {"answer_correctness": 99, "faithfulness": 0.5, "hallucination": 0, "reason": "bad"},
            {"answer_correctness": 0.6, "faithfulness": 0.5, "hallucination": 0, "reason": "ok"},
        ]
        out = judge_answer("q", "a", {}, [], [], "simple")
        assert out["answer_correctness"] == 0.6

    @patch("arknights_wiki.eval.judge.chat_json", side_effect=RuntimeError("api down"))
    def test_failure_is_unknown_not_zero(self, _):
        """W11-α：judge 失败必须表达为**未知**（None + judge_error），不得伪造成 0 分。

        旧行为返回 hallucination=1（等价 0 分）且无失败标记 —— 度量会撒谎，聚合分母也会静默漂移。
        presence-aware 红线：Unknown ≠ Zero。
        """
        out = judge_answer("q", "a", {}, [], [], "simple")
        assert out["judge_error"] is True
        assert out["answer_correctness"] is None
        assert out["faithfulness"] is None
        assert out["citation_accuracy"] is None
        assert out["hallucination"] is None
        assert "judge 调用失败" in out["reason"]
