# Spec 10 交接汇报 — Packaging and Local Contract CI

> 日期：2026-09-16
> Spec：`10 — Packaging and Local Contract CI`（`IMPLEMENTATION-READY`，DAG：`09 → 10 → 11`）
> 分支：Wiki / Coding 各 `feature/foundation-contract-spec10`
> 规范真相源：[Master Spec](../specs/2026-09-10-dual-agent-foundation-contract-master-spec.md) · 状态真相源：[execution-status-events.jsonl](../specs/foundation-contract/execution-status-events.jsonl)
> 性质：**非规范性**交接记录（不进入 Contract Payload，不构成规范载体）

本文件只记录 Spec 10 实际交付、验证证据、provisional 决策、deviation 与向 Spec 11 的交接事实。若与母 Spec 冲突，以母 Spec 为准并触发 `SPEC_CONFLICT`。

---

## 1. Pre-freeze tooling inventory

Spec 10 是 Candidate A 冻结前最后一个实施单元。以下全部实现**必须在 A 冻结后保持不变**（`GOV-FRZ-001`）；冻结后若发现缺陷，只能把 A 标 `SUPERSEDED` 并回到所属 pre-freeze Spec 形成 A2（`GOV-FRZ-002`）。

### 1.1 两仓共有

| 产物 | 规范来源 | 说明 |
|---|---|---|
| `pyproject.toml` 变更 | Master §3.3、Spec10:62 | 显式 `[build-system]`、`pydantic==2.13.4` 精确固定、显式 package discovery（含 `agent_core*`）、contract payload 非 Python 文件注册为 package data、`dev` extra 增加 `build>=1.2` |
| `scripts/contracts/validate_local.py` | Master §15.1、§11.2、§11.4、Appendix C.1/C.3 | `--gate pr`（8 步）/ `--gate candidate`（+ 全量回归 + nodeid/指纹门 + L1/L2/L3 证据闭合）/ `--gate smoke`（§11.2 八项闭合） |
| `scripts/contracts/replay_history.py` | Master §13.2、Spec12 | allowlist 历史来源 + strict mapping + `OBSERVED / NOT_OBSERVED / LEGACY_DATA_INSUFFICIENT / REPRODUCTION_RESTRICTED` 分类 + sanitized corpus + secret/path/forbidden-field/size/Schema 扫描 |
| `scripts/contracts/publish_evidence.py` | Master §11.3、D.2、Spec14 | CLI（A 中冻结）`--candidate <A_SHA> --release-version 0.1.0`；allowlist 构造（非 denylist）；六类扫描；`contract-manifest.json` / `changelog.md`（append-only）/ `validation/<repo>/{run-manifest,evidence-manifest,validation-report,rule-traceability,sanitized-replay-corpus}`；Evidence Manifest **不含**自身 hash 与 B SHA |
| `config/contracts/smoke-v0.1.json` | Master §13.3、Spec13 | L3 run 预登记（provisional 键名） |
| `config/contracts/replay-v0.1.json` | Master §13.2、Spec12 | L2 run 预登记（provisional 结构） |
| `tests/contracts/test_packaging.py` | Spec10:62-65、C.3 | `FND-PKG-003` 落点：wheel/package-data/clean-env import 与 payload 读取 |
| `.github/workflows/contract-local.yml` | §15.1、Appendix C.4、F.2/F.3 | Windows Local PR Contract Gate，无密钥、不跨仓 |
| `.github/workflows/contract-payload-linux.yml` | §15.2、C.3 | Linux 最小依赖 canonical hash job |
| `tests/contracts/test_validate_local_tools.py` | Spec10:32/44 | `validate_local.py` 工具自测（扫描/junit/指纹/判定/子集/用法门/commit 解析） |

### 1.2 仅 Wiki（canonical author + coordinator + finalizer）

| 产物 | 规范来源 | 说明 |
|---|---|---|
| `scripts/contracts/status_ledger.py` | Appendix I、Spec10:78-79 | Event Schema / genesis / DAG 与 Authority / 8 条 reducer 规则 / append-only / canonical prefix + controlled pending suffix；非法 → `SPEC_STATUS_CONFLICT` |
| `scripts/contracts/coordinate_cycle.py` | §16.4、§16.5、Spec15 | `--plan` / `--output`；9 项校验；17 字段输出；只能 `PASS/READY_FOR_FINALIZATION` / `FAILED` / `DIVERGED`，**绝不**输出 `COMPLETE` |
| `scripts/contracts/finalize_cycle.py` | §16.6、Spec15 | coordination hash 精确一致；`current.json` 仅 4 字段；不记录 C 自身 SHA；严格 C allowlist；B_wiki ancestor of C_wiki；**拒绝写真实账本** |
| `.github/workflows/contract-coordinate.yml` | §15.3、Spec10:91 | 仅 `workflow_dispatch`；固定 A/B SHA（机器校验 `^[0-9a-f]{40}$`）；只读 Coding checkout token；不调用真实模型、不产生 L3 |
| `tests/contracts/test_status_ledger.py` | Spec10:79 | 8 类用例：duplicate ID / missing prerequisite / `READY→COMPLETE` 跳跃 / mutually exclusive successors / correction / self-reference / pending suffix hash 与 append 一致性 / Candidate 隔离 |
| `tests/contracts/test_cycle_tools.py` | Spec10:110-111 | coordinator/finalizer synthetic fixture + **真实 reducer** 集成用例 |
| `tests/contracts/test_replay_publish_tools.py` | Spec10:32 | replay/publish 工具自测 |

### 1.3 明确**未**创建（属规范边界，不是遗漏）

- L2/L3 workflow 文件（`Historical replay` / `Fresh smoke`）：Spec10:29/41 只允许 5 个 workflow 文件，C.4 的这两个 job 是**受控 Windows 手动运行**且需要真实业务路径/模型密钥。命令已写入两仓 `contract-local.yml` 末尾注释块。
- Coding 的 coordinator / finalizer / ledger workflow：Master §3.2 与 Spec10:39 规定这些只存在于 Wiki。

---

## 2. Spec 12–15「零实现工作」声明

`GOV-FRZ-001` 要求 Spec 12–15 所需的全部工具在 Spec 11 冻结 A **之前**存在且已开发验证。逐条对应如下（"零实现工作"= 下游 Spec 不得新增工具；发现工具缺陷必须 supersede A）：

| 下游 Spec | 下游禁止修改（原文位置） | Spec 10 已预交付 |
|---|---|---|
| 11 | 冻结后禁止修改 Payload / Adapter / 接线 / 测试 / replay / sanitizer / smoke / invariance / publisher / reducer / coordinator / finalizer / config / pyproject / lock / workflow（Spec11:34-45） | packaging、`validate_local.py`（pr/candidate）、baseline comparator（Spec 09 + 本 Spec 反向核验）、`python -m build`、全部 5+6 个工具与 5 个 workflow、pre-freeze tooling inventory（本文件 §1） |
| 12 | 不得新增/修改 runner、sanitizer、assertion、Schema、Adapter、test、config、workflow（Spec12:24） | `replay_history.py` + `replay-v0.1.json` + allowlist 提取 + sanitizer（不做 contract mapping）+ corpus 生成 + evidence status 分类 + 六类扫描 |
| 13 | 不得修改 smoke harness、producer checker、invariance comparator、Adapter、sink、config、tests、业务代码、workflow（Spec13:23） | `validate_local.py --gate smoke`（§11.2 八项）+ `smoke-v0.1.json` + producer/stage coverage checker（ALL_STAGES / ONE_OF）+ run-summary 闭合检查 + `run-manifest` 预登记与实际值载体 |
| 14 | Forbidden：Payload、Adapter、producer、tests、scripts、config、pyproject、lock、workflow 全部不可改（Spec14:45） | `publish_evidence.py` + 发布扫描 + `EvidenceArtifactKind` allowlist + manifest/corpus/traceability writer + `A is ancestor of B` 与 diff allowlist 校验 + ledger 纯追加校验（依赖 `status_ledger.py`） |
| 15 | 不得修改 coordinator、workflow、report generator、finalizer、status reducer、Schema 或任何 Candidate/Evidence 文件（Spec15:24） | `coordinate_cycle.py` + `finalize_cycle.py` + cycle-report 生成（内嵌 coordinator）+ canonical JSON/MD coordination artifact 与 hash 校验 + `current.json` writer + `COORDINATION_PASSED`/`FINALIZATION_COMPLETE` reducer 支持 + 严格 C allowlist |

> 声明：**Spec 12–15 无待实现工具。** 剩余工作全是"在冻结后的固定 A 上执行并产出证据"，不是"写新工具"。

---

## 3. Rule coverage 增量

| 项 | Spec 09 末 | Spec 10 末 |
|---|---|---|
| payload 规范规则 | 68 | 68（不变） |
| conformance 落点 | 56 | 56 |
| 项目层落点（`PROJECT_SCOPED_RULES`） | 6 | **7**（新增 `FND-PKG-003`） |
| 显式 deferral（`DEFERRED_PAYLOAD_RULES`） | 6 | **5**（`FND-PKG-003` 移出） |

`FND-PKG-003`（"Built project distributions MUST expose `agent_core.contracts` and packaged schemas"）此前 defer 给 Spec 10，现在落点在两仓 `tests/contracts/test_packaging.py`（`@contract_rule("FND-PKG-003")`）。等式仍成立：`68 = 56 + 7 + 5`。

**这是 Contract Payload 内容变更**（`conformance/rules.py` 与 `conformance/test_traceability.py` 都在 `agent_core/contracts/**` 内），已按 §12.7 重新生成确定性 bundle 并原子提升 Coding 镜像；两仓 payload 身份重新收敛为 `sha256:64049830…`（40 文件）。

---

## 4. 验证证据（实测输出）

<!-- EVIDENCE -->

全部命令使用权威解释器 `D:\CodexPython312\python.exe`（Python 3.12.10 / pydantic 2.13.4），在各自 worktree 仓库根执行。

### 4.1 两仓通用的 6 条 Development Validation Commands

| # | 命令 | Wiki | Coding |
|---|---|---|---|
| 1 | `python -m agent_core.contracts.tooling.generate_schemas --check` | **exit 0** — `contract_version=0.1.0 schemas=6 schema_set_hash=sha256:d785d52d… rules=68`；descriptor `sha256:5780138f…` | **exit 0**（逐字相同） |
| 2 | `python -m agent_core.contracts.tooling.verify_payload` | **exit 0** — `40 files`，payload `sha256:64049830ba0d1ca2969bb04620ede2d54852e0171f2397d71bc646b2339a4576`，descriptor `5780138f…`，schema_set `d785d52d…` | **exit 0**（同一 payload hash） |
| 3 | `python -m pytest agent_core/contracts/conformance -q` | **224 passed** in 4.70s | **224 passed** in 4.81s |
| 4 | `python -m pytest tests/contracts -q` | **311 passed / 3 skipped** in 150.85s（3 例 skip 为 deepeval-gated scoring） | **195 passed** in 11.71s |
| 5 | `python scripts/contracts/validate_local.py --gate pr` | **exit 0，8/8 步** — 第 6 步的契约相关回归子集由 IN_SCOPE producer 模块匹配到 **14 个文件 / 139 passed** | **exit 0，8/8 步** — 子集 **9 个文件 / 191 passed** |
| 6 | `python -m build` | **exit 0** — `arknights_wiki-0.1.0.tar.gz` + wheel，wheel **116 entries** 且 payload 完整 | **exit 0** — wheel **74 entries** 且 payload 完整 |

`--gate pr` 第 8 步（clean wheel install / import / resource smoke）在临时 target 内安装 wheel、把该 target 前置到 `sys.path`、断言 `agent_core.__file__` 位于该 target 内，并经 `importlib.resources` 读取 descriptor 与 6 个 schema —— 两仓均通过，证明"不依赖 cwd 的干净安装"。

### 4.2 Wiki 额外的 3 条 fixture 命令（Spec 10 F.2）

| # | 命令 | 结果 |
|---|---|---|
| 7 | `status_ledger.py validate --ledger docs/specs/foundation-contract/execution-status-events.jsonl` | **exit 0** — Spec 01–09 `COMPLETE`、Spec 10–18 `NOT_STARTED`、`canonical_events: 35`（本 Spec 追加事件前；追加后 41 且 Spec 10 `COMPLETE`） |
| 8 | `coordinate_cycle.py --plan <fixture>/cycle-plan.json --output <TEMP>`（完全 synthetic，无真实项目 Evidence） | **exit 0** — `coordination_result = PASS`、`cycle_state = READY_FOR_FINALIZATION`；checks [1][2][3][4][5][7][8][9] 全 PASS（[3] 两仓 A→B diff 各 8 / 7 个文件全在 publication allowlist 内；[8] A 树中真实 reducer 归约通过）。**未出现 `COMPLETE`** |
| 9 | `finalize_cycle.py --coordination <TEMP> --release <fixture release> --ledger <fixture ledger> --b-wiki <B> --c-wiki <C> --wiki-repo <fixture wiki>` | **exit 0，8/8 PASS**（C 必须先由 finalization 落盘并提交为独立 commit）—— `current.json` 恰好 4 字段、C artifact 不含自身 SHA、严格 C allowlist、B_wiki ancestor of C_wiki；随后真实 reducer 对最终账本归约到 Spec 15 `COMPLETE`（`canonical_events: 59`） |

### 4.3 独立复核（不依赖子代理自测）

| 复核项 | 结果 |
|---|---|
| 空账本（0 字节）genesis 归约 | **01 `READY` / 02–18 `NOT_STARTED`，0 事件，exit 0**（`GOV-STAT-002`） |
| 7 类非法事件的判定 | `READY→COMPLETE` 跳跃 / duplicate event_id / missing prerequisite / `VALIDATED` 无 `evidence_refs` / correction 缺 references / 非 canonical JSON / pending suffix hash 不符 —— **全部 exit 1 且输出 `SPEC_STATUS_CONFLICT`** |
| 5 个 workflow 的 YAML 与结构 | 全部可解析；单 job、`permissions: contents: read`、有 `timeout-minutes`、每 step 恰有 `uses` xor `run`；L1 gate **无 `secrets`**、无跨仓 `repository`；`contract-coordinate` **仅 `workflow_dispatch`** |
| 两仓 run manifest 与本仓事实自洽 | 5 项断言全通过（IN_SCOPE stage 全覆盖、`expected_calls` 键、`run_id` 形态、replay producer 已登记、币种 = 本仓 `CURRENCY_CONTEXT`：Wiki `CNY` / Coding `USD`）——已固化为常驻测试 `test_shipped_manifests_match_this_repo_registry`（两仓 PASS） |
| 全量回归（`python -m pytest tests/ -q`） | Wiki **854 passed / 10 skipped / 0 failed**（Spec 09 末 637/10/0）；Coding **527 passed / 13 skipped / 0 failed**（Spec 09 末 470/13/8，那 8 条环境诱发失败已消失） |

### 4.4 fail-closed 行为证据（"无法验证 ≠ 通过"）

| 场景 | 结果 |
|---|---|
| `--gate candidate`（Candidate-bound 证据尚不存在） | **exit 1**，明确报"缺少 Evidence Manifest …；L1/L2/L3 证据由 Spec 11–14 在 Candidate A 冻结后产出" |
| `--gate smoke` 未给 `--run-manifest` | **exit 2** + `SPEC_INCOMPLETE / USAGE` |
| `--gate smoke` 缺 `run-summary.json` | 明确报 G-04 承载 artifact 缺失并**失败**（不静默通过） |
| `replay_history.py` 无 `AGENT_CONTRACT_MODE=strict` | **exit 2**，明确 stderr，无 traceback |
| `publish_evidence.py --candidate 0000…0` | **exit 1**，"不在本仓 git 对象库中…拒绝发布，且不会寻找替代 SHA" |
| `finalize_cycle.py` 对**已 finalize 且内容不同**的 release 复跑 | **exit 1**，"不得覆盖既有失败 C（Master §16.7）" |
| `finalize_cycle.py` 的 `--c-wiki` 与 `--b-wiki` 相同（尚无独立 C commit） | **exit 1**，check [5] 报"C artifact 记录了 C_wiki 自身 SHA" |

> 最后一条是**独立复核发现的可用性观察**（不是规范违反）：当 C 与 B 是同一个 commit 时，协调产物中合法的 B 引用会被 check [5] 读成"自身 SHA"。正确流程是 finalization 落盘 → 提交生成独立 C → 用真实 C 复跑（实测 8/8 PASS）。建议 Spec 11 顺手让该检查把这种情况直接报成"C_wiki 必须与 B_wiki 不同"。

### 4.5 真实 L2 管线试跑（未绑定 Candidate，仅验证工具可用）

| 仓 | 结果 |
|---|---|
| Wiki | `replay PASS: records=220 sources=2 status={'REPRODUCTION_RESTRICTED': 220}`（120 条 mapping `OBSERVED`、100 条 `expected semantic correction`） |
| Coding | `replay PASS: records=3 sources=3 status={'LEGACY_DATA_INSUFFICIENT': 3}` |
| 两仓 | `publish_evidence --dry-run` 各准备 **7 个产物**、未写盘 |

这些产物是**未绑定 Candidate 的验证性输出**（`staging/` 为 gitignored 工作区），已在验收后清理，不会与 Spec 12–14 的正式证据混淆。

---

## 5. Provisional 决策与 Spec 11 Stage 0 待校准项

用户裁定：**按最小可行语义实现 + 显式标注 provisional + 入账本 `SPEC_INCOMPLETE` 事件 + 留 Spec 11 Stage 0 校准**。完整决策表见 [执行计划](2026-09-16-foundation-contract-spec10-plan.md) §3。**必须在 A 冻结前校准**的项（按风险排序）：

| 优先级 | 缺口 | provisional 收敛 | 为什么必须在冻结前定 |
|---|---|---|---|
| **P0** | **G-03** pending suffix 无载体 | 双文件载体：`*.pending.jsonl` + `*.pending.json`（`pending_version` / `target_boundary` / `candidate_commit` / `event_count` / `suffix_hash`；envelope 不参与自身 hash） | 它是 Spec 11 解锁 Spec 12/13 的机制依赖；冻结后修改 reducer 必须 supersede A |
| **P0** | **G-01 / G-02** 两个 run manifest 无字段规范 | 键名由规范字段概念直译；`repository_commit: null` = 运行期由 `AGENT_CONTRACT_COMMIT` 解析 | Spec 13/14 禁止修改 config；冻结后 manifest 若不正确将无法修正 |
| P1 | **G-04** `sink_failure_count` 无承载 artifact | `output/contract-validation/staging/<run_id>/run-summary.json`（8 键），缺失即 gate 失败 | L3 运行前必须固定 |
| P1 | **G-06** workflow 触发条件未定义 | 推断集合（`pull_request` + `push(main, feature/**)` + `workflow_dispatch`）；coordinate 仅 dispatch | 影响 CI 治理 |
| P2 | **G-05** regression subset 未定义 | IN_SCOPE producer 源码模块 → 静态匹配项目测试；无匹配则退化全量并注明 | 影响 PR gate 语义 |
| P2 | **G-15 / G-16** expected hash 来源未定义 | 只接受显式传入（`--expect-payload-hash` / dispatch input），不自动推断、不 clone 另一仓 | 影响跨平台门禁可信度 |
| P2 | **G-07** 基线硬编码与现状冲突 | 按规范 `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY` 分支：不失败、标记 review、不静默改基线 | 影响 Spec 11 Candidate Gate 的期望文本 |
| P3 | G-17 fixture 位置 / G-18 退出码 | fixture 全在临时目录；退出码 `0/1/2` | 低 |

### 5.1 实施期新发现的规范缺口（G-22 – G-27）

规范提取阶段（G-01 – G-21）之外，`status_ledger.py` 的实现又暴露出 6 条母 Spec / 子 Spec 未定义的语义。它们同样是**发明物**，其中 **G-22 与 G-26 必须在 A 冻结前固化**，否则 A 内的 reducer 一旦需要修改就是 A2（`GOV-FRZ-002`）。

| 编号 | 缺口 | provisional 收敛 | 冻结前必须处理？ |
|---|---|---|---|
| **G-22** | rule 4/8 的"互斥后继"无操作性定义：14 个 `reason_code` 从未被映射到状态转换；且 `FREEZE_BOUNDARY_REACHED` / `CANDIDATE_FROZEN` / `EVIDENCE_PUBLISHED` / `COORDINATION_PASSED` / `FINALIZATION_COMPLETE` 这 5 个码**完全没有定义对应哪个转换**（但 rule 7 要求它们携带 `candidate_commit`，说明它们确为状态事件） | 实现为 reason_code ↔ 转换耦合表 + 禁止 `from == to` 的 no-op + 首个违规即失败；5 个边界码允许落在 `IN_PROGRESS→VALIDATED` 与 `VALIDATED→COMPLETE` | **是** |
| **G-26** | Spec10:109 冻结的 CLI 只有 `validate --ledger <path>`，但 coordinator 的 check 8 依赖扩展参数 `--spec-dir` / `--index`（并要求脚本本身存在于候选 A 树内） | 扩展参数随 A 一并冻结（该调用形态已实测 exit 0） | **是** |
| G-23 | rule 7 只写"01–11 的 pre-freeze 事件允许 null"，从未写"12–18 必须非空" | 实现为 post-freeze 必须非空（缺 null → 冲突）；若 Spec 12–15 存在合法 null 事件则本 reducer 过严 | 建议 |
| G-24 | A 被 `SUPERSEDED` 后，已 `COMPLETE` 的 spec 如何回到工作态未定义 | 允许 `SUPERSEDED → IN_PROGRESS` + `CANDIDATE_SUPERSEDED`（A2 重启）；否则 `SUPERSEDED` 是死胡同 | 建议 |
| G-25 | I.1 只冻结 ledger 路径，未定义 reducer 如何定位 genesis 来源（子 Spec 目录） | `--spec-dir`（默认 = ledger 所在目录）；恰好因账本与子 Spec 同目录才可用 | 建议 |
| G-27 | I.4 边界表把"01–10 真实状态 + Spec 11 freeze-boundary entry"放在 A 边界，与 rule 7 的"01–11 pre-freeze"只有隐式一致 | 按 rule 7 字面实现（01–11 允许 null） | 建议 |

另有一处**已知限制**（非缺口，但需在冻结前决定是否补强）：`assert_suffix_appended()` 目前只是库 API，CLI 没有"新账本"参数，因此 pending suffix 的**逐字节追加一致性未被门禁强制**——当前由 `coordinate_cycle.py` 的 check 8 自行实现前缀检查。

### 5.2 需要 Spec 12 校准的 L2 语料选择

Coding 仓**没有任何在仓的运行时证据**（无 `output/`，`.gitignore` 全忽略 `/output/`；实扫只有 `benchmark/cases/**/*.json` 与 `config/contracts/*.json`）。`coding/config/contracts/replay-v0.1.json` 因此把**本仓已跟踪的真实 benchmark artifact**登记为 replay source（`benchmark/cases/{feature/schedule-99,bug/schedule-608,test/schedule-602}.json`，`source_class: benchmark`、`producer_id: coding.benchmark.case_cost`、`mapping_stage: normal`、`runtime_adapter_status: IN_SCOPE`、`evidence_role: historical_replay_only`），`reproduction_restriction: REPRODUCTION_RESTRICTED`。

被否决的两个替代方案（记录理由，避免重复讨论）：

- **仓库外受控路径**：provisional schema（G-02）要求 `sources[].path` 为**仓库相对路径且当前存在**，且工具对来源做 allowlist 根校验（`SOURCE_ROOTS=("benchmark/cases",)`）；指向仓库外会让预登记不可验证，而 A 冻结后 config 不可修改 → 路径一旦失效即永久无法运行。
- **`sources: []`**：会让 L2 空转；`replay_history.validate_manifest` 对空 sources 是**显式 exit 2**（不是静默 PASS，该行为已被测试固定）。

实测结果：Coding 的 L2 是 **3/3 记录 = `LEGACY_DATA_INSUFFICIENT`**（`difference_class="legacy insufficiency"`）——即"本仓没有可复现历史语料"的诚实表达，同时把 allowlist extraction → Adapter mapping → 分类整条管线在真实文件上跑通。Wiki 侧实测为 **220 条记录全部 `REPRODUCTION_RESTRICTED`**（源为真实 `output/eval/cost_log.jsonl` 与 `results_scored.jsonl`）。

需要 Spec 12 定的只有一件事：**接受"数据不足但管线已跑通"作为本 Cycle 的 L2 结论**，还是要求补造可复现语料（后者会超出 v0.1 范围，且 Spec 12 禁止修改 config）。这不阻塞 Spec 10。

---

## 6. Deviation 记录

| # | 位置 | 内容 | 理由 |
|---|---|---|---|
| 1 | `agent_core/contracts/conformance/{rules.py,test_traceability.py}`（两仓，经 bundle） | `FND-PKG-003` 从 `DEFERRED_PAYLOAD_RULES` 移出并加入 `PROJECT_SCOPED_RULES` | 该规则本就 defer 给 Spec 10；本 Spec 交付 clean wheel smoke 后它不再是 deferral |
| 2 | `tests/contracts/test_test_baseline.py`（两仓） | 新增 `test_project_scoped_rules_have_real_landings`（AST 静态扫描 `@contract_rule` 落点） | `test_traceability.py` 的 docstring 声称两仓 `test_test_baseline.py` 会反向核验 `PROJECT_SCOPED_RULES` 的真实落点，但 Spec 09 未实现 —— 补上以消除"声明有落点、实际无人落点"的假闭环 |
| 3 | `.gitignore`（两仓） | 新增 `build/`、`dist/` | Spec 10 自身的权威命令 `python -m build` 与 `test_packaging.py` 会在源树产生这两个目录；不忽略会被误提交 |
| 4 | `pyproject.toml`（两仓） | `dev` extra 增加 `build>=1.2` | G-19：`python -m build` 的前置模块在环境中未声明 |
| 5 | `scripts/contracts/*.py`（两仓，全部脚本） | 脚本顶部把仓库根插入 `sys.path` | Spec 10 的权威命令是 `python scripts/contracts/x.py ...`，此时 `sys.path[0]` 是脚本目录而非仓库根；且两仓都提供顶层 `agent_core`，同一解释器无法同时可编辑安装两者，不能依赖 editable install |

---

## 7. 残余验证缺口（如实声明，不得冒充通过）

1. **Linux 跨平台 payload hash 未在本环境复跑**：Docker 守护进程未运行；WSL Ubuntu 的 Python 是 3.14.4 且无 pip/venv（与规范要求的 py3.12 + pydantic 2.13.4 不符）。Spec 03 已为**当时**的 payload（`df479f0c`）证明过 Windows≡Linux；本次 payload 变更只涉及两个纯 Python 源文件（内容在两平台经同一 git blob 取出一致），且 hash 输入只含文件内容（无 mtime / 绝对路径）。真正的复核由本 Spec 新建的 `contract-payload-linux.yml` 在 CI 完成，也是 Spec 11 L1 的一部分。
2. **5 个 workflow 未在真实 GitHub runner 上执行过**：本环境无法运行 Actions。已完成的是 YAML 解析、结构性断言（单 job、`permissions: contents: read`、`timeout-minutes`、step 的 `uses` xor `run`、无 `secrets`、无跨仓 `repository`）与命令一致性核对。action 未 pin 到 commit SHA（仓库无既有 pin 约定，亦未被授权新建）。
3. **`--gate candidate` 与 `--gate smoke` 当前预期失败**：Candidate-bound 的 Evidence Manifest（Spec 12–14）与 L3 的 `run-summary.json`（Spec 13）尚不存在。这是**预期行为**，不是缺陷；两者的失败路径已被验证为"干净失败"（明确 stderr + 退出码 1/2，无 traceback）。
4. **Wiki `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY`**：三条登记 known failure 现已全部 PASS（G-07）。本 Spec 不刷新 baseline，该事实需 Spec 11 Stage 0 显式处理。

---

## 8. 回滚与交接

- **回滚**：本 Spec 全部改动在 Candidate A 冻结之前，可分别回退 packaging / scripts / configs / workflows / tests。涉及 shared payload 的部分（deviation #1）必须双仓重新 bundle 后再 apply，回滚亦同。
- **账本**：append-only，永不回退；状态修正只能追加 `STATUS_CORRECTION` 语义的新事件并引用原错误事件。
- **交接给 Spec 11（Candidate A Freeze / L1 / 全量回归）**：
  1. Spec 11 Stage 0 必须先完成本文件 §5 的 **P0 两项校准**（pending suffix 载体、两个 run manifest 的键名与 `repository_commit` 约定），再冻结 A。
  2. Candidate A 的起点必须是**两个 worktree 分支的 HEAD**（Wiki `feature/foundation-contract-spec10`、Coding 同名），而不是两仓 `main` —— 两仓 `main` 都没有任何 Foundation 产物（Master Appendix G:2700 的"起点漂移"风险）。
  3. A 冻结后 `docs/contracts/releases/0.1.0/` 与 Lemma 账本事件由 Spec 12–14 产出；`--gate candidate` 到那时才应转绿。
