# ADR-0002：Foundation 事实语义与旁路治理

- 状态：Accepted
- 日期：2026-09-10
- 决策范围：Foundation v0.1 的事实表达与 Legacy 接入方式
- 实施授权：无；实施以 Master Spec Part I 为准

## Context

两个仓库都存在同一类语义歧义：Legacy 为便于计算或报告，把“没有用量/单价/成本信息”归一为 `0`。真实零成本、未知成本和估算成本因此无法可靠区分。若直接把 Legacy 数字装入统一 DTO，未来 Trace、Evaluation、Dashboard 和模型比较即使结构一致，也会得出不可信结论。

同时，两个项目已有不同的异常、恢复、观测和报告链路。让 Foundation 对象反向驱动 Legacy 业务，或把 ErrorEnvelope 变成新的内部异常框架，都会扩大 v0.1 的侵入范围。

## Decision

Foundation v0.1 采用 presence-aware facts 和非侵入旁路治理。

### Fact semantics

Adapter 映射可证明事实，而不是 Legacy convenience defaults：

```text
Foundation mapping
= value
+ field presence
+ provenance
+ pricing evidence
```

核心语义：

```text
Unknown is not Zero
Estimated is not Reported
USD is not CNY
Raw Cost is not Converted Cost
```

Usage 与 Cost 是 Foundation 公共值对象，不属于 Model、Observability 或 Evaluation 任一单独 family。缺失 token 保持 `null`；provider total 原样保存，不在 Adapter 内自动相加。Cost 使用 Decimal 字符串、保留原币种和 epistemic source，不进行隐式汇率转换。Legacy `0` 只有在明确 provider 或 confirmed pricing evidence 证明时才映射为真实零。

CostSummary 独立表达组成项聚合状态：已知小计、币种、完整性和 known/unknown counts。它不伪造统一 source 或 pricing version，也不从 Legacy total 反推出不存在的组成项。

### Shadow governance

Phase 1 的运行拓扑固定为：

```text
                 ┌→ Legacy Business Path → Existing Result
Input ───────────┤
                 └→ Foundation Adapter → Validation Evidence
```

Contract Mode 语义固定为：

- `off`：完全跳过 facts、Adapter 和 Evidence 分支。
- `observe`：执行同一映射并记录结果；任何契约或 Evidence 失败都不得改变 Legacy 业务结果。
- `strict`：使用与 observe 完全相同的 facts 和 Adapter，只让验证命令在错误时失败；不作为 Phase 1 生产主路径。

`observe` 不是 fallback，也不是 Foundation-first。Foundation consumer 不参与模型选择、路由、Evaluation score、Benchmark 判定、现有 cost report、Trace 展示、异常恢复或副作用决策。

ErrorEnvelope 只是跨序列化、API/IPC/MCP、Adapter 或 Evidence 边界的 DTO。两个仓库保留原异常类、传播和恢复逻辑；禁止 `raise ErrorEnvelope`、`except ErrorEnvelope` 或用它建立新的内部统一 Result 模式。

允许为建立 observation seam、presence facts、依赖注入和固定测试进行局部行为保持型重构；禁止借此统一全仓成本实现或让 Foundation 接管 Legacy 聚合。

## Consequences

正面结果：

- 未知、真实零和估算值可被机器区分。
- 双仓差异通过 Adapter 表达，不污染公共 DTO。
- Foundation 接线可以在真实主链路接受验证，同时保持即时 `off` 回滚。
- 现有 Langfuse、cost log、Evaluation、Benchmark 和报告仍是业务真相源。
- L2/L3 能暴露真实语义缺口，并为 v0.2 提供合法演进依据。

成本与限制：

- Legacy 与 Foundation 在 Phase 1 会并行存在，Evidence 不能直接替代业务结果。
- facts extractor 必须保留 field presence，接线工作比机械 DTO 转换更细。
- 某些历史 `0` 会保守地变为 unknown，牺牲表面精度以避免虚假确定性。
- Evidence sink 成功与业务成功分离，需要独立的闭合运行门禁。

## Rejected Alternatives

### 机械转换 Legacy 数值

拒绝原因：`0` 无法证明真实免费，会永久固化现有语义债务。

### Foundation 结果回写并驱动 Legacy

拒绝原因：这会把 Cycle 1 从旁路验证变成主路径迁移，无法证明非侵入性。

### ErrorEnvelope 取代内部异常

拒绝原因：两仓恢复与副作用语义不同，公共 DTO 会反向渗透业务控制流。

### 自动币种换算或只汇总已知金额

拒绝原因：隐藏 FX 语义或把不完整小计伪装成总成本，都会破坏可审计性。

## Related Documents

- [Foundation Contract Master Spec](../specs/2026-09-10-dual-agent-foundation-contract-master-spec.md)
- [ADR-0001：渐进式契约族抽取](0001-progressive-contract-family-extraction.md)
- [统一领域语言](../../CONTEXT.md)
