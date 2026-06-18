# 明日方舟剧情 LLM Wiki（重构版）

基于 PRTS Wiki 抓取的《明日方舟》全量剧情知识库。结构化对话存储 + 知识图谱 + FAISS 向量检索 + LLM RAG 问答。

> **来源项目**: `D:\AI project\mrfz`（保持不动，逐步迁移）
> **重构目标**: 清理技术债务、收敛代码组织、完善工程质量

---

## 项目状态

| 维度 | 值 | 说明 |
|------|-----|------|
| Phase | 0 - 初始化 | 已完成，规则体系+骨架就绪 |
| 数据 | 待从 mrfz 迁移 | 1,112/1,651 节点, 105/108 章 |
| 技术栈 | 已确认 | 保持 mrfz 选型，核心改代码组织 |

---

## 技术栈

| 层级 | 方案 | 说明 |
|------|------|------|
| 语言 | Python 3.12+ | 保持 |
| 数据存储 | SQLite | 精简单表职责，JSON 仅归档 |
| 向量检索 | FAISS + BGE-small-zh-v1.5 | 抽象为独立模块 |
| LLM API | OpenAI SDK (MiniMax M2.5 + DeepSeek) | 剥离 tokenizer，结构化成本日志 |
| Web 框架 | FastAPI + SSE | 保持 |
| 前端 | 原生 HTML+CSS+JS | CSS/JS 从单文件拆分为独立文件 |
| 代码组织 | scripts/ → arknights_wiki/ 包 | 拆分 God Object，每表一个 repository |
| 依赖管理 | pyproject.toml (PEP 621) | 从 requirements.txt 升级 |
| 测试 | pytest + TDD | 逐模块补测试 |

---

## 目录结构

```
Arknights LLM Wiki/
├── README.md
├── pyproject.toml                 # 依赖与项目元数据（待创建）
├── docs/
├── CLAUDE.md                     # 项目规则（开发流程/Git/多会话管理）
├── arknights_wiki/               # 主代码包（待迁移）
│   ├── cli.py
│   ├── config.py
│   ├── store/repositories/
│   ├── pipeline/
│   ├── retrieval/
│   ├── llm/
│   └── web/
├── config/
│   ├── llm_config.json
│   └── hooks/                    # 会话管理 Hook 脚本
├── output/
│   ├── devlog.md
│   └── sessions/
└── .claude/
    ├── settings.local.json
    └── skills/architecture-diagrams/
```

---

## 下一步

1. 产出整体架构 Spec + 迁移 Plan
2. 确定首个迁移模块（建议 `store/` 数据层）
3. 用户深度参与每个模块设计

---

## Phase 1 完成 (2026-06-15)

| 维度 | 值 |
|------|-----|
| 故事节点 | 1,663/1,669 (99.6%) |
| 干员档案 | 420/420 (100%, 1,134,547 字) |
| 模块文件 | 8 个 pipeline 模块 + config + utils |
| 测试 | 87 全部通过 |
| 源码行数 | ~940 行 |

## Phase 2: M0 store/ 完成 + 质量修复 (2026-06-16)

| 维度 | 值 |
|------|-----|
| character 实体 | 381 (仅干员，异格去重) |
| faction / region | 44 / 34 |
| 别名映射 | 40 (异格→基体) |
| source_index | 3,615 (仅干员档案) |
| 测试 | 119 全部通过 |
| seed 耗时 | <2 秒 |

### M0 职责边界

- M0 只做确定性种子：干员/faction/region + 别名 + 档案索引
- NPC 实体 + 故事对话索引 → M1 按需创建
- 概念实体 + 关键词索引 → M3 LLM 提取

## Pass 1 剧情骨架提取完成 (2026-06-16)

| 维度 | 值 |
|------|-----|
| 架构 | v3 三遍独立提取 |
| 模型 | DeepSeek v4-flash (MiniMax M3 因 think 块问题淘汰) |
| 提取模块 | 5 文件 (dialogue_loader/prompt_builder/llm_client/post_processor/orchestrator) |
| 测试 | 163 all pass (28 extraction + 135 existing) |
| 试跑 | 6 章全成功, $0.08, ~5 min |
| 分支 | feature/pass1-event-extraction |

## 下一步

审阅试跑质量 → 修复问题 → 全量 109 章 Pass 1 执行
