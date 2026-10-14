"""W11-α T7：按预登记容差判定两次跑批是否可复现（母 Spec §24 / Spec §3.5）。

规则在**跑批前**固化（见 `arknights_wiki/eval/freeze.py:PREREGISTERED_TOLERANCES`）：
- 确定性指标（tool_selection_accuracy / task_completion）：逐题必须**完全一致**
- 随机 LLM 指标（answer_correctness / faithfulness / citation_accuracy / hallucination）：
  ① 均值差 ≤ 0.03；② 逐题一致率 ≥ 90%（一致 = 同题同指标差值 ≤ 0.1；hallucination 为 0/1，须相等）
- judge 失败率 ≤ 5%
- 安全与副作用零容忍（未批准 push/PR、sandbox violation、approval bypass）

用法：
  python scripts/eval/check_reproducibility.py --base output/eval/w11a_baseline --rerun output/eval/w11a_baseline_run2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from arknights_wiki.eval.freeze import PREREGISTERED_TOLERANCES  # noqa: E402
from arknights_wiki.eval.metrics import METRICS, _metric_value, aggregate  # noqa: E402

DETERMINISTIC = set(PREREGISTERED_TOLERANCES["deterministic_metrics_list"])
STOCHASTIC = [m for m in METRICS if m not in DETERMINISTIC]
MEAN_TOL = float(PREREGISTERED_TOLERANCES["stochastic_metric_mean_delta_max"])
AGREE_MIN = float(PREREGISTERED_TOLERANCES["stochastic_per_case_agreement_min"])
FAIL_MAX = float(PREREGISTERED_TOLERANCES["judge_failure_rate_max"])
PER_CASE_TOL = 0.1  # judge 输出按 0.1 网格；同题同指标差值 ≤ 一格视为一致
FAIL_ANSWER_MARKERS = ("[run error", "[http 调用失败", "回答生成出了点问题")


def load(run_dir: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in (run_dir / "results_v1.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[f"{r['id']}:{r.get('mode')}"] = r
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="复现性判定")
    ap.add_argument("--base", required=True, help="基线 run 目录")
    ap.add_argument("--rerun", required=True, help="复跑 run 目录")
    ap.add_argument("--out", default="", help="判定报告输出路径（默认写到 base 目录）")
    args = ap.parse_args()

    base_dir, rerun_dir = Path(args.base), Path(args.rerun)
    a, b = load(base_dir), load(rerun_dir)

    problems: list[str] = []
    warnings: list[str] = []

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    if only_a or only_b:
        problems.append(f"两次跑批的题目集合不同：仅基线 {len(only_a)} 条、仅复跑 {len(only_b)} 条")

    def failed(rows: dict[str, dict]) -> list[str]:
        return [
            k for k, r in rows.items()
            if r.get("route") == "error"
            or any(str(r.get("answer", "")).startswith(m) for m in FAIL_ANSWER_MARKERS)
        ]

    fa, fb = failed(a), failed(b)
    print(f"基线: {len(a)} 行（失败 {len(fa)}） · 复跑: {len(b)} 行（失败 {len(fb)}）")
    if fa:
        problems.append(f"基线存在失败行 {len(fa)} 条")
    if fb:
        problems.append(f"复跑存在失败行 {len(fb)} 条（示例 {fb[:3]}）")

    # judge 失败率
    for label, rows in (("基线", a), ("复跑", b)):
        agg = aggregate(list(rows.values()))
        rate = agg.get("coverage", {}).get("judge_failure_count", 0) / max(len(rows), 1)
        print(f"{label} judge 失败率: {rate:.2%}（上限 {FAIL_MAX:.0%}）")
        if rate > FAIL_MAX:
            problems.append(f"{label} judge 失败率 {rate:.2%} 超出预登记上限 {FAIL_MAX:.0%}")

    # 确定性指标：逐题完全一致
    det_mismatch: list[str] = []
    for key in sorted(set(a) & set(b)):
        for m in DETERMINISTIC:
            va, vb = _metric_value(a[key], m), _metric_value(b[key], m)
            if va != vb:
                det_mismatch.append(f"{key}/{m}: {va} vs {vb}")
    print(f"确定性指标逐题不一致: {len(det_mismatch)} 处")
    if det_mismatch:
        problems.append(f"确定性指标必须完全一致，但 {len(det_mismatch)} 处不同（示例 {det_mismatch[:3]}）")

    # 随机指标：均值差 + 逐题一致率
    print("\n随机指标：")
    print("| 指标 | 基线均值 | 复跑均值 | 均值差 | 逐题一致率 | 判定 |")
    print("|---|---|---|---|---|---|")
    for m in STOCHASTIC:
        va = [(v, _metric_value(a[v], m)) for v in a if _metric_value(a[v], m) is not None]
        vb = [(v, _metric_value(b[v], m)) for v in b if _metric_value(b[v], m) is not None]
        ma = sum(x for _, x in va) / len(va) if va else None
        mb = sum(x for _, x in vb) / len(vb) if vb else None
        common = sorted(set(a) & set(b))
        paired = [(m, _metric_value(a[k], m), _metric_value(b[k], m)) for k in common]
        paired = [(mm, x, y) for mm, x, y in paired if x is not None and y is not None]
        if m == "hallucination":
            agree = sum(1 for _, x, y in paired if x == y)
        else:
            agree = sum(1 for _, x, y in paired if abs(float(x) - float(y)) <= PER_CASE_TOL)
        rate = agree / len(paired) if paired else 0.0
        delta = abs(ma - mb) if (ma is not None and mb is not None) else None
        ok = rate >= AGREE_MIN and (delta is not None and delta <= MEAN_TOL)
        print(f"| {m} | {ma} | {mb} | {delta if delta is None else round(delta, 4)} | {rate:.1%} | {'PASS' if ok else 'FAIL'} |")
        if not paired:
            warnings.append(f"{m} 无配对样本")
        elif not ok:
            problems.append(f"{m}: 均值差 {delta} / 一致率 {rate:.1%} 未达预登记要求")

    # 安全与副作用（零容忍）：本评测的 agent 工具集为只读检索，结果行不应出现写操作痕迹
    for label, rows in (("基线", a), ("复跑", b)):
        bad = [k for k, r in rows.items() if any(
            w in json.dumps(r, ensure_ascii=False)
            for w in ("git push", "create_pull_request", "pull_request", "approved_by")
        )]
        if bad:
            problems.append(f"{label} 出现疑似副作用痕迹：{bad[:3]}")

    verdict = "REPRODUCIBLE" if not problems else "NOT_REPRODUCIBLE"
    out = Path(args.out) if args.out else base_dir / "reproducibility.md"
    lines = [
        "# W11-α T7 复现性判定",
        "",
        f"- 基线：`{base_dir.as_posix()}`",
        f"- 复跑：`{rerun_dir.as_posix()}`",
        f"- 预登记容差：确定性指标完全一致 · 随机指标均值差 ≤ {MEAN_TOL} 且逐题一致率 ≥ {AGREE_MIN:.0%}"
        f"（一致 = 差值 ≤ {PER_CASE_TOL}，hallucination 须相等）· judge 失败率 ≤ {FAIL_MAX:.0%} · 安全零容忍",
        "",
        f"## 判定：**{verdict}**",
        "",
    ]
    if problems:
        lines += ["### 未达项", ""] + [f"- {p}" for p in problems] + [""]
    if warnings:
        lines += ["### 提示", ""] + [f"- {w}" for w in warnings] + [""]
    lines += [
        "### 说明",
        "",
        "判定规则在跑批**之前**固化于 `arknights_wiki/eval/freeze.py:PREREGISTERED_TOLERANCES`；",
        "本判定不调整任何容差（母 Spec §24：不得事后决定容差）。",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n判定: {verdict}")
    for p in problems:
        print("  ✗", p)
    print(f"报告: {out}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
