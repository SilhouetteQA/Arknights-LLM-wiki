# Spec 02 — Foundation Semantic Models

> Spec ID：`02`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 01 `COMPLETE`  
> Target Repository：canonical authoring in `WIKI_REPO`；最终镜像到 `CODING_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §2、§3.1、§4–6、§12.6、Appendix A.1–A.4
- ADR-0002
- `FND-MAP-*`、`FND-USAGE-*`、`FND-COST-*`、`FND-CSUM-*`、`FND-ERR-*`、`FND-EXT-*`、`FND-MODE-*`

## Objective

在 Wiki canonical 仓建立 Foundation v0.1 的最小规范性数据与行为边界：ContractMode、Usage、Cost、CostSummary、ErrorEnvelope、extension 基础约束及其 `contract.md` 规则。此步骤不包含 Evidence DTO/Protocol、Schema/hash tooling、项目 Adapter 或 producer 接线。

## Allowed Changes

```text
WIKI_REPO/agent_core/__init__.py
WIKI_REPO/agent_core/contracts/__init__.py
WIKI_REPO/agent_core/contracts/version.py
WIKI_REPO/agent_core/contracts/contract.md
WIKI_REPO/agent_core/contracts/enums/{__init__,modes,sources,errors}.py
WIKI_REPO/agent_core/contracts/models/{__init__,base,usage,cost,error}.py
WIKI_REPO/agent_core/contracts/conformance/{__init__,rules,test_usage,test_cost,test_cost_summary,test_extensions,test_error_envelope,test_modes}.py
```

Coding mirror 只能由 Spec 03 的受控 bundle 同步，本步骤不得在 Coding 手工复制或修补。

## Forbidden Changes

- Provider、Adapter、Langfuse、Eval、Benchmark、Dashboard 或项目配置。
- ModelRequest、ToolResult、Trace、Evaluation、Checkpoint 正式契约。
- `agent_core` 根级 convenience export。
- 自动 FX、字段级 Usage provenance、per-family SemVer 或项目专有字段。

## Implementation Steps

1. 建立普通 Python package；`agent_core/__init__.py` 仅保留 namespace docstring。
2. 在 `version.py` 固定 Contract Set `0.1.0` 与所需 canonicalization/tooling version 常量，不写 maturity state。
3. 定义 StrEnum：ContractMode、UsageSource、CostSource、ErrorCategory 和基础 error codes。
4. 定义统一 base model，默认 `ConfigDict(extra="forbid")`，禁止任意额外字段。
5. 实现 Usage 的 nullable non-negative token fields 与 object-level source；不得自动补 total。
6. 实现 Cost 的 Decimal-string serialization、三字母 currency、source/pricing invariant；拒绝 float 输入。
7. 实现独立 CostSummary 及所有 count、complete、currency aggregation invariants；CurrencyMismatch 必须先于 incomplete 判断。
8. 实现最小 ErrorEnvelope；它必须是 DTO 而非 Exception，`message` 不可驱动逻辑，v0.1 retryable 固定 false。
9. 在 base/validators 中实现 extension namespace、JSON-only、16 KiB、depth 4 与 sensitive payload 防线。
10. 在完整 `contract.md` 中按 Rule ID 写规范性语义、禁止项与示例；说明 JSON Schema 只是派生快照。
11. 编写最小开发期 conformance tests；Spec 09 将完成全量追踪和双仓项目测试。

## Required Invariants

```text
missing != zero
estimated != provider_reported
provider total is preserved
missing total is not synthesized
Decimal string only
raw currency is preserved
mixed currencies fail explicitly
CostSummary does not invent source/pricing_version
Foundation treats extensions as opaque
ErrorEnvelope does not replace internal exceptions
```

## Validation Commands

开发阶段在 Wiki：

```powershell
python -m pytest agent_core/contracts/conformance/test_usage.py -q
python -m pytest agent_core/contracts/conformance/test_cost.py -q
python -m pytest agent_core/contracts/conformance/test_cost_summary.py -q
python -m pytest agent_core/contracts/conformance/test_extensions.py -q
python -m pytest agent_core/contracts/conformance/test_error_envelope.py -q
python -m pytest agent_core/contracts/conformance/test_modes.py -q
```

正式 Candidate-bound L1 必须在 Spec 11 重跑；这里通过不构成 Cycle Evidence。

## Expected Outputs

- 可导入的 Foundation v0.1 semantic models/enums。
- 完整 `contract.md` Rule ID 定义。
- 覆盖核心不变量的开发期 conformance tests。
- 明确排除未来 family 的 public surface。

## Acceptance Criteria

- Appendix A.2–A.4 的每条适用规则至少有模型/文档表达，并具备测试落点。
- 未知 Cost 无法序列化为 `amount="0", source="unknown"`。
- 显式零、空集合、全未知、部分未知和币种冲突语义可区分。
- ContractMode 非法值明确失败。
- `agent_core` 未出现实现代码或根级 re-export。

## Stop Conditions

- 需要项目专有字段才能通过模型验证。
- 必须引入 per-field provenance、FX 或新 family 才能完成 v0.1。
- Pydantic 输出行为与 Master 定义不一致且无法通过明确配置实现。
- 子 Spec 与 Master Rule 冲突。

## Rollback / Handoff

在尚未被项目 Adapter 消费前，可整体删除本步骤新增的 Wiki `agent_core` package。Handoff 必须列出 public imports、Rule ID 覆盖和所有有意未实现的 family。
