"""`Router`: the one place that decides which provider answers a model call (connectors design 3.6, D17, D30-D33, D37, D38).

    plan       a pure function of the request, the policy and the cached health: which providers, in which order, with
               which model, and why each other one was dropped (no process; raises NoProviderError when none is left)
    attempts   per provider: the allowance gate and the provider's concurrency cap before every spawn, a retry of a
               retryable error up to `max_attempts` tries in all, then the next provider when the error allows it
    json       `call_json`: the connector's JSON strategy (native schema, prompted path, stateless repair rounds); the
               router adds the `native_blocked` memory: a schema whose native call ended in a `structured` error is sent
               prompted from then on (one failed call per process)
    usage      EXACTLY ONE `UsageIn` per request, a failed request included, built by `build_usage_row` and handed to the
               usage sink; the same keys ride in `CompletionResult.detail` and in a failed request's `ConnectorError.detail`
    chat       sessions: the provider session is a cache of the app's transcript; a provider switch or a lost session starts
               a new one with the deterministic carry-over of `transcript.py`
    health     `HealthBook` is updated after every spawn; `connector.health` and `connector.switch` events go out through
               the injected `events(type, data)` callback

The router never falls back to the stub on its own (D36). The caller keeps its budget (D38): the router applies only an
`Allowance` the caller sent and its own ceiling of `max_calls_per_request` spawns per request.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import random
import re
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Protocol, Sequence

from sutra_app.engine.port import Allowance, CompletionRequest, CompletionResult

from .base import ModelConnector, Hooks, CallInfo, CallRecord, prompted_prompt
from .errors import (
    CallCancelledError, ConnectorError, EnvelopeExceededError, InvalidJsonError, InvalidRequestError, NoProviderError,
    SessionLostError, StructuredError,
)
from .health import API_KEY_REFUSED, HealthBook, HealthState
from .jsonio import parse_reply
from .models import (
    AskRequest, ConnectorEvent, JsonRequest, JsonResult, M, Message, Provider, Quota, RouteContext, SESSION_ID_PATTERN,
    SessionSpec, SessionState, TurnResult,
)
from .policy import Resolved, RoutingPolicy
from .quota_windows import plan_label
from .schema import fits_native, schema_sha, to_json_schema
from .budget import carry_chars
from .discover import explain_missing
from .transcript import render_carry_over
from .independence import NOT_INDEPENDENT, Independence
from .usage import Attempt, UsageIn, UsageSink, build_usage_row, load_session_state, new_request_id, save_session_state

__all__ = [
    "Router", "Plan", "RouterStatus", "ProviderStatus", "PolicyInfo", "ModelBrief", "TodayCounts", "TranscriptSource",
    "mode_from_env", "CONNECTOR_MODES", "TRANSCRIPT_LIMIT", "NEW_MESSAGE_LABEL", "fallback_phrase",
]

log = logging.getLogger("sutra_app.connectors.router")

CONNECTOR_MODES = ("auto", "claude", "codex", "stub")
TRANSCRIPT_LIMIT = 20                 # `resume_info` gives at most 20 messages (ORCH 3.4), so the carry-over cap rarely bites
NEW_MESSAGE_LABEL = "New message:"    # separates the carry-over block from the message in the first prompt of a new session
_STUB_CONCURRENCY = 64
_SESSION_ID = re.compile(SESSION_ID_PATTERN)

# the words of the note "claude out of quota, answered by codex" (J2 llm.py:173,187)
_PHRASES = {
    "quota": "out of quota", "rate_limited": "rate limited", "overloaded": "overloaded", "server_error": "had a server error",
    "timeout": "timed out", "not_signed_in": "not signed in", "account_blocked": "account blocked", "cli_missing": "not installed",
    "cli_flag_unsupported": "does not support a needed flag", "crashed": "crashed", "protocol_error": "gave unreadable output",
    "provider_error": "had an error", "model_not_found": "has no such model", "empty_reply": "returned nothing",
    "invalid_json": "gave invalid JSON",
}


def fallback_phrase(code: str) -> str:
    return _PHRASES.get(code, code.replace("_", " "))


class TranscriptSource(Protocol):
    """Implemented by the orchestrator's `ChatTranscripts(chats)` (role agent becomes assistant, kinds text and question with
    state ok, the newest `limit` in order)."""

    def messages(self, session_id: str, limit: int = 20) -> list[Message]: ...


def mode_from_env(environ: Optional[Mapping[str, str]] = None) -> tuple[str, bool]:
    """`(connector, offline)` from `SUTRA_CONNECTOR` (auto|claude|codex|stub, default auto) and `SUTRA_OFFLINE` (`1`). The
    router itself reads no environment; the factory passes these to its constructor. A bad `SUTRA_CONNECTOR` is a ValueError."""
    env = os.environ if environ is None else environ
    connector = (env.get("SUTRA_CONNECTOR") or "auto").strip().lower() or "auto"
    if connector not in CONNECTOR_MODES:
        raise ValueError(f"SUTRA_CONNECTOR must be one of {', '.join(CONNECTOR_MODES)}, not {connector!r}")
    return connector, env.get("SUTRA_OFFLINE") == "1"


# ---- results ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """What `plan()` decided. `order` is the providers to try; `skipped` is every provider dropped, with the reason."""

    order: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]
    resolved: Resolved
    models: Mapping[str, str]
    tools: tuple[str, ...] = ()


class PolicyInfo(M):
    version: int
    source: str
    error: Optional[str] = None


class ModelBrief(M):
    slug: str
    label: str


class TodayCounts(M):
    calls: int = 0
    tokens: int = 0
    usd: float = 0.0


class ProviderStatus(M):
    name: str
    installed: bool
    version: Optional[str] = None
    signed_in: Optional[bool] = None
    method: Optional[str] = None
    billing: str = "unknown"
    plan: Optional[str] = None
    plan_label: Optional[str] = None          # the plan in words ("Claude Max", "ChatGPT Plus"; quota_windows.plan_label)
    account: Optional[str] = None
    detail: str = ""
    health: HealthState
    quota: Optional[Quota] = None
    models: list[ModelBrief] = []
    today: TodayCounts = TodayCounts()


class RouterStatus(M):
    """The router's part of `GET /api/connectors/status` (CN-9 adds `tools` and `mediated`)."""

    mode: str
    policy: PolicyInfo
    providers: list[ProviderStatus]


# ---- one request -----------------------------------------------------------------------------------------------------------

class _Request(Hooks):
    """The state of ONE request and the hooks the connectors call around every spawn.

    before_call: the allowance gate (deadline, max_calls, max_usd, the ceiling), then the provider's concurrency cap.
    after_call:  the attempt (for the usage row), the money spent, the HealthBook, `native_blocked`.
    finish:      builds and sinks the one usage row (once)."""

    def __init__(self, router: "Router", ctx: RouteContext, resolved: Resolved, *, kind: str, purpose: Optional[str] = None) -> None:
        self.router = router
        self.ctx = ctx
        self.resolved = resolved
        self.kind = kind                              # text | json | chat
        self.purpose = purpose
        self.request_id = new_request_id()
        self.started = router._clock()
        self.attempts: list[Attempt] = []
        self.spawns = 0
        self.usd_spent = 0.0
        self.failures: list[tuple[str, ConnectorError]] = []
        self.note: Optional[str] = None
        self.default_provider: Optional[str] = None
        self.last_native = False
        self.row: Optional[UsageIn] = None
        self._held: list[threading.Semaphore] = []

    # ---- the gate ---------------------------------------------------------------------------------------------------------
    def _exceeded(self, limit: str, message: str) -> EnvelopeExceededError:
        return EnvelopeExceededError(message, detail={"limit": limit, "calls_made": self.spawns, "usd_spent": round(self.usd_spent, 9),
                                                      "envelope_id": self.ctx.allowance.envelope_id})

    def check_gate(self) -> None:
        a = self.ctx.allowance
        if a.deadline is not None and self.router._clock() >= a.deadline:
            raise self._exceeded("deadline", "the envelope's deadline has passed")
        if a.max_calls is not None and self.spawns >= a.max_calls:
            raise self._exceeded("max_calls", f"the envelope allows {a.max_calls} model call{'s' if a.max_calls != 1 else ''} "
                                              f"for this request and {self.spawns} were made")
        if a.max_usd is not None and self.usd_spent >= a.max_usd:
            raise self._exceeded("max_usd", f"the envelope allows ${a.max_usd:g} for this request and ${self.usd_spent:g} was spent")
        if self.spawns >= self.resolved.max_calls_per_request:
            raise self._exceeded("max_calls_per_request", f"the router allows at most {self.resolved.max_calls_per_request} "
                                                         "model calls for one request")

    def connector_ctx(self) -> RouteContext:
        """The context a connector sees: `max_usd` reduced by what earlier spawns of this request spent."""
        a = self.ctx.allowance
        if a.max_usd is None:
            return self.ctx
        return self.ctx.model_copy(update={"allowance": a.model_copy(update={"max_usd": max(0.0, a.max_usd - self.usd_spent)})})

    def timeout_s(self) -> float:
        """The call timeout, cut to the time left until the envelope's deadline (at least one second)."""
        timeout = self.resolved.timeout_s
        deadline = self.ctx.allowance.deadline
        if deadline is not None:
            timeout = min(timeout, max(1.0, deadline - self.router._clock()))
        return timeout

    # ---- Hooks ------------------------------------------------------------------------------------------------------------
    def before_call(self, info: CallInfo) -> None:
        self.check_gate()
        sem = self.router._semaphore(info.provider)
        sem.acquire()
        try:
            self.check_gate()                         # the deadline may have passed while this request waited for the cap
        except BaseException:
            sem.release()
            raise
        self._held.append(sem)
        self.spawns += 1
        self.last_native = info.native

    def after_call(self, record: CallRecord) -> None:
        sem = self._held.pop() if self._held else None
        try:
            self._record(record)
        finally:
            if sem is not None:
                sem.release()

    def on_quota(self, provider: str, quota: Quota) -> None:
        self.router._health_update(provider, quota=quota)

    def _record(self, record: CallRecord) -> None:
        info, turn = record.info, record.turn
        provider = info.provider
        usage = turn.usage if record.ok and turn is not None else None
        usd = record.usd if record.ok else None
        auth = self.router.health.peek_auth(provider)
        self.attempts.append(Attempt(
            provider=provider, model=(turn.model if turn is not None else None) or info.model, effort=info.effort,
            code="ok" if record.ok else (record.code or "provider_error"), usage=usage, usd=usd,
            usd_basis=turn.usd_basis if turn is not None else "none", seconds=record.seconds, cli_version=record.cli_version,
            billing=auth.billing if auth is not None else "unknown"))
        self.usd_spent += usd or 0.0
        if record.ok:
            self.router.independence.note(self.ctx, provider)
        self.router._count_today(provider, usage.total if usage is not None else 0, usd or 0.0)
        if record.code == "structured" and record.native_schema_sha:
            self.router._block_native(provider, record.native_schema_sha)
        self.router._health_update(provider, error=record.error, quota=turn.quota if turn is not None else None)

    # ---- the usage row ----------------------------------------------------------------------------------------------------
    def _how(self, result_how: Optional[str]) -> str:
        provider = self.attempts[-1].provider if self.attempts else self.default_provider
        if self.kind == "chat":
            return "chat"
        if provider == "stub":
            return "stub"
        if result_how:
            return result_how
        if self.kind == "json":
            return "native" if self.last_native else "prompted"
        return "text"

    def finish(self, *, ok: bool, error: Optional[BaseException] = None, result_how: Optional[str] = None) -> UsageIn:
        if self.row is not None:
            return self.row
        provider = self.default_provider or (self.resolved.order[0] if self.resolved.order else "stub")
        self.row = build_usage_row(
            ctx=self.ctx, attempts=self.attempts, request_id=self.request_id, ok=ok, how=self._how(result_how if ok else None),
            purpose=self.purpose, seconds=max(0.0, self.router._clock() - self.started), note=self.note,
            provider=provider)           # type: ignore[arg-type]
        if isinstance(error, ConnectorError) and not ok:
            error.detail.update(self.row.detail or {})
        sink = self.router.usage_sink
        if sink is not None:
            try:
                sink.record(self.row)
            except Exception:             # a lost ledger row must not turn a model answer into a failure
                log.warning("the usage sink refused a row (request %s)", self.request_id, exc_info=True)
        return self.row


# ---- the router ------------------------------------------------------------------------------------------------------------

class Router:
    def __init__(self, connectors: Mapping[str, ModelConnector], policy: RoutingPolicy, *, usage_sink: Optional[UsageSink] = None,
                 health: Optional[HealthBook] = None, transcripts: Optional[TranscriptSource] = None,
                 events: Optional[Callable[[str, dict], None]] = None,
                 session_hook: Optional[Callable[[str, Provider, str, Optional[str]], None]] = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time,
                 rng: Callable[[], float] = random.random, connector: str = "auto", offline: bool = False,
                 policy_source: str = "default", policy_error: Optional[str] = None) -> None:
        if connector not in CONNECTOR_MODES:
            raise ValueError(f"connector must be one of {', '.join(CONNECTOR_MODES)}, not {connector!r}")
        self._connectors: dict[str, ModelConnector] = dict(connectors)
        self.policy = policy
        self.usage_sink = usage_sink
        self._clock = clock
        self.health = health or HealthBook(clock=clock)
        self.transcripts = transcripts
        self._events = events
        self._session_hook = session_hook
        self._sleep = sleep
        self._rng = rng
        self._offline = bool(offline)
        self._restrict: Optional[str] = "stub" if offline else (None if connector == "auto" else connector)
        self.policy_source = policy_source
        self.policy_error = policy_error
        self.native_blocked: set[tuple[str, str]] = set()      # (provider, sha of the native schema) whose native call ended in `structured`
        self._lock = threading.RLock()
        self._sems: dict[str, threading.Semaphore] = {}
        self._closed = threading.Event()
        self._chat_busy: set[str] = set()
        self._chat_stop_early: set[str] = set()        # a Stop that arrived before the turn's process was registered
        self._chat_active: dict[str, tuple[ModelConnector, SessionState]] = {}
        self._pins: dict[str, str] = {}
        self.choice_source: Optional[Callable[[str], Optional[str]]] = None      # session id -> the owner's persisted provider choice (ABS-8)
        self.egress: Optional[Any] = None                      # an `egress.Egress`, set by the factory (ABS-2); None = no scrub, no row
        self.independence = Independence()                     # who built a run's work, so Audit can go to the other model (off unless the policy says so)
        self._today: dict[str, list] = {}                      # provider -> [date, calls, tokens, usd]
        self._background: list[threading.Thread] = []

    # ---- small things --------------------------------------------------------------------------------------------------------
    @property
    def connectors(self) -> Mapping[str, ModelConnector]:
        return dict(self._connectors)

    @property
    def mode(self) -> str:
        return "offline" if self._restrict == "stub" else "live"

    def _emit(self, type_: str, data: dict) -> None:
        if self._events is None:
            return
        try:
            self._events(type_, data)
        except Exception:
            log.warning("the event callback failed for %s", type_, exc_info=True)

    def _semaphore(self, provider: str) -> threading.Semaphore:
        with self._lock:
            sem = self._sems.get(provider)
            if sem is None:
                limit = self.policy.max_concurrency(provider) if provider in self.policy.providers else _STUB_CONCURRENCY
                sem = self._sems[provider] = threading.BoundedSemaphore(limit)
            return sem

    def _block_native(self, provider: str, sha: str) -> None:
        with self._lock:
            self.native_blocked.add((provider, sha))

    def _is_blocked(self, provider: str, connector: ModelConnector, schema: dict) -> bool:
        with self._lock:
            if not self.native_blocked:
                return False
            blocked = set(self.native_blocked)
        return (provider, schema_sha(connector.transport_schema(schema))) in blocked

    def _health_update(self, provider: str, *, error: Optional[ConnectorError] = None, quota: Optional[Quota] = None) -> None:
        before = self.health.state(provider)               # type: ignore[arg-type]
        self.health.update(provider, error=error, quota=quota)       # type: ignore[arg-type]
        after = self.health.state(provider)                # type: ignore[arg-type]
        if after != before:
            self._emit("connector.health", {"provider": provider, "state": after.state, "until": after.until, "reason": after.reason})

    def _count_today(self, provider: str, tokens: int, usd: float) -> None:
        today = datetime.fromtimestamp(self._clock()).strftime("%Y-%m-%d")
        with self._lock:
            row = self._today.get(provider)
            if row is None or row[0] != today:
                row = self._today[provider] = [today, 0, 0, 0.0]
            row[1] += 1
            row[2] += tokens
            row[3] += usd

    def _reject_closed(self) -> None:
        if self._closed.is_set():
            raise CallCancelledError("the model router was closed")

    @staticmethod
    def _check_images(images: Sequence[str]) -> None:
        for path in images:
            if not Path(str(path)).is_file():
                raise InvalidRequestError(f"image not found: {path}")

    # ---- plan --------------------------------------------------------------------------------------------------------------
    def plan(self, req: AskRequest, *, pinned: Optional[str] = None) -> Plan:
        """Pure: no process is started (a stale health cache runs a status command, never a model call). Raises
        NoProviderError with a reason for every provider dropped."""
        return self._plan(self.policy.resolve(req), req, pinned)

    def _chosen_for(self, req: Any) -> Optional[str]:
        """The owner's persisted choice for the session of this call, if the app gave the Router a source for it."""
        sid = getattr(getattr(req, "ctx", None), "session_id", None)
        if self.choice_source is None or not sid:
            return None
        try:
            return self.choice_source(sid) or None
        except Exception:
            log.warning("could not read the chat choice of %s", sid, exc_info=True)
            return None

    def _plan(self, resolved: Resolved, req: Any, pinned: Optional[str] = None) -> Plan:
        chosen = None
        if pinned is None:
            pinned = chosen = self._chosen_for(req)
        order = list(resolved.order)
        if self._restrict is not None:
            order = [self._restrict]
            pinned = pinned if pinned == self._restrict else None
        avoid = set(req.ctx.avoid)
        if self.policy.defaults.independent_audit:                  # GAP2 rules-notes: the checker is not the maker (soft: tried last)
            avoid |= set(self.independence.avoid_for(req.ctx))
        if avoid:
            order = [p for p in order if p not in avoid] + [p for p in order if p in avoid]
        if pinned is not None and pinned in self._connectors:
            order = [pinned] + [p for p in order if p != pinned]
        tools = tuple(req.tools) or (() if resolved.tool_profile == "none" else tuple(resolved.tool_profile.split("+")))
        skipped: list[tuple[str, str]] = []
        usable: list[str] = []
        models: dict[str, str] = {}
        for provider in order:
            reason = self._skip_reason(provider, bool(req.images), bool(tools))
            if reason is None:
                try:
                    models[provider] = self._connectors[provider].resolve_model(self.policy.model_for(provider))   # type: ignore[arg-type]
                except ConnectorError as e:
                    reason = e.user_message()
            if reason is None:
                usable.append(provider)
            else:
                skipped.append((provider, reason))
        if not usable:
            raise NoProviderError(skipped=skipped)
        if chosen is not None and chosen not in usable:           # the pill said one thing, the policy order decides: say so
            self._emit("connector.choice_unavailable", {"session_id": req.ctx.session_id, "wanted": chosen,
                                                         "reason": dict(skipped).get(chosen, "not usable"), "used": usable[0]})
        return Plan(order=tuple(usable), skipped=tuple(skipped), resolved=resolved, models=models, tools=tools)

    def _skip_reason(self, provider: str, need_images: bool, need_tools: bool) -> Optional[str]:
        connector = self._connectors.get(provider)
        if connector is None:
            return "not configured"
        entry = self.policy.providers.get(provider)      # type: ignore[call-overload]
        if entry is None and provider != "stub":
            return "not in the routing policy"
        if entry is not None and not entry.enabled:
            return "disabled in the routing policy"
        if need_images and not connector.capabilities.images:
            return "cannot take images"
        if need_tools and not connector.capabilities.mcp:
            return "cannot use tools"
        if provider != "stub":
            exe = self._exe(connector)
            if not self.health.installed(provider, lambda: shutil.which(exe) is not None):          # type: ignore[arg-type]
                if provider == "codex":
                    return "CLI not found on PATH (install it and run `codex login`)"
                return explain_missing(provider, self._desktop(connector), f"CLI not found on PATH (install it and run `{provider}` once)")
            try:
                status = self.health.auth(provider, connector.auth_status)                         # type: ignore[arg-type]
            except ConnectorError as e:
                return e.user_message()
            if status.signed_in is False:
                return ("not signed in: use Sign in or run `codex login`" if provider == "codex"
                        else f"not signed in: run `{provider} auth login`")
            if status.billing == "api_key":
                return API_KEY_REFUSED
        block = self.health.cooldown(provider)               # type: ignore[arg-type]
        if block is not None:
            return f"{block.reason}, retry after {datetime.fromtimestamp(block.until).strftime('%H:%M:%S')}"
        return None

    @staticmethod
    def _exe(connector: ModelConnector) -> str:
        return str(getattr(connector.cfg, f"{connector.name}_exe", connector.name))

    @staticmethod
    def _desktop(connector: ModelConnector) -> bool:
        """Claude Desktop is installed on this Mac (discover.py): a missing `claude` is then named as Claude Code, not as a PATH problem."""
        return bool(getattr(connector.cfg, "claude_desktop", False))

    # ---- attempts ----------------------------------------------------------------------------------------------------------
    def _may_fall_back(self, err: ConnectorError, resolved: Resolved) -> bool:
        return err.fallback_ok or (err.code == "invalid_json" and resolved.fallback_on_invalid_json)

    def _independence_note(self, state: "_Request", provider: str, note: Optional[str]) -> Optional[str]:
        """With independent audit on: when a call of Audit was answered by a model that built this run's work (the other one was not
        available, or the team is pinned), the note says the audit was not independent. The note rides the usage row and J2's progress line."""
        tag = state.ctx.tag
        if not self.policy.defaults.independent_audit or tag.function != "audit" or provider not in self.independence.builders(tag.run_id):
            return note
        return f"{note}; {NOT_INDEPENDENT}" if note else NOT_INDEPENDENT

    def _note(self, failures: Sequence[tuple[str, ConnectorError]], answered_by: str) -> Optional[str]:
        if not failures:
            return None
        return ", ".join(f"{p} {fallback_phrase(e.code)}" for p, e in failures) + f", answered by {answered_by}"

    def _drive(self, state: _Request, plan: Plan, make: Callable[[Plan, str, ModelConnector], Iterator[Any]]) -> Iterator[Any]:
        """The attempt loop, as a generator: it yields what `make(...)` yields and returns the value `make(...)` returns.

        Per provider: gate, then the call; a retryable error is tried again after the policy's delay while the provider has
        had fewer than `max_attempts` tries (J2 `range(2)`: the default is one retry); then, when the error allows it, the
        next provider. Any other error propagates (the last error of the last provider)."""
        order = plan.order
        for index, provider in enumerate(order):
            connector = self._connectors[provider]
            tries = 0
            while True:
                self._reject_closed()
                state.check_gate()
                tries += 1
                try:
                    result = yield from make(plan, provider, connector)
                except ConnectorError as err:
                    if self._closed.is_set():
                        raise
                    if err.retryable and tries < plan.resolved.max_attempts:
                        state.check_gate()                         # no point waiting for a retry the envelope will refuse
                        delay = plan.resolved.retry_delay(tries - 1)
                        if delay > 0:
                            self._sleep(delay + self._rng())
                        continue
                    if self._may_fall_back(err, plan.resolved) and index + 1 < len(order):
                        state.failures.append((provider, err))
                        break
                    raise
                state.note = self._independence_note(state, provider, self._note(state.failures, provider))
                return result
        raise AssertionError("unreachable: the last provider returns or raises")       # pragma: no cover

    @staticmethod
    def _consume(gen: Iterator[Any]) -> Any:
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            return stop.value

    # ---- text and schema-text requests ---------------------------------------------------------------------------------------
    def ask(self, req: AskRequest, on_progress: Optional[Callable[[dict], None]] = None) -> TurnResult:
        return self._ask(req, on_progress)[0]

    def _ask(self, req: AskRequest, on_progress: Optional[Callable[[dict], None]]) -> tuple[TurnResult, _Request]:
        def make(plan: Plan, provider: str, connector: ModelConnector) -> Iterator[Any]:
            return _once(lambda: self._text_call(state, plan, req, provider, connector, on_progress))

        resolved = self.policy.resolve(req)
        state = _Request(self, req.ctx, resolved, kind="text" if req.schema is None else "json")
        ok, failure = False, None
        try:
            self._reject_closed()
            self._check_images(req.images)
            plan = self._plan(resolved, req)
            state.default_provider = plan.order[0]
            if self.egress is not None:                      # J2's prompts are not ours to edit: observe only, byte-identical
                self.egress.check(req.user, system=req.system, session=req.ctx.session_id, provider=plan.order[0], replace=False)
            turn = self._consume(self._drive(state, plan, make))
            ok = True
            if state.note and on_progress is not None:
                on_progress({"note": state.note})          # J2 llm.py:173,187: the owner sees that another provider answered
            return turn, state
        except BaseException as exc:
            failure = exc
            raise
        finally:
            state.finish(ok=ok, error=failure)

    def _text_call(self, state: _Request, plan: Plan, req: AskRequest, provider: str, connector: ModelConnector,
                   on_progress: Optional[Callable[[dict], None]]) -> TurnResult:
        """One connector call for a text request (or a text request that carries a schema: the engine's `json_schema`)."""
        on_event = _progress(on_progress)
        model = plan.models[provider]
        scripted = req.scripted if provider == "stub" else None
        if req.schema is None:
            kw: dict[str, Any] = {"scripted": scripted} if scripted is not None else {}
            return connector.call_text(req.user, system=req.system, images=req.images, tools=plan.tools, timeout=state.timeout_s(),
                                       ctx=state.connector_ctx(), effort=plan.resolved.effort, model=model, hooks=state,
                                       on_event=on_event, partials=req.partials, **kw)
        return self._schema_text(state, plan, req, provider, connector, model, scripted, on_event)

    def _schema_text(self, state: _Request, plan: Plan, req: AskRequest, provider: str, connector: ModelConnector, model: str,
                     scripted: Optional[Callable[[], str]], on_event: Optional[Callable[[ConnectorEvent], None]]) -> TurnResult:
        """The native step of the JSON strategy and nothing more (`complete()` never repairs, D33): the reply text is returned as
        it came; the engine validates it. A `structured` error on the native path is remembered and the same request goes
        prompted once."""
        schema = to_json_schema(req.schema)                         # type: ignore[arg-type]
        native = connector.capabilities.native_schema and fits_native(schema) and not self._is_blocked(provider, connector, schema)

        def plan_for(native_now: bool):
            return connector._oneshot_plan(                           # the base's own plan builder: same checks as call_text
                req.user if native_now else prompted_prompt(req.user, schema), system=req.system, kind="json", model=model,
                effort=plan.resolved.effort, timeout=state.timeout_s(), ctx=state.connector_ctx(), images=req.images,
                tools=plan.tools, schema=connector.transport_schema(schema) if native_now else None, partials=False, spent=0.0)

        scope = connector._request(schema, scripted) if provider == "stub" else contextlib.nullcontext()   # type: ignore[attr-defined]
        with scope:
            try:
                turn = connector._execute(plan_for(native), state, on_event)
            except StructuredError:
                if not native:
                    raise
                native = False
                turn = connector._execute(plan_for(False), state, on_event)
        if native:
            try:                                                      # Codex: the strict schema forced nulls in; drop them
                value = parse_reply(turn.text)
                cleaned = connector.clean_native(value, schema)
                if cleaned != value:
                    turn = turn.model_copy(update={"text": json.dumps(cleaned, ensure_ascii=False)})
            except InvalidJsonError:
                pass
        return turn

    # ---- JSON requests ------------------------------------------------------------------------------------------------------
    def call_json(self, req: JsonRequest, on_progress: Optional[Callable[[dict], None]] = None) -> JsonResult:
        """The connector's JSON strategy per provider (native, prompted, repair rounds), then the router's retry and fallback.
        `value` is a pydantic instance for a class schema; with no schema the reply is parsed to a dict (prompted path)."""
        def make(plan: Plan, provider: str, connector: ModelConnector) -> Iterator[Any]:
            return _once(lambda: self._json_call(state, plan, req, provider, connector, on_progress))

        resolved = self.policy.resolve(req)
        state = _Request(self, req.ctx, resolved, kind="json")
        ok, failure, result = False, None, None
        try:
            self._reject_closed()
            self._check_images(req.images)
            plan = self._plan(resolved, req)
            state.default_provider = plan.order[0]
            if self.egress is not None:
                req = req.model_copy(update={
                    "user": self.egress.check(req.user, session=req.ctx.session_id, provider=plan.order[0], replace=True),
                    "system": self.egress.check(req.system, session=req.ctx.session_id, provider=plan.order[0], replace=True) if req.system else ""})
            result = self._consume(self._drive(state, plan, make))
            ok = True
            if state.note and on_progress is not None:
                on_progress({"note": state.note})
        except BaseException as exc:
            failure = exc
            raise
        finally:
            state.finish(ok=ok, error=failure, result_how=result.how if result is not None else None)
        assert state.row is not None
        return result.model_copy(update={"usd": state.row.usd, "calls_made": state.spawns, "usd_spent": round(state.usd_spent, 9)})

    def _json_call(self, state: _Request, plan: Plan, req: JsonRequest, provider: str, connector: ModelConnector,
                   on_progress: Optional[Callable[[dict], None]]) -> JsonResult:
        schema = req.schema if req.schema is not None else {"type": "object"}
        force = req.schema is None or self._is_blocked(provider, connector, to_json_schema(schema))
        kw: dict[str, Any] = {"scripted": req.scripted} if provider == "stub" and req.scripted is not None else {}
        return connector.call_json_result(
            req.user, plan.tools, schema, state.timeout_s(), system=req.system, ctx=state.connector_ctx(), effort=plan.resolved.effort,
            model=plan.models[provider], images=req.images, hooks=state, on_event=_progress(on_progress), force_prompted=force,
            repair_rounds=plan.resolved.repair_rounds, **kw)

    # ---- the engine seam ------------------------------------------------------------------------------------------------------
    def complete(self, req: CompletionRequest, on_progress: Optional[Callable[[dict], None]] = None) -> CompletionResult:
        """`CompletionRequest` in, `CompletionResult` out (connectors 3.10). With a `json_schema` only the native step runs and the
        reply text comes back as it is; the router never repairs here, so every call the engine pays for is a call it sees."""
        ask = AskRequest(
            system=req.system, user=req.user, ctx=RouteContext(tag=req.tag, allowance=req.allowance or Allowance()),
            kind="json" if (req.json_mode or req.json_schema is not None) else "text", effort=req.effort, images=list(req.images),
            schema=req.json_schema, timeout_s=req.timeout_s, partials=on_progress is not None and req.json_schema is None,
            scripted=req.scripted)
        turn, state = self._ask(ask, on_progress)
        row = state.row
        assert row is not None
        stub = turn.provider == "stub"
        return CompletionResult(
            text=turn.text if stub else turn.text.strip(), model=turn.model, provider=turn.provider,
            input_tokens=turn.usage.input_total, output_tokens=turn.usage.output_tokens, usd=row.usd, duration_ms=turn.duration_ms,
            session_id=turn.provider_session_id,
            structured={"provider": turn.provider, "subtype": turn.subtype, "present": turn.structured is not None}
            if req.json_schema is not None else None,
            note=state.note, detail=row.detail)

    # ---- chat sessions -------------------------------------------------------------------------------------------------------------
    def _workdir(self, session_id: str) -> Path:
        if _SESSION_ID.fullmatch(session_id or "") is None:
            raise InvalidRequestError("session_id must be 1 to 64 characters of letters, digits, '_' or '-' (it names a directory)")
        if not self._connectors:
            raise NoProviderError("no connector is configured")
        cfg = next(iter(self._connectors.values())).cfg
        return Path(os.path.realpath(cfg.resolved_work_root() / session_id))

    def chat_start(self, spec: SessionSpec, ctx: Optional[RouteContext] = None) -> SessionState:
        """Creates the work dir and `session.json` with the provider the plan chose (the pinned one first, then the policy), or
        `spec.provider`. No process is started."""
        ctx = (ctx or RouteContext()).model_copy(update={"session_id": spec.session_id})
        req = AskRequest(user="chat", ctx=ctx, kind="text")
        resolved = self.policy.resolve(req)
        plan = self._plan(resolved, req, pinned=spec.provider or self._pins.get(spec.session_id))
        provider = plan.order[0]
        if spec.provider is not None and provider != spec.provider:
            raise NoProviderError(skipped=list(plan.skipped), detail={"wanted": spec.provider})
        connector = self._connectors[provider]
        state = connector.start(spec.model_copy(update={
            "provider": provider, "model": spec.model or plan.models[provider], "effort": spec.effort or resolved.effort,
            "tool_profile": spec.tool_profile if spec.tool_profile != "none" else resolved.tool_profile}))
        pinned = self._pins.get(spec.session_id)
        if pinned is not None:
            state.pinned = pinned          # type: ignore[assignment]
            save_session_state(state)
        return state

    def chat_send(self, session_id: str, m: Message, ctx: Optional[RouteContext] = None,
                  on_event: Optional[Callable[[ConnectorEvent], None]] = None) -> TurnResult:
        """One turn. A second send to a session that is running a turn raises InvalidRequestError (`detail.busy`)."""
        result: Optional[TurnResult] = None
        for event in self._chat(session_id, m, ctx or RouteContext(), partials=on_event is not None):
            if event.kind == "turn_done":
                result = TurnResult.model_validate(event.data["result"])
            elif on_event is not None:
                on_event(event)
        assert result is not None
        return result

    def chat_stream(self, session_id: str, m: Message, ctx: Optional[RouteContext] = None) -> Iterator[ConnectorEvent]:
        """The events of one turn; the last one is `turn_done` with `data["result"]`. Errors surface while iterating."""
        return self._chat(session_id, m, ctx or RouteContext(), partials=True)

    def chat_stop(self, session_id: str) -> bool:
        with self._lock:
            active = self._chat_active.get(session_id)
            if active is None and session_id in self._chat_busy:
                self._chat_stop_early.add(session_id)        # the turn is being set up: it ends before any process starts
                return True
        return False if active is None else active[0].stop(active[1])

    def chat_pin(self, session_id: str, provider: Optional[str]) -> None:
        """Pins the chat's provider (the next send switches to it, if it is usable) or clears the pin with None."""
        self._workdir(session_id)
        if provider is not None and provider not in self._connectors:
            raise InvalidRequestError(f"{provider} is not a configured provider")
        with self._lock:
            if provider is None:
                self._pins.pop(session_id, None)
            else:
                self._pins[session_id] = provider
        stored = load_session_state(self._workdir(session_id))
        if stored is not None:
            stored.pinned = provider        # type: ignore[assignment]
            save_session_state(stored)

    def _chat(self, session_id: str, m: Message, ctx: RouteContext, *, partials: bool) -> Iterator[ConnectorEvent]:
        sid = session_id
        self._workdir(sid)
        with self._lock:
            if sid in self._chat_busy:
                raise InvalidRequestError(f"session {sid} is already running a turn", detail={"busy": True})
            self._chat_busy.add(sid)
            self._chat_stop_early.discard(sid)
        try:
            ctx = ctx.model_copy(update={"session_id": sid})
            req = AskRequest(user=m.text, ctx=ctx, kind="text", images=list(m.images))
            resolved = self.policy.resolve(req)
            state = _Request(self, ctx, resolved, kind="chat", purpose="chat")
            ok, failure = False, None
            try:
                if m.role != "user":
                    raise InvalidRequestError("a chat turn is sent as a user message")
                self._reject_closed()
                self._check_images(m.images)
                stored = load_session_state(self._workdir(sid))
                plan = self._plan(resolved, req, pinned=stored.pinned if stored is not None else self._pins.get(sid))
                state.default_provider = plan.order[0]

                def make(plan_: Plan, provider: str, connector: ModelConnector) -> Iterator[Any]:
                    return self._chat_turn(state, plan_, provider, connector, m, partials)

                turn = yield from self._drive(state, plan, make)
                ok = True
                yield ConnectorEvent(kind="turn_done", data={"result": turn.model_dump(mode="json")})
            except BaseException as exc:
                failure = exc
                raise
            finally:
                state.finish(ok=ok, error=failure)
        finally:
            with self._lock:
                self._chat_busy.discard(sid)
                self._chat_stop_early.discard(sid)

    def _read_system(self, workdir: Path) -> str:
        try:
            return (workdir / "system.txt").read_text(encoding="utf-8")
        except OSError:
            return ""

    def _transcript(self, session_id: str, m: Message) -> list[Message]:
        if self.transcripts is None:
            return []
        found = list(self.transcripts.messages(session_id, TRANSCRIPT_LIMIT))
        if found and found[-1].role == "user" and found[-1].text == m.text:
            found = found[:-1]            # the owner's message is stored before the call; it is sent as the new message, not as history
        return found

    def _new_session(self, state: _Request, plan: Plan, provider: str, connector: ModelConnector, old: Optional[SessionState],
                     m: Message) -> tuple[SessionState, str, bool]:
        """A new provider session in the same work dir, with the carry-over in front of the message.
        -> (state, first prompt, whether it replaces a live session of the app's)"""
        sid = state.ctx.session_id or ""
        workdir = self._workdir(sid)
        pinned = old.pinned if old is not None else self._pins.get(sid)
        replaces = old is not None and (old.provider != provider or old.provider_session_id is not None)
        same = old is not None and old.provider == provider
        fresh = connector.start(SessionSpec(
            session_id=sid, provider=provider, model=old.model if same and old is not None else plan.models[provider],
            effort=old.effort if old is not None else plan.resolved.effort,
            tool_profile=old.tool_profile if old is not None else plan.resolved.tool_profile, system=self._read_system(workdir)))
        fresh.turns = old.turns if old is not None else 0
        fresh.switches = (old.switches + (1 if replaces else 0)) if old is not None else 0
        fresh.pinned = pinned          # type: ignore[assignment]
        save_session_state(fresh)
        window = carry_chars(provider, fresh.model)
        carry = render_carry_over(self._transcript(sid, m), from_provider=old.provider if old is not None else None, to_provider=provider,
                                  budget=window["full_chars"])
        return fresh, (f"{carry}\n\n{NEW_MESSAGE_LABEL}\n{m.text}" if carry else m.text), replaces

    def _chat_turn(self, state: _Request, plan: Plan, provider: str, connector: ModelConnector, m: Message,
                   partials: bool) -> Iterator[ConnectorEvent]:
        sid = state.ctx.session_id or ""
        lost = False
        for round_no in (1, 2):
            old = load_session_state(self._workdir(sid))
            session: Optional[SessionState] = None
            text, replaces = m.text, False
            if old is not None and not lost and old.provider == provider and old.provider_session_id is not None:
                session = connector.resume(old)
                if session.provider_session_id is None:         # the work dir was lost: the provider session went with it
                    session = None
            if session is None:
                session, text, replaces = self._new_session(state, plan, provider, connector, old, m)
            previous_id = None if (old is None or lost or old.provider != provider) else old.provider_session_id
            if self.egress is not None:
                text = self.egress.check(text, session=sid, provider=provider, replace=True)
            with self._lock:
                stopped_early = sid in self._chat_stop_early
                self._chat_stop_early.discard(sid)
                if not stopped_early:
                    self._chat_active[sid] = (connector, session)
            if stopped_early:
                raise CallCancelledError("the turn was stopped before it started", provider=provider)
            turn: Optional[TurnResult] = None
            try:
                for event in connector.stream(session, Message(role="user", text=text, images=list(m.images)),
                                              timeout_s=state.timeout_s(), partials=partials, hooks=state):
                    if event.kind == "turn_done":
                        turn = TurnResult.model_validate(event.data["result"])
                    else:
                        yield event
            except SessionLostError:
                if round_no == 2:
                    raise
                lost = True
                continue
            finally:
                with self._lock:
                    if self._chat_active.get(sid, (None, None))[1] is session:
                        del self._chat_active[sid]
            assert turn is not None
            self._after_turn(state, provider, old, session, previous_id, replaces, lost, plan)
            return turn
        raise AssertionError("unreachable")       # pragma: no cover

    def _after_turn(self, state: _Request, provider: str, old: Optional[SessionState], session: SessionState,
                    previous_id: Optional[str], replaces: bool, lost: bool, plan: Plan) -> None:
        sid = state.ctx.session_id or ""
        if replaces and old is not None:
            if lost:
                reason = "session lost"
            elif state.failures:
                reason = fallback_phrase(state.failures[-1][1].code)
            elif old.pinned == provider:
                reason = "pinned"
            else:
                reason = "policy"
            self._emit("connector.switch", {"session_id": sid, "from": old.provider, "to": provider, "reason": reason})
            if old.provider != provider and old.provider_session_id is not None and old.provider in self._connectors:
                self._forget_later(self._connectors[old.provider], old)
        if (replaces or session.provider_session_id != previous_id) and self._session_hook is not None:
            try:
                self._session_hook(sid, provider, session.model, session.provider_session_id)       # type: ignore[arg-type]
            except Exception:
                log.warning("the session hook failed for %s", sid, exc_info=True)

    def _forget_later(self, connector: ModelConnector, old: SessionState) -> None:
        """Best effort, in the background: remove the old provider's own transcript of the session."""
        def run() -> None:
            try:
                connector.forget(old)
            except Exception:
                log.warning("forget failed for session %s", old.session_id, exc_info=True)

        thread = threading.Thread(target=run, name=f"forget-{old.session_id}", daemon=True)
        with self._lock:
            self._background = [t for t in self._background if t.is_alive()] + [thread]
        thread.start()

    def drain(self, timeout: float = 10.0) -> None:
        """Waits for the background work (forgetting old provider sessions)."""
        with self._lock:
            threads = list(self._background)
        for t in threads:
            t.join(timeout)

    # ---- status and shutdown --------------------------------------------------------------------------------------------------------
    def provider_summary(self, name: str, *, refresh: bool = False, models: bool = False) -> ProviderStatus:
        """One provider as `GET /api/connectors/status` shows it. Never a model call; a status command runs only when its cache
        is older than 30 s (or `refresh`)."""
        connector = self._connectors[name]
        health = self.health.state(name)             # type: ignore[arg-type]
        quota = self.health.quota(name)              # type: ignore[arg-type]
        installed, auth, detail = True, None, ""
        if name != "stub":
            exe = self._exe(connector)
            if refresh:
                self.health.forget_installed(name)   # type: ignore[arg-type]
            installed = self.health.installed(name, lambda: shutil.which(exe) is not None)       # type: ignore[arg-type]
            if installed:
                try:
                    auth = self.health.auth(name, lambda: connector.auth_status(refresh=refresh), refresh=refresh)    # type: ignore[arg-type]
                except ConnectorError as e:
                    detail = e.user_message()
            else:
                detail = explain_missing(name, self._desktop(connector), "CLI not found on PATH")
            health = self.health.state(name)         # type: ignore[arg-type]
        listed: list[ModelBrief] = []
        if models and installed and (auth is None or auth.signed_in is not False):
            try:
                listed = [ModelBrief(slug=mi.slug, label=mi.label) for mi in connector.models() if mi.listed]
            except ConnectorError:
                listed = []
        with self._lock:
            counts = self._today.get(name)
        today_key = datetime.fromtimestamp(self._clock()).strftime("%Y-%m-%d")
        today = TodayCounts(calls=counts[1], tokens=counts[2], usd=round(counts[3], 9)) if counts and counts[0] == today_key else TodayCounts()
        plan = (auth.plan if auth else None) or (quota.plan if quota is not None else None)    # Codex names its plan only in a quota
        return ProviderStatus(
            name=name, installed=installed, version=auth.version if auth else None, signed_in=auth.signed_in if auth else (True if name == "stub" else None),
            method=auth.method if auth else None, billing=auth.billing if auth else "unknown", plan=plan, plan_label=plan_label(name, plan),
            account=auth.account if auth else None, detail=(auth.detail if auth else detail), health=health, quota=quota, models=listed,
            today=today)

    def status(self, *, refresh: bool = False) -> RouterStatus:
        return RouterStatus(
            mode=self.mode, policy=PolicyInfo(version=self.policy.version, source=self.policy_source, error=self.policy_error),
            providers=[self.provider_summary(name, refresh=refresh, models=True) for name in self._connectors])

    def close(self) -> None:
        """Stops every running child (the cancel ladder) and refuses new work. Safe to call twice."""
        self._closed.set()
        with self._lock:
            active = list(self._chat_active.values())
        for connector, session in active:
            try:
                connector.stop(session)
            except Exception:
                log.warning("stop failed for session %s", session.session_id, exc_info=True)
        for connector in self._connectors.values():
            try:
                connector.runner.stop_all()
            except Exception:
                log.warning("stop_all failed for %s", connector.name, exc_info=True)
        self.drain(2.0)


def _once(fn: Callable[[], Any]) -> Iterator[Any]:
    """A generator that does `fn()` and returns its value: the attempt loop drives generators (chat turns stream events)."""
    return fn()
    yield       # pragma: no cover  (makes this a generator)


def _progress(on_progress: Optional[Callable[[dict], None]]) -> Optional[Callable[[ConnectorEvent], None]]:
    """J2's progress events: `{"chars": n, "text": text so far}` after every piece of the reply."""
    if on_progress is None:
        return None
    acc = {"text": "", "sent": None}

    def on_event(event: ConnectorEvent) -> None:
        if event.kind == "started":
            acc["text"], acc["sent"] = "", None
            return
        if event.kind == "text_delta":
            acc["text"] += str(event.data.get("text", ""))
        elif event.kind == "text":
            acc["text"] = str(event.data.get("text", acc["text"]))
        else:
            return
        if acc["text"] != acc["sent"]:                  # a final `text` that repeats the deltas is not a new progress
            acc["sent"] = acc["text"]
            on_progress({"chars": len(acc["text"]), "text": acc["text"]})

    return on_event
