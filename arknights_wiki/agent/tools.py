"""LangGraph Agent 工具函数 -- 8 个检索工具

使用 @tool 装饰器注册，TOOL_DEFINITIONS 和 TOOL_EXECUTORS 自动生成，
添加新工具只需定义函数 + 装饰器，无需手动同步三处。
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


# === 工具注册表 ===

_tool_registry: list[tuple] = []


def tool(description: str, param_descriptions: dict[str, str], required: list[str] | None = None, *, name: str | None = None, fallback: str | None = None):
    """装饰器：注册函数为 Agent 工具，同时记录 LLM function calling 所需的元数据。

    参数:
        description: 工具描述（供 LLM 阅读）
        param_descriptions: 参数名 → 参数描述
        required: 必填参数名列表
        name: LLM 可见的工具名（默认使用函数名）。用于函数名与 LLM 名不一致的情况。
        fallback: 恢复链降级工具名（W2，需为已注册工具名；失败重试耗尽后自动调用）

    使用方式:
        @tool("搜索 Wiki 页面", {"query": "搜索关键词"}, required=["query"])
        def search_wiki(query: str, category: str | None = None) -> str:
            ...
    """
    def decorator(func):
        _tool_registry.append((func, description, param_descriptions, required or [], name or func.__name__, fallback))
        return func
    return decorator


def _build_param_schema(func, param_descriptions: dict[str, str]) -> dict:
    """从函数类型注解和参数描述构建 JSON Schema properties"""
    import typing
    hints = typing.get_type_hints(func)
    properties = {}
    for name, desc in param_descriptions.items():
        hint = hints.get(name)
        if hint is int:
            properties[name] = {"type": "integer", "description": desc}
        else:
            properties[name] = {"type": "string", "description": desc}
    return properties


def _build_tool_definitions() -> list[dict]:
    """从注册表自动生成 LangGraph function calling 工具定义"""
    definitions = []
    for func, description, param_descriptions, required, tool_name, _fallback in _tool_registry:
        properties = _build_param_schema(func, param_descriptions)
        definitions.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return definitions


def _build_tool_executors() -> dict:
    """从注册表自动生成 tool name → executor 映射

    W3 MCP 双轨: ARKNIGHTS_USE_MCP=1 时切换到 MCP client 调用（工具名/签名不变，
    LLM 无感知）；MCP 调用失败自动回退内部函数（双保险）。
    """
    base = {tool_name: func for func, _, _, _, tool_name, _ in _tool_registry}
    if os.environ.get("ARKNIGHTS_USE_MCP") != "1":
        return base
    return {name: _make_mcp_executor(name, fn) for name, fn in base.items()}


# W3: Agent 工具 → (MCP 工具, 参数适配函数)
def _mcp_tool_map() -> dict[str, tuple[str, callable]]:
    def _identity(args):
        return args

    def _to_entities_from_page(args):
        return {"query": args.get("name", ""), "category": args.get("entity_type")}

    def _to_events_from_chapter(args):
        return {"chapter": args.get("chapter", ""), "limit": 15}

    def _to_entities_from_semantic(args):
        return {"query": args.get("query", "")}

    return {
        "search_wiki": ("search_entities", _identity),
        "get_entity_page": ("search_entities", _to_entities_from_page),
        "search_events": ("search_events", _identity),
        "search_dialogue": ("search_story", _identity),
        "search_timeline": ("query_timeline", _identity),
        "get_chapter_summary": ("search_events", _to_events_from_chapter),
        "semantic_search": ("search_entities", _to_entities_from_semantic),
        "lookup_entity_index": ("query_relationship", _identity),
    }


def _make_mcp_executor(tool_name: str, fallback_fn):
    """生成走 MCP 的 executor；MCP 未初始化/调用失败时回退内部函数"""
    mapping = _mcp_tool_map()
    mcp_tool, adapt = mapping[tool_name]

    def executor(**kwargs):
        from arknights_wiki.mcp_server.client import get_mcp_client

        client = get_mcp_client()
        if client is None:
            return fallback_fn(**kwargs)
        try:
            mcp_args = adapt(dict(kwargs))
            return client.call_tool_traced(mcp_tool, mcp_args)
        except Exception as e:  # noqa: BLE001 — MCP 路径失败回退内部函数
            return f"[MCP 调用失败，回退内部函数: {str(e)[:200]}]\n{fallback_fn(**kwargs)}"

    return executor


def _build_tool_fallbacks() -> dict[str, str]:
    """从注册表生成 tool name → fallback 工具名映射（W2 恢复链）"""
    return {tool_name: fb for _, _, _, _, tool_name, fb in _tool_registry if fb}


@tool("全文搜索 Wiki 页面。用于查找角色、概念、阵营、地点的名称或相关描述。",
      {"query": "搜索关键词（实体名或描述）", "category": "限定类别: concept/faction/location/character，不传则搜索全部"},
      required=["query"])
def search_wiki(query: str, category: str | None = None) -> str:
    """全文搜索 Wiki 页面（概念/阵营/地点/角色）。"""
    store = WikiStore(data_dir=_get_data_dir())
    results = store.search(query, category=category, limit=10)
    if not results:
        return f"未找到与 '{query}' 相关的 Wiki 页面。"
    lines = [f"搜索 '{query}' 找到 {len(results)} 个结果:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] [{r['entity_type']}] {r['name']} ({r['match_type']})")
        lines.append(r["text"][:2000])
    return "\n".join(lines)


@tool("获取实体完整 Wiki 页面。当发现关键实体需要深入了解时使用。",
      {"name": "实体名称", "entity_type": "实体类型: concept/faction/location/character"},
      required=["name", "entity_type"],
      fallback="search_wiki")
def get_entity_page(name: str, entity_type: str) -> str:
    """获取实体完整 Wiki 页面。"""
    store = WikiStore(data_dir=_get_data_dir())
    page = store.get_page(name, entity_type)
    if page is None:
        return f"未找到 {entity_type} 实体: {name}"
    return page["text"]


@tool("搜索剧情事件。按参与者、事件类型或章节筛选。",
      {"entity": "参与者名称（可选）", "event_type": "事件类型（可选）", "chapter": "章节名称（可选）"})
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
        lines.append(f"\n[{i}] {r['text'][:1000]}")
    return "\n".join(lines)


@tool("全文搜索原始剧情对话文本。适合查找 Wiki 和 Events 未覆盖的具体对话。",
      {"query": "搜索关键词", "chapter": "限定章节（可选）"},
      required=["query"])
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
        lines.append(r["text"][:1000])
    return "\n".join(lines)


@tool("搜索泰拉历史时间线。用于时间/因果关系问题。",
      {"query": "搜索关键词"},
      required=["query"])
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


@tool("获取指定章节的叙事摘要。",
      {"chapter": "章节名称"},
      required=["chapter"],
      fallback="search_events")
def get_chapter_summary(chapter: str) -> str:
    """获取指定章节的叙事摘要。"""
    store = EventStore(data_dir=_get_data_dir())
    result = store.get_chapter_summary(chapter)
    if result is None:
        return f"未找到章节 '{chapter}' 的摘要。"
    return f"[{chapter}] 章节摘要:\n{result['text']}"


@tool("FAISS 语义搜索。处理描述性/模糊查询，也能查到精确实体名匹配不到的相关内容。",
      {"query": "搜索查询", "top_k": "返回结果数，默认10"},
      required=["query"],
      name="semantic_search",
      fallback="search_wiki")
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
        lines.append(r["text"][:800])
    return "\n".join(lines)


@tool("查找实体在预构建索引中的关联实体、相关章节。用于确定检索方向和发现相关实体。",
      {"entity_name": "实体名称"},
      required=["entity_name"],
      fallback="search_wiki")
def lookup_entity_index(entity_name: str) -> str:
    """查找实体在预构建索引中的关联实体和相关章节。用于确定检索范围和发现相关实体。"""
    from arknights_wiki.agent.retrieval import EntityIndexStore
    store = EntityIndexStore(data_dir=_get_data_dir())
    entry = store.lookup(entity_name)
    if entry is None:
        return f"未在索引中找到实体: {entity_name}"

    lines = [f"实体 '{entity_name}' ({entry['type']}):"]

    for field, label in [
        ("related_entities", "关联概念"),
        ("related_factions", "关联阵营"),
        ("related_locations", "关联地点"),
        ("related_characters", "关联角色"),
    ]:
        items = entry.get(field, [])
        if items:
            lines.append(f"  {label}: {', '.join(items[:10])}")

    chapters = store.get_source_chapters(entity_name)
    if chapters:
        lines.append(f"  出现章节: {', '.join(chapters[:10])}")

    return "\n".join(lines)


# === 自动生成: 工具定义 + 执行器映射（来源: @tool 装饰器注册表） ===

TOOL_DEFINITIONS = _build_tool_definitions()
TOOL_EXECUTORS = _build_tool_executors()
TOOL_FALLBACKS = _build_tool_fallbacks()  # W2: 工具名 → fallback 工具名


def build_tool_listing() -> str:
    """从 @tool 注册表自动生成工具列表文本，供提示词使用。

    与 AGENT_SYSTEM_PROMPT 手工维护的工具列表不同，
    此函数直接读取 _tool_registry 元数据，确保与 TOOL_DEFINITIONS 保持同步。
    """
    lines = []
    for i, (func, description, param_descriptions, required, tool_name, _fallback) in enumerate(_tool_registry, 1):
        params = []
        for pname, pdesc in param_descriptions.items():
            marker = " (必填)" if pname in required else " (可选)"
            params.append(f"{pname}{marker}")
        param_str = ", ".join(params) if params else "无"
        lines.append(f"{i}. {tool_name}({param_str}) — {description}")
    return "\n".join(lines)
