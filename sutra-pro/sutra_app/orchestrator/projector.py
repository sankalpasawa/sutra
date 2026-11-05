"""The Projector: the lines of a run's `events.jsonl` become graph, chat, atom and usage rows (orchestrator 5.6; D15, D16, D58-D60;
S1-contracts-09, -10, -16; S3-web-04; S4-fnodes-08..10, -14).

    projector = Projector(db, graph=..., chats=..., atoms=..., usage=..., store=task_store, taskgraph=task_graph)
    projector.drain(task_id)                       # read the new complete lines, apply them AND the new offset in ONE transaction
    projector.mark_ended(task_id, "crashed", ...)  # the server's own terminal event (process gone, app closed, stopped by you)
    projector.flag_silent(task_id, seconds)        # the step node says 'no signal for N s'

The server is the only SQLite writer (D16). Every projection is idempotent: chat lines by `src_ref`, usage rows by `call_ref`, atoms
by their forward-only rules and ledger key, nodes and edges by value, and the whole batch by `tasks.events_offset`, which commits
with the rows it covers. A file shorter than the offset restarts at 0 (the replay changes nothing).

What an event does (5.6):
  run.started  task `running`, pid                      node   a function node: state, detail, wait_on, stats (calls, seconds, tokens);
  say          a chat line in the right session                 a step node: state and detail. NEVER goal, task or context
  step         a step node, its depends_on edges       atom   AtomStore.apply_transition (cards, Atom log, open_atom, atom_count)
  usage        a usage_ledger row                      heartbeat  last_event_at          run.ended  the task ends (see `_finish`)
One event that cannot be applied is skipped with a `note` in Identity's working log; the rest of the batch goes on (F9).
"""
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from sutra_app.connectors.usage import UsageIn
from sutra_app.library.atom import abandon_atom, ledger_row
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.node import STEP_REF_RE, FunctionNode, NodeStats, NodeTokens, make_edge, step_node_id
from sutra_app.library.types import FUNCTIONS, clip, function_node_id
from sutra_app.orchestrator.chats import parse_options
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.ids import ORG_SESSION_ID, Clock, SystemClock, iso_z, parse_iso_z
from sutra_app.orchestrator.models import (
    DoneCard, EventParseError, NeedsYouCard, RunAtom, RunEnded, RunNode, RunSay, RunStarted, RunStep, RunUsage, parse_event,
)
from sutra_app.orchestrator.tasks import TaskGraph, TaskRow, TaskStore

__all__ = ["Projector", "Drained", "MAX_CHUNK_BYTES", "MAX_LINE_BYTES", "DEFAULT_OUTCOMES"]

log = logging.getLogger(__name__)
MAX_CHUNK_BYTES = 2_000_000
MAX_LINE_BYTES = 64_000_000
DEFAULT_OUTCOMES = {
    "done": "Done.", "done_with_open_items": "Done with open items.", "stopped": "Stopped.", "crashed": "The team stopped unexpectedly.",
}
_BUILDER_ID = re.compile(r"W-[0-9]+")
_FUNCTION_ATOM = re.compile(r"a-[a-z0-9]{1,16}-[0-9]{2,6}")      # a function atom or an overhead key; anything else is J2's own id (W-3.a1)
_OPEN_WORK_STATUSES = ("starting", "running", "waiting_user")
_EDGE_STATUSES = ("filed", "running", "waiting", "waiting_on_you", "fault", "not_made", "idle")
_META_KEYS = ("act", "pause", "next", "to_user")
CRASH_TEXT = "Something went wrong. Try again."


@dataclass
class Drained:
    """What one `drain` did. `ended`: the task is over (a terminal event was applied now or before). `freed_slot`: a team began
    waiting for the owner or a task ended, so `start_ready()` may start something. `more`: the chunk limit was hit; drain again."""

    applied: int = 0
    skipped: int = 0
    ended: bool = False
    status: str | None = None
    freed_slot: bool = False
    more: bool = False
    offset: int = 0


@dataclass
class _Batch:
    tx: Tx
    row: TaskRow
    freed: bool = False
    ended: bool = False
    changed: bool = False
    skipped: int = 0

    @property
    def run(self) -> str:
        return self.row.run_id or ""


class Projector:
    def __init__(self, db: Database, *, graph: Any, chats: Any, atoms: Any, usage: Any, store: TaskStore, taskgraph: TaskGraph,
                 clock: Clock | None = None) -> None:
        self.db = db
        self.graph = graph
        self.chats = chats
        self.atoms = atoms
        self.usage = usage
        self.store = store
        self.taskgraph = taskgraph
        self.clock = clock or SystemClock()

    # =================================================================================================================
    # reading the file and applying a batch
    # =================================================================================================================

    def drain(self, task_id: str) -> Drained:
        """Apply the complete lines of the task's `events.jsonl` that came after `events_offset`, with the new offset, in one
        transaction. A finished task is left alone."""
        with self.db.tx() as tx:
            row = self.store.row_in(tx.conn, task_id)
            if row is None:
                raise NotFound("that task")
            if row.terminal:
                return Drained(ended=True, status=row.status, offset=row.events_offset)
            if row.run_id is None:
                return Drained(status=row.status, offset=row.events_offset)
            path = self.store.run_dir_of(row) / "events.jsonl"
            offset = row.events_offset
            try:
                size = path.stat().st_size
            except OSError:
                return Drained(status=row.status, offset=offset)
            if size < offset:
                offset = 0                                   # the file was replaced by a shorter one: replay it (all projections are idempotent)
            data, limit = b"", MAX_CHUNK_BYTES
            if size > offset:
                with open(path, "rb") as handle:
                    while True:                                  # a line longer than the chunk makes the chunk bigger, up to MAX_LINE_BYTES
                        handle.seek(offset)
                        data = handle.read(limit)
                        if b"\n" in data or len(data) < limit or limit >= MAX_LINE_BYTES:
                            break
                        limit *= 2
            end = data.rfind(b"\n")
            if end < 0 and len(data) >= MAX_LINE_BYTES:           # one line of 64 MB or more: skip it (noted) rather than stall the run
                self._note(_Batch(tx, row), f"Skipped a line of the run's events that is {len(data)} bytes long.", f"{row.run_id}#skip:{offset}")
                self.store.touch(tx, task_id, events_offset=offset + len(data))
                return Drained(skipped=1, status=row.status, offset=offset + len(data), more=size > offset + len(data))
            if end < 0:
                if offset != row.events_offset:
                    self.store.touch(tx, task_id, events_offset=offset)
                return Drained(status=row.status, offset=offset)
            chunk = data[: end + 1]
            batch = _Batch(tx, row)
            dropped: list[str] = []
            applied, newest, position = 0, None, offset
            for raw in chunk.split(b"\n")[:-1]:
                start, position = position, position + len(raw) + 1
                if not raw.strip():
                    continue
                if batch.row.terminal:                       # nothing follows run.ended
                    break
                try:
                    event = parse_event(raw, strict=False, dropped=dropped)
                except EventParseError as exc:
                    self._note(batch, f"Skipped a line of the run's events ({exc.code}: {exc}).", f"{batch.run}#skip:{start}")
                    batch.skipped += 1
                    continue
                for key in dict.fromkeys(dropped):
                    self._note(batch, f"Ignored the unknown field {key} in a {event.t} event.", f"{batch.run}#dropped:{event.t}.{key}")
                dropped.clear()
                if self._apply_guarded(batch, event, start):
                    applied += 1
                try:
                    newest = parse_iso_z(event.at)
                except ValueError:
                    pass
            new_offset = offset + len(chunk)                  # nothing is read after run.ended, so the rest of a chunk may be dropped
            self.store.touch(tx, task_id, events_offset=new_offset, last_event_at=newest)
            if batch.changed or applied:
                self._refresh(batch)
            return Drained(applied=applied, skipped=batch.skipped, ended=batch.row.terminal, status=batch.row.status,
                           freed_slot=batch.freed, more=offset + len(data) < size, offset=new_offset)

    def apply(self, tx: Tx, task: TaskRow, events: list[Any]) -> _Batch:
        """Apply parsed events inside the caller's transaction (tests and replays); no file, no offset."""
        batch = _Batch(tx, task)
        for index, event in enumerate(events):
            self._apply_guarded(batch, event, index)
        self._refresh(batch)
        return batch

    def _refresh(self, batch: _Batch) -> None:
        row = self.store.row_in(batch.tx.conn, batch.row.id)
        if row is not None:
            batch.row = row
            if not row.terminal:
                self.taskgraph.sync(batch.tx, row, announce=False)         # a node that said 'no signal' says nothing again
        self.graph.aggregate(batch.tx)

    def _apply_guarded(self, batch: _Batch, event: Any, where: int) -> bool:
        """One event in a savepoint: an event that cannot be applied is noted and skipped, the batch goes on (F9)."""
        conn = batch.tx.conn
        conn.execute("SAVEPOINT event")
        try:
            handler = getattr(self, "_on_" + event.t.replace(".", "_"))
            handler(batch, event)
            batch.row = self.store.row_in(conn, batch.row.id) or batch.row
        except (GateError, ValidationError, ValueError, AppError, sqlite3.IntegrityError) as exc:
            conn.execute("ROLLBACK TO event")
            batch.skipped += 1
            log.warning("run %s: a %s event was skipped: %s", batch.run, event.t, exc)
            self._note(batch, f"Skipped a {event.t} event: {clip(str(exc), 300)}", f"{batch.run}#error:{where}:{event.t}")
            conn.execute("RELEASE event")
            return False
        conn.execute("RELEASE event")
        batch.changed = True
        return True

    # =================================================================================================================
    # helpers
    # =================================================================================================================

    def _node(self, tx: Tx, node_id: str) -> Any:
        return tx.ctx.get("node", node_id)

    def _session_of(self, tx: Tx, node_id: str) -> str | None:
        found = tx.conn.execute("SELECT chat_session_id FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
        return found["chat_session_id"] if found is not None else None

    def _note(self, batch: _Batch, text: str, src_ref: str) -> None:
        """A `note` in Identity's working log (idempotent by `src_ref`). Never raises."""
        tx = batch.tx
        session = self._session_of(tx, function_node_id(batch.row.dept_id, "identity"))
        if session is None:
            return
        try:
            self.chats.post(tx, session, GATE.check("chat_message", dict(
                kind="note", session_id=session, role="system", who="system", text=clip(text, 1000), task_id=batch.row.id, src_ref=src_ref,
                at=tx.now()), ctx=tx.ctx))
        except (GateError, AppError, sqlite3.Error) as exc:
            log.warning("could not post a note: %s", exc)

    def _post(self, batch: _Batch, session_id: str, *, who: str, kind: str, text: str = "", role: str = "agent", src_ref: str | None = None,
              at: int | None = None, **extra: Any) -> Any:
        tx = batch.tx
        payload = dict(kind=kind, session_id=session_id, role=role, who=clip(who, 60), text=text, task_id=batch.row.id, src_ref=src_ref,
                       at=at if at is not None else tx.now(), **extra)
        return self.chats.post(tx, session_id, GATE.check("chat_message", payload, ctx=tx.ctx))

    def _step_node(self, batch: _Batch, ref: str, *, label: str | None = None, state: str | None = None, detail: str | None = None,
                   parent_ref: str | None = None) -> str:
        """The step node of `ref` ('W-3', 'team:Product Analyst'), made when it does not exist yet."""
        if not STEP_REF_RE.fullmatch(ref):
            raise ValueError(f"{clip(ref, 60)!r} is not a step reference (W-<n> or team:<role>)")
        parent_id = None
        if parent_ref is not None and STEP_REF_RE.fullmatch(parent_ref) and parent_ref != ref:
            candidate = step_node_id(batch.row.id, parent_ref)
            parent_id = candidate if self._node(batch.tx, candidate) is not None else None
        return self.taskgraph.ensure_step(batch.tx, batch.row, ref, label=label, state=state, detail=detail, parent_id=parent_id)

    # =================================================================================================================
    # the eight events
    # =================================================================================================================

    def _on_run_started(self, batch: _Batch, ev: RunStarted) -> None:
        row = batch.row
        if row.status == "starting":
            row = self.store.update(batch.tx, row.id, status="running", pid=ev.pid)
            self.taskgraph.sync(batch.tx, row)
        elif row.pid != ev.pid:
            self.store.update(batch.tx, row.id, pid=ev.pid)

    def _on_heartbeat(self, batch: _Batch, ev: Any) -> None:
        return None                                             # last_event_at is set from the batch's newest line

    # ---- say -------------------------------------------------------------------------------------------------------------

    def _on_say(self, batch: _Batch, ev: RunSay) -> None:
        tx, row = batch.tx, batch.row
        who, dept = ev.who, batch.row.dept_id
        if not ev.text.strip():
            raise ValueError("a say event has no text")
        identity = function_node_id(dept, "identity")
        question = who == "identity" and ev.to_user and ev.act == "ASK_REQUESTER"
        if who == "identity" and ev.to_user:
            session = self._session_of(tx, dept)
        elif who in FUNCTIONS:
            session = self._session_of(tx, function_node_id(dept, who))
        elif who == "validator":
            session = self._session_of(tx, function_node_id(dept, ev.next if ev.next in FUNCTIONS else "identity"))
        elif who == "system":
            session = self._session_of(tx, identity)
        else:                                                   # W-<n> or team:<role>: that step's own log
            session = self._session_of(tx, self._step_node(batch, who))
        if session is None:
            raise ValueError(f"no chat session for {who}")
        meta = {key: value for key, value in (("act", ev.act), ("pause", ev.pause), ("next", ev.next), ("to_user", ev.to_user or None)) if value is not None}
        posted = self._post(batch, session, who=who, kind="question" if question else "text", text=ev.text, src_ref=f"{batch.run}#chat:{ev.id}",
                            pause=ev.pause if question else None, meta=meta, at=self._event_ts(ev, tx))
        if posted is None:
            return                                              # a replayed line: everything below happened the first time
        if question:
            self._ask(batch, posted, ev)
        if who in FUNCTIONS and ev.next in FUNCTIONS and ev.next != who:
            self._speaks_to(batch, function_node_id(dept, who), function_node_id(dept, ev.next), ev.id)

    @staticmethod
    def _event_ts(ev: Any, tx: Tx) -> int:
        try:
            return parse_iso_z(ev.at)
        except ValueError:
            return tx.now()

    def _ask(self, batch: _Batch, posted: Any, ev: RunSay) -> None:
        """Identity asked the owner: the task waits, Identity is `waiting_on_you`, and the org chat gets the `needs_you` card."""
        tx, row = batch.tx, batch.row
        if row.status in ("starting", "running"):
            row = self.store.update(tx, row.id, status="waiting_user")
            self.taskgraph.sync(tx, row)
        batch.freed = True
        identity = self._node(tx, function_node_id(row.dept_id, "identity"))
        if identity is not None and identity.state != "waiting_on_you":
            self.graph.put_node(tx, GATE.check("node", identity.evolve(state="waiting_on_you", wait_on="you", ts_updated=max(identity.ts_updated, tx.now())), ctx=tx.ctx))
        name = tx.conn.execute("SELECT name FROM org_nodes WHERE id = ?", (row.dept_id,)).fetchone()
        card = NeedsYouCard(type="needs_you", dept_id=row.dept_id, dept_name=name["name"] if name is not None else row.dept_id,
                            question_message_id=posted.id, text=ev.text, options=parse_options(ev.text))
        self._post(batch, ORG_SESSION_ID, who="sutra", kind="card", card=card.model_dump(mode="json"), src_ref=f"{batch.run}#needs:{ev.id}")

    def _speaks_to(self, batch: _Batch, source: str, target: str, say_id: int) -> None:
        tx = batch.tx
        edge_id = f"speaks_to:{source}>{target}"
        old = tx.conn.execute("SELECT body FROM graph_edges WHERE id = ?", (edge_id,)).fetchone()
        count = (json.loads(old["body"]).get("n") or 0) + 1 if old is not None else 1
        edge = make_edge("speaks_to", source, target, label=str(count), n=count,
                         source={"file": "chat.jsonl", "field": "next", "value": str(say_id)})
        self.graph.put_edge(tx, GATE.check("edge", edge, ctx=tx.ctx))

    # ---- node and step -----------------------------------------------------------------------------------------------------

    def _on_node(self, batch: _Batch, ev: RunNode) -> None:
        tx, row = batch.tx, batch.row
        if ev.step is not None:
            self._step_node(batch, ev.step, state=ev.status, detail=clip(ev.detail, 300))
            return
        node = self._node(tx, function_node_id(row.dept_id, ev.fn))
        if not isinstance(node, FunctionNode):
            raise ValueError(f"function node {row.dept_id}.{ev.fn} does not exist")
        wait_on = None
        if ev.status == "waiting_on_you":
            wait_on = "you"
        elif ev.status == "waiting":
            wait_on = ev.wait_on or "identity"
        tokens = NodeTokens(input=ev.tokens.input, output=ev.tokens.output) if ev.tokens is not None else node.stats.tokens
        stats = NodeStats(calls=ev.calls, seconds=ev.seconds, tokens=tokens)
        # state, detail, wait_on and stats only: goal, task and context are static (written when the node is made)
        updated = node.evolve(state=ev.status, detail=clip(ev.detail, 300), wait_on=wait_on, stats=stats, ts_updated=max(node.ts_updated, tx.now()))
        self.graph.put_node(tx, GATE.check("node", updated, ctx=tx.ctx))

    def _on_step(self, batch: _Batch, ev: RunStep) -> None:
        tx, row = batch.tx, batch.row
        node_id = self._step_node(batch, ev.step, label=ev.name, state=ev.status, parent_ref=ev.parent)
        edges: list[tuple[str, str, str]] = [(r, "reads", "reads") for r in ev.reads]
        if ev.rework:
            edges.append((ev.rework, "revises", "rework"))                  # written after the reads: a pair that is both shows 'revises'
        status = ev.status if ev.status in _EDGE_STATUSES else "idle"
        for target_ref, label, field in edges:
            if target_ref == ev.step or not STEP_REF_RE.fullmatch(target_ref):
                continue
            target = self._step_node(batch, target_ref)
            workflow = ev.step if _BUILDER_ID.fullmatch(ev.step) else None
            edge = make_edge("depends_on", node_id, target, label=label, status=status,
                             source={"file": "workflows.json", "workflow": workflow, "field": field, "value": target_ref})
            self.graph.put_edge(tx, GATE.check("edge", edge, ctx=tx.ctx))

    # ---- atoms and usage -----------------------------------------------------------------------------------------------------

    def _on_atom(self, batch: _Batch, ev: RunAtom) -> None:
        tx, row = batch.tx, batch.row
        target = ev.node
        if STEP_REF_RE.fullmatch(target) and target != "task":
            node_id = self._step_node(batch, target)
            ev = ev.model_copy(update={"node": node_id})
        else:
            node_id = target
            if ev.atom.schema_ == "atom/1" or not node_id.startswith(f"{row.dept_id}."):
                raise ValueError(f"atom {ev.atom.id} names the node {clip(target, 60)}, which is not a node of this run")
        if self._is_replay(tx, ev, row.run_id or ""):
            return
        result = self.atoms.apply_transition(tx, node_id, ev, run_id=row.run_id, task_id=row.id)
        if result.status == "rejected":
            self._note(batch, f"Atom {ev.atom.id} was not stored: {result.reason}", f"{batch.run}#atom:{ev.atom.id}:{ev.atom.status}:{ev.atom.attempt}")

    @staticmethod
    def _is_replay(tx: Tx, ev: RunAtom, run_id: str) -> bool:
        """Is this line an EARLIER step of an atom whose row has moved on? A file read again from the top (a shorter file, a
        reset offset) shows every atom's old transitions again: they change nothing and are not worth a note. A line that
        disagrees with the stored FINAL state (closed, then abandoned) is not a replay: the store refuses it and it is noted."""
        ea = ev.atom
        key = ea.id if ea.schema_ == "work-atom/0.3" else f"{run_id}:{ea.id}"
        old = tx.conn.execute("SELECT state, display, attempt FROM atoms WHERE id = ?", (key,)).fetchone()
        if old is None:
            return False
        if ea.schema_ == "work-atom/0.3":
            if old["state"] != "open":
                return ea.status == "open"                       # a final row: only an opening or a failed try can come from before
            return ea.status == "open" and ea.attempt < old["attempt"]
        rank = {"open": 0, "verify_failed": 1, "closed": 2, "abandoned": 2}
        return rank[ea.status] < rank[old["display"]]

    def _on_usage(self, batch: _Batch, ev: RunUsage) -> None:
        tx, row = batch.tx, batch.row
        node_id = None
        if ev.fn in FUNCTIONS:
            node_id = function_node_id(row.dept_id, ev.fn)
        elif _BUILDER_ID.fullmatch(ev.fn):
            node_id = step_node_id(row.id, ev.fn)
        elif ev.step and STEP_REF_RE.fullmatch(ev.step) and ev.step != "task":
            node_id = step_node_id(row.id, ev.step)
        node = self._node(tx, node_id) if node_id else None
        atom_id = None
        if ev.atom:
            atom_id = ev.atom if _FUNCTION_ATOM.fullmatch(ev.atom) else clip(f"{batch.run}:{ev.atom}", 200)
        try:
            entry = UsageIn(
                provider=ev.provider, model=ev.model or "", purpose=ev.purpose, session_id=node.chat_session_id if node is not None else None,
                node_id=node.id if node is not None else None, task_id=row.id, dept_id=row.dept_id, fn=clip(ev.fn, 20), step=ev.step,
                atom_id=atom_id, usd=ev.usd, tokens_in=ev.tokens_in, tokens_out=ev.tokens_out, seconds=ev.seconds, ok=ev.ok, how=ev.how,
                call_ref=ev.call_ref, detail=ev.detail)
        except ValidationError as exc:
            raise ValueError(f"the usage line is not a usage row: {exc.errors(include_url=False)[0]['msg']}") from None
        self.usage.record(entry, tx=tx)

    # ---- the end ---------------------------------------------------------------------------------------------------------------

    def _on_run_ended(self, batch: _Batch, ev: RunEnded) -> None:
        self._finish(batch, ev.status, ev.outcome, ev.code, self._event_ts(ev, batch.tx))

    def mark_ended(self, task_id: str, status: str, outcome: str, code: str | None = None) -> bool:
        """The server's own terminal event for a task whose process wrote none (crashed, or stopped by the server): False when
        the task is over already. Opens its own transaction."""
        with self.db.tx() as tx:
            row = self.store.row_in(tx.conn, task_id)
            if row is None:
                raise NotFound("that task")
            if row.terminal:
                return False
            batch = _Batch(tx, row)
            self._finish(batch, status, outcome, code, tx.now())
            self.graph.aggregate(tx)
            return True

    def flag_silent(self, task_id: str, seconds: int) -> None:
        """The task's step node says 'no signal for N s' (nothing is killed: a sleeping laptop freezes both sides)."""
        with self.db.tx() as tx:
            row = self.store.row_in(tx.conn, task_id)
            if row is not None and row.live:
                self.taskgraph.ensure_step(tx, row, "task", detail=f"no signal for {int(seconds)} s")

    def _finish(self, batch: _Batch, status: str, outcome: str, code: str | None, when: int) -> None:
        """A task ends: status, outcome and time; steps settle (map/1 words), functions go idle; every open function atom of the
        task is abandoned ('run ended: <status>'); blocked dependants are queued or cancelled; a `done` card in the org chat; a
        crash also says so in the department chat."""
        tx = batch.tx
        row = batch.row
        text = clip((outcome or "").strip() or DEFAULT_OUTCOMES[status], 2000)
        ended_at = max(when, row.started_at or row.created_at, row.created_at)
        row = self.store.update(tx, row.id, status=status, outcome=text, ended_at=ended_at)
        batch.row = row
        batch.ended = batch.freed = True
        self._abandon_open_atoms(batch, status)
        self._settle_nodes(batch, status)
        self.taskgraph.sync(tx, row)
        self.store.settle_blocked(tx, lambda moved: self.taskgraph.sync(tx, moved))
        name = tx.conn.execute("SELECT name FROM org_nodes WHERE id = ?", (row.dept_id,)).fetchone()
        card = DoneCard(type="done", task_id=row.id, dept_name=name["name"] if name is not None else row.dept_id, title=clip(row.title, 200),
                        status=status, outcome=text)
        self._post(batch, ORG_SESSION_ID, who="sutra", kind="card", card=card.model_dump(mode="json"), src_ref=f"{batch.run}#done", at=ended_at)
        if status == "crashed":
            session = self._session_of(tx, row.dept_id)
            if session is not None:
                self._post(batch, session, who="sutra", kind="error", text=CRASH_TEXT, role="system", src_ref=f"{batch.run}#crashed", at=ended_at)

    def _settle_nodes(self, batch: _Batch, status: str) -> None:
        tx, row = batch.tx, batch.row
        for r in tx.conn.execute("SELECT id, state FROM graph_nodes WHERE task_id = ? AND kind = 'step' AND step_ref != 'task'", (row.id,)).fetchall():
            if r["state"] in ("running", "waiting", "waiting_on_you"):
                new = "done_unchecked" if status == "done" else "left_open"
            elif r["state"] == "idle" and status != "done":
                new = "not_made"
            else:
                continue
            node = self._node(tx, r["id"])
            self.graph.put_node(tx, GATE.check("node", node.evolve(state=new, ts_updated=max(node.ts_updated, tx.now())), ctx=tx.ctx))
        for fn in FUNCTIONS:
            node = self._node(tx, function_node_id(row.dept_id, fn))
            if node is not None and (node.state != "idle" or node.wait_on is not None):
                self.graph.put_node(tx, GATE.check("node", node.evolve(state="idle", wait_on=None, ts_updated=max(node.ts_updated, tx.now())), ctx=tx.ctx))

    def _abandon_open_atoms(self, batch: _Batch, status: str) -> None:
        """Every function atom of the task that is still open ends 'run ended: <status>' (library `abandon_atom`), through
        the same store path as any transition: row, Atom log, card, node counters, `atom.updated`."""
        tx, row = batch.tx, batch.row
        now = tx.now()
        for r in tx.conn.execute(
                "SELECT id FROM atoms WHERE task_id = ? AND schema = 'work-atom/0.3' AND state = 'open' ORDER BY rowid", (row.id,)).fetchall():
            atom = tx.ctx.get("atom", r["id"])
            transition = abandon_atom(atom, f"run ended: {status}", now, code="run_ended")
            if transition.refusal is not None:
                continue
            ended = transition.atom
            event = RunAtom.model_validate({
                "t": "atom", "at": iso_z(now), "node": ended.node_id, "outcome": "abandoned", "card": transition.card.model_dump(mode="json"),
                "ledger": ledger_row(ended).model_dump(mode="json"),
                "atom": {"id": ended.id, "schema": "work-atom/0.3", "goal": ended.goal, "work_kind": ended.work.dispatch_kind,
                         "verify_template": ended.verify.checks[0].template if ended.verify.checks else None, "status": "abandoned",
                         "attempt": ended.attempt, "closed_by": ended.closed_by, "reason": ended.reason,
                         "body": ended.model_dump(mode="json"), "ts_open": ended.ts_open, "ts_closed": ended.ts_closed}})
            result = self.atoms.apply_transition(tx, ended.node_id, event, run_id=row.run_id or "", task_id=row.id)
            if result.status == "rejected":
                log.warning("could not abandon atom %s: %s", ended.id, result.reason)
