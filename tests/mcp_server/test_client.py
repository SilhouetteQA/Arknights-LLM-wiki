"""MCP Client 集成测试（W3，真实 stdio 子进程 + temp 数据目录）"""
import os

import pytest

from arknights_wiki.mcp_server.client import ArknightsMcpClient

pytestmark = pytest.mark.mcp_integration


@pytest.fixture
def mcp_client(temp_data_dir):
    """指向临时数据目录的 MCP client（子进程继承 env）"""
    env = {**os.environ, "ARKNIGHTS_DATA_DIR": temp_data_dir}
    return ArknightsMcpClient(env=env)


class TestClientTools:
    def test_search_entities(self, mcp_client):
        result = mcp_client.call_tool("search_entities", {"query": "罗德岛", "limit": 3})
        assert "罗德岛" in result

    def test_search_events(self, mcp_client):
        result = mcp_client.call_tool("search_events", {"entity": "阿米娅", "limit": 3})
        assert isinstance(result, str)

    def test_query_relationship(self, mcp_client):
        result = mcp_client.call_tool("query_relationship", {"entity_name": "阿米娅"})
        assert isinstance(result, str)

    def test_query_timeline(self, mcp_client):
        result = mcp_client.call_tool("query_timeline", {"query": "移动城市", "limit": 3})
        assert isinstance(result, str)

    def test_search_story(self, mcp_client):
        result = mcp_client.call_tool("search_story", {"query": "博士", "limit": 3})
        assert isinstance(result, str)

    def test_unknown_tool_raises(self, mcp_client):
        with pytest.raises(Exception):
            mcp_client.call_tool("not_a_tool", {})
