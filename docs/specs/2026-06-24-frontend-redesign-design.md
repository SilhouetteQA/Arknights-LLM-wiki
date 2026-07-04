# Spec: Agent 前端 UI 重设计

**日期**: 2026-06-24
**状态**: 已完成
**关联**: feature/langgraph-agent

## 背景

当前 `server.py` 内嵌 ~60 行原生 HTML，深蓝色调，仅消费 SSE `token` 事件。缺失：
- 检索步骤可视化（`route`/`step` 事件未渲染）
- 来源展开/引用溯源（`sources` 事件未渲染）
- 流式 token 渲染（当前按 50 字符分块，非真正逐字）
- Loading/空状态/错误状态
- distinctive 视觉设计（generic dark theme）

## 设计决策

### 美学方向: PRTS 终端 (Retro-Futuristic Terminal)

模拟游戏内 PRTS 系统界面。工业感等宽字体体系 + 罗德岛靛蓝/琥珀配色 + CRT 纹理效果。

### 布局: 双栏 (Split Panel)

```
+------------------------------------------+
|  Header: PRTS v3.7.1 | 数据库就绪 | 统计   |
+------------------------------------------+
|  Chat Panel (flex:1)  |  Search Panel     |
|                        |  (280px)          |
|  - 用户消息(右对齐)      |  - 路由步骤卡片     |
|  - 路由信息条           |  - 语义搜索结果     |
|  - AI 回答卡片(角标)     |  - 来源清单        |
|                        |                   |
+------------------------------------------+
|  > 命令输入区_______________[执行]         |
+------------------------------------------+
|  Status: READY | Latency | Tokens        |
+------------------------------------------+
```

### 字体

| 角色 | 字体 | 备选 |
|------|------|------|
| 标题/标签 | Share Tech Mono | monospace fallback |
| 正文/代码 | Source Code Pro | monospace fallback |

### 配色

| CSS 变量 | 色值 | 用途 |
|----------|------|------|
| `--bg-root` | #080c14 | 页面底色 |
| `--bg-panel` | #0d1525 | 面板/卡片底色 |
| `--bg-input` | #060a12 | 输入区底色 |
| `--bg-hover` | #152030 | 悬停/选中态 |
| `--accent-blue` | #4fc3f7 | 系统状态/链接/用户消息 |
| `--accent-amber` | #ffb000 | 标题/检索步骤/警告 |
| `--accent-gold` | #e6b422 | 关键数据/引用编号 |
| `--text-primary` | #c8d6e5 | 正文内容 |
| `--text-secondary` | #5a6a80 | 时间戳/元数据 |
| `--border-dim` | #1a2740 | 面板分割线 |

### 纹理/效果

| 效果 | 实现 | 强度 |
|------|------|------|
| 文字发光 | text-shadow (blue/amber) | 标题、系统状态、步骤标签 |
| 发光边框 + 角标 | 1px border + 四角 L 形 ::before/::after | 面板、卡片 |
| 自定义光标 | caret-color: amber; cursor: crosshair | 输入区、按钮 |

不包含扫描线（会影响可读性）和噪点纹理（token 消耗与收益不成正比），按用户选择 2/4/5 执行。

## 文件变更

### 新建

| 文件 | 职责 |
|------|------|
| `arknights_wiki/agent/static/style.css` | 全部 CSS（变量、布局、组件、动画） |
| `arknights_wiki/agent/static/app.js` | SSE 事件消费、DOM 更新、交互逻辑 |

### 修改

| 文件 | 变更 |
|------|------|
| `arknights_wiki/agent/server.py` | 删除内嵌 HTML；挂载 static/ 目录；`/` 路由返回独立 HTML 文件或用 `HTMLResponse` 读取模板 |

> 实际实施时 server.py 可改为 Jinja2 模板或保持 HTMLResponse 从文件读取，具体在 Plan 阶段决定。

## 组件树

```
index.html
├── #header-bar          — PRTS 标识、系统状态、数据统计
├── #main-content
│   ├── #chat-panel      — 对话流（flex: 1）
│   │   ├── .msg-user    — 用户消息气泡（右对齐，blue accent）
│   │   ├── .msg-route   — 路由信息条（amber 标签）
│   │   └── .msg-answer  — AI 回答卡片（四角 L 形装饰）
│   └── #search-panel    — 检索追踪（280px）
│       ├── .panel-header — "> 检索追踪_"
│       └── .step-card   — 步骤卡片（ROUTE/SEMANTIC/SOURCES）
├── #input-bar           — ">" prompt + input + 执行按钮
└── #status-bar          — READY | Latency | Tokens
```

## SSE 事件映射

| SSE Event | UI 行为 |
|-----------|---------|
| `route` | 渲染路由信息条 `.msg-route`；初始化检索面板 ROUTE 步骤卡片 |
| `step` | 新增/更新检索面板中的步骤卡片，slideInRight 动画 |
| `token` | 追加字符到当前 `.msg-answer` 的文本内容（逐字流式） |
| `sources` | 渲染检索面板 SOURCES 卡片；回答卡片中引用编号可 hover |
| `done` | 更新状态栏 Latency/Tokens；重置输入区状态 |

### 流式渲染策略

`token` 事件当前为每 50 字符分块。前端直接 `textContent += chunk`，由浏览器原生渲染，不额外做 CSS 逐字动画。分块策略在 Plan 阶段评估是否需要改为逐字 SSE 发送。

## 动效

| 时机 | 动效 | 实现 |
|------|------|------|
| 页面加载 | Header 滑入 + 面板淡入（staggered） | @keyframes + animation-delay |
| 步骤卡片新增 | 从右滑入 | @keyframes slideInRight 300ms |
| 按钮 hover | glow 增强 + 背景提亮 | transition |
| 输入区聚焦 | prompt `>` 脉冲 glow | @keyframes pulse :focus-within |
| 引用 hover | 编号高亮 | :hover color transition |

## 不实现

- 移动端响应式（桌面优先，后续迭代）
- 暗/亮主题切换（仅暗色 PRTS 主题）
- 对话历史持久化（后续迭代）
- Markdown 富文本渲染（当前回答为纯文本）
- React/Vue 框架迁移（保持原生 HTML/CSS/JS）

## 验证标准

1. 浏览器打开 `/` 页面，显示完整 PRTS 终端界面
2. 输入问题后：路由信息条出现 → token 逐字渲染 → 检索面板步骤卡片滑入 → 来源清单出现 → 状态栏更新
3. 引用编号 hover 显示 tooltip
4. 按钮 hover 有 glow 过渡
5. 输入区聚焦时 prompt `>` 脉冲
6. 现有 45 tests 仍然通过
