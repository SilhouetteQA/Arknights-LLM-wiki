import json, os, tempfile
from arknights_wiki.extraction.orchestrator import (
    generate_review_markdown,
    save_extraction,
    discover_chapters,
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
