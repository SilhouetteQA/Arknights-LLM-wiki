# Spec 09 — Shared Conformance and Project Contract Tests

> Spec ID：`09`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Specs 02–08 `COMPLETE`  
> Target Repository：`WIKI_REPO`、`CODING_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §0.2/0.3、§13.1、§14.1/14.2、Appendix A、Appendix F.1–F.3
- 全部 v0.1 Contract Rule IDs

## Objective

完成共享 conformance、双仓 Adapter/wiring/sink/packaging前置测试，以及确定性 invariance、replay assertion 和 producer coverage harness。这里开发并验证测试能力，但不形成正式 Candidate-bound L1/L2/L3 Evidence。

## Allowed Changes

Shared payload：

```text
agent_core/contracts/conformance/**
agent_core/contracts/contract.md（仅修复已确认规范遗漏）
agent_core/contracts/payload-descriptor.json
```

每仓：

```text
tests/contracts/test_foundation_mapping.py
tests/contracts/test_evidence_sink.py
tests/contracts/test_producer_wiring.py
tests/contracts/test_business_invariance.py
tests/contracts/test_test_baseline.py
tests/contracts/test_packaging.py
tests/contracts/conftest.py（如需要）
```

## Forbidden Changes

- 为让测试通过改变已确认规范。
- Shared tests import Wiki/Coding modules。
- 用 fixture 冒充 L2/L3。
- 将新增 tests 混入 Existing Baseline comparison。
- 因三条已知 Wiki failure 放宽所有失败。

## Implementation Steps

1. 为 Appendix A 每个 payload Rule ID建立机器 metadata；允许一规则多测试/一测试关联紧密多规则。
2. 完成 Usage、Cost、CostSummary、extensions、Error、Evidence、Mode、Versioning全边界矩阵。
3. Shared tests只接收model/factory/Protocol实现，不 import项目。
4. Wiki/Coding Adapter tests分别覆盖真实 Legacy facts 与 expected Foundation mapping。
5. sink tests覆盖atomic temp/replace、concurrency、invalid IDs、64 KiB、injected I/O failure与无递归。
6. wiring tests静态/动态证明Registry中每个 in-scope stage调用同一runtime。
7. invariance harness捕获output、decision、side effects、Legacy telemetry四类可比较对象。
8. replay assertions比较 observed input、expected mapping、actual mapping；不得在sanitizer中预先“修正”输入。
9. coverage assertions读取Registry，不把expected stages写死在脚本中。
10. baseline comparator按Existing PASS/SKIP/known fingerprint/New Contract tests分组。
11. 自动生成Rule traceability预览，若Rule无测试或测试引用未知Rule则失败。
12. 每次共享测试变更通过Spec03 bundle同步，双仓hash保持相同。

## Development Validation Commands

两仓分别运行：

```powershell
python -m pytest agent_core/contracts/conformance -q
python -m pytest tests/contracts -q
```

这些结果证明测试实现可用；Spec 11必须在冻结A上重新执行，不能复用此处结果作为正式L1。

## Expected Outputs

- 完整shared conformance suite与Rule metadata。
- 两仓项目contract tests。
- deterministic invariance/replay/coverage/baseline assertion libraries。
- traceability预览和无缺口检查。

## Acceptance Criteria

- 每条v0.1 payload Rule至少一个shared conformance落点。
- 所有in-scope producer/stage至少一个wiring test。
- 所有新增测试100% PASS。
- Wiki三条known failure只在baseline comparator中精确allow；Coding无allowlist failure。
- shared payload测试文件在两仓hash一致。

## Stop Conditions

- 某Rule无法写出确定性测试且`contract.md`也无法明确语义。
- 项目测试必须读取敏感业务内容。
- invariance只能比较最终文本而无法观察决策/副作用/Legacy telemetry。
- 为通过测试需要改动Deferred领域。

## Rollback / Handoff

项目tests可各自回退；shared conformance必须canonical回退并重同步。Handoff列出Rule coverage、producer stage coverage、fixture来源类别和仍未形成的L2/L3事实。
