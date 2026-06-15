"""M0 store 模块测试"""
import sqlite3
import pytest
from arknights_wiki.store._schema import get_connection, init_db


class TestSchema:
    """DDL 和连接管理测试"""

    def test_init_db_creates_tables(self, tmp_path):
        """init_db 应该创建所有必需的表"""
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert 'entities' in table_names
        assert 'entity_aliases' in table_names
        assert 'source_index' in table_names
        assert 'wiki_pages' in table_names

    def test_init_db_idempotent(self, tmp_path):
        """init_db 应该幂等（重复调用不报错）"""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        init_db(db_path)  # should not error

    def test_get_connection_returns_sqlite3_connection(self, tmp_path):
        """get_connection 应该返回可用的 sqlite3.Connection，WAL 和外键已启用"""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        conn = get_connection(db_path)
        assert isinstance(conn, sqlite3.Connection)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == 'wal'
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.row_factory == sqlite3.Row
        conn.execute("SELECT 1")

    def test_entities_columns(self, tmp_path):
        """entities 表应该包含所有必需列"""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        cols = [c[1] for c in sqlite3.connect(db_path).execute("PRAGMA table_info(entities)")]
        assert 'id' in cols
        assert 'type' in cols
        assert 'name_zh' in cols
        assert 'aliases' in cols
        assert 'lifecycle' in cols


import json
from arknights_wiki.store.entity_repository import EntityRepository


class TestEntityRepository:
    @pytest.fixture
    def repo(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        return EntityRepository(db_path)

    def test_insert_and_get(self, repo):
        eid = repo.insert({
            'id': 'character:test',
            'type': 'character',
            'name_zh': '测试干员',
            'source_data': json.dumps({'race': '菲林'})
        })
        assert eid == 'character:test'
        entity = repo.get('character:test')
        assert entity is not None
        assert entity['name_zh'] == '测试干员'
        assert entity['type'] == 'character'

    def test_insert_duplicate_id_raises(self, repo):
        repo.insert({'id': 'character:dup', 'type': 'character', 'name_zh': 'A'})
        with pytest.raises(Exception):
            repo.insert({'id': 'character:dup', 'type': 'character', 'name_zh': 'B'})

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get('character:ghost') is None

    def test_get_by_name(self, repo):
        repo.insert({'id': 'character:c1', 'type': 'character', 'name_zh': '阿米娅'})
        result = repo.get_by_name('阿米娅', 'character')
        assert result is not None
        assert result['name_zh'] == '阿米娅'

    def test_list_by_type(self, repo):
        repo.insert({'id': 'character:c1', 'type': 'character', 'name_zh': 'A'})
        repo.insert({'id': 'character:c2', 'type': 'character', 'name_zh': 'B'})
        repo.insert({'id': 'faction:f1', 'type': 'faction', 'name_zh': '罗德岛'})
        chars = repo.list_by_type('character')
        assert len(chars) == 2
        factions = repo.list_by_type('faction')
        assert len(factions) == 1

    def test_search_by_name(self, repo):
        repo.insert({'id': 'character:a1', 'type': 'character', 'name_zh': '星熊'})
        repo.insert({'id': 'character:a2', 'type': 'character', 'name_zh': '星极'})
        results = repo.search_by_name('星')
        assert len(results) == 2
        results_empty = repo.search_by_name('不存在')
        assert len(results_empty) == 0

    def test_count(self, repo):
        assert repo.count() == 0
        repo.insert({'id': 'character:c1', 'type': 'character', 'name_zh': 'A'})
        assert repo.count() == 1
        assert repo.count('character') == 1
        assert repo.count('faction') == 0

    def test_update(self, repo):
        repo.insert({'id': 'character:t1', 'type': 'character', 'name_zh': '原名'})
        repo.update('character:t1', {'name_zh': '新名', 'lifecycle': 'deprecated'})
        entity = repo.get('character:t1')
        assert entity['name_zh'] == '新名'
        assert entity['lifecycle'] == 'deprecated'

    def test_delete(self, repo):
        repo.insert({'id': 'character:del', 'type': 'character', 'name_zh': '待删'})
        repo.delete('character:del')
        assert repo.get('character:del') is None

    def test_add_alias_and_resolve_name(self, repo):
        repo.insert({'id': 'character:r001', 'type': 'character', 'name_zh': '阿米娅'})
        repo.add_alias('character:r001', '近卫阿米娅', 'form')
        repo.add_alias('character:r001', 'Guard', 'codename')
        assert repo.resolve_name('近卫阿米娅') == 'character:r001'
        assert repo.resolve_name('Guard') == 'character:r001'
        assert repo.resolve_name('阿米娅') == 'character:r001'
        assert repo.resolve_name('博士') is None

    def test_resolve_name_with_type_filter(self, repo):
        repo.insert({'id': 'character:amiya', 'type': 'character', 'name_zh': '阿米娅'})
        repo.insert({'id': 'faction:rhodes', 'type': 'faction', 'name_zh': '罗德岛'})
        result = repo.resolve_name('阿米娅', 'character')
        assert result == 'character:amiya'
        result = repo.resolve_name('阿米娅', 'faction')
        assert result is None

    def test_get_aliases(self, repo):
        repo.insert({'id': 'character:r001', 'type': 'character', 'name_zh': '阿米娅'})
        repo.add_alias('character:r001', 'Guard', 'codename')
        repo.add_alias('character:r001', '近卫阿米娅', 'form')
        aliases = repo.get_aliases('character:r001')
        assert 'Guard' in aliases
        assert '近卫阿米娅' in aliases

    def test_remove_alias(self, repo):
        repo.insert({'id': 'character:r001', 'type': 'character', 'name_zh': '阿米娅'})
        repo.add_alias('character:r001', 'Guard', 'codename')
        repo.remove_alias('character:r001', 'Guard')
        assert repo.resolve_name('Guard') is None


from arknights_wiki.store.source_repository import SourceIndexRepository


class TestSourceIndexRepository:
    @pytest.fixture
    def repo(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        er = EntityRepository(db_path)
        er.insert({'id': 'character:amiya', 'type': 'character', 'name_zh': '阿米娅'})
        er.insert({'id': 'character:chen', 'type': 'character', 'name_zh': '陈'})
        er.insert({'id': 'concept:abyssal', 'type': 'concept', 'name_zh': '深海猎人'})
        return SourceIndexRepository(db_path)

    def test_insert_and_query_by_entity(self, repo):
        repo.insert({
            'entity_id': 'character:amiya', 'source_type': 'story',
            'source_id': '3-1_会合_行动前', 'source_location': '对话行1',
            'match_type': 'exact', 'relevance': 1.0,
            'source_text': '陈长官，究竟发生了什么事？'
        })
        sources = repo.get_sources_for('character:amiya')
        assert len(sources) == 1
        assert sources[0]['source_id'] == '3-1_会合_行动前'
        assert sources[0]['match_type'] == 'exact'

    def test_insert_duplicate_ignored(self, repo):
        entry = {
            'entity_id': 'character:amiya', 'source_type': 'story',
            'source_id': 'node_1', 'source_location': 'loc_1'
        }
        rid1 = repo.insert(entry)
        rid2 = repo.insert(entry)
        assert rid1 == rid2

    def test_query_by_source(self, repo):
        repo.insert({
            'entity_id': 'character:amiya', 'source_type': 'story',
            'source_id': 'node_1', 'source_location': '对话行1'
        })
        repo.insert({
            'entity_id': 'character:chen', 'source_type': 'story',
            'source_id': 'node_1', 'source_location': '对话行2'
        })
        entities = repo.get_entities_for('story', 'node_1')
        assert len(entities) == 2

    def test_filter_by_match_type(self, repo):
        repo.insert({
            'entity_id': 'character:amiya', 'source_type': 'story',
            'source_id': 'n1', 'source_location': 'a',
            'match_type': 'exact', 'relevance': 1.0
        })
        repo.insert({
            'entity_id': 'concept:abyssal', 'source_type': 'story',
            'source_id': 'n1', 'source_location': 'b',
            'match_type': 'concept_keyword', 'relevance': 0.7
        })
        all_sources = repo.get_sources_for('character:amiya')
        assert len(all_sources) == 1
        keyword_only = repo.get_sources_for('concept:abyssal', match_type='concept_keyword')
        assert len(keyword_only) == 1

    def test_delete_by_entity(self, repo):
        repo.insert({
            'entity_id': 'character:amiya', 'source_type': 'story',
            'source_id': 'n1', 'source_location': 'a'
        })
        repo.delete_by_entity('character:amiya')
        assert len(repo.get_sources_for('character:amiya')) == 0

    def test_delete_by_source(self, repo):
        repo.insert({
            'entity_id': 'character:amiya', 'source_type': 'story',
            'source_id': 'n1', 'source_location': 'a'
        })
        repo.delete_by_source('story', 'n1')
        assert len(repo.get_sources_for('character:amiya')) == 0
