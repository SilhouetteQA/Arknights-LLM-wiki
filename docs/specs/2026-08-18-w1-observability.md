# W1 — Observability / Tracing 设计规格（2026-08-18）

> 依据：《01_现有明日方舟LLM_Wiki项目评估与升级方案.md》§8（Observability/Tracing）+ §14 最终架构
> 规则：CLAUDE.md U-04（全链路可观测）+ 第六章升级工作流
> 前置：W0 已完成（100 题 Benchmark 基线 report_v1_mimo.md overall 0.857）

---

## 1. 背景与目标

### 1.1 背景

当前项目只有 `stats/collector.py`（开发期成本统计）和 `eval/cost_log.jsonl`（评测成本日志），
没有任何运行期可观测设施：一次问答内部的 Router / Retrieval / Tool Call / LLM Call 无法事后复盘，
出问题时只能靠前端 SSE 事件流或重新跑一遍。

升级方案 §8 要求：每次 Agent 执行产出完整 Trace（User Request → Planner → Agent Handoff →
Retrieval → Tool Call → LLM Call → Retry → Critic → Final Answer），每步记录
latency / tokens / model / tool / error / retry / cost。

### 1.2 用户决策（2026-08-18 确认）

| 决策项 | 选择 |
|--------|------|
| Langfuse 部署方式 | **本地 Docker 部署**（Docker Desktop 已安装于 `D:\Docker`，daemon 当前未启动，实施时先启动） |
| 埋点技术 | **Langfuse Python SDK v4**（`@observe()` 装饰器 + `get_client()`，OTel 基础） |

### 1.3 目标

- 任意一次问答（simple 与 complex 两条路径）在 Langfuse UI 可导出完整 trace 树
- trace 树覆盖：User Request → Router → Retrieval → Tool Call → LLM Call → Final Answer
- 每步记录：latency / input+output tokens / model / tool / error / retry / cost
- 埋点**可开关、不侵入业务逻辑**：未配置环境变量时行为与现状完全一致
- 与 `output/devlog.md` 成本汇总对接（CLAUDE.md 1.4 节监控表）
- 评测跑批（eval runner）可选开启 trace，便于事后复盘 Benchmark 问题题

---

## 2. 现状分析

### 2.1 一次问答的调用链（已通读代码确认）

```
POST /chat (server.py)
  └─ route_query (router.py)                    # 本地规则 + LLM 兜底（_llm_intent_rewrite）
       ├─ simple → simple_search (simple_search.py)
       │    ├─ search_and_collect                # 多层检索
       │    │    ├─ WikiStore/EventStore/DialogueStore/TimelineStore (retrieval.py)
       │    │    └─ FAISS semantic_search (vector_index.py)
       │    └─ LLM 回答生成 (client.chat.completions.create)
       └─ complex → LangGraph (graph.py)
            ├─ call_model  × N 次 (≤8)           # LLM 带 tools 调用
            ├─ tool_node   × N 次                 # 执行 8 个工具 (tools.py TOOL_EXECUTORS)
            └─ synthesize_node                    # LLM 最终回答
```

### 2.2 LLM 调用统一入口

所有 Agent 侧 LLM 调用都经过 `extraction/llm_client.py`：
- `chat_completion()` — graph / simple_search 回答 / 评测跑批
- `_llm_intent_rewrite()` 内部直接 `client.chat.completions.create`（router.py）
- `call_llm()` — 提取管线专用（带重试）

→ **在 `chat_completion` 一处包装，可覆盖绝大部分运行期 LLM 调用**；router 内的直接调用单独补埋。

### 2.3 环境现状

- 项目运行环境：`D:\CodexPython312\python.exe`（fastapi 0.136 / langgraph 1.2.6 / openai 2.38 / sse-starlette 3.4）
- **langfuse / opentelemetry 未安装**
- Docker Desktop 已安装于 `D:\Docker\Docker Desktop.exe`（**daemon 未运行**，docker CLI 29.7.2 + compose v5.3.1 可用）
- 项目无 `.venv`，依赖以 `pyproject.toml` 声明（`agent` extra），实际环境手动管理

---

## 3. 技术方案

### 3.1 Langfuse 本地部署（Docker）

- 用官方 compose（Langfuse v3，`langfuse/langfuse:3`）：`langfuse-web` + `langfuse-worker` + `postgres:16` + `clickhouse` + `redis:7` + `minio`
- compose 文件置于 `docker/langfuse/docker-compose.yml`（仓库内提交，secrets 用 `.env` 文件，`.env` 不提交）
- 端口：`3000`（Web UI + SDK ingest endpoint）
- 首次启动：浏览器 `http://localhost:3000` 注册账号 → 创建项目 → 复制 Public Key / Secret Key
- SDK 环境变量：`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL=http://localhost:3000`
- 密钥持久化：写入项目根 `.env`（gitignore 已有排除）或由用户在 shell 设置

### 3.2 埋点架构：`arknights_wiki/observability/` 新包

```
arknights_wiki/observability/
├── __init__.py        # 导出 get_client / traced / is_enabled / flush
├── client.py          # 客户端初始化 + 全局开关（懒加载，未配置时不初始化）
├── decorators.py      # traced() 可开关装饰器（包装 langfuse observe）
└── schema.py          # trace 树结构约定（节点类型、metadata 字段、成本计算）
```

**设计要点：**

1. **全局开关**：`is_enabled()` = `LANGFUSE_PUBLIC_KEY && LANGFUSE_SECRET_KEY && LANGFUSE_BASE_URL` 三者齐备
   且 `ARKNIGHTS_TRACING != "0"`。未启用时 `traced()` 直接返回原函数（零开销 no-op）。
2. **`traced(name, as_type="span"|"generation", metadata_fn=None)`**：包装 `langfuse.observe`。
   - 运行期开关（SDK v4 的 `@observe` 在未初始化 client 时是 no-op，但为明确可测，自定义开关更稳）
   - 支持在 span 上挂 `update_current_span()` 补充字段（cost / retry / error 等）
3. **LLM 调用统一埋点**：在 `llm_client.chat_completion` 内用 `traced(as_type="generation")` 包装，
   usage（prompt_tokens / completion_tokens）、model 从 response 提取后 `update_current_span()` 写入；
   cost 按 `eval/pricing.json` 单价计算（RMB），与现有 `stats/_estimate_cost` 口径一致。
4. **trace 根**：`server.py /chat` 用 `traced(name="chat_request")` 作为根（或手动 `start_as_current_observation`），
   metadata 记录 `question / complexity / question_type / entities / benchmark_id(评测时)`。
5. **Retry 记录**：现状仅 `call_llm`（提取管线）有重试；在 `chat_completion` 统一埋点中把
   单次调用包一层 span，`metadata.retry` 记录（当前恒 0，W2 恢复链落地后自动扩展）。
6. **成本口径**：RMB（¥），沿用 `eval/pricing.json` + `compute_cost`；Langfuse 自带 USD 模型价目，
   我们不依赖其自动计价，统一自己计算写入 metadata（保证与 devlog 成本汇总一致）。

### 3.3 埋点清单（Trace 结构）

| 节点 | 类型 | 位置 | 记录字段 |
|------|------|------|----------|
| `chat_request` | trace 根 | server.py `/chat` | question, complexity, question_type, entities, latency, error, benchmark_id |
| `router` | span | router.py `route_query` | source(local/llm), entities, time_scope, reason, latency |
| `intent_rewrite_llm` | generation | router.py `_llm_intent_rewrite` | model, tokens, cost, latency |
| `simple_search` | span | simple_search.py 主函数 | latency, n_sources |
| `retrieval` | span | search_and_collect / 各 Store | tool/层名, query, n_hits, latency |
| `faiss_search` | span | vector_index.semantic_search | top_k, n_hits, latency |
| `answer_generation` | generation | simple_search 回答 / graph synthesize | model, tokens, cost, latency |
| `agent_call_model` | span+generation | graph.py `call_model` | iteration, model, tokens, tool_calls 数, latency |
| `tool_call` | span | graph.py `tool_node` 内每个工具 | tool, args, result 摘要, latency, error |
| `synthesize` | span+generation | graph.py `synthesize_node` | model, tokens, cost, latency |

> 注：Planner / Critic / Retry 链在 W2/W4 落地，本规格在 schema 中预留 `node_type` 字段，
> 未来节点直接接入，无需改动既有埋点。

### 3.4 评测对接（eval runner）

- `runner.py` 增加环境变量感知：`ARKNIGHTS_TRACING=1` 时跑批开启 trace，
  每题一个 trace，`metadata.benchmark_id = item["id"]`、`metadata.mode = direct|http`
- 便于事后在 Langfuse UI 按 benchmark_id 过滤复盘（如 event_complex_003 空回答类问题）
- 默认不开启（不改变评测行为，U-03 评测优先不回归）

### 3.5 devlog 成本汇总对接

- 新增脚本 `scripts/trace_cost_summary.py`（或并入 observability CLI）：
  拉取最近 N 小时 trace 成本，输出 `output/observability/cost_summary.md` 供 devlog 引用
- 与现有 `stats.jsonl` / `cost_log.jsonl` 三轨并存，不删除旧机制

---

## 4. 验收标准（对齐路线图 W1）

1. **完整 trace 树**：simple + complex 各一次问答，Langfuse UI 可见
   `chat_request → router → (retrieval → answer_generation | agent_call_model → tool_call → synthesize)` 层级结构
2. **字段齐全**：抽查任意 span/generation，含 latency / tokens / model / tool / error / retry / cost
3. **可开关不侵入**：未配置 `LANGFUSE_*` 时全量 pytest 通过、行为与现状一致（无网络调用、无 trace 写入）
4. **评测可选开启**：`ARKNIGHTS_TRACING=1` 跑 2-3 题，UI 可按 benchmark_id 过滤
5. 成本汇总脚本可输出 devlog 可引用的摘要

---

## 5. 风险与取舍

| 风险 | 影响 | 缓解 |
|------|------|------|
| Docker daemon 未启动 | 无法部署 | 实施时先启动 Docker Desktop（`D:\Docker\Docker Desktop.exe`），必要时请用户协助 |
| Langfuse v3 六容器内存占用（ClickHouse 最重） | 本机资源吃紧 | compose 限制 ClickHouse/RDBMS 内存；本机 8GB+ 可运行；必要时降级 v2（仅 postgres，功能少） |
| langfuse SDK v4 与 openai 2.38 兼容性 | 埋点失败 | 先做冒烟：单次 chat_completion 出 trace 再铺开 |
| langgraph 1.2.6 无官方 instrumentation | 需手动埋点 | 用 `traced()` 包装节点函数，已验证可行 |
| trace 数据含用户问题/检索原文 | 数据体积与隐私 | 检索原文截断（与前端一致 ≤1000 字符）；本项目本地单用户，风险低 |
| 与现有 stats 双轨 | 口径不一致 | cost 统一走 `eval/pricing.json` + `compute_cost`（RMB） |

---

## 6. 范围外（后续窗口）

- Planner / Critic / Fact Checker 节点埋点（W4/W5 落地后接入，schema 已预留）
- Retry / timeout / circuit breaker 埋点（W2 恢复链落地后接入）
- OpenTelemetry 标准导出（当前 Langfuse SDK 内部即 OTel；如需导出到第三方后端，W9 再评估）
- 前端 trace 可视化（保留 UI 查看，不做自定义前端）
