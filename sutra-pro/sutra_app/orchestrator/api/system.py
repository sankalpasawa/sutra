"""`GET /api/health` and `GET /api/config` (orchestrator 6.2; work package ORCH-8). Both are reads: open on loopback, no token.

    /api/health   {ok, version, schema, connectors:{claude:{...}, codex:{...}}}
                  `ok` is true when the database answers; `schema` is the database's schema version; `connectors` is the
                  connector layer's `status()` (per provider: installed, signed_in, detail, ...). The release launcher and the
                  macOS proof step poll this route, so it answers fast: the connector status may run a CLI's status command when
                  its cache is older than 30 s, and when that takes longer than `STATUS_WAIT_S` the route answers with
                  `connectors: {}` (the next call finds the warmed cache). A database that cannot answer is 503 `ok: false`.
    /api/config   the non-secret settings (`Settings.public()`: never the token or the override key), `max_runs` and `max_live`
                  among them.
"""
import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.db import run_blocking

__all__ = ["build_router", "STATUS_WAIT_S"]

log = logging.getLogger(__name__)
STATUS_WAIT_S = 1.5


def _json(request: Request, content: Any, status: int = 200) -> RedactedJSONResponse:
    services = services_of(request)
    scrub = getattr(services.redact, "scrub", None)
    return RedactedJSONResponse(scrub(content) if callable(scrub) else content, status_code=status)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["system"])

    @router.get("/health", summary="Is the server up, and which connectors work")
    async def get_health(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        try:
            version = await run_blocking(services.db.version)
        except Exception:                                                         # noqa: BLE001
            log.exception("the health check could not read the database")
            return _json(request, {"ok": False, "version": services.version, "schema": None, "connectors": {}}, 503)
        connectors: dict[str, Any] = {}
        try:
            connectors = dict(await asyncio.wait_for(run_blocking(services.connector.status), STATUS_WAIT_S))
        except asyncio.TimeoutError:
            log.warning("the connector status took longer than %.1f s; health answers without it", STATUS_WAIT_S)
        except Exception:                                                         # noqa: BLE001
            log.exception("the connector status failed")
        return _json(request, {"ok": True, "version": services.version, "schema": version, "connectors": connectors})

    @router.get("/config", summary="The non-secret settings")
    async def get_config(request: Request) -> RedactedJSONResponse:
        return _json(request, services_of(request).settings.public())

    return router
