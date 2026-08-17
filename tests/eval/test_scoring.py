"""T7: DeepEvalScorer 打分层测试（fake deepeval，宿主无 deepeval 依赖）

覆盖（2026-08-17 打分审计后的关键路径）：
- VolcEngineLLM.generate：json_mode 传给 chat（mimo 推理模型 JSON 稳定关键）
- score_answer：metric_set 过滤 / hallucination 转换 / 异常→None / faithfulness GEval
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---- 注入 fake deepeval 模块（scoring.py import 需要） ----
_fake_telemetry = types.ModuleType("deepeval.telemetry")
_fake_telemetry.telemetry_opt_out = True

_fake_g_eval = types.ModuleType("deepeval.metrics.g_eval.utils")
_fake_g_eval.SingleTurnParams = type(
    "SingleTurnParams", (), {
        "ACTUAL_OUTPUT": "actual_output",
        "EXPECTED_OUTPUT": "expected_output",
        "RETRIEVAL_CONTEXT": "retrieval_context",
    }
)

_fake_deepeval = types.ModuleType("deepeval")
_fake_deepeval_metrics = types.ModuleType("deepeval.metrics")


class _FakeMetric:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.score = 0.7
        self.reason = "fake reason"

    def measure(self, tc):
        pass


_fake_deepeval_metrics.FaithfulnessMetric = _FakeMetric
_fake_deepeval_metrics.GEval = _FakeMetric
_fake_deepeval_metrics.HallucinationMetric = _FakeMetric


class _FakeLLMTestCase:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


_fake_deepeval.models = types.ModuleType("deepeval.models")
_fake_deepeval.models.DeepEvalBaseLLM = object
_fake_deepeval.test_case = types.ModuleType("deepeval.test_case")
_fake_deepeval.test_case.LLMTestCase = _FakeLLMTestCase

sys.modules.setdefault("deepeval", _fake_deepeval)
sys.modules.setdefault("deepeval.metrics", _fake_deepeval_metrics)
sys.modules.setdefault("deepeval.metrics.g_eval.utils", _fake_g_eval)
sys.modules.setdefault("deepeval.telemetry", _fake_telemetry)
sys.modules.setdefault("deepeval.models", _fake_deepeval.models)
sys.modules.setdefault("deepeval.test_case", _fake_deepeval.test_case)

# fake 注入后再 import（scoring 顶层 import deepeval）
from arknights_wiki.eval import scoring  # noqa: E402


class TestVolcEngineLLM:
    def test_generate_passes_json_mode(self):
        """json_mode=True 必须传给 chat（mimo 推理模型 JSON 稳定性关键）"""
        scorer_llm = scoring.VolcEngineLLM("mimo-v2.5")
        with patch("arknights_wiki.eval.scoring.chat") as mock_chat:
            mock_chat.return_value = {"content": '{"score": 1}', "tokens_in": 100, "tokens_out": 50, "cost": 0.0}
            out = scorer_llm.generate("judge prompt")
            assert out == '{"score": 1}'
            kwargs = mock_chat.call_args.kwargs
            assert kwargs.get("json_mode") is True
            assert kwargs.get("max_retries") == 2
            assert kwargs.get("timeout") == 300.0

    def test_generate_uses_judge_model(self):
        scorer_llm = scoring.VolcEngineLLM("custom-model")
        assert scorer_llm.get_model_name() == "custom-model"


class TestScoreAnswer:
    def _scorer(self):
        return scoring.DeepEvalScorer()

    def _failing_metric(self):
        m = MagicMock()
        m.measure.side_effect = RuntimeError("boom")
        return m

    def test_default_metric_set_all(self):
        """默认 metric_set = 全 4 指标，异常时置 None 而非 0"""
        s = self._scorer()
        with patch("arknights_wiki.eval.scoring.GEval", return_value=self._failing_metric()):
            with patch("arknights_wiki.eval.scoring.HallucinationMetric", return_value=self._failing_metric()):
                out = s.score_answer("q", "a", {"summary": "s"}, ["ctx"], [])
                assert out["answer_correctness"] is None
                assert "error" in out.get("correctness_reason", "")
                assert out["hallucination"] is None
                assert out["faithfulness"] is None

    def test_metric_set_filter(self):
        """metric_set 只算指定指标"""
        s = self._scorer()
        with patch("arknights_wiki.eval.scoring.GEval", return_value=self._failing_metric()) as m_geval:
            with patch("arknights_wiki.eval.scoring.HallucinationMetric", return_value=self._failing_metric()):
                out = s.score_answer("q", "a", {"summary": "s"}, ["ctx"], [], metric_set={"hallucination"})
        # 只算 hallucination：faithfulness/correctness 的 GEval 不应被实例化
        assert m_geval.call_count == 0
        assert "hallucination" in out
        assert "answer_correctness" not in out

    def test_hallucination_conversion(self):
        """原始分 >=0.5 → 幻觉率 1（有幻觉）；<0.5 → 0（无幻觉）"""
        s = self._scorer()
        with patch("arknights_wiki.eval.scoring.HallucinationMetric") as m_h:
            metric = MagicMock()
            metric.measure.return_value = None
            metric.score = 0.8
            metric.reason = "有幻觉"
            m_h.return_value = metric
            out = s.score_answer("q", "a", {"summary": "s"}, ["ctx"], [], metric_set={"hallucination"})
            assert out["hallucination"] == 1.0

        with patch("arknights_wiki.eval.scoring.HallucinationMetric") as m_h:
            metric = MagicMock()
            metric.measure.return_value = None
            metric.score = 0.0
            metric.reason = "无幻觉"
            m_h.return_value = metric
            out = s.score_answer("q", "a", {"summary": "s"}, ["ctx"], [], metric_set={"hallucination"})
            assert out["hallucination"] == 0.0

    def test_faithfulness_uses_geval(self):
        """faithfulness 走单次 GEval（2026-08-17 替换 FaithfulnessMetric 多次调用）"""
        s = self._scorer()
        with patch("arknights_wiki.eval.scoring.GEval") as m_g:
            metric = MagicMock()
            metric.score = 0.9
            metric.reason = "忠实"
            m_g.return_value = metric
            with patch("arknights_wiki.eval.scoring.HallucinationMetric", side_effect=RuntimeError("x")):
                out = s.score_answer("q", "a", {"summary": "s"}, ["ctx"], [], metric_set={"faithfulness"})
            assert out["faithfulness"] == 0.9
            # GEval 的 evaluation_params 应含 RETRIEVAL_CONTEXT
            _, kwargs = m_g.call_args
            params = kwargs.get("evaluation_params")
            assert "retrieval_context" in params
