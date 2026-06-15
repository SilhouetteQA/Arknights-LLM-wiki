# arknights_wiki/pipeline/parse_dialogue.py
"""解析 PRTS Wiki 剧情页面中的对话数据"""

import html
import os
import re

from bs4 import BeautifulSoup

from arknights_wiki._utils import sanitize_filename, ensure_dir, write_json
from arknights_wiki.config import DATA_DIR

DIRECTIVE_PATTERN = re.compile(r'^\[(?!name=)[^\]]*\]')


def extract_datas_txt(html_text: str) -> str | None:
    """从 HTML 中提取 datas_txt 的原始文本内容"""
    soup = BeautifulSoup(html_text, 'lxml')
    pre_tag = soup.find('pre', id='datas_txt')
    if pre_tag:
        return pre_tag.get_text()
    return None


def parse_datas_txt(raw_text: str) -> list[dict]:
    """解析 datas_txt 自定义格式，返回 [{speaker, type, text}, ...]

    - [name="角色名"] 文本 → type=dialogue, speaker=角色名
    - [name=""] 文本 → type=narration, 无 speaker 字段
    - 其他 [...] 指令行 → 跳过
    """
    if not raw_text or not raw_text.strip():
        return []

    raw_text = html.unescape(raw_text)
    lines = []

    for raw_line in raw_text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        name_match = re.match(r'^\[name="([^"]*)"\]\s*(.*)', line)
        if name_match:
            speaker = name_match.group(1)
            text = name_match.group(2).strip()

            text = text.replace('{@nickname}', '博士')

            if not text:
                continue

            if speaker == '':
                lines.append({"type": "narration", "text": text})
            else:
                lines.append({"speaker": speaker, "type": "dialogue", "text": text})
            continue

        if DIRECTIVE_PATTERN.match(line):
            continue

    return lines


def parse_story_html(
    html_text: str,
    story_id: str,
    title: str,
    chapter: str,
    category: str,
    source_url: str
) -> dict:
    """解析完整剧情页面 HTML，返回结构化 story JSON"""
    raw_text = extract_datas_txt(html_text)
    lines = parse_datas_txt(raw_text) if raw_text else []
    return {
        "id": story_id,
        "title": title,
        "chapter": chapter,
        "category": category,
        "source_url": source_url,
        "lines": lines,
    }


def save_story_json(story: dict) -> str:
    """将 story JSON 保存到 data/stories/{category}/{chapter}/{id}.json"""
    category_dir = sanitize_filename(story["category"])
    chapter = story.get("chapter", "未知")
    chapter_dir = sanitize_filename(chapter)
    filename = sanitize_filename(story["id"]) + ".json"
    dirpath = os.path.join(DATA_DIR, "stories", category_dir, chapter_dir)
    ensure_dir(dirpath)
    filepath = os.path.join(dirpath, filename)
    write_json(filepath, story)
    return filepath
