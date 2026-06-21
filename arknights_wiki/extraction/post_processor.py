"""后处理：场景行号→全局行号 + 角色名对齐 + 事件去重 + 分批合并 + 校验"""
import json
from difflib import SequenceMatcher


def load_identity_map(config_path: str = "config/identity_map.json") -> dict:
    """加载角色别名映射配置，返回 {别名: 规范名} 字典"""
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", {})


def normalize_character_type(char: dict, id_map: dict) -> str:
    """根据 identity_map 修正角色 type"""
    if char["name"] in id_map:
        return "operator"
    return char.get("type", "npc")


def _convert_scene_ranges(data: dict, cd) -> dict:
    """将 LLM 输出的 scene-relative line_range 转换为全局行号。

    输入: {"scene": 1, "lines": [10, 20]}
    输出: line_range → [全局起始, 全局结束]
    """
    from .dialogue_loader import scene_line_to_global

    for ev in data.get("events", []):
        lr = ev.get("line_range", {})
        if isinstance(lr, dict) and "scene" in lr:
            scene_num = lr["scene"]
            lines = lr.get("lines", [1, 1])
            ev["line_range"] = [
                scene_line_to_global(cd, scene_num, lines[0]),
                scene_line_to_global(cd, scene_num, lines[1]),
            ]
        elif isinstance(lr, list):
            # 已经是全局行号格式，保持不变
            pass

    for c in data.get("concepts", []):
        lr = c.get("line_range", {})
        if isinstance(lr, dict) and "scene" in lr:
            scene_num = lr["scene"]
            lines = lr.get("lines", [1, 1])
            c["line_range"] = [
                scene_line_to_global(cd, scene_num, lines[0]),
                scene_line_to_global(cd, scene_num, lines[1]),
            ]

    return data


def align_character_names(
    characters: list[dict],
    operators: list[dict],
    id_map: dict,
) -> tuple[list[dict], list[str]]:
    """角色名对齐到规范干员名。四级匹配：精确→identity_map→复合名拆分→模糊"""
    op_names = {op["name_zh"] for op in operators}
    unmatched = []

    for char in characters:
        name = char["name"].strip()

        if name in op_names:
            continue

        if name in id_map:
            canonical = id_map[name]
            if canonical != name and not canonical.startswith("character:"):
                char["name"] = canonical
            char["type"] = "operator"
            continue

        # 复合名拆分匹配
        matched = False
        if "·" in name or len(name) >= 4:
            segments = name.split("·") if "·" in name else [name]
            for part in segments:
                if part == name:
                    continue
                if part in id_map:
                    char["name"] = id_map[part]
                    char["type"] = "operator"
                    matched = True
                    break
                if part in op_names:
                    char["name"] = part
                    char["type"] = "operator"
                    matched = True
                    break
            if matched:
                continue

        # 模糊匹配
        best_ratio = 0.0
        best_name = name
        for opn in op_names:
            len_diff = abs(len(name) - len(opn))
            if len_diff > 3:
                continue
            ratio = SequenceMatcher(None, name, opn).ratio()
            if ratio >= 0.6 and ratio > best_ratio:
                best_ratio = ratio
                best_name = opn
        if best_ratio >= 0.6:
            char["name"] = best_name
            char["type"] = "operator"
        else:
            unmatched.append(name)

    return characters, unmatched


def deduplicate_events(events: list[dict], threshold: float = 0.75) -> list[dict]:
    """事件去重：相似度 > threshold 的事件合并，保留更详细的版本"""
    if len(events) <= 1:
        return events

    kept = []
    merged_indices = set()

    for i, e1 in enumerate(events):
        if i in merged_indices:
            continue
        best = e1
        for j, e2 in enumerate(events):
            if j <= i or j in merged_indices:
                continue
            ratio = SequenceMatcher(None, e1["event"], e2["event"]).ratio()
            if ratio >= threshold:
                if len(e2["event"]) > len(best["event"]):
                    best = e2
                merged_indices.add(j)
        kept.append(best)

    return kept


def _reject_broad_concepts(concepts: list[dict], total_lines: int) -> list[dict]:
    """拒绝范围过大的概念（覆盖整个章节/批次的不是实质性讨论）"""
    filtered = []
    for c in concepts:
        lr = c.get("line_range", [0, 0])
        span = lr[1] - lr[0] if len(lr) == 2 else total_lines
        # 概念讨论范围不应超过 200 行或总行数的 30%
        max_span = min(200, total_lines * 0.3)
        if span <= max_span and lr[0] > 0:
            filtered.append(c)
    return filtered


def merge_batches(batches: list[dict], chapter: str, source_category: str = "",
                  chapter_cd=None) -> dict:
    """合并多个批次的提取结果。"""
    if len(batches) == 1:
        result = dict(batches[0])
        result["chapter"] = chapter
        result["batch_count"] = 1
        if source_category:
            result["category"] = source_category
        if "_raw" not in result:
            result["_raw"] = batches[0].get("_raw", "")
        if "_parse_error" not in result:
            result["_parse_error"] = batches[0].get("_parse_error", False)
        return result

    merged = {
        "chapter": chapter,
        "category": source_category or batches[0].get("category", ""),
        "batch_count": len(batches),
        "summary": "",
        "events": [],
        "characters": [],
        "concepts": [],
        "factions": [],
        "locations": [],
        "_raw": "\n---BATCH---\n".join(b.get("_raw", "") for b in batches if b.get("_raw")),
        "_parse_error": any(b.get("_parse_error") for b in batches),
    }

    # summary: 合并所有批次
    merged["summary"] = "\n\n".join(
        b.get("summary", "") for b in batches if b.get("summary")
    )

    # events: 收集 → 排序 → 去重
    all_events = []
    for b in batches:
        all_events.extend(b.get("events", []))
    all_events.sort(key=lambda e: (
        e.get("line_range", [0, 0])[0] if isinstance(e.get("line_range"), list) else 0
    ))
    merged["events"] = deduplicate_events(all_events)

    # characters: 同名合并
    seen_chars: dict[str, dict] = {}
    for b in batches:
        for c in b.get("characters", []):
            name = c["name"]
            if name in seen_chars:
                if c.get("first_appearance_chapter"):
                    seen_chars[name]["first_appearance_chapter"] = True
            else:
                seen_chars[name] = dict(c)
    merged["characters"] = list(seen_chars.values())

    # concepts: 同名合并 + 拒绝范围过大的
    seen_concepts: dict[str, dict] = {}
    for b in batches:
        for c in b.get("concepts", []):
            name = c["concept"]
            if name in seen_concepts:
                existing = seen_concepts[name]
                lr = c.get("line_range", [0, 0])
                existing["line_range"] = [
                    min(existing["line_range"][0], lr[0]),
                    max(existing["line_range"][1], lr[1]),
                ]
                if c.get("discussion_summary"):
                    existing["discussion_summary"] = (
                        existing.get("discussion_summary", "")
                        + "\n\n"
                        + c["discussion_summary"]
                    )
            else:
                seen_concepts[name] = dict(c)
    all_concepts = list(seen_concepts.values())

    # 拒绝范围过大的概念
    total_lines = max(
        (e.get("line_range", [0, 0])[1] for e in all_events if isinstance(e.get("line_range"), list)),
        default=100
    )
    merged["concepts"] = _reject_broad_concepts(all_concepts, total_lines)

    # factions: 跨批合并，同名保留不同 line_range 的条目
    merged["factions"] = []
    for b in batches:
        merged["factions"].extend(b.get("factions", []))

    # locations: 跨批合并，同名保留不同 line_range 的条目
    merged["locations"] = []
    for b in batches:
        merged["locations"].extend(b.get("locations", []))

    return merged


def validate_extraction(data: dict, total_lines: int) -> list[str]:
    """合法性校验"""
    errors: list[str] = []

    if not data.get("chapter"):
        errors.append("chapter 字段为空")
    if not data.get("category"):
        errors.append("category 字段为空")
    if not data.get("events"):
        errors.append("events 数组为空或缺失")

    for i, event in enumerate(data.get("events", [])):
        if not event.get("event"):
            errors.append(f"events[{i}].event 为空")
        if not event.get("type"):
            errors.append(f"events[{i}].type 为空")
        lr = event.get("line_range", [])
        if not isinstance(lr, list) or len(lr) != 2:
            errors.append(f"events[{i}].line_range 无效: {lr}")
        elif lr[1] > total_lines:
            errors.append(f"events[{i}].line_range {lr} 超出总行数 {total_lines}")

    return errors


# ─── 角色输出校验 ───

VALID_POWER_LEVELS = {
    "信息不足",
    "战场中坚",
    "军事精锐",
    "大国将军",
    "传奇英雄",
    "王庭之主",
    "神明碎片",
    "崛起之物",
    "文明之敌",
}


def validate_character_output(data: dict, name_zh: str) -> list[str]:
    """校验角色 Wiki 页面输出 JSON 的合法性。

    Args:
        data: 角色 Wiki JSON 数据
        name_zh: 角色中文名（用于错误信息）

    Returns:
        错误字符串列表，空列表表示校验通过
    """
    errors: list[str] = []

    # summary 必须是非空字符串
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        errors.append(f"{name_zh}: summary 为空或缺失")

    # personality 必须是 dict，且包含非空的 traits (list) 和 description (string)
    personality = data.get("personality")
    if not isinstance(personality, dict):
        errors.append(f"{name_zh}: personality 缺失或不是 dict")
    else:
        traits = personality.get("traits")
        if not isinstance(traits, list) or len(traits) == 0:
            errors.append(f"{name_zh}: personality.traits 为空或缺失")
        desc = personality.get("description")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"{name_zh}: personality.description 为空或缺失")

    # abilities 必须是 dict，包含非空 description (string) 和合法的 power_level
    abilities = data.get("abilities")
    if not isinstance(abilities, dict):
        errors.append(f"{name_zh}: abilities 缺失或不是 dict")
    else:
        ab_desc = abilities.get("description")
        if not isinstance(ab_desc, str) or not ab_desc.strip():
            errors.append(f"{name_zh}: abilities.description 为空或缺失")
        power_level = abilities.get("power_level", "")
        if power_level not in VALID_POWER_LEVELS:
            errors.append(f"{name_zh}: abilities.power_level 值无效: {power_level}")
        # power_level_evidence: list of {chapter, evidence}
        evidence = abilities.get("power_level_evidence")
        if not isinstance(evidence, list):
            errors.append(f"{name_zh}: abilities.power_level_evidence 缺失或不是 list")
        else:
            for k, ev_item in enumerate(evidence):
                if not isinstance(ev_item, dict):
                    errors.append(f"{name_zh}: power_level_evidence[{k}] 不是 dict")
                    continue
                if not isinstance(ev_item.get("chapter"), str) or not ev_item["chapter"].strip():
                    errors.append(f"{name_zh}: power_level_evidence[{k}].chapter 为空")
                if not isinstance(ev_item.get("evidence"), str) or not ev_item["evidence"].strip():
                    errors.append(f"{name_zh}: power_level_evidence[{k}].evidence 为空")

    # participated_events 必须是 list；若包含条目，每个条目的 event 和 chapter 必须非空
    participated = data.get("participated_events")
    if not isinstance(participated, list):
        errors.append(f"{name_zh}: participated_events 缺失或不是 list")
    else:
        for i, pe in enumerate(participated):
            if not isinstance(pe, dict):
                errors.append(f"{name_zh}: participated_events[{i}] 不是 dict")
                continue
            ev = pe.get("event")
            ch = pe.get("chapter")
            if not isinstance(ev, str) or not ev.strip():
                errors.append(f"{name_zh}: participated_events[{i}].event 为空")
            if not isinstance(ch, str) or not ch.strip():
                errors.append(f"{name_zh}: participated_events[{i}].chapter 为空")

    return errors
