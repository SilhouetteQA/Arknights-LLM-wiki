"""Agent Tools 测试"""
import os
from unittest.mock import patch

from arknights_wiki.agent.tools import (
    search_wiki,
    get_entity_page,
    search_events,
    search_dialogue,
    search_timeline,
    get_chapter_summary,
    semantic_search_tool,
    lookup_entity_index,
    TOOL_DEFINITIONS,
    TOOL_EXECUTORS,
)


class TestSearchWiki:
    def test_search_returns_string(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_wiki("源石")
            assert isinstance(result, str)
            assert len(result) > 0

    def test_search_no_results(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_wiki("不存在的实体名称xyz123")
            assert isinstance(result, str)


class TestGetEntityPage:
    def test_get_existing_concept(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = get_entity_page("源石", "concept")
            assert "源石" in result

    def test_get_nonexistent(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = get_entity_page("不存在", "concept")
            assert "未找到" in result


class TestSearchEvents:
    def test_search_by_entity(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_events(entity="阿米娅")
            assert isinstance(result, str)


class TestSearchDialogue:
    def test_search_dialogue(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_dialogue("博士")
            assert isinstance(result, str)


class TestTimeline:
    def test_search_timeline(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_timeline("移动城市")
            assert isinstance(result, str)


class TestChapterSummary:
    def test_get_summary(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = get_chapter_summary("黑暗时代·上")
            assert isinstance(result, str)


class TestSemanticSearchTool:
    def test_returns_error_when_no_index(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = semantic_search_tool("源石")
            assert isinstance(result, str)


class TestLookupEntityIndex:
    """lookup_entity_index 工具测试"""

    def test_lookup_missing_entity(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = lookup_entity_index("不存在的实体XYZ")
            assert "未在索引中找到" in result

    def test_tool_in_definitions(self):
        tool_names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert "lookup_entity_index" in tool_names

    def test_tool_in_executors(self):
        assert "lookup_entity_index" in TOOL_EXECUTORS
