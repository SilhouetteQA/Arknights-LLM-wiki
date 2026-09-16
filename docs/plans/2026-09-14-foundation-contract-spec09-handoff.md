# Spec 09 收尾与交接汇报

> 日期：2026-09-14
> Spec：`09 — Shared Conformance and Project Contract Tests`
> Authority：`IMPLEMENTATION-READY`（Executable：YES）
> 最终状态：**`COMPLETE`**（账本 event `2255f9ed-6dcf-41bd-8769-abf181656f05`，`ACCEPTANCE_COMPLETE`）
> 性质：**非规范性**收尾记录（不进入 Contract Payload，不构成规范载体）
> 规范真相源：[Master Spec](../specs/2026-09-10-dual-agent-foundation-contract-master-spec.md) · 状态真相源：[execution-status-events.jsonl](../specs/foundation-contract/execution-status-events.jsonl)

本文件只记录 Spec 09 实际交付、验证证据、deviation 与向 Spec 10 的交接事实。若与母 Spec 冲突，以母 Spec 为准并触发 `SPEC_CONFLICT`。

---

## 1. 交付物

| 位置 | 文件 | 说明 |
|---|---|---|
| 双仓 | `agent_core/contracts/conformance/rules.py` | 新增 `RULE_REGISTRY`（79 条 statement）、`DEFERRED_PAYLOAD_RULES`、`PROJECT_SCOPED_RULES`、`rule_statement()`、`registered_rule_ids()`、`contract_rule` 装饰器 |
| 双仓 | `agent_core/contracts/conformance/test_traceability.py` | 6 例：descriptor 全覆盖 statement、无孤儿引用、conformance 只引用 payload 规则、payload 规则落点闭环 |
| 双仓 | `tests/contracts/test_evidence_sink.py` | 各 7 例：合法写入 / 原子 replace / 并发 8 条互不覆盖 / 残留 `.tmp` 不被读作证据 / 5 类非法 ID / 注入 I/O 失败 / 超限（模型层）/ 环境变量覆盖 staging 根 |
| 双仓 | `tests/contracts/test_test_baseline.py` | 各 10 例：逐字节复现 Appendix E 三条 anchor 指纹、指纹对字段顺序不敏感、回归分类（`ALLOWED_BASELINE_FAILURE` / `FINGERPRINT_MISMATCH` / `NEW_FAILURE` / `BASELINE_PASS_NOW_FAIL` / `SKIP_REGRESSION` / `RESOLVED_UNEXPECTEDLY`） |
| 双仓 | `tests/contracts/test_foundation_mapping.py` | 补 `@contract_rule` 落点：`FND-MAP-001` / `FND-MAP-002` |
| 双仓 | `tests/contracts/test_business_invariance.py` | 补 `@contract_rule` 落点：`FND-MODE-004` |
| 双仓 | `**/adapters/foundation/evidence_sink.py` | **deviation**：目录穿越检查由 `Path.resolve()` 改为 `os.path.abspath`（见 §5） |
| Wiki | `docs/specs/foundation-contract/execution-status-events.jsonl` | 追加 Spec 09 的 4 条状态事件（READY / IN_PROGRESS / VALIDATED / COMPLETE） |

## 2. Rule coverage 闭环

```text
payload 规范规则 68 条
  = conformance 落地 56 条
  + 项目侧落地    6 条（PROJECT_SCOPED_RULES）
  + 显式 deferral 6 条（DEFERRED_PAYLOAD_RULES）
```

- 显式 deferral：`EVD-PUB-002/003/004/006/007` → Spec 12 / 14；`FND-PKG-003` → Spec 10。
- `RULE_REGISTRY` 共 79 条 statement，`descriptor.normative_rule_set` 保持 **68 条不变**、不改 schema、不改 payload 语义。
- `test_traceability` 保证：descriptor 中每条规则都有 statement；无 statement 引用不存在的规则；conformance 只引用 payload 规则；**无孤儿引用**。

## 3. producer / stage 覆盖

Spec 07（Wiki）与 Spec 08（Coding）已各自为**每个** `IN_SCOPE` producer 的**每个** stage 建立固定响应 wiring test：

- Wiki 6 个 seam：`chat_completion` / `intent_rewrite` / `runner` / `judge` / `scoring` / `cost_log_summary`（13 例 wiring + 14 例 invariance）
- Coding 7 个 seam：`openai_compat` / `langfuse_generation` / `normal` / `environment_error` / `error` / `sdk` / `clickhouse`（12 例 wiring + 9 例 invariance）
- stage → producer 身份对照 `config/contracts/producer-registry.json` 与 `adapters/foundation/runtime.py::STAGE_PRODUCER` 双向验证。
- 未接线项：Wiki `trace.summary` 保持 `DEFERRED` 且**未伪造任何事件**。

## 4. 验证证据（账本 event `80612493…` / `2255f9ed…`）

| 命令 / 维度 | 结果 |
|---|---|
| `pytest agent_core/contracts/conformance -q`（双仓） | **224 passed** |
| `pytest tests/contracts` | Wiki **92 passed / 3 skipped**（3 例为 deepeval-gated scoring 用例）；Coding **97 passed** |
| Wiki 全量 `pytest tests/` | **637 passed / 10 skipped / 0 failed** |
| Coding 全量 `pytest tests/` | **470 passed / 13 skipped / 8 failed**（8 条全为已登记 git-ref 沙箱伪失败，数量在 8–12 间浮动，非代码回归） |
| Payload 身份 | `sha256:df479f0c…` / **40 文件**，双仓逐字节一致 |
| Appendix E 指纹 | 三条 anchor 指纹逐字节复现（`test_test_baseline`） |

## 5. Deviation 记录（必须在 Spec 11 冻结前被看见）

`**/adapters/foundation/evidence_sink.py` **不在** Spec 09 的 Allowed Changes 内，但必须修一处**真实缺陷**：

- 现状：Wiki `_within` / Coding `_escapes` 用 `Path.resolve()` 做防目录穿越检查。
- 问题：`Path.resolve()` 对**尚未 mkdir 的目录**在 Windows 并发下存在竞态，令合法的并发写入偶发被判为"逃出 staging 根"而拒绝（实测 30–50 轮里失败 2–3 次），**违反 `EVD-SINK-004` 的 concurrent-writer safe 要求**。
- 最小修复：改用 `os.path.abspath`（纯词法规范化，不访问文件系统、不解析 symlink）。防穿越能力不变（`run_id` / `event_id` 已由形状校验排除 `..` / `/` / `:`）。修复后 50 轮并发 0 失败。
- 性质：这是 Spec 09 的 sink 并发测试**暴露出的 Spec 04 遗留缺陷**，与 Spec 07/08 的缺陷修复同类，已记入账本。

Spec 04 / 07 / 08 另有累计三笔 deviation（`adapters/foundation/runtime.py` 增加进程级 accessor 与少量窄 helper、facts 补读 `prompt_tokens`/`completion_tokens`），均已在各自账本事件中登记。

## 6. 尚未形成的 L2/L3 事实（明确不声称）

- **本 Spec 不产出任何正式 Candidate-bound 证据。** 所有测试均在 Candidate A 冻结前的工作树上运行，`candidate_commit` 字段在账本中为 `null`。
- L2（历史重放 + 脱敏语料）与 L3（fresh smoke + producer 覆盖 + 业务不变性）**尚未执行**，其能力由 **Spec 10** 交付、由 **Spec 12/13** 在冻结后的固定 Candidate A 上执行。
- Wiki 三条 `stats.collector` 已知失败仍为 `DEFERRED`：仅 baseline comparator 按指纹精确 allow，**Cycle 1 内禁止顺手修复**。
- 历史 Benchmark 指标（`0.857`）为 `BENCHMARK_BASELINE_NOT_REPRODUCIBLE`，`gate_effect=NONE`，**不得**作为本 Cycle 的证据或判定依据。

## 7. 交接给 Spec 10

Spec 10（`Packaging and Local Contract CI`）是 DAG 上唯一解锁的 `IMPLEMENTATION-READY` 单元，也是 **Candidate A 冻结前的最后一个实施单元**。它必须交付：

1. 两仓 packaging：显式 `[build-system]`、固定 `pydantic==2.13.4`、package discovery 覆盖 `agent_core*`（Wiki 另含 `arknights_wiki*`，Coding 另含当前 packages + `adapters*`）、`contract.md` / descriptor / `schemas/*.json` 注册为 package data。
2. `scripts/contracts/`：`validate_local.py`（pr / candidate / smoke 三档）、`replay_history.py`、`publish_evidence.py`；Wiki 另含 `status_ledger.py`、`coordinate_cycle.py`、`finalize_cycle.py`。
3. `config/contracts/{smoke-v0.1,replay-v0.1}.json`。
4. `tests/contracts/test_packaging.py` + 必要的 tooling self-tests。
5. `.github/workflows/`：Wiki `contract-local` / `contract-payload-linux` / `contract-coordinate`；Coding `contract-local` / `contract-payload-linux`。

**验收前置（本 Spec 已就绪的原语）**：`conformance/rules.py` 的规则注册表与落点断言、`test_test_baseline.py` 的指纹比对器、`tooling/{canonical_json,generate_schemas,verify_payload,bundle}.py`。

**Handoff 声明**：Spec 09 交付的 Rule coverage、producer stage coverage、fixture 来源与"L2/L3 事实尚未形成"的口径已在本文件 §2 / §3 / §6 逐项列出；Spec 10 不得复用本文件的数字作为门禁证据，必须在其自身的权威命令下重新产生。

## 8. 回滚

- 项目侧测试各自回退（`tests/contracts/*` 为新增文件，删除即可）。
- shared conformance 改动通过 canonical repo 回退 + bundle 重新同步到 Coding 镜像（两仓 payload hash 必须重新收敛）。
- 账本**永不回退**：状态修正只能追加 `correction` 语义的新事件，不得改写或删除既有字节。
