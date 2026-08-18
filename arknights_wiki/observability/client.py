"""Observability 客户端与全局开关（W1 Observability/Tracing）

设计原则（Spec 2026-08-18-w1-observability §3.2）:
  - 可开关: 未配置 LANGFUSE_* 三键 或 ARKNIGHTS_TRACING=0 时全部 no-op
  - 懒加载: get_client() 首次调用才初始化 langfuse，关闭态零开销
  - 不侵入: 业务代码只 import is_enabled/traced/flush，无其他副作用
"""
from __future__ import annotations

import os

_client = None


def is_enabled() -> bool:
    """全局开关：LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY + LANGFUSE_BASE_URL 齐备，
    且 ARKNIGHTS_TRACING 未显式设为 '0'。"""
    if os.environ.get("ARKNIGHTS_TRACING") == "0":
        return False
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
        and os.environ.get("LANGFUSE_BASE_URL")
    )


def get_client():
    """懒加载 Langfuse 客户端；未启用时返回 None（不初始化、不产生警告）。"""
    global _client
    if not is_enabled():
        return None
    if _client is None:
        from langfuse import get_client as _get_client

        _client = _get_client()
    return _client


def flush() -> None:
    """冲刷未导出的 trace（短生命周期进程/脚本结束前调用）。"""
    c = get_client()
    if c is not None:
        try:
            c.flush()
        except Exception:  # noqa: BLE001 — 观测层失败不影响业务
            pass


def record_llm_usage(
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost: float,
    *,
    extra: dict | None = None,
) -> None:
    """在当前的 generation observation 上记录 LLM usage/cost（由 traced(as_type='generation') 内部调用）。

    SDK v4 中 usage/cost 只能通过 update_current_generation 写入（update_current_span 无此参数），
    因此调用方必须处于 generation observation 内。不启用时 no-op。
    """
    c = get_client()
    if c is None:
        return
    try:
        usage = {"input": int(tokens_in or 0), "output": int(tokens_out or 0)}
        details = {"total": round(float(cost or 0.0), 6)}
        meta = {"model": model, "retry": 0}
        if extra:
            meta.update(extra)
        c.update_current_generation(
            model=model,
            usage_details=usage,
            cost_details=details,
            metadata=meta,
        )
    except Exception:  # noqa: BLE001 — 观测层失败不影响业务
        pass
