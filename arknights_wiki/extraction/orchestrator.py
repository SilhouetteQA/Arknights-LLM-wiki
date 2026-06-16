"""编排器：章节目录遍历 → 对话加载 → LLM 调用 → 后处理 → 落盘 + 审阅 Markdown"""
import json, os, time
from datetime import datetime, timezone

from .dialogue_loader import load_chapter, split_chapter
from .prompt_builder import build_system_prompt, build_user_prompt
from .llm_client import create_client, call_llm
from .post_processor import (
    align_character_names,
    load_identity_map,
    merge_batches,
    validate_extraction,
)


def discover_chapters(data_dir: str = "data/stories") -> list[tuple[str, str]]:
    """发现所有章节，返回 [(category, chapter_name), ...]"""
    chapters = []
    for category in ["main", "side", "special"]:
        cat_dir = os.path.join(data_dir, category)
        if not os.path.isdir(cat_dir):
            continue
        for ch_name in sorted(os.listdir(cat_dir)):
            ch_dir = os.path.join(cat_dir, ch_name)
            if os.path.isdir(ch_dir) and any(f.endswith(".json") for f in os.listdir(ch_dir)):
                chapters.append((category, ch_name))
    return chapters


def extract_chapter(
    category: str,
    chapter: str,
    data_dir: str = "data/stories",
    identity_map_path: str = "config/identity_map.json",
    operators_path: str = "data/operators.json",
) -> dict:
    """提取单章：加载 → 分批 → LLM → 合并 → 后处理"""
    chapter_dir = os.path.join(data_dir, category, chapter)
    cd = load_chapter(chapter_dir)
    batches = split_chapter(cd)

    id_map = load_identity_map(identity_map_path)
    with open(operators_path, "r", encoding="utf-8") as f:
        operators = json.load(f)["operators"]

    client = create_client()
    system_prompt = build_system_prompt()
    all_batches = []
    total_stats = {"tokens_in": 0, "tokens_out": 0, "elapsed_s": 0}

    for batch in batches:
        user_prompt = build_user_prompt(
            chapter=batch.chapter,
            dialogue_text=batch.text,
            total_lines=len(batch.lines),
        )

        t0 = time.time()
        llm_result = call_llm(client, system_prompt, user_prompt)
        elapsed = time.time() - t0

        if llm_result.get("_parse_error"):
            print(f"  WARNING: {chapter} JSON 解析失败，记录原始输出")
            all_batches.append({
                "chapter": batch.chapter, "category": cd.category,
                "summary": "", "events": [], "characters": [], "concepts": [],
                "_parse_error": True, "_raw": llm_result.get("_raw", ""),
            })
        else:
            stats = llm_result.pop("_stats", {})
            total_stats["tokens_in"] += stats.get("tokens_in", 0)
            total_stats["tokens_out"] += stats.get("tokens_out", 0)
            all_batches.append(llm_result)

        total_stats["elapsed_s"] += elapsed

    merged = merge_batches(all_batches, chapter)
    merged["processed_at"] = datetime.now(timezone.utc).isoformat()
    merged["model"] = "MiniMax-M3"
    merged["stats"] = total_stats

    errors = validate_extraction(merged, len(cd.lines))
    if errors:
        merged["_validation_errors"] = errors

    if merged.get("characters"):
        merged["characters"], unmatched = align_character_names(
            merged["characters"], operators, id_map)
        if unmatched:
            merged["_unmatched_names"] = unmatched

    return merged


def save_extraction(data: dict, output_base: str = "data/extractions/v1_events") -> str:
    """保存提取结果 JSON"""
    category = data["category"]
    chapter = data["chapter"]
    out_dir = os.path.join(output_base, category)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{chapter}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path


def generate_review_markdown(data: dict, lines: list[str]) -> str:
    """生成人工审阅 Markdown"""
    chapter = data["chapter"]
    md = f"# {chapter}\n\n"
    md += f"**类别:** {data.get('category', '')} | "
    md += f"**模型:** {data.get('model', '')} | "
    md += f"**批次:** {data.get('batch_count', 1)}\n\n"

    md += "## 章节摘要\n\n"
    md += data.get("summary", "无") + "\n\n"

    md += "## 事件列表\n\n"
    for i, ev in enumerate(data.get("events", []), 1):
        md += f"### {i}. {ev.get('type', '?')} — {ev.get('event', '?')}\n\n"
        md += f"- **行号范围:** {ev.get('line_range', [])}\n"
        md += f"- **参与角色:** {', '.join(ev.get('participants', []))}\n"
        md += f"- **地点:** {ev.get('location', '未知')}\n"
        md += f"- **意义:** {ev.get('significance', '')}\n\n"

        lr = ev.get("line_range", [0, 0])
        if lr[0] > 0 and lr[0] <= len(lines):
            md += "**原文引用:**\n\n```\n"
            for li in range(lr[0] - 1, min(lr[1], len(lines))):
                if li < len(lines):
                    md += f"[{li + 1}] {lines[li]}\n"
            md += "```\n\n"

    md += "## 角色列表\n\n"
    md += "| 名称 | 类型 | 本章角色 | 首次登场 |\n"
    md += "|------|------|----------|----------|\n"
    for c in data.get("characters", []):
        first = "Y" if c.get("first_appearance_chapter") else ""
        md += f"| {c['name']} | {c.get('type', '')} | {c.get('role_in_chapter', '')} | {first} |\n"

    md += "\n## 概念列表\n\n"
    for c in data.get("concepts", []):
        md += f"### {c.get('concept', '')}\n\n"
        md += f"- **行号范围:** {c.get('line_range', [])}\n"
        md += f"- **讨论摘要:** {c.get('discussion_summary', '')}\n"
        md += f"- **实质讨论:** {c.get('is_substantive', False)}\n\n"

    return md
