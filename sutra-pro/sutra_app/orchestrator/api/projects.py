"""The multi-agent nodes routes (guardrails 7; D279). This package (MAN-4) holds the kill switch and pause; the project routes arrive with the projects (MAN-5).

    GET  /api/nodes/status        -> {level none|pause|kill, kill, pause}      (what the two files say; no token, like every read)
    POST /api/nodes/pause-all     {reason?}  -> {affected: n}                  n = nodes that now wait to start; the ones that run finish
    POST /api/nodes/kill-all      {reason?}  -> {affected: n, file_written: bool}   n = nodes stopped through the stop ladder (all together); file_written is false when
                                                                              the KILL file could not be written (the nodes are stopped anyway); no new node starts until resumed
    POST /api/nodes/resume        {}         -> {resumed: bool}                removes both files; what waited starts
    POST /api/nodes/{id}/stop     {}         -> {stopped: bool}                that node's task through the stop ladder; 404 for a node that does not exist

    GET  /api/projects            ?status=&limit=&offset=  -> ProjectOut[]                  (MAN-5: the projects, newest first)
    GET  /api/projects/{id}       -> snapshot: project, nodes, edges, caps, spend, open approvals, last_message_seq
    POST /api/projects/{id}/stop  {}                       -> {stopped: n}                  the project is stopped, its agents go through the stop ladder together
    POST /api/projects/{id}/pause {resume?: bool}          -> ProjectOut

Every route answers `404 not_found` while SUTRA_NODES_V1 is off, whoever asks and whether or not a token came (the feature does not exist then); with it on, every write needs the launch
token (`require_token`) as everywhere. Errors are the app's envelope. The router reads `request.app.state.services.node_control` (a `killswitch.NodeControl`).
"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.killswitch import REASON_MAX, NodeControl

__all__ = ["build_router", "ReasonBody", "EmptyBody", "PauseBody"]


class ReasonBody(BaseModel):
    """The body of pause-all and kill-all. Closed; the reason is a few words for the audit (clipped and scrubbed there too)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    reason: str = Field("", max_length=REASON_MAX)


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PauseBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    resume: bool = False


async def nodes_enabled(request: Request) -> None:
    """The feature's one guard: 404 while SUTRA_NODES_V1 is off. It runs before the token check, so an off feature looks the same to everybody."""
    if not services_of(request).settings.nodes_v1:
        raise NotFound("that")


def _control(request: Request) -> NodeControl:
    found = getattr(services_of(request), "node_control", None)
    if found is None:
        raise AppError("internal", "the node controls are not wired")
    return found


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(tags=["nodes"], dependencies=[Depends(nodes_enabled)])

    @router.get("/api/nodes/status", summary="The kill switch and pause, as the two files say")
    async def status(request: Request) -> RedactedJSONResponse:
        return _json(request, _control(request).switch.status())

    @router.post("/api/nodes/pause-all", summary="No new agent starts; the ones that run finish", dependencies=[Depends(require_token)])
    async def pause_all(request: Request, body: ReasonBody) -> RedactedJSONResponse:
        return _json(request, {"affected": await _control(request).pause_all(by="owner", reason=body.reason)})

    @router.post("/api/nodes/kill-all", summary="Stop every agent through the stop ladder; none starts until you resume", dependencies=[Depends(require_token)])
    async def kill_all(request: Request, body: ReasonBody) -> RedactedJSONResponse:
        result = await _control(request).kill_all(by="owner", reason=body.reason)
        return _json(request, {"affected": int(result), "file_written": result.file_written})

    @router.post("/api/nodes/resume", summary="Remove the pause and the kill switch", dependencies=[Depends(require_token)])
    async def resume(request: Request, body: EmptyBody) -> RedactedJSONResponse:
        return _json(request, {"resumed": await _control(request).resume(by="owner")})

    @router.post("/api/nodes/{node_id}/stop", summary="Stop one agent through the stop ladder", dependencies=[Depends(require_token)])
    async def stop_node(request: Request, node_id: str, body: EmptyBody) -> RedactedJSONResponse:
        stopped = await _control(request).stop_node(node_id, by="owner")
        if not stopped and await _gone(request, node_id):
            raise NotFound("that agent")
        return _json(request, {"stopped": stopped})

    # ---- the projects (MAN-5) ----------------------------------------------------------------------------------------------------

    @router.get("/api/projects", summary="The projects, newest first")
    async def list_projects(request: Request, status: str | None = None, limit: int = 50, offset: int = 0) -> RedactedJSONResponse:
        found = await run_blocking(lambda: _projects(request).list_projects(status=status, limit=limit, offset=offset))
        return _json(request, [project.model_dump(mode="json") for project in found])

    @router.get("/api/projects/{project_id}", summary="One project: its nodes, edges, caps, spend and open questions")
    async def get_project(request: Request, project_id: str) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_projects(request).snapshot, project_id))

    @router.post("/api/projects/{project_id}/stop", summary="Stop a project: its agents through the stop ladder, nothing starts by itself afterwards", dependencies=[Depends(require_token)])
    async def stop_project(request: Request, project_id: str, body: EmptyBody) -> RedactedJSONResponse:
        return _json(request, {"stopped": await _projects(request).stop(project_id, by="owner")})

    @router.post("/api/projects/{project_id}/pause", summary="Pause or resume one project: no agent of it starts while it is paused", dependencies=[Depends(require_token)])
    async def pause_project(request: Request, project_id: str, body: PauseBody) -> RedactedJSONResponse:
        return _json(request, (await _projects(request).pause(project_id, resume=body.resume)).model_dump(mode="json"))

    return router


def _projects(request: Request) -> Any:
    found = getattr(services_of(request), "projects", None)
    if found is None:
        raise AppError("internal", "the projects are not wired")
    return found


async def _gone(request: Request, node_id: str) -> bool:
    """True when there is no node with this id at all (a node whose task is over answers `{stopped: false}`, not 404)."""
    db = services_of(request).db
    return await run_blocking(lambda: db.conn().execute("SELECT 1 FROM agent_nodes WHERE id = ?", (node_id,)).fetchone() is None)
