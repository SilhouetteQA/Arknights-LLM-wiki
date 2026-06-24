"""LangGraph Agent 状态定义"""
from typing import TypedDict


class AgentState(TypedDict):
    messages: list          # 完整对话历史（含 ToolMessage）
    question: str           # 用户原始问题
    collected_docs: list    # 已收集的检索结果
    iteration: int          # 当前 ReAct 迭代次数
    route: dict             # Router 分类结果: {complexity, question_type, entities, time_scope, reason}
