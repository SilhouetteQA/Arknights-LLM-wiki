# W11-α — Pre-extraction Benchmark Baseline 冻结规格（2026-10-12）

> 依据：Foundation Contract 母 Spec §24 `Benchmark Freeze and Quality Gate`（`docs/specs/2026-09-10-dual-agent-foundation-contract-master-spec.md:2000-2045`）
> 规则：CLAUDE.md U-03（评测优先）· U-10（成本性能量化）· U-13（上下文预算）· U-14（评估基准建库）· N-01（不自行做重大决策）· 第六章升级工作流
> 上游状态：Spec 17 `Foundation Family Extraction Gate` = `NOT_READY_FOR_EXTRACTION`，其中 `reproducible_quality_gate` = **FAIL**（`docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md` §13）
> 本 Spec 的定位：**只补齐该 FAIL 项所需的冻结件**，不改变 Gate 结论，不触碰任何抽取动作
> 用户决策（2026-10-12 交流确认）：
>   - judge 口径：**冻结在当前统一 judge**（`deepseek/deepseek-v4.1-flash` @ `api.commandcode.ai`），显式记录身份并声明与 0.857 不可比
>   - Wiki 语料：**先补齐 `no_answer` / `hallucination_bait` 两类**（U-14 要求 8 类）再冻结
>   - Coding 侧：**先补最小元数据再冻结**（改动限于 `benchmark/` 元数据与固定，不动 agent/adapters）

---

## 1. 背景与目标

### 1.1 背景

母 Spec §24 明文规定顺序不可颠倒：

```text
BenchmarkSpec freeze → immutable pre-extraction baseline
→ agent-core extraction candidate → same-config candidate benchmark → comparison
```

即：**在冻结 BenchmarkSpec 与不可变 baseline 之前，不得进入抽取**。当前 Spec 17 的 eligibility 公式中
`reproducible_quality_gate` 判定为 FAIL，理由记录为「尚未冻结 pre-extraction BenchmarkSpec 与 immutable
baseline」。这是 12 项里唯一 100% 落在当前权限内、且**不需要修改任何产品代码**即可推进的缺失项。

Step 1 只读探测（`output/_w11_probe/w11a_step1_report.md`）给出了三个决定性事实：

1. **judge 身份已经漂移**：`arknights_wiki/eval/config.py:123-133` 的 `get_judge_model()` 现在返回
   **与 agent 相同的模型**（统一 provider `command_goat`），历史基线 `report_v1_mimo.md` 的 judge
   `mimo-v2.5`（旧 opencode 网关）当前返回 **HTTP 400**，不可用。
   ⇒ 0.857 基线**无法原样复现**，且当前 Wiki 侧实质是**自评**。
2. **两仓都缺 §24 要求的全部冻结字段**：无 corpus hash、无 harness commit、无 judge 版本、无
   temperature/seed、无失败计数、无预登记容差；Coding 侧另缺 fixture commit、真实 executor、side-effect policy。
3. **测量环境不完整**：Docker 引擎当前不可用（Coding benchmark 只能用 `local` 执行器）；
   Wiki 侧 `max_tokens=16` 时出现「16 个 completion token 但 content 为空」——小额 token 预算会被推理消耗。

### 1.2 目标

产出一套**可复算、可冻结、可判定**的 pre-extraction 基线证据，使 Spec 17 的
`reproducible_quality_gate` 从「无证据」变为「有据可查」，并成为未来 extraction candidate 的唯一对照标尺。

**非目标**：不改变 Spec 17 的 Gate 结论（其余 5 项仍 FAIL），不产生任何抽取候选，不重跑 L1/L2/L3 证据链。

---

## 2. 现状分析（Step 1 实测摘要）

| 维度 | Wiki 现状 | Coding 现状 |
|---|---|---|
| 语料 | `questions_draft.jsonl` 100 题 / **6 类**（缺 `no_answer`、`hallucination_bait`）；runner 默认 `questions.jsonl` **不存在** | `benchmark/cases/**` **5 个 case**（bug 2 / feature 1 / test 1 / refactor 1 / domain 0） |
| 选样 | `--limit` 取文件头部，**顺序敏感且顺序不记录** | 全量、顺序 for 循环、无 limit/seed |
| 版本记录 | 结果行无 model/provider/temperature；报告头无 commit（`eval/report.py:27-32`） | `metadata.git_commit` 记的是 **harness** HEAD，非 fixture commit |
| judge | 与 agent 同模型（自评）；judge note 硬编码且过期（`report.py:10`） | 与 agent 共用同一 `LLMClient`（自评） |
| 聚合 | `_mean` 静默丢 null（`eval/metrics.py:30-32`），分母会漂移；失败次数不记录 | — |
| 成本 | judge 侧精确记录；agent 侧按字符估算并标 `estimate` | `MODEL_PRICE_USD_PER_1K = {}` ⇒ `cost_usd` 恒 **0.0**（假值） |
| 执行器 | direct（无副作用）/ http（需 localhost:8000） | Docker 不可用；`executor` 字段写配置值，实际由 `KA_EXECUTOR` 决定 ⇒ **可谎报** |
| 既有基线 | `report_v1_mimo.md` overall 0.857（judge=mimo-v2.5，无 commit 记录） | **不存在** benchmark 报告 |
| 副作用 | 只写 `output/eval/**`；工具只读检索；有 `--dry-run` | 运行时 `gh repo clone` + 沙箱内写文件；无 approval_dir ⇒ 不 push/PR；**无 dry-run** |

---

## 3. 技术方案

### 3.1 BenchmarkSpec 字段定义

#### Wiki（对齐母 Spec §24 的 10 项）

| §24 字段 | 落地形式 |
|---|---|
| corpus hash | 冻结 questions 文件的 canonical-JSONL 字节 sha256 + `materials/*.json` 各文件 sha256 |
| case IDs | 冻结文件的**有序 id 列表**（含条数），随 MANIFEST 固化 |
| reference data | `benchmarks/arknights_bench/materials/**` 的哈希清单（题目的 `material_refs` 校验用） |
| runner version | harness git commit（写入每个结果行与报告头） |
| judge / scoring version | judge 模型 + provider + base host + judge prompt sha256 + `eval/scoring.py` 与 `eval/metrics.py` 的 commit |
| model / provider | agent 模型 + provider + base host（写入每行） |
| temperature / reasoning | 逐节点 temperature 常量（0.1 / 0.3）与 `max_tokens` 写入结果元数据；**空 content 记为失败，不得记为 0 分** |
| prompt / template version | `arknights_wiki/agent/prompts.py` 等提示词文件的 sha256 |
| aggregation rules | 聚合规则版本常量；`overall` 的**显式分母**与 `judge_failure_count` / `null_metric_count` |
| pre-registered tolerances | 跑批**前**写入 Spec 的容差表（见 3.5） |

#### Coding（对齐母 Spec §24 的 9 项）

| §24 字段 | 落地形式 |
|---|---|
| case set hash | 5 个 case 文件 + 5 个 gold diff 的排序后 sha256 清单 |
| repository commit / fixture state | 新增 `benchmark/cases.lock.json`：逐 case 记录 `repository_commit`；运行时解析出实际 commit 并写入报告 |
| model / provider | 写入报告（含 base host） |
| executor and sandbox policy | 记录**实际执行器**（取 `sandbox_executor()` 内的真实分支，而非配置值）+ 镜像/CPU/内存/pids/network 策略 |
| iteration limit / timeout | 逐 case `max_iterations` + `KA_SETUP_TIMEOUT_S` / `KA_LLM_TIMEOUT_S` / `KA_LLM_MAX_RETRIES` 写入报告 |
| judge version | judge prompt sha256 + judge 模型；**显式标注「judge 与 agent 同模型＝自评」** |
| resolution definition | 版本常量（`test_pass AND judge PASS`） |
| side-effect policy | 新增 `side_effect_policy: "read_only"` 字段（benchmark 路径本就无 approval_dir，属**声明已有事实**） |
| pre-registered tolerances | 同 Wiki，跑批前固化 |

### 3.2 Wiki 语料补齐（U-14 的 8 类）

新增两类各 **≥10 条**（对齐 W0 验收标准「每类 ≥10 条」），100 → **≥120 题**：

- `no_answer`：语料内确实无答案的问题（如询问不存在于 5,213 实体/事件索引中的对象），期望 Agent **明确弃答**而非编造；
- `hallucination_bait`：预设错误前提的问题（如把不存在的身份关系当既成事实），期望 Agent **指出前提错误**。

约束（W0 备注要求）：**必须人工构造，不得 LLM 生成**。执行方式：由我起草候选（依据 `materials/**` 与实体索引构造），
**交用户抽验后方可入冻结集**（N-01）。若现有 `eval/metrics.py:9-18` 的两类判定逻辑不完整，
同步补一条纯规则指标 `abstention_accuracy`（不引入 LLM 判定）。

### 3.3 最小测量仪表化

| 仓 | 文件 | 改动性质 |
|---|---|---|
| Wiki | `arknights_wiki/eval/runner.py` | 结果行增补 model/provider/base_host/temperature/max_tokens/commit/prompt_sha256 |
| Wiki | `arknights_wiki/eval/report.py` | 报告头写完整 metadata；**删除硬编码的过期 judge note** |
| Wiki | `arknights_wiki/eval/metrics.py` | 输出 `judge_failure_count` / `null_metric_count` 与显式分母 |
| Coding | `benchmark/report.py` | metadata 增补 provider/base_url/temperature/max_tokens/实际 executor/sandbox policy/iteration+timeout/resolution 版本/side_effect_policy/judge prompt sha |
| Coding | `benchmark/loader.py` | case schema 增可选 `repository_commit`；读取 `cases.lock.json` |
| Coding | `benchmark/runner.py` | `cost_usd` 改为 **`null` + `cost_source: "unknown"`**（presence-aware：不得继续写 0.0 假值），或在价格表补齐后写真实值 |

**边界**：以上均不触及 imports、dependencies、packaging、Adapter、`agent_core/**`，
因此不落入 Spec 17 的 `Forbidden Actions`。

### 3.4 冻结与不可变产物

```text
Wiki:
  benchmarks/arknights_bench/frozen/w11a-v1/questions.jsonl        # 冻结语料（≥120 题）
  benchmarks/arknights_bench/frozen/w11a-v1/MANIFEST.json          # corpus hash / case ids / materials hashes
  output/eval/w11a_baseline/benchmark-spec.json                    # 10 字段
  output/eval/w11a_baseline/{results.jsonl, results_scored.jsonl, report.md}
  output/eval/w11a_baseline/SHA256SUMS

Coding:
  benchmark/frozen/w11a-v1/{cases.lock.json, MANIFEST.json}        # 9 字段
  output/benchmark/w11a-baseline/{report.json, report.md, benchmark-spec.json, SHA256SUMS}
```

不可变性：上述产物一经生成，**只读不改**；后续对比一律读冻结件。任何修正都必须形成 `w11a-v2` 新目录，
并在 Spec 中记录 `SUPERSEDED` 原因（与 Candidate A 冻结同一纪律）。

### 3.5 预登记容差与复跑判定（跑批前固化）

| 指标类别 | 判定规则 |
|---|---|
| 确定性指标（`tool_selection_accuracy`、`task_completion`、Coding 的 `test_pass` / `resolution`） | **必须完全一致**，否则判 FAIL |
| 随机 LLM 质量（`answer_correctness` / `faithfulness` / `citation_accuracy` / `hallucination` / `overall`） | 复跑均值差 **≤ ±0.03** 且逐题一致率 ≥ 90%（阈值本文即预登记，**不得跑完再定**） |
| judge 失败率 / null 指标占比 | ≤ **5%**，超出即判本次基线不可用 |
| 安全与副作用 | **零容忍**：未经批准 push/PR、sandbox boundary violation、approval bypass 任一出现即 FAIL |

复跑方式：同 corpus / config / model / judge / runner 下**再跑一遍全量**，用上述规则判定，判定脚本与输出一并冻结。

### 3.6 执行编排与成本

- 先 `--dry-run` 报数 → 用户确认 → 执行（沿用 W0 的既有纪律）。
- Wiki 主口径 = **direct**（与 0.857 同口径，可解释）；`http` 作为可选第二口径，需先起 server，默认不跑。
- 成本量级（Step 1 实测估算）：judge 侧 100 题 ≈ **¥0.180** ⇒ 120 题 ≈ ¥0.22/轮；复跑 ×2；
  agent 侧按 DeepSeek 计价另计（同一份 `cost_log.jsonl` 口径）。
- Coding 侧：Docker 不可用时使用 `local` 执行器（历史实测 12 次调用 / 83s），**并把「实际执行器=local」
  写入报告**；跨执行器结果不可比，需在报告中声明。

---

### 3.7 冻结口径与已决事项（2026-10-12）

| 事项 | 决定 | 依据 |
|---|---|---|
| 取值域新增 `expected_behavior="reject"` / `route="reject"` | **接受并显式声明** | base 100 题实测只用 `complex 62 / simple 38`；`arknights_wiki/eval/metrics.py:99` 存在 `reject` 真实分支。冻结 MANIFEST 必须记录取值分布 |
| 取值域新增 `meta_eval.verdict="skipped"` | **接受**；冻结过滤**不得**要求 `verdict=="pass"` | 元评估是作者辅助而非测量；本批**未跑** LLM 元评估，拒绝伪造 `pass`（base 取值为 pass 92 / reject 5 / review 3） |
| 拒绝词白名单（`metrics.py:100`） | **暂不扩建**，登记为已知限制 | 它是确定性指标，凭空放宽会掩盖问题。基线报告的覆盖率与 `task_completion` 分布将作为证据；若出现系统性假阴性，形成 `w11a-v2` 并登记 SUPERSEDED 原因 |
| 既有 `manual_draft.jsonl`（13+13） | **不并入冻结集** | 实测缺 `route`/`chapter_check`/`material_refs`/`meta_eval` 四个字段、`expected_behavior` 混用（complex 11 / reject 15）、`answer_key.evidence` 为空（无验证证据） |
| 被审阅字节 = 被冻结字节 | **强制校验** | `scripts/eval/freeze_corpus.py` 要求 `--reviewed-sha256` 等于审阅文件哈希；不匹配即中止，防止冻结未经审阅的内容 |
| T6 执行拆分 | **T6a Wiki 先行；T6b Coding 随后** | Coding 侧需 GitHub clone + 执行器（Docker / 网络就绪后执行）；若阻塞则如实记 `BLOCKED`，不放宽任何标准 |

### 3.8 Coding 侧已实现的测量字段（T3，2026-10-12）

在 Coding 仓 `feature/pre-extraction-baseline` 上落地（提交 `66302c7`，31 条改动 / 6 文件，`pytest` 91 passed）：

`RunMetadata` 增补 `provider` / `base_url` / `temperature` / `max_tokens` / `executor_actual` / `sandbox_policy` /
`iteration_limits` / `timeouts` / `resolution_definition_version` / `side_effect_policy` / `judge_prompt_sha256`；
`cost_usd` 不再是假 `0.0`（价格表为空时写 `null` + `cost_source="unknown"`）；
`loader` 支持可选 `repository_commit` 与 `cases.lock.json`；`docker_sandbox` 记录**实际**执行器与生效 sandbox 策略。

**已知缺口（必须随冻结清单披露，不得掩饰）**：
1. `temperature` / `max_tokens` 目前记为 `null` —— Coding 的 `LLMClient` 不发送这两个参数（provider 默认值）。
   要在冻结中固定真实采样参数，需要改 `agent/llm.py`（超出 T3 范围，另立决定）。
2. `benchmark/frozen/<ver>/cases.lock.json` 尚未编写（缺真实 fixture commit）→ `repository_commit` 仍为空字符串。
3. `sandbox_policy.executor` 在无 Docker 环境下只能回显声明值；docker 分支的实际执行器记录未在本机验证。



## 4. 验收标准

1. 两仓 BenchmarkSpec 的 §24 字段**全部有值**，且任何一方都可从冻结件重算出相同哈希。
2. `output/eval/w11a_baseline/` 与 `output/benchmark/w11a-baseline/` 产物齐全、带 SHA256SUMS、写明 harness commit。
3. Wiki 冻结语料 **8 类各 ≥10 题**。
4. 复跑判定脚本产出 `REPRODUCIBLE` / `NOT_REPRODUCIBLE` 结论并写入报告；非确定性指标在预登记容差内。
5. 安全与副作用零容忍项 = **0**。
6. Spec 17 的 `reproducible_quality_gate` 可被引用为「已冻结 + 已复跑验证」；
   **Gate 总判定仍为 `NOT_READY_FOR_EXTRACTION`**（其余 5 项未变），且报告中如实写明。

---

## 5. 风险与取舍

| 风险 | 影响 | 取舍 |
|---|---|---|
| `mimo-v2.5` 不可得（HTTP 400） | 与 0.857 不可比 | **接受**：重建基线并在 Spec/报告中显式声明不可比，而不是伪造可比性 |
| judge 与 agent 同模型（自评） | 指标偏高、系统性偏差 | **接受并标注**：记录为已知限制；未来 judge 分离后须重建基线 |
| Docker 不可用 | Coding 侧执行器与 L3 记录不一致 | 使用 `local` 并**显式标注实际执行器**；不把跨执行器结果当同一标尺 |
| 20 道新题质量不足 | 基线可信度下降 | 人工构造 + 用户抽验后才入冻结集 |
| 随机性 | 复跑不一致 | 容差**跑批前预登记**；超出即如实判 NOT_REPRODUCIBLE |
| 改动 Coding `benchmark/` 代码 | 触碰另一仓 | 已获用户批准（D3）；改动限定元数据与固定，不触 agent/adapters/imports/packaging |

---

## 6. 范围外（明确不做）

- ❌ 不创建/发布 `agent-core` distribution，不删除任何 repo-local mirror，不改 imports / dependencies / packaging
- ❌ 不修改任何 Adapter（`arknights_wiki/adapters/foundation/**`、`adapters/foundation/**`）
- ❌ 不重跑或改写 Cycle 1 的 L1/L2/L3 证据，不触碰 Candidate A / Evidence B / Finalization C
- ❌ 不启动 Cycle 2、不提出 v0.2 字段或 Schema 变更（Spec 16 仍为 `NO_ARTIFICIAL_V0_2`）
- ❌ 不改 agent 产品逻辑（router / graph / planner / tools / prompts 的行为语义）
- ❌ 不扩大剧情数据量（U-02）；本任务只增删**评测题目**，不增删剧情语料

---

## 7. 与 Spec 17 门禁的对应关系（诚实预期）

| eligibility 条件 | 本任务后 |
|---|---|
| `reproducible_quality_gate` | ❌ FAIL → ✅ **有据可查（本任务目标）** |
| `duplicate_adapter_evidence` | ⚠️ PARTIAL → 本任务附带产出量化审计（723 共享行 / 500–650 可共享行 / 9 条抽象税），为后续裁定提供证据，但**不自行改判** |
| `cycle_2_complete` / `real_feedback_revision_exists` | 仍 FAIL（需真实 Contract defect，本任务不产生） |
| `rollback_verified` | 仍 FAIL（需 mirror rollback 演练，本 Spec 范围外） |
| `dependency_boundary_stable` | 仍 FAIL（Model/Tool/Observability/Evaluation/Checkpoint 仍 `REMAIN_EXPERIMENTAL`） |

⇒ 本任务完成后，Spec 17 的合法输出**仍是 `NOT_READY_FOR_EXTRACTION`**。本任务的价值是消除「无标尺」这一项，
而不是把门禁打开。

---

## 8. 实测结果（2026-10-12 收口）

| 验收项 | 结果 |
|---|---|
| 两仓 BenchmarkSpec §24 字段全部有值且可复算 | ✅ Wiki（`frozen/w11a-v1/MANIFEST.json`，自校验 PASS）· Coding（`benchmark/frozen/w11a-v1/MANIFEST.json`） |
| 冻结产物齐全 + SHA256SUMS | ✅ `output/eval/w11a_baseline/`（8 文件）· Coding `benchmark/baselines/w11a-v1/` |
| Wiki 冻结语料 8 类各 ≥10 | ✅ 122 题（U-14 八类：18/18/16/16/16/16/11/11） |
| **复跑判定脚本产出结论** | ✅ 产出，结论为 **`NOT_REPRODUCIBLE`** |
| 安全与副作用零容忍项 = 0 | ✅ |
| `reproducible_quality_gate` 可被引用 | ❌ **未通过**：逐题一致率 58–82%（预登记 ≥90%）、provider 失败率 22.1%（预登记 ≤5%） |

### 未通过的原因（实测，非推断）

1. **判分在单题粒度不稳定**：`answer_correctness` 均值差仅 0.005（很稳），但逐题一致率 82.1%；
   `faithfulness` / `hallucination` 均值差 0.042 / 0.069 双双超出 ±0.03。根因是 judge 与 agent **同模型**（自评）+ 0.1 温度。
2. **网关并发不可靠**：`--workers 4` 下首次复跑 47/122（38.5%）返回 400 `invalid request error`，`--retry-errors`
   重试后仍失败 27/122（22.1%）。
3. 确定性指标（tool_selection / task_completion）在「两次都跑成功」的题目上完全一致；报告中的 54 处不一致
   全部来自失败行的 `1.0 vs None`，不构成测量漂移。

### 结论

`reproducible_quality_gate` **仍未闭合** ⇒ Spec 17 的合法输出仍是 `NOT_READY_FOR_EXTRACTION`。
本窗口的价值不在于把门禁打开，而在于把「缺证据」变成了三条可执行的阻塞原因，并顺带修掉 7 个真实缺陷（D1–D7）。
**不得**为了通过门禁而放宽容差；下一步应先解决判分稳定性与网关可靠性，再重建基线。
