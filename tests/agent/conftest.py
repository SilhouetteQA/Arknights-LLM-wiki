"""Agent 测试共享 fixtures"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_concept_page():
    """Pass 3 概念页示例"""
    return """# 源石

**分类:** 自然现象/物质

**定义:** 泰拉世界一种蕴含巨大能量的矿物。

## 概述

源石是泰拉世界最核心的能量来源和工业原料。它也是矿石病的病原体。

## 剧情事件

### 黑暗时代·上

- **首次提及源石** [minor]: 阿米娅向博士解释源石和矿石病的关系。
"""


@pytest.fixture
def sample_character_json():
    """Pass 2 角色 JSON 示例"""
    return {
        "name": "Amiya",
        "display_name": "阿米娅",
        "summary": "罗德岛公开领袖，公开身份为感染者。拥有出色的源石技艺天赋。",
        "personality": "认真、温柔、坚强，对博士绝对信任。",
        "power_level": "军事精锐·标准",
        "power_level_evidence": "多次在正面战场中展现出色的战术指挥和源石技艺能力。",
        "story_events": [
            {"chapter": "黑暗时代·上", "summary": "在切尔诺伯格唤醒失忆的博士。"},
        ],
    }


@pytest.fixture
def sample_pass1_events():
    """Pass 1 事件 JSON 示例"""
    return {
        "summary": "博士在切尔诺伯格苏醒，整合运动发动袭击。",
        "events": [
            {
                "event": "博士在切尔诺伯格核心区苏醒，被阿米娅告知其罗德岛成员身份。",
                "type": "revelation",
                "line_range": [1, 78],
                "participants": ["阿米娅", "医疗干员", "博士"],
                "location": "切尔诺伯格核心区废弃设施",
                "is_imaginary": False,
            },
            {
                "event": "整合运动突袭设施，阿米娅请求博士指挥。",
                "type": "ambush",
                "line_range": [79, 124],
                "participants": ["阿米娅", "博士", "整合运动成员"],
                "location": "切尔诺伯格核心区废弃设施",
                "is_imaginary": False,
            },
        ],
    }


@pytest.fixture
def sample_timeline():
    """Timeline 示例"""
    return """# 泰拉历史时间线

## 759

**维多利亚工程师发明了第一台轮式源石外燃机**

## 797

**七城联邦建成泰拉历史上第一座现代移动城市**
"""


@pytest.fixture
def sample_dialogue():
    """原始对话示例"""
    return {
        "id": "main_01_01",
        "chapter": "黑暗时代·上",
        "lines": [
            {"type": "narration", "text": "5:57 a.m. / 多云"},
            {"type": "dialogue", "speaker": "阿米娅", "text": "博士，您醒了吗？"},
            {"type": "dialogue", "speaker": "博士", "text": "这里...是哪里？"},
            {"type": "dialogue", "speaker": "阿米娅", "text": "欢迎回来，博士。我是罗德岛的阿米娅。"},
        ],
    }


@pytest.fixture
def mock_llm_client():
    """模拟 LLM 客户端（不发起真实 API 调用）"""
    client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"complexity": "simple", "question_type": "worldview", "entities": ["源石"], "time_scope": "cross_arc", "reason": "简单事实查询"}'
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    client.chat.completions.create.return_value = mock_response
    return client


@pytest.fixture
def temp_data_dir():
    """临时数据目录，包含最小 wiki 数据"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建子目录
        concepts_dir = os.path.join(tmpdir, "extractions", "v3_wiki", "concepts")
        factions_dir = os.path.join(tmpdir, "extractions", "v3_wiki", "factions")
        locations_dir = os.path.join(tmpdir, "extractions", "v3_wiki", "locations")
        characters_dir = os.path.join(tmpdir, "extractions", "v2_characters")
        events_dir = os.path.join(tmpdir, "extractions", "v1_events", "main")
        stories_dir = os.path.join(tmpdir, "stories", "main", "黑暗时代·上")

        for d in [concepts_dir, factions_dir, locations_dir, characters_dir, events_dir, stories_dir]:
            os.makedirs(d, exist_ok=True)

        # 写入示例数据
        with open(os.path.join(concepts_dir, "源石.md"), "w", encoding="utf-8") as f:
            f.write("# 源石\n\n**分类:** 自然现象/物质\n\n**定义:** 泰拉世界一种蕴含巨大能量的矿物。\n\n## 概述\n\n源石是泰拉世界最核心的能源。也是矿石病的病原体。\n")

        with open(os.path.join(concepts_dir, "矿石病.md"), "w", encoding="utf-8") as f:
            f.write("# 矿石病\n\n**分类:** 自然现象/物质\n\n**定义:** 由源石感染引发的致命疾病。\n\n## 概述\n\n矿石病是泰拉世界的绝症。\n")

        with open(os.path.join(factions_dir, "罗德岛.md"), "w", encoding="utf-8") as f:
            f.write("# 罗德岛\n\n**分类:** 势力/组织\n\n**定义:** 致力于解决感染者问题的医药公司。\n\n## 概述\n\n罗德岛表面为制药公司，实际致力于解决感染者问题。\n")

        with open(os.path.join(locations_dir, "切尔诺伯格.md"), "w", encoding="utf-8") as f:
            f.write("# 切尔诺伯格\n\n**分类:** 城市/移动城市\n\n**定义:** 乌萨斯帝国的主要移动城市之一。\n\n## 概述\n\n切尔诺伯格是乌萨斯帝国的主要移动城市。\n")

        with open(os.path.join(characters_dir, "Amiya.json"), "w", encoding="utf-8") as f:
            json.dump({
                "name": "Amiya",
                "display_name": "阿米娅",
                "summary": "罗德岛公开领袖。",
                "personality": "认真、温柔、坚强。",
            }, f, ensure_ascii=False)

        with open(os.path.join(events_dir, "黑暗时代·上.json"), "w", encoding="utf-8") as f:
            json.dump({
                "summary": "博士苏醒，整合运动袭击。",
                "events": [
                    {"event": "博士在切尔诺伯格苏醒。", "type": "revelation", "line_range": [1, 78], "participants": ["阿米娅", "博士"], "location": "切尔诺伯格", "is_imaginary": False},
                ],
            }, f, ensure_ascii=False)

        with open(os.path.join(stories_dir, "main_01_01.json"), "w", encoding="utf-8") as f:
            json.dump({
                "id": "main_01_01",
                "chapter": "黑暗时代·上",
                "lines": [
                    {"type": "dialogue", "speaker": "阿米娅", "text": "博士，您醒了吗？"},
                ],
            }, f, ensure_ascii=False)

        # 写 timeline
        timeline_dir = os.path.join(tmpdir, "extractions", "v3_wiki")
        os.makedirs(timeline_dir, exist_ok=True)
        with open(os.path.join(timeline_dir, "timeline.md"), "w", encoding="utf-8") as f:
            f.write("# 泰拉历史时间线\n\n## 797\n\n**七城联邦建成第一座移动城市**\n\n")

        yield tmpdir
