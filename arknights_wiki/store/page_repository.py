"""Wiki 页面存储 Repository"""
import json as _json
from arknights_wiki.store._schema import get_connection


class WikiPageRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    # ── CRUD ──

    def insert(self, page: dict) -> int:
        conn = self._conn()
        conn.execute(
            """INSERT INTO wiki_pages (entity_id, page_type, version, content_json, content_md,
               source_refs, quality_score, status, generated_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (page['entity_id'], page['page_type'],
             page.get('version', 1), page['content_json'],
             page.get('content_md'), page.get('source_refs', '[]'),
             page.get('quality_score'), page.get('status', 'draft'),
             page.get('generated_by'))
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def update(self, page_id: int, updates: dict):
        if not updates:
            return
        allowed = {'content_json', 'content_md', 'source_refs', 'quality_score', 'status'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return
        set_clause = ', '.join(f"{k} = ?" for k in filtered)
        set_clause += ", updated_at = datetime('now')"
        values = list(filtered.values()) + [page_id]
        conn = self._conn()
        conn.execute(f"UPDATE wiki_pages SET {set_clause} WHERE id = ?", values)
        conn.commit()

    def delete(self, page_id: int):
        conn = self._conn()
        conn.execute("DELETE FROM wiki_pages WHERE id = ?", (page_id,))
        conn.commit()

    # ── Query ──

    def get(self, page_id: int) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM wiki_pages WHERE id = ?", (page_id,)).fetchone()
        return dict(row) if row else None

    def get_latest(self, entity_id: str, page_type: str) -> dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM wiki_pages WHERE entity_id = ? AND page_type = ? ORDER BY version DESC LIMIT 1",
            (entity_id, page_type)
        ).fetchone()
        return dict(row) if row else None

    def list_by_entity(self, entity_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM wiki_pages WHERE entity_id = ? ORDER BY version DESC",
            (entity_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_type(self, page_type: str, status: str = 'published') -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM wiki_pages WHERE page_type = ? AND status = ? ORDER BY entity_id",
            (page_type, status)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Lifecycle 原子操作 ──

    def generate(self, entity_id: str, page_type: str, content: dict) -> int:
        latest = self.get_latest(entity_id, page_type)
        version = (latest['version'] + 1) if latest else 1
        return self.insert({
            'entity_id': entity_id, 'page_type': page_type, 'version': version,
            'content_json': _json.dumps(content, ensure_ascii=False),
            'generated_by': 'M0:seed', 'status': 'draft'
        })

    def patch(self, page_id: int, section: str, new_content: str):
        page = self.get(page_id)
        if not page:
            raise ValueError(f'Page {page_id} not found')
        content = _json.loads(page['content_json'])
        content[section] = new_content
        self.update(page_id, {'content_json': _json.dumps(content, ensure_ascii=False)})

    def link(self, source_page_id: int, target_entity_id: str, relation: str):
        page = self.get(source_page_id)
        if not page:
            raise ValueError(f'Page {source_page_id} not found')
        content = _json.loads(page['content_json'])
        links = content.get('_links', [])
        links.append({
            'target': target_entity_id,
            'relation': relation
        })
        content['_links'] = links
        self.update(source_page_id, {'content_json': _json.dumps(content, ensure_ascii=False)})

    def validate(self, page_id: int, score: float):
        self.update(page_id, {'quality_score': score})
