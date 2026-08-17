#!/usr/bin/env python
"""W0 T1: DeepEval 连通性冒烟测试（火山引擎 doubao 作为 judge 模型）

用法：python scripts/smoke_deepeval.py
成本：1 条样例打分，<¥0.01，记录到 output/eval/cost_log.jsonl
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json

from arknights_wiki.eval import config as eval_config
from arknights_wiki.eval.llm import chat

COST_LOG = ROOT / "output" / "eval" / "cost_log.jsonl"


def _log_cost(entry: dict) -> None:
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    with COST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


from deepeval.models import DeepEvalBaseLLM


class VolcEngineLLM(DeepEvalBaseLLM):
    """DeepEval 自定义模型：火山引擎 doubao（OpenAI 兼容）"""

    def __init__(self, model_name: str | None = None):
        self._model = model_name or eval_config.get_judge_model()
        super().__init__()

    def load_model(self):
        return None

    def generate(self, prompt: str, **kwargs) -> str:
        result = chat(self._model, [{"role": "user", "content": prompt}], temperature=0.1)
        _log_cost(
            {
                "step": "deepeval_smoke",
                "model": self._model,
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
                "cost": result["cost"],
            }
        )
        return result["content"]

    async def a_generate(self, prompt: str, **kwargs) -> str:
        return self.generate(prompt, **kwargs)

    def get_model_name(self) -> str:
        return self._model


def main() -> int:
    if not eval_config.get_ark_api_key():
        print("错误：未检测到 arkcode_api", file=sys.stderr)
        return 1
    print("=== DeepEval 连通性冒烟 ===")
    print(f"judge 模型: {eval_config.get_judge_model()}")
    print(f"base: {eval_config.get_ark_base()}")

    from deepeval.metrics import FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase

    judge = VolcEngineLLM()
    test_case = LLMTestCase(
        input="德克萨斯就职于哪家公司？",
        actual_output="德克萨斯是企鹅物流的成员，在企鹅物流担任信使工作。",
        expected_output="企鹅物流",
        retrieval_context=["企鹅物流是罗德岛合作物流公司，德克萨斯为其成员与信使。"],
    )
    # 1) GEval：答案与参考答案的事实一致性（替代 3.x 的 AnswerCorrectness）
    from deepeval.metrics.g_eval.utils import SingleTurnParams

    g = GEval(
        name="answer_correctness",
        criteria="判断实际回答与参考答案在事实上是否一致（允许措辞不同，关注核心事实而非表述）",
        evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
        model=judge,
    )
    g.measure(test_case)
    print(f"GEval(correctness) score={g.score:.3f} passed={g.is_successful()}")
    print(f"  reason={g.reason}")
    # 2) Faithfulness：答案是否忠于检索上下文
    f = FaithfulnessMetric(model=judge, threshold=0.5)
    f.measure(test_case)
    print(f"Faithfulness score={f.score:.3f} passed={f.is_successful()}")
    print(f"  reason={f.reason}")
    print("\n✅ 冒烟通过：DeepEval 4.x 已能通过火山 doubao 打分")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
