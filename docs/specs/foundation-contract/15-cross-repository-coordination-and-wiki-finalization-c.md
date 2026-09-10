# Spec 15 — Cross-repository Coordination and Wiki Finalization C

> Spec ID：`15`  
> Execution Authority：`IMPLEMENTATION-READY — COORDINATION/FINALIZATION ONLY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 14 `COMPLETE`  
> Target Repository：coordination truth in `WIKI_REPO`; read-only checkout of `CODING_REPO`  
> Candidate Phase：fixed A/B coordination then C_wiki

## Normative References

- Master §15.3、§16.4–16.7、§17 Stage 10、Appendix C.5/D.3/F.4/I.4
- `FND-REL-001` 至 `FND-REL-006`
- `GOV-STAT-004`

## Objective

使用Candidate A中已经冻结的Wiki coordinator验证两个固定A/B，产生`PASS/READY_FOR_FINALIZATION`，再由Wiki-only C持久化唯一Cycle Report、current pointer与最终状态事件。Coordination PASS本身不等于Cycle COMPLETE。

## No-implementation Boundary

不得修改coordinator、workflow、report generator、finalizer、status reducer、Schema或任何Candidate/Evidence文件。Coordinator defect可以在新版本工具下固定同一A/B重验，但若工具属于Candidate A治理范围，则必须按Master缺陷分流形成A2；不能在本步骤热修后伪称仍由A验证。

## Closed Cycle Plan

在两个B已经存在后，于协调系统外部构造：

```text
cycle_id
target contract version
expected Payload Hash
A_wiki / A_coding
B_wiki / B_coding
created_at
```

Cycle plan不属于任一A/B Git tree，不允许自动搜索替代SHA。

## Coordination Checks

1. checkout两个固定A与B；Coding token只读且不得进入artifact/log。
2. 验证每仓`A ancestor of B`与A→B diff allowlist。
3. 重新计算A_wiki/A_coding version与Payload Hash；相同版本不同hash只能为`DIVERGED`。
4. 验证两Evidence Manifest分别引用对应A与同一Payload，且Evidence commit为B。
5. 计算两项目独立Evidence Manifest Hash；不同是正常事实。
6. 验证L1/L2/L3、full regression、producer coverage、reproducibility和publication scan结果。
7. 验证Wiki Ledger在B中纯追加并可由A中reducer合法归约。
8. 记录coordinator repository、A中的coordinator commit/tool version、workflow version和run ID。
9. 生成canonical JSON/Markdown coordination artifact，状态只能`PASS/READY_FOR_FINALIZATION`、`FAILED`或`DIVERGED`。

## Wiki Finalization C

Coordination PASS后：

1. 复制与coordination artifact hash一致的`cycle-report.json/.md`到Wiki release。
2. 生成最小`current.json` pointer。
3. 只追加Spec15 `COORDINATION_PASSED`、`FINALIZATION_COMPLETE`等合法Ledger events；不写C SHA。
4. 形成C_wiki，验证`B_wiki ancestor of C_wiki`和严格finalization diff allowlist。
5. 将C合并canonical branch后，从该branch重新验证reports、pointer、Ledger、ancestry与diff。
6. 只有此时外部治理结论与Ledger归约才可称Cycle COMPLETE。

Coding停在B_coding，不提交cycle-report、current pointer或Ledger。

## Validation Commands

```powershell
python scripts/contracts/coordinate_cycle.py --plan <CYCLE_PLAN> --output <COORDINATION_OUTPUT>
python scripts/contracts/finalize_cycle.py --coordination <COORDINATION_OUTPUT> --release docs/contracts/releases/0.1.0
```

最终验证必须针对canonical branch上的C tree，而不是未提交工作区。

## Expected Outputs

- 可复现coordination artifact与identity。
- C_wiki SHA。
- Wiki唯一cycle-report/current pointer。
- Wiki Ledger最终append events。
- Cycle COMPLETE验证记录。

## Acceptance Criteria

- 两仓固定A/B完整闭合且payload一致。
- Coordination artifact未提前宣称COMPLETE。
- C只含finalization allowlist，报告hash精确一致。
- C与Ledger均不引用自身SHA。
- Coding无重复最终化。
- C合并后canonical verifier判定Cycle COMPLETE。

## Stop Conditions

- plan不闭合或任一SHA不存在。
- Evidence commit/payload/verified A不一致。
- A/B diff越界、Ledger非纯追加或状态无法归约。
- Coordinator需要调用真实模型或moving main。
- C混入规范、实现、测试或旧Evidence修改。

## Retry / Rollback

Evidence defect回Spec14形成B2；Candidate defect回拥有者Spec并形成A2；Coordinator defect固定同一A/B按新coordinator identity重验；Finalization copy/allowlist defect保留原失败C历史，使用相同coordination artifact形成合法C2。不得覆盖任何既有B、coordination result或C。
