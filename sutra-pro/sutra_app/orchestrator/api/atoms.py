"""Atom routes (orchestrator 6.2). All are reads, so they need no token.

    GET /api/atoms?node_id=&task_id=&status=&limit=&offset=   -> AtomOut[]   (newest first; `status` is a display word; limit 1..500, default 50)
    GET /api/atoms/log?node_id=&after=&limit=                 -> AtomLogRow[] (the Atom log in `seq` order; `after` is a seq)
    GET /api/atoms/{id}                                       -> AtomOut     (404 not_found; the id is the stored key, so '<run>:W-3.a1' is valid)

`/atoms/log` is declared before `/atoms/{id}`. The router reads `request.app.state.services.atoms` (an `AtomStore`).
"""
from typing import Literal

from fastapi import APIRouter, Path, Query, Request

from sutra_app.orchestrator.api.chat import ID_PATTERN, respond
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.atoms import AtomStore
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError

__all__ = ["router", "build_router"]


def _store(request: Request) -> AtomStore:
    store = getattr(services_of(request), "atoms", None)
    if store is None:
        raise AppError("internal", "the atom store is not wired")
    return store


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/atoms", tags=["atoms"])

    @router.get("", summary="Atoms, newest first")
    async def list_atoms(
        request: Request,
        node_id: str | None = Query(None, pattern=ID_PATTERN),
        task_id: str | None = Query(None, pattern=ID_PATTERN),
        status: Literal["open", "verify_failed", "closed", "refused", "abandoned"] | None = Query(None, description="the display word"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> RedactedJSONResponse:
        found = await run_blocking(lambda: _store(request).find(node_id=node_id, task_id=task_id, status=status, limit=limit, offset=offset))
        return respond(request, found)

    @router.get("/log", summary="The Atom log")
    async def atom_log(
        request: Request,
        node_id: str | None = Query(None, pattern=ID_PATTERN),
        after: int = Query(0, ge=0, description="only rows with a seq above this"),
        limit: int = Query(50, ge=1, le=500),
    ) -> RedactedJSONResponse:
        return respond(request, await run_blocking(lambda: _store(request).log(node_id=node_id, after=after, limit=limit)))

    @router.get("/{atom_id}", summary="One atom")
    async def get_atom(request: Request, atom_id: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        return respond(request, await run_blocking(lambda: _store(request).get(atom_id)))

    return router


router = build_router()
