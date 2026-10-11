# Spec 06 执行计划 — Coding Presence-aware Facts, Adapter and Component Provenance

> 依赖：Spec 04 `COMPLETE`（账本 15 条事件）
> 目标仓：仅 `CODING_REPO`
> Candidate Phase：pre-A（`candidate_commit` 必须保持 `null`）
> 边界：**本步骤不修改任何 producer；不创建新的业务成本账本**
> 计划文档位置说明：与 Spec 03/04/05 一致统一放在 Wiki `docs/plans/`（Wiki 是 coordinator），
> 但**执行目标仓是 Coding**。

## 1. 目标

在 Coding 项目内建立 **presence-aware facts → Foundation mapping → mode runtime → client-local
component provenance sidecar** 四层，为 Spec 08 的 Agent / Trace / Benchmark / report seams
提供**真实组成项**，同时不动 `tokens_total`、不动 `CaseResult.cost_usd`、不动 Benchmark 判定。

## 2. 文件清单（与 Allowed Changes 逐条对应）

| 路径 | 类型 | 内容 |
|---|---|---|
| `adapters/__init__.py` | NEW | 子包说明（Allowed 明确"仅在不存在时"创建；当前不存在） |
| `adapters/foundation/__init__.py` | M | 补充新增模块说明（Spec 04 已建） |
| `adapters/foundation/facts.py` | NEW | Coding facts 类型 + extractor |
| `adapters/foundation/mapping.py` | NEW | facts → Usage / Cost / CostSummary（与 Wiki 语义一致，代码独立） |
| `adapters/foundation/runtime.py` | NEW | mode policy + EvidenceRecord 组装 + sink 注入 |
| `adapters/foundation/observation_ledger.py` | NEW | client-local component provenance sidecar |
| `tests/contracts/test_foundation_mapping.py` | NEW | Spec 06 列出的 8 类 fixture |

`tests/` 无 `__init__.py`（该仓既有风格），因此 `tests/contracts/` 也不放，无需 deviation。

## 3. 关键设计决策

### 3.1 Facts 结构

```python
@dataclass(frozen=True)
class CodingLegacyUsageFacts:
    call_observed: bool
    usage_object_present: bool
    field_presence: Mapping[str, bool]      # prompt_tokens / completion_tokens
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None                # provider 原值，不重算
    model: str | None

@dataclass(frozen=True)
class CodingLegacyCostFacts:
    call_observed: bool
    model: str | None
    price_entry_present: bool               # MODEL_PRICE_USD_PER_1K 是否有该 model
    pricing_value_present: bool
    legacy_cost_usd: float | None           # runner/tracing 传入的 0.0 也在内
    currency_context: str | None            # Coding 为 "USD"
    price_table_size: int                   # 当前空表 = 0，是"unknown 而非 true zero"的直接证据
```

关键事实（母 Spec §1.5 Coding 段）：`MODEL_PRICE_USD_PER_1K` **当前为空**，
`_cost_usd` 恒返回 `0.0`；`record_usage(model, pt, ct, 0.0)` 也硬编码 `0.0`。
因此 **`legacy_cost_usd == 0.0` 在 v0.1 一律不能证明真实零** → 映射 unknown。

### 3.2 Usage 映射

与 Wiki 完全同表（Master §6.1）：

| facts | Foundation |
|---|---|
| `usage_object_present=False` | token 字段全 `null`，`source=unknown` |
| 存在且字段明确为 `0` | 该字段 `0`，`source=provider_reported` |
| 存在且字段缺失 | 该字段 `null` |
| provider total 存在 / 缺失 | 精确保留 / `null`，禁止重算 |

补充：`agent/llm.py` 在 `usage is None` 时**既不累加 `tokens_total` 也不调 `record_usage`** ——
所以 seam（Spec 08）能同时观察到"调用发生"与"usage 缺失"两件事，facts 必须分开记录
`call_observed` 与 `usage_object_present`。

### 3.3 Cost 映射

| facts | Foundation |
|---|---|
| `price_entry_present=False`（当前空表） | `amount=null`、`source=unknown`、保留 `currency="USD"` 上下文 |
| `pricing_value_present=False` | 同上 |
| 有效价格 | Decimal amount、`source=price_table`、`pricing_version` 必填 |
| provider 明确报告货币成本 | `source=provider_reported` |
| 只有 `legacy_cost_usd=0.0` | **不足以**证明真实零 → unknown |

**Legacy 数值不变**：本步骤只产生 Foundation facts 与证据，`CaseResult.cost_usd`、
`LLMClient.tokens_total`、Benchmark 判定全部保持原样（Spec 08 接线时同样如此）。

### 3.4 Component provenance sidecar（`observation_ledger.py`）

```text
Coding component provenance
= project-local, in-memory, client-scoped observation support

NOT: 业务成本真相源 / 持久化账务 / 共享契约 / Evidence 去重机制
```

- **client-scoped**：每个 `OpenAICompatClient` 实例一份，不是全局单例
- **in-memory**：无磁盘、无跨进程、无跨仓依赖
- API 形状：

```python
sidecar = ComponentLedger()            # 只在 observe/strict 创建
sidecar.append(facts)                  # 追加最小 component facts
mark = sidecar.cursor()                # case 开始：取游标
components = sidecar.slice(mark)       # case 结束：取本 case 组成项
```

- `slice(mark)` 返回 **mark 之后**的组成项，天然不串入前一 case
- **不设计**新的全局 invocation ID；若既有安全稳定 call ID 已存在可放进 `coding.*` extension，
  **不存在则不创建**（母 Spec §9.1）
- **不做 Evidence 去重**，**不改变** `tokens_total`
- `off` 模式**不创建、不分配、不积累**：sidecar 由 runtime 在 mode 判定后才实例化

### 3.5 故障后组件保留

母 Spec §9.1 step 8：

```text
environment/error case 无模型调用        → 允许空 component set
已有调用后最终失败                        → 保留已观察 components，不得因错误清零
```

因此 `slice(mark)` 只按游标切分，**不做成功/失败过滤**；"无调用"与"调用后失败"由此
产生不同的 CostSummary 语义（`component_count=0` vs `component_count>0`，
`complete` 也随之不同）。

### 3.6 Runtime

与 Wiki 同策略、独立实现：

```text
off     立即返回（且不创建 sidecar）
observe 提取 → 映射 → 记录 sidecar → emit Evidence；失败只产 FAIL 证据与计数
strict  同一路径；失败先 emit FAIL 证据再抛 ContractValidationError
```

- 非法 `AGENT_CONTRACT_MODE` 必须明确失败（FND-MODE-003）
- sink failure counter 不可递归
- `run_id`：显式优先；observe 缺省生成进程级 UUID；strict 缺省直接失败

### 3.7 sanitized_input_facts 的落地形态

```text
coding.legacy.call_observed          bool
coding.legacy.usage_object_present   bool
coding.legacy.field_presence         {token 名: bool}
coding.pricing.entry_present         bool
coding.pricing.table_size            int      ← 空表是最直接的"unknown"证据
coding.currency.context              str
coding.model.name                    str
coding.case.component_count          int      ← 来自 sidecar slice
```

命名空间 `coding.*` 已在 Spec 04 的 facts allowlist 内；不含 prompt / response /
reasoning / 代码正文 / diff / 环境转储。

## 4. 执行顺序

1. `adapters/__init__.py` + 更新 `foundation/__init__.py` 说明
2. `facts.py`
3. `mapping.py`
4. `observation_ledger.py`（sidecar）
5. `runtime.py`（装配 sidecar 生命周期）
6. `tests/contracts/test_foundation_mapping.py`（8 类 fixture）
7. 跑 Spec 06 官方验证命令；跑 Coding 全量既有测试确认零回归
8. **复查 Coding 主仓 HEAD 与 worktree 状态**（该仓全量测试会污染仓库，见长期记忆）

## 5. 验证命令（Spec 06 官方）

```powershell
python -m pytest tests/contracts/test_foundation_mapping.py -q
```

必须覆盖的 fixture：provider usage absent / present、显式零、unknown USD cost、
partial calls before failure、no-call environment error、cursor isolation、
off no-allocation、concurrent client isolation。

## 6. 验收对照

- [ ] sidecar 无磁盘持久化、无跨项目依赖、无 public contract exposure
- [ ] 空 price table 导致 Foundation unknown，不导致 Legacy 数值变化
- [ ] case slice 不串入前一 case components
- [ ] off 模式与未安装 Adapter 前的 state/return 等价
- [ ] 已调用后失败与根本未调用可产生不同 Foundation Summary 语义

## 7. 回滚 / Handoff

尚未接线，删除 `adapters/foundation/` 下新增的四个模块与
`tests/contracts/test_foundation_mapping.py` 即可（`evidence_sink.py` 属 Spec 04，保留）。

Handoff：

- **sidecar 生命周期**：由 runtime 在 mode 判定通过后**惰性创建**；每个 runtime 实例一份
  （client-scoped），不是全局单例；容量上限 10 000 条，超出丢弃最旧项。
- **cursor 归属**：`ledger.cursor()` 同时充当 case 的 begin 与 end 游标。
  `range_slice(start, end)` 是**边界稳定**切片（推荐用法）；
  `slice(mark)` 等价于 `range_slice(mark, cursor())`，取调用时刻的窗口。
- **off 行为**：不分配 sidecar（`ledger_allocated is False`），`begin_case()` 返回 `0`，
  `case_components()` 返回空 —— 与未安装 Adapter 的 state/return 等价。
- **故障后 components 保留规则**：切片只按游标切分、**不做成功/失败过滤**，
  因此「已有调用后失败」保留全部已观察组件（`component_count>0`、`complete=false`），
  「根本未调用」得到空集合（`component_count=0`、`complete=true`）。

## 8. 决策记录（与 Spec 05 共用）

| 决策点 | 结论（2026-09-11 经用户确认） |
|---|---|
| runtime 身份来源 | payload hash 从已安装的 `agent_core` 现场复算；commit 由构造参数注入或读 `AGENT_CONTRACT_COMMIT` |
| 价格表 identity | Coding 没有价格表**文件**，改为对 `MODEL_PRICE_USD_PER_1K` 映射内容做 canonical JSON + SHA256 作为 `price_table_hash`，在 `source=price_table` 时填充必需的 `pricing_version`（与 Wiki 的 pricing.json 快照口径同构） |
| 执行节奏 | 先完整做完 Spec 05，再做 Spec 06 |
| `is_character_estimate` | 仅适用 Wiki（Coding 无字符估算路径） |

### 8.1 实现中发现的语义点（已按规范补齐）

`ComponentLedger.slice(mark)` 是「从 mark 到**调用时刻**末尾」的活动窗口，不是快照。
Spec 06 step 6 要求 "case begin/end cursor"，因此补充了 `range_slice(start, end)`：
两端在取切片前确定，后续追加不会混入。`slice(mark)` 保留为便捷形式，
文档明确要求 mark 在 case 结束时就地消费。两条路径都有测试覆盖。
