"""Arknights 知识库 MCP Server（W3 MCP Server）

暴露 5 个只读工具（stdio transport）:
  search_entities / search_events / query_relationship / query_timeline / search_story

启动: python -m arknights_wiki.mcp_server.server
数据目录: ARKNIGHTS_DATA_DIR 覆盖（默认 config.DATA_DIR）
"""
from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from arknights_wiki.agent.retrieval import (
    DialogueStore,
    EntityIndexStore,
    EventStore,
    TimelineStore,
    WikiStore,
)
from arknights_wiki.config import DATA_DIR

server = MCPServer(
    "arknights-knowledge",
    title="明日方舟剧情知识库",
    description="基于大规模剧情知识图谱的只读检索服务（Wiki 实体 / 事件 / 关系 / 时间线 / 原始剧情）",
    version="0.1.0",
)


def _data_dir() -> str:
    return os.environ.get("ARKNIGHTS_DATA_DIR", DATA_DIR)


@server.tool(
    name="search_entities",
    description="搜索 Wiki 实体（角色/概念/阵营/地点）。精确实体名优先，支持类别过滤与内容子串匹配。",
)
async def search_entities(
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> str:
    """全文搜索 Wiki 实体页面；实体索引存在时补充关联信息。"""
    store = WikiStore(data_dir=_data_dir())
    results = store.search(query, category=category, limit=limit)
    if not results:
        return f"未找到与 '{query}' 相关的 Wiki 实体。"

    lines = [f"搜索 '{query}' 找到 {len(results)} 个实体:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] [{r['entity_type']}] {r['name']} ({r.get('match_type', '')})")
        lines.append(r["text"][:2000])

    # 实体索引补充关联信息（精确实体名时）
    idx = EntityIndexStore(data_dir=_data_dir())
    entry = idx.lookup(query)
    if entry:
        related = []
        for field in ("related_entities", "related_factions", "related_locations", "related_characters"):
            items = entry.get(field, [])
            if items:
                related.append(f"{field.replace('related_', '')}: {', '.join(items[:8])}")
        if related:
            lines.append("\n[关联] " + " | ".join(related))
    return "\n".join(lines)


@server.tool(
    name="search_events",
    description="按参与者/事件类型/章节搜索剧情事件（结构化）。适合查找谁参与了什么事件。",
)
async def search_events(
    entity: str | None = None,
    event_type: str | None = None,
    chapter: str | None = None,
    limit: int = 15,
) -> str:
    """搜索 Pass 1 结构化剧情事件。"""
    store = EventStore(data_dir=_data_dir())
    results = store.search(entity=entity, event_type=event_type, chapter=chapter, limit=limit)
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


@server.tool(
    name="query_relationship",
    description="查询实体在预构建索引中的关联实体、阵营、地点、角色与出现章节。用于关系网络与检索方向发现。",
)
async def query_relationship(entity_name: str) -> str:
    """实体关系查询（EntityIndexStore）。"""
    store = EntityIndexStore(data_dir=_data_dir())
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


@server.tool(
    name="query_timeline",
    description="搜索泰拉历史时间线（按年份记录的历史事件）。适合时间/因果关系问题。",
)
async def query_timeline(query: str | None = None, limit: int = 10) -> str:
    """泰拉历史时间线搜索。"""
    store = TimelineStore(data_dir=_data_dir())
    results = store.search(query or "", limit=limit)
    if not results:
        return f"未在时间线中找到 '{query or ''}'。"
    lines = [f"搜索时间线 '{query or ''}' 找到 {len(results)} 个事件:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] 年份 {r['year']}: {r['text']}")
    return "\n".join(lines)


@server.tool(
    name="search_story",
    description="全文搜索原始剧情对话文本（含台词）。适合 Wiki/事件未覆盖的具体对话细节。",
)
async def search_story(
    query: str,
    chapter: str | None = None,
    limit: int = 10,
) -> str:
    """原始剧情对话全文搜索。"""
    store = DialogueStore(data_dir=_data_dir())
    results = store.search(query, chapter=chapter, limit=limit)
    if not results:
        return f"未在剧情对话中找到 '{query}'。"
    lines = [f"搜索 '{query}' 找到 {len(results)} 段对话:"]
    for i, r in enumerate(results, 1):
        source = f"[{r.get('chapter', '')}/{r.get('node_id', '')}]"
        lines.append(f"\n[{i}] {source}")
        lines.append(r["text"][:1000])
    return "\n".join(lines)


if __name__ == "__main__":
    server.run(transport="stdio")
