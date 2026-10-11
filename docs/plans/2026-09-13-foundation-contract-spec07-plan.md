# Spec 07 执行计划 — Wiki Producer Observation Seams

> 依赖：Spec 05 `COMPLETE`（账本 23 条事件）
> 目标仓：仅 `WIKI_REPO`
> Candidate Phase：pre-A
> 边界：**第一次改动业务文件** —— 只做行为保持型局部重构

## 1. 目标

把 Wiki 的 6 个 in-scope mapping stage 接到 Spec 05 的旁路 runtime 上，
同时保持模型调用、Langfuse、cost log、Eval summary 与所有业务结果**逐字节不变**。

```text
                 ┌→ Legacy Business Path → Existing Result      ← 完全不变
Input ───────────┤
                 └→ Foundation Adapter → Validation Evidence    ← 本步骤接线
```

## 2. 文件清单

### 2.1 Allowed Changes（规范已列，6 个函数 + 2 个测试）

| 位置 | stage | 插入点 |
|---|---|---|
| `extraction/llm_client.py::chat_completion` | `chat_completion` | 模型成功响应后、Langfuse 分支**之前** |
| `agent/router.py::_llm_intent_rewrite` | `intent_rewrite` | `latency_ms` 计算后、`is_enabled()` 分支之前 |
| `eval/runner.py::_log_cost` | `runner` | 形成 entry/timestamp 后、实际写入前 |
| `eval/judge.py::_log_cost` | `judge` | 同上 |
| `eval/scoring.py::_log_cost` | `scoring` | 同上 |
| `eval/metrics.py::summarize_cost` | `cost_log_summary` | 同一次逐行读取中收集 facts；旧结果形成后发射 |
| `tests/contracts/test_producer_wiring.py` | — | NEW：每个 `(producer_id, mapping_stage)` 至少一个固定响应接线测试 |
| `tests/contracts/test_business_invariance.py` | — | NEW：Wiki 的 off/observe 不变性 |

### 2.2 Spec deviations（2 个文件，均已登记）

**D1 — `arknights_wiki/adapters/foundation/runtime.py`**（不在 Spec 07 的 Allowed Changes 内）：

```python
get_foundation_runtime() / set_foundation_runtime() / reset_foundation_runtime()
detect_repository_commit() / reset_repository_commit_probe()
WikiFoundationRuntime.accepts_observation          # property，producer 最外层短路
WikiFoundationRuntime.observe_summary_entries(...) # 接受已解析条目（Master §8.5 单次读取）
observe_eval_cost_entry(entry, *, stage)           # 模块级窄 helper（Master §8.4 指名的形态）
observe_summary_entries(entries, malformed, ...)   # 模块级窄 helper
```

理由：

1. **访问器无处安放**。六个 producer 只是"多一行观察"，不应各自构造 runtime
   （会每次重算 39 文件的 payload hash 并重载 pricing 快照）。
2. **summary 必须单次读取**。`observe_summary(path)` 会自己再读一遍文件，
   而 Master §8.5 要求"在同一次逐行读取中并行收集 component facts"。
3. **`_emit` 构造防护**：`_build_record` 的校验失败原本会冒出到业务函数，
   与"observe 不改变业务返回"矛盾 —— 现在构造失败只令该 run 失效。

**D2 — `arknights_wiki/adapters/foundation/facts.py`**（不在 Spec 07 的 Allowed Changes 内）：

`extract_usage_from_response` 原本按 `input_tokens` / `output_tokens` 读 provider 属性，
但 OpenAI 兼容响应在 `usage` 上给的是 **`prompt_tokens` / `completion_tokens`**。
这会让 Wiki 的 agent usage producer 在真实响应上**永远只得到 unknown**（把"已报告"错判成"未知"），
Spec 13 的真实冒烟必然暴露。修法是加一张候选表：

```python
USAGE_FIELD_SOURCES = (
    ("input_tokens",  ("prompt_tokens", "input_tokens")),
    ("output_tokens", ("completion_tokens", "output_tokens")),
    ("total_tokens",  ("total_tokens",)),
    ("cache_read_tokens",  ("cache_read_input_tokens", "cache_read_tokens")),
    ("cache_write_tokens", ("cache_creation_input_tokens", "cache_write_tokens")),
)
```

两种命名都接受是**正确**而非将就：OpenAI 经典 Chat Completions 用 `prompt_tokens`，
而新的 Responses 形态与部分兼容网关用 `input_tokens`。Spec 05 的 50 例因此无需改动
（它们用的是后一种命名，仍然命中）。

`version.py`、`generate_schemas.py` 等**不需要**改；本步骤不改 payload，契约身份保持
`payload sha256:45da9d66…c3d854` / 39 文件 / 六类 Schema。

## 3. 关键设计决策

### 3.1 runtime 获取与 off 零开销

```python
def get_foundation_runtime() -> WikiFoundationRuntime:
    # 首次调用：解析 AGENT_CONTRACT_MODE
    #   off      → 缓存一个 mode=OFF、sink=None 的 runtime（零 I/O、不构造 sink）
    #   非 off   → 缓存 WikiFoundationRuntime(sink=FileEvidenceSink(), ...)
    # 之后每次调用只做一次属性访问
```

- `off` 下**不构造 FileEvidenceSink、不读 payload、不读 pricing、不提取 facts**，
  六个 producer 的调用各自在 `_guard()` 处立即返回 —— 这是"off 与未安装 Adapter 等价"的实现
- `AGENT_CONTRACT_RUN_ID` → `run_id`；缺省时 runtime 生成进程级 UUID（strict 缺省即失败）
- `AGENT_CONTRACT_EVIDENCE_DIR` → staging 根（由 Spec 04 的 `FileEvidenceSink` 读取）
- `AGENT_CONTRACT_COMMIT` → `repository_commit`（见 §3.2）

### 3.2 commit 与 cost_amount 的取值口径

**commit**：由 `AGENT_CONTRACT_COMMIT` 提供（见待确认问题 2）。

**cost_amount**：`chat_completion` / `_llm_intent_rewrite` 的 Legacy 成本只在 Langfuse 分支里算，
但 Master §8.2 要求 Foundation 观察**不以 Langfuse 为前提**。因此 seam 在
**provider 明确报告 usage 时**用既有 `compute_cost_rmb(model, tokens_in, tokens_out)`
算出同一个数值并传给观察（只读调用，不改 Langfuse 分支的任何参数）；

```text
usage present → cost_amount = compute_cost_rmb(...)   → 可能得到 estimated / price_table
usage absent  → cost_amount = None                    → unknown（而不是 legacy 的 0.0）
```

**关键**：usage 缺失时**不**调用 `compute_cost_rmb`（它会用 `usage else 0` 产生 0.0，
正是要消歧的 ambiguous zero）。

### 3.3 六个 seam 的具体插入形态

**`chat_completion`**（`llm_client.py`）：

```python
response, rstats = retry_call(_do_create, (), {}, retry_config)
latency_ms = ...
message = response.choices[0].message          # ← 既有行，位置不变

# ── 新增：旁路观察（放在 is_enabled() 之前，使 Foundation 不以 Langfuse 为前提）
get_foundation_runtime().observe_chat_completion(
    response, model=config["model"], stage="chat_completion",
    cost_amount=<usage 存在时 compute_cost_rmb(...)，否则 None>,
)
# ─────────────────────────────────────────────

if is_enabled():                               # ← 既有分支，一个字符都不改
    ...
```

**`_llm_intent_rewrite`**（`router.py`）：同样的形态，插在 `latency_ms` 之后、
`if is_enabled():` 之前，`stage="intent_rewrite"`。

**三个 `_log_cost`**：在 `entry["timestamp"] = ...` 之后、`with COST_LOG.open(...)` 之前加：

```python
get_foundation_runtime().observe_eval_cost_entry(entry, stage="runner"|"judge"|"scoring")
```

helper 内部只做「白名单 entry → facts → mapping → emit」，**不写文件、不改 entry**。
三个函数继续各自独立存在（禁止合并为业务 cost service）。

**`summarize_cost`**：同一次循环里收集 `entries` 与 `malformed` 标识，
Legacy 的 `total` / `steps` / `round` / malformed skip **一行不改**；旧 `result` 形成后：

```python
get_foundation_runtime().observe_summary_entries(entries, malformed, legacy_total=result["total"])
return result                                   # ← 既有返回值，不变
```

malformed 存在时 `observe_summary_entries` 产 FAIL 证据（不改变 Legacy 的跳过行为）。

### 3.4 测试策略

**deepeval 的处理方式**（本步骤第一次实现时走了弯路，已修正）：

`arknights_wiki/eval/scoring.py` 顶层 `import deepeval`，而本机**宿主未安装 deepeval** ——
项目只在 **`deepeval-local` 容器**里跑打分（`Dockerfile.deepeval` 用 Linux wheelhouse 构建，
宿主 pip 装不上，见 `output/devlog.md`）。最初我在测试里用 `sys.modules.setdefault` 注入假
deepeval，结果**污染了 `tests/eval/test_scoring.py`**（它的断言依赖假模块的具体字段值，
而 `setdefault` 让先导入者的假模块全局生效）。

现在的做法：**不注入任何假模块**。

```python
def real_deepeval_available() -> bool:
    """区分"真实安装"（有 __file__）与"测试注入的假模块"（没有 __file__）。"""
```

- 宿主：`scoring` 相关的 3 个用例**明确 skip**，skip 理由写明原因与容器命令
- 容器：真实 deepeval 4.1.8 下**全部执行**，不打折

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "<wiki worktree>:/work:ro" -w /work \
  --entrypoint sh deepeval-local:latest -c \
  'python3 -m pytest tests/contracts -q -p no:cacheprovider'
```

**`test_producer_wiring.py`**（每个 stage 至少一个固定响应测试）：

- monkeypatch `create_client`（模块边界）返回假的 chat client，其 `chat.completions.create`
  返回带/不带 `usage` 的固定响应 —— 不 monkeypatch 业务私有函数
- 三个 `_log_cost`：monkeypatch 模块级 `COST_LOG` 到 `tmp_path`，直接调用并断言
  evidence 的 `producer_id` / `mapping_stage` / `foundation_output`
- `summarize_cost`：造一个含 normal + malformed 行的临时 cost log
- 每个测试前 `set_foundation_runtime(<注入的运行期>)` + 固定 `payload_hash`

**`test_business_invariance.py`**（Wiki cases）：

```text
同一组固定响应下，分别以 off / observe 跑同一条路径，断言：
  - chat_completion 的 (content, message) 与 provider 请求参数逐字段相等
  - _llm_intent_rewrite 的返回值（含 None 兜底路径）相等
  - 三个 _log_cost 写出的 JSONL 行逐字段相等（timestamp 归一后）
  - summarize_cost 返回 dict 完全相等（含缺文件 → {"total": 0.0, "steps": {}}）
  - Langfuse 遥测一致：is_enabled→True 且 record_llm_usage 为 spy，
    断言 off/observe 下调用参数完全相同（latency_ms 归一）
  - observe 下注入 mapping / sink 失败时，以上输出与副作用仍然不变
```

### 3.5 明确不做

`wiki.trace.summary` 保持 `DEFERRED`（不接线）；不碰 Dashboard、offline extraction、
StatsCollector、`eval/report.py`；不合并三个 `_log_cost`；不改 Langfuse 启用条件与 JSONL 格式。

## 4. 执行顺序

1. **deviation**：`runtime.py` 新增 `get/set/reset_foundation_runtime` 与 `observe_summary_entries`
2. `llm_client.py::chat_completion` seam → 立即跑 `tests/test_extraction*` 与既有 LLM 相关测试
3. `router.py::_llm_intent_rewrite` seam → 跑既有 router 测试
4. `runner.py` / `judge.py` / `scoring.py` 三个 `_log_cost` seam
5. `metrics.py::summarize_cost` seam
6. `test_producer_wiring.py` + `test_business_invariance.py`
7. 官方两条验证命令 + Wiki 全量（目标：基线 602 + 新增，0 failed）
8. 复核 `git diff` 的每一行都只增不改语义；确认 Langfuse 分支零改动

## 5. 验证命令（Spec 07 官方）

```powershell
python -m pytest tests/contracts/test_producer_wiring.py -q
python -m pytest tests/contracts/test_business_invariance.py -q
```

## 6. 验收对照

- [ ] `AGENT_CONTRACT_MODE=off` 时不执行 facts/Adapter/sink
- [ ] observe 下注入 mapping/sink 失败时旧返回与副作用不变
- [ ] 固定响应下 off/observe 的 output、decision、Legacy side effects/telemetry 精确一致
- [ ] `wiki.trace.summary` 仍为 `DEFERRED` 且无虚构事件

## 7. 回滚 / Handoff

运行时回滚：`AGENT_CONTRACT_MODE=off`。代码回滚：只移除各 producer 的 observation 调用与
为 seam 抽取的窄 helper，保留全部原业务逻辑（Legacy 从未消费 Foundation 输出）。

Handoff 按 stage 列出：固定输入、Legacy invariant、Evidence producer identity。

## 8. 决策记录（2026-09-13 经用户确认）

| 决策点 | 结论 |
|---|---|
| deviation 形态 | **单文件 `runtime.py` 集中新增**（D1）—— 比新开 `seams.py` 少一个文件 |
| `repository_commit` 来源 | **env 优先 + git 回退**：`AGENT_CONTRACT_COMMIT` 优先；未设置时惰性执行**一次只读** `git rev-parse HEAD` 并缓存；失败即放弃（observe 记日志、strict 失败），绝不写仓库、绝不抛错 |
| 执行粒度 | 6 个 seam 一次做完，含两类测试 |

### 8.1 实现中发现并修复的缺陷（D2）

`facts.extract_usage_from_response` 读错了 provider 属性名（见 §2.2 D2）。
Spec 05 的实现与它自己的 50 例测试**同时**用了错误命名，所以两轮验证都没暴露；
Spec 07 的接线测试用真实 provider 字段名（`prompt_tokens`/`completion_tokens`）构造固定响应时立刻失败。
这属于"测试与实现共享同一个错误假设"，已通过候选表修复，且两种命名都兼容。

### 8.2 一处规范解读

Master §8.5 第 3 步是"旧 result 完成后旁路生成 CostSummary Evidence"。
`summarize_cost` 对**缺文件**有 early return，原实现会漏掉这条路径的证据。
现改为两条路径都在 result 形成后观察 —— 返回值逐字节不变，但 Smoke 能看到
summary producer 确实跑过（`component_count=0`、`complete=true`，即"没有组成项"而非"成本为零"）。

## 9. 执行结果

**宿主（Windows，无 deepeval）**

| 项目 | 结果 |
|---|---|
| `tests/contracts/test_producer_wiring.py` | 11 passed + 2 skipped（scoring 相关） |
| `tests/contracts/test_business_invariance.py` | 13 passed + 1 skipped（scoring 相关） |
| `tests/contracts` 全量 | 75 passed + 3 skipped |
| Wiki 全量 | **620 passed / 10 skipped / 0 failed**（= worktree 基线 595+7 加新增 25 通过 + 3 skip） |

**容器（`deepeval-local`，真实 deepeval 4.1.8 + pytest 9.1.1）**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "<wiki worktree>:/work:ro" -w /work \
  --entrypoint sh deepeval-local:latest -c \
  'python3 -m pytest tests/contracts -q -p no:cacheprovider'
```

结果 **78 passed / 0 skipped** —— 宿主上因缺 deepeval 而 skip 的 3 个 `scoring` 用例
在真实 deepeval 下全部真正执行。

**复核结论**

- `git diff` 复核：`is_enabled()` 分支、`record_llm_usage` 参数、JSONL 序列化、rounding、
  缺文件早退返回值、append 次数全部零改动；六个 seam 只增观察调用
- 契约身份未变（本步骤不进 payload）：payload `sha256:45da9d66…c3d854` / 39 文件
- 账本追加 Spec 07 的 4 条事件（27 条，Spec 01–07 全部 COMPLETE）

**说明**：账本 `VALIDATED` 事件记录的是当时的验证结论（当时测试用的是假 deepeval）。
本步骤去掉假模块、改为容器内真实执行属于**测试实现方式**的修正，不改变 spec 状态，
因此**不追加账本事件**（账本是状态迁移的 append-only 记录，没有"重新验证"这一迁移），
改动只在本文档、提交信息与项目记忆中留痕。
