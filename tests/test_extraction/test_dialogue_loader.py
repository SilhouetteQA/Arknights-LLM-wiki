"""dialogue_loader 模块测试"""
import json, os, tempfile
from arknights_wiki.extraction.dialogue_loader import load_chapter, ChapterDialogue, split_chapter


def test_load_chapter_single_node():
    """加载包含一个 story node 的章节目录"""
    tmp = tempfile.mkdtemp()
    os.makedirs(f"{tmp}/测试章", exist_ok=True)
    node = {
        "id": "1-1_test",
        "title": "测试节点",
        "chapter": "测试章",
        "category": "main",
        "source_url": "https://example.com",
        "lines": [
            {"speaker": "阿米娅", "type": "dialogue", "text": "博士，准备好了吗？"},
            {"speaker": "博士", "type": "dialogue", "text": "走吧。"},
            {"speaker": "旁白", "type": "narration", "text": "罗德岛的走廊空无一人。"}
        ]
    }
    with open(f"{tmp}/测试章/1-1_test.json", "w", encoding="utf-8") as f:
        json.dump(node, f, ensure_ascii=False)

    result = load_chapter(f"{tmp}/测试章")

    assert isinstance(result, ChapterDialogue)
    assert result.chapter == "测试章"
    assert result.category == "main"
    assert len(result.lines) == 3
    assert result.lines[0]["index"] == 1
    assert result.lines[0]["speaker"] == "阿米娅"
    assert result.lines[0]["type"] == "dialogue"
    assert result.lines[0]["text"] == "博士，准备好了吗？"
    assert result.lines[2]["index"] == 3
    assert result.lines[2]["speaker"] == "旁白"
    assert result.lines[2]["type"] == "narration"
    assert result.lines[2]["text"] == "罗德岛的走廊空无一人。"
    assert "阿米娅" in result.text
    assert "罗德岛的走廊空无一人" in result.text


def test_load_chapter_multi_node_order():
    """多个 node 按文件名排序拼接，行号连续递增"""
    tmp = tempfile.mkdtemp()
    os.makedirs(f"{tmp}/测试章", exist_ok=True)
    for i, name in enumerate(["2_second.json", "1_first.json"]):
        node = {
            "id": f"1-{i}_test", "title": name, "chapter": "测试章",
            "category": "side", "source_url": "",
            "lines": [{"speaker": "测试角色", "type": "dialogue", "text": f"第{i}句"}]
        }
        with open(f"{tmp}/测试章/{name}", "w", encoding="utf-8") as f:
            json.dump(node, f, ensure_ascii=False)

    result = load_chapter(f"{tmp}/测试章")
    assert result.nodes[0] == "1_first.json"
    assert result.nodes[1] == "2_second.json"
    assert result.lines[0]["index"] == 1
    assert result.lines[1]["index"] == 2
    assert result.category == "side"


def test_split_chapter_single_batch():
    """小章不拆分"""
    cd = ChapterDialogue(chapter="小章", category="main", nodes=["a.json"], lines=[
        {"index": 1, "speaker": "A", "type": "dialogue", "text": "短对话", "_node_file": "a.json"}
    ])
    batches = split_chapter(cd)
    assert len(batches) == 1
    assert batches[0] is cd


def test_split_chapter_two_batches():
    """超长章切成 2 批"""
    lines = []
    nodes = []
    for ni in range(100):
        nname = f"{ni:03d}_node.json"
        nodes.append(nname)
        for li in range(200):
            lines.append({
                "index": len(lines) + 1,
                "speaker": f"角色{ni}",
                "type": "dialogue",
                "text": "长文本。" * 20,
                "_node_file": nname,
            })

    cd = ChapterDialogue(chapter="超大章", category="main", nodes=nodes, lines=lines)
    assert cd.token_estimate > 128000

    batches = split_chapter(cd)
    assert len(batches) == 2
    assert "批次 1/2" in batches[0].chapter
    assert "批次 2/2" in batches[1].chapter
    assert len(batches[0].lines) + len(batches[1].lines) == len(lines)
