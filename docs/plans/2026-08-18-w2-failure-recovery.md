# W2 — Failure Recovery 实施计划（2026-08-18）

> 依据：docs/specs/2026-08-18-w2-failure-recovery.md
> 规则：CLAUDE.md U-07 / U-04 / U-03 + 第六章升级工作流；TDD（先写测试再实现）
> 分支：feature/w2-failure-recovery

## 任务分解

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| T1 | resilience 核心模块（TDD） | `arknights_wiki/agent/resilience.py` + `tests/agent/test_resilience.py` | 无 |
| T2 | 工具执行接入恢复链 + fallback 注册 | graph.py `_execute_tool_traced` 改造、tools.py 注册表加 fallback 字段、trace metadata 增强 | T1 |
| T3 | LLM 调用重试（chat_completion 统一） | llm_client.py chat_completion 重试 + simple_search `_do_generate` 改走 chat_completion | T1 |
| T4 | LangGraph checkpoint 断点续跑 | graph.py `build_agent_graph(checkpointer)` + server.py SqliteSaver 接入 + 断点续跑测试 | T3 |
| T5 | 模拟失败验证 + 回归 | scripts/failure_demo.py 验收脚本、benchmark 子集回归、trace 可见性验证 | T2/T3/T4 |
| T6 | 收尾 | devlog、路线图 W2 状态、commit | T5 |

## 里程碑

- M1（T1 完成）：resilience 模块 + 单测全绿
- M2（T3 完成）：LLM 重试接入，simple/complex 回答路径带重试
- M3（T4 完成）：checkpoint 断点续跑可用
- M4（T5 完成）：验收脚本 3 场景通过，benchmark 子集不回归
- M5（T6 完成）：devlog + 路线图 + commit

## 关键实现细节

1. **resilience.py 线程池**：模块级 `ThreadPoolExecutor(max_workers=8)`，仅 timeout>0 时启用
2. **breaker 状态机**：`closed/open/half_open` + threading.Lock；`__call__` 语义：open 直接抛 `BreakerOpenError`
3. **fallback 注册**：tools.py `_tool_registry` 元组加第 6 个元素 `fallback_name`（可选）；`TOOL_FALLBACKS` 映射构建
4. **chat_completion 重试**：仅对 `openai.APIConnectionError / APITimeoutError / RateLimitError / InternalServerError` 重试（不重试 4xx 业务错误）
5. **SqliteSaver**：`langgraph.checkpoint.sqlite.SqliteSaver`（checkpoint 4.1.1），DB 路径 `output/checkpoints/agent.sqlite`；server 线程内使用，实测线程安全，若报错改 MemorySaver
6. **测试环境**：`D:\CodexPython312\python.exe -m pytest tests/agent/test_resilience.py -x`

## 验证清单

- [ ] `pytest tests/agent/test_resilience.py` 全绿（TDD）
- [ ] `pytest tests/agent/ tests/observability/` 无回归
- [ ] 全量 pytest 无回归（4 个预存失败除外：3 stats + 1 worldbuilding）
- [ ] scripts/failure_demo.py 3 场景输出符合预期
- [ ] benchmark 子集（10 题）实施后指标 vs 基线 0.857 不回归
- [ ] Langfuse trace 可见 retries / breaker_state / fallback_used 字段
