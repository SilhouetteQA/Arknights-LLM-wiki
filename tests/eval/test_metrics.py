"""T6: 指标聚合与报告测试"""
import json
from pathlib import Path

from arknights_wiki.eval.metrics import aggregate, hallucination_rate, rule_metrics, summarize_cost


def _row(rid, mode, cat, m=None, j=None):
    return {
        "id": rid,
        "mode": mode,
        "category": cat,
        "metrics": m or {"tool_selection_accuracy": 1.0, "task_completion": 1.0},
        "judge": j or {
            "answer_correctness": 0.8,
            "faithfulness": 0.9,
            "citation_accuracy": None,
            "hallucination": 0,
        },
    }


class TestAggregate:
    def test_single_mode(self):
        rows = [_row("a", "direct", "single_hop"), _row("b", "direct", "single_hop")]
        agg = aggregate(rows)
        assert agg["modes"] == ["direct"]
        m = agg["by_mode"]["direct"]["metrics"]
        assert m["answer_correctness"] == 0.8
        assert m["hallucination"] == 1.0  # 无幻觉率
        assert m["overall"] is not None

    def test_two_modes_and_categories(self):
        rows = [
            _row("a", "direct", "single_hop"),
            _row("a", "http", "single_hop"),
            _row("b", "http", "timeline"),
        ]
        agg = aggregate(rows)
        assert set(agg["modes"]) == {"direct", "http"}
        cats_direct = agg["by_mode"]["direct"]["categories"]
        assert cats_direct["single_hop"]["count"] == 1
        cats_http = agg["by_mode"]["http"]["categories"]
        assert cats_http["timeline"]["count"] == 1

    def test_na_citation_excluded(self):
        rows = [_row("a", "direct", "single_hop")]
        agg = aggregate(rows)
        assert agg["by_mode"]["direct"]["metrics"]["citation_accuracy"] is None

    def test_na_hallucination_excluded(self):
        """回归：hallucination=None（judge 失败）时 aggregate 不应崩溃（2026-08-17 修复）"""
        r = _row("a", "direct", "single_hop")
        r["judge"]["hallucination"] = None
        agg = aggregate([r])
        assert agg["by_mode"]["direct"]["metrics"]["hallucination"] is None


class TestRuleMetrics:
    """规则指标（2026-08-17 统一至 metrics.py 单一数据源，tool_selection 用交集语义）"""

    def test_reject_answer_counts_complete(self):
        m = rule_metrics("知识库中未找到相关资料，无法回答。", [], [], "reject")
        assert m["task_completion"] == 1.0

    def test_reject_missing_answer_counts_incomplete(self):
        m = rule_metrics("这是罗德岛的设定。", [], [], "reject")
        assert m["task_completion"] == 0.0

    def test_tool_selection_exact_match(self):
        m = rule_metrics("答案" * 20, ["get_entity_page", "search_events"], ["get_entity_page", "search_events"], "complex")
        assert m["tool_selection_accuracy"] == 1.0

    def test_tool_selection_no_overlap(self):
        m = rule_metrics("答案" * 20, ["search_dialogue"], ["get_entity_page"], "complex")
        assert m["tool_selection_accuracy"] == 0.0

    def test_tool_selection_superset_ok(self):
        """回归：Agent 多调探索工具（超集）不再判 0（2026-08-17 修复，原 62/100 误伤）"""
        m = rule_metrics("答案" * 20, ["get_entity_page", "semantic_search", "search_dialogue"], ["get_entity_page"], "complex")
        assert m["tool_selection_accuracy"] == 1.0

    def test_simple_no_tools_ok(self):
        m = rule_metrics("答案" * 20, [], [], "simple")
        assert m["tool_selection_accuracy"] == 1.0

    def test_no_tools_called_fails(self):
        m = rule_metrics("答案" * 20, [], ["get_entity_page"], "complex")
        assert m["tool_selection_accuracy"] == 0.0

    def test_normal_answer_short_fails(self):
        m = rule_metrics("短", [], [], "simple")
        assert m["task_completion"] == 0.0


class TestHallucinationRate:
    """deepeval HallucinationMetric 原始分 → 幻觉率转换（2026-08-17 修复反转）"""

    def test_zero_score_no_hallucination(self):
        assert hallucination_rate(0.0) == 0.0

    def test_high_score_hallucination(self):
        assert hallucination_rate(0.7) == 1.0
        assert hallucination_rate(0.5) == 1.0  # threshold 边界判有幻觉

    def test_low_score_no_hallucination(self):
        assert hallucination_rate(0.4) == 0.0


def _tmp(sub: str) -> Path:
    p = Path(__file__).resolve().parents[2] / "output" / "_tmp_tests" / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


class TestSummarizeCost:
    def test_empty(self):
        assert summarize_cost(_tmp("cost_empty") / "missing.jsonl")["total"] == 0.0

    def test_aggregation(self):
        p = _tmp("cost_agg") / "cost_log.jsonl"
        p.write_text(
            '{"step": "judge:a", "cost": 0.1}\n'
            '{"step": "judge:b", "cost": 0.2}\n'
            '{"step": "agent_direct:simple", "cost": 0.3}\n',
            encoding="utf-8",
        )
        s = summarize_cost(p)
        assert s["total"] == 0.6
        assert s["steps"]["judge:a"]["count"] == 1
        assert s["steps"]["judge:b"]["count"] == 1
        assert s["steps"]["agent_direct:simple"]["count"] == 1
