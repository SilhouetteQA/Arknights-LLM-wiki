"""统计收集器 — 收集开发过程指标并写入 JSONL"""
import json as _json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone


def _resolve_data_dir() -> str:
    """解析 data/ 目录，尊重环境变量"""
    import pathlib
    data_dir = os.environ.get('ARKNIGHTS_DATA_DIR')
    if data_dir:
        return data_dir
    pkg_dir = pathlib.Path(__file__).resolve().parent.parent.parent
    return str(pkg_dir / 'data')


# 模块级缓存：原始数据总量，首次计算后复用
_raw_data_cache: dict | None = None


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
        return self._write_snapshot()

    def _auto_snapshot_loop(self) -> None:
        while self._stop_event is not None and not self._stop_event.wait(self._auto_interval):
            self._write_snapshot()

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

    def _write_snapshot(self) -> dict:
        snapshot = self._build_snapshot()
        os.makedirs(os.path.dirname(self._jsonl_path), exist_ok=True)
        with open(self._jsonl_path, 'a', encoding='utf-8') as f:
            f.write(_json.dumps(snapshot, ensure_ascii=False) + '\n')
        return snapshot
