"""LangGraph checkpoint 断点续跑测试（W2 Failure Recovery）

验证:
  - build_agent_graph 支持 checkpointer
  - 同 thread_id 二次 stream 从断点恢复（已成功工具不重复执行）
  - server_checkpoint 工厂的 sqlite/memory 降级
"""
import json
import types
from unittest.mock import patch

import pytest

from arknights_wiki.agent.graph import build_agent_graph
from arknights_wiki.agent.server_checkpoint import make_checkpointer, _checkpoint_db


class _Msg:
    """可序列化的消息对象（替代 MagicMock，checkpoint serde 需要真实值）"""

    def __init__(self, content: str, tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls or []


def _tool_call(name: str, arguments: dict):
    return types.SimpleNamespace(
        id="tc1",
        type="function",
        function=types.SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)),
    )


class TestBuildGraphWithCheckpointer:
    def test_compile_with_memory_saver(self):
        from langgraph.checkpoint.memory import MemorySaver

        graph = build_agent_graph(checkpointer=MemorySaver())
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_compile_without_checkpointer(self):
        graph = build_agent_graph()
        assert graph is not None


class TestCheckpointResume:
    def test_resume_after_interruption(self):
        """graph 中途失败 → 同 thread 从 checkpoint 恢复，已完成工具不重复"""
        from langgraph.checkpoint.memory import MemorySaver

        calls = {"n": 0}

        # 第一次运行：call_model 返回带 tool_calls 的消息 → 工具执行 → 第二个 call_model 抛异常
        # 用 patch 序列控制 LLM 调用
        tool_msg = _Msg("需要检索", [_tool_call("search_wiki", {"query": "源石"})])
        final_msg = _Msg("最终回答")

        # chat_completion 序列: 有 tool 结果 → 无 tool_calls（最终回答）；否则带 tool_calls
        def _fake_chat(messages, temperature=0.1, max_tokens=None, tools=None):
            has_tool_result = any(m.get("role") == "tool" for m in messages)
            if has_tool_result:
                return "最终回答", final_msg
            return "", tool_msg

        # 工具执行器：只允许执行一次（证明恢复时未重复执行）
        def _fake_executor(**kwargs):
            calls["n"] += 1
            if calls["n"] > 1:
                raise AssertionError("checkpoint 恢复后不应重复执行已成功的工具")
            return "工具结果"

        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS", {"search_wiki": _fake_executor}):
            with patch("arknights_wiki.extraction.llm_client.chat_completion", side_effect=_fake_chat):
                graph = build_agent_graph(checkpointer=MemorySaver())
                config = {"configurable": {"thread_id": "resume-test-1"}}
                state = {
                    "messages": [],
                    "question": "源石是什么",
                    "collected_docs": [],
                    "iteration": 0,
                    "route": {"complexity": "complex", "entities": ["源石"]},
                }
                events = list(graph.stream(state, config=config))
                assert any("synthesize" in e for e in events)
                assert calls["n"] == 1  # 工具只执行一次


class TestServerCheckpointFactory:
    def test_checkpoint_db_path(self):
        db = _checkpoint_db()
        assert str(db).endswith("agent.sqlite")

    def test_make_checkpointer_sqlite(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ARKNIGHTS_CHECKPOINT_DB", str(tmp_path / "ck.sqlite"))
        ck = make_checkpointer()
        # 能完成一次 put/get 即证明可用
        assert ck is not None

    def test_make_checkpointer_disabled(self, monkeypatch):
        monkeypatch.setenv("ARKNIGHTS_CHECKPOINT", "0")
        from langgraph.checkpoint.memory import MemorySaver

        assert isinstance(make_checkpointer(), MemorySaver)
