# 双旗舰 Agent Foundation Contract Master Spec

> 日期：2026-09-10  
> 状态：`APPROVED_FOR_DOCUMENTATION`  
> 适用仓库：Arknights LLM Wiki、Knowledge-Augmented Autonomous Coding Agent  
> Contract Set 目标版本：`0.1.0`  
> 当前执行边界：只批准文档，不代表已实施 Contract v0.1

## 0. Document Contract

### 0.1 规格深度随证据成熟度变化

本规格采用以下三种深度，后续执行者不得把它们混为一谈：

```text
Part I  — IMPLEMENTATION-READY
Part II — FEEDBACK-BOUND
Part III — GATE-DEFINED
```

- `[NORMATIVE]`：规范性约束，违反即为 Contract Defect。
- `[IMPLEMENTATION-READY]`：可以按本规格直接实施；若仓库事实与本文不一致，必须停止并报告。
- `[FEEDBACK-BOUND]`：只批准演进流程，不批准任何预设的未来语义变更。
- `[GATE-DEFINED]`：只定义进入条件和验收门禁；门禁满足前不得开始实现。
- `[DEFERRED]`：已发现但本轮明确延期，不是遗漏。
- `[NON-NORMATIVE NOTE]`：解释性信息，不单独构成实现授权。

执行授权：

```text
Part I:
MAY implement exactly as specified.

Part II:
MAY implement process/tooling only.
Contract semantic changes require new L2/L3 evidence.

Part III:
MUST NOT begin implementation solely because it appears in this document.
Every family must satisfy its entry gate first.
```

本轮文档工作本身的边界：

```text
本轮产出 = Master Spec + CONTEXT.md + 两份 ADR
本轮产出 ≠ 创建 agent_core/contracts
本轮产出 ≠ 修改 Adapter 或业务代码
本轮产出 ≠ 执行 Contract v0.1 Cycle
```

### 0.2 规范性载体与冲突处理

Contract Payload 由职责不同但地位平等的规范性载体共同定义：

| 载体 | 规范职责 |
|---|---|
| Pydantic v2 Models / StrEnum | 数据形状、序列化和结构性不变量 |
| `typing.Protocol` | 行为能力和调用签名 |
| `contract.md` | 类型系统无法完整表达的语义、禁止项和状态关系 |
| Shared Conformance Tests | 对规范规则的可执行证明 |
| Generated JSON Schema | Pydantic 自动生成的受控机器快照 |
| `payload-descriptor.json` | 版本、工具链、Schema 和 Rule ID 的机器目录 |

`changelog.md` 仅解释历史，不是规范性载体，不进入 Contract Payload Hash。

任何规范性载体相互矛盾时，不存在“代码优先”“测试优先”或“文档优先”：

```text
NORMATIVE CONFLICT
→ CONTRACT_CONFLICT
→ release INVALID
→ Cycle cannot COMPLETE
```

修复必须先确认正确语义，再同步修改全部相关载体、重新生成 Schema、重跑共享测试和双仓验证。

### 0.3 术语与规则编号

统一术语以仓库根目录 `CONTEXT.md` 为准。规范规则编号格式为：

```text
<FAMILY>-<SUBDOMAIN>-<NNN>
```

示例：`FND-USAGE-001`、`FND-COST-001`、`EVD-SINK-001`。编号发布后永不复用；废弃规则保留编号并标记 `DEPRECATED`。

共享测试必须使用机器可读 metadata 关联 Rule ID，例如：

```python
@contract_rule("FND-COST-001")
def test_unknown_cost_is_not_zero():
    ...
```

测试函数名只是人类可读信息，不能代替 Rule ID。

### 0.4 仓库角色与真相源

Phase 1：

| 角色 | 仓库 |
|---|---|
| Canonical contract authoring | Arknights LLM Wiki |
| Contract mirror consumer | Knowledge-Augmented Autonomous Coding Agent |
| Cross-repository coordinator | Arknights LLM Wiki |
| Final cycle truth source | Arknights LLM Wiki |

Phase 1 两仓分别携带完全相同的 `agent_core.contracts` 本地镜像，但不存在独立 `agent-core` distribution。Coding 仓不得局部修补公共镜像；接入反馈必须回到 Wiki canonical payload 形成新版本，再重新同步。

Phase 2 只有在对应契约族通过抽取门禁后，canonical ownership 才可以迁移到独立 `agent-core` 仓库。

### 0.5 与原路线文档的关系

`06_双旗舰Agent_统一工程化路线.md` 是方向性输入。本规格对其进行以下约束性收敛：

- “共享 Agent Engineering Layer”不等于立即共享实现。
- 第一阶段统一契约、证据和门禁，不抽公共运行时。
- Foundation 先行，Model、Tool、Observability、Evaluation、Checkpoint 不搭便车进入 v0.1。
- 契约族独立成熟、独立抽取；`agent_core` 可以长期只包含部分契约族。

### 0.6 配套决策记录

- [Foundation Contract 子 Spec 执行索引](foundation-contract/00-execution-index.md)
- [ADR-0001：渐进式契约族抽取](../adr/0001-progressive-contract-family-extraction.md)
- [ADR-0002：Foundation 事实语义与旁路治理](../adr/0002-foundation-fact-semantics-and-shadow-governance.md)
- [统一领域语言](../../CONTEXT.md)

ADR 只解释长期架构选择及其取舍。Producer Registry、Rule Registry、文件级修改清单、执行命令、Evidence Schema、failure fingerprint 和 A/B/C 操作步骤以本 Master Spec 为唯一实施依据。

### 0.7 Child Spec Execution Projection Model

本 Master Spec 是规范真相源；`docs/specs/foundation-contract/01-18` 是各工作单元的执行投影；`00-execution-index.md` 只维护静态依赖、初始状态和导航。

```text
Master Spec
= Normative Source of Truth

Child Spec
= Operationally self-contained execution projection

00 Index
= Static dependency and authority coordinator

execution-status-events.jsonl
= Sole dynamic execution-status source
```

子 Spec 可以完整描述本单元的目标文件、当前行为、修改步骤、保留逻辑、测试、命令、产物、验收、停止条件和回滚，但不得重新定义 Foundation Schema、Rule、Producer、A/B/C 身份或版本政策。冲突处理：

```text
Child contradicts Master
→ SPEC_CONFLICT
→ STOP without modifying code

Required fact absent from Child but defined by Master
→ follow explicit Master reference

Required semantic fact absent from both
→ SPEC_INCOMPLETE
→ STOP; do not invent contract behavior
```

所有子 Spec 仅由 Wiki canonical 仓维护。Coding 可以在 Evidence 中引用 Spec ID，但 MUST NOT 保存子 Spec、DAG 或状态摘要的 shadow copy。

每份子 Spec 声明静态 `Initial Status` 和 `Current Status Source`。它不保存动态 Current Status；当前状态由 Appendix I 定义的空账本 genesis 与 append-only 状态事件确定性归约得到。文档存在不等于工程工作完成。

Spec 11 是冻结边界：

```text
Specs 01–10
→ MAY implement or modify Candidate code, validation tooling and workflows

Spec 11
→ freeze Candidate A
→ formally rerun L1 and full regression on exact A

Specs 12–13
→ execution only against A

Spec 14
→ Evidence-only publication B

Spec 15
→ fixed A/B coordination and Wiki-only Finalization C
```

越过 Spec 11 后不得新增或修改 replay runner、sanitizer、smoke harness、coverage/invariance comparator、Evidence publisher、coordinator、cycle-report generator、status reducer 或 workflow。发现缺陷时 Candidate A 进入 `SUPERSEDED`，回到对应前置子 Spec形成新 A2并重新取证。
- 实际语义差异由 Adapter 表达，不为了接口外观抹平不同状态机。

## 1. Current System Baseline

### 1.1 仓库快照

| 仓库 | 路径 | 已核验 HEAD | Python |
|---|---|---|---|
| Wiki | `D:\AI project\Arknights LLM Wiki` | `838ba4c1440ece174da845f900428075f16cf05b` | `>=3.12` |
| Coding | `D:\AI project\Knowledge-Augmented Autonomous Coding Agent` | `08a8275c91872a934f66a9db38fc30cf608c690d` | `>=3.12` |

环境中两仓当前均解析到 Pydantic `2.13.4`，但都没有把它作为 Foundation 的直接、精确锁定依赖。v0.1 必须显式固定 `pydantic==2.13.4`；升级 Pydantic 本身属于显式 contract/tooling change。

两仓当前均没有 `.github/workflows`。Local Contract Gate 与 Coordination Gate 是 Part I 的新建内容，不得在规格中假设已有 CI 基础设施。

### 1.2 包装基线

Wiki 当前 `pyproject.toml` 仅发现 `arknights_wiki*`，不会自动把未来的 `agent_core*` 放入 wheel。Coding 当前没有显式 package discovery。只验证仓库根目录可 import 不足以证明安装后的命名空间存在。

v0.1 packaging smoke 必须执行：

```text
build wheel
→ install into clean environment
→ import agent_core.contracts
→ import Usage / Cost / CostSummary / ErrorEnvelope / CONTRACT_VERSION
→ read packaged schemas through importlib.resources
```

### 1.3 测试基线

唯一权威完整命令：

```powershell
# Wiki
python -m pytest tests/

# Coding
python -m pytest tests/
```

不得使用 Wiki 仓库根目录的裸 `pytest` 作为权威门禁；它会额外收集 `output/` 历史归档和脚本测试。

已核验结果：

| 仓库 | PASS | SKIP | 已知失败 | 门禁状态 |
|---|---:|---:|---:|---|
| Wiki | 542 | 7 | 3 | `PASS_WITH_KNOWN_BASELINE_FAILURES` |
| Coding | 381 | 13 | 0 | `PASS` |

Wiki 已知失败注册表初值：

| nodeid | exception type | normalized error signature | scope |
|---|---|---|---|
| `tests/test_stats_collector.py::TestStatsCollectorContent::test_collect_content_reads_db` | `AttributeError` | `story collection received list where object with get was expected` | `DEFERRED` |
| `tests/test_stats_collector.py::TestStatsCollectorSnapshot::test_finish_writes_jsonl_line` | `AttributeError` | `story collection received list where object with get was expected` | `DEFERRED` |
| `tests/test_stats_collector.py::TestStatsCollectorSnapshot::test_finish_resets_state` | `AttributeError` | `story collection received list where object with get was expected` | `DEFERRED` |

三项失败共同根因是 `arknights_wiki.stats.collector._get_raw_data` 读取真实 story JSON 时假定顶层为对象，实际遇到列表。它属于离线 Stats 范围，本规格不得顺手修复。

回归判定按 nodeid、baseline status 和规范化失败指纹，不按总数：

```text
baseline PASS → FAIL          = FAIL
baseline PASS → SKIP          = FAIL unless explicitly approved
known nodeid + same fingerprint = ALLOWED_BASELINE_FAILURE
known nodeid + changed fingerprint = FAIL
new failing nodeid            = FAIL
known failure unexpectedly PASS = REVIEW_REQUIRED
```

意外转为 PASS 不立即令 Cycle 失败，但必须调查环境、依赖或旁路是否意外影响 Deferred 路径；当前 Cycle 不得静默删除原基线记录。

### 1.4 Benchmark 基线限制

Wiki 存在历史 100 题 direct 报告，总分 `0.857`，但当前 runner 默认引用的 `benchmarks/arknights_bench/questions.jsonl` 已不存在，只保留 draft 和历史结果，因此状态为：

```text
BENCHMARK_BASELINE_NOT_REPRODUCIBLE
```

Coding 当前有 5 个真实案例，历史 Docker 运行结果为 `20% (1/5)`；历史记录显示单 case 曾消耗 1–5M prompt tokens、耗时 341–1665 秒，且当前代码已演进、本地缺少对应原始 report snapshot，因此状态为：

```text
BENCHMARK_REPRODUCTION_RESTRICTED
```

以上历史数值只能作为 `Historical Quality Reference`，`gate_effect=NONE`，不得声明为当前 baseline 或参与 Cycle PASS/FAIL。

### 1.5 当前 Usage/Cost 语义缺口

Wiki：

- Agent 和 Eval 在 usage 缺失时经常把 token 默认成 `0`。
- `pricing.json` 中当前有数值的模型均标记 `estimate=true`。
- 未知价格或 `tbd` 由 Legacy 计算成 `0.0`。
- Eval cost log 与报告使用 CNY；现有 Langfuse、Dashboard、cost log 和报告必须保持不变。

Coding：

- `agent/llm.py` 获得 provider usage 后累计 prompt/completion token。
- `tools/tracing.py` 将 `cost_usd=0.0` 写入 Langfuse。
- `benchmark/runner.py` 的价格表为空，未知模型成本返回 `0.0`。
- `tools/report_trace.py` 的 SDK 路径也会形成默认 `cost_usd=0.0`。

这些 `0` 混合了真实零值与缺失信息，是 Foundation v0.1 要观察并消歧的核心问题。

# Part I — Foundation v0.1 / Cycle 1

## 2. Scope and Architecture [IMPLEMENTATION-READY]

### 2.1 目标

v0.1 验证：

> 统一的 Foundation 事实语义能否在不改变两个既有系统业务行为的前提下，映射当前 Agent、Trace 和 Evaluation 主链路的真实 Usage/Cost 数据，并形成可复现、可发布、可跨仓协调的证据。

最小垂直切片：

```text
Foundation Contract
→ Presence-aware Legacy Facts
→ Repository-local Adapter
→ Real Usage/Cost Producers
→ Staging Evidence
→ L1/L2/L3 Validation
→ Cross-repository Cycle Gate
```

### 2.2 v0.1 正式范围

进入 `CYCLING`：

- Lockstep versioning、Payload Descriptor、Schema Manifest。
- Extension Boundary。
- `Usage`、`Cost`、`CostSummary`。
- 最小 `ErrorEnvelope`。
- `ContractMode`。
- `FoundationObservation`、`EvidenceRecord`、`EvidenceSink Protocol`。
- Shared Conformance Tests、canonicalization、payload verification。

保持 `EXPERIMENTAL`，不得接入正式业务边界：

- ModelRequest / ModelResult。
- ToolSpec / ToolResult。
- 完整 Observability / Trace 契约。
- 完整 Evaluation Result 契约。
- Checkpoint 数据或状态机。

### 2.3 非目标与禁止项

v0.1 不做：

- 不创建独立 `agent-core` distribution。
- 不统一 Model Provider 实现、重试、熔断或模型选择。
- 不统一 Wiki retrieval、memory、KG、LangGraph state。
- 不统一 Coding sandbox、approval、GitHub、tool dispatch。
- 不修改现有 Dashboard、报告格式、评分、判定或路由。
- 不做 FX conversion。
- 不迁移历史 artifact 原文件。
- 不把 Foundation 对象转换回 Legacy 后驱动主路径。
- 不合并 Wiki 三个 `_log_cost` 为统一成本服务。
- 不为双仓对称性虚构不存在的 Wiki TraceSummary。

### 2.4 主路径不变量

```text
                 ┌→ Legacy Business Path → Existing Result
Input ───────────┤
                 └→ Foundation Adapter → Validation Evidence
```

Foundation consumer 只能观察，不能影响：

- 模型调用、模型选择或路由。
- Evaluation score、Benchmark resolution 或 pass/fail。
- 现有 cost calculation、cost log、Trace、Dashboard 和 report。
- 重试、异常传播、恢复或审批。
- 文件、数据库、Git、网络等既有副作用。

允许为了 observation seam、presence facts 和可测试性进行行为保持型局部重构；不允许扩大契约治理范围或让 Foundation 成为主路径。

## 3. Phase 1 Package and File Layout [IMPLEMENTATION-READY]

### 3.1 两仓完全相同的 Contract Payload

两个仓库都应得到以下镜像，内容逐字节规范化后完全一致：

```text
agent_core/
├── __init__.py
└── contracts/
    ├── __init__.py
    ├── version.py
    ├── contract.md
    ├── payload-descriptor.json
    ├── enums/
    │   ├── __init__.py
    │   ├── modes.py
    │   ├── sources.py
    │   ├── errors.py
    │   └── evidence.py
    ├── models/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── usage.py
    │   ├── cost.py
    │   ├── error.py
    │   └── evidence.py
    ├── protocols/
    │   ├── __init__.py
    │   └── evidence_sink.py
    ├── conformance/
    │   ├── __init__.py
    │   ├── rules.py
    │   ├── test_usage.py
    │   ├── test_cost.py
    │   ├── test_cost_summary.py
    │   ├── test_extensions.py
    │   ├── test_error_envelope.py
    │   ├── test_evidence.py
    │   ├── test_modes.py
    │   └── test_versioning.py
    ├── schemas/
    │   ├── usage.schema.json
    │   ├── cost.schema.json
    │   ├── cost-summary.schema.json
    │   ├── error-envelope.schema.json
    │   ├── foundation-observation.schema.json
    │   └── evidence-record.schema.json
    └── tooling/
        ├── __init__.py
        ├── canonical_json.py
        ├── generate_schemas.py
        ├── verify_payload.py
        └── bundle.py
```

`agent_core/__init__.py` 只能包含 namespace docstring，不得 re-export `Cost` 等类型。稳定 import 必须使用 `agent_core.contracts...`。

Phase 1 `agent_core/` 白名单只有：

```text
agent_core/__init__.py
agent_core/contracts/**
```

出现 provider client、retry、checkpoint、Adapter、领域模型、配置或项目状态代码时 Local Contract Gate 直接失败。

### 3.2 项目本地 Adapter 与验证文件

Wiki：

```text
arknights_wiki/adapters/
└── foundation/
    ├── __init__.py
    ├── facts.py
    ├── mapping.py
    ├── runtime.py
    └── evidence_sink.py

config/contracts/
├── producer-registry.json
├── known-test-baseline.json
├── smoke-v0.1.json
└── replay-v0.1.json

scripts/contracts/
├── validate_local.py
├── replay_history.py
├── publish_evidence.py
├── coordinate_cycle.py
├── finalize_cycle.py
└── status_ledger.py

tests/contracts/
├── test_foundation_mapping.py
├── test_evidence_sink.py
├── test_producer_wiring.py
├── test_business_invariance.py
├── test_test_baseline.py
└── test_packaging.py
```

Coding：

```text
adapters/
└── foundation/
    ├── __init__.py
    ├── facts.py
    ├── mapping.py
    ├── runtime.py
    ├── observation_ledger.py
    └── evidence_sink.py

config/contracts/
├── producer-registry.json
├── known-test-baseline.json
├── smoke-v0.1.json
└── replay-v0.1.json

scripts/contracts/
├── validate_local.py
├── replay_history.py
└── publish_evidence.py

tests/contracts/
├── test_foundation_mapping.py
├── test_evidence_sink.py
├── test_producer_wiring.py
├── test_business_invariance.py
├── test_test_baseline.py
└── test_packaging.py
```

项目文件不进入 Contract Payload Hash，可以不同；其职责是证明各自能符合共同契约。

### 3.3 Packaging 修改

Wiki `pyproject.toml`：

- 增加明确 `[build-system]`。
- 主依赖增加 `pydantic==2.13.4`。
- package discovery 从仅 `arknights_wiki*` 扩展为 `arknights_wiki*` 与 `agent_core*`。
- 将 `contract.md`、descriptor 和 `schemas/*.json` 注册为 package data。

Coding `pyproject.toml`：

- 主依赖增加 `pydantic==2.13.4`。
- 显式发现当前项目 packages、`adapters*` 与 `agent_core*`，不得依赖 cwd import 巧合。
- 将同一批 Contract Payload 非 Python 文件注册为 package data。

两仓 package discovery 配置不要求逐字相同，但干净安装后的 import path 和 payload 必须相同。

### 3.4 Phase 2 防双份 namespace 预留门禁

本节只是 v0.1 的前置约束，不授权 Phase 2：

```text
local mirror OFF
public agent-core dependency ON
```

二者不得同时存在。未来迁移必须检查 `agent_core.__file__` 来源、删除本地 mirror、移除本地 packaging include，再安装固定版本依赖。

## 4. Foundation v0.1 Data Contract [IMPLEMENTATION-READY]

所有 Pydantic 模型默认：

```python
model_config = ConfigDict(extra="forbid")
```

跨边界 JSON 使用 UTF-8；`Decimal` 序列化为十进制字符串，禁止 JSON float 作为金额输入。内部构造可以使用 `Decimal`，Legacy float 必须经 `Decimal(str(value))` 转换。

### 4.1 ContractMode

```python
class ContractMode(StrEnum):
    OFF = "off"
    OBSERVE = "observe"
    STRICT = "strict"
```

唯一配置入口：`AGENT_CONTRACT_MODE`。非法值必须明确报配置错误，不得静默当作 `off`。

### 4.2 Usage

```yaml
Usage:
  input_tokens: int | null
  output_tokens: int | null
  total_tokens: int | null
  cache_read_tokens: int | null
  cache_write_tokens: int | null
  source: provider_reported | locally_calculated | estimated | unknown
  extensions: dict[str, JsonValue]
```

不变量：

- 所有非空 token 字段均为非负整数。
- `0` 表示明确观察到零；`null` 表示未知或未报告。
- provider 返回的 `total_tokens` 原样保留，即使与 input/output 之和不同也不改写。
- provider 未返回 `total_tokens` 时保持 `null`，Adapter 禁止自动相加。
- object-level `source` 描述已填充字段的共同来源；缺失字段为 `null`，不会单独降低来源等级。
- v0.1 不做 per-field provenance；真实路径出现混合来源需求时只能由 L2/L3 驱动 v0.2。

### 4.3 Cost

```yaml
Cost:
  amount: Decimal-string | null
  currency: string | null
  source: provider_reported | price_table | estimated | unknown
  pricing_version: string | null
  extensions: dict[str, JsonValue]
```

不变量：

- 已知 `amount` 必须 `>= 0` 且 `currency` 必须存在。
- `currency` 采用大写三字母 ISO 格式校验，不使用封闭 Enum。
- `source=unknown` 时 `amount=null`。
- `source=price_table` 时 `pricing_version` 必填。
- `amount=0` 只表示有 presence/provenance 证明的真实零成本。
- Contract 层不做汇率换算或默认币种替换。
- `CostSource` 描述认识论可信来源，不只是价格存储位置。

### 4.4 CostSummary

```yaml
CostSummary:
  known_amount: Decimal-string | null
  currency: string | null
  complete: bool
  component_count: int
  known_component_count: int
  unknown_component_count: int
  extensions: dict[str, JsonValue]
```

不变量：

```text
all counts >= 0
component_count = known_component_count + unknown_component_count
complete = (unknown_component_count == 0)
```

- `known_component_count=0` 时 `known_amount=null`。
- `known_component_count>0` 时 `known_amount>=0` 且 `currency` 非空。
- 真实零成本属于 known component。
- 所有非空 currency 必须一致；已知金额 USD 与未知金额 CNY 仍然是 `CurrencyMismatch`。
- currency 缺失本身不产生 mismatch，但对应未知金额仍令 summary incomplete。
- 空集合固定为 `0/0/0/null/null/complete=true`。
- Summary 不声明统一 `source` 或 `pricing_version`。
- 币种兼容性必须先于完整性计算；冲突显式失败，不能返回伪造的 `complete=false` 混合金额。

### 4.5 ErrorEnvelope

```yaml
ErrorEnvelope:
  category: validation | compatibility | aggregation
  code: string
  message: string
  retryable: bool
  extensions: dict[str, JsonValue]
```

v0.1 Foundation codes：

```text
foundation.invalid_usage
foundation.invalid_cost
foundation.invalid_cost_summary
foundation.schema_version_mismatch
foundation.currency_mismatch
```

机器逻辑只允许依据 `code`，禁止解析 `message`。以上错误均固定 `retryable=false`。

`ErrorEnvelope` 是边界 DTO，不是异常类型，不得：

- `raise ErrorEnvelope` 或 `except ErrorEnvelope`。
- 替换仓库现有异常类、传播、重试和恢复逻辑。
- 成为内部 `Result[T, ErrorEnvelope]` 通用返回模式。

仅在序列化、API/IPC、MCP、跨仓 Adapter 或 Evaluation artifact 边界，由 Adapter 将内部错误映射为 Envelope。`cause_code` 延期，只有 Cycle 1 真实反馈证明需要时才可进入 v0.2。

Evidence infrastructure 使用独立机器码：

```text
evidence.sink_write_failed
evidence.invalid_run_id
evidence.artifact_unavailable
```

sink 无法写入时不能递归使用同一个 sink 记录失败，最后防线是结构化应用日志和进程内计数。

### 4.6 FoundationObservation 与 EvidenceRecord

单次 Producer 可能同时形成 Usage 和 Cost，因此 Evidence 不使用含糊的任意 dict。定义：

```yaml
FoundationObservation:
  usage: Usage | null
  cost: Cost | null
  cost_summary: CostSummary | null
```

至少一项必须存在。

```yaml
EvidenceRecord:
  event_id: UUID-string
  run_id: string
  repository: wiki | coding
  repository_commit: 40-hex string
  producer_id: string
  mapping_stage: string
  contract_mode: observe | strict
  contract_version: string
  contract_payload_hash: sha256-string
  timestamp: RFC3339 string
  validation_status: PASS | FAIL
  sanitized_input_facts: dict[str, JsonValue]
  foundation_output: FoundationObservation | null
  error_envelope: ErrorEnvelope | null
```

状态不变量：

```text
PASS → foundation_output exists AND error_envelope is null
FAIL → error_envelope exists; foundation_output may be null
```

`run_id` 仅允许 `[A-Za-z0-9_-]+`；`event_id` 使用 UUID，不允许任一标识直接携带 `/`、`\`、`..` 或 `:` 参与路径构造。单个 EvidenceRecord 的 canonical JSON UTF-8 大小不得超过 64 KiB。

### 4.7 EvidenceSink Protocol

```python
class EvidenceSink(Protocol):
    def emit(self, record: EvidenceRecord) -> None: ...
```

Protocol 只定义行为边界，不定义目录、命名、rotation 或 cleanup。符合实现必须接收合法记录；无法持久化时显式报告失败，不能静默丢弃。

## 5. Extension Boundary [IMPLEMENTATION-READY]

`extensions` 是受限逃生口，不是第二套自由 Schema。

合法 key 格式：

```text
^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$
```

允许首段：

```text
wiki
coding
provider
adapter
```

`foundation` 与 `shared` 保留，项目 Adapter 禁止写入。provider/adapter ID 也必须满足小写字母、数字和下划线规范。

值类型为递归 JSON：

```python
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
```

禁止 `Decimal`、datetime、Path、bytes、Exception、Pydantic 实例、dataclass 或任意 Python object。时间等内容必须由 Adapter 转成稳定 JSON 表达。

容量与深度：

- 对 `extensions` 做 canonical JSON UTF-8 序列化后不得超过 16 KiB。
- `extensions` 根映射不计层；extension value 的第一层 container 记作 depth 1；最大 depth 为 4。

敏感内容禁止进入：

- raw prompt、完整 response、reasoning、traceback。
- credentials、Authorization、access token、cookie、password、secret、API key。
- 未脱敏本机绝对路径、代码正文、diff 或完整 provider payload。

实现必须同时使用结构校验和 best-effort 敏感 key/content scanner，但 scanner 只是辅助防线。Evidence/Extension 生产者承担不写入敏感内容的首要责任。

Foundation 对 `wiki.*`、`coding.*`、`provider.*`、`adapter.*` 全部保持语义不透明，只能存储、序列化、传播或统计 key；不得基于它们改变 Cost、Usage 或其他规范行为。

连续两个 Cycle 被双仓共同使用只产生 `PROMOTION_CANDIDATE`，是否晋升还需判断语义是否相同、是否稳定、能否定义不变量以及是否长期存在。

## 6. Presence-aware Mapping Contract [IMPLEMENTATION-READY]

总原则：

```text
Foundation mapping
= value + presence + provenance + pricing evidence

Legacy normalized value ≠ Foundation fact
```

项目内部 `LegacyUsageFacts` / `LegacyCostFacts` 不进入公共 Contract Payload。两仓可以使用不同内部结构，但至少必须表达：

```text
usage_object_present
field_presence
provider_cost_present
provider_cost_currency_present
call_observed
price_entry_present
pricing_value_present
price_entry_complete
pricing_is_estimate
legacy_amount
currency_context
model
```

Facts extractor 自身禁止使用 `getattr(..., 0)` 抹去 presence。

### 6.1 Usage 映射

| Legacy/Provider facts | Foundation |
|---|---|
| usage object absent | token fields `null`，`source=unknown` |
| usage object present，字段明确为 0 | 对应字段 `0`，`source=provider_reported` |
| usage object present，字段缺失 | 对应字段 `null` |
| Wiki 按响应字符估算 | input `null`，output 为估算 N，total `null`，`source=estimated` |
| provider total present | 精确保留 |
| provider total absent | `null`，禁止自动相加 |

未来若需要 `input=provider_reported`、`output=estimated` 等混合 provenance，必须由真实 L2/L3 证据驱动 v0.2；v0.1 不预设 per-field source。

### 6.2 Cost 映射

| Pricing facts | Foundation |
|---|---|
| price entry absent | `amount=null`、`source=unknown`、保留币种上下文 |
| price 为 `null/tbd` | 同上 |
| price entry 有效且 `estimate=true` | 已知 Decimal amount、`source=estimated`、记录 pricing snapshot hash |
| price entry 有效且确认价格 | 已知 Decimal amount、`source=price_table`、`pricing_version` 必填 |
| provider 明确报告货币成本 | `source=provider_reported` |
| 只有 legacy amount `0.0` | 不足以证明真实零成本 |

Wiki pricing snapshot version：对整个 `pricing.json` 做 canonical JSON、sorted keys、compact UTF-8 后计算 SHA256。不能使用 mtime、Python dict repr 或 Git 时间戳。

### 6.3 Summary 映射

正确关系：

```text
Legacy components ─→ Legacy aggregation ─→ unchanged legacy result
        │
        └→ provenance facts ─→ Foundation Cost components ─→ CostSummary
```

禁止从 `legacy total=0.0` 反推组成项、完整性或真实零成本。 malformed legacy record 可以继续按旧逻辑跳过，但 `observe` 必须产生失败 Evidence，`strict` replay 必须失败。

## 7. In-Scope Producer Registry [IMPLEMENTATION-READY]

`producer_id` 是稳定的契约观察语义边界；`mapping_stage` 是当前实现路径，可以随实现演进，但变化必须进入 Validation Report。

项目 `config/contracts/producer-registry.json` 至少包含：

```yaml
producer_id
repository
mapping_stages
status
source_locations
foundation_objects
evidence_requirements
notes/reason
```

### 7.1 Wiki Registry

| producer_id | mapping stages | source locations | objects | status |
|---|---|---|---|---|
| `wiki.agent.llm_usage` | `chat_completion`, `intent_rewrite` | `arknights_wiki/extraction/llm_client.py`, `arknights_wiki/agent/router.py` | Usage, Cost | `IN_SCOPE` |
| `wiki.eval.cost_log` | `runner`, `judge`, `scoring` | `arknights_wiki/eval/runner.py`, `judge.py`, `scoring.py` | Usage, Cost | `IN_SCOPE` |
| `wiki.eval.cost_summary` | `cost_log_summary` | `arknights_wiki/eval/metrics.py` | CostSummary | `IN_SCOPE` |
| `wiki.trace.summary` | none | no stable online DTO; Dashboard aggregation excluded | none | `DEFERRED` |

另外登记但延期：

```text
wiki.extraction.pass1
wiki.extraction.pass2
wiki.extraction.pass3
wiki.worldbuilding_extraction
wiki.stats_collector
wiki.dashboard_cost_aggregation
```

延期原因：独立批处理生命周期、不同成本语义或会扩大本轮范围。历史样本可以参加 L2 semantic replay，但必须标记 `evidence_role=historical_replay_only` 和 `runtime_adapter_status=DEFERRED`。

### 7.2 Coding Registry

| producer_id | mapping stages | source locations | objects | status |
|---|---|---|---|---|
| `coding.agent.llm_usage` | `openai_compat` | `agent/llm.py` | Usage, Cost | `IN_SCOPE` |
| `coding.trace.generation_usage` | `langfuse_generation` | `tools/tracing.py` | Usage, Cost | `IN_SCOPE` |
| `coding.benchmark.case_cost` | `normal`, `environment_error`, `error` | `benchmark/runner.py` | CostSummary | `IN_SCOPE` |
| `coding.trace.summary` | `sdk`, `clickhouse` | `tools/report_trace.py` | Usage, CostSummary | `IN_SCOPE` |

Sandbox、Approval、GitHub、Tool envelope、Agent routing 和 Benchmark 判定/渲染全部延期。

### 7.3 分层覆盖要求

“未观察到”不等于失败，因此 Registry 必须按证据层指定覆盖策略：

| Producer | L1 Contract/Adapter Tests | L2 Historical Replay | L3 Fresh Smoke |
|---|---|---|---|
| Wiki agent usage | 所有 stage | 至少一个真实历史 stage；不足需标记 | manifest 预登记的所有 required stages |
| Wiki eval cost log | runner/judge/scoring 全部 | 所有可用历史 stage | runner/judge/scoring 全部 |
| Wiki eval summary | 正常、未知、malformed | 必须有真实 cost log | required |
| Coding agent usage | provider usage 存在/缺失/零值 | 必须有真实历史记录或标记不足 | required |
| Coding trace generation | tracing on/off、usage presence | 可用历史 trace | required |
| Coding benchmark case | normal/environment/error 全部 | 可用历史 case | `normal` required；错误 stage 可 `NOT_OBSERVED` |
| Coding trace summary | sdk/clickhouse 全部 | 可用历史 trace | `ONE_OF(sdk, clickhouse)` |

Fresh Smoke manifest 中的 `required_producer_stages` 是本次运行的闭合预期；不得因为某个 stage 未运行而在事后删除要求。新发现 Producer 默认登记并分类，不能自动扩大 v0.1 scope。

## 8. Wiki Implementation Plan [IMPLEMENTATION-READY]

### 8.1 新增项目 Adapter 层

#### `arknights_wiki/adapters/foundation/facts.py`

职责：

- 定义 Wiki 内部 `WikiLegacyUsageFacts`、`WikiLegacyCostFacts`。
- 从 OpenAI-compatible response、Eval dict 和 pricing snapshot 提取 presence-aware facts。
- 保留 provider field presence、call observed、价格项存在性与 `estimate` 标记。

禁止：

- 构造公共 Pydantic 对象。
- 写文件或调用 Langfuse。
- 用零值补齐缺失字段。

#### `arknights_wiki/adapters/foundation/mapping.py`

职责：

- facts → Usage/Cost/CostSummary。
- 将 Pydantic/聚合失败映射为稳定 ErrorEnvelope。
- 复用一个窄 helper 供三个 `_log_cost` stage 调用。

禁止接管 Legacy `compute_cost`、`summarize_cost` 或报告生成。

#### `arknights_wiki/adapters/foundation/runtime.py`

职责：

- 解析 `AGENT_CONTRACT_MODE`。
- 使用同一 Adapter 执行 `off/observe/strict` policy。
- 创建 EvidenceRecord 并调用注入的 EvidenceSink。
- 维护不可递归的 sink failure counter。

#### `arknights_wiki/adapters/foundation/evidence_sink.py`

职责：项目本地 `FileEvidenceSink`。输出到 `output/contract-validation/staging/<run_id>/events/<event_id>.json`，采用同目录临时文件、flush/close、`os.replace` 原子发布。

### 8.2 `arknights_wiki/extraction/llm_client.py`

目标函数：`chat_completion`。

当前行为：统一 Agent LLM 调用，创建客户端，执行既有 resilience retry，返回 `(content, message)`；只有 Langfuse 开启时才提取 usage 并调用 `record_llm_usage`。

v0.1 修改：

1. 模型调用成功后，从原始 response 提取 field presence，不再把 usage extraction 完全包在 Langfuse 条件内。
2. 调用 Wiki facts extractor 和旁路 runtime，stage=`chat_completion`。
3. 现有 Langfuse 条件、`record_llm_usage` 参数、retry metadata 和返回值保持不变。

必须保持：

- `_get_model_config`、client 创建、timeout/retry/backoff 和 breaker 配置。
- provider 请求参数与调用次数。
- message/content 解析和返回顺序。
- Langfuse 未启用时仍不初始化 client、不写旧 Trace。

### 8.3 `arknights_wiki/agent/router.py`

目标函数：`_llm_intent_rewrite`。

v0.1 修改：response 成功后先提取 presence-aware facts，再 stage=`intent_rewrite` 旁路观察；旧 `is_enabled()` 条件内的 `record_llm_usage` 行为保持不变。

必须保持：

- 本地意图识别和 fallback 逻辑。
- retry、异常捕获和返回 `None` 的既有控制流。
- entity/hallucination 过滤。
- prompt、temperature、max_tokens 和路由结果。

### 8.4 Wiki Eval cost-log producers

目标：

- `arknights_wiki/eval/runner.py::_log_cost`
- `arknights_wiki/eval/judge.py::_log_cost`
- `arknights_wiki/eval/scoring.py::_log_cost`

每个函数仍然独立存在。允许调用同一个窄 `observe_eval_cost_entry(...)` helper，但 helper 只做：

```text
allowlisted legacy entry
→ facts extraction
→ Foundation mapping
→ Evidence emit
```

修改顺序：

1. 按旧逻辑构造或补充 timestamp。
2. 在实际写入前复制白名单 facts，按 runner/judge/scoring stage 旁路观察。
3. 使用原 entry、原路径、原 JSON 序列化和原 append 行为写入。

不得改变 cost log 字段、时间格式、文件位置、写入次数、异常行为或 Eval 结果。

映射差异：

- runner 的 Agent 响应字符估算：`input_tokens=null`、`output_tokens=N`、`source=estimated`。
- judge/scoring 的 provider usage：按字段 presence 映射为 `provider_reported`。
- 当前 pricing entry 为 `estimate=true` 时，Cost source 必须是 `estimated`。

### 8.5 `arknights_wiki/eval/metrics.py`

目标函数：`summarize_cost`。

当前行为：逐行读取 JSONL，跳过 malformed JSON，将 cost 转 float，累计 total 和 step 汇总。

v0.1 修改：在同一次逐行读取中并行收集 component facts；旧 total/steps 继续使用原算法和原 rounding。旧结果完全形成后，再产生 Foundation CostSummary Evidence。

必须保持：

- 缺文件返回 `{"total": 0.0, "steps": {}}`。
- malformed JSON 对 Legacy 结果继续跳过。
- step key、count、rounding 和返回 dict 不变。

Foundation 旁路中，malformed JSON 必须形成失败 evidence；不能因为 Legacy 跳过就宣称 Summary complete。

### 8.6 Wiki 明确不修改的现有文件

除非实施审计发现上述接线无法完成并先停止报告，否则 v0.1 不修改：

- `arknights_wiki/eval/report.py`。
- `arknights_wiki/observability/dashboard.py`。
- `arknights_wiki/stats/collector.py`。
- extraction orchestrators 和 worldbuilding producers。
- retrieval、memory、KG、checkpoint 和业务状态。

## 9. Coding Implementation Plan [IMPLEMENTATION-READY]

### 9.1 新增项目 Adapter 层

`adapters/foundation/facts.py` 与 `mapping.py` 承担 Coding presence facts 和 Foundation mapping；`runtime.py`、`evidence_sink.py` 的策略与 Wiki 相同但实现独立。

`observation_ledger.py` 是仅在项目内使用的 client-local sidecar ledger：

- 记录当前 LLM client 在 observe/strict 模式下产生的最小 Usage/Cost facts。
- Benchmark 通过开始/结束 cursor 取得本 case 的组成项。
- 不设计跨仓或全局 invocation ID。
- 不做 Evidence 去重，不改变 `tokens_total`。
- `off` 模式不创建或积累 ledger 数据。

### 9.2 `agent/llm.py`

目标函数：`OpenAICompatClient.chat`。

当前行为：构造 provider 请求；response 有 usage 时把 prompt/completion 强制转 int，累加 `tokens_total`，再调用 `record_usage(..., 0.0)`；最后构造 `LLMMessage`。

v0.1 修改：

1. provider response 返回后、Legacy coercion 前提取 usage object 和各字段 presence。
2. stage=`openai_compat` 旁路生成 Usage/未知 USD Cost Evidence。
3. 同一 facts 写入 client-local observation ledger，供 benchmark case summary 使用。
4. 继续执行原 `tokens_total` 和 `record_usage` 逻辑。

必须保持：

- provider 配置、timeout/max_retries、请求 messages/tools。
- `tokens_total` 的既有数值和累加条件。
- `_parse_tool_call`、reasoning_content 回放语义和 `LLMMessage` 返回。
- usage 缺失时 Legacy 仍不调用 `record_usage`。

可在存在安全稳定的当前调用 ID 时，把它写入受限 `coding.*` extension；不得为 v0.1 新设计全局 correlation ID。

### 9.3 `tools/tracing.py`

目标函数：`record_usage`。

增加一个只供旁路使用的 keyword-only `contract_facts` 参数；它不得合并进 Langfuse `extra` 或旧 metadata。调用方未传时保持兼容。

执行顺序：

1. 若 mode 不是 off 且存在 contract facts，stage=`langfuse_generation` 执行同一 mapping。
2. 再按旧逻辑调用 `get_client()`。
3. client 不存在时继续原样 no-op。
4. client 存在时使用原 usage/cost/meta 写入。

这使 Foundation Evidence 不依赖 Langfuse 是否开启，同时保持旧 Trace 完全不变。

### 9.4 `benchmark/runner.py`

目标函数：`_run_one_case`、`_environment_error_result`、`_case_result` 及异常 CaseResult 分支。

每个分支必须先按旧逻辑形成完整 `CaseResult`，然后调用统一 case observation helper：

- `normal`：使用本 case ledger slice 形成 Cost components 和 CostSummary。
- `environment_error`：若 Agent 未执行且 ledger slice 为空，形成空 Summary，`complete=true`、currency null。
- `error`：若已发生模型调用，按 ledger 中真实 components 形成 incomplete Summary；无调用则为空 Summary。

必须保持：

- repository setup、sandbox、baseline test、Agent execution 和 judge 顺序。
- resolution、test_pass、patch_acceptance 和 consistency 判定。
- `CaseResult.cost_usd` 的 Legacy 值，即使仍为 `0.0`。
- 单 case 异常不终止其他 case 的控制流。

Foundation 不能参与 Benchmark pass/fail，也不能用 Evidence 修正 `CaseResult`。

### 9.5 `tools/report_trace.py`

目标函数：`_summarize_trace`、`_summarize_events`。

两个路径都在原始 observation/row 仍可见时收集 presence facts，先形成旧 `TraceSummary`，再旁路 emit：

- SDK stage：缺少实际 cost 字段时，旧 `cost_usd=0.0` 映射为未知，不是真零。
- ClickHouse stage：在 `_as_float` 前区分 `total_cost` 缺失与显式零；各 generation/row 形成 component provenance。

必须保持：

- SDK 优先、ClickHouse fallback 的既有 `fetch_trace` 控制流。
- TraceError 语义。
- latency span 计算、tool/error/retry/test 汇总。
- TraceSummary 字段和 report Markdown/JSON 渲染。

### 9.6 Coding 明确不修改的行为

- `benchmark/report.py` 的格式与指标。
- Agent 路由、Tool dispatch、review 和 retry。
- Sandbox、Git、GitHub、Approval 与 push/PR 安全边界。
- Benchmark case、gold patch、judge prompt 和 resolution definition。

## 10. Contract Mode and Rollback [IMPLEMENTATION-READY]

三个模式必须共用同一 facts extractor、Adapter 和 validation 逻辑，只改变失败 policy：

```text
OFF
→ skip facts/adaptation/evidence entirely

OBSERVE
→ adapt and validate
→ emit PASS/FAIL evidence
→ mapping/sink failure does not affect business

STRICT
→ use same path
→ emit evidence
→ any contract failure fails validation command
```

`observe` 不是 fallback；不存在 Foundation primary path。Evidence sink 写失败时：

```text
structured application log
+ in-memory sink_failure_count
→ business continues in observe
→ current run invalid for Evidence Gate
```

即时运行时回滚：

```text
AGENT_CONTRACT_MODE=off
```

代码回滚点是 Candidate A 中各 Producer 的旁路调用和项目 Adapter 层；由于 Legacy 从未消费 Foundation 输出，删除这些调用即可恢复仓库内原实现。不得用“Foundation 失败后回退 Legacy”的双主路径描述回滚。

## 11. Evidence Runtime and Publication [IMPLEMENTATION-READY]

### 11.1 Staging Evidence

默认目录：

```text
output/contract-validation/staging/<run_id>/events/<event_id>.json
```

配置：

```text
AGENT_CONTRACT_EVIDENCE_DIR
AGENT_CONTRACT_RUN_ID
```

Controlled Smoke、Replay 和 strict validation 必须显式提供 run_id；普通本地 observe 未提供时可以生成进程级 UUID。`staging` 只表示尚未发布聚合，仍然禁止原始 Prompt、response、trace、代码和凭据。

原子写入：

```text
canonical serialize
→ <event_id>.json.tmp in same directory
→ flush and close
→ os.replace
→ <event_id>.json
```

发布工具只读取 `.json`，忽略 `.tmp`。任何残留 `.tmp` 都令 Smoke Evidence Gate 失败。

两仓 `.gitignore` 必须明确加入：

```text
/output/contract-validation/staging/
```

### 11.2 闭合 Smoke Run 校验

Smoke harness 必须验证：

- 显式 run_id 与 run manifest 一致。
- observed `(producer_id, mapping_stage)` 满足预登记 required set。
- 所有 event 的 repository、repository_commit、contract version、payload hash 一致。
- 所有 event mode 为 `observe`。
- event_id 无重复。
- 没有 `.tmp` 残留。
- `sink_failure_count == 0`。
- 没有未映射错误或被拒绝的 EvidenceRecord。

一条成功事件或目录非空不构成有效 Smoke 证据。

### 11.3 Evidence Publication Boundary

发布必须采用 allowlist extraction：

```text
controlled business/historical source
→ minimal staging facts
→ construct new publishable Evidence DTO
→ validate and scan
→ hash
→ release snapshot
```

不得采用“序列化原始对象后删除已知敏感字段”的 denylist 做法。

允许进入 Evidence Publication Commit B：

```text
run-manifest.json
contract-manifest.json
evidence-manifest.json
validation-report.md
rule-traceability.json
sanitized-replay-corpus.jsonl
```

最终 `cycle-report.json/.md` 只在 Wiki Finalization C 写入。

`sanitized-replay-corpus.jsonl` 是契约输入语料，不是原始日志副本。每条只保留 record_id、source_class、最小 legacy usage/cost facts、expected mapping、actual mapping 和 sanitized record hash。公开 artifact 不提交 raw prompt hash；需要私下关联原始记录时可以在受控环境使用带私钥 HMAC，但 key 和 raw digest 不进入 Git。

### 11.4 发布扫描

发布前机器检查：

- secret pattern 与 forbidden field。
- `prompt`、`response_body`、`reasoning`、`traceback`、`authorization` 等禁止 key。
- Windows/Linux 绝对路径。
- 单 record/单 artifact 容量。
- UTF-8、BOM 和换行。
- JSON Schema。

run manifest 只记录净化命令；secret、临时目录和私人路径替换为 `<SECRET>`、`<WORKSPACE>`、`<REDACTED>`。

### 11.5 Raw Business Evidence 生命周期

原始 Trace 或受限业务记录只能位于受控临时环境，不进入上述 staging 目录。默认策略：Cycle COMPLETE 且 publishable evidence 验证完成后删除。确需保留时必须有显式 retention decision、负责人、位置和到期日。

证据状态至少支持：

```text
VERIFIED
PARTIALLY_OBSERVED
NOT_OBSERVED
NOT_APPLICABLE
LEGACY_DATA_INSUFFICIENT
REPRODUCIBLE
PARTIALLY_REPRODUCIBLE
REPRODUCTION_RESTRICTED
CONFLICT
FAIL
```

`REPRODUCTION_RESTRICTED` 表示结论有真实证据支持，但完整复现依赖不可发布数据或受限环境；它不是 FAIL，也不能伪报为完全可复现。

## 12. Payload, Schema and Version Integrity [IMPLEMENTATION-READY]

### 12.1 Payload Descriptor

`agent_core/contracts/payload-descriptor.json` 在总 Payload Hash 之前生成，至少包含：

```json
{
  "contract_version": "0.1.0",
  "canonicalization_version": "1",
  "pydantic_version": "2.13.4",
  "families": ["foundation"],
  "schema_hashes": {
    "Usage": "sha256:...",
    "Cost": "sha256:...",
    "CostSummary": "sha256:...",
    "ErrorEnvelope": "sha256:...",
    "FoundationObservation": "sha256:...",
    "EvidenceRecord": "sha256:..."
  },
  "normative_rule_set": ["FND-USAGE-001", "..."]
}
```

治理状态 `EXPERIMENTAL/CYCLING/ELIGIBLE/...` 不进入 descriptor；成熟度变化不改变契约身份。

### 12.2 生成顺序

```text
1. 从 Pydantic 重新生成 JSON Schema 到临时目录
2. canonicalize schemas
3. 计算各 schema hash
4. 生成 payload-descriptor.json
5. 校验 descriptor 与实际文件、Rule ID 和 Schema 一致
6. canonicalize 整个 Contract Payload
7. 计算 contract_payload_hash
8. 计算 payload_descriptor_hash 和 schema_set_hash
9. 在 Payload 外生成 contract-manifest.json
10. Evidence Manifest 引用 contract_payload_hash
```

CI 只能把临时生成的 Schema 与已提交 snapshot 比较，不能自动覆盖工作区。

### 12.3 Schema canonicalization

```python
canonical = json.dumps(
    schema,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
)
```

UTF-8 编码后计算 SHA256。`contract_version` 与 schema hash 是独立概念。

`schema_set_hash` 对按 schema ID 排序后的 `schema ID + NUL + schema hash` 序列计算，用于快速诊断 Payload 差异；它不是第三套治理身份。

### 12.4 Contract Payload Hash

输入范围：

```text
agent_core/__init__.py
agent_core/contracts/**
```

其中包括 Models、Enums、Protocols、完整 `contract.md`、共享 conformance tests、generated schemas、tooling 和 descriptor。排除 `__pycache__`、`.pyc`、临时文件、mtime、permissions 和绝对路径。

canonical file bundle：

```text
normalize relative path separator to /
→ sort paths
→ UTF-8 without BOM
→ CRLF/CR to LF for text
→ canonical JSON for JSON files
→ concatenate path + NUL + content + NUL
→ SHA256
```

Python 和 Markdown 不做 AST/语义 canonicalization，只做编码和换行规范化；注释或格式变化也会改变 Payload Hash，这是镜像一致性检查的预期行为。

### 12.5 Contract Manifest

外部路径：

```text
docs/contracts/releases/0.1.0/contract-manifest.json
```

字段：

```yaml
contract_version
contract_payload_hash
payload_descriptor_hash
schema_set_hash
canonical_payload_repository: wiki
canonical_payload_commit: <Wiki Candidate A>
```

它位于所声明 Payload 外，不进入 Payload Hash。同步到 Coding 后内容保持不变；Coding Candidate/Evidence commit 只出现在 Coding Evidence Manifest 和 Cycle Report。

### 12.6 Lockstep Contract Set Versioning

Phase 1 只维护一个 Contract Set Version，不给各 family 单独 SemVer。

```text
0.1.0 → Foundation Cycle 1
0.2.0 → 真实 L2/L3 反馈导致的非文档语义修订
0.x.y → 不改变契约 Schema/不变量/映射/行为的修正
1.0.0 → 首批成熟 family 已抽入 agent-core 并承诺稳定公共 API
```

Minor bump 包括字段、Schema、不变量、序列化、映射、聚合、错误或行为语义变化，即使 Schema hash 不变也必须 bump。改变 validator 接受范围属于 minor，不是 patch。

Patch 只允许文档错字、报告/验证工具 bug、非语义日志改善，或证明 Schema 与行为完全不变的 tooling/Pydantic 修正。整个 `contract.md` 进入 Payload，因此非规范文字变化仍会改变 Payload Hash，并至少要求 patch release snapshot，不能覆盖旧版本。

硬门禁：

```text
same version + different payload/schema hash → FAIL or DIVERGED
same schema hash + changed semantics without version bump → VERSIONING_VIOLATION
Cycle completed but repo versions differ → FAIL
```

Phase 1 不维护 N-1 runtime compatibility，但每个不兼容变化必须写 migration notes。

### 12.7 镜像 bundle

Wiki 生成确定性 Contract Payload bundle；Coding 必须先解包到临时目录并验证：

- 没有意外文件。
- 预期文件完整。
- descriptor 有效。
- regenerated schemas 匹配。
- unpacked payload hash 等于 expected hash。

全部通过后才原子替换 Coding `agent_core/contracts` mirror。bundle 只是 transport，不是第三个真相源；archive hash 可以记录，但永远不等于或替代 Contract Payload Hash。

## 13. Validation Evidence Gate [IMPLEMENTATION-READY]

```text
Cycle Evidence Gate
= L1 Deterministic Contract Tests
AND L2 Historical Artifact Replay
AND L3 Fresh Real-path Smoke Run
```

### 13.1 L1 — SPEC EVIDENCE

共享 conformance tests 至少覆盖：

- Usage 缺失、显式零、负值、provider total 保留、不自动相加。
- Decimal 字符串序列化、float 拒绝、未知不等于零。
- CostSummary 空集合、全未知、真实零、部分未知、币种冲突。
- Extension namespace、JSON-only、16 KiB、depth 4 和敏感字段。
- ErrorEnvelope boundary semantics 和 retryable=false。
- EvidenceRecord PASS/FAIL 互斥、64 KiB、ID/path 安全。
- ContractMode 非法配置。
- EvidenceSink 成功写入、原子写、失败不静默。
- descriptor/schema/payload hash 确定性。

项目 Adapter tests 将各仓 facts/mapping factory 喂给共享 assertions；共享测试不得 import `arknights_wiki`、`agent`、`benchmark` 或 `tools`。

### 13.2 L2 — PRODUCTION-HISTORY EVIDENCE

从真实历史 cost log/trace/benchmark artifact 提取 allowlisted 最小记录。报告必须同时保存：

```text
observed legacy facts
expected Foundation mapping
actual Foundation mapping
source domain
runtime adapter status
evidence role
```

离线 extraction 记录可以暴露 estimated、USD、unknown price 和 legacy zero，但只能作为 replay 证据，不能证明 runtime producer 已接线。

### 13.3 L3 — CURRENT-RUNTIME EVIDENCE

必须使用：

```text
AGENT_CONTRACT_MODE=observe
```

真实运行副作用限制：

- Wiki：read/query/eval only。
- Coding：local fixture repository 或 sandbox，允许读写和本地 test；禁止 push 和 create PR。

运行前 `run-manifest.json` 预登记：

```yaml
model
provider
case_ids
required_producer_stages
expected_calls
max_calls
estimated_cost_cap
network_requirement
side_effect_policy
contract_version
payload_hash
candidate_commit
```

运行后记录 actual calls/tokens、known/unknown cost components、duration、producer coverage 和 sink failures。业务完成但 Evidence 不闭合时，业务结果保留，L3 Gate 失败。

### 13.4 Semantic Coverage Matrix

Validation Report 必须生成：

| Semantic Case | Rule ID | Contract Test | Historical | Fresh | Count | Status | Notes |
|---|---|---|---|---|---:|---|---|
| provider-reported usage | FND-USAGE-* | PASS | OBSERVED | OBSERVED | n | VERIFIED |  |
| estimated usage | FND-USAGE-* | PASS | OBSERVED | NOT_OBSERVED | n | PARTIALLY_OBSERVED |  |
| unknown cost | FND-COST-* | PASS | OBSERVED | OBSERVED | n | VERIFIED |  |
| true zero cost | FND-COST-* | PASS | NOT_OBSERVED | NOT_OBSERVED | 0 | NOT_OBSERVED | legal but absent |
| partial unknown summary | FND-CSUM-* | PASS | OBSERVED | OBSERVED | n | VERIFIED |  |

Fixture 可以证明合法性，但不能冒充 L2/L3 观察。

## 14. Deterministic Non-intrusion and Regression Gates [IMPLEMENTATION-READY]

### 14.1 BusinessInvariant

对固定输入和固定模型响应分别运行 off/observe：

```text
BusinessInvariant(observe) == BusinessInvariant(off)
```

精确比较：

1. Output：业务返回值。
2. Decision：路由、模型选择、评分和 approval 决策。
3. Side Effects：文件、数据库、Git 和外部 API 调用集合。
4. Legacy Telemetry：现有 Trace、cost log、report 内容与调用参数。

Foundation staging artifact、contract log 和 adapter metric 允许不同，不在比较对象中。

### 14.2 项目完整回归

Baseline Existing Tests、New Shared Conformance Tests、New Project Adapter Tests 分开计算：

```text
existing previously PASS → 100% remain non-failing and non-skipped
known failures → only exact registered fingerprints allowed
new conformance/adapter tests → 100% PASS
```

Wiki 预期状态：`PASS_WITH_KNOWN_BASELINE_FAILURES`。Coding 预期状态：`PASS`。新增失败零容忍。

### 14.3 Benchmark 在 Cycle 中的角色

Cycle 1/2 不使用不可复现的历史数值作为质量门禁。硬门禁是 deterministic non-intrusion；Historical Benchmark 只作为 reference：

```yaml
historical_value: ...
reproducibility: NOT_REPRODUCIBLE | REPRODUCTION_RESTRICTED
gate_effect: NONE
```

完整 live quality regression 推迟到 Foundation Family Extraction Gate，见 Part III。

## 15. CI Gates [IMPLEMENTATION-READY]

### 15.1 Level 1 — Repository Contract Gate

每仓独立运行，不 clone 或读取另一个仓库。

PR Contract Gate：

```text
payload allowlist
→ schema regeneration diff
→ descriptor/payload hash verification
→ shared conformance tests
→ project adapter/wiring/invariance tests
→ contract-related regression subset
→ evidence publication safety scan
→ clean wheel install/import/resource smoke
```

Cycle Candidate Gate 额外执行 canonical full regression 与本仓 L1/L2/L3 evidence verification。

建议权威命令接口：

```powershell
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
python -m pytest agent_core/contracts/conformance -q
python -m pytest tests/contracts -q
python scripts/contracts/validate_local.py --gate pr
python -m build
python scripts/contracts/validate_local.py --gate candidate
```

最后一条内部调用本仓 `python -m pytest tests/` 并应用已知失败指纹规则。

### 15.2 跨平台 hash job

Windows 运行完整 Contract CI；Linux 只安装最小 contract dependencies，使用同一 `canonicalization_version=1` 和同一共享实现重新生成 Schema、计算 Payload Hash 并比较 expected hash。它不宣称两个业务系统跨平台兼容。

### 15.3 Level 2 — Cross-repository Cycle Gate

Phase 1 由 Wiki workflow 承担，只读取闭合 `cycle-plan.json`，不得推断最新成功 commit 或 checkout 移动 main。私有 Coding checkout token 只读、最小权限，禁止进入日志、环境 dump、extension 或 artifact。

状态：

- `DIVERGED`：相同目标 contract version，但 Candidate Payload Hash 不同。
- `FAILED`：Evidence 缺失、commit/payload 不匹配、Local Gate/回归失败、plan 非法等。
- `PASS / READY_FOR_FINALIZATION`：两个固定 A/B 完整满足协调条件。
- `COMPLETE`：仅在合法 Wiki Finalization C 合并后成立。

Coordination 是确定性证据验证器，不调用真实模型、不产生新的 L3 Evidence。

## 16. Candidate, Evidence and Finalization Protocol [IMPLEMENTATION-READY]

### 16.1 身份模型

```text
Candidate Commit A
= what was validated

Evidence Publication Commit B
= where evidence for A was published

Evidence Manifest Hash
= what the published evidence says

Coordination identity
= which coordinator implementation verified A/B

Finalization Commit C_wiki
= canonical long-term persistence of the cross-repo result
```

拓扑：

```text
A_wiki   → B_wiki   ─┐
                      ├→ Coordination PASS → C_wiki → Cycle COMPLETE
A_coding → B_coding ─┘
```

### 16.2 Candidate A

A 包含 Contract Payload mirror、项目 Adapter、接线代码、测试与配置，不包含声称验证自身的最终 Evidence。两仓完成 Candidate 后固定 SHA，后续验证不再使用 branch name。

如果采用 PR/squash 流程，Evidence 必须绑定合并后的最终代码 SHA，而不是被替换掉的临时 PR SHA。

Candidate A 可以包含截至冻结边界已经发生的 Wiki canonical 状态事件，但这些事件不得引用包含自身的 A SHA。A 内最后一个 Spec 11 事件最多表达 `READY → IN_PROGRESS` 或 `FREEZE_BOUNDARY_REACHED`；真正绑定 A SHA 的 `CANDIDATE_FROZEN` 事件只能在 A 已存在后生成，并随 B_wiki append。

### 16.3 Evidence B

Evidence Manifest 至少包含：

```yaml
contract_version
contract_payload_hash
verified_repository_commit: Candidate A
repository
environment_allowlist
contract_tests
historical_replay
fresh_smoke
full_regression
benchmark_reference_status
producer_coverage
```

不包含：

```text
evidence_manifest_hash
evidence_commit
```

因为这两个身份只能在 manifest 生成后知道。Coordination 对 canonical manifest 计算 Evidence Manifest Hash 并写入 cycle report。

机器门禁必须同时满足：

```text
A is ancestor of B
AND diff(A, B) is subset of evidence publication allowlist
```

禁止 A→B 修改 Contract Payload、Adapter、业务代码、测试、`pyproject.toml` 或锁文件。Cycle 建议使用 `contract-cycle/<cycle_id>` 发布分支，避免无关 main 提交混入 A/B 之间。

Wiki B 还允许对 `docs/specs/foundation-contract/execution-status-events.jsonl` 进行严格 append-only 更新，记录 Spec 11 的 Candidate 绑定以及 Spec 12–14 的真实执行事实；不得修改、删除或重排 A 中已有字节。Coding B 不保存或复制该账本。

### 16.4 Cycle Plan

```json
{
  "cycle_id": "foundation-0.1.0-cycle-1",
  "target_contract_version": "0.1.0",
  "expected_contract_payload_hash": "sha256:...",
  "wiki_candidate_commit": "<A_wiki>",
  "coding_candidate_commit": "<A_coding>",
  "wiki_evidence_commit": "<B_wiki>",
  "coding_evidence_commit": "<B_coding>",
  "created_at": "<RFC3339>"
}
```

Coordination 输入闭合后不得自动寻找替代 SHA。

### 16.5 Coordination Report

报告字段至少包含：

```yaml
cycle_id
contract_version
contract_payload_hash
wiki_candidate_commit
coding_candidate_commit
wiki_evidence_commit
coding_evidence_commit
wiki_evidence_manifest_hash
coding_evidence_manifest_hash
coordination_result: PASS
cycle_state: READY_FOR_FINALIZATION
coordinator_repository
coordinator_commit
coordination_tool_version
coordination_run_id
completed_at
```

Coordination artifact 不能提前写 `Cycle COMPLETE`。

### 16.6 Wiki Finalization C

C 只允许：

```text
docs/contracts/releases/<version>/cycle-report.json
docs/contracts/releases/<version>/cycle-report.md
docs/contracts/current.json
必要的 append-only coordination index
docs/specs/foundation-contract/execution-status-events.jsonl（仅追加）
```

必须满足：

```text
B_wiki is ancestor of C_wiki
AND diff(B_wiki, C_wiki) is subset of finalization allowlist
```

`cycle-report.json` 必须与 Coordination artifact canonical JSON hash 一致；Markdown 在 UTF-8、LF 规范化后 hash 一致。C 不记录自身 SHA，不修改 B 中证据。

`current.json` 只允许保存：

```json
{
  "contract_version": "0.1.0",
  "contract_payload_hash": "sha256:...",
  "cycle_id": "foundation-0.1.0-cycle-1",
  "release_path": "docs/contracts/releases/0.1.0"
}
```

它只是指针，不是第三份 cycle manifest。

C_wiki 中账本只能追加 Spec 15 的 `COORDINATION_PASSED`、`FINALIZATION_COMPLETE` 等已有 reducer 可识别事件。状态账本不是 Cycle Report，不得包含 C 自身 SHA。

### 16.7 失败分流

| 缺陷类型 | 后续动作 |
|---|---|
| Candidate code/contract/test defect | 形成新 A2，重新完整取证 |
| Evidence publication/sanitization defect | 保留 A，旧 B append-only，形成 B2 |
| Coordinator implementation defect | 固定同一 A/B，用新 coordinator version 重验 |
| Finalization copy/allowlist defect | 固定 A/B 和 Coordination artifact，形成合法 C2 |

旧 B、旧协调结果和已存在的失败 C 不得覆盖。

## 17. Cycle 1 Execution Sequence [IMPLEMENTATION-READY]

实施必须按以下阶段推进；每一阶段都形成可检查产物和局部回滚点。

### Stage 0 — Baseline freeze

1. 记录两仓 Candidate 起点、Python/Pydantic 版本。
2. 生成 baseline test nodeid/status 文件。
3. 登记 Wiki 三个 failure fingerprints。
4. 记录 Benchmark reproducibility 限制。

退出条件：baseline artifact 可由本仓验证工具读取。

### Stage 1 — Canonical Payload in Wiki

1. 创建 `agent_core.contracts` namespace 和 Foundation models。
2. 编写 `contract.md` 规范规则与 Rule ID。
3. 编写 shared conformance tests。
4. 生成 Schema 与 descriptor。
5. 通过 Windows/Linux payload hash 验证。

退出条件：Wiki Payload 自洽，无 CONTRACT_CONFLICT。

回滚：删除未接入业务的 payload 文件，不影响 Wiki 主路径。

### Stage 2 — Mirror promotion to Coding

1. Wiki 生成 transport bundle 和 expected Payload Hash。
2. Coding 临时解包并完整验证。
3. 原子替换 Coding mirror。
4. 两仓 clean wheel import smoke。

退出条件：两仓 version、descriptor、schema set 和 Payload Hash 完全一致。

### Stage 3 — Project Adapters and sinks

1. 先实现 facts extraction 和纯 mapping。
2. 再实现 runtime mode/policy。
3. 最后实现 FileEvidenceSink 与 publication scanner。
4. 运行 shared conformance + project adapter tests。

退出条件：不接任何真实 producer 时，Adapter 能在固定 facts 上独立验证。

### Stage 4 — Producer wiring

按 Registry 逐个接入，每完成一个 stage 都执行：

```text
current behavior capture
→ add observation seam
→ fixed-response off/observe comparison
→ producer wiring test
→ update coverage record
```

禁止先一次性修改全部 producer 再定位回归。

### Stage 5 — Candidate A freeze

1. 完成所有 Payload、Adapter、producer wiring、tests、config 和 Candidate CI 定义。
2. 分别形成并固定 A_wiki/A_coding SHA。
3. 后续 L1/L2/L3、完整回归和 package smoke 必须从对应 A 的干净 checkout 执行。
4. 从本阶段起 Candidate 内容不可改变；任何 contract/code/test/config 缺陷都必须形成新 A2。

### Stage 6 — L1 and project regression

1. Shared conformance 全通过。
2. Adapter/wiring/invariance tests 全通过。
3. 两仓 canonical full test command。
4. 应用 nodeid/fingerprint gate。

### Stage 7 — L2 Historical Replay

1. 从受控历史 artifact allowlist 提取最小事实。
2. strict 模式 replay。
3. 输出 semantic mapping table、差异和未观察状态。
4. 生成 sanitized replay corpus。

### Stage 8 — L3 Fresh Smoke

1. 预先冻结 run manifest、call/cost cap 和 required stages。
2. 使用 observe 运行真实 Wiki/Coding 路径。
3. 验证业务正常完成。
4. 单独检查 staging Evidence run 闭合。
5. 不满足 Evidence 条件时 Smoke Gate 失败，但不改写业务结果。

### Stage 9 — Evidence B publication

1. 所有 Evidence Manifest 的 verified commit 必须是对应 A。
2. 只通过 allowlist 形成 B_wiki/B_coding。
3. 校验 A→B ancestry 和 diff。
4. B 不得包含引用其自身 SHA 的 cycle plan 或 manifest 字段。

### Stage 10 — Coordination and Finalization

1. 在协调系统中构造不属于 A/B Git tree 的闭合 `cycle-plan.json`，固定两个 A 和两个 B。
2. Wiki coordinator checkout 固定 A/B。
3. 校验双仓 Payload、Evidence、完整回归和状态。
4. 生成 `PASS/READY_FOR_FINALIZATION` artifact。
5. Wiki 形成 C 并校验报告 hash 与 finalization allowlist。
6. C 合并 canonical branch 后 Cycle 进入 COMPLETE。

## 18. Cycle 1 Definition of Done [IMPLEMENTATION-READY]

- [ ] Foundation Pydantic models、Enums 和 Protocol 建立。
- [ ] 所有共享模型默认 `extra=forbid`。
- [ ] JSON Schema snapshots、descriptor、schema set hash 和 Payload Hash 建立。
- [ ] 两仓 Payload Hash 一致，Pydantic 固定为 `2.13.4`。
- [ ] Shared Conformance Tests 全通过且 Rule ID 可追踪。
- [ ] Wiki 全部 in-scope producer/stage 完成旁路接线。
- [ ] Coding 全部 in-scope producer/stage 完成旁路接线。
- [ ] Deferred producer 全部在 Registry 中有理由。
- [ ] off/observe BusinessInvariant 精确一致。
- [ ] Wiki 回归状态为 `PASS_WITH_KNOWN_BASELINE_FAILURES`，无 fingerprint 漂移。
- [ ] Coding 回归状态为 `PASS`，无新增失败。
- [ ] L1、L2、L3 全部形成真实证据。
- [ ] Staging Evidence 无敏感字段、无 `.tmp`、无 sink failure。
- [ ] Validation Report 包含 semantic mappings、coverage 和 NOT_OBSERVED。
- [ ] Historical Benchmark 只作 reference，不宣称当前 PASS。
- [ ] A/B ancestry、diff allowlist 和 Evidence commit binding 全通过。
- [ ] Coordination 结果为 `PASS/READY_FOR_FINALIZATION`。
- [ ] Wiki Finalization C 合法并合并 canonical branch。
- [ ] immutable release snapshot 和 `current.json` 指针生成。

如果真实接入完全没有暴露任何问题，必须先检查垂直接入是否足够深；不得为了满足“两轮”人为制造 v0.2。

# Part II — Foundation v0.2 / Cycle 2

## 19. Real-feedback Intake [FEEDBACK-BOUND]

本部分不授权任何预设字段或 validator 修改。允许驱动契约修订的来源只有：

```text
L2 Historical Replay observed issue
L3 Fresh Real-path observed issue
```

Fixture 可以复现和验证问题，但不能独立创造 Cycle 2 需求。普通代码 bug 如果没有暴露契约演进需求，也不能包装为“真实反馈驱动的 contract change”。

真实反馈流程：

```text
Observed issue
→ immutable evidence reference
→ semantic classification
→ contract impact analysis
→ affected Rule IDs
→ migration note
→ version decision
→ v0.2 candidate payload
→ double-repo mirror promotion
→ adapter changes
→ Cycle 2 validation
```

每个 issue 必须回答：

- 哪条 L2/L3 Evidence 证明问题真实存在？
- 是数据形状、序列化、mapping、aggregation、error 还是 behavior 语义？
- 能否仅由项目 Adapter 表达？若能，不应污染公共契约。
- 是否产生 breaking risk？
- 哪些规范载体必须同步更新？
- 两仓迁移如何完成？

## 20. v0.2 Change Classification [FEEDBACK-BOUND]

符合“非纯文档型契约变化”的例子：

- 字段增删或字段语义调整。
- error taxonomy 调整。
- event/evidence 语义调整。
- versioning/compatibility 规则调整。
- Usage/Cost/CostSummary/Error/Evidence schema 或 validator 调整。

不要求 breaking change，但必须真实影响接入实现。若只是报告生成器、文档错字或验证工具 bug，按 patch 处理，不能充当 Cycle 2。

允许的 Cycle 2 状态：

```text
真实反馈充分
→ prepare Contract Set 0.2.0

真实反馈不足
→ Foundation remains CYCLING
→ no artificial schema churn
```

## 21. Cycle 2 Required Artifacts [FEEDBACK-BOUND]

候选 v0.2 必须产生新的不可变 release directory：

```text
docs/contracts/releases/0.2.0/
├── contract-manifest.json
├── changelog.md
├── migration.md
├── validation/
└── cycle-report.json/.md after finalization
```

`changelog.md` 解释变化，`migration.md` 明确旧表示如何映射到新语义，以及 `0.1 Adapter not supported by 0.2 runtime` 等兼容性事实。旧 `0.1.0` 目录禁止覆盖。

Cycle 2 重复 Part I 的双仓同步、L1/L2/L3、回归、A/B/C 与 Coordination Gate。第二轮必须包含至少一次由真实接入反馈触发、会调整双仓 Adapter 的非文档契约变化。

## 22. Cycle 2 Definition of Done [FEEDBACK-BOUND]

- [ ] 至少一个 L2/L3 issue 有不可变 Evidence reference。
- [ ] issue 分类和 contract impact review 完成。
- [ ] Contract Set version 为 `0.2.0` 或更高 minor，而不是伪 patch。
- [ ] Pydantic/Enum/Protocol/contract.md/tests/Schema/descriptor 无冲突。
- [ ] 双仓 Adapter 针对真实变化完成迁移。
- [ ] 双仓 Payload Hash 锁步。
- [ ] L1/L2/L3 与项目回归重新完成。
- [ ] 新 migration notes 足以从 0.1 迁移，不要求维护双版本运行时。
- [ ] A/B/C 无环提交和 finalization 完成。
- [ ] Foundation maturity evidence 更新，但治理状态不写入 Payload Descriptor。

# Part III — Extraction and Later Families

## 23. Foundation Family Extraction Gate [GATE-DEFINED]

Foundation 只有全部满足时才可标记 `ELIGIBLE`：

```text
cycle_1_complete
AND cycle_2_complete
AND real_feedback_revision_exists
AND wiki_regression_pass
AND coding_regression_pass
AND duplicate_implementation_evidence
AND rollback_verified
AND semantic_divergence_acceptable
AND dependency_boundary_stable
AND reproducible_quality_gate_pass
```

`semantic_divergence_acceptable` 表示差异可由 Adapter 表达，无需项目字段渗入公共契约。`dependency_boundary_stable` 表示抽取 Foundation 不迫使未成熟 family 一同进入公共包。

## 24. Benchmark Freeze and Quality Gate [GATE-DEFINED]

MUST NOT extract before a reproducible BenchmarkSpec and pre-extraction baseline are frozen.

Wiki BenchmarkSpec 至少固定：

```text
corpus hash
case IDs
reference data
runner version
judge/scoring version
model/provider
temperature/reasoning parameters
prompt/template version
aggregation rules
pre-registered quality tolerances
```

Coding BenchmarkSpec 至少固定：

```text
case set hash
repository commit/fixture state
model/provider
executor and sandbox policy
iteration limit and timeout
judge version
resolution definition
side-effect policy
pre-registered quality tolerances
```

顺序不可颠倒：

```text
BenchmarkSpec freeze
→ immutable pre-extraction baseline
→ agent-core extraction candidate
→ same-config candidate benchmark
→ comparison
```

随机 LLM 质量指标按预登记容差判断，不能事后决定容差；安全和副作用不变量零容忍，包括未经批准 push/PR、sandbox boundary violation 和 approval bypass。

若 provider、预算或环境仍无法形成完整 pre/post Evidence，Foundation 状态保持 `NOT_READY_FOR_EXTRACTION`，不得降低门禁强行抽取。

## 25. agent-core Distribution Migration [GATE-DEFINED]

MAY proceed only after Foundation is `ELIGIBLE` and the quality gate passes.

迁移目标：

```text
Phase 1:
project wheel contains local agent_core.contracts mirror

Phase 2:
pip install agent-core
provides the same agent_core.contracts import path
```

迁移门禁：

- [ ] 创建独立 distribution `agent-core`，import namespace 固定为 `agent_core`。
- [ ] 公共 package Payload Hash 与最终 Phase 1 eligible payload 一致。
- [ ] 两仓删除本地 `agent_core/contracts` mirror。
- [ ] 两仓 packaging 不再包含本地 `agent_core*`。
- [ ] 两仓增加固定 `agent-core` dependency。
- [ ] clean environment 证明 `agent_core.__file__` 来自 dependency。
- [ ] 原 `agent_core.contracts.*` imports 无需修改。
- [ ] 不存在 local/dependency 双份 namespace。
- [ ] 双仓 shared conformance、adapter、回归和 frozen benchmark 通过。
- [ ] rollback 能恢复 repo-local mirror adapter 形态。

物理移动代码不自动等于 `1.0.0`。只有首批成熟 family 正式抽取并承诺稳定公共 API 时，才发布 `agent-core 1.0.0`。

## 26. Contract Family Maturity [GATE-DEFINED]

允许状态：

```text
EXPERIMENTAL
CYCLING
ELIGIBLE
EXTRACTED
LOCAL_BY_DESIGN
DEPRECATED
```

成熟度矩阵由治理 artifact 维护，不进入 Contract Payload：

| Family | C1 | C2 | 双仓回归 | 重复度证据 | 语义分歧 | 跨族依赖 | 可回滚 | Breaking Risk | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| Foundation |  |  |  |  |  |  |  |  | `CYCLING` |
| Model |  |  |  |  |  | Foundation |  |  | `EXPERIMENTAL` |
| Tool |  |  |  |  |  | Foundation, Model |  |  | `EXPERIMENTAL` |
| Observability |  |  |  |  |  | Foundation, Model/Tool metadata |  |  | `EXPERIMENTAL` |
| Evaluation |  |  |  |  |  | Foundation, Observability |  |  | `EXPERIMENTAL` |
| Checkpoint |  |  |  |  | high expected | Foundation |  | high | `EXPERIMENTAL` |

状态变化不等于 Contract Set version 变化；只有规范性载荷改变才按版本规则 bump。

## 27. Later-family Entry Gates [GATE-DEFINED]

任何 family 在 Foundation 足够稳定前 MUST NOT 进入正式 CYCLING。

### Model

Entry evidence 必须证明两个项目确实需要共同的 ModelRequest/ModelResult 边界，并能在不统一 provider、retry、timeout 实现的情况下表达。Protocol 必须配套 timeout、cancellation、usage、structured output 和 invalid request 行为测试。

### Tool

Entry evidence 必须证明 Wiki read-only knowledge tools 与 Coding side-effect tools 的共同字段不会抹平 risk/approval/sandbox 差异。若公共接口需要项目字段才能工作，应继续 EXPERIMENTAL。

### Observability

Entry evidence 必须证明 TraceContext/Span/Event 不依赖半成熟 ModelResult 或 ToolResult；provider/project extensions 仍保持 opaque。不得为了统一 Dashboard 改变项目已有观测系统。

### Evaluation

Entry evidence 必须证明只共享 Result Envelope、run metadata 和 regression primitives，不统一 Wiki quality scores 与 Coding resolution/safety scores。Benchmark runner 与 evaluator 可以继续项目本地。

### Checkpoint

Checkpoint 最可能长期保持本地。Wiki thread/session persistence 与 Coding durable task execution、sandbox state、side-effect idempotency、approval consumption/replay safety 不应被空洞状态机抹平。

允许最终只共享 `CheckpointStore Protocol`、CheckpointId/Metadata/Error，具体数据模型与 persistence semantics 标记 `LOCAL_BY_DESIGN`。决定不抽取是合法成熟结论，不是失败。

## 28. Family Extraction Rule [GATE-DEFINED]

```text
Contract Family
→ independent Cycle 1
→ independent Cycle 2 with real feedback revision
→ Family Extraction Gate
→ ELIGIBLE
→ agent_core/<family>

Not eligible
→ repository mirror + Adapter
OR LOCAL_BY_DESIGN
```

Phase 2 的 `agent_core` 可以不完整。例如只包含 Foundation、Model 和 Observability，而 Checkpoint 长期留在两仓，属于健康架构状态。

## 29. v1.x Governance [GATE-DEFINED]

`agent-core 1.0.0` 表示：

- 至少首批抽取 family 通过各自 gate。
- 独立 package 已发布并由两仓真实依赖。
- 稳定公共 import path 和 API compatibility 开始承诺。
- 使用标准 SemVer 处理后续 breaking/feature/fix。

它不表示所有 Agent 基础设施均已共享，也不要求 Checkpoint 或领域实现进入公共包。

## 30. Implementation Control and Risk Register [IMPLEMENTATION-READY]

### 30.1 执行职责

| 职责 | Phase 1 责任边界 |
|---|---|
| Wiki contract author | 编写规范载荷、生成 bundle、处理接入反馈 |
| Wiki adapter implementer | 只接入 Wiki Registry 中的 `IN_SCOPE` producer |
| Coding adapter implementer | 只接入 Coding Registry 中的 `IN_SCOPE` producer，不修改镜像契约 |
| Local Contract CI | 证明单仓 payload、Adapter、Evidence 和回归自洽 |
| Coordination CI | 针对固定 A/B SHA 核验两仓 Cycle，不产生新 Evidence |
| Wiki finalizer | 只将协调结论和 current pointer 写入 C_wiki |

同一执行者可以承担多个角色，但不得合并其证据身份或绕过各自门禁。

### 30.2 风险与控制

| 风险 | 早期信号 | 硬控制 | 回滚/处置 |
|---|---|---|---|
| Foundation 进入主路径 | Legacy 输出开始消费 Foundation 对象 | `off == observe` 四类不变性 | 关闭 mode，移除 producer seam |
| 缺失值再次被补成零 | facts extractor 使用 `or 0`、`get(..., 0)` | presence-aware tests 与 FND-MAP 规则 | 修复 Candidate，形成 A2 并重取证 |
| `extensions` 变成自由 Schema | key 数量或体积持续增长 | namespace、16 KiB、depth 4、趋势审计 | 拒绝事件；评估晋升或删除字段 |
| 敏感内容进入 Git | artifact 出现 prompt/path/token key | allowlist DTO、发布扫描、staging ignore | 阻止 B；净化工具修复后形成 B2 |
| Windows/Linux 假分歧 | 相同文件得到不同 hash | 同一 canonicalization 实现与 Linux hash job | 修复 tooling；按缺陷类型决定 A2/B2 |
| 两仓镜像漂移 | 同版本 payload hash 不同 | bundle 验证与 `DIVERGED` 状态 | 回到 Wiki canonical revision 后重新同步 |
| Evidence 自引用 | manifest 记录其自身 commit/hash | A/B/C 无环身份规则 | 拒绝 artifact，按 publication defect 形成 B2 |
| 范围膨胀 | 新 producer 被顺手接入 | Registry 默认 `UNKNOWN`，显式分类后才接入 | 撤销越界接线，保持 `DEFERRED` |
| 测试债务掩盖新回归 | 只比较失败数量 | nodeid + normalized fingerprint | 新失败或指纹漂移直接失败 |
| 不可复现 benchmark 被误用 | 把 0.857 或 1/5 写为当前 PASS | Cycle 与 Extraction 两类门禁分离 | 标记历史 reference，不参与 Cycle 判定 |
| Phase 2 双份 namespace | local mirror 与 dependency 同时安装 | clean wheel provenance smoke | local mirror OFF 后再启用 dependency |

# Appendices

## Appendix A — Normative Rule Registry [IMPLEMENTATION-READY]

本表是 v0.1 `payload-descriptor.json.normative_rule_set` 的人类可读来源。实施时 `contract.md` 与共享 conformance metadata 必须逐项对应；未列入 descriptor 的测试不能冒充规范规则。

### A.1 Packaging and Versioning

| Rule ID | Normative statement | Minimum conformance proof |
|---|---|---|
| FND-PKG-001 | Phase 1 `agent_core` MUST only contain root `__init__.py` and `contracts/**`. | allowlist tree test |
| FND-PKG-002 | Project Adapter MUST NOT reside under `agent_core`. | import/tree test |
| FND-PKG-003 | Built project distributions MUST expose `agent_core.contracts` and packaged schemas. | clean wheel smoke |
| FND-PKG-004 | `agent_core.__init__` MUST NOT re-export contract/runtime symbols. | public import test |
| FND-VER-001 | Phase 1 MUST use one lockstep Contract Set version; any semantic change requires a minor bump. | version decision tests |
| FND-VER-002 | Contract Payload MUST NOT contain its own `contract_payload_hash`. | descriptor schema test |
| FND-VER-003 | `payload-descriptor.json` MUST be fully derivable before payload hashing. | deterministic generation test |
| FND-VER-004 | `contract-manifest.json` MUST reside outside the payload it identifies. | tree/manifest test |
| FND-VER-005 | Evidence Manifest MUST bind an existing Candidate commit and Payload Hash. | manifest validation test |
| FND-VER-006 | Governance lifecycle changes MUST NOT change payload identity unless normative content changes. | hash fixture test |

### A.2 Presence-aware Usage and Cost

| Rule ID | Normative statement | Minimum conformance proof |
|---|---|---|
| FND-MAP-001 | Adapter MUST map provable facts, not Legacy convenience defaults. | absent/zero mapping fixtures |
| FND-MAP-002 | Facts extraction MUST preserve presence and provenance and MUST NOT reconstruct missing facts from aggregate defaults. | extractor tests |
| FND-USAGE-001 | Known token counts MUST be non-negative; explicit zero and unknown `null` are distinct. | negative/zero/null tests |
| FND-USAGE-002 | Provider-reported `total_tokens` MUST be preserved exactly even when it differs from visible components. | provider mismatch fixture |
| FND-USAGE-003 | Missing `total_tokens` MUST remain `null`; Adapter MUST NOT synthesize input plus output. | missing total test |
| FND-COST-001 | Unknown cost MUST be `amount=null, source=unknown`; it MUST NOT be represented by zero. | unknown versus zero test |
| FND-COST-002 | Cost aggregation MUST NOT perform implicit FX; multiple non-null currencies MUST raise currency mismatch. | mixed currency tests |
| FND-COST-003 | Monetary values MUST use `Decimal` and serialize as decimal strings; float input is rejected. | precision/serialization tests |
| FND-COST-004 | Non-null currency MUST be an uppercase three-letter code. | currency validator tests |
| FND-COST-005 | `source`, `amount`, `currency` and `pricing_version` MUST satisfy the source invariant matrix in section 4.3. | parameterized matrix |
| FND-COST-006 | `source=price_table` MUST include a reproducible `pricing_version`. | missing version rejection |
| FND-COST-007 | Zero is known only when provider or confirmed pricing evidence explicitly proves zero for an observed call. | explicit zero fixtures |
| FND-COST-008 | Unknown amount MAY preserve a known currency context without becoming known cost. | unknown CNY/USD tests |
| FND-COST-009 | Raw Cost MUST remain in its source currency and MUST NOT claim converted/normalized semantics. | no-conversion test |
| FND-COST-010 | Cost MUST NOT contain task/span/report scope; scope belongs to the consuming family. | schema field exclusion |
| FND-COST-011 | `CostSource` describes epistemic provenance, not the storage location of pricing data. | Wiki estimate fixture |
| FND-COST-012 | Legacy numeric zero alone MUST NOT prove a true zero Cost. | ambiguous legacy zero tests |
| FND-COST-013 | Pricing-derived known amounts MUST reference a canonical pricing snapshot hash. | pricing hash fixture |

### A.3 CostSummary

| Rule ID | Normative statement | Minimum conformance proof |
|---|---|---|
| FND-CSUM-001 | All component counts MUST be non-negative. | validation test |
| FND-CSUM-002 | `component_count == known_component_count + unknown_component_count`. | invariant test |
| FND-CSUM-003 | `complete == (unknown_component_count == 0)`. | invariant test |
| FND-CSUM-004 | Zero known components require `known_amount=null`. | all-unknown/empty tests |
| FND-CSUM-005 | One or more known components require non-negative `known_amount` and non-null currency. | known subtotal tests |
| FND-CSUM-006 | A true zero Cost is a known component. | zero component test |
| FND-CSUM-007 | All non-null component currencies MUST be identical. | known/unknown mixed currency tests |
| FND-CSUM-008 | Null currency does not itself create mismatch, but an unknown amount still makes the summary incomplete. | null currency test |
| FND-CSUM-009 | Empty input MUST yield counts 0/0/0, null amount/currency and `complete=true`. | empty aggregation test |
| FND-CSUM-010 | CostSummary MUST NOT declare a single `source` or `pricing_version`. | schema field exclusion |
| FND-CSUM-011 | Summary MUST be built from observed components and MUST NOT reverse-engineer them from a Legacy total. | ledger/component test |

### A.4 Error, Mode and Extension Boundaries

| Rule ID | Normative statement | Minimum conformance proof |
|---|---|---|
| FND-ERR-001 | ErrorEnvelope is a boundary DTO, not an exception class or internal control-flow framework. | type/usage guard |
| FND-ERR-002 | Machine behavior MUST use stable `code`; `message` MUST NOT drive logic. | branch/static guard |
| FND-ERR-003 | Foundation v0.1 errors MUST have `retryable=false`. | parameterized error tests |
| FND-ERR-004 | Error details MUST be structured, sanitized and bounded; exception objects and tracebacks are forbidden. | forbidden-value tests |
| FND-ERR-005 | ErrorEnvelope MAY be produced only at declared serialization, API/IPC/MCP, Adapter or artifact boundaries. | boundary tests/review |
| FND-EXT-001 | Every extension key MUST use a registered namespace and valid dotted identifier. | namespace matrix |
| FND-EXT-002 | Extension values MUST be recursively JSON-compatible. | accepted/rejected type tests |
| FND-EXT-003 | Canonical serialized `extensions` MUST be at most 16 KiB. | byte-boundary tests |
| FND-EXT-004 | Extension value nesting MUST be at most four container levels, excluding the root mapping. | depth tests |
| FND-EXT-005 | Secrets, raw prompts/responses, tracebacks, credentials and unredacted paths MUST NOT enter extensions. | scanner fixtures |
| FND-EXT-006 | Foundation logic MUST treat project/provider extensions as opaque and MUST NOT change normative behavior from them. | behavior tests/static review |
| FND-MODE-001 | `off`, `observe` and `strict` have the exact semantics defined in section 10. | mode matrix |
| FND-MODE-002 | Observe and strict MUST execute the same extractor and Adapter; only failure policy differs. | shared-path test |
| FND-MODE-003 | Invalid `AGENT_CONTRACT_MODE` MUST fail configuration validation and MUST NOT silently become off. | configuration test |
| FND-MODE-004 | Observe mapping failure MUST preserve Legacy behavior and emit failed validation evidence. | injected failure invariance test |

`evidence.*` sink/I/O diagnostic codes are infrastructure diagnostics, not new `ErrorCategory` values and not `foundation.*` semantic errors.

### A.5 Evidence and Release Integrity

| Rule ID | Normative statement | Minimum conformance proof |
|---|---|---|
| EVD-RUN-001 | Controlled smoke, replay and strict commands MUST receive an explicit safe `run_id`. | missing/unsafe ID tests |
| EVD-RUN-002 | Every EvidenceRecord MUST bind contract version, Payload Hash and verified repository commit. | record validation test |
| EVD-SINK-001 | EvidenceSink MUST NOT silently discard a valid record. | injected sink failure test |
| EVD-SINK-002 | Sink failure in observe MUST NOT change the business result. | off/observe failure test |
| EVD-SINK-003 | Any sink failure invalidates that run as Cycle Evidence. | smoke closure test |
| EVD-SINK-004 | File event publication MUST be atomic and concurrent-writer safe. | temp/replace/concurrency test |
| EVD-DATA-001 | Staging Evidence MUST exclude raw business content and obey allowlist, JSON and 64 KiB constraints. | DTO/size/scanner tests |
| EVD-PUB-001 | Git release artifacts MUST be constructed from explicit allowlists. | publication transform test |
| EVD-PUB-002 | Raw prompts, responses, reasoning, code bodies, diffs and raw traces MUST NOT enter releases. | forbidden-field scan |
| EVD-PUB-003 | Credentials, environment dumps and private endpoints MUST NOT enter releases. | secret scan |
| EVD-PUB-004 | Replay corpus MUST contain only fields needed to reproduce contract semantics. | corpus schema test |
| EVD-PUB-005 | Restricted evidence MUST be labeled `REPRODUCTION_RESTRICTED`. | status validation test |
| EVD-PUB-006 | Published evidence MUST bind version, Payload Hash and Candidate commit. | manifest validation test |
| EVD-PUB-007 | Raw temporary evidence MUST have an explicit retention decision. | publication checklist |
| FND-REL-001 | Phase 1 has one canonical Cycle Report truth source: Wiki. | coordinator/finalizer test |
| FND-REL-002 | Coding Evidence B MUST NOT be required to duplicate the final Cycle Report. | release tree test |
| FND-REL-003 | Coordination PASS is not Cycle COMPLETE; COMPLETE requires merged canonical finalization. | state transition test |
| FND-REL-004 | Finalization C MUST contain only allowlisted coordination artifacts. | A/B/C tree-diff test |
| FND-REL-005 | Finalization artifacts MUST NOT reference C's own commit SHA. | self-reference test |
| FND-REL-006 | B_wiki to C_wiki MUST NOT mutate payload, Adapter, tests, business code or published Evidence. | ancestry/tree-diff test |

### A.6 Regression and Non-intrusion

| Rule ID | Normative statement | Minimum conformance proof |
|---|---|---|
| FND-REG-001 | Every previously passing test nodeid MUST remain non-failing and non-skipped. | baseline comparator |
| FND-REG-002 | Only registered failure nodeids with identical normalized fingerprints may remain failing. | fingerprint comparator |
| FND-REG-003 | A registered failure that becomes PASS is reported for review, not treated as Cycle failure or silently removed. | status transition fixture |
| FND-REG-004 | New shared conformance and project Adapter tests MUST all pass. | separate result sets |
| FND-REG-005 | Cycle quality claims MUST use deterministic non-intrusion; non-reproducible historical benchmark values are reference only. | report schema/gate test |

## Appendix B — Producer Registry Artifact [IMPLEMENTATION-READY]

`config/contracts/producer-registry.json` MUST use this shape:

```json
{
  "registry_version": "1",
  "contract_version": "0.1.0",
  "repository": "wiki",
  "producers": [
    {
      "producer_id": "wiki.eval.cost_log",
      "mapping_stages": ["runner", "judge", "scoring"],
      "status": "IN_SCOPE",
      "source_locations": [
        "arknights_wiki/eval/runner.py::_log_cost",
        "arknights_wiki/eval/judge.py::_log_cost",
        "arknights_wiki/eval/scoring.py::_log_cost"
      ],
      "legacy_fields": ["input_tokens", "output_tokens", "cost_cny", "model", "step"],
      "foundation_objects": ["Usage", "Cost"],
      "evidence_requirement": "ALL_STAGES",
      "notes": "原 cost log 写入保持不变"
    },
    {
      "producer_id": "wiki.trace.summary",
      "mapping_stages": [],
      "status": "DEFERRED",
      "source_locations": [],
      "legacy_fields": [],
      "foundation_objects": ["CostSummary"],
      "evidence_requirement": "NOT_APPLICABLE",
      "reason": "no_stable_online_summary_boundary"
    }
  ]
}
```

Coding 使用相同 Schema，将 `repository` 改为 `coding` 并登记 section 7.2 的 producer/stage。`producer_id` 是稳定规范身份；`mapping_stage` 是随实现演进的观察位置。Smoke Gate 比较 `(producer_id, mapping_stage)`，不能只比较 producer。

状态只能是：

```text
IN_SCOPE
DEFERRED
OUT_OF_SCOPE_BY_DESIGN
UNKNOWN
```

新发现项先进入 `UNKNOWN`；只有显式 scope review 能改为 `IN_SCOPE`。Historical Replay 可使用 `DEFERRED` 来源，但必须声明 `runtime_adapter_status=DEFERRED` 和 `evidence_role=historical_replay_only`。

## Appendix C — Canonical Commands and Environment Matrix [IMPLEMENTATION-READY]

下列命令是 Part I 实施后的权威接口；脚本不存在时不得用临时命令冒充完成门禁。

### C.1 Wiki

工作目录：`D:\AI project\Arknights LLM Wiki`

```powershell
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
python -m pytest agent_core/contracts/conformance -q
python -m pytest tests/contracts -q
python scripts/contracts/validate_local.py --gate pr
python -m build
python scripts/contracts/validate_local.py --gate candidate
python -m pytest tests/
```

L2/L3：

```powershell
$env:AGENT_CONTRACT_MODE = 'strict'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-wiki-replay'
python scripts/contracts/replay_history.py --run-manifest config/contracts/replay-v0.1.json

$env:AGENT_CONTRACT_MODE = 'observe'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-wiki-smoke'
python scripts/contracts/validate_local.py --gate smoke --run-manifest config/contracts/smoke-v0.1.json
```

### C.2 Coding

工作目录：`D:\AI project\Knowledge-Augmented Autonomous Coding Agent`

```powershell
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
python -m pytest agent_core/contracts/conformance -q
python -m pytest tests/contracts -q
python scripts/contracts/validate_local.py --gate pr
python -m build
python scripts/contracts/validate_local.py --gate candidate
python -m pytest tests/
```

L2/L3：

```powershell
$env:AGENT_CONTRACT_MODE = 'strict'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-coding-replay'
python scripts/contracts/replay_history.py --run-manifest config/contracts/replay-v0.1.json

$env:AGENT_CONTRACT_MODE = 'observe'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-coding-smoke'
python scripts/contracts/validate_local.py --gate smoke --run-manifest config/contracts/smoke-v0.1.json
```

### C.3 Wheel and package-data smoke

两个仓库都必须在新建临时虚拟环境中执行：

```powershell
python -m build
python -m venv <TEMP_VENV>
& '<TEMP_VENV>\Scripts\python.exe' -m pip install <BUILT_WHEEL>
& '<TEMP_VENV>\Scripts\python.exe' -c "from agent_core.contracts.models.usage import Usage; from importlib.resources import files; print(files('agent_core.contracts.schemas'))"
```

验收不是“当前工作目录中能 import”，而是 wheel 独立安装后能导入核心类型并读取 Schema package data。

### C.4 CI 环境矩阵

| Job | OS | 业务依赖 | 密钥 | 责任 |
|---|---|---|---|---|
| Local PR Contract Gate | Windows | 本仓完整/测试依赖 | 无 | Schema、Payload、L1、Adapter、invariance、package |
| Canonical full regression | Windows | 本仓完整依赖 | 无或沿用项目测试约束 | Wiki 542/7/3 指纹；Coding 381/13/0 |
| Canonical hash | Linux | 最小契约依赖 | 无 | 同一工具重算 Schema/Payload Hash |
| Historical replay | 受控 Windows | 本仓回放依赖 | 不应需要模型密钥 | L2 |
| Fresh smoke | 受控 Windows | 真实路径依赖 | 最小必要密钥 | L3，只读/本地可逆 |
| Coordination | Windows 或 Linux | Git + 契约验证工具 | Coding 只读 checkout token | 固定 A/B 验证，不调用模型 |

### C.5 Coordination and finalization

Wiki 协调端：

```powershell
python scripts/contracts/coordinate_cycle.py --plan <CYCLE_PLAN> --output <COORDINATION_OUTPUT>
python scripts/contracts/finalize_cycle.py --coordination <COORDINATION_OUTPUT> --release docs/contracts/releases/0.1.0
```

`coordinate_cycle.py` 只产生 `PASS/READY_FOR_FINALIZATION` artifact；`finalize_cycle.py` 只准备 C_wiki allowlist 文件。Cycle COMPLETE 由 C_wiki 合并后的验证产生，不由上述命令提前声明。

## Appendix D — Artifact Schemas and Paths [IMPLEMENTATION-READY]

### D.1 Candidate Payload artifacts

| Artifact | Repository/commit | Hash relation | Mutable fields forbidden |
|---|---|---|---|
| `agent_core/contracts/payload-descriptor.json` | 两仓 Candidate A | inside Payload | payload hash、governance state、commit SHA |
| generated `schemas/*.json` | 两仓 Candidate A | inside Payload | timestamp、absolute path |
| `contract.md` | 两仓 Candidate A | whole file in Payload | release-specific Evidence |
| shared conformance tests | 两仓 Candidate A | inside Payload | project imports |

### D.2 Evidence Publication B artifacts

推荐路径：

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

`changelog.md` 必须随 release append-only 保存，但不进入 Contract Payload Hash。Release 目录在 C_wiki 合并前仍处于 finalizing；Cycle COMPLETE 后不得覆盖既有文件。

Evidence Manifest 最小 Schema：

```json
{
  "contract_version": "0.1.0",
  "contract_payload_hash": "sha256:<hex>",
  "verified_repository_commit": "<Candidate A>",
  "repository": "wiki",
  "environment": {
    "python": "3.x.y",
    "pydantic": "2.13.4",
    "os": "windows"
  },
  "evidence": {
    "contract_tests": "PASS",
    "historical_replay": "PASS",
    "fresh_smoke": "PASS",
    "full_regression": "PASS_WITH_KNOWN_BASELINE_FAILURES"
  },
  "producer_coverage": [],
  "benchmark_reference_status": "BENCHMARK_BASELINE_NOT_REPRODUCIBLE"
}
```

Coding 的 `repository`、回归和 benchmark 状态分别是 `coding`、`PASS`、`BENCHMARK_REPRODUCTION_RESTRICTED`。Evidence Manifest 不包含自己的 hash 或 B SHA；它的 canonical hash 由 coordinator 计算。

Rule traceability 只保存引用：

```json
{
  "contract_version": "0.1.0",
  "rules": [
    {
      "rule_id": "FND-COST-001",
      "shared_tests": ["test_unknown_cost_is_not_zero"],
      "evidence_ids": ["wiki-cost-00017"]
    }
  ]
}
```

### D.3 Cycle Plan and Finalization

`cycle-plan.json` 在两个 B SHA 已存在后由协调系统构造，是 CI dispatch/input artifact，不属于 A_wiki、A_coding、B_wiki 或 B_coding 的 Git tree。它可以由受控协调运行归档，但不得通过自引用方式放进自己所声明的 Evidence commit。

Wiki 最终路径：

```text
docs/contracts/releases/0.1.0/cycle-report.json
docs/contracts/releases/0.1.0/cycle-report.md
docs/contracts/current.json
```

Cycle Report 的 JSON 结构以 section 16.5 为准。`current.json` 只能是 release pointer。Coding 停在 B_coding，不创建对应 cycle-report 或 current pointer。

### D.4 EvidenceRecord invariants

除 section 4.6 字段外，机器校验必须满足：

```text
PASS → foundation_output present AND error_envelope null
FAIL → error_envelope present; foundation_output optional
canonical event JSON <= 64 KiB
run_id matches ^[A-Za-z0-9_-]+$
event_id is canonical UUID or ULID
producer_id/stage exists in Registry
```

Evidence sink I/O 失败使用 `evidence.sink_write_failed`、`evidence.invalid_run_id` 或 `evidence.artifact_unavailable` 诊断到结构化应用日志与内存 counter，不能递归写回同一个 sink。

## Appendix E — Known Baseline Failure Fingerprints [IMPLEMENTATION-READY]

### E.1 规范化算法

Fingerprint 输入只包含：

```text
pytest nodeid
exception type
symbolic failure locus
normalized semantic signature
scope
baseline commit
```

必须移除绝对路径、临时目录、对象地址、堆栈行号和参数化运行序号。`fingerprint_sha256` 对上述字段的 canonical JSON 计算，不能直接 hash traceback。

### E.2 Wiki baseline records

基线提交：`838ba4c1440ece174da845f900428075f16cf05b`。三条记录共享：

```json
{
  "exception_type": "AttributeError",
  "symbolic_failure_locus": "arknights_wiki.stats.collector._get_raw_data",
  "normalized_error_signature": "story_shape_list_has_no_get",
  "scope": "DEFERRED",
  "baseline_commit": "838ba4c1440ece174da845f900428075f16cf05b"
}
```

按 Appendix E.1 的 canonical JSON 算法得到的初始记录：

| nodeid | fingerprint_sha256 |
|---|---|
| `tests/test_stats_collector.py::TestStatsCollectorContent::test_collect_content_reads_db` | `621b20760ce7091bc179a4fbb9bf15e738e7f11487374bd9d0a240ddee254b35` |
| `tests/test_stats_collector.py::TestStatsCollectorSnapshot::test_finish_writes_jsonl_line` | `bbed5cfa4515e997b3d661e333eec49d9065977518c696deeecbea8abe7b0925` |
| `tests/test_stats_collector.py::TestStatsCollectorSnapshot::test_finish_resets_state` | `b59ab80b45001b131aea3e70af8b0fef0a54da9c21270c310e29a71507d37bdf` |

实施 Stage 0 必须由 baseline tool 重算并核对上述值，再将三个完整 record 写入 `config/contracts/known-test-baseline.json`；若不一致，视为基线漂移并停止，不能自动接受新指纹。期望全量结果：

```text
542 PASS
7 SKIP
3 KNOWN_BASELINE_FAILURE
overall = PASS_WITH_KNOWN_BASELINE_FAILURES
```

判断：

```text
known nodeid + same fingerprint → ALLOWED_BASELINE_FAILURE
known nodeid + different fingerprint → FAIL
new failing nodeid → FAIL
baseline PASS → FAIL or SKIP → FAIL
known failure → PASS → KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY; review required
```

意外 PASS 不使当前 Cycle 失败，也不得在同一 Cycle 中静默删除 baseline。确认原因后只能在下一版本更新基线。

### E.3 Coding baseline

基线提交：`08a8275c91872a934f66a9db38fc30cf608c690d`。

```text
381 PASS
13 SKIP
0 FAIL
overall = PASS
```

`known_failures=[]`。任何新 FAIL，或任何 baseline PASS 变成 SKIP，均令 Candidate Gate 失败。

## Appendix F — File-level Change Matrix [IMPLEMENTATION-READY]

本矩阵是 Part I 的改动白名单。若实施发现必须修改未列文件，必须先停止、记录原因并修订 Spec；不能以“顺手重构”扩大范围。

### F.1 Mirrored Contract Payload — both repositories

| File/pattern | Current state | v0.1 change | Must preserve / forbid | Verification | Rollback point |
|---|---|---|---|---|---|
| `agent_core/__init__.py` | 不存在 | namespace reservation docstring | 不导出符号，不放运行时 | FND-PKG-001/004 | 删除本地 namespace |
| `agent_core/contracts/version.py` | 不存在 | `CONTRACT_VERSION=0.1.0` 和 tooling version constants | 不含治理状态 | version tests | 删除 mirror |
| `agent_core/contracts/enums/**` | 不存在 | modes、sources、errors、evidence StrEnum | 禁止项目专有值 | schema/conformance | 删除 mirror |
| `agent_core/contracts/models/**` | 不存在 | base、Usage、Cost、CostSummary、ErrorEnvelope、FoundationObservation、EvidenceRecord | `extra=forbid`；只含跨边界 DTO | L1 + Schema | 删除 mirror |
| `agent_core/contracts/protocols/evidence_sink.py` | 不存在 | 窄 `emit/write(record)` Protocol | 不规定文件 I/O | protocol/conformance | 删除 mirror |
| `agent_core/contracts/contract.md` | 不存在 | v0.1 全部规范规则 | 全文进入 Payload；不放项目实施细节 | Rule traceability | 删除 mirror |
| `agent_core/contracts/conformance/**` | 不存在 | 共享 Rule ID tests | 不 import 项目代码 | shared tests | 删除 mirror |
| `agent_core/contracts/schemas/**` | 不存在 | 受控生成 Schema | 不手改 | regeneration diff | 删除 mirror |
| `agent_core/contracts/tooling/**` | 不存在 | canonical JSON、Schema、hash、bundle 工具 | Windows/Linux 同一实现 | deterministic hash jobs | 删除 mirror |
| `agent_core/contracts/payload-descriptor.json` | 不存在 | 无自引用的 payload 目录 | 不含 payload hash、commit、maturity | descriptor tests | 删除 mirror |

两仓上述镜像必须由 Wiki bundle 产生，不能人工分别实现。

### F.2 Wiki project files

| File | Current behavior | v0.1 change | Must remain unchanged | Verification | Rollback |
|---|---|---|---|---|---|
| `pyproject.toml` | 仅发现 Wiki package；当前环境已有 Pydantic | 固定 Pydantic、build system、包含 `agent_core*` 与 package data | Wiki 原依赖与入口 | clean wheel smoke | 还原 packaging 条目 |
| `arknights_wiki/adapters/foundation/**` | 不存在 | facts/mapping/runtime/FileEvidenceSink | 不承载 Legacy 业务逻辑 | Adapter/L1/sink tests | 删除 Adapter 目录 |
| `arknights_wiki/extraction/llm_client.py::chat_completion` | 模型调用、resilience、可选 Langfuse usage | 在 Langfuse 条件外提取 presence facts并旁路观察 | 请求、retry、返回、旧 Trace | fixed-response invariance + stage smoke | mode off；移除 seam |
| `arknights_wiki/agent/router.py::_llm_intent_rewrite` | LLM rewrite 与既有 fallback | 成功响应后旁路观察 | prompt、过滤、异常/fallback、返回 | routing invariance + stage smoke | mode off；移除 seam |
| `arknights_wiki/eval/runner.py::_log_cost` | 写原 cost JSONL | 写前复制 allowlisted facts，stage runner | entry、路径、次数、异常语义 | cost-log byte/semantic invariance | mode off；移除 seam |
| `arknights_wiki/eval/judge.py::_log_cost` | 写原 cost JSONL | 同上，stage judge | 同上 | 同上 | 同上 |
| `arknights_wiki/eval/scoring.py::_log_cost` | 写原 cost JSONL | 同上，stage scoring | 同上 | 同上 | 同上 |
| `arknights_wiki/eval/metrics.py::summarize_cost` | Legacy float 汇总并跳过 malformed | 并行收集 components 并在旧汇总完成后 emit | 旧返回、rounding、step、missing-file 语义 | summary invariance + malformed evidence | mode off；移除旁路 |
| `config/contracts/producer-registry.json` | 不存在 | Wiki Registry | 新 producer 默认 UNKNOWN | registry/schema/smoke coverage | 删除配置 |
| `config/contracts/known-test-baseline.json` | 不存在 | 542/7/3 nodeid+fingerprint | 不修 StatsCollector | baseline comparator | 删除配置并禁用 gate |
| `config/contracts/smoke-v0.1.json`、`replay-v0.1.json` | 不存在 | 预登记 L2/L3 run scope | 不含凭据 | manifest validation | 删除配置 |
| `scripts/contracts/*.py` | 不存在 | local validation、replay、publication、coordination、finalization | 不成为业务运行入口 | tool self-tests/CI dry run | 删除 scripts |
| `tests/contracts/**` | 不存在 | mapping、sink、wiring、invariance、baseline、packaging | 与 existing baseline 分组 | 100% PASS | 删除新增 tests |
| `.github/workflows/contract-local.yml` | 不存在 | Wiki Local Gate | 不 checkout Coding | workflow review/run | 删除 workflow |
| `.github/workflows/contract-payload-linux.yml` | 不存在 | Linux minimal hash | 不运行完整 Wiki | expected hash | 删除 workflow |
| `.github/workflows/contract-coordinate.yml` | 不存在 | 固定 SHA coordinator | 不调用真实模型 | coordination fixtures | 删除 workflow |
| `.gitignore` | 未忽略契约 staging | 忽略 staging/raw/private evidence | 保留原规则 | ignore test/review | 删除新增行 |

明确不在白名单：`arknights_wiki/eval/report.py`、Dashboard、StatsCollector、offline extraction、retrieval、memory、KG、checkpoint 和业务状态。

### F.3 Coding project files

| File | Current behavior | v0.1 change | Must remain unchanged | Verification | Rollback |
|---|---|---|---|---|---|
| `pyproject.toml` | 当前项目 packaging | 固定 Pydantic、发现 `adapters*`/`agent_core*`、package data | 原 packages/entry points | clean wheel smoke | 还原 packaging 条目 |
| `adapters/foundation/**` | 不存在 | facts/mapping/runtime/ledger/FileEvidenceSink | 不承载 Agent、Sandbox、审批逻辑 | Adapter/L1/sink tests | 删除 Adapter 目录 |
| `agent/llm.py::OpenAICompatClient.chat` | provider 调用、tokens_total、Legacy trace | coercion 前取 presence facts、emit、写 local ledger | request、parse、tokens_total、返回 | fixed-response invariance + two-stage smoke | mode off；移除 seam/ledger call |
| `tools/tracing.py::record_usage` | 可选 Langfuse generation | 加 keyword-only contract facts 并独立 emit | 旧签名兼容、client no-op、trace args | call-spy invariance | mode off；移除新参数 |
| `benchmark/runner.py` 指定 CaseResult 分支 | 形成正常/环境/异常结果 | CaseResult 完成后按 ledger slice emit summary | 执行顺序、判定、`cost_usd`、异常隔离 | deterministic case invariance | mode off；移除 helper |
| `tools/report_trace.py::_summarize_trace/_summarize_events` | SDK/ClickHouse 形成 Legacy TraceSummary | coercion 前取 facts，旧 summary 后 emit | fallback、TraceError、计算、渲染 | fixture invariance + stage coverage | mode off；移除 seam |
| `config/contracts/*.json` | 不存在 | Registry、baseline、L2/L3 manifests | 不含凭据/私有路径 | schema validation | 删除配置 |
| `scripts/contracts/*.py` | 不存在 | local validation、replay、publication | 不含 coordinator/finalizer | tool self-tests | 删除 scripts |
| `tests/contracts/**` | 不存在 | mapping、sink、wiring、invariance、baseline、packaging | 与 existing baseline 分组 | 100% PASS | 删除新增 tests |
| `.github/workflows/contract-local.yml` | 不存在 | Coding Local Gate | 不 checkout Wiki | workflow review/run | 删除 workflow |
| `.github/workflows/contract-payload-linux.yml` | 不存在 | Linux minimal hash | 不运行完整 Coding Agent | expected hash | 删除 workflow |
| `.gitignore` | 未忽略契约 staging | 忽略 staging/raw/private evidence | 保留原规则 | ignore test/review | 删除新增行 |

明确不在白名单：Sandbox、GitHub、Approval、Tool envelope、Agent routing/review/retry、Benchmark cases/gold patches/judge prompt 和 `benchmark/report.py`。

### F.4 Evidence and release files by commit identity

| Commit | Allowed new/changed files | Forbidden changes |
|---|---|---|
| A_wiki | Payload、Wiki Adapter/wiring/tests/config/CI | Deferred domains、cycle report/current |
| A_coding | mirror、Coding Adapter/wiring/tests/config/CI | Sandbox/Approval/GitHub、cycle report/current |
| B_wiki | Wiki validation artifacts、contract manifest、changelog、状态账本纯追加 | Payload、code、tests、packaging、cycle plan、existing Evidence/status mutation |
| B_coding | Coding validation artifacts、same contract manifest/changelog | Payload、code、tests、packaging、cycle report/current |
| C_wiki | cycle-report JSON/Markdown、current pointer、状态账本纯追加、optional coordination index | 所有其他文件、B Evidence/status mutation、自身 SHA reference |

## Appendix G — Cycle 1 Handoff Checklist [IMPLEMENTATION-READY]

将本 Spec 交给实施者时，必须附带以下约束：

1. 先重新确认两个仓库的目标 Candidate 起点；若已漂移，更新 Stage 0 baseline artifact，不得静默继续使用本文快照。
2. 只执行 Part I；Part II 的契约语义取决于未来 L2/L3，Part III 在 gate 满足前没有实施授权。
3. 先完成 Wiki canonical Payload，再通过 bundle 同步 Coding；不得双边手写公共契约。
4. 每个 producer 按“现状 → observation seam → facts → mapping → evidence → 不变性 → rollback”逐项完成。
5. 每完成一个 stage 都验证旧业务行为；不要等所有接线完成后才检查侵入性。
6. 任何真实仓库事实与本 Spec 不符、任何必须修改未列文件、任何 producer 无法在不改变业务语义下接入时，停止并形成 Spec deviation report。
7. Cycle 1 只有 L1、L2、L3、双仓回归、固定 A/B coordination 和 C_wiki finalization 全部闭合后才能标记 COMPLETE。

Spec deviation report 至少记录：

```yaml
repository
candidate_base_commit
spec_section
observed_fact
expected_fact
scope_impact
proposed_resolution
requires_contract_revision: true | false
```

该报告用于修正文档或重新授权，不允许作为越过门禁的临时批准。

## Appendix H — Requirements Traceability [NORMATIVE]

| Source decision | Master Spec location |
|---|---|
| 契约优先、实现本地保留 | sections 2–3, ADR-0001 |
| 两个真实 Contract Iteration Cycle | sections 17–22 |
| Pydantic/Protocol/Schema/conformance 多载体 | sections 0.2, 3–5, Appendix A |
| Foundation-only v0.1 | sections 2, 4 |
| Unknown is not Zero / presence-aware facts | sections 4, 6, Appendix A.2–A.3, ADR-0002 |
| Extension Boundary | section 5, Appendix A.4 |
| off/observe/strict shadow validation | sections 10, 14, ADR-0002 |
| L1/L2/L3 Evidence Gate | sections 11, 13 |
| Publishable Evidence boundary | section 11, Appendix A.5/D |
| Lockstep version and dual integrity hashes | section 12 |
| Local CI and fixed-SHA Coordination | section 15 |
| Candidate A / Evidence B / Finalization C | section 16, Appendix D/F.4 |
| Known failure fingerprints | sections 1.3, 14.2, Appendix E |
| Cycle non-intrusion vs extraction quality | sections 14.3, 23–24 |
| Family-specific extraction and LOCAL_BY_DESIGN | sections 23, 26–29, ADR-0001 |

本文冻结的是 v0.1 的实施规范、v0.2 的证据驱动流程和未来抽取门禁。它不宣称任何 Contract、Adapter、CI、Evidence 或 Cycle 已经实施或通过。

## Appendix I — Child Spec Execution Status Governance [NORMATIVE]

### I.1 Static genesis

路径：

```text
docs/specs/foundation-contract/execution-status-events.jsonl
```

合法初始文件为 0 bytes / 0 records。Reducer 从静态子 Spec 读取 genesis：Spec 01 为 `READY`，Spec 02–18 为 `NOT_STARTED`。Initial Status 不重复写入 Ledger。

### I.2 Execution Status Event Schema

每个非空 JSONL 行必须是独立 canonical JSON object：

```json
{
  "event_id": "<UUID-or-ULID>",
  "spec_id": "09",
  "from_status": "IN_PROGRESS",
  "to_status": "VALIDATED",
  "candidate_commit": "<existing-A-or-null>",
  "evidence_refs": ["contract-tests:<artifact-id>"],
  "timestamp": "<RFC3339>",
  "reason_code": "VALIDATION_PASSED",
  "reason": "Shared conformance and adapter tests passed.",
  "references": []
}
```

`candidate_commit` 对 A 存在前的 01–11 pre-freeze 事件为 `null`；A 存在后的正式验证、发布和协调事件必须引用已存在的 A。事件不得保存包含自己的 Git commit SHA 或 Ledger hash。

状态：

```text
NOT_STARTED
READY
IN_PROGRESS
BLOCKED
VALIDATED
COMPLETE
SUPERSEDED
```

Reason code 至少包括：

```text
PREREQUISITES_SATISFIED
EXECUTION_STARTED
VALIDATION_PASSED
ACCEPTANCE_COMPLETE
BLOCKED
SPEC_CONFLICT
SPEC_INCOMPLETE
FREEZE_BOUNDARY_REACHED
CANDIDATE_FROZEN
CANDIDATE_SUPERSEDED
EVIDENCE_PUBLISHED
COORDINATION_PASSED
FINALIZATION_COMPLETE
STATUS_CORRECTION
```

### I.3 Deterministic reducer

Reducer 必须进入 Candidate A，并验证：

1. 文件严格 UTF-8、每个非空行均满足 Event Schema。
2. `event_id` 全局唯一，事件按文件顺序 append；不得排序后重新解释。
3. `from_status` 必须等于前一归约状态。
4. 状态转换必须合法；默认 DAG 依赖只由 upstream `COMPLETE` 解锁，子 Spec 显式允许 `VALIDATED` 时除外。
5. `VALIDATED` 必须有 validation result/Evidence reference；`COMPLETE` 必须已满足全部 acceptance criteria。
6. Execution Authority 必须允许该动作；FEEDBACK-BOUND/GATE-DEFINED 不能因状态变化自动获得实施权限。
7. Candidate A 后的事件必须符合 A/B/C 阶段、commit binding 和 append-only allowlist。
8. 同一状态出现互斥后继、跳过强制阶段或缺失前置条件时，不采用“最后一行赢”，而是返回 `SPEC_STATUS_CONFLICT`。

运行中的依赖解锁允许 reducer 接受两段输入：

```text
canonical persisted ledger prefix
+ Candidate-bound validated pending suffix from controlled staging
→ effective execution status
```

Pending suffix 必须由同一 Candidate A 中的 reducer 生成/验证、记录目标持久化边界并具备自身 canonical hash。它只用于当前受控执行中解锁 downstream，不是 Git canonical history，不能单独证明 Cycle COMPLETE，也不能跨 Candidate 复用。下一 A/B/C 边界必须逐字节追加该 suffix；若未追加、被修改或 Candidate 被取代，依赖它产生的 downstream Evidence 无效。

合法主路径：

```text
NOT_STARTED → READY → IN_PROGRESS → VALIDATED → COMPLETE
```

`BLOCKED` 可从 READY/IN_PROGRESS 进入，并在阻塞解除后回到原执行阶段。`COMPLETE → IN_PROGRESS` 只允许 `STATUS_CORRECTION` 补偿事件且必须引用错误事件；历史行永不修改。Candidate 缺陷使用 `CANDIDATE_SUPERSEDED`，不得修改既有 A 身份。

### I.4 Persistence boundaries

运行期间状态事件先在受控 staging 生成，不要求每个动作单独提交。Git 持久化边界：

| Boundary | Wiki Ledger allowed events | Coding Ledger |
|---|---|---|
| Candidate A | 01–10 的真实状态与 Spec 11 freeze-boundary entry；不引用 A 自身 SHA | 不存在 |
| Evidence B_wiki | 只追加绑定 A 的 Spec 11–14 validation/publication events | 不存在 |
| Finalization C_wiki | 只追加 Spec 15 coordination/finalization events | 不存在 |

任何对旧行的修改、删除、重排或非法新增都令相应 Candidate/Evidence/Finalization Gate 失败。

因此，Spec 11 的正式 L1/回归通过后，可以由经验证的 pending suffix 将其 effective status 归约为 `COMPLETE` 并解锁 Specs 12/13；Specs 12/13 的完成事件同样先进入该 suffix，待 Spec 14 原样写入 B_wiki。此机制不创建中间B提交，也不改变Candidate A。

### I.5 Governance rules

```text
GOV-SPEC-001  Child Specs are execution projections and MUST NOT override Master semantics.
GOV-SPEC-002  Child/Index documents MUST remain static after Candidate A except through a new superseding Candidate.
GOV-STAT-001  The append-only Ledger is the sole dynamic execution-status source.
GOV-STAT-002  Empty Ledger plus Child Initial Status defines genesis state.
GOV-STAT-003  Current state MUST be produced by the Candidate-bound deterministic reducer.
GOV-STAT-004  B/C MAY only append phase-legal events and MUST NOT rewrite history.
GOV-FRZ-001   All tools required by Specs 12–15 MUST exist and be validated before Spec 11 freezes A.
GOV-FRZ-002   Post-freeze tooling defects MUST supersede A and return to an owning pre-freeze Spec.
```

这些治理规则不属于 `agent_core.contracts` Contract Payload，不进入 `payload-descriptor.normative_rule_set`；它们约束本次工程执行与证据身份。
