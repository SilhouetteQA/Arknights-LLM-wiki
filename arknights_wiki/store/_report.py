"""M0 实体覆盖报告生成器 — 按章节生成实体覆盖审阅 md"""
import sqlite3
import json
import os
import re
import pathlib


def generate_chapter_reports(db_path: str, output_dir: str):
    """按章节生成实体覆盖报告，每个章节一个 md 文件"""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row

    # 读取 index.json 获取章节列表和节点归属
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    index_path = os.path.join(project_root, 'data', 'index.json')
    with open(index_path, 'r', encoding='utf-8') as f:
        idx = json.load(f)

    # 按章节分组 nodes
    chapters = {}
    for node in idx['nodes']:
        ch = node.get('chapter', '未知')
        if ch not in chapters:
            chapters[ch] = {'nodes': [], 'category': node.get('category', '')}
        chapters[ch]['nodes'].append(node['id'])

    os.makedirs(output_dir, exist_ok=True)

    total_characters = set()
    total_concepts = set()

    for ch, info in sorted(chapters.items()):
        lines = []
        lines.append(f'# 章节: {ch}')
        lines.append('')
        lines.append(f'- 分类: {info["category"]}')
        lines.append(f'- 节点数: {len(info["nodes"])}')
        lines.append('')

        # 角色实体
        lines.append('## 本章出现的角色实体')
        lines.append('')
        lines.append('| 角色名 | entity_id | 对话行数 | 示例对话 |')
        lines.append('|--------|-----------|----------|----------|')

        characters = {}
        for node_id in info['nodes']:
            rows = conn.execute(
                """SELECT si.entity_id, si.source_text, e.name_zh
                   FROM source_index si JOIN entities e ON si.entity_id = e.id
                   WHERE si.source_id = ? AND e.type = 'character' AND si.match_type = 'exact'""",
                (node_id,)
            ).fetchall()
            for row in rows:
                eid = row['entity_id']
                if eid not in characters:
                    characters[eid] = {'name': row['name_zh'], 'count': 0, 'samples': []}
                characters[eid]['count'] += 1
                if len(characters[eid]['samples']) < 2:
                    text = (row['source_text'] or '')[:60].replace('|', '/')
                    characters[eid]['samples'].append(text)

        for eid, cinfo in sorted(characters.items(), key=lambda x: -x[1]['count']):
            total_characters.add(eid)
            sample = '; '.join(cinfo['samples'][:2])
            lines.append(f'| {cinfo["name"]} | {eid} | {cinfo["count"]} | {sample} |')

        if not characters:
            lines.append('| (无角色实体) | - | 0 | - |')

        # 概念实体
        lines.append('')
        lines.append('## 本章出现的概念实体')
        lines.append('')
        lines.append('| 概念 | entity_id | 命中数 |')
        lines.append('|------|-----------|--------|')

        concepts = {}
        for node_id in info['nodes']:
            rows = conn.execute(
                """SELECT si.entity_id, e.name_zh
                   FROM source_index si JOIN entities e ON si.entity_id = e.id
                   WHERE si.source_id = ? AND si.match_type = 'concept_keyword'""",
                (node_id,)
            ).fetchall()
            for row in rows:
                eid = row['entity_id']
                if eid not in concepts:
                    concepts[eid] = {'name': row['name_zh'], 'count': 0}
                concepts[eid]['count'] += 1

        for eid, cinfo in sorted(concepts.items(), key=lambda x: -x[1]['count']):
            total_concepts.add(eid)
            lines.append(f'| {cinfo["name"]} | {eid} | {cinfo["count"]} |')

        if not concepts:
            lines.append('| (无概念实体) | - | 0 |')

        sanitized = re.sub(r'[\\/:*?"<>|]', '_', ch)[:60]
        filepath = os.path.join(output_dir, f'{sanitized}.md')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    conn.close()
    return {
        'total_chapters': len(chapters),
        'total_characters': len(total_characters),
        'total_concepts': len(total_concepts),
    }


def generate_summary_report(db_path: str, output_path: str):
    """生成总体统计摘要"""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row

    lines = []
    lines.append('# M0 种子统计报告')
    lines.append('')

    # 实体数量
    lines.append('## 实体统计')
    lines.append('')
    lines.append('| 类型 | 数量 |')
    lines.append('|------|------|')
    for t in ['character', 'faction', 'region', 'concept', 'chapter']:
        cnt = conn.execute("SELECT COUNT(*) FROM entities WHERE type=?", (t,)).fetchone()[0]
        lines.append(f'| {t} | {cnt} |')

    # 别名统计
    alias_cnt = conn.execute("SELECT COUNT(*) FROM entity_aliases").fetchone()[0]
    lines.append(f'| entity_aliases | {alias_cnt} |')

    lines.append('')

    # source_index 统计
    lines.append('## 源文档索引统计')
    lines.append('')
    lines.append('| match_type | 数量 |')
    lines.append('|------------|------|')
    for mt in ['exact', 'alias', 'concept_keyword']:
        cnt = conn.execute("SELECT COUNT(*) FROM source_index WHERE match_type=?", (mt,)).fetchone()[0]
        lines.append(f'| {mt} | {cnt} |')

    # Top 角色
    lines.append('')
    lines.append('## 对话行数 Top 20 角色')
    lines.append('')
    lines.append('| 排名 | 角色 | entity_id | 索引条目数 |')
    lines.append('|------|------|-----------|-----------|')
    top = conn.execute(
        """SELECT entity_id, COUNT(*) as cnt, e.name_zh
           FROM source_index si JOIN entities e ON si.entity_id = e.id
           WHERE e.type = 'character' AND si.match_type = 'exact'
           GROUP BY entity_id ORDER BY cnt DESC LIMIT 20"""
    ).fetchall()
    for i, row in enumerate(top, 1):
        lines.append(f'| {i} | {row["name_zh"]} | {row["entity_id"]} | {row["cnt"]} |')

    lines.append('')
    lines.append('## 数据库文件大小')
    lines.append(f'')
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    lines.append(f'- {size_mb:.1f} MB')

    conn.close()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.environ.get('ARKNIGHTS_DATA_DIR', os.path.join(project_root, 'data'))
    db_path = os.path.join(data_dir, 'arknights_wiki.db')

    chapter_dir = os.path.join(project_root, 'output', 'm0_entities_by_chapter')
    result = generate_chapter_reports(db_path, chapter_dir)
    print(f'章节报告: {result["total_chapters"]} 章')
    print(f'覆盖角色实体: {result["total_characters"]}')
    print(f'覆盖概念实体: {result["total_concepts"]}')

    summary_path = os.path.join(project_root, 'output', 'm0_seed_summary.md')
    generate_summary_report(db_path, summary_path)
    print(f'总体报告: {summary_path}')
