import json, os, tempfile
from arknights_wiki.extraction.orchestrator import (
    generate_review_markdown,
    save_extraction,
    discover_chapters,
    build_character_pipeline,
    save_character_output,
)


def test_discover_chapters():
    """发现章节目录"""
    tmp = tempfile.mkdtemp()
    for cat in ["main", "side"]:
        os.makedirs(f"{tmp}/{cat}/测试章", exist_ok=True)
        node = {
            "id": "1-1", "title": "测试", "chapter": "测试章",
            "category": cat, "source_url": "",
            "lines": [{"speaker": "阿米娅", "type": "dialogue", "text": "测试"}]
        }
        with open(f"{tmp}/{cat}/测试章/1-1.json", "w", encoding="utf-8") as f:
            json.dump(node, f, ensure_ascii=False)

    chapters = discover_chapters(tmp)
    assert ("main", "测试章") in chapters
    assert ("side", "测试章") in chapters


def test_generate_review_markdown():
    """生成审阅 Markdown"""
    data = {
        "chapter": "慈悲灯塔",
        "category": "main",
        "summary": "测试摘要。",
        "events": [
            {"event": "战斗开始", "type": "battle", "line_range": [1, 2],
             "participants": ["阿米娅"], "location": "战场", "significance": "重要"},
        ],
        "characters": [
            {"name": "阿米娅", "type": "operator", "role_in_chapter": "指挥"},
        ],
        "concepts": [
            {"concept": "源石", "line_range": [1, 2],
             "discussion_summary": "讨论源石的本质", "is_substantive": True},
        ],
    }
    lines = ["[阿米娅] 准备作战。", "[旁白] 战场硝烟弥漫。"]

    md = generate_review_markdown(data, lines)
    assert "# 慈悲灯塔" in md
    assert "战斗开始" in md
    assert "battle" in md
    assert "阿米娅" in md
    assert "源石" in md


def test_save_extraction_creates_directory_and_file():
    """保存提取结果自动创建目录"""
    tmp = tempfile.mkdtemp()
    data = {
        "chapter": "测试章", "category": "main", "processed_at": "2026-06-16",
        "model": "MiniMax-M3", "batch_count": 1, "summary": "测试",
        "events": [], "characters": [], "concepts": [],
        "stats": {"tokens_in": 100, "tokens_out": 50, "elapsed_s": 2.0},
    }
    output_dir = f"{tmp}/extractions/v1_events"
    save_extraction(data, output_dir)
    path = f"{output_dir}/main/测试章.json"
    assert os.path.exists(path)
    loaded = json.load(open(path, encoding="utf-8"))
    assert loaded["chapter"] == "测试章"


class TestCharacterExtraction:
    """角色 Wiki 提取编排测试"""

    def test_build_character_pipeline_aggregates(self):
        """build_character_pipeline 链式调用：收集→规范化→过滤→注入上下文"""
        import tempfile, os, json
        from arknights_wiki.extraction.orchestrator import build_character_pipeline

        # 创建临时 v1_events 目录
        tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmpdir, "main"), exist_ok=True)
        chapter_data = {
            "chapter": "test_chapter",
            "category": "main",
            "events": [
                {"event": "test event", "type": "battle", "line_range": [1, 10],
                 "participants": ["阿米娅", "博士"], "significance": "test", "is_imaginary": False}
            ]
        }
        with open(os.path.join(tmpdir, "main", "test_chapter.json"), "w", encoding="utf-8") as f:
            json.dump(chapter_data, f, ensure_ascii=False)

        operators = [{"name_zh": "阿米娅", "race": "卡特斯", "nation": "罗德岛", "team": "", "group": ""}]
        id_map = {}
        keep_set = set()

        try:
            targets, ops = build_character_pipeline(
                v1_dir=tmpdir, data_dir=None,
                operators=operators, id_map=id_map, keep_set=keep_set
            )
            assert "阿米娅" in targets
            assert len(targets["阿米娅"]["events"]) == 1
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_save_character_output(self, tmp_path):
        """保存角色输出 JSON 到指定目录"""
        import os, json
        from arknights_wiki.extraction.orchestrator import save_character_output
        data = {"name_zh": "阿米娅", "summary": "test summary"}
        out_dir = str(tmp_path / "v2_test")
        path = save_character_output(data, output_dir=out_dir)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["name_zh"] == "阿米娅"

    def test_save_character_output_sanitizes_filename(self, tmp_path):
        """文件名中的 / \\ : 被替换为 _"""
        import os
        from arknights_wiki.extraction.orchestrator import save_character_output
        data = {"name_zh": "A/B:C", "summary": "test"}
        out_dir = str(tmp_path / "v2_test")
        path = save_character_output(data, output_dir=out_dir)
        assert "/" not in os.path.basename(path)
        assert "\\" not in os.path.basename(path)
        assert ":" not in os.path.basename(path)
