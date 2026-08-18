# W1 — Observability / Tracing 实施计划（2026-08-18）

> 关联 Spec：`docs/specs/2026-08-18-w1-observability.md`
> 规则：CLAUDE.md G-01（feature 分支）/ G-02（小步提交）/ U-04（全链路可观测）
> 运行环境：`D:\CodexPython312\python.exe`；分支：`feature/w1-observability`

---

## 任务分解

### T1. 部署 Langfuse（本地 Docker）

- [ ] 启动 Docker Desktop（`D:\Docker\Docker Desktop.exe`，等待引擎就绪，`docker info` 有 Server 段）
- [ ] 创建 `docker/langfuse/`，放置官方 compose（langfuse v3：web+worker+postgres+clickhouse+redis+minio），
      secrets 通过 `.env`（不提交）；ClickHouse/Redis 加内存限制
- [ ] `docker compose up -d`，等待 `langfuse-web` Ready（日志 "Ready"），`http://localhost:3000` 可访问
- [ ] 注册账号 → 创建项目 → 复制 Public/Secret Key
- [ ] 冒烟：`pip install langfuse`（到项目运行环境）→ 最小脚本 `get_client()` + 一条 trace 写入 → UI 可见

**验证**：UI 可登录；最小 trace 出现在 UI；`.env` 含三键且不入 git。

### T2. observability 包骨架

- [ ] `pyproject.toml`：`agent` extra 增加 `langfuse>=4.0`
- [ ] 新建 `arknights_wiki/observability/{__init__,client,decorators,schema}.py`
      - `client.py`：懒加载 `get_client()`；`is_enabled()`（三环境变量齐备 && `ARKNIGHTS_TRACING != "0"`）；`flush()`
      - `decorators.py`：`traced(name, as_type, metadata_fn)` — 关闭时原函数直通（no-op）
      - `schema.py`：节点名常量、cost 计算（复用 `eval/pricing.json` + `compute_cost`）、node_type 预留
- [ ] 单元测试 `tests/observability/test_observability.py`：is_enabled 三态 / 关闭时 no-op / cost 计算

**验证**：`python -m pytest tests/observability/ -q` 通过；关闭态导入不触发 langfuse 网络调用。

### T3. LLM 统一埋点（llm_client）

- [ ] `chat_completion()` 外包 `traced(as_type="generation", name="llm_call")`：
      response 后 `update_current_span()` 写 model / prompt_tokens / completion_tokens / cost(RMB) / latency
- [ ] router.py `_llm_intent_rewrite` 的直接 `create()` 调用补 `generation` 埋点
- [ ] 测试：`tests/observability/test_llm_tracing.py` — mock client 返回 usage，断言 span metadata 字段齐全；
      关闭态调用不产生任何 trace 副作用

**验证**：字段齐全断言通过；`llm_call` span 出现在 Langfuse UI。

### T4. 业务链路埋点

- [ ] `server.py` `/chat`：trace 根 `chat_request`（metadata: question/complexity/question_type/entities/latency/error/benchmark_id）
- [ ] `router.py` `route_query`：span `router`（metadata: source/entities/time_scope/reason）
- [ ] `simple_search.py`：span `simple_search`；`search_and_collect` 各层 span `retrieval`
      （layer 名 + query + n_hits）；回答生成走 T3 已有 generation
- [ ] `graph.py`：`call_model` span+generation（iteration/tool_calls 数）、`tool_node` 每工具 span
      `tool_call`（tool/args/result 摘要/error）、`synthesize_node` span
- [ ] 冒烟：启动 server，一次 simple + 一次 complex 问答，UI 看完整 trace 树

**验证**：UI trace 树结构符合 Spec §3.3 清单；simple 与 complex 两路径均可导出。

### T5. 评测对接 + 成本汇总

- [ ] `eval/runner.py`：读 `ARKNIGHTS_TRACING`，开启时 trace 根 metadata 带 `benchmark_id`/`mode`
      （`run_direct` 内用当前线程 context 包裹，worker 并行下各线程独立）
- [ ] `scripts/trace_cost_summary.py`：拉取最近 N 小时 trace 成本 → `output/observability/cost_summary.md`
- [ ] 验证：`ARKNIGHTS_TRACING=1` 跑 3 题（direct），UI 按 benchmark_id 过滤可见；成本脚本输出可引用摘要

### T6. 全量回归 + 验收

- [ ] 关闭态全量 pytest（424+ 预期通过，无回归；无 LANGFUSE 环境变量）
- [ ] 开启态抽 2-3 题评测跑批不报错
- [ ] 按 Spec §4 验收清单逐项核对（trace 树 / 字段 / 可开关 / 评测可选 / 成本摘要）

### T7. Review + 收尾

- [ ] 自查 + 代码审查（无 review 前不 commit，CLAUDE.md 1.1）
- [ ] 更新 `output/devlog.md`（架构决策、埋点清单、冒烟结果、成本示例）
- [ ] 更新 `docs/plans/2026-08-15-upgrade-roadmap.md`：W1 ⏳ → ✅
- [ ] commit（feature 分支）

---

## 文件变更总览

| 文件 | 变更 |
|------|------|
| `docker/langfuse/docker-compose.yml` + `.env.example` | 新增（Langfuse 部署） |
| `pyproject.toml` | agent extra + `langfuse>=4.0` |
| `arknights_wiki/observability/` | 新增包（client/decorators/schema） |
| `arknights_wiki/extraction/llm_client.py` | `chat_completion` 埋点 |
| `arknights_wiki/agent/router.py` | `route_query` span + `_llm_intent_rewrite` generation |
| `arknights_wiki/agent/server.py` | trace 根 |
| `arknights_wiki/agent/simple_search.py` | simple_search/retrieval span |
| `arknights_wiki/agent/graph.py` | call_model/tool_node/synthesize span |
| `arknights_wiki/eval/runner.py` | `ARKNIGHTS_TRACING` 支持 |
| `scripts/trace_cost_summary.py` | 新增（成本汇总） |
| `tests/observability/` | 新增测试 |
| `docs/specs/2026-08-18-w1-observability.md` / `docs/plans/2026-08-18-w1-observability.md` | 本窗口产出 |
| `output/devlog.md` + 路线图 | 收尾更新 |

## 验证标准（每步）

- T2/T3/T6：pytest 全绿（关闭态无回归）
- T1/T4：Langfuse UI 可见完整 trace 树
- T5：benchmark_id 过滤 + cost_summary.md 可引用
