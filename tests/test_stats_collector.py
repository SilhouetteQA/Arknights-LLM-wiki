"""StatsCollector 测试"""
import pytest
from arknights_wiki.stats.collector import StatsCollector


class TestStatsCollectorLifecycle:
    def test_init_sets_defaults(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        collector = StatsCollector(db_path)
        assert collector._operation is None
        assert collector._start_time is None
        assert collector._llm_calls == {}
        assert collector._steps == {}

    def test_start_sets_operation_and_time(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        collector = StatsCollector(db_path)
        collector.start("test_op")
        assert collector._operation == "test_op"
        assert collector._start_time is not None
        assert collector._llm_calls == {}
        assert collector._steps == {}

    def test_start_second_time_resets_state(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        collector = StatsCollector(db_path)
        collector.start("op1")
        collector.record_step("step1", 100)
        collector.start("op2")
        assert collector._operation == "op2"
        assert collector._llm_calls == {}
        assert collector._steps == {}
