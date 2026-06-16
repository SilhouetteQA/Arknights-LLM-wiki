"""统计收集器 — 收集开发过程指标并写入 JSONL"""
import json as _json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone


# 模块级缓存：原始数据总量，首次计算后复用
_raw_data_cache: dict | None = None


def _get_raw_data() -> dict:
    global _raw_data_cache
    if _raw_data_cache is not None:
        return _raw_data_cache
    # Task 5 实现
    _raw_data_cache = {'stories_count': 0, 'operators_count': 0, 'total_chars': 0}
    return _raw_data_cache


class StatsCollector:
    _PAGE_TYPES = ['character', 'faction', 'region', 'concept',
                   'event', 'storyarc', 'chapter', 'timeline', 'glossary']

    def __init__(self, db_path: str,
                 jsonl_path: str | None = None,
                 auto_snapshot_interval: int = 600):
        self._db_path = db_path
        self._auto_interval = auto_snapshot_interval
        # 默认 JSONL 路径：项目根/output/stats.jsonl
        if jsonl_path is None:
            import pathlib
            pkg_dir = pathlib.Path(__file__).resolve().parent.parent.parent
            jsonl_path = str(pkg_dir / 'output' / 'stats.jsonl')
        self._jsonl_path = jsonl_path
        self._operation: str | None = None
        self._start_time: float | None = None
        self._llm_calls: dict[str, dict] = {}
        self._steps: dict[str, int] = {}
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None

    def _collect_content(self) -> dict:
        conn = sqlite3.connect(f'file:{self._db_path}?mode=ro', uri=True)

        # entities 按 type 分组
        entities = {}
        for row in conn.execute(
            "SELECT type, COUNT(*) FROM entities GROUP BY type"
        ):
            entities[row[0]] = row[1]

        # 别名总数
        aliases_count = conn.execute(
            "SELECT COUNT(*) FROM entity_aliases"
        ).fetchone()[0]

        # source_index 按 match_type 分组
        source_index = {}
        for row in conn.execute(
            "SELECT match_type, COUNT(*) FROM source_index GROUP BY match_type"
        ):
            source_index[row[0]] = row[1]

        # wiki_pages 按 page_type × status 二维分组
        wiki_pages = {pt: {'draft': 0, 'published': 0} for pt in self._PAGE_TYPES}
        for row in conn.execute(
            "SELECT page_type, status, COUNT(*) FROM wiki_pages GROUP BY page_type, status"
        ):
            if row[0] in wiki_pages:
                wiki_pages[row[0]][row[1]] = row[2]

        # 数据库文件大小
        db_size_mb = round(os.path.getsize(self._db_path) / (1024 * 1024), 2)

        # 原始数据总量 (Task 5 实现真实逻辑)
        raw_data = _get_raw_data()

        conn.close()

        return {
            'entities': entities,
            'entity_aliases': aliases_count,
            'source_index': source_index,
            'wiki_pages': wiki_pages,
            'db_size_mb': db_size_mb,
            'raw_data': raw_data,
        }

    def start(self, operation: str) -> None:
        self._operation = operation
        self._start_time = time.time()
        self._llm_calls = {}
        self._steps = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._auto_snapshot_loop, daemon=True)
        self._thread.start()

    def record_step(self, step_name: str, duration_ms: int) -> None:
        self._steps[step_name] = duration_ms

    def record_llm_call(self, model: str, tokens_in: int,
                        tokens_out: int, duration_ms: int) -> None:
        if model not in self._llm_calls:
            self._llm_calls[model] = {
                'calls': 0, 'tokens_in': 0, 'tokens_out': 0, 'duration_ms': 0
            }
        self._llm_calls[model]['calls'] += 1
        self._llm_calls[model]['tokens_in'] += tokens_in
        self._llm_calls[model]['tokens_out'] += tokens_out
        self._llm_calls[model]['duration_ms'] += duration_ms
        total_calls = sum(m['calls'] for m in self._llm_calls.values())
        print(f"[stats] #{total_calls} model={model} {duration_ms/1000:.1f}s",
              file=sys.stderr)

    def finish(self) -> dict:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        return {}

    def _auto_snapshot_loop(self) -> None:
        while self._stop_event is not None and not self._stop_event.wait(self._auto_interval):
            self._write_snapshot()

    def _write_snapshot(self) -> dict:
        return {}
