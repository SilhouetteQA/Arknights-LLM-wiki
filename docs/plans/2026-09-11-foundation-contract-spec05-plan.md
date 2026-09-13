# Spec 05 执行计划 — Wiki Presence-aware Facts and Adapter

> 依赖：Spec 04 `COMPLETE`（账本 15 条事件）
> 目标仓：仅 `WIKI_REPO`
> Candidate Phase：pre-A（`candidate_commit` 必须保持 `null`）
> 边界：**本步骤不修改任何 producer 或 Legacy 业务文件**

## 1. 目标

在 Wiki 项目内建立 **presence-aware facts → Foundation mapping → 统一 mode runtime** 三层，
为 Spec 07 的 producer seams 提供**单一旁路入口**。核心是把 Legacy 里为方便计算产生的
`0` 拆成「真实零 / 未知 / 估算」，同时**不改变任何业务返回值**。

## 2. 文件清单（与 Allowed Changes 逐条对应）

| 路径 | 类型 | 内容 |
|---|---|---|
| `arknights_wiki/adapters/__init__.py` | NEW | 子包说明（Allowed 明确"仅在不存在时"创建；当前不存在） |
| `arknights_wiki/adapters/foundation/__init__.py` | M | 补充本步骤新增模块的说明（Spec 04 已建） |
| `arknights_wiki/adapters/foundation/facts.py` | NEW | `WikiLegacyUsageFacts` / `WikiLegacyCostFacts` / summary component facts + 三个 extractor |
| `arknights_wiki/adapters/foundation/mapping.py` | NEW | facts → Usage / Cost / CostSummary，以及边界 ErrorEnvelope 映射 |
| `arknights_wiki/adapters/foundation/runtime.py` | NEW | mode 解析、policy 执行、EvidenceRecord 构造、sink 注入与 failure counter |
| `tests/contracts/test_foundation_mapping.py` | NEW | 至少覆盖 Spec 05 列出的 10 类 fixture |

`evidence_sink.py`（Spec 04）被调用但**不改变 I/O 语义**。

`tests/contracts/` 不放 `__init__.py` —— 与仓库现有 `tests/eval/`、`tests/observability/`
风格一致（Wiki `tests/` 下两种风格并存），无需 deviation。

## 3. 关键设计决策

### 3.1 Facts 结构（不进入共享 payload）

Master §6 要求的 12 项 presence/provenance 全部落成显式字段，**不使用** `getattr(..., 0)`：

```python
@dataclass(frozen=True)
class WikiLegacyUsageFacts:
    call_observed: bool                 # 是否发生过一次模型调用
    usage_object_present: bool          # response.usage 是否为 None
    field_presence: Mapping[str, bool]  # prompt_tokens / completion_tokens / total_tokens
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None            # 原样保留，绝不与 input+output 求和
    is_character_estimate: bool         # runner 的按字符估算路径
    model: str | None

@dataclass(frozen=True)
class WikiLegacyCostFacts:
    call_observed: bool
    model: str | None
    price_entry_present: bool           # pricing.json 是否有该 model 键
    pricing_value_present: bool         # in/out 均存在且不是 None/"tbd"
    price_entry_complete: bool          # 同上（in 与 out 都可用）
    pricing_is_estimate: bool           # pricing.json 的 estimate 标记
    per_call_pricing: bool              # firecrawl_search 这类按次计价项
    legacy_amount: float | None         # legacy 计算出的 float（可为 0.0）
    currency_context: str | None        # Wiki 为 "CNY"
    pricing_snapshot_hash: str | None   # 见 3.3

@dataclass(frozen=True)
class WikiLegacySummaryFacts:
    components: tuple[WikiLegacyCostFacts, ...]
    malformed_records: tuple[str, ...]  # 被 Legacy 跳过的 malformed 行标识
```

**Extractor 输入是"已解包的原始对象"**（OpenAI 兼容 response 或 usage 对象、Eval cost entry
dict、pricing snapshot dict），**不 import 任何业务模块**，因此没有副作用、不触发 Langfuse、
不写文件，也不会与 Spec 07 的 seam 产生循环依赖。

### 3.2 Usage 映射（Master §6.1 逐行）

| facts | Foundation |
|---|---|
| `usage_object_present=False` | 5 个 token 字段全 `null`，`source=unknown` |
| usage 存在且字段明确为 `0`，非估算 | 该字段 `0`，`source=provider_reported` |
| usage 存在且字段缺失 | 该字段 `null` |
| `is_character_estimate=True` | `input=null`、`output=估算 N`、`total=null`、`source=estimated` |
| provider total 存在 | 精确保留（即使与 input+output 不符） |
| provider total 缺失 | `null`，**禁止**自动相加 |

`call_observed=False` 时 `source=unknown`，全部 `null`。

### 3.3 Pricing snapshot identity

按 Master §6.2：对整个 `eval/pricing.json` 做 canonical JSON（sorted keys、compact、
UTF-8、无 BOM），取 SHA256，作为 `pricing_version` 与 facts 的 `pricing_snapshot_hash`。

**不使用** mtime、`repr(dict)`、Git 时间戳。Legacy float 一律先 `Decimal(str(value))`
再参与计算，禁止二进制 float 误差扩散。snapshot 由 extractor 一次性加载并缓存于实例，
不在模块级缓存（避免测试间串味）。

### 3.4 Cost 映射（Master §6.2 逐行）

| facts | Foundation |
|---|---|
| `price_entry_present=False` | `amount=null`、`source=unknown`、保留 `currency="CNY"` 上下文 |
| `pricing_value_present=False`（`null` / `"tbd"`） | 同上 |
| 有效且 `pricing_is_estimate=True` | Decimal amount、`source=estimated`、`pricing_version=snapshot hash` |
| 有效且确认价 | Decimal amount、`source=price_table`、`pricing_version=snapshot hash` |
| provider 明确报告货币成本 | `source=provider_reported` |
| 只有 `legacy_amount=0.0` | **不足以**证明真实零 → `source=unknown`、`amount=null` |

真实零只在「`call_observed=True` **且** 存在明确免费证据」时映射 —— v0.1 的 Wiki 数据里
唯一明确的免费证据是 `pricing.json` 中显式的免费条目（如 `per_call` 项在免费额度内），
其余一律 unknown。**任何 ambiguous legacy zero 一律 unknown。**

### 3.5 Summary 映射

```text
Legacy components ─→ Legacy aggregation ─→ unchanged legacy result
        │
        └→ provenance facts ─→ Foundation components ─→ CostSummary
```

- `CostSummary.from_costs` 只接受组成项，**没有 total 参数** —— 结构上堵死"从 legacy total 反推"
- malformed legacy record 继续按旧逻辑被跳过，但 `observe` 必须产 FAIL Evidence（extractor
  把它们的标识记进 `malformed_records`，不打内容），`strict` 直接令验证失败

### 3.6 Runtime 与 mode policy

```text
off     解析后立即返回，不提取、不映射、不建 sink（零分配）
observe 提取 → 映射 → 构造 EvidenceRecord → 交给注入的 sink；失败只产 FAIL 证据，不改业务返回
strict  完全相同的提取与映射路径；任何失败 → 先 emit FAIL 证据，再抛 ContractValidationError
```

- `off` 与「未安装 Adapter」在 state 与 return 上等价（SPEC 验收项）
- 三种模式共用**同一** extractor 与 mapping，只有失败策略不同（FND-MODE-002）
- **sink failure counter 不可递归**：sink 抛错时只计数 + 记日志，绝不再调 sink
- `run_id`：显式传入优先；未传且 mode 为 `observe` → 生成进程级 UUID；
  未传且 mode 为 `strict` → 直接失败（Master §11.1 要求受控命令必须显式提供）
- `evidence.*` 基础设施失败**不得**被包装成 `ErrorEnvelope`（两者互不继承）

### 3.7 窄 helper API（供 Spec 07 的 seam 调用）

```python
runtime.observe_chat_completion(response, *, model, stage) -> None
runtime.observe_eval_result(result: Mapping, *, stage) -> None
runtime.observe_eval_cost_entry(entry: Mapping, *, stage) -> None
runtime.observe_summary(cost_log_path, legacy_summary: Mapping) -> None
```

每个 helper 只做「提取 facts → 映射 → 交 sink」，**不含** Legacy 计算、不含文件写入、
不返回业务值。调用约定：seam 先让 Legacy 完成原逻辑，再调 helper。

### 3.8 sanitized_input_facts 的落地形态

facts 不能原文进证据，映射为 `JsonValue` 键值：

```text
wiki.legacy.call_observed            bool
wiki.legacy.usage_object_present     bool
wiki.legacy.field_presence           {token 名: bool}     ← 列表形式以满足 JSON 值域
wiki.legacy.is_character_estimate    bool
wiki.legacy.malformed_record_count   int
wiki.pricing.entry_present           bool
wiki.pricing.value_present           bool
wiki.pricing.is_estimate             bool
wiki.currency.context                str
wiki.model.name                      str
```

命名空间 `wiki.*` 已在 Spec 04 的 facts allowlist 内；不含任何 prompt/response/正文。
键数远低于 64 上限。

## 4. 执行顺序

1. `adapters/__init__.py` + 更新 `foundation/__init__.py` 说明
2. `facts.py`（三个 facts 类型 + 三个 extractor + pricing snapshot 加载）
3. `mapping.py`（Usage/Cost/CostSummary 映射 + ErrorEnvelope 边界）
4. `runtime.py`（mode policy + EvidenceRecord 组装 + sink 注入 + failure counter）
5. `tests/contracts/test_foundation_mapping.py`（10 类 fixture）
6. 跑 Spec 05 官方验证命令；跑全量既有测试确认零回归
7. 复核 `off == 未安装` 与「不出现 `get(..., 0)` / `or 0` / total 重建」

## 5. 验证命令（Spec 05 官方）

```powershell
python -m pytest tests/contracts/test_foundation_mapping.py -q
```

必须覆盖的 fixture：usage absent、provider zero、provider total mismatch、runner estimate、
unknown price、estimate price、confirmed/free price、CNY context、malformed summary component、
mode invalid value。

## 6. 验收对照

- [ ] Facts extractor 不出现 `get(..., 0)`、`or 0` 或 total reconstruction
- [ ] `estimate=true` 得到 `source=estimated`
- [ ] price missing/tbd 得到 `amount=null`、`source=unknown`，并保留 CNY context
- [ ] mapping failure 在 observe 中形成 FAIL Evidence，但模拟业务返回不变
- [ ] project facts 未进入 `agent_core.contracts` 或 JSON Schema

## 7. 回滚 / Handoff

尚未接线，删除 `arknights_wiki/adapters/foundation/` 下新增的三个模块与
`tests/contracts/test_foundation_mapping.py` 即可（`evidence_sink.py` 属 Spec 04，保留）。
Handoff 必须列出每类 facts 的 presence/provenance 来源与仍然 ambiguous 的 Legacy 情况。

## 8. 决策记录（2026-09-11 经用户确认）

| 决策点 | 结论 |
|---|---|
| runtime 身份来源 | **payload hash 现场复算 + commit 注入**：`contract_payload_hash` 由 runtime 从已安装的 `agent_core` 用 Spec 03 的 `canonical_file_bundle_digest` 复算（可独立验证）；`repository_commit` 由构造参数注入，否则读 `AGENT_CONTRACT_COMMIT` |
| 字符估算里的 `tokens_in=0` | **视为未测量 → null**（`_estimate_llm_cost` 硬编码的 0 是哨兵，不是测量值），与 Master §6.1 逐字一致 |
| pricing 快照 identity | **包含 `_note` 全文件**：按 Master §6.2「对整个 pricing.json」执行；指纹即文件内容身份，改注释也算新快照 |
| 执行节奏 | 先完整做完 Spec 05，再做 Spec 06 |
| `tests/contracts/` 是否放 `__init__.py` | 不放：与仓库现有 `tests/eval/`、`tests/observability/` 风格一致 |
| `arknights_wiki/adapters/__init__.py` | 创建：Allowed 明确"仅在不存在时"，当前不存在 |

### 8.1 实现中发现的一处必要精化（已登记）

决策表述为「commit 缺失时 observe 产 FAIL 证据、strict 直接失败」，但
**`repository_commit` 是 `EvidenceRecord` 的必填字段**（EVD-RUN-002 + 模型定义），
因此 commit 不可用时连一条合法 FAIL 记录都构造不出来。

实际实现（更严格，且不可能靠伪造通过）：

```text
commit 缺失 + observe  → 该 run 标记为失效（failure counter +1 + 结构化日志），不产出任何记录，
                          业务返回完全不受影响
commit 缺失 + strict   → 首次观察即抛 ContractValidationError
```

与决策意图一致（observe 不改变业务、strict 失败），只是把「产 FAIL 证据」落实为
「该 run 明确失效」—— 伪造一个假提交号塞进证据会直接违反 EVD-RUN-002。
`test_missing_repository_commit_degrades_in_observe_and_fails_in_strict` 覆盖该行为。
