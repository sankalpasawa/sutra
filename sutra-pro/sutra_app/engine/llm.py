"""J2's `llm` module, kept at its call syntax and rebuilt on a `ModelPort` (engine design 4.2, D17).

J2 called a model provider here. This shim sends every call through one seam instead: `ask(...)` builds a
`CompletionRequest` with a `CallTag` and hands it to the configured `ModelPort` (the connector layer's router, or
`ScriptedPort`, J2's mock mode). The five J2 call sites keep their syntax (they only gain a `tagged(...)` block); the
host calls `configure(...)` BEFORE the vendored `j2` module is imported because J2 reads `MOCK` at import.

    ask            J2's signature (`timeout` included) plus a keyword `tag`; the reply text, stripped (unstripped in mock mode, as J2)
    CallTimeout    what `ask` raises when the port reports a timeout (J2's `except llm.CallTimeout`, D170)
    can_read_files False: the agents' file tools are bound to the owner's working folder, never to a run folder (D170)
    tools_on, can_use_tools, TOOLS   builder tools (D245, superseding D240): on for a live run when the provider that would take a builder
                                     call can run one (the Claude CLI), unless J2_AGENT_TOOLS=0; else J2 takes its section path. Offline,
                                     J2_AGENT_TOOLS=1 turns J2's general path on with scripted replies, as in J2
    sandbox_on, sandbox_status       the sandbox (D245): J2_SANDBOX decides when it is set; unset, a live engine has it on for macOS and Linux
                                     when the sandbox runtime (J2_SANDBOX_CMD, default srt) is found, else off; offline it is J2's (J2_SANDBOX=1)
    inside                           J2's helper: a path strictly inside a folder
    run_env, RUN_PASS_NAMES          the allowlisted environment of a script the engine runs, plus what its plan states (D446)
    is_loader_name, RUN_LOADER_NAMES a fixed safety guardrail of loader and proxy names, not a secret detector (D446, D449)
    login_homes                      where the CLI sign-ins and the app's data live: never a plan's secret file (D446)
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
import shlex
import shutil
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

from sutra_app.connectors.env import WINDOWS_PASS_NAMES
from sutra_app.library.replies import close_json, extract_json     # re-exported: one copy, tested in test_lib_replies.py
from sutra_app.library.types import clip

from .port import (
    Allowance, CallTag, CompletionRequest, CompletionResult, ModelError, ModelPort, NoModelAvailable, PortInfo, PreflightResult,
    ToolGrant, UsageRecorder,
)

__all__ = [
    "ask", "CallTimeout", "can_read_files", "tools_on", "can_use_tools", "sandbox_on", "sandbox_status", "inside", "TOOLS", "configure", "tagged", "current_tag", "bind_atom", "bound_atom", "env_mock", "step_label", "ScriptedPort",
    "EmptyReply", "extract_json", "close_json", "extract_html", "partial_html", "LAST_META", "MOCK", "PROVIDER", "MODEL",
    "MOCK_ENV", "TAG_HOOKS", "PROGRESS_HOOKS", "NodeMeter", "NodeCapReached", "CAP_WORDS",
    "RUN_PASS_NAMES", "RUN_LOADER_NAMES", "run_env", "is_loader_name", "login_homes",
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
_METER: "Optional[NodeMeter]" = None
_DEFAULT_PORT: Optional["ScriptedPort"] = None     # mock mode with no port configured: made on first use
_BASE_TAG: CallTag = CallTag()
_BOUND_ATOM: Optional[str] = None
_TAG: ContextVar[Optional[CallTag]] = ContextVar("sutra_engine_call_tag", default=None)


class CallTimeout(RuntimeError):
    """J2's own name for a model call stopped at its time limit (`J2Run.call` retries it once). Raised by `ask` for a
    `ModelError` with code `timeout`; the original is `__cause__`. D170."""

    code = "timeout"          # what the P8 run_error hook reports when a timed-out call ends the run


def can_read_files() -> bool:
    """J2 asks whether the agent can read files at a path; here it never can: the agents' file tools are bound to the owner's
    working folder, never to a run folder, so J2's "read the rest at <path>" hint would point at nothing (D170)."""
    return False


# Builder tools (D245, superseding D240). J2 gives a builder Claude's built-in tools in a folder of the run (`ask(tools=...)`, its "general path")
# when `llm.tools_on()`. Live, the call goes through the router as a `CompletionRequest.run_tools` grant, and only a connector that can run one
# takes it (the Claude CLI): the router plans no other, so a tools call never falls back to Codex. When no such connector is usable (the Claude
# CLI missing or signed out, a Codex-only router) tools are off and J2 builds through its section path, as with J2_AGENT_TOOLS=0. Offline the
# switch is J2's own (J2_AGENT_TOOLS=1, mock only). `TOOLS` maps a provider name to whether it can run a tools call.
TOOLS: dict = {"claude": True, "codex": False, "stub": False}
TOOL_KEYS = ("tools", "allow", "cwd", "root", "usd", "log_chars")      # J2's tools request: every key given (J2 llm.TOOL_KEYS)


def tools_provider() -> Optional[str]:
    """The provider a builder tools call would go to now, or None: mock mode, no port, or a port that can run none (from the router's cached
    status: no model call)."""
    if MOCK or _PORT is None:
        return None
    probe = getattr(_PORT, "tools_provider", None)
    try:
        return probe() if callable(probe) else None
    except Exception:                    # a probe that fails is "no tools": J2 takes its section path
        return None


def tools_on() -> bool:
    """J2 asks whether builders get tools. Live: unless J2_AGENT_TOOLS=0, when a connector can run the call (`can_use_tools`). Offline (mock) only
    when J2_AGENT_TOOLS=1, as in J2: the scripted replies stand for the builders' writes, so J2's own flow test can walk the general path."""
    if MOCK:
        return os.getenv("J2_AGENT_TOOLS") == "1"
    return os.getenv("J2_AGENT_TOOLS") != "0" and can_use_tools()


def can_use_tools() -> bool:
    """J2 asks whether the current provider can run a call with tools in a folder: live, when the router has a connector that can (D245)."""
    return bool(TOOLS.get(tools_provider() or "", False))


SANDBOX_PLATFORMS = ("darwin", "linux")      # where the sandbox runtime works; off on Windows unless J2_SANDBOX=1 (D245)


def sandbox_status(mock: Optional[bool] = None, environ: Optional[Mapping[str, str]] = None) -> tuple[bool, str]:
    """(on, why) of J2's sandbox for builders' commands, the test rerun and a real run (D245). J2_SANDBOX set: exactly that. Offline (mock):
    J2's default, off. Live and unset: on for macOS and Linux when the sandbox runtime J2_SANDBOX_CMD (default srt) is found on PATH, else off
    with the reason and how to install it; off on Windows. `environ` (default the process's) is where J2_SANDBOX is read."""
    value = (os.environ if environ is None else environ).get("J2_SANDBOX")
    if value not in (None, ""):
        return value == "1", f"J2_SANDBOX={value}"
    if MOCK if mock is None else mock:
        return False, "offline: J2's default (J2_SANDBOX=1 turns it on)"
    if not sys.platform.startswith(SANDBOX_PLATFORMS):
        return False, f"not on {sys.platform} (J2_SANDBOX=1 turns it on)"
    try:
        program = shlex.split(os.getenv("J2_SANDBOX_CMD") or "srt")[0]
    except (ValueError, IndexError):
        return False, "J2_SANDBOX_CMD can't be read"
    found = shutil.which(program)
    if found is None:
        return False, f"{program} not found; install it with: npm i -g @anthropic-ai/sandbox-runtime"
    return True, f"{program} at {found}"


def sandbox_on() -> bool:
    """J2's switch: builders' commands, the test rerun and a real run go through a sandbox (`sandbox_status`)."""
    return sandbox_status()[0]


# D446: the whole environment of a script the engine runs (real run, dry run, test rerun) is an allowlist, never a blocklist.
# Common, never secret; Windows' own (USERNAME, USERPROFILE, TEMP, ...) come from WINDOWS_PASS_NAMES. Proxies stay out, and a plan may not set them either (D449).
RUN_PASS_NAMES: tuple[str, ...] = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TZ", "TERM", "LANG", "LC_ALL", "LC_CTYPE",
                                   "TMPDIR") + WINDOWS_PASS_NAMES
# D446: a fixed safety guardrail, not a secret detector: names that change how a runtime or the dynamic loader starts a
# program, or (D449) where it connects. Entries ending "_" are prefixes. Never extended by pattern.
RUN_LOADER_NAMES: tuple[str, ...] = ("LD_", "DYLD_", "NODE_OPTIONS", "PYTHONSTARTUP", "PYTHONPATH", "PERL5OPT", "RUBYOPT",
                                     "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def run_env(extra: Optional[Mapping[str, str]] = None, environ: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """The whole environment of a script the engine runs (real run, dry run, test rerun; D446): the RUN_PASS_NAMES found in
    environ (default os.environ), then extra (the plan's settings and secret-file paths, checked by _register) on top."""
    source = os.environ if environ is None else environ
    return {**{n: source[n] for n in RUN_PASS_NAMES if n in source}, **(extra or {})}


def is_loader_name(name: str) -> bool:
    """D446, D449: True when name (upper-cased) is in RUN_LOADER_NAMES, or starts with one of its "_"-ending prefixes."""
    n = name.upper()
    return any(n.startswith(x) if x.endswith("_") else n == x for x in RUN_LOADER_NAMES)


def login_homes(environ: Optional[Mapping[str, str]] = None) -> list[str]:
    """Where the sign-ins the app relies on live, and the app's own data: a plan may never hand a script a file there (D446).
    Claude ($CLAUDE_CONFIG_DIR, ~/.claude, ~/.claude.json), Codex ($CODEX_HOME, ~/.codex), gh ($GH_CONFIG_DIR,
    ${XDG_CONFIG_HOME:-~/.config}/gh, %APPDATA%/GitHub CLI), the app ($SUTRA_DATA_DIR, $SUTRA_ENV_FILE,
    paths.default_data_dir(), paths.default_env_file(), and both channels' data folders, desktop/src/channels.json
    dataDirName, whichever channel runs). Unset ones left out; duplicates dropped."""
    from . import paths      # lazily: paths is the host's module
    env = os.environ if environ is None else environ
    xdg = env.get("XDG_CONFIG_HOME") or "~/.config"
    appdata = env.get("APPDATA")
    found = [env.get("CLAUDE_CONFIG_DIR"), "~/.claude", "~/.claude.json", env.get("CODEX_HOME"), "~/.codex", env.get("GH_CONFIG_DIR"),
             os.path.join(xdg, "gh"), appdata and os.path.join(appdata, "GitHub CLI"), env.get("SUTRA_DATA_DIR"),
             env.get("SUTRA_ENV_FILE"), str(paths.default_data_dir(env)), str(paths.default_env_file(env)),
             "~/.sutra-pro", "~/.sutra-pro-beta"]      # the stable and the beta app's data (channels.json), locked by both
    return list(dict.fromkeys(os.path.expanduser(p) for p in found if p))


def _tool_problems(tools) -> list:
    """Why a tools request can't be run ([] when it can), as J2 checks it: every key given, the lists not empty, the folder there and inside the
    run folder (root) once symlinks are resolved."""
    if not isinstance(tools, Mapping):
        return ["tools must be an object"]
    out = [f"tools needs {k}" for k in TOOL_KEYS if tools.get(k) in (None, "", [], ())]
    if not out and not os.path.isdir(tools["cwd"]):
        out.append(f"tools cwd {tools['cwd']} is not a folder")
    elif not out and not inside(tools["cwd"], tools["root"]):
        out.append(f"tools cwd {tools['cwd']} does not resolve inside the run folder {tools['root']}")
    return out


def inside(path, root) -> bool:
    """J2's helper, verbatim in meaning: True when `path` resolves (symlinks followed) to a path strictly inside `root`."""
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p != r and p.startswith(r.rstrip(os.sep) + os.sep)


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


CAP_WORDS = {"calls": "used up its model calls", "usd": "used up its dollars", "wall": "ran out of time"}      # what a node that reached a cap says, in plain words


class NodeCapReached(ModelError):
    """A node of a multi-agent project used up what its grant lets it spend: `which` is `calls`, `usd` or `wall`. A `ModelError`, so J2's own failure paths end the run; the host then says why
    in the run's outcome (MAN-9). Never retryable: the next call would be refused too."""

    code = "node_cap"
    retryable = False

    def __init__(self, which: str) -> None:
        super().__init__(f"this step {CAP_WORDS[which]}")
        self.which = which


class NodeMeter:
    """What one node of a project has spent across ALL its calls, and what is left (MAN-9, D272): calls, dollars and wall time. The router's allowance is per request; this meter makes it
    cumulative for the process, so a node that makes many small calls is still stopped. `check()` raises `NodeCapReached` before a call that would go past a cap; `allowance()` is what one
    request may still spend, `charge()` adds a finished call. A cap of None is not checked. With no meter (every run that is not a node) `ask` sends the allowance it always sent: none."""

    def __init__(self, *, max_calls: Optional[int] = None, max_usd: Optional[float] = None, wall_s: Optional[float] = None, clock: Callable[[], float] = time.time) -> None:
        self.max_calls, self.max_usd, self.wall_s, self._clock = max_calls, max_usd, wall_s, clock
        self.started = clock()
        self.calls = 0
        self.usd = 0.0
        self.reached: Optional[str] = None
        self._lock = threading.Lock()

    def _deadline(self) -> Optional[float]:
        return self.started + self.wall_s if self.wall_s is not None else None

    def check(self) -> None:
        with self._lock:
            which = ("calls" if self.max_calls is not None and self.calls >= self.max_calls else "usd" if self.max_usd is not None and self.usd >= self.max_usd
                     else "wall" if self._deadline() is not None and self._clock() >= self._deadline() else None)
            if which is not None:
                self.reached = self.reached or which
                raise NodeCapReached(which)

    def allowance(self) -> Allowance:
        with self._lock:
            return self._allowance()

    def _allowance(self) -> Allowance:
        return Allowance(max_calls=None if self.max_calls is None else max(0, self.max_calls - self.calls), max_usd=None if self.max_usd is None else max(0.0, self.max_usd - self.usd),
                         deadline=self._deadline())

    def begin(self) -> Allowance:
        """Check the caps AND count the call in one step under the lock (two threads cannot both take the last call), and give what this one request may still spend."""
        with self._lock:
            which = ("calls" if self.max_calls is not None and self.calls >= self.max_calls else "usd" if self.max_usd is not None and self.usd >= self.max_usd
                     else "wall" if self._deadline() is not None and self._clock() >= self._deadline() else None)
            if which is not None:
                self.reached = self.reached or which
                raise NodeCapReached(which)
            allowance = self._allowance()
            self.calls += 1
            return allowance

    def refund(self) -> None:
        """Take back the count of a call that never started a model program (it waited for a machine-wide slot and gave up: PB-14)."""
        with self._lock:
            self.calls = max(0, self.calls - 1)

    def charge(self, usd: Optional[float]) -> None:
        """Add what a finished call cost (the call itself was counted by `begin`)."""
        with self._lock:
            self.usd += float(usd or 0.0)


def configure(port: Optional[ModelPort] = None, *, mock: Optional[bool] = None,
              base_tag: Optional[CallTag | Mapping] = None, meter: "Optional[NodeMeter]" = None) -> None:
    """Set the model port, mock mode and the tag every call starts from. Each call replaces the whole configuration:
    `configure()` is the environment's default (mock only if `env_mock()`, no port, an empty tag).

    mock: True/False, else the port's `describe().mock`, else `env_mock()`. In mock mode `PROVIDER` and `MODEL` stay None
    (J2 wrote null provider and model into its run files in mock mode); otherwise they come from `port.describe()`.
    With `mock` true and no port, `ask` uses a `ScriptedPort` made on first use."""
    global _PORT, _BASE_TAG, MOCK, PROVIDER, MODEL, _METER
    info: Optional[PortInfo] = port.describe() if port is not None else None
    if mock is not None:
        is_mock = bool(mock)
    elif info is not None:
        is_mock = info.mock
    else:
        is_mock = env_mock()
    _PORT = port
    _METER = meter                       # a node's meter, or None: every run that is not a node (MAN-9)
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
        schema=None, timeout=None, tools=None, *, tag=None) -> str:
    """One model call. `mock` is J2's scripted reply (a callable); only the stub path calls it. `images` are PNG paths and
    the ones that do not exist are dropped. `schema` is a JSON Schema the reply should follow (advisory: the engine checks
    the reply itself). `timeout` is J2's per-call limit in seconds (D170): it becomes `CompletionRequest.timeout_s`, which the
    router honours and cuts to the envelope's deadline; a `ModelError` with code `timeout` is re-raised as `CallTimeout`.
    `tag` names the call; default `current_tag()`. Raises a `ModelError` when the port does. `tools` is J2's tools request (D245): checked as J2 checks it,
    then sent as a `ToolGrant` with the sandbox choice; LAST_META then gets J2's tool record ("tool_calls", "denied", "stop"). Mock mode
    ignores it, as J2 does."""
    grant = None
    if tools is not None and not MOCK:      # mock mode ignores tools, as J2's own mock does
        if bad := _tool_problems(tools):
            raise RuntimeError("; ".join(bad))
        grant = ToolGrant(tools=tuple(tools["tools"]), allow=tuple(tools["allow"]), cwd=os.path.realpath(tools["cwd"]),
                          root=os.path.realpath(tools["root"]), usd=float(tools["usd"]), log_chars=int(tools["log_chars"]),
                          extra=tuple(tools.get("extra") or ()), sandbox=sandbox_on())
    images = [p for p in images or [] if p and os.path.exists(p)]
    LAST_META.clear()
    port = _active_port()
    tag = current_tag() if tag is None else _as_tag(tag)
    if tag.atom is None and _BOUND_ATOM is not None:
        tag = tag.model_copy(update={"atom": _BOUND_ATOM})
    tag = _hooked_tag(tag)
    meter = _METER
    allowance = meter.begin() if meter is not None else None       # a node past its calls, dollars or time makes no call (raises `NodeCapReached`); the call is counted here, under a lock
    request = CompletionRequest(system=system, user=user, max_tokens=max_tokens, effort=effort, json_mode=json_mode,
                                images=images, json_schema=schema, timeout_s=timeout or None, tag=tag, allowance=allowance,
                                scripted=mock, run_tools=grant)
    try:
        result = port.complete(request, _hooked_progress(tag, on_progress))
    except ModelError as exc:
        if meter is not None and (getattr(exc, "detail", None) or {}).get("slots") is True:
            meter.refund()                                                    # it never started a program: not a call (PB-14)
        if exc.code == "timeout":
            raise CallTimeout(str(exc)) from exc
        raise
    else:
        if meter is not None:
            meter.charge(result.usd)
    if MOCK:                          # J2 reported nothing for a mock reply, and returned it as it was
        return result.text
    meta = {"model": result.model, "provider": result.provider, "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens, "usd": result.usd, "duration_ms": result.duration_ms,
            "structured": result.structured}
    LAST_META.update({key: value for key, value in meta.items() if value is not None})
    if grant is not None:
        LAST_META.update(result.tool_record or {"tool_calls": [], "denied": 0, "stop": "no result"})
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
