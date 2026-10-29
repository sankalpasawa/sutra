"""shadow_graph_api.py -- GET /api/shadow/graph and /api/shadow/graph/task/{mid} (PRD amendment A5, A5.2.2).

The builder validated what it returns before it memoised it (finding F11), so these routes only serve it: JSONResponse over the
validated dict, no response_model (STR-4). No import of app."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import providers
import shadow_graph

router = APIRouter()


@router.get("/api/shadow/graph")
async def api_shadow_graph(focus: str = "", include_done: int = 0):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    return JSONResponse(shadow_graph.build(focus=focus or None, include_done=bool(include_done)))


@router.get("/api/shadow/graph/task/{mid}")
async def api_shadow_graph_task(mid: str):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    got = shadow_graph.detail(mid)
    if got is None:
        raise HTTPException(404, "no such task")
    return JSONResponse(got)
