"""StatsCollector 测试"""
import json
import os
import sqlite3
import time

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


class TestStatsCollectorSnapshot:
    def test_finish_writes_jsonl_line(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        jsonl_path = str(tmp_path / "stats.jsonl")
        collector = StatsCollector(db_path, jsonl_path=jsonl_path, auto_snapshot_interval=3600)
        collector.start("seed_m0")
        collector.record_step("step1", 100)
        collector.record_llm_call("deepseek-v4-flash", 100, 50, 1200)
        time.sleep(0.01)  # 确保 duration_ms > 0
        result = collector.finish()

        # 返回的 dict 包含所有字段
        assert result['operation'] == 'seed_m0'
        assert result['duration_ms'] > 0
        assert 'content' in result
        assert 'cost' in result
        assert 'timing' in result

        # JSONL 文件存在且包含正确数据
        assert os.path.exists(jsonl_path)
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 1
        snapshot = json.loads(lines[0])
        assert snapshot['operation'] == 'seed_m0'
        assert snapshot['cost']['models']['deepseek-v4-flash']['calls'] == 1

    def test_finish_resets_state(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        collector = StatsCollector(db_path, auto_snapshot_interval=3600)
        collector.start("test")
        collector.finish()
        assert collector._thread is None
