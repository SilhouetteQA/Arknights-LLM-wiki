"""Arknights 知识库 MCP 客户端（W3 MCP Server）

同步封装（Agent 工具在 executor 线程调用，无需事件循环线程管理）:
  - 每次 call_tool 用 asyncio.run() 完成 stdio 子进程生命周期
  - W2 resilience: 进程启动/调用异常经 execute_with_resilience 重试
  - trace: mcp_call tool span（mcp_tool/args/retries）
  - 懒加载单例 get_mcp_client()，仅 ARKNIGHTS_USE_MCP=1 时初始化
"""
from __future__ import annotations

import asyncio
import os
import sys
import time as time_mod

from arknights_wiki.agent.resilience import (
    ResilienceConfig,
    execute_with_resilience,
)

_USE_MCP = os.environ.get("ARKNIGHTS_USE_MCP") == "1"

_MCP_RESILIENCE_CONFIG = ResilienceConfig(
    timeout_seconds=float(os.environ.get("ARKNIGHTS_MCP_TIMEOUT", "30")),
    max_retries=int(os.environ.get("ARKNIGHTS_MCP_MAX_RETRIES", "2")),
    backoff_base=1.0,
    backoff_max=8.0,
    breaker_threshold=0,  # MCP 子进程故障由 Agent 工具 fallback 处理，不开熔断
)

_client_instance: "ArknightsMcpClient | None" = None


class ArknightsMcpClient:
    """MCP stdio 客户端（同步接口）"""

    def __init__(self, command: str | None = None, args: list[str] | None = None,
                 env: dict | None = None):
        self._command = command or sys.executable
        self._args = args or ["-m", "arknights_wiki.mcp_server.server"]
        self._env = {**os.environ, **(env or {})}

    # ---- 内部 async 生命周期 ----

    async def _call_tool_async(self, name: str, arguments: dict) -> str:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self._command, args=self._args, env=self._env,
            cwd=os.getcwd(),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=arguments)
                if result.is_error:
                    raise RuntimeError(
                        f"MCP 工具 {name} 返回错误: "
                        f"{result.content[0].text if result.content else 'unknown'}"
                    )
                if not result.content:
                    return ""
                # 取第一个 text 块
                texts = [c.text for c in result.content if hasattr(c, "text")]
                return "\n".join(texts) if texts else str(result.content)

    # ---- 同步入口 ----

    def call_tool(self, name: str, arguments: dict | None = None) -> str:
        """同步调用 MCP 工具（带 W2 恢复链重试）"""
        arguments = arguments or {}
        t0 = time_mod.time()

        def _do_call():
            return asyncio.run(self._call_tool_async(name, arguments))

        result, stats = execute_with_resilience(
            _do_call, (), {}, _MCP_RESILIENCE_CONFIG,
        )
        # W2 stats 供 trace 埋点
        self._last_stats = stats
        self._last_latency_ms = round((time_mod.time() - t0) * 1000, 1)
        return result

    def call_tool_traced(self, name: str, arguments: dict | None = None) -> str:
        """带 trace 的调用（mcp_call tool span + W2 恢复统计）"""
        arguments = arguments or {}
        from arknights_wiki.observability import get_client

        c = get_client()
        if c is None:
            return self.call_tool(name, arguments)
        with c.start_as_current_observation(
            name="mcp_call",
            as_type="tool",
            metadata={"mcp_tool": name, "args": arguments},
        ) as _obs:
            result = self.call_tool(name, arguments)
            try:
                meta = {
                    "mcp_tool": name,
                    "latency_ms": getattr(self, "_last_latency_ms", 0),
                    "result_len": len(result),
                }
                stats = getattr(self, "_last_stats", {})
                for key in ("retries", "breaker_state", "fallback_used", "error"):
                    if stats.get(key) not in (None, "", 0):
                        meta[key] = stats[key]
                c.update_current_span(metadata=meta)
            except Exception:  # noqa: BLE001 — 观测层失败不影响业务
                pass
            return result


def get_mcp_client() -> ArknightsMcpClient | None:
    """懒加载单例；ARKNIGHTS_USE_MCP != 1 时返回 None"""
    global _client_instance
    if not _USE_MCP:
        return None
    if _client_instance is None:
        _client_instance = ArknightsMcpClient()
    return _client_instance
