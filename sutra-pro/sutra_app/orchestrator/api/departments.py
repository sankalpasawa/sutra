"""Department routes (orchestrator 6.2). All reads, so no token.

    GET /api/departments                  -> DepartmentOut[]   (chart order)
    GET /api/departments/{id}             -> DepartmentOut     (404 not_found)
    GET /api/departments/{id}/runs        -> RunRef[]          (newest first; 404 not_found)

A department is never archived (DL5), so there is no `include=archived`. The router reads `request.app.state.services.departments`.
"""
from typing import Any

from fastapi import APIRouter, Path, Request
from pydantic import BaseModel

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.departments import DepartmentStore
from sutra_app.orchestrator.errors import AppError

__all__ = ["router", "build_router"]

DEPT_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"       # a department id is stricter, but the URL rule is the generic one (design 6.1)


def _store(request: Request) -> DepartmentStore:
    store = getattr(services_of(request), "departments", None)
    if store is None:
        raise AppError("internal", "the department store is not wired")
    return store


def _json(request: Request, data: Any) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(content=scrub(data) if callable(scrub) else data)


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/departments", tags=["departments"])

    @router.get("", summary="Every department")
    async def get_departments(request: Request) -> RedactedJSONResponse:
        rows = await run_blocking(lambda: _store(request).listing())
        return _json(request, [_dump(r) for r in rows])

    @router.get("/{dept_id}", summary="One department")
    async def get_department(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(lambda: _store(request).get(dept_id))))

    @router.get("/{dept_id}/runs", summary="The runs of a department, newest first")
    async def get_runs(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        rows = await run_blocking(lambda: _store(request).runs(dept_id))
        return _json(request, [_dump(r) for r in rows])

    return router


router = build_router()
