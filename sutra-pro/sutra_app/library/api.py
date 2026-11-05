"""The schema router: `/api/schemas` (library design section 13; S3-web-03, S3-web-15; work package L8).

    GET  /api/schemas                      {"families": [{"family", "versions", "kinds"}]}
    GET  /api/schemas/{family}/{version}   the JSON Schema of one version (2020-12), or 404 `unknown_schema`
    POST /api/schemas/validate             {"family", "version"?, "payload"} -> 200 {"ok": true, "sha256"}
                                           | 422 `validation` with details.violations | 413 `payload_too_large`

The prefix `/api/library` is J2's template library, which is why these routes live under `/api/schemas`.

Reads carry no token. The POST is a write by method (it stores nothing, the rule is by method): it takes `write_guard`, the
app's `Services.require_token` (header `X-Sutra-Token`), as a dependency; the factory REQUIRES it, as the connectors' router
does. A guard refusal is the app's own error (the orchestrator's `install_error_handlers` turns it into its envelope: 401
`bad_token`); this module imports nothing from the orchestrator.

Every error this module makes is the orchestrator's envelope `{"error": {"code", "message", "details"}}`. The body is read and
parsed here, not by FastAPI, so a malformed request is the same envelope and not FastAPI's own `detail` list.
"""
import json
from collections.abc import Callable
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .gate import GATE, MAX_PAYLOAD_BYTES, Gate, GateError
from .registry import REGISTRY, ModelRegistry, RegistryError
from .types import Violation, violation

__all__ = ["PREFIX", "MAX_BODY_BYTES", "build_api_router", "build_router", "error_body"]

PREFIX = "/api/schemas"
MAX_BODY_BYTES = MAX_PAYLOAD_BYTES + 8192       # the payload's limit plus room for the "family" and "version" around it


def error_body(code: str, message: str, details: Optional[dict] = None) -> dict:
    """The orchestrator's envelope (`orchestrator.errors.error_body`, copied: the library imports nothing from it)."""
    return {"error": {"code": code, "message": message, "details": dict(details or {})}}


def _error(status: int, code: str, message: str, details: Optional[dict] = None) -> JSONResponse:
    return JSONResponse(error_body(code, message, details), status_code=status)


def _invalid(violations: list[Violation], message: str = "The request was refused") -> JSONResponse:
    return _error(422, "validation", message, {"violations": [v.model_dump() for v in violations]})


def _version_of(text: str) -> Optional[int]:
    """`1` or `v1` (the file name's own form); anything else is not a version."""
    digits = text[1:] if text[:1] == "v" else text
    return int(digits) if digits.isascii() and digits.isdigit() and len(digits) < 8 else None


def build_api_router(*, write_guard: Callable[..., Any], registry: Optional[ModelRegistry] = None,
                     gate: Optional[Gate] = None) -> APIRouter:
    """The `/api/schemas` routes over `registry` and `gate` (default: the app's). `write_guard` is required: a callable FastAPI
    dependency (`Services.require_token`); the POST route depends on it and the GET routes do not."""
    if not callable(write_guard):
        raise TypeError("write_guard must be a callable FastAPI dependency (Services.require_token)")
    reg = registry if registry is not None else REGISTRY
    checker = gate if gate is not None else (GATE if registry is None else Gate(reg))
    api = APIRouter(prefix=PREFIX, tags=["schemas"])

    @api.get("", summary="Every registered family with its versions and kinds")
    def list_schemas() -> dict:
        return {"families": [{"family": f, "versions": reg.versions(f), "kinds": list(reg.kinds(f))} for f in reg.families()]}

    @api.get("/{family}/{version}", summary="The JSON Schema of one version of a family")
    def get_schema(family: str, version: str):
        number = _version_of(version)
        try:
            if number is None or number not in reg.versions(family):
                raise RegistryError("unknown_version", version)
            return reg.json_schema(family, number)
        except RegistryError:
            known = reg.versions(family) if family in reg.families() else []
            return _error(404, "unknown_schema", f"There is no schema {family!r} version {version!r}",
                          {"family": family, "version": version, "versions": known})

    @api.post("/validate", dependencies=[Depends(write_guard)], summary="Check a payload against a family; stores nothing")
    async def validate(request: Request):
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return _too_large(int(declared))
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            return _too_large(len(raw))
        try:
            body = json.loads(raw)
        except (ValueError, RecursionError):
            return _invalid([violation("", "not_json", "the body must be one JSON object")])
        problems = _body_problems(body)
        if problems:
            return _invalid(problems)
        try:
            checked = await run_in_threadpool(checker.check, body["family"], body["payload"], version=body.get("version"))
        except GateError as exc:
            if exc.stage == "size":
                return _error(413, "payload_too_large", "The payload is over the 1 MiB limit",
                              {"limit": MAX_PAYLOAD_BYTES, "violations": [v.model_dump() for v in exc.violations]})
            return _invalid(exc.violations, str(exc))
        except RegistryError as exc:
            return _error(500, "internal", f"the registry could not check this payload ({exc.code})")
        return {"ok": True, "sha256": checked.sha256}

    return api


def _too_large(size: int) -> JSONResponse:
    return _error(413, "payload_too_large", "The request is over the 1 MiB limit", {"limit": MAX_PAYLOAD_BYTES, "size": size})


def _body_problems(body: Any) -> list[Violation]:
    if not isinstance(body, dict):
        return [violation("", "not_an_object", "the body must be a JSON object")]
    found: list[Violation] = []
    family = body.get("family")
    if not isinstance(family, str) or not 1 <= len(family) <= 120:
        found.append(violation("family", "family", "family is required: a string of 1 to 120 characters"))
    version = body.get("version")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int)):
        found.append(violation("version", "version", "version, when given, must be an integer"))
    if not isinstance(body.get("payload"), dict):
        found.append(violation("payload", "payload", "payload is required and must be a JSON object"))
    found.extend(violation(key, "extra_forbidden", "this key is not part of the request")
                 for key in body if key not in ("family", "version", "payload"))
    return found


build_router = build_api_router
