# tests/test_extraction/test_character_aggregator.py
"""character_aggregator 模块测试：参与者规范化 + 数据收集 + 合并 + 过滤 + 上下文注入"""
import os
import json
import tempfile
import shutil
from arknights_wiki.extraction.character_aggregator import (
    normalize_participant,
    collect_from_v1,
    normalize_and_merge,
    filter_targets,
    parse_keep_list,
    _cut_lines,
    inject_context,
    get_operator_archive,
)
from arknights_wiki.extraction.dialogue_loader import ChapterDialogue


# ─── TestNormalizeParticipant ───

OP_NAMES = {"阿米娅", "凯尔希", "临光", "迷迭香", "陈", "博士"}
ID_MAP = {"玛嘉烈·临光": "临光", "玛莉娅·临光": "瑕光"}


def test_strips_question_mark_chinese():
    """中文问号去除"""
    assert normalize_participant("凯尔希？", OP_NAMES, ID_MAP) == "凯尔希"


def test_strips_question_mark_english():
    """英文问号去除"""
    assert normalize_participant("凯尔希?", OP_NAMES, ID_MAP) == "凯尔希"


def test_strips_brackets():
    """括号及括号内内容去除"""
    assert normalize_participant("凯尔希(幼年)", OP_NAMES, ID_MAP) == "凯尔希"


def test_strips_angle_quotes():
    """书名号去除"""
    result = normalize_participant("「陈」", OP_NAMES, ID_MAP)
    assert result == "陈"


def test_exact_operator_match():
    """精确匹配干员名"""
    assert normalize_participant("凯尔希", OP_NAMES, ID_MAP) == "凯尔希"


def test_identity_map_lookup():
    """identity_map 精确映射"""
    assert normalize_participant("玛嘉烈·临光", OP_NAMES, ID_MAP) == "临光"


def test_compound_name_split():
    """复合名 · 拆分后匹配"""
    assert normalize_participant("玛嘉烈·临光", OP_NAMES, {}) == "临光"


def test_fuzzy_match():
    """模糊匹配（SequenceMatcher >= 0.65）"""
    assert normalize_participant("迷迭", OP_NAMES, ID_MAP) == "迷迭香"


def test_unchanged_for_npc():
    """无匹配的 NPC 保持原名"""
    assert normalize_participant("Guard", OP_NAMES, ID_MAP) == "Guard"


def test_normalize_strips_whitespace():
    """去除首尾空白"""
    assert normalize_participant("  阿米娅  ", OP_NAMES, ID_MAP) == "阿米娅"


# ─── TestCollectFromV1 ───


def _make_v1_event_json(chapter, category, events):
    """构造 v1_events JSON 内容"""
    return {
        "chapter": chapter,
        "category": category,
        "events": events,
        "summary": "",
        "_parse_error": False,
    }


def test_collects_all_participants():
    """收集所有事件中的参与者"""
    tmpdir = tempfile.mkdtemp()
    try:
        for cat in ("main", "side", "special"):
            os.makedirs(os.path.join(tmpdir, cat), exist_ok=True)

        # 主线下两个章节
        ch1 = _make_v1_event_json("黑暗时代·上", "main", [
            {
                "event": "博士苏醒",
                "type": "revelation",
                "line_range": [1, 78],
                "participants": ["阿米娅", "医疗干员", "博士"],
                "significance": "",
                "is_imaginary": False,
            },
            {
                "event": "整合运动突袭",
                "type": "ambush",
                "line_range": [79, 124],
                "participants": ["阿米娅", "博士", "整合运动成员"],
                "significance": "",
                "is_imaginary": False,
            },
        ])
        ch2 = _make_v1_event_json("黑暗时代·下", "main", [
            {
                "event": "撤离",
                "type": "retreat",
                "line_range": [1, 50],
                "participants": ["阿米娅", "杜宾"],
                "significance": "",
                "is_imaginary": False,
            },
        ])
        with open(os.path.join(tmpdir, "main", "黑暗时代·上.json"), "w", encoding="utf-8") as f:
            json.dump(ch1, f, ensure_ascii=False)
        with open(os.path.join(tmpdir, "main", "黑暗时代·下.json"), "w", encoding="utf-8") as f:
            json.dump(ch2, f, ensure_ascii=False)

        result = collect_from_v1(tmpdir)

        assert "阿米娅" in result
        assert "医疗干员" in result
        assert "博士" in result
        assert "整合运动成员" in result
        assert "杜宾" in result
        # 阿米娅出现在2个章节
        assert result["阿米娅"]["chapters"] == {"黑暗时代·上", "黑暗时代·下"}
        assert len(result["阿米娅"]["events"]) == 3
    finally:
        shutil.rmtree(tmpdir)


def test_collects_from_parse_error_chapters():
    """含有 _parse_error 的 JSON 仍然收集其 events"""
    tmpdir = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmpdir, "main"), exist_ok=True)
        ch = _make_v1_event_json("测试章", "main", [
            {
                "event": "测试事件",
                "type": "battle",
                "line_range": [1, 10],
                "participants": ["阿米娅"],
                "significance": "",
                "is_imaginary": False,
            },
        ])
        ch["_parse_error"] = True
        with open(os.path.join(tmpdir, "main", "测试章.json"), "w", encoding="utf-8") as f:
            json.dump(ch, f, ensure_ascii=False)

        result = collect_from_v1(tmpdir)
        assert "阿米娅" in result
        assert len(result["阿米娅"]["events"]) == 1
    finally:
        shutil.rmtree(tmpdir)


def test_handles_empty_participants():
    """空 participants 列表不产生条目"""
    tmpdir = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmpdir, "main"), exist_ok=True)
        ch = _make_v1_event_json("空参与章", "main", [
            {
                "event": "无人事件",
                "type": "narration",
                "line_range": [1, 5],
                "participants": [],
                "significance": "",
                "is_imaginary": False,
            },
            {
                "event": "有人事件",
                "type": "battle",
                "line_range": [6, 10],
                "participants": ["阿米娅"],
                "significance": "",
                "is_imaginary": False,
            },
        ])
        with open(os.path.join(tmpdir, "main", "空参与章.json"), "w", encoding="utf-8") as f:
            json.dump(ch, f, ensure_ascii=False)

        result = collect_from_v1(tmpdir)
        # 空 participants 不应产生 key
        assert "" not in result
        assert "阿米娅" in result
    finally:
        shutil.rmtree(tmpdir)


def test_handles_missing_participants_key():
    """缺少 participants 字段的事件被跳过"""
    tmpdir = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmpdir, "main"), exist_ok=True)
        ch = _make_v1_event_json("缺字段章", "main", [
            {
                "event": "无参与字段",
                "type": "narration",
                "line_range": [1, 5],
                "significance": "",
                "is_imaginary": False,
            },
            {
                "event": "正常事件",
                "type": "battle",
                "line_range": [6, 10],
                "participants": ["凯尔希"],
                "significance": "",
                "is_imaginary": False,
            },
        ])
        with open(os.path.join(tmpdir, "main", "缺字段章.json"), "w", encoding="utf-8") as f:
            json.dump(ch, f, ensure_ascii=False)

        result = collect_from_v1(tmpdir)
        assert "凯尔希" in result
    finally:
        shutil.rmtree(tmpdir)


# ─── TestNormalizeAndMerge ───


def test_merges_same_character():
    """相同角色不同写法合并为一条"""
    raw_participants = {
        "陈晖洁": {
            "events": [
                {"event": "事件A", "type": "battle", "line_range": [1, 5],
                 "chapter": "章1", "category": "main", "pass1_index": 0,
                 "significance": "", "is_imaginary": False},
            ],
            "chapters": {"章1"},
        },
        "陈": {
            "events": [
                {"event": "事件B", "type": "planning", "line_range": [10, 15],
                 "chapter": "章2", "category": "side", "pass1_index": 0,
                 "significance": "", "is_imaginary": False},
            ],
            "chapters": {"章2"},
        },
    }
    operators = [{"name_zh": "陈", "id": "R001"}]
    id_map = {"陈晖洁": "陈"}

    result = normalize_and_merge(raw_participants, operators, id_map)

    assert "陈" in result
    assert len(result["陈"]["events"]) == 2
    assert result["陈"]["chapters"] == {"章1", "章2"}
    assert "陈晖洁" in result["陈"]["aliases"]


def test_keeps_unmapped_npc():
    """无匹配的 NPC 保持原名，aliases 为空"""
    raw_participants = {
        "Guard": {
            "events": [
                {"event": "守卫事件", "type": "battle", "line_range": [1, 5],
                 "chapter": "章1", "category": "main", "pass1_index": 0,
                 "significance": "", "is_imaginary": False},
            ],
            "chapters": {"章1"},
        },
    }
    operators = [{"name_zh": "阿米娅", "id": "R002"}]
    id_map = {}

    result = normalize_and_merge(raw_participants, operators, id_map)

    assert "Guard" in result
    assert len(result["Guard"]["events"]) == 1
    assert result["Guard"]["aliases"] == set()


# ─── TestFilterTargets ───


def _make_merged_entry(events, chapters, aliases=None):
    return {
        "events": events,
        "chapters": set(chapters),
        "aliases": aliases or set(),
    }


def test_keeps_operators():
    """干员始终保留"""
    operators = [
        {"name_zh": "阿米娅", "id": "R001"},
    ]
    merged = {
        "阿米娅": _make_merged_entry(
            [{"event": "e1", "type": "battle", "line_range": [1, 5],
              "chapter": "c1", "category": "main", "pass1_index": 0,
              "significance": "", "is_imaginary": False}],
            ["c1"],
        ),
    }
    result = filter_targets(merged, operators, keep_set=set())
    assert "阿米娅" in result


def test_keeps_multi_chapter_npc():
    """出场 >= 2 章的 NPC 保留"""
    operators = [{"name_zh": "阿米娅", "id": "R001"}]
    merged = {
        "Guard": _make_merged_entry(
            [{"event": "e1", "type": "battle", "line_range": [1, 5],
              "chapter": "c1", "category": "main", "pass1_index": 0,
              "significance": "", "is_imaginary": False},
             {"event": "e2", "type": "battle", "line_range": [1, 5],
              "chapter": "c2", "category": "side", "pass1_index": 0,
              "significance": "", "is_imaginary": False}],
            ["c1", "c2"],
        ),
    }
    result = filter_targets(merged, operators, keep_set=set())
    assert "Guard" in result


def test_drops_single_chapter_npc():
    """单章 NPC 且不在 KEEP 集合中被丢弃"""
    operators = [{"name_zh": "阿米娅", "id": "R001"}]
    merged = {
        "路人甲": _make_merged_entry(
            [{"event": "e1", "type": "battle", "line_range": [1, 5],
              "chapter": "c1", "category": "main", "pass1_index": 0,
              "significance": "", "is_imaginary": False}],
            ["c1"],
        ),
    }
    result = filter_targets(merged, operators, keep_set=set())
    assert "路人甲" not in result


def test_keeps_user_keep_single_chapter():
    """单章 NPC 但在 KEEP 集合中保留"""
    operators = [{"name_zh": "阿米娅", "id": "R001"}]
    merged = {
        "Rosmontis": _make_merged_entry(
            [{"event": "e1", "type": "battle", "line_range": [1, 5],
              "chapter": "c1", "category": "main", "pass1_index": 0,
              "significance": "", "is_imaginary": False}],
            ["c1"],
        ),
    }
    result = filter_targets(merged, operators, keep_set={"Rosmontis"})
    assert "Rosmontis" in result


# ─── TestParseKeepList ───


def test_parse_keep_list_extracts_keep():
    """从 markdown 表格中提取 [KEEP] 标记的角色"""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    try:
        md_path = os.path.join(tmpdir, "test_keep.md")
        content = """# Header

| # | 角色名 | 事件类型 | 事件描述 | 处理 |
|---|--------|----------|----------|------|
| 1 | Rosmontis | flashback | ... | [KEEP ] |
| 2 | 龙门市民 | battle | ... | [ ] |
| 3 | 伊斯拉姆·维特 | political | ... | [KEEP] |
| 4 | 路人 | battle | ... | [DROP] |
"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)

        result = parse_keep_list(md_path)
        assert "Rosmontis" in result
        assert "伊斯拉姆·维特" in result
        assert "龙门市民" not in result
        assert "路人" not in result
    finally:
        shutil.rmtree(tmpdir)


def test_parse_keep_list_empty_file():
    """空文件返回空集合"""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    try:
        md_path = os.path.join(tmpdir, "test_empty.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("")

        result = parse_keep_list(md_path)
        assert result == set()
    finally:
        shutil.rmtree(tmpdir)


# ─── TestCutLines ───


def _make_cd(lines_data):
    """构造测试用的 ChapterDialogue"""
    lines = [
        {"global_index": d[0], "speaker": d[1], "type": d[2], "text": d[3]}
        for d in lines_data
    ]
    return ChapterDialogue(chapter="test", category="main", nodes=[], lines=lines)


def test_cut_lines_includes_buffer():
    """buffer=1 时，范围 [2,4] 应包含 1-5 行"""
    cd = _make_cd([
        (1, "阿米娅", "dialogue", "你好"),
        (2, "博士", "dialogue", "这是测试"),
        (3, "凯尔希", "dialogue", "中间行"),
        (4, "阿米娅", "dialogue", "结束"),
        (5, "杜宾", "dialogue", "后续"),
    ])
    result = _cut_lines(cd, 2, 4, buffer=1)
    lines = result.strip().split("\n")
    # 应包含 5 行
    assert len(lines) == 5
    # 第一行应该是 index=1
    assert "[1]" in lines[0]
    # 最后一行应该是 index=5
    assert "[5]" in lines[-1]


def test_cut_lines_clamps_to_bounds():
    """buffer 超出范围时裁剪到边界"""
    cd = _make_cd([
        (1, "阿米娅", "dialogue", "第一行"),
        (2, "博士", "dialogue", "第二行"),
    ])
    result = _cut_lines(cd, 1, 2, buffer=5)
    lines = result.strip().split("\n")
    # 总共只有 2 行
    assert len(lines) == 2


def test_cut_lines_format():
    """检查输出格式 [global_index] [speaker] text"""
    cd = _make_cd([
        (1, "阿米娅", "dialogue", "博士，醒醒"),
        (2, "博士", "dialogue", "这里是..."),
    ])
    result = _cut_lines(cd, 1, 2, buffer=0)
    lines = result.strip().split("\n")
    assert lines[0] == "[1] [阿米娅] 博士，醒醒"
    assert lines[1] == "[2] [博士] 这里是..."


def test_cut_lines_narration_no_speaker():
    """旁白类型无发言人，只输出 index 和 text"""
    cd = _make_cd([
        (1, "", "narration", "切尔诺伯格陷入一片火海"),
    ])
    result = _cut_lines(cd, 1, 1, buffer=0)
    assert result.strip() == "[1] 切尔诺伯格陷入一片火海"


# ─── TestInjectContext ───


def test_inject_context_adds_context():
    """inject_context 为每个事件添加原文"""
    # 这里我们不实际加载文件，而是测试 _cut_lines 的集成
    # inject_context 依赖文件系统，这里做轻量验证
    # 直接测试它接受 targets 并返回（不实际加载 data/stories）
    targets = {}
    result = inject_context(targets, data_dir="data/stories")
    assert result == {}


# ─── TestGetOperatorArchive ───


def test_finds_operator():
    """精确匹配找到干员完整信息（含顶层字段 race/nation/team/group）"""
    operators = [
        {"name_zh": "阿米娅", "id": "R001", "race": "卡特斯", "nation": "罗德岛",
         "archives": {"基础档案": "test"}},
        {"name_zh": "凯尔希", "id": "R002", "race": "未知", "nation": "罗德岛",
         "archives": {"基础档案": "test2"}},
    ]
    result = get_operator_archive("阿米娅", operators)
    assert result is not None
    assert result["name_zh"] == "阿米娅"
    assert result["race"] == "卡特斯"
    assert result["nation"] == "罗德岛"
    assert result["archives"]["基础档案"] == "test"


def test_returns_none_for_unknown():
    """未找到返回 None"""
    operators = [{"name_zh": "阿米娅", "id": "R001", "archives": {"基础档案": "test"}}]
    result = get_operator_archive("未知角色", operators)
    assert result is None
