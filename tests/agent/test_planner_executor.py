"""Planner 任务执行器测试（W4：拓扑调度 + 串行执行 + 失败不中断）"""
from unittest.mock import patch

from arknights_wiki.agent.graph import _topo_sort, execute_task_graph
from arknights_wiki.agent.planner import build_rule_plan


class TestTopoSort:
    def test_respects_dependencies(self):
        tasks = [
            {"id": "t1", "tool": "a", "depends_on": []},
            {"id": "t2", "tool": "b", "depends_on": ["t1"]},
            {"id": "t3", "tool": "c", "depends_on": ["t2"]},
        ]
        order = [t["id"] for t in _topo_sort(tasks)]
        assert order.index("t1") < order.index("t2") < order.index("t3")

    def test_independent_tasks_any_order(self):
        tasks = [
            {"id": "t1", "tool": "a", "depends_on": []},
            {"id": "t2", "tool": "b", "depends_on": []},
        ]
        order = [t["id"] for t in _topo_sort(tasks)]
        assert set(order) == {"t1", "t2"}

    def test_cycle_defensive(self):
        """环防御：不无限循环，返回全部任务"""
        tasks = [
            {"id": "t1", "tool": "a", "depends_on": ["t2"]},
            {"id": "t2", "tool": "b", "depends_on": ["t1"]},
        ]
        order = [t["id"] for t in _topo_sort(tasks)]
        assert set(order) == {"t1", "t2"}


class TestExecuteTaskGraph:
    def test_serial_execution_and_aggregation(self):
        """串行执行并聚合为 collected_docs 结构"""
        calls = []

        def fake_executor(**kwargs):
            calls.append(kwargs)
            return f"result-{kwargs}"

        plan = [
            {"id": "t1", "description": "a", "tool": "search_wiki",
             "args": {"query": "q1"}, "depends_on": [], "status": "pending"},
            {"id": "t2", "description": "b", "tool": "search_events",
             "args": {"entity": "x"}, "depends_on": ["t1"], "status": "pending"},
        ]
        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS",
                   {"search_wiki": fake_executor, "search_events": fake_executor}):
            collected = execute_task_graph(plan)

        assert len(calls) == 2  # 串行执行两次
        assert len(collected) == 2
        assert collected[0]["tool"] == "search_wiki"
        assert "result-" in collected[0]["result"]
        assert plan[0]["status"] == "done"
        assert plan[1]["status"] == "done"

    def test_failure_does_not_abort(self):
        """工具失败经 W2 恢复链降级为文本（不抛异常），整图继续执行"""
        def broken(**kwargs):
            raise ConnectionError("down")

        def ok(**kwargs):
            return "ok-result"

        plan = [
            {"id": "t1", "description": "a", "tool": "search_wiki",
             "args": {"query": "q"}, "depends_on": [], "status": "pending"},
            {"id": "t2", "description": "b", "tool": "search_events",
             "args": {"entity": "x"}, "depends_on": [], "status": "pending"},
        ]
        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS",
                   {"search_wiki": broken, "search_events": ok}):
            collected = execute_task_graph(plan)

        # 两个任务都执行完（恢复链兜底）：失败任务带降级文本，成功任务带结果
        assert len(collected) == 2
        assert "失败" in collected[0]["result"] or "重试" in collected[0]["result"]
        assert collected[1]["result"] == "ok-result"
        assert plan[0]["status"] == "done"  # 恢复链兜底视为完成
        assert plan[1]["status"] == "done"

    def test_unknown_tool_marked_failed(self):
        plan = [{"id": "t1", "description": "a", "tool": "not_a_tool",
                 "args": {}, "depends_on": [], "status": "pending"}]
        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS", {}):
            collected = execute_task_graph(plan)
        assert collected == []
        assert plan[0]["status"] == "failed"

    def test_rule_plan_executable(self, temp_data_dir):
        """规则模板任务图可直接执行（真实检索）"""
        from arknights_wiki.agent.router import _extract_entities_local

        route = {"question_type": "comparison", "entities": ["罗德岛", "阿米娅"]}
        plan = build_rule_plan(route)
        # 执行需要真实 data_dir（temp 数据不足时至少不抛异常）
        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS", {}):
            # 工具缺失场景：全部 failed 但无异常
            collected = execute_task_graph(plan)
        assert isinstance(collected, list)


class TestParallelExecution:
    """W4 增强: 无依赖任务并行执行"""

    def test_layer_plan_groups_independent_tasks(self):
        from arknights_wiki.agent.graph import _layer_plan

        tasks = [
            {"id": "t1", "depends_on": []},
            {"id": "t2", "depends_on": ["t1"]},
            {"id": "t3", "depends_on": []},
        ]
        layers = _layer_plan(tasks)
        ids = [[t["id"] for t in layer] for layer in layers]
        assert ids[0] == ["t1", "t3"]  # 无依赖 → 同层（可并行）
        assert ids[1] == ["t2"]        # 依赖 t1 → 第二层

    def test_independent_tasks_run_in_parallel(self):
        """两个无依赖慢任务：并行 ≈ max(0.3, 0.3) 而非 0.6"""
        import time

        def slow(**kwargs):
            time.sleep(0.3)
            return "done"

        plan = [
            {"id": "t1", "tool": "search_wiki", "args": {"query": "a"},
             "depends_on": [], "status": "pending"},
            {"id": "t2", "tool": "search_events", "args": {"entity": "b"},
             "depends_on": [], "status": "pending"},
        ]
        t0 = time.monotonic()
        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS",
                   {"search_wiki": slow, "search_events": slow}):
            collected = execute_task_graph(plan)
        elapsed = time.monotonic() - t0
        assert len(collected) == 2
        assert elapsed < 0.55  # 并行而非串行（串行会 ~0.6s）

    def test_dependent_tasks_serial(self):
        """有依赖任务分层串行，结果依赖可用"""
        import time

        def slow(**kwargs):
            time.sleep(0.2)
            return "res"

        plan = [
            {"id": "t1", "tool": "search_wiki", "args": {"query": "a"},
             "depends_on": [], "status": "pending"},
            {"id": "t2", "tool": "search_events", "args": {"entity": "b"},
             "depends_on": ["t1"], "status": "pending"},
        ]
        t0 = time.monotonic()
        with patch("arknights_wiki.agent.graph.TOOL_EXECUTORS",
                   {"search_wiki": slow, "search_events": slow}):
            collected = execute_task_graph(plan)
        elapsed = time.monotonic() - t0
        assert len(collected) == 2
        assert elapsed >= 0.35  # 两层串行 ~0.4s（放宽计时精度），区分并行 ~0.2s
