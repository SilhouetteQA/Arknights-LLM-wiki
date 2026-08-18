"""W3 MCP 验收脚本：Agent 走 MCP 完成一次真实问答 + trace 验证

用法:
  ARKNIGHTS_USE_MCP=1 python scripts/mcp_demo.py [问题]
  默认问题: "凯尔希和罗德岛之间是什么关系？请梳理时间线"

验证点:
  1. complex 路径 LangGraph 工具经 MCP client 调用（tool_call → mcp_call trace 层级）
  2. 回答正常产出（真实 LLM）
  3. Langfuse trace 落库（benchmark_id=w3-acceptance 可过滤）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _enable_trace_from_env_file():
    """从 docker/langfuse/.env 注入 SDK 三键（不覆盖已设置值）"""
    env_file = PROJECT_ROOT / "docker" / "langfuse" / ".env"
    if not env_file.exists():
        return
    env = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"')
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", env.get("LANGFUSE_INIT_PROJECT_PUBLIC_KEY", ""))
    os.environ.setdefault("LANGFUSE_SECRET_KEY", env.get("LANGFUSE_INIT_PROJECT_SECRET_KEY", ""))
    os.environ.setdefault("LANGFUSE_BASE_URL", env.get("LANGFUSE_BASE_URL", "http://localhost:3000"))


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "凯尔希和罗德岛之间是什么关系？请梳理时间线"
    _enable_trace_from_env_file()
    os.environ["ARKNIGHTS_USE_MCP"] = "1"

    from arknights_wiki.agent.router import route_query
    from arknights_wiki.observability import TRACE_ROOT, flush, get_client
    from arknights_wiki.observability.client import is_enabled

    print(f"问题: {question}")
    route = route_query(question)
    print(f"路由: complexity={route['complexity']} type={route['question_type']}")

    c = get_client()
    ctx = c.start_as_current_observation(
        name=TRACE_ROOT, as_type="chain",
        input={"question": question},
        metadata={"complexity": route.get("complexity", ""),
                  "question_type": route.get("question_type", ""),
                  "benchmark_id": "w3-acceptance"},
    ) if c else __import__("contextlib").nullcontext()

    with ctx:
        if route["complexity"] == "simple":
            from arknights_wiki.agent.simple_search import simple_search
            result = simple_search(question, route)
            answer = result["answer"]
        else:
            from arknights_wiki.agent.graph import build_agent_graph
            from arknights_wiki.agent.state import AgentState
            graph = build_agent_graph()
            state: AgentState = {
                "messages": [], "question": question,
                "collected_docs": [], "iteration": 0, "route": route,
            }
            final = graph.invoke(state)
            answer = final["messages"][-1].get("content", "")
            n_tools = len(final.get("collected_docs", []))
            print(f"工具调用次数: {n_tools}")

    flush()
    print(f"\n回答摘要: {answer[:300]}")
    print(f"\ntrace 已导出（is_enabled={is_enabled()}），UI: http://localhost:3000 (benchmark_id=w3-acceptance)")


if __name__ == "__main__":
    main()
