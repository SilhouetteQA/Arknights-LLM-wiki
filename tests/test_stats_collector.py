"""StatsCollector 测试"""
import sqlite3
import pytest
from arknights_wiki.stats.collector import StatsCollector
from arknights_wiki.store._schema import init_db


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


class TestStatsCollectorContent:
    def test_collect_content_reads_db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        # 用已知数据初始化数据库
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO entities (id, type, name_zh) VALUES ('c:1', 'character', 'A')")
        conn.execute("INSERT INTO entities (id, type, name_zh) VALUES ('c:2', 'character', 'B')")
        conn.execute("INSERT INTO entities (id, type, name_zh) VALUES ('f:1', 'faction', 'X')")
        conn.execute("INSERT INTO entity_aliases (alias_text, entity_id) VALUES ('AltA', 'c:1')")
        conn.execute("INSERT INTO source_index (entity_id, source_type, source_id, match_type) VALUES ('c:1', 'story', 's1', 'exact')")
        conn.execute("INSERT INTO wiki_pages (entity_id, page_type, content_json, status) VALUES ('c:1', 'character', '{}', 'draft')")
        conn.commit()
        conn.close()

        collector = StatsCollector(db_path)
        collector.start("test")
        content = collector._collect_content()
        assert content['entities'] == {'character': 2, 'faction': 1}
        assert content['entity_aliases'] == 1
        assert content['source_index'] == {'exact': 1}
        assert content['wiki_pages']['character'] == {'draft': 1, 'published': 0}
        assert content['wiki_pages']['faction'] == {'draft': 0, 'published': 0}
        assert 'db_size_mb' in content
