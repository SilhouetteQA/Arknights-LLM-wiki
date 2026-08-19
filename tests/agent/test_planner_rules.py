"""Planner 规则模板与任务图校验测试（W4）"""
import pytest

from arknights_wiki.agent.planner import (
    build_rule_plan,
    check_plan,
    validate_tasks,
)


def _route(question_type: str, entities: list[str] | None = None, chapter: str | None = None) -> dict:
    return {
        "complexity": "complex",
        "question_type": question_type,
        "entities": entities or [],
        "time_scope": "cross_arc",
        "reason": "test",
    }


class TestRulePlanComparison:
    def test_two_entity_comparison(self):
        """comparison: 两实体 → 页面×2 + 事件×2"""
        plan = build_rule_plan(_route("comparison", ["凯尔希", "阿米娅"]))
        assert len(plan) == 4
        tools = [t["tool"] for t in plan]
        assert tools.count("get_entity_page") == 2
        assert tools.count("search_events") == 2

    def test_tasks_have_valid_structure(self):
        plan = build_rule_plan(_route("comparison", ["凯尔希", "阿米娅"]))
        for t in plan:
            assert t["id"]
            assert t["description"]
            assert t["tool"] in ("get_entity_page", "search_events", "search_wiki", "search_timeline")
            assert isinstance(t["args"], dict)
            assert isinstance(t["depends_on"], list)


class TestRulePlanByType:
    def test_chapter_summary(self):
        plan = build_rule_plan(_route("chapter_summary", ["第九章"], chapter="第九章"))
        tools = [t["tool"] for t in plan]
        assert "get_chapter_summary" in tools or "search_events" in tools

    def test_causal_reasoning_has_timeline(self):
        plan = build_rule_plan(_route("causal_reasoning", ["源石"]))
        tools = [t["tool"] for t in plan]
        assert "search_timeline" in tools

    def test_no_entity_fallback(self):
        """无实体 → 关键词搜索兜底"""
        plan = build_rule_plan(_route("fact_lookup", []))
        assert len(plan) >= 1
        assert plan[0]["tool"] in ("search_wiki", "semantic_search")


class TestValidateTasks:
    def test_invalid_tool_rejected(self):
        tasks = [{
            "id": "t1", "description": "x", "tool": "not_a_tool",
            "args": {"query": "q"}, "depends_on": [],
        }]
        ok, errors = validate_tasks(tasks)
        assert not ok
        assert any("tool" in e for e in errors)

    def test_dangling_dependency_rejected(self):
        tasks = [{
            "id": "t1", "description": "x", "tool": "search_wiki",
            "args": {"query": "q"}, "depends_on": ["t9"],
        }]
        ok, errors = validate_tasks(tasks)
        assert not ok
        assert any("t9" in e for e in errors)

    def test_cycle_detected(self):
        tasks = [
            {"id": "t1", "description": "x", "tool": "search_wiki", "args": {"query": "q"}, "depends_on": ["t2"]},
            {"id": "t2", "description": "x", "tool": "search_wiki", "args": {"query": "q"}, "depends_on": ["t1"]},
        ]
        ok, errors = validate_tasks(tasks)
        assert not ok
        assert any("环" in e for e in errors)

    def test_too_many_tasks_rejected(self):
        tasks = [
            {"id": f"t{i}", "description": "x", "tool": "search_wiki",
             "args": {"query": "q"}, "depends_on": []}
            for i in range(10)
        ]
        ok, errors = validate_tasks(tasks)
        assert not ok

    def test_valid_plan_passes(self):
        tasks = [
            {"id": "t1", "description": "查实体", "tool": "get_entity_page",
             "args": {"name": "凯尔希", "entity_type": "character"}, "depends_on": []},
            {"id": "t2", "description": "查事件", "tool": "search_events",
             "args": {"entity": "凯尔希"}, "depends_on": ["t1"]},
        ]
        ok, errors = validate_tasks(tasks)
        assert ok, errors


class TestCheckPlan:
    def test_check_plan_ok(self):
        plan = build_rule_plan(_route("comparison", ["凯尔希", "阿米娅"]))
        assert check_plan(plan) is True
