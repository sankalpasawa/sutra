"""The run-event protocol of the engine process (engine design 4.5, S1-contracts-09, S2-models-07, S3-web-04).

An engine process talks to the server through files only. It appends ONE JSON object per line to `events.jsonl` and engine
detail to `trace.jsonl`; the server's watcher projects the first into rows. The event list is closed at eight types, each
line has `t` and an ISO-8601 UTC `at`, and `run.ended` is the last line:

    run.started  say  node  step  atom  usage  heartbeat  run.ended

* `*_event` builders return a plain dict with exactly the fields of the design (`t` and `at` first) and refuse anything
  the design forbids, so a caller's mistake fails at the call and not in the watcher. They never write.
* `EventWriter` is the one writer: a line is one `os.write` on an `O_APPEND` descriptor under a lock (the watcher never
  reads half a line), `at` is stamped when missing, and nothing follows `run.ended`.
* `EventUsageSink` is the sink the router (or `llm.ScriptedPort`) hands each usage row to: it appends the `usage` event.

Lines are written with `ensure_ascii=True`: a model's text may hold U+2028, U+0085 or a lone surrogate, which a reader that
splits lines with `str.splitlines()` or encodes as UTF-8 would trip over. Every escape is still valid JSON.
This module imports nothing from the connectors, the orchestrator or the UI.
"""
import json
import math
import os
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sutra_app.library.types import ATOM_ID_RE, FUNCTIONS, clip

__all__ = [
    "EVENT_TYPES", "EVENTS_SCHEMA", "SEEDS", "NODE_STATUSES", "FUNCTION_STATUSES", "END_STATUSES", "ATOM_SCHEMAS",
    "WORK_KINDS", "ATOM_STATUSES", "ATOM_OUTCOMES", "TASK_STATES", "STEP_RE", "EventError", "utc_iso", "context_strings",
    "run_started_event", "say_event", "node_event", "step_event", "atom_event", "usage_event", "heartbeat_event",
    "run_ended_event", "encode_line", "EventWriter", "EventUsageSink",
]

EVENTS_SCHEMA = "events/1"
EVENT_TYPES = ("run.started", "say", "node", "step", "atom", "usage", "heartbeat", "run.ended")   # = ORCH's RUN_EVENT_TYPES
SEEDS = ("none", "rehydrated", "fresh")
NODE_STATUSES = ("idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made")
FUNCTION_STATUSES = NODE_STATUSES[:5]          # a function node uses the first five words
END_STATUSES = ("done", "done_with_open_items", "stopped", "crashed")
ATOM_SCHEMAS = ("atom/1", "work-atom/0.3")     # a builder's J2 atom view / a function-node atom
WORK_KINDS = ("llm", "skill", "bash", "manual")
ATOM_STATUSES = {"atom/1": ("open", "closed", "verify_failed", "abandoned"),
                 "work-atom/0.3": ("open", "closed", "refused", "abandoned")}
ATOM_OUTCOMES = ("opened", "verify_failed", "closed", "refused", "abandoned")
TASK_STATES = ("running", "done")
TASK_KEYS = ("id", "kind", "summary", "state", "set_by")
ATOM_KEYS = ("id", "schema", "goal", "work_kind", "verify_template", "status", "attempt", "closed_by", "reason", "body",
             "ts_open", "ts_closed")
ATOM_REQUIRED = ("id", "schema", "goal", "work_kind", "status", "attempt", "body", "ts_open")
SAY_NAMES = (*FUNCTIONS, "validator", "system")      # `who` of a say event; "user" is never an event
TASK_SUMMARY_MAX = 300
CONTEXT_ITEM_MAX = 200
CONTEXT_ITEMS_MAX = 40

STEP_RE = re.compile(r"W-[0-9]+|team:[^\x00-\x1f\x7f]{1,80}")       # a builder step or a persona's team
_AT_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


class EventError(ValueError):
    """An event was built or written wrongly. A bug in the caller, never bad data from a model."""


def utc_iso(ts: Optional[float] = None) -> str:
    """ISO-8601 UTC with seconds and a Z, e.g. 2026-11-04T10:00:06Z. `ts` is epoch seconds, default now."""
    moment = datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- argument checks -------------------------------------------------------------------------------------------

def _fail(name: str, why: str) -> None:
    raise EventError(f"{name}: {why}")


def _text(name: str, value: Any, *, nullable: bool = False, empty: bool = True) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _fail(name, f"must be a string, not {type(value).__name__}")
    if not empty and not value:
        _fail(name, "must not be empty")
    return value


def _int(name: str, value: Any, *, minimum: int = 0, maximum: Optional[int] = None, nullable: bool = False) -> Optional[int]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(name, f"must be an integer, not {type(value).__name__}")
    if value < minimum or (maximum is not None and value > maximum):
        _fail(name, f"must be {minimum}.." + (str(maximum) if maximum is not None else "") + f", not {value}")
    return value


def _number(name: str, value: Any, *, nullable: bool = False) -> Optional[float]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        _fail(name, f"must be a finite number >= 0, not {value!r}")
    return float(value)


def _bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        _fail(name, f"must be true or false, not {type(value).__name__}")
    return value


def _choice(name: str, value: Any, allowed: Sequence[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail(name, f"must be one of {', '.join(allowed)}, not {value!r}")
    return value


def _step_id(name: str, value: Any) -> str:
    if not isinstance(value, str) or not STEP_RE.fullmatch(value):
        _fail(name, f"must be W-<n> or team:<role>, not {value!r}")
    return value


def _stamp(at: Optional[str]) -> str:
    if at is None:
        return utc_iso()
    if not isinstance(at, str) or not _AT_RE.fullmatch(at):
        _fail("at", f"must look like 2026-11-04T10:00:06Z, not {at!r}")
    return at


def _list_of_text(name: str, value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(name, "must be a list of strings")
    return [_text(f"{name}[{i}]", item) for i, item in enumerate(value)]


def _event(t: str, at: Optional[str], fields: dict[str, Any]) -> dict[str, Any]:
    return {"t": t, "at": _stamp(at), **fields}


def context_strings(items: Sequence[Any]) -> list[str]:
    """`TurnInfo.context` pairs (kind, summary), or ready strings, as the `context` list of a node event: '<kind>: <summary>'
    cut to 200 characters, at most 40 items."""
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
        _fail("context", "must be a list")
    out = []
    for i, item in enumerate(items[:CONTEXT_ITEMS_MAX]):
        if isinstance(item, str):
            line = item
        elif isinstance(item, Sequence) and not isinstance(item, bytes) and len(item) == 2 \
                and all(isinstance(part, str) for part in item):
            line = f"{item[0]}: {item[1]}"
        else:
            _fail(f"context[{i}]", "must be a string or a (kind, summary) pair")
        out.append(clip(line, CONTEXT_ITEM_MAX))
    return out


# ---- the eight builders ----------------------------------------------------------------------------------------

def run_started_event(*, pid: int, mock: bool, seed: str, at: Optional[str] = None) -> dict:
    """The host emits it after the seed decision; a run that fails early emits only `run.ended`."""
    return _event("run.started", at, {"pid": _int("pid", pid, minimum=1), "schema": EVENTS_SCHEMA,
                                      "mock": _bool("mock", mock), "seed": _choice("seed", seed, SEEDS)})


def say_event(*, id: int, who: str, text: str, to_user: bool = False, act: Optional[str] = None,
              pause: Optional[str] = None, questions: Optional[list] = None, next: Optional[str] = None,
              at: Optional[str] = None) -> dict:
    """A message J2 posted, except the owner's own. `questions` (J2 `paused.questions`) only for act ASK_REQUESTER."""
    if who == "user":
        _fail("who", "the owner's own lines are never say events")
    if who not in SAY_NAMES and not (isinstance(who, str) and STEP_RE.fullmatch(who)):
        _fail("who", f"must be a function, validator, system, W-<n> or team:<role>, not {who!r}")
    if questions is not None:
        if act != "ASK_REQUESTER":
            _fail("questions", "only a message with act ASK_REQUESTER carries questions")
        if isinstance(questions, (str, bytes)) or not isinstance(questions, Sequence) \
                or not all(isinstance(q, Mapping) for q in questions):
            _fail("questions", "must be a list of objects")
        questions = [dict(q) for q in questions]
    return _event("say", at, {"id": _int("id", id, minimum=1), "who": who, "text": _text("text", text),
                              "to_user": _bool("to_user", to_user), "act": _text("act", act, nullable=True),
                              "pause": _text("pause", pause, nullable=True), "questions": questions,
                              "next": _text("next", next, nullable=True)})


def _task_info(task: Any) -> dict:
    if not isinstance(task, Mapping) or set(task) != set(TASK_KEYS):
        _fail("task", f"must be an object with exactly {', '.join(TASK_KEYS)}")
    return {"id": _text("task.id", task["id"], empty=False), "kind": _text("task.kind", task["kind"], nullable=True),
            "summary": clip(_text("task.summary", task["summary"]), TASK_SUMMARY_MAX),
            "state": _choice("task.state", task["state"], TASK_STATES), "set_by": _text("task.set_by", task["set_by"])}


def _wait_on(value: Any) -> Optional[str]:
    if value is None or value == "you" or value in FUNCTIONS:
        return value
    return _step_id("wait_on", value) if isinstance(value, str) else _fail("wait_on", f"bad value {value!r}")


def node_event(*, status: str, fn: Optional[str] = None, step: Optional[str] = None, detail: str = "", calls: int = 0,
               seconds: float = 0.0, task: Optional[Mapping] = None, context: Optional[Sequence] = None,
               wait_on: Optional[str] = None, tokens: Optional[Mapping] = None, at: Optional[str] = None) -> dict:
    """The state of ONE node: a function (`fn`) or a builder step (`step`). There is no `goal`: a function node's standing
    goal, task line and context come from its FunctionSpec, never from an event. `task` and `context` are trace-only
    hints; `wait_on` (null, 'you', a function key or a builder id) and `tokens` {input, output} come from the map node
    and the server derives the node's stats from `calls`, `seconds` and `tokens` (S3-web-04). Optional parts that are
    None are left out of the line."""
    if (fn is None) == (step is None):
        _fail("node", "exactly one of fn or step")
    if fn is not None:
        _choice("fn", fn, FUNCTIONS)
        _choice("status", status, FUNCTION_STATUSES)
    else:
        _step_id("step", step)
        _choice("status", status, NODE_STATUSES)
    fields: dict[str, Any] = {"fn": fn} if fn is not None else {"step": step}
    fields.update(status=status, detail=_text("detail", detail), calls=_int("calls", calls),
                  seconds=_number("seconds", seconds))
    if task is not None:
        fields["task"] = _task_info(task)
    if context is not None:
        fields["context"] = context_strings(context)
    if wait_on is not None:
        fields["wait_on"] = _wait_on(wait_on)
    if tokens is not None:
        if not isinstance(tokens, Mapping) or set(tokens) != {"input", "output"}:
            _fail("tokens", "must be an object with exactly input and output")
        fields["tokens"] = {"input": _int("tokens.input", tokens["input"]), "output": _int("tokens.output", tokens["output"])}
    return _event("node", at, fields)


def step_event(*, step: str, name: str, status: str, parent: Optional[str] = None, handoff: Sequence[str] = (),
               reads: Sequence[str] = (), rework: Optional[str] = None, at: Optional[str] = None) -> dict:
    """One builder step or work box of the map. `handoff` lists the steps that read it, `reads` what it reads."""
    return _event("step", at, {"step": _step_id("step", step), "name": _text("name", name),
                               "parent": _text("parent", parent, nullable=True), "status": _choice("status", status, NODE_STATUSES),
                               "handoff": _list_of_text("handoff", handoff), "reads": _list_of_text("reads", reads),
                               "rework": _text("rework", rework, nullable=True)})


def _atom_body(atom: Any) -> dict:
    if not isinstance(atom, Mapping):
        _fail("atom", "must be an object")
    unknown = sorted(set(atom) - set(ATOM_KEYS))
    missing = [k for k in ATOM_REQUIRED if k not in atom]
    if unknown or missing:
        _fail("atom", "unknown fields " + ", ".join(unknown) if unknown else "missing fields " + ", ".join(missing))
    schema = _choice("atom.schema", atom["schema"], ATOM_SCHEMAS)
    atom_id = _text("atom.id", atom["id"], empty=False)
    if not ATOM_ID_RE.fullmatch(atom_id):
        _fail("atom.id", f"is not an atom id: {atom_id!r}")
    if not isinstance(atom["body"], Mapping):
        _fail("atom.body", "must be an object")
    return {"id": atom_id, "schema": schema, "goal": _text("atom.goal", atom["goal"]),
            "work_kind": _choice("atom.work_kind", atom["work_kind"], WORK_KINDS),
            "verify_template": _text("atom.verify_template", atom.get("verify_template"), nullable=True),
            "status": _choice("atom.status", atom["status"], ATOM_STATUSES[schema]),
            "attempt": _int("atom.attempt", atom["attempt"], maximum=3),
            "closed_by": _text("atom.closed_by", atom.get("closed_by"), nullable=True),
            "reason": _text("atom.reason", atom.get("reason"), nullable=True), "body": dict(atom["body"]),
            "ts_open": _int("atom.ts_open", atom["ts_open"]),
            "ts_closed": _int("atom.ts_closed", atom.get("ts_closed"), nullable=True)}


def atom_event(*, node: str, atom: Mapping, outcome: Optional[str] = None, card: Optional[Mapping] = None,
               ledger: Optional[Mapping] = None, at: Optional[str] = None) -> dict:
    """A work-atom transition or an `atom/1` view. `atom` holds exactly the twelve fields of the design (missing optional
    ones become null) and its status words depend on its schema. `outcome`, `card` and `ledger` are fields of the event
    next to `node` and `atom`; they exist for `work-atom/0.3` only: a function atom brings its Card with every transition
    and its LedgerRow (the library's, as an object) at the terminal one, so `ledger` stays null while the atom is open."""
    body = _atom_body(atom)
    fields: dict[str, Any] = {"node": _text("node", node, empty=False), "atom": body}
    if body["schema"] == "work-atom/0.3":
        fields["outcome"] = None if outcome is None else _choice("outcome", outcome, ATOM_OUTCOMES)
        fields["card"] = None if card is None else dict(_mapping("card", card))
        fields["ledger"] = None if ledger is None else dict(_mapping("ledger", ledger))
    elif outcome is not None or card is not None or ledger is not None:
        _fail("atom", "outcome, card and ledger belong to work-atom/0.3 only")
    return _event("atom", at, fields)


def _mapping(name: str, value: Any) -> Mapping:
    if not isinstance(value, Mapping):
        _fail(name, "must be an object")
    return value


def usage_event(*, fn: str, step: Optional[str], atom: Optional[str], provider: str, model: Optional[str], purpose: str,
                usd: Optional[float], tokens_in: Optional[int], tokens_out: Optional[int], seconds: float, ok: bool,
                how: str, call_ref: str, detail: Optional[Mapping] = None, at: Optional[str] = None) -> dict:
    """One model request (a failed one and the helper calls included). `atom` is the id the call is charged to; the engine
    host and the chat agent always set it (S4-fnodes-07). `call_ref` is `<run_id>:<call_no>` or `r:<request_id>`."""
    return _event("usage", at, {
        "fn": _text("fn", fn), "step": _text("step", step, nullable=True), "atom": _text("atom", atom, nullable=True),
        "provider": _text("provider", provider, empty=False), "model": _text("model", model, nullable=True),
        "purpose": _text("purpose", purpose, empty=False), "usd": _number("usd", usd, nullable=True),
        "tokens_in": _int("tokens_in", tokens_in, nullable=True), "tokens_out": _int("tokens_out", tokens_out, nullable=True),
        "seconds": _number("seconds", seconds), "ok": _bool("ok", ok), "how": _text("how", how, empty=False),
        "call_ref": _text("call_ref", call_ref, empty=False),
        "detail": None if detail is None else dict(_mapping("detail", detail))})


def heartbeat_event(*, at: Optional[str] = None) -> dict:
    """Proves the process lives, not that the run progresses (a daemon thread writes it every SUTRA_HEARTBEAT_S)."""
    return _event("heartbeat", at, {})


def run_ended_event(*, status: str, outcome: str, code: Optional[str] = None, at: Optional[str] = None) -> dict:
    """The last line. `code` is the ModelError code, 'start_failed' or 'internal', and only for a crashed run."""
    _choice("status", status, END_STATUSES)
    if code is not None and status != "crashed":
        _fail("code", "only a crashed run has a code")
    return _event("run.ended", at, {"status": status, "outcome": _text("outcome", outcome),
                                    "code": _text("code", code, nullable=True, empty=False)})


# ---- writing ---------------------------------------------------------------------------------------------------

def encode_line(obj: Mapping) -> bytes:
    """One JSON object and a newline: compact, ASCII only, no NaN. The newline never occurs inside the text."""
    return (json.dumps(obj, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


class EventWriter:
    """Appends events to `<run_dir>/events.jsonl` and engine detail to `<run_dir>/trace.jsonl`.

    The run directory must already exist: the orchestrator makes it and the engine never does. `events.jsonl` is opened at
    once (so a caller learns now whether it can write), `trace.jsonl` on the first trace line; both are created with mode
    0600 when missing. A line is written by one `os.write` while a lock is held, so lines from the run thread, the
    publisher and the heartbeat never mix; a short write is completed before the next line. After `run.ended` the
    events file refuses everything (that line is the last one); the trace stays open until `close()`."""

    EVENTS_NAME = "events.jsonl"
    TRACE_NAME = "trace.jsonl"

    def __init__(self, run_dir, *, clock: Callable[[], float] = time.time):
        self.run_dir = Path(run_dir)
        self.events_path = self.run_dir / self.EVENTS_NAME
        self.trace_path = self.run_dir / self.TRACE_NAME
        self._clock = clock
        self._lock = threading.RLock()       # re-entrant: a signal handler that fires mid-write can still write run.ended
        self._events_fd: Optional[int] = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        self._trace_fd: Optional[int] = None
        self._seq = 0
        self._ended = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def ended(self) -> bool:
        """True once `run.ended` was written."""
        return self._ended

    @staticmethod
    def _write_all(fd: int, data: bytes, write: Callable[[int, Any], int] = os.write) -> None:
        """Write all of `data`: a short write is completed by the next call (the lock is held, so no other line comes
        between), and a write that makes no progress is an error, not a loop."""
        view = memoryview(data)
        while view:
            written = write(fd, view)
            if written <= 0:
                raise OSError("write made no progress")
            view = view[written:]

    def emit(self, event: Mapping) -> dict:
        """Append one event; `at` is stamped when missing. Returns the dict that was written."""
        t = event.get("t") if isinstance(event, Mapping) else None
        if t not in EVENT_TYPES:
            raise EventError(f"t: must be one of {', '.join(EVENT_TYPES)}, not {t!r}")
        with self._lock:
            if self._closed:
                raise EventError("the writer is closed")
            if self._ended:
                raise EventError("run.ended was written: it is the last line of events.jsonl")
            at = event.get("at") or utc_iso(self._clock())
            if not isinstance(at, str) or not _AT_RE.fullmatch(at):
                raise EventError(f"at: must look like 2026-11-04T10:00:06Z, not {at!r}")
            line = {"t": t, "at": at, **{k: v for k, v in event.items() if k not in ("t", "at")}}
            self._write_all(self._events_fd, encode_line(line))
            if t == "run.ended":
                self._ended = True
        return line

    def trace(self, type: str, data: Optional[Mapping] = None) -> dict:
        """Append one detail line `{"seq", "at", "type", "data"}` to trace.jsonl. `seq` counts from 1 per writer."""
        if not isinstance(type, str) or not type:
            raise EventError("type: must be a non-empty string")
        with self._lock:
            if self._closed:
                raise EventError("the writer is closed")
            if self._trace_fd is None:
                self._trace_fd = os.open(self.trace_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            line = {"seq": self._seq + 1, "at": utc_iso(self._clock()), "type": type, "data": dict(data or {})}
            self._write_all(self._trace_fd, encode_line(line))
            self._seq += 1
        return line

    def close(self) -> None:
        """Close both files. Safe to call twice."""
        with self._lock:
            self._closed = True
            events_fd, self._events_fd = self._events_fd, None
            trace_fd, self._trace_fd = self._trace_fd, None
            for fd in (events_fd, trace_fd):
                if fd is not None:
                    os.close(fd)

    def __enter__(self) -> "EventWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class EventUsageSink:
    """The sink an engine process gives its model port: `record(row)` appends the `usage` event and returns a local
    counter (1 for the first row). `row` is a connector `UsageIn` or a plain mapping with the same keys (the mock path
    never imports the connectors): the event takes `fn, step, atom, provider, model, purpose, usd, tokens_in, tokens_out,
    seconds, ok, how, call_ref, detail` and ignores the rest (session, node, task and department ids belong to the
    server). `atom_id` of a UsageIn becomes `atom`. A row without an atom is charged to `default_atom` when one was given:
    the engine host passes the run overhead key, so no usage line leaves without an atom (S4-fnodes-07)."""

    def __init__(self, writer: EventWriter, *, default_atom: Optional[str] = None):
        self.writer = writer
        self.default_atom = default_atom
        self.count = 0
        self._lock = threading.Lock()

    @staticmethod
    def _as_dict(row: Any) -> dict:
        if isinstance(row, Mapping):
            return dict(row)
        dump = getattr(row, "model_dump", None)
        if callable(dump):
            return dump()
        raise TypeError("a usage row is a UsageIn or a mapping")

    def record(self, row: Any) -> int:
        data = self._as_dict(row)
        atom = data.get("atom")
        if atom is None:
            atom = data.get("atom_id")
        if atom is None:
            atom = self.default_atom
        event = usage_event(
            fn=data.get("fn") or "", step=data.get("step"), atom=atom, provider=data.get("provider"),
            model=data.get("model"), purpose=data.get("purpose"), usd=data.get("usd"), tokens_in=data.get("tokens_in"),
            tokens_out=data.get("tokens_out"), seconds=data.get("seconds"), ok=data.get("ok"), how=data.get("how"),
            call_ref=data.get("call_ref"), detail=data.get("detail"))
        self.writer.emit(event)
        with self._lock:
            self.count += 1
            return self.count
