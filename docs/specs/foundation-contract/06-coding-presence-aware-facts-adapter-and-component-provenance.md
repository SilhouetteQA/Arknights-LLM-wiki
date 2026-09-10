# Spec 06 — Coding Presence-aware Facts, Adapter and Component Provenance

> Spec ID：`06`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 04 `COMPLETE`  
> Target Repository：`CODING_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §6、§9.1、Appendix A.2–A.5、Appendix F.3
- ADR-0002
- `FND-MAP-*`、`FND-USAGE-*`、`FND-COST-*`、`FND-CSUM-011`、`FND-MODE-*`

## Objective

建立 Coding 项目内部 facts、Foundation mapping、mode runtime 与 client-local component provenance sidecar，为 Agent、Trace、Benchmark 和 report seams 提供真实组成项，不创建新的业务成本账本。

## Allowed Changes

```text
CODING_REPO/adapters/__init__.py（仅在不存在时）
CODING_REPO/adapters/foundation/__init__.py
CODING_REPO/adapters/foundation/facts.py
CODING_REPO/adapters/foundation/mapping.py
CODING_REPO/adapters/foundation/runtime.py
CODING_REPO/adapters/foundation/observation_ledger.py
CODING_REPO/tests/contracts/test_foundation_mapping.py
```

文件名保留 Master 中的 `observation_ledger.py`，但规范术语是 project-local component provenance sidecar。

## Forbidden Changes

- Agent/LLM、tracing、benchmark 或 report producer 接线。
- 新的持久化账本、跨进程 ledger、公共 `agent_core` Ledger 对象。
- Foundation 接管 `tokens_total`、`CaseResult.cost_usd`、Benchmark 计算或 Trace summary。
- 为关联事件设计新的全局 invocation ID。
- 让 off 模式积累 provenance state。

## Component Provenance Boundary

```text
Coding component provenance
= project-local, in-memory, client-scoped observation support

It is NOT:
- a business cost source of truth
- a durable accounting system
- a shared contract
- an Evidence deduplication mechanism
```

## Implementation Steps

1. 定义 Coding 内部 usage/cost/component facts，保留 provider usage object、每字段 presence、call observed、monetary cost presence 和 USD context。
2. usage missing/field missing/explicit zero 严格区分；provider total 不重算。
3. 当前空 price table 或 `record_usage(..., 0.0)` 默认值映射 unknown USD Cost，不映射 true zero。
4. 实现 facts → Foundation mapping 和 ErrorEnvelope boundary，逻辑与 Wiki 共享契约一致但代码项目本地。
5. 实现统一 ContractMode runtime 和 sink injection；非法配置明确失败。
6. 实现 client-local sidecar，支持 append minimal components、case begin/end cursor 和 slice retrieval。
7. sidecar 只在 observe/strict 激活；off 不分配、不积累、不影响 tokens_total。
8. environment/error case 若无模型调用，允许空 component set；若已有调用，保留已观察 components，不能因最终错误清零。
9. 若现有安全稳定 call ID 已存在，可放入 `coding.*` extension；不存在时不创建。

## Validation Commands

```powershell
python -m pytest tests/contracts/test_foundation_mapping.py -q
```

开发 fixtures 覆盖 provider usage absent/present、显式零、unknown USD cost、partial calls before failure、no-call environment error、cursor isolation、off no-allocation 和 concurrent client isolation。

## Expected Outputs

- Coding-only facts/mapping/runtime。
- client-local component provenance sidecar。
- project mapping tests。
- 不影响 Legacy cost/tokens/Benchmark 的调用 API。

## Acceptance Criteria

- sidecar 无磁盘持久化、无跨项目依赖、无 public contract exposure。
- 空 price table 导致 Foundation unknown，不导致 Legacy 数值变化。
- case slice 不串入前一 case components。
- off 模式与未安装 Adapter 前的 state/return 等价。
- 已调用后失败与根本未调用可产生不同 Foundation Summary 语义。

## Stop Conditions

- 必须修改 Benchmark 判定或 Agent control flow 才能维护 cursor。
- sidecar 需要全局单例或持久化才能工作。
- provider SDK 已经删除所需 field presence，且无法在 coercion 前取得。
- 需要公共 correlation contract 才能接入。

## Rollback / Handoff

尚未 producer 接线时可整体删除 Coding Adapter 目录和新增 tests。Handoff 必须说明 sidecar 生命周期、cursor 归属、off 行为和故障后 components 保留规则。
