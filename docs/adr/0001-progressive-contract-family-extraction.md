# ADR-0001：渐进式契约族抽取

- 状态：Accepted
- 日期：2026-09-10
- 决策范围：双旗舰 Agent 的公共工程层形成方式
- 实施授权：无；实施以 Master Spec Part I 和后续门禁为准

## Context

Arknights LLM Wiki 与 Knowledge-Augmented Autonomous Coding Agent 都已形成可工作的领域实现，但两者的核心语义并不对称：前者围绕 retrieval、memory、KG 与 thread/session，后者还涉及 sandbox、GitHub、approval、durable task execution 和副作用安全。

立即抽取一个包含共同实现的 `agent_core` 会同时引入三类风险：尚未验证的抽象、对既有主路径的侵入，以及为了接口外观统一而抹平真实语义差异。等所有契约族整体成熟再一次性抽取，又会让 Checkpoint 等高分歧领域阻塞已经稳定的基础契约。

## Decision

采用渐进式、证据驱动的契约族抽取：

```text
Phase 1
repo-local implementation
→ project Adapter
→ mirrored agent_core.contracts payload
→ shared conformance
→ two-repository validation

Phase 2
family-specific extraction gate
→ eligible families move to agent-core distribution
→ projects depend on the same import namespace
```

具体约束：

1. Phase 1 统一跨边界契约，不统一 provider、retrieval、memory、sandbox、approval、GitHub 或 checkpoint 实现。
2. 两仓从 Phase 1 起预留相同 `agent_core.contracts.*` import namespace；此时它只是仓库内镜像，不是独立公共运行时。
3. 一个 Contract Iteration Cycle 必须完成双仓适配、共享契约测试、原测试与适用验证、问题记录和固定提交闭环。
4. 抽取资格以 Contract Family 为最小单位。每个 family 独立完成两轮，其中第二轮必须包含由真实 L2/L3 接入反馈驱动的非纯文档修订。
5. Foundation 是首批 family 的依赖边界；未成熟 family 不得因其他 family 已成熟而搭便车抽取。
6. `agent-core` 可以只包含部分 family。未成熟 family 继续保留镜像和 Adapter；经验证不适合共享的 family 可以标记 `LOCAL_BY_DESIGN`。
7. Phase 1 使用一个锁步 Contract Set version；不为每个 family 建立独立 SemVer。Phase 2 的独立 `agent-core` 统一发布版本。
8. `1.0.0` 表示首批成熟 family 已正式抽取并开始承诺稳定公共 API，不等于所有 Agent 基础设施都已共享。

Family extraction 必须同时证明：两个真实周期、双仓回归、重复实现证据、可回滚、语义分歧可由 Adapter 表达、依赖边界稳定，以及冻结后的 pre/post quality 与 safety gate。

## Consequences

正面结果：

- 先保护两个旗舰项目已经工作的领域实现。
- 让公共 API 由真实接入证据塑形，而不是由假想用例提前设计。
- 已成熟的 Model、Observability 等不会被 Checkpoint 阻塞。
- Phase 2 主要是移动已验证载荷和测试，而不是重新设计公共接口。
- `LOCAL_BY_DESIGN` 允许系统明确承认不可消除的领域差异。

成本与限制：

- Phase 1 需要维护双仓镜像和固定 SHA 协调流程。
- 两仓 Adapter 可能暂时重复；这是进入抽取门禁所需的证据，不是立即消除的目标。
- family 之间必须维护依赖关系和成熟度证据。
- 在完成第二个真实周期前，公共 package 的发布速度会被主动限制。

## Rejected Alternatives

### 立即抽取完整 `agent_core`

拒绝原因：契约尚未经历双仓真实接入，容易把项目专有字段和状态机固化为公共 API。

### 等所有 family 同时成熟后一次性抽取

拒绝原因：高分歧 Checkpoint 会阻塞较稳定 family，也会诱导不成熟契约搭便车。

### 强制统一具体实现或建立单体仓库

拒绝原因：两项目领域层、发布节奏与安全边界不同；共享实现不是 Phase 1 目标。

### 每个 family 独立版本

拒绝原因：双项目规模下版本矩阵和依赖协调成本高于收益；独立成熟度、Schema Hash 和 Cycle Evidence 已足够表达状态。

## Related Documents

- [Foundation Contract Master Spec](../specs/2026-09-10-dual-agent-foundation-contract-master-spec.md)
- [ADR-0002：Foundation 事实语义与旁路治理](0002-foundation-fact-semantics-and-shadow-governance.md)
- [统一领域语言](../../CONTEXT.md)
