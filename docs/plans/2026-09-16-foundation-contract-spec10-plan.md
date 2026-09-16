# Spec 10 执行计划 — Packaging and Local Contract CI

> 日期：2026-09-16
> Spec：`10 — Packaging and Local Contract CI`（`IMPLEMENTATION-READY`，DAG：`09 → 10 → 11`）
> 分支：Wiki / Coding 各 `feature/foundation-contract-spec10`（自 `feature/foundation-contract` 分出）
> 规范来源：Master §3.3 / §11–§17 / Appendix B–I；子 Spec 10–15
> 前置：Spec 01–09 全部 `COMPLETE`（账本 35 条事件，末条 2026-09-14）
> 性质：**非规范性**执行计划与决策记录（不进入 Contract Payload）

本文件记录 Spec 10 的实施范围、provisional 决策、验证证据与交接事实。若与母 Spec 冲突，以母 Spec 为准并触发 `SPEC_CONFLICT`。

---

## 1. 目标与边界

Spec 10 是 **Candidate A 冻结前最后一个实施单元**。它必须把 Spec 12–15 需要的**全部**工具预先交付并开发验证；Spec 11 冻结 A 之后这些实现不得再改变（`GOV-FRZ-001/002`）。

不做的：创建独立 `agent-core` distribution、统一 provider/retrieval/memory/sandbox/approval/checkpoint、修改 Dashboard/报告/评分/路由、FX 换算、L2/L3 workflow 文件（C.4 的 Historical replay / Fresh smoke 属受控手动运行）。

## 2. 交付清单（对照 Spec 10 Allowed Changes）

| 产物 | Wiki | Coding | 状态 |
|---|---|---|---|
| `pyproject.toml`（build-system / `pydantic==2.13.4` / package discovery / package data / `build` dev 依赖） | ✅ | ✅ | 完成 |
| `scripts/contracts/validate_local.py`（`pr` / `candidate` / `smoke`） | ✅ | ✅ | 完成 |
| `scripts/contracts/replay_history.py` | ✅ | ✅ | 完成 |
| `scripts/contracts/publish_evidence.py` | ✅ | ✅ | 完成 |
| `scripts/contracts/status_ledger.py` | ✅ | — （规范规定仅 Wiki） | 完成 |
| `scripts/contracts/coordinate_cycle.py` | ✅ | — | 完成 |
| `scripts/contracts/finalize_cycle.py` | ✅ | — | 完成 |
| `config/contracts/smoke-v0.1.json` | ✅ | ✅ | 完成 |
| `config/contracts/replay-v0.1.json` | ✅ | ✅ | 完成 |
| `tests/contracts/test_packaging.py` | ✅ | ✅ | 完成 |
| `tests/contracts/test_test_baseline.py`（Spec 09 产物，本 Spec 补项目层规则反向核验） | ✅ | ✅ | 完成 |
| contract tooling self-tests（`test_status_ledger` / `test_replay_publish_tools` / `test_cycle_tools` / `test_validate_local_tools`） | ✅ | 按仓适用 | 完成 |
| `.github/workflows/contract-local.yml` | ✅ | ✅ | 完成 |
| `.github/workflows/contract-payload-linux.yml` | ✅ | ✅ | 完成 |
| `.github/workflows/contract-coordinate.yml` | ✅ | — | 完成 |

## 3. Provisional 决策（用户已批准：最小可行语义 + 显式标注 + Spec 11 Stage 0 校准）

规范提取（`output/spec10-normative-extraction-report.md`）识别出 21 条冲突/缺口，其中 3 条为 `SPEC_INCOMPLETE`（规范完全未定义必要语义）。用户裁定：**按最小可行语义实现，显式标注 provisional，入账本 `SPEC_INCOMPLETE` 事件，留 Spec 11 Stage 0 校准**。

| 缺口 | 内容 | provisional 收敛 | 风险 |
|---|---|---|---|
| **G-02** | `replay-v0.1.json` 字段结构完全未定义 | 只使用规范命名的概念：`run_id` / `contract_mode` / `contract_version` / `payload_hash` / `repository_commit` / `sources[]`（含 `source_class` / `runtime_adapter_status` / `evidence_role`）/ `max_records` / `reproduction_restriction` | 中：项目本地 config，不进 Payload |
| **G-01** | `smoke-v0.1.json` 只有 YAML 伪字段、无 JSON 键名 | 键名由 §13.3 的字段概念直译（snake_case），并加 `manifest_version` / `coverage_policy` / `evidence_root` | 中：同上 |
| **G-03** | pending suffix 无载体（Event Schema 无对应字段、无路径格式） | 双文件载体：`*.pending.jsonl`（纯事件行）+ `*.pending.json`（envelope：`pending_version` / `target_boundary` / `candidate_commit` / `event_count` / `suffix_hash`，envelope 不参与自身 hash） | 高：规范语义最重，必须在 Spec 11 Stage 0 前校准 |
| **G-04** | `sink_failure_count` / 被拒绝记录在进程内存，无承载 artifact | 运行后汇总 `output/contract-validation/staging/<run_id>/run-summary.json`（8 键），**缺失即 gate 失败**（无法验证 ≠ 通过） | 中 |
| **G-05** | "contract-related regression subset" 未定义 | 由 `producer-registry.json` 的 **IN_SCOPE** producer `source_locations` 导出模块名，静态匹配引用它们的测试文件（排除 `tests/contracts/`）；无匹配则退化为 `tests/` 全量并注明 | 低 |
| **G-06** | C.4 列 6 个 job，Spec 10 只允许 5 个 workflow 文件；`on:` 触发条件全文未定义 | 只建 5 个文件；L2/L3 以注释形式给出受控手动命令，不建 workflow | 低 |
| **G-08** | `changelog.md` 不在 §11.3 的 B 清单内，但 D.2/Spec14/F.4 都要求 | 发布 allowlist 与 coordinator 的 diff allowlist **显式包含** `changelog.md` | 低 |
| **G-13** | `--gate smoke` 是"跑业务"还是"只校验"未定义 | 只校验已完成的 run；业务运行由受控手动命令完成 | 低 |
| **G-15 / G-16** | Linux / Coding 侧的 expected payload hash 来源未定义 | 不自动推断、不 clone 另一仓；仅显式 `--expect-payload-hash` / workflow input 时比较 | 低 |
| **G-17** | fixture 文件位置未定义 | fixture 全部建在临时目录，不入库 | 低 |
| **G-18** | 退出码全文未定义 | `0` 通过 / `1` gate 失败 / `2` 用法或配置错误（沿用 `generate_schemas` 的既有约定） | 低 |
| **G-19** | `python -m build` 前置 `build` 模块未声明 | 两仓 `dev` extra 增加 `build>=1.2` | 低 |
| **G-12** | Spec 09 的 comparator 位于无 `__init__.py` 的 `tests/contracts/` | 按文件路径 `importlib.util.spec_from_file_location` 加载，不新建 payload 模块 | 低 |

## 4. 关键实现决策（非规范缺口，属工程选择）

1. **脚本自举**：`python scripts/contracts/x.py` 的 `sys.path[0]` 是脚本目录，仓库根不在其中（只有 `python -m` 才加 CWD）。所有 `scripts/contracts/*.py` 必须自行把仓库根插入 `sys.path`，**不得**依赖 editable install —— 两仓都提供顶层 `agent_core`，同一解释器无法同时可编辑安装两者。
2. **payload deferral 归属变更**：`FND-PKG-003` 原在 `DEFERRED_PAYLOAD_RULES`（defer 给 Spec 10）。本 Spec 交付 clean wheel smoke 后，它移出 deferral、登记进 `test_traceability.PROJECT_SCOPED_RULES`，落点在两仓 `tests/contracts/test_packaging.py`。这是 **Payload 内容变更**，已按 §12.7 重新 bundle 并原子提升 Coding 镜像（`sha256:64049830…`，40 文件）。
3. **项目层规则反向核验**：`test_traceability.py` 的 docstring 声称 `PROJECT_SCOPED_RULES` 由两仓 `test_test_baseline.py` 反向核验真实落点，但 Spec 09 未实现该核验。本 Spec 补上 `test_project_scoped_rules_have_real_landings`（AST 静态扫描 `@contract_rule`），消除"声明有落点、实际无人落点"的假闭环。
4. **PR gate 的 package smoke 用 `pip install --target`** 而非新建 venv：把 wheel 装进临时 target，`sys.path` 前置该 target，并断言 `agent_core.__file__` 确实位于 target 内（否则说明落回了 editable 安装），再经 `importlib.resources` 读取 descriptor 与 6 个 schema。等价于"不依赖 cwd 的干净安装"，但快得多。

## 5. 基线口径（G-07）

规范 §1.3 / §14.2 / C.4 / Appendix E.2 硬写 Wiki 基线为 `542 PASS / 7 SKIP / 3 FAIL → PASS_WITH_KNOWN_BASELINE_FAILURES`；但实测三条登记 known failure（`tests/test_stats_collector.py`）**现已全部 PASS**，Spec 09 账本记录全量为 `637 passed / 10 skipped / 0 failed`。

**用户裁定**：按规范自身定义的 `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY` 分支处理——**不使 gate 失败**，但**标记需 review**，且**不静默删除基线**。本 Spec 不刷新 `known-test-baseline.json`（baseline refresh 属 Spec 01 治理动作）。

## 6. 验证（见交接文档 §4 的实测输出）

| 命令 | 期望 |
|---|---|
| `python -m agent_core.contracts.tooling.generate_schemas --check` | exit 0 |
| `python -m agent_core.contracts.tooling.verify_payload` | exit 0 |
| `python -m pytest agent_core/contracts/conformance -q` | 全通过 |
| `python -m pytest tests/contracts -q` | 全通过（Wiki 允许 deepeval-gated skip） |
| `python scripts/contracts/validate_local.py --gate pr` | exit 0 |
| `python -m build` | exit 0 |
| Wiki fixture 三条：`status_ledger.py validate` / `coordinate_cycle.py` / `finalize_cycle.py` | exit 0（synthetic fixture） |

`--gate candidate` 与 `--gate smoke` 在 Spec 12–14 产出 Candidate-bound 证据前**预期失败**（缺 Evidence Manifest / 缺 run-summary），这是预期行为而非缺陷。

## 7. 风险与回滚

- 本 Spec 所有改动都在 Candidate A 冻结**之前**，可分别回退 packaging / scripts / workflows / configs；涉及 shared payload 的部分（`FND-PKG-003` deferral 归属）必须双仓重新同步，回滚亦须重新 bundle。
- 账本**永不回退**：状态修正只能追加 `correction` 语义的新事件。
- 最大遗留风险：G-03 pending suffix 载体是 provisional 设计，且它是 Spec 11 解锁 Spec 12/13 的机制依赖；必须在 Spec 11 Stage 0 优先校准。
