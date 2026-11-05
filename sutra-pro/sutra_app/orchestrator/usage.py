"""The usage ledger (orchestrator 3.4, 4.1, 6.2; S1-contracts-05, S4-fnodes-07).

    usage = UsageStore(db, chats=chat_store)
    usage.record(usage_in)               # the connector router's `UsageSink`: one row per model request, returns the row id
    usage.record(usage_in, tx=tx)        # the same inside the Projector's transaction (a transaction cannot nest)
    usage.rows(task_id="tsk_...", ...)   # UsageOut[] plus totals over the same filter
    usage.summary("atom")                # groups by dept, fn, provider, day or atom

`UsageIn` is defined once in `sutra_app.connectors.usage` and imported here, and only here. A row is built from it as a library
`usage_record`, checked by the gate and stored once: `INSERT ... ON CONFLICT(task_id, call_ref) WHERE call_ref IS NOT NULL DO
NOTHING` makes a replayed engine line harmless (the same holds for rows without a task, which SQLite's unique index would let
through, so those are looked up first). A new row also keeps the session's provider chip current (`ChatStore.note_provider`, for
successful requests only) and emits `usage.recorded {row, task_total}`.

A reference that points at nothing (a node, session, task or department the database does not know) is stored as NULL and the
original is kept in `detail.unlinked`: the cost of a request is never lost for a dangling link. Stub rows (provider `stub`) are
stored, and counted in totals and groups only when the caller asks for them (`include_stub`).
"""
import json
import logging
import sqlite3
from typing import Any, Literal

from sutra_app.connectors.usage import UsageIn
from sutra_app.library.gate import GATE
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.ids import iso_z, parse_iso_z
from sutra_app.orchestrator.models import UsageOut, UsageTotals
from sutra_app.orchestrator.records import UsageRecord

__all__ = ["UsageStore", "UsageGroup", "SUMMARY_KEYS", "NO_KEY", "parse_since"]

log = logging.getLogger(__name__)
SUMMARY_KEYS = ("dept", "fn", "provider", "day", "atom")
NO_KEY = "(none)"
MAX_ROWS = 500
_COLUMNS = ("id, at, provider, model, purpose, session_id, node_id, task_id, dept_id, fn, step, atom_id, usd, tokens_in, tokens_out, "
            "seconds, ok, how, call_ref, detail_json")
_GROUP_SQL = {"dept": "dept_id", "fn": "fn", "provider": "provider", "day": "strftime('%Y-%m-%d', at, 'unixepoch')", "atom": "atom_id"}
_LINKS = (("session_id", "chat_sessions"), ("node_id", "graph_nodes"), ("task_id", "tasks"), ("dept_id", "departments"))

UsageGroup = dict[str, Any]


def parse_since(text: str | int) -> int:
    """`since` as epoch seconds: whole seconds, or an ISO time like 2026-11-04T10:00:06Z. Anything else is a ValueError."""
    if isinstance(text, int) and not isinstance(text, bool):
        return text
    if isinstance(text, str) and text.isdigit():
        return int(text)
    return parse_iso_z(text)


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _totals(row: sqlite3.Row) -> UsageTotals:
    return UsageTotals(calls=row["calls"], usd=_round(row["usd"]), tokens_in=row["tin"], tokens_out=row["tout"])


def _out(row: sqlite3.Row) -> UsageOut:
    return UsageOut(
        id=row["id"], at=iso_z(row["at"]), provider=row["provider"], model=row["model"], purpose=row["purpose"],
        session_id=row["session_id"], node_id=row["node_id"], task_id=row["task_id"], dept_id=row["dept_id"], fn=row["fn"],
        step=row["step"], atom_id=row["atom_id"], usd=row["usd"], tokens_in=row["tokens_in"], tokens_out=row["tokens_out"],
        seconds=row["seconds"], ok=bool(row["ok"]), how=row["how"], call_ref=row["call_ref"],
        detail=json.loads(row["detail_json"]) if row["detail_json"] else None)


class UsageStore:
    """The server's usage sink and the usage reads."""

    def __init__(self, db: Database, *, chats: Any = None) -> None:
        self.db = db
        self.chats = chats

    # ---- the sink --------------------------------------------------------------------------------------------------

    def record(self, row: UsageIn, *, tx: Tx | None = None) -> int:
        """Store one request's usage and return the ledger id (the id of the stored row when this `call_ref` was seen before).
        Opens its own transaction unless `tx` is given. A row the gate refuses raises `GateError`."""
        if not isinstance(row, UsageIn):
            raise TypeError("UsageStore.record takes a UsageIn")
        if tx is not None:
            return self._record(tx, row)
        with self.db.tx() as own:
            return self._record(own, row)

    def _record(self, tx: Tx, row: UsageIn) -> int:
        conn = tx.conn
        links, unlinked = self._links(conn, row)
        detail = dict(row.detail) if row.detail is not None else None
        if unlinked:
            detail = {**(detail or {}), "unlinked": unlinked}
        payload = dict(
            kind="usage_record", at=tx.now(), provider=row.provider, model=row.model or "", purpose=row.purpose, **links, fn=row.fn or None,
            step=row.step or None, atom_id=row.atom_id or None, usd=row.usd, tokens_in=row.tokens_in, tokens_out=row.tokens_out,
            seconds=row.seconds, ok=row.ok, how=row.how, call_ref=row.call_ref, detail=detail)
        checked = GATE.check("usage_record", payload, ctx=tx.ctx)
        r: UsageRecord = checked.model
        if r.call_ref is not None and r.task_id is None:
            seen = conn.execute("SELECT id FROM usage_ledger WHERE task_id IS NULL AND call_ref = ?", (r.call_ref,)).fetchone()
            if seen is not None:
                return int(seen["id"])
        cursor = conn.execute(
            "INSERT INTO usage_ledger(at, provider, model, purpose, session_id, node_id, task_id, dept_id, fn, step, atom_id, usd, tokens_in,"
            " tokens_out, seconds, ok, how, call_ref, detail_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(task_id, call_ref) WHERE call_ref IS NOT NULL DO NOTHING",
            (r.at, r.provider, r.model, r.purpose, r.session_id, r.node_id, r.task_id, r.dept_id, r.fn, r.step, r.atom_id, r.usd,
             r.tokens_in, r.tokens_out, r.seconds, int(r.ok), r.how, r.call_ref,
             json.dumps(r.detail, separators=(",", ":"), ensure_ascii=False, sort_keys=True) if r.detail is not None else None))
        if cursor.rowcount == 0:
            return int(conn.execute("SELECT id FROM usage_ledger WHERE task_id = ? AND call_ref = ?", (r.task_id, r.call_ref)).fetchone()["id"])
        ledger_id = int(cursor.lastrowid)
        if r.ok and r.session_id is not None and self.chats is not None:
            self.chats.note_provider(tx, r.session_id, r.provider, r.model)
        out = _out(conn.execute(f"SELECT {_COLUMNS} FROM usage_ledger WHERE id = ?", (ledger_id,)).fetchone())
        total = self._task_total(conn, r.task_id)
        tx.emit("usage.recorded", {"row": out.model_dump(mode="json"), "task_total": total.model_dump(mode="json") if total else None})
        return ledger_id

    @staticmethod
    def _links(conn: sqlite3.Connection, row: UsageIn) -> tuple[dict[str, str | None], dict[str, str]]:
        """The row's references that exist, and the ones that do not (stored as NULL, kept in `detail.unlinked`)."""
        found: dict[str, str | None] = {}
        lost: dict[str, str] = {}
        for column, table in _LINKS:
            value = getattr(row, column)
            if value and conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (value,)).fetchone() is not None:
                found[column] = value
            else:
                found[column] = None
                if value:
                    lost[column] = value
        return found, lost

    # ---- reads -----------------------------------------------------------------------------------------------------

    @staticmethod
    def _where(*, task_id: str | None, dept_id: str | None, fn: str | None, since: int | None, include_stub: bool) -> tuple[str, list[Any]]:
        where, args = [], []
        for column, value in (("task_id", task_id), ("dept_id", dept_id), ("fn", fn)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        if since is not None:
            where.append("at >= ?")
            args.append(int(since))
        if not include_stub:
            where.append("provider != 'stub'")
        return (" WHERE " + " AND ".join(where)) if where else "", args

    def rows(self, *, task_id: str | None = None, dept_id: str | None = None, fn: str | None = None, since: int | None = None,
             include_stub: bool = False, after: int = 0, limit: int = 50) -> tuple[list[UsageOut], UsageTotals]:
        """The matching rows in id order (ids above `after`, at most `limit`) and the totals over ALL matching rows, not just the
        page. Stub rows are left out of both unless `include_stub`."""
        conn = self.db.conn()
        where, args = self._where(task_id=task_id, dept_id=dept_id, fn=fn, since=since, include_stub=include_stub)
        totals = conn.execute(
            f"SELECT count(*) AS calls, sum(usd) AS usd, sum(tokens_in) AS tin, sum(tokens_out) AS tout FROM usage_ledger{where}", args).fetchone()
        paged = conn.execute(
            f"SELECT {_COLUMNS} FROM usage_ledger{where}{' AND' if where else ' WHERE'} id > ? ORDER BY id LIMIT ?",
            (*args, max(0, int(after)), max(1, min(int(limit), MAX_ROWS)))).fetchall()
        return [_out(r) for r in paged], _totals(totals)

    def summary(self, by: Literal["dept", "fn", "provider", "day", "atom"], *, include_stub: bool = False, limit: int = MAX_ROWS) -> list[UsageGroup]:
        """Calls and sums per `by`, in key order; a row without a key is grouped under `(none)`. A sum is null when every row's
        part is null. The days are UTC dates."""
        if by not in _GROUP_SQL:
            raise ValueError(f"usage is grouped by {', '.join(SUMMARY_KEYS)}, not {by!r}")
        where, args = self._where(task_id=None, dept_id=None, fn=None, since=None, include_stub=include_stub)
        key = _GROUP_SQL[by]
        found = self.db.conn().execute(
            f"SELECT {key} AS k, count(*) AS calls, sum(usd) AS usd, sum(tokens_in) AS tin, sum(tokens_out) AS tout FROM usage_ledger{where}"
            f" GROUP BY k ORDER BY k LIMIT ?", (*args, max(1, min(int(limit), MAX_ROWS)))).fetchall()
        return [{"key": r["k"] if r["k"] is not None else NO_KEY, "calls": r["calls"], "usd": _round(r["usd"]),
                 "tokens_in": r["tin"], "tokens_out": r["tout"]} for r in found]

    def task_total(self, task_id: str) -> UsageTotals:
        """Calls and sums of one task, stub rows left out."""
        return self._task_total(self.db.conn(), task_id) or UsageTotals()

    @staticmethod
    def _task_total(conn: sqlite3.Connection, task_id: str | None) -> UsageTotals | None:
        if task_id is None:
            return None
        row = conn.execute(
            "SELECT count(*) AS calls, sum(usd) AS usd, sum(tokens_in) AS tin, sum(tokens_out) AS tout FROM usage_ledger"
            " WHERE task_id = ? AND provider != 'stub'", (task_id,)).fetchone()
        return _totals(row)
