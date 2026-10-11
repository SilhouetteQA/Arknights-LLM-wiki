# Spec 02 执行计划 — Foundation Semantic Models

> 关联 Spec：`docs/specs/foundation-contract/02-foundation-semantic-models.md`
> 规范真相源：Master Spec §2、§3.1、§4–6、§12.6、Appendix A.1–A.4
> 目标仓库：canonical authoring in `WIKI_REPO`（Coding 镜像由 Spec 03 的 bundle 同步，本步骤禁止在 Coding 手写）
> Candidate Phase：pre-A
> 前置：Spec 01 `COMPLETE` ✅（commit `00ac1d8`）

## 1. 目标与边界

在 Wiki canonical 仓建立 Foundation v0.1 的**最小规范性数据与行为边界**：ContractMode、Usage、Cost、CostSummary、ErrorEnvelope、extension 基础约束，及其 `contract.md` 规则文本与最小开发期 conformance tests。

**不做**（属后续 Spec）：Evidence DTO/Protocol（Spec 04）、Schema/hash/bundle tooling（Spec 03）、项目 Adapter（Spec 05/06）、producer 接线（Spec 07/08）、ModelRequest/ToolResult/Trace/Evaluation/Checkpoint 契约、`agent_core` 根级 convenience export。

## 2. 文件清单（严格等于 Spec 02 Allowed Changes）

| 文件 | 职责 | 关键不变量 |
|---|---|---|
| `agent_core/__init__.py` | 仅 namespace docstring | 不导出任何符号、不放运行时 |
| `agent_core/contracts/__init__.py` | 包标识 | 不聚合 re-export |
| `agent_core/contracts/version.py` | `CONTRACT_VERSION="0.1.0"` + canonicalization/tooling version 常量 | 不含 maturity state |
| `agent_core/contracts/contract.md` | 全部 Rule ID 的规范性语义、禁止项、示例 | 说明 JSON Schema 只是派生快照 |
| `enums/modes.py` | `ContractMode(OFF/OBSERVE/STRICT)` | 唯一配置入口 `AGENT_CONTRACT_MODE`，非法值必须报错 |
| `enums/sources.py` | `UsageSource`、`CostSource` | 描述认识论来源，不是存储位置 |
| `enums/errors.py` | `ErrorCategory` + `foundation.*` 错误码 | 仅 3 个 category；5 个 v0.1 code |
| `models/base.py` | 统一 base（`extra="forbid"`）+ `JsonValue` + extension 校验器 + 敏感内容防线 | namespace / JSON-only / 16 KiB / depth 4 |
| `models/usage.py` | `Usage` | 非负、`0≠null`、provider total 原样保留、缺失 total 不相加 |
| `models/cost.py` | `Cost`、`CostSummary` | Decimal-string、三字母大写 currency、source/pricing 矩阵、币种冲突先于 complete |
| `models/error.py` | `ErrorEnvelope` | DTO 而非 Exception、`message` 不驱动逻辑、retryable 固定 false |
| `conformance/rules.py` | `@contract_rule(<ID>)` 元数据机制 | 测试函数名不能代替 Rule ID |
| `conformance/test_{usage,cost,cost_summary,extensions,error_envelope,modes}.py` | 核心不变量证明 | 不 import 任何项目模块 |

## 3. Rule ID 覆盖对照

`contract.md` 至少覆盖下列规则，且每条在 conformance 中有落点：

```text
FND-PKG-001/004          agent_core 白名单；根 __init__ 不 re-export
FND-VER-001/002/003/006  lockstep 版本；Payload 不含自身 hash；descriptor 可先于 hash 派生；治理状态不改身份
FND-MAP-001/002          facts 而非 convenience default；保留 presence/provenance
FND-USAGE-001..003       非负/零与 null 互斥；total 原样保留；缺失 total 不得相加
FND-COST-001..013        unknown≠zero、禁隐式 FX、Decimal 字符串、三字母 currency、source 矩阵、pricing_version、真实零、原始币种
FND-CSUM-001..011        counts 非负/勾稽、complete 定义、空集合、币种一致、不声明统一 source
FND-ERR-001..005         DTO 边界、code 驱动、retryable=false、结构化有界、只在声明的边界产生
FND-EXT-001..006         namespace、JSON-only、16 KiB、depth 4、敏感内容禁入、opaque 语义
FND-MODE-001..004        off/observe/strict 语义、共用 extractor、非法配置失败、observe 失败不影响业务
```

## 4. 执行顺序

1. `agent_core/__init__.py` + `contracts/__init__.py`（普通 package，仅 docstring）
2. `version.py`（版本常量，无治理状态）
3. `enums/`（3 个文件）
4. `models/base.py`（base model + JsonValue + extension 校验 + 敏感防线）
5. `models/usage.py`、`models/cost.py`、`models/error.py`
6. `conformance/rules.py` + 6 个测试文件
7. `contract.md`（按 Rule ID 写全，与 4–6 的实际实现逐条对齐）

每步完成后立即跑对应测试；全部完成后跑 Spec 02 的 6 条 Validation Commands。

## 5. 验证命令（Spec 02 官方）

```powershell
python -m pytest agent_core/contracts/conformance/test_usage.py -q
python -m pytest agent_core/contracts/conformance/test_cost.py -q
python -m pytest agent_core/contracts/conformance/test_cost_summary.py -q
python -m pytest agent_core/contracts/conformance/test_extensions.py -q
python -m pytest agent_core/contracts/conformance/test_error_envelope.py -q
python -m pytest agent_core/contracts/conformance/test_modes.py -q
```

⚠️ 这些命令依赖 pytest 的 rootdir 机制把仓库根加入 `sys.path`（`agent_core/`、`contracts/`、`conformance/` 均有 `__init__.py`，向上回溯止于仓库根）。
**若首跑无法 import `agent_core`，则属于「必须修改未列文件」→ 停止并出 Spec deviation report，不得自行加 `conftest.py`。**

本步骤通过**不构成 Cycle Evidence**；正式 L1 必须在 Spec 11 于冻结的 Candidate A 上重跑。

## 6. 验收对照（Spec 02 Acceptance Criteria）

- [ ] Appendix A.2–A.4 每条适用规则都有模型/文档表达 + 测试落点
- [ ] 未知 Cost 无法序列化为 `amount="0", source="unknown"`
- [ ] 显式零 / 空集合 / 全未知 / 部分未知 / 币种冲突 语义可区分
- [ ] ContractMode 非法值明确失败
- [ ] `agent_core` 未出现实现代码或根级 re-export

## 7. 待确认的设计决策

| # | 决策点 | 选项 |
|---|---|---|
| 1 | `contract.md` 正文语言 | A. 中文（与母 Spec / 子 Spec / 项目文档一致）B. 英文（更接近公共契约与未来 `agent-core` 包惯例）C. 英文规范语句 + 中文说明 |
| 2 | 敏感内容 scanner 的拦截强度 | A. key 黑名单 + 内容启发式（路径/长串），命中即拒绝（严格，可能误伤）B. key 黑名单硬拦截 + 内容命中仅记录不拒绝（宽松） |

## 8. 回滚

本步骤尚未被任何项目 Adapter 消费，整体删除新增的 `agent_core/` package 即可回滚，不影响 Wiki 主路径。
