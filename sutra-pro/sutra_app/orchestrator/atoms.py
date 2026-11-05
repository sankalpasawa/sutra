"""Atoms and the Atom log (orchestrator 3.4, 4.1, 5.6, 6.2; S2-models-07, S2-models-10, S4-fnodes-08, S4-fnodes-09).

    atoms = AtomStore(db, chats=chat_store, graph=graph_store)
    atoms.apply_transition(tx, node, run_atom_event, run_id=..., task_id=...)   # the Projector's entry for an `atom` line
    atoms.upsert(tx, checked_atom, ...)          # the one writer of `atoms`; computes `display`
    atoms.append_ledger(tx, checked_row)         # the one writer of `atom_ledger`; one row per atom, ever
    atoms.get(id) / atoms.find(...) / atoms.log(...)     # AtomOut, AtomOut[], AtomLogRow[]

Two schemas share the table. `work-atom/0.3` is a function node's atom (the library `Atom`, id `a-<sid>-<nn>`); `atom/1` is a
builder's J2 view (the library `AtomView`, stored under the key `<run_id>:<J2 id>` because J2 restarts at W-1 in every run).
`display` is one of open, verify_failed, closed, refused, abandoned: `atom_display_state(body)` for work atoms (a stored
`abandoned` with the code `verify_failed` shows `verify_failed`), the view's own status for `atom/1`. It is computed here from
the checked body and never taken from the event.

`apply_transition` is all-or-nothing and never raises for bad event data: it returns an `AtomResult` whose status is
`applied`, `unchanged` (a replay) or `rejected` (with the reason, for the Projector to note). Rules: the body passes the gate;
only forward moves (work atoms: open to open with the same or a higher attempt, open to closed or abandoned; closed, abandoned
and refused are final; `atom/1`: open, then verify_failed, then closed or abandoned); one open work atom per node; the ledger
row is appended once; a work atom's card is posted once to the node's own session; `open_atom` and `atom_count` are written to
a function node in the same transaction; `atom.updated` is emitted.
"""
import json
import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from sutra_app.library.atom import (
    Atom, AtomError, AtomView, LedgerRow, atom_display_state, ledger_row, ledger_row_from_view,
)
from sutra_app.library.gate import GATE, Checked, GateError
from sutra_app.library.node import Node
from sutra_app.library.types import FUNCTIONS
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import AtomCard, AtomLogRow, AtomOut, RunAtom, UsageTotals

__all__ = ["AtomStore", "AtomResult", "DISPLAY_WORDS", "ATOMS_LIMIT"]

log = logging.getLogger(__name__)
DISPLAY_WORDS = ("open", "verify_failed", "closed", "refused", "abandoned")
ATOMS_LIMIT = 500
_COLUMNS = "id, schema, node_id, task_id, state, display, attempt, goal, body, ts_open, ts_closed"
_FITS = {
    "opened": lambda a: a.state == "open" and a.attempt == 0,
    "verify_failed": lambda a: a.state == "open" and a.attempt >= 1,
    "closed": lambda a: a.state == "closed",
    "abandoned": lambda a: a.state == "abandoned",
    "refused": lambda a: True,
}
_VIEW_RANK = {"open": 0, "verify_failed": 1, "closed": 2, "abandoned": 2}


@dataclass(frozen=True)
class AtomResult:
    """What `apply_transition` did. `status`: applied (rows written), unchanged (the same body again: a replay) or rejected
    (nothing written; `reason` says why, for a note in the node's session)."""

    status: Literal["applied", "unchanged", "rejected"]
    atom_id: str
    reason: str = ""
    display: str | None = None
    outcome: str | None = None
    ledgered: bool = False
    card_message_id: int | None = None

    @property
    def applied(self) -> bool:
        return self.status == "applied"


def _marks(count: int) -> str:
    return ",".join("?" * count)


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _atom_usage(conn: sqlite3.Connection, atom_ids: Sequence[str]) -> dict[str, UsageTotals]:
    """atom id -> calls and sums of its ledger rows, stub rows left out; a part is null when every row's part is null."""
    out: dict[str, UsageTotals] = {}
    if atom_ids:
        for r in conn.execute(
                "SELECT atom_id, count(*) AS calls, sum(usd) AS usd, sum(tokens_in) AS tin, sum(tokens_out) AS tout FROM usage_ledger"
                " WHERE provider != 'stub' AND atom_id IN (SELECT value FROM json_each(?)) GROUP BY atom_id", (json.dumps(list(atom_ids)),)):
            out[r["atom_id"]] = UsageTotals(calls=r["calls"], usd=_round(r["usd"]), tokens_in=r["tin"], tokens_out=r["tout"])
    return out


def _atom_outs(conn: sqlite3.Connection, rows: Sequence[sqlite3.Row]) -> list[AtomOut]:
    usage = _atom_usage(conn, [r["id"] for r in rows])
    return [AtomOut(
        id=r["id"], schema=r["schema"], node_id=r["node_id"], task_id=r["task_id"], state=r["display"], goal=r["goal"],
        attempt=r["attempt"], ts_open=iso_z(r["ts_open"]), ts_closed=iso_z(r["ts_closed"]) if r["ts_closed"] is not None else None,
        body=json.loads(r["body"]), usage=usage.get(r["id"], UsageTotals())) for r in rows]


class AtomStore:
    """`atoms` and `atom_ledger`. `chats` and `graph` are only needed by `apply_transition` (the card and the node body)."""

    def __init__(self, db: Database, *, chats: Any = None, graph: Any = None) -> None:
        self.db = db
        self.chats = chats
        self.graph = graph

    # ---- reads -----------------------------------------------------------------------------------------------------

    def get(self, atom_id: str) -> AtomOut:
        conn = self.db.conn()
        row = conn.execute(f"SELECT {_COLUMNS} FROM atoms WHERE id = ?", (atom_id,)).fetchone()
        if row is None:
            raise NotFound("that atom")
        return _atom_outs(conn, [row])[0]

    def find(self, *, node_id: str | None = None, task_id: str | None = None, status: str | None = None, limit: int = 50,
             offset: int = 0) -> list[AtomOut]:
        """Newest first (`ts_open`, then insertion). `status` is a display word."""
        if status is not None and status not in DISPLAY_WORDS:
            raise ValueError(f"an atom status is one of {', '.join(DISPLAY_WORDS)}, not {status!r}")
        where, args = [], []
        for column, value in (("node_id", node_id), ("task_id", task_id), ("display", status)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        sql = (f"SELECT {_COLUMNS} FROM atoms" + (f" WHERE {' AND '.join(where)}" if where else "")
               + " ORDER BY ts_open DESC, rowid DESC LIMIT ? OFFSET ?")
        conn = self.db.conn()
        rows = conn.execute(sql, (*args, max(1, min(int(limit), ATOMS_LIMIT)), max(0, int(offset)))).fetchall()
        return _atom_outs(conn, rows)

    def log(self, *, node_id: str | None = None, after: int = 0, limit: int = 50) -> list[AtomLogRow]:
        """The Atom log in `seq` order, rows with a `seq` above `after`."""
        where, args = ["seq > ?"], [max(0, int(after))]
        if node_id is not None:
            where.append("node_id = ?")
            args.append(node_id)
        rows = self.db.conn().execute(
            f"SELECT seq, atom_id, node_id, status, body, ts FROM atom_ledger WHERE {' AND '.join(where)} ORDER BY seq LIMIT ?",
            (*args, max(1, min(int(limit), ATOMS_LIMIT)))).fetchall()
        return [AtomLogRow(seq=r["seq"], atom_id=r["atom_id"], node_id=r["node_id"], status=r["status"], body=json.loads(r["body"]),
                           ts=iso_z(r["ts"])) for r in rows]

    # ---- the two writers -------------------------------------------------------------------------------------------

    def upsert(self, tx: Tx, atom: Checked, *, key: str | None = None, node_id: str | None = None, task_id: str | None = None,
               department_id: str | None = None, ts_open: int | None = None, ts_closed: int | None = None,
               attempt: int | None = None) -> str:
        """Insert or update the row of a checked atom and return its stored key. A `work-atom/0.3` (`Checked[Atom]`) is keyed by
        its own id; an `atom/1` view (`Checked[AtomView]`) needs `key` (`<run_id>:<J2 id>`), `node_id` and `ts_open`. The keyword
        values are the server's and win over the body's. `display` is computed from the checked body. The node, task and
        department rows must exist (foreign keys); one open work atom per node is the unique index's rule."""
        if not isinstance(atom, Checked):
            raise TypeError("AtomStore.upsert takes a Checked atom or atom_view from GATE.check")
        model = atom.model
        if atom.family == "atom":
            schema, state, display = "work-atom/0.3", model.state, atom_display_state(model)
            stored_key, goal = model.id, model.goal
            node_id = node_id or model.node_id
            task_id = task_id if task_id is not None else model.task_id
            department_id = department_id if department_id is not None else model.department_id
            ts_open = model.ts_open if ts_open is None else ts_open
            ts_closed = model.ts_closed if ts_closed is None else ts_closed
            attempt = model.attempt if attempt is None else attempt
        elif atom.family == "atom_view":
            schema, state = "atom/1", model.status
            display = state
            if key is None or node_id is None or ts_open is None:
                raise ValueError("an atom/1 view is stored with its key '<run_id>:<id>', its node and its opening time")
            stored_key, goal = key, model.goal or model.name
            attempt = (model.attempt or 0) if attempt is None else attempt
        else:
            raise TypeError(f"the atoms table holds atom and atom_view records, not {atom.family!r}")
        tx.conn.execute(
            "INSERT INTO atoms(id, schema, node_id, department_id, task_id, state, display, attempt, goal, body, sha256, ts_open, ts_closed)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state = excluded.state, display = excluded.display,"
            " attempt = excluded.attempt, goal = excluded.goal, body = excluded.body, sha256 = excluded.sha256,"
            " ts_closed = excluded.ts_closed, department_id = excluded.department_id, task_id = excluded.task_id",
            (stored_key, schema, node_id, department_id, task_id, state, display, attempt, goal, atom.json, atom.sha256, ts_open, ts_closed))
        return stored_key

    def append_ledger(self, tx: Tx, row: Checked[LedgerRow], *, key: str | None = None) -> bool:
        """Append one row to the Atom log; True when it was added, False when the atom has a row already (the log is
        append-only and holds one row per atom). `key` is the atom's stored key (default: the row's own atom id)."""
        if not isinstance(row, Checked) or row.family != "atom_ledger_row":
            raise TypeError("AtomStore.append_ledger takes a Checked atom_ledger_row from GATE.check")
        model: LedgerRow = row.model
        cursor = tx.conn.execute(
            "INSERT INTO atom_ledger(atom_id, node_id, status, body, ts) VALUES (?,?,?,?,?) ON CONFLICT(atom_id) DO NOTHING",
            (key or model.atom_id, model.node_id, model.status, row.json, model.ts))
        return cursor.rowcount == 1

    # ---- the Projector's entry -------------------------------------------------------------------------------------

    def apply_transition(self, tx: Tx, node: Node | str, event: RunAtom, *, run_id: str, task_id: str | None = None) -> AtomResult:
        """Project one `atom` event of `node` (the node or its id) in the Projector's transaction. `run_id` makes the key of an
        `atom/1` view; `task_id` (the task the Projector is applying) and the node's department are the server's facts and
        replace what the body says."""
        node_id = node if isinstance(node, str) else node.id
        stored = tx.ctx.get("node", node_id)
        if stored is None:
            return AtomResult("rejected", event.atom.id, f"node {node_id} does not exist")
        if event.node != node_id:
            return AtomResult("rejected", event.atom.id, f"the event is for node {event.node}, not {node_id}")
        if event.atom.schema_ == "atom/1":
            return self._apply_view(tx, stored, event, run_id, task_id)
        return self._apply_function_atom(tx, stored, event, run_id, task_id)

    def _apply_function_atom(self, tx: Tx, node: Node, event: RunAtom, run_id: str, task_id: str | None) -> AtomResult:
        ea = event.atom
        body = dict(ea.body)
        body["department_id"] = node.department_id if node.department_id is not None else body.get("department_id")
        if task_id is not None:
            body["task_id"] = task_id
        if body.get("session_id") is None and "-" in ea.id:
            body["session_id"] = ea.id.split("-")[1]
        try:
            checked = GATE.check("atom", body, ctx=tx.ctx)
        except GateError as exc:
            return AtomResult("rejected", ea.id, f"the atom body was refused: {exc}")
        atom: Atom = checked.model
        problem = self._event_problem(atom, event, node)
        if problem is not None:
            return AtomResult("rejected", atom.id, problem)
        old = tx.conn.execute("SELECT sha256 FROM atoms WHERE id = ?", (atom.id,)).fetchone()
        if old is not None and old["sha256"] == checked.sha256:
            return AtomResult("unchanged", atom.id, display=atom_display_state(atom))
        problem = self._move_problem(tx.conn, atom)
        if problem is not None:
            return AtomResult("rejected", atom.id, problem)
        display = atom_display_state(atom)
        outcome = event.outcome or self._outcome_of(atom, display)
        ledger_checked: Checked | None = None
        if display != "open":
            try:
                payload = event.ledger if event.ledger is not None else ledger_row(atom)
                ledger_checked = GATE.check("atom_ledger_row", payload)
            except (GateError, AtomError, ValidationError) as exc:
                return AtomResult("rejected", atom.id, f"the ledger row was refused: {exc}")
            row: LedgerRow = ledger_checked.model
            if row.atom_id != atom.id or row.status != display or row.node_id != node.id:
                return AtomResult("rejected", atom.id, f"the ledger row ({row.atom_id}, {row.status}) does not match the atom ({atom.id}, {display})")
        elif event.ledger is not None:
            return AtomResult("rejected", atom.id, "an atom that is still open has no ledger row")
        self.upsert(tx, checked, task_id=task_id if task_id is not None else atom.task_id)
        ledgered = self.append_ledger(tx, ledger_checked) if ledger_checked is not None else False
        card_id = self._post_card(tx, node, event, atom, outcome, run_id, task_id)
        self._refresh_node(tx, node)
        self._emit(tx, atom.id, node.id, outcome, display)
        return AtomResult("applied", atom.id, display=display, outcome=outcome, ledgered=ledgered, card_message_id=card_id)

    @staticmethod
    def _event_problem(atom: Atom, event: RunAtom, node: Node) -> str | None:
        """Why the event and its body disagree, or None. Reads nothing."""
        ea = event.atom
        if atom.id != ea.id:
            return f"the event names atom {ea.id} but its body is atom {atom.id}"
        if atom.node_id != node.id:
            return f"atom {atom.id} belongs to node {atom.node_id}, not to {node.id}"
        if atom.state != ea.status or atom.attempt != ea.attempt:
            return f"the event says {ea.status} at attempt {ea.attempt}, the body says {atom.state} at attempt {atom.attempt}"
        if event.outcome is not None and not _FITS[event.outcome](atom):
            return f"outcome {event.outcome} does not fit an atom that is {atom.state} at attempt {atom.attempt}"
        return None

    @staticmethod
    def _move_problem(conn: sqlite3.Connection, atom: Atom) -> str | None:
        """Why the stored rows do not allow this move (not forward, not open, a second open atom), or None."""
        old = conn.execute("SELECT schema, node_id, state, attempt FROM atoms WHERE id = ?", (atom.id,)).fetchone()
        if old is not None:
            if old["schema"] != "work-atom/0.3" or old["node_id"] != atom.node_id:
                return f"atom {atom.id} is stored for another node or schema"
            if old["state"] != "open":
                return f"atom {atom.id} is {old['state']} and final: no later move is stored"
            if atom.attempt < old["attempt"]:
                return f"atom {atom.id} went from attempt {old['attempt']} back to {atom.attempt}"
        if atom.state == "open":
            other = conn.execute(
                "SELECT id FROM atoms WHERE node_id = ? AND state = 'open' AND schema = 'work-atom/0.3' AND id != ?", (atom.node_id, atom.id)).fetchone()
            if other is not None:
                return f"node {atom.node_id} already has the open atom {other['id']}: a node holds one open atom"
        return None

    @staticmethod
    def _outcome_of(atom: Atom, display: str) -> str:
        if atom.state == "refused":
            return "refused"
        if atom.state == "open":
            return "verify_failed" if atom.attempt >= 1 else "opened"
        return "closed" if display == "closed" else "abandoned"

    def _post_card(self, tx: Tx, node: Node, event: RunAtom, atom: Atom, outcome: str, run_id: str, task_id: str | None) -> int | None:
        """The transition's card, once, in the node's own session (`src_ref` makes a replay a no-op)."""
        if event.card is None or node.chat_session_id is None:
            return None
        if self.chats is None:
            raise RuntimeError("AtomStore needs a ChatStore to post an atom card")
        try:
            card = AtomCard(type="atom", atom_id=atom.id, outcome=outcome, label=event.card.get("label", ""), goal=event.card.get("goal", ""),
                            rows=[{"label": r["label"], "text": r["text"]} for r in event.card.get("rows", [])])
        except (ValidationError, KeyError, TypeError) as exc:
            log.warning("atom %s: the shipped card is not an atom card (%s); no card posted", atom.id, exc)
            return None
        message = dict(
            kind="card", session_id=node.chat_session_id, role="agent", who=node.kind if node.kind in FUNCTIONS else node.id,
            card=card.model_dump(mode="json"), task_id=task_id, src_ref=f"{run_id}#atom:{atom.id}:{outcome}:{atom.attempt}", at=tx.now())
        try:
            checked = GATE.check("chat_message", message, ctx=tx.ctx)
        except GateError as exc:
            log.warning("atom %s: the card message was refused (%s); no card posted", atom.id, exc)
            return None
        posted = self.chats.post(tx, node.chat_session_id, checked)
        return posted.id if posted is not None else None

    def _apply_view(self, tx: Tx, node: Node, event: RunAtom, run_id: str, task_id: str | None) -> AtomResult:
        ea = event.atom
        key = f"{run_id}:{ea.id}"
        try:
            checked = GATE.check("atom_view", ea.body, ctx=tx.ctx)
        except GateError as exc:
            return AtomResult("rejected", key, f"the atom view was refused: {exc}")
        view: AtomView = checked.model
        if view.id != ea.id or view.status != ea.status:
            return AtomResult("rejected", key, f"the event says atom {ea.id} is {ea.status}, its view says atom {view.id} is {view.status}")
        old = tx.conn.execute("SELECT schema, node_id, display, attempt, sha256 FROM atoms WHERE id = ?", (key,)).fetchone()
        if old is not None:
            if old["schema"] != "atom/1" or old["node_id"] != node.id:
                return AtomResult("rejected", key, f"atom {key} is stored for another node or schema")
            if old["sha256"] == checked.sha256:
                return AtomResult("unchanged", key, display=view.status)
            if _VIEW_RANK[old["display"]] == 2 and old["display"] != view.status:
                return AtomResult("rejected", key, f"atom {key} is {old['display']} and final: no later move is stored")
            if _VIEW_RANK[view.status] < _VIEW_RANK[old["display"]] or (view.attempt or 0) < old["attempt"]:
                return AtomResult("rejected", key, f"atom {key} cannot go back from {old['display']} to {view.status}")
        self.upsert(tx, checked, key=key, node_id=node.id, task_id=task_id, department_id=node.department_id,
                    ts_open=ea.ts_open, ts_closed=ea.ts_closed, attempt=ea.attempt)
        ledgered = False
        if view.status != "open":
            row = ledger_row_from_view(view, node.id, node.department_id, now=ea.ts_closed if ea.ts_closed is not None else tx.now())
            ledgered = self.append_ledger(tx, GATE.check("atom_ledger_row", row), key=key)
        outcome = "opened" if view.status == "open" else view.status
        self._emit(tx, key, node.id, outcome, view.status)
        return AtomResult("applied", key, display=view.status, outcome=outcome, ledgered=ledgered)

    def _refresh_node(self, tx: Tx, node: Node) -> None:
        """Write `open_atom` and `atom_count` to a function node's body, in this transaction (the counts include the row just
        written). Other nodes have neither field."""
        if self.graph is None or not hasattr(node, "open_atom"):
            return
        opened = tx.conn.execute("SELECT id FROM atoms WHERE node_id = ? AND state = 'open' AND schema = 'work-atom/0.3'", (node.id,)).fetchone()
        count = tx.conn.execute("SELECT count(*) FROM atoms WHERE node_id = ? AND schema = 'work-atom/0.3'", (node.id,)).fetchone()[0]
        updated = node.evolve(open_atom=opened["id"] if opened is not None else None, atom_count=count,
                              ts_updated=max(node.ts_updated, tx.now()))
        self.graph.put_node(tx, GATE.check("node", updated, ctx=tx.ctx))

    def _emit(self, tx: Tx, key: str, node_id: str, outcome: str, display: str) -> None:
        out = _atom_outs(tx.conn, [tx.conn.execute(f"SELECT {_COLUMNS} FROM atoms WHERE id = ?", (key,)).fetchone()])[0]
        tx.emit("atom.updated", {"atom_id": key, "node_id": node_id, "outcome": outcome, "state": display,
                                 "atom": out.model_dump(mode="json", by_alias=True)})
