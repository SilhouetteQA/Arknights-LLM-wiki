---
name: session-summary
description: 结束会话时调用，总结当前会话的关键决策、架构变更、进度状态，写入 project memory 供下个会话恢复。
---

# 会话总结 (Session Summary)

结束当前会话前调用。产出两部分：1) memory 文件供下个会话加载 2) 面向用户的简洁总结。

## 步骤

### 1. 回顾当前会话内容
从对话历史中提取：
- 关键决策 (做了什么设计选择，为什么)
- 架构变更 (新增/修改/删除了什么模块或文件)
- 进度状态 (当前处于哪个 Phase/Step，完成度如何)
- 未解决问题 (open questions, blockers)
- 下一步行动 (下个会话应该从哪开始)

### 2. 写入 project memory
路径: `$HOME/.claude/projects/D--AI-project-Arknights-LLM-Wiki/memory/`

文件命名: `session_YYYYMMDD_topic.md`

frontmatter:
```yaml
---
name: session-YYYYMMDD-topic
description: "一句话描述"
metadata:
  type: project
---
```

内容: 决策、架构、进度、下一步。

### 3. 更新 MEMORY.md 索引
在 `memory/MEMORY.md` 文件末尾添加一行链接:
`- [Session YYYY-MM-DD Topic](session_YYYYMMDD_topic.md) — 一句话摘要`

### 4. 输出面向用户的总结
简洁汇报：做了什么决定、当前进度、下个会话第一步。
