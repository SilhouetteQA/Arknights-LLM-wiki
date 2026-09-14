# Spec 09 执行计划 — Shared Conformance and Project Contract Tests

> 计划日期：2026-09-14　|　Spec：`09-shared-conformance-and-project-contract-tests.md`
> 目标仓库：`WIKI_REPO` + `CODING_REPO`
> 前置：Specs 02–08 `COMPLETE`

## 1. 目标与现状

建立**测试能力**（不形成正式 L1/L2/L3 Evidence——那是 Spec 11/13 的职责）：让 68 条
payload 规则全部有机器可查的落点，补齐 Spec 04 遗留的 sink 文件行为测试与 baseline
comparator，并建立 traceability 检查。

**现状**（已实测）：

- descriptor `normative_rule_set` = 68 条 Rule ID 字符串（机器来源，**无 statement**）
- `contract.md` 声明 68 条规则（人类来源）
- conformance 测试覆盖 **56 条**，缺口 **12 条**：

| 缺口 | 落点 | 归属 |
|---|---|---|
| `FND-MAP-001/002` | 项目 Adapter 测试 | **本 Spec** |
| `FND-MODE-004` | 项目 invariance 测试 | **本 Spec** |
| `EVD-SINK-002/003/004` | 项目 sink 测试 | **本 Spec** |
| `FND-PKG-003` | packaging 前置 | Spec 10 |
| `EVD-PUB-002/003` | publication scan | Spec 12/14 |
| `EVD-PUB-004/006/007` | corpus/manifest/retention | Spec 12/14 |

## 2. Allowed Changes 逐项映射

**Shared payload（Wiki canonical，bundle 同步到 Coding）**

| 文件 | 改动 |
|---|---|
| `agent_core/contracts/conformance/rules.py` | 加 `RULE_REGISTRY`（rule_id → statement，从 Appendix A 提取） |
| `agent_core/contracts/conformance/test_traceability.py` | 新建：规则全覆盖 + 无孤儿引用 + statement 齐备 |
| `agent_core/contracts/conformance/` 现有 test_*.py | 补边界矩阵缺口 |
| `agent_core/contracts/payload-descriptor.json` | 仅当规则声明漂移时修正（不扩 schema） |

**每仓 `tests/contracts/`**

| 文件 | 改动 |
|---|---|
| `test_evidence_sink.py` | **新建**：FileEvidenceSink 五类文件行为（Spec 04 遗留） |
| `test_test_baseline.py` | **新建**：baseline comparator（FND-REG-001~004） |
| `test_foundation_mapping.py` | 补 `@contract_rule("FND-MAP-001/002")` 落点 |
| `test_business_invariance.py` | 补 `@contract_rule("FND-MODE-004")` 落点 |
| `conftest.py` | 如需要：共享 fixture（sink 临时目录等） |

## 3. 分阶段执行

### 阶段 A — 规则 metadata + traceability（shared，Wiki 先做）

1. `rules.py` 加 `RULE_REGISTRY: dict[str, str]`，从 Appendix A 提取 68 条 statement。
2. 加 `declared_rules()` / `rule_statement()` 访问器。
3. 新建 `test_traceability.py`，验证：
   - descriptor 的 68 条 ⊆ RULE_REGISTRY（每条有 statement）
   - conformance 测试引用不超出 descriptor（无孤儿）
   - **全覆盖门槛**：descriptor 规则在 conformance + 项目测试的并集里有落点（允许
     "项目层规则"由项目测试提供落点，通过一个可配置的 `PROJECT_RULE_SCOPES` 白名单声明）

### 阶段 B — sink 文件行为测试（两仓，Spec 04 遗留）

新建 `tests/contracts/test_evidence_sink.py`，覆盖：

- 合法写入（formal `.json`，canonical JSON）
- 原子 replace（落盘无 `.tmp`，同 event_id 重写）
- 并发 8 条互不覆盖、event_id 唯一
- 5 类非法 ID 被拒且不越出 staging 根
- 超限（>64 KiB）被拒
- 注入 `os.replace` 失败抛 `SinkFailure` 并计数
- 残留 `.tmp` 不被读取为证据
- 环境变量覆盖 staging 根
- 补 `@contract_rule("EVD-SINK-002/003/004")` 落点

（Spec 04 已用临时脚本 `verify_sinks_spec04.py` 验证过 61/61，本轮转为正式测试文件。）

### 阶段 C — baseline comparator（两仓）

新建 `tests/contracts/test_test_baseline.py`，实现 FND-REG-001~004：

- 读 `config/contracts/known-test-baseline.json`
- 分组：Existing PASS / SKIP / known-fingerprint / New Contract tests
- fingerprint 算法（Appendix E.1）：
  `sha256(json.dumps({nodeid, exception_type, symbolic_failure_locus, normalized_error_signature, scope, baseline_commit}, sort_keys=True, separators=(",",":"), ensure_ascii=False))`
- Wiki：三条 `stats.collector` 已知失败精确 allow；Coding：无 allowlist
- 意外 PASS（known failure 变 PASS）→ 报告不静默删除

### 阶段 D — 项目规则落点补全（两仓）

- `test_foundation_mapping.py` 加 `@contract_rule("FND-MAP-001/002")`
- `test_business_invariance.py` 加 `@contract_rule("FND-MODE-004")`
- 项目测试 import `agent_core.contracts.conformance.rules.contract_rule`（不 import 其它 shared 内部）

### 阶段 E — coverage assertions（可选，读 Registry）

新增 conformance 侧 helper：读 `producer-registry.json`，断言每个 IN_SCOPE producer 的
每个 stage 在 wiring 测试里有落点（不写死 stage 名）。

### 阶段 F — bundle 同步 + 验证 + 提交

1. 全量 conformance + `tests/contracts` 两仓跑绿。
2. bundle 同步 shared 改动到 Coding（hash 一致）。
3. 账本追加事件、提交。

## 4. 验收对照（Spec 09 Acceptance Criteria）

- [ ] 每条 v0.1 payload Rule 至少一个落点（conformance 或项目测试）
- [ ] 所有 in-scope producer/stage 至少一个 wiring test（Spec 07/08 已满足，阶段 E 验证）
- [ ] 所有新增测试 100% PASS
- [ ] Wiki 三条 known failure 只在 baseline comparator 精确 allow；Coding 无 allowlist
- [ ] shared payload 测试文件在两仓 hash 一致

## 5. 决策记录（已确认）

1. **执行分批**：核心四段一次做完（采纳）—— 阶段 A–D，阶段 E（coverage assertions）留待需要时。
2. **规则 metadata 落点**：`rules.py` 加 `RULE_REGISTRY`（采纳）—— 79 条 statement，descriptor 的
   `normative_rule_set` 保持 68 条不变、不扩 schema、不改 payload 语义。
3. **deferral 处理**：6 条 defer 给后续 Spec（采纳）—— `EVD-PUB-002/003/004/006/007`（Spec 12/14）、
   `FND-PKG-003`（Spec 10），用 `DEFERRED_PAYLOAD_RULES` 白名单显式登记。

## 6. 执行结果

**阶段 A（规则 metadata + traceability）**
- `conformance/rules.py` 加 `RULE_REGISTRY`（79 条 statement）+ `DEFERRED_PAYLOAD_RULES`（6 条）
  + `rule_statement()` / `registered_rule_ids()`。
- 新建 `conformance/test_traceability.py`（6 例）：descriptor 全覆盖 statement、无孤儿引用、
  conformance 只引用 payload 规则、payload 规则落点 = conformance + 项目声明 + deferral。

**阶段 B（sink 文件行为测试）**
- 两仓新建 `tests/contracts/test_evidence_sink.py`（各 7 例）：合法写入 / 原子 replace / 并发 8 条 /
  残留 `.tmp` 不被读作证据 / 5 类非法 ID / 注入 I/O 失败 / 超限（模型层）/ 环境变量覆盖。
- 补 `@contract_rule("EVD-SINK-004")` 落点。

**阶段 C（baseline comparator）**
- 两仓新建 `tests/contracts/test_test_baseline.py`（各 10 例）：逐字节复现 Appendix E.2 三条 anchor
  指纹、指纹的顺序/无关字段不变性、回归分类（`ALLOWED_BASELINE_FAILURE` / `FINGERPRINT_MISMATCH` /
  `NEW_FAILURE` / `BASELINE_PASS_NOW_FAIL` / `SKIP_REGRESSION` / `RESOLVED_UNEXPECTEDLY`）、
  本仓 baseline 自洽。补 `FND-REG-001/002/003` 落点。

**阶段 D（项目规则落点）**
- 两仓 `test_foundation_mapping.py` 补 `FND-MAP-001` / `FND-MAP-002` / `FND-MODE-004` /
  `EVD-SINK-002` / `EVD-SINK-003` 落点（`@contract_rule` 装饰器）。

**闭环**：payload 68 条 = conformance 56 条落点 + 项目 6 条（`PROJECT_SCOPED_RULES`）+ deferral 6 条。

## 7. ⚠️ deviation（1 个文件，两仓）：sink 并发写竞态修复

`**/adapters/foundation/evidence_sink.py` 不在 Spec 09 的 Allowed Changes 内，但必须修一处**真实缺陷**：

- `_within`（Wiki）/ `_escapes`（Coding）用 `Path.resolve()` 做防目录穿越检查。
- `Path.resolve()` 对**尚未 mkdir 的目录**在 Windows 并发下有竞态，令合法的并发写入偶发被误判为
  「逃出 staging 根」而拒绝（实测 30~50 轮里 2~3 次失败），**违反 EVD-SINK-004「concurrent-writer safe」**。
- **最小修复**：改用 `os.path.abspath`（纯词法规范化，不访问文件系统、不解析 symlink）。防穿越能力
  不变（`run_id`/`event_id` 已由形状校验排除 `..` / `/` / `:`）。实测修复后 50 轮并发 0 失败。

这是 Spec 09 的 sink 并发测试**暴露**的 Spec 04 遗留缺陷，与 Spec 07/08 的缺陷修复同类。

## 8. 验收对照（Spec 09 Acceptance Criteria）

- [x] 每条 v0.1 payload Rule 至少一个落点（56 conformance + 6 项目 + 6 deferral = 68）
- [x] 所有 in-scope producer/stage 至少一个 wiring test（Spec 07/08 已满足）
- [x] 所有新增测试 100% PASS（conformance 224；两仓 contracts 全绿）
- [x] Wiki 三条 known failure 只在 baseline comparator 精确 allow；Coding 无 allowlist
- [x] shared payload 测试文件在两仓 hash 一致（payload `sha256:df479f0c…`，40 文件）

## 9. 回滚 / Handoff

项目 tests 各自回退；shared conformance 改动用 canonical 回退 + bundle 重同步。
Handoff 列出 Rule coverage、producer stage coverage、fixture 来源与仍未形成的 L2/L3 事实。

