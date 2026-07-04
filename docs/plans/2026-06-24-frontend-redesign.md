# Agent 前端 UI 重设计 实施计划

> **状态**: 已完成
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 server.py 内嵌 60 行 HTML 替换为 PRTS 终端风格双栏 SSE 聊天界面（独立 HTML/CSS/JS）

**Architecture:** server.py 挂载 `StaticFiles`，`/` 路由读取 `static/index.html` 文件。前端纯原生 HTML/CSS/JS，fetch + ReadableStream 消费 SSE 事件驱动 UI。

**Tech Stack:** FastAPI StaticFiles, HTML5, CSS3 (variables/keyframes/grid/flexbox), vanilla JS (SSE parsing via ReadableStream)

> **状态**: 已完成

---

## File Structure

```
arknights_wiki/agent/
├── static/                   # 新建
│   ├── index.html            # 完整 HTML 结构
│   ├── style.css             # 变量/布局/组件/动画
│   └── app.js                # SSE 解析/DOM 更新/交互
├── server.py                 # 修改: 删除内嵌HTML, 添加StaticFiles mount
```

---

### Task 1: server.py — StaticFiles 挂载 + / 路由重构

**Files:**
- Modify: `arknights_wiki/agent/server.py`
- Create: `arknights_wiki/agent/static/index.html` (占位)
- Create: `arknights_wiki/agent/static/style.css` (空文件)
- Create: `arknights_wiki/agent/static/app.js` (空文件)
- Test: `tests/agent/test_server.py` (已有，需确认通过)

- [x] **Step 1: 修改 server.py — 添加 StaticFiles import 和 mount，替换 / 路由**

```python
"""FastAPI Web 服务 -- SSE 流式对话 API"""
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from arknights_wiki.config import DATA_DIR
from arknights_wiki.agent.router import route_query
from arknights_wiki.agent.simple_search import simple_search
from arknights_wiki.agent.state import AgentState


class ChatRequest(BaseModel):
    question: str
    history: list[dict] | None = None


app = FastAPI(title="明日方舟剧情 Wiki Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _simple_search_events(question: str, route: dict):
    """Simple search SSE 事件流"""
    yield {"event": "route", "data": json.dumps(route, ensure_ascii=False)}

    result = simple_search(question, route)
    answer = result.get("answer", "")

    for chunk in _split_text(answer):
        yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}

    yield {
        "event": "sources",
        "data": json.dumps(result.get("sources", []), ensure_ascii=False),
    }
    yield {"event": "done", "data": json.dumps({"total_steps": 1})}


async def _agent_search_events(question: str, route: dict):
    """Complex (LangGraph Agent) SSE 事件流"""
    from arknights_wiki.agent.graph import build_agent_graph

    yield {"event": "route", "data": json.dumps(route, ensure_ascii=False)}

    graph = build_agent_graph()
    initial_state: AgentState = {
        "messages": [],
        "question": question,
        "collected_docs": [],
        "iteration": 0,
        "route": route,
    }

    final_state = initial_state
    for event in graph.stream(initial_state):
        node_name = list(event.keys())[0]
        node_state = event[node_name]
        final_state = node_state

        if node_name == "tools":
            docs = node_state.get("collected_docs", [])
            if docs:
                last_doc = docs[-1]
                yield {
                    "event": "step",
                    "data": json.dumps({
                        "step": len(docs),
                        "tool": last_doc.get("tool", ""),
                        "summary": last_doc.get("result", "")[:200],
                    }, ensure_ascii=False),
                }
        elif node_name == "synthesize":
            messages = node_state.get("messages", [])
            if messages:
                final_message = messages[-1]
                answer = final_message.get("content", "")
                for chunk in _split_text(answer):
                    yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}

    sources = []
    for i, doc in enumerate(final_state.get("collected_docs", []), 1):
        sources.append({
            "ref": i,
            "tool": doc.get("tool", ""),
            "args": doc.get("args", {}),
            "summary": doc.get("result", "")[:200],
        })
    yield {
        "event": "sources",
        "data": json.dumps(sources, ensure_ascii=False),
    }
    yield {
        "event": "done",
        "data": json.dumps({"total_steps": len(final_state.get("collected_docs", []))}),
    }


def _split_text(text: str, chunk_size: int = 50) -> list[str]:
    """按句子分块模拟流式输出"""
    if not text:
        return [""]
    chunks = []
    current = ""
    for char in text:
        current += char
        if len(current) >= chunk_size or char in "。！？\n":
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


@app.post("/chat")
async def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    route = route_query(question)

    if route["complexity"] == "simple":
        event_generator = _simple_search_events(question, route)
    else:
        event_generator = _agent_search_events(question, route)

    return EventSourceResponse(event_generator)


@app.get("/", response_class=HTMLResponse)
async def index():
    """PRTS 终端对话 UI"""
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()
```

要点：原始 `server.py` 第 139-202 行的内嵌 HTML 已删除；新增 `StaticFiles` import/mount；`/` 路由改为从文件读取。

- [x] **Step 2: 创建占位文件**

`arknights_wiki/agent/static/index.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>明日方舟剧情 Wiki</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div id="app">PRTS 终端加载中...</div>
<script src="/static/app.js"></script>
</body>
</html>
```

创建空文件:

```bash
touch "D:/AI project/Arknights LLM Wiki/arknights_wiki/agent/static/style.css"
touch "D:/AI project/Arknights LLM Wiki/arknights_wiki/agent/static/app.js"
```

- [x] **Step 3: 运行现有测试，验证重构不破坏功能**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_server.py -v
```

Expected: 3 passed

- [x] **Step 4: Commit**

```bash
git add arknights_wiki/agent/server.py arknights_wiki/agent/static/
git commit -m "refactor(server): extract inline HTML to static/ files, mount StaticFiles"
```

---

### Task 2: HTML 结构 — 完整 PRTS 终端组件树

**Files:**
- Modify: `arknights_wiki/agent/static/index.html`

- [x] **Step 1: 重写 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRTS · 明日方舟剧情 Wiki</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>

<header id="header-bar">
  <div class="header-left">
    <span class="logo">PRTS</span>
    <span class="version">v3.7.1</span>
    <span class="separator">|</span>
    <span id="sys-status" class="status-ready">数据库就绪</span>
  </div>
  <div class="header-right" id="header-stats">
    <span class="stat"><span class="stat-value">6,666</span> 向量</span>
    <span class="stat"><span class="stat-value">1,251</span> 概念</span>
    <span class="stat"><span class="stat-value">642</span> 角色</span>
    <span class="stat">106 章</span>
  </div>
</header>

<main id="main-content">
  <section id="chat-panel">
    <div id="chat-messages">
      <div id="empty-state" class="empty-state">
        <div class="empty-prompt">&gt; 输入查询以检索泰拉数据库_</div>
        <div class="empty-hint">试试: "巨兽是什么" · "阿米娅的源石技艺" · "岁兽的碎片"</div>
      </div>
    </div>
    <div id="input-bar">
      <span class="prompt">&gt;</span>
      <input type="text" id="question-input" placeholder="输入查询..." autofocus>
      <button id="send-btn">执行</button>
    </div>
  </section>

  <aside id="search-panel">
    <div class="panel-header">&gt; 检索追踪_</div>
    <div id="search-steps">
      <div id="panel-empty" class="panel-empty">等待查询...</div>
    </div>
    <div id="panel-footer" class="panel-footer">就绪</div>
  </aside>
</main>

<footer id="status-bar">
  <span id="status-text">READY</span>
  <span id="status-latency"></span>
  <span id="status-tokens"></span>
</footer>

<script src="/static/app.js"></script>
</body>
</html>
```

- [x] **Step 2: 启动服务验证页面可访问**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m uvicorn arknights_wiki.agent.server:app --host 127.0.0.1 --port 8000 &
sleep 3
curl -s http://127.0.0.1:8000/ | head -3
# Expected: <!DOCTYPE html>...<title>PRTS · 明日方舟剧情 Wiki</title>
```

- [x] **Step 3: Commit**

```bash
git add arknights_wiki/agent/static/index.html
git commit -m "feat(ui): PRTS terminal HTML structure — dual panel layout"
```

---

### Task 3: CSS — 变量、布局、组件、动画

**Files:**
- Modify: `arknights_wiki/agent/static/style.css`

- [x] **Step 1: 写入 CSS 变量 + 基础重置**

```css
/* === CSS 变量 === */
:root {
  --bg-root: #080c14;
  --bg-panel: #0d1525;
  --bg-input: #060a12;
  --bg-hover: #152030;
  --accent-blue: #4fc3f7;
  --accent-amber: #ffb000;
  --accent-gold: #e6b422;
  --text-primary: #c8d6e5;
  --text-secondary: #5a6a80;
  --border-dim: #1a2740;
  --font-mono: 'Source Code Pro', 'Cascadia Code', 'Consolas', monospace;
  --font-display: 'Share Tech Mono', 'Courier New', monospace;
  --glow-blue: 0 0 6px rgba(79, 195, 247, 0.4);
  --glow-amber: 0 0 6px rgba(255, 176, 0, 0.4);
  --glow-gold: 0 0 6px rgba(230, 180, 34, 0.4);
}

/* === 基础重置 === */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--bg-root);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  overflow: hidden;
  cursor: crosshair;
}

body { display: flex; flex-direction: column; }
input, textarea { cursor: text; }
button { cursor: crosshair; font-family: var(--font-mono); }
```

- [x] **Step 2: 写入布局样式**

```css
/* === 布局 === */
#main-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

#chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-dim);
}

#search-panel {
  width: 280px;
  display: flex;
  flex-direction: column;
  background: #0a1020;
}
```

- [x] **Step 3: 写入 Header 组件样式**

```css
/* === Header === */
#header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #0a1020;
  border-bottom: 1px solid var(--border-dim);
  animation: slideDown 0.4s ease-out;
}

.header-left, .header-right { display: flex; align-items: center; gap: 10px; }

.logo {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 3px;
  color: var(--accent-gold);
  text-shadow: var(--glow-gold);
}

.version { color: var(--text-secondary); font-size: 11px; }
.separator { color: var(--border-dim); }

#sys-status {
  font-size: 11px;
  color: var(--accent-blue);
  text-shadow: var(--glow-blue);
}

.stat { color: var(--text-secondary); font-size: 11px; }
.stat-value { color: var(--accent-amber); }
```

- [x] **Step 4: 写入聊天区组件样式**

```css
/* === 空状态 === */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  animation: fadeIn 0.6s ease-out 0.2s both;
}

.empty-prompt {
  color: var(--accent-blue);
  font-size: 15px;
  text-shadow: var(--glow-blue);
}

.empty-hint { color: var(--text-secondary); font-size: 11px; }

/* === 聊天消息区 === */
#chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

#chat-messages::-webkit-scrollbar { width: 4px; }
#chat-messages::-webkit-scrollbar-track { background: transparent; }
#chat-messages::-webkit-scrollbar-thumb { background: var(--border-dim); }

/* 用户消息 */
.msg-user {
  align-self: flex-end;
  max-width: 75%;
  background: rgba(79, 195, 247, 0.08);
  border: 1px solid rgba(79, 195, 247, 0.2);
  border-radius: 3px;
  padding: 10px 14px;
  color: var(--accent-blue);
  text-shadow: 0 0 4px rgba(79, 195, 247, 0.2);
  animation: fadeIn 0.3s ease-out;
}

/* 路由信息条 */
.msg-route {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 10px;
  padding: 2px 0;
  animation: fadeIn 0.3s ease-out;
}

.msg-route .route-label {
  color: var(--accent-amber);
  text-shadow: var(--glow-amber);
}

/* AI 回答卡片 */
.msg-answer {
  background: var(--bg-panel);
  border: 1px solid var(--border-dim);
  border-radius: 3px;
  padding: 14px 16px;
  color: var(--text-primary);
  line-height: 1.7;
  position: relative;
  animation: fadeIn 0.4s ease-out;
}

.msg-answer::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 10px; height: 10px;
  border-top: 1px solid rgba(255, 176, 0, 0.25);
  border-left: 1px solid rgba(255, 176, 0, 0.25);
}

.msg-answer .corner-tr {
  position: absolute;
  top: -1px; right: -1px;
  width: 10px; height: 10px;
  border-top: 1px solid rgba(255, 176, 0, 0.25);
  border-right: 1px solid rgba(255, 176, 0, 0.25);
}

.msg-answer .ref-link {
  color: var(--accent-gold);
  cursor: crosshair;
  transition: color 0.2s;
}

.msg-answer .ref-link:hover {
  color: var(--accent-amber);
  text-shadow: var(--glow-amber);
}
```

- [x] **Step 5: 写入输入区样式**

```css
/* === 输入区 === */
#input-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg-input);
  border-top: 1px solid var(--border-dim);
  position: relative;
}

#input-bar::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 10px; height: 10px;
  border-top: 1px solid rgba(79, 195, 247, 0.25);
  border-left: 1px solid rgba(79, 195, 247, 0.25);
}

.prompt {
  color: var(--accent-blue);
  font-weight: 700;
  font-size: 15px;
  text-shadow: var(--glow-blue);
  transition: text-shadow 0.3s;
}

#input-bar:focus-within .prompt {
  animation: pulse 1.5s ease-in-out infinite;
}

#question-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  outline: none;
  caret-color: var(--accent-amber);
}

#question-input::placeholder { color: var(--text-secondary); }

#send-btn {
  background: rgba(255, 176, 0, 0.12);
  border: 1px solid rgba(255, 176, 0, 0.35);
  color: var(--accent-amber);
  padding: 6px 16px;
  border-radius: 2px;
  font-size: 11px;
  letter-spacing: 1px;
  text-shadow: var(--glow-amber);
  transition: background 0.2s, box-shadow 0.2s;
}

#send-btn:hover {
  background: rgba(255, 176, 0, 0.22);
  box-shadow: 0 0 12px rgba(255, 176, 0, 0.2);
}

#send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
```

- [x] **Step 6: 写入检索面板 + 状态栏样式**

```css
/* === 检索面板 === */
.panel-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-dim);
  color: var(--accent-amber);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-shadow: var(--glow-amber);
}

#search-steps {
  flex: 1;
  overflow-y: auto;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

#search-steps::-webkit-scrollbar { width: 4px; }
#search-steps::-webkit-scrollbar-track { background: transparent; }
#search-steps::-webkit-scrollbar-thumb { background: var(--border-dim); }

.panel-empty {
  color: var(--text-secondary);
  font-size: 11px;
  text-align: center;
  padding: 20px 0;
}

.step-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-dim);
  border-radius: 3px;
  padding: 8px 10px;
  position: relative;
  animation: slideInRight 0.3s ease-out;
}

.step-card::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 6px; height: 6px;
  border-top: 1px solid rgba(79, 195, 247, 0.3);
  border-left: 1px solid rgba(79, 195, 247, 0.3);
}

.step-card .step-label {
  font-size: 10px;
  margin-bottom: 4px;
  letter-spacing: 1px;
}

.step-card .step-label.route    { color: var(--accent-blue);  text-shadow: var(--glow-blue); }
.step-card .step-label.semantic { color: var(--accent-amber); text-shadow: var(--glow-amber); }
.step-card .step-label.sources  { color: var(--accent-blue);  text-shadow: var(--glow-blue); }

.step-card .step-detail { font-size: 11px; color: var(--text-primary); line-height: 1.5; }
.step-card .step-detail .dim { color: var(--text-secondary); }
.step-card .step-timing { font-size: 10px; color: var(--text-secondary); margin-top: 3px; }

.source-item { font-size: 10px; line-height: 1.6; }
.source-item .source-idx { color: var(--accent-gold); }
.source-item .source-type { color: var(--accent-blue); }

.panel-footer {
  padding: 6px 14px;
  border-top: 1px solid var(--border-dim);
  color: var(--text-secondary);
  font-size: 10px;
}

/* === 状态栏 === */
#status-bar {
  display: flex;
  justify-content: space-between;
  padding: 4px 16px;
  background: var(--bg-input);
  border-top: 1px solid var(--border-dim);
  color: var(--text-secondary);
  font-size: 10px;
}

#status-text { color: var(--accent-blue); }
```

- [x] **Step 7: 写入动画 keyframes**

```css
/* === 动画 === */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-16px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes slideInRight {
  from { opacity: 0; transform: translateX(20px); }
  to   { opacity: 1; transform: translateX(0); }
}

@keyframes pulse {
  0%, 100% { text-shadow: 0 0 6px rgba(79, 195, 247, 0.4); }
  50%      { text-shadow: 0 0 14px rgba(79, 195, 247, 0.7); }
}
```

- [x] **Step 8: Commit**

```bash
git add arknights_wiki/agent/static/style.css
git commit -m "feat(ui): PRTS terminal CSS — variables, layout, components, animations"
```

---

### Task 4: JavaScript — SSE 解析 + DOM 渲染 + 交互

**Files:**
- Modify: `arknights_wiki/agent/static/app.js`

- [x] **Step 1: 写入 DOM 引用和工具函数**

```js
/* PRTS 终端 -- SSE 流式对话客户端 */
const $ = (sel) => document.querySelector(sel);
const chatMessages = $('#chat-messages');
const emptyState = $('#empty-state');
const searchSteps = $('#search-steps');
const panelEmpty = $('#panel-empty');
const panelFooter = $('#panel-footer');
const questionInput = $('#question-input');
const sendBtn = $('#send-btn');
const statusText = $('#status-text');
const statusLatency = $('#status-latency');
const statusTokens = $('#status-tokens');

let currentAnswerSpan = null;
let stepCount = 0;
let isLoading = false;

function scrollChat() { chatMessages.scrollTop = chatMessages.scrollHeight; }
function scrollSteps() { searchSteps.scrollTop = searchSteps.scrollHeight; }

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
```

- [x] **Step 2: 写入消息渲染函数**

```js
function addUserMessage(text) {
  if (emptyState) emptyState.remove();
  var div = document.createElement('div');
  div.className = 'msg-user';
  div.textContent = text;
  chatMessages.appendChild(div);
  scrollChat();
}

function addRouteInfo(route) {
  var div = document.createElement('div');
  div.className = 'msg-route';
  div.innerHTML =
    '<span class="route-label">[路由]</span> ' + escapeHtml(route.complexity || '') +
    ' <span class="separator">|</span> ' +
    '<span class="route-label">[类别]</span> ' + escapeHtml(route.question_type || '') +
    ' <span class="separator">|</span> ' +
    '<span class="route-label">[实体]</span> ' + escapeHtml((route.entities || []).join(', '));
  chatMessages.appendChild(div);
  scrollChat();
}

function createAnswerCard() {
  var card = document.createElement('div');
  card.className = 'msg-answer';
  var corner = document.createElement('div');
  corner.className = 'corner-tr';
  card.appendChild(corner);
  var span = document.createElement('span');
  span.className = 'answer-text';
  card.appendChild(span);
  chatMessages.appendChild(card);
  return { card: card, span: span };
}

function appendToken(text) {
  if (!currentAnswerSpan) {
    var created = createAnswerCard();
    currentAnswerSpan = created.span;
  }
  currentAnswerSpan.textContent += text;
  scrollChat();
}
```

- [x] **Step 3: 写入检索面板函数**

```js
function clearSteps() {
  if (panelEmpty) panelEmpty.remove();
  var cards = searchSteps.querySelectorAll('.step-card');
  for (var i = 0; i < cards.length; i++) { cards[i].remove(); }
  stepCount = 0;
}

function addStepCard(label, labelClass, detailHtml, timing) {
  stepCount++;
  var card = document.createElement('div');
  card.className = 'step-card';
  card.innerHTML =
    '<div class="step-label ' + labelClass + '">[' + stepCount + '] ' + escapeHtml(label) + '</div>' +
    '<div class="step-detail">' + detailHtml + '</div>' +
    (timing ? '<div class="step-timing">' + escapeHtml(timing) + '</div>' : '');
  searchSteps.appendChild(card);
  scrollSteps();
}

function showSources(sources) {
  var detail = '';
  sources.forEach(function(s) {
    detail += '<div class="source-item">' +
      '[<span class="source-idx">' + s.ref + '</span>] ' +
      '<span class="source-type">' + escapeHtml(s.tool || s.entity_type || '') + ':</span> ' +
      escapeHtml(s.name || s.summary || '') +
      '</div>';
  });
  addStepCard('SOURCES', 'sources', detail, null);
  panelFooter.textContent = '总计 ' + sources.length + ' 来源';
}
```

- [x] **Step 4: 写入 SSE 流处理和主 ask 函数**

```js
function handleSSE(event, data) {
  switch (event) {
    case 'route':
      addRouteInfo(data);
      addStepCard('ROUTE', 'route',
        escapeHtml(data.complexity || '') + ' / ' + escapeHtml(data.question_type || '') +
        '<br><span class="dim">entities: ' + escapeHtml((data.entities || []).join(', ')) + '</span>',
        null);
      break;
    case 'token':
      appendToken(data.text || '');
      break;
    case 'step':
      addStepCard(data.tool || 'STEP', 'semantic',
        escapeHtml(data.summary || ''), null);
      break;
    case 'sources':
      if (Array.isArray(data)) showSources(data);
      break;
    case 'done':
      panelFooter.textContent = '总计 ' + (data.total_steps || 0) + ' 步骤';
      break;
  }
}

async function ask() {
  var question = questionInput.value.trim();
  if (!question || isLoading) return;

  addUserMessage(question);
  questionInput.value = '';
  isLoading = true;
  sendBtn.disabled = true;
  statusText.textContent = 'QUERYING...';
  statusText.style.color = '#ffb000';

  currentAnswerSpan = null;
  stepCount = 0;
  clearSteps();

  var startTime = performance.now();

  try {
    var response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question }),
    });

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    var currentEvent = '';

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;

      buffer += decoder.decode(chunk.value, { stream: true });
      var lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try {
            var data = JSON.parse(line.slice(6));
            handleSSE(currentEvent, data);
            currentEvent = '';
          } catch(e) {}
        } else if (line === '') {
          currentEvent = '';
        }
      }
    }

    var elapsed = Math.round(performance.now() - startTime);
    statusText.textContent = 'READY';
    statusText.style.color = '#4fc3f7';
    statusLatency.textContent = 'Latency: ' + elapsed + 'ms';
  } catch (err) {
    statusText.textContent = 'ERROR';
    statusText.style.color = '#ff4444';
    console.error('Fetch error:', err);
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

sendBtn.addEventListener('click', ask);
questionInput.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') ask();
});
```

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/agent/static/app.js
git commit -m "feat(ui): PRTS terminal JS — SSE parsing, DOM rendering, step/source visualization"
```

---

### Task 5: 端到端验证

- [x] **Step 1: 运行全部 agent 测试**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/ -v
```

Expected: 45 passed

- [x] **Step 2: 启动服务器，手动验证关键路径**

```bash
python -m uvicorn arknights_wiki.agent.server:app --host 127.0.0.1 --port 8000 &
```

浏览器访问 http://127.0.0.1:8000/ 验证:
- [x] 页面加载: Header 滑入动画、双栏布局可见、空状态提示显示
- [x] 输入 "巨兽是什么" 提交: 用户消息出现 → 路由信息条出现 → token 流式渲染 → 检索面板步骤卡片滑入 → 来源清单显示 → 状态栏更新
- [x] 输入区聚焦: prompt `>` 符号脉冲动画
- [x] 按钮 hover: 执行按钮 glow 增强
- [x] `/health` 端点正常: `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`

- [x] **Step 3: 停止服务器**

```bash
kill %1
```

- [x] **Step 4: Final commit (如有微调)**

```bash
git add -A
git commit -m "feat(ui): end-to-end verification — PRTS terminal frontend complete"
```

---

## 验证标准总结

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | 45 tests 仍然通过 | `pytest tests/agent/ -v` |
| 2 | `/` 返回完整 HTML（非内嵌字符串） | `curl -s localhost:8000/ | head -1` 含 `<!DOCTYPE html>` |
| 3 | `/static/style.css` 可访问 (200) | `curl -s -o /dev/null -w "%{http_code}" localhost:8000/static/style.css` |
| 4 | `/static/app.js` 可访问 (200) | `curl -s -o /dev/null -w "%{http_code}" localhost:8000/static/app.js` |
| 5 | SSE 5 种事件全部有 UI 响应 | 浏览器手动测试 |
| 6 | 动效: slideDown(slideDown), fadeIn(消息/卡片), slideInRight(步骤), pulse(prompt) | 浏览器手动测试 |
| 7 | 发光效果: 标题 gold glow, 状态 blue glow, 步骤 amber/blue glow | 浏览器手动测试 |
| 8 | 角标: 回答卡片四角 L 形, 步骤卡片角标, 输入区角标 | 浏览器手动测试 |
