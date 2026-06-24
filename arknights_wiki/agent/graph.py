"""LangGraph ReAct Agent 图定义

Graph 结构:
  START -> call_model (agent_node)
             |- tool_calls -> tool_node -> call_model
             |- no_tool_calls -> synthesize_node -> END
"""
import json

from langgraph.graph import StateGraph, END

from arknights_wiki.agent.state import AgentState
from arknights_wiki.agent.prompts import AGENT_SYSTEM_PROMPT, SYNTHESIS_PROMPT
from arknights_wiki.agent.tools import TOOL_DEFINITIONS, TOOL_EXECUTORS

MAX_ITERATIONS = 8


def call_model(state: AgentState) -> AgentState:
    """调用 LLM（带 tool 定义），决定下一步: tool_call 或 final answer"""
    from arknights_wiki.extraction.llm_client import create_client

    question = state["question"]
    iteration = state.get("iteration", 0)

    if not state.get("messages"):
        state["messages"] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
    else:
        if state["messages"][0].get("role") != "system":
            state["messages"].insert(0, {"role": "system", "content": AGENT_SYSTEM_PROMPT})

    client = create_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=state["messages"],
        tools=TOOL_DEFINITIONS,
        temperature=0.1,
        max_tokens=8192,
    )

    choice = response.choices[0]
    assistant_message = choice.message

    new_message = {"role": "assistant"}
    if assistant_message.content:
        new_message["content"] = assistant_message.content
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
            try:
                result_text = executor(**func_args)
            except Exception as e:
                result_text = f"工具执行失败: {str(e)}"
        else:
            result_text = f"未知工具: {func_name}"

        collected_docs.append({
            "tool": func_name,
            "args": func_args,
            "result": result_text[:500],
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


def synthesize_node(state: AgentState) -> AgentState:
    """综合所有证据，生成最终回答"""
    from arknights_wiki.extraction.llm_client import create_client

    question = state["question"]
    collected_docs = state.get("collected_docs", [])

    evidence_parts = []
    for i, doc in enumerate(collected_docs, 1):
        evidence_parts.append(f"[来源{i}] 工具: {doc['tool']}, 参数: {doc['args']}")
        evidence_parts.append(doc["result"])
        evidence_parts.append("")

    evidence_text = "\n".join(evidence_parts) if evidence_parts else "无证据收集到。"

    if not collected_docs:
        answer = "未能收集到与问题相关的证据，无法回答。请尝试更具体地描述问题。"
    else:
        prompt = SYNTHESIS_PROMPT.format(evidence=evidence_text, question=question)
        try:
            client = create_client()
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )
            answer = response.choices[0].message.content or ""
        except Exception as e:
            answer = f"回答生成失败: {str(e)}"

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


def build_agent_graph():
    """构建并编译 LangGraph agent 图"""
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

    return workflow.compile()
