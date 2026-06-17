"""编排器：章节目录遍历 → 对话加载 → LLM 调用 → 后处理 → 落盘 + 审阅 Markdown"""
import json, os, time
from datetime import datetime, timezone

from .dialogue_loader import (
    load_chapter, split_chapter, build_context_prompt, scene_line_to_global,
)
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


def _get_model_label() -> str:
    """获取当前模型标识"""
    from .llm_client import _get_model_config
    return _get_model_config()["model"]


def _convert_batch_scene_ranges(batch_data: dict, batch_cd) -> dict:
    """将单个批次的 scene-relative line_range 转换为批内全局行号"""
    for ev in batch_data.get("events", []):
        lr = ev.get("line_range", {})
        if isinstance(lr, dict) and "scene" in lr:
            scene_num = lr["scene"]
            lines = lr.get("lines", [1, 1])
            ev["line_range"] = [
                scene_line_to_global(batch_cd, scene_num, lines[0]),
                scene_line_to_global(batch_cd, scene_num, lines[1]),
            ]

    for c in batch_data.get("concepts", []):
        lr = c.get("line_range", {})
        if isinstance(lr, dict) and "scene" in lr:
            scene_num = lr["scene"]
            lines = lr.get("lines", [1, 1])
            c["line_range"] = [
                scene_line_to_global(batch_cd, scene_num, lines[0]),
                scene_line_to_global(batch_cd, scene_num, lines[1]),
            ]

    for f in batch_data.get("factions", []):
        lr = f.get("line_range", {})
        if isinstance(lr, dict) and "scene" in lr:
            scene_num = lr["scene"]
            lines = lr.get("lines", [1, 1])
            f["line_range"] = [
                scene_line_to_global(batch_cd, scene_num, lines[0]),
                scene_line_to_global(batch_cd, scene_num, lines[1]),
            ]

    for loc in batch_data.get("locations", []):
        lr = loc.get("line_range", {})
        if isinstance(lr, dict) and "scene" in lr:
            scene_num = lr["scene"]
            lines = lr.get("lines", [1, 1])
            loc["line_range"] = [
                scene_line_to_global(batch_cd, scene_num, lines[0]),
                scene_line_to_global(batch_cd, scene_num, lines[1]),
            ]

    return batch_data


def _offset_line_ranges(batch_data: dict, offset: int):
    """将批次内的 line_range 统一加偏移量，映射到章全局行号"""
    for section in ["events", "concepts", "factions", "locations"]:
        for item in batch_data.get(section, []):
            lr = item.get("line_range", [])
            if isinstance(lr, list) and len(lr) == 2:
                item["line_range"] = [lr[0] + offset, lr[1] + offset]


def extract_chapter(
    category: str,
    chapter: str,
    data_dir: str = "data/stories",
    identity_map_path: str = "config/identity_map.json",
    operators_path: str = "data/operators.json",
) -> dict:
    """提取单章：加载 → 分批 → LLM（带上下文）→ scene→global 转换 → 合并 → 后处理"""
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
    batch_line_offset = 0  # 累计行数偏移，用于将批次行号映射到全局行号

    for bi, batch in enumerate(batches):
        context = ""
        if bi > 0 and all_batches:
            context = build_context_prompt(all_batches)

        user_prompt = build_user_prompt(
            chapter=batch.chapter,
            dialogue_text=batch.text,
            total_lines=len(batch.lines),
            scene_count=batch.scene_count(),
            context=context,
        )

        ctx_info = f" (带前{len([b for b in all_batches if not b.get('_parse_error')])}批上下文)" if context else ""
        print(f"  批次 {bi+1}/{len(batches)}: {len(batch.lines)} 行, {batch.scene_count()} 场景, ~{batch.token_estimate:,} tokens{ctx_info}")

        t0 = time.time()
        llm_result = call_llm(client, system_prompt, user_prompt)
        elapsed = time.time() - t0

        if llm_result.get("_parse_error"):
            print(f"  WARNING: JSON 解析失败")
            all_batches.append({
                "summary": "", "events": [], "characters": [], "concepts": [],
                "_parse_error": True, "_raw": llm_result.get("_raw", ""),
            })
        else:
            stats = llm_result.pop("_stats", {})
            total_stats["tokens_in"] += stats.get("tokens_in", 0)
            total_stats["tokens_out"] += stats.get("tokens_out", 0)
            # scene-relative → batch-local global → chapter-global（加上前几批的偏移）
            llm_result = _convert_batch_scene_ranges(llm_result, batch)
            if batch_line_offset > 0:
                _offset_line_ranges(llm_result, batch_line_offset)
            all_batches.append(llm_result)
            n_ev = len(llm_result.get("events", []))
            n_cc = len(llm_result.get("concepts", []))
            print(f"  tokens: in={stats.get('tokens_in',0):,} out={stats.get('tokens_out',0):,} events={n_ev} concepts={n_cc} {elapsed:.1f}s")

        total_stats["elapsed_s"] += elapsed
        batch_line_offset += len(batch.lines)

    # 合并所有批次
    merged = merge_batches(all_batches, chapter, source_category=cd.category)
    merged["processed_at"] = datetime.now(timezone.utc).isoformat()
    merged["model"] = _get_model_label()
    merged["stats"] = total_stats

    # 校验（使用原始 cd 的总行数）
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
    category = data.get("category", "unknown")
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
        if isinstance(lr, list) and lr[0] > 0 and lr[0] <= len(lines):
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


def run_trial(
    trial_chapters: list[tuple[str, str]],
    data_dir: str = "data/stories",
) -> dict[str, dict]:
    """试跑：提取指定章节"""
    results = {}
    os.makedirs("output/trial_review", exist_ok=True)

    for category, chapter in trial_chapters:
        print(f"\n{'='*50}")
        print(f"提取: [{category}] {chapter}")
        print(f"{'='*50}")

        data = extract_chapter(category, chapter, data_dir)
        save_extraction(data)

        chapter_dir = os.path.join(data_dir, category, chapter)
        try:
            cd = load_chapter(chapter_dir)
            review_texts = [l["text"] for l in cd.lines]
        except Exception:
            review_texts = []
        md = generate_review_markdown(data, review_texts)
        md_path = f"output/trial_review/{chapter}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)

        s = data.get("stats", {})
        events_n = len(data.get("events", []))
        chars_n = len(data.get("characters", []))
        concepts_n = len(data.get("concepts", []))
        print(f"  事件: {events_n}")
        print(f"  角色: {chars_n}")
        print(f"  概念: {concepts_n}")
        print(f"  tokens: in={s.get('tokens_in',0):,} out={s.get('tokens_out',0):,}")
        if data.get("_validation_errors"):
            print(f"  校验: {data['_validation_errors']}")
        if data.get("_unmatched_names"):
            print(f"  未匹配: {data['_unmatched_names']}")
        print(f"  JSON → data/extractions/v1_events/{data.get('category', category)}/{chapter}.json")

        results[chapter] = data

    return results


def run_all(
    data_dir: str = "data/stories",
    skip_chapters: set = None,
) -> list[dict]:
    """全量章节提取"""
    if skip_chapters is None:
        skip_chapters = set()

    chapters = discover_chapters(data_dir)
    results = []

    for category, chapter in chapters:
        if chapter in skip_chapters:
            continue
        print(f"[{category}] {chapter} ...", end=" ", flush=True)
        try:
            data = extract_chapter(category, chapter, data_dir)
            save_extraction(data)
            n_events = len(data.get("events", []))
            n_chars = len(data.get("characters", []))
            toks = data.get("stats", {}).get("tokens_in", 0)
            elapsed = data.get("stats", {}).get("elapsed_s", 0)
            print(f"events={n_events} chars={n_chars} toks_in={toks} {elapsed:.1f}s")
            results.append(data)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"chapter": chapter, "category": category, "_error": str(e)})

    return results
