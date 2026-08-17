"""T4: 生成管线 v3 纯函数测试（mock LLM，零外部调用）"""
import json
from pathlib import Path

from scripts.generate_benchmark_questions import (
    ANGLE_CONFIG,
    build_prompt,
    chapter_name_check,
    kb_check,
    load_materials,
)

MATERIALS = Path("benchmarks/arknights_bench/materials")


class TestLoadMaterials:
    def test_missing_angle_returns_empty(self):
        assert load_materials("no_such_angle") == []

    def test_loads_existing(self):
        items = load_materials("region")
        assert len(items) >= 20
        first = items[0]
        assert first["name"] and first["source_file"] and first["excerpt"]


class TestChapterCheck:
    def test_known_chapter(self):
        # 《二次呼吸》在 chapter_timeline.json 中
        res = chapter_name_check("《二次呼吸》讲了什么", "")
        assert "二次呼吸" not in res["unknown"]

    def test_unknown_chapter(self):
        res = chapter_name_check("《不存在的章节名XYZ》是什么", "")
        assert "不存在的章节名XYZ" in res["unknown"]

    def test_no_chapters(self):
        res = chapter_name_check("德克萨斯是谁", "")
        assert res["checked"] == 0


class TestKbCheck:
    def test_empty_evidence(self):
        res = kb_check({"evidence": []})
        assert res["kb_all_found"] is None or res["kb_all_found"] is False

    def test_kb_entity(self):
        res = kb_check({"evidence": ["德克萨斯"]})
        assert isinstance(res, dict)


class TestBuildPrompt:
    def test_simple_route(self):
        mats = [{"name": "德克萨斯", "source_file": "x.json", "excerpt": "企鹅物流成员"}]
        p = build_prompt("character", "simple", mats)
        assert "[材料1]" in p
        assert "简单路由" in p
        assert "企鹅物流成员" in p

    def test_complex_route(self):
        mats = [
            {"name": "A", "source_file": "a.json", "excerpt": "内容A"},
            {"name": "B", "source_file": "b.json", "excerpt": "内容B"},
        ]
        p = build_prompt("event", "complex", mats)
        assert "[材料1]" in p and "[材料2]" in p
        assert "复杂路由" in p


class TestConfig:
    def test_all_angles_defined(self):
        assert set(ANGLE_CONFIG) == {"character", "event", "region", "organization", "combat_power", "worldview"}

    def test_total_100(self):
        assert sum(c["total"] for c in ANGLE_CONFIG.values()) == 100
