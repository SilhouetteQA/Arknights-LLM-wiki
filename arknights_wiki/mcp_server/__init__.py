"""MCP Server 包（W3）

对外 API: create_server（server.py）/ get_mcp_client（client.py，ARKNIGHTS_USE_MCP=1 时启用）
"""
from arknights_wiki.mcp_server.client import ArknightsMcpClient, get_mcp_client
from arknights_wiki.mcp_server.server import server as create_server

__all__ = ["create_server", "ArknightsMcpClient", "get_mcp_client"]
