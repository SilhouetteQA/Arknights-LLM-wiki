# Spec 01 — Baseline Freeze and Governance Skeleton

> Spec ID：`01`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES  
> Initial Status：`READY`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：无  
> Target Repository：`WIKI_REPO`、`CODING_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §0.7、§1、§7、§14、§17 Stage 0、Appendix E、Appendix I
- `FND-REG-001` 至 `FND-REG-005`
- `GOV-SPEC-001`、`GOV-STAT-001`、`GOV-STAT-002`

## Objective

在任何契约代码出现前冻结双仓事实基线、Producer 范围和治理目录，使后续实现能够判定“新回归”“范围扩大”和“状态推进”。本步骤不创建 `agent_core`，也不修改业务逻辑。

## Inputs

- 两仓当前 canonical branch 与实际 HEAD。
- Master Spec 的测试、Benchmark 和 Producer 审计结果。
- Wiki 已知 StatsCollector 失败事实。
- 空的 canonical execution status ledger。

若实际 HEAD、测试集合或 producer 位置已相对 Master 快照变化，必须记录为 baseline refresh，不得静默复用旧数字。

## Allowed Changes

Wiki 与 Coding：

```text
config/contracts/producer-registry.json
config/contracts/known-test-baseline.json
.gitignore
```

Wiki canonical docs：只允许按 Master Appendix I 初始化状态验证约束；账本保持空，不追加“文档创建”事件。

## Forbidden Changes

- `agent_core/**`、Adapter、producer 业务文件、测试实现和 CI workflow。
- 修复 Wiki StatsCollector 失败。
- 改动 Benchmark case、评分、报告或历史数据。
- 把新发现 producer 自动列为 `IN_SCOPE`。

## Execution Steps

1. 解析 `WIKI_REPO` 与 `CODING_REPO`，记录 repository identity、branch、HEAD、Python、Pydantic、pytest 和 packaging backend。
2. 在两个固定 HEAD 上分别执行唯一 canonical full-test command：`python -m pytest tests/`。
3. 将 Existing PASS、SKIP、FAIL nodeid 分组；不得把未来契约测试混入 baseline existing set。
4. Wiki 对三个 StatsCollector failure 生成规范化指纹，核对 Master Appendix E；Coding 确认 known failures 为空。
5. 审计 Master §7 的每个 producer source location 和 mapping stage 是否仍存在。
6. 将全部已发现 producer 记录为 `IN_SCOPE`、`DEFERRED`、`OUT_OF_SCOPE_BY_DESIGN` 或 `UNKNOWN`；不得遗漏来源和理由。
7. 更新 `.gitignore`，至少排除 staging、raw business evidence、private replay 和环境文件；不删除已有 ignore 规则。
8. 验证 `execution-status-events.jsonl` 为 0 bytes；此时 reducer genesis 必须得到 Spec 01 READY、02–18 NOT_STARTED。

## Required File Semantics

`known-test-baseline.json` 至少包含：

```text
baseline_commit
canonical_command
existing_pass_nodeids
existing_skip_nodeids
known_failures[nodeid, exception_type, normalized_signature, fingerprint, scope]
tool_versions
captured_at
```

`producer-registry.json` 必须符合 Master Appendix B；Producer ID 表示治理语义，mapping stage 表示当前实现路径。

## Validation Commands

在各自仓库运行：

```powershell
python -m pytest tests/
```

在 Wiki 额外复核三个已知 nodeid；在本步骤实现的配置校验方式可使用现有 JSON parser，但不得提前发明 Spec 10 的 validation CLI。

## Expected Outputs

- 双仓独立 baseline JSON。
- 双仓 producer registry。
- 明确的 benchmark historical-reference 状态。
- staging/private evidence ignore 规则。
- baseline deviation report（仅在与 Master 快照不一致时）。

## Acceptance Criteria

- Wiki 每个既有失败都绑定 nodeid、异常类型和相同规范化根因；任何新增失败均已阻止本步骤完成。
- Coding baseline 无失败；PASS 变 SKIP 的行为被视为失败。
- 所有已发现 producer 均有显式状态，in-scope mapping stages 完整。
- 没有修改业务、测试、Benchmark 或契约代码。
- 空 Ledger genesis 可唯一解析。

达到以上条件后才可追加真实状态事件使 Spec 01 进入 `VALIDATED`/`COMPLETE` 并解锁 Spec 02。

## Stop Conditions

- canonical test command 无法稳定收集。
- 失败 nodeid 或 fingerprint 相对 Master 发生漂移且原因未确认。
- Producer location 不存在或出现新的成本主链路但无法分类。
- 需要修业务代码才能形成 baseline。
- Master 与当前仓库事实冲突。

触发时记录 `BLOCKED`、`SPEC_CONFLICT` 或 `SPEC_INCOMPLETE`，不继续 Spec 02。

## Rollback / Handoff

删除本步骤新增的 config 文件和本次新增的 ignore 行即可回到工程前状态；不得删除既有用户 ignore 规则。Handoff 必须列出两个实际 baseline SHA、测试统计、已知失败与 Producer coverage。
