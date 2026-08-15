# CLAUDE.md — 明日方舟剧情 LLM Wiki（重构版）

本文档定义本项目的开发、管理和协作规则。全局通用规则见用户目录下的 `CLAUDE.md`，本文档仅包含本项目**差异化**规则。

---

## 一、开发流程规则

本项目采用 Superpowers 方法论驱动开发，完整流程如下：

### 1.1 流程概览

```
需求浮现
  │
  ▼
[1. Spec]  使用 superpowers:brainstorming 澄清意图 → 产出设计规格
  │  - 问题背景、目标与范围、技术方案、风险与取舍
  │  - 存放: docs/specs/YYYY-MM-DD-slug.md
  │
  ▼
[2. Plan]  使用 superpowers:writing-plans 产出实施计划
  │  - 关联 Spec，拆解为可执行任务（checkbox），每项含文件变更范围和验证标准
  │  - 存放: docs/plans/YYYY-MM-DD-slug.md
  │
  ▼
[3. 实施]  使用 superpowers:subagent-driven-development 并行推进独立任务
  │  - 复杂子任务派发 P7 sub-agent 独立执行
  │  - 使用 superpowers:test-driven-development 以 TDD 方式编写代码
  │  - 使用 architecture-diagrams skill 分析生成的代码结构/依赖/数据流
  │
  ▼
[4. Codex Review]  完成后使用 codex:code-review 审查变更
  │
  ▼
[5. 修复]  使用 superpowers:systematic-debugging 或 /diagnose 定位并修复问题
  │
  ▼
[6. Commit]  问题修复后 commit，原则上禁止在 review 完成前提交
```

### 1.2 架构分析工具

项目已安装 `architecture-diagrams` skill（位于 `.claude/skills/architecture-diagrams/`），支持 Mermaid / PlantUML / C4 / 流程图 / 序列图。在以下节点必须使用该 skill 分析产出：

| 触发时机 | 分析内容 |
|----------|----------|
| Spec 产出后 | 用 C4 Context 图分析系统边界和外部依赖 |
| Plan 产出后 | 用流程图分析任务依赖关系和执行顺序 |
| 实施完成时 | 用组件图分析代码模块结构和数据流 |
| 重构前后 | 对比架构变化，生成迁移图 |

### 1.3 数据质量保障

不设置自动化批量 QA 体系。质量由人工逐项验证：提取结果自带 line_range 源引用，可直接追溯到原文对应位置逐一核对。

### 1.4 效率与成本监控

每个处理步骤必须自动记录并汇总以下指标：

| 指标 | 说明 | 记录方式 |
|------|------|----------|
| 步骤耗时 | 每步开始/结束时间戳，计算 elapsed | 代码内置，输出到日志 |
| API 调用次数 | 每步 LLM API 请求数 | 代码内置计数 |
| Token 消耗 | 每步 input/output token 合计 | 从 API response 提取 |
| 费用 | 按模型单价实时计算 | `token * price` |
| 缓存命中率 | 增量处理中的缓存命中数/总数 | 从缓存层读取 |

监控数据在会话有实质进展时汇总到 `output/devlog.md`。

---

## 二、Git 使用规则

| 编号 | 规则 | 说明 |
|------|------|------|
| G-01 | **功能分支隔离** | 新功能/重构前从主分支创建 feature 分支，不直接在 master 上开发 |
| G-02 | **小步提交** | 每个逻辑完成点 commit，不攒大量改动一次性提交 |
| G-03 | **提交前检查** | commit 前确认无临时文件、无密钥、无敏感信息混入 |
| G-04 | **不强制推送** | 禁止 `--force` push 到共享分支，禁止 amend 已推送的 commit |
| G-05 | **.gitignore 覆盖** | 排除数据产物（`data/stories/`、`data/index/`）、缓存（`__pycache__/`、`.cache/`）、IDE 配置、临时输出 |
| G-06 | **迁移需审批** | 重构过程中每次代码迁移/架构变更需经用户同意后方可提交 |

---

## 三、多会话管理规则

### 3.1 两个持久化文件

| 文件 | 位置 | 写入内容 | 更新时机 |
|------|------|----------|----------|
| **README.md** | 项目根目录 | 项目状态、数据基线、Phase 进度、遗留问题、技术栈、常用命令 | 项目关键信息变更时 |
| **Devlog** | `output/devlog.md` | 开发过程总结、架构决策、遇到的问题和解决方案 | 每次会话有实质进展时 |

### 3.2 新会话启动流程

1. 读 README.md — 项目状态、数据基线、遗留问题
2. 读 output/devlog.md — 最新架构决策和开发日志
3. 确认关键资源状态（数据库、索引、模型配置）

### 3.3 会话结束流程

1. 如有数据基线/Phase 变化，更新 README.md 对应表
2. 如有架构决策/关键发现，更新 `output/devlog.md`

---

## 四、新增规则

| 编号 | 规则 | 说明 |
|------|------|------|
| N-01 | **多与人交互** | 不自行做重大决策。遇到模糊需求、多种方案、设计取舍时，主动与用户沟通确认。使用 `/grill-with-docs` 深挖用户需求，基于领域文档追问，把澄清的术语和决策写入文档 |
| N-02 | **每个文件审查用途** | 每个文件、每个函数的用途需经用户审查确认。创建新文件前说明其职责和理由 |
| N-03 | **开发过程详细记录** | 每个模块、每个程序文件的开发过程尽量详细。在 devlog 中记录关键设计决策和实现细节 |
| N-04 | **迁移变更需审批** | 重构过程中，每次从 mrfz 原项目的代码迁移和架构变更都需经用户同意后再执行 |

---

## 五、升级阶段规则（依据《01_现有明日方舟LLM_Wiki项目评估与升级方案.md》）

> 项目定位升级为：**基于大规模剧情知识图谱与 LangGraph Agent 的领域自治研究 Agent**。
> 核心目标从「证明我会 LLM+RAG+Agent」升级为「证明我能把 Agent 做成**可评测、可观测、可控、可恢复**的生产级系统」。
> 升级路线图见 `docs/plans/2026-08-15-upgrade-roadmap.md`，每个任务对应一个独立会话窗口。

| 编号 | 规则 | 说明 |
|------|------|------|
| U-01 | **窗口任务制** | 每个会话（窗口）只处理路线图中的一个任务。进入窗口：读 README.md + output/devlog.md + 路线图对应任务；退出窗口：更新 devlog.md 与路线图任务状态（✅/⏳/❌） |
| U-02 | **数据规模冻结** | 升级阶段停止扩大剧情数据量（不再新增章节/故事），全力投入系统能力建设 |
| U-03 | **评测优先** | Agent 能力任何变更（工具/节点/prompt/路由）前必须先建立 Benchmark 基线，变更后重跑对比，指标（Answer Correctness / Faithfulness / Context Precision / Context Recall / Citation Accuracy / Tool Selection Accuracy / Hallucination Rate / Task Completion Rate）记录到 devlog。无评测对照的 Agent 变更禁止合并 |
| U-04 | **全链路可观测** | 每次 Agent 执行必须可产出完整 Trace（User Request → Planner → Agent Handoff → Retrieval → Tool Call → LLM Call → Retry → Critic → Final Answer），每步记录 latency / tokens / model / tool / error / retry / cost。技术方向：**Langfuse + OpenTelemetry** |
| U-05 | **MCP 优先接入** | 知识库能力优先包装为标准 MCP Server（search_entities / search_events / query_relationship / query_timeline / search_story），Agent 通过标准化工具协议访问外部能力，证明 Tool Protocol 能力 |
| U-06 | **显式规划** | 复杂问题必须经显式 Planner 拆解为任务图（并行/串行执行 + 结果聚合），禁止无规划的隐式多步推理 |
| U-07 | **失败恢复必做** | 工具调用必须实现 timeout → retry → exponential backoff → circuit breaker → fallback → checkpoint/resume → human escalation 的恢复链；考虑 idempotency 与 partial failure |
| U-08 | **安全护栏** | 所有工具定义权限分级（READ / WRITE / DELETE / ADMIN），不同 Agent 不同权限；LLM 输出必须经 Pydantic / JSON Schema 校验；外部内容一律视为不可信（防 prompt injection）；用户记忆数据隔离 |
| U-09 | **人工确认** | 高风险操作（修改/删除数据、发布内容、外部 API 写操作）必须 Human-in-the-loop 人工确认后才执行 |
| U-10 | **成本性能量化** | 每次执行记录 P50/P95 Latency、Tokens/Request、Cost/Request、Tool Calls/Request、Retry Rate、Success Rate；优化手段（prompt cache / retrieval cache / result cache / model routing / 小大模型分工 / parallel tool calls / context compression / streaming）必须用数据佐证 |
| U-11 | **多 Agent 按需** | 多 Agent 划分必须基于职责（Research Manager → KG/Timeline/Character Agent → Critic → Final Writer），不为多而多；需展示 routing / handoff / parallel execution / state sharing / failure recovery |
| U-12 | **Memory 分层** | 短期（任务状态）/ 长期（用户偏好、常问主题、历史任务）/ 情景（历史任务结果复用）三层记忆，用户间数据隔离 |
| U-13 | **上下文预算** | 本仓库数据规模大（原始剧情 3,710 万字），主会话上下文有限：探索/调研/大规模阅读任务必须派发子代理执行并只收结构化报告，主会话禁止通读大文件（>2,000 行或 >500KB 的文件一律子代理处理） |
| U-14 | **评估基准建库** | 建立固定 Benchmark（100–500 条高质量问题，覆盖单跳/多跳/时间线/人物关系/跨章节/多工具/无答案/易幻觉八类），作为全部后续 Agent 版本对比的固定标尺（Agent V1 → 82% → V2 → 89% → V3 → 94% 的演进证据链） |

---

## 六、升级阶段工作流（覆盖一~五章规则）

每个升级任务窗口的标准流程：

1. **领任务**：从路线图取一个任务（窗口任务制 U-01）
2. **探索**：涉及的大文件/未知模块派发子代理探索（U-13），只收报告
3. **Spec**：用 superpowers:brainstorming 产出设计规格 → `docs/specs/YYYY-MM-DD-slug.md`
4. **Plan**：用 superpowers:writing-plans 产出实施计划 → `docs/plans/YYYY-MM-DD-slug.md`
5. **评测基线**（U-03）：若任务涉及 Agent 行为变更，先在 Benchmark 上跑基线
6. **实施**：superpowers:subagent-driven-development + TDD，按 G-01 建 feature 分支
7. **验证**：重跑 Benchmark 对比指标（U-03）；补 Trace 验证可观测性（U-04）
8. **Review**：codex:code-review 审查，修复后再提交（禁止 review 前 commit）
9. **记录**：更新 output/devlog.md（指标、决策、问题）+ 路线图任务状态

> 备注：U-14 的 Benchmark 建库为 P0 首任务，其完成后所有涉及 Agent 行为的任务（U-03）才可开始。

