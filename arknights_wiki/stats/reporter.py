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

        raw = content.get('raw_data', {})
        if raw:
            print(f"  原始数据: {raw.get('operators_count', 0)} 干员, {raw.get('stories_count', 0)} 故事, {raw.get('total_chars', 0):,} 字符")

        db_size = content.get('db_size_mb')
        if db_size is not None:
            print(f"  数据库: {db_size} MB")
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
