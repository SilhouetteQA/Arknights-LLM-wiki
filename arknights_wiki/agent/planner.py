"""W4 Planner：显式任务规划（LLM 规划 + 规则模板兜底）

任务图模型 TaskNode + 规则模板 + 校验。
LLM 规划在 plan_tasks（见下）；执行器在 graph.py（复用工具执行）。
"""
from __future__ import annotations

import json
import os
from typing import TypedDict

from arknights_wiki.agent.tools import TOOL_EXECUTORS

MAX_TASKS = 6

_ENTITY_TYPES = {"concept", "faction", "location", "character"}

# 规则模板允许的工具（LLM 白名单用全部 TOOL_EXECUTORS）
RULE_TOOLS = {"get_entity_page", "search_events", "search_wiki",
              "search_timeline", "search_dialogue", "get_chapter_summary",
              "semantic_search", "lookup_entity_index"}


class TaskNode(TypedDict, total=False):
    id: str
    description: str
    tool: str
    args: dict
    depends_on: list[str]
    status: str
    result: str


# ---- 工具白名单（LLM 规划校验）----

def _tool_whitelist() -> set[str]:
    """合法工具名集合（受 MCP 双轨影响的 TOOL_EXECUTORS 键名一致）"""
    return set(TOOL_EXECUTORS.keys())


# ---- 规则模板 ----

def _task(tid: str, description: str, tool: str, args: dict,
          depends_on: list[str] | None = None) -> TaskNode:
    return {
        "id": tid, "description": description, "tool": tool,
        "args": args, "depends_on": depends_on or [],
        "status": "pending",
    }


def _probe_entity_type(name: str, data_dir: str | None = None) -> str | None:
    """探测实体类型（get_entity_page 需要 entity_type）；找不到返回 None"""
    from arknights_wiki.agent.retrieval import WikiStore

    store = WikiStore(data_dir=data_dir)
    for etype in ("character", "concept", "faction", "location"):
        if store.get_page(name, etype) is not None:
            return etype
    return None


def _entity_page_task(tid: str, entity: str, data_dir: str | None = None) -> TaskNode | None:
    """构造 get_entity_page 任务；类型探测失败则降级 search_wiki"""
    etype = _probe_entity_type(entity, data_dir)
    if etype is not None:
        return _task(tid, f"获取实体「{entity}」的完整页面", "get_entity_page",
                     {"name": entity, "entity_type": etype})
    return _task(tid, f"搜索实体「{entity}」相关信息", "search_wiki", {"query": entity})


def build_rule_plan(route: dict, data_dir: str | None = None) -> list[TaskNode]:
    """按 question_type 生成规则任务图（LLM 失败时的兜底）

    任务只含检索步骤；最终综合由 synthesize 节点统一完成。
    """
    entities = [e for e in route.get("entities", []) if not e.startswith("__")]
    qt = route.get("question_type", "")
    plan: list[TaskNode] = []
    tid = 0

    def next_id() -> str:
        nonlocal tid
        tid += 1
        return f"t{tid}"

    def add_entity_tasks(entity: str, with_timeline: bool = False):
        page = _entity_page_task(next_id(), entity, data_dir)
        plan.append(page)
        plan.append(_task(
            next_id(), f"搜索与「{entity}」相关的事件", "search_events",
            {"entity": entity, "limit": 15}, [page["id"]],
        ))
        if with_timeline:
            plan.append(_task(
                next_id(), f"搜索「{entity}」相关时间线", "search_timeline",
                {"query": entity, "limit": 5},
            ))

    if qt == "comparison":
        for ent in entities[:2]:
            add_entity_tasks(ent)
    elif qt == "list_enumeration":
        for ent in entities[:3]:
            add_entity_tasks(ent)
    elif qt == "causal_reasoning":
        for ent in entities[:2]:
            add_entity_tasks(ent, with_timeline=True)
    elif qt == "chapter_summary":
        chapter = entities[0] if entities else route.get("chapter", "")
        if chapter:
            plan.append(_task(next_id(), f"获取章节「{chapter}」摘要", "get_chapter_summary",
                              {"chapter": chapter}))
            plan.append(_task(next_id(), f"搜索章节「{chapter}」事件", "search_events",
                              {"chapter": chapter, "limit": 15}))
        else:
            plan.append(_task(next_id(), "搜索剧情梗概", "search_wiki", {"query": "剧情"}))
    else:
        for ent in entities[:3]:
            add_entity_tasks(ent)
        if not entities:
            plan.append(_task(next_id(), "关键词搜索补充", "search_wiki",
                              {"query": route.get("rewritten_question", "")[:50]}))

    return plan[:MAX_TASKS]


# ---- 校验 ----

def _has_cycle(tasks: list[TaskNode]) -> bool:
    ids = {t["id"] for t in tasks}
    visiting: set[str] = set()
    done: set[str] = set()

    def dfs(node_id: str) -> bool:
        if node_id in done:
            return False
        if node_id in visiting:
            return True
        visiting.add(node_id)
        node = next((t for t in tasks if t["id"] == node_id), None)
        if node:
            for dep in node.get("depends_on", []):
                if dep in ids and dfs(dep):
                    return True
        visiting.discard(node_id)
        done.add(node_id)
        return False

    return any(dfs(t["id"]) for t in tasks)


def validate_tasks(tasks: list[TaskNode]) -> tuple[bool, list[str]]:
    """校验任务图：工具白名单 / 依赖存在 / 无环 / 任务数上限"""
    errors: list[str] = []
    whitelist = _tool_whitelist()
    ids = {t["id"] for t in tasks}

    if len(tasks) > MAX_TASKS:
        errors.append(f"任务数 {len(tasks)} 超过上限 {MAX_TASKS}")
    for t in tasks:
        if t.get("tool") not in whitelist:
            errors.append(f"任务 {t['id']} 工具名非法: {t.get('tool')}")
        for dep in t.get("depends_on", []):
            if dep not in ids:
                errors.append(f"任务 {t['id']} 依赖不存在: {dep}")
    if not errors and _has_cycle(tasks):
        errors.append("任务依赖存在循环")
    return (len(errors) == 0, errors)


def check_plan(plan: list[TaskNode]) -> bool:
    """便捷校验入口"""
    ok, _ = validate_tasks(plan)
    return ok


# ---- LLM 规划 ----

PLANNER_PROMPT = """你是《明日方舟》剧情检索规划器。把用户问题拆解为**检索任务图**。

规则：
1. 只输出 JSON 数组（不要 markdown），每个元素:
   {{"id": "t1", "description": "任务描述", "tool": "工具名", "args": {{参数}}, "depends_on": ["依赖任务id"]}}
2. 工具名必须来自下方工具列表；args 键名必须与工具参数一致
3. 任务 ≤ {max_tasks} 个；无依赖任务 depends_on 为空数组
4. 不要包含"综合/总结"类任务（回答合成由系统统一完成）
5. 任务间依赖（depends_on）必须引用已定义的任务 id

可用工具：
{tools}

示例输出：
[{{"id": "t1", "description": "获取凯尔希实体页面", "tool": "get_entity_page", "args": {{"name": "凯尔希", "entity_type": "character"}}, "depends_on": []}},
 {{"id": "t2", "description": "搜索凯尔希相关事件", "tool": "search_events", "args": {{"entity": "凯尔希", "limit": 15}}, "depends_on": ["t1"]}}]"""


def _normalize_plan(tasks: list[TaskNode]) -> list[TaskNode]:
    """归一化 LLM 规划：get_entity_page 的 entity_type 必须在合法集内。

    LLM 可能幻觉非法类型（如 "organization" → 应为 "faction"）：
    非法时尝试探测，仍失败则降级为 search_wiki。
    """
    for t in tasks:
        if t.get("tool") == "get_entity_page":
            et = t["args"].get("entity_type")
            name = t["args"].get("name", "")
            if et not in _ENTITY_TYPES:
                probed = _probe_entity_type(name)
                if probed:
                    t["args"]["entity_type"] = probed
                else:
                    t["tool"] = "search_wiki"
                    t["args"] = {"query": name}
                    t["description"] = f"搜索实体「{name}」相关信息"
    return tasks


def _llm_plan(question: str, route: dict) -> list[TaskNode] | None:
    """LLM 生成任务图；任何失败/校验不过返回 None（由调用方走规则兜底）"""
    try:
        from arknights_wiki.agent import wrap_user_input
        from arknights_wiki.agent.tools import build_tool_listing
        from arknights_wiki.extraction.llm_client import chat_completion

        tools_text = build_tool_listing()
        prompt = PLANNER_PROMPT.format(max_tasks=MAX_TASKS, tools=tools_text)
        content, _ = chat_completion(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": wrap_user_input(question)},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        text = content.strip().strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
        data = json.loads(text)
        if not isinstance(data, list):
            return None
        tasks: list[TaskNode] = []
        for i, item in enumerate(data, 1):
            if not isinstance(item, dict):
                return None
            tasks.append({
                "id": str(item.get("id") or f"t{i}"),
                "description": str(item.get("description", "")),
                "tool": str(item.get("tool", "")),
                "args": item.get("args") or {},
                "depends_on": [str(d) for d in (item.get("depends_on") or [])],
                "status": "pending",
            })
        ok, _ = validate_tasks(tasks)
        return _normalize_plan(tasks) if ok else None
    except Exception:  # noqa: BLE001 — 规划失败走规则兜底
        return None


def plan_tasks(question: str, route: dict, use_llm: bool = True) -> tuple[list[TaskNode], str]:
    """生成检索任务图。

    Returns:
        (tasks, source) — source: "llm" | "rule"
    """
    if use_llm:
        llm_plan = _llm_plan(question, route)
        if llm_plan is not None:
            return llm_plan, "llm"
    return build_rule_plan(route), "rule"
