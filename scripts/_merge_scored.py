"""合并打分结果（临时）：备份的可信指标 + 新重跑的 hallucination/faithfulness

用法: python scripts/_merge_scored.py
输入:
  output/eval/results_scored_v1_buggy.jsonl  # 备份（correctness/citation 可信，hallucination/faithfulness 已损坏）
  output/eval/results_scored.jsonl           # 新重跑（hallucination/faithfulness 修复值 + 修正后的 rule metrics）
输出:
  output/eval/results_scored_final.jsonl
"""
import json
from pathlib import Path

OUT = Path("output/eval")


def load(fp: Path) -> dict:
    rows = {}
    if fp.exists():
        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["id"]] = r
    return rows


def main() -> None:
    buggy = load(OUT / "results_scored_v1_buggy.jsonl")
    fresh = load(OUT / "results_scored.jsonl")
    print(f"备份 {len(buggy)} 条, 新重跑 {len(fresh)} 条")

    merged = []
    for qid, r in fresh.items():
        # 从备份继承 correctness/citation（未重跑）
        b = buggy.get(qid, {})
        bj = b.get("judge", {})
        rj = r.get("judge", {})
        for k in ("answer_correctness", "correctness_reason", "citation_accuracy"):
            if rj.get(k) is None and bj.get(k) is not None:
                rj[k] = bj[k]
        merged.append(r)

    # 备份中有但新文件没有的（理论上不存在的题）
    missing = [qid for qid in buggy if qid not in fresh]
    if missing:
        print(f"注意: 新文件缺失 {len(missing)} 条: {missing[:5]}")

    final = OUT / "results_scored_final.jsonl"
    with final.open("w", encoding="utf-8") as f:
        for r in sorted(merged, key=lambda x: x["id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"合并完成 → {final} ({len(merged)} 条)")


if __name__ == "__main__":
    main()
