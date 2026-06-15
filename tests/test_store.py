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
