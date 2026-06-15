# arknights_wiki/pipeline/gen_operators_md.py
"""从 operators.json 生成按阵营分类的可读 Markdown 文件"""

import os

from arknights_wiki._utils import ensure_dir, read_json, sanitize_filename
from arknights_wiki.config import DATA_DIR, OUTPUT_DIR

# 档案节输出顺序
_ARCHIVE_ORDER = [
    "基础档案", "客观履历", "临床诊断分析",
    "档案资料一", "档案资料二", "档案资料三", "档案资料四",
    "晋升记录",
]


def operator_to_markdown(op: dict) -> str:
    """将单个干员数据转为 Markdown 字符串"""
    name_zh = op.get("name_zh", "未知")
    race = op.get("race", "")
    nation = op.get("nation", "")
    birth_place = op.get("birth_place", "")
    sex = op.get("sex", "")
    team = op.get("team", "")
    group = op.get("group", "")

    lines = [f"# {name_zh}", ""]

    meta_parts = [f"种族：{race}"]
    if nation:
        meta_parts.append(f"阵营：{nation}")
    if birth_place:
        meta_parts.append(f"出身地：{birth_place}")
    if sex:
        meta_parts.append(f"性别：{sex}")
    lines.append(f"> {' | '.join(meta_parts)}")

    extra_parts = []
    if team:
        extra_parts.append(f"小队：{team}")
    if group:
        extra_parts.append(f"组织：{group}")
    if extra_parts:
        lines.append(f"> {' | '.join(extra_parts)}")

    lines.append("")
    lines.append("---")

    archives = op.get("archives", {})
    if not archives:
        lines.append("")
        lines.append("*（无档案数据）*")
        return "\n".join(lines)

    for title in _ARCHIVE_ORDER:
        if title in archives:
            content = archives[title].strip()
            if content:
                lines.append("")
                lines.append(f"## {title}")
                lines.append("")
                lines.append(content)

    for title, content in archives.items():
        if title not in _ARCHIVE_ORDER:
            content = content.strip()
            if content:
                lines.append("")
                lines.append(f"## {title}")
                lines.append("")
                lines.append(content)

    return "\n".join(lines)


def generate_all_operators_markdown(operators_path: str = None) -> int:
    """遍历 operators.json，生成每个干员的 Markdown 文件"""
    if operators_path is None:
        operators_path = os.path.join(DATA_DIR, "operators.json")

    if not os.path.exists(operators_path):
        return 0

    data = read_json(operators_path)
    operators = data.get("operators", [])
    count = 0

    for op in operators:
        name_zh = op.get("name_zh", "")
        if not name_zh:
            continue

        logo = op.get("logo", "") or "未知"
        safe_logo = sanitize_filename(logo)
        safe_name = sanitize_filename(name_zh)

        md_text = operator_to_markdown(op)

        md_dir = os.path.join(OUTPUT_DIR, "markdown", "operators", safe_logo)
        ensure_dir(md_dir)
        md_path = os.path.join(md_dir, f"{safe_name}.md")

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_text)
        count += 1

    return count
