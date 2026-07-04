# run_full_operators.py
"""全量干员档案抓取 + Markdown 生成"""
import sys, asyncio, os, time
sys.stdout.reconfigure(encoding='utf-8')

from arknights_wiki.pipeline.fetch_operators import (
    fetch_operator_list, fetch_all_archives, save_operators_json,
)
from arknights_wiki.pipeline.gen_operators_md import generate_all_operators_markdown
from arknights_wiki.config import DATA_DIR

t0 = time.time()

print('[1/3] 获取干员一览页...')
all_ops = fetch_operator_list()
total = len(all_ops)
print(f'全量: {total} 个')

print(f'[2/3] 并发抓取档案 (15路)...')
all_ops = asyncio.run(fetch_all_archives(all_ops, max_concurrent=15))

has = sum(1 for op in all_ops if op.get('archives'))
empty = total - has
sections = sum(len(op.get('archives', {})) for op in all_ops)
chars = sum(sum(len(v) for v in op.get('archives', {}).values()) for op in all_ops)
elapsed = time.time() - t0

print(f'\n[结果]')
print(f'  有档案: {has}/{total}')
print(f'  无档案: {empty}')
print(f'  总节数: {sections}')
print(f'  总字数: {chars}')
print(f'  耗时: {elapsed:.0f}s')
print(f'  速率: {elapsed/total:.1f}s/干员')

out = os.path.join(DATA_DIR, 'operators.json')
save_operators_json(all_ops, out)
print(f'\n[3/3] JSON: {out} ({os.path.getsize(out)/1024/1024:.1f} MB)')

count = generate_all_operators_markdown(out)
print(f'Markdown: {count} 个文件')

total_elapsed = time.time() - t0
print(f'\n总耗时: {total_elapsed:.0f}s 完成')
