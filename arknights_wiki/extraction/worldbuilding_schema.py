"""Pass 3 世界观实体 Schema 定义与校验"""
from typing import List


# === 分类枚举 ===

CONCEPT_CATEGORIES = {
    "自然现象/物质",
    "种族/血脈",
    "超自然存在",
    "技术/技艺体系",
    "社会制度/文化",
    "特殊地域/异域",
}

FACTION_CATEGORIES = {"nation", "organization"}

LOCATION_CATEGORIES = {"city", "facility"}

VALID_SOURCES = {"terra_book", "video", "story_text"}
VALID_CONFIDENCE = {"confirmed", "inferred", "conflicting"}


# === 通用必填字段 ===

_CONCEPT_REQUIRED = {"category", "definition", "summary"}
_FACTION_REQUIRED = {"category", "definition", "summary"}
_LOCATION_REQUIRED = {"category", "definition", "summary"}

# 各子类独有字段（仅用于文档，不做强制校验）
_CONCEPT_SUBCLASS_FIELDS = {
    "自然现象/物质": {"manifestation", "origin_hypothesis", "related_arts"},
    "种族/血脈": {"origin_region", "physical_traits", "related_races",
                 "oripathy_susceptibility", "lifespan"},
    "超自然存在": {"nature", "scale", "known_instances", "relation_to_humanity"},
    "技术/技艺体系": {"underlying_principle", "practitioners", "spread", "key_applications"},
    "社会制度/文化": {"origin_nation", "characteristics", "key_institutions", "social_impact"},
    "特殊地域/异域": {"location_type", "accessibility", "hazards", "phenomena"},
}

_NATION_FIELDS = {"government_type", "ruler", "key_figures", "capital",
                  "territory", "major_races", "historical_events", "foreign_relations"}
_ORGANIZATION_FIELDS = {"type", "parent_nation", "leader", "headquarters",
                        "member_composition", "goal", "external_relations"}

_CITY_FIELDS = {"parent_nation", "city_type", "scale", "known_districts", "key_events"}
_FACILITY_FIELDS = {"located_in", "facility_type", "owner", "purpose", "key_events"}


# === 校验函数 ===

def _validate_common(data: dict, required: set, valid_categories: set) -> List[str]:
    """通用字段校验"""
    errors = []
    for field in required:
        if field not in data or data[field] is None or (isinstance(data[field], str) and not data[field].strip()):
            errors.append(f"缺少必填字段: {field}")
    category = data.get("category", "")
    if category not in valid_categories:
        errors.append(f"非法 category 值: '{category}'，合法值: {valid_categories}")
    definition = data.get("definition", "")
    if isinstance(definition, str) and len(definition) > 80:
        errors.append(f"definition 超过 80 字限制 (当前 {len(definition)} 字)")
    return errors


def _validate_source_records(data: dict) -> List[str]:
    """校验 source_records 数组"""
    errors = []
    records = data.get("source_records", [])
    if not isinstance(records, list):
        return errors
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f"source_records[{i}] 不是 dict")
            continue
        src = rec.get("source", "")
        if src not in VALID_SOURCES:
            errors.append(f"source_records[{i}].source 非法: '{src}'")
        conf = rec.get("confidence", "")
        if conf and conf not in VALID_CONFIDENCE:
            errors.append(f"source_records[{i}].confidence 非法: '{conf}'")
    return errors


def validate_concept(data: dict) -> List[str]:
    """校验概念实体"""
    errors = _validate_common(data, _CONCEPT_REQUIRED, CONCEPT_CATEGORIES)
    errors.extend(_validate_source_records(data))
    name = data.get("name", "")
    if not isinstance(name, str) or not name.strip():
        errors.append("name 为空或非字符串")
    return errors


def validate_faction(data: dict) -> List[str]:
    """校验阵营实体"""
    errors = _validate_common(data, _FACTION_REQUIRED, FACTION_CATEGORIES)
    errors.extend(_validate_source_records(data))
    name = data.get("name", "")
    if not isinstance(name, str) or not name.strip():
        errors.append("name 为空或非字符串")
    return errors


def validate_location(data: dict) -> List[str]:
    """校验地点实体"""
    errors = _validate_common(data, _LOCATION_REQUIRED, LOCATION_CATEGORIES)
    errors.extend(_validate_source_records(data))
    name = data.get("name", "")
    if not isinstance(name, str) or not name.strip():
        errors.append("name 为空或非字符串")
    return errors
