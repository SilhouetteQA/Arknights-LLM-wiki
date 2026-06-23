import json
from arknights_wiki.extraction.worldbuilding_schema import (
    CONCEPT_CATEGORIES, FACTION_CATEGORIES, LOCATION_CATEGORIES,
    validate_concept, validate_faction, validate_location,
)


class TestConceptSchema:
    def test_valid_minimal_concept(self):
        """最简合法概念实体通过校验"""
        concept = {
            "name": "源石",
            "category": "自然现象/物质",
            "definition": "泰拉世界的核心能源矿物",
            "summary": "源石是泰拉世界最核心的能源物质...",
        }
        errors = validate_concept(concept)
        assert errors == []

    def test_concept_missing_required_fields(self):
        """缺少必填字段时返回错误"""
        errors = validate_concept({"name": "源石"})
        assert len(errors) > 0

    def test_concept_invalid_category(self):
        """不在六子类中的 category 被拒绝"""
        errors = validate_concept({
            "name": "源石", "category": "不存在的分类",
            "definition": "...", "summary": "..."
        })
        assert len(errors) == 1
        assert "category" in errors[0]

    def test_concept_category_values(self):
        """六子类合法值全部通过"""
        for cat in CONCEPT_CATEGORIES:
            errors = validate_concept({
                "name": "test", "category": cat,
                "definition": "...", "summary": "..."
            })
            assert errors == [], f"合法 category '{cat}' 不应产生错误"

    def test_concept_with_subclass_fields(self):
        """带子类独有字段的概念实体通过校验"""
        concept = {
            "name": "萨卡兹",
            "category": "种族/血脈",
            "definition": "泰拉世界的古老种族",
            "summary": "萨卡兹是...",
            "aliases": ["魔族", "提卡兹"],
            "origin_region": "卡兹戴尔地区",
            "physical_traits": "体表有角或尾等特征",
            "related_races": ["提卡兹"],
            "oripathy_susceptibility": "高",
            "lifespan": "较长",
            "source_records": [{
                "source": "terra_book", "source_detail": "大地巡旅 第4章",
                "location": "page 80", "confidence": "confirmed"
            }],
            "story_events": [],
            "related_concepts": [],
            "related_factions": [],
            "related_locations": [],
        }
        errors = validate_concept(concept)
        assert errors == []

    def test_concept_definition_too_long(self):
        """definition 超过 80 字返回错误"""
        errors = validate_concept({
            "name": "test", "category": "自然现象/物质",
            "definition": "x" * 81, "summary": "ok"
        })
        assert len(errors) == 1
        assert "definition" in errors[0]

    def test_concept_source_records_invalid_source(self):
        """source_records 中非法 source 值返回错误"""
        concept = {
            "name": "test", "category": "自然现象/物质",
            "definition": "...", "summary": "...",
            "source_records": [{"source": "invalid", "source_detail": "",
                                "location": "", "confidence": "confirmed"}]
        }
        errors = validate_concept(concept)
        assert len(errors) >= 1

    def test_concept_source_records_invalid_confidence(self):
        """source_records 中非法 confidence 值返回错误"""
        concept = {
            "name": "test", "category": "自然现象/物质",
            "definition": "...", "summary": "...",
            "source_records": [{"source": "terra_book", "source_detail": "",
                                "location": "", "confidence": "maybe"}]
        }
        errors = validate_concept(concept)
        assert len(errors) >= 1


class TestFactionSchema:
    def test_valid_minimal_nation(self):
        faction = {
            "name": "维多利亚",
            "category": "nation",
            "definition": "泰拉世界的帝国之一",
            "summary": "维多利亚是...",
        }
        errors = validate_faction(faction)
        assert errors == []

    def test_valid_minimal_organization(self):
        faction = {
            "name": "莱茵生命",
            "category": "organization",
            "definition": "哥伦比亚的科研公司",
            "summary": "莱茵生命是...",
        }
        errors = validate_faction(faction)
        assert errors == []

    def test_faction_invalid_category(self):
        errors = validate_faction({
            "name": "test", "category": "invalid",
            "definition": "...", "summary": "..."
        })
        assert len(errors) == 1

    def test_nation_with_all_fields(self):
        faction = {
            "name": "乌萨斯",
            "category": "nation",
            "definition": "北方的军事帝国",
            "summary": "乌萨斯是泰拉北方的军事帝国...",
            "aliases": ["乌萨斯帝国"],
            "government_type": "军事帝国",
            "ruler": "费奥多尔皇帝",
            "key_figures": [{"name": "维特", "role": "议长", "description": "..."}],
            "capital": "切尔诺伯格（已废弃）/ 新都",
            "territory": "泰拉北方大部，含多座移动城市",
            "major_races": ["乌萨斯"],
            "historical_events": [{"name": "乌卡战争", "timeframe": "...",
                                   "description": "多次与卡西米尔的战争"}],
            "foreign_relations": [{"target_nation": "卡西米尔", "attitude": "敌对",
                                   "description": "..."}],
            "source_records": [],
            "story_events": [],
            "related_concepts": [],
        }
        errors = validate_faction(faction)
        assert errors == []

    def test_organization_with_member_composition(self):
        faction = {
            "name": "整合运动",
            "category": "organization",
            "definition": "感染者反抗组织",
            "summary": "...",
            "type": "地下/军事",
            "leader": "塔露拉（前）",
            "member_composition": [
                {"name": "塔露拉", "role": "前领袖", "description": "..."},
                {"name": "弑君者", "role": "干部", "description": "..."},
            ],
            "goal": "为感染者争取生存权利",
            "source_records": [],
            "story_events": [],
            "related_concepts": [],
        }
        errors = validate_faction(faction)
        assert errors == []


class TestLocationSchema:
    def test_valid_minimal_city(self):
        location = {
            "name": "龙门",
            "category": "city",
            "definition": "大炎移动城市",
            "summary": "龙门是大炎的代表性移动城市...",
        }
        errors = validate_location(location)
        assert errors == []

    def test_valid_minimal_facility(self):
        location = {
            "name": "罗德岛本舰",
            "category": "facility",
            "definition": "罗德岛制药公司的陆行舰",
            "summary": "罗德岛本舰是...",
        }
        errors = validate_location(location)
        assert errors == []

    def test_location_invalid_category(self):
        errors = validate_location({
            "name": "test", "category": "invalid",
            "definition": "...", "summary": "..."
        })
        assert len(errors) == 1

    def test_city_with_all_fields(self):
        location = {
            "name": "汐斯塔",
            "category": "city",
            "definition": "哥伦比亚的独立移动城市",
            "summary": "...",
            "aliases": ["汐斯塔市"],
            "parent_nation": "哥伦比亚",
            "city_type": "移动城市",
            "scale": "中型移动城市",
            "known_districts": [{"name": "汐斯塔市区", "description": "..."}],
            "key_events": [{"name": "汐斯塔火山事件", "description": "..."}],
            "source_records": [],
            "story_events": [],
            "related_factions": [],
            "related_concepts": [],
        }
        errors = validate_location(location)
        assert errors == []

    def test_facility_with_owner(self):
        location = {
            "name": "切尔诺伯格核心城",
            "category": "facility",
            "definition": "切尔诺伯格的核心城区",
            "summary": "...",
            "located_in": "切尔诺伯格",
            "facility_type": "移动城市核心区",
            "owner": "乌萨斯（原）",
            "purpose": "城市指挥中心及能源核心",
            "key_events": [{"name": "切尔诺伯格事变", "chapter": "黑暗时代",
                            "description": "..."}],
            "source_records": [],
            "story_events": [],
            "related_factions": [],
            "related_concepts": [],
        }
        errors = validate_location(location)
        assert errors == []
