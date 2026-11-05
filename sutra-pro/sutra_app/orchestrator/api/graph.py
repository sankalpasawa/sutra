"""Graph routes (orchestrator 6.2): `GET /api/graph` and `GET /api/graph/nodes/{id}`. Both are reads, so they need no token.

    GET /api/graph?level=chart|full&dept=&task=     -> GraphView   (nodes in depth-first pre-order; a function node's meta is {stats, wait_on})
    GET /api/graph/nodes/{id}                       -> NodeDetail  (404 not_found; a function node's meta is the full seven keys)

The router reads `request.app.state.services.graph` (a `GraphStore`). The store is synchronous, so each call runs on a worker
thread (`run_blocking`). Bodies go through the redacting JSON response; when `Services.redact` is a `Redactor` its `scrub` cleans
the data first, so the launch token and the override key (explicit secrets, not only environment values) are removed too.
"""
from typing import Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.graph import GraphStore, Level

__all__ = ["router", "build_router"]

ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"       # every id in a URL (design 6.1)


def _store(request: Request) -> GraphStore:
    store = getattr(services_of(request), "graph", None)
    if store is None:
        raise AppError("internal", "the graph store is not wired")
    return store


def _body(request: Request, model: BaseModel) -> RedactedJSONResponse:
    data: Any = model.model_dump(mode="json")
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/graph", tags=["graph"])

    @router.get("", summary="The workflow graph")
    async def get_graph(
        request: Request,
        level: Level = Query("chart", description="chart: root, departments, divisions and the latest task step of each department; full: adds function nodes and the steps of live or recent tasks"),
        dept: str | None = Query(None, pattern=ID_PATTERN, description="keep this department's subtree and the way up to the root"),
        task: str | None = Query(None, pattern=ID_PATTERN, description="keep only this task's steps"),
    ) -> RedactedJSONResponse:
        view = await run_blocking(lambda: _store(request).view(level=level, dept=dept, task=task))
        return _body(request, view)

    @router.get("/nodes/{node_id}", summary="One node with its chat session, atoms, usage and task")
    async def get_node(request: Request, node_id: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        detail = await run_blocking(lambda: _store(request).node(node_id))
        return _body(request, detail)

    return router


router = build_router()
