"""Pass 3 后处理: JSON 解析 + 校验 + 跨章聚合 + 种子库 IO + Wiki 页面生成"""
import json
import os
from typing import Optional

from .llm_client import parse_llm_response
from .worldbuilding_schema import validate_concept, validate_faction, validate_location


def parse_worldbuilding_output(raw: str) -> Optional[dict]:
    """解析 LLM 世界构建输出，返回 dict 或 None"""
    return parse_llm_response(raw)


def _merge_entity(existing: dict, new: dict) -> dict:
    """合并两个同名实体，保留更详细的信息"""
    merged = dict(existing)

    # definition: 保留更长的
    if len(new.get("definition", "")) > len(existing.get("definition", "")):
        merged["definition"] = new["definition"]

    # summary: 拼接（去重合并）
    existing_summary = existing.get("summary", "")
    new_summary = new.get("summary", "")
    if new_summary and new_summary not in existing_summary:
        if existing_summary:
            merged["summary"] = existing_summary + "\n\n" + new_summary
        else:
            merged["summary"] = new_summary

    # aliases: 合并去重
    existing_aliases = set(existing.get("aliases", []))
    new_aliases = set(new.get("aliases", []))
    merged["aliases"] = sorted(existing_aliases | new_aliases)

    # source_records: 合并
    merged["source_records"] = existing.get("source_records", []) + new.get("source_records", [])

    # 独有字段: 非空值从 new 提升
    for key in new:
        if key in ("name", "category", "definition", "summary", "aliases",
                    "source_records", "story_events"):
            continue
        if key not in merged or not merged[key]:
            new_val = new.get(key)
            if new_val:
                merged[key] = new_val

    # related_*: 合并去重
    for rel_key in ("related_concepts", "related_factions", "related_locations"):
        existing_rels = {r.get("name", ""): r for r in existing.get(rel_key, [])}
        for r in new.get(rel_key, []):
            rname = r.get("name", "")
            if rname and rname not in existing_rels:
                existing_rels[rname] = r
        merged[rel_key] = list(existing_rels.values())

    return merged


def aggregate_chapters(chapter_results: list[dict]) -> dict:
    """跨章聚合: 同名实体合并去重

    Args:
        chapter_results: 每章的 LLM 输出列表，每项含 concepts/factions/locations

    Returns:
        聚合后的种子库 {"concepts": [...], "factions": [...], "locations": [...]}
    """
    aggregated = {"concepts": {}, "factions": {}, "locations": {}}

    for chapter in chapter_results:
        for entity_type in ("concepts", "factions", "locations"):
            entities = chapter.get(entity_type, [])
            for entity in entities:
                name = entity.get("name", "").strip()
                if not name:
                    continue
                if name in aggregated[entity_type]:
                    aggregated[entity_type][name] = _merge_entity(
                        aggregated[entity_type][name], entity
                    )
                else:
                    aggregated[entity_type][name] = dict(entity)

    return {
        "concepts": list(aggregated["concepts"].values()),
        "factions": list(aggregated["factions"].values()),
        "locations": list(aggregated["locations"].values()),
    }


def load_seed_db(path: str) -> dict:
    """加载种子库 JSON"""
    if not os.path.exists(path):
        return {"concepts": [], "factions": [], "locations": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_seed_db(seed_db: dict, path: str):
    """保存种子库 JSON"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seed_db, f, ensure_ascii=False, indent=2)


def generate_wiki_pages(seed_db: dict, output_dir: str) -> list[str]:
    """从种子库生成初版 Wiki 页面 Markdown

    每个实体生成一个 md 文件，按实体类型分目录。
    """
    paths = []
    for entity_type in ("concepts", "factions", "locations"):
        type_dir = os.path.join(output_dir, entity_type)
        os.makedirs(type_dir, exist_ok=True)
        for entity in seed_db.get(entity_type, []):
            name = entity["name"]
            safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
            path = os.path.join(type_dir, f"{safe_name}.md")
            md = _entity_to_markdown(entity, entity_type)
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            paths.append(path)
    return paths


def _entity_to_markdown(entity: dict, entity_type: str) -> str:
    """单个实体转 Markdown"""
    md = f"# {entity['name']}\n\n"
    md += f"**分类:** {entity.get('category', '')}\n\n"
    md += f"**定义:** {entity.get('definition', '')}\n\n"
    md += f"## 概述\n\n{entity.get('summary', '')}\n\n"

    if entity.get("aliases"):
        md += f"**别名:** {', '.join(entity['aliases'])}\n\n"

    # 来源
    sources = entity.get("source_records", [])
    if sources:
        md += "## 来源\n\n"
        for s in sources:
            md += f"- {s.get('source_detail', s.get('source', ''))}"
            if s.get("confidence"):
                md += f" (置信度: {s['confidence']})"
            md += "\n"

    return md
