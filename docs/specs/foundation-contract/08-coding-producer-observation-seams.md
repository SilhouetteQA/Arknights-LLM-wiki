# Spec 08 — Coding Producer Observation Seams

> Spec ID：`08`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 06 `COMPLETE`  
> Target Repository：`CODING_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §2.4、§7.2/7.3、§9、§10、Appendix F.3
- `FND-MAP-*`、`FND-MODE-*`、`FND-CSUM-011`
- Producer Registry IDs：`coding.agent.llm_usage`、`coding.trace.generation_usage`、`coding.benchmark.case_cost`、`coding.trace.summary`

## Objective

连接 Coding 的 provider、Langfuse generation、Benchmark CaseResult 与 TraceSummary 边界，产生独立观察事件并保持 Agent、Sandbox、Benchmark 和报告行为不变。

## Allowed Changes

```text
agent/llm.py::OpenAICompatClient.chat
tools/tracing.py::record_usage
benchmark/runner.py::_run_one_case/_environment_error_result/_case_result及异常CaseResult分支
tools/report_trace.py::_summarize_trace/_summarize_events
tests/contracts/test_producer_wiring.py
tests/contracts/test_business_invariance.py（Coding cases）
```

## Forbidden Changes

- Agent routing/review/retry、Tool dispatch、Sandbox、Approval、Git/GitHub。
- Benchmark cases、gold patch、judge prompt、resolution definition 或 `benchmark/report.py`。
- 改动 `tokens_total` 或 `CaseResult.cost_usd` Legacy 数值。
- 去重 provider/trace 两个 producer event。
- 为关联设计新全局 invocation ID。

## Producer Steps

### `coding.agent.llm_usage / openai_compat`

1. provider response 后、int coercion 前提取 usage presence。
2. emit Usage + unknown USD Cost，并 append同一 minimal component facts到 client-local sidecar。
3. 继续原 tokens_total、`record_usage(..., 0.0)`、tool-call parse、reasoning replay 和 LLMMessage 返回。

### `coding.trace.generation_usage / langfuse_generation`

1. 给 `record_usage` 增加向后兼容的 keyword-only contract facts。
2. mode 非 off 且 facts存在时先旁路观察，再执行原 `get_client`/no-op/Trace write。
3. Foundation facts 不得进入 Langfuse `extra` 或旧 metadata。

### `coding.benchmark.case_cost / normal|environment_error|error`

1. 每个分支先完整形成原 CaseResult。
2. normal 读取本 case sidecar slice形成 components/summary。
3. environment_error 若无 Agent call 则空 summary；error 若已有 calls则保留 partial components。
4. emit 在 Result 完成后，不参与 resolution/test/patch/consistency 判定。

### `coding.trace.summary / sdk|clickhouse`

1. SDK/row 原始 observation 仍可见时提取 presence，再形成旧 TraceSummary。
2. SDK 缺 cost 时旧 `0.0` 映射 unknown。
3. ClickHouse 在 `_as_float` 前区分 absent 与 explicit zero，保留 row components。
4. 保持 SDK 优先/ClickHouse fallback、TraceError、latency 和 renderer。

## Validation Commands

```powershell
python -m pytest tests/contracts/test_producer_wiring.py -q
python -m pytest tests/contracts/test_business_invariance.py -q
```

必须覆盖全部七个 stage variants：openai_compat、langfuse_generation、normal、environment_error、error、sdk、clickhouse；同一模型调用产生两条 producer evidence 是预期而非重复错误。

## Expected Outputs

- Coding 七个 stage 的旁路接线。
- CaseResult/TraceSummary fixed fixtures。
- provider与trace边界独立 Evidence。
- no-call 与 partial-call error semantics。

## Acceptance Criteria

- off/observe 固定响应的业务不变量精确一致。
- Langfuse client absent 时原 no-op 行为不变但 Foundation observation不依赖它。
- CaseResult 原字段和报告字节/语义不变。
- SDK/ClickHouse fallback 次序与 TraceError 不变。
- sidecar data 不跨 case 泄漏。

## Stop Conditions

- 必须改变 Sandbox/approval/Benchmark 判定才能接线。
- 无法在 coercion 前读取 raw presence。
- `record_usage` 新参数破坏现有调用方。
- producer event 必须去重才能通过当前契约。

## Rollback / Handoff

先切换 off；代码回滚只移除 observation calls、keyword-only参数和sidecar hooks，保留原 provider/trace/benchmark/report流程。Handoff 按 stage 记录 invariant与sidecar slice边界。
