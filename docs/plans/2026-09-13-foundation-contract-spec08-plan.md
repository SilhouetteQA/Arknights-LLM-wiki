# Spec 08 执行计划 — Coding Producer Observation Seams

> 计划日期：2026-09-13　|　Spec：`08-coding-producer-observation-seams.md`
> 目标仓库：`CODING_REPO`（`D:\AI project\_worktrees\foundation-contract\coding`）
> 前置：Spec 06 `COMPLETE`（Coding `adapters/foundation/` 已建 facts/mapping/runtime/ledger）

## 1. 目标

把 Coding 的七个 stage variant 接到 Spec 06 已建的旁路 runtime：

| producer | stage | 业务函数 | 现有 helper |
|---|---|---|---|
| `coding.agent.llm_usage` | `openai_compat` | `agent/llm.py::chat` | `observe_chat_completion` |
| `coding.trace.generation_usage` | `langfuse_generation` | `tools/tracing.py::record_usage` | `observe_usage`（需改） |
| `coding.benchmark.case_cost` | `normal` / `environment_error` / `error` | `benchmark/runner.py` 三个分支 | `begin_case` + `observe_case_cost` |
| `coding.trace.summary` | `sdk` / `clickhouse` | `tools/report_trace.py` 两个 summarize | `observe_trace_summary` |

每个 seam 只增**一行观察**（或几行 presence 提取），既有分支与数值一行不改。

## 2. Allowed Changes 逐文件映射

| Allowed 文件 | 改动 | 备注 |
|---|---|---|
| `agent/llm.py::chat` | coercion 前加 openai_compat 观察；`record_usage` 传 `contract_facts` | 只增不改 |
| `tools/tracing.py::record_usage` | 加 keyword-only `contract_facts`；非 off 时 langfuse_generation 观察 | 只增不改 |
| `benchmark/runner.py` | `_run_one_case` 开头 `begin_case()`；三个分支形成 CaseResult 后 `observe_case_cost(mark, stage)` | 只增不改 |
| `tools/report_trace.py` | 两个 summarize 遍历时收集 presence，形成旧 TraceSummary 后 emit | 只增不改 |
| `tests/contracts/test_producer_wiring.py` | 新建 | — |
| `tests/contracts/test_business_invariance.py` | 新建（Coding cases） | — |

## 3. ⚠️ 需要的 Spec deviation（1 个文件）

**`adapters/foundation/runtime.py` 不在 Spec 08 的 Allowed Changes 内，但必须新增进程级访问器与窄 helper**，
与 Wiki Spec 07 的 D1 对称，否则 4 个 producer 无处取 runtime、每次调用都要重算 39 文件的
payload hash 并重载价格表：

```python
def get_foundation_runtime() -> CodingFoundationRuntime   # 进程级惰性单例
def set_foundation_runtime(runtime) -> None               # 受控注入（测试 / Spec 13 smoke）
def reset_foundation_runtime() -> None                    # 测试用

# 进程级访问器附带的短路与 git 回退
CodingFoundationRuntime.accepts_observation  # off 下 False，producer 最外层短路（零 I/O）
detect_repository_commit()                    # 惰性只读 git rev-parse HEAD，最多一次，失败即放弃

# 模块级窄 helper（避免四个业务文件各自构造 runtime / 重复价格表加载）
observe_openai_compat(response, model, ...)          # chat 用（openai_compat，写 ledger）
observe_langfuse_generation(model, pin, pout, cost)  # record_usage 用（langfuse_generation，不写 ledger）
observe_case_cost_entry(mark, stage)                 # benchmark 用
observe_trace_summary_entry(components, usage_facts, stage)  # report_trace 用
```

**为什么必须**：与 Wiki Spec 07 完全同构 —— 六个/四个 producer 各构造 runtime 会重复
重算 39 文件 payload hash + 重载价格表；进程级惰性单例是唯一不重复代码又不改签名的做法。
`detect_repository_commit` 沿用 Wiki Spec 07 已批准的「env 优先 + git 回退」决策（Coding 的
`resolve_repository_commit` 目前只读 env，需补 git 回退）。

**不改** payload、不生成 Schema、不改 `generate_schemas.py`。契约身份保持
`payload sha256:45da9d66…c3d854` / 39 文件 / 六类 Schema / 68 条规则。

## 4. 七个 stage 的接线细节

### 4.1 `openai_compat`（`agent/llm.py::chat`）

现状（`llm.py` 184–191 行）：

```python
resp = self._client.chat.completions.create(**params)
usage = getattr(resp, "usage", None)
if usage is not None:
    pt = int(getattr(usage, "prompt_tokens", 0) or 0)   # ← coercion
    ct = int(getattr(usage, "completion_tokens", 0) or 0)
    self.tokens_total["prompt"] += pt
    self.tokens_total["completion"] += ct
    record_usage(self.model, pt, ct, 0.0)
```

v0.1：在 `usage = getattr(...)` **之后、`pt = int(...)` 之前**（coercion 前）插入：

```python
usage = getattr(resp, "usage", None)
observe_openai_compat(resp, model=self.model)   # ← 旁路：emit + 写 ledger（stage=openai_compat）
if usage is not None:
    ...
    record_usage(self.model, pt, ct, 0.0, contract_facts=True)
```

- `observe_openai_compat` 内部调 `runtime.observe_chat_completion(resp, model, legacy_cost_usd=0.0, cost_is_default=True)`，
  从 raw `resp.usage` 提取 presence（`prompt_tokens`/`completion_tokens`/`total_tokens`），
  映射 Usage + unknown USD Cost，**写 ledger** 供 benchmark case summary 用。
- 放在 `is_enabled` 无关处，满足「Foundation 不依赖 Langfuse 开启」。
- `usage is None` 时仍观察（call_observed=True, usage_object_present=False），Legacy 不调 record_usage 的分支不变。

### 4.2 `langfuse_generation`（`tools/tracing.py::record_usage`）

现状签名：`record_usage(model, tokens_in, tokens_out, cost_usd, extra=None)`。

v0.1：加 keyword-only `contract_facts=None`，在旧逻辑**之前**：

```python
def record_usage(model, tokens_in, tokens_out, cost_usd, extra=None, *, contract_facts=None):
    if contract_facts is not None:
        observe_langfuse_generation(model, tokens_in, tokens_out, cost_usd)  # 旁路 emit-only
    c = get_client()
    ...
```

- `observe_langfuse_generation` 内部调 `runtime.observe_usage(...)`，stage=`langfuse_generation`，**不写 ledger**（见 §5 语义修正）。
- `contract_facts` **不得**合并进 Langfuse `extra` / `meta`（本实现根本不碰它们）。
- 现有其它调用方（`tests/test_tracing.py::test_record_usage_disabled_noop`）未传 → 保持兼容。

### 4.3 benchmark 三个 stage（`benchmark/runner.py`）

`_run_one_case` 开头（`start = time.monotonic()` 之后）取游标：

```python
mark = observe_case_begin()   # = get_foundation_runtime().begin_case()（off 返回 0）
```

三个分支在**先完整形成原 CaseResult 后**各自 emit（`CaseResult` 构造一字节不改）：

- `_environment_error_result(...)` 构造后 → `observe_case_cost_entry(mark, stage="environment_error")`
- `_case_result(...)` 构造后 → `observe_case_cost_entry(mark, stage="normal")`
- `_run_one_case` 的 `except Exception` 分支构造后 → `observe_case_cost_entry(mark, stage="error")`

`observe_case_cost_entry` 内部调 `runtime.observe_case_cost(mark, stage=...)`，从 ledger slice 取
components 映射 CostSummary。语义：
- `environment_error`：Agent 未执行 → slice 为空 → 空 Summary（`complete=true`、currency null）
- `error`：若已发生模型调用 → slice 保留 partial components → incomplete Summary；无调用 → 空 Summary
- `normal`：slice 含本 case 全部组件 → 完整 Summary

### 4.4 `sdk` / `clickhouse`（`tools/report_trace.py`）

两个 summarize 都在**原始 observation/row 仍可见时**收集 presence，形成旧 `TraceSummary` **后** emit：

- `_summarize_trace`（sdk）：遍历 `obs` 时用 `getattr` 安全读每个 observation 的 usage/cost
  （SDK v4 字段，缺失即 absent），收集成 `components` 与可选 `usage_facts`；旧
  `TraceSummary(tokens_prompt=0, cost_usd=0.0)` 的硬编码**保持不变**。返回前
  `observe_trace_summary_entry(components, usage_facts, stage="sdk")`。
- `_summarize_events`（clickhouse）：遍历 rows 时，在 `_as_float(total_cost)` **之前**区分
  `total_cost is None`（absent）与显式零，对每个 generation row 形成 component；旧
  `cost_usd += _as_float(total_cost)` 累加**一字节不改**。返回前
  `observe_trace_summary_entry(components, None, stage="clickhouse")`。

保持：SDK 优先 / ClickHouse fallback 的 `fetch_trace` 控制流、`TraceError` 语义、latency 计算、
`trace_report_md` 渲染 —— 全部不碰。

## 5. ⚠️ 语义修正：`observe_usage` 改为 emit-only

母 Spec §9.3 明确 `langfuse_generation` 只「旁路观察」，**不 append ledger**。否则同一 provider
调用会因 openai_compat（chat）与 langfuse_generation（record_usage）各写一次 ledger，导致 benchmark
的 case summary **double-count**。

`observe_usage` 当前通过 `_record` 写 ledger（Spec 06 实现）。修正：

- `observe_chat_completion` → `_record(..., write_ledger=True)`（openai_compat，写 ledger）
- `observe_usage` → `_record(..., write_ledger=False)`（langfuse_generation，不写 ledger）

连带调整 Spec 06 测试：`test_case_cost_stages_map_to_case_cost_producer` 用 `observe_usage` 写 ledger，
需改用 `observe_chat_completion`（真正的「写 ledger」入口）；`test_cursor_slice_does_not_leak_previous_case_components`
与 `test_client_isolation_between_two_runtimes` 同理（意图是测 ledger 隔离，改用 `observe_chat_completion`）。

## 6. 验证

```powershell
cd D:\AI project\_worktrees\foundation-contract\coding
D:\CodexPython312\python.exe -m pytest tests/contracts/test_producer_wiring.py -q
D:\CodexPython312\python.exe -m pytest tests/contracts/test_business_invariance.py -q
```

必须覆盖七个 stage variant：`openai_compat`、`langfuse_generation`、`normal`、`environment_error`、
`error`、`sdk`、`clickhouse`；同一模型调用产生两条 producer evidence（`coding.agent.llm_usage` +
`coding.trace.generation_usage`）是**预期而非重复错误**。

## 7. 验收对照（Spec 08 Acceptance Criteria）

- [ ] off/observe 固定响应的业务不变量精确一致
- [ ] Langfuse client absent 时原 no-op 不变，但 Foundation observation 不依赖它
- [ ] CaseResult 原字段与报告字节/语义不变
- [ ] SDK/ClickHouse fallback 次序与 TraceError 不变
- [ ] sidecar data 不跨 case 泄漏
- [ ] 同一模型调用两条 producer evidence 均为 PASS，ledger 不 double-count

## 8. 决策记录（已确认）

1. **deviation**：`runtime.py` 加进程级访问器（采纳）—— `get/set/reset_foundation_runtime` +
   `accepts_observation` + `detect_repository_commit`（git 回退）+ 四个模块级窄 helper。
2. **语义修正**：`observe_usage` 改 emit-only（采纳）—— `_record` 加 `write_ledger` 参数，
   `observe_chat_completion` 写 ledger、`observe_usage` 不写；Spec 06 的 6 处测试改用
   `observe_chat_completion` 测 ledger 行为。
3. **执行粒度**：七个 stage 一次做完（采纳）。

**实现精化（相对计划 §4.4）**：`observe_trace_summary_entry` 最终接收**原始 presence rows**
（每项 `{model, cost, cost_present}`），由 runtime 内部用价格表构造 components —— 而不是让
`report_trace.py` 直接构造 `CodingLegacyCostFacts`（那会迫使 report_trace 依赖价格表）。

**附带修复（接线测试暴露的原始 bug）**：`_summarize_events` 缺 `latency = 0.0` 初始化，
空 trace（所有 row 无时间戳）时抛 `UnboundLocalError`（`_summarize_trace` 有初始化、它没有）。
已补上，有数据时的行为一字节不变。

## 9. 回滚 / Handoff

先切 off；代码回滚只移除 observation calls、`contract_facts` 参数与 sidecar hooks，保留原
provider/trace/benchmark/report 流程。Handoff 按 stage 记录 invariant 与 sidecar slice 边界。
