"""实体注册表 Repository"""
import json as _json
import re
from arknights_wiki.store._schema import get_connection


def _slugify(text: str) -> str:
    """中文字符保留，西文转 snake_case，用于生成 entity_id slug"""
    text = text.strip().lower()
    text = re.sub(r'[()（）·\s]+', '_', text)
    text = re.sub(r'[^a-z0-9_一-鿿]', '', text)
    return text[:64]


class EntityRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    # ── CRUD ──

    def insert(self, entity: dict) -> str:
        conn = self._conn()
        conn.execute(
            """INSERT INTO entities (id, type, name_zh, aliases, source_data)
               VALUES (?, ?, ?, ?, ?)""",
            (entity['id'], entity['type'], entity['name_zh'],
             entity.get('aliases', '[]'), entity.get('source_data'))
        )
        conn.commit()
        return entity['id']

    def update(self, entity_id: str, updates: dict):
        if not updates:
            return
        allowed = {'name_zh', 'aliases', 'source_data', 'lifecycle'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return
        set_clause = ', '.join(f"{k} = ?" for k in filtered)
        set_clause += ", updated_at = datetime('now')"
        values = list(filtered.values()) + [entity_id]
        conn = self._conn()
        conn.execute(f"UPDATE entities SET {set_clause} WHERE id = ?", values)
        conn.commit()

    def delete(self, entity_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        conn.commit()

    # ── Query ──

    def get(self, entity_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        return dict(row) if row else None

    def get_by_name(self, name_zh: str, type: str) -> dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM entities WHERE name_zh = ? AND type = ?", (name_zh, type)
        ).fetchone()
        return dict(row) if row else None

    def list_by_type(self, type: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM entities WHERE type = ? ORDER BY name_zh", (type,)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_by_name(self, name: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM entities WHERE name_zh LIKE ? ORDER BY name_zh",
            (f"%{name}%",)
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self, type: str | None = None) -> int:
        conn = self._conn()
        if type:
            row = conn.execute("SELECT COUNT(*) FROM entities WHERE type = ?", (type,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
        return row[0]

    # ── 别名管理 ──

    def add_alias(self, entity_id: str, alias: str, alias_type: str = 'alt_name'):
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO entity_aliases (alias_text, entity_id, alias_type) VALUES (?, ?, ?)",
            (alias, entity_id, alias_type)
        )
        conn.commit()

    def remove_alias(self, entity_id: str, alias: str):
        conn = self._conn()
        conn.execute(
            "DELETE FROM entity_aliases WHERE entity_id = ? AND alias_text = ?",
            (entity_id, alias)
        )
        conn.commit()

    def get_aliases(self, entity_id: str) -> list[str]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT alias_text FROM entity_aliases WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        return [r['alias_text'] for r in rows]

    # ── 实体解析 ──

    def resolve_name(self, name: str, type: str = None) -> str | None:
        """给定名称 -> 规范 entity_id。先查别名表，再查实体名。可选类型过滤。"""
        conn = self._conn()
        if type:
            row = conn.execute(
                """SELECT entity_id FROM entity_aliases ea
                   JOIN entities e ON ea.entity_id = e.id
                   WHERE ea.alias_text = ? AND e.type = ?""",
                (name, type)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT entity_id FROM entity_aliases WHERE alias_text = ?", (name,)
            ).fetchone()
        if row:
            return row['entity_id']
        # 查实体的 name_zh
        if type:
            row = conn.execute(
                "SELECT id FROM entities WHERE name_zh = ? AND type = ?", (name, type)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM entities WHERE name_zh = ?", (name,)
            ).fetchone()
        return row['id'] if row else None

    # ── Seed ──

    def seed_from_operators(self, operators_json_path: str) -> int:
        """从 operators.json 提取 character/faction/region 实体"""
        with open(operators_json_path, 'r', encoding='utf-8') as f:
            data = _json.load(f)
        count = 0
        logos = set()
        nations = set()
        birth_places = set()
        teams = set()
        groups = set()
        for op in data['operators']:
            oid = op['id']
            name = op['name_zh']
            if self.get(f'character:{oid}'):
                continue
            self.insert({
                'id': f'character:{oid}',
                'type': 'character',
                'name_zh': name.split('(')[0].split('（')[0].strip(),
                'source_data': _json.dumps({
                    'race': op.get('race', ''), 'nation': op.get('nation', ''),
                    'birth_place': op.get('birth_place', ''), 'sex': op.get('sex', ''),
                    'logo': op.get('logo', ''), 'team': op.get('team', ''),
                    'group': op.get('group', ''),
                }, ensure_ascii=False)
            })
            count += 1
            if op.get('logo'): logos.add(op['logo'])
            if op.get('nation'): nations.add(op['nation'])
            if op.get('birth_place'): birth_places.add(op['birth_place'])
            if op.get('team'): teams.add(op['team'])
            if op.get('group'): groups.add(op['group'])
        # factions from logo
        for name in logos:
            oid = f'faction:{_slugify(name)}'
            if not self.get(oid):
                self.insert({'id': oid, 'type': 'faction', 'name_zh': name,
                             'source_data': _json.dumps({'source': 'operators.json logo'}, ensure_ascii=False)})
                count += 1
        # factions from team/group
        for name in (teams | groups):
            oid = f'faction:{_slugify(name)}'
            if not self.get(oid):
                self.insert({'id': oid, 'type': 'faction', 'name_zh': name,
                             'source_data': _json.dumps({'source': 'operators.json team/group'}, ensure_ascii=False)})
                count += 1
        # regions
        for name in (nations | birth_places):
            oid = f'region:{_slugify(name)}'
            if not self.get(oid):
                self.insert({'id': oid, 'type': 'region', 'name_zh': name,
                             'source_data': _json.dumps({'source': 'operators.json'}, ensure_ascii=False)})
                count += 1
        return count

    def _filter_npc(self, name: str) -> bool:
        """True 表示应过滤（是无名 NPC），False 表示保留"""
        _NPC_PATTERNS = [
            r'\?{2,}', r'？{1,}',
            r'(成员|士兵|队员|干员|佣兵|术师|术士|守卫|卫兵|军官|警员|警察|宪兵|教徒|信使|难民|赏金猎人)$',
            r'(居民|市民|村民|船员|路人|工人|学生|教师|商人|医生|护士|研究员|科学家)$',
            r'(老人|少女|少年|小孩|孩子|男子|女子|妇人|老头|老太太|女孩|男孩|青年|中年|男性|女性)([甲乙丙丁戊己庚辛壬癸A-Za-z0-9]*)$',
            r'^(系统|广播|旁白|报道|记者|播音员|众|合声|合唱|齐声|众人|一同)',
            r'^(带队的|带剑的|老练的|沉默的|高大的|神秘的|年轻的|陌生的|年老的|苍老的|瘦小的|魁梧的)',
            r'罗德岛[^\s]{0,2}(干员|成员)',
            r'整合运动[^\s]{0,2}(成员|士兵|干部|术师)',
            r'近卫局[^\s]{0,2}(成员|队员|干员)',
            r'深池[^\s]{0,2}(士兵|成员)',
            r'萨卡兹[^\s]{0,2}(雇佣兵|士兵|佣兵)',
            r'维多利亚[^\s]{0,2}(士兵|军官)',
            r'哥伦比亚[^\s]{0,2}(士兵|军官)',
            r'无胄盟[^\s]{0,2}(成员)',
            r'莱茵[^\s]{0,2}(防卫科|生命)[^\s]{0,2}(成员)',
            r'赦罪师[^\s]{0,2}(直属)?[^\s]{0,2}(卫兵)',
            r'拓荒(者|队)[^\s]{0,2}(成员)?',
            r'家族[^\s]{0,2}(成员|干部)',
        ]
        for pattern in _NPC_PATTERNS:
            if re.search(pattern, name):
                return True
        return False

    def seed_from_story_dialogue(self, index_json_path: str, stories_dir: str) -> int:
        """从 stories/ 对话提取 story NPC character 实体"""
        import pathlib as _pl
        speakers = set()
        stories_path = _pl.Path(stories_dir)
        for fp in stories_path.glob('**/*.json'):
            with open(fp, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            for line in data.get('lines', []):
                sp = (line.get('speaker') or '').strip()
                if sp and not self._filter_npc(sp):
                    speakers.add(sp)
        count = 0
        for sp in sorted(speakers):
            resolved = self.resolve_name(sp, 'character')
            if resolved:
                continue
            existing = self.get_by_name(sp, 'character')
            if existing:
                continue
            oid = f'character:npc_{_slugify(sp)}'
            if self.get(oid):
                continue
            self.insert({
                'id': oid, 'type': 'character', 'name_zh': sp,
                'source_data': _json.dumps({'source': 'stories dialogue'}, ensure_ascii=False)
            })
            count += 1
        return count

    def seed_identity_map(self, identity_map_path: str) -> int:
        """加载 identity_map.json -> entity_aliases"""
        with open(identity_map_path, 'r', encoding='utf-8') as f:
            data = _json.load(f)
        count = 0
        for alias, entity_id in data.get('mappings', {}).items():
            self.add_alias(entity_id, alias, 'alt_name')
            count += 1
        return count
