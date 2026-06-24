"""LangGraph Agent 工具函数 -- 7 个检索工具

每个工具接收参数，返回字符串结果供 ToolMessage 使用。
包含 TOOL_DEFINITIONS (供 LLM function calling) 和 TOOL_EXECUTORS (供 graph 执行)。
"""
import json
import os

from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
)
from arknights_wiki.config import DATA_DIR


def _get_data_dir():
    return os.environ.get("ARKNIGHTS_DATA_DIR", DATA_DIR)


def search_wiki(query: str, category: str | None = None) -> str:
    """全文搜索 Wiki 页面（概念/阵营/地点/角色）。"""
    store = WikiStore(data_dir=_get_data_dir())
    results = store.search(query, category=category, limit=10)
    if not results:
        return f"未找到与 '{query}' 相关的 Wiki 页面。"
    lines = [f"搜索 '{query}' 找到 {len(results)} 个结果:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] [{r['entity_type']}] {r['name']} ({r['match_type']})")
        lines.append(r["text"][:800])
    return "\n".join(lines)


def get_entity_page(name: str, entity_type: str) -> str:
    """获取实体完整 Wiki 页面。"""
    store = WikiStore(data_dir=_get_data_dir())
    page = store.get_page(name, entity_type)
    if page is None:
        return f"未找到 {entity_type} 实体: {name}"
    return page["text"]


def search_events(
    entity: str | None = None,
    event_type: str | None = None,
    chapter: str | None = None,
) -> str:
    """搜索 Pass 1 剧情事件。"""
    store = EventStore(data_dir=_get_data_dir())
    results = store.search(entity=entity, event_type=event_type, chapter=chapter, limit=15)
    if not results:
        parts = []
        if entity:
            parts.append(f"entity={entity}")
        if event_type:
            parts.append(f"type={event_type}")
        if chapter:
            parts.append(f"chapter={chapter}")
        return f"未找到匹配的事件 ({', '.join(parts)})。"
    lines = [f"找到 {len(results)} 个事件:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] {r['text'][:500]}")
    return "\n".join(lines)


def search_dialogue(query: str, chapter: str | None = None) -> str:
    """全文搜索原始剧情对话。"""
    store = DialogueStore(data_dir=_get_data_dir())
    results = store.search(query, chapter=chapter, limit=15)
    if not results:
        return f"未在对话中找到 '{query}'。"
    lines = [f"搜索 '{query}' 找到 {len(results)} 段对话:"]
    for i, r in enumerate(results, 1):
        source = f"[{r.get('chapter', '')}/{r.get('node_id', '')}]"
        lines.append(f"\n[{i}] {source}")
        lines.append(r["text"][:500])
    return "\n".join(lines)


def search_timeline(query: str) -> str:
    """搜索泰拉历史时间线。"""
    store = TimelineStore(data_dir=_get_data_dir())
    results = store.search(query, limit=10)
    if not results:
        return f"未在时间线中找到 '{query}'。"
    lines = [f"搜索时间线 '{query}' 找到 {len(results)} 个事件:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] 年份 {r['year']}: {r['text']}")
    return "\n".join(lines)


def get_chapter_summary(chapter: str) -> str:
    """获取指定章节的叙事摘要。"""
    store = EventStore(data_dir=_get_data_dir())
    result = store.get_chapter_summary(chapter)
    if result is None:
        return f"未找到章节 '{chapter}' 的摘要。"
    return f"[{chapter}] 章节摘要:\n{result['text']}"


def semantic_search_tool(query: str, top_k: int = 10) -> str:
    """FAISS 语义搜索 -- 处理描述性/模糊查询。"""
    index_dir = os.path.join(_get_data_dir(), "index")
    index_path = os.path.join(index_dir, "faiss.index")
    map_path = os.path.join(index_dir, "chunk_map.json")

    if not os.path.exists(index_path) or not os.path.exists(map_path):
        return "FAISS 索引未就绪。请先运行 build_agent_index.py。可尝试其他检索工具。"

    from arknights_wiki.agent.vector_index import load_index, semantic_search as faiss_search
    index, chunk_map = load_index(index_path, map_path)
    results = faiss_search(query, index, chunk_map, top_k=top_k)

    if not results:
        return f"语义搜索 '{query}' 未找到相关结果。"
    lines = [f"语义搜索 '{query}' 找到 {len(results)} 个结果:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] [{r['entity_type']}] {r['name']} (score: {r['score']:.3f})")
        lines.append(r["text"][:400])
    return "\n".join(lines)


# LangGraph function calling 工具定义
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "全文搜索 Wiki 页面。用于查找角色、概念、阵营、地点的名称或相关描述。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（实体名或描述）"},
                    "category": {
                        "type": "string",
                        "enum": ["concept", "faction", "location", "character"],
                        "description": "限定类别，不传则搜索全部",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_page",
            "description": "获取实体完整 Wiki 页面。当发现关键实体需要深入了解时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "实体名称"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["concept", "faction", "location", "character"],
                        "description": "实体类型",
                    },
                },
                "required": ["name", "entity_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "搜索剧情事件。按参与者、事件类型或章节筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "参与者名称（可选）"},
                    "event_type": {"type": "string", "description": "事件类型（可选）"},
                    "chapter": {"type": "string", "description": "章节名称（可选）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_dialogue",
            "description": "全文搜索原始剧情对话文本。适合查找 Wiki 和 Events 未覆盖的具体对话。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "chapter": {"type": "string", "description": "限定章节（可选）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_timeline",
            "description": "搜索泰拉历史时间线。用于时间/因果关系问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chapter_summary",
            "description": "获取指定章节的叙事摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {"type": "string", "description": "章节名称"},
                },
                "required": ["chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "FAISS 语义搜索。处理描述性/模糊查询（如'那个整合运动的女领袖'），也能查到精确实体名匹配不到的相关内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "top_k": {"type": "integer", "description": "返回结果数，默认10"},
                },
                "required": ["query"],
            },
        },
    },
]

# tool name -> executor mapping
TOOL_EXECUTORS = {
    "search_wiki": search_wiki,
    "get_entity_page": get_entity_page,
    "search_events": search_events,
    "search_dialogue": search_dialogue,
    "search_timeline": search_timeline,
    "get_chapter_summary": get_chapter_summary,
    "semantic_search": semantic_search_tool,
}
