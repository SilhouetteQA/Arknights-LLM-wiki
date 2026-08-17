"""W0 T6: 报告生成（report_v1.md）：总分 / 分指标 / 分八类 / 双路径对比 / 成本汇总"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from arknights_wiki.eval.metrics import CATEGORY_ZH, METRICS, _mean, aggregate, summarize_cost

JUDGE_NOTE = "opencode zen/go 网关 mimo-v2.5（judge 精确计费；agent 侧成本为字符估算，含 estimate 标记）"


def generate_report(results_path: Path, out_dir: Path) -> Path:
    """从 results_v1.jsonl 生成 report_v1.md，返回报告路径"""
    results = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    agg = aggregate(results)
    cost = summarize_cost(out_dir / "cost_log.jsonl")

    lines = [
        "# Agent V1 评测报告",
        "",
        f"> 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"> 题目数：{len(results)} 条结果 · 模式：{' / '.join(agg['modes'])}",
        f"> judge：{JUDGE_NOTE}",
        "",
        "## 一、总分与分指标",
        "",
        "| 指标 | 总分 | " + " | ".join(agg["modes"]) + " |",
        "|------|------|" + "|".join(["------"] * len(agg["modes"])) + "|",
    ]
    ov = agg.get("overall", {})
    line = "| overall | " + (f"{ov.get('overall', '-')}" if ov else "-")
    for mode in agg["modes"]:
        v = agg["by_mode"][mode]["metrics"].get("overall")
        line += f" | {v if v is not None else '-'}"
    lines.append(line + " |")
    for m in METRICS:
        v = ov.get(m) if ov else None
        line = f"| {m} | {v if v is not None else '-'}"
        for mode in agg["modes"]:
            v = agg["by_mode"][mode]["metrics"].get(m)
            line += f" | {v if v is not None else '-'}"
        lines.append(line + " |")

    lines += [
        "",
        "## 二、分八类",
        "",
        "| 类别 | 题数 | overall | correctness | faithfulness | 无幻觉率 | task_completion |",
        "|------|------|---------|-------------|--------------|----------|-----------------|",
    ]
    per_cat: dict[str, dict] = {}
    for mode in agg["modes"]:
        for cat, vals in agg["by_mode"][mode]["categories"].items():
            target = per_cat.setdefault(cat, {"count": 0, "vals": []})
            target["count"] += vals["count"]
            target["vals"].append(vals)

    def cat_mean(info: dict, key: str):
        vals = [v.get(key) for v in info["vals"] if v.get(key) is not None]
        return _mean(vals) if vals else None

    for cat in sorted(per_cat, key=lambda c: CATEGORY_ZH.get(c, c)):
        info = per_cat[cat]
        o = cat_mean(info, "overall")
        ac = cat_mean(info, "answer_correctness")
        fa = cat_mean(info, "faithfulness")
        hl = cat_mean(info, "hallucination")
        tc = cat_mean(info, "task_completion")
        lines.append(
            f"| {CATEGORY_ZH.get(cat, cat)} | {info['count']} | "
            f"{o if o is not None else '-'} | {ac if ac is not None else '-'} | "
            f"{fa if fa is not None else '-'} | {hl if hl is not None else '-'} | {tc if tc is not None else '-'} |"
        )

    lines += ["", "## 三、成本汇总", "", f"- **总计：¥{cost['total']}**", "- 分步骤："]
    for step, s in sorted(cost["steps"].items()):
        lines.append(f"  - {step}: {s['count']} 次 · ¥{s['cost']}")

    lines += ["", "## 四、双路径对比（direct vs http）", ""]
    if "direct" in agg["by_mode"] and "http" in agg["by_mode"]:
        d = agg["by_mode"]["direct"]["metrics"]
        h = agg["by_mode"]["http"]["metrics"]
        lines += ["| 指标 | direct | http | 差异 |", "|------|--------|------|------|"]
        for m in ["overall"] + METRICS:
            dv, hv = d.get(m), h.get(m)
            diff = ""
            if dv is not None and hv is not None:
                diff = f"{round(hv - dv, 3):+.3f}"
            lines.append(f"| {m} | {dv if dv is not None else '-'} | {hv if hv is not None else '-'} | {diff} |")
    else:
        lines.append("（当前仅单一模式，无对比）")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report_v1.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
