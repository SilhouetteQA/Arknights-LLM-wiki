# 明日方舟剧情 LLM Wiki

基于《明日方舟》全量剧情构建的结构化知识库与 AI 问答系统。覆盖主线第 1-15 章、67 个支线/插曲活动、21 个故事集、6 个集成战略主题，共 109 章剧情经三遍 LLM 提取管线转化为可检索知识图谱，由 LangGraph ReAct Agent 提供自然语言问答。

> 最新收录剧情：泡影苍霆（怪物猎人二期联动）。

> 启动服务后访问 `http://localhost:8000`，PRTS 终端风格双栏 SSE 聊天界面。

---

## 功能特性

- **三遍知识提取**：事件骨架 (Pass 1) -> 角色 Wiki (Pass 2) -> 世界观实体 (Pass 3)，每遍独立 LLM 扫描
- **混合检索**：精确 Wiki 检索 + FAISS 语义搜索 + 原始对话全文搜索 + 章节感知过滤
- **LangGraph ReAct Agent**：多步推理 + 8 工具调用 + 证据综合，支持对比/枚举/因果推理
- **实体双向索引**：5,213 实体的 25,300 条引用，支持精确匹配和别名解析
- **PRTS 终端前端**：SSE 流式聊天、检索步骤可视化、来源引用展开
- **W0 评测体系**（升级阶段）：`arknights_wiki/eval/` Benchmark 建库——100 题八类覆盖、DeepEval 打分、mimo-v2.5 统一 judge（`report_v1_mimo.md` overall 0.857）、路由/打分层 bug 修复与测试补全
- **Foundation Contract 公共工程层**（2026-09 起）：与 Knowledge-Augmented Autonomous Coding Agent 共享 `agent_core.contracts` 契约镜像——presence-aware 事实语义（Unknown ≠ Zero / Estimated ≠ Reported / USD ≠ CNY）、非侵入旁路治理、append-only 状态账本与双仓 L1/L2/L3 证据门禁。Cycle 1 进度：Spec 01–12 `COMPLETE`，Spec 13（双仓 L3 新鲜冒烟）`BLOCKED` —— Wiki 半边已 gate 8/8 闭合，Coding 半边被一个**实测的候选业务代码缺陷**挡住，故 Spec 14/15 仍锁定；缺陷与恢复条件见 `docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md` §11

---

## 快速开始

**环境要求**：Python 3.12+, 8GB+ 内存

```bash
git clone <repo-url>
cd "Arknights LLM Wiki"
pip install -e .

# 启动 Agent 服务
python -m arknights_wiki.agent.server
# 浏览器打开 http://localhost:8000

# 构建索引（首次运行前）
python scripts/build_agent_index.py      # FAISS 向量索引
python scripts/build_entity_index.py     # 实体双向索引
```

### Foundation Contract 验证（权威环境）

契约相关命令必须使用权威解释器（PATH 里的默认 `python` 未安装项目依赖）：

```powershell
D:\CodexPython312\python.exe -m agent_core.contracts.tooling.generate_schemas --check
D:\CodexPython312\python.exe -m agent_core.contracts.tooling.verify_payload
D:\CodexPython312\python.exe -m pytest agent_core/contracts/conformance -q
D:\CodexPython312\python.exe -m pytest tests/contracts -q
D:\CodexPython312\python.exe scripts/contracts/validate_local.py --gate pr   # 8 步本地门禁
D:\CodexPython312\python.exe -m build                                        # sdist + wheel（package smoke）
D:\CodexPython312\python.exe -m pytest tests/            # 权威完整测试口径（禁止仓库根裸 pytest）
```

契约运行开关：`AGENT_CONTRACT_MODE=off|observe|strict`（默认 `off`）。

自 Spec 10 起另有：`--gate candidate`（全量回归 + nodeid/指纹门 + L1/L2/L3 证据闭合）与 `--gate smoke`（§11.2 八项闭合）——两者在 Spec 12–14 产出 Candidate-bound 证据前**预期失败**（fail-closed）。Wiki 侧治理工具：`scripts/contracts/status_ledger.py`（状态账本 reducer）、`coordinate_cycle.py`、`finalize_cycle.py`。

CI：`.github/workflows/contract-local.yml`（Windows L1，无密钥、不跨仓）、`contract-payload-linux.yml`（Linux 最小依赖 canonical hash）、`contract-coordinate.yml`（仅手动触发，Wiki）。

> 本改造在独立 worktree / 分支上进行：`feature/foundation-contract` → `feature/foundation-contract-spec10`（见 `docs/plans/2026-09-10-foundation-contract-cycle1-kickoff.md`）。

---

## 架构概览

```
用户问题 → [router.py] 意图识别 + 实体提取 + 复杂度分类
              ├── simple → 多层检索管线 → LLM 合成
              └── complex → LangGraph ReAct Agent (8 tools, ≤8 轮) → LLM 合成
                             （可切换 Planner 显式规划: ARKNIGHTS_AGENT_MODE=planner）
```

架构图详见 **[docs/diagrams/architecture.md](docs/diagrams/architecture.md)**，或用浏览器打开 **[docs/diagrams/architecture.html](docs/diagrams/architecture.html)** 查看交互式预览。

### Agent 工具

`search_wiki` / `get_entity_page` / `search_events` / `search_dialogue` / `search_timeline` / `get_chapter_summary` / `semantic_search` / `lookup_entity_index`

---

## 工程化能力（2026-08 升级阶段 W1–W4，P0 全部完成）

| 阶段 | 能力 | 说明 |
|------|------|------|
| **W1 Observability** | Langfuse 全链路 Trace | `@observe` 埋点（router/simple/graph 各节点）、Docker 本地部署、ClickHouse 直查、ECharts Dashboard（`python -m arknights_wiki.observability.dashboard` :8001） |
| **W2 Failure Recovery** | 六层恢复链 | timeout(线程池) → 指数退避重试 → circuit breaker(按工具隔离) → fallback(4 工具降级) → checkpoint(SqliteSaver 断点续跑) → escalation；LLM 网络/限流/5xx 重试（4xx 不重试）；恢复统计入 trace |
| **W3 MCP Server** | 知识库标准协议化 | `arknights_wiki/mcp_server/`：5 个只读 MCP 工具（search_entities/events/relationship/timeline/story），stdio transport；Agent 双轨切换 `ARKNIGHTS_USE_MCP=1`（工具名不变，LLM 无感知，失败回退内部函数） |
| **W4 Planner** | 显式任务规划 | LLM 拆解任务图（规则兜底 + 白名单校验 + entity_type 归一化）→ 分层并行执行 → 综合；崩溃检测自动切 ReAct 兜底；`ARKNIGHTS_AGENT_MODE=react\|planner` 双轨 |
| **W0 评测体系** | Benchmark 100 题 | 六类八类覆盖、mimo-v2.5 统一 judge（基线 `report_v1_mimo.md` overall 0.857）；三路由 A/B 同环境对比（ReAct 0.942 / Planner 0.903 / 任务级ReAct 0.758，`output/eval/w4_cmp_*`） |

**关键开关**：`ARKNIGHTS_AGENT_MODE`（react 默认/planner 可选）、`ARKNIGHTS_USE_MCP`（MCP 双轨）、`ARKNIGHTS_PLANNER_TASK_REACT`（实验）、`ARKNIGHTS_PLANNER_FALLBACK`（崩溃兜底，默认开）、`ARKNIGHTS_TOOL_*`/`ARKNIGHTS_LLM_*`（恢复链参数）、`ARKNIGHTS_HTTP_PROXY`（显式代理）。

---

## 双旗舰公共工程层：Foundation Contract（2026-09 起）

与本项目配对的旗舰项目 **Knowledge-Augmented Autonomous Coding Agent** 共享一层"公共工程契约"。定位是**契约统一，不是 agent 实现合并**：两个项目各自保留领域实现（retrieval / memory / KG / LangGraph state ↔ sandbox / GitHub / approval / durable execution），只统一跨边界的事实语义。

它要解决的真实问题：两仓都把"没有用量 / 单价 / 成本信息"归一为 `0`，于是**真实零成本、未知成本、估算成本无法区分**——结构再统一，Trace / Evaluation / Dashboard 的结论也不可信。

```text
                 ┌→ Legacy 业务路径 → 现有结果（唯一真相源，不受影响）
Input ───────────┤
                 └→ Foundation Adapter → Validation Evidence
```

| 层 | 归属 | 说明 |
|---|---|---|
| `agent_core/contracts/**` | **双仓逐字节相同的镜像** | 唯一 canonical author 是本项目；Coding 侧只能由 bundle 原子提升，禁止手工修补 |
| 项目本地 Adapter | 各仓自持 | `arknights_wiki/adapters/foundation/` —— 差异由 Adapter 表达，不污染公共 DTO |
| 证据与门禁 | 本项目协调 | append-only 状态账本、L1/L2/L3 验证、Candidate A 冻结 → Evidence B → Finalization C |

v0.1 契约内容：`Usage` / `Cost` / `CostSummary` / `ErrorEnvelope` / `FoundationObservation` / `EvidenceRecord` + `ContractMode` + `EvidenceSink Protocol` + 共享 conformance 测试 + canonicalization / payload hash / mirror bundle 工具。

### 契约身份（v0.1 / Cycle 1）

| 项 | 值 |
|---|---|
| contract_version | `0.1.0`（lockstep 单一 Contract Set，不为每个 family 建独立 SemVer） |
| canonicalization_version | `1` |
| pydantic | `2.13.4` |
| Payload | 40 文件 / `sha256:64049830…`（两仓一致） |
| Schema 清单 | Usage / Cost / CostSummary / ErrorEnvelope / FoundationObservation / EvidenceRecord |
| 规范规则 | 68 条（56 conformance 落地 + 7 项目落地 + 5 显式 deferral） |
| 状态账本 | `docs/specs/foundation-contract/execution-status-events.jsonl`（append-only，唯一动态状态源） |

### 执行进度

母 Spec 按证据成熟度分三层授权，当前**只有 Part I 可执行**：

| 范围 | 授权 | 进度 |
|---|---|---|
| Part I — Cycle 1 / Foundation v0.1（Spec 01–15） | `IMPLEMENTATION-READY` | **Spec 01–12 `COMPLETE`；Spec 13 `BLOCKED`** —— 候选经 **A→A2→A3→A4（Wiki）/ A→A2→A5（Coding）** 固化（**A_wiki `554bce2f`** / **A_coding `c5d0af0f`**）；Wiki 半边 L3 gate **8/8** 闭合，**Coding 半边 L3 未闭合**（见下）；**Spec 14/15 因此仍锁定** |
| Part II — Cycle 2 / v0.2（Spec 16） | `FEEDBACK-BOUND` | 需真实 L2/L3 问题驱动才可启动 |
| Part III — 抽取门禁（Spec 17–18） | `GATE-DEFINED` | 只评估门禁，不得实现 |

DAG：`01 → 02 → 03 → 04 →（05 → 07 / 06 → 08）→ 09 → 10 → 11`（**Candidate A 冻结边界**）`→ 12(L2) / 13(L3) → 14(Evidence B) → 15(协调 + Finalization C → Cycle COMPLETE)`。

Spec 10 已交付**全部 pre-freeze 工具与 5 个 CI workflow**（两仓 `scripts/contracts/`、`.github/workflows/`）；Spec 11 之后这些实现不得再改——缺工具只能把 Candidate A 标 `SUPERSEDED` 并回到所属 Spec 形成 A2（`GOV-FRZ-001/002`）。

### Candidate A 冻结边界（2026-09-17 现状）

| 项 | 值 |
|---|---|
| A_wiki | `554bce2f2ebd00f5f4e6ac722680a8a57ab8cc66`（A4） |
| A_coding | `c5d0af0f4c9110259945fc90151da4336a07d639`（A5；取代 A2 `339768dd`） |
| Payload 身份 | `contract_version=0.1.0`、40 文件、`payload_hash=sha256:64049830…` —— 自 A 起**从未变化**，A2/A3/A4/A5 全部是 payload-neutral 的项目本地改动 |
| Cycle 分支 | `contract-cycle/foundation-0.1.0-cycle-1`（**A/B/C 的唯一承载分支**）。母 Spec §16.3 要求 `diff(A,B) ⊆ evidence publication allowlist`，因此 README / devlog 等非 allowlist 提交必须留在 `feature/foundation-contract-spec10`，不得插入 A→B 之间 |
| 正式 L1（A5 干净 checkout） | 6 条命令全部 exit 0：`generate_schemas --check`（schemas=6 / rules=68）；`verify_payload`（三哈希未变）；conformance **224 passed**；`tests/contracts` **242 passed**；`validate_local --gate pr` **8/8**；`python -m build` |
| 全量回归 | Wiki `913 passed / 10 skipped / **0 failed**`（A4）；Coding `638 passed / 3 skipped / **0 failed**`（A5） |
| 候选轮次 | Wiki：A `b726c09` → A2 `ca24a199` → A3 `3972c887` → **A4 `554bce2f`**；Coding：A `c8e06e5` → A2 `339768dd` → **A5 `c5d0af0f`**。每一轮都由一个**实测缺陷**驱动，逐轮记录见 `output/devlog.md` |
| 受控 staging（**故意不提交**） | `docs/specs/foundation-contract/execution-status-events.pending.{jsonl,json}`（23 事件），`target_boundary=candidate_a`、`candidate_commit=A_wiki`、`suffix_hash=sha256:673486d1…`。Spec 14 必须把它**逐字节** append 到 B_wiki 账本，否则 Spec 12/13 的证据无效 |

### Spec 12 `COMPLETE` / Spec 13 `BLOCKED`：经验证的进展与经验证的缺口

L2（Spec 12）在两仓真实跑通：Wiki 220 records / 2 sources（`REPRODUCTION_RESTRICTED`，`difference_class` = `NONE`×120 + `expected semantic correction`×100）、Coding 3 records（`LEGACY_DATA_INSUFFICIENT`×3）、`adapter_defects=0`、发布扫描无命中；来源 sha256 绑定 **A 的已提交 blob**（Wiki `cost_log` `9f4bd645…`、`results_scored` `aa6f633d…`）。

L3（Spec 13）**只有 Wiki 半边闭合**：`AGENT_CONTRACT_MODE=observe` 下驱动真实 `arknights_wiki.eval.runner`，gate **8/8**、业务 exit 0、51.2s、12 事件、5 个 producer-stage 对 `ALL_STAGES 5/5`，未观测项按 `NOT_OBSERVED_ALLOWED` 具名登记且**不计为覆盖**。

Coding 半边 L3 **未闭合**，四条原因全部实测（逐条证据见 `docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md` §11）：

| 编号 | 内容 | 性质 |
|---|---|---|
| F1 | 预登记 provider `opencode_go`/`mimo-v2.5` → HTTP 429 `GoUsageLimitError`（月度额度耗尽） | 环境 |
| F2 | 预登记 case `schedule-99` 的 fixture（`dbader/schedule`）测试模块调用 POSIX-only `time.tzset()` → Windows 下必然 `environment_error`，Agent 不运行，`case_cost/normal` 不可观测 | 平台/夹具 |
| F3 | `benchmark/runner.py::_run_one_case` 先 `with sandbox_executor(repo_dir)` 再 `_ensure_repository()`，而 `DockerExecutor.create()` 要求 `workspace_root` 已存在 → **任何全新 workspace** 下的 docker 执行器都以「沙箱工作区不存在」失败 | **候选（业务代码）缺陷** |
| F4 | 即使临时修正 F3 的顺序（未提交试验），docker 路径仍在冻结的 `timeout_seconds=600` 内不闭合，业务路径 0 provider 响应、0 事件 | 候选路径 + provider，未定论 |

对照：同一 agent + 同一 provider + 同一 case 在 local 执行器下 **12 次调用 / 83s** 全部正常，证明 provider 与 agent 本身健康（F5）。

按 Spec 13 的 `No-implementation Boundary` 与 Stop Conditions，本轮**不热修**业务代码、**不**事后调高冻结预算、**不**把失败 run 发布为 Evidence —— 而是如实记 `13 BLOCKED`，把 F3 的最小修改建议与恢复条件写入校准记录 §11.6，交回 pre-freeze 子 Spec 形成新候选。失败 run 已按 Spec 13 要求保留在 `output/contract-validation/{staging/,}failed-runs/`。

### 全程红线

- Legacy 主路径**永不消费** Foundation 对象；Foundation 不参与模型选择、路由、评分、成本报告、Dashboard、恢复、审批与副作用。
- presence-aware：facts extractor 禁止 `get(..., 0)` / `or 0` / 由 legacy total 反推组成项。
- `off == observe` 四类不变性：Output / Decision / Side Effects / Legacy Telemetry。
- `agent_core/` 白名单只有 `__init__.py` + `contracts/**`。
- 证据发布只允许 allowlist 重建，禁止"先全量序列化再删敏感字段"。
- Spec 11 冻结 Candidate A 后，**不得再新增/修改任何 post-freeze 工具**；缺工具只能 `SUPERSEDED` 回所属 Spec 形成 A2。

### 相关文档

- 母 Spec：`docs/specs/2026-09-10-dual-agent-foundation-contract-master-spec.md`
- 执行索引与 18 个子 Spec：`docs/specs/foundation-contract/`
- 决策记录：`docs/adr/0001-progressive-contract-family-extraction.md`、`docs/adr/0002-foundation-fact-semantics-and-shadow-governance.md`
- 开工准备（环境 / 基线 / worktree / 红线 / 风险）：`docs/plans/2026-09-10-foundation-contract-cycle1-kickoff.md`

---

## 技术栈

| 层级 | 方案 |
|------|------|
| 语言 | Python 3.12+ |
| 数据存储 | SQLite（实体注册表 + 源索引 + Wiki 页面） |
| 向量检索 | FAISS (IndexFlatIP) + BGE-small-zh-v1.5 (512-dim) |
| LLM API | DeepSeek（OpenAI SDK 兼容）· 火山 Ark / opencode zen-go 网关（评测 judge） |
| Agent | LangGraph ReAct Agent |
| Web | FastAPI + SSE 流式 |
| 前端 | 原生 HTML/CSS/JS（PRTS 终端风格） |
| 评测 | DeepEval 4.1.8（Docker）+ Benchmark 100 题 + mimo-v2.5 judge |
| 契约层 | `agent_core.contracts` v0.1.0（双仓镜像）+ Pydantic 2.13.4 + 共享 conformance + canonical JSON / payload hash / mirror bundle |
| 测试 | pytest（`pytest tests/`：854 passed / 10 skipped；含 `tests/contracts/` 311 项契约测试） |

---

## 目录结构

```
Arknights LLM Wiki/
├── agent_core/                   # 契约镜像（Phase 1 白名单：仅 __init__.py + contracts/**）
│   └── contracts/                # version / contract.md / payload-descriptor.json
│       ├── enums/ models/ protocols/
│       ├── conformance/          # 共享契约测试（两仓逐字节一致）
│       ├── schemas/              # 6 个 JSON Schema
│       └── tooling/              # canonical_json / generate_schemas / verify_payload / bundle
├── docs/
│   ├── specs/                    # 设计规格
│   │   └── foundation-contract/  # 执行索引 00 + 子 Spec 01–18 + execution-status-events.jsonl
│   ├── plans/                    # 实施计划
│   ├── diagrams/                 # 架构图 (Mermaid + HTML)
│   └── adr/                      # 架构决策记录
├── arknights_wiki/
│   ├── extraction/               # Pass 1/2/3 提取模块
│   ├── agent/                    # LangGraph Agent
│   │   ├── server.py             # FastAPI + SSE 服务
│   │   ├── static/               # 前端 (HTML + CSS + JS)
│   │   ├── router.py             # 意图识别 + 实体提取 + 复杂度分类
│   │   ├── simple_search.py      # 多层检索管线
│   │   ├── graph.py              # LangGraph ReAct Agent
│   │   ├── tools.py              # 8 个检索工具
│   │   ├── retrieval.py          # Wiki/Event/Dialogue/Timeline 数据层
│   │   └── prompts.py            # LLM 提示词模板
│   ├── adapters/foundation/      # 项目本地 Adapter（facts / mapping / runtime / evidence_sink）
│   └── store/                    # SQLite 数据层
├── config/
│   ├── chapter_timeline.json     # 章节时间线
│   ├── collab_series.json        # 联动活动映射
│   ├── identity_map.json         # 角色身份映射
│   └── contracts/                # producer-registry / known-test-baseline / smoke-v0.1 / replay-v0.1
├── data/
│   ├── stories/                  # 原始剧情对话 (2,160 JSON)
│   ├── extractions/
│   │   ├── v1_events/            # Pass 1 事件 (106 章)
│   │   ├── v2_characters/        # Pass 2 角色 Wiki (641 角色)
│   │   └── v3_wiki/              # Pass 3 世界观 Wiki
│   ├── lorebook/                 # 大地巡旅描述 (原始数据在仓库外)
│   ├── entity_source_map.json    # 实体双向索引 (2.3MB)
│   └── index/                    # FAISS 向量索引
├── scripts/
│   ├── build_agent_index.py      # FAISS 向量索引
│   ├── build_entity_index.py     # 实体双向索引
│   └── contracts/                # 契约工具：validate_local / status_ledger / replay_history
│                                 #          publish_evidence / coordinate_cycle / finalize_cycle
├── tests/
│   └── contracts/                # 契约测试：mapping / sink / wiring / invariance / baseline
│                                 #          packaging / 工具自测（311 项）
└── .github/workflows/            # contract-local / contract-payload-linux / contract-coordinate
```

---

## 数据规模

| 数据层 | 文件数 | 字符数 | 约合 Tokens | 数据来源 |
|--------|--------|--------|-------------|----------|
| 原始剧情对话 | 2,160 | 3,710 万 | 1,237 万 | PRTS Wiki (prts.wiki) 抓取 |
| 干员档案 | 1 | 133 万 | 44 万 | PRTS Wiki 干员页面抓取 |
| Pass 1 事件标注 | 106 章 | 243 万 | 81 万 | LLM 提取 (DeepSeek) |
| Pass 2 角色 Wiki | 642 角色 | 128 万 | 43 万 | LLM 提取 (DeepSeek) |
| Pass 3 世界观 Wiki | 1,757 页面 | 121 万 | 40 万 | LLM 提取 (DeepSeek) |
| 视频字幕 | 37 个 | 5 万 | 2 万 | 官方视频 (手动转录) |
| **合计** | — | **4,337 万** | **1,447 万** | |

| 索引层 | 规模 |
|--------|------|
| 实体双向索引 (entity_source_map.json) | 5,213 实体 / 25,300 引用 / 2.0 MB |
| FAISS 向量索引 (BGE-small-zh-v1.5, 512-dim) | 6,666 向量 / 13.7 MB |
| chunk_map 分块映射 | 6.2 MB |

---

## 许可证

本项目仅用于学习和研究目的。明日方舟及其相关内容版权归 Hypergryph / Studio Montagne 所有。
