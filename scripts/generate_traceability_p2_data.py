"""生成 Pass 2 角色可追溯性评估数据 (30% 样本)
检查: source_pass1_chapters 有效性 + participated_events 与 Pass 1 的关联
"""
import json
import os
import glob
import random

random.seed(42)
SAMPLE_RATE = 0.3

# 先收集所有 Pass 1 事件（按章节分组），用于验证 source_pass1_chapters
p1_chapters = set()
for fpath in sorted(glob.glob("data/extractions/v1_events/**/*.json", recursive=True)):
    parts = fpath.replace("\\", "/").split("/")
    chapter_name = os.path.splitext(parts[4])[0]
    p1_chapters.add(chapter_name)

print(f"Pass 1 chapters available: {len(p1_chapters)}")

# 统计所有 Pass 2 角色
char_files = sorted(glob.glob("data/extractions/v2_characters/*.json"))
print(f"Pass 2 character files: {len(char_files)}")

total_chapters = 0
valid_chapters = 0
missing_chapters = 0
total_events = 0
samples = []

for fpath in char_files:
    with open(fpath, encoding="utf-8") as f:
        char = json.load(f)

    source_chapters = char.get("source_pass1_chapters", [])
    participated = char.get("participated_events", [])
    summary = char.get("summary", "")
    name = char.get("name_zh", "?")

    total_chapters += len(source_chapters)
    total_events += len(participated)

    for ch in source_chapters:
        if ch in p1_chapters:
            valid_chapters += 1
        else:
            missing_chapters += 1

    # 30% 抽样
    if random.random() < SAMPLE_RATE:
        # 提取 participated_events 摘要
        events_text = ""
        for pe in participated:
            events_text += f"- [{pe.get('chapter', '?')}] {pe.get('event', '?')} (角色: {pe.get('role', '?')})\n"

        samples.append({
            "character_name": str(name),
            "summary": str(summary)[:1500],
            "participated_events_count": len(participated),
            "source_chapters": source_chapters,
            "participated_events_text": events_text[:3000],
            "source_chapters_valid": ",".join([ch for ch in source_chapters if ch in p1_chapters]),
            "source_chapters_missing": ",".join([ch for ch in source_chapters if ch not in p1_chapters]),
        })

print(f"\nRule check results:")
print(f"  source_pass1_chapters: total={total_chapters}, valid={valid_chapters}, missing={missing_chapters}")
print(f"  participated_events total: {total_events}")
print(f"  characters with 0 events: {sum(1 for f in char_files if len(json.load(open(f, encoding='utf-8')).get('participated_events', [])) == 0)}")

# Count characters with 0 source chapters
zero_ch = 0
for fpath in char_files:
    with open(fpath, encoding="utf-8") as f:
        char = json.load(f)
    if not char.get("source_pass1_chapters"):
        zero_ch += 1
print(f"  characters with 0 source chapters: {zero_ch}")

print(f"  30% sample: {len(samples)} characters")

# Write JSONL
outdir = "arknights_wiki/eval/registry/data"
os.makedirs(outdir, exist_ok=True)
path = os.path.join(outdir, "traceability_p2_sample.jsonl")
with open(path, "w", encoding="utf-8") as f:
    for s in samples:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
print(f"Written to {path}")
