"""A `views.Reply` becomes an HTTP response, and every engine response carries the security headers (engine design 7.2, S3-web-14).

- text bodies (str, or bytes of a text type) are decoded, redacted through `services.redact`, and sent as UTF-8 with
  `; charset=utf-8`; PNG and DOCX are sent as they are (J2's `_send`);
- every response gets `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`; `text/html` (generated sites, html
  artifacts, rendered documents) also gets `Content-Security-Policy: sandbox allow-scripts allow-forms allow-popups;
  frame-ancestors 'self'`, so a generated page cannot read the page token (D83);
- no response sets a cookie; `Cache-Control` is the reply's (default `no-store`).
"""
import json
import re
from collections.abc import Callable
from typing import Any, Optional

from fastapi.responses import Response

from ..views import DOCX, Reply

__all__ = ["SECURITY_HEADERS", "SANDBOX_CSP", "BINARY_TYPES", "EngineError", "to_response", "json_reply", "envelope",
           "dept_required", "not_found", "read_only", "validation", "error_response"]

SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
SANDBOX_CSP = "sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'"
BINARY_TYPES = ("image/png", DOCX)


class EngineError(Exception):
    """A refusal made before a view runs. `body` is sent as it is: J2's `{"error": "dept_required"}` on the J2 routes, the
    orchestrator's `{"error": {"code", "message", "details"}}` envelope where the design says so."""

    def __init__(self, status: int, body: dict) -> None:
        super().__init__(json.dumps(body))
        self.status = status
        self.body = body


def envelope(code: str, message: str, details: Optional[dict] = None) -> dict:
    return {"error": {"code": code, "message": message, "details": dict(details or {})}}


def dept_required() -> EngineError:
    return EngineError(400, {"error": "dept_required"})


def not_found() -> EngineError:
    return EngineError(404, {"error": "not_found"})


def read_only() -> EngineError:
    return EngineError(403, envelope("read_only", "This team was merged into another one and is read-only"))


def validation(violations: list[dict], message: str = "The request was refused") -> EngineError:
    return EngineError(422, envelope("validation", message, {"violations": violations}))


def json_reply(obj: Any, code: int = 200) -> Reply:
    return Reply(code, json.dumps(obj, ensure_ascii=False))


def _file_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:200] or "download"


def to_response(reply: Reply, redact: Callable[[str], str]) -> Response:
    headers = {**SECURITY_HEADERS, "Cache-Control": reply.cache}
    ctype = reply.ctype
    if ctype in BINARY_TYPES and isinstance(reply.body, bytes):
        data = reply.body
        headers["Content-Type"] = ctype
    else:
        text = reply.body if isinstance(reply.body, str) else reply.body.decode("utf-8", "replace")
        data = redact(text).encode("utf-8")
        headers["Content-Type"] = f"{ctype}; charset=utf-8"
    if ctype == DOCX:
        headers["Content-Disposition"] = f'attachment; filename="{_file_name(reply.name or "prd.docx")}"'
    if ctype.split(";")[0].strip().lower() == "text/html":
        headers["Content-Security-Policy"] = SANDBOX_CSP
    return Response(content=data, status_code=reply.code, headers=headers)


def error_response(exc: EngineError, redact: Callable[[str], str]) -> Response:
    return to_response(Reply(exc.status, json.dumps(exc.body, ensure_ascii=False)), redact)
