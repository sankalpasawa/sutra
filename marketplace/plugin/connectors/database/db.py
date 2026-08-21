"""SQLite connection + migrations.

WAL mode, foreign keys ON (SQLite defaults them OFF, which quietly makes every
REFERENCES clause decorative), 0600 on the file, and ONE CONNECTION PER THREAD.

The per-thread part is not defensive tidiness. `sqlite3.connect()` defaults to
`check_same_thread=True`, so a connection binds to the thread that created it
and raises ProgrammingError anywhere else. The panel serves its connector
endpoints as synchronous `def` handlers -- deliberately, so a blocking GitHub
call cannot stall the event loop -- and FastAPI runs those in a THREADPOOL. A
single shared connection therefore works for the first request and fails as
soon as the pool hands the next one to a different worker:

    /api/connectors -> 200   (first request, thread A)
    /api/connectors -> 500   (later request, thread B)

which is exactly the failure that shipped in 2.112.0. It looked transient
because a restart put a fresh connection on whichever thread asked first, and
it never appeared in tests or the CLI because both are single-threaded.

WAL lets independent connections read and write concurrently, so per-thread
connections are the right shape here rather than a global lock around every
statement -- a lock would also have to cover cursor iteration, which several
callers do lazily.
"""
import os
import sqlite3
import threading
from typing import Optional

from .migrations import MIGRATIONS


class Database:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        #: An in-memory database lives INSIDE its connection, so per-thread
        #: connections would hand each thread its own empty database. Memory
        #: databases therefore share one connection with the thread check
        #: switched off; they are only used by tests, which are single-threaded.
        self._shared = path == ":memory:"
        self._local = threading.local()
        self._shared_conn: Optional[sqlite3.Connection] = None

        first_time = self._shared or not os.path.exists(path)
        if not self._shared:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, mode=0o700, exist_ok=True)

        conn = self._connect()
        if self._shared:
            self._shared_conn = conn
        else:
            self._local.conn = conn
            if first_time:
                os.chmod(path, 0o600)
        self._ensure_migrations_table()

    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None,
                               check_same_thread=not self._shared)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._shared:
            conn.execute("PRAGMA journal_mode = WAL")
            # Without this, two threads writing at once surface as an immediate
            # "database is locked" rather than a short wait.
            conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if self._shared:
            return self._shared_conn
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    # ------------------------------------------------------------------ #
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
        """Closes THIS thread's connection. Other threads keep their own; they
        are released when the process ends, which for a bounded threadpool is
        the only lifetime that matters."""
        conn = self._shared_conn if self._shared else getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            if self._shared:
                self._shared_conn = None
            else:
                self._local.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
