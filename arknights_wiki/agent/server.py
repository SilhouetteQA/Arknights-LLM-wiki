"""FastAPI Web 服务 -- SSE 流式对话 API"""
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
    """简单对话 UI"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>明日方舟剧情 Wiki</title>
<style>
body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
h1 { color: #e6b422; }
#chat { height: 60vh; overflow-y: auto; border: 1px solid #333; padding: 15px; margin-bottom: 15px; border-radius: 8px; background: #16213e; }
.msg { margin-bottom: 12px; }
.user { text-align: right; color: #4fc3f7; }
.assistant { color: #e0e0e0; line-height: 1.6; }
input { width: 75%; padding: 10px; border: 1px solid #333; border-radius: 4px; background: #16213e; color: #e0e0e0; }
button { padding: 10px 20px; background: #e6b422; border: none; border-radius: 4px; cursor: pointer; color: #1a1a2e; }
</style>
</head>
<body>
<h1>明日方舟 剧情 Wiki Agent</h1>
<div id="chat"></div>
<input type="text" id="question" placeholder="提问关于明日方舟剧情的问题..." onkeydown="if(event.key==='Enter')ask()">
<button onclick="ask()">提问</button>
<script>
const chat = document.getElementById("chat");
const input = document.getElementById("question");
async function ask() {
    const q = input.value.trim();
    if (!q) return;
    addMsg("user", q);
    input.value = "";
    const assistantDiv = document.createElement("div");
    assistantDiv.className = "msg assistant";
    assistantDiv.innerHTML = "<strong>Wiki:</strong> <span class='answer'></span><div class='sources'></div>";
    chat.appendChild(assistantDiv);
    const answerSpan = assistantDiv.querySelector(".answer");
    const response = await fetch("/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({question: q})});
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value).split("\\n")) {
            if (line.startsWith("data: ")) {
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) answerSpan.textContent += data.text;
                } catch(e) {}
            }
        }
    }
}
function addMsg(role, text) {
    const div = document.createElement("div");
    div.className = "msg " + role;
    div.innerHTML = "<strong>" + (role === "user" ? "你" : "Wiki") + ":</strong> " + text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}
</script>
</body>
</html>"""
