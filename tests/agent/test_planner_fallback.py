"""Planner 崩溃检测 → ReAct 兜底测试（W4 增强）"""
from unittest.mock import patch

from arknights_wiki.agent.graph import build_planner_graph, should_fallback_to_react
from arknights_wiki.agent.state import AgentState


def _state(docs: list | None = None) -> AgentState:
    return {
        "messages": [],
        "question": "问题",
        "collected_docs": docs or [],
        "iteration": 0,
        "route": {"complexity": "complex", "question_type": "comparison", "entities": ["A", "B"]},
    }


class TestShouldFallback:
    def test_empty_docs_falls_back(self):
        assert should_fallback_to_react(_state([])) == "fallback"

    def test_good_evidence_continues(self):
        state = _state([{"tool": "search_wiki", "args": {}, "result": "凯尔希是罗德岛成员。"}])
        assert should_fallback_to_react(state) == "continue"

    def test_weak_evidence_falls_back(self):
        """结果大部分是"未找到" → fallback"""
        state = _state([
            {"tool": "search_wiki", "args": {}, "result": "未找到与 x 相关的资料"},
            {"tool": "search_wiki", "args": {}, "result": "未在知识库中找到 y"},
            {"tool": "search_wiki", "args": {}, "result": "凯尔希是罗德岛成员。"},
        ])
        assert should_fallback_to_react(state) == "fallback"

    def test_disabled_no_fallback(self, monkeypatch):
        monkeypatch.setenv("ARKNIGHTS_PLANNER_FALLBACK", "0")
        assert should_fallback_to_react(_state([])) == "continue"


class TestPlannerGraphFallback:
    def _fake_msg(self, content: str, tool_calls: list | None = None):
        class _Msg:
            pass
        m = _Msg()
        m.content = content
        m.tool_calls = tool_calls
        return m

    def test_fallback_runs_react_then_synthesize(self):
        """execute 后证据不足 → 走 agent(ReAct) → synthesize"""
        import types

        tool_tc = types.SimpleNamespace(
            id="tc1", type="function",
            function=types.SimpleNamespace(name="search_wiki", arguments='{"query": "A"}'),
        )
        tool_msg = self._fake_msg("需要检索", [tool_tc])
        final_msg = self._fake_msg("ReAct 兜底后的最终回答")

        def _fake_executor(**kwargs):
            return "ReAct 检索到的关键证据"

        with patch("arknights_wiki.agent.planner.plan_tasks",
                   return_value=([{"id": "t1", "tool": "search_wiki",
                                   "args": {"query": "x"}, "depends_on": []}], "rule")):
            with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS", {"search_wiki": _fake_executor}):
                with patch("arknights_wiki.extraction.llm_client.chat_completion",
                           side_effect=[
                               ("", tool_msg),          # agent: 决策要检索
                               ("最终回答", final_msg),  # agent: 检索后无 tool_calls
                               ("ReAct 兜底后的最终回答", final_msg),  # synthesize
                           ]):
                    graph = build_planner_graph()
                    # Planner execute 结果弱证据（手动构造不经过真实 execute）
                    state = _state([
                        {"tool": "search_wiki", "args": {}, "result": "未找到与 x 相关的资料"},
                        {"tool": "search_wiki", "args": {}, "result": "未找到 y 的资料"},
                    ])
                    final = graph.invoke(state)
        assert "ReAct 兜底后的最终回答" in final["messages"][-1]["content"]

    def test_good_evidence_skips_react(self):
        """证据充分 → 直接 synthesize，不经 agent"""
        final_msg = self._fake_msg("Planner 直接综合的答案")
        with patch("arknights_wiki.agent.planner.plan_tasks",
                   return_value=([{"id": "t1", "tool": "search_wiki",
                                   "args": {"query": "x"}, "depends_on": []}], "rule")):
            with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS", {"search_wiki": lambda **kw: "有效证据"}):
                with patch("arknights_wiki.extraction.llm_client.chat_completion",
                           return_value=("Planner 直接综合的答案", final_msg)):
                    graph = build_planner_graph()
                    final = graph.invoke(_state())
        assert "Planner 直接综合的答案" in final["messages"][-1]["content"]
