"""Shared API dependencies: the write guard, the error envelope and the redacting JSON response (orchestrator 6.1, D81).

`require_token` is THE guard (S3-web-03): every route whose method is not GET, HEAD or OPTIONS depends on it, the orchestrator's,
the engine's and the connectors' alike (`Services.require_token`). It checks, in this order,

  1. the header `X-Sutra-Token` equals the launch token (`hmac.compare_digest`)  -> 401 `bad_token`
  2. a present `Origin` equals `http://<the Host header>`; `Origin: null`, another site or another port -> 403 `bad_origin`.
     An absent Origin is allowed (curl, scripts).

There is no cookie anywhere and the token is never read from the URL or the body. The Host allow-list is the app-wide
`TrustedHostMiddleware` (400 `bad_host`), not this dependency. The token is read from `app.state.services.settings.token`
at request time, so one function serves every router.

Errors leave as `{"error": {"code", "message", "details"}}` (`install_error_handlers`), and every JSON body goes through
`RedactedJSONResponse` (secret values become `[redacted]`).
"""
import hmac
import logging
import sqlite3
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sutra_app.config import default_env_file
from sutra_app.library.types import violation
from sutra_app.orchestrator.errors import AppError, error_body, validation_error
from sutra_app.orchestrator.redact import Redactor

__all__ = [
    "TOKEN_HEADER", "SAFE_METHODS", "require_token", "redacted_response_class", "RedactedJSONResponse", "install_error_handlers",
    "services_of",
]

log = logging.getLogger(__name__)
TOKEN_HEADER = "X-Sutra-Token"
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def services_of(request: Request) -> Any:
    """The app's `Services` (set by `create_app` as `app.state.services`)."""
    found = getattr(request.app.state, "services", None)
    if found is None:
        raise AppError("internal", "the app has no services configured")
    return found


async def require_token(request: Request) -> None:
    """The one write guard. Safe methods pass untouched; every other method needs the token and a matching Origin."""
    if request.method.upper() in SAFE_METHODS:
        return
    expected = services_of(request).settings.token
    supplied = request.headers.getlist(TOKEN_HEADER)
    if len(supplied) != 1 or not hmac.compare_digest(supplied[0].encode("utf-8"), expected.encode("utf-8")):
        raise AppError("bad_token", "A valid X-Sutra-Token header is required for this request")
    origins = request.headers.getlist("origin")
    if origins:                                        # present, even if empty or "null"
        host = request.headers.get("host", "")
        if len(origins) != 1 or origins[0].lower() != f"http://{host}".lower() or not host:
            raise AppError("bad_origin", "The Origin of this request is not this app")


def redacted_response_class(redactor: Redactor) -> type[JSONResponse]:
    """A JSONResponse class that removes every secret of `redactor` from the content before it is written."""

    class RedactedJSONResponse(JSONResponse):
        def render(self, content: Any) -> bytes:
            return super().render(redactor.scrub(content))

    return RedactedJSONResponse


RedactedJSONResponse = redacted_response_class(Redactor(default_env_file()))      # environment and the default .env only


def install_error_handlers(app: FastAPI, response_class: type[JSONResponse] = RedactedJSONResponse) -> None:
    """Make every refusal an error envelope: AppError (its own code), request validation (422 `validation`), a locked
    database (503 `store_busy`) and anything unexpected (500 `internal`, nothing leaked)."""

    async def on_app_error(request: Request, exc: AppError) -> JSONResponse:
        return response_class(status_code=exc.status, content=exc.body())

    async def on_request_invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        found = [violation(".".join(str(p) for p in err["loc"]), str(err["type"]), str(err["msg"])) for err in exc.errors()[:50]]
        return response_class(status_code=422, content=validation_error(found).body())

    async def on_sqlite(request: Request, exc: sqlite3.OperationalError) -> JSONResponse:
        text = str(exc).lower()
        if "locked" in text or "busy" in text:
            return response_class(status_code=503, content=error_body("store_busy", "Try again in a moment."))
        log.exception("database error on %s %s", request.method, request.url.path)
        return response_class(status_code=500, content=error_body("internal", "Something went wrong on the server."))

    async def on_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return response_class(status_code=500, content=error_body("internal", "Something went wrong on the server."))

    app.add_exception_handler(AppError, on_app_error)
    app.add_exception_handler(RequestValidationError, on_request_invalid)
    app.add_exception_handler(sqlite3.OperationalError, on_sqlite)
    app.add_exception_handler(Exception, on_unexpected)
