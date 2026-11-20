"""The multi-agent nodes routes (guardrails 7; D279). This package (MAN-4) holds the kill switch and pause; the project routes arrive with the projects (MAN-5).

    GET  /api/nodes/status        -> {level none|pause|kill, kill, pause}      (what the two files say; no token, like every read)
    POST /api/nodes/pause-all     {reason?}  -> {affected: n}                  n = nodes that now wait to start; the ones that run finish
    POST /api/nodes/kill-all      {reason?}  -> {affected: n, file_written: bool}   n = nodes stopped through the stop ladder (all together); file_written is false when
                                                                              the KILL file could not be written (the nodes are stopped anyway); no new node starts until resumed
    POST /api/nodes/resume        {}         -> {resumed: bool}                removes both files; what waited starts
    GET  /api/nodes/app-location  -> {usual: bool, note: str}                  (MAN-13, D322 d: false with plain words when the installed app is not in the usual place)
    POST /api/nodes/{id}/stop     {}         -> {stopped: bool}                that node's task through the stop ladder; 404 for a node that does not exist

    GET  /api/projects            ?status=&limit=&offset=&client_id=  -> ProjectOut[]                  (MAN-5: the projects, newest first)
    POST /api/projects            {client_id, text, budget?, failure_policy?, decide_for_me?} -> 202 {message_id, turn, duplicate:false}; a repeated client_id -> 200 {duplicate:true}   (MAN-13, D326)
    GET  /api/projects/{id}/messages ?after=&limit=         -> node-message/1[] in seq order (MAN-6; 1, 2, 3 ... per project with no gap, D297)
    GET  /api/projects/{id}/audit    ?after=&limit=         -> the audit rows of the project
    GET  /api/projects/{id}       -> snapshot: project, nodes, edges, caps, spend, open approvals, last_message_seq
    POST /api/projects/{id}/stop  {}                       -> {stopped: n}                  the project is stopped, its agents go through the stop ladder together
    POST /api/projects/{id}/pause {resume?: bool}          -> ProjectOut
    POST /api/projects/{id}/system/{item}/check {}          -> snapshot                      (MAN-15: the probe runs again; allowed: the steps that waited go on)
    POST /api/projects/{id}/system/{item}/skip  {}          -> snapshot                      (only the steps that need that permission are cancelled)
    POST /api/projects/{id}/approvals/{aid} {decision}     -> snapshot                      (MAN-8: allow_once | allow_project | deny; the plan is evaluated again and, when nothing is left to ask, the project starts)

Every route answers `404 not_found` while SUTRA_NODES_V1 is off, whoever asks and whether or not a token came (the feature does not exist then); with it on, every write needs the launch
token (`require_token`) as everywhere. Errors are the app's envelope. The router reads `request.app.state.services.node_control` (a `killswitch.NodeControl`).
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from sutra_app import oslayer
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound
from sutra_app.orchestrator.ids import ORG_SESSION_ID, IdFactory
from sutra_app.orchestrator.killswitch import REASON_MAX, NodeControl

__all__ = ["build_router", "ReasonBody", "EmptyBody", "PauseBody"]


class ReasonBody(BaseModel):
    """The body of pause-all and kill-all. Closed; the reason is a few words for the audit (clipped and scrubbed there too)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    reason: str = Field("", max_length=REASON_MAX)


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AnswerBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["allow_once", "allow_project", "deny"]


class StartBody(BaseModel):
    """`POST /api/projects` (MAN-13, D310 c, D326). The owner's request in their own words, how the project fails and the same two switches the home screen has. Closed."""

    model_config = ConfigDict(extra="forbid", strict=True)
    client_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    text: str = Field(min_length=1, max_length=8000)
    budget: int | None = Field(None, ge=1, le=100_000)
    failure_policy: Literal["stop_branch", "stop_all"] = "stop_branch"
    decide_for_me: bool = False


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
        settings = request.app.state.services.settings
        return _json(request, {**_control(request).switch.status(), "settings": {"SUTRA_NODES_V1": True, "SUTRA_NODES_LANES": bool(settings.nodes_lanes), "SUTRA_NODES_REVIEWER": bool(settings.nodes_reviewer),
                                                                               "SUTRA_NODES_SLOTS": bool(settings.nodes_slots)}})     # what THIS running app was started with (the command line reads it: its own shell may differ, D384)

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

    @router.get("/api/nodes/app-location", summary="Whether the app runs from the usual place for an installed app (plain words when it does not)")
    async def app_location(request: Request) -> RedactedJSONResponse:
        return _json(request, await run_blocking(oslayer.app_location))

    # ---- the projects (MAN-5) ----------------------------------------------------------------------------------------------------

    @router.get("/api/projects", summary="The projects, newest first")
    async def list_projects(request: Request, status: str | None = None, limit: int = 50, offset: int = 0, client_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]{8,64}$")) -> RedactedJSONResponse:
        request_id = None
        if client_id is not None:                                                          # the project a `POST /api/projects` with this `client_id` started (R6, D334); none yet = []
            runner = getattr(services_of(request), "runner", None)
            line = await run_blocking(runner.line_of, client_id) if runner is not None else None
            if line is None:
                return _json(request, [])
            request_id = IdFactory.request_id(line)
        found = await run_blocking(lambda: _projects(request).list_projects(status=status, limit=limit, offset=offset, request_id=request_id))
        return _json(request, [project.model_dump(mode="json") for project in found])

    @router.post("/api/projects", summary="Start a project from a request in the owner's own words", dependencies=[Depends(require_token)])
    async def start_project(request: Request, body: StartBody) -> RedactedJSONResponse:
        """The request goes to the org chat as the owner's line, exactly as if typed there, with the failure policy kept for the project it may become; the plan is made after this answers, so the
        answer is `202 {message_id, turn}` and the project appears in `GET /api/projects` (D326). A repeated `client_id` answers `200 {duplicate: true, message_id}` and starts nothing."""
        runner = getattr(services_of(request), "runner", None)
        if runner is None:
            raise AppError("internal", "the chat agent is not wired")
        if (found := await run_blocking(runner.line_of, body.client_id)) is not None:
            return _json(request, {"duplicate": True, "message_id": found, "client_id": body.client_id})
        try:
            accepted = await runner.post_user_message(ORG_SESSION_ID, body.text, None, budget=body.budget, decide_for_me=body.decide_for_me, failure_policy=body.failure_policy, client_id=body.client_id)
        except AlreadyDecided:                                                      # the same send, caught while its first request was storing the line
            return _json(request, {"duplicate": True, "message_id": await run_blocking(runner.line_of, body.client_id), "client_id": body.client_id})
        return _json(request, {**accepted.model_dump(mode="json"), "duplicate": False, "client_id": body.client_id}, 202)

    @router.get("/api/projects/{project_id}", summary="One project: its nodes, edges, caps, spend and open questions")
    async def get_project(request: Request, project_id: str) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_projects(request).snapshot, project_id))

    @router.get("/api/projects/{project_id}/messages", summary="The messages of a project after `after`, in order (1, 2, 3 ... with no gap)")
    async def project_messages(request: Request, project_id: str, after: int = 0, limit: int = 100) -> RedactedJSONResponse:
        service = _projects(request)
        await run_blocking(service.get, project_id)                                  # 404 for a project that does not exist
        found = await run_blocking(lambda: service.store.messages(project_id, after=after, limit=limit))
        return _json(request, [message.as_dict() for message in found])

    @router.get("/api/projects/{project_id}/audit", summary="The audit rows of a project after `after`")
    async def project_audit(request: Request, project_id: str, after: int = 0, limit: int = 100) -> RedactedJSONResponse:
        service = _projects(request)
        await run_blocking(service.get, project_id)
        return _json(request, await run_blocking(lambda: service.store.audit_rows(project_id=project_id, after=after, limit=limit)))

    @router.post("/api/projects/{project_id}/stop", summary="Stop a project: its agents through the stop ladder, nothing starts by itself afterwards", dependencies=[Depends(require_token)])
    async def stop_project(request: Request, project_id: str, body: EmptyBody) -> RedactedJSONResponse:
        return _json(request, {"stopped": await _projects(request).stop(project_id, by="owner")})

    @router.post("/api/projects/{project_id}/approvals/{approval_id}", summary="Answer one question of a project: allow_once, allow_project or deny", dependencies=[Depends(require_token)])
    async def answer_approval(request: Request, project_id: str, approval_id: str, body: AnswerBody) -> RedactedJSONResponse:
        return _json(request, await _projects(request).answer(project_id, approval_id, body.decision, by="owner"))

    @router.post("/api/projects/{project_id}/system/{item}/check", summary="Check again: the computer has been asked for the permission once more", dependencies=[Depends(require_token)])
    async def system_check(request: Request, project_id: str, item: str, body: EmptyBody) -> RedactedJSONResponse:
        return _json(request, await _projects(request).system_check(project_id, item))

    @router.post("/api/projects/{project_id}/system/{item}/skip", summary="Skip: cancel only the steps that need that permission", dependencies=[Depends(require_token)])
    async def system_skip(request: Request, project_id: str, item: str, body: EmptyBody) -> RedactedJSONResponse:
        return _json(request, await _projects(request).system_skip(project_id, item))

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
