"""Sidebar sections: the owner's named groups of projects (see `sections.py`). The read needs no token; the write depends on `require_token` (D81).

    GET    /api/sections                   -> {version, sections}   the empty default when nothing was saved or the file is damaged
    PUT    /api/sections                   {version, sections} -> the document as kept   replaces it whole (422 `validation`, each refusal named)

The store is built from `services.settings.data_dir` on each call (it holds no state of its own), so a test `Services` needs no wiring.
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.sections import SectionsStore

__all__ = ["router", "build_router"]


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def _store(request: Request) -> SectionsStore:
    return SectionsStore(services_of(request).settings.data_dir)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["sections"])

    @router.get("/sections", summary="The owner's sidebar sections")
    async def get_sections(request: Request) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_store(request).load))

    @router.put("/sections", summary="Replace the owner's sidebar sections", dependencies=[Depends(require_token)])
    async def put_sections(request: Request, body: Any = Body(...)) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_store(request).save, body))

    return router


router = build_router()
