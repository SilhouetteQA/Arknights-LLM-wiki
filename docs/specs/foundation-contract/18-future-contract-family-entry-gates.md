# Spec 18 — Future Contract Family Entry Gates

> Spec ID：`18`  
> Execution Authority：`GATE-DEFINED / NOT EXECUTABLE YET`  
> Executable：NO  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Foundation兼容边界达到相应family所需稳定度  
> Target Repository：cross-repository governance  
> Candidate Phase：future family maturity evaluation only

## Normative References

- Master §26–29
- ADR-0001

## Authority Boundary

本文只定义Model、Tool、Observability、Evaluation和Checkpoint何时可以从`EXPERIMENTAL`进入`CYCLING`，以及未来如何评估抽取。它不定义未来Pydantic字段、Protocol签名、文件清单或实现任务。

## Shared Maturity Model

```text
EXPERIMENTAL
CYCLING
ELIGIBLE
EXTRACTED
LOCAL_BY_DESIGN
DEPRECATED
```

每个family独立评估Cycle 1、Cycle 2、双仓回归、重复度、语义分歧、跨族依赖、rollback和breaking risk。一个family成熟不授权其他family搭便车。

## Foundation Prerequisite

任何future family进入正式CYCLING前，至少要证明其依赖的Foundation version/error/extension/Usage/Cost边界足够稳定。上游不一定已物理抽包，但必须有明确兼容边界。

## Model Entry Gate

MAY enter CYCLING only when真实双仓路径证明共同ModelRequest/ModelResult边界有重复价值，并能在不统一provider、retry、timeout或内部state的前提下表达。

所需Evidence类别：timeout、cancellation、invalid request、usage、structured output和provider-specific extension边界。本文不预定义字段或签名。

## Tool Entry Gate

MAY enter CYCLING only whenWiki read-only knowledge tools与Coding side-effect tools的共同形状不会抹平risk、approval、sandbox和side-effect语义。

若公共接口需要`wiki.*`或`coding.*`字段才能工作，保持EXPERIMENTAL或LOCAL_BY_DESIGN。

## Observability Entry Gate

MAY enter CYCLING only whenTraceContext/Span/Event不依赖半成熟ModelResult/ToolResult，并能保持两仓现有Langfuse/OTel/report/Dashboard实现独立。

Provider/project extensions必须opaque；不得为了统一展示系统而改变业务观测链路。

## Evaluation Entry Gate

MAY enter CYCLING only when可以只共享Result Envelope、run metadata和regression primitives，而不统一Wiki quality score与Coding resolution/safety score。

Benchmark runner、judge和项目指标继续本地，除非未来真实Evidence另有证明。

## Checkpoint Entry Gate

Checkpoint预期高语义分歧：Wiki偏thread/session persistence；Coding包含durable task、sandbox、side-effect idempotency与approval replay safety。

合法结论包括：

- 只共享CheckpointStore行为抽象和少量identity/metadata/error；
- 具体数据模型与persistence semantics保持项目本地；
- 整个family标记`LOCAL_BY_DESIGN`。

“决定不抽取”是成熟结论，不是失败。

## Family Cycling Requirements

每个进入CYCLING的family必须重新使用：

```text
L1 deterministic conformance
L2 production-history replay
L3 current real-path smoke
off/observe non-intrusion
project regression
two real iteration cycles
family-specific extraction gate
```

Cycle 2同样必须由真实反馈产生非纯文档演进，不能人为制造Schema churn。

## Gate Outputs

对每个family只允许：

```text
REMAIN_EXPERIMENTAL
MAY_ENTER_CYCLING
LOCAL_BY_DESIGN
DEPRECATED
```

`MAY_ENTER_CYCLING`只允许另立family-specific implementation-ready Master/Child Specs；它不直接生成coding task。

## Forbidden Actions

- 在本文中定义未来字段、validator、Protocol或目录。
- 因Foundation已抽取就自动抽取其他family。
- 为接口“看起来统一”抹平实际不同语义。
- 为每个family创建独立SemVer矩阵。
- 把Checkpoint具体状态机强行共享。

## Stop Conditions

- 所需Foundation上游边界仍在变化或没有完成其证据周期。
- 两仓对候选family的共同语义无法在Adapter边界内协调。
- 只有假想fixture，没有L2/L3真实需求。
- 进入CYCLING会迫使另一个未成熟family搭便车。
- 评估者开始预写未来字段、Protocol或实现任务。

## Completion Criteria

某family的entry assessment只有在前置Evidence、依赖图、语义差异和状态决定均可追踪时才完整。没有足够Evidence时保持EXPERIMENTAL，不产生实现授权。

## Handoff

任何`MAY_ENTER_CYCLING`决定必须交给新的、单独批准的family规格工作流；本文件只提供门禁输入，不承担未来实施细节。
