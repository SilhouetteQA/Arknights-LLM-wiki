"""源文档双向索引 Repository"""
import json as _json
import pathlib as _pl
from arknights_wiki.store._schema import get_connection
from arknights_wiki.store.entity_repository import EntityRepository


class SourceIndexRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    # ── CRUD ──

    def insert(self, entry: dict) -> int:
        conn = self._conn()
        conn.execute(
            """INSERT OR IGNORE INTO source_index
               (entity_id, source_type, source_id, source_location, match_type, relevance, source_text)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entry['entity_id'], entry['source_type'], entry['source_id'],
             entry.get('source_location'), entry.get('match_type', 'exact'),
             entry.get('relevance', 1.0), entry.get('source_text'))
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM source_index WHERE entity_id=? AND source_type=? AND source_id=? AND source_location=?",
            (entry['entity_id'], entry['source_type'], entry['source_id'],
             entry.get('source_location'))
        ).fetchone()
        return row['id']

    def delete_by_entity(self, entity_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM source_index WHERE entity_id = ?", (entity_id,))
        conn.commit()

    def delete_by_source(self, source_type: str, source_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM source_index WHERE source_type = ? AND source_id = ?",
                     (source_type, source_id))
        conn.commit()

    # ── Query ──

    def get_sources_for(self, entity_id: str, match_type: str = None) -> list[dict]:
        conn = self._conn()
        if match_type:
            rows = conn.execute(
                "SELECT * FROM source_index WHERE entity_id = ? AND match_type = ? ORDER BY relevance DESC",
                (entity_id, match_type)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM source_index WHERE entity_id = ? ORDER BY relevance DESC",
                (entity_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_entities_for(self, source_type: str, source_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM source_index WHERE source_type = ? AND source_id = ?",
            (source_type, source_id)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Seed ──

    def seed_operator_archives(self, operators_json_path: str) -> int:
        """每个干员档案 -> source_index"""
        er = EntityRepository(self.db_path)
        with open(operators_json_path, 'r', encoding='utf-8') as f:
            data = _json.load(f)
        count = 0
        for op in data['operators']:
            oid = op['id']
            entity_id = f'character:{oid}'
            if not er.get(entity_id):
                continue
            archives = op.get('archives', {})
            for section_name, section_text in archives.items():
                if not section_text.strip():
                    continue
                text_preview = section_text[:2000]
                self.insert({
                    'entity_id': entity_id, 'source_type': 'operator_archive',
                    'source_id': oid, 'source_location': section_name,
                    'match_type': 'exact', 'relevance': 1.0,
                    'source_text': text_preview
                })
                count += 1
        return count

    def seed_story_dialogue(self, index_json_path: str, stories_dir: str) -> int:
        """故事对话行 -> source_index（仅已有 entity 的角色）"""
        er = EntityRepository(self.db_path)
        stories_path = _pl.Path(stories_dir)
        count = 0
        for fp in stories_path.glob('**/*.json'):
            with open(fp, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            source_id = data.get('id', fp.stem)
            for i, line in enumerate(data.get('lines', [])):
                sp = (line.get('speaker') or '').strip()
                if not sp:
                    continue
                entity_id = er.resolve_name(sp, 'character')
                if not entity_id:
                    # fallback: direct name_zh lookup
                    entity = er.get_by_name(sp, 'character')
                    entity_id = entity['id'] if entity else None
                if not entity_id:
                    continue
                text = line.get('text', '') or ''
                text_preview = text[:1000]
                self.insert({
                    'entity_id': entity_id, 'source_type': 'story',
                    'source_id': source_id, 'source_location': f'对话行{i}',
                    'match_type': 'exact', 'relevance': 1.0,
                    'source_text': f'[{sp}]: {text_preview}'
                })
                count += 1
        return count

    def seed_concept_keywords(self, concept_keywords_path: str) -> int:
        """概念关键词 -> 扫描 source_index 中已有 source_text，建立概念级索引"""
        er = EntityRepository(self.db_path)
        with open(concept_keywords_path, 'r', encoding='utf-8') as f:
            config = _json.load(f)
        count = 0
        for item in config.get('keywords', []):
            entity_id = item['entity_id']
            if not er.get(entity_id):
                er.insert({
                    'id': entity_id, 'type': 'concept',
                    'name_zh': item['display_name'],
                    'source_data': _json.dumps({'keywords': item['keywords']}, ensure_ascii=False)
                })
            kw_list = item['keywords']
            conn = self._conn()
            rows = conn.execute("SELECT id, source_type, source_id, source_text FROM source_index").fetchall()
            for row in rows:
                text = row['source_text'] or ''
                matched_kw = None
                for kw in kw_list:
                    if kw in text:
                        matched_kw = kw
                        break
                if matched_kw:
                    self.insert({
                        'entity_id': entity_id,
                        'source_type': row['source_type'],
                        'source_id': row['source_id'],
                        'source_location': f'concept:{matched_kw}',
                        'match_type': 'concept_keyword',
                        'relevance': 0.7,
                        'source_text': text[:1000]
                    })
                    count += 1
        return count
