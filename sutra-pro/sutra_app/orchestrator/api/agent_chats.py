"""The chats of the agents (agent-sessions design 3.6, D130 to D132). Reads need no token; writes do (D81).

    GET  /api/teams/{dept}/agents?run=<run_id>   -> [{agent, label, kind: function|step, title, session_id, node_id, run_id, task_id, state, live, status, own,
                                                       run_pick, effective: {provider, model, effort, source}, usage: {calls, usd, tokens_in, tokens_out}, last_at}]
                                                    the team's five active function sessions plus every session stamped with `run` (builders, and the function
                                                    sessions a later run rolled); `run` defaults to the live run, else the latest (404 for a run of another team)

The router reads `services.db`, `services.tasks` and, for the policy default of an agent, `services.chat_port` (a stand-in without one knows no default).
"""
from __future__ import annotations

from fastapi import APIRouter, Path, Query, Request

from sutra_app.orchestrator.agent_sessions import team_agents
from sutra_app.orchestrator.api.chat import ID_PATTERN, respond
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError

__all__ = ["router", "build_router"]


def _need(request: Request, name: str):
    found = getattr(services_of(request), name, None)
    if found is None:
        raise AppError("internal", f"the {name} is not wired")
    return found


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["agent chats"])

    @router.get("/teams/{dept}/agents", summary="The chats of a team's agents for one run")
    async def agents(request: Request, dept: str = Path(pattern=ID_PATTERN), run: str | None = Query(None, pattern=ID_PATTERN)) -> RedactedJSONResponse:
        db, tasks = _need(request, "db"), _need(request, "tasks")
        port = getattr(services_of(request), "chat_port", None)
        default = getattr(port, "default_pick", None)
        found = await run_blocking(lambda: team_agents(db.conn(), tasks.store, dept, run, default if callable(default) else None))
        return respond(request, found)

    return router


router = build_router()
