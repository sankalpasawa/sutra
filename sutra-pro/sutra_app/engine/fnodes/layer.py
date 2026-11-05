"""The function-node layer: `FunctionNodeHooks(EventHooks)` and `factory` (function-nodes.md section 5, engine design 4.3a).

One function turn is one work atom. The layer hangs on the P8 hooks of the vendored J2 and only OBSERVES: it changes no
prompt, reply, route or outcome. Hook by hook (section 5.2):

    run_started      bind the run overhead key (`llm.bind_atom`), learn the run and department
    turn_started     the five function names only: abandon a stale open atom of the node (`replaced`), declare the turn
                     (`declare.py`), `open_atom`, emit the `atom` event with its card; refused: stored, ledgered, carded, a
                     trace line `atom.refused`, the turn goes on without an atom; opened: bind the atom for cost
    call_finished    the node's own agent_turn call: buffer the reply, run the reply-phase checks; a failure is a close that
                     fails (attempt + 1, card VERIFY FAILED, the atom stays open); the third failure abandons it at once
    message_posted   buffer the message; an answer from the owner closes an open manual atom; a message by a function with no
                     open atom writes `layer.touches_miss`
    record_saved     buffer the record; a record the function may not write writes `layer.touches_miss`
    turn_finished    run every check on the whole turn: all ok or na closes the atom (`RECOVERED:` / `WAIVED:` in the
                     evidence); otherwise the close fails and the atom is abandoned with code `verify_failed`. A turn that
                     ended paused opens the manual atom for the question. The run overhead key is bound again
    run_status       waiting and not paused, and `run_error`: abandon every open atom, `run ended: <status>`

Every hook body is wrapped: an error becomes a `layer.error` trace line and never reaches J2. The one exception is the
library's strict mode: a fatal exception (`is_fatal`) from the base class's record gate passes through unchanged, because
stopping the run on a rejected record is the strict mode's whole point. The layer itself never sets `fatal`.

Every transition is written, synchronously, as one `atom` event (`atom_event`): the library's `Checked[Atom]` body, its Card
and, at the end of an atom, its LedgerRow. The Projector on the server turns those lines into rows.

Warn-and-log scope (section 5.4): a message by a function with no open atom, and a record outside what the function writes
(`WRITE_TERMS` maps the prose of `FunctionSpec.writes` to the record files it means), write one `layer.touches_miss` line
and block nothing.
"""
import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final, Optional

from sutra_app.engine import llm
from sutra_app.engine.events import EventWriter, atom_event
from sutra_app.engine.hooks import CallInfo, EventHooks, TurnInfo, TurnOutcome, is_fatal
from sutra_app.library.atom import MAX_ATTEMPTS, Atom, Seen, Transition, abandon_atom, close_atom, ledger_row, open_atom
from sutra_app.library.gate import GATE
from sutra_app.library.node import FunctionSpecs, FunctionSpecsError, load_function_specs
from sutra_app.library.types import FUNCTIONS, clip

from .checks import CheckRunner, TurnBuffer
from .declare import declare, declare_question
from .evidence import RECORD_NAMES, read_records
from .ids import AtomIds, node_id_of, run_overhead_id

__all__ = ["FunctionNodeHooks", "factory", "NODE_MODES", "WRITE_TERMS", "writable_records", "SCHEMA"]

SCHEMA: Final = "work-atom/0.3"
NODE_MODES: Final = ("on", "off", "enforce")
ERROR_MAX = 500
# What the prose of `FunctionSpec.writes` means in record files (the five records the checks read). A phrase that is not here
# names no record (a chat message or a hand-off). Warn-and-log only: a wrong row costs a trace line, never an outcome.
WRITE_TERMS: Final = MappingProxyType({
    "identity decisions": ("goal.json", "conflicts.json"),
    "questions to the Requester": (),
    "done verdicts": ("audits.json",),
    "proposals": ("workflows.json", "realization.json"),
    "revisions": ("workflows.json", "realization.json"),
    "grants": ("workflows.json",),
    "counters": ("workflows.json",),
    "refusals": ("workflows.json",),
    "envelope changes": ("workflows.json",),
    "schedule decisions": ("workflows.json",),
    "holds": ("workflows.json", "conflicts.json"),
    "handoffs": (),
    "alarms": ("conflicts.json",),
    "findings": ("audits.json", "conflicts.json"),
    # GAP-TUNE (G14): the records J2 saves legitimately that the first list left out. Adaptation and Priority argue a proposal
    # conflict with each other and J2 saves every attempt in conflicts.json; Identity's `split` ruling registers the workflows
    # it names, which saves workflows.json.
    "conflict positions": ("conflicts.json",),
    "split registrations": ("workflows.json",),
})


def writable_records(writes: list[str]) -> frozenset[str]:
    """The record files a function may save, from the `writes` of its spec."""
    return frozenset(name for term in writes for name in WRITE_TERMS.get(term, ()))


def _get(spec: Any, key: str) -> Any:
    return spec.get(key) if isinstance(spec, Mapping) else getattr(spec, key, None)


class FunctionNodeHooks(EventHooks):
    """The default hooks of the engine (SUTRA_NODES=on). `specs` are the five FunctionSpecs (default: the shipped file),
    `clock` gives epoch seconds (tests pass a fake), `runner` and `ids` can be replaced for tests."""

    def __init__(self, writer: EventWriter, notify: Callable[[], None], validator: Optional[Callable[[str, Any], Any]] = None,
                 node_context_file=None, *, specs: Optional[FunctionSpecs] = None, clock: Callable[[], float] = time.time,
                 runner: Optional[CheckRunner] = None, ids: Optional[AtomIds] = None, run_id: Optional[str] = None,
                 dept_id: Optional[str] = None):
        super().__init__(writer, notify, validator, node_context_file)
        self.specs = specs if specs is not None else load_function_specs()
        self.clock = clock
        self.runner = runner if runner is not None else CheckRunner()
        self.ids = ids if ids is not None else AtomIds()
        self.run_id: Optional[str] = run_id
        self.dept_id: Optional[str] = dept_id
        self._lock = threading.RLock()                          # hooks come from the run thread and the inbox thread
        self.errors: list[str] = []                             # the layer.error texts, newest last (tests read them)
        self._open: dict[str, Atom] = {}                        # node id -> its open atom (a function atom or the manual one)
        self._owners: dict[str, str] = {}                       # atom id -> owner node, for the checks
        self._manual: dict[str, TurnBuffer] = {}                # node id -> the buffer the manual atom's answer is judged on
        self._buf: Optional[TurnBuffer] = None                  # the function turn in progress
        self._turn_node: Optional[str] = None                   # the node whose atom belongs to that turn (None: refused / none)

    # ---- plumbing ---------------------------------------------------------------------------------------------------
    @property
    def open_atoms(self) -> dict[str, Atom]:
        """The open atoms by node id (a copy)."""
        return dict(self._open)

    def _now(self) -> int:
        return int(self.clock())

    def _layer_error(self, hook: str, exc: BaseException | str) -> None:
        text = clip(exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}", ERROR_MAX)
        self.errors.append(f"{hook}: {text}")
        try:
            self.trace("layer.error", {"hook": hook, "error": text})
        except Exception:      # noqa: BLE001  a closed writer must not turn a swallowed error into a raised one
            pass

    def _guard(self, hook: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:      # noqa: BLE001
            if is_fatal(exc):         # the library's strict mode: the run must stop
                raise
            self._layer_error(hook, exc)
            return None

    def _learn(self, run_id: Any = None, dept_id: Any = None) -> None:
        if isinstance(run_id, str) and run_id:
            self.run_id = run_id
        if isinstance(dept_id, str) and dept_id:
            self.dept_id = dept_id

    def _rebind(self) -> None:
        """Calls made outside a function turn are charged to the run's overhead key."""
        if self.run_id:
            llm.bind_atom(run_overhead_id(self.run_id))

    # ---- emitting transitions ---------------------------------------------------------------------------------------
    def _emit(self, node: str, tr: Transition) -> None:
        """Write one transition as an `atom` event, and keep our book of open atoms."""
        atom = tr.atom
        body = json.loads(GATE.check("atom", atom).json)
        ledger = None
        if tr.outcome in ("closed", "abandoned", "refused"):
            ledger = json.loads(GATE.check("atom_ledger_row", ledger_row(atom)).json)
        checks = atom.verify.checks
        event = atom_event(
            node=node,
            atom={"id": atom.id, "schema": SCHEMA, "goal": atom.goal, "work_kind": atom.work.dispatch_kind,
                  "verify_template": checks[0].template if checks else None, "status": atom.state, "attempt": atom.attempt,
                  "closed_by": atom.closed_by, "reason": atom.refusal.message if atom.state == "refused" and atom.refusal else atom.reason,
                  "body": body, "ts_open": atom.ts_open, "ts_closed": atom.ts_closed},
            outcome=tr.outcome, card=tr.card.model_dump(mode="json"), ledger=ledger)
        self.writer.emit(event)
        if atom.state == "open":
            self._open[node] = atom
        else:
            self._open.pop(node, None)
        self.notify()

    def _unchanged(self, what: str, tr: Transition) -> bool:
        """A close or abandon the library refused leaves the atom as it was and publishes nothing: say so in the trace."""
        if tr.outcome == "refused" and tr.atom.state != "refused":
            self._layer_error(what, f"{tr.refusal.code if tr.refusal else 'refused'}: {tr.refusal.message if tr.refusal else ''}")
            return True
        return False

    def _seen(self, atom: Atom, buf: Optional[TurnBuffer]) -> Seen:
        """What the turn did, to correct a wrong guess of the declared work kind and to stamp the model."""
        if atom.work.dispatch_kind == "manual" or buf is None:
            return Seen()
        model = buf.model
        return Seen(work="llm" if buf.calls else "bash", model=clip(model, 80) if model else None)

    def _abandon(self, node: str, atom: Atom, reason: str, code: str, seen: Optional[Seen] = None) -> None:
        tr = abandon_atom(atom, reason, self._now(), code=code, seen=seen)
        if not self._unchanged("abandon", tr):
            self._emit(node, tr)

    def _close_try(self, node: str, atom: Atom, rnd: Any, buf: Optional[TurnBuffer], *, final: bool) -> None:
        """Record one close run. All results 0: the atom closes. Otherwise the atom stays open with one more attempt (VERIFY
        FAILED), and is abandoned with code verify_failed when this was the final run or no run is left."""
        seen = self._seen(atom, buf)
        tr = close_atom(atom, rnd.results, self._now(), seen=seen)
        if self._unchanged("close", tr):
            return
        self._emit(node, tr)
        if tr.outcome == "verify_failed" and (final or tr.atom.attempt >= MAX_ATTEMPTS):
            self._abandon(node, tr.atom, rnd.reason, "verify_failed", seen)

    def _open_draft(self, node: str, turn: TurnInfo, draft: Any) -> Atom | None:
        atom_id = self.ids.next(turn.run_id, node)
        tr = open_atom(draft, id=atom_id, node_id=node, now=self._now(), department_id=turn.dept_id, task_id=turn.task_id,
                       session_id=self.ids.sid(turn.run_id, node), other_open=self._open.get(node))
        self._emit(node, tr)
        if tr.outcome == "refused":
            self.trace("atom.refused", {"fn": node.rpartition(".")[2], "atom": atom_id, "node": node,
                                        "code": tr.refusal.code if tr.refusal else "", "message": tr.refusal.message if tr.refusal else ""})
            return None
        self._owners[atom_id] = node
        return tr.atom

    def _abandon_all(self, reason: str, code: str = "run_ended") -> None:
        for node, atom in list(self._open.items()):
            buf = self._buf if node == self._turn_node else self._manual.get(node)
            self._guard("abandon", self._abandon, node, atom, reason, code, self._seen(atom, buf))
        self._manual.clear()
        self._buf, self._turn_node = None, None

    def abandon_open(self, status: str = "stopped") -> None:
        """End every open atom with `run ended: <status>`. The host calls this when a stop or SIGTERM ends the run, where no
        `run_status` hook will come."""
        with self._lock:
            self._guard("abandon_open", self._abandon_all, f"run ended: {status}")
            self._guard("abandon_open", self._rebind)

    # ---- hooks ------------------------------------------------------------------------------------------------------
    def run_started(self, spec: dict) -> None:
        with self._lock:
            self._guard("run_started", self._on_run_started, spec)

    def _on_run_started(self, spec: Any) -> None:
        self._learn(_get(spec, "run_id"), _get(spec, "dept_id"))
        self._rebind()

    def turn_started(self, t: TurnInfo) -> None:
        with self._lock:
            self._guard("turn_started", super().turn_started, t)
            self._guard("turn_started", self._on_turn_started, t)

    def _on_turn_started(self, t: TurnInfo) -> None:
        self._learn(t.run_id, t.dept_id)
        self._buf, self._turn_node = None, None
        if t.function not in FUNCTIONS:           # a builder W-n, or anything else: no function atom
            return
        node = node_id_of(t.dept_id, t.function)
        stale = self._open.get(node)
        if stale is not None:
            self._abandon(node, stale, f"replaced: atom {stale.id} was still open when turn {t.turn_no} began", "replaced")
        buf = TurnBuffer(turn=t, owners=dict(self._owners))
        buf.before = read_records(self.writer.run_dir)
        self._buf = buf
        draft = declare(t, self.specs.specs[t.function], workflows=buf.before.get("workflows.json"))
        atom = self._open_draft(node, t, draft)
        if atom is not None:
            self._turn_node = node
            buf.owners[atom.id] = node
            llm.bind_atom(atom.id)

    def call_finished(self, c: CallInfo) -> None:
        with self._lock:
            self._guard("call_finished", super().call_finished, c)
            self._guard("call_finished", self._on_call_finished, c)

    def _on_call_finished(self, c: CallInfo) -> None:
        buf = self._buf
        if buf is None or c.function != buf.turn.function or c.purpose != "agent_turn":
            return                      # helper calls are charged to the open atom by the binding; they are no replies
        buf.add_call(c)
        node = self._turn_node
        atom = self._open.get(node) if node else None
        if atom is None:
            return
        rnd = self.runner.round(atom, buf, "reply", self._now())
        if not rnd.passed:
            self._close_try(node, atom, rnd, buf, final=False)

    def message_posted(self, m: dict, questions: Optional[list] = None) -> None:
        with self._lock:
            self._guard("message_posted", super().message_posted, m, questions)
            self._guard("message_posted", self._on_message, m)

    def _on_message(self, m: Mapping) -> None:
        who = m.get("who")
        buf = self._buf
        if buf is not None:
            buf.add_message(m)
            if m.get("act") == "ASK_REQUESTER" and isinstance(m.get("id"), int):
                pause = m.get("pause")
                buf.question = {"id": m["id"], "text": str(m.get("text") or ""), "pause": None if pause is None else str(pause)}
        if who == "user":
            self._on_answer(m)
        elif who in FUNCTIONS and self.dept_id:
            node = node_id_of(self.dept_id, who)
            if node not in self._open:
                self.trace("layer.touches_miss", {"fn": who, "atom": None, "target": "message",
                                                  "reason": f"{who} posted a message while its node has no open atom"})

    def _on_answer(self, m: Mapping) -> None:
        """The owner spoke: judge `answer-recorded` for every open manual atom and close it."""
        for node, mbuf in list(self._manual.items()):
            atom = self._open.get(node)
            if atom is None or atom.work.dispatch_kind != "manual":
                self._manual.pop(node, None)
                continue
            mbuf.add_message(m)
            rnd = self.runner.round(atom, mbuf, "event", self._now())
            self._close_try(node, atom, rnd, mbuf, final=False)
            if node not in self._open:
                self._manual.pop(node, None)

    def record_saved(self, name: str, data: Any) -> list[str]:
        with self._lock:
            warnings = self._guard("record_saved", super().record_saved, name, data)
            self._guard("record_saved", self._on_record, name, data)
        return warnings if isinstance(warnings, list) else []

    def _on_record(self, name: str, data: Any) -> None:
        buf = self._buf
        if buf is None:
            return
        buf.add_record(name, data)
        function = buf.turn.function
        if name in RECORD_NAMES and name not in writable_records(self.specs.specs[function].writes):
            atom = self._open.get(self._turn_node) if self._turn_node else None
            self.trace("layer.touches_miss", {"fn": function, "atom": atom.id if atom else None, "target": name,
                                              "reason": f"{function} saved {name}, which its spec does not list in writes"})

    def turn_finished(self, t: TurnInfo, o: TurnOutcome) -> None:
        with self._lock:
            self._guard("turn_finished", super().turn_finished, t, o)
            try:
                self._guard("turn_finished", self._on_turn_finished, t, o)
            finally:
                self._buf, self._turn_node = None, None
                self._guard("turn_finished", self._rebind)

    def _on_turn_finished(self, t: TurnInfo, o: TurnOutcome) -> None:
        buf, node = self._buf, self._turn_node
        if buf is None or buf.turn.turn_no != t.turn_no:
            return
        atom = self._open.get(node) if node else None
        if atom is not None and atom.state == "open":
            rnd = self.runner.round(atom, buf, "turn", self._now(), outcome=o)
            self._close_try(node, atom, rnd, buf, final=True)
        if o.result == "paused":
            self._open_question(t, o, buf)

    def _open_question(self, t: TurnInfo, o: TurnOutcome, buf: TurnBuffer) -> None:
        """A turn that ended paused leaves one manual atom: the owner's answer to the question is recorded."""
        asked = buf.question or {}
        question_id = asked.get("id") or (o.messages[-1] if o.messages else 0)
        node = node_id_of(t.dept_id, "identity")
        draft = declare_question(t, self.specs.specs["identity"], question_id, question=asked.get("text", ""), pause=asked.get("pause"))
        atom = self._open_draft(node, t, draft)
        if atom is not None:
            self._manual[node] = TurnBuffer(turn=t.model_copy(update={"function": "identity"}), owners=dict(self._owners))

    def run_status(self, snap: dict) -> None:
        with self._lock:
            self._guard("run_status", super().run_status, snap)
            self._guard("run_status", self._on_run_status, snap)

    def _on_run_status(self, snap: Mapping) -> None:
        if snap.get("status") == "waiting" and not snap.get("paused"):
            self._abandon_all(f"run ended: {snap.get('status')}")
            self._rebind()

    def run_error(self, code: str, message: str) -> None:
        with self._lock:
            self._guard("run_error", super().run_error, code, message)
            self._guard("run_error", self._abandon_all, "run ended: crashed")
            self._guard("run_error", self._rebind)


def factory(writer: EventWriter, notify: Callable[[], None], validator: Optional[Callable[[str, Any], Any]] = None,
            node_context_file=None, task: Any = None, *, spec: Any = None, environ: Optional[Mapping[str, str]] = None,
            specs: Optional[FunctionSpecs] = None, clock: Callable[[], float] = time.time) -> EventHooks:
    """What the host calls to get its hooks (`SUTRA_HOOKS` default `sutra_app.engine.fnodes.layer:factory`, engine 4.7 step 6):
    `factory(writer, notify, validator, node_context_file, spec=<TaskSpec>)`, the way the host calls it; `task` is an alias of
    `spec` (the E7 tests use it) and both together are a `TypeError`. `SUTRA_NODES` picks the mode:
    `on` (default) the layer, `off` the plain `EventHooks`, `enforce` is reserved and a `ValueError`, like any other word and
    like function specs that cannot be loaded (the host ends the run as "could not start")."""
    if task is not None and spec is not None:
        raise TypeError("factory() takes the TaskSpec as `spec` or as its alias `task`, not both")
    task = spec if spec is not None else task
    env = os.environ if environ is None else environ
    mode = (env.get("SUTRA_NODES") or "on").strip().lower()
    if mode == "off":
        return EventHooks(writer, notify, validator, node_context_file)
    if mode == "enforce":
        raise ValueError("SUTRA_NODES=enforce is reserved: version 1 observes (use on or off)")
    if mode != "on":
        raise ValueError(f"SUTRA_NODES must be one of {', '.join(NODE_MODES)}, not {mode!r}")
    try:
        return FunctionNodeHooks(writer, notify, validator, node_context_file, specs=specs, clock=clock,
                                 run_id=_get(task, "run_id"), dept_id=_get(task, "dept_id"))
    except FunctionSpecsError as exc:
        raise ValueError(f"function specs: {exc}") from exc
