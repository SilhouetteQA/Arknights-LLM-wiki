# Spec 16 — Cycle 2 Feedback Intake and Evolution Process

> Spec ID：`16`  
> Execution Authority：`FEEDBACK-BOUND / PROCESS-ONLY`  
> Engineering Implementation Executable：NO  
> Governance Process Executable：MAY，only after qualified trigger exists  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 15 / Cycle 1 `COMPLETE`，以及真实L2/L3问题  
> Target Repository：canonical decision in `WIKI_REPO`  
> Candidate Phase：future Cycle 2 planning only

## Normative References

- Master Part II §19–22、§12.6、Appendix I
- ADR-0001、ADR-0002

## Authority Boundary

本文只允许执行反馈接收、证据验证、语义分类、版本判断和迁移计划形成。它不批准任何具体v0.2字段、validator、Schema、Error code或Adapter修改。

```text
Qualified real feedback absent
→ Foundation remains CYCLING
→ Spec 16 remains NOT_STARTED/BLOCKED
→ no artificial v0.2
```

纯fixture、预想需求、一般重构愿望或“为了完成第二轮”不能单独构成trigger。

## Qualified Inputs

至少一个问题必须来自：

- Cycle 1 L2 Historical Replay中可引用的真实历史语义冲突；或
- Cycle 1 L3 Fresh Real-path中可引用的当前运行问题。

Evidence引用必须绑定Cycle 1 Payload、A/B和发布Evidence ID。Contract test可以帮助复现与验证，但不能把假想case提升为真实反馈。

## Feedback Intake Process

```text
Observed issue
→ Evidence reference validation
→ semantic classification
→ current Rule ID impact
→ schema/invariant/mapping/behavior impact
→ two-repository Adapter impact
→ compatibility and version decision
→ migration note
→ v0.2 candidate proposal
→ explicit authorization before implementation
```

每个proposal至少回答：

1. 旧契约为何无法诚实表达观察事实。
2. 问题是Contract defect、Adapter defect、Evidence defect还是Legacy insufficiency。
3. 是否需要非纯文档规范变化。
4. 哪些Rule ID新增、修改、deprecated；旧编号不得复用。
5. Schema不变时是否仍有序列化/映射/行为语义变化。
6. 两仓如何迁移，哪些项目差异继续留在Adapter。
7. 为什么不能通过修Adapter或保持NOT_OBSERVED解决。

## Allowed Outputs

```text
feedback-intake record
evidence-linked semantic issue
contract impact analysis
version decision
migration proposal
Cycle 2 authorization request
```

任何候选change都以“PROPOSED / NOT AUTHORIZED”存在，直到用户或治理方明确批准新的implementation-ready Spec。

## Forbidden Outputs

- 已实现的v0.2代码、Schema、tests或Adapter。
- 未经Evidence支持的新字段。
- 为满足Cycle 2而做的无意义rename或churn。
- 将tooling bug包装成真实契约演进。
- 承诺0.1/0.2并行runtime compatibility。

## Process Validation

- Evidence ID在Cycle 1 release中存在且状态允许支持结论。
- 问题来自L2/L3而非纯fixture。
- 语义变化至少属于字段/validator/error/event/versioning/envelope行为之一，且影响真实接入。
- Contract Set version按minor/patch规则判定。
- Migration note明确0.1→0.2及不支持旧runtime的范围。

## Completion Criteria

Spec 16只有在形成一份证据充分、尚未实施的Cycle 2 change proposal并获得独立实施授权时，才可进入`VALIDATED/COMPLETE`。若真实反馈不足，保持`CYCLING`是正确结果，不构成失败。

## Stop Conditions

- Evidence无法公开引用或只存在主观推测。
- 两仓对问题语义理解不同且尚未reconcile。
- 提案会强迫未成熟family进入Foundation。
- 变更实质是项目专有需求，应留Adapter/extension。
- 执行者准备直接修改Contract代码。

## Handoff

Handoff只交付change proposal、Evidence引用、受影响Rule和migration/version决定。后续实现必须另行形成新的implementation-ready执行投影，不得把本文直接转换为coding task。
