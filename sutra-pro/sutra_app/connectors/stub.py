"""`StubConnector` and `ReplyBook`: the connector that answers without a process (connectors design 3.7, CD11, CD18, D36).

It is a `ModelConnector` whose spawn is replaced by a deterministic reply, so it inherits everything else of the base: the
one-shot calls, the JSON strategy with its repair rounds, the chat sessions (work dir and `session.json`), the hooks the
Router listens to (`before_call` / `after_call` around every call, a failed one included) and the connector's usage total.
No child process is started, nothing is read from the environment except `STUDIO_MOCK_DELAY` (J2's `llm.py:53`).

A reply is chosen in this order (3.7); the name of the rule that answered is kept in `StubConnector.calls`:

    1. `scripted`      the request's `scripted()` callable (J2's `mock`, `llm.py:73-74`)
    2. `book`         `ReplyBook` entry `(function, stage)` of the call's tag
    3. `book`         `(function, "*")`
    4. `book`         `("*", "*")`
    5. `builtin`      a request with a schema: `example_from_schema(schema)` as JSON; a JSON request without one: `{}` (a repair round always has a schema);
                      text: `"[stub] "` + the first 60 characters of the prompt

Every reply is text, returned unstripped. Usage is `provider "stub"`, `model "scripted"`, `usd 0.0`, `usd_basis "none"`, tokens =
characters // 4 (the same numbers as `engine.llm.ScriptedPort`, its twin). With `delay > 0` the text arrives as 30
`text_delta` events spread over `delay` seconds (J2 `_stream_mock`); without a delay it is one event. `fail_next(code)` makes the
next calls raise any ConnectorError, for Router tests. A chat session keeps its transcript in memory (`transcript(session_id)`).
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import math
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Iterator, Mapping, Optional, Sequence

from pydantic import BaseModel

from .base import CallInfo, CallRecord, Hooks, LineParser, ModelConnector, TurnPlan
from .errors import CallCancelledError, ConnectorError, ERROR_CLASSES, ProviderError, error_for_code
from .models import (
    AuthStatus, Capabilities, ConnectorConfig, ConnectorEvent, Effort, JsonResult, Message, ModelInfo,
    SessionSpec, SessionState, TurnResult, Usage,
)
from .process import Command, ProcessRunner
from .schema import example_from_schema, to_json_schema

__all__ = ["StubConnector", "ReplyBook", "StubCall", "STUB_MODEL", "CHUNKS", "PROMPT_ECHO_CHARS", "WILDCARD"]

STUB_MODEL = "scripted"
CHUNKS = 30                  # a delayed reply streams in this many pieces (J2 `_stream_mock`, llm.py:191-198)
PROMPT_ECHO_CHARS = 60       # the built-in text reply echoes this much of the prompt
WILDCARD = "*"
_EFFORTS: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")

# what the current request carries past the base class's signatures: the schema (also when the base sends none, e.g. a schema
# over 100,000 characters or `force_prompted`) and the request's `scripted` callable. A ContextVar, so threads do not mix them.
_SCHEMA: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("stub_schema", default=None)
_SCRIPTED: contextvars.ContextVar[Optional[Callable[[], Any]]] = contextvars.ContextVar("stub_scripted", default=None)


def _clean_delay(value: Any) -> float:
    """Seconds as a finite number >= 0; anything else is no delay (same rule as `engine.llm`)."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    return seconds if math.isfinite(seconds) and seconds > 0 else 0.0


def _reply_text(value: Any) -> str:
    """A reply as text: a string stays as it is (unstripped), anything else is JSON."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise TypeError(f"a stub reply is text or JSON-serialisable: {e}") from None


# ---- ReplyBook ----------------------------------------------------------------------------------------------------------------

class ReplyBook:
    """Canned replies keyed by `(function, stage)`, the two fields of the call's tag that say what a call is for.

    A key part may be `"*"`. A lookup tries the exact pair, then `(function, "*")`, then `("*", "*")`. A call without a tag
    has function `""` and stage `""`. A reply is a string, any JSON value (stored as its JSON text) or a callable with no
    arguments that returns one of those (it runs at every lookup, so it can hand out a sequence).
    """

    def __init__(self, entries: Optional[Mapping[tuple[str, str], Any]] = None) -> None:
        self._entries: dict[tuple[str, str], Any] = {}
        for key, reply in (entries or {}).items():
            self.set(key[0], key[1], reply)

    def set(self, function: str, stage: str, reply: Any) -> "ReplyBook":
        """Add or replace one entry; returns the book, so calls chain."""
        for name, part in (("function", function), ("stage", stage)):
            if not isinstance(part, str):
                raise TypeError(f"{name} must be a string (use '*' for any), not {type(part).__name__}")
        if not callable(reply):
            _reply_text(reply)               # refuse an unserialisable reply now, not in the middle of a run
        self._entries[(function, stage)] = reply
        return self

    def lookup(self, function: str, stage: str) -> tuple[bool, Any]:
        """`(True, reply)` for the first matching entry in the order of the class docstring, else `(False, None)`."""
        for key in ((function, stage), (function, WILDCARD), (WILDCARD, WILDCARD)):
            if key in self._entries:
                return True, self._entries[key]
        return False, None

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(frozen=True)
class StubCall:
    """One answered (or failed) call, for tests: what was asked and which rule of 3.7 answered."""

    kind: str                       # text | json | repair | chat
    prompt: str
    system: str
    function: str
    stage: str
    session_id: Optional[str]
    schema: Optional[dict]
    rule: str                       # scripted | book | builtin | failed
    reply: Optional[str]            # None for a failed call
    code: Optional[str] = None      # the error code of a failed call


# ---- the connector ------------------------------------------------------------------------------------------------------------

class StubConnector(ModelConnector):
    name: ClassVar = "stub"
    # native_schema is True so the base hands the schema to the spawn (the stub reads it to build its example); nothing is sent anywhere.
    capabilities: ClassVar[Capabilities] = Capabilities(native_schema=True, resume=True, images=True, partials=True, mcp=False)
    default_model: ClassVar[str] = STUB_MODEL

    def __init__(self, cfg: ConnectorConfig, runner: Optional[ProcessRunner] = None, clock: Callable[[], float] = time.time,
                 hooks: Optional[Hooks] = None, *, book: Optional[ReplyBook] = None, delay: Optional[float] = None) -> None:
        super().__init__(cfg, runner, clock, hooks)
        self.book = book if book is not None else ReplyBook()
        self.delay = _clean_delay(os.getenv("STUDIO_MOCK_DELAY", "0")) if delay is None else _clean_delay(delay)
        self._failures: deque[tuple[str, str, dict]] = deque()
        self._calls: list[StubCall] = []
        self._transcripts: dict[str, list[Message]] = {}
        self._cancel: dict[str, threading.Event] = {}

    # ---- test controls -------------------------------------------------------------------------------------------------------
    def fail_next(self, code: str, times: int = 1, message: str = "", **kw: Any) -> None:
        """The next `times` spawns (a repair round counts) raise the error of `code` (any key of `ERROR_CLASSES`), `before_call`
        and `after_call` included. `kw` goes to the error (`detail`, `resets_at`, ...). Failures are used in the order given."""
        if code not in ERROR_CLASSES:
            raise ValueError(f"unknown error code {code!r}: use one of {', '.join(sorted(ERROR_CLASSES))}")
        if isinstance(times, bool) or not isinstance(times, int) or times < 1:
            raise ValueError("times must be a positive integer")
        with self._lock:
            self._failures.extend([(code, message, dict(kw))] * times)

    @property
    def calls(self) -> list[StubCall]:
        with self._lock:
            return list(self._calls)

    def transcript(self, session_id: str) -> list[Message]:
        """The messages of a chat session since `start()`: each turn adds the user's and the stub's."""
        with self._lock:
            return list(self._transcripts.get(session_id, []))

    # ---- the hooks the base requires; a stub has no process ------------------------------------------------------------------
    def build_command(self, plan: TurnPlan) -> Command:
        raise ProviderError("the stub connector starts no process", provider=self.name)

    def new_parser(self, plan: TurnPlan) -> LineParser:
        raise ProviderError("the stub connector reads no process output", provider=self.name)

    def probe_auth(self) -> AuthStatus:
        return AuthStatus(provider="stub", installed=True, version="stub", signed_in=True, method="none", billing="unknown",
                          detail="the stub answers from a script; no model is called", checked_at=self._clock())

    def probe_flags(self) -> dict[str, bool]:
        return {}

    def models(self) -> list[ModelInfo]:
        return [ModelInfo(slug=STUB_MODEL, label="Scripted (stub)", efforts=list(_EFFORTS), context_window=None, images=True,
                          listed=True)]

    def resolve_model(self, requested: Optional[str]) -> str:
        return STUB_MODEL          # the policy's model names mean nothing here: the row always says "scripted"

    # ---- request context: the schema and `scripted` that the base signatures do not carry ------------------------------------
    @contextlib.contextmanager
    def _request(self, schema: Optional[dict], scripted: Optional[Callable[[], Any]]) -> Iterator[None]:
        a, b = _SCHEMA.set(schema), _SCRIPTED.set(scripted)
        try:
            yield
        finally:
            _SCRIPTED.reset(b)
            _SCHEMA.reset(a)

    def call_text(self, prompt: str, *, scripted: Optional[Callable[[], Any]] = None, **kw: Any) -> TurnResult:
        """As the base, plus `scripted`: the request's `scripted()` callable (rule 1)."""
        with self._request(None, scripted):
            return super().call_text(prompt, **kw)

    def call_json_result(self, prompt: str, tools: Sequence[str] = (), schema: "type[BaseModel] | dict | None" = None,
                         *args: Any, scripted: Optional[Callable[[], Any]] = None, **kw: Any) -> JsonResult:
        """As the base, plus `scripted`. `how` is always `"stub"` (3.7), whatever path the base took."""
        schema_dict = to_json_schema(schema) if schema is not None else None
        with self._request(schema_dict, scripted):
            result = super().call_json_result(prompt, tools, schema, *args, **kw)
        return result.model_copy(update={"how": "stub"})

    # ---- sessions ------------------------------------------------------------------------------------------------------------
    def start(self, spec: SessionSpec) -> SessionState:
        state = super().start(spec)
        with self._lock:
            self._transcripts[spec.session_id] = []
        return state

    def forget(self, s: SessionState) -> None:
        with self._lock:
            self._transcripts.pop(s.session_id, None)

    def stop(self, s: SessionState) -> bool:
        """Ends a streaming turn that is waiting out its delay; False when the session is idle."""
        with self._lock:
            event = self._cancel.get(s.session_id)
        if event is None:
            return False
        event.set()
        return True

    def _commit_turn(self, s: SessionState, plan: TurnPlan, turn: TurnResult, parser: Optional[LineParser]) -> None:
        super()._commit_turn(s, plan, turn, parser)
        with self._lock:
            history = self._transcripts.setdefault(s.session_id, [])
            history.append(Message(role="user", text=plan.prompt, images=list(plan.images)))
            history.append(Message(role="assistant", text=turn.text))

    # ---- one spawn, without a process ---------------------------------------------------------------------------------------
    def _spawn(self, plan: TurnPlan, hooks: Hooks, box: dict) -> Iterator[ConnectorEvent]:
        info = CallInfo(provider=self.name, kind=plan.kind, model=plan.model, effort=plan.effort, ctx=plan.ctx,
                        session_id=plan.session.session_id if plan.session else None, native=plan.schema is not None,
                        attempt=plan.attempt, max_budget_usd=plan.max_budget_usd)
        hooks.before_call(info)                     # may raise EnvelopeExceededError, as for a real connector
        started = self._clock()
        error: Optional[ConnectorError] = None
        turn: Optional[TurnResult] = None
        key = plan.session.session_id if plan.session is not None else None
        cancel = threading.Event()
        schema = plan.schema if plan.schema is not None else _SCHEMA.get()
        try:
            with self._lock:
                failure = self._failures.popleft() if self._failures else None
            if failure is not None:
                code, message, kw = failure
                self._log(plan, schema, "failed", None, code)
                raise error_for_code(code, message, provider=self.name, **kw)
            text, rule = self._resolve(plan, schema)
            self._log(plan, schema, rule, text, None)
            if key is not None:
                with self._lock:
                    self._cancel[key] = cancel
            try:
                yield ConnectorEvent(kind="started", data={"session_id": plan.provider_session_id, "model": STUB_MODEL,
                                                           "tools": list(plan.tools), "mcp_servers": []})
                steps = CHUNKS if self.delay else 1
                for i in range(1, steps + 1):
                    piece = text[len(text) * (i - 1) // steps:len(text) * i // steps]
                    if piece:
                        yield ConnectorEvent(kind="text_delta", data={"text": piece, "kind": "text"})
                    if self.delay and cancel.wait(self.delay / steps):
                        raise CallCancelledError("the stub reply was stopped", provider=self.name)
                yield ConnectorEvent(kind="text", data={"text": text})
            finally:
                if key is not None:
                    with self._lock:
                        if self._cancel.get(key) is cancel:
                            del self._cancel[key]
            turn = TurnResult(
                text=text, provider="stub", model=STUB_MODEL,
                provider_session_id=self._provider_session(plan), usage=Usage(
                    input_tokens=len(plan.system + plan.prompt) // 4, output_tokens=len(text) // 4),
                usd=0.0, usd_basis="none", duration_ms=max(0, round((self._clock() - started) * 1000)))
        except ConnectorError as e:
            error = e
            raise
        finally:
            if error is None and turn is None:      # the consumer stopped reading, or a non-connector exception (a bad scripted reply)
                error = CallCancelledError("the call was abandoned before it finished", provider=self.name)
            hooks.after_call(CallRecord(
                info=info, ok=error is None, code=None if error is None else error.code, error=error,
                turn=turn if error is None else None, seconds=max(0.0, self._clock() - started),
                usage=turn.usage if turn is not None else Usage(), usd=turn.usd if turn is not None else None,
                exit_code=None, native_schema_sha=None, cli_version=None))
        with self._lock:
            self._total = self._total + turn.usage
        box["turn"] = turn

    @staticmethod
    def _provider_session(plan: TurnPlan) -> Optional[str]:
        """A chat turn keeps its provider session id; a first turn gets one derived from the session id (deterministic)."""
        if plan.session is None:
            return None
        if plan.provider_session_id and plan.resume:
            return plan.provider_session_id
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sutra-stub:{plan.session.session_id}"))

    def _resolve(self, plan: TurnPlan, schema: Optional[dict]) -> tuple[str, str]:
        """`(text, rule)` by the order of the module docstring."""
        scripted = _SCRIPTED.get()
        if scripted is not None:
            text = scripted()
            if not isinstance(text, str):
                raise TypeError("a scripted reply is text")
            return text, "scripted"
        found, reply = self.book.lookup(plan.ctx.tag.function, plan.ctx.tag.stage or "")
        if found:
            return _reply_text(reply() if callable(reply) else reply), "book"
        if schema is not None:
            return json.dumps(example_from_schema(schema), ensure_ascii=False), "builtin"
        if plan.kind == "json":
            return "{}", "builtin"
        return "[stub] " + plan.prompt[:PROMPT_ECHO_CHARS], "builtin"

    def _log(self, plan: TurnPlan, schema: Optional[dict], rule: str, reply: Optional[str], code: Optional[str]) -> None:
        tag = plan.ctx.tag
        call = StubCall(kind=plan.kind, prompt=plan.prompt, system=plan.system, function=tag.function, stage=tag.stage or "",
                        session_id=plan.session.session_id if plan.session else None, schema=schema, rule=rule, reply=reply,
                        code=code)
        with self._lock:
            self._calls.append(call)
