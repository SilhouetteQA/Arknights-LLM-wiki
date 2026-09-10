# Spec 17 — Foundation Family Extraction Gate

> Spec ID：`17`  
> Execution Authority：`GATE-DEFINED / NOT EXECUTABLE YET`  
> Executable：NO  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Foundation Cycle 1和真实反馈驱动的Cycle 2均`COMPLETE`  
> Target Repository：cross-repository governance  
> Candidate Phase：future eligibility evaluation only

## Normative References

- Master Part III §23–25、§28–29
- ADR-0001

## Authority Boundary

本文只定义是否允许进入Foundation extraction的判定。它不批准创建独立`agent-core`仓库、删除local mirror、修改依赖或发布package。

门禁未全部满足时唯一合法结论是：

```text
NOT_READY_FOR_EXTRACTION
```

不得因“公共代码已经存在”或“物理移动很简单”降低证据标准。

## Eligibility Formula

```text
FoundationExtractionEligible =
    cycle_1_complete
AND cycle_2_complete
AND real_feedback_revision_exists
AND shared_contract_tests_pass
AND wiki_regression_pass
AND coding_regression_pass
AND duplicate_adapter_evidence
AND rollback_verified
AND semantic_divergence_acceptable
AND dependency_boundary_stable
AND reproducible_quality_gate_pass
AND zero_new_safety_or_side_effect_violation
```

`semantic_divergence_acceptable`表示差异可由Adapter表达而不污染公共契约。`dependency_boundary_stable`表示抽Foundation不会迫使Model、Trace、Evaluation、Checkpoint等未成熟family一起进入package。

## Required Evidence

### Two real cycles

- 0.1 Cycle 1完整L1/L2/L3与A/B/C历史。
- 0.2 Cycle 2包含至少一个真实L2/L3驱动的非纯文档变化。
- 两轮release不可变、Rule traceability和migration notes完整。

### Duplication and abstraction quality

- 两仓Adapter存在可识别重复，抽取会减少重复而非增加abstraction glue。
- 无项目专有字段持续渗入shared models/extensions。
- Foundation public surface不依赖Deferred/Experimental family。

### Reproducible quality gate

必须在任何抽取代码出现前冻结BenchmarkSpec和immutable pre-extraction baseline。候选只可使用相同corpus/config/model/judge/runner/side-effect policy比较。

- 随机LLM质量：使用candidate运行前预登记容差。
- Safety/side effects：未经批准push/PR、sandbox violation、approval bypass等零容忍。
- 无法形成可靠pre/post Evidence时保持NOT_READY，不使用历史0.857或1/5替代。

### Rollback and packaging

- rollback可恢复repo-local mirror/Adapter。
- local mirror OFF与public dependency ON不能重叠。
- clean environment能证明`agent_core`只来自独立dependency。

## Gate Outputs

允许输出：

```text
ELIGIBLE
NOT_READY_FOR_EXTRACTION
```

判定记录必须逐项引用Evidence；不能只写总体PASS。`ELIGIBLE`仍只是允许另立extraction implementation Spec，不是本文件授权实施。

## Forbidden Actions

- 创建/发布`agent-core`distribution。
- 删除两仓local mirror。
- 改动imports、dependencies、packaging或Adapter。
- 抽取未通过gate的family。
- 将物理抽包直接标为1.0.0。

## Completion Criteria

本Gate文档可以在判定记录完整时标记`VALIDATED`；只有正式eligibility decision被接受时才`COMPLETE`。即使结果为NOT_READY，判定本身也可以完整，但不能解锁实现。

## Stop Conditions

- 任一Cycle证据不完整或0.2变化非真实反馈驱动。
- BenchmarkSpec在抽取后才冻结。
- safety violation被质量提升抵消。
- 抽取会拖入未成熟family或产生双份namespace。

## Handoff

若结果ELIGIBLE，下一步是另行生成并批准独立extraction implementation Spec；若NOT_READY，记录缺失门禁及其Evidence，不产生coding task。
