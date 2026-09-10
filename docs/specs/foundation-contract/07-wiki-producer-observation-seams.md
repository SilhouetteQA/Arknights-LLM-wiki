# Spec 07 — Wiki Producer Observation Seams

> Spec ID：`07`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 05 `COMPLETE`  
> Target Repository：`WIKI_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §2.4、§7.1/7.3、§8、§10、Appendix F.2
- `FND-MAP-*`、`FND-MODE-*`、`FND-REG-005`
- Producer Registry IDs：`wiki.agent.llm_usage`、`wiki.eval.cost_log`、`wiki.eval.cost_summary`

## Objective

把 Wiki in-scope Agent/Eval/summary 主链路连接到 Spec 05 的旁路 runtime，同时保持模型调用、Langfuse、cost log、Eval summary 和所有业务结果不变。

## Allowed Changes

```text
arknights_wiki/extraction/llm_client.py::chat_completion
arknights_wiki/agent/router.py::_llm_intent_rewrite
arknights_wiki/eval/runner.py::_log_cost
arknights_wiki/eval/judge.py::_log_cost
arknights_wiki/eval/scoring.py::_log_cost
arknights_wiki/eval/metrics.py::summarize_cost
tests/contracts/test_producer_wiring.py
tests/contracts/test_business_invariance.py（Wiki cases）
```

只允许为 observation seam、facts extraction、依赖注入或窄 helper 做行为保持型局部重构。

## Forbidden Changes

- 合并三个 `_log_cost` 为业务 cost service。
- 改动 Langfuse 启用条件、旧记录参数、JSONL 格式、rounding 或 report。
- 接线 `wiki.trace.summary`、Dashboard、offline extraction 或 StatsCollector。
- Foundation output 回写 Legacy 或改变异常/fallback。

## Producer Steps

### `wiki.agent.llm_usage / chat_completion`

1. 模型成功响应后、Legacy coercion/Trace 前提取 presence facts。
2. Langfuse usage extraction 不再是 Foundation 观察的前提。
3. 调用旁路 runtime，stage=`chat_completion`。
4. 继续原 `_get_model_config`、client、retry/breaker、request、解析、Langfuse 和 `(content, message)` 返回。

### `wiki.agent.llm_usage / intent_rewrite`

1. `_llm_intent_rewrite` 成功响应后提取 facts并观察 stage=`intent_rewrite`。
2. 保持 prompt、temperature、max_tokens、本地意图、过滤、异常捕获和返回 `None` 逻辑。

### `wiki.eval.cost_log / runner|judge|scoring`

1. 每个 `_log_cost` 按原逻辑形成 entry/timestamp。
2. 写入前复制 allowlisted facts并调用同一窄 helper。
3. 用原 entry、路径、编码和 append 次数写 Legacy log。
4. runner estimate 与 judge/scoring provider source 不得混同。

### `wiki.eval.cost_summary / cost_log_summary`

1. `summarize_cost` 在旧逐行读取中并行收集 component facts。
2. Legacy total/steps 使用原 float、rounding 和 malformed skip 逻辑。
3. 旧 result 完成后旁路生成 CostSummary Evidence。
4. malformed line 对 Legacy 继续 skip，但 Foundation summary 必须记录不完整/失败，不能反向改变返回。

## Validation Commands

```powershell
python -m pytest tests/contracts/test_producer_wiring.py -q
python -m pytest tests/contracts/test_business_invariance.py -q
```

每个 `(producer_id, mapping_stage)` 至少有一次 fixed-response wiring test。正式 Smoke coverage 在 Spec 13执行。

## Expected Outputs

- 六个 Wiki mapping stages 的旁路接线。
- 旧 Langfuse/cost log/Eval summary 不变性 fixtures。
- Registry 与代码位置一致的 wiring assertions。

## Acceptance Criteria

- `AGENT_CONTRACT_MODE=off` 时不执行 facts/Adapter/sink。
- observe injected mapping/sink failure 时旧返回和副作用不变。
- 固定响应下 off/observe 的 output、decision、Legacy side effects/telemetry 精确一致。
- `wiki.trace.summary` 仍为 DEFERRED 且无虚构事件。

## Stop Conditions

- 任一 producer 必须改写 Legacy entry/result 才能旁路观察。
- 为覆盖某 stage 需要扩大到 Dashboard/offline stats。
- 原函数事实与 Master 当前行为描述不符。
- 新接线改变模型调用次数、retry、异常或写入次数。

## Rollback / Handoff

运行时先设 `AGENT_CONTRACT_MODE=off`。代码回滚只移除各 producer 的 observation call/seam和仅为 seam 抽取的窄 helper；保留所有原业务逻辑。Handoff 按 stage 列出固定输入、Legacy invariant 和 Evidence producer identity。
