"""W11-α T5：冻结评测语料并生成 MANIFEST（母 Spec §24 BenchmarkSpec 的 corpus 部分）。

设计要点（不可变性纪律）：
- **必须提供 `--reviewed-sha256`**：它必须是人工审阅过的那份新增题目文件的字节哈希。
  冻结前会重新计算并比对 —— 不匹配即中止。这样"冻结下来的语料"与"人看过的语料"必然是同一份字节。
- 已存在的冻结目录**拒绝覆盖**（只能用 `--force` 显式重建，且必须同时给出理由 `--supersede-reason`）。
- 冻结件只写一次，之后只读；任何修正都形成新版本目录（v2）并登记 SUPERSEDED 原因。

用法：
  python scripts/eval/freeze_corpus.py --reviewed-sha256 <sha256> [--version w11a-v1]
  python scripts/eval/freeze_corpus.py --reviewed-sha256 <sha256> --force --supersede-reason "..."
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from arknights_wiki.eval import freeze  # noqa: E402

BASE_BENCH = ROOT / "benchmarks" / "arknights_bench" / "questions_draft.jsonl"
NEW_ITEMS = ROOT / "benchmarks" / "arknights_bench" / "drafts" / "w11a_new_categories.jsonl"
REVIEW_NOTES = ROOT / "benchmarks" / "arknights_bench" / "drafts" / "w11a_review_notes.md"
MATERIALS = ROOT / "benchmarks" / "arknights_bench" / "materials"
FROZEN_ROOT = ROOT / "benchmarks" / "arknights_bench" / "frozen"

#: U-14 要求的八类（冻结时必须全部有题）
REQUIRED_CATEGORIES = (
    "character", "event", "region", "organization",
    "combat_power", "worldview", "no_answer", "hallucination_bait",
)
MIN_PER_REQUIRED_CATEGORY = 10


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="W11-α 冻结评测语料")
    ap.add_argument("--reviewed-sha256", required=True, help="人工审阅过的 drafts 文件字节哈希")
    ap.add_argument("--version", default="w11a-v1")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--supersede-reason", default="")
    args = ap.parse_args()

    if not BASE_BENCH.exists():
        print(f"错误：基础语料不存在 {BASE_BENCH}", file=sys.stderr)
        return 1
    if not NEW_ITEMS.exists():
        print(f"错误：新增题目不存在 {NEW_ITEMS}", file=sys.stderr)
        return 1

    actual = _sha256(NEW_ITEMS)
    print(f"审阅哈希校验：期望 {args.reviewed_sha256}")
    print(f"              实际 {actual}")
    if actual != args.reviewed_sha256:
        print("中止：被审阅字节与待冻结字节不一致（不得冻结未经审阅的内容）", file=sys.stderr)
        return 2

    base = _load(BASE_BENCH)
    new = _load(NEW_ITEMS)
    merged = base + new

    ids = [x["id"] for x in merged]
    dupes = [i for i, c in Counter(ids).items() if c > 1]
    if dupes:
        print(f"中止：id 重复 {dupes}", file=sys.stderr)
        return 3

    cats = Counter(x.get("category", "") for x in merged)
    missing = [c for c in REQUIRED_CATEGORIES if cats.get(c, 0) == 0]
    thin = [c for c in REQUIRED_CATEGORIES if 0 < cats.get(c, 0) < MIN_PER_REQUIRED_CATEGORY]
    extra = [c for c in cats if c not in REQUIRED_CATEGORIES]
    print(f"\n合并后：{len(merged)} 题（base {len(base)} + new {len(new)}）")
    for c in REQUIRED_CATEGORIES:
        print(f"  {c:20s} {cats.get(c, 0)}")
    if extra:
        print(f"  非 U-14 类别：{extra}")
    if missing:
        print(f"中止：U-14 类别缺题 {missing}", file=sys.stderr)
        return 4
    if thin:
        print(f"警告：以下类别少于 {MIN_PER_REQUIRED_CATEGORY} 题 {thin}", file=sys.stderr)

    out_dir = FROZEN_ROOT / args.version
    if out_dir.exists() and not args.force:
        print(f"中止：{out_dir} 已存在（冻结件不可覆盖；如需重建请用 --force 并给出 --supersede-reason）", file=sys.stderr)
        return 5
    if args.force and not args.supersede_reason:
        print("中止：--force 必须同时提供 --supersede-reason", file=sys.stderr)
        return 6

    out_dir.mkdir(parents=True, exist_ok=True)
    bench_path = out_dir / "questions.jsonl"
    bench_path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in merged) + "\n",
        encoding="utf-8",
    )

    spec = freeze.build_benchmark_spec(bench_path, MATERIALS, ROOT)
    spec["freeze"] = {
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "version": args.version,
        "supersede_reason": args.supersede_reason or None,
        "sources": {
            "base": {"path": str(BASE_BENCH.relative_to(ROOT)), "sha256": _sha256(BASE_BENCH), "count": len(base)},
            "new_items": {"path": str(NEW_ITEMS.relative_to(ROOT)), "sha256": actual, "count": len(new)},
            "review_notes": {
                "path": str(REVIEW_NOTES.relative_to(ROOT)),
                "sha256": _sha256(REVIEW_NOTES) if REVIEW_NOTES.exists() else "",
            },
        },
        "review": {
            "reviewed_bytes_sha256": actual,
            "note": "冻结内容与人工审阅内容为同一份字节（哈希比对通过）",
        },
        "value_domains": {
            "category_counts": dict(sorted(cats.items())),
            "expected_behavior_counts": dict(Counter(x.get("expected_behavior", "") for x in merged)),
            "route_counts": dict(Counter(x.get("route", "") for x in merged)),
            "source_counts": dict(Counter(x.get("source", "") for x in merged)),
            "meta_eval_verdict_counts": dict(
                Counter((x.get("meta_eval") or {}).get("verdict", "") for x in merged)
            ),
            "declared_new_values": {
                "expected_behavior": ["reject"],
                "meta_eval.verdict": ["skipped"],
                "note": "base 100 题只使用 simple/complex 与 pass/reject/review；本批引入 reject（行为）"
                        "与 skipped（未跑元评估，拒绝伪造 pass）—— 必须在冻结清单中显式声明。",
            },
        },
        "excluded": {
            "manual_draft.jsonl": "未并入：实测缺 route/chapter_check/material_refs/meta_eval 四字段、"
                                  "expected_behavior 混用(complex 11 / reject 15)、answer_key.evidence 为空"
                                  "（无验证证据）。如需启用需先补齐 schema 与证据并重跑缺失校验。",
        },
    }
    manifest_path = freeze.write_benchmark_spec(out_dir / "MANIFEST.json", spec)

    ok, problems = freeze.verify_manifest(manifest_path, root=ROOT)
    print(f"\n冻结语料: {bench_path}（{len(merged)} 题）")
    print(f"MANIFEST : {manifest_path}")
    print(f"corpus_sha256: {spec['corpus']['corpus_sha256']}")
    print(f"自校验: {'PASS' if ok else 'FAIL'}")
    for p in problems:
        print(f"  - {p}")
    return 0 if ok else 7


if __name__ == "__main__":
    raise SystemExit(main())
