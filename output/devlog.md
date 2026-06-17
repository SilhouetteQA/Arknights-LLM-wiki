# 明日方舟 LLM Wiki — 开发日志

> 重构项目，来源 `D:\AI project\mrfz`（原项目保持不动，逐步迁移）。

---

## Phase 0: 项目初始化 (2026-06-15)

### 决策

- 规则体系继承全局 CLAUDE.md，项目规则仅保留差异化内容
- 开发流程采用 Superpowers 方法论： brainstorming → writing-plans → subagent-driven-development + TDD → Codex Review → diagnose修复
- 数据质量从自动化 QA 改为用户预设问题 + 抽查
- 技术栈整体保持 mrfz 验证的选型（SQLite/FAISS/BGE/FastAPI），核心改变在代码组织
- 代码从 `scripts/` 松散结构迁移到 `arknights_wiki/` Python 包

### 文件

| 文件 | 说明 |
|------|------|
| docs/project-rules.md | 四章项目规则 |
| config/hooks/session-start.sh | 会话启动 Hook |
| config/hooks/session-end.sh | 会话结束 Hook |
| .claude/settings.local.json | Hook + 权限配置 |
| .claude/skills/architecture-diagrams/ | 架构图 skill |

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/ 下最新文件 — 上次会话详情
4. 下一步：开新会话 → 产出第一份 Spec（整体架构+迁移策略）

---

## Phase 1: 原始内容提取 (2026-06-15)

### 架构决策

- 代码从 `scripts/` 迁移到 `arknights_wiki/` Python 包
- `pipeline.py` 改名 `orchestrate.py` 避免与包名冲突
- 工具函数拆分为 `config.py`（配置）+ `_utils.py`（纯工具），LLM 工具留到 Phase 2
- 干员档案解析器适配 PRTS Wiki 的 `<table class="wikitable">` 格式

### 数据基线

| 指标 | 值 |
|------|-----|
| 故事节点 | 1,663/1,669 |
| 干员档案 | 420/420 (1,134,547 字) |
| 测试数 | 87 |

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策和数据基线
3. 读 output/sessions/ 下日期最新的会话总结
4. 下一步：M0 质量评估（用户审阅 entity md 后），然后进入 M1 chapter 页面生成

---

## M0 store/ 完成 (2026-06-15)

### 架构决策

- 4 张 SQLite 表：entities / entity_aliases / source_index / wiki_pages
- 3 个 Repository 类每表一个，seed.py 编排种子流程
- 异格自动提取：PRTS Wiki API `Category:异格干员` → `config/identity_map.json` (40 条)
- 概念关键词索引：`config/concept_keywords.json` (9 个概念) → source_index match_type=concept_keyword
- 无名 NPC 过滤：5 类正则模式，行级过滤，边界 case 保留供 M3 处理
- 实施方法：Spec → Plan → Subagent-Driven TDD (8 commits, 31 new tests)

### 数据基线

| 指标 | 值 |
|------|-----|
| character | 3,766 (420 干员 + 3,346 NPC) |
| faction | 44 |
| region | 34 |
| concept | 9 |
| aliases | 40 |
| source_index(exact) | 246,214 |
| source_index(concept_keyword) | 4,794 |
| 章节覆盖 | 109/109 (100%) |
| 测试 | 119 全部通过 |

### 已知问题

- 少量泛型 NPC 未被过滤（路过的观众A、黑帮A/B、老奶奶 等）
- seed_concept_keywords O(n*m) 复杂度，当前够用但可优化
- chapter 实体未种子（M1 处理）
- 23/1663 节点未索引

### 审阅文档

- `output/m0_seed_summary.md` — 总体统计
- `output/m0_entities_by_chapter/` — 109 章实体覆盖 md

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 memory/session_20250615_m0_store.md — 完整会话记录
4. 下一步：用户审阅 entity md → M0 质量评估修复 → 通过后进入 M1 chapter

---

## 数据整理 (2026-06-17)

### 架构决策

- **5级剧情分类**：`config/story_taxonomy.json` 将 109 章分为 full(91)/is(6)/ra(2)/light(7)/skip(3)。Why: 不同类型剧情在 KG 中的意义权重不同，不能一刀切全量提取
- **IS 仅保留结局**：藏品/事件/月度小队全部删除。结局完整叙事文本从 PRTS Wiki 记录页（深蓝记录仪/冬夜展览馆/巫仪档案库/见字图册）提取，写入 `{node}_ending.json` 与 story node 并列。Why: 结局文本是最核心的叙事数据（每结局 3-4 Parts，50-100 行），藏品/事件属于碎片化侧面信息
- **向下兼容**：taxonomy 新增字段，保留 index.json 的 category

### 数据基线

| 指标 | 值 |
|------|-----|
| 剧情纯文本 | 560万字 (~310万 tokens) |
| IS 结局覆盖 | 水月(4) + 探索者(4) + 萨卡兹(5) + 岁(5) = 18 个 ~90K chars |
| IS 未覆盖 | 傀影(无对应 PRTS 格式)、刻俄柏(无记录页) |

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-17-1.md — 上次 Pass 1 质量修复
4. 下一步：切回 feature/pass1-event-extraction → 适配 IS 结局读取 → 全量 109 章 Pass 1
