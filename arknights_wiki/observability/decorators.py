"""可开关 trace 装饰器（W1 Observability/Tracing）

traced() 是 langfuse observe 的可开关包装：
  - 关闭态: 装饰时即返回原函数（零开销、保持身份）
  - 开启态: 用 langfuse observe 包装；metadata_fn 回调结果写入 span metadata
"""
from __future__ import annotations

import functools

from arknights_wiki.observability.client import get_client, is_enabled


def traced(
    name: str | None = None,
    as_type: str = "span",
    capture_input: bool = False,
    capture_output: bool = False,
    metadata_fn=None,
):
    """可开关 trace 装饰器。

    Args:
        name: span 名称，缺省用函数名
        as_type: span | generation | tool | agent | chain | retriever 等（langfuse 支持类型）
        capture_input / capture_output: 是否记录函数入参/返回值原文（默认关，避免敏感/大文本）
        metadata_fn: (args, kwargs, result) -> dict | None，附加 metadata（如 cost/retry/工具参数）
    """

    def deco(func):
        if not is_enabled():
            return func

        from langfuse import observe

        decorated = observe(
            name=name or func.__name__,
            as_type=as_type,
            capture_input=capture_input,
            capture_output=capture_output,
        )(func)

        if metadata_fn is None:
            return decorated

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = decorated(*args, **kwargs)
            try:
                meta = metadata_fn(args, kwargs, result)
                if meta:
                    c = get_client()
                    if c is not None:
                        c.update_current_span(metadata=meta)
            except Exception:  # noqa: BLE001 — 观测层失败不影响业务
                pass
            return result

        return wrapper

    return deco
