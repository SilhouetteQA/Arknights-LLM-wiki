"""Planner graph 集成测试（W4: plan → execute → synthesize）"""
from unittest.mock import MagicMock, patch

from arknights_wiki.agent.graph import build_planner_graph, execute_node, plan_node
from arknights_wiki.agent.state import AgentState


class _Msg:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = None


def _state(**overrides) -> AgentState:
    state: AgentState = {
        "messages": [],
        "question": "凯尔希与罗德岛是什么关系？",
        "collected_docs": [],
        "iteration": 0,
        "route": {"complexity": "complex", "question_type": "comparison",
                  "entities": ["凯尔希", "罗德岛"]},
    }
    state.update(overrides)
    return state


class TestPlanNode:
    def test_plan_node_writes_tasks(self):
        with patch("arknights_wiki.agent.planner.plan_tasks",
                   return_value=([{"id": "t1", "tool": "search_wiki",
                                   "args": {"query": "q"}, "depends_on": []}], "rule")):
            state = plan_node(_state())
        assert len(state["tasks"]) == 1
        assert state["planner_source"] == "rule"


class TestExecuteNode:
    def test_execute_node_aggregates(self):
        def fake_executor(**kwargs):
            return "res"

        state = _state(tasks=[
            {"id": "t1", "tool": "search_wiki", "args": {"query": "q"},
             "depends_on": [], "status": "pending"},
        ])
        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS", {"search_wiki": fake_executor}):
            out = execute_node(state)
        assert len(out["collected_docs"]) == 1
        assert out["collected_docs"][0]["result"] == "res"


class TestPlannerGraph:
    def test_full_graph_invoke(self):
        """plan → execute → synthesize 全链路（mock 规划与 LLM）"""
        fake_msg = _Msg("凯尔希与罗德岛关系密切，她是罗德岛的核心成员。")
        with patch("arknights_wiki.agent.planner.plan_tasks",
                   return_value=([{"id": "t1", "tool": "search_wiki",
                                   "args": {"query": "凯尔希"}, "depends_on": []}], "rule")):
            with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS",
                       {"search_wiki": lambda **kw: "凯尔希是罗德岛医疗部门负责人。"}):
                with patch("arknights_wiki.extraction.llm_client.chat_completion",
                           return_value=(fake_msg.content, fake_msg)):
                    graph = build_planner_graph()
                    final = graph.invoke(_state())
        assert "凯尔希与罗德岛关系密切" in final["messages"][-1]["content"]
        assert len(final["collected_docs"]) == 1
