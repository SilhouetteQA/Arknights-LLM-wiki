"""W4 Planner 验收脚本：示例拆解 + 真实问答（Planner 路径）+ trace

用法:
  python scripts/planner_demo.py [问题]
  默认问题: "分析凯尔希与罗德岛的历史关系，并按照时间线整理"
环境:
  ARKNIGHTS_AGENT_MODE=react 可对比 ReAct 路径（默认 planner）
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _enable_trace_from_env_file():
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
    question = sys.argv[1] if len(sys.argv) > 1 else "分析凯尔希与罗德岛的历史关系，并按照时间线整理"
    _enable_trace_from_env_file()

    from arknights_wiki.agent.router import route_query
    from arknights_wiki.observability import TRACE_ROOT, flush, get_client

    print(f"问题: {question}")
    route = route_query(question)
    print(f"路由: complexity={route['complexity']} type={route['question_type']} entities={route['entities']}")

    # 展示任务图（规划）
    from arknights_wiki.agent.planner import plan_tasks
    plan, source = plan_tasks(question, route)
    print(f"\n任务图（来源: {source}，{len(plan)} 个任务）:")
    for t in plan:
        print(f"  [{t['id']}] {t['tool']}({json.dumps(t['args'], ensure_ascii=False)}) 依赖={t['depends_on']}")

    if route["complexity"] == "simple":
        print("\n[simple 路径，不走 Planner]")
        from arknights_wiki.agent.simple_search import simple_search
        c = get_client()
        ctx = c.start_as_current_observation(
            name=TRACE_ROOT, as_type="chain", input={"question": question},
            metadata={"complexity": "simple", "benchmark_id": "w4-acceptance"},
        ) if c else contextlib.nullcontext()
        with ctx:
            result = simple_search(question, route)
        answer = result["answer"]
    else:
        from arknights_wiki.agent.graph import build_planner_graph
        from arknights_wiki.agent.state import AgentState
        mode = os.environ.get("ARKNIGHTS_AGENT_MODE", "planner")
        print(f"\n[complex 路径，agent_mode={mode}]")
        c = get_client()
        ctx = c.start_as_current_observation(
            name=TRACE_ROOT, as_type="chain", input={"question": question},
            metadata={"complexity": "complex", "question_type": route.get("question_type", ""),
                      "benchmark_id": "w4-acceptance"},
        ) if c else contextlib.nullcontext()
        with ctx:
            graph = build_planner_graph()
            state: AgentState = {
                "messages": [], "question": question, "collected_docs": [],
                "iteration": 0, "route": route,
            }
            final = graph.invoke(state)
        answer = final["messages"][-1].get("content", "")
        print(f"工具调用: {len(final.get('collected_docs', []))} 次 | planner_source={final.get('planner_source')}")

    flush()
    print(f"\n回答摘要: {answer[:400]}")
    print("\ntrace 已导出: http://localhost:3000 (benchmark_id=w4-acceptance)")


if __name__ == "__main__":
    main()
