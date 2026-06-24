"""Query Router 测试"""
from unittest.mock import patch

from arknights_wiki.agent.router import (
    _extract_entities_local,
    _infer_question_type,
    _infer_time_scope,
    classify_complexity_local,
    route_query,
)


class TestQuestionType:
    def test_worldview_type(self):
        assert _infer_question_type("源石是什么") == "worldview"

    def test_event_type(self):
        assert _infer_question_type("黑暗时代上发生了什么") == "event"

    def test_comparison_type(self):
        assert _infer_question_type("阿米娅和凯尔希对比") == "comparison"

    def test_summary_type(self):
        assert _infer_question_type("整体剧情脉络") == "summary"

    def test_default_event(self):
        assert _infer_question_type("第三章") == "event"


class TestTimeScope:
    def test_cross_arc_indicators(self):
        assert _infer_time_scope("矿石病在整个泰拉的演变", []) == "cross_arc"

    def test_chapter_explicit(self):
        assert _infer_time_scope("第三章讲了什么", ["第三章"]) == "chapter"

    def test_default_cross_arc(self):
        assert _infer_time_scope("源石是什么", ["源石"]) == "cross_arc"


class TestComplexity:
    def test_simple_fact(self):
        result = classify_complexity_local("源石是什么", ["源石"], "worldview", "cross_arc")
        assert result["complexity"] == "simple"

    def test_complex_comparison(self):
        result = classify_complexity_local(
            "对比阿米娅和凯尔希", ["阿米娅", "凯尔希"], "comparison", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_complex_causal(self):
        result = classify_complexity_local(
            "切尔诺伯格事件的起因是什么", [], "event", "cross_arc"
        )
        assert result["complexity"] == "complex"


class TestRouteQuery:
    def test_route_simple_question(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = route_query("源石是什么")
            assert "complexity" in result
            assert "question_type" in result
            assert "entities" in result
            assert isinstance(result["entities"], list)
