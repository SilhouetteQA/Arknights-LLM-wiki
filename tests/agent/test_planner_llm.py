"""Planner LLM 规划测试（W4：LLM 任务图 + 白名单校验 + 规则兜底）"""
import json
from unittest.mock import MagicMock, patch

from arknights_wiki.agent.planner import MAX_TASKS, plan_tasks

_ROUTE = {
    "complexity": "complex", "question_type": "comparison",
    "entities": ["凯尔希", "阿米娅"], "time_scope": "cross_arc",
}


def _valid_plan_json(n: int = 3) -> str:
    tasks = [
        {"id": f"t{i}", "description": f"任务{i}", "tool": "search_wiki",
         "args": {"query": "q"}, "depends_on": []}
        for i in range(1, n + 1)
    ]
    return json.dumps(tasks, ensure_ascii=False)


class TestPlanTasksLlm:
    def test_llm_valid_plan_used(self):
        """LLM 返回合法任务图 → 使用 llm 规划"""
        mock_msg = MagicMock()
        mock_msg.content = _valid_plan_json(3)
        mock_msg.tool_calls = None
        with patch("arknights_wiki.extraction.llm_client.chat_completion",
                   return_value=(mock_msg.content, mock_msg)):
            plan, source = plan_tasks("问题", _ROUTE)
        assert source == "llm"
        assert len(plan) == 3

    def test_llm_invalid_tool_falls_back_to_rule(self):
        """LLM 幻觉非法工具 → 规则兜底"""
        tasks = [{"id": "t1", "description": "x", "tool": "not_a_tool",
                  "args": {}, "depends_on": []}]
        mock_msg = MagicMock()
        mock_msg.content = json.dumps(tasks)
        mock_msg.tool_calls = None
        with patch("arknights_wiki.extraction.llm_client.chat_completion",
                   return_value=("", mock_msg)):
            plan, source = plan_tasks("问题", _ROUTE)
        assert source == "rule"
        # 规则模板：comparison 两实体 → 4 任务
        assert len(plan) == 4

    def test_llm_exception_falls_back(self):
        """LLM 调用异常 → 规则兜底"""
        with patch("arknights_wiki.extraction.llm_client.chat_completion",
                   side_effect=ConnectionError("api down")):
            plan, source = plan_tasks("问题", _ROUTE)
        assert source == "rule"
        assert len(plan) > 0

    def test_use_llm_false_rule_only(self):
        """关闭 LLM → 纯规则"""
        plan, source = plan_tasks("问题", _ROUTE, use_llm=False)
        assert source == "rule"
        assert len(plan) == 4

    def test_llm_too_many_tasks_falls_back(self):
        """LLM 返回超上限任务数 → 规则兜底"""
        mock_msg = MagicMock()
        mock_msg.content = _valid_plan_json(MAX_TASKS + 2)
        mock_msg.tool_calls = None
        with patch("arknights_wiki.extraction.llm_client.chat_completion",
                   return_value=("", mock_msg)):
            plan, source = plan_tasks("问题", _ROUTE)
        assert source == "rule"
