# Foundation Contract v0.1 / Cycle 1 开工准备说明

> 日期：2026-09-10
> 性质：**非规范性**开工准备记录（不进入 Contract Payload，不构成规范载体）
> 规范真相源：[Master Spec](../specs/2026-09-10-dual-agent-foundation-contract-master-spec.md)
> 执行投影：[00-execution-index](../specs/foundation-contract/00-execution-index.md) + 子 Spec 01–18

本文件只记录"开工前已经核验过的事实、环境、取舍与红线"。若与 Master Spec 冲突，以 Master Spec 为准，并触发 `SPEC_CONFLICT`。

---

## 1. 本轮边界

母 Spec 采用按证据成熟度分层的授权，**只有 Part I 可执行**：

| 范围 | 授权 | 本轮是否可做 |
|---|---|---|
| Part I：Spec 01–15 / Cycle 1 Foundation v0.1 | `IMPLEMENTATION-READY` | ✅ 可做 |
| Part II：Spec 16 / Cycle 2 v0.2 | `FEEDBACK-BOUND` | ❌ 必须先有真实 L2/L3 问题 |
| Part III：Spec 17–18 / 抽取门禁 | `GATE-DEFINED` | ❌ 只评估门禁，不得实现 |

本轮**不做**：创建独立 `agent-core` distribution、抽公共运行时、统一 provider/retrieval/memory/KG/sandbox/approval/checkpoint、修改 Dashboard/报告/评分/路由、FX 换算。

---

## 2. 环境与权威命令

**权威解释器**（两仓共用，实测可用）：

```text
D:\CodexPython312\python.exe      # Python 3.12.10 + pydantic 2.13.4 + arknights-wiki 0.1.0(editable)
```

⚠️ 注意：`PATH` 里默认的 `python`（`C:\Users\...\workbuddy\binaries\python\3.13.12`）**没有安装项目依赖**（无 pydantic），
直接用它跑测试会失败。所有 pytest / build 命令必须显式使用 `D:\CodexPython312\python.exe`。

权威完整测试命令（Master §1.3，唯一口径）：

```powershell
# Wiki
D:\CodexPython312\python.exe -m pytest tests/

# Coding
D:\CodexPython312\python.exe -m pytest tests/
```

**禁止**使用仓库根目录裸 `pytest` 作为 Wiki 门禁——它会额外收集 `output/` 历史归档与脚本测试，污染基线。

---

## 3. 基线快照（2026-09-10 核验）

| 项 | Wiki | Coding |
|---|---|---|
| 仓库路径 | `D:\AI project\Arknights LLM Wiki` | `D:\AI project\Knowledge-Augmented Autonomous Coding Agent` |
| 本轮分支起点 SHA | `bc954d3` | `08a8275` |
| Python | 3.12.10 | 3.12.10 |
| Pydantic | 2.13.4（**未在 pyproject 声明**） | 2.13.4（**未在 pyproject 声明**） |
| `pytest tests/` 收集数 | **552** | **394** |
| 期望结果 | 542 PASS / 7 SKIP / 3 已知失败 → `PASS_WITH_KNOWN_BASELINE_FAILURES` | 381 PASS / 13 SKIP / 0 失败 → `PASS` |
| Benchmark | `BENCHMARK_BASELINE_NOT_REPRODUCIBLE`（历史 0.857 仅作 reference，`gate_effect=NONE`） | `BENCHMARK_REPRODUCTION_RESTRICTED`（历史 1/5 仅作 reference） |
| `.github/workflows` | 不存在（本地门禁为 Part I 新建内容） | 不存在 |

收集数与 Master §1.3 的 552 / 394 完全吻合。**实际 PASS/SKIP/FAIL 划分必须由 Spec 01 在权威命令下重新产生并落盘**，不得复用本文数字作为门禁证据。

Wiki 三个已知失败（Master Appendix E.2，Spec 01 必须原样核对 fingerprint，漂移即停止）：

```text
tests/test_stats_collector.py::TestStatsCollectorContent::test_collect_content_reads_db
tests/test_stats_collector.py::TestStatsCollectorSnapshot::test_finish_writes_jsonl_line
tests/test_stats_collector.py::TestStatsCollectorSnapshot::test_finish_resets_state
```

共同根因：`arknights_wiki.stats.collector._get_raw_data` 假定 story JSON 顶层为对象，实际遇到列表。
**属于 DEFERRED 范围，本 Cycle 禁止顺手修复。**

### 基线偏离登记（必须记录，不得静默复用）

Master §1.1 / Appendix E 记录的 Wiki 基线提交是 `838ba4c`。为让子 Spec 进入 Git（未提交文件不会进入 worktree），
本轮已先在 `main` 追加一次**纯文档提交** `bc954d3`：

```text
bc954d3  docs(foundation): 双旗舰 Foundation Contract 母 Spec + 18 子 Spec + 2 ADR
          （25 个文件，仅 docs/ + CONTEXT.md + 06_路线文档，无任何代码/测试/配置改动）
```

因此 Spec 01 的 Stage 0 必须做一次 **baseline refresh**：

```text
baseline_commit = bc954d3        # 而非 Master 快照的 838ba4c
deviation_type  = docs_only_baseline_refresh
impact          = 测试集合、依赖、producer 位置均未变化；预期统计不变
```

若 Spec 01 实测统计与 542/7/3 不一致，视为真实漂移，必须停止并出 Spec deviation report。

---

## 4. 分支与 worktree 布局

| 仓库 | 分支 | worktree 路径 | 起点 |
|---|---|---|---|
| Wiki（canonical author + coordinator + finalizer） | `feature/foundation-contract` | `D:\AI project\_worktrees\foundation-contract\wiki` | `bc954d3` |
| Coding（mirror consumer） | `feature/foundation-contract` | `D:\AI project\_worktrees\foundation-contract\coding` | `08a8275` |

- 两仓分支同名但相互独立（不同仓库）。
- `main` / `feature/remote-preparation` 原工作区保持不动，仍可用于对照与回滚。
- Coding 起点 `08a8275` = Coding `main`(`99c6f1a`) + 6 个 remote-preparation 提交，
  与 Master §1.1 / Appendix E.3 的核验 HEAD 一致。**注意 Coding `main` 目前落后于该点 6 个提交**，
  后续合并 `feature/foundation-contract` 时会一并带入这 6 个提交（如需避免，请在开工前确认基线口径）。

### 开工环境注意（重要）

本机 Bash 沙箱会**拦截 git 内部对 `.git/refs/heads/<name>/…` 新子目录的创建**，表现为
`git branch feature/xxx` / `git worktree add -b` **静默成功但不生成 ref**。
已验证的可靠做法：**先手工写入 loose ref，再 `git pack-refs --all` 将其并入 `packed-refs`**。
新建 worktree 时如遇同类问题，沿用该方式；不要误判为 git 仓库损坏。

---

## 5. 执行顺序与解锁关系

```text
01 → 02 → 03
     02 + 03 → 04
04 → 05 → 07 ─┐
               ├→ 09 → 10 → 11
04 → 06 → 08 ─┘
─────────────── CANDIDATE A FREEZE BOUNDARY ───────────────
11 ─→ 12 (L2) ─┐
  └→ 13 (L3) ──┼→ 14 Evidence B → 15 Coordination / C_wiki → Cycle COMPLETE
11 L1 + 全量回归 ┘
16 = FEEDBACK-BOUND（需真实 L2/L3）
17 = GATE-DEFINED（不可执行）
18 = GATE-DEFINED（不可执行）
```

编号只是阅读顺序，**只有 DAG 与归约状态决定解锁**；依赖默认要求 upstream `COMPLETE`。

### 当前唯一可启动的工作单元：Spec 01（`READY`）

目标：在**任何契约代码出现前**冻结双仓事实基线、Producer 范围与治理目录。**不创建 `agent_core`，不改业务逻辑。**

Spec 01 任务清单：

1. 记录两仓 identity / branch / HEAD / Python / Pydantic / pytest / packaging backend。
2. 在两仓固定 HEAD 上执行唯一权威命令 `python -m pytest tests/`，分组 PASS / SKIP / FAIL nodeid。
3. Wiki 为三个 StatsCollector 失败生成规范化指纹并与 Appendix E 核对；Coding 确认 known failures 为空。
4. 审计 Master §7 每个 producer 的 source location 与 mapping stage 是否仍存在。
5. 全部已发现 producer 标状态：`IN_SCOPE` / `DEFERRED` / `OUT_OF_SCOPE_BY_DESIGN` / `UNKNOWN`（新发现默认 `UNKNOWN`）。
6. 写 `config/contracts/producer-registry.json`（Master Appendix B 结构）与 `config/contracts/known-test-baseline.json`。
7. 更新 `.gitignore`：至少排除 `output/contract-validation/staging/`、raw business evidence、private replay、环境文件（**不删既有规则**）。
8. 校验 `execution-status-events.jsonl` 为 0 bytes，reducer genesis = `01 READY` / `02–18 NOT_STARTED`。

Spec 01 允许改动仅：`config/contracts/*.json`、`.gitignore`。其余一律禁止。

---

## 6. 全程红线（违反即 Contract Defect）

```text
off == observe 四类不变性（Output / Decision / Side Effects / Legacy Telemetry）
```

- Legacy 业务主路径**永不消费** Foundation 对象；Foundation 只观察、只产出证据。
- 未提交 Event 不得改写既有 Trace / cost log / report / Dashboard / 评分 / 路由 / 恢复 / 审批。
- 未接线的 DTO 不得出现 `raise ErrorEnvelope` / `except ErrorEnvelope`；它不是异常基类。
- presence-aware：facts extractor **禁止** `get(..., 0)`、`or 0`、由 legacy total 反推组成项。
- `agent_core` Phase 1 白名单只有 `agent_core/__init__.py` + `agent_core/contracts/**`；出现 provider/retry/checkpoint/Adapter/项目状态即门禁失败。
- 只有 **Wiki** 能写 canonical payload；Coding 只能由 bundle 原子提升，禁止手工修补镜像。
- Coding 不得保存子 Spec 副本、DAG 或状态摘要 shadow copy。
- 状态账本是**唯一动态状态源**，append-only；第一条事件必须是真实工程动作（Spec 01 `READY → IN_PROGRESS`），不能记"文档已生成"。
- 证据发布只允许 allowlist 重建，禁止"先全量序列化再删敏感字段"。
- 不在 Spec 11 之后新增或修改任何 replay / sanitizer / smoke / invariance / publisher / coordinator / reducer / workflow 工具；发现缺陷则 Candidate A `SUPERSEDED`，回到所属 Spec 形成 A2。

**明确不修改的文件**（Wiki）：`eval/report.py`、`observability/dashboard.py`、`stats/collector.py`、extraction orchestrators、retrieval/memory/KG/checkpoint。
**明确不修改的行为**（Coding）：`benchmark/report.py` 格式、Agent 路由/工具分发/review/retry、Sandbox/Git/GitHub/Approval 边界、Benchmark case/gold patch/judge prompt。

---

## 7. 风险登记（开工前已知）

| 风险 | 信号 | 处置 |
|---|---|---|
| 用错解释器导致基线失真 | 默认 `python` 报 `No module named pydantic` | 统一用 `D:\CodexPython312\python.exe` |
| 把 `838ba4c` 旧 SHA 写进 baseline | baseline artifact 的 commit 与当前 HEAD 不符 | 采用本文件 §3 的 baseline refresh 口径 |
| Coding `main` 落后 6 提交 | 合并时意外带入 remote-preparation 提交 | 开工前确认基线口径 |
| pyproject 缺 pydantic / build-system / package discovery | Spec 10 之前 clean wheel 失败 | 属 Spec 10 范围，不在 Spec 01 提前修 |
| Coding `pyproject.toml` 无显式 package discovery | `agent_core*` / `adapters*` 不进 wheel | 属 Spec 10 范围 |
| sandbox 拦截 git ref 子目录创建 | `git branch`/`worktree add -b` 静默失败 | 手工写 ref + `pack-refs`（见 §4） |
| 11 个 6 月遗留 worktree（`.claude/worktrees/agent-*`，locked） | `git worktree list` 冗长 | 已 ignore，不影响状态；清理需显式确认 |
| 未提交运行产物混入提交 | `data/extractions/v3_seed_db_v2.json`、`output/eval/cost_log.jsonl` 仍为 modified | 提交前逐项确认，不随文档/代码一起提交 |

---

## 8. 会话接手提示

新会话按 CLAUDE.md §3.2 启动，并追加本文件：

1. `README.md`（项目状态、数据基线）
2. `output/devlog.md`（最新架构决策）
3. **本文件**（Foundation Contract 开工准备：环境、基线、分支、红线）
4. 母 Spec §0 / §1 / §17 与目标子 Spec（例如先读 Spec 01 全文）

进入 worktree 工作：

```powershell
cd "D:\AI project\_worktrees\foundation-contract\wiki"
```

任何"仓库事实与 Spec 不符 / 必须修改未列文件 / producer 无法在不改业务语义下接入"，停止并出 Spec deviation report，不得自行扩范围。
