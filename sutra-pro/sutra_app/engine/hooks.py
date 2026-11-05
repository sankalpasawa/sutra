"""Where the function nodes and the library plug into J2 (engine design 4.3).

The vendored `J2Run` calls these hooks at fixed places (patch P8): a run starts, a function's turn starts and ends, a
model call finishes, a message is posted, a run file is saved, the run's status changes or the run fails. A hook only
OBSERVES. The one exception is `system_addendum`, the only hook that can change a prompt, and it is empty unless a
`node_context_file` names text for a function. A hook that raises is caught by J2 and written to stderr, unless the
exception carries `fatal = True` or is named `RecordRejected` (the library's strict mode): then the run stops.

    NullHooks    does nothing (J2Run's default)
    EventHooks   writes the `say` events and the trace lines and wakes the publisher; the base class of the function-node
                 layer `fnodes.layer.FunctionNodeHooks` (WP E6)

`TurnInfo`, `CallInfo` and `TurnOutcome` are the records the layer reads; J2Run (WP E1) builds them in one place each.
"""
import importlib
import json
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from sutra_app.library.types import clip

from .events import EventWriter, say_event

__all__ = [
    "TurnInfo", "CallInfo", "TurnOutcome", "EngineHooks", "NullHooks", "EventHooks", "is_fatal", "load_validator",
    "DEFAULT_RECORDS_HOOK", "RECORD_MODES", "ADDENDUM_HEADING",
]

ADDENDUM_HEADING = "\n\n## Node context\n"
DEFAULT_RECORDS_HOOK = "sutra_app.library.records:gate_record"
RECORD_MODES = ("log", "strict")
_TARGET_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*")
WARNING_MAX = 500


class TurnInfo(BaseModel):
    """One function's turn, which is one work atom for the node layer. There is no goal field: it duplicated `step_label`."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    dept_id: str
    task_id: Optional[str] = None
    turn_no: int
    function: str                          # identity..audit, or "W-<n>"
    kind: Optional[str] = None             # handoff["kind"]: intake, propose, audit, limit, ...
    step: int
    step_label: str                        # e.g. "J2.b Adaptation proposes workflows"
    cycle: int
    stage: Optional[str] = None
    task: str                              # the handoff's "why", else its kind
    context: list[tuple[str, str]]         # J2Run._inputs(fn, "") pairs: charter, ledger, workflows, findings, chat


class CallInfo(BaseModel):
    """One finished `J2Run.call`. `atom` is read from the current tag (`llm.bind_atom`, S1-contracts-10)."""

    model_config = ConfigDict(extra="forbid")

    call_no: int
    function: str
    step: int
    stage: Optional[str] = None
    purpose: str
    model: Optional[str] = None
    provider: Optional[str] = None
    tokens: Optional[dict] = None
    usd: Optional[float] = None
    seconds: float
    session_id: Optional[str] = None
    inputs: list
    reply: Optional[dict] = None
    reason: Optional[str] = None
    atom: Optional[str] = None


class TurnOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: Literal["ok", "redirected", "paused", "error"]
    next: Optional[str] = None
    messages: list[int] = []
    calls: list[int] = []
    notes: list[str] = []


@runtime_checkable
class EngineHooks(Protocol):
    def run_started(self, spec: dict) -> None: ...

    def run_status(self, snap: dict) -> None: ...

    def turn_started(self, t: TurnInfo) -> None: ...

    def turn_finished(self, t: TurnInfo, o: TurnOutcome) -> None: ...

    def call_finished(self, c: CallInfo) -> None: ...

    def message_posted(self, m: dict, questions: Optional[list] = None) -> None: ...

    def record_saved(self, name: str, data: Any) -> list[str]: ...    # warnings only; never changes an outcome

    def run_error(self, code: str, message: str) -> None: ...

    def system_addendum(self, fn: str) -> str: ...                    # "" by default; the only hook that can change a prompt


class NullHooks:
    """Every hook does nothing; `record_saved` has no warnings and `system_addendum` is empty."""

    def run_started(self, spec: dict) -> None:
        return None

    def run_status(self, snap: dict) -> None:
        return None

    def turn_started(self, t: TurnInfo) -> None:
        return None

    def turn_finished(self, t: TurnInfo, o: TurnOutcome) -> None:
        return None

    def call_finished(self, c: CallInfo) -> None:
        return None

    def message_posted(self, m: dict, questions: Optional[list] = None) -> None:
        return None

    def record_saved(self, name: str, data: Any) -> list[str]:
        return []

    def run_error(self, code: str, message: str) -> None:
        return None

    def system_addendum(self, fn: str) -> str:
        return ""


def is_fatal(exc: BaseException) -> bool:
    """P8's rule: an exception stops the run when it carries `fatal = True` or its class is named `RecordRejected`."""
    return bool(getattr(exc, "fatal", False)) or type(exc).__name__ == "RecordRejected"


class EventHooks(NullHooks):
    """Writes what the hooks see: a `say` event for every message J2 posts (the owner's own excepted), `trace.jsonl` lines
    for turns, calls, saves and errors, and a `notify()` so the publisher wakes. It writes no `usage` and no `session`
    event: usage comes from the router's sink and the `session` event does not exist (S1-contracts-05, -09).

    `validator(name, data)` checks a record or a chat line (the library's `gate_record` through `load_validator`, or
    None for no checking). It returns a list of warnings or None; a warning, or an exception that is not fatal, becomes a
    `record.warning` trace line and never changes an outcome. A fatal exception (`is_fatal`: the strict mode of the
    library) is traced and raised again. `node_context_file` is JSON `{function: text}`, re-read on every call like the
    role files; its text for a function is appended to that function's system prompt."""

    def __init__(self, writer: EventWriter, notify: Callable[[], None], validator: Optional[Callable[[str, Any], Any]] = None,
                 node_context_file=None):
        self.writer = writer
        self.notify = notify
        self.validator = validator
        self.node_context_file = None if node_context_file is None else Path(node_context_file)
        self.last_error: Optional[tuple[str, str]] = None      # (code, message) of the last run_error
        self._addendum_seen: set[str] = set()

    def trace(self, type: str, data: Optional[Mapping] = None) -> dict:
        """One line of trace.jsonl; subclasses (the layer's `layer.error`, `atom.refused`) write theirs through here."""
        return self.writer.trace(type, data)

    def run_status(self, snap: dict) -> None:
        self.notify()

    def turn_started(self, t: TurnInfo) -> None:
        self.trace("turn.started", {"turn_no": t.turn_no, "function": t.function, "kind": t.kind, "step": t.step,
                                    "step_label": t.step_label, "cycle": t.cycle})
        self.notify()

    def turn_finished(self, t: TurnInfo, o: TurnOutcome) -> None:
        self.trace("turn.finished", {"turn_no": t.turn_no, "function": t.function, "result": o.result, "next": o.next,
                                     "messages": o.messages, "calls": o.calls, "notes": [clip(n, WARNING_MAX) for n in o.notes]})
        self.notify()

    def call_finished(self, c: CallInfo) -> None:
        self.trace("call.finished", {"call_no": c.call_no, "function": c.function, "step": c.step, "stage": c.stage,
                                     "purpose": c.purpose, "model": c.model, "provider": c.provider, "tokens": c.tokens,
                                     "usd": c.usd, "seconds": c.seconds, "session_id": c.session_id, "atom": c.atom})
        self.notify()

    def message_posted(self, m: dict, questions: Optional[list] = None) -> None:
        if m.get("who") != "user":
            asking = m.get("act") == "ASK_REQUESTER"
            self.writer.emit(say_event(id=m.get("id"), who=m.get("who"), text=m.get("text"), to_user=bool(m.get("to_user")),
                                       act=m.get("act"), pause=m.get("pause"), questions=questions if asking else None,
                                       next=m.get("next")))
        self._validate("chat.jsonl", m)
        self.notify()

    def record_saved(self, name: str, data: Any) -> list[str]:
        warnings = self._validate(name, data)
        self.trace("record.saved", {"name": name, "warnings": len(warnings)})
        self.notify()
        return warnings

    def run_error(self, code: str, message: str) -> None:
        self.last_error = (code, message)
        self.trace("run.error", {"code": code, "message": clip(str(message), WARNING_MAX)})
        self.notify()

    def system_addendum(self, fn: str) -> str:
        path = self.node_context_file
        if path is None:
            return ""
        try:
            with open(path, encoding="utf-8") as f:
                texts = json.load(f)
            if not isinstance(texts, Mapping):
                raise ValueError("the file must hold a JSON object {function: text}")
        except FileNotFoundError:
            return ""
        except (OSError, ValueError) as exc:           # a bad file must never break a prompt; say so once per message
            note = clip(f"{type(exc).__name__}: {exc}", WARNING_MAX)
            if note not in self._addendum_seen:
                self._addendum_seen.add(note)
                self.trace("addendum.error", {"file": str(path), "error": note})
            return ""
        text = texts.get(fn)
        return ADDENDUM_HEADING + text if isinstance(text, str) and text.strip() else ""

    def _validate(self, name: str, data: Any) -> list[str]:
        if self.validator is None:
            return []
        try:
            out = self.validator(name, data)
        except Exception as exc:
            warning = clip(f"{type(exc).__name__}: {exc}", WARNING_MAX)
            self.trace("record.warning", {"name": name, "warning": warning, "fatal": is_fatal(exc)})
            if is_fatal(exc):
                raise
            return [warning]
        warnings = [clip(str(w), WARNING_MAX) for w in out] if isinstance(out, (list, tuple)) else []
        for warning in warnings:
            self.trace("record.warning", {"name": name, "warning": warning, "fatal": False})
        return warnings


def load_validator(environ: Optional[Mapping[str, str]] = None) -> Optional[Callable[[str, Any], Any]]:
    """The `validator` of `EventHooks`, from the environment: `SUTRA_RECORDS_HOOK` is `package.module:function` (default
    `sutra_app.library.records:gate_record`, used when that module exists) and `SUTRA_RECORDS` is `log` (default) or
    `strict`. The function is called as `function(name, data, mode=<mode>)`. Returns None when the default module is not
    there (yet). A hook the owner named that cannot be imported, or an unknown mode, is an error, not a silent skip."""
    env = os.environ if environ is None else environ
    mode = (env.get("SUTRA_RECORDS") or "log").strip().lower()
    if mode not in RECORD_MODES:
        raise ValueError(f"SUTRA_RECORDS must be one of {', '.join(RECORD_MODES)}, not {mode!r}")
    named = (env.get("SUTRA_RECORDS_HOOK") or "").strip()
    target = named or DEFAULT_RECORDS_HOOK
    if not _TARGET_RE.fullmatch(target):
        raise ValueError(f"SUTRA_RECORDS_HOOK must look like package.module:function, not {target!r}")
    module_name, _, attr = target.partition(":")
    try:
        function = getattr(importlib.import_module(module_name), attr)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""      # the default may be a module that has not been written yet; anything else is an error
        if not named and missing and (module_name == missing or module_name.startswith(missing + ".")):
            return None
        raise ImportError(f"{target}: {exc}") from exc
    except (ImportError, AttributeError) as exc:
        raise ImportError(f"{target}: {exc}") from exc

    def validate(name: str, data: Any) -> Any:
        return function(name, data, mode=mode)

    return validate
