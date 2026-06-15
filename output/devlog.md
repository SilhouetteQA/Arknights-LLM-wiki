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
