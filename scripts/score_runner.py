#!/usr/bin/env python
"""W0 M4: 容器内 DeepEval 打分（并发版）

用法（容器内）：
  python scripts/score_runner.py --results output/eval/results_v1.jsonl --questions benchmarks/arknights_bench/questions_draft.jsonl --out output/eval
  python scripts/score_runner.py ... --metrics correctness,faithfulness --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from arknights_wiki.eval.scoring import DeepEvalScorer, rule_metrics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--materials", default=str(ROOT / "benchmarks" / "arknights_bench" / "materials"))
    parser.add_argument("--out", default=str(ROOT / "output" / "eval"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--metrics", default="all", help="all 或逗号分隔: correctness,faithfulness,hallucination,citation")
    args = parser.parse_args()

    results = [json.loads(l) for l in Path(args.results).read_text(encoding="utf-8").splitlines() if l.strip()]
    questions = {r["id"]: r for r in (json.loads(l) for l in Path(args.questions).read_text(encoding="utf-8").splitlines() if l.strip())}
    materials: dict[str, str] = {}
    for p in Path(args.materials).glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for it in data.get("items", []):
                materials[it["name"]] = it.get("excerpt", "")
        except Exception:
            continue

    # 断点续跑：跳过已打分的
    out_path = Path(args.out) / "results_scored.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done_ids: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done_ids.add(json.loads(line)["id"])
                except Exception:
                    pass

    if args.limit:
        results = results[: args.limit]
    pending = [r for r in results if r["id"] not in done_ids]
    if not pending:
        print("全部已打分，无待处理。")
        return 0

    metric_set = set(args.metrics.split(",")) if args.metrics != "all" else {"correctness", "faithfulness", "hallucination", "citation"}
    lock = threading.Lock()

    def budget_context(raw_rc: list) -> list[str]:
        """上下文预算：单段 ≤800 字、总 ≤4000 字。
        2026-08-17：不截断时 faithfulness 的 judge prompt 过大，火山 180s 内生成不完
        → 读超时 ×5 重试（每题卡 15min）。截断到可控规模后 judge 可在超时内完成。"""
        segments = []
        total = 0
        for t in raw_rc:
            if not isinstance(t, str) or len(t) <= 50:
                continue
            seg = t[:800]
            segments.append(seg)
            total += len(seg)
            if total >= 4000:
                break
        return segments

    def score_one(row: dict) -> dict:
        q = questions.get(row["id"], {})
        ak = q.get("answer_key", {})
        mrefs = q.get("material_refs", [])
        material_texts = [materials.get(m, "") for m in mrefs if materials.get(m)]
        # faithfulness/hallucination 的正确依据 = Agent 实际检索上下文（runner 记录）
        # 过滤无意义短条目（如 simple 路径的纯名字元数据）；无有效内容时回退出题材料
        raw_rc = row.get("retrieval_context") or []
        retrieval_context = budget_context(raw_rc) or material_texts
        scorer = DeepEvalScorer()
        scores = scorer.score_answer(
            row["question"], row["answer"], ak, material_texts,
            retrieval_context=retrieval_context, metric_set=metric_set,
        )
        rules = rule_metrics(
            row["answer"],
            row.get("tools_called", []),
            q.get("requires_tools", []),
            q.get("expected_behavior", ""),
        )
        row["judge"] = scores
        row["metrics"] = rules
        return row

    written = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fmap = {ex.submit(score_one, r): r["id"] for r in pending}
        for fut in as_completed(fmap):
            qid = fmap[fut]
            try:
                row = fut.result()
                with lock:
                    with out_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
                s = row["judge"]
                print(f"  ✓ {qid}: correct={s.get('answer_correctness')} faith={s.get('faithfulness')} halluc={s.get('hallucination')} cit={s.get('citation_accuracy')}")
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {qid}: {str(e)[:150]}", file=sys.stderr)
    print(f"完成：新打分 {written} 条 → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
