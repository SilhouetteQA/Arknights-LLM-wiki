# Spec 10（Packaging and Local Contract CI）规范性提取报告

> 提取者：规范提取子代理。只读文档 + 只读代码探针，未修改任何代码或规范。
> 规范来源：`docs/specs/2026-09-10-dual-agent-foundation-contract-master-spec.md`（下称 **Master**，行号以该文件为准）、
> `docs/specs/foundation-contract/10..15-*.md`（下称 **Spec N**）、`00-execution-index.md`（下称 **Index**）。
> 标注约定：**[N]** = 文档写死的规范要求（附行号）；**（推断）** = 我的推断，非文档明文；**（未核验）** = 超出本子代理工作目录、无法验证。
> 探针环境：`D:\AI project\_worktrees\foundation-contract\wiki`（分支 `feature/foundation-contract`，HEAD `102de4c`）；
> Coding 侧只读探针：`D:\AI project\_worktrees\foundation-contract\coding`（分支 `feature/foundation-contract-spec10`，HEAD `1798859`）。

---

## 0. 已核验现状（事实快照）

| 事实 | 证据 |
|---|---|
| `scripts/contracts/` 目录在两仓都**不存在**（6 个脚本 0/6 实现） | `Test-Path` = False（wiki / coding） |
| `config/contracts/smoke-v0.1.json`、`replay-v0.1.json` 两仓都**不存在** | 目录列举（wiki 仅 producer-registry / known-test-baseline；coding 同） |
| `.github/workflows` 两仓都**不存在**（workflow 0/5） | `Test-Path` = False |
| `tests/contracts/test_packaging.py` 两仓都**不存在**；其余 5 个测试文件已在 Spec 09 落地 | 目录列举 |
| Wiki `pyproject.toml`：无 `[build-system]`、无 `pydantic==2.13.4`、discovery 仅 `include = ["arknights_wiki*"]`、无 package-data | wiki `pyproject.toml:1-27` |
| Coding `pyproject.toml`：**已**有 `[build-system]`(line1)、`pydantic==2.13.4`(15)、`include=[agent*,adapters*,agent_core*,benchmark*,tools*]`(30)、`[tool.setuptools.package-data]` 含 `contract.md`,`payload-descriptor.json`,`schemas/*.json`(34-40) | coding `pyproject.toml` |
| 两仓各 40 个 payload 文件；Wiki payload hash `sha256:df479f0ca413936d147bcceb8c50a0e88424520826bbde8f6340c35f97254623` | `verify_payload` 实跑输出 |
| 两仓 descriptor 的 canonical JSON hash 相同（`5780138f…`），但**磁盘原始字节不同**（Wiki `0A79D328…` ≠ Coding `5780138F…`）→ 只是 JSON 落盘格式差异，payload hash 走 canonical JSON，不影响身份 | 文件 SHA256 对比 |
| Ledger `execution-status-events.jsonl` 现有 35 行，Spec 09 `COMPLETE` 已入库；**Spec 10 effective status = NOT_STARTED** | `Get-Content` 尾部 6 行 |
| Ledger 事件是**按键名排序的 canonical JSON**（`candidate_commit,event_id,evidence_refs,from_status,reason,reason_code,references,spec_id,timestamp,to_status`） | 尾行实测 |
| `.gitignore` 已含 `output/contract-validation/staging/`、`raw/`、`private/`（Spec 01 已做）；但**缺前导斜杠**，与 `§11.1:1194` 要求的 `/output/contract-validation/staging/` 非逐字一致 | wiki `.gitignore:74-79` |
| 环境**未安装** `build` 模块：`import build` → `ModuleNotFoundError` | 实跑 |

> **⚠ 并发写入警告（提取期间实测）**：本 worktree 在本次提取过程中被**另一执行者**同时修改（mtime 2026-09-16 13:31–13:33）。
> `git status` 从最初的仅 `M output/devlog.md` 变为：
> `M agent_core/contracts/conformance/rules.py`、`M agent_core/contracts/conformance/test_traceability.py`、`M pyproject.toml`、`?? tests/contracts/test_packaging.py`。
> 具体变化：Wiki `pyproject.toml` 已补 `[build-system]`/`pydantic==2.13.4`/`include=[arknights_wiki*, agent_core*]`/`[tool.setuptools.package-data]`；
> `DEFERRED_PAYLOAD_RULES` 中移除了 `FND-PKG-003`（改为项目层落点 `tests/contracts/test_packaging.py` + `test_traceability.PROJECT_SCOPED_RULES`）。
> 因此下表"Wiki pyproject 无 build-system/pydantic pin"与"`test_packaging.py` 不存在"两行**在我核验时成立、之后已被改动**；
> F 节的命令 5/6/9 现状也可能已被推进。以最新工作区为准，本报告其余规范提取部分不受影响。

---

## A. 9 个待实现交付物的精确契约

### A.0 可直接复用的已实现原语（不得修改）

**[N]** 共享层只能来自 Spec 03/04/09 的既有实现；Spec 10 若发现缺陷必须回 Spec 03 修正并重验依赖（Spec10:47）。

- `agent_core/contracts/tooling/canonical_json.py`：`canonical_json_dumps/bytes`、`sha256_hex()`（返回 `sha256:<hex>`）、`read_text()`（剥 BOM、非 UTF-8 显式失败）、`normalize_text()`（CRLF/CR→LF）、`iter_payload_files(root)`（排除 `__pycache__`/`.pyc`/`.tmp`/`.lock`…）、`file_canonical_content()`（JSON 重排为 canonical，其余只规范化换行）、`canonical_file_bundle_digest(root) -> (payload_hash, per_file)`、`schema_content_hash()`、`schema_set_hash()`。
- `tooling/generate_schemas.py`：`find_repo_root()`、`render_schemas()`、`build_descriptor()`、`parse_declared_rules()`、`check(root)->list[Drift]`、`write(root)`；CLI `--check`(默认)/`--write`；退出 0/1，无 `agent_core` 时 2。
- `tooling/verify_payload.py`：`verify_tree(root, expected_payload_hash=None) -> VerifyReport{ok,diverged,payload_hash,descriptor_hash,schema_set_hash,file_count,per_file_hashes,errors}`，覆盖 FND-PKG-001/002、FND-VER-002/003/004/006 + Schema 漂移 + DIVERGED；CLI `--repo-root/--expect-payload-hash/--json`，退出 0/1。
- `tooling/bundle.py`：`create_bundle` / `inspect_bundle` / `extract_and_verify` / `apply_bundle`（确定性 ZIP_STORED、固定时间戳、原子替换 + 回滚 + 落地复算），CLI `create|inspect|apply`，失败退出 1。
- `conformance/rules.py`：`RULE_REGISTRY`（79 条 statement：68 payload + FND-REG-001..005 + FND-REL-001..006 + EVD-DATA-001）、`DEFERRED_PAYLOAD_RULES = (FND-PKG-003, EVD-PUB-002/003/004/006/007)`、`contract_rule`/`rules_of`/`collect_rule_usages`/`unimplemented_rules`。
- `models/evidence.py`：`EvidenceRecord`（14 字段 + 全部不变量）、`FoundationObservation`（三者至少一项）、`is_safe_run_id`/`is_canonical_event_id`/`is_path_safe_identifier`/`normalize_event_id`、`EVIDENCE_FACT_NAMESPACES={wiki,coding,provider,adapter}`、64 键 / 64 KiB 上限。
- `enums/evidence.py`：`EvidenceRepository{wiki,coding}`、`ValidationStatus{PASS,FAIL}`、`EvidenceArtifactKind`（6 个文件名）、`EvidenceStatus`（§11.5 的 10 个值）、3 个 `evidence.*` 基础设施码（闭集）。
- `protocols/evidence_sink.py`：`EvidenceSink.emit`、`SinkFailure(code,message,event_id)`（只接受上述 3 码）。
- Wiki 项目侧：`FileEvidenceSink`（`AGENT_CONTRACT_EVIDENCE_DIR` 覆盖，默认 `output/contract-validation/staging`；`run_events_dir(run_id)=<root>/<run_id>/events`；`.json.tmp`→`os.replace`→`.json`；`sink_failure_count`；`iter_published_events`、`has_residual_temp_files`）、`runtime.py`（`WikiFoundationRuntime`、`STAGE_PRODUCER` 6 stage、`AGENT_CONTRACT_RUN_ID`、`AGENT_CONTRACT_COMMIT`、`resolve_payload_hash()`、`get/set/reset_foundation_runtime`、`ContractConfigurationError`/`ContractValidationError`）。
- `config/contracts/known-test-baseline.json` 实际字段：`baseline_commit, canonical_command, captured_at, repository, master_snapshot_commit, fingerprint_algorithm, fingerprint_anchor_commit, baseline_refresh_note, counts{pass,skip,fail,total}, existing_pass_nodeids[542], existing_skip_nodeids[7], known_failures[3]{nodeid,exception_type,symbolic_failure_locus,normalized_error_signature,scope,fingerprint_sha256,fingerprint_anchor_commit}, tool_versions{python,pydantic,pytest}`。
  - **注意**：Spec01:70 只写 `known_failures[nodeid, exception_type, normalized_signature, fingerprint, scope]`（简写），与文件实际键名不同 → 以实现文件 + Appendix E.1 六字段为准（见 G-11）。

### A.1 `scripts/contracts/validate_local.py`（两仓）

- **[N] 路径**：Wiki `scripts/contracts/validate_local.py`（Spec10:27）；Coding `scripts/contracts/validate_local.py`（Spec10:39）。
- **[N] CLI**：`--gate pr`（Spec10:102、Master C.1:2369）、`--gate candidate`（Master C.1:2371、§15.1:1576）、`--gate smoke --run-manifest config/contracts/smoke-v0.1.json`（Master C.1:2384、Spec13:63）。smoke 额外依赖环境变量 `AGENT_CONTRACT_MODE=observe` 与显式 `AGENT_CONTRACT_RUN_ID`（Master C.1:2382-2384；EVD-RUN-001）。
- **[N] `--gate pr` 内容**（Master §15.1:1552-1563 的保序组合；Spec10:16/89 复述）：
  1. payload allowlist（FND-PKG-001/002）；
  2. Schema regeneration diff（`generate_schemas --check`）；
  3. descriptor / payload hash verification（`verify_payload`）；
  4. shared conformance tests（`pytest agent_core/contracts/conformance`）；
  5. project adapter / wiring / invariance tests（`pytest tests/contracts`）；
  6. **contract-related regression subset**（文档未定义子集 → G-05）；
  7. evidence publication safety scan（§11.4:1244-1251：secret pattern、forbidden field/key（`prompt`/`response_body`/`reasoning`/`traceback`/`authorization` 等）、Windows/Linux 绝对路径、单 record/单 artifact 容量、UTF-8/BOM/换行、JSON Schema）；
  8. clean wheel install / import / resource smoke（Master C.3:2414-2425）。
- **[N] 禁止**：PR gate 不得 clone 或读取另一仓（Master §15.1:1550；Spec10:51）；不得调用真实模型；不得转储环境变量/凭据/私有 endpoint（Spec10:53）。
- **[N] `--gate candidate`** = pr 全部 + canonical full regression（本仓 `python -m pytest tests/`，Master §15.1:1579）+ nodeid/fingerprint gate（Master §15.1:1579、§14.2:1522-1532）+ 本仓 L1/L2/L3 evidence verification（Master §15.1:1565）。
  - Wiki 期望 `PASS_WITH_KNOWN_BASELINE_FAILURES`；Coding 期望 `PASS`；新增失败零容忍（§14.2:1532）。
  - 判定表（Appendix E.2:2597-2607）：known nodeid+同指纹→`ALLOWED_BASELINE_FAILURE`；known nodeid+指纹变化→FAIL；新失败 nodeid→FAIL；baseline PASS→FAIL/SKIP→FAIL；known failure→PASS→`KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY`（**不使 Cycle 失败**，但需 review，且不得同 Cycle 静默删基线）。
  - 指纹算法（Appendix E.1:2553-2564）：输入仅 `pytest nodeid / exception type / symbolic failure locus / normalized semantic signature / scope / baseline commit`，canonical JSON 后 SHA256；**不得直接 hash traceback**。已验证的三条 anchor 指纹见 Appendix E.2:2582-2586。
- **[N] `--gate smoke`**（Master §11.2:1197-1210、§13.3:1457-1487、Spec13:25-54）必须验证：
  1. 显式 run_id 与 run manifest 一致；
  2. observed `(producer_id, mapping_stage)` 满足预登记 required set；
  3. 所有 event 的 repository / repository_commit / contract version / payload hash 一致；
  4. 所有 event `contract_mode == observe`；
  5. `event_id` 无重复；
  6. 无 `.tmp` 残留（`has_residual_temp_files`）；
  7. `sink_failure_count == 0`；
  8. 无未映射错误、无被拒绝的 EvidenceRecord。
  - "一条成功事件或目录非空不构成有效 Smoke 证据"（§11.2:1210）。
  - Registry 覆盖语义：`ALL_STAGES` 逐 stage 覆盖；`ONE_OF` 按预登记策略（Spec13:51；Appendix B:2343）。
  - 业务完成 ≠ Evidence 闭合：业务结果保留，L3 Gate 失败（§13.3:1487、Spec13:49）。
  - 运行前 `run-manifest.json` 预登记字段（§13.3:1470-1485）：`model, provider, case_ids, required_producer_stages, expected_calls, max_calls, estimated_cost_cap, network_requirement, side_effect_policy, contract_version, payload_hash, candidate_commit`；Spec13:29-40 追加 `timeout/duration cap`、`Evidence directory + explicit run_id`。
  - 运行后记录：actual calls/tokens、known/unknown cost components、duration、producer coverage、sink failures（§13.3:1487）。
  - 不变性比较（§14.1:1505-1520）：固定 input + 固定 model response 下 off/observe 的 Output / Decision / Side Effects / Legacy Telemetry 必须精确相等；staging artifact、contract log、adapter metric **不在**比较对象内。
  - Fixture 只能证明合法性，**不能冒充 L2/L3 观察**（§13.4:1501）。
- **[N] 必须覆盖的规则 ID**：FND-PKG-001/002/003/004、FND-VER-002/003/004/006、FND-REG-001/002/003/004/005、EVD-DATA-001、EVD-RUN-001/002、EVD-SINK-001/002/003/004、EVD-PUB-001/002/003、FND-MODE-001..004。
- **[N] 输出产物**：staging events（`output/contract-validation/staging/<run_id>/events/<event_id>.json`）+ semantic coverage matrix（§13.4:1491-1501 表头为 `Semantic Case / Rule ID / Contract Test / Historical / Fresh / Count / Status / Notes`）+ validation-report（B 阶段才发布，D.2）。
- **[N] 退出码语义未在文档任何位置定义**（全文检索 `exit code|退出码|返回码` 无命中）。**（推断）**：0 = gate 通过；1 = gate 失败（含 SPEC_STATUS_CONFLICT 以外的语义失败）；2 = 用法/配置缺失（与既有 `generate_schemas` 返回 2 的约定一致）。禁止把"脚本不存在"当作通过（Master Appendix C:2358）。

### A.2 `scripts/contracts/replay_history.py`（两仓）

- **[N] 路径**：两仓 `scripts/contracts/replay_history.py`（Spec10:27/39）。
- **[N] CLI**：`python scripts/contracts/replay_history.py --run-manifest config/contracts/replay-v0.1.json`；前置 `AGENT_CONTRACT_MODE=strict` + 显式 `AGENT_CONTRACT_RUN_ID`（Master C.1:2378-2380、C.2:2405-2407、Spec12:57-69）。**未定义其它参数**。
- **[N] 行为**（Spec10:70、Master §13.2:1442-1455、Spec12:35-51）：
  - 只读取 **allowlisted historical sources**（真实 cost log / trace / benchmark / 其它登记 artifact），strict mapping；
  - sanitizer **不得**执行 contract mapping（Spec12:46）；
  - 每记录必须保存：`observed legacy facts`、`expected Foundation mapping`、`actual Foundation mapping`、`source domain`、`runtime adapter status`、`evidence role`（§13.2:1446-1453）；
  - 逐 Rule/Semantic case 统计 `OBSERVED / NOT_OBSERVED / LEGACY_DATA_INSUFFICIENT / REPRODUCTION_RESTRICTED` 等真实状态（Spec12:48）；
  - 生成 sanitized corpus，每条**只含** `record_id, source_class, minimal legacy usage/cost facts, expected mapping, actual mapping, sanitized record hash`（§11.3:1240、Spec12:49）；公开 artifact **不含 raw prompt hash**；如需私下关联可用带私钥 HMAC，但 key 与 raw digest 不入 Git（§11.3:1240）；
  - 执行 secret/path/forbidden-field/size/Schema 扫描（Spec12:50）；
  - 原始业务证据留在受控位置，不得复制进 contract staging 或 Git（Spec12:51）；
  - `DEFERRED` 来源可用，但必须标 `runtime_adapter_status=DEFERRED` 与 `evidence_role=historical_replay_only`（Appendix B:2354）；
  - 差异必须分类为：Adapter defect / Contract feedback / legacy insufficiency / expected semantic correction（Spec12:84）。
- **[N] 必须覆盖的规则 ID**：EVD-PUB-001、EVD-PUB-004、EVD-PUB-005、EVD-PUB-007、EVD-RUN-001/002、EVD-DATA-001、FND-MAP-001/002。
- **[N] 输出**：Candidate-bound L2 run 结果、sanitized corpus candidate、observed/expected/actual mapping matrix、reproduction restriction 与 legacy insufficiency 说明、可供 Spec 14 发布的 Evidence IDs/hashes（Spec12:73-77）。
- **[N] 禁止**：本步骤不得新增/修改任何 runner、sanitizer、assertion、Schema、Adapter、test、config、workflow；工具不足即 A superseded（Spec12:24、Spec10:56）。

### A.3 `scripts/contracts/publish_evidence.py`（两仓）

- **[N] 路径**：两仓 `scripts/contracts/publish_evidence.py`（Spec10:27/39；Coding 无 coordinator/finalizer）。
- **[N] CLI（文档唯一写死者）**：`python scripts/contracts/publish_evidence.py --candidate <A_SHA> --release-version 0.1.0`（Spec14:78）。Spec14:81 明确"具体 CLI 参数以 A 中的已冻结接口为准，不得在本步骤修改"——即接口在 Spec 10 冻结，Spec 14 只能用。
- **[N] 行为**：
  - allowlist extraction：`controlled business/historical source → minimal staging facts → construct new publishable Evidence DTO → validate and scan → hash → release snapshot`（§11.3:1214-1223）；**禁止** "序列化原始对象后删敏感字段"的 denylist 做法（§11.3:1225、Spec10:54）。
  - 扫描项同 A.1 第 7 条（§11.4）。
  - run manifest 只记录净化命令；secret / 临时目录 / 私人路径替换为 `<SECRET>` / `<WORKSPACE>` / `<REDACTED>`（§11.4:1253）。
  - 生成 D.2 的 artifact 集；`contract-manifest.json` 内容 Coding 与 Wiki 相同，`canonical_payload_commit` 指向 A_wiki（§12.5:1369-1378、Spec14:55）；Evidence Manifest 的 `verified_repository_commit` 分别指向各自 A（Spec14:56）。
  - Evidence Manifest **不得**包含 `evidence_manifest_hash` 或 `evidence_commit`（§16.3:1653-1660、D.2:2503）；其 canonical hash 由 coordinator 计算（§16.3:1660）。
  - Wiki B 只允许对 ledger 做**严格字节追加**（§16.3:1671、Spec14:59）；Coding B 不保存 ledger（Spec14:41）。
  - 必须验证 `A is ancestor of B` 且 `diff(A,B) ⊆ evidence publication allowlist`（§16.3:1662-1669、Spec14:61）；A→B 禁止改 Payload/Adapter/业务代码/测试/`pyproject.toml`/lock（§16.3:1669）。
  - B 不得包含引用自身 SHA 的 cycle plan / manifest 字段（§17 Stage 9:1853）。
- **[N] 必须覆盖的规则 ID**：EVD-PUB-001..007、FND-VER-004/005、FND-REL-001/002、GOV-STAT-004。
- **[N] 输出**：`B_wiki`/`B_coding` SHA、两份独立 Evidence Manifest 及待协调 canonical hash、同一 Contract Manifest/Payload identity、Wiki canonical 状态事件追加；**不得**产出 cycle plan / cycle report / current pointer（Spec14:85-89）。

### A.4 `scripts/contracts/status_ledger.py`（仅 Wiki）

- **[N] 路径**：Wiki only（Spec10:27；Coding 无，Spec10:39 / Master §3.2:492-495）。
- **[N] CLI**：`python scripts/contracts/status_ledger.py validate --ledger docs/specs/foundation-contract/execution-status-events.jsonl`（Spec10:109）。
- **[N] 必须实现**（Spec10:11 即 78 行、Spec10:78-79）：Appendix I 的 Event Schema、空 ledger genesis、DAG/authority/evidence/transition reducer、append-only diff validation、canonical prefix + controlled pending suffix 归约（细则见 **C 节**）。
- **[N] 禁止**：忽略非法行、重排 events、采用 last-line-wins（Spec10:55）。
- **[N] 必须被测试覆盖的用例**（Spec10:79）：duplicate ID、missing prerequisite、`READY→COMPLETE` 跳跃、mutually exclusive successors、correction、self-reference、pending suffix hash/append 一致性、Candidate 隔离。
- **[N] 非法事件返回 `SPEC_STATUS_CONFLICT`**（Spec10:129、Index:106、Master I.3:2820）。
- **（推断）**退出码：0 = 合法；非 0 + 输出 `SPEC_STATUS_CONFLICT` = 非法（文档未给数字）。

### A.5 `scripts/contracts/coordinate_cycle.py`（仅 Wiki）

- **[N] 路径/CLI**：`python scripts/contracts/coordinate_cycle.py --plan <CYCLE_PLAN> --output <COORDINATION_OUTPUT>`（Master C.5:2443、Spec15:69、Spec10:110）。
- **[N] 输入 plan 闭合字段**（§16.4:1675-1686）：`cycle_id, target_contract_version, expected_contract_payload_hash, wiki_candidate_commit, coding_candidate_commit, wiki_evidence_commit, coding_evidence_commit, created_at`；plan 不属于任一 A/B git tree，**输入闭合后不得自动寻找替代 SHA**（§16.4:1688、Spec15:39）。
- **[N] 校验清单**（Spec15:42-51）：① checkout 两个固定 A 与 B，Coding token 只读且不得进入 artifact/log；② 每仓 `A ancestor of B` 与 A→B diff allowlist；③ 重算两仓 version 与 Payload Hash（同版本不同 hash → 只能 `DIVERGED`）；④ 两 Evidence Manifest 分别引用对应 A 与同一 Payload，且 Evidence commit 为 B；⑤ 计算两项目独立 Evidence Manifest Hash（不同是正常事实）；⑥ 验证 L1/L2/L3、full regression、producer coverage、reproducibility、publication scan 结果；⑦ Wiki Ledger 在 B 中纯追加且可由 A 中 reducer 合法归约；⑧ 记录 coordinator repository、A 中 coordinator commit/tool version、workflow version、run ID。
- **[N] 输出字段**（§16.5:1694-1711）：`cycle_id, contract_version, contract_payload_hash, wiki_candidate_commit, coding_candidate_commit, wiki_evidence_commit, coding_evidence_commit, wiki_evidence_manifest_hash, coding_evidence_manifest_hash, coordination_result, cycle_state, coordinator_repository, coordinator_commit, coordination_tool_version, coordination_run_id, completed_at`；`coordination_result=PASS`、`cycle_state=READY_FOR_FINALIZATION`。
- **[N] 状态闭集**：只能 `PASS/READY_FOR_FINALIZATION`、`FAILED`、`DIVERGED`（Spec15:51；`DIVERGED`/`FAILED` 语义见 Master §15.3:1591-1594）；**不得提前写 `Cycle COMPLETE`**（§16.5:1713、Spec10:84）。
- **[N] 禁止**：调用真实模型、产生新 L3 Evidence、推断最新成功 commit、checkout 移动 main（Master §15.3:1587-1596、Spec10:52、Spec15:97）。
- **[N] 规则 ID**：FND-REL-001..006、FND-VER-005、FND-REG-001..004、GOV-STAT-004。
- **[N] 产物**：canonical JSON + Markdown coordination artifact（Spec15:51），作为 C 的输入。

### A.6 `scripts/contracts/finalize_cycle.py`（仅 Wiki）

- **[N] 路径/CLI**：`python scripts/contracts/finalize_cycle.py --coordination <COORDINATION_OUTPUT> --release docs/contracts/releases/0.1.0`（Master C.5:2444、Spec15:70）。
- **[N] 行为**（Spec10:85、Spec15:55-64、§16.6:1715-1749）：校验 coordination artifact hash → 复制**hash 精确一致**的 `cycle-report.json/.md` → 生成最小 `current.json` → 只追加 `COORDINATION_PASSED`、`FINALIZATION_COMPLETE` 等 reducer 可识别事件 → **不记录 C 自身 SHA** → 形成 `C_wiki` 并验证 `B_wiki ancestor of C_wiki` 且 diff ⊆ 严格 finalization allowlist → C 合并 canonical branch 后重新验证。
- **[N] C 只允许改**（§16.6:1717-1725）：`docs/contracts/releases/<version>/cycle-report.json`、`/cycle-report.md`、`docs/contracts/current.json`、必要的 append-only coordination index、`docs/specs/foundation-contract/execution-status-events.jsonl`（仅追加）。
- **[N] `current.json` 只允许 4 字段**：`contract_version, contract_payload_hash, cycle_id, release_path`（§16.6:1738-1745）；它只是指针，不是第三份 manifest。
- **[N] 最终验证必须针对 canonical branch 上的 C tree，而非未提交工作区**（Spec15:73）。
- **[N] 规则 ID**：FND-REL-003/004/005/006、GOV-STAT-004。
- **（推断）**与 A.5 的边界：coordinator 只产 artifact，finalizer 只准备 C allowlist 文件（Spec10:85、Master C.5:2447）。

### A.7 `config/contracts/smoke-v0.1.json` 与 `replay-v0.1.json`（两仓）

- **[N] 路径**：两仓 `config/contracts/smoke-v0.1.json`、`config/contracts/replay-v0.1.json`（Spec10:28/40；Master §3.2:454-455/489-490）。
- **[N] 语义**：预登记 L2/L3 run scope（Appendix F:2657）；不得含凭据/私有路径（Appendix F.2:2657、F.3:2677）；不得事后删除 required stage 或提高成本上限（Spec13:42）。
- **[N] smoke 文件的字段来源** = `§13.3:1472-1485` 的 run-manifest 预登记字段 + Spec13:29-40 的追加项（总数 ≥14 个概念字段）。**文档未给出这些字段在 JSON 中的确切键名**（Master 用 YAML 伪字段列表）→ **SPEC_INCOMPLETE**（G-01）。
- **[N] replay 文件**：**文档完全没有定义字段结构**，只要求它能被 `replay_history.py --run-manifest` 消费，并支撑"allowlisted historical sources + expected mapping 预登记"（Spec12:35-40、Master §13.2）。→ **SPEC_INCOMPLETE**（G-02）。不得自行发明字段名。
- **（推断）**两文件必须是合法 JSON 且被 manifest validation 覆盖（Appendix F:2657 "Verification: manifest validation"）。

### A.8 `tests/contracts/test_packaging.py`（两仓）

- **[N] 路径**：Wiki/Coding 各一份 `tests/contracts/test_packaging.py`（Spec10:30/42；Master §3.2:471/503）。
- **[N] 应断言**（Spec10:62-65、Master §3.3:508-523、FND-PKG-003、C.3:2414-2425、Spec10:126/137）：
  1. `pyproject.toml` 固定 `pydantic==2.13.4`（Master §1.2:200、§3.3:513/519）；
  2. 存在明确 `[build-system]`（Wiki 需新增；Coding 已有，line1）；
  3. package discovery 覆盖 `agent_core*`（Wiki 还要保留 `arknights_wiki*`；Coding 还需当前 packages 与 `adapters*`，不得依赖 cwd import 巧合）；
  4. `contract.md`、`payload-descriptor.json`、`schemas/*.json` 注册为 package data，并可通过 `importlib.resources.files(...)` 读取；
  5. wheel 构建产物包含 `agent_core*`；在**新建临时 venv** 中安装后能 `import` 核心类型（`from agent_core.contracts.models.usage import Usage`）并读取 Schema package data；验收标准是"wheel 独立安装后可用"，**不是**"当前 cwd 能 import"（C.3:2425）；
  6. 该新增测试属 FND-REG-004 范畴：100% PASS 才可通过 Candidate Gate。
- **[N] 配套**：`tests/contracts/test_test_baseline.py` 两仓都必须存在（Spec10:31/43；Wiki 已有，Coding 已有）。

---

## B. 3+2 个 CI workflow 的精确要求

**[N] 文件清单**
- Wiki：`.github/workflows/contract-local.yml`、`contract-payload-linux.yml`、`contract-coordinate.yml`（Spec10:29；Appendix F.2:2660-2662）。
- Coding：`.github/workflows/contract-local.yml`、`contract-payload-linux.yml`（Spec10:41；Appendix F.3:2680-2681）。

**[N] job 划分与 OS 职责**（Master Appendix C.4:2429-2436 + §15.1-15.3）
| Job | OS | 依赖/密钥 | 职责 |
|---|---|---|---|
| Local PR Contract Gate | Windows | 本仓完整/测试依赖；**无密钥** | Schema、Payload、L1、Adapter、invariance、package smoke |
| Canonical full regression | Windows | 本仓完整依赖；无或沿用项目测试约束 | Wiki 542/7/3 指纹；Coding 381/13/0（**与实际漂移见 G-07**） |
| Canonical hash | Linux | 最小契约依赖；无 | 同一工具重算 Schema/Payload Hash |
| Historical replay | 受控 Windows | 本仓回放依赖；不应需要模型密钥 | L2 |
| Fresh smoke | 受控 Windows | 真实路径依赖；最小必要密钥 | L3，只读/本地可逆 |
| Coordination | Windows 或 Linux | Git + 契约验证工具；**Coding 只读 checkout token** | 固定 A/B 验证，不调用模型 |

- **[N] Windows**：运行完整 Contract CI（§15.2:1583）。
- **[N] Linux**：只安装最小 contract dependencies，用同一 `canonicalization_version=1` 与**同一共享实现**重新生成 Schema、计算 Payload Hash 并比较 expected hash；不宣称两业务系统跨平台兼容（§15.2:1583）。
- **[N] PR Gate 内容**（Spec10:16/89）：Schema/Payload/L1/project tests/publication safety/package smoke，独立运行，**不 clone 另一仓**。
- **[N] Coordination workflow**（Spec10:18/91）：使用**最小只读 Coding checkout token**，**不产生 L3**；只读闭合 `cycle-plan.json`；不得推断最新成功 commit、不得 checkout 移动 main（§15.3:1587）；token 禁止进入日志、环境 dump、extension 或 artifact（§15.3:1587、Spec10:53）。
- **[N] 跨平台一致性硬门禁**：Windows/Linux 同 payload hash；不同即失败（Spec10:131、Stop Conditions:138）。
- **[N] 禁止事项汇总**：① 普通 PR Local CI clone 另一仓（Spec10:51）；② Coordination CI 调用真实模型或寻找 latest successful commit（Spec10:52）；③ workflow 转储环境变量/凭据/private endpoint（Spec10:53）；④ Linux job 运行完整业务仓（F.2:2661）。
- **（推断，无文档明文）**触发条件：`contract-local.yml` = `pull_request` + `push`；candidate 档 = `workflow_dispatch`（或带固定 SHA 输入的 dispatch）；`contract-payload-linux.yml` = 与 local 相同触发；`contract-coordinate.yml` = 仅 `workflow_dispatch` 且输入闭合 plan。权限建议 `permissions: contents: read`（Coding checkout token 的载体形式文档未指定）。
- **（推断）**"最小权限"实现方式文档只给约束不给机制（deploy key / PAT / App token 均未写死）。
- **（歧义）**C.4 列了 6 个 job，但 Spec10 只允许 5 个 workflow 文件，且 L2/L3 的触发方式未定义 → 见 G-06。

---

## C. Appendix I 状态治理（完整规范）

### C.1 静态 genesis（I.1:2747-2755）
- **[N] 路径**：`docs/specs/foundation-contract/execution-status-events.jsonl`。
- **[N] 合法初始文件 = 0 bytes / 0 records**；Reducer 从静态子 Spec 读取 genesis：Spec 01 = `READY`，Spec 02–18 = `NOT_STARTED`。
- **[N] Initial Status 不重复写入 Ledger**；第一条事件必须来自真实工程动作（Index:100）。

### C.2 Event Schema 完整字段表（I.2:2757-2776）
每个非空 JSONL 行必须是**独立 canonical JSON object**，字段：

| 字段 | 类型/取值 | 约束 |
|---|---|---|
| `event_id` | `<UUID-or-ULID>` | 全局唯一；canonical UUID 或 26 位 Crockford ULID（I.3:2814） |
| `spec_id` | `"09"` 形式的字符串 | 01–18 |
| `from_status` | 7 状态之一 | 必须等于前一归约状态（I.3:2815） |
| `to_status` | 7 状态之一 | 转换必须合法（I.3:2816） |
| `candidate_commit` | `<existing-A-or-null>` | 01–11 的 pre-freeze 事件为 `null`；A 存在后的正式验证/发布/协调事件**必须**引用已存在 A（I.2:2776） |
| `evidence_refs` | `["contract-tests:<artifact-id>"]` | `VALIDATED` 必须有 validation result / Evidence reference（I.3:2817） |
| `timestamp` | `<RFC3339>` | — |
| `reason_code` | 闭集（见 C.4） | — |
| `reason` | 字符串 | — |
| `references` | 数组 | 修正事件须引用错误事件（I.3:2838） |

- **[N]** 事件**不得**保存包含自己的 Git commit SHA 或 Ledger hash（I.2:2776）。
- **[N] 实际文件落地形态**：按键名排序的 canonical JSON 单行（本报告 §0 已实测）。

### C.3 合法状态与状态转换（I.2:2778-2788、I.3:2832-2838）
- 状态闭集：`NOT_STARTED, READY, IN_PROGRESS, BLOCKED, VALIDATED, COMPLETE, SUPERSEDED`。
- 合法主路径：`NOT_STARTED → READY → IN_PROGRESS → VALIDATED → COMPLETE`。
- `BLOCKED` 可从 `READY` / `IN_PROGRESS` 进入，阻塞解除后**回到原执行阶段**。
- `COMPLETE → IN_PROGRESS` **只允许** `STATUS_CORRECTION` 补偿事件，且必须引用错误事件；历史行永不修改。
- Candidate 缺陷使用 `CANDIDATE_SUPERSEDED`，不得修改既有 A 身份。
- 依赖解锁：默认只由 upstream `COMPLETE` 解锁；子 Spec 显式允许 `VALIDATED` 时除外（I.3:2816）。Index:85 同义。

### C.4 reason_code 取值（I.2:2790-2807，共 14 个）
`PREREQUISITES_SATISFIED, EXECUTION_STARTED, VALIDATION_PASSED, ACCEPTANCE_COMPLETE, BLOCKED, SPEC_CONFLICT, SPEC_INCOMPLETE, FREEZE_BOUNDARY_REACHED, CANDIDATE_FROZEN, CANDIDATE_SUPERSEDED, EVIDENCE_PUBLISHED, COORDINATION_PASSED, FINALIZATION_COMPLETE, STATUS_CORRECTION`。

### C.5 Reducer 8 条校验规则（I.3:2809-2820）
1. 文件严格 UTF-8；每个非空行满足 Event Schema。
2. `event_id` 全局唯一；事件按**文件顺序** append，**不得排序后重新解释**。
3. `from_status` 必须等于前一归约状态。
4. 状态转换必须合法；DAG 依赖默认只由 upstream `COMPLETE` 解锁。
5. `VALIDATED` 必须有 validation result/Evidence reference；`COMPLETE` 必须已满足全部 acceptance criteria。
6. Execution Authority 必须允许该动作；`FEEDBACK-BOUND` / `GATE-DEFINED` **不能因状态变化自动获得实施权限**（对应 Index:33-39 权限表；Spec 16–18 不可执行）。
7. Candidate A 后的事件必须符合 A/B/C 阶段、commit binding 与 append-only allowlist。
8. 同一状态出现互斥后继、跳过强制阶段或缺失前置条件时，**不采用 last-line-wins**，返回 `SPEC_STATUS_CONFLICT`。

### C.6 append-only 校验（I.4:2840-2852）
- **[N]** 运行期状态事件先在受控 staging 生成，不要求每动作单独提交。
- **[N] 持久化边界表**：
  | Boundary | Wiki Ledger 允许事件 | Coding Ledger |
  |---|---|---|
  | Candidate A | 01–10 的真实状态与 Spec 11 freeze-boundary entry；**不引用 A 自身 SHA** | 不存在 |
  | Evidence B_wiki | 只追加绑定 A 的 Spec 11–14 validation/publication events | 不存在 |
  | Finalization C_wiki | 只追加 Spec 15 coordination/finalization events | 不存在 |
- **[N]** 任何对旧行的修改/删除/重排/非法新增 → 相应 Candidate/Evidence/Finalization Gate 失败（I.4:2850）。

### C.7 canonical prefix + controlled pending suffix 归约（I.3:2822-2830）
- **[N] 形式**：`canonical persisted ledger prefix` + `Candidate-bound validated pending suffix from controlled staging` → `effective execution status`。
- **[N] suffix 必须**：由同一 Candidate A 中的 reducer 生成/验证；记录目标持久化边界；具备自身 canonical hash。
- **[N] suffix 不是 Git canonical history**；不能单独证明 Cycle COMPLETE；**不能跨 Candidate 复用**。
- **[N]** 下一 A/B/C 边界必须**逐字节追加**该 suffix；若未追加、被修改或 Candidate 被取代，依赖它产生的 downstream Evidence **无效**。
- **[N] 具体用法**：Spec 11 正式 L1/回归通过后，由 pending suffix 归约到 `COMPLETE` 并解锁 Specs 12/13；12/13 完成事件同样先进 suffix，待 Spec 14 原样写入 B_wiki；该机制不创建中间 B 提交、不改变 A（I.4:2852、Spec11:98、Spec12:8、Spec13:8）。
- **[N] Candidate 隔离要求**：suffix 由同一 Candidate A 的 reducer 生成/验证，不跨 Candidate 复用；Candidate A 后事件必须符合 A/B/C 阶段与 commit binding（I.3 规则 7；Spec10:79 "Candidate 隔离"）。

### C.8 非法事件返回（I.3:2820、Spec10:129、Index:106）
**[N]** 返回 `SPEC_STATUS_CONFLICT`；禁止忽略非法行 / 重排 / last-line-wins（Spec10:55）。`SPEC_INCOMPLETE` 与 `SPEC_CONFLICT` 另作为 reason_code 存在（I.2:2798-2799）。

### C.9 治理规则（I.5:2854-2867）
`GOV-SPEC-001`（子 Spec 不得覆盖 Master）、`GOV-SPEC-002`（Candidate A 后子/索引文档静态，只能新 superseding Candidate）、`GOV-STAT-001`（append-only Ledger 是唯一动态执行状态源）、`GOV-STAT-002`（空 Ledger + Child Initial Status = genesis）、`GOV-STAT-003`（当前状态必须由 Candidate-bound 确定性 reducer 产生）、`GOV-STAT-004`（B/C 只能 append 阶段合法事件，不得改写历史）、`GOV-FRZ-001`（Specs 12–15 所需全部工具必须在 Spec 11 冻结 A 前存在且已开发验证）、`GOV-FRZ-002`（freeze 后工具缺陷必须 supersede A 并回到 owning pre-freeze Spec）。
**[N]** 这些治理规则**不属于** `agent_core.contracts` Payload，**不进入** `payload-descriptor.normative_rule_set`（I.5:2867）。

---

## D. Appendix D 产物路径与 schema 清单

### D.1 Candidate Payload artifacts（D.1:2451-2458）
| Artifact | 位置/身份 | 禁止可变字段 |
|---|---|---|
| `agent_core/contracts/payload-descriptor.json` | 两仓 Candidate A，**inside Payload** | payload hash、governance state、commit SHA |
| `schemas/*.json` | 两仓 Candidate A，inside Payload | timestamp、absolute path |
| `contract.md` | 两仓 Candidate A，整文件进 Payload | release-specific Evidence |
| shared conformance tests | 两仓 Candidate A，inside Payload | project imports |

### D.2 Evidence Publication B artifacts（D.2:2460-2518）
**[N] 推荐路径**：
```text
docs/contracts/releases/0.1.0/
├── contract-manifest.json
├── changelog.md
└── validation/
    └── <wiki|coding>/
        ├── run-manifest.json
        ├── evidence-manifest.json
        ├── validation-report.md
        ├── rule-traceability.json
        └── sanitized-replay-corpus.jsonl
```
- **[N]** `changelog.md` 必须随 release **append-only** 保存，**不进入** Payload Hash；Cycle COMPLETE 后不得覆盖既有文件（D.2:2477）。
- **[N] Evidence Manifest 最小 Schema**（D.2:2481-2500）：`contract_version`、`contract_payload_hash`、`verified_repository_commit`、`repository`、`environment{python,pydantic,os}`、`evidence{contract_tests,historical_replay,fresh_smoke,full_regression}`、`producer_coverage[]`、`benchmark_reference_status`。
  - Wiki：`repository="wiki"`、`full_regression="PASS_WITH_KNOWN_BASELINE_FAILURES"`、`benchmark_reference_status="BENCHMARK_BASELINE_NOT_REPRODUCIBLE"`；Coding：`"coding"`/`"PASS"`/`"BENCHMARK_REPRODUCTION_RESTRICTED"`（D.2:2503）。
  - **不含**自身 hash 与 B SHA（D.2:2503）。
- **[N] Rule traceability**（D.2:2505-2518）只保存引用：`{contract_version, rules:[{rule_id, shared_tests:[...], evidence_ids:[...]}]}`。
- **[N] `contract-manifest.json` 字段**（§12.5:1369-1376）：`contract_version, contract_payload_hash, payload_descriptor_hash, schema_set_hash, canonical_payload_repository: wiki, canonical_payload_commit: <Wiki Candidate A>`；位于所声明 Payload **之外**，不进 Payload Hash；同步到 Coding 后内容不变（§12.5:1378）。

### D.3 Cycle Plan 与 Finalization（D.3:2520-2532）
- **[N]** `cycle-plan.json` 在两个 B SHA 已存在后由协调系统构造，是 CI dispatch/input artifact，**不属于** A_wiki/A_coding/B_wiki/B_coding 的 git tree；可由受控协调运行归档，但**不得**以自引用方式放进自己所声明的 Evidence commit。
- **[N] Wiki 最终路径**：`docs/contracts/releases/0.1.0/cycle-report.json`、`cycle-report.md`、`docs/contracts/current.json`。
- **[N]** Cycle Report JSON 结构以 §16.5 为准（见 A.6/A.5）；`current.json` 只能是 release pointer（4 字段）；Coding 停在 B_coding，**不创建** cycle-report 或 current pointer。

### D.4 EvidenceRecord invariants（D.4:2534-2547）
- **[N] 机器校验**：`PASS → foundation_output present AND error_envelope null`；`FAIL → error_envelope present; foundation_output optional`；canonical event JSON ≤ 64 KiB；`run_id` 匹配 `^[A-Za-z0-9_-]+$`；`event_id` 为 canonical UUID 或 ULID；`producer_id`/`stage` 必须存在于 Registry。
- **[N]** sink I/O 失败使用 `evidence.sink_write_failed` / `evidence.invalid_run_id` / `evidence.artifact_unavailable` 诊断到结构化应用日志与内存 counter，**不能递归写回同一 sink**。

### D.5 其他权威路径
- **[N] Staging**：`output/contract-validation/staging/<run_id>/events/<event_id>.json`（§11.1:1167）；配置 `AGENT_CONTRACT_EVIDENCE_DIR`、`AGENT_CONTRACT_RUN_ID`（§11.1:1173-1174）。
- **[N] 原子写入序列**：canonical serialize → `<event_id>.json.tmp`（同目录）→ flush/close（实现另加 fsync）→ `os.replace` → `<event_id>.json`；发布工具只读 `.json`，忽略 `.tmp`；**任何残留 `.tmp` 令 Smoke Evidence Gate 失败**（§11.1:1179-1189）。
- **[N] Contract Manifest 外部路径**：`docs/contracts/releases/0.1.0/contract-manifest.json`（§12.5:1364）。
- **[N] `.gitignore` 必须加入** `/output/contract-validation/staging/`（§11.1:1191-1195）。

---

## E. Spec 11–15 对 Spec 10 的"零实现工作"声明要求

**[N] 总纲**：Spec 10 必须在 Candidate A 冻结前交付全部 post-freeze 依赖：packaging、local gates、L2/L3 harness、sanitizer/publisher、status reducer、Wiki coordinator/finalizer 与 workflows；Spec 11 以后这些实现不得再改变（Spec10:19）。Spec10:132 与 Acceptance 要求"Spec 12–15 所需能力无待实现项"；Stop Condition：任一 post-freeze 步骤仍需要未实现脚本/Schema/workflow 即停止（Spec10:136）。Index:89 同义。

逐条（每条 = Spec 10 必须预先交付的能力，否则下游 Spec 不得新增工具）：

| 下游 | 零实现声明（原文位置） | Spec 10 必须预先交付 |
|---|---|---|
| 11 | 冻结后禁止修改 Contract Payload/Adapter/接线/测试/replay/sanitizer/smoke/invariance/publisher/status reducer/coordinator/finalizer/config/pyproject/lock/workflows（Spec11:34-45）；A 必须包含 Specs 12–15 所需全部工具与 workflow（Spec11:91） | 6 个脚本 + 2 个 config + workflows + packaging + baseline/tooling inventory；`validate_local.py --gate pr/candidate`、`-m build`、baseline comparator、known-test-baseline |
| 12 | 不得新增/修改任何 runner、sanitizer、assertion、Schema、Adapter、test、config、workflow；工具不足即停（Spec12:24）；Stop：工具需要修改、sanitizer 改变 Legacy facts（Spec12:89-91） | `replay_history.py` + `replay-v0.1.json` + allowlist extraction + 扫描 + corpus 生成 + evidence status 分类 |
| 13 | 不得修改 smoke harness、producer checker、invariance comparator、Adapter、sink、config、tests、business code、workflow（Spec13:23）；Stop：需要修改工具/接线/tests（Spec13:98） | `validate_local.py --gate smoke` + `smoke-v0.1.json` + producer/stage coverage checker + off/observe 四类不变性 comparator + run manifest 预登记与实际值记录 + Evidence 闭合检查 |
| 14 | Forbidden：Payload、Adapter、producer、tests、scripts、config、pyproject、lock、workflow 全部不可改（Spec14:45）；Stop：publisher 必须修改才能正确净化（Spec14:102） | `publish_evidence.py` + 发布扫描 + EvidenceArtifactKind allowlist + manifest/corpus/traceability writer + ancestry/diff allowlist 校验 + ledger 纯追加校验（status reducer） |
| 15 | 不得修改 coordinator、workflow、report generator、finalizer、status reducer、Schema 或任何 Candidate/Evidence 文件（Spec15:24）；Stop：coordinator 需要调用真实模型或 moving main（Spec15:97） | `coordinate_cycle.py` + `finalize_cycle.py` + cycle-report generator + canonical JSON/MD coordination artifact 与 hash 校验 + `current.json` writer + `COORDINATION_PASSED`/`FINALIZATION_COMPLETE` reducer 支持 + 严格 C allowlist |

**[N] 治理层要求**：`GOV-FRZ-001`（Spec 12–15 所需全部工具必须在 Spec 11 冻结 A 前存在并验证，I.5:2863）；`GOV-FRZ-002`（freeze 后工具缺陷必须 supersede A 并回到 owning pre-freeze Spec，I.5:2864）。Master §0.7:188 同义。
**[N] Spec 10 Handoff 必须提供**：完整 pre-freeze tooling inventory、版本、synthetic 验证结果和"Spec 12–15 零实现工作"声明（Spec10:144）；只有 Spec 10 `COMPLETE` 才可进入 Spec 11。

---

## F. Spec 10 的 6 条 Development Validation Commands：期望 vs 现状

（Spec10:95-104 两仓通用 6 条；Spec10:106-112 Wiki 额外 3 条 fixture 命令。现状为我在本 worktree 实测，Python 3.12 / 仓库 HEAD `102de4c`。）

### F.1 两仓通用 6 条

| # | 命令 | Spec 10 期望 | 当前现状（实测） |
|---|---|---|---|
| 1 | `python -m agent_core.contracts.tooling.generate_schemas --check` | 退出 0；Schema 快照与 Pydantic 重生成一致；descriptor 可派生；无工作区写入（§12.2:1317） | **已通过**，exit 0：`schema check OK: contract_version=0.1.0 schemas=6 schema_set_hash=sha256:d785d52d0f6ed9fc… rules=68` |
| 2 | `python -m agent_core.contracts.tooling.verify_payload` | 退出 0；白名单/descriptor/无自引用/Payload Hash 全部通过（FND-PKG-001/002、FND-VER-002/003/004/006） | **已通过**，exit 0：`40 files`，`payload_hash=sha256:df479f0ca413936d147bcceb8c50a0e88424520826bbde8f6340c35f97254623`，`descriptor_hash=sha256:5780138f…`，`schema_set_hash=sha256:d785d52d…` |
| 3 | `python -m pytest agent_core/contracts/conformance -q` | 全通过（§13.1 覆盖清单） | **已通过**：`224 passed in 5.96s` |
| 4 | `python -m pytest tests/contracts -q` | 全通过；Wiki 允许 3 个 deepeval 相关 skip | **已通过**：`92 passed, 3 skipped in 3.71s`（缺 `test_packaging.py`） |
| 5 | `python scripts/contracts/validate_local.py --gate pr` | 退出 0，执行 A.1 的 8 步 PR gate | **失败**，exit **2**：`python.exe: can't open file '…\scripts\contracts\validate_local.py': [Errno 2] No such file or directory`（`scripts/contracts/` 目录不存在） |
| 6 | `python -m build` | 生成 wheel + sdist，可 clean venv 安装（C.3） | **失败**，exit **1**：`ModuleNotFoundError: No module named 'build'`；且 Wiki `pyproject.toml` 无 `[build-system]`、无 pydantic pin、discovery 仅 `arknights_wiki*`（Coding 侧这些已具备，但 `build` 模块同样缺失） |

**变体**（同一缺失根因，均 exit 2）：
- `python scripts/contracts/validate_local.py --gate candidate`（Master C.1:2371）
- `$env:AGENT_CONTRACT_MODE='observe'; $env:AGENT_CONTRACT_RUN_ID='…'; python scripts/contracts/validate_local.py --gate smoke --run-manifest config/contracts/smoke-v0.1.json`（Master C.1:2382-2384）
- `$env:AGENT_CONTRACT_MODE='strict'; python scripts/contracts/replay_history.py --run-manifest config/contracts/replay-v0.1.json`（Master C.1:2378-2380）
- `python scripts/contracts/publish_evidence.py --candidate <A_SHA> --release-version 0.1.0`（Spec14:78）

### F.2 Wiki 额外 3 条 fixture 命令（Spec10:106-112，"工具开发验证，不是正式 Cycle coordination"）

| # | 命令 | 期望 | 现状 |
|---|---|---|---|
| 7 | `python scripts/contracts/status_ledger.py validate --ledger docs/specs/foundation-contract/execution-status-events.jsonl` | 退出 0；空 ledger → genesis；合法 pending suffix 可临时解锁；非法 events → `SPEC_STATUS_CONFLICT` | **失败**，exit 2：`can't open file '…\status_ledger.py'` |
| 8 | `python scripts/contracts/coordinate_cycle.py --plan <FIXTURE_PLAN> --output <TEMP_OUTPUT>` | 退出 0，产出 `PASS/READY_FOR_FINALIZATION`，无 self-reference、tree allowlist 生效 | **失败**，exit 2：`can't open file '…\coordinate_cycle.py'` |
| 9 | `python scripts/contracts/finalize_cycle.py --coordination <TEMP_OUTPUT> --release <TEMP_RELEASE>` | 退出 0，仅准备 C allowlist 文件与 pointer，不记 C 自身 SHA | **失败**，exit 2：`can't open file '…\finalize_cycle.py'` |

### F.3 参考现状（与 gate 期望的偏差，见 G-07）
- `known-test-baseline.json` 记录 `counts = 542/7/3, total 552`，`baseline_commit=bc954d3…`，`fingerprint_anchor_commit=838ba4c…`。
- **实测**：`python -m pytest tests/test_stats_collector.py -q` → `10 passed`（exit 0）。即 Appendix E.2 登记的三条 known failure **当前全部 PASS**，将落入 `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY` 分支（E.2:2604）。
- Spec 09 ledger 事件实测记录：Wiki full suite `637 passed / 10 skipped / 0 failed`；与 §1.3:236、§14.2:1532、C.4:2432、E.2:2590-2595 写死的 `542/7/3 → PASS_WITH_KNOWN_BASELINE_FAILURES` **不一致**。

---

## G. 风险与歧义清单（不自行填补）

### SPEC_CONFLICT（文档内部/文档与仓库事实冲突）

- **G-01 `smoke-v0.1.json` 无字段级规范**：§13.3:1470-1485 用 YAML 伪字段列 `model, provider, case_ids, required_producer_stages, expected_calls, max_calls, estimated_cost_cap, network_requirement, side_effect_policy, contract_version, payload_hash, candidate_commit`，Spec13:29-40 再追加 `timeout/duration cap`、`Evidence directory + explicit run_id`；但**没有任何地方给出 JSON 键名、必填/可选、或 Schema 文件**。Appendix F:2657 只要求"manifest validation"与"不含凭据"。→ 不得发明键名；实现前需回修 Spec（`SPEC_INCOMPLETE`）。
- **G-02 `replay-v0.1.json` 结构完全未定义**：Spec12:35-40 只描述来源选择原则（source domain / runtime adapter status / evidence role / `historical_replay_only`），未给任何字段；`replay_history.py --run-manifest` 的消费契约因此不可实现。→ `SPEC_INCOMPLETE`。
- **G-03 pending suffix 的载体与 schema 未定义**：I.3:2822-2830 要求 suffix "由同一 Candidate A 中的 reducer 生成/验证、记录目标持久化边界、具备自身 canonical hash"，但 I.2 的 Event Schema **没有** `persistence_boundary`/`suffix_hash`/`sequence_no` 字段，也没有规定 suffix 的路径、文件格式或与 canonical ledger 的分隔方式。→ `SPEC_INCOMPLETE`（Spec10:78 却要求实现它）。
- **G-04 `sink_failure_count == 0` 与"被拒绝的 EvidenceRecord"跨进程不可观测**：§11.2:1207-1208 要求 Smoke Gate 检查这两项，但 counter 是 Wiki runtime/sink 的**进程内内存计数**（`runtime.py:227,256`、`evidence_sink.py:97,107`），文档未定义任何把 actual count / rejected record 传递给 `validate_local.py --gate smoke` 的 artifact 字段。→ `SPEC_INCOMPLETE`.
- **G-05 PR gate 的 "contract-related regression subset" 未定义**：§15.1:1560 列出该步骤，但没有任何地方界定子集范围（按目录？按 marker？按 nodeid 前缀？）。→ `SPEC_INCOMPLETE`。
- **G-06 job ↔ workflow 文件数不匹配**：C.4:2429-2436 列出 6 个 job（含 Historical replay、Fresh smoke 为"受控 Windows"、Coordination），但 Spec10:29/41 只允许 5 个 workflow 文件，且没有任何 L2/L3 workflow 文件；触发条件（`on:`）全文未定义。→ 需澄清 L2/L3 是受控手动运行（按 C.1/C.2 命令）还是 workflow。
- **G-07 回归基线硬编码与仓库现状冲突（最高优先）**：§1.3:236、§14.2:1532、C.4:2432、Appendix E.2:2590-2595 均写死 Wiki `542 PASS / 7 SKIP / 3 FAIL → PASS_WITH_KNOWN_BASELINE_FAILURES`；但 Spec 09 ledger（已入库）记录 Wiki 全量为 `637 passed / 10 skipped / 0 failed`，且我实测 `tests/test_stats_collector.py` 三条登记失败**当前全部 PASS**。按 E.2:2604 应走 `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY`（不使 Cycle 失败，但需 review，且不得同 Cycle 静默删基线）。→ Candidate Gate 的"期望状态"文字与可观测结果不一致；需在 Spec 10/11 前明确：baseline refresh、期望状态改写，还是按 review 分支放行。
- **G-08 changelog.md 的 allowlist 归属冲突**：§11.3:1227-1236 的"允许进入 B"清单**只有 6 项**（run-manifest / contract-manifest / evidence-manifest / validation-report / rule-traceability / sanitized-replay-corpus），**不含** `changelog.md`；但 D.2:2467-2477 要求它必须随 release append-only 存在，Spec14:27 也把它列入 Allowed Changes，F.4:2692 的 B_wiki/B_coding 行写"Wiki validation artifacts、contract manifest、changelog"。→ 发布扫描的 allowlist 必须显式含 changelog，否则 Coordinator 的 diff allowlist 会自相矛盾。
- **G-09 `known_failures` 字段命名三处不一致**：Spec01:70 写 `normalized_signature / fingerprint`；文件实际是 `normalized_error_signature / fingerprint_sha256`（+`symbolic_failure_locus`、`fingerprint_anchor_commit`）；Appendix E.1:2553-2564 的六字段含 `symbolic_failure_locus`。→ validate_local.py 必须按实际文件 + E.1 六字段实现，但文档未声明哪份为准。
- **G-10 `.gitignore` 条目与规范非逐字一致**：§11.1:1194 要求 `/output/contract-validation/staging/`；实际写入 `output/contract-validation/staging/`（无前导 `/`）并额外加 `raw/`、`private/`（Spec01:58 允许 raw/private）。→ 低危，但严格逐字门禁会报差。

### SPEC_INCOMPLETE / 实现边界歧义

- **G-11 "cycle-report generator" 无文件路径**：Spec10:84 要求 "cycle-report generator 只输出 PASS/READY_FOR_FINALIZATION"，但 Allowed Changes（Spec10:27）只有 6 个脚本，未列 generator 文件；可能内嵌于 `coordinate_cycle.py`，但文档未说明。同理 Spec10:71-72 的 "fresh-smoke harness / invariance comparator / baseline comparator" 也没有独立文件条目——Spec 09 已把后两者放在 `tests/contracts/`，而 Spec 10 说"复用 Spec09 assertions"（Spec10:69）。→ 需明确哪些能力是"脚本"哪些是"测试库"。
- **G-12 `validate_local.py` 无法干净复用 Spec 09 comparator**：`fingerprint_sha256`/`classify_failure`/`classify_status` 目前是 `tests/contracts/test_test_baseline.py` 内的测试局部函数（非包 API）。Spec10:69 说"复用 Spec09 assertions"，但未说明是导入 tests 模块、复制实现，还是上移到 `agent_core.contracts`（后者会改 Payload → 触发 A2/镜像同步）。
- **G-13 smoke 命令语义二义**：Spec10:71 说 harness "业务运行结束后独立检查 Evidence 闭合"，暗示 check-only；但文档给的唯一 smoke 命令是 `validate_local.py --gate smoke`，Spec13:48 又要求"以 observe 执行真实模型/Trace/Eval/Benchmark 相关路径"。→ 无法确定该命令是"跑业务 + 校验"还是"只校验已完成的 run"，也没有定义业务路径的入口清单。
- **G-14 expected mapping 的预登记来源未定义**：§13.2:1448、Spec12:47 要求 `actual` 与"预登记 expected mapping"比较，但没有任何 artifact 字段/文件被指定承载 expected mapping（推测在 `replay-v0.1.json`，但见 G-02）。
- **G-15 Linux/跨平台 job 的 "expected hash" 来源未定义**：§15.2:1583 要求 Linux 重算并"比较 expected hash"，但未说明 expected hash 从哪个 artifact 读取（`contract-manifest.json`？bundle？workflow 输入？）。
- **G-16 Coding Local CI 不 clone Wiki 时如何取得预期身份**：§15.1:1550 与 Spec10:51 禁止 clone 另一仓，但"同版本不同载荷 → DIVERGED/FAIL"（§12.6:1398）的判定需要权威 expected hash；文档未定义 Coding 侧的 expected hash 来源。
- **G-17 fixture 文件位置未定义**：Spec10:110-111 用 `<FIXTURE_PLAN>` / `<TEMP_OUTPUT>` / `<TEMP_RELEASE>` 占位，但 Allowed Changes 只允许"必要的 contract tooling self-tests"（Spec10:32/44），没有 fixtures 目录或样例 cycle-plan。
- **G-18 退出码全部未定义**：见 A.1/A.4；文档只规定 `SPEC_STATUS_CONFLICT` 这一符号，不给进程退出码映射。
- **G-19 `python -m build` 的前置依赖未声明**：环境缺 `build` 模块；Spec10 允许改 `pyproject.toml`，但没写要把 `build` 加进 dev 依赖，也没写 build 是否允许联网做 isolated build（离线环境会失败）。
- **G-20 Wiki/Coding descriptor 磁盘字节不同**：canonical hash 相同，故 payload hash 一致（已核验）；但若任何工具对 descriptor **原始字节**做比较（例如二进制 diff 或 sha256sum），会出现假阳性。文档只说 canonicalize，未禁止逐字节比较 → 实现注意项。
- **G-21 并发修改 `conformance/rules.py` 会改变 Contract Payload Hash（需双仓重同步）**：`agent_core/contracts/conformance/rules.py` 位于 `agent_core/contracts/**` 内（§12.4:1339-1343），编辑它必然改变 `contract_payload_hash`。观察到的实际编辑把 `FND-PKG-003` 从 `DEFERRED_PAYLOAD_RULES` 移出并转入项目层落点。**[N]** 两仓镜像必须由 Wiki bundle 产生、不能人工分别实现（F.1:2641）；Coding 必须解包校验后才原子替换（§12.7:1407-1415）。**（推断）**因此该修改后必须：重跑 `generate_schemas --check` + `verify_payload`、重新 bundle 并 apply 到 Coding、同步更新 Coding 侧 `test_traceability.py`；否则两仓 Payload Hash 不一致 → DIVERGED/FAIL（§12.6:1398）。另外 `normative_rule_set` 由 `contract.md` 解析（`generate_schemas.parse_declared_rules`），**不含** DEFERRED 列表，故 descriptor 的 context 不变；但 Spec10:47 要求共享工具缺陷回到 Spec 03 修正并重验依赖——本次修改落在 Spec 09 的产物上，归属需明确。

### 未能核验项
- Coding 仓的 `tests/contracts/`、`adapters/foundation/` 现状只在 `_worktrees\foundation-contract\coding`（`feature/foundation-contract-spec10`）核验；Coding canonical `main`（`08a8275`）**没有**任何 Foundation 文件（`scripts/contracts`、`config/contracts/smoke-v0.1.json`、`tests/contracts` 均不存在）。Spec 11 的 "Candidate A 起点" 需明确是哪个分支/worktree（Master §1.1:198 的 Coding HEAD `08a8275` 与当前 worktree `1798859` 不同）。→ 这是 Candidate A 起点漂移风险，需在 Spec 11 Stage 0 处理（Master Appendix G:2700）。
- Coding 侧 `python -m build` / `pytest tests/contracts` 未在此环境实跑（（未核验））。
