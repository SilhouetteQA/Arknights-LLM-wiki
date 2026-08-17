"""W0 T5: LLM-as-judge 六指标评分（doubao-seed-1-6-flash）与规则指标

指标（Spec §3.4）：
- LLM judge 四项：answer_correctness / faithfulness / citation_accuracy / hallucination
- 规则两项：tool_selection_accuracy / task_completion_rate（不消耗 LLM）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from arknights_wiki.eval import config as eval_config
from arknights_wiki.eval.llm import chat_json
from arknights_wiki.eval.metrics import rule_metrics  # 单一数据源（judge/scoring 共用）

COST_LOG = Path(__file__).resolve().parents[2] / "output" / "eval" / "cost_log.jsonl"


def _log_cost(entry: dict) -> None:
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    with COST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

JUDGE_SYSTEM_PROMPT = """你是《明日方舟》剧情专家评审。你只依据给出的「参考答案与证据」和「用户答案」进行客观评分，不臆测。

评分指标（全部输出 0-1 的小数，保留 1 位）：
1. answer_correctness：答案的事实正确性（与参考答案要点一致程度）
2. faithfulness：答案声称的内容是否都能在提供的证据/知识库依据中找到出处（无依据即扣分）
3. citation_accuracy：答案中提及的章节/角色/组织等引用是否准确；若答案完全不涉及引用，输出 null
4. hallucination：答案是否存在明显编造/无依据的断言（0=无幻觉，1=有幻觉）

输出严格 JSON：{"answer_correctness": 0.0-1.0, "faithfulness": 0.0-1.0, "citation_accuracy": 0.0-1.0|null, "hallucination": 0|1, "reason": "一两句中文理由"}"""


def _build_prompt(question: str, answer: str, answer_key: dict) -> str:
    summary = (answer_key or {}).get("summary", "")
    evidence = (answer_key or {}).get("evidence", [])
    return (
        f"问题：{question}\n\n"
        f"参考答案要点：{summary}\n"
        f"参考答案证据：{json.dumps(evidence, ensure_ascii=False)}\n\n"
        f"用户答案（待评分）：{answer[:3000]}\n\n"
        "请按系统要求输出六指标 JSON。"
    )


def _validate(parsed: dict) -> dict | None:
    """校验 judge 输出 schema；不合法返回 None（触发重试）"""
    required = {"answer_correctness", "faithfulness", "hallucination", "reason"}
    if not all(k in parsed for k in required):
        return None
    for k in ("answer_correctness", "faithfulness"):
        v = parsed.get(k)
        if not isinstance(v, (int, float)) or not (0.0 <= float(v) <= 1.0):
            return None
    h = parsed.get("hallucination")
    if h not in (0, 1):
        return None
    ca = parsed.get("citation_accuracy")
    if ca is not None and (not isinstance(ca, (int, float)) or not (0.0 <= float(ca) <= 1.0)):
        return None
    return parsed


def judge_answer(
    question: str,
    answer: str,
    answer_key: dict,
    tools_called: list[str],
    expected_tools: list[str],
    expected_behavior: str,
) -> dict:
    """六指标评分。返回 {metrics..., reason, _stats}；judge 失败时返回降级值。"""
    prompt = _build_prompt(question, answer, answer_key)
    for attempt in range(2):
        try:
            out = chat_json(
                eval_config.get_judge_model(),
                JUDGE_SYSTEM_PROMPT,
                prompt,
            )
            stats = out.pop("_stats", {})
            parsed = _validate(out)
            if parsed is not None:
                parsed["_stats"] = stats
                _log_cost(
                    {
                        "step": "judge",
                        "model": eval_config.get_judge_model(),
                        "tokens_in": stats.get("tokens_in", 0),
                        "tokens_out": stats.get("tokens_out", 0),
                        "cost": stats.get("cost", 0.0),
                    }
                )
                return parsed
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:200]
            continue
    return {
        "answer_correctness": 0.0,
        "faithfulness": 0.0,
        "citation_accuracy": None,
        "hallucination": 1,
        "reason": f"judge 调用失败: {last_err}",
        "_stats": {},
    }
