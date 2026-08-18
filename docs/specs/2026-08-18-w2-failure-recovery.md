# W2 — Failure Recovery 恢复链设计规格（2026-08-18）

> 依据：《01_现有明日方舟LLM_Wiki项目评估与升级方案.md》§12（Failure Recovery）+ §14 最终架构
> 规则：CLAUDE.md U-07（失败恢复必做）+ U-04（全链路可观测）+ 第六章升级工作流
> 前置：W0 ✅（基准 report_v1_mimo.md overall 0.857）· W1 ✅（Langfuse trace 全链路埋点，schema 已预留 NODE_TYPE_RETRY）
> 用户决策（2026-08-18）：P1（W5–W9）全部跳过；W2 人工升级环节简化为 escalation 标记 + 可读错误，不引入完整 HITL 交互

---

## 1. 背景与目标

### 1.1 背景

当前 Agent 路径的失败处理是「零散 try/except」：

- 工具异常 → 返回 `工具执行失败: {str(e)}` 文本给 LLM（有基本降级，但无重试/超时/熔断/fallback）
- LLM 调用（`chat_completion`）**无重试**：一次网络抖动/限流直接整题失败（graph 路径抛到 server → SSE error）
- 工具执行**无超时**：FAISS 加载或异常工具可能挂起
- LangGraph `compile()` **无 checkpointer**：中途失败无法断点续跑
- W1 trace 中 `retry` 字段恒 0，恢复过程不可见

升级方案 §12 要求完整恢复链：`timeout → retry（指数退避）→ circuit breaker → fallback tool → checkpoint/resume → human escalation`，并考虑 idempotency 与 partial failure。

### 1.2 目标

1. 工具调用从「失败即错」升级为可配置的完整恢复链
2. LLM 调用（agent 路径）失败自动重试（指数退避），重试耗尽后优雅降级而非整题失败
3. LangGraph 支持 checkpoint 持久化与断点续跑
4. 恢复全过程在 Langfuse trace 可见（retry 次数 / breaker 状态 / fallback 命中 / escalation）
5. 恢复链**可配置、可开关**：默认参数对现有行为影响最小，未启用时不改变行为
6. 模拟失败场景（超时/报错/连续失败）均可按恢复链正确降级（验收脚本 + 单元测试）

---

## 2. 现状分析：失败点清单

| 环节 | 位置 | 当前行为 | 缺口 |
|------|------|----------|------|
| LLM 意图改写 | router.py `_llm_intent_rewrite` | try/except → None → 本地兜底 | 无重试（一次失败直接降级，可接受但可补重试） |
| LLM chat_completion | llm_client.py `chat_completion` | 无重试，异常向上抛 | **缺重试/超时**（graph/simple 共用入口，优先补） |
| LLM 回答生成 | simple_search.py `_do_generate` | 不走 chat_completion，无重试 | **缺重试/超时** |
| Agent 工具执行 | graph.py `_execute_tool_traced` | 异常 → 文本降级 + trace ERROR | **缺 timeout/retry/breaker/fallback** |
| 工具未注册 | graph.py `tool_node` | 返回 `未知工具: {name}` | 可接受（LLM 幻觉），不属恢复链 |
| synthesize | graph.py `synthesize_node` | chat_completion 异常 → 固定文案 | 可接受（最终兜底），可补重试 |
| FAISS 加载/搜索 | simple_search.py `_collect_semantic_fallback` | 异常 pass（静默跳过该层） | 可接受（多层兜底），可记录 error |
| LangGraph 图执行 | server.py `_agent_search_events` | graph_error → SSE error | **缺 checkpoint/resume** |
| 前端 SSE | server.py `_simple_search_events` | 异常 → SSE error | 已有兜底 ✅ |

**结论**：优先补三处——(A) 工具执行恢复链（timeout/retry/breaker/fallback）；(B) LLM 调用重试（chat_completion + simple_search 回答）；(C) LangGraph checkpoint。

---

## 3. 技术方案

### 3.1 新模块：`arknights_wiki/agent/resilience.py`

独立于 observability 的通用恢复链模块（不依赖 trace 开关，可独立测试）。

```
ResilienceConfig (dataclass)
  timeout_seconds: float = 30.0      # 单次执行超时（0 = 不超时）
  max_retries: int = 2               # 重试次数（不含首次；0 = 不重试）
  backoff_base: float = 1.0          # 指数退避基数：wait = backoff_base * 2**attempt
  backoff_max: float = 8.0           # 退避上限
  retryable_exceptions: tuple        # 可重试异常类型（默认 (Exception,)）
  breaker_threshold: int = 5         # 熔断打开阈值（连续失败次数）
  breaker_reset_seconds: float = 60.0  # 熔断打开后恢复探测间隔
  fallback_enabled: bool = True
```

**组件**：

1. `TimeoutError`（自定义，语义明确）
2. `with_timeout(fn, args, kwargs, seconds)` — 线程池执行 + `future.result(timeout)`；超时取消并抛 `TimeoutError`（Windows 无 SIGALRM，线程方案跨平台）
3. `CircuitBreaker` — 状态机 `closed → open → half_open → closed`：
   - closed：连续失败 ≥ threshold → open；成功 → 计数清零
   - open：直接短路抛 `BreakerOpenError`（不执行函数）；reset_seconds 后 → half_open
   - half_open：放行 1 次探测，成功 → closed，失败 → open
   - `record_success() / record_failure() / state` 线程安全（lock）
4. `retry_call(fn, args, kwargs, config, breaker)` — 指数退避重试；每次失败记录到 breaker
5. `execute_with_resilience(fn, args, kwargs, config, fallbacks=None) -> (result, stats)` — 统一入口：
   - `fallbacks`: 可迭代的 (候选函数, 描述)，主函数失败耗尽后依次尝试
   - `stats` 返回：`{attempts, retries, timeout_hit, breaker_state, fallback_used, error}` 供埋点与测试
   - 全链失败 → 抛 `ResilienceError`（含 stats），由调用方决定最终降级（工具给 LLM 文本 / 服务层 SSE error）

**幂等性**：本系统工具全部只读（检索），天然幂等，重试安全；配置字段预留 `idempotent` 供未来写操作使用（本次不实现写工具）。

### 3.2 工具执行接入恢复链（graph.py）

`_execute_tool_traced` 改为经 `execute_with_resilience` 执行：

- 每个工具可声明 fallback：在 tools.py 注册表增加可选 `fallback` 字段（如 `semantic_search` → `search_wiki`；`get_entity_page` → `search_wiki`），未声明则无 fallback
- 工具失败最终仍返回友好文本给 LLM（保持现有协议不变）：
  - 恢复链命中 fallback → 返回 fallback 结果（文本前缀标注 `[已降级: {fallback_name}]`）
  - 恢复链耗尽 → 返回 `工具执行失败（重试{n}次后）: {error}`
- trace 增强：tool_call span metadata 增加 `retries` / `breaker_state` / `fallback_used` / `error`；`NODE_TYPE_RETRY` 用于标记重试节点（span name 带 retry 计数，如 `tool_call:retry#1`）

### 3.3 LLM 调用重试（llm_client.py + simple_search.py）

- `chat_completion`：内部用 `retry_call` 包装 `client.chat.completions.create`（复用 ResilienceConfig，默认 max_retries=2、timeout=60s）
  - trace：llm_call generation metadata 增加 `retries`（W1 已预留，当前恒 0 → 自动填充）
- `simple_search._do_generate`：同样套 `retry_call`（或不重复实现，改走 `chat_completion`；**选后者**——统一入口、顺带获得埋点）
- `router._llm_intent_rewrite`：保持 try/except 降级（本地兜底已是强降级），补 1 次重试（低优先级，随 chat_completion 模式统一）

### 3.4 LangGraph checkpoint（graph.py + server.py）

- `build_agent_graph(checkpointer=None)`：`checkpointer` 传入时 `workflow.compile(checkpointer=...)`
- server.py complex 路径：`SqliteSaver` 持久化到 `output/checkpoints/agent.sqlite`（langgraph-checkpoint 4.x，实施时确认 `langgraph.checkpoint.sqlite` 导入与线程安全）
  - 注意：server 在 executor 线程执行 graph，SqliteSaver 线程安全性需实测（若受限，降级 `MemorySaver` + 会话内断点续跑语义）
- **断点续跑语义**：checkpoint 以 thread_id 为键。本次演示场景：
  - graph 中途失败（模拟 synthesize LLM 调用异常）→ 捕获并读取该 thread 的 checkpoint → 从断点恢复重跑
  - 恢复后不重复执行已成功的工具（幂等，只读工具天然安全）
- 断点续跑测试：`graph.stream(initial_state, config={"configurable": {"thread_id": "t1"}})` 两段执行，验证工具调用不重复

### 3.5 失败埋点扩展（observability/schema.py）

- 复用 `NODE_TYPE_RETRY`（已预留），新增常量：
  - `SPAN_BREAKER = "circuit_breaker"`（breaker 状态变化事件，可选）
  - metadata 约定字段：`retries` / `breaker_state` / `fallback_used` / `escalated`
- `tool_call` / `llm_call` span 的 metadata 统一由 `execute_with_resilience` 返回的 stats 填充
- Dashboard 无需改动（现有节点聚合按 name，新增字段仅入 metadata）

### 3.6 恢复链末端：human escalation（简化版，因 W7 已跳过）

- 恢复链全失败 → `ResilienceError` → 服务层：
  - complex：SSE `error` 事件（现有）+ trace 根 metadata `escalated=true`
  - simple：SSE `error` 事件（现有）
- 不做 W7 的确认/拒绝/修改交互（用户决策跳过 P1）；escalation 仅作为「已耗尽恢复手段，需人工介入」的可观测标记，为将来 W7 预留接口（`EscalationHandler` 可注入点，默认打印/记录）

---

## 4. 验收标准（对齐路线图 W2）

1. **模拟工具失败**（3 场景 × 工具）：
   - 超时：工具 sleep > timeout → 触发重试 → fallback → 最终返回降级文本，trace 可见 retries
   - 报错：工具抛异常 → 重试 → fallback 命中 → 文本标注降级来源
   - 连续失败：≥ threshold → breaker 打开 → 后续调用短路（不执行函数）→ 恢复期后 half-open 探测
2. **LLM 重试**：mock `chat.completions.create` 前 2 次抛错 → 第 3 次成功，`llm_call` trace 含 `retries=2`；耗尽后 graceful 降级（simple 走 SSE error，graph 走 escalate）
3. **checkpoint**：graph 中途失败 → 从 checkpoint 恢复重跑成功，已成功工具不重复执行
4. **可开关不侵入**：默认配置下全量 pytest 通过；未配置 LANGFUSE 时行为与现状一致
5. **回归**：benchmark 子集（≥10 题）实施前后指标不回归（基线 report_v1_mimo.md overall 0.857）

---

## 5. 风险与取舍

| 风险 | 影响 | 缓解 |
|------|------|------|
| 重试放大成本/延迟（LLM 调用） | 失败时多花 2 次调用费 | 默认 max_retries=2 + 指数退避上限 8s；仅对可重试异常重试（网络/限流），4xx 业务错误不重试 |
| 线程超时方案资源开销 | 每次工具执行一个线程 | 线程池复用（`ThreadPoolExecutor` 单例，max_workers=8）；仅当 timeout>0 才走线程 |
| breaker 误伤 | 瞬时故障后 60s 内短路 | threshold=5（连续失败才算），reset 后 half-open 探测；可配置关闭 |
| SqliteSaver 线程安全 | server executor 线程 | 实测；受限则降级 MemorySaver + 单会话语义（checkpoint 演示仍成立） |
| fallback 改变回答质量 | 降级结果可能偏差 | fallback 文本前缀标注来源，评测可见；默认 fallback 仅语义相近工具 |
| checkpoint 数据体积 | 每次执行写盘 | 仅保留最近 N=20 个 thread 的 checkpoint（SqliteSaver 按 thread_id 覆盖） |

---

## 6. 范围外

- 完整 HITL 交互（W7 已跳过，仅留 escalation 接口）
- 写操作幂等性实现（当前全部只读工具）
- 跨进程分布式熔断（单进程内存态即可）
- OpenTelemetry 独立导出（沿用 W1 决策）
