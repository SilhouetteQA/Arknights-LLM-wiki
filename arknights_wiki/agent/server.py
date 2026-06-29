"""FastAPI Web 服务 -- SSE 流式对话 API"""
import json
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from arknights_wiki.config import DATA_DIR
from arknights_wiki.agent.router import route_query
from arknights_wiki.agent.simple_search import simple_search
from arknights_wiki.agent.state import AgentState


QA_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output")


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

    return EventSourceResponse(_log_and_stream(question, route, event_generator))


async def _log_and_stream(question: str, route: dict, event_generator):
    """包装 SSE 流，捕获完整回答后写入 JSONL 日志"""
    answer_chunks = []
    sources = []
    yield_msg = None
    try:
        async for msg in event_generator:
            yield msg
            event = msg.get("event", "")
            if event == "token":
                data = json.loads(msg["data"])
                answer_chunks.append(data.get("text", ""))
            elif event == "sources":
                sources = json.loads(msg["data"])
            elif event == "done":
                yield_msg = msg
    except Exception:
        pass

    # 写入日志
    full_answer = "".join(answer_chunks)
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "route_complexity": route.get("complexity", ""),
        "route_intent": route.get("question_type", ""),
        "route_entities": route.get("entities", []),
        "route_reason": route.get("reason", ""),
        "answer": full_answer,
        "sources": sources,
    }
    os.makedirs(QA_LOG_DIR, exist_ok=True)
    log_path = os.path.join(QA_LOG_DIR, "qa_log.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


@app.get("/", response_class=HTMLResponse)
async def index():
    """PRTS 终端对话 UI"""
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()
