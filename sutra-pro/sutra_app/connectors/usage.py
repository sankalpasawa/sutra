"""Usage normalisation, the usage row and its sinks (connectors design 3.8, S1-contracts-05, S4-fnodes-07).

    usage_from_claude / usage_from_codex   a CLI's usage object -> `Usage` (disjoint parts)
    cumulative_delta / cost_delta          the delta rules (CD5): counters that are cumulative on resume become per-call
    rate_card_usd                          Codex: rate card x tokens, or None when the owner left a needed price null
    Attempt, build_usage_row               the Router's one builder: ONE `UsageIn` per request, a failed request included
    UsageIn                                the row; defined here once, imported by the orchestrator and the engine
    UsageSink, MemoryUsageSink             the sink Protocol (`record(row) -> int`) and an in-memory sink for tests
    save_session_state / load_session_state   `<work_dir>/session.json`, atomic, mode 0600

Tokens are the comparable unit (known for both providers). `usd` is Claude's list-price delta, a rate-card estimate for
Codex when the owner filled `rates`, else None. Credits are never converted to usd.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from pydantic import Field, ValidationError, field_validator

from sutra_app.engine.port import CallTag, PURPOSE_PATTERN

from .models import Effort, M, Provider, RouteContext, SessionState, Usage
from .policy import Rate

__all__ = [
    "HOW_VALUES", "Attempt", "UsageIn", "UsageSink", "MemoryUsageSink", "usage_from_claude", "usage_from_codex",
    "cumulative_delta", "cost_delta", "rate_card_usd", "build_usage_row", "step_label", "call_ref", "new_request_id",
    "session_path", "save_session_state", "load_session_state", "SESSION_FILE", "J2_STEP_LETTERS",
]

SESSION_FILE = "session.json"
J2_STEP_LETTERS = "abcdefgh"                       # CallTag.step 1..8 = J2.a..J2.h
HowName = Literal["native", "prompted", "repaired", "stub", "chat", "text"]
HOW_VALUES = ("native", "prompted", "repaired", "stub", "chat", "text")
UsdBasis = Literal["reported", "rate_card", "unknown", "none"]
_BUILDER_ID = re.compile(r"^W-\d+$")
_USD_DIGITS = 9                                    # below a nano-dollar is float noise (0.019034799999999998 - 0.009745899999999998)


# ---- normalising a CLI's usage object ----------------------------------------------------------------------------------
def _count(data: Mapping[str, Any], name: str) -> int:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return 0
    return max(0, int(value))


def usage_from_claude(data: Optional[Mapping[str, Any]]) -> Usage:
    """Claude `result.usage` (per turn). Fresh input, `cache_read_input_tokens` as cached, `cache_creation_input_tokens` as writes."""
    data = data or {}
    return Usage(input_tokens=_count(data, "input_tokens"), cached_input_tokens=_count(data, "cache_read_input_tokens"),
                 cache_write_tokens=_count(data, "cache_creation_input_tokens"), output_tokens=_count(data, "output_tokens"),
                 reasoning_tokens=_count(data, "reasoning_tokens"))


def usage_from_codex(data: Optional[Mapping[str, Any]]) -> Usage:
    """Codex `turn.completed.usage` (CUMULATIVE for the thread): fresh input = `input_tokens` minus `cached_input_tokens`."""
    data = data or {}
    cached = _count(data, "cached_input_tokens")
    return Usage(input_tokens=max(0, _count(data, "input_tokens") - cached), cached_input_tokens=cached,
                 cache_write_tokens=_count(data, "cache_write_input_tokens"), output_tokens=_count(data, "output_tokens"),
                 reasoning_tokens=_count(data, "reasoning_output_tokens"))


# ---- the delta rules (CD5) ---------------------------------------------------------------------------------------------
def cumulative_delta(now: Usage, previous: Usage) -> Usage:
    """What one call used, from a counter that is cumulative for the session. A one-shot call passes `Usage()` as `previous`.

    A counter that went backwards (a new provider session, a CLI change) is taken whole: any part smaller than before means
    the counter restarted, so `now` is the call's usage. Otherwise part by part, `now - previous`."""
    for name in Usage.model_fields:
        if getattr(now, name) < getattr(previous, name):
            return now
    return now - previous


def cost_delta(total: float, previous: float) -> float:
    """Claude `total_cost_usd` is cumulative for the session: this call's cost is `total - previous`, never negative.
    A total below the previous one (counter restarted) is taken whole. The caller then stores `total` as the new `cum_usd`."""
    value = total if total < previous else total - previous
    return round(max(0.0, value), _USD_DIGITS)


def rate_card_usd(rate: Optional[Rate], usage: Usage) -> Optional[float]:
    """Rate card x tokens in USD, or None. None when there is no rate, `in_per_mtok` or `out_per_mtok` is null, or cached
    tokens were used and `cached_in_per_mtok` is null. A null `cache_write_per_mtok` prices writes like fresh input."""
    if rate is None or rate.in_per_mtok is None or rate.out_per_mtok is None:
        return None
    if usage.cached_input_tokens and rate.cached_in_per_mtok is None:
        return None
    cached = rate.cached_in_per_mtok or 0.0
    writes = rate.in_per_mtok if rate.cache_write_per_mtok is None else rate.cache_write_per_mtok
    total = (usage.input_tokens * rate.in_per_mtok + usage.cached_input_tokens * cached
             + usage.cache_write_tokens * writes + usage.output_tokens * rate.out_per_mtok) / 1_000_000
    return round(total, _USD_DIGITS)


# ---- the row -------------------------------------------------------------------------------------------------------------
class Attempt(M):
    """One CLI invocation of a request, as the router saw it. `usage` is None when the call ended before any count."""

    provider: Provider
    model: Optional[str] = None
    effort: Optional[Effort] = None
    code: str = "ok"                       # "ok" or the ConnectorError code
    usage: Optional[Usage] = None
    usd: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    usd_basis: UsdBasis = "none"
    seconds: float = Field(0.0, ge=0, allow_inf_nan=False)
    cli_version: Optional[str] = None
    billing: Literal["subscription", "api_key", "unknown"] = "unknown"


class UsageIn(M):
    """One model request, built once by the Router. `UsageOut` (orchestrator) adds `id` and `at`."""

    provider: Provider
    model: str = ""
    purpose: str = Field(pattern=PURPOSE_PATTERN)
    session_id: Optional[str] = None
    node_id: Optional[str] = None
    task_id: Optional[str] = None
    dept_id: Optional[str] = None
    fn: Optional[str] = None
    step: Optional[str] = None             # `J2.c` for a J2 step, `W-3` for a builder (step_label)
    atom_id: Optional[str] = None          # tag.atom as given; None only for an untagged call
    usd: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    tokens_in: Optional[int] = Field(None, ge=0)
    tokens_out: Optional[int] = Field(None, ge=0)
    seconds: float = Field(0.0, ge=0, allow_inf_nan=False)
    ok: bool = True
    how: HowName
    call_ref: Optional[str] = Field(None, min_length=1)
    detail: Optional[dict[str, Any]] = None

    @field_validator("detail")
    @classmethod
    def _json_detail(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is not None:
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"detail must be JSON: {exc}") from None
        return value


def step_label(tag: CallTag) -> Optional[str]:
    """The tag's step label: the builder id when the call is a builder's (`function` `W-<n>`), else the J2 step letter
    (`CallTag.step` 1..8 = `J2.a`..`J2.h`), else None. `CallTag.step` is a number; ORCH's string step never lands in it."""
    if _BUILDER_ID.match(tag.function or ""):
        return tag.function
    if 1 <= tag.step <= len(J2_STEP_LETTERS):
        return f"J2.{J2_STEP_LETTERS[tag.step - 1]}"
    return None


def call_ref(tag: CallTag, request_id: str) -> str:
    """`<run_id>:<call_no>` for a call the engine logs (the id in calls.jsonl), else `r:<request_id>`. A call number with no
    run id would collide across runs, so it also falls back to the request id."""
    if tag.call_no > 0 and tag.run_id:
        return f"{tag.run_id}:{tag.call_no}"
    return f"r:{request_id}"


def new_request_id() -> str:
    return secrets.token_hex(6)


def _sum_optional(values: Sequence[Optional[int]]) -> Optional[int]:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def _attempt_detail(a: Attempt) -> dict[str, Any]:
    usage = a.usage
    return {"provider": a.provider, "model": a.model, "effort": a.effort, "code": a.code, "usd": a.usd,
            "tokens_in": None if usage is None else usage.input_total, "tokens_out": None if usage is None else usage.output_tokens,
            "seconds": round(a.seconds, 3)}


def build_usage_row(*, ctx: RouteContext, attempts: Sequence[Attempt], request_id: str, ok: bool, how: str,
                    purpose: Optional[str] = None, seconds: Optional[float] = None, note: Optional[str] = None,
                    provider: Optional[Provider] = None) -> UsageIn:
    """The one row of a request. `attempts` are every CLI invocation in order, the failed ones included.

    provider/model: the last attempt (the one that answered, or the last tried). With no attempt at all (the request failed
    before any spawn) `provider` must say which one the plan chose. tokens: sums over the attempts, None when none reported
    a count. usd: the sum of the attempts that know theirs (Codex without rates adds nothing), None when none knows.
    seconds: wall time of the whole request when given (retry waits included), else the sum of the attempts."""
    if not attempts and provider is None:
        raise ValueError("a request with no attempt needs `provider`")
    tag = ctx.tag
    last = attempts[-1] if attempts else None
    usages = [a.usage for a in attempts if a.usage is not None]
    known_usd = [a.usd for a in attempts if a.usd is not None]
    cached = sum(u.cached_input_tokens for u in usages)
    writes = sum(u.cache_write_tokens for u in usages)
    reasoning = sum(u.reasoning_tokens for u in usages)
    detail = {
        "request_id": request_id, "attempts": [_attempt_detail(a) for a in attempts],
        "cached_in": cached, "cache_write": writes, "reasoning": reasoning,
        "usd_basis": last.usd_basis if last else "none", "billing": last.billing if last else "unknown",
        "cli_version": last.cli_version if last else None, "envelope_id": ctx.allowance.envelope_id, "note": note,
    }
    return UsageIn(
        provider=last.provider if last else provider, model=(last.model if last else None) or "",
        purpose=purpose or tag.purpose, session_id=ctx.session_id, node_id=ctx.node_id, task_id=tag.task_id,
        dept_id=tag.dept_id or None, fn=tag.function or None, step=step_label(tag), atom_id=tag.atom,
        usd=round(sum(known_usd), _USD_DIGITS) if known_usd else None,
        tokens_in=_sum_optional([u.input_total for u in usages]), tokens_out=_sum_optional([u.output_tokens for u in usages]),
        seconds=round(seconds if seconds is not None else sum(a.seconds for a in attempts), 3), ok=ok, how=how,
        call_ref=call_ref(tag, request_id), detail=detail)


# ---- sinks ---------------------------------------------------------------------------------------------------------------
@runtime_checkable
class UsageSink(Protocol):
    """Where the Router hands each row. `UsageStore` (server) and `EventUsageSink` (engine host) implement it;
    `record` returns the row's id (or a local counter)."""

    def record(self, row: UsageIn) -> int: ...


class MemoryUsageSink:
    """Keeps rows in a list, for tests and offline use. Every call appends (no de-duplication: a double write must show)."""

    def __init__(self) -> None:
        self.rows: list[UsageIn] = []
        self._lock = threading.Lock()

    def record(self, row: UsageIn) -> int:
        with self._lock:
            self.rows.append(row)
            return len(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def clear(self) -> None:
        with self._lock:
            self.rows.clear()


# ---- session state file --------------------------------------------------------------------------------------------------
def session_path(workdir: "str | Path") -> Path:
    return Path(workdir) / SESSION_FILE


def save_session_state(state: SessionState) -> Path:
    """Write `<state.workdir>/session.json` atomically (temp file in the same folder, then rename), mode 0600."""
    path = session_path(state.workdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".session-", suffix=".tmp", dir=path.parent)       # mkstemp creates the file 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state.model_dump(mode="json"), indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def load_session_state(workdir: "str | Path") -> Optional[SessionState]:
    """The stored state, or None when the file is missing or unreadable (the caller then starts a new provider session
    with the carry-over, connectors 3.6 "Chat sessions")."""
    try:
        return SessionState.model_validate(json.loads(session_path(workdir).read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError):
        return None
