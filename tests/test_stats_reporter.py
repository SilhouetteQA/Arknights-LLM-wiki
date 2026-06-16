"""StatsReporter 测试"""
import json
import pytest
from arknights_wiki.stats.reporter import StatsReporter


class TestStatsReporter:
    @pytest.fixture
    def jsonl_path(self, tmp_path):
        return str(tmp_path / "test.jsonl")

    def test_read_empty_returns_empty_list(self, jsonl_path):
        reporter = StatsReporter(jsonl_path)
        assert reporter._read_all() == []

    def test_read_all_parses_lines(self, jsonl_path):
        snapshots = [
            {"timestamp": "2026-06-16T15:00:00+00:00", "operation": "op1", "duration_ms": 100,
             "content": {"entities": {"character": 10}, "entity_aliases": 5,
                         "source_index": {"exact": 100}, "wiki_pages": {}},
             "cost": {"models": {}, "total_cost_rmb": 0},
             "timing": {"module_steps": {}, "llm_calls_count": 0, "llm_calls_total_ms": 0}},
            {"timestamp": "2026-06-16T16:00:00+00:00", "operation": "op2", "duration_ms": 200,
             "content": {"entities": {"character": 12}, "entity_aliases": 6,
                         "source_index": {"exact": 120}, "wiki_pages": {}},
             "cost": {"models": {}, "total_cost_rmb": 0},
             "timing": {"module_steps": {}, "llm_calls_count": 0, "llm_calls_total_ms": 0}},
        ]
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for s in snapshots:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
        reporter = StatsReporter(jsonl_path)
        result = reporter._read_all()
        assert len(result) == 2
        assert result[0]['operation'] == 'op1'

    def test_show_latest_prints_last(self, jsonl_path, capsys):
        snapshots = [
            {"timestamp": "2026-06-16T15:00:00+00:00", "operation": "op1", "duration_ms": 100,
             "content": {"entities": {"character": 10}, "entity_aliases": 5,
                         "source_index": {"exact": 100}, "wiki_pages": {'character': {'draft': 0, 'published': 0}}},
             "cost": {"models": {}, "total_cost_rmb": 0},
             "timing": {"module_steps": {}, "llm_calls_count": 0, "llm_calls_total_ms": 0}},
            {"timestamp": "2026-06-16T16:00:00+00:00", "operation": "op2", "duration_ms": 200,
             "content": {"entities": {"character": 12, "faction": 1}, "entity_aliases": 6,
                         "source_index": {"exact": 120, "alias": 5}, "wiki_pages": {'character': {'draft': 1, 'published': 0}}},
             "cost": {"models": {"deepseek-v4-flash": {"calls": 5, "tokens_in": 1000, "tokens_out": 500}}, "total_cost_rmb": 0.003},
             "timing": {"module_steps": {"gen": 50000}, "llm_calls_count": 5, "llm_calls_total_ms": 10000}},
        ]
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for s in snapshots:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
        reporter = StatsReporter(jsonl_path)
        reporter.show_latest()
        captured = capsys.readouterr().out
        assert 'op2' in captured

    def test_show_last_prints_table(self, jsonl_path, capsys):
        snapshots = [
            {"timestamp": "2026-06-16T15:00:00+00:00", "operation": "seed_m0", "duration_ms": 1847,
             "content": {"entities": {"character": 381}, "entity_aliases": 40,
                         "source_index": {"exact": 3615},
                         "wiki_pages": {'character': {'draft': 0, 'published': 0}}},
             "cost": {"models": {}, "total_cost_rmb": 0},
             "timing": {"module_steps": {}, "llm_calls_count": 0, "llm_calls_total_ms": 0}},
            {"timestamp": "2026-06-16T16:00:00+00:00", "operation": "gen_chapter", "duration_ms": 45200,
             "content": {"entities": {"character": 381, "chapter": 5}, "entity_aliases": 42,
                         "source_index": {"exact": 4120},
                         "wiki_pages": {'chapter': {'draft': 5, 'published': 0}}},
             "cost": {"models": {"deepseek-v4-flash": {"calls": 120, "tokens_in": 60000, "tokens_out": 30000}},
                      "total_cost_rmb": 0.18},
             "timing": {"module_steps": {"llm_generate": 44000}, "llm_calls_count": 120, "llm_calls_total_ms": 43000}},
        ]
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for s in snapshots:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
        reporter = StatsReporter(jsonl_path)
        reporter.show_last(2)
        captured = capsys.readouterr().out
        assert 'seed_m0' in captured
        assert 'gen_chapter' in captured
        assert '1847' in captured

    def test_show_diff_compares_last_two(self, jsonl_path, capsys):
        snapshots = [
            {"timestamp": "2026-06-16T15:00:00+00:00", "operation": "seed_m0", "duration_ms": 1847,
             "content": {"entities": {"character": 381, "faction": 44}, "entity_aliases": 40,
                         "source_index": {"exact": 3615},
                         "wiki_pages": {'character': {'draft': 0, 'published': 0}, 'faction': {'draft': 0, 'published': 0}},
                         "db_size_mb": 2.3,
                         "raw_data": {"stories_count": 1663, "operators_count": 420, "total_chars": 1134547}},
             "cost": {"models": {}, "total_cost_rmb": 0},
             "timing": {"module_steps": {}, "llm_calls_count": 0, "llm_calls_total_ms": 0}},
            {"timestamp": "2026-06-16T16:00:00+00:00", "operation": "gen_chapter", "duration_ms": 45200,
             "content": {"entities": {"character": 381, "faction": 44, "chapter": 5}, "entity_aliases": 42,
                         "source_index": {"exact": 4120},
                         "wiki_pages": {'character': {'draft': 0, 'published': 0}, 'faction': {'draft': 0, 'published': 0}, 'chapter': {'draft': 5, 'published': 0}},
                         "db_size_mb": 2.5,
                         "raw_data": {"stories_count": 1663, "operators_count": 420, "total_chars": 1134547}},
             "cost": {"models": {"deepseek-v4-flash": {"calls": 120, "tokens_in": 60000, "tokens_out": 30000}},
                      "total_cost_rmb": 0.18},
             "timing": {"module_steps": {}, "llm_calls_count": 120, "llm_calls_total_ms": 43000}},
        ]
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for s in snapshots:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
        reporter = StatsReporter(jsonl_path)
        reporter.show_diff()
        captured = capsys.readouterr().out
        assert 'seed_m0' in captured
        assert 'gen_chapter' in captured
        assert '+5' in captured
        assert 'chapter' in captured

    def test_show_diff_needs_two_snapshots(self, jsonl_path, capsys):
        """只有一次快照时提示信息不足"""
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps({"timestamp": "2026-06-16T15:00:00+00:00", "operation": "only", "duration_ms": 100,
             "content": {"entities": {}, "entity_aliases": 0, "source_index": {}, "wiki_pages": {}, "db_size_mb": 0, "raw_data": {"stories_count": 0, "operators_count": 0, "total_chars": 0}},
             "cost": {"models": {}, "total_cost_rmb": 0},
             "timing": {"module_steps": {}, "llm_calls_count": 0, "llm_calls_total_ms": 0}}, ensure_ascii=False) + '\n')
        reporter = StatsReporter(jsonl_path)
        reporter.show_diff()
        captured = capsys.readouterr().out
        assert '至少' in captured or '两次' in captured
