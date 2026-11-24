"""Appearance choices kept for this app profile (see `orchestrator/appearance.py`): today the team avatar style. The read needs no token; the write
depends on `require_token` (D81).

    GET    /api/appearance                 -> {version, avatars}    "classic" when nothing was saved or the file is damaged
    PUT    /api/appearance   {avatars}     -> {version, avatars}    "classic" | "illustrated" (422 `validation` on anything else)

The store is built from `services.settings.data_dir` on each call (it holds no state of its own), so a test `Services` needs no wiring. The page
server reads the same file into each page's boot block, so a page draws the chosen style on its first paint, also on a new port.
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.appearance import AppearanceStore
from sutra_app.orchestrator.db import run_blocking

__all__ = ["router", "build_router"]


class AppearanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    avatars: Literal["classic", "illustrated"]


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def _store(request: Request) -> AppearanceStore:
    return AppearanceStore(services_of(request).settings.data_dir)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["appearance"])

    @router.get("/appearance", summary="The look choices of this app profile (the team avatar style)")
    async def get_appearance(request: Request) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_store(request).load))

    @router.put("/appearance", summary="Keep the team avatar style", dependencies=[Depends(require_token)])
    async def put_appearance(request: Request, body: AppearanceIn) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_store(request).save, {"avatars": body.avatars}))

    return router


router = build_router()
