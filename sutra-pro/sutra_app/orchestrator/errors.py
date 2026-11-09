"""`AppError`: one error type for every refusal the API makes (orchestrator 6.1, S3-web-15).

Every new route answers errors with `{"error": {"code", "message", "details"}}`; the code decides the HTTP status. The codes
are a closed list, so a typo in a store fails where it is raised and not as a 500 in the browser.
"""
from collections.abc import Sequence
from typing import Any

from sutra_app.library.gate import GateError
from sutra_app.library.types import Violation

__all__ = [
    "STATUS_BY_CODE", "AppError", "NotFound", "Busy", "ReadOnly", "AlreadyDecided", "StoreBusy", "validation_error",
    "rules_error", "error_body",
]

STATUS_BY_CODE: dict[str, int] = {
    "bad_token": 401, "bad_host": 400, "bad_origin": 403, "validation": 422, "rules": 422, "not_found": 404, "busy": 409,
    "stale_chart": 409, "already_decided": 409, "not_running": 409, "read_only": 403, "too_many_pending": 429, "provider_unavailable": 503,
    "cli_missing": 503, "store_busy": 503, "internal": 500,
}


class AppError(Exception):
    """A refusal with an error code. `details` is a JSON-able dict (for `validation`: `{"violations": [...]}`)."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        if code not in STATUS_BY_CODE:
            raise ValueError(f"unknown error code {code!r}: use one of {', '.join(sorted(STATUS_BY_CODE))}")
        super().__init__(message)
        self.code = code
        self.status = STATUS_BY_CODE[code]
        self.message = message
        self.details: dict[str, Any] = dict(details or {})

    def body(self) -> dict[str, Any]:
        return error_body(self.code, self.message, self.details)


class NotFound(AppError):
    def __init__(self, what: str = "that") -> None:
        super().__init__("not_found", f"{what} was not found")


class Busy(AppError):
    def __init__(self, message: str = "The team is working. You can write again when it asks you something or is done") -> None:
        super().__init__("busy", message)


class ReadOnly(AppError):
    def __init__(self, message: str = "This chat is read-only") -> None:
        super().__init__("read_only", message)


class StoreBusy(AppError):
    """The database stayed locked beyond its busy timeout (failure F10): nothing was half-written."""

    def __init__(self) -> None:
        super().__init__("store_busy", "Try again in a moment.")


class AlreadyDecided(AppError):
    """A second decision on a change that was decided already; `result` is the first decision's outcome."""

    def __init__(self, result: Any = None) -> None:
        super().__init__("already_decided", "That change was already decided")
        self.result = result


def validation_error(violations: Sequence[Violation], message: str = "The request was refused") -> AppError:
    """422 `validation` with every violation in `details.violations` (path, code, message)."""
    return AppError("validation", message, {"violations": [v.model_dump() for v in violations]})


def rules_error(violations: Sequence[Violation], message: str = "The change breaks the chart rules") -> AppError:
    """422 `rules`: the chart rules refused a well-formed change."""
    return AppError("rules", message, {"violations": [v.model_dump() for v in violations]})


def from_gate_error(exc: GateError) -> AppError:
    """A GateError on API input is 422 `validation` (an internal write that fails is a bug: callers raise `internal`)."""
    return validation_error(exc.violations, str(exc))


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": dict(details or {})}}


__all__.append("from_gate_error")
