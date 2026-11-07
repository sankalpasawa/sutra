"""`ModelConnector`: the base class of the CLI connectors (connectors design 3.3, D27, D28, D32, D33).

A connector turns a request into ONE child process of a model CLI and the child's stdout lines into events and a result.
The base owns everything the CLIs have in common; a child class (claude.py, codex.py) supplies four hooks:

    build_command(plan) -> Command      argv, cwd, env, stdin text, files to remove afterwards
    new_parser(plan)    -> LineParser   `.feed(line) -> [ConnectorEvent]`, `.finish(exit) -> TurnResult`, or raises a ConnectorError
    probe_auth()        -> AuthStatus   sign-in state without a model call
    probe_flags()       -> {flag: bool} feature detection from `--help`

and may override `recover(plan, error)` (one retry with another plan), `resolve_model`, `transport_schema` (Codex: the strict
schema) and `clean_native` (Codex: prune the nulls the strict schema forced in).

What the base does:
- one-shot calls (`call_text`, `call_json`, `call_json_result`): a fresh empty working directory removed afterwards;
- chat sessions (`start`, `send`, `stream`, `stop`, `resume`, `forget`): one process per turn, the provider session is a cache of
  the app's transcript, state in `<work_root>/<session_id>/session.json` (mode 0600, atomic);
- the JSON strategy of one connector (3.3, 3.6): native schema when the connector has one and the schema is small enough, a
  switch to the prompted path on a `StructuredError`, tolerant parse then strict validation, and up to `repair_rounds`
  stateless repair calls; `how` is native | prompted | repaired;
- `Hooks.before_call` (may raise EnvelopeExceededError) and `Hooks.after_call` around EVERY spawn; the connector never builds
  usage rows, the Router does (S1-contracts-05). `CallRecord` carries what the Router needs for them.

Direct use outside the Router is for tests. Every call is deterministic given the child's output; nothing here sleeps.
"""
from __future__ import annotations

import os
from sutra_app import oslayer
import re
import shutil
import tempfile
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterator, Optional, Sequence

from pydantic import BaseModel

from .env import child_env
from .errors import (
    CallCancelledError, ConnectorError, CliMissingError, EnvelopeExceededError, InvalidJsonError, InvalidRequestError,
    ProviderError, StructuredError,
)
from .jsonio import parse_and_validate, repair_prompt, validate_reply
from .models import (
    AuthStatus, Capabilities, ConnectorConfig, ConnectorEvent, Effort, JsonResult, Message, ModelInfo, Provider, Quota,
    RouteContext, SessionSpec, SessionState, TurnResult, Usage,
)
from .process import Command, ExitInfo, ProcessRunner, RunningProcess
from .schema import fits_native, schema_sha, schema_text, to_json_schema

__all__ = [
    "ModelConnector", "TurnPlan", "LineParser", "Hooks", "CallInfo", "CallRecord", "DEFAULT_TIMEOUT_S", "DEFAULT_IDLE_TIMEOUT_S",
    "AUTH_TTL_S", "PROBE_TIMEOUT_S", "REPAIR_ROUNDS", "MAX_PROMPT_CHARS", "EFFORTS", "write_private_file", "write_state",
    "prompted_prompt", "tool_names",
]

DEFAULT_TIMEOUT_S = 900.0          # J2 llm.py:156, and the policy default
DEFAULT_IDLE_TIMEOUT_S = 120.0     # applies only to streams with partials (without them a long generation prints nothing)
AUTH_TTL_S = 30.0                  # `auth_status` is cached this long
PROBE_TIMEOUT_S = 20.0             # a status, version, help or purge command
REPAIR_ROUNDS = 2                  # stateless repair calls after a reply that does not parse or validate (D33)
MAX_PROMPT_CHARS = 4_000_000       # about four times the largest context window; beyond it the request is refused
EFFORTS = ("low", "medium", "high", "xhigh", "max")
_MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\[\]/-]{0,99}")
_KNOWN_TOOLS = ("sutra", "github")
_PRIVATE_DIR = 0o700
_PRIVATE_FILE = 0o600


# ---- the small value types of the contract --------------------------------------------------------------------------------

@dataclass(frozen=True)
class TurnPlan:
    """Everything one spawn needs, decided before the child starts. Built by the base, read by the child class."""

    prompt: str
    ctx: RouteContext
    system: str = ""
    model: str = ""
    effort: str = "low"
    kind: str = "text"                           # text | json | repair | chat
    timeout_s: Optional[float] = None
    idle_timeout_s: Optional[float] = None       # only used when `partials`
    partials: bool = False
    schema: Optional[dict] = None                # the NATIVE schema this spawn sends (None: text, or the prompted path)
    images: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()                  # normalised profile names: ("sutra",) or ("sutra", "github")
    session: Optional[SessionState] = None       # a chat turn
    resume: bool = False                         # chat turn n (the provider session exists)
    provider_session_id: Optional[str] = None    # the id to create (turn 1) or to resume (turn n)
    workdir: str = ""                            # the session dir (session.json, system.txt), or a fresh empty one-shot dir; the child's cwd unless `folder`
    folder: str = ""                             # the owner's working folder (GAP3-workdir): the child's cwd, with read-only file tools; "" none
    oneshot: bool = True
    max_budget_usd: Optional[float] = None       # only with Allowance.max_usd
    cum_usd: float = 0.0                         # the session's counters BEFORE this turn (delta rules, CD5)
    cum_usage: Usage = field(default_factory=Usage)
    inline_system: bool = False                  # Claude: the system text goes on argv even when it is long
    attempt: int = 1                             # 1 for the first spawn of a request, 2 for a recovery retry


@dataclass(frozen=True)
class CallInfo:
    """What `Hooks.before_call` sees: enough to apply an allowance (calls, usd, deadline) before a process starts."""

    provider: str
    kind: str
    model: str
    effort: str
    ctx: RouteContext
    session_id: Optional[str]
    native: bool
    attempt: int
    max_budget_usd: Optional[float] = None


@dataclass
class CallRecord:
    """What `Hooks.after_call` gets after EVERY spawn, success or failure: the Router builds its usage row from these."""

    info: CallInfo
    ok: bool
    code: Optional[str]                          # the error code, None on success
    error: Optional[ConnectorError]
    turn: Optional[TurnResult]
    seconds: float
    usage: Usage
    usd: Optional[float]
    exit_code: Optional[int]
    native_schema_sha: Optional[str]             # set when a native schema was sent (the Router's `native_blocked` is keyed by it)
    cli_version: Optional[str] = None


class Hooks:
    """The Router subclasses this. The defaults do nothing, so a connector works on its own in tests."""

    def before_call(self, info: CallInfo) -> None:
        """Called before each spawn. Raise EnvelopeExceededError to stop it: no process has started."""

    def after_call(self, record: CallRecord) -> None:
        """Called once after each spawn that `before_call` allowed."""

    def on_quota(self, provider: str, quota: Quota) -> None:
        """A rate-limit snapshot seen in the stream (Claude's `rate_limit_event`), for the HealthBook."""


class LineParser(ABC):
    """One spawn's parser. After `finish`, `cum_usd` / `cum_usage` hold the session counters to store (None: unchanged)."""

    cum_usd: Optional[float] = None
    cum_usage: Optional[Usage] = None
    skipped: int = 0                              # stdout lines that were not events (noise), counted and ignored

    @abstractmethod
    def feed(self, line: str) -> list[ConnectorEvent]: ...

    @abstractmethod
    def finish(self, exit: ExitInfo) -> TurnResult:
        """The result, or a ConnectorError from the table of 3.4 / 3.5. `exit.reason` timeouts and cancels come first."""


class _CountingHooks(Hooks):
    """Wraps the caller's hooks and counts the spawns (`JsonResult.calls_made`)."""

    def __init__(self, inner: Hooks) -> None:
        self.inner = inner
        self.calls = 0

    def before_call(self, info: CallInfo) -> None:
        self.inner.before_call(info)
        self.calls += 1

    def after_call(self, record: CallRecord) -> None:
        self.inner.after_call(record)

    def on_quota(self, provider: str, quota: Quota) -> None:
        self.inner.on_quota(provider, quota)


# ---- helpers ---------------------------------------------------------------------------------------------------------------

def tool_names(tools: Sequence[str]) -> tuple[str, ...]:
    """Profile names from `("sutra",)`, `("sutra", "github")`, `("sutra+github",)` or `("none",)`: `none` and empty drop out,
    unknown names are refused, duplicates collapse, the order is sutra then github."""
    found: set[str] = set()
    for item in tools:
        for part in re.split(r"[+,]", str(item)):
            part = part.strip().lower()
            if part in ("", "none"):
                continue
            if part not in _KNOWN_TOOLS:
                raise InvalidRequestError(f"unknown tool profile {part!r}: use none, sutra or sutra+github")
            found.add(part)
    return tuple(n for n in _KNOWN_TOOLS if n in found)


def prompted_prompt(prompt: str, schema: dict) -> str:
    """The prompted JSON path (3.6 step 2): the prompt plus the schema text and the one-object instruction."""
    return (f"{prompt}\n\nAnswer with ONE JSON object only, no prose and no code fence. It must match this JSON Schema:\n"
            f"{schema_text(schema)}")


def write_private_file(path: Path, text: str) -> None:
    """A new file of mode 0600 (never readable by others, not even for an instant)."""
    fd = os.open(str(path), os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, _PRIVATE_FILE)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def write_state(state: SessionState) -> None:
    """`<workdir>/session.json`, atomically, mode 0600."""
    directory = Path(state.workdir)
    tmp = directory / f".session.{uuid.uuid4().hex[:8]}.tmp"
    try:
        write_private_file(tmp, state.model_dump_json(indent=2))
        oslayer.replace(tmp, directory / "session.json")
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _positive(value: Optional[float], name: str) -> Optional[float]:
    if value is not None and not (isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 and value == value
                                  and value != float("inf")):
        raise InvalidRequestError(f"{name} must be a positive number of seconds")
    return None if value is None else float(value)


# ---- the connector ---------------------------------------------------------------------------------------------------------

class ModelConnector(ABC):
    name: ClassVar[Provider]
    capabilities: ClassVar[Capabilities]
    default_model: ClassVar[str] = ""
    repair_rounds: int = REPAIR_ROUNDS
    idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S

    def __init__(self, cfg: ConnectorConfig, runner: Optional[ProcessRunner] = None, clock: Callable[[], float] = time.time,
                 hooks: Optional[Hooks] = None) -> None:
        self.cfg = cfg
        self.runner = runner or ProcessRunner()
        self._clock = clock
        self.hooks: Hooks = hooks or Hooks()
        self._lock = threading.RLock()
        self._busy: set[str] = set()
        self._procs: dict[str, RunningProcess] = {}
        self._total = Usage()
        self._auth: Optional[tuple[float, AuthStatus]] = None
        self._flags: Optional[dict[str, bool]] = None
        self._version: Optional[str] = None

    # ---- hooks a child implements ------------------------------------------------------------------------------------------
    @abstractmethod
    def build_command(self, plan: TurnPlan) -> Command: ...

    @abstractmethod
    def new_parser(self, plan: TurnPlan) -> LineParser: ...

    @abstractmethod
    def probe_auth(self) -> AuthStatus: ...

    @abstractmethod
    def probe_flags(self) -> dict[str, bool]: ...

    # ---- hooks a child may override ----------------------------------------------------------------------------------------
    def models(self) -> list[ModelInfo]:
        """The models this CLI can be asked for (no model call). The base knows none."""
        return []

    def recover(self, plan: TurnPlan, error: ConnectorError) -> Optional[TurnPlan]:
        """One retry of a spawn that failed for a reason the connector can fix itself (Claude C3: no system-prompt file)."""
        return None

    def resolve_model(self, requested: Optional[str]) -> str:
        model = requested or self.default_model
        if not model or _MODEL_PATTERN.fullmatch(model) is None:
            raise InvalidRequestError(f"{model!r} is not a usable model name", provider=self.name)
        return model

    def transport_schema(self, schema: dict) -> dict:
        """The schema as the CLI wants it natively (Codex: `strict_schema`)."""
        return schema

    def clean_native(self, value: Any, original_schema: "type[BaseModel] | dict") -> Any:
        """A native reply before validation (Codex: `prune_nulls`)."""
        return value

    # ---- paths ---------------------------------------------------------------------------------------------------------------
    def work_root(self) -> Path:
        root = self.cfg.resolved_work_root()
        root.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIR)
        return root

    def _private_dir(self, kind: str) -> Path:
        """A fresh private directory under the work root: `oneshot` working dirs and `files` (prompt, schema, MCP config)."""
        parent = self.work_root() / f"_{kind}"
        parent.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIR)
        return Path(os.path.realpath(tempfile.mkdtemp(prefix=f"{self.name}-", dir=parent)))

    def probe_dir(self) -> str:
        """The working directory of status, version, help and purge commands: explicit, empty, under the work root."""
        path = self.work_root() / "_probe"
        path.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIR)
        return str(path)

    def _env(self) -> dict[str, str]:
        return child_env(self.name, self.cfg.extra_env)

    def _run_probe(self, argv: Sequence[str], *, timeout_s: float = PROBE_TIMEOUT_S) -> tuple[ExitInfo, list[str]]:
        """A short command that is not a model call: its stdout lines and how it ended. Raises CliMissingError."""
        lines: list[str] = []
        cmd = Command(argv=tuple(argv), cwd=self.probe_dir(), env=self._env(), provider=self.name)
        info = self.runner.run(cmd, on_line=lines.append, timeout_s=timeout_s)
        return info, lines

    # ---- health (never a model call) -----------------------------------------------------------------------------------------
    def auth_status(self, *, refresh: bool = False) -> AuthStatus:
        """`probe_auth`, cached for 30 s on the injected clock. A `not_signed_in` error drops the cache."""
        now = self._clock()
        with self._lock:
            if not refresh and self._auth is not None and now - self._auth[0] < AUTH_TTL_S:
                return self._auth[1]
        status = self.probe_auth()
        with self._lock:
            self._auth = (now, status)
            if status.version:
                self._version = status.version
        return status

    def forget_cli(self) -> None:
        """The CLI file changed (the owner chose another one, discover.use_cli): its sign-in, flags and version are read again."""
        with self._lock:
            self._auth = None
            self._flags = None
            self._version = None

    def flags(self) -> dict[str, bool]:
        """`probe_flags`, read once per connector."""
        with self._lock:
            if self._flags is None:
                self._flags = self.probe_flags()
            return dict(self._flags)

    def usage(self, s: Optional[SessionState] = None) -> Usage:
        """The session's cumulative usage, or this connector's total since it was built."""
        if s is not None:
            return s.cum_usage
        with self._lock:
            return self._total

    # ---- one-shot --------------------------------------------------------------------------------------------------------------
    def call_text(self, prompt: str, *, system: str = "", images: Sequence[str] = (), tools: Sequence[str] = (),
                  timeout: float = DEFAULT_TIMEOUT_S, ctx: Optional[RouteContext] = None, effort: Optional[Effort] = None,
                  model: Optional[str] = None, hooks: Optional[Hooks] = None,
                  on_event: Optional[Callable[[ConnectorEvent], None]] = None, partials: bool = False) -> TurnResult:
        ctx = ctx or RouteContext()
        plan = self._oneshot_plan(prompt, system=system, kind="text", model=model, effort=effort or "high", timeout=timeout,
                                  ctx=ctx, images=images, tools=tools, schema=None, partials=partials, spent=0.0)
        return self._execute(plan, hooks or self.hooks, on_event)

    def call_json(self, prompt: str, tools: Sequence[str] = (), schema: "type[BaseModel] | dict | None" = None,
                  timeout: float = DEFAULT_TIMEOUT_S, *, system: str = "", ctx: Optional[RouteContext] = None,
                  effort: Optional[Effort] = None, model: Optional[str] = None, **more: Any) -> tuple[Any, Optional[float], str]:
        """`(value, usd, how)`: the diagram's tuple. `value` is the pydantic instance when `schema` is a class."""
        return self.call_json_result(prompt, tools, schema, timeout, system=system, ctx=ctx, effort=effort, model=model,
                                     **more).as_tuple()

    def call_json_result(self, prompt: str, tools: Sequence[str] = (), schema: "type[BaseModel] | dict | None" = None,
                         timeout: float = DEFAULT_TIMEOUT_S, *, system: str = "", ctx: Optional[RouteContext] = None,
                         effort: Optional[Effort] = None, model: Optional[str] = None, images: Sequence[str] = (),
                         hooks: Optional[Hooks] = None, on_event: Optional[Callable[[ConnectorEvent], None]] = None,
                         force_prompted: bool = False, repair_rounds: Optional[int] = None, folder: str = "") -> JsonResult:
        """The JSON strategy of one connector (3.6). `force_prompted` is the Router's `native_blocked`: skip the native path. `folder` is the
        owner's working folder (GAP3-workdir): only the org chat agent's calls carry one."""
        ctx = ctx or RouteContext()
        counting = _CountingHooks(hooks or self.hooks)
        rounds = self.repair_rounds if repair_rounds is None else repair_rounds
        if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 0:
            raise InvalidRequestError("repair_rounds must be a non-negative integer")
        schema_dict = to_json_schema(schema) if schema is not None else None
        native = (schema_dict is not None and self.capabilities.native_schema and not force_prompted and fits_native(schema_dict))
        sent = self.transport_schema(schema_dict) if native and schema_dict is not None else None
        spent: list[Optional[float]] = []
        turns: list[TurnResult] = []

        def spawn(text: str, native_now: bool, kind: str) -> TurnResult:
            plan = self._oneshot_plan(text, system=system, kind=kind, model=model, effort=effort or "low", timeout=timeout,
                                      ctx=ctx, images=images, tools=tools, schema=sent if native_now else None, partials=False,
                                      spent=sum(u for u in spent if u is not None), folder=folder)
            turn = self._execute(plan, counting, on_event)
            turns.append(turn)
            spent.append(turn.usd)
            return turn

        prompt_now = prompt if native or schema_dict is None else prompted_prompt(prompt, schema_dict)
        try:
            turn = spawn(prompt_now, native, "json")
        except StructuredError:
            if not native or schema_dict is None:
                raise
            native = False                                   # one switch to the prompted path, then the error stands
            prompt_now = prompted_prompt(prompt, schema_dict)
            turn = spawn(prompt_now, False, "json")
        how = "native" if native else "prompted"
        attempt = 0
        while True:
            try:
                value = self._read_reply(turn, schema, native)
                break
            except InvalidJsonError as e:
                if attempt >= rounds:
                    raise InvalidJsonError(e.message, provider=self.name,
                                           detail={"rounds": attempt, "calls": counting.calls}) from None
                attempt += 1
                how = "repaired"
                turn = spawn(repair_prompt(prompt_now, e.message, turn.text), native, "repair")
        known = [u for u in spent if u is not None]
        return JsonResult(value=value, usd=sum(known) if known else None, how=how, turn=turn, calls_made=counting.calls,
                          usd_spent=sum(known))

    def _read_reply(self, turn: TurnResult, schema: "type[BaseModel] | dict | None", native: bool) -> Any:
        if schema is None:
            return turn.structured if turn.structured is not None else turn.text
        if native and turn.structured is not None:
            return validate_reply(self.clean_native(turn.structured, schema), schema)
        value = parse_and_validate(turn.text, None)
        return validate_reply(self.clean_native(value, schema) if native else value, schema)

    def _oneshot_plan(self, prompt: str, *, system: str, kind: str, model: Optional[str], effort: str, timeout: float,
                      ctx: RouteContext, images: Sequence[str], tools: Sequence[str], schema: Optional[dict], partials: bool,
                      spent: float, folder: str = "") -> TurnPlan:
        self._check_prompt(prompt)
        self._check_effort(effort)
        images = self._check_images(images)
        return TurnPlan(
            prompt=prompt, ctx=ctx, system=system or "", model=self.resolve_model(model), effort=effort, kind=kind,
            timeout_s=_positive(timeout, "timeout"), idle_timeout_s=self.idle_timeout_s if partials else None,
            partials=partials, schema=schema, images=images, tools=tool_names(tools), folder=folder,
            max_budget_usd=self._budget_left(ctx, spent))

    @staticmethod
    def _budget_left(ctx: RouteContext, spent: float) -> Optional[float]:
        limit = ctx.allowance.max_usd
        if limit is None:
            return None
        left = limit - spent
        if left <= 0:
            raise EnvelopeExceededError("the envelope allows no more money", detail={"max_usd": limit, "spent": spent})
        return left

    def _check_prompt(self, prompt: str) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvalidRequestError("the prompt is empty", provider=self.name)
        if len(prompt) > MAX_PROMPT_CHARS:
            raise InvalidRequestError(f"the prompt is too long ({len(prompt):,} characters; the limit is {MAX_PROMPT_CHARS:,})",
                                      provider=self.name)

    def _check_effort(self, effort: str) -> None:
        if effort not in EFFORTS:      # the CLI only warns on a bad value and runs with its default, so refuse it here
            raise InvalidRequestError(f"effort must be one of {', '.join(EFFORTS)}, not {effort!r}", provider=self.name)

    def _check_images(self, images: Sequence[str]) -> tuple[str, ...]:
        out = tuple(str(p) for p in images)
        if out and not self.capabilities.images:
            raise InvalidRequestError(f"{self.name} cannot take images", provider=self.name)
        for path in out:
            if not Path(path).is_file():
                raise InvalidRequestError(f"image not found: {path}", provider=self.name)
        return out

    # ---- one spawn ---------------------------------------------------------------------------------------------------------------
    def _execute(self, plan: TurnPlan, hooks: Hooks, on_event: Optional[Callable[[ConnectorEvent], None]] = None) -> TurnResult:
        box: dict[str, TurnResult] = {}
        for event in self._events(plan, hooks, box):
            if on_event is not None:
                on_event(event)
        return box["turn"]

    def _events(self, plan: TurnPlan, hooks: Hooks, box: dict) -> Iterator[ConnectorEvent]:
        """One request: a spawn, and one more when the connector can fix the failure itself (`recover`)."""
        try:
            yield from self._spawn(plan, hooks, box)
        except ConnectorError as e:
            retry = self.recover(plan, e)
            if retry is None:
                raise
            yield from self._spawn(replace(retry, attempt=plan.attempt + 1), hooks, box)

    def _spawn(self, plan: TurnPlan, hooks: Hooks, box: dict) -> Iterator[ConnectorEvent]:
        info = CallInfo(provider=self.name, kind=plan.kind, model=plan.model, effort=plan.effort, ctx=plan.ctx,
                        session_id=plan.session.session_id if plan.session else None, native=plan.schema is not None,
                        attempt=plan.attempt, max_budget_usd=plan.max_budget_usd)
        hooks.before_call(info)                     # may raise EnvelopeExceededError: nothing has started
        started = self._clock()
        error: Optional[ConnectorError] = None
        turn: Optional[TurnResult] = None
        exit_info: Optional[ExitInfo] = None
        sha = schema_sha(plan.schema) if plan.schema is not None else None
        key = plan.session.session_id if plan.session is not None else None
        try:
            if plan.oneshot and not plan.workdir:
                plan = replace(plan, workdir=str(self._private_dir("oneshot")))
                oneshot_dir: Optional[str] = plan.workdir
            else:
                oneshot_dir = None
            try:
                cmd = self.build_command(plan)
            except BaseException:
                if oneshot_dir:
                    shutil.rmtree(oneshot_dir, ignore_errors=True)
                raise
            if oneshot_dir:
                cmd = replace(cmd, cleanup=cmd.cleanup + (oneshot_dir,))
            parser = self.new_parser(plan)
            idle = plan.idle_timeout_s if plan.partials else None
            try:
                proc = self.runner.start(cmd, timeout_s=plan.timeout_s, idle_timeout_s=idle)
            except ProviderError as e:
                if isinstance(e.__cause__, PermissionError):          # C1: the file is there but cannot be run
                    raise CliMissingError(f"{cmd.argv[0]} cannot be run", provider=self.name,
                                          detail={"cli": cmd.argv[0]}) from e
                raise
            with proc:
                self._track(key, proc)
                try:
                    for line in proc.lines():
                        for event in parser.feed(line):
                            if event.kind == "quota":
                                hooks.on_quota(self.name, Quota.model_validate(event.data))
                            yield event
                    exit_info = proc.wait()
                finally:
                    self._untrack(key, proc)
            box["parser"] = parser
            turn = parser.finish(exit_info)
        except ConnectorError as e:
            error = e
            if e.provider is None:
                e.provider = self.name
            if e.code == "cli_missing" and self.name == "claude" and getattr(self.cfg, "claude_desktop", False):
                e.detail.setdefault("desktop", True)          # the sentence names Claude Code, not PATH (errors.DESKTOP_ONLY)
            if e.code == "not_signed_in":
                with self._lock:
                    self._auth = None
            raise
        finally:
            if error is None and turn is None:          # the consumer stopped reading, or a non-connector exception
                error = CallCancelledError("the call was abandoned before it finished", provider=self.name)
            hooks.after_call(CallRecord(
                info=info, ok=error is None, code=None if error is None else error.code, error=error,
                turn=turn if error is None else None, seconds=max(0.0, self._clock() - started),
                usage=turn.usage if turn is not None else Usage(), usd=turn.usd if turn is not None else None,
                exit_code=None if exit_info is None else exit_info.returncode, native_schema_sha=sha,
                cli_version=self._version))
        with self._lock:
            self._total = self._total + turn.usage
        box["turn"] = turn

    def _track(self, key: Optional[str], proc: RunningProcess) -> None:
        if key is not None:
            with self._lock:
                self._procs[key] = proc

    def _untrack(self, key: Optional[str], proc: RunningProcess) -> None:
        if key is not None:
            with self._lock:
                if self._procs.get(key) is proc:
                    del self._procs[key]

    # ---- sessions (chat nodes) ---------------------------------------------------------------------------------------------------
    def _session_dir(self, session_id: str) -> Path:
        return Path(os.path.realpath(self.work_root() / session_id))

    def start(self, spec: SessionSpec) -> SessionState:
        """Creates the work dir and `session.json`; no process yet. An existing `session.json` is replaced: a new provider
        session starts here (the Router calls this on a switch, and the work dir stays)."""
        if spec.provider is not None and spec.provider != self.name:
            raise InvalidRequestError(f"this is the {self.name} connector, not {spec.provider}", provider=self.name)
        effort = spec.effort or "low"
        self._check_effort(effort)
        model = self.resolve_model(spec.model)
        tool_names(() if spec.tool_profile == "none" else (spec.tool_profile,))        # refuses an unknown profile
        directory = self._session_dir(spec.session_id)
        directory.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIR)
        state = SessionState(session_id=spec.session_id, provider=self.name, provider_session_id=None, model=model, effort=effort,
                             tool_profile=spec.tool_profile, workdir=str(directory), created_at=self._clock())
        system_file = directory / "system.txt"
        system_file.unlink(missing_ok=True)
        if spec.system:
            write_private_file(system_file, spec.system)
        write_state(state)
        return state

    def resume(self, ref: SessionState) -> SessionState:
        """Local checks only: the provider, the work dir, the ids. `session.json` is authoritative when it exists; when it is
        missing (or the work dir was lost) the result has no provider session id, so the next `send` starts a new provider
        session and the Router adds the carry-over (S1-contracts-08). A dead provider session shows at the next send."""
        if ref.provider != self.name:
            raise InvalidRequestError(f"session {ref.session_id} belongs to {ref.provider}, not {self.name}", provider=self.name)
        directory = self._check_workdir(ref)
        state = ref
        file = directory / "session.json"
        if directory.is_dir() and file.is_file():
            try:
                state = SessionState.model_validate_json(file.read_text(encoding="utf-8"))
            except ValueError as e:
                raise InvalidRequestError(f"session.json of {ref.session_id} is not valid: {str(e).splitlines()[0]}",
                                          provider=self.name) from None
            if state.session_id != ref.session_id or state.provider != self.name:
                raise InvalidRequestError(f"session.json does not belong to session {ref.session_id}", provider=self.name)
            self._check_workdir(state)
        else:
            state = ref.model_copy(update={"provider_session_id": None})
            directory.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIR)
        if state.provider_session_id is not None and not self.valid_provider_session_id(state.provider_session_id):
            state = state.model_copy(update={"provider_session_id": None})
        if state is not ref or not file.is_file():
            write_state(state)
        return state

    @staticmethod
    def valid_provider_session_id(value: str) -> bool:
        try:
            uuid.UUID(value)
        except ValueError:
            return False
        return True

    def _check_workdir(self, state: SessionState) -> Path:
        """The work dir of a session is always `<work_root>/<session_id>`: a stored path that points elsewhere is refused."""
        expected = self._session_dir(state.session_id)
        if Path(os.path.realpath(state.workdir)) != expected:
            raise InvalidRequestError(f"the work dir of session {state.session_id} is not under the work root", provider=self.name)
        return expected

    def send(self, s: SessionState, m: Message, *, timeout_s: Optional[float] = None,
             on_event: Optional[Callable[[ConnectorEvent], None]] = None, hooks: Optional[Hooks] = None, folder: str = "") -> TurnResult:
        """One turn, consuming `stream()` (no partials)."""
        box: dict[str, TurnResult] = {}
        for event in self._turn(s, m, timeout_s, False, hooks or self.hooks, box, folder):
            if on_event is not None and event.kind != "turn_done":
                on_event(event)
        return box["turn"]

    def stream(self, s: SessionState, m: Message, *, timeout_s: Optional[float] = None, partials: bool = True,
               hooks: Optional[Hooks] = None, folder: str = "") -> Iterator[ConnectorEvent]:
        """The events of one turn; the last one is `turn_done` with `data["result"]` (the TurnResult as JSON). `folder` is the owner's
        working folder for this turn (GAP3-workdir): the child runs in it with read-only file tools; the session's own files stay in its work dir."""
        return self._turn(s, m, timeout_s, partials, hooks or self.hooks, {}, folder)

    def _turn(self, s: SessionState, m: Message, timeout_s: Optional[float], partials: bool, hooks: Hooks,
              box: dict, folder: str = "") -> Iterator[ConnectorEvent]:
        if m.role != "user":
            raise InvalidRequestError("a chat turn is sent as a user message", provider=self.name)
        if s.provider != self.name:
            raise InvalidRequestError(f"session {s.session_id} belongs to {s.provider}, not {self.name}", provider=self.name)
        directory = self._check_workdir(s)
        self._check_prompt(m.text)
        images = self._check_images(m.images)
        timeout = _positive(DEFAULT_TIMEOUT_S if timeout_s is None else timeout_s, "timeout_s")
        self._check_effort(s.effort)
        with self._lock:
            if s.session_id in self._busy:
                raise InvalidRequestError(f"session {s.session_id} is already running a turn", provider=self.name)
            self._busy.add(s.session_id)
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIR)
            if not (directory / "session.json").is_file():       # the work dir was lost: the provider session is lost with it
                s.provider_session_id = None
            # a provider session belongs to the folder it began in (Claude keys it by its cwd): a turn in another folder starts a new one
            # (the Router adds the carry-over first, so nothing the owner said is lost)
            resume = s.provider_session_id is not None and s.work_folder == folder
            plan = TurnPlan(
                prompt=m.text, ctx=RouteContext(session_id=s.session_id), system=self._session_system(directory),
                model=self.resolve_model(s.model), effort=s.effort, kind="chat", timeout_s=timeout,
                idle_timeout_s=self.idle_timeout_s if partials else None, partials=partials, images=images,
                tools=tool_names(() if s.tool_profile == "none" else (s.tool_profile,)), session=s, resume=resume,
                provider_session_id=s.provider_session_id if resume else self.new_provider_session_id(),
                workdir=str(directory), folder=folder, oneshot=False, cum_usd=s.cum_usd, cum_usage=s.cum_usage)
            holder: dict[str, Any] = {}
            for event in self._events(plan, hooks, holder):
                yield event
            turn = holder["turn"]
            self._commit_turn(s, plan, turn, holder.get("parser"))
            box["turn"] = turn
            yield ConnectorEvent(kind="turn_done", data={"result": turn.model_dump(mode="json")})
        finally:
            with self._lock:
                self._busy.discard(s.session_id)

    def new_provider_session_id(self) -> str:
        return str(uuid.uuid4())

    def _session_system(self, directory: Path) -> str:
        try:
            return (directory / "system.txt").read_text(encoding="utf-8")
        except OSError:
            return ""

    def _commit_turn(self, s: SessionState, plan: TurnPlan, turn: TurnResult, parser: Optional[LineParser]) -> None:
        s.turns += 1
        s.work_folder = plan.folder
        s.provider_session_id = turn.provider_session_id or plan.provider_session_id
        if parser is not None and parser.cum_usd is not None:
            s.cum_usd = parser.cum_usd
        if parser is not None and parser.cum_usage is not None:
            s.cum_usage = parser.cum_usage
        else:
            s.cum_usage = s.cum_usage + turn.usage
        write_state(s)

    def stop(self, s: SessionState) -> bool:
        """The cancel ladder on the session's running child; False when it is idle. The turn then raises CallCancelledError."""
        with self._lock:
            proc = self._procs.get(s.session_id)
        if proc is None:
            return False
        return proc.cancel()

    def forget(self, s: SessionState) -> None:
        """Best effort: remove the CLI's own transcript of this session. The work dir is kept (a switch reuses it)."""
        argv = self.forget_command(s)
        if argv is None:
            return
        try:
            self._run_probe(argv)
        except ConnectorError:
            pass

    def forget_command(self, s: SessionState) -> Optional[Sequence[str]]:
        return None
