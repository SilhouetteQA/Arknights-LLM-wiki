"""worldbuilding_processor 模块测试"""
import json
import os
import tempfile

from arknights_wiki.extraction.worldbuilding_processor import (
    parse_worldbuilding_output,
    aggregate_chapters,
    load_seed_db,
    save_seed_db,
    generate_wiki_pages,
)


class TestParseWorldbuildingOutput:
    def test_parse_valid_output(self):
        """解析合法的 LLM 输出"""
        raw = '{"concepts": [{"name": "源石", "category": "自然现象/物质", "definition": "核心能源", "summary": "源石是..."}], "factions": [], "locations": []}'
        result = parse_worldbuilding_output(raw)
        assert result is not None
        assert len(result["concepts"]) == 1
        assert result["concepts"][0]["name"] == "源石"

    def test_parse_output_with_code_block(self):
        """解析含 code block 的输出"""
        raw = '```json\n{"concepts": [], "factions": [], "locations": []}\n```'
        result = parse_worldbuilding_output(raw)
        assert result is not None

    def test_parse_invalid_output_returns_none(self):
        """解析无效输出返回 None"""
        result = parse_worldbuilding_output("这不是 JSON")
        assert result is None


class TestAggregateChapters:
    def test_aggregate_dedup_same_name_concept(self):
        """同名概念在跨章聚合时合并"""
        chapters = [
            {"concepts": [
                {"name": "源石", "category": "自然现象/物质", "definition": "能源矿物", "summary": "源石是基础能源。"},
            ], "factions": [], "locations": []},
            {"concepts": [
                {"name": "源石", "category": "自然现象/物质", "definition": "核心能源矿物", "summary": "源石也是矿石病的源头。"},
            ], "factions": [], "locations": []},
        ]
        result = aggregate_chapters(chapters)
        assert len(result["concepts"]) == 1
        c = result["concepts"][0]
        assert c["name"] == "源石"
        assert "基础能源" in c["summary"]
        assert "矿石病" in c["summary"]

    def test_aggregate_preserves_different_entities(self):
        """不同实体保留各自条目"""
        chapters = [
            {"concepts": [
                {"name": "源石", "category": "自然现象/物质", "definition": "...", "summary": "..."},
                {"name": "天灾", "category": "自然现象/物质", "definition": "...", "summary": "..."},
            ], "factions": [], "locations": []},
        ]
        result = aggregate_chapters(chapters)
        assert len(result["concepts"]) == 2

    def test_aggregate_splits_by_category(self):
        """聚合结果按三层分组"""
        chapters = [
            {"concepts": [], "factions": [
                {"name": "维多利亚", "category": "nation", "definition": "...", "summary": "..."},
            ], "locations": [
                {"name": "龙门", "category": "city", "definition": "...", "summary": "..."},
            ]},
        ]
        result = aggregate_chapters(chapters)
        assert "concepts" in result
        assert "factions" in result
        assert "locations" in result

    def test_aggregate_empty_chapters(self):
        """空列表不报错"""
        result = aggregate_chapters([])
        assert result["concepts"] == []
        assert result["factions"] == []
        assert result["locations"] == []


class TestSeedDbIO:
    def test_save_and_load_roundtrip(self):
        """保存后加载的种子库应一致"""
        seed_db = {
            "concepts": [{"name": "源石", "category": "自然现象/物质",
                          "definition": "...", "summary": "..."}],
            "factions": [],
            "locations": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "seed_db.json")
            save_seed_db(seed_db, path)
            loaded = load_seed_db(path)
            assert loaded["concepts"][0]["name"] == "源石"

    def test_load_nonexistent_returns_empty(self):
        """加载不存在的文件返回空种子库"""
        result = load_seed_db("/nonexistent/path.json")
        assert result == {"concepts": [], "factions": [], "locations": []}


class TestGenerateWikiPages:
    def test_generate_writes_files(self):
        """生成 Wiki 页面写入文件"""
        seed_db = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质",
                 "definition": "核心能源", "summary": "源石是泰拉世界的基础。"},
            ],
            "factions": [
                {"name": "维多利亚", "category": "nation",
                 "definition": "帝国", "summary": "泰拉帝国之一。"},
            ],
            "locations": [
                {"name": "龙门", "category": "city",
                 "definition": "移动城市", "summary": "大炎的经济中心。"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = generate_wiki_pages(seed_db, tmp)
            assert len(paths) == 3
            for p in paths:
                assert os.path.exists(p)
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                    assert "源石" in content or "维多利亚" in content or "龙门" in content
