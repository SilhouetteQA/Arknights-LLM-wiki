"""W0 T6: 报告生成（report_v1.md）：总分 / 分指标 / 分八类 / 双路径对比 / 成本汇总

W11-α 改造（母 Spec §24）：
- 报告头改为**数据驱动**的冻结元数据块 —— 删除硬编码的 judge note（它曾长期写着已失效的
  `mimo-v2.5`，使报告本身在撒谎）；
- 显式声明「与历史基线不可比」与「judge 与 agent 同模型 = 自评」；
- 新增覆盖率章节：judge 失败与 null 指标必须可见，分母不得静默漂移。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from arknights_wiki.eval.freeze import load_benchmark_spec
from arknights_wiki.eval.metrics import CATEGORY_ZH, METRICS, _mean, aggregate, summarize_cost


def _short(sha: str | None, n: int = 16) -> str:
    return (sha or "-")[:n]


def _metadata_block(spec: dict | None) -> list[str]:
    """冻结元数据块（不依赖任何硬编码常量）。"""
    if not spec:
        return [
            "## 〇、冻结元数据",
            "",
            "> ⚠️ 未找到 `benchmark-spec.json` —— 本报告缺少冻结元数据，**不可作为 Baseline 证据**。",
            "",
        ]
    models = spec.get("models") or {}
    harness = spec.get("harness") or {}
    corpus = spec.get("corpus") or {}
    lines = [
        "## 〇、冻结元数据（母 Spec §24 BenchmarkSpec）",
        "",
        f"- spec_version `{spec.get('spec_version')}` · aggregation_rules_version `{spec.get('aggregation_rules_version')}`",
        f"- harness `{harness.get('commit')}`（{harness.get('branch')}）",
        f"- corpus `{corpus.get('case_count')}` 题 · sha256 `{_short(corpus.get('corpus_sha256'), 24)}`",
        f"- agent `{models.get('agent_model')}` @ `{models.get('agent_provider')}`",
        f"- judge `{models.get('judge_model')}` @ `{models.get('judge_provider')}`",
        f"- temperature_policy `{json.dumps(spec.get('temperature_policy'), ensure_ascii=False)}`",
        f"- max_tokens_policy `{json.dumps(spec.get('max_tokens_policy'), ensure_ascii=False)}`",
    ]
    if models.get("judge_is_same_as_agent"):
        lines.append(
            "- ⚠️ **judge 与 agent 同模型 = 自评**：指标存在系统性偏差，属已知限制，必须随报告披露。"
        )
    hist = spec.get("historical_baseline") or {}
    if hist and hist.get("comparable") is False:
        lines.append(
            f"- ⚠️ **与历史基线不可比**：`{hist.get('artifact')}` 的 judge 是 `{hist.get('judge_model')}`"
            f"（overall {hist.get('overall')}），与本报告不同源 —— 禁止把两者并列比较。"
        )
    tol = spec.get("preregistered_tolerances") or {}
    if tol:
        lines.append(f"- 预登记容差（跑批前固化，禁止事后修改）：`{json.dumps(tol, ensure_ascii=False)}`")
    lines.append("")
    return lines


def _coverage_block(agg: dict) -> list[str]:
    """覆盖率与失败（W11-α）：分母与 null 必须可见。"""
    cov = agg.get("coverage") or {}
    if not cov:
        return []
    total = cov.get("rows") or 0
    fails = cov.get("judge_failure_count", 0)
    rate = f"{fails / total:.1%}" if total else "-"
    nulls = cov.get("metric_null_count") or {}
    non_null = cov.get("metric_non_null_count") or {}
    lines = [
        "",
        "## 五、覆盖率与失败（W11-α：分母必须可见）",
        "",
        f"- 结果行数：{total} · judge 失败行数：{fails} · 失败率：{rate}",
        "",
        "| 指标 | 有效值 | null（未评/失败） |",
        "|------|--------|------------------|",
    ]
    for m in METRICS:
        lines.append(f"| {m} | {non_null.get(m, 0)} | {nulls.get(m, '-')} |")
    return lines


def generate_report(results_path: Path, out_dir: Path, spec: dict | None = None) -> Path:
    """从 results_v1.jsonl 生成 report_v1.md，返回报告路径。

    `spec` 为冻结元数据；未显式传入时尝试从 `out_dir/benchmark-spec.json` 读取。
    """
    results = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if spec is None:
        spec = load_benchmark_spec(out_dir / "benchmark-spec.json")
    agg = aggregate(results)
    cost = summarize_cost(out_dir / "cost_log.jsonl")

    lines = [
        "# Agent 评测报告",
        "",
        f"> 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"> 题目数：{len(results)} 条结果 · 模式：{' / '.join(agg['modes'])}",
        "",
    ]
    lines += _metadata_block(spec)
    lines += [
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

    lines += _coverage_block(agg)

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report_v1.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
