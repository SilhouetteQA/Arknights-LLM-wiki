# Pass 3 世界观实体提取 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从大地巡旅(6章)+37视频提取概念/阵营/地点三层实体，产出 Seed DB + 初版 Wiki 页面

**Architecture:** 6 个新模块：book_splitter(书本章节切分)、video_merger(视频合并)、worldbuilding_schema(输出格式定义)、worldbuilding_prompts(提示词)、worldbuilding_processor(解析+校验+聚合)、worldbuilding_orchestrator(编排 pipeline)。复用现有 llm_client.py 不变。

**Tech Stack:** Python 3.12+, pytest, DeepSeek API, 复用 arknights_wiki/extraction/llm_client.py

---

## 文件结构

```
arknights_wiki/extraction/
  llm_client.py                   # [复用] LLM API 调用
  book_splitter.py                # [新建] 大地巡旅按章切分
  video_merger.py                 # [新建] 37视频合并
  worldbuilding_schema.py         # [新建] 输出 JSON Schema 定义
  worldbuilding_prompts.py        # [新建] Phase 1/2 提示词
  worldbuilding_processor.py      # [新建] 解析+校验+聚合+种子库IO
  worldbuilding_orchestrator.py   # [新建] Phase 1+2 编排

tests/
  test_book_splitter.py
  test_video_merger.py
  test_worldbuilding_schema.py
  test_worldbuilding_prompts.py
  test_worldbuilding_processor.py
  test_worldbuilding_orchestrator.py
```

---

### Task 1: worldbuilding_schema — 输出格式定义

**Files:**
- Create: `arknights_wiki/extraction/worldbuilding_schema.py`
- Test: `tests/test_worldbuilding_schema.py`

- [ ] **Step 1: 写 failing test — 验证概念 JSON Schema 包含所有必填字段**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_worldbuilding_schema.py -v
# Expected: 全部 FAIL (ImportError: No module named 'worldbuilding_schema')
```

- [ ] **Step 3: 实现 worldbuilding_schema.py**

```python
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

_CONCEPT_REQUIRED = {"name", "category", "definition", "summary"}
_FACTION_REQUIRED = {"name", "category", "definition", "summary"}
_LOCATION_REQUIRED = {"name", "category", "definition", "summary"}

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
        if field not in data or (isinstance(data[field], str) and not data[field].strip()):
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_worldbuilding_schema.py -v
# Expected: 11 passed
```

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/worldbuilding_schema.py tests/test_worldbuilding_schema.py
git commit -m "feat: worldbuilding_schema — concept/faction/location validation"
```

---

### Task 2: book_splitter — 大地巡旅章节切分

**Files:**
- Create: `arknights_wiki/extraction/book_splitter.py`
- Test: `tests/test_book_splitter.py`

- [ ] **Step 1: 写 failing test**

```python
import os
from arknights_wiki.extraction.book_splitter import split_book, ChapterSegment


class TestBookSplitter:
    def test_split_returns_chapter_segments(self):
        """切分返回 ChapterSegment 列表，每段有 title 和 text"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        assert len(segments) >= 6  # 6 章 + 附录
        for seg in segments:
            assert isinstance(seg, ChapterSegment)
            assert seg.title
            assert len(seg.text) > 0

    def test_chapter_titles_match_expected(self):
        """章节标题覆盖六章"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        titles = [s.title for s in segments]
        assert any("源石" in t for t in titles)
        assert any("科技" in t for t in titles)
        assert any("生物" in t for t in titles)
        assert any("种族" in t for t in titles)
        assert any("国家" in t for t in titles)
        assert any("组织" in t for t in titles)

    def test_each_chapter_starts_with_page_marker(self):
        """每章以 ## 第 X 页 开头"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        for seg in segments:
            assert seg.text.strip().startswith("## 第"), \
                f"章节 '{seg.title}' 不以页面标记开头: {seg.text[:50]}..."

    def test_no_overlap_between_chapters(self):
        """章节之间无内容重叠"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        for i in range(len(segments) - 1):
            assert segments[i].text not in segments[i+1].text or \
                len(segments[i].text) < 100
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_book_splitter.py -v
# Expected: FAIL (ImportError)
```

- [ ] **Step 3: 实现 book_splitter.py**

```python
"""大地巡旅 OCR 全文按章节切分"""
import re
from dataclasses import dataclass


@dataclass
class ChapterSegment:
    title: str
    text: str
    start_page: int
    end_page: int


# 章节边界定义: (起始页号, "章节标题关键词")
# 页号对应 OCR 文件中的 "## 第 N 页" 编号
_CHAPTER_BOUNDARIES = [
    (1,   "目录与前言"),
    (3,   "第一章：源石，天灾，矿石病"),
    (33,  "第二章：泰拉科技"),
    (59,  "第三章：泰拉生物"),
    (79,  "第四章：泰拉种族"),
    (107, "第五章：国家与地区"),
    (347, "第六章：组织"),
    (389, "附录：组织名录"),  # Ch6 的子部分，合并入 Ch6
]


def _find_page_offset(lines: list[str], page_num: int) -> int:
    """在行列表中找到指定页号的行索引"""
    marker = f"## 第 {page_num} 页"
    for i, line in enumerate(lines):
        if line.strip() == marker:
            return i
    # 如果精确页号不存在（如被审查拦截的页），找最近的下一个存在的页
    for offset in range(1, 10):
        marker = f"## 第 {page_num + offset} 页"
        for i, line in enumerate(lines):
            if line.strip() == marker:
                return i
    return -1


def split_book(filepath: str) -> list[ChapterSegment]:
    """将大地巡旅全文按 7 个章节 + 附录切分

    返回 ChapterSegment 列表，合并连续的非正文页（目录、前言）为一个 segment。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    # 找各章起始行
    chapter_starts = []
    for page_num, title in _CHAPTER_BOUNDARIES:
        offset = _find_page_offset(lines, page_num)
        if offset >= 0:
            chapter_starts.append((offset, page_num, title))

    # 切分
    segments = []
    for i, (start_offset, page, title) in enumerate(chapter_starts):
        if i + 1 < len(chapter_starts):
            end_offset = chapter_starts[i + 1][0]
        else:
            end_offset = len(lines)

        text = "\n".join(lines[start_offset:end_offset]).strip()
        seg = ChapterSegment(
            title=title,
            text=text,
            start_page=page,
            end_page=chapter_starts[i+1][1] if i+1 < len(chapter_starts) else 999,
        )
        segments.append(seg)

    # 合并 Ch6 和附录（附录是 Ch6 内的组织名录）
    # 跳过目录段（第 1 页）

    # 返回实质章节：跳过目录，合并 Ch6+附录
    result = []
    for seg in segments:
        if "目录" in seg.title:
            continue
        if "附录" in seg.title:
            # 合并到前一个章节（Ch6）
            if result:
                result[-1].text += "\n\n" + seg.text
                result[-1].end_page = seg.end_page
            continue
        result.append(seg)

    return result
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_book_splitter.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/book_splitter.py tests/test_book_splitter.py
git commit -m "feat: book_splitter — split Terra book by chapter boundaries"
```

---

### Task 3: video_merger — 视频字幕合并

**Files:**
- Create: `arknights_wiki/extraction/video_merger.py`
- Test: `tests/test_video_merger.py`

- [ ] **Step 1: 写 failing test**

```python
import os, tempfile, json
from arknights_wiki.extraction.video_merger import merge_videos, VideoMeta


class TestVideoMerger:
    def test_merge_returns_string(self):
        """合并返回非空字符串"""
        result = merge_videos("data/videos")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_merge_includes_video_titles(self):
        """合并结果包含每个视频的标题"""
        result = merge_videos("data/videos")
        # 至少包含几个已知视频标题
        assert "拉特兰：圣灵" in result or "Lateland" in result.lower()

    def test_merge_includes_publish_dates(self):
        """合并结果包含发布时间"""
        result = merge_videos("data/videos")
        assert "发布时间" in result

    def test_parse_video_meta(self):
        """解析单个视频文件的元数据"""
        from arknights_wiki.extraction.video_merger import parse_video_meta
        # 使用第一个视频文件测试
        files = sorted(os.listdir("data/videos"))
        md_files = [f for f in files if f.endswith(".md")]
        if md_files:
            meta = parse_video_meta(os.path.join("data/videos", md_files[0]))
            assert isinstance(meta, VideoMeta)
            assert meta.title
            assert meta.publish_date is not None  # 可能为 "未知"

    def test_merge_result_structure(self):
        """合并结果有清晰的节结构"""
        result = merge_videos("data/videos")
        # 每个视频应以分隔标记开始
        assert "===" in result or "---" in result or "##" in result
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_video_merger.py -v
# Expected: FAIL (ImportError)
```

- [ ] **Step 3: 实现 video_merger.py**

```python
"""37 个世界观视频字幕合并为一个文本块"""
import os
import re
from dataclasses import dataclass


@dataclass
class VideoMeta:
    title: str
    publish_date: str  # "未知" 或 ISO 格式
    bv_id: str
    url: str


def parse_video_meta(filepath: str) -> VideoMeta:
    """从视频 md 文件中提取元数据"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取标题（第一个 # 标题）
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else os.path.basename(filepath)

    # 提取发布时间
    date_match = re.search(r"\*\*发布时间\*\*:\s*(.+)", content)
    publish_date = date_match.group(1).strip() if date_match else "未知"

    # 提取 BV 号
    bv_match = re.search(r"\*\*BV号\*\*:\s*(\S+)", content)
    bv_id = bv_match.group(1).strip() if bv_match else ""

    # 提取视频链接
    url_match = re.search(r"\*\*视频链接\*\*:\s*(\S+)", content)
    url = url_match.group(1).strip() if url_match else ""

    return VideoMeta(title=title, publish_date=publish_date, bv_id=bv_id, url=url)


def merge_videos(video_dir: str = "data/videos") -> str:
    """合并所有视频字幕为一个文本块

    格式：
    === 视频 1: <标题> (发布时间: <date>) ===
    <内容>

    === 视频 2: <标题> (发布时间: <date>) ===
    <内容>
    """
    files = sorted([
        f for f in os.listdir(video_dir)
        if f.endswith(".md") and f != "input.md"  # input.md 是原始输入文件
    ])

    parts = []
    parts.append(f"# 明日方舟世界观视频字幕合集\n")
    parts.append(f"共 {len(files)} 个视频\n")

    for i, filename in enumerate(files, 1):
        filepath = os.path.join(video_dir, filename)
        meta = parse_video_meta(filepath)

        # 提取台词部分（## 台词 之后的内容）
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        dialogue_match = re.search(r"##\s*台词\s*\n(.+)", content, re.DOTALL)
        dialogue = dialogue_match.group(1).strip() if dialogue_match else content

        parts.append(f"\n{'='*60}")
        parts.append(f"视频 {i}: {meta.title}")
        parts.append(f"发布时间: {meta.publish_date}")
        parts.append(f"{'='*60}\n")
        parts.append(dialogue)

    return "\n".join(parts)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_video_merger.py -v
# Expected: 5 passed
```

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/video_merger.py tests/test_video_merger.py
git commit -m "feat: video_merger — merge 37 video transcripts with metadata"
```

---

### Task 4: worldbuilding_prompts — Phase 1/2 提示词

**Files:**
- Create: `arknights_wiki/extraction/worldbuilding_prompts.py`
- Test: `tests/test_worldbuilding_prompts.py`

- [ ] **Step 1: 写 failing test**

```python
from arknights_wiki.extraction.worldbuilding_prompts import (
    build_book_system_prompt,
    build_book_user_prompt,
    build_video_system_prompt,
    build_video_user_prompt,
    build_seed_context,
)


class TestBookPrompts:
    def test_book_system_prompt_contains_categories(self):
        """system prompt 包含六子类说明"""
        prompt = build_book_system_prompt()
        assert "自然现象/物质" in prompt
        assert "种族/血脈" in prompt
        assert "超自然存在" in prompt

    def test_book_system_prompt_no_json_block(self):
        """system prompt 不含 markdown code block"""
        prompt = build_book_system_prompt()
        assert "```json" not in prompt

    def test_book_user_prompt_includes_chapter_content(self):
        """user prompt 包含章节文本"""
        prompt = build_book_user_prompt(
            chapter_title="第一章：源石",
            chapter_text="## 第 3 页\n源石是泰拉世界的基础..."
        )
        assert "第一章：源石" in prompt
        assert "源石是泰拉世界的基础" in prompt

    def test_book_user_prompt_includes_output_schema(self):
        """user prompt 包含输出格式说明"""
        prompt = build_book_user_prompt("test", "content")
        assert "concepts" in prompt.lower() or "concept" in prompt.lower()
        assert "factions" in prompt.lower() or "faction" in prompt.lower()


class TestVideoPrompts:
    def test_video_system_prompt_mentions_enrichment(self):
        """视频 system prompt 强调丰富已有实体"""
        prompt = build_video_system_prompt()
        assert "丰富" in prompt or "补充" in prompt or "已有" in prompt

    def test_video_user_prompt_without_seed(self):
        """无种子库时的 user prompt"""
        prompt = build_video_user_prompt("video content", seed_context="")
        assert "video content" in prompt

    def test_video_user_prompt_with_seed(self):
        """有种子库时的 user prompt 包含已知实体列表"""
        seed = build_seed_context({"concepts": [], "factions": [], "locations": []})
        prompt = build_video_user_prompt("video content", seed_context=seed)
        assert len(prompt) > 0

    def test_video_prompt_mentions_publish_date_context(self):
        """视频提示词包含发布时间上下文说明"""
        prompt = build_video_system_prompt()
        assert "发布时间" in prompt


class TestSeedContext:
    def test_build_seed_context_empty_db(self):
        """空种子库产出简洁提示"""
        ctx = build_seed_context({"concepts": [], "factions": [], "locations": []})
        assert isinstance(ctx, str)

    def test_build_seed_context_with_entities(self):
        """有实体时列出名称和分类"""
        seed_db = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质", "definition": "核心能源"},
                {"name": "萨卡兹", "category": "种族/血脈", "definition": "古老种族"},
            ],
            "factions": [
                {"name": "维多利亚", "category": "nation", "definition": "帝国"},
            ],
            "locations": [],
        }
        ctx = build_seed_context(seed_db)
        assert "源石" in ctx
        assert "萨卡兹" in ctx
        assert "维多利亚" in ctx
        assert "自然现象/物质" in ctx
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_worldbuilding_prompts.py -v
# Expected: FAIL
```

- [ ] **Step 3: 实现 worldbuilding_prompts.py**

```python
"""Pass 3 世界观实体提取提示词"""
import json


_BOOK_SYSTEM_PROMPT = """你是一位《明日方舟》世界观设定档案编纂者。你的任务是从设定集《大地巡旅》的章节中提取结构化世界观实体。

## 提取三类实体

### 1. 概念 (concepts)
世界观层面的客观实体，分为六子类:
- 自然现象/物质: 源石、天灾、活性源石、矿石病
- 种族/血脈: 萨卡兹、阿戈尔、库兰塔、提卡兹
- 超自然存在: 巨兽、兽主、海嗣、邪魔、岁兽
- 技术/技艺体系: 源石技艺七学派、移动城市技术、炼金术
- 社会制度/文化: 拉特兰律法、骑士竞技、天灾信使制度
- 特殊地域/异域: 焚风热土、黑流树海、荒域、星荚

纳入标准: 属于六子类之一的客观世界实体
排除标准: 情感/品德/角色观点/模糊隐喻
不设频率门槛: 即使只在文中出现一次，只要是关键设定信息就提取

### 2. 阵营 (factions)
有组织的行动者，分为两类:
- nation (国家/政权): 维多利亚、乌萨斯、炎、拉特兰、卡兹戴尔...
- organization (势力/组织): 莱茵生命、整合运动、罗德岛、黑钢国际...

### 3. 地点 (locations)
具体物理场所，分为两类:
- city (城市/移动城市): 龙门、汐斯塔、切尔诺伯格...
- facility (设施/建筑): 罗德岛本舰、莱茵生命总部、移动城市核心城...

注意: 特殊地貌/异域归入概念层的"特殊地域/异域"子类，不在地点层。

## 提取规则

1. **同名实体合并**: 如果同一实体在本章多处出现，合并为一个条目，在 summary 中综合所有信息
2. **不做跨章猜测**: 只基于本章提供的内容提取，不要引入你在其他资料中知道的信息
3. **人名/地名/事件名显式标注**: 在 summary 和独有字段中，使用【】标注关键实体名
4. **source_records**: 标注 source="terra_book"，source_detail="大地巡旅 <章节名>"
5. **关系字段**: 如果文中提到实体间的关联，填写 related_concepts / related_factions / related_locations
6. **注意实体辨析**: 同一个词在不同语境下可能对应不同实体，例如"萨卡兹"作为种族(概念层)和"萨卡兹王庭"作为政治组织(阵营层)

## 输出格式

严格输出 JSON，不要包含 ```json 等 markdown 标记。
JSON 字符串值内禁止使用英文双引号 "，用「」代替。"""


_BOOK_USER_PROMPT_TEMPLATE = """## 设定集章节: {chapter_title}

以下是《大地巡旅》中"{chapter_title}"的完整文本:

{chapter_text}

## 输出要求

请提取本章中所有三层实体，输出 JSON:

{output_schema}

## 规则
- 必须基于提供的文本内容，不编造
- 同一实体在多处出现时合并为一个条目
- definition 一句话定义不超过 80 字
- 概念 summary 不超过 500 字，阵营不超过 400 字，地点不超过 300 字
- 各类独有字段有信息就填，没有可省略"""


_VIDEO_SYSTEM_PROMPT = """你是一位《明日方舟》世界观设定档案编纂者。你的任务是从官方世界观视频中提取结构化实体，并丰富已有的设定集实体库。

## 已有实体库

下方提供了从《大地巡旅》官方设定集提取的已知实体列表。你的首要任务是:

1. **丰富已有实体**: 如果视频内容对已知实体提供了新信息（细节、案例、不同角度），更新该实体的 summary 和独有字段
2. **发现新实体**: 只有确认是现有实体库中没有的全新实体时，才创建新条目
3. **不重复创建**: 视频中出现但实体库已有的实体，不要作为新实体输出

## 视频发布时间说明

视频的发布时间已标注在每个视频的头部。当视频内容涉及主线剧情演进（如组织的成立/解散、城市的建立/废弃、角色的状态变化等），注意结合发布时间判断视频描述的是转变前还是转变后的状态。常规世界观信息（如源石原理、种族特征）不受发布时间影响。

## 提取三类实体

与设定集提取相同: concepts(六子类) / factions(两类) / locations(两类)

## 输出格式

严格输出 JSON，不要包含 ```json 等 markdown 标记。
JSON 字符串值内禁止使用英文双引号 "，用「」代替。"""


_VIDEO_USER_PROMPT_TEMPLATE = """## 视频字幕合集

{video_text}

{seed_context}

## 输出要求

请基于视频内容，对已知实体库进行补充和丰富，如发现新实体则创建。

输出 JSON:

{output_schema}

## 规则
- 优先丰富已有实体，只有确认是全新实体时才创建
- source_records 中 source="video"，source_detail 标注视频标题和发布时间
- 新实体和丰富后的实体都输出，已有实体无新增信息则不输出
- 视频中的信息可能与设定集一致（跳过），也可能提供新角度（补充），也可能冲突（标注 confidence="conflicting"）
- 注意发布时间与主线剧情演进的关系"""


_OUTPUT_SCHEMA = """{
  "concepts": [
    {
      "name": "实体名称",
      "category": "六子类之一",
      "definition": "一句话定义(≤80字)",
      "summary": "综合描述(≤500字)",
      "aliases": ["别名1"],
      "manifestation": "表现形态(自然现象/物质)",
      "origin_hypothesis": "起源假说(自然现象/物质)",
      "related_arts": "关联源石技艺(自然现象/物质)",
      "origin_region": "起源地(种族)",
      "physical_traits": "体貌特征(种族)",
      "related_races": ["亲缘种族(种族)"],
      "oripathy_susceptibility": "矿石病易感性(种族)",
      "lifespan": "寿命特征(种族)",
      "nature": "本质(超自然存在)",
      "scale": "位阶/规模(超自然存在)",
      "known_instances": ["已知个体(超自然存在)"],
      "relation_to_humanity": "与人类关系(超自然存在)",
      "underlying_principle": "底层原理(技术)",
      "practitioners": "使用群体(技术)",
      "spread": "传播范围(技术)",
      "key_applications": ["关键应用(技术)"],
      "origin_nation": "起源国家(社会制度)",
      "characteristics": "制度特点(社会制度)",
      "key_institutions": ["核心机构(社会制度)"],
      "social_impact": "社会影响(社会制度)",
      "location_type": "地域类型(特殊地域)",
      "accessibility": "进入方式(特殊地域)",
      "hazards": ["危险要素(特殊地域)"],
      "phenomena": ["独特现象(特殊地域)"],
      "source_records": [{"source": "terra_book或video", "source_detail": "...", "location": "...", "publish_date": "...(仅video)", "confidence": "confirmed或inferred或conflicting"}],
      "story_events": [],
      "related_concepts": [{"name": "...", "relation": "...", "desc": "..."}],
      "related_factions": [{"name": "...", "relation": "...", "desc": "..."}],
      "related_locations": [{"name": "...", "relation": "...", "desc": "..."}]
    }
  ],
  "factions": [
    {
      "name": "实体名称",
      "category": "nation或organization",
      "definition": "一句话定义(≤80字)",
      "summary": "综合描述(≤400字)",
      "aliases": ["别名"],
      "government_type": "政体(仅nation)",
      "ruler": "统治者(仅nation)",
      "key_figures": [{"name": "...", "role": "...", "description": "..."}],
      "capital": "首都(仅nation)",
      "territory": "疆域(仅nation)",
      "major_races": ["主要种族(仅nation)"],
      "historical_events": [{"name": "...", "timeframe": "...", "description": "..."}],
      "foreign_relations": [{"target_nation": "...", "attitude": "...", "description": "..."}],
      "type": "类型(仅organization)",
      "parent_nation": "所属国家(仅organization)",
      "leader": "首领(仅organization)",
      "headquarters": "总部(仅organization)",
      "member_composition": [{"name": "...", "role": "...", "description": "..."}],
      "goal": "宗旨(仅organization)",
      "external_relations": [{"target": "...", "relation_type": "...", "description": "..."}],
      "source_records": [{"source": "terra_book或video", "source_detail": "...", "location": "...", "publish_date": "...(仅video)", "confidence": "confirmed或inferred或conflicting"}],
      "story_events": [],
      "related_concepts": [{"name": "...", "relation": "...", "desc": "..."}]
    }
  ],
  "locations": [
    {
      "name": "实体名称",
      "category": "city或facility",
      "definition": "一句话定义(≤80字)",
      "summary": "综合描述(≤300字)",
      "aliases": ["别名"],
      "parent_nation": "所属国家(仅city)",
      "city_type": "类型(仅city)",
      "scale": "规模(仅city)",
      "known_districts": [{"name": "...", "description": "..."}],
      "key_events": [{"name": "...", "description": "..."}],
      "located_in": "所在城市(仅facility)",
      "facility_type": "设施类型(仅facility)",
      "owner": "所属阵营(仅facility)",
      "purpose": "用途(仅facility)",
      "source_records": [{"source": "terra_book或video", "source_detail": "...", "location": "...", "publish_date": "...(仅video)", "confidence": "confirmed或inferred或conflicting"}],
      "story_events": [],
      "related_factions": [{"name": "...", "relation": "...", "desc": "..."}],
      "related_concepts": [{"name": "...", "relation": "...", "desc": "..."}]
    }
  ]
}"""


def build_book_system_prompt() -> str:
    return _BOOK_SYSTEM_PROMPT


def build_book_user_prompt(chapter_title: str, chapter_text: str) -> str:
    return _BOOK_USER_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        chapter_text=chapter_text,
        output_schema=_OUTPUT_SCHEMA,
    )


def build_video_system_prompt() -> str:
    return _VIDEO_SYSTEM_PROMPT


def build_video_user_prompt(video_text: str, seed_context: str = "") -> str:
    return _VIDEO_USER_PROMPT_TEMPLATE.format(
        video_text=video_text,
        seed_context=seed_context,
        output_schema=_OUTPUT_SCHEMA,
    )


def build_seed_context(seed_db: dict) -> str:
    """将种子库转为视频 prompt 中的已知实体列表"""
    concepts = seed_db.get("concepts", [])
    factions = seed_db.get("factions", [])
    locations = seed_db.get("locations", [])

    parts = ["## 已知实体库 (来自《大地巡旅》设定集)"]
    parts.append("请优先丰富以下已有实体，只有确认是新实体时才创建新条目。\n")

    if concepts:
        parts.append(f"### 概念 ({len(concepts)} 个)")
        for c in concepts:
            parts.append(f"- {c['name']} [{c.get('category', '')}]: {c.get('definition', '')}")
        parts.append("")

    if factions:
        parts.append(f"### 阵营 ({len(factions)} 个)")
        for f in factions:
            parts.append(f"- {f['name']} [{f.get('category', '')}]: {f.get('definition', '')}")
        parts.append("")

    if locations:
        parts.append(f"### 地点 ({len(locations)} 个)")
        for l in locations:
            parts.append(f"- {l['name']} [{l.get('category', '')}]: {l.get('definition', '')}")
        parts.append("")

    return "\n".join(parts)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_worldbuilding_prompts.py -v
# Expected: 10 passed
```

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/worldbuilding_prompts.py tests/test_worldbuilding_prompts.py
git commit -m "feat: worldbuilding_prompts — Phase 1/2 extraction prompts"
```

---

### Task 5: worldbuilding_processor — 解析+校验+跨章聚合+种子库 IO

**Files:**
- Create: `arknights_wiki/extraction/worldbuilding_processor.py`
- Test: `tests/test_worldbuilding_processor.py`

- [ ] **Step 1: 写 failing test**

```python
import json, tempfile, os
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_worldbuilding_processor.py -v
# Expected: FAIL
```

- [ ] **Step 3: 实现 worldbuilding_processor.py**

```python
"""Pass 3 后处理: JSON 解析 + 校验 + 跨章聚合 + 种子库 IO + Wiki 页面生成"""
import json
import os
from typing import Optional

from .llm_client import parse_llm_response
from .worldbuilding_schema import validate_concept, validate_faction, validate_location


def parse_worldbuilding_output(raw: str) -> Optional[dict]:
    """解析 LLM 世界构建输出，返回 dict 或 None"""
    return parse_llm_response(raw)


def _merge_entity(existing: dict, new: dict) -> dict:
    """合并两个同名实体，保留更详细的信息"""
    merged = dict(existing)

    # definition: 保留更长的
    if len(new.get("definition", "")) > len(existing.get("definition", "")):
        merged["definition"] = new["definition"]

    # summary: 拼接（去重合并）
    existing_summary = existing.get("summary", "")
    new_summary = new.get("summary", "")
    if new_summary and new_summary not in existing_summary:
        if existing_summary:
            merged["summary"] = existing_summary + "\n\n" + new_summary
        else:
            merged["summary"] = new_summary

    # aliases: 合并
    existing_aliases = set(existing.get("aliases", []))
    new_aliases = set(new.get("aliases", []))
    merged["aliases"] = sorted(existing_aliases | new_aliases)

    # source_records: 合并
    merged["source_records"] = existing.get("source_records", []) + new.get("source_records", [])

    # 独有字段: 合并非空值
    for key in new:
        if key in ("name", "category", "definition", "summary", "aliases",
                    "source_records", "story_events"):
            continue
        if key not in merged or not merged[key]:
            new_val = new.get(key)
            if new_val:
                merged[key] = new_val

    # related_*: 合并去重
    for rel_key in ("related_concepts", "related_factions", "related_locations"):
        existing_rels = {r.get("name", ""): r for r in existing.get(rel_key, [])}
        for r in new.get(rel_key, []):
            rname = r.get("name", "")
            if rname and rname not in existing_rels:
                existing_rels[rname] = r
        merged[rel_key] = list(existing_rels.values())

    return merged


def aggregate_chapters(chapter_results: list[dict]) -> dict:
    """跨章聚合: 同名实体合并去重

    Args:
        chapter_results: 每章的 LLM 输出列表，每项含 concepts/factions/locations

    Returns:
        聚合后的种子库 {"concepts": [...], "factions": [...], "locations": [...]}
    """
    aggregated = {"concepts": {}, "factions": {}, "locations": {}}

    for chapter in chapter_results:
        for entity_type in ("concepts", "factions", "locations"):
            entities = chapter.get(entity_type, [])
            for entity in entities:
                name = entity.get("name", "").strip()
                if not name:
                    continue
                if name in aggregated[entity_type]:
                    aggregated[entity_type][name] = _merge_entity(
                        aggregated[entity_type][name], entity
                    )
                else:
                    aggregated[entity_type][name] = dict(entity)

    return {
        "concepts": list(aggregated["concepts"].values()),
        "factions": list(aggregated["factions"].values()),
        "locations": list(aggregated["locations"].values()),
    }


def load_seed_db(path: str) -> dict:
    """加载种子库 JSON"""
    if not os.path.exists(path):
        return {"concepts": [], "factions": [], "locations": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_seed_db(seed_db: dict, path: str):
    """保存种子库 JSON"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seed_db, f, ensure_ascii=False, indent=2)


def generate_wiki_pages(seed_db: dict, output_dir: str) -> list[str]:
    """从种子库生成初版 Wiki 页面 Markdown

    每个实体生成一个 md 文件，按实体类型分目录。
    """
    paths = []
    for entity_type in ("concepts", "factions", "locations"):
        type_dir = os.path.join(output_dir, entity_type)
        os.makedirs(type_dir, exist_ok=True)
        for entity in seed_db.get(entity_type, []):
            name = entity["name"]
            safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
            path = os.path.join(type_dir, f"{safe_name}.md")
            md = _entity_to_markdown(entity, entity_type)
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            paths.append(path)
    return paths


def _entity_to_markdown(entity: dict, entity_type: str) -> str:
    """单个实体转 Markdown"""
    md = f"# {entity['name']}\n\n"
    md += f"**分类:** {entity.get('category', '')}\n\n"
    md += f"**定义:** {entity.get('definition', '')}\n\n"
    md += f"## 概述\n\n{entity.get('summary', '')}\n\n"

    if entity.get("aliases"):
        md += f"**别名:** {', '.join(entity['aliases'])}\n\n"

    # 来源
    sources = entity.get("source_records", [])
    if sources:
        md += "## 来源\n\n"
        for s in sources:
            md += f"- {s.get('source_detail', s.get('source', ''))}"
            if s.get("confidence"):
                md += f" (置信度: {s['confidence']})"
            md += "\n"

    return md
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_worldbuilding_processor.py -v
# Expected: 8 passed
```

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/worldbuilding_processor.py tests/test_worldbuilding_processor.py
git commit -m "feat: worldbuilding_processor — parse, aggregate, seed DB I/O, wiki pages"
```

---

### Task 6: worldbuilding_orchestrator — Phase 1 + Phase 2 编排

**Files:**
- Create: `arknights_wiki/extraction/worldbuilding_orchestrator.py`
- Test: `tests/test_worldbuilding_orchestrator.py`

- [ ] **Step 1: 写 failing test**

```python
import os, tempfile
from unittest.mock import patch, MagicMock
from arknights_wiki.extraction.worldbuilding_orchestrator import (
    run_phase1_book,
    run_phase2_video,
    run_pass3,
)


class TestPhase1Book:
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.call_llm")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.create_client")
    def test_phase1_returns_seed_db(self, mock_create, mock_call):
        """Phase 1 返回种子库，含三层实体"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_call.return_value = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质",
                 "definition": "...", "summary": "..."},
            ],
            "factions": [],
            "locations": [],
            "_stats": {"tokens_in": 1000, "tokens_out": 200},
        }

        with tempfile.TemporaryDirectory() as tmp:
            seed_db_path = os.path.join(tmp, "seed_db.json")
            result = run_phase1_book(
                book_path="data/lorebook/terra_a_journey_full.md",
                seed_db_path=seed_db_path,
            )
            assert "concepts" in result
            assert "factions" in result
            assert "locations" in result
            # 确认种子库文件已保存
            assert os.path.exists(seed_db_path)

    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.call_llm")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.create_client")
    def test_phase1_calls_llm_per_chapter(self, mock_create, mock_call):
        """Phase 1 对每章调用一次 LLM"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_call.return_value = {
            "concepts": [], "factions": [], "locations": [],
            "_stats": {"tokens_in": 100, "tokens_out": 50},
        }

        with tempfile.TemporaryDirectory() as tmp:
            seed_db_path = os.path.join(tmp, "seed_db.json")
            run_phase1_book(
                book_path="data/lorebook/terra_a_journey_full.md",
                seed_db_path=seed_db_path,
            )
            # 6 章 + 附录并入 Ch6 = 6 次调用
            assert mock_call.call_count == 6


class TestPhase2Video:
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.call_llm")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.create_client")
    def test_phase2_returns_enriched_seed_db(self, mock_create, mock_call):
        """Phase 2 在种子库基础上返回丰富后的种子库"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_call.return_value = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质",
                 "definition": "...", "summary": "补充：视频中展示了源石的..."},
            ],
            "factions": [],
            "locations": [],
            "_stats": {"tokens_in": 5000, "tokens_out": 300},
        }

        seed_db_v1 = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质",
                 "definition": "...", "summary": "基础设定。"},
            ],
            "factions": [],
            "locations": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            result = run_phase2_video(
                seed_db=seed_db_v1,
                video_dir="data/videos",
                output_dir=tmp,
            )
            assert "concepts" in result
            # 源石应被丰富
            assert result["concepts"][0]["summary"] != "基础设定。"


class TestRunPass3:
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.run_phase1_book")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.run_phase2_video")
    def test_run_pass3_calls_both_phases(self, mock_p2, mock_p1):
        """完整 Pass 3 依次调用 Phase 1 和 Phase 2"""
        mock_p1.return_value = {"concepts": [], "factions": [], "locations": []}
        mock_p2.return_value = {"concepts": [], "factions": [], "locations": []}

        with tempfile.TemporaryDirectory() as tmp:
            result = run_pass3(
                book_path="data/lorebook/terra_a_journey_full.md",
                video_dir="data/videos",
                output_dir=tmp,
            )
            mock_p1.assert_called_once()
            mock_p2.assert_called_once()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_worldbuilding_orchestrator.py -v
# Expected: FAIL
```

- [ ] **Step 3: 实现 worldbuilding_orchestrator.py**

```python
"""Pass 3 世界观实体提取编排器: Phase 1 图书 + Phase 2 视频"""
import os, time, json
from datetime import datetime, timezone

from .llm_client import create_client, call_llm, _get_model_config
from .book_splitter import split_book
from .video_merger import merge_videos
from .worldbuilding_prompts import (
    build_book_system_prompt, build_book_user_prompt,
    build_video_system_prompt, build_video_user_prompt,
    build_seed_context,
)
from .worldbuilding_processor import (
    parse_worldbuilding_output, aggregate_chapters,
    save_seed_db, load_seed_db, generate_wiki_pages,
)


def _estimate_cost(tokens_in: int, tokens_out: int) -> float:
    """估算 DeepSeek API 成本 (USD)"""
    return tokens_in / 1_000_000 * 0.27 + tokens_out / 1_000_000 * 1.10


def run_phase1_book(
    book_path: str = "data/lorebook/terra_a_journey_full.md",
    seed_db_path: str = "data/extractions/v3_seed_db_v1.json",
) -> dict:
    """Phase 1: 提取大地巡旅设定集

    Returns:
        种子库 v1 dict
    """
    segments = split_book(book_path)
    print(f"大地巡旅切分为 {len(segments)} 个章节")

    client = create_client()
    system_prompt = build_book_system_prompt()
    chapter_results = []
    total_tokens_in = 0
    total_tokens_out = 0
    t_start = time.time()

    for i, seg in enumerate(segments, 1):
        print(f"\n[Phase 1] 章节 {i}/{len(segments)}: {seg.title}")
        print(f"  页数: {seg.start_page}-{seg.end_page}, 字符数: {len(seg.text):,}")

        user_prompt = build_book_user_prompt(seg.title, seg.text)

        t0 = time.time()
        result = call_llm(client, system_prompt, user_prompt)
        elapsed = time.time() - t0

        if result.get("_parse_error"):
            print(f"  ERROR: JSON 解析失败")
            continue

        stats = result.pop("_stats", {})
        ti = stats.get("tokens_in", 0)
        to = stats.get("tokens_out", 0)
        total_tokens_in += ti
        total_tokens_out += to

        n_c = len(result.get("concepts", []))
        n_f = len(result.get("factions", []))
        n_l = len(result.get("locations", []))
        print(f"  concepts={n_c} factions={n_f} locations={n_l}")
        print(f"  tokens: in={ti:,} out={to:,} {elapsed:.1f}s")

        chapter_results.append(result)

    # 跨章聚合
    seed_db = aggregate_chapters(chapter_results)
    seed_db["_meta"] = {
        "phase": 1,
        "model": _get_model_config()["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "大地巡旅",
        "chapters_processed": len(chapter_results),
        "stats": {
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "elapsed_s": time.time() - t_start,
            "cost_usd": _estimate_cost(total_tokens_in, total_tokens_out),
        },
    }

    save_seed_db(seed_db, seed_db_path)
    print(f"\nPhase 1 完成:")
    print(f"  概念: {len(seed_db['concepts'])}")
    print(f"  阵营: {len(seed_db['factions'])}")
    print(f"  地点: {len(seed_db['locations'])}")
    print(f"  tokens: in={total_tokens_in:,} out={total_tokens_out:,}")
    print(f"  成本: ${seed_db['_meta']['stats']['cost_usd']:.3f}")
    print(f"  种子库: {seed_db_path}")

    return seed_db


def run_phase2_video(
    seed_db: dict = None,
    video_dir: str = "data/videos",
    output_dir: str = "data/extractions/v3_wiki",
) -> dict:
    """Phase 2: 视频补充提取

    Args:
        seed_db: Phase 1 种子库（如为 None，从默认路径加载）
        video_dir: 视频字幕目录
        output_dir: Wiki 页面输出目录

    Returns:
        丰富后的种子库 v2
    """
    if seed_db is None:
        seed_db = load_seed_db("data/extractions/v3_seed_db_v1.json")

    # 合并视频
    video_text = merge_videos(video_dir)
    print(f"视频合并完成: {len(video_text):,} 字符")

    # 构建种子上下文
    seed_context = build_seed_context(seed_db)

    client = create_client()
    system_prompt = build_video_system_prompt()
    user_prompt = build_video_user_prompt(video_text, seed_context=seed_context)

    print(f"\n[Phase 2] 视频提取开始...")
    t0 = time.time()
    result = call_llm(client, system_prompt, user_prompt)
    elapsed = time.time() - t0

    if result.get("_parse_error"):
        print(f"  ERROR: JSON 解析失败")
        return seed_db

    stats = result.pop("_stats", {})
    ti = stats.get("tokens_in", 0)
    to = stats.get("tokens_out", 0)

    n_c = len(result.get("concepts", []))
    n_f = len(result.get("factions", []))
    n_l = len(result.get("locations", []))
    print(f"  新/丰富: concepts={n_c} factions={n_f} locations={n_l}")
    print(f"  tokens: in={ti:,} out={to:,} {elapsed:.1f}s")

    # 合并到种子库
    enriched = aggregate_chapters([seed_db, result])
    enriched["_meta"] = {
        "phase": 2,
        "model": _get_model_config()["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "大地巡旅 + 视频",
        "stats": {
            "tokens_in": ti + seed_db.get("_meta", {}).get("stats", {}).get("tokens_in", 0),
            "tokens_out": to + seed_db.get("_meta", {}).get("stats", {}).get("tokens_out", 0),
            "elapsed_s": elapsed,
            "cost_usd": _estimate_cost(ti, to),
        },
    }

    # 保存种子库 v2
    seed_db_v2_path = "data/extractions/v3_seed_db_v2.json"
    save_seed_db(enriched, seed_db_v2_path)

    # 生成 Wiki 页面
    wiki_paths = generate_wiki_pages(enriched, output_dir)
    print(f"\nPhase 2 完成:")
    print(f"  概念: {len(enriched['concepts'])}")
    print(f"  阵营: {len(enriched['factions'])}")
    print(f"  地点: {len(enriched['locations'])}")
    print(f"  Wiki 页面: {len(wiki_paths)} 个")
    print(f"  种子库 v2: {seed_db_v2_path}")

    return enriched


def run_pass3(
    book_path: str = "data/lorebook/terra_a_journey_full.md",
    video_dir: str = "data/videos",
    output_dir: str = "data/extractions/v3_wiki",
) -> dict:
    """运行完整 Pass 3: Phase 1 + Phase 2"""
    print("=" * 60)
    print("Pass 3: 世界观实体提取")
    print(f"模型: {_get_model_config()['model']}")
    print("=" * 60)

    # Phase 1
    seed_db_v1 = run_phase1_book(book_path)

    # Phase 2
    seed_db_v2 = run_phase2_video(
        seed_db=seed_db_v1,
        video_dir=video_dir,
        output_dir=output_dir,
    )

    return seed_db_v2
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_worldbuilding_orchestrator.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/worldbuilding_orchestrator.py tests/test_worldbuilding_orchestrator.py
git commit -m "feat: worldbuilding_orchestrator — Phase 1 book + Phase 2 video pipeline"
```

---

## Plan Self-Review

### 覆盖检查
- [x] Spec 四 概念 Schema → Task 1 (schema validation) + Task 5 (aggregation)
- [x] Spec 五 阵营 Schema → Task 1
- [x] Spec 六 地点 Schema → Task 1
- [x] Spec 三 Phase 1 书章节切分 → Task 2 (book_splitter)
- [x] Spec 三 Phase 2 视频合并 → Task 3 (video_merger)
- [x] Spec 八 Prompt 设计 → Task 4 (prompts)
- [x] Spec 三 跨章聚合 → Task 5 (aggregate_chapters)
- [x] Spec 三 种子库 + Wiki 页面 → Task 5 (IO + wiki generation)
- [x] Spec 三 Pipeline 编排 → Task 6 (orchestrator)

### 占位符扫描
- 无 TBD/TODO
- 无"implement later"或"add appropriate handling"
- 所有代码步骤包含完整实现

### 类型一致性
- validate_concept/faction/location 签名在 Task 1 和 Task 5 一致
- seed_db dict 结构 {concepts, factions, locations} 全局一致
- ChapterSegment dataclass 在 Task 2 定义，Task 6 使用
- build_seed_context 在 Task 4 定义，Task 6 使用
