"""Agent 双轨切换测试（W3: ARKNIGHTS_USE_MCP=1 → 工具走 MCP，失败回退内部函数）"""
import os
from unittest.mock import patch

import pytest

from arknights_wiki.agent.tools import _make_mcp_executor, _mcp_tool_map


class TestMcpToolMap:
    def test_all_tools_mapped(self):
        mapping = _mcp_tool_map()
        assert set(mapping) == {
            "search_wiki", "get_entity_page", "search_events", "search_dialogue",
            "search_timeline", "get_chapter_summary", "semantic_search", "lookup_entity_index",
        }

    def test_entity_page_arg_adapt(self):
        _, adapt = _mcp_tool_map()["get_entity_page"]
        assert adapt({"name": "罗德岛", "entity_type": "faction"}) == {
            "query": "罗德岛", "category": "faction",
        }

    def test_chapter_adapt(self):
        _, adapt = _mcp_tool_map()["get_chapter_summary"]
        assert adapt({"chapter": "第九章"}) == {"chapter": "第九章", "limit": 15}


class TestMakeMcpExecutor:
    def test_fallback_to_internal_when_mcp_disabled(self, temp_data_dir):
        """get_mcp_client 返回 None（未启用）→ 直接走内部函数"""
        def internal(**kwargs):
            return "internal-result"

        executor = _make_mcp_executor("search_wiki", internal)
        with patch("arknights_wiki.agent.tools._mcp_tool_map",
                   return_value={"search_wiki": ("search_entities", lambda a: a)}):
            with patch("arknights_wiki.mcp_server.client.get_mcp_client", return_value=None):
                assert executor(query="罗德岛") == "internal-result"

    def test_mcp_call_used_when_enabled(self, temp_data_dir):
        """MCP 启用时调用 MCP client"""
        def internal(**kwargs):
            return "internal-result"

        class _FakeClient:
            def call_tool_traced(self, name, args):
                return f"mcp-{name}-{args}"

        executor = _make_mcp_executor("search_wiki", internal)
        with patch("arknights_wiki.mcp_server.client.get_mcp_client", return_value=_FakeClient()):
            result = executor(query="罗德岛")
        assert result == "mcp-search_entities-{'query': '罗德岛'}"

    def test_mcp_failure_falls_back_to_internal(self, temp_data_dir):
        """MCP 调用抛异常 → 回退内部函数并标注"""
        def internal(**kwargs):
            return "internal-result"

        class _BrokenClient:
            def call_tool_traced(self, name, args):
                raise ConnectionError("mcp down")

        executor = _make_mcp_executor("search_wiki", internal)
        with patch("arknights_wiki.mcp_server.client.get_mcp_client", return_value=_BrokenClient()):
            result = executor(query="罗德岛")
        assert "回退内部函数" in result
        assert "internal-result" in result
