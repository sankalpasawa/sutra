"""What the chat agent needs from the connector layer, and the constants of one request (orchestrator 3.5, 5.2).

    ConnectorPort       the CON `AsyncConnector` as a Protocol: `call_json(...)` and `status()`
    ConnectorFailure    one error type with the closed five kinds the agent reads: unavailable | auth | quota | timeout | bad_output
    failure_kind(exc)   the kind of any exception a connector raises (CON errors carry `.kind`; other classes are mapped by name);
                        None for an exception that is not a connector failure (a bug: it propagates)
    usable(status)      is any provider ready for a call, and `hint(status)` says in one line why not

`unavailable`, `auth` and `quota` are not retried (failure F1). `timeout` and `bad_output` count as one attempt of a stage.
"""
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "ATTEMPTS", "MAX_CALLS", "CALL_TIMEOUT", "HISTORY", "DIGEST_CHARS", "PENDING_TURNS", "MAX_ASSIGNMENTS", "FAILURE_KINDS",
    "NO_RETRY_KINDS", "FailureKind", "ConnectorFailure", "ConnectorPort", "failure_kind", "usable", "hint", "missing_cli",
]

ATTEMPTS = 3                 # per stage (ADR-029 D4)
MAX_CALLS = 6                # model calls of one request
CALL_TIMEOUT = 120.0         # seconds per call
HISTORY = 12                 # chat messages the decide prompt carries
DIGEST_CHARS = 6000
PENDING_TURNS = 5            # requests that may wait behind the one running
MAX_ASSIGNMENTS = 5
FAILURE_KINDS = ("unavailable", "auth", "quota", "timeout", "bad_output")
NO_RETRY_KINDS = ("unavailable", "auth", "quota")
FailureKind = Literal["unavailable", "auth", "quota", "timeout", "bad_output"]


class ConnectorFailure(Exception):
    """A model call that failed. `kind` is one of the closed five; `provider` names who failed when known."""

    def __init__(self, kind: str, message: str = "", *, provider: str | None = None) -> None:
        if kind not in FAILURE_KINDS:
            raise ValueError(f"a connector failure is one of {', '.join(FAILURE_KINDS)}, not {kind!r}")
        super().__init__(message or kind)
        self.kind: FailureKind = kind          # type: ignore[assignment]
        self.provider = provider


@runtime_checkable
class ConnectorPort(Protocol):
    """CON's `AsyncConnector`. `context` keys: purpose, session_id, node_id, task_id, atom_id (the request's overhead key)."""

    async def call_json(self, prompt: str, *, schema: dict | None = None, tools: Sequence[str] = (), timeout: float = 120.0,
                        function: str = "chat_agent", step: str = "plan",
                        context: Mapping[str, str] | None = None) -> tuple[dict, float | None, str]: ...

    def status(self) -> Mapping[str, Mapping[str, Any]]: ...


_BY_NAME = (                 # class-name fragments -> kind, for an exception that carries no `.kind`
    ("timeout", "timeout"), ("quota", "quota"), ("ratelimit", "quota"), ("notsignedin", "auth"), ("auth", "auth"),
    ("climissing", "unavailable"), ("nomodel", "unavailable"), ("noprovider", "unavailable"), ("unavailable", "unavailable"),
    ("invalidjson", "bad_output"), ("badoutput", "bad_output"), ("structured", "bad_output"), ("truncated", "bad_output"),
)


def failure_kind(exc: BaseException) -> FailureKind | None:
    """The kind of a connector failure, or None when `exc` is no connector failure at all (a bug in our own code: let it
    propagate). An exception with a `.kind` among the five uses it; `TimeoutError` is `timeout`; any other class is mapped by
    the words in its name."""
    kind = getattr(exc, "kind", None)
    if kind in FAILURE_KINDS:
        return kind
    if isinstance(exc, TimeoutError):
        return "timeout"
    name = type(exc).__name__.lower()
    for fragment, mapped in _BY_NAME:
        if fragment in name:
            return mapped  # type: ignore[return-value]
    return None


_NAMES = {"claude": "Claude", "codex": "Codex", "stub": "The stub model"}


def _ready(entry: Mapping[str, Any]) -> bool:
    return bool(entry.get("installed", True)) and entry.get("signed_in") is not False


def usable(status: Mapping[str, Mapping[str, Any]]) -> bool:
    """True when at least one provider is installed and not known to be signed out."""
    return any(_ready(entry) for entry in status.values())


def missing_cli(status: Mapping[str, Mapping[str, Any]]) -> bool:
    """True when there are providers and none of them is installed (503 `cli_missing`, else `provider_unavailable`)."""
    return bool(status) and not any(bool(entry.get("installed", True)) for entry in status.values())


def hint(status: Mapping[str, Mapping[str, Any]]) -> str:
    """One line on why no provider is usable: 'Claude is not installed; Codex is signed out'. Empty when something is usable."""
    if usable(status):
        return ""
    if not status:
        return "no connector is set up"
    parts = []
    for name, entry in status.items():
        label = _NAMES.get(name, name.capitalize())
        if not bool(entry.get("installed", True)):
            parts.append(f"{label} is not installed")
        elif entry.get("signed_in") is False:
            parts.append(f"{label} is signed out")
        else:
            parts.append(f"{label} is not ready")
    return "; ".join(parts)
