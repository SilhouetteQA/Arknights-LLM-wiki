"""Observability 层（W1 Observability/Tracing）

对外 API：is_enabled / get_client / traced / flush / record_llm_usage / compute_cost_rmb
用法：
    from arknights_wiki.observability import traced, is_enabled
    @traced(name="my_step", as_type="span")
    def my_func(...): ...
"""
from arknights_wiki.observability.client import (
    flush,
    get_client,
    is_enabled,
    record_llm_usage,
)
from arknights_wiki.observability.decorators import traced
from arknights_wiki.observability.schema import (
    GENERATION_ANSWER,
    GENERATION_INTENT_REWRITE,
    GENERATION_LLM,
    NODE_TYPE_CRITIC,
    NODE_TYPE_PLANNER,
    NODE_TYPE_RETRY,
    SPAN_AGENT_CALL,
    SPAN_FAISS,
    SPAN_RETRIEVAL,
    SPAN_ROUTER,
    SPAN_SIMPLE_SEARCH,
    SPAN_SYNTHESIZE,
    SPAN_TOOL,
    TRACE_ROOT,
    compute_cost_rmb,
)

__all__ = [
    "flush",
    "get_client",
    "is_enabled",
    "traced",
    "record_llm_usage",
    "compute_cost_rmb",
    "TRACE_ROOT",
    "SPAN_ROUTER",
    "GENERATION_INTENT_REWRITE",
    "SPAN_SIMPLE_SEARCH",
    "SPAN_RETRIEVAL",
    "SPAN_FAISS",
    "GENERATION_ANSWER",
    "GENERATION_LLM",
    "SPAN_AGENT_CALL",
    "SPAN_TOOL",
    "SPAN_SYNTHESIZE",
    "NODE_TYPE_PLANNER",
    "NODE_TYPE_CRITIC",
    "NODE_TYPE_RETRY",
]
