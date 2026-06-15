# arknights_wiki/pipeline/gen_markdown.py
"""从 story JSON 生成 Markdown 副本"""

import os

from arknights_wiki._utils import sanitize_filename, ensure_dir, read_json
from arknights_wiki.config import DATA_DIR, OUTPUT_DIR, CATEGORY_LABELS


def story_to_markdown(story: dict) -> str:
    """将单个 story JSON 转为 Markdown 字符串"""
    story_id = story["id"]
    title = story["title"]
    chapter = story["chapter"]
    category = story["category"]
    source_url = story["source_url"]
    category_label = CATEGORY_LABELS.get(category, category)

    lines = []
    lines.append(f"# {story_id} {title}")
    lines.append("")
    lines.append(f"> 章节：{chapter} | 类型：{category_label}")
    lines.append(f"> 源：[PRTS Wiki]({source_url})")
    lines.append("")
    lines.append("---")
    lines.append("")

    for item in story["lines"]:
        tp = item["type"]
        text = item["text"]

        if tp == "dialogue":
            speaker = item.get("speaker", "")
            lines.append(f"**{speaker}**：{text}")
        elif tp == "narration":
            lines.append(f"*{text}*")
        lines.append("")

    return "\n".join(lines)


def generate_all_markdown() -> None:
    """遍历所有已抓取的 story JSON，生成 Markdown 文件"""
    stories_dir = os.path.join(DATA_DIR, "stories")

    if not os.path.isdir(stories_dir):
        return

    for category in os.listdir(stories_dir):
        cat_dir = os.path.join(stories_dir, category)
        if not os.path.isdir(cat_dir):
            continue

        for chapter_name in os.listdir(cat_dir):
            chapter_dir = os.path.join(cat_dir, chapter_name)
            if not os.path.isdir(chapter_dir):
                continue

            for filename in os.listdir(chapter_dir):
                if not filename.endswith('.json'):
                    continue

                story_path = os.path.join(chapter_dir, filename)
                story = read_json(story_path)

                md_text = story_to_markdown(story)

                md_filename = filename.replace('.json', '.md')
                md_dir = os.path.join(OUTPUT_DIR, "markdown", category, chapter_name)
                ensure_dir(md_dir)
                md_path = os.path.join(md_dir, md_filename)

                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(md_text)
