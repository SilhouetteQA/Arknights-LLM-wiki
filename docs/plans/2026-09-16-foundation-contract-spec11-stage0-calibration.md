# Spec 11 Stage 0 校准记录 —— Candidate A 冻结前的 provisional 语义固化

> 日期：2026-09-16
> 性质：**非规范性**校准记录。它是 Spec 11 Stage 0 的输入，不是规范真相源。
> 规范真相源：[Master Spec](../specs/2026-09-10-dual-agent-foundation-contract-master-spec.md) · 状态真相源：[execution-status-events.jsonl](../specs/foundation-contract/execution-status-events.jsonl)
> 前置：Spec 01–10 全部 `COMPLETE`（账本 41 条事件）
> 关联：[Spec 10 执行计划](2026-09-16-foundation-contract-spec10-plan.md) · [Spec 10 交接汇报](2026-09-16-foundation-contract-spec10-handoff.md) · 规范提取报告 `output/spec10-normative-extraction-report.md`

## 0. 为什么需要这份文档

Spec 10 的实施暴露了大量母 Spec **未定义**的语义（G-01 – G-27）。当时按用户裁定采用"最小可行语义 + 显式标注 provisional + 留 Spec 11 Stage 0 校准"。这些语义已经**写进代码**并会随 Candidate A 一起冻结 —— 一旦 A 冻结，任何改动都必须把 A 标 `SUPERSEDED` 并回到所属 pre-freeze Spec 形成 A2（`GOV-FRZ-002`）。

因此 Stage 0 的唯一任务：**把每一项 provisional 决定显式写成"冻结"或"保留为开放"，并为"冻结"项提供机器可验证的守卫。** 本文档即该记录；Spec 11 冻结 A 时必须引用它。

---

## 1. 已冻结面（代码 + 字面量测试双钉住）

这三项是本 Cycle 风险最高的发明物。它们现在有**字面量表测试**：任何改动都会让测试显式失败，而不是悄悄漂移。守卫位于 `tests/contracts/test_status_ledger.py::TestFrozenSurface`。

### 1.1 G-22 —— reason_code ↔ 状态转换耦合表【已冻结】

**母 Spec 缺口**：rule 4/8 要求判定"互斥后继"，却从未把 14 个 `reason_code` 映射到状态转换；且 `FREEZE_BOUNDARY_REACHED` / `CANDIDATE_FROZEN` / `EVIDENCE_PUBLISHED` / `COORDINATION_PASSED` / `FINALIZATION_COMPLETE` 这 5 个码没有定义对应哪个转换。

**冻结语义**（`status_ledger.REASON_BY_TRANSITION`，测试 `test_reason_by_transition_table_is_frozen`）：

| from → to | 允许的 reason_code |
|---|---|
| `NOT_STARTED → READY` | `PREREQUISITES_SATISFIED` |
| `READY → IN_PROGRESS` | `EXECUTION_STARTED` |
| `IN_PROGRESS → VALIDATED` | `VALIDATION_PASSED` / `FREEZE_BOUNDARY_REACHED` / `CANDIDATE_FROZEN` / `EVIDENCE_PUBLISHED` / `COORDINATION_PASSED` |
| `VALIDATED → COMPLETE` | `ACCEPTANCE_COMPLETE` / `FREEZE_BOUNDARY_REACHED` / `CANDIDATE_FROZEN` / `EVIDENCE_PUBLISHED` / `COORDINATION_PASSED` / `FINALIZATION_COMPLETE` |
| `COMPLETE → IN_PROGRESS` | `STATUS_CORRECTION`（且 `references` 必须非空并指向更早的 event_id） |

运行时判定（不入静态表）：
- 进入 `BLOCKED`：`BLOCKED` / `SPEC_CONFLICT` / `SPEC_INCOMPLETE`（从 `READY` 或 `IN_PROGRESS`）
- 解除 `BLOCKED`：`PREREQUISITES_SATISFIED` / `EXECUTION_STARTED`，且 `to_status` 必须等于**该 spec 进入 BLOCKED 之前**的状态
- 进入 `SUPERSEDED`：起点 ∈ {`READY`,`IN_PROGRESS`,`BLOCKED`,`VALIDATED`,`COMPLETE`}，理由码 `CANDIDATE_SUPERSEDED`；A2 重启为 `SUPERSEDED → IN_PROGRESS` + `CANDIDATE_SUPERSEDED`（G-24）

**附加不变式**（各有测试）：`from == to` 的 no-op 转换非法；首个违规即失败并输出 `行号 + event_id + 规则`（不 last-line-wins、不忽略、不重排）；14 个理由码必须全部可用（`test_every_reason_code_is_usable_somewhere`）；闭集顺序冻结（`test_reason_codes_closed_set_is_frozen`）。

### 1.2 G-26 —— reducer CLI 表面【已冻结】

**母 Spec 缺口**：Spec10:109 只冻结了 `validate --ledger <path>`，但 `coordinate_cycle.py` 的 check 8 依赖扩展参数。

**冻结表面**（测试 `test_validate_cli_surface_is_frozen`）：`validate` 的自定义 flag 恰好为
`--ledger`（必填）、`--pending-jsonl`、`--pending-envelope`、`--spec-dir`、`--index`、`--self-commit`、`--json`（argparse 自动的 `-h/--help` 不算）。

**语义要点**：`--spec-dir` 默认 = ledger 所在目录（genesis 的 Initial Status 来源，G-25）；`--index` 默认 = `<spec-dir>/00-execution-index.md`，存在时逐项校验 DAG/Authority 常量漂移；`--self-commit` 给出时任何事件引用该 SHA 即判 self-reference 冲突。

**冻结含义**：coordinator 以 `cwd = A 树`、`--ledger <A树>/… --spec-dir <A树>/docs/specs/foundation-contract --index <A树>/…` 调用 reducer，并要求 **reducer 脚本本身存在于候选 A 内**；A 中无 reducer 时 coordinator 记 `STATUS_REDUCER_UNAVAILABLE` 并失败（不自行实现、不静默通过）。

### 1.3 G-03 —— pending suffix 载体【已冻结】

**母 Spec 缺口**：I.3 要求 suffix"由同一 Candidate A 的 reducer 生成/验证、记录目标持久化边界、具备自身 canonical hash"，但 Event Schema 无对应字段、无路径格式定义。

**冻结载体**：
- `PENDING_JSONL_FILENAME = "execution-status-events.pending.jsonl"`（仅事件行，格式与 canonical ledger 逐字一致）
- `PENDING_ENVELOPE_FILENAME = "execution-status-events.pending.json"`（envelope 字段闭集：`pending_version` / `target_boundary` / `candidate_commit` / `event_count` / `suffix_hash`）
- **两者必须与 canonical ledger 同目录**；`status_ledger.canonical_pending_paths(ledger_path)` 是唯一定位入口（测试 `test_pending_suffix_paths_are_canonical`）
- `PENDING_ENVELOPE_VERSION = "1"`；`target_boundary ∈ {candidate_a, evidence_b_wiki, finalization_c_wiki}`
- `suffix_hash` = 对 `.jsonl` **原始字节**的 `sha256:<hex>`；**envelope 不参与自身 hash**（避免自引用）

**归约语义**：`canonical ledger prefix` + `pending suffix` → `effective status`（报告标 `pending=True`）；suffix 不是 Git canonical history、不能单独证明 Cycle COMPLETE、不能跨 Candidate 复用。**下一持久化边界必须原样 append**（`assert_suffix_appended` 校验逐字节前缀 + 内容相等；多/少一个字节、顺序改变、非纯追加都冲突）。

**使用方**：Spec 11 的 freeze-boundary 条目与 Spec 12/13 的完成事件写入 `candidate_a` 边界的 suffix；Spec 14 在 B_wiki 中原样追加。

---

## 2. run manifest 冻结（G-01 / G-02）【已冻结】

Spec 13/14 禁止修改 `config/`，因此两个 manifest 的键名必须在 A 冻结前定死。守卫：`test_manifest_key_sets_are_frozen`（`test_status_ledger.py`）+ `test_shipped_manifests_match_this_repo_registry`（`test_replay_publish_tools.py`，两仓）。

### 2.1 `smoke-v0.1.json`（L3 预登记，20 键）

`manifest_version` · `run_id` · `contract_mode` · `contract_version` · `payload_hash` · `candidate_commit` · `repository_commit` · `evidence_root` · `coverage_policy` · `required_producer_stages` · `model` · `provider` · `case_ids` · `expected_calls` · `max_calls` · `estimated_cost_cap` · `network_requirement` · `side_effect_policy` · `timeout_seconds` · `duration_cap_seconds`

- `required_producer_stages[]` 的键固定为 `producer_id` / `mapping_stage` / `evidence_requirement`（单一 `coverage_policy` 表达不了 Coding 的 ALL_STAGES/ONE_OF 混合，故逐条登记 registry 的 `evidence_requirement`）
- `repository_commit: null` = **运行期由 `AGENT_CONTRACT_COMMIT` 解析**；不得自动推断 HEAD。理由：该字段不在 §13.3 的预登记清单内，Candidate A 的 SHA 在 Spec 11 冻结前不可知，且 Spec 13/14 禁止改 config
- 运行后必须产出 `<evidence_root>/<run_id>/run-summary.json`（G-04，见 §3）
- `coverage_policy ∈ {ALL_STAGES, ONE_OF}`

### 2.2 `replay-v0.1.json`（L2 预登记，10 键）

`manifest_version` · `run_id` · `contract_mode` · `contract_version` · `payload_hash` · `repository_commit` · `output_dir` · `sources` · `max_records` · `reproduction_restriction`

- `sources[]` 的键固定为 `source_id` / `source_class` / `path` / `producer_id` / `mapping_stage` / `runtime_adapter_status` / `evidence_role`
- `sources[]` **必须非空**，`path` 必须为仓库相对、当前存在、位于本仓 `SOURCE_ROOTS`（Wiki `output/eval`；Coding `benchmark/cases`）；空 sources = **exit 2**（绝不静默 PASS）
- DEFERRED producer 的 `mapping_stage` 必须为 `null`；其来源须标 `runtime_adapter_status="DEFERRED"` + `evidence_role="historical_replay_only"`
- source 内容绑定：`sources[].sha256` 与 `raw_retention.source_sha256`（回应 Spec 12 的 "artifact 无法绑定来源" Stop Condition）

### 2.3 run_id 形态（两仓一致）

`foundation-0_1_0-c1-{wiki|coding}-{smoke|replay}`，且必须匹配 `^[A-Za-z0-9_-]+$`（`EVD-RUN-001`）。`estimated_cost_cap.currency` 必须等于本仓 adapter 的 `CURRENCY_CONTEXT`（Wiki `CNY` / Coding `USD`）。

---

## 3. 其余 provisional 决定的处置

| 缺口 | 冻结/保留 | 冻结语义 | 守卫 |
|---|---|---|---|
| **G-04** sink 失败计数无承载 artifact | **冻结** | 运行后汇总 `<evidence_root>/<run_id>/run-summary.json`，键固定：`sink_failure_count` / `rejected_records` / `actual_calls` / `actual_tokens` / `duration_seconds` / `producer_coverage` / `known_cost_components` / `unknown_cost_components`。**缺失即 gate 失败**（无法验证 ≠ 通过） | `validate_local.RUN_SUMMARY_KEYS` + smoke gate 实现 |
| **G-05** "contract-related regression subset" 未定义 | **冻结** | 由 `config/contracts/producer-registry.json` 的 **IN_SCOPE** producer `source_locations` 导出模块名，静态匹配引用它们的 `tests/**` 文件（排除 `tests/contracts/`）；无匹配则退化为 `tests/` 全量并在输出注明 | `validate_local.discover_regression_subset` + 工具自测 |
| **G-06** workflow 触发条件未定义 | **冻结（provisional 推断）** | `contract-local` / `contract-payload-linux`：`pull_request` + `push(main, feature/**)` + `workflow_dispatch`；`contract-coordinate`：**仅 `workflow_dispatch`**。L2/L3 **不建 workflow**（受控手动运行，命令在两仓 `contract-local.yml` 末注释） | workflow YAML + 结构断言；已在真实 runner 跑通 |
| **G-08** `changelog.md` 不在 §11.3 的 B 清单内 | **冻结** | 发布 allowlist 与 coordinator 的 diff allowlist **显式包含** `docs/contracts/releases/<v>/changelog.md`，且 append-only（既有内容逐字节保留） | `publish_evidence.release_allowlist` + 测试 |
| **G-12** comparator 位于非包目录 | **冻结** | 按文件路径 `importlib.util.spec_from_file_location` 加载 `tests/contracts/test_test_baseline.py`，**不**上移到 payload（避免触发 A2） | `validate_local._load_baseline_module` + 自测 |
| **G-13** `--gate smoke` 语义 | **冻结** | 只校验**已完成的 run**，不驱动业务路径；业务运行由受控手动命令完成 | `validate_local.gate_smoke` |
| **G-15 / G-16** expected payload hash 来源 | **冻结** | 只接受显式传入（`--expect-payload-hash` / dispatch 输入）；**不自动推断、不 clone 另一仓、不联网取 hash**。不提供时只做自洽校验 | `validate_local._require_payload_hash` + workflow |
| **G-17** fixture 位置 | **冻结** | 一切 fixture 建在 `%TEMP%` / `tmp_path`，**不入库**（不新增仓库内 fixtures 目录） | 各工具自测 |
| **G-18** 退出码 | **冻结** | `0` 通过 / `1` gate 判定失败 / `2` 用法或配置错误；stderr 必带 `SPEC_STATUS_CONFLICT` 或 `SPEC_INCOMPLETE` 以便 grep。`ToolError` + `main()` 兜底，**无 traceback** | 各工具自测 + CI |
| **G-19** `build` 未声明 | **冻结** | 两仓 `dev` extra 增加 `build>=1.2`；CI 另显式 `pip install build "setuptools>=68"` | `test_packaging.py` |
| **G-23** post-freeze `candidate_commit` 是否必须非空 | **冻结（收严）** | Spec 12–18 的事件必须绑定非空 `candidate_commit`；5 个边界/发布类理由码在任何 spec 都必须非空。**若 Spec 12–15 出现合法 null 事件，必须回修本条** | `test_status_ledger.py` self-reference 类测试 |
| **G-25** genesis 来源未定义 | **冻结** | `--spec-dir` 默认 = ledger 所在目录；该目录必须恰有 18 个子 Spec 文件（缺失 → `SPEC_INCOMPLETE`，退出 2） | genesis 测试 |
| **G-27** I.4 边界表与 rule 7 的表述差异 | **冻结** | 按 rule 7 字面：Spec 01–11 允许 `candidate_commit=null` | 同上 |
| **G-10** `.gitignore` 无前导 `/` | **保留为低危差异** | 不修（不影响行为）；若未来收窄 `/output/` 规则需一并处理 | — |
| **G-11** "cycle-report generator" 无文件路径 | **冻结** | cycle report **就是** coordination artifact：coordinator 写 `coordination.json/.md`，finalizer 逐字节复制为 `<release>/cycle-report.json/.md`。不新增 generator 文件 | `test_cycle_tools.py` |
| **G-14** expected mapping 预登记来源 | **冻结** | 不新增 manifest 键：直接取本仓 registry 的 `producer_id`/`mapping_stage`/`foundation_objects`/`evidence_requirement` 作为预登记 expected，与 adapter 的 actual 比较 | `replay_history` 实现 + 测试 |
| **G-20** 两仓 descriptor 磁盘字节不同 | **冻结（实现注意项）** | 身份一律比较 **canonical payload hash**，**绝不**比较文件原始 sha256 | 跨平台 job 实测通过 |

---

## 4. G-07 基线口径（Spec 11 Candidate Gate 必须采用）

规范 §1.3 / §14.2 / C.4 / Appendix E.2 硬写 Wiki 基线 `542 PASS / 7 SKIP / 3 FAIL → PASS_WITH_KNOWN_BASELINE_FAILURES`；实测三条登记 known failure（`tests/test_stats_collector.py`）**现已全部 PASS**，Spec 09 记录的本地全量为 `637 passed / 10 skipped / 0 failed`，端到端为 **854 passed / 10 skipped / 0 failed**。

**口径（用户已裁定，Spec 11 直接采用）**：按规范自身定义的 `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY` 分支处理 —— **不使 gate 失败**、**标记需 review**、**不静默删除或改写基线**。`known-test-baseline.json` 本 Cycle 不刷新（baseline refresh 属 Spec 01 治理动作）。Coding 侧基线为 `PASS`（其 8–12 条 git-ref 环境诱发失败已在本地消失，CI 上 local gate 全绿）。

---

## 5. L2 语料口径（需 Spec 12 确认接受）

- **Wiki**：`output/eval/cost_log.jsonl`（120 条）+ `output/eval/results_scored.jsonl`（100 条），实测 **220 条全部 `REPRODUCTION_RESTRICTED`**（120 条 mapping `OBSERVED`、100 条 `expected semantic correction`）。
- **Coding**：本仓无任何在仓运行时证据（无 `output/`，`.gitignore` 全忽略），故把**已跟踪的 benchmark artifact** 登记为 replay source；实测 **3/3 条 `LEGACY_DATA_INSUFFICIENT`**（`difference_class="legacy insufficiency"`）。
- **两个被否决的替代方案**（记录理由，避免重复讨论）：仓库外受控路径（provisional schema 要求 path 为仓库相对且当前存在 → 不可验证，且 A 冻结后 config 不可改）；`sources: []`（会让 L2 空转，且 `validate_manifest` 对空 sources 显式 exit 2）。
- **需 Spec 12 决定**：接受"管线已跑通但数据不足"作为本 Cycle 的 L2 结论，还是要求补造可复现语料（后者超出 v0.1 范围且禁止改 config）。
- **已知不稳定**：`output/eval/cost_log.jsonl` 是 tracked 且会被项目测试追加（本会话 +12 行）→ 同一 commit 下语料亦非逐字节稳定。已用 per-source sha256 + `REPRODUCTION_RESTRICTED` 缓解；**Spec 11 可决定是否在 A 前冻结来源快照**（当前未做）。

---

## 6. 明确**不**冻结 / 留给后续的事项

| 项 | 现状 | 归属 |
|---|---|---|
| `contract-coordinate.yml` 的真实执行 | 需要闭合 cycle plan + Coding 只读 token；**尚未真实跑过** | Spec 15 |
| action pin 到 commit SHA | 仓库无既有 pin 约定，未新建 | 可选加固 |
| 母 Spec 中"未定义语义"本身 | 本文档只是**校准记录**，不修改母 Spec；母 Spec 的缺口仍在 | 建议在 Spec 16（Cycle 2）或母 Spec 回修中补全，见 §7 |
| Wiki 3 个 API-key 依赖测试 | CI 用**占位环境值**（非凭据）绕过"配置存在性检查"；测试本身仍隐含依赖 provider 配置 | 项目测试卫生问题，非本 Cycle 范围 |

---

## 7. Spec 11 Stage 0 行动清单

1. **逐条 ratify 本文档 §1–§3**（把"已冻结"确认为 Stage 0 的正式决定），并把本文档路径写进 Spec 11 的 freeze-boundary 记录。
2. **确认 §5 的 L2 语料口径**（Wiki `REPRODUCTION_RESTRICTED` / Coding `LEGACY_DATA_INSUFFICIENT` 是否作为本 Cycle 结论）。
3. **确认 §4 的 G-07 口径**并写定 Candidate Gate 的期望文本。
4. 用 `canonical_pending_paths()` 建立 `candidate_a` 边界的 suffix 载体，把 Spec 11 的 freeze-boundary 条目写入其中。
5. 冻结 A：两仓各取 `feature/foundation-contract-spec10` 的 HEAD 作为候选提交（**不是 `main`**，两仓 main 都没有 Foundation 产物），记录 `contract_payload_hash`（当前 `sha256:64049830…`）。
6. 跑 L1 与全量回归，记录 `contract-tests` 证据；按 §4 口径判定。
7. 把 A 的 SHA 与 payload hash 写入账本 `FREEZE_BOUNDARY_REACHED` / `CANDIDATE_FROZEN` 事件（`candidate_commit` 非空）。

> 冻结之后：任何 provisional 语义的进一步修改都必须 `SUPERSEDED` 当前 A 并回到所属 pre-freeze Spec 形成 A2 —— 这正是本文档要在此之前完成的原因。

---

## 8. 机器可验证的守卫（本记录不是空头承诺）

```powershell
# 冻结面（G-22 耦合表 / G-26 CLI 表面 / G-03 suffix 载体 / G-01+G-02 manifest 键集）
D:\CodexPython312\python.exe -m pytest tests/contracts/test_status_ledger.py -q -k FrozenSurface
# 全部契约测试（Wiki 当前 319 passed / 3 skipped）
D:\CodexPython312\python.exe -m pytest tests/contracts -q
# 两仓真实账本仍须合法归约
D:\CodexPython312\python.exe scripts/contracts/status_ledger.py validate --ledger docs/specs/foundation-contract/execution-status-events.jsonl
# 本地契约门禁（8 步）
D:\CodexPython312\python.exe scripts/contracts/validate_local.py --gate pr
```

CI：`.github/workflows/contract-local.yml`（Windows L1）+ `contract-payload-linux.yml`（Linux canonical hash）在两仓均已真实跑通（2026-09-16，全绿）。
