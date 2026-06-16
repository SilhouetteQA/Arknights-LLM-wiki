"""统计收集器 — 收集开发过程指标并写入 JSONL"""
import json as _json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone


class StatsCollector:
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

    def start(self, operation: str) -> None:
        self._operation = operation
        self._start_time = time.time()
        self._llm_calls = {}
        self._steps = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._auto_snapshot_loop, daemon=True)
        self._thread.start()

    def record_step(self, step_name: str, duration_ms: int) -> None:
        """占位实现，Task 3 完成"""
        pass

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
