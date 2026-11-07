"""`CodexConnector`: `codex exec --json` driven on the owner's ChatGPT login (connectors design 3.5, D29, D34).

    codex exec --json --skip-git-repo-check --ignore-user-config --ignore-rules [--ephemeral] -s read-only -C <dir>
      [-i <image> ...] -m <slug> -c model_reasoning_effort="<effort>" [-c mcp_servers.sutra.*] [--output-schema <0600 file>] -
    codex exec resume --json ... -m <slug> -c model_reasoning_effort="<effort>" -c sandbox_mode="read-only" ... <thread_id> -

The prompt goes on stdin (`-`), never argv; the system text goes first in it as `<system>...</system>` (no flag was verified).
`danger-full-access` and `--dangerously-bypass-*` are never emitted. Before every call the connector looks at the cached
`codex login status` (a signed-out `codex exec` retries 401 for 18-20 s), and a stream with two 401 `error` events in a row is
stopped at once (about 3 s instead of 18). `CODEX_ERROR_MAP` is the table of 3.5 as data, rows X1 to X18.

Counters: `turn.completed.usage` is CUMULATIVE for the thread; a turn's usage is the difference to the session's `cum_usage`
(a counter that went backwards is taken whole, usage.py). Codex prints no price: `usd` is rate card x delta when the owner filled
`rates`, else None (`usd_basis "unknown"`). After a turn the last `rate_limits` of that thread's rollout file become a `Quota`
(best effort, ignored on any failure; `--ephemeral` calls leave no rollout, so one-shot calls carry no quota).

Everything here is deterministic given the child's output. Sign-in (`begin_sign_in`) is the one place a long-lived child is used.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional

from sutra_app.config import DB_FILENAME

from .base import AUTH_TTL_S, EFFORTS, Hooks, LineParser, ModelConnector, TurnPlan, write_private_file
from .errors import (
    CallCancelledError, CallTimeoutError, ConnectorError, CliMissingError, CrashedError, EmptyReplyError, FlagUnsupportedError,
    InvalidRequestError, ModelNotFoundError, NotSignedInError, ProtocolError, ProviderError, QuotaError, RateLimitedError,
    ServerError, SessionLostError, StructuredError,
)
from .jsonio import prune_nulls
from .models import AuthStatus, Capabilities, ConnectorConfig, ConnectorEvent, ModelInfo, Quota, SessionState, TurnResult, Usage
from .policy import Rate
from .process import Command, ExitInfo, ProcessRunner, RunningProcess
from .quota_windows import window_key, windows_from_codex
from .schema import strict_schema
from .usage import cumulative_delta, rate_card_usd, usage_from_codex

__all__ = [
    "CodexConnector", "CodexParser", "CodexSignIn", "CODEX_ERROR_MAP", "PROBED_FLAGS", "SANDBOXES", "API_KEY_REFUSED",
    "CATALOG_TTL_S", "SIGN_IN_EXPIRES_S", "SIGN_IN_POLL_S", "parse_device_auth", "parse_reset_time", "quota_from_rate_limits",
    "strip_ansi",
]

API_KEY_REFUSED = "API-key login is refused: sign in with your subscription"
SANDBOXES = ("read-only", "workspace-write")          # `danger-full-access` is never offered
CATALOG_TTL_S = 3600.0                                # `codex debug models` is cached an hour
CATALOG_RETRY_S = 60.0                                # a failed read is not retried at once
SIGN_IN_EXPIRES_S = 900                               # the device code lives 15 minutes
SIGN_IN_POLL_S = 2.0                                  # `login status` is looked at most this often while a sign-in is pending
SIGN_IN_READY_S = 20.0                                # how long `begin_sign_in` waits for the link and the code
AUTH_STREAK = 2                                       # X5: this many 401 `error` events in a row stop the process
PROBED_FLAGS = (
    "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--sandbox", "--cd", "--model",
    "--config", "--output-schema", "--image",
)
_RESULT_TEXT_CHARS = 300
_ROLLOUT_TAIL_BYTES = 262144
_THREAD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
_URL = re.compile(r"https://[^\s\x1b]+")
_CODE = re.compile(r"\b[A-Z0-9]{4,}-[A-Z0-9]{4,}\b")
_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b")
_RESET_FORMATS = ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p", "%b %d %Y %I:%M %p", "%B %d %Y %I:%M %p")

# The table of 3.5 as data: row id -> the error code it must produce. The tests run one case per row.
CODEX_ERROR_MAP: dict[str, str] = {
    "X1": "cli_missing", "X2": "cli_flag_unsupported", "X3a": "invalid_request", "X3b": "invalid_request", "X3c": "invalid_request",
    "X4": "not_signed_in", "X5": "not_signed_in", "X5b": "not_signed_in", "X5c": "not_signed_in", "X6": "quota",
    "X7": "rate_limited", "X8": "server_error", "X9": "structured", "X10": "model_not_found", "X11": "provider_error",
    "X12": "session_lost", "X13": "crashed", "X14": "protocol_error", "X15": "timeout", "X16": "cancelled", "X17": "empty_reply",
    "X18": "ok",
}


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _has_code(text: str, code: str) -> bool:
    """The status number as a word of its own: `401` in a request id such as `req_4401ab` or a ray id does not count."""
    return re.search(rf"(?<![A-Za-z0-9_-]){code}(?![A-Za-z0-9_-])", text) is not None


def _exit_label(exit: ExitInfo) -> Any:
    return exit.signal_name or exit.returncode


def _fraction(value: Any) -> Optional[float]:
    return float(value) / 100.0 if isinstance(value, (int, float)) and not isinstance(value, bool) else None


_window_name = window_key            # one table of window names (quota_windows.py)


def quota_from_rate_limits(rate_limits: Mapping[str, Any]) -> Optional[Quota]:
    """A rollout `rate_limits` object -> `Quota`. The window with the higher `used_percent` (primary or secondary) is the one the
    router blocks on (`window`, `used`, `resets_at`); `windows` keeps both (GAP-providers). `used` is a fraction (0.09 = 9 %, like
    Claude's utilization); `exhausted` when Codex names a reached limit or the window is full, `warning` from 80 %. None when there
    is no window at all."""
    windows = [w for w in (rate_limits.get("primary"), rate_limits.get("secondary")) if isinstance(w, Mapping)]
    if not windows:
        return None
    best = max(windows, key=lambda w: w.get("used_percent") if isinstance(w.get("used_percent"), (int, float)) else -1)
    percent = best.get("used_percent") if isinstance(best.get("used_percent"), (int, float)) else None
    reached = rate_limits.get("rate_limit_reached_type")
    if reached or (percent is not None and percent >= 100):
        status = "exhausted"
    elif percent is not None and percent >= 80:
        status = "warning"
    elif percent is not None:
        status = "ok"
    else:
        status = "unknown"
    resets = best.get("resets_at")
    plan = rate_limits.get("plan_type")
    return Quota(status=status, window=_window_name(best.get("window_minutes")), used=_fraction(percent),
                 resets_at=float(resets) if isinstance(resets, (int, float)) and not isinstance(resets, bool) else None,
                 plan=plan if isinstance(plan, str) else None, source="rollout", windows=windows_from_codex(rate_limits))


def parse_reset_time(text: str, now: float) -> Optional[float]:
    """Epoch seconds from "... try again at Nov 5th, 2026 4:30 PM." (or "... at 4:30 PM", the next such time), local time.
    None when the text names no time this function understands (the HealthBook then cools down for 30 minutes)."""
    found = re.search(r"try again at ([A-Za-z0-9:, ]+)", text, re.I)
    if not found:
        return None
    said = _ORDINAL.sub("", " ".join(found.group(1).split())).strip(" ,")
    for fmt in _RESET_FORMATS:
        try:
            return time.mktime(datetime.strptime(said, fmt).timetuple())
        except ValueError:
            continue
    try:
        clock = datetime.strptime(said, "%I:%M %p")
    except ValueError:
        return None
    today = datetime.fromtimestamp(now).replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
    stamp = time.mktime(today.timetuple())
    return stamp if stamp > now else stamp + 86400.0


def parse_device_auth(lines: list[str]) -> tuple[Optional[str], Optional[str]]:
    """`(url, code)` from the lines `codex login --device-auth` prints: the first `https://...` and, after it, the first
    `XXXX-XXXXX` code. ANSI colours are stripped first (`NO_COLOR` is ignored by the CLI)."""
    url = code = None
    for raw in lines:
        line = strip_ansi(raw)
        if url is None:
            found = _URL.search(line)
            if found:
                url = found.group(0).rstrip(".,)")
            continue
        if code is None:
            found = _CODE.search(line)
            if found:
                code = found.group(0)
    return url, code


# ---- the parser ------------------------------------------------------------------------------------------------------------

class CodexParser(LineParser):
    """`codex exec --json` lines -> events, then `turn.completed` / `turn.failed` -> a TurnResult or the error of 3.5."""

    provider = "codex"

    def __init__(self, plan: TurnPlan, *, version: Optional[str] = None, rate: Optional[Rate] = None,
                 quota_reader: Optional[Callable[[str], Optional[Quota]]] = None, clock: Callable[[], float] = time.time) -> None:
        self.plan = plan
        self.version = version
        self.rate = rate
        self.quota_reader = quota_reader
        self.clock = clock
        self.skipped = 0
        self.objects = 0
        self.thread_id: Optional[str] = None
        self.messages: list[str] = []
        self.errors: list[str] = []
        self.tool_types: list[str] = []
        self.completed: Optional[dict] = None          # the turn.completed event
        self.failed: Optional[str] = None              # the turn.failed message
        self.auth_streak = 0
        self.auth_aborted = False
        self.proc: Optional[RunningProcess] = None     # set by the connector, so the parser can stop a doomed run (X5)
        self.cum_usd = None
        self.cum_usage = None

    # ---- lines -> events -----------------------------------------------------------------------------------------------------
    def feed(self, line: str) -> list[ConnectorEvent]:
        try:
            obj = json.loads(line)
        except ValueError:
            obj = None
        if not isinstance(obj, dict):
            self.skipped += 1
            return []
        self.objects += 1
        kind = obj.get("type")
        handler = getattr(self, "_on_" + kind.replace(".", "_"), None) if isinstance(kind, str) and kind.replace(".", "_").isidentifier() else None
        return handler(obj) if handler is not None else []           # an unknown type is ignored

    def _on_thread_started(self, obj: dict) -> list[ConnectorEvent]:
        if isinstance(obj.get("thread_id"), str):
            self.thread_id = obj["thread_id"]
        return [ConnectorEvent(kind="started", data={"session_id": self.thread_id})]

    def _on_item_completed(self, obj: dict) -> list[ConnectorEvent]:
        item = obj.get("item")
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            return []
        if item["type"] != "error":
            self.auth_streak = 0
        if item["type"] == "agent_message":
            text = item.get("text")
            if not isinstance(text, str):
                return []
            self.messages.append(text)
            return [ConnectorEvent(kind="text", data={"text": text})]
        if item["type"] == "error":
            return [ConnectorEvent(kind="notice", data={"text": str(item.get("message", ""))[:500]})]
        self.tool_types.append(item["type"])                           # X18: unknown item types are tolerated
        return [ConnectorEvent(kind="tool_call", data={"type": item["type"], "id": item.get("id")})]

    def _on_error(self, obj: dict) -> list[ConnectorEvent]:
        message = str(obj.get("message", ""))
        self.errors.append(message)
        if _is_auth_failure(message):
            self.auth_streak += 1
            if self.auth_streak >= AUTH_STREAK and not self.auth_aborted:
                self.auth_aborted = True                               # X5: the run cannot succeed, do not wait for 18 s
                if self.proc is not None:
                    self.proc.cancel()
        else:
            self.auth_streak = 0
        return [ConnectorEvent(kind="notice", data={"text": message[:500]})]

    def _on_turn_completed(self, obj: dict) -> list[ConnectorEvent]:
        self.completed = obj
        return []

    def _on_turn_failed(self, obj: dict) -> list[ConnectorEvent]:
        error = obj.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        self.failed = str(message if message is not None else "")
        return []

    # ---- the end ---------------------------------------------------------------------------------------------------------------
    def _error(self, cls: type, message: str = "", **detail: Any) -> ConnectorError:
        detail.setdefault("cli", "codex")
        if self.version:
            detail.setdefault("version", self.version)
        resets_at = detail.pop("resets_at", None)
        return cls(message, provider="codex", detail=detail, resets_at=resets_at)

    def finish(self, exit: ExitInfo) -> TurnResult:
        if self.auth_aborted:                                                       # X5 (the process was stopped by us)
            raise self._error(NotSignedInError, status=401, reason="401_in_a_row")
        if exit.reason in ("total_timeout", "idle_timeout"):                        # X15
            which = "idle" if exit.reason == "idle_timeout" else "total"
            seconds = self.plan.idle_timeout_s if which == "idle" else self.plan.timeout_s
            raise self._error(CallTimeoutError, which=which, seconds=seconds)
        if exit.reason == "cancelled":                                              # X16
            raise self._error(CallCancelledError, "stopped")
        if self.failed is not None:                                                 # X5c, X6 to X11
            raise self._from_failed(self.failed)
        if self.completed is None:                                                  # X2, X3, X12, X13, X14
            raise self._without_end(exit)
        text = next((m for m in reversed(self.messages) if m.strip()), "")
        if not text:                                                                # X17
            raise self._error(EmptyReplyError)
        return self._turn_result(exit, text)

    def _from_failed(self, message: str) -> ConnectorError:
        shown = message[:_RESULT_TEXT_CHARS]
        low = message.lower()
        if _is_auth_failure(message):                                               # X5c
            return self._error(NotSignedInError, status=401, reason="turn_failed")
        if "usage limit" in low:                                                    # X6
            resets = parse_reset_time(message, self.clock())
            if resets is None:
                resets = self._rollout_reset()
            return self._error(QuotaError, shown, resets_at=resets)
        if _has_code(message, "429") or "too many requests" in low:                 # X7
            return self._error(RateLimitedError, shown, status=429)
        server = re.search(r"(?:last status|unexpected status):?\s*(5\d\d)\b", message)
        if server:                                                                  # X8
            return self._error(ServerError, shown, status=int(server.group(1)))
        if _has_code(message, "400") or "bad request" in low:
            if "schema" in low or "response_format" in low:                         # X9
                return self._error(StructuredError, shown, status=400, present=False)
            if "model" in low:                                                      # X10
                return self._error(ModelNotFoundError, shown, model=self.plan.model, status=400)
        return self._error(ProviderError, shown or "Codex reported an error")      # X11

    def _rollout_reset(self) -> Optional[float]:
        quota = self._rollout_quota()
        return quota.resets_at if quota is not None and quota.status == "exhausted" else None

    def _rollout_quota(self) -> Optional[Quota]:
        if self.quota_reader is None or not self.thread_id:
            return None
        try:
            return self.quota_reader(self.thread_id)
        except Exception:                                                           # noqa: BLE001  best effort, never an error
            return None

    def _without_end(self, exit: ExitInfo) -> ConnectorError:
        stderr = exit.stderr_tail
        low = stderr.lower()
        if "no rollout found for thread id" in low:                                 # X12
            return self._error(SessionLostError, "no rollout found for the thread")
        if self.objects == 0 and exit.returncode not in (0, None):
            unknown = re.search(r"unexpected argument '([^']+)'", stderr)
            if unknown or "unexpected argument" in low:                             # X2
                return self._error(FlagUnsupportedError, stderr.strip()[:200], flag=unknown.group(1) if unknown else None)
            if ("output schema file" in low or "failed to read output schema" in low
                    or "no such file or directory" in low):                         # X3
                lines = [ln.strip() for ln in stderr.splitlines() if ln.strip() and not ln.startswith("Reading additional input")]
                return self._error(InvalidRequestError, (lines[0] if lines else "Codex refused the request")[:200])
        if exit.returncode != 0:                                                    # X13: killed by a signal, or a bad exit
            return self._error(CrashedError, exit=_exit_label(exit), stderr=stderr[-_RESULT_TEXT_CHARS:])
        return self._error(ProtocolError, "the stream ended without a turn end")   # X14

    def _turn_result(self, exit: ExitInfo, text: str) -> TurnResult:
        raw = self.completed.get("usage") if isinstance(self.completed.get("usage"), dict) else None
        if raw is None:
            usage = Usage()                                    # no counter in the event: nothing to charge, the baseline stays
        else:
            now = usage_from_codex(raw)
            usage = cumulative_delta(now, self.plan.cum_usage)
            self.cum_usage = now
        usd = rate_card_usd(self.rate, usage)
        structured = None
        if self.plan.schema is not None:
            try:
                structured = json.loads(text)
            except ValueError:
                structured = None                              # the base then parses the text tolerantly and may repair it
        return TurnResult(
            text=text, structured=structured, provider="codex", model=self.plan.model, provider_session_id=self.thread_id,
            usage=usage, usd=usd, usd_basis="rate_card" if usd is not None else "unknown", quota=self._rollout_quota(),
            duration_ms=int(exit.seconds * 1000))


def _is_auth_failure(message: str) -> bool:
    return (_has_code(message, "401") or "unauthorized" in message.lower() or "missing bearer" in message.lower())


# ---- sign-in -----------------------------------------------------------------------------------------------------------------

@dataclass
class CodexSignIn:
    """One `codex login --device-auth` run. `state` is pending | signed_in | failed | expired (what the API of 5.6 shows)."""

    id: str
    url: str
    code: str
    expires_in: int
    created_at: float
    state: str = "pending"
    reason: Optional[str] = None
    proc: Optional[RunningProcess] = field(default=None, repr=False)
    exit: Optional[ExitInfo] = field(default=None, repr=False)
    last_check: float = field(default=float("-inf"), repr=False)
    output: list[str] = field(default_factory=list, repr=False)

    def as_dict(self) -> dict[str, Any]:
        """The body of `POST /api/connectors/codex/sign-in`."""
        return {"id": self.id, "url": self.url, "code": self.code, "expires_in": self.expires_in}

    def status(self) -> dict[str, Any]:
        """The body of `GET /api/connectors/codex/sign-in/{id}`."""
        return {"state": self.state, "reason": self.reason}


# ---- the connector -----------------------------------------------------------------------------------------------------------

class CodexConnector(ModelConnector):
    name = "codex"
    default_model = "gpt-5.6-luna"
    capabilities = Capabilities(native_schema=True, resume=True, images=True, partials=False, mcp=True)

    def __init__(self, cfg: ConnectorConfig, runner: Optional[ProcessRunner] = None, clock: Callable[[], float] = time.time,
                 hooks: Optional[Hooks] = None, *, rates: Optional[Mapping[str, Rate]] = None, sandbox: str = "read-only") -> None:
        super().__init__(cfg, runner, clock, hooks)
        if sandbox not in SANDBOXES:
            raise InvalidRequestError(f"sandbox must be one of {', '.join(SANDBOXES)}, not {sandbox!r}", provider="codex")
        self.sandbox = sandbox
        self.rates: dict[str, Rate] = dict(rates or {})
        self._tl = threading.local()
        self._catalog: Optional[tuple[float, Optional[list[dict]]]] = None
        self._plan: Optional[str] = None
        self._sign_ins: dict[str, CodexSignIn] = {}

    # ---- the catalog of `codex debug models` -------------------------------------------------------------------------------
    def _catalog_models(self) -> Optional[list[dict]]:
        """The raw model entries, cached an hour (a failed read 60 s). None when the CLI gave no usable list."""
        now = self._clock()
        with self._lock:
            if self._catalog is not None:
                stamp, entries = self._catalog
                if now - stamp < (CATALOG_TTL_S if entries is not None else CATALOG_RETRY_S):
                    return entries
        entries = self._read_catalog()
        with self._lock:
            self._catalog = (now, entries)
        return entries

    def _read_catalog(self) -> Optional[list[dict]]:
        try:
            info, lines = self._run_probe([self.cfg.codex_exe, "debug", "models"])
            doc = json.loads("\n".join(lines))
        except (ConnectorError, ValueError):
            return None
        if info.returncode != 0 or not isinstance(doc, dict) or not isinstance(doc.get("models"), list):
            return None
        return [m for m in doc["models"] if isinstance(m, dict) and isinstance(m.get("slug"), str)]

    def _listed(self) -> list[dict]:
        return [m for m in (self._catalog_models() or []) if m.get("visibility") == "list"]

    def models(self) -> list[ModelInfo]:
        """The models with `visibility "list"` (no model call). Empty when the CLI cannot be asked."""
        out = []
        for entry in self._listed():
            levels = entry.get("supported_reasoning_levels")
            efforts = [lv["effort"] for lv in levels if isinstance(lv, dict) and lv.get("effort") in EFFORTS] if isinstance(levels, list) else []
            window = entry.get("context_window")
            modalities = entry.get("input_modalities")
            out.append(ModelInfo(
                slug=entry["slug"], label=str(entry.get("display_name") or entry["slug"]), efforts=efforts,
                context_window=window if isinstance(window, int) and not isinstance(window, bool) else None,
                images=isinstance(modalities, list) and "image" in modalities, listed=True))
        return out

    def resolve_model(self, requested: Optional[str]) -> str:
        """The slug, checked against the listed models: an unknown one becomes the first listed model, with a `notice`."""
        slug = super().resolve_model(requested)
        listed = self._listed()
        if not listed or any(m["slug"] == slug for m in listed):
            return slug
        replacement = listed[0]["slug"]
        self._note(f"model {slug} is not available in this Codex; using {replacement}", model=slug, used=replacement)
        return replacement

    def effective_effort(self, model: str, effort: str) -> str:
        """`effort` clamped to the model's `supported_reasoning_levels`: the highest supported level not above it, else the
        lowest supported one. A model the catalog does not know keeps the effort as asked."""
        entry = next((m for m in (self._catalog_models() or []) if m["slug"] == model), None)
        levels = entry.get("supported_reasoning_levels") if entry else None
        supported = [lv["effort"] for lv in levels if isinstance(lv, dict) and lv.get("effort") in EFFORTS] if isinstance(levels, list) else []
        if not supported or effort in supported:
            return effort
        rank = EFFORTS.index(effort)
        below = [e for e in supported if EFFORTS.index(e) < rank]
        chosen = max(below, key=EFFORTS.index) if below else min(supported, key=EFFORTS.index)
        return chosen

    # ---- notices (events the connector makes before the child speaks) --------------------------------------------------------
    def _note(self, text: str, **data: Any) -> None:
        pending = getattr(self._tl, "notices", None)
        if pending is None:
            pending = self._tl.notices = []
        pending.append(ConnectorEvent(kind="notice", data={"text": text, **data}))

    def _drain_notices(self) -> Iterator[ConnectorEvent]:
        pending = getattr(self._tl, "notices", None) or []
        self._tl.notices = []
        yield from pending

    def start(self, spec: Any) -> SessionState:
        try:
            return super().start(spec)
        finally:
            self._tl.notices = []                            # a model notice is for a spawn, not for the creation of a session

    # ---- partials: Codex prints no text deltas, so no idle deadline is ever armed --------------------------------------------
    def call_text(self, prompt: str, **kw: Any) -> TurnResult:                     # type: ignore[override]
        kw["partials"] = False
        return super().call_text(prompt, **kw)

    def stream(self, s: SessionState, m: Any, *, timeout_s: Optional[float] = None, partials: bool = False,
               hooks: Optional[Hooks] = None) -> Iterator[ConnectorEvent]:
        return super().stream(s, m, timeout_s=timeout_s, partials=False, hooks=hooks)

    # ---- one spawn: notices before the first event, the rollout quota after the last --------------------------------------------
    def _spawn(self, plan: TurnPlan, hooks: Hooks, box: dict) -> Iterator[ConnectorEvent]:
        try:
            for event in super()._spawn(plan, hooks, box):
                yield from self._drain_notices()
                yield event
            yield from self._drain_notices()
            turn = box.get("turn")
            if turn is not None and turn.quota is not None:
                if turn.quota.plan:
                    self._plan = turn.quota.plan
                hooks.on_quota(self.name, turn.quota)
                yield ConnectorEvent(kind="quota", data=turn.quota.model_dump())
        finally:
            self._tl.notices = []

    def _track(self, key: Optional[str], proc: RunningProcess) -> None:
        parser = getattr(self._tl, "parser", None)
        if parser is not None:                      # new_parser ran just before the child started: hand it its process (X5)
            parser.proc = proc
            self._tl.parser = None
        super()._track(key, proc)

    def new_parser(self, plan: TurnPlan) -> CodexParser:
        parser = CodexParser(plan, version=self._version, rate=self.rates.get(plan.model), quota_reader=self.read_rollout_quota,
                             clock=self._clock)
        self._tl.parser = parser
        return parser

    # ---- schema --------------------------------------------------------------------------------------------------------------
    def transport_schema(self, schema: dict) -> dict:
        return strict_schema(schema)

    def clean_native(self, value: Any, original_schema: Any) -> Any:
        return prune_nulls(value, original_schema)

    # ---- tools -----------------------------------------------------------------------------------------------------------------
    def mcp_servers(self, tools: tuple[str, ...]) -> dict[str, Any]:
        """The MCP entry for a tool profile: the app's own stdlib server. A minimal adapter; CN-8's `tools/profiles.py` can
        override this method. The server's env holds a path, never a secret."""
        import sutra_app
        root = str(Path(sutra_app.__file__).resolve().parent.parent)
        return {"sutra": {"command": self.cfg.python,
                          "args": ["-m", "sutra_app.connectors.tools.mcp_server", "--profile", ",".join(tools)],
                          "env": {"PYTHONPATH": root, "SUTRA_DB_RO": str(Path(self.cfg.data_dir) / DB_FILENAME)}}}

    @staticmethod
    def _toml_string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _mcp_flags(self, tools: tuple[str, ...]) -> list[str]:
        """`-c mcp_servers.<name>.command/args/env=...` per server: TOML values on the argv, nothing on disk."""
        argv: list[str] = []
        for name, server in self.mcp_servers(tools).items():
            if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise InvalidRequestError(f"MCP server name {name!r} is not usable", provider="codex")
            env = ",".join(f"{k}={self._toml_string(str(v))}" if re.fullmatch(r"[A-Za-z0-9_-]+", k) else f"{self._toml_string(k)}={self._toml_string(str(v))}"
                           for k, v in server.get("env", {}).items())
            argv += ["-c", f"mcp_servers.{name}.command={self._toml_string(server['command'])}",
                     "-c", f"mcp_servers.{name}.args=[{','.join(self._toml_string(str(a)) for a in server.get('args', []))}]",
                     "-c", f"mcp_servers.{name}.env={{{env}}}"]
        return argv

    # ---- the four hooks ----------------------------------------------------------------------------------------------------------
    def _precheck(self) -> None:
        """X4, X1 and the billing guard, from the cached `login status`: no process is started for the call itself."""
        status = self.auth_status()
        if not status.installed:
            raise CliMissingError(f"{self.cfg.codex_exe} was not found", provider="codex", detail={"cli": self.cfg.codex_exe})
        if status.billing == "api_key":
            raise NotSignedInError(API_KEY_REFUSED, provider="codex", detail={"cli": "codex", "billing": "api_key"})
        if status.signed_in is False:
            raise NotSignedInError(provider="codex", detail={"cli": "codex", "reason": "login_status"})

    def build_command(self, plan: TurnPlan) -> Command:
        self._precheck()
        argv = [self.cfg.codex_exe, "exec"]
        if plan.resume:
            argv.append("resume")
        argv += ["--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules"]
        if not plan.resume:                                  # `exec resume` takes no -s and no -C: sandbox_mode below, cwd of the process
            if plan.oneshot:
                argv.append("--ephemeral")
            argv += ["-s", self.sandbox, "-C", plan.workdir]
        for image in plan.images:                            # one -i per file, before -m: `-i <FILE>...` would swallow the final `-`
            argv += ["-i", os.path.abspath(image)]
        effort = self.effective_effort(plan.model, plan.effort)
        if effort != plan.effort:
            self._note(f"effort {plan.effort} is not supported by {plan.model}; using {effort}", model=plan.model, asked=plan.effort, used=effort)
        argv += ["-m", plan.model, "-c", f'model_reasoning_effort="{effort}"']
        if plan.resume:
            argv += ["-c", f'sandbox_mode="{self.sandbox}"']
        if plan.tools:
            argv += self._mcp_flags(plan.tools)
        cleanup: list[str] = []
        try:
            if plan.schema is not None:
                files = self._private_dir("files")
                cleanup.append(str(files))
                path = files / "schema.json"
                write_private_file(path, json.dumps(plan.schema, ensure_ascii=False))
                argv += ["--output-schema", str(path)]
            if plan.resume:
                if not plan.provider_session_id or not self.valid_provider_session_id(plan.provider_session_id):
                    raise InvalidRequestError("the stored Codex thread id is not usable", provider="codex")
                argv.append(plan.provider_session_id)
            argv.append("-")
            prompt = plan.prompt
            if plan.system and not plan.resume:              # the thread keeps the system text from its first turn
                prompt = f"<system>\n{plan.system}\n</system>\n\n{plan.prompt}"
            return Command(argv=tuple(argv), cwd=plan.workdir, env=self._env(), stdin_text=prompt, cleanup=tuple(cleanup),
                           provider="codex")
        except BaseException:
            for path in cleanup:
                shutil.rmtree(path, ignore_errors=True)
            raise

    def version(self) -> Optional[str]:
        """The CLI's version from `codex --version` ("codex-cli 0.146.0"), read once; None when it cannot be read."""
        if self._version is None:
            try:
                _, lines = self._run_probe([self.cfg.codex_exe, "--version"])
            except ConnectorError:
                return None
            found = re.search(r"\d+\.\d+\.\d+\S*", " ".join(lines))
            self._version = found.group(0) if found else None
        return self._version

    def probe_auth(self) -> AuthStatus:
        """`codex login status` (text on stderr, exit 0 or 1, no model call). "ChatGPT" is a subscription login; "API key" is
        `billing api_key`, which the Router drops at plan time and `_precheck` refuses (D7, S1-contracts-17); an unknown wording is
        allowed (`billing unknown`)."""
        now = self._clock()
        try:
            info, lines = self._run_probe([self.cfg.codex_exe, "login", "status"])
        except CliMissingError as e:
            return AuthStatus(provider="codex", installed=False, signed_in=None, detail=e.user_message(), checked_at=now)
        except ProviderError as e:
            if isinstance(e.__cause__, PermissionError):             # the file is there but cannot be run: as good as missing
                return AuthStatus(provider="codex", installed=False, signed_in=None, detail=f"{self.cfg.codex_exe} cannot be run",
                                  checked_at=now)
            raise
        version = self.version()
        said = strip_ansi(" ".join([*lines, info.stderr_tail])).strip()
        low = said.lower()
        if "not logged in" in low or "not signed in" in low:
            signed_in: Optional[bool] = False
        elif info.returncode == 0 and "logged in" in low:
            signed_in = True
        elif info.returncode == 1 and not said:
            signed_in = False
        else:
            signed_in = None
        method = None
        billing = "unknown"
        if signed_in:
            if re.search(r"api[ _-]?key", low):
                method, billing = "API key", "api_key"
            elif "chatgpt" in low:
                method, billing = "ChatGPT", "subscription"
        if signed_in is None:
            detail = f"codex login status gave no usable answer (exit {info.returncode}): {said[:200] or 'no answer'}"
        elif signed_in is False:
            detail = "not signed in: use Sign in or run `codex login`"
        elif billing == "api_key":
            detail = API_KEY_REFUSED
        else:
            detail = "signed in" + (f" with {method}" if method else "")
        return AuthStatus(provider="codex", installed=True, version=version, signed_in=signed_in, method=method, billing=billing,
                          plan=self._plan, detail=detail, checked_at=now)

    def probe_flags(self) -> dict[str, bool]:
        """Feature detection from `codex exec --help`, not a version table. Raises CliMissingError when the CLI is not there."""
        _, lines = self._run_probe([self.cfg.codex_exe, "exec", "--help"])
        present = set(re.findall(r"--[A-Za-z][A-Za-z0-9-]*", "\n".join(lines)))
        return {flag: flag in present for flag in PROBED_FLAGS}

    def forget_command(self, s: SessionState) -> Optional[list[str]]:
        if not s.provider_session_id or not self.valid_provider_session_id(s.provider_session_id):
            return None
        return [self.cfg.codex_exe, "delete", s.provider_session_id]

    # ---- the rollout quota ----------------------------------------------------------------------------------------------------
    def read_rollout_quota(self, thread_id: str) -> Optional[Quota]:
        """The last `rate_limits` of `$CODEX_HOME/sessions/**/rollout-*-<thread>.jsonl` as a Quota. Best effort: every failure
        (no file, a format that changed, a bad line) gives None. It reads a session file, never the login (CD8)."""
        if not _THREAD_ID.fullmatch(thread_id or ""):
            return None
        try:
            env = self._env()
            home = env.get("CODEX_HOME") or os.path.join(env.get("HOME") or os.path.expanduser("~"), ".codex")
            files = sorted(Path(home, "sessions").glob(f"**/rollout-*-{thread_id}.jsonl"))
            if not files:
                return None
            with open(files[-1], "rb") as fh:
                size = fh.seek(0, os.SEEK_END)
                fh.seek(max(0, size - _ROLLOUT_TAIL_BYTES))
                tail = fh.read().decode("utf-8", errors="replace").splitlines()
            for raw in reversed(tail):
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                payload = obj.get("payload") if isinstance(obj, dict) else None
                if isinstance(payload, dict) and payload.get("type") == "token_count" and isinstance(payload.get("rate_limits"), dict):
                    return quota_from_rate_limits(payload["rate_limits"])
        except (OSError, ValueError, AttributeError, TypeError):
            return None
        return None

    # ---- sign-in (5.6) ----------------------------------------------------------------------------------------------------------
    def begin_sign_in(self, *, ready_timeout_s: float = SIGN_IN_READY_S) -> CodexSignIn:
        """Start `codex login --device-auth` and return its link and one-time code. The child keeps waiting for the owner;
        `sign_in_poll(id)` looks at `login status` (at most every 2 s), `cancel_sign_in(id)` stops the child. A sign-in that is
        still pending is cancelled first: there is one at a time."""
        for old in list(self._sign_ins.values()):
            if old.state == "pending":
                self._finish_sign_in(old, "failed", "replaced by a new sign-in", cancel=True)
        cmd = Command(argv=(self.cfg.codex_exe, "login", "--device-auth"), cwd=self.probe_dir(), env=self._env(), provider="codex")
        proc = self.runner.start(cmd, timeout_s=SIGN_IN_EXPIRES_S + 60.0)
        output: list[str] = []
        ready = threading.Event()
        found: dict[str, Optional[str]] = {"url": None, "code": None}

        def read() -> None:
            for line in proc.lines():
                output.append(line)
                found["url"], found["code"] = parse_device_auth(output)
                if found["url"] and found["code"]:
                    ready.set()
            ready.set()                                       # the child ended (with or without a code)

        threading.Thread(target=read, name="codex-sign-in", daemon=True).start()
        ready.wait(ready_timeout_s)
        if not (found["url"] and found["code"]):
            proc.cancel()
            tail = strip_ansi(proc.wait().stderr_tail).strip()[:200]
            raise ProviderError("codex login --device-auth showed no link and code" + (f": {tail}" if tail else ""),
                                provider="codex", detail={"cli": "codex"})
        entry = CodexSignIn(id=uuid.uuid4().hex[:12], url=found["url"], code=found["code"], expires_in=SIGN_IN_EXPIRES_S,
                            created_at=self._clock(), proc=proc, output=output)
        with self._lock:
            self._sign_ins[entry.id] = entry
            for stale in [i for i, e in self._sign_ins.items() if e.state != "pending"][:-4]:
                del self._sign_ins[stale]                     # keep the last few finished ones for late polls
        return entry

    def sign_in_poll(self, sign_in_id: str) -> dict[str, Any]:
        """The state of a sign-in (`CodexSignIn.status()`); a pending one is checked against `login status` (throttled)."""
        entry = self._sign_in(sign_in_id)
        if entry.state != "pending":
            return entry.status()
        now = self._clock()
        if now - entry.created_at >= entry.expires_in:
            self._finish_sign_in(entry, "expired", "the one-time code expired", cancel=True)
            return entry.status()
        ended = entry.proc is not None and entry.proc.running is False
        if not ended and now - entry.last_check < SIGN_IN_POLL_S:
            return entry.status()
        entry.last_check = now
        status = self.probe_auth()
        if status.signed_in is True:
            self._finish_sign_in(entry, "signed_in", None, cancel=True)
        elif ended:
            code = entry.proc.wait().returncode if entry.proc is not None else None
            self._finish_sign_in(entry, "failed", f"codex login ended (exit {code}) without a login", cancel=False)
        return entry.status()

    def cancel_sign_in(self, sign_in_id: str) -> bool:
        """Stop the child of a pending sign-in (`DELETE ...`); False when it was not pending."""
        entry = self._sign_in(sign_in_id)
        if entry.state != "pending":
            return False
        self._finish_sign_in(entry, "failed", "cancelled", cancel=True)
        return True

    def _sign_in(self, sign_in_id: str) -> CodexSignIn:
        with self._lock:
            entry = self._sign_ins.get(sign_in_id)
        if entry is None:
            raise InvalidRequestError(f"no sign-in {sign_in_id}", provider="codex")
        return entry

    def _finish_sign_in(self, entry: CodexSignIn, state: str, reason: Optional[str], *, cancel: bool) -> None:
        entry.state, entry.reason = state, reason
        if cancel and entry.proc is not None:
            entry.proc.cancel()
        with self._lock:
            self._auth = None                                 # the next auth_status asks the CLI again
