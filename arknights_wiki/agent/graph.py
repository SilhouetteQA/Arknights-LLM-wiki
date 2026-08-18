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
