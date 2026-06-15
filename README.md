# 明日方舟剧情 LLM Wiki（重构版）

基于 PRTS Wiki 抓取的《明日方舟》全量剧情知识库。结构化对话存储 + 知识图谱 + FAISS 向量检索 + LLM RAG 问答。

> **来源项目**: `D:\AI project\mrfz`（保持不动，逐步迁移）
> **重构目标**: 清理技术债务、收敛代码组织、完善工程质量

---

## 项目状态

| 维度 | 值 | 说明 |
|------|-----|------|
| Phase | 0 - 初始化 | 项目骨架搭建中 |
| 数据 | 待从 mrfz 迁移 | 1,112/1,651 节点, 105/108 章 |
| 技术栈 | 待确定 | 见下方讨论 |

---

## 技术栈（待定）

| 维度 | mrfz 原方案 | 重构建议 |
|------|------------|----------|
| 语言 | Python 3.12 | 保持 |
| 数据存储 | SQLite + JSON | 统一到 SQLite，JSON 仅做归档 |
| 向量检索 | FAISS + BGE-small-zh-v1.5 | 待讨论 |
| LLM API | MiniMax M2.5 + DeepSeek | 待讨论 |
| Web 框架 | FastAPI + SSE | 保持 |
| 前端 | 原生 HTML+CSS+JS | 待讨论 |
| 依赖管理 | requirements.txt | 升级到 pyproject.toml |
| 测试 | pytest | 保持 |

---

## 目录结构

```
Arknights LLM Wiki/
├── README.md                     # 项目总览
├── docs/
│   └── project-rules.md          # 项目规则（Git/会话/协作）
├── config/
│   ├── llm_config.json           # LLM 模型配置
│   └── hooks/                    # 会话管理 Hook 脚本
├── output/
│   ├── devlog.md                 # 开发日志
│   └── sessions/                 # 会话总结
├── .claude/
│   └── settings.local.json       # Claude Code 项目设置
└── .gitignore
```

---

## 下一步

1. 确定项目管理规则（B-01 ~ B-06）
2. 确定技术栈选型
3. 确定目录架构设计
4. 开始从 mrfz 迁移代码
