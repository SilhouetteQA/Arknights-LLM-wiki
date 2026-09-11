# Spec 04 执行计划 — Evidence Contract and Project-local Sinks

> 依赖：Spec 02、03 `COMPLETE`（账本已 11 条事件，03 终态 COMPLETE）
> Candidate Phase：pre-A（`candidate_commit` 必须保持 `null`）
> 目标仓：共享 DTO/Protocol/Schema 在 **Wiki canonical → bundle → Coding mirror**；sink 实现各自项目本地

## 1. 目标

把 Evidence 从"能记录 Usage/Cost"推进到"**能作为可校验、可发布、可跨仓对齐的证据**"：

- 共享层：`FoundationObservation`、`EvidenceRecord`、`EvidenceSink` Protocol、两类 Schema、可发布 DTO 的 allowlist/容量基础
- 项目本地：Wiki 与 Coding **各自独立**的 `FileEvidenceSink`
- 硬边界：**共享 DTO/Protocol ≠ 共享 I/O 实现**；**sink failure ≠ 业务 failure**；**partial `.tmp` ≠ 有效证据**

## 2. 文件清单

### 2.1 Allowed Changes（规范已列）

| 路径 | 类型 | 内容 |
|---|---|---|
| `agent_core/contracts/enums/evidence.py` | NEW | `ValidationStatus` / `EvidenceRepository` / fact key 允许前缀等封闭值域 |
| `agent_core/contracts/models/evidence.py` | NEW | `FoundationObservation`、`EvidenceRecord`、容量常量（64 KiB）、ID 校验器 |
| `agent_core/contracts/protocols/__init__.py` | NEW | 子包 docstring（与 `enums/`、`models/` 同风格，不 re-export） |
| `agent_core/contracts/protocols/evidence_sink.py` | NEW | 窄 `EvidenceSink` Protocol + `SinkFailure` 上报形状 |
| `agent_core/contracts/conformance/test_evidence.py` | NEW | DTO/Protocol/不变量/容量/扫描的共享一致性测试 |
| `agent_core/contracts/schemas/foundation-observation.schema.json` | NEW | 由 Pydantic 派生 |
| `agent_core/contracts/schemas/evidence-record.schema.json` | NEW | 由 Pydantic 派生 |
| `agent_core/contracts/contract.md` | M | 新增 Evidence 章节 + `EVD-*` 规则索引；更新规则总数 |
| `agent_core/contracts/payload-descriptor.json` | M | 重新生成：6 类 schema、更新 `schema_set_hash` 与 `normative_rule_set` |
| `WIKI_REPO/arknights_wiki/adapters/foundation/__init__.py` | NEW | 项目本地 Adapter 子包 |
| `WIKI_REPO/arknights_wiki/adapters/foundation/evidence_sink.py` | NEW | Wiki 的 `FileEvidenceSink` |
| `CODING_REPO/adapters/foundation/__init__.py` | NEW | 同上（Coding 侧） |
| `CODING_REPO/adapters/foundation/evidence_sink.py` | NEW | Coding 的 `FileEvidenceSink` |

### 2.2 Spec deviation（1 个文件，已批准并执行）

`agent_core/contracts/tooling/generate_schemas.py` **不在 Allowed Changes 内，但必须修改**，否则：

1. `SCHEMA_REGISTRY` 只有 4 条 → 两类新 Schema 无法生成、`schema_hashes` 与 `schema_set_hash` 不完整，
   与母 Spec §3.1 的六类清单、Spec 04 步骤 9 冲突；
2. `_RULE_LINE_PREFIX = "| FND-"` 只捞 `FND-*` → `contract.md` 新增的 `EVD-*` 规则**不会进入**
   `payload-descriptor.json` 的 `normative_rule_set`，EVD 规则失去 traceability 入口。

已批准的 deviation（**只改这两处，不重构**，2026-09-11 经用户确认）：

```diff
 SCHEMA_REGISTRY = (
     ...
+    ("FoundationObservation", "agent_core.contracts.models.evidence", "FoundationObservation",
+     "foundation-observation.schema.json"),
+    ("EvidenceRecord", "agent_core.contracts.models.evidence", "EvidenceRecord",
+     "evidence-record.schema.json"),
 )
-_RULE_LINE_PREFIX: Final[str] = "| FND-"
+_RULE_LINE_PREFIXES: Final[tuple[str, ...]] = ("| FND-", "| EVD-")
```

`version.py` **不需要改**：64 KiB 常量放在 `models/evidence.py`（`version.py` 不在 Allowed Changes）。
`conformance/rules.py` **不需要改**：`RULE_ID_PATTERN` 已是通用 `<FAMILY>-<SUBDOMAIN>-<NNN>`，
其 docstring 本就以 `EVD-PUB-004` 为例。

## 3. 关键设计决策

### 3.1 `FoundationObservation`

```yaml
usage: Usage | null
cost: Cost | null
cost_summary: CostSummary | null
```

- `model_validator(mode="after")`：三者至少一项非空，否则拒绝（不是"全空的合法 zero"）
- 它是**跨边界 DTO**，不是业务 `Result`：不得成为任何业务函数返回值，也不得继承 `BaseException`
- `extra="forbid"`（继承 `FoundationModel`）

### 3.2 `EvidenceRecord`

字段严格按母 Spec §4.6，逐项校验：

| 字段 | 校验 |
|---|---|
| `event_id` | canonical UUID（8-4-4-4-12 hex）或 ULID（26 位 Crockford base32）；统一规范化为小写存储 |
| `run_id` | `^[A-Za-z0-9_-]+$`（母 Spec §4.6）；缺失/含 `/`、`\`、`..`、`:` 一律拒绝 |
| `repository` | 封闭枚举 `wiki` / `coding` |
| `repository_commit` | 40 位小写 hex |
| `producer_id` / `mapping_stage` | 非空；形状校验（小写字母数字与 `._-`） |
| `contract_mode` | 复用既有 `ContractMode`，但**只允许 `observe` / `strict`**（`off` 不产出证据） |
| `contract_version` / `contract_payload_hash` | 非空；后者 `sha256:` + 64 hex |
| `timestamp` | RFC3339（带时区偏移） |
| `validation_status` | `PASS` / `FAIL` |
| `sanitized_input_facts` | 见 3.3 |
| `foundation_output` / `error_envelope` | 见 3.4 |

**ID 不得参与路径拼接**：模型层只做"字符集合法"校验；`FileEvidenceSink` 在落盘前**再**用
同一套校验把 `event_id` 作为文件名（`<event_id>.json`），并断言解析出的目标路径仍在
staging 根之下（防目录穿越）。两处校验互为冗余，坏 ID 无法到达文件系统。

### 3.3 `sanitized_input_facts` 的约束（**待确认**）

基线约束（无论选哪种都实现）：

- 必填 mapping；值为递归 `JsonValue`（复用 `models/base.py` 的 `JsonValue` 与校验器）
- key 形状 `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`（与 Extension Boundary 同形）
- 复用既有敏感防线：敏感 key 命中**硬拒绝**；内容启发式命中**告警并计数**
- 键总数上限与整记录 64 KiB 共同构成容量边界

**待确认**的是"allowlist"的强度（见 §8 决策 2）。

### 3.4 状态不变量（母 Spec §4.6 / D.4）

```text
PASS → foundation_output 存在 AND error_envelope 为 null
FAIL → error_envelope 存在；foundation_output 可空
```

用 `model_validator(mode="after")` 实现，两个方向都强制：`PASS` 缺 output 拒绝、
`FAIL` 缺 error 拒绝、`PASS` 带 error 拒绝、`FAIL` 带 output 允许。

### 3.5 容量口径

- 计量对象：**整个 `EvidenceRecord` 的 canonical JSON UTF-8 字节数**（`ensure_ascii=False`，
  无尾随换行），上限 **64 KiB**
- 复用 `models/base.canonical_json_dumps`（唯一实现），在 `model_validator(mode="after")` 末尾计算
- 超限抛 `foundation.evidence_record_too_large` 形态的校验错误；**流式截断不是选项**

### 3.6 `EvidenceSink` Protocol（窄接口）

```python
class EvidenceSink(Protocol):
    def emit(self, record: EvidenceRecord) -> None: ...
```

- 只定义行为边界，**不定义目录、命名、rotation、cleanup**（母 Spec §4.7 明文）
- 无法持久化时必须显式抛 `SinkFailure`（携带 `evidence.sink_write_failed` 基础设施 code），
  不得静默丢弃；`SinkFailure` 与 Foundation semantic `ErrorEnvelope` **是不同类型**，互不继承
- Protocol 内不含任何 I/O 代码；共享层不得出现 `FileEvidenceSink`（Forbidden Changes）

### 3.7 两个 `FileEvidenceSink`（各自独立实现）

两仓各自实现，**不共享代码**，但行为契约一致：

```text
resolve dir: AGENT_CONTRACT_EVIDENCE_DIR，缺省 output/contract-validation/staging
path:        <dir>/<run_id>/events/<event_id>.json
写入:        canonical serialize → 同目录 <event_id>.json.tmp → flush + fsync + close
             → os.replace(.tmp, .json)
文件名:      正式文件只用 .json；.tmp 是过程态，绝不被读取
```

- `run_id` 同样做路径安全校验（防穿越），与 `event_id` 同级
- 失败处理：**结构化应用日志 + 进程内 failure counter**，使用
  `evidence.sink_write_failed` / `evidence.invalid_run_id` / `evidence.artifact_unavailable`；
  **绝不**在 I/O 失败时递归再调同一个 sink
- observe 模式下 sink 失败**不得**改变业务返回；失败只令该 run 的证据失效（Spec 09 的 smoke closure 验证）

### 3.8 可发布 DTO 基础（Spec 04 步骤 8）

只定义**基础**，让 Spec 10 的 publisher 不需要再改共享模型：

- 发布 artifact 枚举（`run-manifest.json` / `contract-manifest.json` / `evidence-manifest.json` /
  `validation-report.md` / `rule-traceability.json` / `sanitized-replay-corpus.jsonl`）
- 命名 `REPRODUCTION_RESTRICTED` 状态（`EVD-PUB-005`）
- 容量/JSON/UTF-8 约束的形状声明
- **allowlist extraction 而非 denylist**：只在契约层声明"发布必须由显式 allowlist 构造"，
  具体扫描器实现留给 Spec 10（本步骤不写 publisher）

## 4. 执行顺序

1. `enums/evidence.py` → 2. `models/evidence.py` → 3. 冒烟自测（DTO 不变量、容量、ID）
4. `protocols/{__init__,evidence_sink}.py` → 5. `conformance/test_evidence.py`
6. `contract.md` 新增 Evidence 章节与 `EVD-*` 索引
7. **deviation**：`generate_schemas.py` 两处最小修改 → `--write` 重新生成 2 个 Schema 与 descriptor
8. 两仓项目本地 `adapters/foundation/{__init__,evidence_sink}.py`
9. 临时脚本验证 sink（合法写入 / 原子 replace / 非法 ID / 超限 / 注入 I/O 失败）
10. `bundle create` → `apply --expect-payload-hash` 重新同步 Coding mirror
11. 跑 Spec 04 三条官方验证命令 + 全量 conformance + 跨平台 hash 复核

## 5. 验证命令（Spec 04 官方）

```powershell
python -m pytest agent_core/contracts/conformance/test_evidence.py -q
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
```

## 6. 验收对照

- [x] Shared payload 不 import 任一项目（`test_shared_payload_does_not_import_any_project`：
      AST 扫描全部 payload 文件，禁止 `arknights_wiki` / `adapters` / `benchmark` / `scripts` / `tools`）
- [x] 合法并发事件不互相覆盖，`event_id` 唯一（sink 以 `event_id` 为文件名 + `os.replace` 原子落盘；
      并发 8 条实测全部落盘且无重复）
- [x] `.tmp` 不被读取为证据（`iter_published_events` 只认 `.json`；`has_residual_temp_files`
      可识别残留，残留即令 Gate 失败）
- [x] observe sink failure 不改变注入的业务返回；该 run 明确失效（sink 只抛 `SinkFailure`
      并递增 `sink_failure_count`，不触碰业务返回；observe 下的吞并处理属 Spec 05/06/09）
- [x] 所有敏感 / 非 JSON / 超限 record 被拒绝（敏感 key 硬拒、`Decimal`/datetime 拒绝、
      64 KiB 与键数上限拒绝）
- [x] 更新后双仓 Payload Hash 重新一致（四路一致，见 §8.2）

## 7. 回滚 / Handoff

关闭尚未接线的 sink 并删除两处项目本地实现即可；共享 Evidence payload 变更**必须**
经 Wiki canonical 回退 + bundle 重同步，不能只回退一仓。

Handoff 记录：Schema 与 hash、最大 event size（64 KiB）、失败诊断方式
（`evidence.*` code + counter）、两个 sink 的原子写验证结果。

## 8. 决策记录与执行结果

### 8.1 已确认决策（2026-09-11）

| 决策点 | 结论 |
|---|---|
| `generate_schemas.py` 不在 Allowed Changes | **接受最小 deviation**（§2.2 两处），已在 plan 登记 |
| `sanitized_input_facts` allowlist 强度 | **命名空间 + 敏感扫描 + 键数上限**：不设固定键白名单，避免后续 Spec 05/06 每加一个 fact 就动契约 |
| sink 行为测试落点 | **临时脚本 + handoff 记录**，不新增 `tests/contracts/test_evidence_sink.py`（属 Spec 09） |
| 实施节奏 | 直接实施 |

补充的两条实现判断（无需 deviation）：

- `evidence.*` 诊断码放进 `enums/evidence.py`（Allowed Changes 内），不动 `enums/errors.py`；
  该文件的模块 docstring 本就预留了"`evidence.*` 由 Spec 04 定义其常量"。
- 未新增 `foundation.*` 错误码：记录级校验失败以 pydantic 校验错误表达，其到
  `ErrorEnvelope` 的映射属 Adapter 层（Spec 05/06/09），避免在 Spec 04 提前固化错误码闭集。
- `arknights_wiki/adapters/` 与 `adapters/` 采用隐式命名空间包（无 `__init__.py`），
  与母 Spec §3.2 的文件清单及 Spec 04 的 Allowed Changes 逐字一致；已实测可正常导入。

### 8.2 执行结果

**契约身份（两仓 × 双平台四路一致）**

| 身份 | 值 |
|---|---|
| `payload_hash` | `sha256:45da9d663ea565a4ed99085057b759d80972b5082c56c8b6c7ada65b53c3d854` |
| `descriptor_hash` | `sha256:5780138f1f6a1254010ad1d77ae0b63e3e7cd741415b17884c53babc41fa7fc4` |
| `schema_set_hash` | `sha256:d785d52d0f6ed9fcfcdf4186b506a7e5af882167567a72f17da90d54f33cc596` |
| `file_count` | 39（Spec 03 为 32） |
| transport `archive_hash` | `sha256:29aadfd3645d6430bdcb9f5c5aba8a98fec200704bb1737aeeb1caf832d5ab01` |

Schema 由 4 类增至 **6 类**（母 Spec §3.1 全集）；`normative_rule_set` 由 54 条增至 **68 条**
（新增 14 条 `EVD-*`）。

**验证**

| 项目 | 结果 |
|---|---|
| `pytest conformance/test_evidence.py` | **24 passed** |
| `generate_schemas --check` | OK |
| `verify_payload` | OK（两仓） |
| 全量 conformance（Windows） | **218 passed**（Spec 03 为 194） |
| 全量 conformance（Linux 容器） | **218 passed** |
| 规则覆盖 | **56/68**，无孤儿引用 |
| 项目 sink 行为验证（临时脚本） | **61/61 passed**（两仓各 30 项 + 环境变量一致性） |

**规则覆盖缺口（12 条，全部有明确落点，非遗漏）**

```text
FND-MAP-001/002    Spec 05/06 Adapter 映射
FND-MODE-004       Spec 09 invariance harness
FND-PKG-003        Spec 10 clean wheel smoke
EVD-SINK-002/003   Spec 09 项目 invariance / smoke closure
EVD-SINK-004       Spec 09 文件发布原子性与并发测试（共享层无 I/O）
EVD-PUB-002/003    Spec 10/14 脱敏与 secret 扫描
EVD-PUB-004/006/007 Spec 12/14 语料、manifest 绑定与保留决策
```

### 8.3 Handoff

- **最大 event size**：64 KiB（canonical JSON UTF-8，无尾随换行）；
  `sanitized_input_facts` 键数上限 64。
- **失败诊断方式**：`evidence.sink_write_failed` / `evidence.invalid_run_id` /
  `evidence.artifact_unavailable` 三个基础设施码，写结构化应用日志（`extra` 字段）
  并递增 sink 实例的 `sink_failure_count`；Smoke Gate 要求该计数为 0。
- **两个 sink 的原子写验证**：合法写入 → 正式 `.json` 存在且无 `.tmp`；并发 8 条互不覆盖；
  `.tmp` 不被 `iter_published_events` 读取；注入 `os.replace` 失败 → 抛 `SinkFailure`
  且计数 +1、无正式文件。两仓行为逐项一致（各自独立实现，源码不共享）。
- **环境限制（非契约缺陷）**：本机沙箱禁止删除文件（`unlink` / `rmtree` 被 fail-closed 拦截），
  因此注入失败后的 `.tmp` **清理**无法在本环境验证；契约层面正确的行为已被验证 ——
  残留 `.tmp` 会被 `has_residual_temp_files` 识别，Smoke Gate 因此失败。
  `bundle apply` 同理留下 `.agent-core-bundle.{incoming,previous}`，已手工清理。
- **Coding 镜像**：由 verified bundle 原子提升，39 文件，两仓 payload 逐字节一致；
  无本地修补。
