"""LangGraph Agent 测试"""
from unittest.mock import patch

from arknights_wiki.agent.graph import build_agent_graph, call_model, tool_node, synthesize_node
from arknights_wiki.agent.tools import TOOL_DEFINITIONS
from arknights_wiki.agent.state import AgentState


class TestAgentGraph:
    def test_build_graph_returns_compiled_graph(self):
        graph = build_agent_graph()
        assert graph is not None
        assert hasattr(graph, "invoke")


class TestAgentNode:
    def test_call_model_adds_assistant_message(self, mock_llm_client):
        """call_model: LLM 返回后 messages 中增加 assistant message"""
        state: AgentState = {
            "messages": [],
            "question": "岁兽有几个碎片？",
            "collected_docs": [],
            "iteration": 0,
            "route": {"complexity": "complex", "entities": ["岁兽"]},
        }
        with patch("arknights_wiki.extraction.llm_client.create_client", return_value=mock_llm_client):
            result = call_model(state)
            assert len(result["messages"]) > 0
            assert result["iteration"] == 1

    def test_tool_node_executes_and_adds_results(self):
        """tool_node 执行工具并将结果追加到 collected_docs"""
        state: AgentState = {
            "messages": [
                {"role": "user", "content": "测试问题"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "search_wiki",
                                "arguments": '{"query": "源石"}',
                            },
                        }
                    ],
                },
            ],
            "question": "测试问题",
            "collected_docs": [],
            "iteration": 1,
            "route": {},
        }

        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS") as mock_execs:
            mock_execs.get.return_value = lambda **kwargs: "找到 3 个结果"
            result = tool_node(state)
            assert len(result["collected_docs"]) > 0


class TestCASUALSynthesis:
    """CASUAL 风格 synthesis 测试"""
    def test_synthesis_no_docs_casual_message(self):
        state: AgentState = {
            "messages": [
                {"role": "system", "content": "test"},
                {"role": "user", "content": "不存在的实体是什么"},
            ],
            "question": "不存在的实体是什么",
            "collected_docs": [],
            "iteration": 1,
            "route": {"intent": "concept_definition", "entities": []},
        }
        result = synthesize_node(state)
        messages = result.get("messages", [])
        answer = messages[-1].get("content", "")
        assert "未找到" in answer or "无法" in answer
        assert len(answer) > 0

    def test_synthesis_with_docs_uses_synthesis_prompt(self, mock_llm_client):
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = "测试回答"
        state: AgentState = {
            "messages": [
                {"role": "system", "content": "test"},
                {"role": "user", "content": "源石是什么"},
            ],
            "question": "源石是什么",
            "collected_docs": [
                {"tool": "get_entity_page", "args": {"name": "源石", "entity_type": "concept"},
                 "result": "源石是泰拉世界的核心能源。"},
            ],
            "iteration": 1,
            "route": {"intent": "concept_definition", "entities": ["源石"]},
        }
        with patch("arknights_wiki.extraction.llm_client.create_client", return_value=mock_llm_client):
            result = synthesize_node(state)
            messages = result.get("messages", [])
            answer = messages[-1].get("content", "")
            assert "测试回答" in answer

    def test_lookup_entity_index_in_tool_definitions(self):
        tool_names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert "lookup_entity_index" in tool_names
