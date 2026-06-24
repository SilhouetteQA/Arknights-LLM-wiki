"""从 v3_wiki Markdown 页面生成 OpenAI Evals JSONL 评估数据"""
import json
import re
from pathlib import Path

V3_WIKI = Path("data/extractions/v3_wiki")
EVAL_DATA = Path("arknights_wiki/eval/registry/data")
MAX_CHARS_PER_SAMPLE = 3000  # 概述+事件截断上限，避免 token 爆炸


def extract_section(text: str, heading: str) -> str:
    """提取 Markdown ## heading 到下一个 ## 之间的内容"""
    pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


def extract_metadata(text: str) -> tuple[str, str]:
    """提取页面名称（# 行）和分类（**分类:** 行）"""
    name = ""
    category = ""
    for line in text.splitlines():
        if line.startswith("# ") and not name:
            name = line[2:].strip()
        if line.startswith("**分类:**"):
            category = line.replace("**分类:**", "").strip()
    return name, category


def process_pages(md_dir: Path) -> list[dict]:
    """处理一个目录下所有 MD 文件，生成评估样本"""
    samples = []
    for md_path in sorted(md_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        name, category = extract_metadata(text)
        overview = extract_section(text, "概述")
        story_events = extract_section(text, "剧情事件")

        # 跳过空页面
        if not overview and not story_events:
            continue

        # 截断长文本
        if len(overview) > MAX_CHARS_PER_SAMPLE:
            overview = overview[:MAX_CHARS_PER_SAMPLE] + "..."
        if len(story_events) > MAX_CHARS_PER_SAMPLE:
            story_events = story_events[:MAX_CHARS_PER_SAMPLE] + "..."

        samples.append({
            "name": name,
            "category": category,
            "overview": overview,
            "story_events": story_events,
        })

    return samples


def write_jsonl(samples: list[dict], filename: str):
    """写入 JSONL 文件"""
    path = EVAL_DATA / filename
    EVAL_DATA.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    return path


def main():
    for entity_type, dirname, outfile in [
        ("概念", "concepts", "wiki_quality_concepts.jsonl"),
        ("阵营", "factions", "wiki_quality_factions.jsonl"),
        ("地点", "locations", "wiki_quality_locations.jsonl"),
    ]:
        md_dir = V3_WIKI / dirname
        if not md_dir.exists():
            print(f"  [跳过] {md_dir} 不存在")
            continue

        samples = process_pages(md_dir)
        path = write_jsonl(samples, outfile)

        # 统计
        has_overview = sum(1 for s in samples if s["overview"])
        has_events = sum(1 for s in samples if s["story_events"])
        empty = sum(1 for s in samples if not s["overview"] and not s["story_events"])
        print(f"  {entity_type}: {len(samples)} 样本 → {path}")
        print(f"    有概述: {has_overview}, 有事件: {has_events}, 跳过空页: {empty}")


if __name__ == "__main__":
    main()
