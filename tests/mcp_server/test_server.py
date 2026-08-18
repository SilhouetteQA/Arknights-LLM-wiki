"""MCP Server 工具函数单测（W3，直接调用 async 工具，不走子进程）"""
import asyncio
from unittest.mock import patch

from arknights_wiki.mcp_server.server import (
    query_relationship,
    query_timeline,
    search_entities,
    search_events,
    search_story,
)


def _run(coro):
    return asyncio.run(coro)


class TestSearchEntities:
    def test_found_faction(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(search_entities("罗德岛", category="faction", limit=3))
        assert "罗德岛" in result
        assert "[1]" in result

    def test_not_found(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(search_entities("不存在的实体XYZ", limit=3))
        assert "未找到" in result

    def test_related_supplement(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(search_entities("罗德岛", limit=2))
        # 实体索引存在时补充 [关联]
        assert isinstance(result, str)


class TestSearchEvents:
    def test_found_by_entity(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(search_events(entity="阿米娅", limit=3))
        assert "事件" in result or "找到" in result

    def test_not_found(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(search_events(entity="不存在角色", limit=3))
        assert "未找到" in result


class TestQueryRelationship:
    def test_found(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(query_relationship("阿米娅"))
        assert isinstance(result, str)

    def test_not_found(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(query_relationship("不存在实体"))
        assert "未在索引中找到" in result


class TestQueryTimeline:
    def test_found(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(query_timeline("移动城市", limit=3))
        assert "797" in result or "找到" in result

    def test_empty_query_still_returns(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(query_timeline("", limit=3))
        assert isinstance(result, str)


class TestSearchStory:
    def test_found(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(search_story("博士", limit=3))
        assert "博士" in result

    def test_not_found(self, temp_data_dir):
        with patch("arknights_wiki.mcp_server.server._data_dir", return_value=temp_data_dir):
            result = _run(search_story("不存在的对话关键词XYZ", limit=3))
        assert "未在剧情对话中找到" in result
