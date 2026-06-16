# arknights_wiki/extraction/post_processor.py
"""后处理：角色名对齐 + 事件去重 + 分批合并 + 合法性校验"""
import json
from difflib import SequenceMatcher


def load_identity_map(config_path: str = "config/identity_map.json") -> dict:
    """加载角色别名映射配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", {})


def normalize_character_type(char: dict, id_map: dict) -> str:
    """根据 identity_map 修正角色 type：若角色名在映射中则返回 operator，否则保持原 type"""
    for alias in id_map:
        if alias == char["name"] or char["name"] == alias:
            return "operator"
    return char.get("type", "npc")


def align_character_names(
    characters: list[dict],
    operators: list[dict],
    id_map: dict,
) -> tuple[list[dict], list[str]]:
    """角色名对齐到规范名。三级匹配：精确匹配 -> identity_map -> 模糊匹配。

    Returns:
        (对齐后的角色列表, 未匹配名称列表)
    """
    op_names = {op["name_zh"] for op in operators}
    unmatched = []

    for char in characters:
        name = char["name"]
        # 1. 精确匹配：名已在 operators 中
        if name in op_names:
            continue
        # 2. identity_map 匹配：别名映射到规范 entity_id
        if name in id_map:
            char["type"] = "operator"
            continue
        # 3. 模糊匹配：相似度 >= 0.6 时修正为规范名（适配短中文名，L=3差1字 ratio≈0.667）
        best_ratio = 0.0
        best_name = name
        for opn in op_names:
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
    """事件去重：相似度 > threshold 的事件合并，保留描述更详细（更长的 event 字段）的版本"""
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
                # 保留更详细的（更长的 event 描述）
                if len(e2["event"]) > len(best["event"]):
                    best = e2
                merged_indices.add(j)
        kept.append(best)

    return kept


def merge_batches(batches: list[dict], chapter: str) -> dict:
    """合并多个批次的提取结果。

    - events: 按 line_range 排序后去重
    - characters: 同名合并，保留 first_appearance_chapter=True
    - concepts: 同名合并 line_range 取最小/最大
    """
    if len(batches) == 1:
        result = dict(batches[0])
        result["chapter"] = chapter
        result["batch_count"] = 1
        # 保留 _raw 和 _parse_error
        if "_raw" not in result:
            result["_raw"] = batches[0].get("_raw", "")
        if "_parse_error" not in result:
            result["_parse_error"] = batches[0].get("_parse_error", False)
        return result

    merged = {
        "chapter": chapter,
        "category": batches[0]["category"],
        "batch_count": len(batches),
        "summary": "\n\n".join(b.get("summary", "") for b in batches if b.get("summary")),
        "events": [],
        "characters": [],
        "concepts": [],
        "_raw": "\n---BATCH---\n".join(b.get("_raw", "") for b in batches if b.get("_raw")),
        "_parse_error": any(b.get("_parse_error") for b in batches),
    }

    # events: 收集所有 -> 按 line_range 起始行排序 -> 去重
    all_events = []
    for b in batches:
        all_events.extend(b.get("events", []))
    all_events.sort(key=lambda e: e.get("line_range", [0, 0])[0])
    merged["events"] = deduplicate_events(all_events)

    # characters: 同名合并，任意批次标记 first_appearance_chapter=True 时保留 True
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

    # concepts: 同名合并 line_range
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
                # 合并 discussion_summary
                if c.get("discussion_summary"):
                    existing["discussion_summary"] = (
                        existing.get("discussion_summary", "")
                        + "\n\n"
                        + c["discussion_summary"]
                    )
            else:
                seen_concepts[name] = dict(c)
    merged["concepts"] = list(seen_concepts.values())

    return merged


def validate_extraction(data: dict, total_lines: int) -> list[str]:
    """合法性校验，返回错误信息列表。校验 chapter、category、events 及 line_range。"""
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
