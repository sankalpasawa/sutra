"""SQLite connection + migrations.

WAL mode, foreign keys ON (SQLite defaults them OFF, which quietly makes every
REFERENCES clause decorative), and 0600 on the file.
"""
import os
import sqlite3
from typing import Optional

from .migrations import MIGRATIONS


class Database:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        first_time = path == ":memory:" or not os.path.exists(path)
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, mode=0o700, exist_ok=True)
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
            if first_time:
                os.chmod(path, 0o600)
        self._ensure_migrations_table()

    def _ensure_migrations_table(self):
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )

    def migrate(self) -> int:
        applied = {row["name"] for row in
                   self.conn.execute("SELECT name FROM schema_migrations")}
        count = 0
        for name, sql in MIGRATIONS:
            if name in applied:
                continue
            self.conn.executescript(sql)
            self.conn.execute(
                "INSERT INTO schema_migrations (name, applied_at) "
                "VALUES (?, datetime('now'))", (name,))
            count += 1
        return count

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
