"""W0 T5: LLM-as-judge 六指标评分（doubao-seed-1-6-flash）与规则指标

指标（Spec §3.4）：
- LLM judge 四项：answer_correctness / faithfulness / citation_accuracy / hallucination
- 规则两项：tool_selection_accuracy / task_completion_rate（不消耗 LLM）
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from arknights_wiki.eval import config as eval_config
from arknights_wiki.eval.llm import chat_json
from arknights_wiki.eval.metrics import rule_metrics  # 单一数据源（judge/scoring 共用）


def cost_log_path() -> Path:
    """成本日志路径（W11-D2）。

    与 `runner.py` 同口径：尊重 `ARKNIGHTS_COST_LOG`。此前这里**硬编码**全局路径，
    于是 `--out <dir>` 的跑批把 judge 开销写到别处 —— 冻结基线的成本章节会漏掉
    全部 judge 成本（实测：17 条 judge 落全局、14 条 agent 落基线目录）。
    """
    env = os.environ.get("ARKNIGHTS_COST_LOG", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "output" / "eval" / "cost_log.jsonl"


def _log_cost(entry: dict) -> None:
    cost_log = cost_log_path()
    cost_log.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    # Spec 07 旁路观察：entry 形成后、实际写入前观察（stage=judge）。
    # 不改 entry、不改路径/编码/append 次数，也不改变任何返回。
    from arknights_wiki.adapters.foundation.runtime import observe_eval_cost_entry

    observe_eval_cost_entry(entry, stage="judge")
    with cost_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

JUDGE_SYSTEM_PROMPT = """你是《明日方舟》剧情专家评审。你只依据给出的「参考答案与证据」「Agent 实际检索到的资料」和「用户答案」进行客观评分，不臆测。

评分指标（全部输出 0-1 的小数，保留 1 位）：
1. answer_correctness：答案的事实正确性（与参考答案要点一致程度）
2. faithfulness：答案声称的内容能否在**实际检索到的资料或参考答案证据**中找到出处（无依据即扣分）
3. citation_accuracy：答案中提及的章节/角色/组织等引用是否准确；若答案完全不涉及引用，输出 null
4. hallucination：答案是否存在**在上述两类依据中都找不到出处**的编造/无依据断言（0=无幻觉，1=有幻觉）

注意：只有在一份依据里出现即可算"有据"——实际检索资料与参考答案证据互为补充，不得因为某条事实只出现在其中一方就扣分。

输出严格 JSON：{"answer_correctness": 0.0-1.0, "faithfulness": 0.0-1.0, "citation_accuracy": 0.0-1.0|null, "hallucination": 0|1, "reason": "一两句中文理由"}"""

#: W11-D4：传给 judge 的检索上下文总量上限（控制在成本与失真之间的平衡）
_MAX_CONTEXT_CHARS = 7000
_MAX_CTX_DOC_CHARS = 1200


def _render_context(retrieval_context: list[str] | None) -> str:
    """把 agent 实际检索到的资料渲染成 judge 可读的段落（W11-D4）。

    此前 judge 只拿到参考答案，于是长答案里凡不在参考答案里的内容都被判为"无据"——
    faithfulness 被系统性压低、hallucination 被系统性判 1，而这两项指标名义上衡量的正是
    "是否有据"。实际检索上下文一直存在（结果行里的 `retrieval_context`），只是没传给 judge。
    """
    docs = [d for d in (retrieval_context or []) if d]
    if not docs:
        return "（本次未记录到检索资料）"
    parts: list[str] = []
    used = 0
    for i, doc in enumerate(docs, 1):
        text = str(doc)[:_MAX_CTX_DOC_CHARS]
        if used + len(text) > _MAX_CONTEXT_CHARS:
            parts.append(f"[{i}] （后续资料因上下文预算省略）")
            break
        parts.append(f"[{i}] {text}")
        used += len(text)
    return "\n\n".join(parts)


def _build_prompt(
    question: str,
    answer: str,
    answer_key: dict,
    retrieval_context: list[str] | None = None,
) -> str:
    summary = (answer_key or {}).get("summary", "")
    evidence = (answer_key or {}).get("evidence", [])
    return (
        f"问题：{question}\n\n"
        f"参考答案要点：{summary}\n"
        f"参考答案证据：{json.dumps(evidence, ensure_ascii=False)}\n\n"
        f"Agent 实际检索到的资料（判定 faithfulness / hallucination 的一等依据）：\n"
        f"{_render_context(retrieval_context)}\n\n"
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
    retrieval_context: list[str] | None = None,
) -> dict:
    """六指标评分。返回 {metrics..., reason, _stats}。

    W11-α（母 Spec §24 / presence-aware 红线）：judge 调用失败时返回**显式的失败标记**
    （`judge_error=True`，四项 judge 指标一律为 `None`），而**不是**降级为 0 分。
    理由：Unknown ≠ Zero —— 把"没评上"写成 0 分，会让度量本身撒谎，并让聚合分母静默漂移。
    失败行由 `metrics.aggregate()` 计入 `judge_failure_count`，不计入指标均值。

    W11-D4：`retrieval_context` 是 agent **实际**检索到的资料，作为 faithfulness /
    hallucination 的一等判据。不传时行为与改造前一致（仅用参考答案），保持向后兼容。
    """
    prompt = _build_prompt(question, answer, answer_key, retrieval_context)
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
        "answer_correctness": None,
        "faithfulness": None,
        "citation_accuracy": None,
        "hallucination": None,
        "judge_error": True,
        "reason": f"judge 调用失败: {last_err}",
        "_stats": {},
    }
