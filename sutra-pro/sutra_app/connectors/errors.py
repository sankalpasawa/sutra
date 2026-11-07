"""The connector error tree (connectors design 3.2).

`ConnectorError` is the engine's `ModelError` (a `RuntimeError`), so J2's `except RuntimeError` and its crash path keep
working (D19). For the six codes the engine names, the class also subclasses the engine's class, so
`isinstance(e, NotSignedIn)` holds for a `NotSignedInError`.

Every class carries four fixed facts, read by the router and the orchestrator's adapter:

    code         the fine vocabulary (the engine's names)
    kind         the coarse one the orchestrator reads: unavailable | auth | quota | timeout | bad_output
    retryable    the router retries it up to `max_attempts`
    fallback_ok  the router may try the next provider

and three things per instance: `provider`, `detail` (a dict that never holds a prompt or a secret: `as_dict` drops such
keys even when a caller put them there) and `resets_at` (epoch seconds, quota errors). `user_message()` is plain and
actionable; the UI shows it verbatim. Facts a message needs travel in `detail`: `cli`, `version`, `flag`, `seconds`,
`exit`, `model`, `skipped`.
"""
from __future__ import annotations

import re
from datetime import datetime, tzinfo
from typing import Any, Mapping, Optional, Sequence

from sutra_app.engine.port import (
    CliMissing, ModelError, ModelTimeout, NoModelAvailable, NotSignedIn, QuotaExhausted, StructuredOutputFailed,
)

__all__ = [
    "ConnectorError", "NoProviderError", "CliMissingError", "FlagUnsupportedError", "NotSignedInError",
    "AccountBlockedError", "QuotaError", "RateLimitedError", "OverloadedError", "ServerError", "CallTimeoutError",
    "CrashedError", "ProtocolError", "ProviderError", "ModelNotFoundError", "SessionLostError", "EmptyReplyError",
    "StructuredError", "InvalidJsonError", "ReplyTruncatedError", "InvalidRequestError", "EnvelopeExceededError",
    "CallCancelledError", "PolicyInvalidError", "ERROR_CLASSES", "error_for_code", "KINDS",
    "MAX_DETAIL_STRING", "MAX_DETAIL_ITEMS", "DESKTOP_ONLY",
]

KINDS = ("unavailable", "auth", "quota", "timeout", "bad_output")
MAX_DETAIL_STRING = 2000      # one string in `detail` is cut here by as_dict
MAX_DETAIL_ITEMS = 50         # one list in `detail` is cut here by as_dict
MAX_PARSE_MESSAGE = 500       # invalid_json shows "the first 500 characters" of pydantic or parse errors
_NAMES = {"claude": "Claude", "codex": "Codex", "stub": "Stub"}
_SECRET = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)
# The sentence for a Mac that has Claude Desktop but not Claude Code (GAP-providers, discover.py): Desktop ships no `claude` command, so
# "not found on PATH" would send the owner after a PATH problem that does not exist. It never says "PATH".
DESKTOP_ONLY = ("Claude Desktop is installed, but Sutra needs Claude Code, a separate command-line tool: install Claude Code "
                "(claude.com/claude-code), or choose its file in Settings, Connectors")
# keys a caller must not put into `detail`: the request text, and anything that carries a credential
_FORBIDDEN_DETAIL_KEYS = frozenset({"prompt", "system", "user", "stdin", "stdin_text", "env", "environ", "argv_prompt", "messages"})


def _name(provider: Optional[str]) -> str:
    return _NAMES.get(provider or "", (provider or "").capitalize() or "The model")


def _clean(value: Any, depth: int = 0) -> Any:
    """`detail` as it may leave the process: JSON-native, strings cut, no forbidden or secret-named keys."""
    if isinstance(value, Mapping):
        if depth > 6:
            return None
        return {str(k): _clean(v, depth + 1) for k, v in value.items()
                if str(k).lower() not in _FORBIDDEN_DETAIL_KEYS and not _SECRET.search(str(k))}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)[:MAX_DETAIL_ITEMS]
        return [_clean(v, depth + 1) for v in items]
    if isinstance(value, str):
        return value if len(value) <= MAX_DETAIL_STRING else value[:MAX_DETAIL_STRING] + "..."
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_DETAIL_STRING]


class ConnectorError(ModelError):
    code = "provider_error"
    kind = "unavailable"
    retryable = False
    fallback_ok = True

    def __init__(self, message: str = "", *, provider: Optional[str] = None, detail: Optional[Mapping[str, Any]] = None,
                 resets_at: Optional[float] = None) -> None:
        self.message = message
        self.provider = provider
        self.detail: dict[str, Any] = dict(detail or {})
        self.resets_at = resets_at
        super().__init__(message or self.user_message())

    # ---- what the person reads -------------------------------------------------------------------------------------
    def _cli(self) -> str:
        return str(self.detail.get("cli") or self.provider or "the CLI")

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        """Plain and actionable. `tz` only matters for quota errors (the time the limit resets); default is local time."""
        return self.message or f"{_name(self.provider)} could not answer"

    # ---- what goes over the wire or into a log ---------------------------------------------------------------------
    def as_dict(self) -> dict[str, Any]:
        """code, kind, flags, provider, the user message, `detail` (cleaned) and `resets_at`. Never a prompt or a secret."""
        return {"code": self.code, "kind": self.kind, "retryable": self.retryable, "fallback_ok": self.fallback_ok,
                "provider": self.provider, "message": self.user_message(), "detail": _clean(self.detail),
                "resets_at": self.resets_at}


class NoProviderError(ConnectorError, NoModelAvailable):
    code = "no_model"
    kind = "unavailable"
    retryable = False
    fallback_ok = False

    def __init__(self, message: str = "", *, skipped: Sequence[tuple[str, str]] = (), provider: Optional[str] = None,
                 detail: Optional[Mapping[str, Any]] = None, resets_at: Optional[float] = None) -> None:
        merged = dict(detail or {})
        if skipped:
            merged["skipped"] = [{"provider": p, "reason": r} for p, r in skipped]
        super().__init__(message, provider=provider, detail=merged, resets_at=resets_at)

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        skipped = self.detail.get("skipped") or []
        why = "; ".join(f"{_name(s.get('provider'))}: {s.get('reason')}" for s in skipped if isinstance(s, Mapping))
        return self.message or f"No model is available: {why or 'no provider is configured'}"


class CliMissingError(ConnectorError, CliMissing):
    code = "cli_missing"
    kind = "unavailable"
    retryable = False
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        if self.provider == "codex":
            return "Codex CLI not found on PATH: install it and run `codex login`"
        if self.provider == "claude" and self.detail.get("desktop"):
            return DESKTOP_ONLY
        if self.provider == "claude":
            return "Claude CLI not found on PATH: install it and run `claude` once"
        return f"{self._cli()} not found on PATH: install it first"


class FlagUnsupportedError(ConnectorError):
    code = "cli_flag_unsupported"
    kind = "unavailable"
    retryable = False
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        version = self.detail.get("version")
        cli = f"{self._cli()} {version}" if version else self._cli()
        return f"{cli} does not accept `{self.detail.get('flag', 'a flag')}`: update the CLI"


class NotSignedInError(ConnectorError, NotSignedIn):
    code = "not_signed_in"
    kind = "auth"
    retryable = False
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        if self.provider == "codex":
            return "Codex is not signed in: use Sign in or run `codex login`"
        if self.provider == "claude":
            return "Claude is not signed in: run `claude auth login`"
        return f"{_name(self.provider)} is not signed in"


class AccountBlockedError(ConnectorError):
    code = "account_blocked"
    kind = "auth"
    retryable = False
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"Your {_name(self.provider)} account needs attention (organisation, hold or verification)"


class QuotaError(ConnectorError, QuotaExhausted):
    code = "quota"
    kind = "quota"
    retryable = False
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        head = f"{_name(self.provider)} usage limit reached"
        if self.resets_at is None:
            return head + "; try again later"
        when = datetime.fromtimestamp(self.resets_at, tz).strftime("%Y-%m-%d %H:%M %Z").strip()
        return f"{head}; resets {when}"


class RateLimitedError(ConnectorError):
    code = "rate_limited"
    kind = "quota"
    retryable = True
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"{_name(self.provider)} is rate limiting; retrying"


class OverloadedError(ConnectorError):
    code = "overloaded"
    kind = "unavailable"
    retryable = True
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"{_name(self.provider)} is busy"


class ServerError(ConnectorError):
    code = "server_error"
    kind = "unavailable"
    retryable = True
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"{_name(self.provider)} had a server error"


class CallTimeoutError(ConnectorError, ModelTimeout):
    code = "timeout"
    kind = "timeout"
    retryable = True
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        seconds = self.detail.get("seconds")
        shown = f"{seconds:g}" if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else "the allowed number of"
        return f"{_name(self.provider)} did not answer within {shown} s"


class CrashedError(ConnectorError):
    code = "crashed"
    kind = "unavailable"
    retryable = True
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"{self._cli()} stopped unexpectedly (exit {self.detail.get('exit', 'unknown')})"


class ProtocolError(ConnectorError):
    code = "protocol_error"
    kind = "unavailable"
    retryable = False
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"{self._cli()} gave output this app cannot read"


class ProviderError(ConnectorError):
    code = "provider_error"
    kind = "unavailable"
    retryable = True
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return self.message or f"{_name(self.provider)} reported an error"


class ModelNotFoundError(ConnectorError):
    code = "model_not_found"
    kind = "unavailable"
    retryable = False
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"model {self.detail.get('model', 'requested')} is not available"


class SessionLostError(ConnectorError):
    """The provider forgot the session (C16, X12). Internal: the router starts a new session with the carry-over."""

    code = "session_lost"
    kind = "unavailable"
    retryable = False
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return "The provider session was lost; a new one is started with the earlier messages"


class EmptyReplyError(ConnectorError):
    code = "empty_reply"
    kind = "bad_output"
    retryable = True
    fallback_ok = True

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return f"{_name(self.provider)} returned nothing"


class StructuredError(ConnectorError, StructuredOutputFailed):
    code = "structured"
    kind = "bad_output"
    retryable = False        # the strategy switches to the prompted path instead of retrying
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return "the structured reply could not be produced"


class InvalidJsonError(ConnectorError):
    """Parse or validation errors after the repair rounds. Whether another provider is tried is the policy's call
    (`fallback_on_invalid_json`, default false), so `fallback_ok` is False here."""

    code = "invalid_json"
    kind = "bad_output"
    retryable = False
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return (self.message or "the reply was not the JSON that was asked for")[:MAX_PARSE_MESSAGE]


class ReplyTruncatedError(ConnectorError):
    code = "reply_truncated"
    kind = "bad_output"
    retryable = False
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return "The reply was cut off because it reached the model's length limit."


class InvalidRequestError(ConnectorError):
    """What was wrong: a bad schema, a missing image, a prompt that is too long."""

    code = "invalid_request"
    kind = "bad_output"
    retryable = False
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return self.message or "the request was not valid"


class EnvelopeExceededError(ConnectorError):
    code = "envelope_exceeded"
    kind = "quota"
    retryable = False
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return "the envelope allows no more calls, money or time"


class CallCancelledError(ConnectorError):
    code = "cancelled"
    kind = "unavailable"
    retryable = False
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return "stopped"


class PolicyInvalidError(ConnectorError):
    code = "policy_invalid"
    kind = "unavailable"
    retryable = False
    fallback_ok = False

    def user_message(self, *, tz: Optional[tzinfo] = None) -> str:
        return self.message or "the routing policy is not valid"


ERROR_CLASSES: dict[str, type[ConnectorError]] = {
    cls.code: cls for cls in (
        NoProviderError, CliMissingError, FlagUnsupportedError, NotSignedInError, AccountBlockedError, QuotaError,
        RateLimitedError, OverloadedError, ServerError, CallTimeoutError, CrashedError, ProtocolError, ProviderError,
        ModelNotFoundError, SessionLostError, EmptyReplyError, StructuredError, InvalidJsonError, ReplyTruncatedError,
        InvalidRequestError, EnvelopeExceededError, CallCancelledError, PolicyInvalidError)
}


def error_for_code(code: str, message: str = "", **kw: Any) -> ConnectorError:
    """The error class of a fine code, built; an unknown code is a `ProviderError` that keeps the code in `detail`."""
    cls = ERROR_CLASSES.get(code)
    if cls is None:
        detail = dict(kw.pop("detail", None) or {})
        detail["code"] = code
        return ProviderError(message, detail=detail, **kw)
    return cls(message, **kw)
