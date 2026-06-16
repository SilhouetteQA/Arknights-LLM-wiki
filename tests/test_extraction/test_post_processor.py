# tests/test_extraction/test_post_processor.py
"""post_processor 模块测试：角色名对齐 + 事件去重 + 分批合并 + 合法性校验"""
from arknights_wiki.extraction.post_processor import (
    align_character_names,
    deduplicate_events,
    merge_batches,
    validate_extraction,
    load_identity_map,
    normalize_character_type,
)


# ─── 角色类型标准化 ───

def test_normalize_character_type_infer_from_identity_map():
    """identity_map 中存在的角色应被修正为 operator 类型"""
    id_map = {"耀骑士临光": "character:KZ01", "W": "character:B00W"}
    assert normalize_character_type({"name": "耀骑士临光", "type": "npc"}, id_map) == "operator"
    assert normalize_character_type({"name": "塔露拉", "type": "npc"}, id_map) == "npc"
    assert normalize_character_type({"name": "阿米娅", "type": "operator"}, id_map) == "operator"


# ─── 角色名对齐 ───

def test_align_character_names_exact_match():
    """精确匹配：角色名已在 operators 列表中"""
    operators = [{"name_zh": "阿米娅"}, {"name_zh": "凯尔希"}]
    chars = [
        {"name": "阿米娅", "type": "operator", "role_in_chapter": "..."},
        {"name": "Amiya", "type": "operator", "role_in_chapter": "..."},
    ]
    result, unmatched = align_character_names(chars, operators, {})
    assert result[0]["name"] == "阿米娅"
    assert result[1]["name"] == "Amiya"
    assert len(unmatched) == 1


def test_align_character_names_identity_map_match():
    """identity_map 匹配：别名映射到规范 entity_id"""
    operators = [{"name_zh": "阿米娅"}, {"name_zh": "凯尔希"}]
    id_map = {"Guard": "character:R001"}
    chars = [
        {"name": "Guard", "type": "operator", "role_in_chapter": "..."},
    ]
    result, _ = align_character_names(chars, operators, id_map)
    assert result[0]["name"] == "Guard"
    assert result[0]["type"] == "operator"


def test_align_character_names_fuzzy_match():
    """模糊匹配：相似度 >= 0.85 时修正为规范名"""
    operators = [{"name_zh": "阿米娅"}, {"name_zh": "陈晖洁"}]
    chars = [
        {"name": "阿米亚", "type": "operator", "role_in_chapter": "..."},
        {"name": "陈辉洁", "type": "operator", "role_in_chapter": "..."},
    ]
    result, _ = align_character_names(chars, operators, {})
    assert result[0]["name"] == "阿米娅"
    assert result[1]["name"] == "陈晖洁"


# ─── 事件去重 ───

def test_deduplicate_events_merge_similar():
    """相似事件合并，保留描述更详细的版本"""
    events = [
        {"event": "Logos断后对抗孽茨雷", "type": "battle", "line_range": [1, 5]},
        {"event": "Logos独自断后抵挡孽茨雷", "type": "battle", "line_range": [3, 8]},
        {"event": "阿米娅召集小队", "type": "planning", "line_range": [10, 15]},
    ]
    result = deduplicate_events(events)
    assert len(result) <= 3
    events_texts = [e["event"] for e in result]
    assert "阿米娅召集小队" in events_texts


def test_deduplicate_events_empty():
    """空列表直接返回空"""
    assert deduplicate_events([]) == []


def test_deduplicate_events_single():
    """单事件直接返回单元素列表"""
    events = [{"event": "唯一事件", "type": "battle", "line_range": [1, 5]}]
    result = deduplicate_events(events)
    assert len(result) == 1


# ─── 分批合并 ───

def test_merge_batches_single():
    """单批次合并等效于原批次"""
    batch = {
        "chapter": "测试章", "category": "main",
        "summary": "摘要",
        "events": [{"event": "事件A", "type": "battle", "line_range": [1, 10]}],
        "characters": [{"name": "阿米娅", "type": "operator", "role_in_chapter": "...", "first_appearance_chapter": True}],
        "concepts": [{"concept": "源石", "line_range": [5, 15], "discussion_summary": "...", "is_substantive": True}],
    }
    merged = merge_batches([batch], chapter="测试章")
    assert merged["batch_count"] == 1
    assert len(merged["events"]) == 1


def test_merge_batches_two():
    """两批次合并：events 排序去重，characters 同名合并，concepts 合并 range"""
    batch1 = {
        "chapter": "测试章 (批次 1/2)", "category": "main",
        "summary": "第一部分",
        "events": [
            {"event": "事件A", "type": "battle", "line_range": [1, 10]},
            {"event": "事件B", "type": "meeting", "line_range": [11, 20]},
        ],
        "characters": [
            {"name": "阿米娅", "type": "operator", "role_in_chapter": "...", "first_appearance_chapter": True},
        ],
        "concepts": [
            {"concept": "源石", "line_range": [5, 15], "discussion_summary": "...", "is_substantive": True},
        ],
    }
    batch2 = {
        "chapter": "测试章 (批次 2/2)", "category": "main",
        "summary": "第二部分",
        "events": [
            {"event": "事件C", "type": "battle", "line_range": [21, 30]},
        ],
        "characters": [
            {"name": "阿米娅", "type": "operator", "role_in_chapter": "...", "first_appearance_chapter": False},
            {"name": "凯尔希", "type": "operator", "role_in_chapter": "...", "first_appearance_chapter": True},
        ],
        "concepts": [],
    }
    merged = merge_batches([batch1, batch2], chapter="测试章")
    assert merged["chapter"] == "测试章"
    assert merged["batch_count"] == 2
    assert len(merged["events"]) == 3
    assert len(merged["characters"]) == 2  # 阿米娅 去重
    # 保留 True 的 first_appearance_chapter
    amiya = [c for c in merged["characters"] if c["name"] == "阿米娅"][0]
    assert amiya["first_appearance_chapter"] is True


# ─── 合法性校验 ───

def test_validate_extraction_valid():
    """合法数据无错误"""
    data = {
        "chapter": "测试", "category": "main",
        "events": [{"event": "测试事件", "type": "battle", "line_range": [1, 5]}],
    }
    errors = validate_extraction(data, total_lines=10)
    assert len(errors) == 0


def test_validate_extraction_missing_events():
    """缺少 events 数组时报错"""
    errors = validate_extraction({"chapter": "测试", "category": "main", "events": []}, total_lines=10)
    assert any("events" in e for e in errors)


def test_validate_extraction_line_range_out_of_bounds():
    """line_range 超出章节总行数时报错"""
    data = {
        "chapter": "测试", "category": "main",
        "events": [{"event": "测试", "type": "battle", "line_range": [1, 999]}],
    }
    errors = validate_extraction(data, total_lines=10)
    assert any("999" in e or "超出" in e for e in errors)
