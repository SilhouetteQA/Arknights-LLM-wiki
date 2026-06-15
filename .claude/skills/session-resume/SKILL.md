---
name: session-resume
description: 新会话开始时调用，加载上次会话总结、检查项目状态、呈现当前进度。用户输入"恢复会话"/"继续"/"resume"时触发。
---

# 会话恢复 (Session Resume)

新会话开始时调用，快速恢复上次工作上下文。

## 步骤

### 1. 加载 memory
- 读取 `$HOME/.claude/projects/D--AI-project-Arknights-LLM-Wiki/memory/MEMORY.md`
- 读取最近的 session 文件 (按日期排序取最新)
- 读取所有 feedback/project 类型的 memory

### 2. 检查项目状态
```bash
# 检查 git 状态和最近提交
git status
git log --oneline -5

# 检查项目文件结构变化
ls -la 确认关键目录存在
```

### 3. 运行现有测试
```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```
确保进入工作前知道当前测试状态。

### 4. 输出恢复摘要
汇报：
- 上次会话做了什么决定
- 当前项目 Phase/进度
- 测试状态 (通过/失败数)
- 下一步要做什么
