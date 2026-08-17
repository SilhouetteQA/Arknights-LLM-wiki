"""W0 T6: 指标聚合与报告生成（纯函数，可单测）"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CATEGORY_ZH = {
    "character": "人物",
    "event": "事件",
    "region": "国家地区",
    "organization": "组织",
    "combat_power": "战斗力",
    "worldview": "世界观",
    "no_answer": "无答案",
    "hallucination_bait": "易幻觉",
}

METRICS = [
    "answer_correctness",
    "faithfulness",
    "citation_accuracy",
    "tool_selection_accuracy",
    "hallucination",
    "task_completion",
]


def _mean(values: list[float]) -> float:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def rule_metrics(
    answer: str,
    tools_called: list[str],
    expected_tools: list[str],
    expected_behavior: str,
) -> dict:
    """规则指标（零 LLM 成本）：tool_selection_accuracy / task_completion

    W0 打分审计后统一单一数据源（2026-08-17）:
    - tool_selection：Agent 为自适应 ReAct，要求 actual ⊆ expected 过严（多调探索工具即判 0，
      实测 62/100 误伤）。正确语义：调用了预期工具集中的至少一个 → 正确。
    - task_completion：reject 题必须给出拒绝说明；正常题必须给出实质答案（≥20 字）。
    """
    expected = set(expected_tools or [])
    actual = set(tools_called or [])
    if expected_behavior == "simple":
        # simple 路由走检索管线不调工具——这是正确行为，工具选择视为符合
        tool_ok = 1.0
    elif not expected:
        tool_ok = 1.0
    else:
        tool_ok = 1.0 if (actual & expected) else 0.0

    if expected_behavior == "reject":
        reject_ok = any(kw in answer for kw in ("无法", "未找到", "没有", "不存在", "知识库", "资料", "无法回答"))
        task_ok = 1.0 if reject_ok else 0.0
    else:
        task_ok = 1.0 if len(answer.strip()) >= 20 else 0.0
    return {"tool_selection_accuracy": tool_ok, "task_completion": task_ok}


def hallucination_rate(raw_score: float) -> float:
    """deepeval 4.x HallucinationMetric 原始分 → 幻觉率 0/1。

    judge reason 实证：score 0 = 无幻觉（"aligns with all provided contexts"），
    score >= threshold(0.5) = 有幻觉。2026-08-17 修复反转。
    """
    return 1.0 if raw_score >= 0.5 else 0.0


def aggregate(results: list[dict]) -> dict:
    """按模式聚合：总分 + 分指标 + 分八类"""
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_mode[r.get("mode", "?")].append(r)

    modes = sorted(by_mode)
    out: dict = {"modes": modes, "by_mode": {}, "overall": {}}

    for mode in modes:
        rows = by_mode[mode]
        per_metric: dict[str, float | None] = {}
        for m in METRICS:
            vals = []
            for row in rows:
                metrics = row.get("metrics") or {}
                j = row.get("judge") or {}
                if m in metrics:
                    vals.append(metrics[m])
                elif m in j and m != "hallucination":
                    vals.append(j[m])
                elif m == "hallucination" and j.get("hallucination") is not None:
                    vals.append(1 - int(j["hallucination"]))  # 无幻觉率
            per_metric[m] = _mean(vals) if vals else None
        per_metric["overall"] = _mean([v for v in per_metric.values() if v is not None])
        out["by_mode"][mode] = per_metric

        # 分八类（该模式）
        per_cat: dict[str, dict] = {}
        for cat in sorted({r.get("category", "?") for r in rows}):
            cat_rows = [r for r in rows if r.get("category") == cat]
            cat_vals = {"count": len(cat_rows)}
            for m in METRICS:
                vals = []
                for row in cat_rows:
                    metrics = row.get("metrics") or {}
                    j = row.get("judge") or {}
                    if m in metrics:
                        vals.append(metrics[m])
                    elif m in j and m != "hallucination":
                        vals.append(j[m])
                    elif m == "hallucination" and j.get("hallucination") is not None:
                        vals.append(1 - int(j["hallucination"]))
                cat_vals[m] = _mean(vals) if vals else None
            cat_vals["overall"] = _mean([v for v in cat_vals.values() if v is not None])
            per_cat[cat] = cat_vals
        out["by_mode"][mode] = {"metrics": per_metric, "categories": per_cat}

    # overall：全模式合并
    all_rows = list(by_mode.values())
    flat = [r for rows in all_rows for r in rows]
    if flat:
        ov: dict[str, float | None] = {}
        for m in METRICS:
            vals = []
            for row in flat:
                metrics = row.get("metrics") or {}
                j = row.get("judge") or {}
                if m in metrics:
                    vals.append(metrics[m])
                elif m in j and m != "hallucination":
                    vals.append(j[m])
                elif m == "hallucination" and j.get("hallucination") is not None:
                    vals.append(1 - int(j["hallucination"]))
            ov[m] = _mean(vals) if vals else None
        ov["overall"] = _mean([v for v in ov.values() if v is not None])
        out["overall"] = ov
    return out


def summarize_cost(cost_log_path: Path) -> dict:
    """汇总 cost_log.jsonl → 分步骤/总计"""
    if not cost_log_path.exists():
        return {"total": 0.0, "steps": {}}
    total = 0.0
    steps: dict[str, dict] = {}
    for line in cost_log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        cost = float(e.get("cost", 0) or 0)
        total += cost
        step = e.get("step", "unknown")
        s = steps.setdefault(step, {"count": 0, "cost": 0.0})
        s["count"] += 1
        s["cost"] = round(s["cost"] + cost, 6)
    return {"total": round(total, 4), "steps": steps}

def get_category_zh() -> dict:
    return dict(CATEGORY_ZH)
