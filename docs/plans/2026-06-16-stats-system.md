# Stats System Implementation Plan

> **状态**: 已完成
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement stats/ module with StatsCollector (JSONL write + auto-snapshot + content collection + LLM progress) and StatsReporter (CLI rendering), integrated into seed.py.

**Architecture:** Two classes in `arknights_wiki/stats/` — Collector writes `output/stats.jsonl`, Reporter reads it. Collector uses a daemon thread for 10-minute auto-snapshots. Raw data total chars cached at module level. CLI via `python -m arknights_wiki.stats`.

**Tech Stack:** Python stdlib only — sqlite3, json, pathlib, threading, time, argparse.

> **状态**: 已完成

---

### Task 1: Create stats package skeleton

**Files:**
- Create: `arknights_wiki/stats/__init__.py`
- Create: `arknights_wiki/stats/__main__.py`
- Create: `arknights_wiki/stats/collector.py`
- Create: `arknights_wiki/stats/reporter.py`
- Create: `tests/test_stats_collector.py`
- Create: `tests/test_stats_reporter.py`

- [x] **Step 1: Create empty package files**

`arknights_wiki/stats/__init__.py`:
```python
"""统计系统 — 开发过程追踪"""
from arknights_wiki.stats.collector import StatsCollector
from arknights_wiki.stats.reporter import StatsReporter
```

`arknights_wiki/stats/__main__.py`:
```python
"""统计系统 CLI 入口 — python -m arknights_wiki.stats"""
import sys


def main():
    print("TODO: CLI")


if __name__ == '__main__':
    main()
```

`arknights_wiki/stats/collector.py`:
```python
"""统计收集器 — 收集开发过程指标并写入 JSONL"""
import json as _json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone


class StatsCollector:
    pass
```

`arknights_wiki/stats/reporter.py`:
```python
"""统计报告器 — 读取 JSONL 并渲染终端输出"""
import json as _json
import os


class StatsReporter:
    pass
```

- [x] **Step 2: Create empty test files**

`tests/test_stats_collector.py`:
```python
"""StatsCollector 测试"""
import pytest
```

`tests/test_stats_reporter.py`:
```python
"""StatsReporter 测试"""
import pytest
```

- [x] **Step 3: Verify imports work**

Run: `python -c "from arknights_wiki.stats import StatsCollector, StatsReporter; print('import OK')"`
Expected: `import OK`

- [x] **Step 4: Commit**

```bash
git add arknights_wiki/stats/ tests/test_stats_collector.py tests/test_stats_reporter.py
git commit -m "feat(stats): add package skeleton"
```

---

### Task 2: StatsCollector — init + start/finish lifecycle

**Files:**
- Modify: `arknights_wiki/stats/collector.py`
- Modify: `tests/test_stats_collector.py`

- [x] **Step 1: Write failing tests for lifecycle**

```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorLifecycle -v`
Expected: FAIL — `TypeError: StatsCollector.__init__() got an unexpected keyword argument`

- [x] **Step 3: Implement init + start**

```python
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorLifecycle -v`
Expected: 3 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add StatsCollector lifecycle (init/start/finish)"
```

---

### Task 3: StatsCollector — record_llm_call + record_step

**Files:**
- Modify: `arknights_wiki/stats/collector.py`
- Modify: `tests/test_stats_collector.py`

- [x] **Step 1: Write failing tests**

```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorRecording -v`
Expected: FAIL — `AttributeError: 'StatsCollector' object has no attribute 'record_step'`

- [x] **Step 3: Implement record methods**

Add to `StatsCollector` class:

```python
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorRecording -v`
Expected: 3 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add record_step and record_llm_call with stderr progress"
```

---

### Task 4: StatsCollector — content auto-collection

**Files:**
- Modify: `arknights_wiki/stats/collector.py`
- Modify: `tests/test_stats_collector.py`

- [x] **Step 1: Write failing test for _collect_content**

```python
import sqlite3
from arknights_wiki.store._schema import init_db


class TestStatsCollectorContent:
    def test_collect_content_reads_db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        # Set up DB with known data
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorContent -v`
Expected: FAIL — `AttributeError: 'StatsCollector' object has no attribute '_collect_content'`

- [x] **Step 3: Implement _collect_content**

Add to `StatsCollector` class:

```python
    _PAGE_TYPES = ['character', 'faction', 'region', 'concept',
                   'event', 'storyarc', 'chapter', 'timeline', 'glossary']

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

        # 原始数据总量
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
```

Add module-level `_get_raw_data` stub (will be implemented in Task 5):

```python
# 模块级缓存：原始数据总量，首次计算后复用
_raw_data_cache: dict | None = None


def _get_raw_data() -> dict:
    global _raw_data_cache
    if _raw_data_cache is not None:
        return _raw_data_cache
    # Task 5 实现
    _raw_data_cache = {'stories_count': 0, 'operators_count': 0, 'total_chars': 0}
    return _raw_data_cache
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorContent -v`
Expected: 1 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add _collect_content with dynamic DB queries"
```

---

### Task 5: StatsCollector — raw_data total chars calculation

**Files:**
- Modify: `arknights_wiki/stats/collector.py`
- Modify: `tests/test_stats_collector.py`

- [x] **Step 1: Write failing test for _get_raw_data**

```python
class TestRawData:
    def test_get_raw_data_cached_after_first_call(self, tmp_path, monkeypatch):
        """首次调用计算并缓存，后续调用复用缓存"""
        # Patch resolve_data_path to use tmp_path
        import arknights_wiki.stats.collector as mod
        monkeypatch.setattr(mod, '_raw_data_cache', None)

        # Create a minimal operators.json
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        op_path = data_dir / "operators.json"
        op_path.write_text('{"operators": [{"id": "R001", "name_zh": "阿米娅", "archives": {"档案1": "测试内容ABC"}}]}', encoding='utf-8')

        # Create minimal stories
        stories_dir = data_dir / "stories"
        stories_dir.mkdir()
        s1 = stories_dir / "s1.json"
        s1.write_text('{"id": "s1", "lines": [{"speaker": "A", "text": "hello"}, {"speaker": "B", "text": "world"}]}', encoding='utf-8')

        # Monkeypatch _resolve_data_dir
        monkeypatch.setattr(mod, '_resolve_data_dir', lambda: str(data_dir))

        result = mod._get_raw_data()
        assert result['operators_count'] == 1
        assert result['stories_count'] == 1
        assert result['total_chars'] > 0  # at least archive text + dialogue text

        # Second call should return cached result
        result2 = mod._get_raw_data()
        assert result2 == result
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stats_collector.py::TestRawData -v`
Expected: FAIL — `NameError: name '_resolve_data_dir' is not defined`

- [x] **Step 3: Implement _get_raw_data and _resolve_data_dir**

Replace the stub `_get_raw_data` with full implementation, and add `_resolve_data_dir`:

```python
def _resolve_data_dir() -> str:
    """解析 data/ 目录，尊重环境变量"""
    import pathlib
    data_dir = os.environ.get('ARKNIGHTS_DATA_DIR')
    if data_dir:
        return data_dir
    pkg_dir = pathlib.Path(__file__).resolve().parent.parent.parent
    return str(pkg_dir / 'data')


def _get_raw_data() -> dict:
    """采集原始数据总量，首次计算后缓存。返回 {stories_count, operators_count, total_chars}"""
    global _raw_data_cache
    if _raw_data_cache is not None:
        return _raw_data_cache

    import pathlib
    data_dir = _resolve_data_dir()

    total_chars = 0
    stories_count = 0
    operators_count = 0

    # 统计 operators.json
    op_path = pathlib.Path(data_dir) / 'operators.json'
    if op_path.exists():
        with open(op_path, 'r', encoding='utf-8') as f:
            ops = _json.load(f)
        operators_count = len(ops.get('operators', []))
        for op in ops.get('operators', []):
            for archive_text in op.get('archives', {}).values():
                total_chars += len(archive_text)

    # 统计 stories/
    stories_dir = pathlib.Path(data_dir) / 'stories'
    if stories_dir.exists():
        for fp in stories_dir.glob('**/*.json'):
            stories_count += 1
            with open(fp, 'r', encoding='utf-8') as f:
                story = _json.load(f)
            for line in story.get('lines', []):
                total_chars += len(line.get('text', '') or '')
                total_chars += len(line.get('speaker', '') or '')

    _raw_data_cache = {
        'stories_count': stories_count,
        'operators_count': operators_count,
        'total_chars': total_chars,
    }
    return _raw_data_cache
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stats_collector.py::TestRawData -v`
Expected: 1 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/collector.py tests/test_stats_collector.py
git commit -m "feat(stats): add raw_data total chars calculation with module-level cache"
```

---

### Task 6: StatsCollector — _build_snapshot + _write_snapshot + finish

**Files:**
- Modify: `arknights_wiki/stats/collector.py`
- Modify: `tests/test_stats_collector.py`

- [x] **Step 1: Write failing tests for snapshot write + finish**

```python
import json


class TestStatsCollectorSnapshot:
    def test_finish_writes_jsonl_line(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        jsonl_path = str(tmp_path / "stats.jsonl")
        collector = StatsCollector(db_path, jsonl_path=jsonl_path, auto_snapshot_interval=3600)
        collector.start("seed_m0")
        collector.record_step("step1", 100)
        collector.record_llm_call("deepseek-v4-flash", 100, 50, 1200)
        result = collector.finish()

        # 返回的 dict
        assert result['operation'] == 'seed_m0'
        assert result['duration_ms'] > 0
        assert 'content' in result
        assert 'cost' in result
        assert 'timing' in result

        # JSONL 文件存在
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorSnapshot -v`
Expected: FAIL — Attributes on returned dict missing

- [x] **Step 3: Implement _build_snapshot + _write_snapshot + update finish**

Add `_build_snapshot` method:

```python
    def _build_snapshot(self) -> dict:
        duration_ms = int((time.time() - self._start_time) * 1000)

        # 构建 cost.models
        models = {}
        for model, stats in self._llm_calls.items():
            models[model] = {
                'calls': stats['calls'],
                'tokens_in': stats['tokens_in'],
                'tokens_out': stats['tokens_out'],
            }

        # 计算总成本（RMB）
        total_cost = _estimate_cost(models)

        llm_count = sum(s['calls'] for s in self._llm_calls.values())
        llm_total_ms = sum(s.get('duration_ms', 0) for s in self._llm_calls.values())

        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'operation': self._operation,
            'duration_ms': duration_ms,
            'content': self._collect_content(),
            'cost': {
                'models': models,
                'total_cost_rmb': total_cost,
            },
            'timing': {
                'module_steps': dict(self._steps),
                'llm_calls_count': llm_count,
                'llm_calls_total_ms': llm_total_ms,
            },
        }
```

Add module-level `_estimate_cost`:

```python
# DeepSeek 定价 (RMB/1K tokens)
_COST_RATES = {
    'deepseek-v4-flash':        {'in': 0.001, 'out': 0.004},
    'deepseek-v4-flash-think':  {'in': 0.001, 'out': 0.004},
}


def _estimate_cost(models: dict) -> float:
    """按模型估算成本，未知模型按 0 计"""
    total = 0.0
    for model, stats in models.items():
        rate = _COST_RATES.get(model, {'in': 0, 'out': 0})
        total += (stats['tokens_in'] / 1000) * rate['in']
        total += (stats['tokens_out'] / 1000) * rate['out']
    return round(total, 4)
```

Update `_write_snapshot`:

```python
    def _write_snapshot(self) -> dict:
        snapshot = self._build_snapshot()
        os.makedirs(os.path.dirname(self._jsonl_path), exist_ok=True)
        with open(self._jsonl_path, 'a', encoding='utf-8') as f:
            f.write(_json.dumps(snapshot, ensure_ascii=False) + '\n')
        return snapshot
```

Update `finish`:

```python
    def finish(self) -> dict:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        return self._write_snapshot()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stats_collector.py::TestStatsCollectorSnapshot -v`
Expected: 2 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/collector.py tests/test_stats_collector.py
git commit -m "feat(stats): implement snapshot build/write and finish with cost estimation"
```

---

### Task 7: StatsReporter — read + show_latest

**Files:**
- Modify: `arknights_wiki/stats/reporter.py`
- Modify: `tests/test_stats_reporter.py`

- [x] **Step 1: Write failing tests**

```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stats_reporter.py::TestStatsReporter -v`
Expected: FAIL — `TypeError: StatsReporter.__init__() got an unexpected keyword argument`

- [x] **Step 3: Implement StatsReporter**

```python
"""统计报告器 — 读取 JSONL 并渲染终端输出"""
import json as _json
import os


class StatsReporter:
    def __init__(self, jsonl_path: str):
        self._jsonl_path = jsonl_path

    def _read_all(self) -> list[dict]:
        if not os.path.exists(self._jsonl_path):
            return []
        snapshots = []
        with open(self._jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    snapshots.append(_json.loads(line))
        return snapshots

    def show_latest(self) -> None:
        snapshots = self._read_all()
        if not snapshots:
            print("(无快照)")
            return
        s = snapshots[-1]
        self._print_detail(s)

    def _print_detail(self, s: dict) -> None:
        """打印单个快照详情"""
        content = s['content']
        cost = s['cost']
        timing = s['timing']
        ts = s['timestamp'][:19].replace('T', ' ')

        print(f"操作: {s['operation']}")
        print(f"时间: {ts}  耗时: {s['duration_ms']}ms")
        print()

        print("── 内容 ──")
        entities = content['entities']
        entity_total = sum(entities.values())
        print(f"  实体: {entity_total} (", end='')
        print(', '.join(f"{t}: {c}" for t, c in sorted(entities.items())), end='')
        print(f")  aliases: {content['entity_aliases']}")

        si = content['source_index']
        si_total = sum(si.values())
        print(f"  索引: {si_total} (", end='')
        print(', '.join(f"{t}: {c}" for t, c in sorted(si.items())), end='')
        print(')')

        wp = content['wiki_pages']
        wp_total = sum(
            sum(statuses.values()) for statuses in wp.values()
        )
        print(f"  Wiki页面: {wp_total}")
        for pt, statuses in sorted(wp.items()):
            if any(statuses.values()):
                print(f"    {pt}: draft={statuses['draft']} published={statuses['published']}")

        raw = content['raw_data']
        print(f"  原始数据: {raw.get('operators_count', 0)} 干员, {raw.get('stories_count', 0)} 故事, {raw.get('total_chars', 0):,} 字符")

        print(f"  数据库: {content['db_size_mb']} MB")
        print()

        print("── 成本 ──")
        models = cost['models']
        if models:
            for model, m in models.items():
                print(f"  {model}: {m['calls']}次 {m['tokens_in']}in/{m['tokens_out']}out tokens")
            print(f"  估算成本: ¥{cost['total_cost_rmb']:.4f}")
        else:
            print("  (无LLM调用)")
        print()

        print("── 耗时 ──")
        steps = timing['module_steps']
        if steps:
            for name, ms in steps.items():
                print(f"  {name}: {ms}ms")
        llm_ms = timing.get('llm_calls_total_ms', 0)
        if llm_ms:
            print(f"  LLM总耗时: {llm_ms}ms ({timing['llm_calls_count']}次)")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stats_reporter.py::TestStatsReporter -v`
Expected: 3 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/reporter.py tests/test_stats_reporter.py
git commit -m "feat(stats): add StatsReporter with show_latest detail view"
```

---

### Task 8: StatsReporter — show_last (table format)

**Files:**
- Modify: `arknights_wiki/stats/reporter.py`
- Modify: `tests/test_stats_reporter.py`

- [x] **Step 1: Write failing test**

```python
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
        assert '¥0' in captured or '0.00' in captured
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stats_reporter.py::TestStatsReporter::test_show_last_prints_table -v`
Expected: FAIL — `AttributeError: 'StatsReporter' object has no attribute 'show_last'`

- [x] **Step 3: Implement show_last**

Add to `StatsReporter`:

```python
    def show_last(self, n: int) -> None:
        snapshots = self._read_all()
        if not snapshots:
            print("(无快照)")
            return
        # 表头
        header = f"{'时间':<20} {'操作':<16} {'实体':>5} {'别名':>4} {'索引':>6} {'页面':>4} {'耗时':>8} {'LLM调用':>7} {'成本':>8}"
        print(header)
        print('-' * len(header))
        for s in snapshots[-n:]:
            ts = s['timestamp'][:19].replace('T', ' ')
            op = s['operation'][:16]
            c = s['content']
            entities_total = sum(c['entities'].values())
            aliases = c['entity_aliases']
            si_total = sum(c['source_index'].values())
            wp_total = sum(sum(st.values()) for st in c['wiki_pages'].values())
            dur = f"{s['duration_ms']}ms" if s['duration_ms'] < 10000 else f"{s['duration_ms']/1000:.1f}s"
            llm = f"{s['timing']['llm_calls_count']}次"
            cost = f"¥{s['cost']['total_cost_rmb']:.4f}"
            print(f"{ts:<20} {op:<16} {entities_total:>5} {aliases:>4} {si_total:>6} {wp_total:>4} {dur:>8} {llm:>7} {cost:>8}")
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stats_reporter.py::TestStatsReporter::test_show_last_prints_table -v`
Expected: 1 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/reporter.py tests/test_stats_reporter.py
git commit -m "feat(stats): add show_last table view for history snapshots"
```

---

### Task 9: StatsReporter — show_diff

**Files:**
- Modify: `arknights_wiki/stats/reporter.py`
- Modify: `tests/test_stats_reporter.py`

- [x] **Step 1: Write failing test**

```python
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
            f.write(json.dumps({"operation": "only"}, ensure_ascii=False) + '\n')
        reporter = StatsReporter(jsonl_path)
        reporter.show_diff()
        captured = capsys.readouterr().out
        assert '至少' in captured or '不足' in captured or '两次' in captured
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stats_reporter.py::TestStatsReporter::test_show_diff_compares_last_two tests/test_stats_reporter.py::TestStatsReporter::test_show_diff_needs_two_snapshots -v`
Expected: FAIL — `AttributeError: 'StatsReporter' object has no attribute 'show_diff'`

- [x] **Step 3: Implement show_diff**

Add to `StatsReporter`:

```python
    def show_diff(self) -> None:
        snapshots = self._read_all()
        if len(snapshots) < 2:
            print("(至少需要两次快照才能对比)")
            return
        a, b = snapshots[-2], snapshots[-1]
        print(f"对比: {a['operation']} ({a['timestamp'][:19].replace('T', ' ')}) "
              f"-> {b['operation']} ({b['timestamp'][:19].replace('T', ' ')})")
        print('─' * 60)

        ac, bc = a['content'], b['content']

        # entities
        ae, be = ac['entities'], bc['entities']
        at = sum(ae.values())
        bt = sum(be.values())
        diff_e = bt - at
        sign = f'+{diff_e}' if diff_e > 0 else str(diff_e)
        print(f"entities:       {at} -> {bt} ({sign})")
        for etype in sorted(set(list(ae.keys()) + list(be.keys()))):
            old = ae.get(etype, 0)
            new = be.get(etype, 0)
            if old != new:
                d = new - old
                s = f'+{d}' if d > 0 else str(d)
                print(f"  {etype}: {old} -> {new} ({s})")

        # aliases
        aa = ac['entity_aliases']
        ba = bc['entity_aliases']
        if aa != ba:
            d = ba - aa
            s = f'+{d}' if d > 0 else str(d)
            print(f"aliases:        {aa} -> {ba} ({s})")

        # source_index
        asi = ac['source_index']
        bsi = bc['source_index']
        at_si = sum(asi.values())
        bt_si = sum(bsi.values())
        if at_si != bt_si:
            d = bt_si - at_si
            s = f'+{d}' if d > 0 else str(d)
            print(f"source_index:   {at_si} -> {bt_si} ({s})")

        # wiki_pages
        awp = ac['wiki_pages']
        bwp = bc['wiki_pages']
        at_wp = sum(sum(st.values()) for st in awp.values())
        bt_wp = sum(sum(st.values()) for st in bwp.values())
        if at_wp != bt_wp:
            d = bt_wp - at_wp
            s = f'+{d}' if d > 0 else str(d)
            print(f"wiki_pages:     {at_wp} -> {bt_wp} ({s})")
            for pt in sorted(awp.keys()):
                a_pt = awp.get(pt, {'draft': 0, 'published': 0})
                b_pt = bwp.get(pt, {'draft': 0, 'published': 0})
                if a_pt != b_pt:
                    print(f"  {pt}: draft {a_pt['draft']}->{b_pt['draft']} published {a_pt['published']}->{b_pt['published']}")

        # db_size
        if ac['db_size_mb'] != bc['db_size_mb']:
            d = bc['db_size_mb'] - ac['db_size_mb']
            s = f'+{d:.1f}' if d > 0 else f'{d:.1f}'
            print(f"db_size:        {ac['db_size_mb']}MB -> {bc['db_size_mb']}MB ({s}MB)")

        # timing
        print(f"耗时:           {a['duration_ms']}ms -> {b['duration_ms']}ms")

        # cost
        allm = a['timing']['llm_calls_count']
        bllm = b['timing']['llm_calls_count']
        if allm != bllm:
            print(f"LLM调用:        {allm} -> {bllm}")
        acost = a['cost']['total_cost_rmb']
        bcost = b['cost']['total_cost_rmb']
        if acost != bcost:
            print(f"成本:           ¥{acost:.4f} -> ¥{bcost:.4f}")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stats_reporter.py::TestStatsReporter::test_show_diff_compares_last_two tests/test_stats_reporter.py::TestStatsReporter::test_show_diff_needs_two_snapshots -v`
Expected: 2 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/stats/reporter.py tests/test_stats_reporter.py
git commit -m "feat(stats): add show_diff to compare last two snapshots"
```

---

### Task 10: CLI entry point — python -m arknights_wiki.stats

**Files:**
- Modify: `arknights_wiki/stats/__main__.py`

- [x] **Step 1: Implement __main__.py**

```python
"""统计系统 CLI 入口 — python -m arknights_wiki.stats"""
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description='开发过程统计')
    parser.add_argument('--last', type=int, metavar='N',
                        help='显示最近 N 次快照')
    parser.add_argument('--diff', action='store_true',
                        help='对比最近两次快照')
    parser.add_argument('--jsonl', default=None,
                        help='JSONL 文件路径 (默认: output/stats.jsonl)')
    args = parser.parse_args()

    # 默认 JSONL 路径
    if args.jsonl is None:
        import pathlib
        pkg_dir = pathlib.Path(__file__).resolve().parent.parent.parent
        jsonl_path = str(pkg_dir / 'output' / 'stats.jsonl')
    else:
        jsonl_path = args.jsonl

    from arknights_wiki.stats.reporter import StatsReporter
    reporter = StatsReporter(jsonl_path)

    if args.diff:
        reporter.show_diff()
    elif args.last is not None:
        reporter.show_last(args.last)
    else:
        reporter.show_latest()


if __name__ == '__main__':
    main()
```

- [x] **Step 2: Verify CLI works (no data yet, expect empty)**

Run: `python -m arknights_wiki.stats`
Expected: `(无快照)`

- [x] **Step 3: Verify --help**

Run: `python -m arknights_wiki.stats --help`
Expected: 显示 usage 和 --last, --diff, --jsonl 参数

- [x] **Step 4: Commit**

```bash
git add arknights_wiki/stats/__main__.py
git commit -m "feat(stats): add CLI entry point with --last, --diff, --jsonl"
```

---

### Task 11: Integration — wire StatsCollector into seed.py

**Files:**
- Modify: `arknights_wiki/store/seed.py`

- [x] **Step 1: Update run_seed to use StatsCollector**

Replace `run_seed` function:

```python
def run_seed(db_path: str | None = None) -> dict:
    if db_path is None:
        db_path = os.path.join(resolve_data_path(''), 'arknights_wiki.db')

    print(f'[M0 Seed] 数据库: {db_path}')

    init_db(db_path)

    from arknights_wiki.stats import StatsCollector
    collector = StatsCollector(db_path)
    collector.start('seed_m0')

    er = EntityRepository(db_path)
    sr = SourceIndexRepository(db_path)

    result = {}

    # 1. 干员/faction/region 实体
    print('[M0 Seed] Step 1/3: 干员实体...')
    t0 = time.time()
    ops_path = resolve_data_path('operators.json')
    idmap_path = resolve_config_path('identity_map.json')
    n_entities = er.seed_from_operators(ops_path, idmap_path)
    collector.record_step('seed_entities', int((time.time() - t0) * 1000))
    result['entities'] = n_entities
    print(f'  -> {n_entities} 实体 (character + faction + region)')

    # 2. identity_map -> entity_aliases
    print('[M0 Seed] Step 2/3: 异格/别名映射...')
    t0 = time.time()
    n_aliases = er.seed_identity_map(idmap_path)
    collector.record_step('seed_aliases', int((time.time() - t0) * 1000))
    result['aliases'] = n_aliases
    print(f'  -> {n_aliases} 别名')

    # 3. 干员档案 -> source_index
    print('[M0 Seed] Step 3/3: 干员档案索引...')
    t0 = time.time()
    n_archive = sr.seed_operator_archives(ops_path, idmap_path)
    collector.record_step('seed_archives', int((time.time() - t0) * 1000))
    result['source_index_entries'] = n_archive
    print(f'  -> {n_archive} 档案索引条目')

    result['characters'] = er.count('character')
    result['factions'] = er.count('faction')
    result['regions'] = er.count('region')

    stats = collector.finish()

    print(f'[M0 Seed] 完成!')
    print(f'  character: {result["characters"]}  faction: {result["factions"]}')
    print(f'  region: {result["regions"]}  source_index: {result["source_index_entries"]}')
    print(f'  统计已写入: {collector._jsonl_path}')
    print(f'  总耗时: {stats["duration_ms"]}ms')

    return result
```

需要添加 `import time` 到 seed.py 顶部。

- [x] **Step 2: Verify seed runs with stats integration**

Run: `python -m arknights_wiki.store.seed`
Expected: `[M0 Seed]` 输出 + `统计已写入` + JSONL 文件生成

- [x] **Step 3: Verify JSONL output**

Run: `python -m arknights_wiki.stats`
Expected: 显示最新的 seed_m0 快照详情

- [x] **Step 4: Commit**

```bash
git add arknights_wiki/store/seed.py
git commit -m "feat(stats): integrate StatsCollector into seed.py with per-step timing"
```

---

### Task 12: Final verification + full test run

- [x] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass (existing 119 + new stats tests)

- [x] **Step 2: Run seed and verify stats CLI**

```bash
python -m arknights_wiki.store.seed
python -m arknights_wiki.stats
python -m arknights_wiki.stats --last 3
python -m arknights_wiki.stats --diff
```

- [x] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(stats): final verification, all tests pass"
```
