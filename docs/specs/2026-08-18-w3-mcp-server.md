# W3 — MCP Server 包装知识库设计规格（2026-08-18）

> 依据：《01_现有明日方舟LLM_Wiki项目评估与升级方案.md》§6（MCP）+ §14 最终架构
> 规则：CLAUDE.md U-05（MCP 优先接入）+ U-03（评测优先）+ 第六章升级工作流
> 前置：W0 ✅（基线 0.857）· W1 ✅（trace）· W2 ✅（resilience/checkpoint）
> 用户决策（2026-08-18）：P1（W5–W9）跳过；本窗口只做 W3，Agent 走 MCP 采用双轨可切换

---

## 1. 背景与目标

### 1.1 背景

当前 Agent 的 8 个检索工具直接调用内部函数（`tools.py TOOL_EXECUTORS` → `retrieval.py` Store），
能力与进程强耦合。升级方案 §6 要求：知识库包装为标准 MCP Server，Agent 通过标准化工具协议
访问外部能力，证明 Tool Protocol 能力。

### 1.2 目标

1. `arknights_wiki/mcp_server/` 提供独立可启动的 MCP Server（stdio），暴露 5 个只读工具：
   `search_entities / search_events / query_relationship / query_timeline / search_story`
2. 工具 schema（输入/输出）完整定义（Pydantic 类型注解 → MCP JSON Schema）
3. Agent 侧双轨：`ARKNIGHTS_USE_MCP=1` 时 8 个现有工具切换到 MCP client 调用（工具名/签名不变，LLM 无感知）
4. MCP 路径与内部函数路径评测可 A/B 对比（U-03）
5. 复用 W2 resilience：MCP 工具调用同样走恢复链（网络类异常重试）
6. MCP 调用在 Langfuse trace 可见（W1 U-04）

---

## 2. 现状分析

- 检索层接口（`agent/retrieval.py`）：`WikiStore.search/get_page`、`EventStore.search/get_chapter_summary`、
  `DialogueStore.search`、`TimelineStore.search`、`EntityIndexStore.lookup/get_source_chapters` — 全部同步、只读
- 数据目录：`DATA_DIR`（`ARKNIGHTS_DATA_DIR` 可覆盖，测试用临时目录）
- 依赖：`mcp==2.0.0` 已安装（项目环境 D:\CodexPython312）
  - Server: `MCPServer` + `@server.tool()`（async 工具函数），`server.run(transport="stdio")`
  - Client: `stdio_client(StdioServerParameters)` → `ClientSession` → `call_tool()`（async）
- 环境变量约定：`ARKNIGHTS_*` 前缀（W2 已用 `ARKNIGHTS_TOOL_*` / `ARKNIGHTS_LLM_*` / `ARKNIGHTS_CHECKPOINT`）

---

## 3. 技术方案

### 3.1 包结构

```
arknights_wiki/mcp_server/
├── __init__.py        # 导出 create_server / get_mcp_client / TOOL_MAP
├── server.py          # MCPServer 定义 + 5 个工具（`python -m arknights_wiki.mcp_server.server` 启动）
└── client.py          # MCP client 同步封装（stdio 子进程 + ClientSession + asyncio.run 生命周期）
```

### 3.2 MCP Server：5 个工具（只读）

| 工具 | 参数（类型注解 → JSON Schema） | 后端 |
|------|-------------------------------|------|
| `search_entities` | `query: str`（必填）、`category: str\|None`（concept/faction/location/character）、`limit: int=10` | `WikiStore.search` + `EntityIndexStore.lookup` 补充关联信息 |
| `search_events` | `entity/event_type/chapter: str\|None`、`limit: int=15` | `EventStore.search` |
| `query_relationship` | `entity_name: str`（必填） | `EntityIndexStore.lookup`（关联实体/阵营/地点/角色 + 出现章节） |
| `query_timeline` | `query: str\|None`、`limit: int=10` | `TimelineStore.search` |
| `search_story` | `query: str`（必填）、`chapter: str\|None`、`limit: int=10` | `DialogueStore.search`（原始对话） |

- 全部返回 `str`（与现有工具输出风格一致，LLM 可直接消费）
- 工具函数内复用 `_get_data_dir()`（`ARKNIGHTS_DATA_DIR` 覆盖）
- **只读**：无任何写操作（对齐 W8 权限分级概念，本窗口不做权限系统）

### 3.3 MCP Client（同步封装）

`client.py` 设计：
- `ArknightsMcpClient`：启动命令 `[sys.executable, "-m", "arknights_wiki.mcp_server.server"]`，
  env 继承 os.environ；`call_tool(name, arguments) -> str` 同步接口
- 每次 `call_tool` 用 `asyncio.run()` 完成完整生命周期（stdio_client → initialize → call_tool → 关闭），
  实现简单、无事件循环线程管理（Agent 工具调用秒级，~100ms 进程开销可接受）
- 模块级懒加载单例 `get_mcp_client()`；`ARKNIGHTS_USE_MCP != 1` 时不初始化
- **W2 恢复链接入**：`call_tool` 的进程启动/网络异常经 `execute_with_resilience`
  （`retryable_exceptions=(APIConnectionError 类 + TimeoutError + OSError)`，默认重试 2 次）

### 3.4 Agent 双轨切换（tools.py）

`TOOL_EXECUTORS` 构建时检测 `ARKNIGHTS_USE_MCP=1` → 对每个工具生成 MCP 包装执行器（懒加载 client）：

| Agent 工具（内部函数） | MCP 工具 | 参数适配 |
|------------------------|----------|----------|
| search_wiki(query, category) | search_entities | 直传 |
| get_entity_page(name, entity_type) | search_entities | `{query: name, category: entity_type}` |
| search_events(entity, event_type, chapter) | search_events | 直传 |
| search_dialogue(query, chapter) | search_story | 直传 |
| search_timeline(query) | query_timeline | 直传 |
| get_chapter_summary(chapter) | search_events | `{chapter: chapter, limit: 15}`（章节事件列表近似摘要） |
| semantic_search(query, top_k) | search_entities | `{query: query}`（关键词近似语义搜索，无 FAISS） |
| lookup_entity_index(entity_name) | query_relationship | 直传 |

- 工具名/LLM 可见定义不变 → 双轨 A/B 只影响"执行后端"，prompt 与路由零改动
- 映射近似性写入注释与 devlog（semantic_search / get_chapter_summary 为近似降级）

### 3.5 trace 集成（U-04）

- MCP client 调用包 `traced(name="mcp_call", as_type="tool")` span，
  metadata：`mcp_tool` / `args` / `latency_ms` / `retries`（W2 stats）
- 与现有 `tool_call` span 嵌套关系：`tool_call(agent 工具) → mcp_call(MCP 工具)`，Langfuse 层级可见

### 3.6 评测 A/B（U-03）

- 内部函数路径：现有 runner（基线 report_v1_mimo.md）
- MCP 路径：`ARKNIGHTS_USE_MCP=1` 跑同一子集 → 对比 overall/correctness/faithfulness
- 本次验证跑 10 题 complex 子集（同 W2 回归集），目标：MCP 路径不显著回落（≥ -0.03）

---

## 4. 验收标准（对齐路线图 W3）

1. **独立启动**：`python -m arknights_wiki.mcp_server.server` stdio 模式正常启动，
   client `list_tools` 返回 5 个工具，schema 含参数描述与必填
2. **Agent 走 MCP 真实问答**：`ARKNIGHTS_USE_MCP=1` 跑 1 次 complex 问答（真实 LLM），
   回答正常产出，trace 可见 `tool_call → mcp_call` 层级
3. **评测不回归**：10 题子集 MCP 路径 vs 内部函数路径指标对比无显著回落
4. **测试**：server 工具单测 + client 集成测试（temp_data_dir）+ 双轨切换测试全绿；
   全量 pytest 无新增失败
5. **可开关**：未设置 `ARKNIGHTS_USE_MCP` 时行为与现状完全一致

---

## 5. 风险与取舍

| 风险 | 影响 | 缓解 |
|------|------|------|
| mcp 2.0 API 与文档示例差异 | 实施受阻 | 已确认 MCPServer/stdio_client/ClientSession 签名；先冒烟再铺开 |
| stdio 子进程每次调用开销（~100ms） | 单次工具调用变慢 | Agent 工具调用本身秒级；评测对比可见成本；后续可长驻 session |
| 双轨映射近似（semantic_search 等） | MCP 路径质量可能略降 | 标注近似性；评测 A/B 量化，回落超阈值则保留内部函数为默认 |
| Windows stdio 子进程中文路径 | 启动失败 | 启动命令用 sys.executable + -m 模块（避免脚本路径）；env 显式 UTF-8 |
| ClientSession async 与同步线程 | 事件循环冲突 | asyncio.run() 每调用独立 loop（Python 3.12 线程独立 loop，安全） |

---

## 6. 范围外

- MCP 权限分级/鉴权（W8 已跳过，工具全只读）
- SSE / streamable-http 传输（本地 stdio 足够）
- MCP resources/prompts（仅 tools）
- 远程 MCP 服务器（后续可扩展）
