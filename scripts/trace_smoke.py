"""W1 Observability 冒烟脚本：验证 Langfuse trace 写入链路

用法（需先启动 Langfuse 并配置环境变量）：
  set LANGFUSE_PUBLIC_KEY=... & set LANGFUSE_SECRET_KEY=... & set LANGFUSE_BASE_URL=http://localhost:3000
  python scripts/trace_smoke.py

产出：一条最小 trace（chat_request 根 → 3 个嵌套 span/generation），
可在 Langfuse UI 中验证层级结构与 usage/cost 字段。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arknights_wiki.observability import (
    GENERATION_LLM,
    SPAN_RETRIEVAL,
    SPAN_ROUTER,
    TRACE_ROOT,
    flush,
    get_client,
    is_enabled,
    record_llm_usage,
    traced,
)


@traced(name=SPAN_ROUTER)
def _fake_router(q: str) -> dict:
    return {"complexity": "simple", "question_type": "fact_lookup"}


@traced(name=SPAN_RETRIEVAL, metadata_fn=lambda a, k, r: {"n_sources": len(r)})
def _fake_retrieve(q: str) -> list[str]:
    return ["阿米娅", "罗德岛"]


@traced(name=GENERATION_LLM, as_type="generation")
def _fake_llm(q: str) -> str:
    record_llm_usage("deepseek-4-flash", 120, 40, 0.00056, extra={"stage": "smoke"})
    return "测试回答"


def main() -> int:
    if not is_enabled():
        print("错误：未启用 trace（需要 LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL）")
        return 1

    c = get_client()
    with c.start_as_current_observation(
        name=TRACE_ROOT,
        as_type="chain",
        input={"question": "冒烟测试问题"},
        metadata={"complexity": "simple", "question_type": "fact_lookup", "smoke": True},
    ):
        route = _fake_router("冒烟测试问题")
        docs = _fake_retrieve("冒烟测试问题")
        answer = _fake_llm("冒烟测试问题")
        print(f"route={route} docs={docs} answer={answer}")
    flush()
    print("冒烟完成：请到 Langfuse UI (http://localhost:3000) 查看 chat_request trace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
