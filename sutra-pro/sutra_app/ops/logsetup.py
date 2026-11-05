"""Logging for the server (gaps G11, orchestrator 4.2 and 5.1): one rotating file, every line redacted, a request id on every response.

    handler = configure(settings, verbose=False)        # once per process, from the CLI (`sutra-pro`)
    app = ...; RequestIdMiddleware(app)                 # `create_app` wraps the whole app in it

`<data>/logs/server.log` is a `RotatingFileHandler` (5 MB x 5 files, mode 0600). A `RedactingFilter` on every handler applies the
`Redactor` (launch token, override key, `.env` values, secret-named environment values) to the finished message, its arguments and the
traceback text, so a secret cannot reach the file through an exception either. Line format: `ts level logger request_id message`.
uvicorn's access log goes through the same handlers; its query string is cut off first (a URL may one day carry something private).
Every HTTP response carries `X-Request-Id` (12 hex characters, made here, never taken from the request) and the same id is printed
by log lines written while the request is served. `verbose` sets DEBUG.
"""
import contextvars
import logging
import logging.handlers
import os
import secrets
import sys
import traceback
from collections.abc import Callable
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = ["configure", "RedactingFilter", "AccessLogFilter", "RequestIdMiddleware", "PrivateRotatingFileHandler", "request_id_var",
           "LOG_FORMAT", "MAX_BYTES", "BACKUPS", "REQUEST_ID_HEADER", "new_request_id"]

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s"
MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 5
REQUEST_ID_HEADER = "X-Request-Id"
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("sutra_request_id", default="-")


def new_request_id() -> str:
    return secrets.token_hex(6)


class RedactingFilter(logging.Filter):
    """Replaces the record's message, arguments, traceback and stack text by their redacted form and stamps `request_id`."""

    def __init__(self, redactor: Callable[[str], str]) -> None:
        super().__init__()
        self._redact = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:                                                   # noqa: BLE001  (a bad format string must not lose the line)
            text = str(record.msg)
        record.msg, record.args = self._redact(text), None
        if record.exc_info and record.exc_info[0] is not None:
            record.exc_text = self._redact("".join(traceback.format_exception(*record.exc_info)).rstrip("\n"))
        elif record.exc_text:
            record.exc_text = self._redact(record.exc_text)
        if record.stack_info:
            record.stack_info = self._redact(record.stack_info)
        record.request_id = request_id_var.get()
        return True


class AccessLogFilter(logging.Filter):
    """uvicorn's access record is `(client, method, full_path, http_version, status)`: the path loses its query string."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if record.name == "uvicorn.access" and isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


class PrivateRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating file whose every new file (the first one and each one after a rollover) is mode 0600."""

    def _open(self) -> Any:
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream


def _default_redactor(settings: Any) -> Callable[[str], str]:
    from sutra_app.orchestrator.wiring import make_redactor
    return make_redactor(settings)


def configure(settings: Any, *, verbose: bool = False, redactor: Callable[[str], str] | None = None, console: bool = True,
              stream: Any = None) -> logging.Handler:
    """Install the file handler (and a stderr handler for warnings, or everything with `verbose`) on the root logger, replacing the
    pair a previous call or ORCH-8's `configure_logging` installed. Returns the file handler."""
    settings.ensure_dirs()
    redact = redactor if redactor is not None else _default_redactor(settings)
    root = logging.getLogger()
    for old in [h for h in root.handlers if getattr(h, "_sutra_app", False)]:
        root.removeHandler(old)
        old.close()
    formatter = logging.Formatter(LOG_FORMAT)
    file_handler = PrivateRotatingFileHandler(settings.log_path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    handlers: list[logging.Handler] = [file_handler]
    if console:
        shown = logging.StreamHandler(stream if stream is not None else sys.stderr)
        shown.setLevel(logging.DEBUG if verbose else logging.WARNING)
        handlers.append(shown)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(AccessLogFilter())
        handler.addFilter(RedactingFilter(redact))
        handler._sutra_app = True                                           # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    return file_handler


class RequestIdMiddleware:
    """Pure ASGI: makes the request id, keeps it in `request_id_var` (and `scope["state"]["request_id"]`) while the app runs and adds
    `X-Request-Id` to the response. Wrap the OUTERMOST app, so a 400 from the Host guard and a 500 carry it too."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = new_request_id()
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id_var.set(rid)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = rid
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)
