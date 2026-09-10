# Spec 11 — Candidate A Freeze, L1 and Full Regression

> Spec ID：`11`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 10 `COMPLETE`  
> Target Repository：`WIKI_REPO`、`CODING_REPO`  
> Candidate Phase：A freeze boundary

## Normative References

- Master §13.1、§14.2、§16.2、§17 Stage 5–6、Appendix C/E/I
- `FND-REG-001` 至 `FND-REG-004`
- `GOV-FRZ-001/002`

## Objective

将两仓全部 Contract、Adapter、producer seams、tests、validation tooling、packaging、config 和 workflows冻结为Candidate A，并在两个精确A SHA的干净checkout上正式重跑L1与完整回归。Spec09/10开发期PASS不能代替本步骤Evidence。

## Inputs

- Specs 01–10 `COMPLETE`的可归约状态与Evidence引用。
- 两仓clean worktree候选内容。
- 已验证的完整post-freeze tooling inventory。
- 双仓known-test-baseline。

## Allowed Changes Before Freeze

- 只允许追加Wiki canonical状态事件，确认Specs01–10真实完成并让Spec11进入`IN_PROGRESS`/`FREEZE_BOUNDARY_REACHED`。
- 修复发现的问题必须回到拥有该文件的Spec01–10执行并重新验证依赖。

## Forbidden Changes After Freeze

冻结A后禁止修改任何：

```text
Contract Payload
Adapter / producer wiring / business code
tests / fixtures / assertions
replay / sanitizer / smoke / invariance / publisher tooling
status reducer / coordinator / finalizer
config / pyproject / lock files / workflows
```

正式L1和回归只产生ignored/controlled staging结果，不提交Evidence B。

## Freeze Procedure

1. 验证两仓无不明工作树变化；现有用户变化必须被明确归属，不能误纳入Candidate。
2. 生成pre-freeze inventory：Payload Hash、Registry Hash、test set、tool versions、workflow files和package result。
3. 在Wiki账本追加截至freeze boundary的合法pre-A events；不得写尚不存在的A SHA。
4. 分别形成A_wiki和A_coding固定提交；若使用PR/squash，以最终合并SHA为A。
5. 标记Candidate artifact状态为`FROZEN`；该状态在A外部staging记录，后续B_wiki事件才能绑定A。
6. 从每个A的干净checkout重新安装/执行权威环境，不使用包含未提交修改的原工作区。

## Formal L1

在两个A上分别执行：

```powershell
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
python -m pytest agent_core/contracts/conformance -q
python -m pytest tests/contracts -q
python scripts/contracts/validate_local.py --gate pr
python -m build
```

所有结果必须绑定repository、A SHA、contract version和Payload Hash。

## Formal Full Regression

```powershell
python -m pytest tests/
```

Wiki：只允许已登记三个nodeid且fingerprint一致，期望`PASS_WITH_KNOWN_BASELINE_FAILURES`。Coding：无失败，期望`PASS`。任何baseline PASS→SKIP/FAIL均失败；新增contract tests单独要求100% PASS。

## Expected Outputs

- 固定A_wiki、A_coding SHA。
- Candidate inventory与Payload identity。
- Candidate-bound L1结果。
- Candidate-bound full regression结果和baseline comparison。
- 尚未发布的Spec11状态/Evidence events。

## Acceptance Criteria

- A包含Specs12–15所需全部工具和workflow。
- 两仓相同contract version与Payload Hash。
- L1全部PASS。
- Wiki/Coding回归状态满足各自严格规则。
- 正式验证在exact A clean checkout运行。
- A形成后无实现文件变化。

满足后，将绑定A的Spec11 `VALIDATED/COMPLETE` events写入受控pending suffix；同一A中的reducer验证canonical prefix + suffix后，可并行解锁Specs12、13。该suffix必须在Spec14逐字节append到B_wiki Ledger，否则Specs12/13 Evidence无效。

## Stop Conditions

- 任一post-freeze工具缺失或未开发验证。
- A后需要改代码/测试/配置才能通过L1或回归。
- known failure fingerprint漂移或新失败。
- Payload Hash不一致或clean wheel失败。
- Candidate包含无关用户变化。

## Supersede / Rollback

冻结前可回到对应前置Spec修正。冻结后任何Candidate defect都使A`SUPERSEDED`；保留A身份，回到拥有缺陷的Spec，重新验证其downstream并形成A2。不得修补A后继续使用旧SHA。
