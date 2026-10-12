# W11-α Step 1 探测与审计报告（2026-10-12）

> 任务：为 Foundation Family Extraction Gate（Spec 17）的 `reproducible_quality_gate` 缺失项
> 建立合法的 pre-extraction benchmark baseline。本文件是 Step 1（1.1 探测 / 1.2 资产盘点 /
> 1.3 Adapter 重复度审计 / 附带：Coding `main` 合并演练）的证据留痕。
>
> 全程只读：未改任何产品代码、未删任何 mirror、未建 distribution、未执行 push。
> 原始产物：`probe_wiki.json` / `probe_coding.json`（同目录）。

## 0. 结论速览

| 项 | 结论 |
|---|---|
| 模型层可用性 | ✅ 双仓均可用：`deepseek/deepseek-v4.1-flash` @ `api.commandcode.ai`（command_goat），双仓 agent 与 judge 是**同一个** provider/model |
| 历史 judge `mimo-v2.5` | ❌ **不可用**：opencode zen/go 网关返回 **HTTP 400**（不是此前的 429 限流）→ 0.857 基线**不可原样复现** |
| Docker（Coding benchmark 执行器） | ❌ 当前不可用：`npipe:////./pipe/dockerDesktopLinuxEngine` 连接失败（rc=1） |
| Benchmark 资产 | ⚠️ 两仓都**没有** master spec §24 要求的任何冻结字段；Wiki 侧 8 类覆盖缺 2 类；Coding 侧仅 5 个 case 且无基线报告 |
| Adapter 重复度 | ⚠️ 真实但集中：每仓约 500–650 行可原样共享（约 28–35%），主要来自 `runtime.py`；`facts.py`/`evidence_sink.py` 抽取被证据否定 |
| Coding `main` 合并 | ✅ 可合并：9 个 add/add 冲突、冲突面很小（合计 +274/−26 行）；无「仅远程存在」的文件 |

---

## 1. 1.1 Provider 探测（实测）

Wiki 侧（`output/_w11_probe/probe_wiki_providers.py`）：

| 项 | 实测值 |
|---|---|
| agent 模型 | `deepseek/deepseek-v4.1-flash`，base host `api.commandcode.ai`，key 存在 |
| judge 模型 | **同上**（`get_judge_model()` 收敛到统一 provider，不再是 `mimo-v2.5`） |
| 统一 judge 调用 | ✅ 成功：2422 ms，38 in / 16 out，¥0.000204；**但 `max_tokens=16` 时 content 为空**（16 个 completion token 被推理消耗）→ 冻结必须记录 `max_tokens` |
| 旧网关 `mimo-v2.5` | ❌ `RuntimeError: 400 Bad Request`（base `opencode.ai`，key 存在） |
| 全量 dry-run 估算 | 100 题 / direct+http ⇒ agent 200 次 + judge 100 次，约 60 万 tokens，judge 侧约 **¥0.180**（Flash 档估算） |

Coding 侧（`output/_w11_probe/probe_coding_provider.py`）：

| 项 | 实测值 |
|---|---|
| 解析出的 provider | `command_goat`（preference：command_goat → deepseek；fallback opencode_go） |
| 模型 / base | `deepseek/deepseek-v4.1-flash` @ `api.commandcode.ai`，key 存在 |
| 调用 | ✅ 成功：3438 ms，38 prompt / 23 completion tokens，content `pong` |
| Docker | ❌ rc=1，无法连接 Docker Desktop Linux engine |

**推论（需记录进 Spec）**：① 当前 Wiki 的 judge 与 agent 同模型同 provider ⇒ **Wiki 侧现在是自评**，
与 0.857 基线（judge=mimo-v2.5）不同源，两者**不可直接比较**；② `mimo-v2.5` 修复路径（网关可用性）
不由本项目控制；③ Coding 的 benchmark 若使用 docker 执行器，必须先恢复 Docker，否则只能用 `local`
执行器 —— 而 `executor` 字段写的是配置值、实际由 `KA_EXECUTOR` 决定，**报告可能与实际不符**。

---

## 2. 1.2 Benchmark 资产盘点（只读）

### 2.1 Wiki

- 数据集：`benchmarks/arknights_bench/questions_draft.jsonl`，207,839 B / **100 条**；
  类别 character 18 / event 18 / region 16 / organization 16 / combat_power 16 / worldview 16；
  route complex 62 / simple 38；**无 version/hash/seed 字段**。
- **U-14 的 8 类里有 2 类为 0 条**：`no_answer`、`hallucination_bait`（定义在 `eval/metrics.py:9-18`，无题目）。
- runner 默认 `--bench` 指向 `benchmarks/arknights_bench/questions.jsonl` —— **该文件不存在**，只能显式传 draft 文件。
- 选样：`--limit` 取文件头部 + `--category` 精确匹配（`eval/runner.py:305-309`），**顺序敏感且顺序不被记录**。
- 结果行不含 model/provider/temperature（`runner.py:256-268`）；judge 模型只落在 `cost_log.jsonl`。
- 报告头部只写 timestamp/count/mode/judge-note（`eval/report.py:27-32`），**judge note 是硬编码的过期字符串**（`report.py:10` 仍写 mimo-v2.5）。
- 聚合：`_mean` 静默丢弃 null（`metrics.py:30-32`）⇒ judge 失败会改变分母；失败次数不记录
  （`results_scored_final.jsonl` 第 1 行已是 `hallucination: null` + `LLM 调用失败（3 次尝试）`）。
- 既有基线：`output/eval/report_v1_mimo.md`（2026-08-17，100 题，direct）：overall **0.857**，
  correctness 0.765 / faithfulness 0.779 / citation 0.733 / tool_selection 0.99 /
  no-hallucination 0.887 / task_completion 0.99，费用 ¥26.4583，**未记录 commit**。

### 2.2 Coding

- 数据集：`benchmark/cases/<category>/<id>.json` 共 **5 个 case**（bug 2 / feature 1 / test 1 / refactor 1 / domain 0），
  gold diff 5 个；无 version/hash/commit 字段（`benchmark/loader.py:41-119`）。
- runner：`benchmark/runner.py`，CLI `python main.py --benchmark`；**全量跑、无 limit/seed/shuffle、顺序 for 循环无线程**。
- judge：`benchmark/judge.py::judge_patch()`，**与被测 agent 共用同一个 `LLMClient`** ⇒ 自评。
- 目标仓状态**未固定**：case 运行时 clone 仓库的 live `default_branch`；`RunMetadata.git_commit` 记的是
  harness 仓的 HEAD 而非 fixture commit ⇒ §24 的「repository commit/fixture state」**无法重建**。
- 成本：`MODEL_PRICE_USD_PER_1K = {}` ⇒ `cost_usd` 恒为 0.0。
- **不存在任何 benchmark 报告**（`output/` 下只有 `exp/` 与 `contract-validation/`）⇒ 无 resolution 基线；
  唯一带评分的记录是 L3 的 `docs/contracts/releases/0.1.0/validation/coding/run-manifest.json`（`case_ids: ["schedule-99"]`）。

### 2.3 §24 冻结字段缺失（两仓共同）

数据集/case-set 内容哈希、有序 case-id 列表、runner 版本（harness commit）、judge 模型+provider+prompt 版本
（逐行而非仅 cost log）、temperature/seed/max_tokens、null-metric/judge-failure 计数、预登记容差 —— **全部缺失**。
Coding 侧另缺：目标仓 commit、真实 executor、sandbox 策略、`side_effect_policy`。

---

## 3. 1.3 Adapter 重复度审计（只读）

- 契约镜像：`agent_core/contracts/**/*.py` **31 个文件逐字节相同**（两仓）。
- 规模：Wiki 1810 行 / Coding 1632 行（不含 `__init__.py`）。
- 逐字共享行：**723 行**（runtime 400 / mapping 127 / facts 117 / sink 75 / init 4）；
  同名 def/class：49 个（Wiki 86 / Coding 89 中）。
- 相似度（重合/平均代码行）：mapping **0.681** > runtime 0.606 > facts 0.413 > sink 0.361。
- 分层估算（每仓）：可原样共享 **500–650 行（约 28–35%）**；需参数化/挂钩 150–250 行；项目专有 900–1100 行。
- 9 条「抽象税」风险，关键几条：① stage→producer 映射表**完全不同且无交集**（wiki 6 stage / coding 7 stage）；
  ② usage facts 字段集需取并集（≥8 字段）；③ payload key 命名空间与 pricing 扩展项各自专有；
  ④ `map_summary` 签名分叉；⑤ Coding 独有的 `ComponentLedger` 旁路；⑥ 失败载体契约不同；
  ⑦ **公共契约本身已明文把目录布局/命名/staging 根留给项目本地实现**
  （`agent_core/contracts/protocols/evidence_sink.py:56-60`，只暴露 `emit`）。
- 裁定：抽取 **runtime 骨架 + mapping 核心** 有证据支撑（可删约 30% 行数）；`facts.py` / `evidence_sink.py` /
  `observation_ledger.py` 抽取**被证据否定**。最强反方论证：723 行中 400 来自 `runtime.py`，扣除文档串与
  样板后真正机械共享约 200–250 行，加上参数化 glue（400–700 行）≈ **接近盈亏平衡**。
  ⇒ 该审计本身足以支撑「duplication is real but concentrated」的结论，但**不足以**单独满足 gate。

---

## 4. 附带：Coding `main` 合并演练（只读，已回滚）

| 项 | 实测 |
|---|---|
| 本地 `main` | `c364b02`（B2），**208** 个提交 |
| `origin/main` | `c38fcd7`（「远程仓库初始导入」），**1** 个提交 |
| `merge-base` | 空 ⇒ **无关历史**，无快进路径 |
| 演练结果 | `git merge --allow-unrelated-histories`：**9 个 add/add 冲突** |
| 冲突文件 | `.env.example`(+16/−6)、`.gitignore`(+13/−0)、`agent/llm.py`(+49/−8)、`benchmark/runner.py`(+21/−4)、`pyproject.toml`(+16/−0)、`tests/test_benchmark_runner.py`(+46/−0)、`tests/test_llm.py`(+75/−2)、`tools/report_trace.py`(+26/−2)、`tools/tracing.py`(+12/−2) |
| 文件集合 | 远程 120 / 本地 193；**仅远程存在 0 个**；仅本地存在 73 个 |
| 整体树差异 | 82 文件变化，+18,249 / −24 |
| 状态 | 演练已 `merge --abort` + `worktree remove` 回滚；`main` 仍为 `c364b02`，两仓工作树干净 |

含义：远程初始导入是本地主干的**真子集**（无独立文件），合并只需裁定 9 个冲突文件的 26 行「远程独有内容」，
风险可控；但这仍属于对共享分支历史结构的改动，需用户确认后再执行（G-04 / N-01）。
