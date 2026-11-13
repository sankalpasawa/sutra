"""J2's `llm` module, kept at its call syntax and rebuilt on a `ModelPort` (engine design 4.2, D17).

J2 called a model provider here. This shim sends every call through one seam instead: `ask(...)` builds a
`CompletionRequest` with a `CallTag` and hands it to the configured `ModelPort` (the connector layer's router, or
`ScriptedPort`, J2's mock mode). The five J2 call sites keep their syntax (they only gain a `tagged(...)` block); the
host calls `configure(...)` BEFORE the vendored `j2` module is imported because J2 reads `MOCK` at import.

    ask            J2's signature (`timeout` included) plus a keyword `tag`; the reply text, stripped (unstripped in mock mode, as J2)
    CallTimeout    what `ask` raises when the port reports a timeout (J2's `except llm.CallTimeout`, D170)
    can_read_files False: the agents' file tools are bound to the owner's working folder, never to a run folder (D170)
    LAST_META      cleared before each call, then filled from the result (model, provider, tokens, usd, duration_ms,
                   structured); a mock call leaves it empty, as J2's did
    MOCK, PROVIDER, MODEL    what J2 reads; fixed by `configure`. In mock mode PROVIDER and MODEL are None, as in J2
    configure      choose the port, mock mode and the base tag (run, department, task)
    tagged         `with tagged(function="audit", step=7): ask(...)`: nested blocks merge over each other and the base tag
    bind_atom      the atom id a call is charged to when its own tag names none (S4-fnodes-07)
    ScriptedPort   J2's mock mode as a ModelPort, with the same usage row as the stub connector
    extract_json, close_json   the library's: ONE copy (S2-models-12). extract_html, partial_html: verbatim from J2

There is no silent offline mode (D36): with no port and mock mode off, `ask` raises `NoModelAvailable`. J2's own providers
(the Anthropic API, Gemini, the `claude -p` runner) are gone; the router chooses models. The engine never retries a failed
call and never sends an allowance (S1-contracts-06): the envelope belongs to `J2Run`.
"""
import itertools
import math
import os
import re
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

from sutra_app.library.replies import close_json, extract_json     # re-exported: one copy, tested in test_lib_replies.py
from sutra_app.library.types import clip

from .port import (
    CallTag, CompletionRequest, CompletionResult, ModelError, ModelPort, NoModelAvailable, PortInfo, PreflightResult,
    UsageRecorder,
)

__all__ = [
    "ask", "CallTimeout", "can_read_files", "configure", "tagged", "current_tag", "bind_atom", "bound_atom", "env_mock", "step_label", "ScriptedPort",
    "EmptyReply", "extract_json", "close_json", "extract_html", "partial_html", "LAST_META", "MOCK", "PROVIDER", "MODEL",
    "MOCK_ENV", "TAG_HOOKS", "PROGRESS_HOOKS",
]

MOCK_ENV = ("SUTRA_MOCK", "SUTRA_OFFLINE", "STUDIO_MOCK")     # any of them set to "1" means mock mode (D36)


def env_mock(environ: Optional[Mapping[str, str]] = None) -> bool:
    """True when SUTRA_MOCK, SUTRA_OFFLINE or STUDIO_MOCK is exactly "1" (J2 compared STUDIO_MOCK the same way)."""
    env = os.environ if environ is None else environ
    return any(env.get(name) == "1" for name in MOCK_ENV)


# Capability hooks (engine/capabilities, D126), filled by `capabilities.install` once per process and read on EVERY call of every
# output, so a capability reaches every agent with no change to a caller. A tag hook is `hook(tag) -> dict` (fields to add to the tag:
# only fields that are still empty on it are taken); a progress hook is `hook(tag, event) -> None`. A hook that raises is skipped with one
# stderr line: a capability can add to a call, never stop it.
TAG_HOOKS: list = []
PROGRESS_HOOKS: list = []

LAST_META: dict = {}                    # one model call at a time per process, so a plain dict is safe
MOCK: bool = env_mock()
PROVIDER: Optional[str] = None
MODEL: Optional[str] = None
_PORT: Optional[ModelPort] = None
_DEFAULT_PORT: Optional["ScriptedPort"] = None     # mock mode with no port configured: made on first use
_BASE_TAG: CallTag = CallTag()
_BOUND_ATOM: Optional[str] = None
_TAG: ContextVar[Optional[CallTag]] = ContextVar("sutra_engine_call_tag", default=None)


class CallTimeout(RuntimeError):
    """J2's own name for a model call stopped at its time limit (`J2Run.call` retries it once). Raised by `ask` for a
    `ModelError` with code `timeout`; the original is `__cause__`. D170."""


def can_read_files() -> bool:
    """J2 asks whether the agent can read files at a path; here it never can: the agents' file tools are bound to the owner's
    working folder, never to a run folder, so J2's "read the rest at <path>" hint would point at nothing (D170)."""
    return False


class EmptyReply(ModelError):
    """A real model answered with no text. J2's providers treated that as a failed call too."""

    code = "empty_reply"


def _as_tag(tag: Any) -> CallTag:
    if tag is None:
        return CallTag()
    if isinstance(tag, CallTag):
        return tag
    if isinstance(tag, Mapping):
        return CallTag(**tag)
    raise TypeError("a tag is a CallTag or a mapping of its fields")


def configure(port: Optional[ModelPort] = None, *, mock: Optional[bool] = None,
              base_tag: Optional[CallTag | Mapping] = None) -> None:
    """Set the model port, mock mode and the tag every call starts from. Each call replaces the whole configuration:
    `configure()` is the environment's default (mock only if `env_mock()`, no port, an empty tag).

    mock: True/False, else the port's `describe().mock`, else `env_mock()`. In mock mode `PROVIDER` and `MODEL` stay None
    (J2 wrote null provider and model into its run files in mock mode); otherwise they come from `port.describe()`.
    With `mock` true and no port, `ask` uses a `ScriptedPort` made on first use."""
    global _PORT, _BASE_TAG, MOCK, PROVIDER, MODEL
    info: Optional[PortInfo] = port.describe() if port is not None else None
    if mock is not None:
        is_mock = bool(mock)
    elif info is not None:
        is_mock = info.mock
    else:
        is_mock = env_mock()
    _PORT = port
    _BASE_TAG = _as_tag(base_tag)
    MOCK = is_mock
    PROVIDER, MODEL = (None, None) if is_mock or info is None else (info.provider, info.model)


def current_tag() -> CallTag:
    """The tag a call gets now: the innermost `tagged` block's, else the base tag from `configure`."""
    return _TAG.get() or _BASE_TAG


@contextmanager
def tagged(**fields: Any) -> Iterator[CallTag]:
    """`with tagged(function="audit", step=7, call_no=12): ...` Fields not named keep the enclosing block's values (or the
    base tag's): a helper call inside a function's turn names only its purpose and role. Unknown or invalid fields raise
    at once. The tag is restored when the block ends, also by an exception."""
    tag = CallTag.model_validate({**current_tag().model_dump(), **fields})
    token = _TAG.set(tag)
    try:
        yield tag
    finally:
        _TAG.reset(token)


def bind_atom(atom_id: Optional[str]) -> None:
    """The atom a call is charged to when its tag has none. The host binds the run overhead key at `run_started`; the layer
    binds the turn's atom after `open_atom` and the overhead key again at `turn_finished` and on every run end path. A tag
    that names an atom (a builder's J2 id) wins. `None` clears the binding and is for tests: a process makes one model call
    at a time, so a module-level binding is safe."""
    global _BOUND_ATOM
    if atom_id is not None and (not isinstance(atom_id, str) or not atom_id):
        raise ValueError("an atom id is a non-empty string, or None to clear the binding")
    _BOUND_ATOM = atom_id


def bound_atom() -> Optional[str]:
    return _BOUND_ATOM


def _active_port() -> ModelPort:
    global _DEFAULT_PORT
    if _PORT is not None:
        return _PORT
    if MOCK:
        if _DEFAULT_PORT is None:
            _DEFAULT_PORT = ScriptedPort()
        return _DEFAULT_PORT
    raise NoModelAvailable("no model is available: no port was configured (llm.configure) and mock mode is off")


def _hook_failed(kind: str, hook: Any, exc: BaseException) -> None:
    name = getattr(hook, "capability", None) or getattr(hook, "__name__", "hook")
    print(f"{kind} hook {name} failed: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)


def _hooked_tag(tag: CallTag) -> CallTag:
    """`tag` with what each tag hook adds. A field already set on the tag (by J2, by an earlier hook) is never replaced, and a field the
    tag does not have is ignored: `workspace` is empty until a capability sets it, whatever any other capability says."""
    for hook in tuple(TAG_HOOKS):
        try:
            extra = hook(tag) or {}
            fill = {name: value for name, value in extra.items()
                    if name in CallTag.model_fields and getattr(tag, name) == CallTag.model_fields[name].default}
            if fill:
                tag = CallTag.model_validate({**tag.model_dump(), **fill})
        except Exception as exc:  # noqa: BLE001
            _hook_failed("tag", hook, exc)
    return tag


def _hooked_progress(tag: CallTag, on_progress: Optional[Callable[[dict], None]]) -> Optional[Callable[[dict], None]]:
    """`on_progress` and every progress hook as one callback; `on_progress` unchanged (maybe None) when no hook is installed, so a
    process without such a capability asks for no partials it did not ask for before."""
    hooks = tuple(PROGRESS_HOOKS)
    if not hooks:
        return on_progress

    def composed(event: dict) -> None:
        for hook in hooks:
            try:
                hook(tag, event)
            except Exception as exc:  # noqa: BLE001
                _hook_failed("progress", hook, exc)
        if on_progress is not None:
            on_progress(event)
    return composed


def ask(system, user, mock, max_tokens=1500, effort="high", on_progress=None, json_mode=False, images=None,
        schema=None, timeout=None, *, tag=None) -> str:
    """One model call. `mock` is J2's scripted reply (a callable); only the stub path calls it. `images` are PNG paths and
    the ones that do not exist are dropped. `schema` is a JSON Schema the reply should follow (advisory: the engine checks
    the reply itself). `timeout` is J2's per-call limit in seconds (D170): it becomes `CompletionRequest.timeout_s`, which the
    router honours and cuts to the envelope's deadline; a `ModelError` with code `timeout` is re-raised as `CallTimeout`.
    `tag` names the call; default `current_tag()`. Raises a `ModelError` when the port does."""
    images = [p for p in images or [] if p and os.path.exists(p)]
    LAST_META.clear()
    port = _active_port()
    tag = current_tag() if tag is None else _as_tag(tag)
    if tag.atom is None and _BOUND_ATOM is not None:
        tag = tag.model_copy(update={"atom": _BOUND_ATOM})
    tag = _hooked_tag(tag)
    request = CompletionRequest(system=system, user=user, max_tokens=max_tokens, effort=effort, json_mode=json_mode,
                                images=images, json_schema=schema, timeout_s=timeout or None, tag=tag, allowance=None,
                                scripted=mock)
    try:
        result = port.complete(request, _hooked_progress(tag, on_progress))
    except ModelError as exc:
        if exc.code == "timeout":
            raise CallTimeout(str(exc)) from exc
        raise
    if MOCK:                          # J2 reported nothing for a mock reply, and returned it as it was
        return result.text
    meta = {"model": result.model, "provider": result.provider, "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens, "usd": result.usd, "duration_ms": result.duration_ms,
            "structured": result.structured}
    LAST_META.update({key: value for key, value in meta.items() if value is not None})
    if not result.text.strip():
        raise EmptyReply(f"{result.provider or 'the model'} returned no text")
    return result.text.strip()


# ---- J2's mock mode as a port -----------------------------------------------------------------------------------

def step_label(tag: CallTag) -> Optional[str]:
    """The `step` of a usage row: a builder's workflow id (W-3), else J2's step label for the number 1..8 (J2.a .. J2.h),
    else None."""
    if re.fullmatch(r"W-[0-9]+", tag.function):
        return tag.function
    return "J2." + "abcdefgh"[tag.step - 1] if 1 <= tag.step <= 8 else None


def _clean_delay(value: Any) -> float:
    """Seconds as a finite number >= 0; anything else is no delay."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    return seconds if math.isfinite(seconds) and seconds > 0 else 0.0


def _mock_delay() -> float:
    """STUDIO_MOCK_DELAY: seconds a mock reply takes, to try the progress UI (J2's llm.py:53). A bad value is no delay."""
    return _clean_delay(os.getenv("STUDIO_MOCK_DELAY", "0"))


class ScriptedPort(ModelPort):
    """J2's mock mode as a `ModelPort`, without the connectors package. `complete` returns `req.scripted()` (a built-in
    canned reply when it is None), streamed as `{"chars", "text"}` progress events (30 chunks when a delay is set, one
    otherwise; STUDIO_MOCK_DELAY or `delay`). For every request, a failed one included, it hands ONE usage row to
    `usage_sink.record(row)`, the same row the stub connector builds: provider `stub`, model `scripted`, tokens = characters
    / 4, usd 0.0, how `stub`. The row is a plain dict with the keys of the connector's `UsageIn`. `close()` ends a request
    that is waiting out its delay, like killing a CLI child."""

    def __init__(self, usage_sink: Optional[UsageRecorder] = None, *, delay: Optional[float] = None):
        self.usage_sink = usage_sink
        self.delay = _mock_delay() if delay is None else _clean_delay(delay)
        self._requests = itertools.count(1)
        self._closed = threading.Event()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def describe(self) -> PortInfo:
        return PortInfo(provider=None, model=None, mock=True)

    def preflight(self) -> PreflightResult:
        return PreflightResult(ok=True, message="mock mode: no model is called", providers=[])

    def close(self) -> None:
        self._closed.set()

    def complete(self, req: CompletionRequest, on_progress: Optional[Callable[[dict], None]] = None) -> CompletionResult:
        started = time.monotonic()
        request_id = next(self._requests)
        text = ""
        try:
            if self._closed.is_set():
                raise ModelError("the model port was closed")
            text = self._reply(req)
            self._stream(text, on_progress)
        except Exception as exc:
            self._record(req, request_id, started, None, getattr(exc, "code", type(exc).__name__))
            raise
        self._record(req, request_id, started, text, None)
        return CompletionResult(text=text, model="scripted", provider="stub", input_tokens=self._tokens(req.system + req.user),
                                output_tokens=self._tokens(text), usd=0.0,
                                duration_ms=round((time.monotonic() - started) * 1000))

    @staticmethod
    def _tokens(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def _reply(req: CompletionRequest) -> str:
        if req.scripted is not None:
            text = req.scripted()
            if not isinstance(text, str):
                raise TypeError("a scripted reply is text")
            return text
        if req.json_schema is not None or req.json_mode:
            return "{}"
        return "[stub] " + req.user[:60]

    def _stream(self, text: str, on_progress: Optional[Callable[[dict], None]]) -> None:
        steps = 30 if self.delay else 1
        for i in range(1, steps + 1):
            part = text[:len(text) * i // steps]
            if on_progress is not None:
                on_progress({"chars": len(part), "text": part})
            if self.delay and self._closed.wait(self.delay / steps):
                raise ModelError("the model port was closed")

    def _record(self, req: CompletionRequest, request_id: int, started: float, text: Optional[str], failure: Optional[str]) -> None:
        if self.usage_sink is None:
            return
        tag = req.tag
        self.usage_sink.record({
            "provider": "stub", "model": "scripted", "purpose": tag.purpose, "session_id": None, "node_id": None,
            "task_id": tag.task_id, "dept_id": tag.dept_id or None, "fn": tag.function, "step": step_label(tag),
            "atom_id": tag.atom, "tokens_in": self._tokens(req.system + req.user),
            "tokens_out": 0 if text is None else self._tokens(text), "usd": 0.0,
            "seconds": round(time.monotonic() - started, 3), "ok": failure is None, "how": "stub",
            "call_ref": f"{tag.run_id}:{tag.call_no}" if tag.call_no > 0 else f"r:{request_id}",
            "detail": None if failure is None else {"note": clip(str(failure), 200)}})


# ---- kept verbatim from J2's llm.py:298-320 (the older studio's HTML helpers) -----------------------------------

def extract_html(text):
    m = re.search(r"```html\s*(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    i = text.lower().find("<!doctype")
    if i == -1:
        i = text.lower().find("<html")
    if i == -1:
        raise ValueError("no HTML in reply")
    return text[i:].strip()


def partial_html(text):
    """HTML written so far in a streaming reply (for the live preview), or '' if none yet."""
    low = text.lower()
    i = low.find("<!doctype")
    if i == -1:
        i = low.find("<html")
    if i == -1:
        return ""
    html = text[i:]
    end = html.find("```")
    return html[:end] if end != -1 else html
