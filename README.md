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
│   └── project-rules.md          # 四章项目规则
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

## 下一步

Phase 2: 知识图谱生成 — 迁移 mrfz `scripts/extraction/` 子包
