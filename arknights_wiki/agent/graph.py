"""LangGraph ReAct Agent 图定义

Graph 结构:
  START -> call_model (agent_node)
             |- tool_calls -> tool_node -> call_model
             |- no_tool_calls -> synthesize_node -> END

W1 Observability: call_model/synthesize 用 traced 装饰（span + 内部 LLM generation 自动嵌套），
tool_node 内每个工具执行包一个 tool span（tool_call）。
W2 Failure Recovery: 工具执行经 execute_with_resilience（timeout→retry→breaker→fallback），
恢复链统计写入 tool_call span metadata（retries/breaker_state/fallback_used/error）。
"""
import concurrent.futures
import contextvars
import json
import os

from langgraph.graph import StateGraph, END

from arknights_wiki.agent.state import AgentState
from arknights_wiki.agent.prompts import AGENT_SYSTEM_PROMPT, SYNTHESIS_PROMPT
from arknights_wiki.agent.resilience import (
    BreakerOpenError,
    CircuitBreaker,
    ResilienceConfig,
    execute_with_resilience,
)
from arknights_wiki.agent.tools import TOOL_DEFINITIONS, TOOL_EXECUTORS, TOOL_FALLBACKS
from arknights_wiki.observability import (
    SPAN_AGENT_CALL,
    SPAN_SYNTHESIZE,
    SPAN_TOOL,
    get_client,
    traced,
)

MAX_ITERATIONS = 8

# W2: 工具执行恢复链配置（环境变量可覆盖；breaker_threshold=0 关闭熔断）
_TOOL_RESILIENCE_CONFIG = ResilienceConfig(
    timeout_seconds=float(os.environ.get("ARKNIGHTS_TOOL_TIMEOUT", "30")),
    max_retries=int(os.environ.get("ARKNIGHTS_TOOL_MAX_RETRIES", "2")),
    backoff_base=1.0,
    backoff_max=8.0,
    breaker_threshold=int(os.environ.get("ARKNIGHTS_TOOL_BREAKER_THRESHOLD", "5")),
    breaker_reset_seconds=60.0,
)

# 同名工具共享熔断器（跨请求连续失败触发熔断）
_tool_breakers: dict[str, CircuitBreaker] = {}


def _get_tool_breaker(tool_name: str) -> CircuitBreaker | None:
    if _TOOL_RESILIENCE_CONFIG.breaker_threshold <= 0:
        return None
    breaker = _tool_breakers.get(tool_name)
    if breaker is None:
        breaker = CircuitBreaker(
            threshold=_TOOL_RESILIENCE_CONFIG.breaker_threshold,
            reset_seconds=_TOOL_RESILIENCE_CONFIG.breaker_reset_seconds,
        )
        _tool_breakers[tool_name] = breaker
    return breaker


def _agent_metadata(args, kwargs, state: AgentState) -> dict:
    """call_model 结果的 trace metadata（迭代数/工具调用数）"""
    if not isinstance(state, dict):
        return {}
    last = state.get("messages", [])[-1] if state.get("messages") else {}
    return {
        "iteration": state.get("iteration", 0),
        "n_tool_calls": len(last.get("tool_calls", [])) if isinstance(last, dict) else 0,
    }


@traced(name=SPAN_AGENT_CALL, metadata_fn=_agent_metadata)
def call_model(state: AgentState) -> AgentState:
    """调用 LLM（带 tool 定义），决定下一步: tool_call 或 final answer"""
    from arknights_wiki.extraction.llm_client import chat_completion
    from arknights_wiki.agent import wrap_user_input

    question = state["question"]
    iteration = state.get("iteration", 0)

    if not state.get("messages"):
        state["messages"] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": wrap_user_input(question)},
        ]
    else:
        if state["messages"][0].get("role") != "system":
            state["messages"].insert(0, {"role": "system", "content": AGENT_SYSTEM_PROMPT})

    content, assistant_message = chat_completion(
        messages=state["messages"],
        temperature=0.1,
        tools=TOOL_DEFINITIONS,
    )

    new_message = {"role": "assistant"}
    if content:
        new_message["content"] = content
    if assistant_message.tool_calls:
        new_message["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in assistant_message.tool_calls
        ]
        new_message["content"] = assistant_message.content

    state["messages"] = state["messages"] + [new_message]
    state["iteration"] = iteration + 1
    return state


def _adapt_fallback_args(fb_name: str, func_args: dict) -> dict:
    """fallback 工具参数适配（W2）: 不同签名工具间映射常用参数。

    当前注册的 fallback 关系:
      get_entity_page(name, entity_type) / lookup_entity_index(entity_name)
        → search_wiki(query, category)
      get_chapter_summary(chapter) → search_events(chapter)
      semantic_search(query, top_k) → search_wiki(query)
    """
    if fb_name == "search_wiki" and "query" not in func_args:
        key = next((k for k in ("name", "entity_name") if k in func_args), None)
        if key is not None:
            adapted = {"query": func_args[key]}
            if "entity_type" in func_args:
                adapted["category"] = func_args["entity_type"]
            return adapted
    if fb_name == "search_events" and "chapter" in func_args:
        return {"chapter": func_args["chapter"]}
    return func_args


def _run_tool_with_resilience(func_name: str, func_args: dict, executor) -> tuple[str, dict]:
    """恢复链执行单个工具（W2）: timeout → retry → breaker → fallback。

    Returns:
        (result_text, stats) — stats 供 trace 埋点
    """
    fallbacks = []
    fb_name = TOOL_FALLBACKS.get(func_name)
    if fb_name:
        fb_executor = TOOL_EXECUTORS.get(fb_name)
        if fb_executor:
            fb_args = _adapt_fallback_args(fb_name, func_args)
            fallbacks.append((lambda: fb_executor(**fb_args), fb_name))

    try:
        result_text, stats = execute_with_resilience(
            executor, (), func_args, _TOOL_RESILIENCE_CONFIG,
            fallbacks=fallbacks, breaker=_get_tool_breaker(func_name),
        )
        if stats.get("fallback_used"):
            result_text = f"[已降级: {stats['fallback_used']}] {result_text}"
        return result_text, stats
    except BreakerOpenError:
        return (
            f"工具 {func_name} 暂时不可用（熔断保护中），请稍后再试。",
            {"breaker_state": "open", "error": "breaker open", "retries": 0,
             "fallback_used": None},
        )
    except Exception as e:  # noqa: BLE001 — 恢复链耗尽，返回友好文本
        return (
            f"工具执行失败（重试后仍失败）: {str(e)[:300]}",
            {"error": str(e)[:300], "retries": 0, "fallback_used": None,
             "breaker_state": "closed"},
        )


def _execute_tool_traced(func_name: str, func_args: dict, executor) -> str:
    """执行单个工具；启用 trace 时包一个 tool_call span（记录 tool/args/error/恢复链统计）"""
    c = get_client()

    def _exec():
        return _run_tool_with_resilience(func_name, func_args, executor)

    if c is None:
        result_text, _ = _exec()
        return result_text

    import time as time_mod

    with c.start_as_current_observation(
        name=SPAN_TOOL,
        as_type="tool",
        metadata={"tool": func_name, "args": func_args},
    ) as _obs:
        _t0 = time_mod.time()
        try:
            result_text, stats = _exec()
        except Exception as e:  # noqa: BLE001
            result_text = f"工具执行失败: {str(e)}"
            stats = {"error": str(e)[:500]}
            try:
                c.update_current_span(level="ERROR", status_message=str(e)[:500])
            except Exception:  # noqa: BLE001
                pass
        try:
            meta = {
                "tool": func_name,
                "latency_ms": round((time_mod.time() - _t0) * 1000, 1),
                "result_len": len(result_text),
            }
            # W2: 恢复链统计（retries/breaker/fallback/error）
            for key in ("retries", "breaker_state", "fallback_used", "error"):
                if stats.get(key) not in (None, "", 0):
                    meta[key] = stats[key]
            c.update_current_span(metadata=meta)
            # 重试/降级发生时附加 retry 子 span（schema 预留 NODE_TYPE_RETRY）
            if stats.get("retries", 0) > 0 or stats.get("fallback_used"):
                from arknights_wiki.observability import NODE_TYPE_RETRY

                with c.start_as_current_observation(
                    name="retry",
                    as_type="span",
                    metadata={
                        "node_type": NODE_TYPE_RETRY,
                        "retries": stats.get("retries", 0),
                        "fallback_used": stats.get("fallback_used"),
                        "breaker_state": stats.get("breaker_state", ""),
                    },
                ):
                    pass
        except Exception:  # noqa: BLE001
            pass
        return result_text


def tool_node(state: AgentState) -> AgentState:
    """执行 tool_calls，将结果追加到 messages 和 collected_docs"""
    last_message = state["messages"][-1]
    tool_calls = last_message.get("tool_calls", [])
    collected_docs = state.get("collected_docs", [])

    for tc in tool_calls:
        func_name = tc["function"]["name"]
        func_args = json.loads(tc["function"]["arguments"])

        executor = TOOL_EXECUTORS.get(func_name)
        if executor:
            result_text = _execute_tool_traced(func_name, func_args, executor)
        else:
            result_text = f"未知工具: {func_name}"

        collected_docs.append({
            "tool": func_name,
            "args": func_args,
            "result": result_text[:1000],
        })

        state["messages"] = state["messages"] + [
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": func_name,
                "content": result_text,
            }
        ]

    state["collected_docs"] = collected_docs
    return state


@traced(name=SPAN_SYNTHESIZE)
def synthesize_node(state: AgentState) -> AgentState:
    """综合所有证据，生成最终回答"""
    from arknights_wiki.extraction.llm_client import chat_completion
    from arknights_wiki.agent import wrap_user_input

    question = state["question"]
    collected_docs = state.get("collected_docs", [])

    evidence_parts = []
    for i, doc in enumerate(collected_docs, 1):
        evidence_parts.append(f"--- 资料 {i}: {doc['tool']} ---")
        evidence_parts.append(f"查询参数: {doc['args']}")
        evidence_parts.append(doc["result"])
        evidence_parts.append("")

    evidence_text = "\n".join(evidence_parts) if evidence_parts else "无证据收集到。"

    if not collected_docs:
        answer = "当前检索到的剧情资料中未找到相关内容，无法给出可靠回答。"
    else:
        prompt = SYNTHESIS_PROMPT.format(evidence=evidence_text, question=wrap_user_input(question))
        try:
            answer, _ = chat_completion(
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
        except Exception as e:
            answer = "抱歉，回答生成出了点问题。请稍后再试。"

    state["messages"] = state["messages"] + [
        {"role": "assistant", "content": answer}
    ]
    return state


def should_continue(state: AgentState) -> str:
    """路由决策: 继续 tool calling 还是结束"""
    last_message = state["messages"][-1]
    iteration = state.get("iteration", 0)

    if iteration >= MAX_ITERATIONS:
        return "synthesize"
    if last_message.get("tool_calls"):
        return "tools"
    return "synthesize"


def build_agent_graph(checkpointer=None):
    """构建并编译 LangGraph agent 图

    W2: checkpointer 传入时启用 checkpoint（断点续跑）。server 传 SqliteSaver
    持久化到 output/checkpoints/agent.sqlite；测试可传 MemorySaver。
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_node("synthesize", synthesize_node)

    workflow.set_entry_point("agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "synthesize": "synthesize"},
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("synthesize", END)

    return workflow.compile(checkpointer=checkpointer)


# ---- W4 Planner: 任务执行器 + 规划图 ----

def _topo_sort(tasks: list[dict]) -> list[dict]:
    """Kahn 拓扑排序（依赖先行）；环/未知依赖防御性忽略"""
    ids = {t["id"] for t in tasks}
    indeg = {t["id"]: sum(1 for d in t.get("depends_on", []) if d in ids) for t in tasks}
    children: dict[str, list[str]] = {t["id"]: [] for t in tasks}
    by_id = {t["id"]: t for t in tasks}
    for t in tasks:
        for d in t.get("depends_on", []):
            if d in ids:
                children[d].append(t["id"])

    order = []
    queue = [t["id"] for t in tasks if indeg[t["id"]] == 0]
    while queue:
        nid = queue.pop(0)
        order.append(by_id[nid])
        for c in children[nid]:
            indeg[c] -= 1
            if indeg[c] == 0:
                queue.append(c)

    done = {t["id"] for t in order}
    order += [t for t in tasks if t["id"] not in done]
    return order


def _run_task(t: dict) -> tuple[str, str]:
    """执行单个任务，返回 (result_text, status)（供并行执行器调用）"""
    executor = TOOL_EXECUTORS.get(t.get("tool"))
    if executor is None:
        return f"未知工具: {t.get('tool')}", "failed"
    try:
        result_text = _execute_tool_traced(t["tool"], t.get("args", {}), executor)
        return result_text[:1000], "done"
    except Exception as e:  # noqa: BLE001 — 单任务失败不中断
        return f"任务执行失败: {str(e)[:200]}", "failed"


def _layer_plan(tasks: list[dict]) -> list[list[dict]]:
    """按依赖分层：层内任务无相互依赖（可并行），层间依赖先行（串行）"""
    by_id = {t["id"]: t for t in tasks}
    depth: dict[str, int] = {}
    for t in _topo_sort(tasks):
        deps = [d for d in t.get("depends_on", []) if d in by_id]
        depth[t["id"]] = (max((depth[d] for d in deps), default=-1)) + 1
    layers: dict[int, list[dict]] = {}
    for t in tasks:
        layers.setdefault(depth[t["id"]], []).append(t)
    return [layers[k] for k in sorted(layers)]


def _submit_with_ctx(ex: concurrent.futures.ThreadPoolExecutor, fn, *args):
    """携带调用方 context 提交（W3 contextvars 传播，子线程 span 挂父 trace）"""
    ctx = contextvars.copy_context()
    return ex.submit(ctx.run, fn, *args)


def execute_task_graph(tasks: list[dict]) -> list[dict]:
    """分层并行执行任务图（W4），聚合为 collected_docs 结构。

    - 按依赖分层：层内无依赖任务并行执行（≤4 并发），层间依赖先行
    - 单任务失败不中断整图（status=failed，结果跳过）
    - 工具执行复用 _execute_tool_traced（tool_call span + W2 恢复链）
    """
    collected: list[dict] = []
    for layer in _layer_plan(tasks):
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(len(layer), 4)),
            thread_name_prefix="ark-task",
        ) as ex:
            futures = [_submit_with_ctx(ex, _run_task, t) for t in layer]
            for t, f in zip(layer, futures):
                result_text, status = f.result()
                t["status"] = status
                t["result"] = result_text
                if status == "done":
                    collected.append({
                        "tool": t["tool"],
                        "args": t.get("args", {}),
                        "result": result_text,
                    })
    return collected


# ---- W4 增强: 任务级 ReAct（Plan + 子 ReAct 混合）----

TASK_AGENT_PROMPT = """你是《明日方舟》剧情检索专员。围绕任务目标收集证据并给出小结。

任务目标：{task}

规则：
1. 先调用工具（可多步）收集与目标相关的证据，工具结果会追加在对话中
2. 证据足够后，直接回复（不要再调工具）：
   【任务完成】基于证据的简要小结
3. 只依据工具返回的证据总结，不编造证据之外的内容；证据不足时如实说明"""


def _execute_task_react(task: dict, max_steps: int = 3) -> str:
    """子任务 ReAct 循环：以任务描述为检索目标，LLM 自主多步检索。

    复用 chat_completion（重试+trace）与 _execute_tool_traced（tool_call span + 恢复链）。
    """
    from arknights_wiki.agent import wrap_user_input
    from arknights_wiki.extraction.llm_client import chat_completion

    desc = task.get("description") or task.get("id", "任务")
    messages = [
        {"role": "system", "content": TASK_AGENT_PROMPT.format(task=desc)},
        {"role": "user", "content": wrap_user_input(desc)},
    ]
    evidence: list[str] = []
    last_content = ""
    for _step in range(max_steps):
        content, assistant_message = chat_completion(
            messages=messages, temperature=0.1, tools=TOOL_DEFINITIONS,
        )
        new_msg: dict = {"role": "assistant"}
        if content:
            new_msg["content"] = content
        if not assistant_message.tool_calls:
            messages.append(new_msg)
            last_content = content or ""
            break
        new_msg["tool_calls"] = [
            {
                "id": tc.id, "type": tc.type,
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in assistant_message.tool_calls
        ]
        new_msg["content"] = assistant_message.content or ""
        messages.append(new_msg)
        for tc in assistant_message.tool_calls:
            func_name = tc.function.name
            try:
                func_args = json.loads(tc.function.arguments)
            except Exception:  # noqa: BLE001
                func_args = {}
            executor = TOOL_EXECUTORS.get(func_name)
            if executor is None:
                result_text = f"未知工具: {func_name}"
            else:
                result_text = _execute_tool_traced(func_name, func_args, executor)
            evidence.append(f"[{func_name}] {result_text[:800]}")
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "name": func_name, "content": result_text,
            })

    # 有最终小结优先返回小结；否则拼接证据
    if last_content:
        return last_content[:1500]
    return "\n".join(evidence)[:2000] if evidence else "未收集到证据"


def _run_task_react(t: dict, max_steps: int) -> tuple[str, str]:
    """执行单个任务级 ReAct，返回 (result_text, status)（供并行执行器调用）"""
    try:
        result_text = _execute_task_react(t, max_steps=max_steps)
        return result_text[:1000], "done"
    except Exception as e:  # noqa: BLE001 — 单任务失败不中断
        return f"任务执行失败: {str(e)[:200]}", "failed"


def execute_task_react_graph(tasks: list[dict], max_steps: int = 3) -> list[dict]:
    """任务级 ReAct 执行（W4 增强）：每任务一个子 ReAct 循环，分层并行，聚合结果"""
    collected: list[dict] = []
    for layer in _layer_plan(tasks):
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(len(layer), 4)),
            thread_name_prefix="ark-task-react",
        ) as ex:
            futures = [_submit_with_ctx(ex, _run_task_react, t, max_steps) for t in layer]
            for t, f in zip(layer, futures):
                result_text, status = f.result()
                t["status"] = status
                t["result"] = result_text
                if status == "done":
                    collected.append({
                        "tool": "task_react",
                        "args": {"task": t.get("description", ""), "id": t.get("id", "")},
                        "result": result_text,
                    })
    return collected


def plan_node(state: AgentState) -> AgentState:
    """W4: 规划节点 —— LLM 拆解任务图（规则兜底），写入 state.tasks"""
    from arknights_wiki.agent.planner import plan_tasks

    question = state["question"]
    route = state.get("route", {})
    use_llm = os.environ.get("ARKNIGHTS_PLANNER_LLM", "1") != "0"
    tasks, source = plan_tasks(question, route, use_llm=use_llm)

    # trace: planner span（schema 预留 node_type=planner）
    c = get_client()
    if c is not None:
        from arknights_wiki.observability import NODE_TYPE_PLANNER

        try:
            with c.start_as_current_observation(
                name="planner",
                as_type="span",
                metadata={"node_type": NODE_TYPE_PLANNER,
                          "n_tasks": len(tasks), "source": source},
            ):
                pass
        except Exception:  # noqa: BLE001 — 观测层失败不影响业务
            pass

    state["tasks"] = tasks
    state["planner_source"] = source
    return state


def execute_node(state: AgentState) -> AgentState:
    """W4: 执行节点 —— 执行任务图，聚合结果。

    ARKNIGHTS_PLANNER_TASK_REACT=1 时每任务跑子 ReAct 循环（Plan+子ReAct 混合），
    默认单工具执行（Plan-then-Execute）。
    """
    tasks = state.get("tasks", [])
    use_task_react = os.environ.get("ARKNIGHTS_PLANNER_TASK_REACT", "0") == "1"
    if use_task_react:
        collected = execute_task_react_graph(tasks)
    else:
        collected = execute_task_graph(tasks)
    state["collected_docs"] = state.get("collected_docs", []) + collected
    return state


# ---- W4 增强: Planner 崩溃检测 → ReAct 兜底 ----

_FALLBACK_SIGNALS = ("未找到", "未在", "未搜索到", "无法", "不足以", "没有找到",
                     "未检索到", "不存在", "查无")


def _fallback_enabled() -> bool:
    return os.environ.get("ARKNIGHTS_PLANNER_FALLBACK", "1") != "0"


def should_fallback_to_react(state: AgentState) -> str:
    """Planner 执行结果质量检测：证据不足 → 切 ReAct 兜底。

    触发条件（任一）:
      1. collected_docs 为空（任务全失败/任务图空）
      2. 有效证据（非"未找到"类文本）占比 < 40%
    Returns: "fallback" | "continue"
    """
    if not _fallback_enabled():
        return "continue"
    docs = state.get("collected_docs", [])
    if not docs:
        return "fallback"
    total = len(docs)
    weak = sum(
        1 for d in docs
        if any(sig in (d.get("result") or "") for sig in _FALLBACK_SIGNALS)
    )
    if total and weak / total >= 0.6:
        return "fallback"
    return "continue"


def build_planner_graph(checkpointer=None):
    """W4: Plan → Execute → (检测) → Synthesize 图（显式规划 + ReAct 兜底）

    执行结果证据不足时自动切 ReAct 循环（call_model ⇄ tool_node）再综合，
    保证开放型/知识库覆盖不足的问题仍有回答。
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_node("synthesize", synthesize_node)

    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "execute")
    workflow.add_conditional_edges(
        "execute",
        should_fallback_to_react,
        {"fallback": "agent", "continue": "synthesize"},
    )
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "synthesize": "synthesize"},
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("synthesize", END)

    return workflow.compile(checkpointer=checkpointer)
