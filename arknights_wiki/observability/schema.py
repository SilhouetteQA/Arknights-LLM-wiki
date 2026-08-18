"""Observability trace 结构约定与成本计算（W1 Observability/Tracing）

节点名常量供全仓埋点统一使用；成本口径与 eval/pricing.json 一致（RMB）。
node_type 预留字段：W2 Retry / W4 Planner / W5 Critic 节点接入时沿用。
"""
from __future__ import annotations

import json
from pathlib import Path

# ---- trace 根 ----
TRACE_ROOT = "chat_request"  # server.py /chat 根 span

# ---- 节点名（Spec §3.3 埋点清单）----
SPAN_ROUTER = "router"  # router.py route_query
GENERATION_INTENT_REWRITE = "intent_rewrite_llm"  # router.py _llm_intent_rewrite
SPAN_SIMPLE_SEARCH = "simple_search"  # simple_search.py 主函数
SPAN_RETRIEVAL = "retrieval"  # 各检索层
SPAN_FAISS = "faiss_search"  # vector_index.semantic_search
GENERATION_ANSWER = "answer_generation"  # simple_search 回答生成
GENERATION_LLM = "llm_call"  # llm_client.chat_completion 统一 LLM 调用
SPAN_AGENT_CALL = "agent_call_model"  # graph.py call_model
SPAN_TOOL = "tool_call"  # graph.py tool_node 内每个工具
SPAN_SYNTHESIZE = "synthesize"  # graph.py synthesize_node

# ---- node_type 预留（后续窗口）----
NODE_TYPE_PLANNER = "planner"  # W4
NODE_TYPE_CRITIC = "critic"  # W5
NODE_TYPE_RETRY = "retry"  # W2

_PRICING_CACHE: dict | None = None


def _load_pricing() -> dict:
    global _PRICING_CACHE
    if _PRICING_CACHE is None:
        path = Path(__file__).resolve().parents[1] / "eval" / "pricing.json"
        _PRICING_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _PRICING_CACHE


def compute_cost_rmb(model: str, tokens_in: int, tokens_out: int) -> float:
    """按单价表计算成本（RMB/元）。未知单价记 0（与 eval.llm.compute_cost 同口径）。"""
    price = _load_pricing().get(model)
    if not price:
        return 0.0
    p_in, p_out = price.get("in"), price.get("out")
    if p_in in (None, "tbd") or p_out in (None, "tbd"):
        return 0.0
    return tokens_in / 1e6 * p_in + tokens_out / 1e6 * p_out
