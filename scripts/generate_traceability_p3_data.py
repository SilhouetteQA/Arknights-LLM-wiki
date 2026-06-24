"""生成 Pass 3 Wiki 页面来源可追溯性评估数据 (30% 样本)
检查: ## 来源 段是否有效引用了 Pass 1 章节
"""
import json
import os
import glob
import re
import random

random.seed(42)
SAMPLE_RATE = 0.3

V3_WIKI = "data/extractions/v3_wiki"


def extract_section(text: str, heading: str) -> str:
    pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


def extract_metadata(text: str) -> tuple:
    name = ""
    category = ""
    for line in text.splitlines():
        if line.startswith("# ") and not name:
            name = line[2:].strip()
        if line.startswith("**分类:**"):
            category = line.replace("**分类:**", "").strip()
    return name, category


# 收集所有 Pass 1 章节名
p1_chapters = set()
for fpath in sorted(glob.glob("data/extractions/v1_events/**/*.json", recursive=True)):
    parts = fpath.replace("\\", "/").split("/")
    chapter_name = os.path.splitext(parts[4])[0]
    p1_chapters.add(chapter_name)
print(f"Pass 1 chapters available: {len(p1_chapters)}")

all_samples = []
has_sources = 0
total_pages = 0

for entity_type, dirname in [("concepts", "concepts"), ("factions", "factions"), ("locations", "locations")]:
    md_dir = os.path.join(V3_WIKI, dirname)
    if not os.path.exists(md_dir):
        continue

    for md_path in sorted(glob.glob(os.path.join(md_dir, "*.md"))):
        total_pages += 1
        text = open(md_path, encoding="utf-8").read()
        name, category = extract_metadata(text)
        sources = extract_section(text, "来源")
        overview = extract_section(text, "概述")
        story_events = extract_section(text, "剧情事件")

        # 解析来源中引用的章节名
        source_chapters = []
        if sources:
            has_sources += 1
            for ch in p1_chapters:
                if ch in sources:
                    source_chapters.append(ch)

        if random.random() < SAMPLE_RATE:
            all_samples.append({
                "entity_type": entity_type,
                "name": str(name),
                "category": str(category),
                "has_sources": bool(sources),
                "sources_text": str(sources)[:2000],
                "overview": str(overview)[:1000],
                "source_chapters_found": source_chapters,
                "source_chapters_count": len(source_chapters),
            })

print(f"\nRule check:")
print(f"  Total pages: {total_pages}")
print(f"  Has ## 来源 section: {has_sources} ({has_sources/total_pages*100:.1f}%)")
print(f"  30% sample: {len(all_samples)} pages")

outdir = "arknights_wiki/eval/registry/data"
os.makedirs(outdir, exist_ok=True)
path = os.path.join(outdir, "traceability_p3_sample.jsonl")
with open(path, "w", encoding="utf-8") as f:
    for s in all_samples:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
print(f"Written to {path}")
