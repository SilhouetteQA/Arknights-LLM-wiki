# Spec 05 — Wiki Presence-aware Facts and Adapter

> Spec ID：`05`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 04 `COMPLETE`  
> Target Repository：`WIKI_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §6、§8.1、Appendix A.2–A.5、Appendix F.2
- ADR-0002
- `FND-MAP-001/002`、`FND-USAGE-*`、`FND-COST-*`、`FND-CSUM-*`、`FND-MODE-*`

## Objective

建立 Wiki 项目内的 presence-aware facts、Foundation mapping 和统一 mode runtime，为后续 producer seams 提供单一旁路入口。本步骤不修改任何 producer 或 Legacy 业务文件。

## Allowed Changes

```text
WIKI_REPO/arknights_wiki/adapters/__init__.py（仅在不存在时）
WIKI_REPO/arknights_wiki/adapters/foundation/__init__.py
WIKI_REPO/arknights_wiki/adapters/foundation/facts.py
WIKI_REPO/arknights_wiki/adapters/foundation/mapping.py
WIKI_REPO/arknights_wiki/adapters/foundation/runtime.py
WIKI_REPO/tests/contracts/test_foundation_mapping.py
```

Spec 04 创建的 `evidence_sink.py` 可被调用但不改变 I/O 语义。

## Forbidden Changes

- `llm_client.py`、router、Eval producers、metrics 或任何业务调用点。
- 重写 Wiki pricing、cost calculation、Langfuse 或 report。
- 在 facts 中直接构造 Pydantic DTO、写 Evidence 或补默认零。
- 把 `estimate=true` price 当作 confirmed price table。
- 使用 Foundation output 反向驱动 Legacy。

## Current Facts to Preserve

- Wiki OpenAI-compatible usage 可能只在 Langfuse 分支被提取。
- runner 的 token 可能是基于响应字符的估算。
- judge/scoring 可有 provider-reported usage。
- pricing snapshot 中有数值的项仍可能标记 `estimate=true`。
- Legacy cost `0.0` 不能单独证明真实零。

## Implementation Steps

1. 在 `facts.py` 定义项目内部 `WikiLegacyUsageFacts`、`WikiLegacyCostFacts` 和 summary component facts；它们不进入 shared payload。
2. extractor 独立保存 usage object/field presence、call observed、原值、provenance、price-entry presence、estimate flag、currency context 和 pricing snapshot identity。
3. usage object absent 时保持全部 token null/source unknown；显式零保持零；缺失 total 不相加。
4. runner 字符估算只写 output token estimate，input/total 为 null。
5. 规范化整个参与计算的 pricing snapshot，生成稳定 hash；Legacy float 先 `Decimal(str(value))`，禁止二进制 float 误差扩散。
6. `mapping.py` 将 facts 转换为 Usage/Cost/CostSummary；所有 Pydantic/aggregation error 只在边界映射为 ErrorEnvelope。
7. 对 ambiguous legacy zero 映射 unknown；只有 call observed 且明确免费证据存在时映射 true zero。
8. `runtime.py` 严格解析 `AGENT_CONTRACT_MODE`，共用同一 extractor/mapping；off skip、observe record-and-continue、strict record-and-fail-validation。
9. runtime 注入 EvidenceSink 并维护非递归 sink failure counter；不读取项目 extensions 改变语义。
10. 提供窄 `observe_eval_cost_entry` 等 helper API，但不包含 producer 的 Legacy calculation 或 file write。

## Validation Commands

```powershell
python -m pytest tests/contracts/test_foundation_mapping.py -q
```

开发 fixtures 至少覆盖：usage absent、provider zero、provider total mismatch、runner estimate、unknown price、estimate price、confirmed/free price、CNY context、malformed summary component 和 mode invalid value。

## Expected Outputs

- Wiki-only facts types/extractors。
- Wiki mapping 与 mode runtime。
- stable pricing snapshot identity。
- 可由 producer 调用但不影响 Legacy 的 observation API。

## Acceptance Criteria

- Facts extractor 不出现 `get(..., 0)`、`or 0` 或 total reconstruction。
- `estimate=true` 得到 `source=estimated`。
- price missing/tbd 得到 amount null、source unknown，并可保留 CNY context。
- mapping failure 在 observe 中形成 FAIL Evidence，但模拟业务返回不变。
- project facts 未进入 `agent_core.contracts` 或 JSON Schema。

## Stop Conditions

- 必须改变 Legacy cost calculation 才能获取事实。
- 无法在不保存 Prompt/response 原文的情况下取证。
- 当前 pricing 数据无法区分 entry absent 与 explicit zero，且实现者准备猜测。
- 需要新增 Foundation 公共字段才能完成；此时触发 `SPEC_INCOMPLETE`。

## Rollback / Handoff

本步骤尚未接线，删除 Wiki Adapter 目录和新增项目 tests 即可回滚。Handoff 必须列出每类 facts 的 presence/provenance 来源与仍然 ambiguous 的 Legacy 情况。
