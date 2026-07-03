"""FastAPI Web 服务 -- SSE 流式对话 API"""
import asyncio
import json
import os
import queue
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from arknights_wiki.config import DATA_DIR
from arknights_wiki.agent.router import route_query
from arknights_wiki.agent.simple_search import simple_search
from arknights_wiki.agent.state import AgentState


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] | None = None


# 简易内存速率限制器: 每个 IP 每分钟最多 30 次请求
_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 30
_RATE_LIMIT_WINDOW = 60.0


def _check_rate_limit(client_ip: str) -> bool:
    """检查 IP 是否超过速率限制，未超过返回 True"""
    now = time.time()
    timestamps = _rate_limit_store.get(client_ip, [])
    # 清理过期记录
    timestamps = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
    if len(timestamps) >= _RATE_LIMIT_MAX:
        _rate_limit_store[client_ip] = timestamps
        return False
    timestamps.append(now)
    _rate_limit_store[client_ip] = timestamps
    return True


app = FastAPI(title="明日方舟剧情 Wiki Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _simple_search_events(question: str, route: dict):
    """Simple search SSE 事件流

    通过 queue.Queue 让检索线程推送进度事件，主协程实时 yield 到前端。
    """
    yield {"event": "route", "data": json.dumps(route, ensure_ascii=False)}
    await asyncio.sleep(0)  # 强制刷新

    progress_queue = queue.Queue()

    def on_progress(tool: str, summary: str):
        progress_queue.put({"tool": tool, "summary": summary})

    # 在独立线程中执行同步阻塞的检索+LLM调用
    loop = asyncio.get_event_loop()
    search_future = loop.run_in_executor(
        None, simple_search, question, route, on_progress
    )

    # 检索进行中持续从队列取进度事件发送到前端
    while not search_future.done():
        try:
            evt = progress_queue.get_nowait()
            yield {"event": "step", "data": json.dumps(evt, ensure_ascii=False)}
            await asyncio.sleep(0)
        except queue.Empty:
            await asyncio.sleep(0.05)

    # 排空残留进度事件
    while not progress_queue.empty():
        evt = progress_queue.get_nowait()
        yield {"event": "step", "data": json.dumps(evt, ensure_ascii=False)}
        await asyncio.sleep(0)

    try:
        result = search_future.result()
    except Exception as e:
        yield {
            "event": "error",
            "data": json.dumps({"error": f"检索过程出错: {str(e)}"}, ensure_ascii=False),
        }
        return
    answer = result.get("answer", "")

    for chunk in _split_text(answer):
        yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}
        await asyncio.sleep(0.015)  # 逐字流式效果

    yield {
        "event": "sources",
        "data": json.dumps(result.get("sources", []), ensure_ascii=False),
    }
    yield {"event": "done", "data": json.dumps({"total_steps": 1})}


async def _agent_search_events(question: str, route: dict):
    """Complex (LangGraph Agent) SSE 事件流

    每个工具调用后立即 yield step 事件 + await asyncio.sleep(0) 刷新，
    确保前端检索追踪面板实时更新。
    """
    from arknights_wiki.agent.graph import build_agent_graph

    yield {"event": "route", "data": json.dumps(route, ensure_ascii=False)}
    await asyncio.sleep(0)  # 强制刷新

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
                tool_name = last_doc.get("tool", "")
                tool_args = last_doc.get("args", {})
                # 构造可读的工具调用描述
                query = tool_args.get("query", "") or tool_args.get("entity_name", "") or tool_args.get("chapter", "") or tool_args.get("name", "")
                label = f"{tool_name}({query})" if query else tool_name
                yield {
                    "event": "step",
                    "data": json.dumps({
                        "step": len(docs),
                        "tool": label,
                        "summary": last_doc.get("result", "")[:200],
                    }, ensure_ascii=False),
                }
                await asyncio.sleep(0)  # 每个工具调用后立即刷新到前端
        elif node_name == "synthesize":
            messages = node_state.get("messages", [])
            if messages:
                final_message = messages[-1]
                answer = final_message.get("content", "")
                for chunk in _split_text(answer):
                    yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}
                    await asyncio.sleep(0.015)  # 逐字流式效果

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
async def chat(req: ChatRequest, request: Request):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 速率限制检查
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

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
