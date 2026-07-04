# Pass 2 角色 Wiki 页面生成 — 实施计划

> **状态**: 已完成
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ~658 个角色生成结构化 Wiki 档案，基于 Pass 1 事件聚合 + 原文上下文 + 干员档案

**Architecture:** 新增 character_aggregator.py（角色聚合+规范化），扩展 prompt_builder.py/orchestrator.py/post_processor.py 三个现有模块。每个角色一次独立 LLM 调用，输入为聚合后的全量事件+原文，输出为 JSON 角色档案。

**Tech Stack:** Python 3.12+, DeepSeek chat API, json-repair, pytest

> **状态**: 已完成

---

## 文件规划

| 文件 | 职责 | 操作 |
|------|------|------|
| `arknights_wiki/extraction/character_aggregator.py` | 参与者收集、名称规范化、目标过滤、原文注入 | **新建** |
| `arknights_wiki/extraction/prompt_builder.py` | 新增角色系统提示词 + 用户提示词 | 扩展 |
| `arknights_wiki/extraction/post_processor.py` | 新增角色输出 JSON 校验 | 扩展 |
| `arknights_wiki/extraction/orchestrator.py` | 新增角色提取编排（单角色+全量） | 扩展 |
| `tests/test_extraction/test_character_aggregator.py` | 聚合器测试 | **新建** |

---

### Task 1: character_aggregator.py — 数据收集与角色聚合

**Files:**
- Create: `arknights_wiki/extraction/character_aggregator.py`
- Create: `tests/test_extraction/test_character_aggregator.py`

- [x] **Step 1: Write failing tests for normalize_participant**

```python
# tests/test_extraction/test_character_aggregator.py
import pytest
from arknights_wiki.extraction.character_aggregator import (
    normalize_participant,
    collect_from_v1,
    normalize_and_merge,
    filter_targets,
    inject_context,
    get_operator_archive,
    parse_keep_list,
    _cut_lines,
)


class TestNormalizeParticipant:
    def test_strips_question_mark(self):
        op_names = {"凯尔希", "阿米娅", "陈"}
        id_map = {}
        assert normalize_participant("凯尔希？", op_names, id_map) == "凯尔希"
        assert normalize_participant("凯尔希?", op_names, id_map) == "凯尔希"

    def test_strips_brackets(self):
        op_names = {"凯尔希"}
        id_map = {}
        assert normalize_participant("凯尔希(幼年)", op_names, id_map) == "凯尔希"

    def test_strips_angle_quotes(self):
        op_names = {"陈"}
        id_map = {}
        assert normalize_participant("「陈」", op_names, id_map) == "陈"

    def test_exact_operator_match(self):
        op_names = {"凯尔希", "阿米娅"}
        id_map = {}
        assert normalize_participant("凯尔希", op_names, id_map) == "凯尔希"
        assert normalize_participant("阿米娅", op_names, id_map) == "阿米娅"

    def test_identity_map_lookup(self):
        op_names = {"临光", "陈"}
        id_map = {"玛嘉烈·临光": "临光", "陈晖洁": "陈"}
        assert normalize_participant("玛嘉烈·临光", op_names, id_map) == "临光"
        assert normalize_participant("陈晖洁", op_names, id_map) == "陈"

    def test_compound_name_split(self):
        op_names = {"临光", "瑕光"}
        id_map = {}
        assert normalize_participant("玛嘉烈·临光", op_names, id_map) == "临光"
        assert normalize_participant("玛莉娅·临光", op_names, id_map) == "瑕光"

    def test_fuzzy_match(self):
        op_names = {"迷迭香", "凯尔希"}
        id_map = {}
        assert normalize_participant("Rosmontis", op_names, id_map) == "Rosmontis"  # 英文名不模糊
        assert normalize_participant("迷迭", op_names, id_map) == "迷迭香"  # 模糊匹配

    def test_unchanged_for_npc(self):
        op_names = {"凯尔希"}
        id_map = {}
        assert normalize_participant("Guard", op_names, id_map) == "Guard"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestNormalizeParticipant -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [x] **Step 3: Implement normalize_participant**

```python
# arknights_wiki/extraction/character_aggregator.py
"""角色聚合器：Pass 1 参与者收集 + 名称规范化 + 目标过滤 + 原文注入"""
import json
import os
import re
from difflib import SequenceMatcher

from .dialogue_loader import load_chapter, ChapterDialogue


def normalize_participant(name: str, op_names: set[str], id_map: dict[str, str]) -> str:
    """规范化参与者名称：去标点 -> identity_map -> 复合名拆分 -> 模糊匹配"""
    name = name.strip()
    name = name.rstrip("?？")
    name = name.replace("「", "").replace("」", "")
    name = re.sub(r"\([^)]*\)$", "", name).strip()
    if not name:
        return name

    if name in op_names:
        return name

    if name in id_map:
        canonical = id_map[name]
        return canonical if canonical in op_names else name

    if "·" in name:
        for part in name.split("·"):
            if part in id_map:
                canonical = id_map[part]
                return canonical if canonical in op_names else part
            if part in op_names:
                return part

    best_ratio = 0.0
    best_name = name
    for opn in op_names:
        if abs(len(name) - len(opn)) > 3:
            continue
        ratio = SequenceMatcher(None, name, opn).ratio()
        if ratio >= 0.65 and ratio > best_ratio:
            best_ratio = ratio
            best_name = opn
    if best_ratio >= 0.65:
        return best_name

    return name
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestNormalizeParticipant -v`
Expected: PASS all 7 tests

- [x] **Step 5: Write failing tests for collect_from_v1**

```python
# 添加到 test_character_aggregator.py 中
import json
import tempfile
import os


class TestCollectFromV1:
    def make_v1_dir(self, events_data: dict) -> str:
        """创建临时 v1_events 目录结构"""
        tmpdir = tempfile.mkdtemp()
        for category, chapters in events_data.items():
            cat_dir = os.path.join(tmpdir, category)
            os.makedirs(cat_dir, exist_ok=True)
            for ch_name, data in chapters.items():
                with open(os.path.join(cat_dir, f"{ch_name}.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
        return tmpdir

    def test_collects_all_participants(self):
        v1_data = {
            "main": {
                "黑暗时代·上": {
                    "events": [
                        {
                            "event": "阿米娅救出博士",
                            "participants": ["阿米娅", "博士", "杜宾"],
                            "line_range": [1, 50],
                        },
                        {
                            "event": "与整合运动交战",
                            "participants": ["阿米娅", "近卫干员"],
                            "line_range": [51, 100],
                        },
                    ]
                }
            }
        }
        tmpdir = self.make_v1_dir(v1_data)
        try:
            result = collect_from_v1(tmpdir)
            assert "阿米娅" in result
            assert "博士" in result
            assert "杜宾" in result
            assert "近卫干员" in result
            assert len(result["阿米娅"]["events"]) == 2
            assert result["阿米娅"]["chapters"] == {"黑暗时代·上"}
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skips_parse_error_events(self):
        v1_data = {
            "side": {
                "孤星": {
                    "events": [{"event": "test", "participants": ["塞雷娅"]}],
                    "_parse_error": True,
                }
            }
        }
        tmpdir = self.make_v1_dir(v1_data)
        try:
            result = collect_from_v1(tmpdir)
            # _parse_error 标记的章节仍收集事件（事件本身可能部分有效）
            assert "塞雷娅" in result
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_handles_empty_participants(self):
        v1_data = {
            "special": {
                "战地秘闻": {
                    "events": [
                        {"event": "test", "participants": []}
                    ]
                }
            }
        }
        tmpdir = self.make_v1_dir(v1_data)
        try:
            result = collect_from_v1(tmpdir)
            assert len(result) == 0
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
```

- [x] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestCollectFromV1 -v`
Expected: FAIL (collect_from_v1 not yet defined)

- [x] **Step 7: Implement collect_from_v1**

```python
# 添加到 character_aggregator.py


def collect_from_v1(v1_dir: str) -> dict[str, dict]:
    """扫描 Pass 1 提取结果，按参与者收集事件。

    返回: {participant_raw_name: {"events": [...], "chapters": set()}}
    """
    participants: dict[str, dict] = {}

    for category in ["main", "side", "special"]:
        cat_dir = os.path.join(v1_dir, category)
        if not os.path.isdir(cat_dir):
            continue
        for fname in sorted(os.listdir(cat_dir)):
            if not fname.endswith(".json"):
                continue
            chapter_name = fname[:-5]
            fpath = os.path.join(cat_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            for ei, event in enumerate(data.get("events", [])):
                for pname in event.get("participants", []):
                    pname = pname.strip()
                    if not pname:
                        continue
                    if pname not in participants:
                        participants[pname] = {"events": [], "chapters": set()}
                    participants[pname]["chapters"].add(chapter_name)
                    participants[pname]["events"].append({
                        "chapter": chapter_name,
                        "category": category,
                        "pass1_index": ei,
                        "event": event.get("event", ""),
                        "type": event.get("type", ""),
                        "line_range": event.get("line_range", []),
                        "significance": event.get("significance", ""),
                        "is_imaginary": event.get("is_imaginary", False),
                    })

    return participants
```

- [x] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestCollectFromV1 -v`
Expected: PASS all 3 tests

- [x] **Step 9: Write failing tests for normalize_and_merge**

```python
class TestNormalizeAndMerge:
    def test_merges_same_character(self):
        raw = {
            "陈晖洁": {
                "events": [{"chapter": "黑暗时代·上", "event": "test1"}],
                "chapters": {"黑暗时代·上"},
            },
            "陈": {
                "events": [{"chapter": "局部坏死", "event": "test2"}],
                "chapters": {"局部坏死"},
            },
        }
        operators = [
            {"name_zh": "陈"},
            {"name_zh": "阿米娅"},
        ]
        # "陈晖洁" -> identity_map -> "陈", "陈" -> exact match
        id_map = {"陈晖洁": "陈"}
        result = normalize_and_merge(raw, operators, id_map)
        assert "陈" in result
        assert len(result["陈"]["events"]) == 2
        assert result["陈"]["chapters"] == {"黑暗时代·上", "局部坏死"}
        assert "陈晖洁" in result["陈"]["aliases"]

    def test_keeps_unmapped_npc(self):
        raw = {
            "Guard": {
                "events": [{"chapter": "苦难摇篮", "event": "test"}],
                "chapters": {"苦难摇篮"},
            }
        }
        operators = [{"name_zh": "阿米娅"}]
        id_map = {}
        result = normalize_and_merge(raw, operators, id_map)
        assert "Guard" in result
        assert result["Guard"]["aliases"] == set()
```

- [x] **Step 10: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestNormalizeAndMerge -v`
Expected: FAIL (normalize_and_merge not yet defined)

- [x] **Step 11: Implement normalize_and_merge**

```python
def normalize_and_merge(
    raw_participants: dict[str, dict],
    operators: list[dict],
    id_map: dict[str, str],
) -> dict:
    """规范化参与者名字并合并同名条目。

    返回: {canonical_name: {"aliases": set(), "chapters": set(), "events": [...]}}
    """
    op_names = {op["name_zh"] for op in operators}
    merged: dict[str, dict] = {}

    for raw_name, data in raw_participants.items():
        canonical = normalize_participant(raw_name, op_names, id_map)

        if canonical not in merged:
            merged[canonical] = {"aliases": set(), "chapters": set(), "events": []}

        if raw_name != canonical:
            merged[canonical]["aliases"].add(raw_name)
        merged[canonical]["chapters"].update(data["chapters"])
        merged[canonical]["events"].extend(data["events"])

    return merged
```

- [x] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestNormalizeAndMerge -v`
Expected: PASS all 2 tests

- [x] **Step 13: Write failing tests for filter_targets and parse_keep_list**

```python
class TestFilterTargets:
    def test_keeps_operators(self):
        merged = {
            "阿米娅": {"chapters": {"黑暗时代·上"}, "events": [], "aliases": set()},
            "博士": {"chapters": {"黑暗时代·上"}, "events": [], "aliases": set()},
        }
        operators = [{"name_zh": "阿米娅"}, {"name_zh": "博士"}]
        result = filter_targets(merged, operators, set())
        assert "阿米娅" in result
        assert "博士" in result

    def test_keeps_multi_chapter_npc(self):
        merged = {
            "Guard": {"chapters": {"苦难摇篮", "局部坏死"}, "events": [], "aliases": set()},
        }
        operators = []
        result = filter_targets(merged, operators, set())
        assert "Guard" in result

    def test_drops_single_chapter_npc(self):
        merged = {
            "路人甲": {"chapters": {"黑暗时代·上"}, "events": [], "aliases": set()},
        }
        operators = []
        result = filter_targets(merged, operators, set())
        assert "路人甲" not in result

    def test_keeps_user_keep_single_chapter(self):
        merged = {
            "白垩": {"chapters": {"尘影余音"}, "events": [], "aliases": set()},
        }
        operators = []
        keep_set = {"白垩"}
        result = filter_targets(merged, operators, keep_set)
        assert "白垩" in result


class TestParseKeepList:
    def test_parses_keep_marks(self, tmp_path):
        md_content = """# Pass 1 单次出场NPC清单
| # | 角色名 | 事件描述 | 处理 |
|---|--------|----------|------|
| 1 | 白垩 | 关键角色 | [KEEP ] |
| 2 | 路人甲 | 泛称 | [ ] |
| 3 | 奥达 | 巴别塔 NPC | [KEEP ] |
"""
        md_path = tmp_path / "test_keep.md"
        md_path.write_text(md_content, encoding="utf-8")
        result = parse_keep_list(str(md_path))
        assert "白垩" in result
        assert "奥达" in result
        assert "路人甲" not in result
        assert len(result) == 2
```

- [x] **Step 14: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestFilterTargets -v && pytest tests/test_extraction/test_character_aggregator.py::TestParseKeepList -v`
Expected: FAIL

- [x] **Step 15: Implement filter_targets and parse_keep_list**

```python
def filter_targets(
    merged: dict,
    operators: list[dict],
    keep_set: set[str],
) -> dict:
    """过滤目标角色：干员 + 出场>=2章的NPC + 用户KEEP"""
    op_names = {op["name_zh"] for op in operators}
    targets = {}

    for name, data in merged.items():
        if name in op_names:
            targets[name] = data
        elif len(data["chapters"]) >= 2:
            targets[name] = data
        elif name in keep_set:
            targets[name] = data

    return targets


def parse_keep_list(md_path: str) -> set[str]:
    """解析单次出场NPC标注文件，提取 [KEEP] 标记的角色名"""
    keep = set()
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            for line in f:
                if "[KEEP" in line:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        name = parts[2].strip()
                        if name:
                            keep.add(name)
    except FileNotFoundError:
        pass
    return keep
```

- [x] **Step 16: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestFilterTargets tests/test_extraction/test_character_aggregator.py::TestParseKeepList -v`
Expected: PASS all 5 tests

- [x] **Step 17: Write failing tests for context injection**

```python
class TestInjectContext:
    def make_cd(self, lines_data: list[dict]) -> ChapterDialogue:
        """构造测试用 ChapterDialogue"""
        from arknights_wiki.extraction.dialogue_loader import ChapterDialogue
        cd = ChapterDialogue(chapter="test", category="main")
        cd.nodes = ["node1.json"]
        for i, ld in enumerate(lines_data):
            cd.lines.append({
                "global_index": i + 1,
                "speaker": ld.get("speaker", ""),
                "type": ld.get("type", "dialogue"),
                "text": ld.get("text", ""),
                "_node_file": "node1.json",
            })
        return cd

    def test_cut_lines_includes_buffer(self):
        cd = self.make_cd([
            {"speaker": "A", "text": "line 1"},
            {"speaker": "B", "text": "line 2"},
            {"speaker": "A", "text": "line 3"},
            {"speaker": "C", "text": "line 4"},
            {"speaker": "D", "text": "line 5"},
        ])
        result = _cut_lines(cd, 2, 4, buffer=1)
        assert "line 1" in result   # buffer before
        assert "line 2" in result   # range start
        assert "line 4" in result   # range end
        assert "line 5" in result   # buffer after

    def test_cut_lines_clamps_to_bounds(self):
        cd = self.make_cd([
            {"speaker": "A", "text": "line 1"},
            {"speaker": "B", "text": "line 2"},
        ])
        result = _cut_lines(cd, 1, 2, buffer=5)
        assert "line 1" in result
        assert "line 2" in result


class TestGetOperatorArchive:
    def test_finds_operator(self):
        operators = [
            {"name_zh": "阿米娅", "race": "卡特斯", "nation": "罗德岛"},
            {"name_zh": "凯尔希", "race": "未知", "nation": "罗德岛"},
        ]
        result = get_operator_archive("阿米娅", operators)
        assert result is not None
        assert result["race"] == "卡特斯"

    def test_returns_none_for_unknown(self):
        operators = [{"name_zh": "阿米娅"}]
        result = get_operator_archive("Guard", operators)
        assert result is None
```

- [x] **Step 18: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_character_aggregator.py::TestInjectContext tests/test_extraction/test_character_aggregator.py::TestGetOperatorArchive -v`
Expected: FAIL

- [x] **Step 19: Implement _cut_lines, inject_context, get_operator_archive**

```python
def _cut_lines(cd: ChapterDialogue, start: int, end: int, buffer: int = 3) -> str:
    """从 ChapterDialogue 中截取指定行范围 + 前后各 buffer 行"""
    buf_start = max(1, start - buffer)
    buf_end = end + buffer

    lines = []
    for line in cd.lines:
        gi = line["global_index"]
        if buf_start <= gi <= buf_end:
            if line["type"] == "dialogue" and line["speaker"]:
                lines.append(f"[{gi}] [{line['speaker']}] {line['text']}")
            else:
                lines.append(f"[{gi}] {line['text']}")

    return "\n".join(lines)


def inject_context(targets: dict, data_dir: str = "data/stories") -> dict:
    """为每个目标角色的事件注入对应原文。

    加载章节对话并缓存，按 line_range 截取原文 + 前后3行缓冲。
    """
    needed_chapters: set[tuple[str, str]] = set()
    for data in targets.values():
        for ev in data["events"]:
            needed_chapters.add((ev["category"], ev["chapter"]))

    chapter_cache: dict[str, ChapterDialogue] = {}
    for category, chapter in needed_chapters:
        chapter_dir = os.path.join(data_dir, category, chapter)
        try:
            chapter_cache[chapter] = load_chapter(chapter_dir)
        except Exception:
            continue

    for name, data in targets.items():
        for ev in data["events"]:
            cd = chapter_cache.get(ev["chapter"])
            if cd is None:
                ev["context_text"] = ""
                continue
            lr = ev.get("line_range", [])
            if not isinstance(lr, list) or len(lr) != 2 or lr[0] <= 0:
                ev["context_text"] = ""
                continue
            ev["context_text"] = _cut_lines(cd, lr[0], lr[1], buffer=3)

    return targets


def get_operator_archive(name_zh: str, operators: list[dict]) -> dict | None:
    """获取干员档案信息"""
    for op in operators:
        if op["name_zh"] == name_zh:
            return op
    return None
```

- [x] **Step 20: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_character_aggregator.py -v`
Expected: PASS all tests

- [x] **Step 21: Commit**

```bash
git add arknights_wiki/extraction/character_aggregator.py tests/test_extraction/test_character_aggregator.py
git commit -m "feat: add character_aggregator — participant collection, name normalization, filtering, context injection"
```

---

### Task 2: prompt_builder.py — 角色 Wiki 提示词

**Files:**
- Modify: `arknights_wiki/extraction/prompt_builder.py`

- [x] **Step 1: Write failing tests for character prompt functions**

```python
# 添加到 tests/test_extraction/test_prompt_builder.py 中
import json
from arknights_wiki.extraction.prompt_builder import (
    build_system_prompt,
    build_user_prompt,
    build_character_system_prompt,
    build_character_user_prompt,
    get_summary_word_limit,
)


class TestCharacterSystemPrompt:
    def test_contains_key_rules(self):
        prompt = build_character_system_prompt()
        assert "角色档案编纂者" in prompt
        assert "summary" in prompt
        assert "power_level" in prompt
        assert "participated_events" in prompt
        assert "JSON" in prompt
        assert "markdown" in prompt
        assert "编造" in prompt
        assert "信息不足" in prompt

    def test_mentions_power_level_system(self):
        prompt = build_character_system_prompt()
        assert "战场中坚" in prompt
        assert "灭世灾厄" in prompt
        assert "信息不足" in prompt


class TestCharacterUserPrompt:
    def test_includes_character_name(self):
        prompt = build_character_user_prompt(
            name_zh="阿米娅",
            chapter_count=32,
            events_with_context=[],
            operator_archive=None,
        )
        assert "阿米娅" in prompt
        assert "32" in prompt

    def test_includes_operator_archive_when_present(self):
        archive = {
            "name_zh": "阿米娅",
            "race": "卡特斯",
            "nation": "罗德岛",
            "team": "行动组A4",
            "group": "",
            "archives": {
                "基础档案": "代号阿米娅...",
                "客观履历": "罗德岛的公开领袖...",
            },
        }
        prompt = build_character_user_prompt(
            name_zh="阿米娅",
            chapter_count=32,
            events_with_context=[],
            operator_archive=archive,
        )
        assert "卡特斯" in prompt
        assert "罗德岛" in prompt
        assert "基础档案" in prompt

    def test_includes_events_with_context(self):
        events = [
            {
                "chapter": "黑暗时代·上",
                "event": "阿米娅救出博士",
                "context_text": "[1] [阿米娅] 博士！\n[2] [博士] 嗯。",
                "line_range": [1, 2],
                "significance": "关键救援",
                "is_imaginary": False,
            }
        ]
        prompt = build_character_user_prompt(
            name_zh="阿米娅",
            chapter_count=1,
            events_with_context=events,
            operator_archive=None,
        )
        assert "黑暗时代·上" in prompt
        assert "阿米娅救出博士" in prompt
        assert "[1] [阿米娅] 博士！" in prompt
        assert "IS-IF线" not in prompt  # 非IS事件不标注

    def test_marks_imaginary_events(self):
        events = [
            {
                "chapter": "萨卡兹的无终奇语",
                "event": "IF事件",
                "context_text": "[1] test",
                "line_range": [1, 1],
                "significance": "",
                "is_imaginary": True,
            }
        ]
        prompt = build_character_user_prompt(
            name_zh="阿米娅",
            chapter_count=1,
            events_with_context=events,
            operator_archive=None,
        )
        assert "IS-IF线" in prompt

    def test_includes_summary_limit(self):
        prompt = build_character_user_prompt(
            name_zh="阿米娅",
            chapter_count=32,
            events_with_context=[],
            operator_archive=None,
        )
        assert "500" in prompt  # >=20章 → 500字


class TestGetSummaryWordLimit:
    def test_limits_by_chapter_count(self):
        assert get_summary_word_limit(40) == 500
        assert get_summary_word_limit(20) == 500
        assert get_summary_word_limit(15) == 350
        assert get_summary_word_limit(10) == 350
        assert get_summary_word_limit(7) == 250
        assert get_summary_word_limit(5) == 250
        assert get_summary_word_limit(3) == 150
        assert get_summary_word_limit(2) == 150
        assert get_summary_word_limit(1) == 100
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_prompt_builder.py -v -k "Character or Summary"`
Expected: FAIL (functions not defined)

- [x] **Step 3: Implement character prompt functions in prompt_builder.py**

```python
# 添加到 prompt_builder.py 末尾（在 build_user_prompt 函数之后）


def get_summary_word_limit(chapter_count: int) -> int:
    """按出场章数返回 summary 最大字数"""
    if chapter_count >= 20:
        return 500
    elif chapter_count >= 10:
        return 350
    elif chapter_count >= 5:
        return 250
    elif chapter_count >= 2:
        return 150
    else:
        return 100


CHARACTER_SYSTEM_PROMPT = """你是一个《明日方舟》角色档案编纂者。你的任务是基于该角色在所有章节中的出场事件和对话原文，撰写一份结构化的角色 Wiki 档案。

严格遵守以下规则：

1. **输出格式**：严格输出 JSON，不要包含 ```json 等 markdown 标记。<EXTREMELY_IMPORTANT>JSON 字符串值内禁止使用英文双引号 \"，用「」代替。</EXTREMELY_IMPORTANT>

2. **summary（核心字段）**：对该角色性格全貌、能力定位、剧情弧线、关键转变的综合判断和跨章总结。必须基于提供的对话原文，不编造原文中没有的信息。根据出场章数有最大字数上限。

3. **participated_events**：只保留有意义的大型事件。琐碎对话（闲聊/问候/转场）不列入。同一战役/冲突的多个阶段合并为一个条目。不使用 line_range，改用 chapter + nodes 定位。

4. **power_level**：按九级体系保守评估。综合干员档案、参与事件表现、概念提及内容判断。不确定时标注「信息不足」。

5. **personality.traits**：2-5 个简短标签，如「冷静」「果断」「温柔」等。

6. **abilities.description**：一句话概括（源石技艺/战斗方式/特殊技能），不展开细项。

7. **archive**：仅干员填充，直接从提供的档案信息复制 race 和 affiliations，LLM 不重新生成。

战力分级体系参考：
| 等级 | 说明 |
|------|------|
| 战场中坚 | 标准作战人员，多数干员 |
| 军事精锐 | 精英战斗/军事人员 |
| 大国将军 | 国家级军事领袖 |
| 传奇英雄 | 跨国家喻户晓的传奇强者 |
| 王庭之主 | 萨卡兹王庭级存在 |
| 神明碎片 | 神明/巨兽的碎片或化身 |
| 崛起之物 | 正在觉醒/崛起的超凡存在 |
| 文明之敌 | 威胁文明级别的存在 |
| 灭世灾厄 | 灭世级别的终极威胁 |

每级有四个子级：下位 / 标准 / 上位 / 顶尖。格式如「战场中坚·标准」。
"""


def build_character_system_prompt() -> str:
    return CHARACTER_SYSTEM_PROMPT


CHARACTER_OUTPUT_SCHEMA = """```json
{
  "summary": "跨章角色总结：性格全貌 + 能力定位 + 剧情弧线 + 关键转变。根据出场章数有最大字数限制。",
  "personality": {
    "traits": ["标签1", "标签2"],
    "description": "1-2句性格具体描述"
  },
  "abilities": {
    "description": "一句话能力概括",
    "power_level": "战场中坚·标准 或 信息不足"
  },
  "participated_events": [
    {
      "chapter": "章节名",
      "nodes": "大致节点或阶段描述",
      "event": "LLM识别的大型事件概述（同场战役多阶段合并）",
      "role": "角色在此事件中的作用和表现"
    }
  ],
  "first_appearance": "首次出场章节名",
  "appearance_count": 15
}
```"""


def build_character_user_prompt(
    name_zh: str,
    chapter_count: int,
    events_with_context: list[dict],
    operator_archive: dict | None = None,
) -> str:
    """构建角色提取 user prompt。

    Args:
        name_zh: 角色规范中文名
        chapter_count: 出场章数
        events_with_context: [{"chapter", "event", "context_text", "line_range", "significance", "is_imaginary"}, ...]
        operator_archive: 干员档案 dict（非干员为 None）
    """
    limit = get_summary_word_limit(chapter_count)
    parts = [
        f"## 角色名: {name_zh}",
        f"出场章节数: {chapter_count}",
        f"summary 最大字数: {limit} 字",
        "",
    ]

    # 干员档案
    if operator_archive:
        archive_info = operator_archive
        parts.append("## 干员档案（官方资料）")
        race = archive_info.get("race", "")
        nation = archive_info.get("nation", "")
        team = archive_info.get("team", "")
        group = archive_info.get("group", "")
        parts.append(f"种族: {race}")
        affiliations = [a for a in [nation, team, group] if a]
        parts.append(f"所属: {' / '.join(affiliations) if affiliations else '未知'}")
        parts.append("")

        archives = archive_info.get("archives", {})
        for key in ["基础档案", "综合体检测试", "客观履历", "临床诊断分析",
                     "档案资料一", "档案资料二", "档案资料三", "档案资料四",
                     "综合性能检测结果"]:
            if key in archives and archives[key]:
                parts.append(f"### {key}")
                parts.append(archives[key])
                parts.append("")
    else:
        parts.append("（非干员角色，无官方档案）")
        parts.append("")

    # 出场事件与原文
    if events_with_context:
        parts.append("## 出场事件与原文对话")
        parts.append("")

        # 按章节分组
        chapter_groups: dict[str, list] = {}
        for ev in events_with_context:
            ch = ev["chapter"]
            if ch not in chapter_groups:
                chapter_groups[ch] = []
            chapter_groups[ch].append(ev)

        event_num = 1
        for ch_name, ch_events in chapter_groups.items():
            parts.append(f"### {ch_name}")
            parts.append("")
            for ev in ch_events:
                imaginary_tag = " [IS-IF线]" if ev.get("is_imaginary") else ""
                parts.append(f"**事件 #{event_num}: {ev['event']}**{imaginary_tag}")
                lr = ev.get("line_range", [])
                parts.append(f"原文行号: {lr}")
                if ev.get("significance"):
                    parts.append(f"剧情意义: {ev['significance']}")
                if ev.get("context_text"):
                    parts.append("原文:")
                    parts.append(ev["context_text"])
                parts.append("")
                event_num += 1

    parts.append("## 输出 JSON 格式")
    parts.append(CHARACTER_OUTPUT_SCHEMA)
    parts.append("")
    parts.append("## 规则")
    parts.append("- 必须基于提供的对话原文，不编造原文中没有的信息")
    parts.append("- summary 是核心产出，覆盖性格全貌 + 能力定位 + 剧情弧线 + 关键转变")
    parts.append("- 琐碎对话（闲聊/问候/转场）不列入 participated_events，但其蕴含的角色信息需吸收到 summary")
    parts.append("- participated_events 合并同一战役/冲突的多个阶段为一个条目")
    parts.append("- power_level 按九级体系保守评估，不确定标注「信息不足」")
    parts.append("- personality.traits 为 2-5 个简短标签")
    parts.append("- 干员的 archive 字段直接复制提供的档案信息（race/affiliations）")

    return "\n".join(parts)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_prompt_builder.py -v -k "Character or Summary"`
Expected: PASS all 8 tests

- [x] **Step 5: Verify existing tests still pass**

Run: `pytest tests/test_extraction/test_prompt_builder.py -v`
Expected: ALL pass (existing + new)

- [x] **Step 6: Commit**

```bash
git add arknights_wiki/extraction/prompt_builder.py tests/test_extraction/test_prompt_builder.py
git commit -m "feat: add character wiki prompts to prompt_builder — system prompt, user prompt, summary word limit"
```

---

### Task 3: post_processor.py — 角色输出校验

**Files:**
- Modify: `arknights_wiki/extraction/post_processor.py`
- Modify: `tests/test_extraction/test_post_processor.py`

- [x] **Step 1: Write failing tests for character output validation**

```python
# 添加到 tests/test_extraction/test_post_processor.py 中
import pytest
from arknights_wiki.extraction.post_processor import validate_character_output


class TestValidateCharacterOutput:
    def test_valid_output_passes(self):
        data = {
            "summary": "阿米娅是罗德岛的公开领袖，性格坚定而温柔。作为卡特斯少女，她继承了魔王的力量...",
            "personality": {
                "traits": ["坚定", "温柔", "果断"],
                "description": "外表柔弱但内心极其坚韧的少女领袖"
            },
            "abilities": {
                "description": "源石技艺适应性卓越，能使用精神系和破坏系多种法术",
                "power_level": "传奇英雄·标准"
            },
            "participated_events": [
                {
                    "chapter": "黑暗时代·上",
                    "nodes": "切尔诺伯格营救",
                    "event": "阿米娅带领罗德岛小队深入切尔诺伯格营救博士",
                    "role": "营救行动的核心指挥和执行者"
                }
            ],
            "first_appearance": "黑暗时代·上",
            "appearance_count": 32,
        }
        errors = validate_character_output(data, "阿米娅")
        assert len(errors) == 0

    def test_missing_required_field(self):
        data = {"summary": "test"}
        errors = validate_character_output(data, "test")
        assert any("personality" in e for e in errors)

    def test_empty_participated_events(self):
        data = {
            "summary": "test",
            "personality": {"traits": ["未知"], "description": "未知"},
            "abilities": {"description": "未知", "power_level": "信息不足"},
            "participated_events": [],
            "first_appearance": "",
            "appearance_count": 0,
        }
        errors = validate_character_output(data, "test")
        # 空 participated_events 不报错（单章角色可能无大事件）
        assert len([e for e in errors if "participated_events" in e]) == 0

    def test_invalid_power_level_format(self):
        data = {
            "summary": "test",
            "personality": {"traits": ["未知"], "description": "未知"},
            "abilities": {"description": "未知", "power_level": "超级无敌"},
            "participated_events": [],
            "first_appearance": "",
            "appearance_count": 0,
        }
        errors = validate_character_output(data, "test")
        assert any("power_level" in e for e in errors)

    def test_valid_power_level_formats(self):
        valid_levels = [
            "战场中坚·下位", "战场中坚·标准", "战场中坚·上位", "战场中坚·顶尖",
            "军事精锐·标准", "大国将军·上位", "传奇英雄·顶尖",
            "王庭之主·标准", "神明碎片·下位", "崛起之物·上位",
            "文明之敌·标准", "灭世灾厄",
            "信息不足",
        ]
        for level in valid_levels:
            data = {
                "summary": "test",
                "personality": {"traits": ["x"], "description": "x"},
                "abilities": {"description": "x", "power_level": level},
                "participated_events": [],
                "first_appearance": "",
                "appearance_count": 0,
            }
            errors = validate_character_output(data, "test")
            assert not any("power_level" in e for e in errors), f"Failed for {level}: {errors}"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_post_processor.py -v -k "ValidateCharacter"`
Expected: FAIL (validate_character_output not defined)

- [x] **Step 3: Implement validate_character_output in post_processor.py**

```python
# 添加到 post_processor.py 末尾

VALID_POWER_LEVELS = {
    "战场中坚·下位", "战场中坚·标准", "战场中坚·上位", "战场中坚·顶尖",
    "军事精锐·下位", "军事精锐·标准", "军事精锐·上位", "军事精锐·顶尖",
    "大国将军·下位", "大国将军·标准", "大国将军·上位", "大国将军·顶尖",
    "传奇英雄·下位", "传奇英雄·标准", "传奇英雄·上位", "传奇英雄·顶尖",
    "王庭之主·下位", "王庭之主·标准", "王庭之主·上位", "王庭之主·顶尖",
    "神明碎片·下位", "神明碎片·标准", "神明碎片·上位", "神明碎片·顶尖",
    "崛起之物·下位", "崛起之物·标准", "崛起之物·上位", "崛起之物·顶尖",
    "文明之敌·下位", "文明之敌·标准", "文明之敌·上位", "文明之敌·顶尖",
    "灭世灾厄",
    "信息不足",
}


def validate_character_output(data: dict, name_zh: str) -> list[str]:
    """校验角色 Wiki 输出 JSON 的完整性和格式"""
    errors: list[str] = []

    if not data.get("summary"):
        errors.append(f"summary 为空")

    personality = data.get("personality", {})
    if not isinstance(personality, dict):
        errors.append("personality 不是 dict")
    else:
        if not personality.get("traits"):
            errors.append("personality.traits 为空")
        if not personality.get("description"):
            errors.append("personality.description 为空")

    abilities = data.get("abilities", {})
    if not isinstance(abilities, dict):
        errors.append("abilities 不是 dict")
    else:
        power_level = abilities.get("power_level", "")
        if power_level not in VALID_POWER_LEVELS:
            errors.append(f"power_level 无效: '{power_level}'")

    events = data.get("participated_events", [])
    if not isinstance(events, list):
        errors.append("participated_events 不是 list")
    else:
        for i, ev in enumerate(events):
            if not ev.get("event"):
                errors.append(f"participated_events[{i}].event 为空")
            if not ev.get("chapter"):
                errors.append(f"participated_events[{i}].chapter 为空")

    return errors
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_post_processor.py -v -k "ValidateCharacter"`
Expected: PASS all 5 tests

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/post_processor.py tests/test_extraction/test_post_processor.py
git commit -m "feat: add validate_character_output — character wiki JSON validation with power_level checks"
```

---

### Task 4: orchestrator.py — 角色提取编排

**Files:**
- Modify: `arknights_wiki/extraction/orchestrator.py`
- Modify: `tests/test_extraction/test_orchestrator.py`

- [x] **Step 1: Write failing integration test for character extraction**

```python
# 添加到 tests/test_extraction/test_orchestrator.py 中
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from arknights_wiki.extraction.orchestrator import (
    run_character_extraction,
    save_character_output,
    build_character_pipeline,
)


class TestCharacterExtraction:
    def make_temp_v1_dir(self):
        """创建临时 v1_events 目录用于测试"""
        tmpdir = tempfile.mkdtemp()
        for cat in ["main", "side", "special"]:
            os.makedirs(os.path.join(tmpdir, cat), exist_ok=True)

        # 写入一个测试章
        chapter_data = {
            "chapter": "黑暗时代·上",
            "category": "main",
            "events": [
                {
                    "event": "阿米娅救出博士",
                    "type": "rescue",
                    "line_range": [1, 50],
                    "participants": ["阿米娅", "博士", "杜宾"],
                    "significance": "故事开端",
                    "is_imaginary": False,
                },
                {
                    "event": "遭遇整合运动",
                    "type": "battle",
                    "line_range": [51, 100],
                    "participants": ["阿米娅", "近卫干员"],
                    "significance": "展示战斗",
                    "is_imaginary": False,
                },
            ],
        }
        with open(os.path.join(tmpdir, "main", "黑暗时代·上.json"), "w", encoding="utf-8") as f:
            json.dump(chapter_data, f, ensure_ascii=False)
        return tmpdir

    def test_build_character_pipeline_aggregates(self):
        """测试 pipeline 能正确聚合角色"""
        v1_dir = self.make_temp_v1_dir()
        operators = [{"name_zh": "阿米娅", "race": "卡特斯"}]
        id_map = {}
        keep_set = set()

        try:
            targets, op_list = build_character_pipeline(
                v1_dir=v1_dir,
                operators=operators,
                id_map=id_map,
                keep_set=keep_set,
                data_dir=None,  # 不注入原文
            )
            assert "阿米娅" in targets
            assert len(targets["阿米娅"]["events"]) == 2
        finally:
            import shutil
            shutil.rmtree(v1_dir, ignore_errors=True)

    def test_save_character_output(self, tmp_path):
        """测试保存角色输出到文件"""
        data = {
            "entity_id": "character:R001",
            "name_zh": "阿米娅",
            "summary": "测试摘要",
        }
        out_dir = str(tmp_path / "v2_characters")
        path = save_character_output(data, output_dir=out_dir)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["name_zh"] == "阿米娅"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extraction/test_orchestrator.py -v -k "Character"`
Expected: FAIL

- [x] **Step 3: Implement character extraction functions in orchestrator.py**

```python
# 添加到 orchestrator.py 末尾（在 generate_run_report 之后）


def build_character_pipeline(
    v1_dir: str = "data/extractions/v1_events",
    data_dir: str = "data/stories",
    operators_path: str = "data/operators.json",
    identity_map_path: str = "config/identity_map.json",
    keep_list_path: str = "output/pass2_single_appearance_npc.md",
    operators: list[dict] = None,
    id_map: dict = None,
    keep_set: set = None,
) -> tuple[dict, list[dict]]:
    """构建角色提取管道：收集 → 规范化 → 过滤 → 注入上下文。

    Args:
        operators: 直接传入干员列表（测试用），为 None 时从文件加载
        id_map: 直接传入别名映射（测试用），为 None 时从文件加载
        keep_set: 直接传入 KEEP 集合（测试用），为 None 时从文件加载

    Returns:
        (targets, operators): targets 是 {name: {aliases, chapters, events}} 字典
    """
    from .character_aggregator import (
        collect_from_v1,
        normalize_and_merge,
        filter_targets,
        inject_context,
        parse_keep_list,
    )

    if operators is None:
        with open(operators_path, "r", encoding="utf-8") as f:
            operators = json.load(f)["operators"]

    if id_map is None:
        from .post_processor import load_identity_map
        id_map = load_identity_map(identity_map_path)

    if keep_set is None:
        keep_set = parse_keep_list(keep_list_path)

    raw = collect_from_v1(v1_dir)
    merged = normalize_and_merge(raw, operators, id_map)
    targets = filter_targets(merged, operators, keep_set)

    if data_dir:
        targets = inject_context(targets, data_dir)

    return targets, operators


def run_character_extraction(
    name_zh: str,
    character_data: dict,
    operator_archive: dict | None = None,
) -> dict:
    """提取单个角色的 Wiki 档案。

    Args:
        name_zh: 角色规范名
        character_data: 聚合后的角色数据 {"aliases", "chapters", "events"}
        operator_archive: 干员档案（非干员为 None）

    Returns:
        角色 Wiki JSON dict
    """
    from .prompt_builder import build_character_system_prompt, build_character_user_prompt
    from .llm_client import create_client, call_llm
    from .dialogue_loader import load_chapter

    chapter_count = len(character_data["chapters"])
    events = character_data["events"]

    system_prompt = build_character_system_prompt()
    user_prompt = build_character_user_prompt(
        name_zh=name_zh,
        chapter_count=chapter_count,
        events_with_context=events,
        operator_archive=operator_archive,
    )

    client = create_client()
    llm_result = call_llm(client, system_prompt, user_prompt)

    if llm_result.get("_parse_error"):
        return {"_parse_error": True, "name_zh": name_zh}

    stats = llm_result.pop("_stats", {})
    return {"name_zh": name_zh, **llm_result, "_stats": stats}


def save_character_output(
    data: dict,
    output_dir: str = "data/extractions/v2_characters",
) -> str:
    """保存角色 Wiki JSON 到文件。"""
    os.makedirs(output_dir, exist_ok=True)

    name = data.get("name_zh", "unknown")
    # 安全文件名：替换特殊字符
    safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
    out_path = os.path.join(output_dir, f"{safe_name}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return out_path


def run_trial_characters(
    trial_names: list[str],
    data_dir: str = "data/stories",
    v1_dir: str = "data/extractions/v1_events",
) -> dict[str, dict]:
    """试跑：为指定角色列表生成 Wiki 档案。"""
    targets, operators = build_character_pipeline(
        v1_dir=v1_dir,
        data_dir=data_dir,
    )

    from .character_aggregator import get_operator_archive
    from .post_processor import validate_character_output
    from datetime import datetime, timezone

    results = {}
    os.makedirs("output/pass2_trial", exist_ok=True)

    total_in = 0
    total_out = 0
    t_start = time.time()

    for i, name in enumerate(trial_names):
        if name not in targets:
            print(f"[{i+1}/{len(trial_names)}] {name} SKIP (未在 Pass 1 中找到)")
            continue

        char_data = targets[name]
        ch_count = len(char_data["chapters"])
        ev_count = len(char_data["events"])
        archive = get_operator_archive(name, operators)

        print(f"\n[{i+1}/{len(trial_names)}] {name}: {ch_count} 章, {ev_count} 事件")

        t0 = time.time()
        result = run_character_extraction(
            name_zh=name,
            character_data=char_data,
            operator_archive=archive,
        )
        elapsed = time.time() - t0

        result["aliases"] = list(char_data["aliases"])
        result["source_pass1_chapters"] = sorted(char_data["chapters"])
        result["source_pass1_event_count"] = ev_count

        if archive:
            result["archive"] = {
                "race": archive.get("race", ""),
                "affiliations": [
                    a for a in [archive.get("nation", ""), archive.get("team", ""), archive.get("group", "")]
                    if a
                ],
            }

        stats = result.pop("_stats", {})
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["model"] = "deepseek-chat"

        errors = validate_character_output(result, name)
        if errors:
            result["_validation_errors"] = errors
            print(f"  校验错误: {errors}")

        total_in += stats.get("tokens_in", 0)
        total_out += stats.get("tokens_out", 0)

        out_path = save_character_output(result, output_dir="output/pass2_trial")
        print(f"  tok: in={stats.get('tokens_in',0):,} out={stats.get('tokens_out',0):,} events={len(result.get('participated_events',[]))} power={result.get('abilities',{}).get('power_level','?')} ({elapsed:.1f}s)")
        print(f"  saved => {out_path}")

        results[name] = result

    elapsed_all = time.time() - t_start
    print(f"\n试跑完成: {len(results)}/{len(trial_names)} 角色")
    print(f"  tokens: in={total_in:,} out={total_out:,}")
    print(f"  耗时: {elapsed_all:.0f}s ({elapsed_all/60:.1f}m)")

    return results
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extraction/test_orchestrator.py -v -k "Character"`
Expected: PASS (build_character_pipeline and save_character_output tests)

- [x] **Step 5: Run all tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: ALL pass

- [x] **Step 6: Commit**

```bash
git add arknights_wiki/extraction/orchestrator.py tests/test_extraction/test_orchestrator.py
git commit -m "feat: add character extraction orchestration — build_character_pipeline, run_character_extraction, save_character_output, run_trial_characters"
```

---

### Task 5: 试跑 17 角色

**Files:**
- Create: `run_pass2_trial.py` (临时脚本)

- [x] **Step 1: Create trial script**

```python
# run_pass2_trial.py
"""Pass 2 试跑：17 角色 Wiki 档案生成"""
import sys
sys.path.insert(0, ".")

from arknights_wiki.extraction.orchestrator import run_trial_characters

TRIAL_CHARACTERS = [
    "博士",       # 40章 - 最大输入压力测试
    "凯尔希",     # 32章 - 长跨章总结
    "阿米娅",     # 32章 - Schema 完整性
    "能天使",     # 7章 - 中高频
    "玛恩纳",     # 5章 - 关键 NPC
    "临光",       # 6章 - 大型活动主角
    "莫斯提马",   # 4章 - 低出场高频提及
    "刻俄柏",     # 4章 - 档案丰富型
    "塞雷娅",     # 4章 - 多势力归属
    "望",         # 4章 - 岁兽阵营
    "菲亚梅塔",   # 2章 - 中低频
    "余",         # 2章 - 岁兽碎片
    "Guard",      # 5章 - 多面性 NPC
    "白垩",       # 1章 - 单章关键 NPC
    "龙舌兰",     # 1章 - 单章干员
    "奥达",       # 1章 - 单章 NPC
    "德克萨斯",   # (备用，代替未找到的)
]

if __name__ == "__main__":
    results = run_trial_characters(TRIAL_CHARACTERS)
```

- [x] **Step 2: Run trial (dry-run first — collect stats without LLM calls)**

Run: `python -c "
from arknights_wiki.extraction.orchestrator import build_character_pipeline
targets, operators = build_character_pipeline()
for name in ['博士','凯尔希','阿米娅','能天使','玛恩纳','临光','莫斯提马','刻俄柏','塞雷娅','望','菲亚梅塔','余','Guard','白垩','龙舌兰','奥达']:
    if name in targets:
        d = targets[name]
        print(f'{name}: {len(d[\"chapters\"])}章, {len(d[\"events\"])}事件, aliases={d[\"aliases\"]}')
    else:
        print(f'{name}: NOT FOUND')
" 2>&1
`
Expected: Show chapter/event counts for all 16 characters. Note any NOT FOUND.

- [x] **Step 3: Run trial with LLM calls**

Run: `python run_pass2_trial.py 2>&1 | tee output/pass2_trial_log.txt`
Expected: 16 JSON files in `output/pass2_trial/`, 100% JSON parse success

- [x] **Step 4: Quality check**

Manual review of:
- `output/pass2_trial/博士.json` — 500字 summary 质量
- `output/pass2_trial/阿米娅.json` — participated_events 合并质量
- `output/pass2_trial/白垩.json` — 单章角色质量
- Power level "信息不足" 占比

- [x] **Step 5: Commit trial results**

```bash
git add run_pass2_trial.py output/pass2_trial/ output/pass2_trial_log.txt
git commit -m "feat: Pass 2 trial run — 16/16 characters extracted, review pending"
```

---

## 全量执行（试跑验证通过后）

```python
# 在 orchestrator.py 中添加 run_all_characters 函数
def run_all_characters(
    data_dir: str = "data/stories",
    v1_dir: str = "data/extractions/v1_events",
    output_dir: str = "data/extractions/v2_characters",
    resume: bool = True,
) -> list[dict]:
    """全量角色 Wiki 生成"""
    ...
```

成本估算: ~658 角色, ~$2.0 USD (DeepSeek)
