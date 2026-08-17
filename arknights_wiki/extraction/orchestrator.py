"""编排器：章节目录遍历 → 对话加载 → LLM 调用 → 后处理 → 落盘 + 审阅 Markdown"""
import json, os, time
from datetime import datetime, timezone

from .dialogue_loader import (
    load_chapter, split_chapter, build_context_prompt, scene_line_to_global,
)
from .prompt_builder import (
    build_system_prompt, build_user_prompt,
    build_character_system_prompt, build_character_user_prompt,
)
from .llm_client import create_client, call_llm
from .post_processor import (
    align_character_names,
    load_identity_map,
    merge_batches,
    validate_extraction,
    validate_character_output,
)
from .character_aggregator import (
    collect_from_v1, normalize_and_merge, filter_targets,
    inject_context, parse_keep_list, get_operator_archive,
)


def _load_taxonomy(taxonomy_path: str = "config/story_taxonomy.json") -> dict:
    """加载剧情分类配置"""
    if not os.path.exists(taxonomy_path):
        return {"chapters": {}}
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_chapter_type(chapter: str, taxonomy: dict = None) -> str:
    """获取章节的 taxonomy 类型，默认 full"""
    if taxonomy is None:
        return "full"
    return taxonomy.get("chapters", {}).get(chapter, "full")


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
    chapter_type: str = "full",
) -> dict:
    """提取单章：加载 → 分批 → LLM（带上下文）→ scene→global 转换 → 合并 → 后处理"""
    chapter_dir = os.path.join(data_dir, category, chapter)
    cd = load_chapter(chapter_dir)
    batches = split_chapter(cd)

    id_map = load_identity_map(identity_map_path)
    with open(operators_path, "r", encoding="utf-8") as f:
        operators = json.load(f)["operators"]

    client = create_client()
    system_prompt = build_system_prompt(chapter_type)
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
            chapter_type=chapter_type,
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
    merged["taxonomy_type"] = chapter_type

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
    taxonomy_path: str = "config/story_taxonomy.json",
) -> dict[str, dict]:
    """试跑：提取指定章节"""
    taxonomy = _load_taxonomy(taxonomy_path)
    results = {}
    os.makedirs("output/trial_review", exist_ok=True)

    for category, chapter in trial_chapters:
        chapter_type = _get_chapter_type(chapter, taxonomy)
        print(f"\n{'='*50}")
        print(f"提取: [{category}] {chapter} (type={chapter_type})")
        print(f"{'='*50}")

        data = extract_chapter(category, chapter, data_dir, chapter_type=chapter_type)
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


def _chapter_already_extracted(category: str, chapter: str, output_base: str = "data/extractions/v1_events") -> bool:
    """检查章节是否已有提取结果"""
    out_path = os.path.join(output_base, category, f"{chapter}.json")
    if not os.path.exists(out_path):
        return False
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data.get("events", [])) > 0 or len(data.get("concepts", [])) > 0
    except Exception:
        return False


def _estimate_cost(tokens_in: int, tokens_out: int) -> float:
    """估算 DeepSeek API 成本 (USD)，deepseek-4-flash 定价（deepseek-chat 已下线）"""
    cost_in = tokens_in / 1_000_000 * 0.27
    cost_out = tokens_out / 1_000_000 * 1.10
    return cost_in + cost_out


def run_all(
    data_dir: str = "data/stories",
    skip_chapters: set = None,
    taxonomy_path: str = "config/story_taxonomy.json",
    resume: bool = True,
) -> list[dict]:
    """全量章节提取，taxonomy 驱动策略"""
    if skip_chapters is None:
        skip_chapters = set()
    taxonomy = _load_taxonomy(taxonomy_path)
    taxonomy_chapters = taxonomy.get("chapters", {})

    # 自动跳过 taxonomy 中标记为 skip 的章节
    for ch_name, ch_type in taxonomy_chapters.items():
        if ch_type == "skip":
            skip_chapters.add(ch_name)

    chapters = discover_chapters(data_dir)
    results = []

    # 统计
    skipped_resume = 0
    total_tokens_in = 0
    total_tokens_out = 0
    total_elapsed = 0.0
    t_start_all = time.time()

    for i, (category, chapter) in enumerate(chapters):
        idx = f"{i+1}/{len(chapters)}"
        if chapter in skip_chapters:
            print(f"[{idx}] [{category}] {chapter} SKIP (taxonomy)")
            continue
        if resume and _chapter_already_extracted(category, chapter):
            skipped_resume += 1
            print(f"[{idx}] [{category}] {chapter} SKIP (resume: 已提取)")
            continue
        chapter_type = _get_chapter_type(chapter, taxonomy)
        print(f"[{idx}] [{category}] {chapter} (type={chapter_type}) ...", end=" ", flush=True)
        try:
            data = extract_chapter(category, chapter, data_dir, chapter_type=chapter_type)
            save_extraction(data)
            n_events = len(data.get("events", []))
            n_concepts = len(data.get("concepts", []))
            n_chars = len(data.get("characters", []))
            s = data.get("stats", {})
            tok_in = s.get("tokens_in", 0)
            tok_out = s.get("tokens_out", 0)
            elapsed = s.get("elapsed_s", 0)
            total_tokens_in += tok_in
            total_tokens_out += tok_out
            total_elapsed += elapsed
            print(f"events={n_events} concepts={n_concepts} chars={n_chars} tok={tok_in:,}/{tok_out:,} {elapsed:.1f}s")
            results.append(data)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"chapter": chapter, "category": category, "_error": str(e)})

    elapsed_all = time.time() - t_start_all
    cost = _estimate_cost(total_tokens_in, total_tokens_out)

    print(f"\n{'='*50}")
    print(f"全量提取完成")
    print(f"  成功: {len(results)} 章")
    print(f"  跳过(taxonomy): {len([c for c in chapters if c[1] in skip_chapters])} 章")
    print(f"  跳过(resume): {skipped_resume} 章")
    print(f"  失败: {len([r for r in results if '_error' in r])} 章")
    print(f"  tokens: in={total_tokens_in:,} out={total_tokens_out:,}")
    print(f"  估算成本: ${cost:.3f} USD")
    print(f"  总耗时: {elapsed_all:.0f}s ({elapsed_all/60:.1f}m)")

    return results


def generate_run_report(output_base: str = "data/extractions/v1_events", taxonomy_path: str = "config/story_taxonomy.json") -> str:
    """生成全量提取统计报告 Markdown"""
    taxonomy = _load_taxonomy(taxonomy_path)
    tax_chapters = taxonomy.get("chapters", {})

    rows = []
    totals = {"events": 0, "concepts": 0, "factions": 0, "locations": 0, "tokens_in": 0, "tokens_out": 0, "elapsed": 0.0, "count": 0}
    by_taxonomy = {}

    for cat in ["main", "side", "special"]:
        cat_dir = os.path.join(output_base, cat)
        if not os.path.isdir(cat_dir):
            continue
        for fname in sorted(os.listdir(cat_dir)):
            if not fname.endswith(".json"):
                continue
            chapter = fname[:-5]
            fpath = os.path.join(cat_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            typ = data.get("taxonomy_type", tax_chapters.get(chapter, "?"))
            s = data.get("stats", {})
            ev = len(data.get("events", []))
            cc = len(data.get("concepts", []))
            fa = len(data.get("factions", []))
            lo = len(data.get("locations", []))
            ti = s.get("tokens_in", 0)
            to = s.get("tokens_out", 0)
            el = s.get("elapsed_s", 0)
            errs = len(data.get("_validation_errors", []))
            ec = s.get("errors", 0) if isinstance(s, dict) else 0

            rows.append({
                "chapter": chapter, "category": cat, "type": typ,
                "events": ev, "concepts": cc, "factions": fa, "locations": lo,
                "tokens_in": ti, "tokens_out": to, "elapsed": el,
                "errors": errs + ec,
            })

            totals["events"] += ev
            totals["concepts"] += cc
            totals["factions"] += fa
            totals["locations"] += lo
            totals["tokens_in"] += ti
            totals["tokens_out"] += to
            totals["elapsed"] += el
            totals["count"] += 1

            if typ not in by_taxonomy:
                by_taxonomy[typ] = {"count": 0, "events": 0, "concepts": 0, "tokens_in": 0, "tokens_out": 0, "elapsed": 0.0}
            bt = by_taxonomy[typ]
            bt["count"] += 1
            bt["events"] += ev
            bt["concepts"] += cc
            bt["tokens_in"] += ti
            bt["tokens_out"] += to
            bt["elapsed"] += el

    cost = _estimate_cost(totals["tokens_in"], totals["tokens_out"])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = f"""# Pass 1 全量提取报告

**生成时间:** {now}
**模型:** {_get_model_label()}

---

## 总览

| 指标 | 值 |
|------|-----|
| 已提取章节 | {totals['count']} |
| 总事件数 | {totals['events']} |
| 总概念数 | {totals['concepts']} |
| 总阵营数 | {totals['factions']} |
| 总地点数 | {totals['locations']} |
| 总输入 tokens | {totals['tokens_in']:,} |
| 总输出 tokens | {totals['tokens_out']:,} |
| 估算成本 | ${cost:.3f} USD |
| 总耗时 | {totals['elapsed']:.0f}s ({totals['elapsed']/60:.1f}m) |

## 按 Taxonomy 类型统计

| 类型 | 章节数 | 事件数 | 概念数 | 输入 tokens | 耗时 |
|------|--------|--------|--------|-------------|------|
"""
    for typ in ["full", "is", "ra", "light"]:
        bt = by_taxonomy.get(typ)
        if bt:
            md += f"| {typ} | {bt['count']} | {bt['events']} | {bt['concepts']} | {bt['tokens_in']:,} | {bt['elapsed']:.0f}s |\n"

    md += f"""
## 各章明细

| # | 章节 | 类别 | 类型 | 事件 | 概念 | 阵营 | 地点 | tok_in | tok_out | 耗时 | 校验 |
|---|------|------|------|------|------|------|------|--------|---------|------|------|
"""
    for i, r in enumerate(rows, 1):
        err_flag = f"ERR={r['errors']}" if r["errors"] else ""
        md += f"| {i} | {r['chapter']} | {r['category']} | {r['type']} | {r['events']} | {r['concepts']} | {r['factions']} | {r['locations']} | {r['tokens_in']:,} | {r['tokens_out']:,} | {r['elapsed']:.0f}s | {err_flag} |\n"

    md += "\n"
    return md


# ====================================================================
# 角色 Wiki 页面提取编排
# ====================================================================


def build_character_pipeline(
    v1_dir: str = "data/extractions/v1_events",
    data_dir: str = "data/stories",
    operators_path: str = "data/operators.json",
    identity_map_path: str = "config/identity_map.json",
    keep_list_path: str = "config/npc_single_keep.md",
    operators: list = None,
    id_map: dict = None,
    keep_set: set = None,
) -> tuple[dict, list]:
    """构建角色提取流水线：收集 → 规范化 → 过滤 → 注入上下文。

    Args:
        v1_dir: Pass 1 提取结果目录
        data_dir: 原始故事数据目录（用于注入上下文）
        operators_path: 干员 JSON 路径
        identity_map_path: 身份映射 JSON 路径
        keep_list_path: 单章 NPC KEEP 列表 markdown 路径
        operators: 预加载干员列表（用于测试，为 None 时从文件加载）
        id_map: 预加载身份映射（用于测试，为 None 时从文件加载）
        keep_set: 预加载 KEEP 集合（用于测试，为 None 时从文件加载）

    Returns:
        (targets dict, operators list)
    """
    # 加载配置数据（如未预加载）
    if operators is None:
        with open(operators_path, "r", encoding="utf-8") as f:
            operators = json.load(f)["operators"]
    if id_map is None:
        id_map = load_identity_map(identity_map_path)
    if keep_set is None:
        keep_set = parse_keep_list(keep_list_path)

    # 链式调用
    raw = collect_from_v1(v1_dir)
    normalized = normalize_and_merge(raw, operators, id_map)
    targets = filter_targets(normalized, operators, keep_set)

    # 注入上下文（data_dir 为 None 时跳过，用于测试环境无原始数据的情况）
    if data_dir is not None:
        targets = inject_context(targets, data_dir)

    return targets, operators


def run_character_extraction(
    name_zh: str,
    character_data: dict,
    operator_archive: dict = None
) -> dict:
    """对单个角色执行 LLM 提取，生成 Wiki 页面 JSON。

    Args:
        name_zh: 角色中文名
        character_data: 聚合后的角色数据，含 chapters（set）和 events（list）
        operator_archive: 干员档案信息（可选）

    Returns:
        角色 Wiki JSON dict，包含 name_zh + LLM 输出字段 + _stats
    """
    chapter_count = len(character_data.get("chapters", []))
    events = character_data.get("events", [])

    system_prompt = build_character_system_prompt()
    user_prompt = build_character_user_prompt(
        name_zh, chapter_count, events, operator_archive
    )

    client = create_client()
    t0 = time.time()
    llm_result = call_llm(client, system_prompt, user_prompt)
    elapsed = time.time() - t0

    if llm_result.get("_parse_error"):
        return {
            "name_zh": name_zh,
            "_parse_error": True,
            "_raw": llm_result.get("_raw", ""),
            "_stats": llm_result.get("_stats", {}),
        }

    stats = llm_result.pop("_stats", {})
    llm_result["_stats"] = {**stats, "elapsed_s": elapsed}
    llm_result["name_zh"] = name_zh

    return llm_result


def save_character_output(
    data: dict,
    output_dir: str = "data/extractions/v2_characters"
) -> str:
    """保存角色 Wiki JSON 到文件。

    文件名由 name_zh 生成，将 / \\ : 替换为 _ 以避免路径问题。

    Args:
        data: 角色 Wiki JSON 数据
        output_dir: 输出目录

    Returns:
        输出文件路径
    """
    name = data["name_zh"]
    safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{safe_name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path


def run_trial_characters(
    trial_names: list[str],
    data_dir: str = "data/stories",
    v1_dir: str = "data/extractions/v1_events",
) -> dict[str, dict]:
    """试跑指定角色列表的 Wiki 页面提取。

    Args:
        trial_names: 试跑角色中文名列表
        data_dir: 原始故事数据目录
        v1_dir: Pass 1 提取结果目录

    Returns:
        {角色名: 角色 Wiki JSON} 字典
    """
    print(f"\n{'='*50}")
    print(f"角色 Wiki 提取试跑：{len(trial_names)} 个角色")
    print(f"{'='*50}")

    # 构建流水线，获取目标角色和干员列表
    targets, operators = build_character_pipeline(
        v1_dir=v1_dir, data_dir=data_dir
    )
    print(f"流水线完成：{len(targets)} 个目标角色")

    results: dict[str, dict] = {}
    total_tokens_in = 0
    total_tokens_out = 0
    t_start = time.time()
    output_dir = "output/pass2_trial"

    for i, name in enumerate(trial_names, 1):
        print(f"\n{'='*50}")
        print(f"[{i}/{len(trial_names)}] {name}")
        print(f"{'='*50}")

        if name not in targets:
            print(f"  SKIP: 不在目标角色列表中")
            continue

        character_data = targets[name]
        chapter_count = len(character_data.get("chapters", []))
        event_count = len(character_data.get("events", []))
        print(f"  出场章节: {chapter_count}, 关联事件: {event_count}")

        # 获取干员档案（如存在）
        op_archive = get_operator_archive(name, operators)

        # 执行 LLM 提取
        result = run_character_extraction(
            name, character_data, operator_archive=op_archive
        )

        s = result.get("_stats", {})
        tok_in = s.get("tokens_in", 0)
        tok_out = s.get("tokens_out", 0)
        total_tokens_in += tok_in
        total_tokens_out += tok_out

        if result.get("_parse_error"):
            print(f"  ERROR: LLM 输出解析失败")
            results[name] = result
            continue

        # 校验
        errors = validate_character_output(result, name)
        if errors:
            result["_validation_errors"] = errors
            print(f"  WARNING: 校验发现 {len(errors)} 个问题")
            for err in errors:
                print(f"    - {err}")

        # 填充后处理字段
        result["aliases"] = list(character_data.get("aliases", []))
        result["source_pass1_chapters"] = sorted(character_data.get("chapters", []))
        result["model"] = _get_model_label()
        result["generated_at"] = datetime.now(timezone.utc).isoformat()

        # 从干员数据填充档案字段
        if op_archive:
            result["race"] = op_archive.get("race", "")
            affiliations = []
            for field in ["nation", "team", "group"]:
                val = op_archive.get(field, "")
                if val:
                    affiliations.append(val)
            result["affiliations"] = affiliations

        # 保存
        path = save_character_output(result, output_dir=output_dir)
        print(f"  tokens: in={tok_in:,} out={tok_out:,}")
        print(f"  saved: {path}")

        results[name] = result

    elapsed = time.time() - t_start
    print(f"\n{'='*50}")
    print(f"试跑完成")
    print(f"  成功: {len([r for r in results.values() if not r.get('_parse_error')])} 角色")
    print(f"  失败: {len([r for r in results.values() if r.get('_parse_error')])} 角色")
    print(f"  tokens: in={total_tokens_in:,} out={total_tokens_out:,}")
    print(f"  耗时: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"  输出目录: {output_dir}/")

    return results
