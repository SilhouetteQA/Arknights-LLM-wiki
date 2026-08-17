"""W0 M4: DeepEval 4.x 打分层（容器内运行）

指标映射（Spec §3.3）：
- answer_correctness → GEval（vs answer_key）
- faithfulness → FaithfulnessMetric（vs 材料/检索上下文）
- hallucination → HallucinationMetric（vs 材料）
- citation_accuracy → 自定义 judge（GEval）
- tool_selection_accuracy / task_completion → 规则指标（纯函数，非 LLM）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# 禁用 deepeval 遥测（posthog 出网会挂起导致 measure 极慢）——必须在 import metrics 前
from deepeval.telemetry import telemetry_opt_out

telemetry_opt_out = True

from deepeval.metrics import FaithfulnessMetric, GEval, HallucinationMetric
from deepeval.metrics.g_eval.utils import SingleTurnParams
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from arknights_wiki.eval import config as eval_config
from arknights_wiki.eval.llm import chat
from arknights_wiki.eval.metrics import hallucination_rate, rule_metrics  # 单一数据源

COST_LOG = Path(__file__).resolve().parents[2] / "output" / "eval" / "cost_log.jsonl"


def _log_cost(entry: dict) -> None:
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    with COST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class VolcEngineLLM(DeepEvalBaseLLM):
    """DeepEval 自定义模型：火山引擎（OpenAI 兼容）"""

    def __init__(self, model_name: str | None = None):
        self._model = model_name or eval_config.get_judge_model()
        super().__init__()

    def load_model(self):
        return None

    def generate(self, prompt: str, **kwargs) -> str:
        # timeout=300, max_retries=2：超时场景重试是纯浪费（火山长上下文生成慢）
        # json_mode=True：DeepEval 各指标要求 judge 输出 JSON；mimo-v2.5 推理模型偶尔
        #   夹带思考/格式漂移导致 invalid JSON，强制 response_format=json_object 稳定解析
        result = chat(self._model, [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=4096, max_retries=2, timeout=300.0, json_mode=True)
        _log_cost({"step": "judge", "model": self._model, "tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"], "cost": result["cost"]})
        return result["content"]

    async def a_generate(self, prompt: str, **kwargs) -> str:
        return self.generate(prompt, **kwargs)

    def get_model_name(self) -> str:
        return self._model


class DeepEvalScorer:
    """DeepEval 4.x 指标封装（judge = 火山引擎）"""

    def __init__(self):
        self.judge = VolcEngineLLM()

    def score_answer(
        self,
        question: str,
        answer: str,
        answer_key: dict,
        material_texts: list[str],
        retrieval_context: list[str] | None = None,
        metric_set: set[str] | None = None,
    ) -> dict:
        """返回六指标评分；retrieval_context 为 Agent 实际检索上下文（faithfulness/hallucination 依据）；
        metric_set 控制计算哪些指标（默认全量）"""
        metric_set = metric_set or {"correctness", "faithfulness", "hallucination", "citation"}
        expected = answer_key.get("summary", "")
        retrieval_context = retrieval_context or material_texts or answer_key.get("evidence", [])
        tc = LLMTestCase(
            input=question,
            actual_output=answer,
            expected_output=expected,
            context=retrieval_context,          # Hallucination 指标使用 context
            retrieval_context=retrieval_context,  # Faithfulness 指标使用 retrieval_context
        )
        out: dict = {}

        # 1) correctness (GEval)
        if "correctness" in metric_set:
            g = GEval(
                name="answer_correctness",
                criteria="判断实际回答与参考答案在事实上是否一致（允许措辞不同，关注核心事实而非表述）",
                evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
                model=self.judge,
                async_mode=False,
            )
            try:
                g.measure(tc)
                out["answer_correctness"] = round(float(g.score), 3)
                out["correctness_reason"] = g.reason
            except Exception as e:  # noqa: BLE001
                out["answer_correctness"] = None  # 失败≠错误：与其它指标一致（用量/报错区分）
                out["correctness_reason"] = f"error: {str(e)[:150]}"

        # 2) faithfulness
        if "faithfulness" in metric_set:
            # 2026-08-17: 弃用 deepeval FaithfulnessMetric（内部 claims→verdicts→truths→reason
            # 多次 LLM 调用，长上下文下每题十几分钟且读超时）。改用单次 GEval：
            # 一次 judge 调用直接判"回答是否忠实于检索上下文"，可控超时内完成。
            f = GEval(
                name="faithfulness",
                criteria=(
                    "判断实际回答是否忠实于提供的检索上下文（context）："
                    "回答中的所有事实性陈述都应能在上下文中找到依据；"
                    "完全基于上下文得 1.0，有部分超出上下文的内容按比例扣分，完全无依据得 0。"
                ),
                evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
                model=self.judge,
                async_mode=False,
            )
            try:
                f.measure(tc)
                out["faithfulness"] = round(float(f.score), 3)
                out["faithfulness_reason"] = f.reason
            except Exception as e:  # noqa: BLE001
                out["faithfulness"] = None
                out["faithfulness_reason"] = f"error: {str(e)[:150]}"

        # 3) hallucination（无依据断言）
        if "hallucination" in metric_set:
            h = HallucinationMetric(model=self.judge, threshold=0.5, async_mode=False)
            try:
                h.measure(tc)
                # deepeval 4.x HallucinationMetric: score 0 = 无幻觉（judge reason 实证
                # "score is 0.00 because the actual output aligns with all provided contexts"）。
                # score >= threshold(0.5) = 有幻觉 → 幻觉率 0/1。2026-08-17 修复反转 bug。
                out["hallucination"] = hallucination_rate(h.score)
                out["hallucination_reason"] = h.reason
            except Exception as e:  # noqa: BLE001
                out["hallucination"] = None
                out["hallucination_reason"] = f"error: {str(e)[:150]}"

        # 4) citation_accuracy（自定义 judge：答案中引用是否准确）
        if "citation" in metric_set:
            cit = GEval(
                name="citation_accuracy",
                criteria="检查实际回答中提及的章节/角色/组织/事件等引用是否与参考答案证据一致；若回答无任何引用，输出 1.0（不适用）",
                evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
                model=self.judge,
                async_mode=False,
            )
            try:
                cit.measure(tc)
                out["citation_accuracy"] = round(float(cit.score), 3)
            except Exception as e:  # noqa: BLE001
                out["citation_accuracy"] = None
                out["citation_reason"] = f"error: {str(e)[:150]}"

        return out
