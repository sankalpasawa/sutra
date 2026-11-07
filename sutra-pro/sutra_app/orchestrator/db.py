"""The SQLite database: one connection per thread, explicit transactions, events delivered after COMMIT (orchestrator 3.1).

    db = Database(path, publish)         # publish(list[Event]) is the event bus
    db.migrate()                         # walks PRAGMA user_version over schema.MIGRATIONS, each step in one transaction
    with db.tx() as tx:                  # BEGIN IMMEDIATE ... COMMIT; ROLLBACK on any exception; nested use raises
        tx.conn.execute(...)
        tx.emit("graph.updated", {...})  # handed to publish() only after COMMIT, dropped on ROLLBACK
    db.conn()                            # reads (autocommit) on this thread's connection

The server is the only writer (D16). WAL, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. A database that stays
locked past the busy timeout is `StoreBusy` (503 `store_busy`, failure F10): nothing is half-written. Stores are
synchronous; async code calls them through `run_blocking`.

`StoreContext` is what the gate's cross rules see: `get(family, id)` over the open transaction for the families
`node`, `atom`, `org_chart` and `department`.
"""
import copy
import logging
import sqlite3
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anyio.to_thread

from sutra_app.library import atom as _atom                   # noqa: F401  (importing registers the family)
from sutra_app.library import department as _department      # noqa: F401
from sutra_app.library import node as _node                   # noqa: F401
from sutra_app.library import org_chart as _org_chart         # noqa: F401
from sutra_app.library.base import Value
from sutra_app.library.gate import GateContext
from sutra_app.library.registry import REGISTRY
from sutra_app.orchestrator import schema
from sutra_app.orchestrator.errors import StoreBusy
from sutra_app.orchestrator.ids import Clock, SystemClock, iso_z
from sutra_app.orchestrator.models import Event

__all__ = ["Database", "Tx", "StoreContext", "StoreContextError", "SchemaError", "run_blocking", "BUSY_TIMEOUT_MS"]

log = logging.getLogger(__name__)
BUSY_TIMEOUT_MS = 5000
CHART_IDS = ("chart", "head")


class SchemaError(RuntimeError):
    """The database file cannot be used by this version of the app."""


class StoreContextError(ValueError):
    """A cross rule asked the context for a family it does not hold: a bug in the rule, not bad data."""


def _is_busy(exc: sqlite3.Error) -> bool:
    text = str(exc).lower()
    return isinstance(exc, sqlite3.OperationalError) and ("locked" in text or "busy" in text)


class StoreContext(GateContext):
    """`get(family, id)` for the gate's cross rules, read through the open transaction's connection (so it sees what the
    transaction has written so far). Returns the stored model or None. The families: `node` (graph_nodes), `atom` (a
    `work-atom/0.3` row of atoms), `org_chart` (id `chart`, `head` or a revision number) and `department`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, family: str, id: str) -> Value | None:
        if family == "node":
            sql, args = "SELECT body FROM graph_nodes WHERE id = ?", (id,)
        elif family == "atom":
            sql, args = "SELECT body FROM atoms WHERE id = ? AND schema = 'work-atom/0.3'", (id,)
        elif family == "department":
            sql, args = "SELECT body FROM departments WHERE id = ?", (id,)
        elif family == "org_chart":
            if id in CHART_IDS:
                sql, args = "SELECT body FROM org_charts ORDER BY revision DESC LIMIT 1", ()
            elif isinstance(id, str) and id.isdigit():
                sql, args = "SELECT body FROM org_charts WHERE revision = ?", (int(id),)
            else:
                return None
        else:
            raise StoreContextError(f"the store context holds node, atom, org_chart and department, not {family!r}")
        row = self._conn.execute(sql, args).fetchone()
        return REGISTRY.adapter(family).validate_json(row[0]) if row is not None else None


class Tx:
    """An open write transaction. Events are collected and delivered by `Database.tx` after COMMIT."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self.conn = conn
        self.ctx = StoreContext(conn)
        self._clock = clock
        self._events: list[Event] = []
        self._open = True

    def emit(self, type: str, data: dict[str, Any]) -> None:
        if not self._open:
            raise RuntimeError("the transaction is closed: emit inside the `with db.tx()` block")
        self._events.append(Event(seq=0, at=iso_z(self._clock.now()), type=type, data=copy.deepcopy(data)))

    @property
    def pending(self) -> list[Event]:
        """The events emitted so far (a copy)."""
        return list(self._events)

    def now(self) -> int:
        return self._clock.now()


class Database:
    """One SQLite file. `publish` receives each committed transaction's events as a list, in order, with `seq` 0 (the bus
    assigns the real sequence number)."""

    def __init__(self, path: str | Path, publish: Callable[[list[Event]], None], *, clock: Clock | None = None) -> None:
        self.path = Path(path)
        self._publish = publish
        self._clock = clock or SystemClock()
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._closed = False
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)       # the file holds the owner's work: a folder made here is private, as `Settings.ensure_dirs` makes it

    # ---- connections ----------------------------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        return conn

    def conn(self) -> sqlite3.Connection:
        """This thread's connection (autocommit unless a `tx()` or `read()` block is open on this thread)."""
        if self._closed:
            # on every call, not only when a thread makes its first connection: a pooled worker thread that already has one must not start a
            # statement on it while `close()` is closing it (an access violation on Windows, a segmentation fault on macOS)
            raise SchemaError("the database is closed")
        found = getattr(self._local, "conn", None)
        if found is None:
            with self._lock:
                if self._closed:
                    raise SchemaError("the database is closed")
                found = self._connect()
                self._all.append(found)
            self._local.conn = found
            self._local.depth = 0
        return found

    def close(self) -> None:
        """Close every thread's connection. Later use raises. Safe to call twice. Waits (up to 5 s) for store calls still running on worker threads."""
        with self._lock:
            self._closed = True
        if not _wait_for_store_calls():
            log.warning("closing the database while a store call is still running (waited 5 s)")
        with self._lock:
            conns, self._all = self._all, []
        for conn in conns:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        self._local = threading.local()

    def checkpoint(self) -> None:
        """Fold the WAL into the main file and truncate it (app shutdown)."""
        self.conn().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()

    # ---- transactions ---------------------------------------------------------------------------------------

    @contextmanager
    def tx(self) -> Iterator[Tx]:
        conn = self.conn()
        if getattr(self._local, "depth", 0):
            raise RuntimeError("transactions do not nest: one db.tx() per thread at a time")
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise (StoreBusy() if _is_busy(exc) else exc) from None
        self._local.depth = 1
        tx = Tx(conn, self._clock)
        try:
            yield tx
        except BaseException:
            tx._open = False
            self._rollback(conn)
            raise
        try:
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            tx._open = False
            self._rollback(conn)
            raise (StoreBusy() if _is_busy(exc) else exc) from None
        tx._open = False
        self._local.depth = 0
        if tx._events:
            try:
                self._publish(tx.pending)
            except Exception:                    # the data is committed: a broken subscriber must not undo that
                log.exception("publishing %d event(s) failed", len(tx._events))

    def _rollback(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        self._local.depth = 0

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """One consistent snapshot for several SELECTs (BEGIN ... COMMIT). Inside a `tx()` or another `read()` of this thread
        it just yields the connection."""
        conn = self.conn()
        if getattr(self._local, "depth", 0):
            yield conn
            return
        conn.execute("BEGIN")
        self._local.depth = 1
        try:
            yield conn
        finally:
            self._local.depth = 0
            try:
                conn.execute("COMMIT")
            except sqlite3.Error:
                self._rollback(conn)

    # ---- schema ---------------------------------------------------------------------------------------------

    def version(self) -> int:
        return int(self.conn().execute("PRAGMA user_version").fetchone()[0])

    def migrate(self, migrations: Sequence[schema.Migration] | None = None) -> int:
        """Bring the file to the newest version: step i runs `migrations[i]` and sets `user_version = i + 1` in the same
        transaction, so a failing step leaves the file as it was. Runs again as a no-op. A file from a newer app is a
        `SchemaError`. Returns the version reached."""
        steps = schema.MIGRATIONS if migrations is None else tuple(migrations)
        current = self.version()
        if current > len(steps):
            raise SchemaError(f"the database is version {current}, newer than this app understands ({len(steps)}): update the app")
        for index in range(current, len(steps)):
            with self.tx() as tx:
                if int(tx.conn.execute("PRAGMA user_version").fetchone()[0]) != index:
                    continue                        # another process migrated while this one waited for the lock
                step = steps[index]
                if callable(step):
                    step(tx.conn)
                else:
                    for statement in step:
                        tx.conn.execute(statement)
                tx.conn.execute(f"PRAGMA user_version = {index + 1}")
        return self.version()


_inflight = 0                                    # store calls running on worker threads right now (all databases of this process)
_inflight_idle = threading.Condition()


async def run_blocking(fn: Callable[..., Any], *args: Any) -> Any:
    """Run a synchronous store call on a worker thread (each thread has its own connection). `Database.close` waits for the calls that are
    still running: closing a SQLite connection that another thread is in the middle of a statement on is undefined, and on Windows and on macOS
    it is a crash that takes the whole process down. The call is counted on the worker thread itself, around `fn`: a count kept by the
    awaiting coroutine would leak whenever an event loop ends while a call is pending (a test's loop does), and `close` would then wait for
    nothing and close under a live statement anyway."""
    def counted() -> Any:
        global _inflight
        with _inflight_idle:
            _inflight += 1
        try:
            return fn(*args)
        finally:
            with _inflight_idle:
                _inflight -= 1
                _inflight_idle.notify_all()

    return await anyio.to_thread.run_sync(counted)


def _wait_for_store_calls(seconds: float = 5.0) -> bool:
    """True when no `run_blocking` call is running (after waiting up to `seconds` for the ones that are)."""
    with _inflight_idle:
        return _inflight_idle.wait_for(lambda: _inflight == 0, timeout=seconds)
