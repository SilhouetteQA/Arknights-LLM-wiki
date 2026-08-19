"""T5: runner 双路径测试（mock agent 与 graph）"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from arknights_wiki.eval import runner


class TestRunDirect:
    @patch("arknights_wiki.eval.runner._log_cost")
    @patch("arknights_wiki.agent.simple_search.simple_search", return_value={"answer": "简单答案"})
    def test_simple_path(self, mock_simple, _log):
        with patch("arknights_wiki.agent.router.route_query", return_value={"complexity": "simple", "entities": ["德克萨斯"]}):
            res = runner.run_direct("德克萨斯在哪家公司？")
        assert res["route"] == "simple"
        assert res["answer"] == "简单答案"
        assert res["latency_ms"] >= 0

    @patch("arknights_wiki.eval.runner._log_cost")
    def test_complex_path(self, _log):
        """默认 react 模式：runner 用 build_agent_graph（2026-08-19 用户决策质量优先）"""
        fake_graph = MagicMock()
        fake_graph.stream.return_value = [
            {"tools": {"collected_docs": [{"tool": "search_events", "args": {"query": "x"}, "result": "r"}]}},
            {"synthesize": {"messages": [{"role": "assistant", "content": "复杂答案"}]}},
        ]
        with patch("arknights_wiki.agent.router.route_query", return_value={"complexity": "complex"}), patch(
            "arknights_wiki.agent.graph.build_agent_graph", return_value=fake_graph
        ):
            res = runner.run_direct("凯尔希与阿米娅的关系？")
        assert res["route"] == "complex"
        assert "复杂答案" in res["answer"]
        assert res["tools_called"] == ["search_events"]

    @patch("arknights_wiki.eval.runner._log_cost")
    def test_complex_path_planner_mode(self, _log, monkeypatch):
        """ARKNIGHTS_AGENT_MODE=planner 时用 build_planner_graph（可选）"""
        monkeypatch.setenv("ARKNIGHTS_AGENT_MODE", "planner")
        fake_graph = MagicMock()
        fake_graph.stream.return_value = [
            {"execute": {"collected_docs": [{"tool": "search_events", "args": {"query": "x"}, "result": "r"}]}},
            {"synthesize": {"messages": [{"role": "assistant", "content": "Planner 答案"}]}},
        ]
        with patch("arknights_wiki.agent.router.route_query", return_value={"complexity": "complex"}), patch(
            "arknights_wiki.agent.graph.build_planner_graph", return_value=fake_graph
        ):
            res = runner.run_direct("凯尔希与阿米娅的关系？")
        assert "Planner 答案" in res["answer"]


def _sse(event: str, data) -> str:
    import json as _json

    payload = data if isinstance(data, str) else _json.dumps(data, ensure_ascii=False)
    return "data: " + _json.dumps({"event": event, "data": payload}, ensure_ascii=False)


class TestRunHttp:
    @patch("arknights_wiki.eval.runner._log_cost")
    def test_sse_parse(self, _log):
        fake_stream = MagicMock()
        fake_stream.__enter__.return_value = fake_stream
        fake_stream.iter_lines.return_value = [
            _sse("route", {"complexity": "simple"}),
            _sse("token", {"text": "你好"}),
            _sse("token", {"text": "世界"}),
            _sse("done", {"total_steps": 0}),
        ]
        with patch("arknights_wiki.eval.runner.httpx.stream", return_value=fake_stream):
            res = runner.run_http("测试", "http://localhost:8000")
        assert res["answer"] == "你好世界"
        assert res["route"] == "simple"

    @patch("arknights_wiki.eval.runner._log_cost")
    def test_http_error(self, _log):
        def boom(*a, **kw):
            raise ConnectionError("refused")

        with patch("arknights_wiki.eval.runner.httpx.stream", side_effect=boom):
            res = runner.run_http("测试", "http://localhost:8000")
        assert "http 调用失败" in res["answer"]
        assert res["route"] == "error"


def _tmp(sub: str) -> Path:
    p = Path(__file__).resolve().parents[2] / "output" / "_tmp_tests" / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


class TestLoaders:
    def test_load_questions(self):
        p = _tmp("load_q") / "q.jsonl"
        p.write_text('{"id": "a", "category": "single_hop"}\n{"id": "b"}\n', encoding="utf-8")
        items = runner._load_questions(p)
        assert len(items) == 2

    def test_existing_ids(self):
        p = _tmp("load_ids") / "r.jsonl"
        p.write_text('{"id": "a", "mode": "direct"}\nbad line\n{"id": "b", "mode": "http"}\n', encoding="utf-8")
        ids = runner._existing_ids(p)
        assert ids == {"a:direct", "b:http"}
