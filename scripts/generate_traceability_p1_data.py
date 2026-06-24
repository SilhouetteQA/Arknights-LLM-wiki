"""生成 Pass 1 实体可追溯性评估数据 (30% 样本)"""
import json
import os
import glob
import random
from arknights_wiki.extraction.dialogue_loader import load_chapter

random.seed(42)
SAMPLE_RATE = 0.3

samples = []
total_entities = 0
total_with_text = 0
errors = 0

for fpath in sorted(glob.glob("data/extractions/v1_events/**/*.json", recursive=True)):
    parts = fpath.replace("\\", "/").split("/")
    category = parts[3]  # main/side/special
    chapter_id = os.path.splitext(parts[4])[0]

    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)

    chapter_dir = os.path.join("data/stories", category, chapter_id)
    try:
        chapter_text = load_chapter(chapter_dir)
    except Exception:
        errors += 1
        continue

    full_text = chapter_text.text_no_markers

    for etype, key in [
        ("events", "events"),
        ("concepts", "concepts"),
        ("factions", "factions"),
        ("locations", "locations"),
    ]:
        items = data.get(key, [])
        for item in items:
            total_entities += 1
            lr = item.get("line_range", [])
            if not lr or len(lr) < 2 or lr[0] >= lr[1]:
                continue

            name_key = {
                "events": "event",
                "concepts": "concept",
                "factions": "faction",
                "locations": "location",
            }[etype]
            desc_key = {
                "events": "significance",
                "concepts": "discussion_summary",
                "factions": "description",
                "locations": "description",
            }[etype]

            source_lines = full_text.split("\n")
            start = min(lr[0], len(source_lines) - 1)
            end = min(lr[1], len(source_lines))
            snippet = "\n".join(source_lines[start:end])

            total_with_text += 1
            if random.random() < SAMPLE_RATE:
                samples.append({
                    "entity_type": etype,
                    "entity_name": str(item.get(name_key, "?")),
                    "entity_description": str(item.get(desc_key, "")),
                    "line_range": lr,
                    "source_text": snippet[:2500],
                    "chapter": chapter_id,
                    "category": category,
                })

print(f"Pass 1 scan done:")
print(f"  Total entities: {total_entities}")
print(f"  With valid lr + text: {total_with_text}")
print(f"  Chapter load errors: {errors}")
print(f"  30% sample size: {len(samples)}")

by_type = {}
for s in samples:
    by_type.setdefault(s["entity_type"], []).append(s)
for etype, items in sorted(by_type.items()):
    print(f"    {etype}: {len(items)}")

outdir = "arknights_wiki/eval/registry/data"
os.makedirs(outdir, exist_ok=True)
path = os.path.join(outdir, "traceability_p1_sample.jsonl")
with open(path, "w", encoding="utf-8") as f:
    for s in samples:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
print(f"Written to {path}")
