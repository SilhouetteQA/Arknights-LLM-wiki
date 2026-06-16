"""StatsCollector 测试"""
import pytest
from arknights_wiki.stats.collector import StatsCollector


class TestStatsCollectorRecording:
    def test_record_step_stores_duration(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        collector = StatsCollector(db_path)
        collector.start("test_op")
        collector.record_step("seed_entities", 500)
        collector.record_step("seed_aliases", 200)
        assert collector._steps == {"seed_entities": 500, "seed_aliases": 200}

    def test_record_llm_call_accumulates(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        collector = StatsCollector(db_path)
        collector.start("test_op")
        collector.record_llm_call("deepseek-v4-flash", 100, 50, 1200)
        collector.record_llm_call("deepseek-v4-flash", 200, 80, 1500)
        m = collector._llm_calls["deepseek-v4-flash"]
        assert m["calls"] == 2
        assert m["tokens_in"] == 300
        assert m["tokens_out"] == 130
        assert m["duration_ms"] == 2700

    def test_record_llm_call_multi_model(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        collector = StatsCollector(db_path)
        collector.start("test_op")
        collector.record_llm_call("deepseek-v4-flash", 100, 50, 1000)
        collector.record_llm_call("deepseek-v4-flash-think", 200, 100, 2000)
        assert set(collector._llm_calls.keys()) == {"deepseek-v4-flash", "deepseek-v4-flash-think"}


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
