# 项目规则 — 明日方舟剧情 LLM Wiki（重构版）

本文档定义本项目的开发、管理和协作规则。全局通用规则见 `CLAUDE.md`，本文档仅包含本项目**差异化**规则。

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

不设置自动化批量 QA 体系。数据质量由以下方式保障：

- **用户预设问题**：在 Spec 阶段由用户定义关键验证问题（10-20 个）
- **抽查机制**：每个 Phase 完成后，用户抽查预设问题的答案质量
- **质量门槛**：预设问题通过率达标后，方可进入下一 Phase

### 1.4 效率与成本监控

每个处理步骤必须自动记录并汇总以下指标：

| 指标 | 说明 | 记录方式 |
|------|------|----------|
| 步骤耗时 | 每步开始/结束时间戳，计算 elapsed | 代码内置，输出到日志 |
| API 调用次数 | 每步 LLM API 请求数 | 代码内置计数 |
| Token 消耗 | 每步 input/output token 合计 | 从 API response 提取 |
| 费用 | 按模型单价实时计算 | `token * price` |
| 缓存命中率 | 增量处理中的缓存命中数/总数 | 从缓存层读取 |

监控数据在每次会话总结中汇总，写入 `output/sessions/YYYY-MM-DD-N.md`（N 为当天序号，从 1 开始） 的数据基线段落。

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

### 3.1 三个持久化文件

| 文件 | 位置 | 写入内容 | 更新时机 |
|------|------|----------|----------|
| **README.md** | 项目根目录 | 项目状态、数据基线、Phase 进度、遗留问题、技术栈、常用命令 | 项目关键信息变更时 |
| **Devlog** | `output/devlog.md` | 开发过程总结、架构决策、遇到的问题和解决方案 | 每次会话有实质进展时 |
| **会话总结** | `output/sessions/YYYY-MM-DD-N.md`（N 为当天序号，从 1 开始） | 本次会话对话轮次、每轮解决内容、修改文件清单、遗留问题、下一步计划 | 每次会话结束时 |

### 3.2 Hook 机制

通过 Claude Code 的 settings.local.json 配置了两个 Hook：

- **SessionStart Hook**：会话启动时自动提示读取 README → devlog → 最新会话总结
- **Stop Hook**：会话结束时自动提示写入会话总结 → 更新 README → 更新 devlog

Hook 脚本位于 `config/hooks/`：
- `session-start.sh`：输出上下文恢复检查清单
- `session-end.sh`：输出状态保存检查清单

### 3.3 新会话启动流程

1. Hook 自动提示阅读三个文件
2. 形成认知：当前 Phase、数据基线、下一步做什么
3. 确认关键资源状态（数据库、索引、模型配置）

### 3.4 会话结束流程

1. Hook 自动提示保存
2. 写 `output/sessions/YYYY-MM-DD-N.md`（N 为当天序号，从 1 开始）（对话轮次+解决内容+修改清单+遗留问题+下一步）
3. 如有数据基线/Phase 变化，更新 README.md 对应表
4. 如有架构决策/关键发现，更新 `output/devlog.md`

---

## 四、新增规则

| 编号 | 规则 | 说明 |
|------|------|------|
| N-01 | **多与人交互** | 不自行做重大决策。遇到模糊需求、多种方案、设计取舍时，主动与用户沟通确认。使用 `/grill-with-docs` 深挖用户需求，基于领域文档追问，把澄清的术语和决策写入文档 |
| N-02 | **每个文件审查用途** | 每个文件、每个函数的用途需经用户审查确认。创建新文件前说明其职责和理由 |
| N-03 | **开发过程详细记录** | 每个模块、每个程序文件的开发过程尽量详细。在会话总结中记录关键设计决策和实现细节 |
| N-04 | **迁移变更需审批** | 重构过程中，每次从 mrfz 原项目的代码迁移和架构变更都需经用户同意后再执行 |
