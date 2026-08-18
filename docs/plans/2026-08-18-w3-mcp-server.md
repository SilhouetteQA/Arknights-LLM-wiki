# W3 — MCP Server 实施计划（2026-08-18）

> 依据：docs/specs/2026-08-18-w3-mcp-server.md
> 规则：CLAUDE.md U-05 / U-03 / U-04 + 第六章升级工作流；TDD
> 依赖：mcp==2.0.0 已安装

## 任务分解

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| T1 | MCP Server（MCPServer + 5 工具 + 冒烟） | `arknights_wiki/mcp_server/__init__.py` + `server.py` + 冒烟脚本 | 无 |
| T2 | MCP Client 同步封装 + resilience 接入 | `arknights_wiki/mcp_server/client.py` | T1 |
| T3 | Agent 双轨切换（tools.py ARKNIGHTS_USE_MCP） | tools.py 改造 + 映射表 | T2 |
| T4 | 测试补全 | server 单测 / client 集成 / 双轨测试 | T1-T3 |
| T5 | 验证：独立启动 + 真实问答 + trace + 评测 A/B | 验收脚本 + 10 题对比 | T4 |
| T6 | 收尾：devlog + 路线图 + commit | — | T5 |

## 里程碑

- M1（T2）：server 冒烟通过，client 可调用 5 工具
- M2（T3）：Agent 双轨可切换
- M3（T5）：真实问答 + 评测 A/B 完成
- M4（T6）：devlog/路线图/commit

## 关键实现细节

1. **server.py**：`MCPServer("arknights-knowledge", version="0.1.0")`；工具用 `@server.tool(name=, description=)`；
   工具函数 `async def`；复用 `retrieval.py` Store；`if __name__ == "__main__": server.run(transport="stdio")`
2. **client.py**：`StdioServerParameters(command=sys.executable, args=["-m", "arknights_wiki.mcp_server.server"], env={**os.environ})`；
   `call_tool` 内 `asyncio.run(_call(...))`：`async with stdio_client(...) as (r, w): async with ClientSession(r, w) as s: await s.initialize(); return await s.call_tool(...)`
   - 结果解析：call_tool 返回 `CallToolResult`，取 `content[0].text`
   - W2 恢复链：`execute_with_resilience` 包住整个 asyncio.run（重试 2 次，retryable=(Exception,)）
   - trace：`traced(name="mcp_call", as_type="tool")` + metadata_fn 记录 mcp_tool/retries
3. **tools.py 双轨**：`_build_tool_executors()` 检测 `ARKNIGHTS_USE_MCP=1` → `_mcp_wrapper(tool_name)`；
   映射表 `_MCP_TOOL_MAP = {agent_tool: (mcp_tool, adapt_fn)}`；包装器懒加载 `get_mcp_client()`，
   失败时 fallback 回内部函数（双保险：MCP 挂 → 内部函数），日志标注
4. **测试**：
   - `tests/mcp_server/test_server.py`：直接调用 server 模块的工具函数（await）→ 断言返回文本
   - `tests/mcp_server/test_client.py`：真实 stdio 子进程 + call_tool（temp_data_dir 环境变量）→ 5 工具各一次
   - `tests/agent/test_mcp_dual_track.py`：ARKNIGHTS_USE_MCP=1 时 search_wiki 走 MCP 且失败回退内部函数
5. **评测 A/B**：`ARKNIGHTS_USE_MCP=1 python -m arknights_wiki.eval.runner --bench ... --limit 10 --out output/eval/w3_mcp`，
   对比 `output/eval/w2_regression/report_v1.md`（同 10 题内部函数路径）

## 验证清单

- [ ] 冒烟：client list_tools 5 工具 + 各工具一次调用
- [ ] `pytest tests/mcp_server/ tests/agent/test_mcp_dual_track.py` 全绿
- [ ] 全量 pytest 无新增失败
- [ ] ARKNIGHTS_USE_MCP=1 真实 complex 问答 + trace 可见 mcp_call
- [ ] 10 题 A/B：MCP 路径 overall vs 内部路径 ≥ -0.03
