"""SQL DDL 定义 + 数据库连接管理"""
import sqlite3

DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS entities (
        id              TEXT PRIMARY KEY,
        type            TEXT NOT NULL,
        name_zh         TEXT NOT NULL,
        aliases         TEXT DEFAULT '[]',
        source_data     TEXT,
        lifecycle       TEXT DEFAULT 'active',
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)""",
    """CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name_zh)""",

    """CREATE TABLE IF NOT EXISTS entity_aliases (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        alias_text      TEXT NOT NULL,
        entity_id       TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        alias_type      TEXT DEFAULT 'alt_name',
        UNIQUE(alias_text, entity_id)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_aliases_text ON entity_aliases(alias_text)""",
    """CREATE INDEX IF NOT EXISTS idx_aliases_entity ON entity_aliases(entity_id)""",

    """CREATE TABLE IF NOT EXISTS source_index (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id       TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        source_type     TEXT NOT NULL,
        source_id       TEXT NOT NULL,
        source_location TEXT,
        match_type      TEXT DEFAULT 'exact',
        relevance       REAL DEFAULT 1.0,
        source_text     TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        UNIQUE(entity_id, source_type, source_id, source_location)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_src_entity ON source_index(entity_id)""",
    """CREATE INDEX IF NOT EXISTS idx_src_source ON source_index(source_type, source_id)""",
    """CREATE INDEX IF NOT EXISTS idx_src_match ON source_index(match_type)""",

    """CREATE TABLE IF NOT EXISTS wiki_pages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id       TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        page_type       TEXT NOT NULL,
        version         INTEGER DEFAULT 1,
        content_json    TEXT NOT NULL,
        content_md      TEXT,
        source_refs     TEXT DEFAULT '[]',
        quality_score   REAL,
        status          TEXT DEFAULT 'draft',
        generated_by    TEXT,
        generated_at    TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE INDEX IF NOT EXISTS idx_pages_entity ON wiki_pages(entity_id)""",
    """CREATE INDEX IF NOT EXISTS idx_pages_type ON wiki_pages(page_type)""",
    """CREATE INDEX IF NOT EXISTS idx_pages_status ON wiki_pages(status)""",
    """CREATE INDEX IF NOT EXISTS idx_pages_entity_version ON wiki_pages(entity_id, version DESC)""",
]


def get_connection(db_path: str) -> sqlite3.Connection:
    """获取数据库连接（启用 WAL 模式和外键）"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> sqlite3.Connection:
    """初始化数据库：创建所有表（幂等）"""
    conn = get_connection(db_path)
    for stmt in DDL_STATEMENTS:
        conn.execute(stmt)
    conn.commit()
    return conn
