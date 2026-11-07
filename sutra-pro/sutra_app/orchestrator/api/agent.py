"""The chat agent's routes (orchestrator 6.2): posting in a chat, retrying a failed request, answering a chart change.

    POST /api/chats/{sid}/messages               {text, choice?}  -> org chat: 202 Accepted | team chat: 200 Delivery | read-only: 403
    POST /api/chats/cs_org/retry                                  -> 202 Accepted
    POST /api/chart/changes/{change_id}/decision {approve}        -> 200 ChangeResult | 409 already_decided   (goes through the turn runner)

Every route needs the token (`require_token`). The org chat belongs to the chat agent (`TurnRunner`): the call returns at once and the
turn runs behind it; a missing or signed-out connector is 503 `provider_unavailable` / `cli_missing` before anything is stored, a full
queue is 429 `too_many_pending`. A department or division chat takes the owner's words to the team's Identity through
`TaskService.deliver` (409 `busy` while it works); a function or step chat, and an archived one, is 403 `read_only`. Either route is 409 `busy` while a
direct turn is answering in that chat (`direct_running`).

The decision route has the same path as the one in `api/chart.py` on purpose: this one finishes the request the change belongs to
(assignments, tasks, lines, cards), the chart router's only decides. `create_app` includes THIS router BEFORE the chart router, so
Starlette's first match is the one that runs.
"""
from typing import Any

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator import direct_running
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, Busy, ReadOnly
from sutra_app.orchestrator.ids import ORG_SESSION_ID
from sutra_app.orchestrator.models import ChatPost

__all__ = ["router", "build_router", "DecisionIn"]

ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"
CHANGE_ID_PATTERN = r"^chg-[0-9]{4,9}$"


class DecisionIn(BaseModel):
    """`{approve: true|false}`, closed: any other key is a 422."""

    model_config = ConfigDict(extra="forbid", strict=True)
    approve: bool


def _need(request: Request, name: str) -> Any:
    found = getattr(services_of(request), name, None)
    if found is None:
        raise AppError("internal", f"the {name} is not wired")
    return found


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(tags=["chat agent"])

    @router.post("/api/chats/{sid}/messages", summary="Write in a chat", dependencies=[Depends(require_token)])
    async def post_message(request: Request, body: ChatPost, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        chats = _need(request, "chats")
        session = await run_blocking(chats.session, sid)                       # 404 for an unknown chat
        if session.status != "active" or not session.writable or session.kind in ("function", "step"):
            raise ReadOnly("This chat is read-only" if session.status == "active" else "This chat is archived and read-only")
        if direct_running.answering(sid):                                     # the owner asked the model directly and it is still writing: two answers would interleave
            raise Busy("This chat is already answering")
        if session.kind == "org":
            accepted = await _need(request, "runner").post_user_message(sid, body.text, body.choice)
            return _json(request, accepted.model_dump(mode="json"), 202)
        delivery = await run_blocking(_need(request, "tasks").deliver, sid, body.text)
        return _json(request, delivery.model_dump(mode="json"))

    @router.post(f"/api/chats/{ORG_SESSION_ID}/retry", summary="Run the last failed request again", dependencies=[Depends(require_token)])
    async def post_retry(request: Request) -> RedactedJSONResponse:
        accepted = await _need(request, "runner").retry(ORG_SESSION_ID)
        return _json(request, accepted.model_dump(mode="json"), 202)

    @router.post("/api/chart/changes/{change_id}/decision", summary="Answer a pending approval", dependencies=[Depends(require_token)])
    async def post_decision(request: Request, body: DecisionIn, change_id: str = Path(pattern=CHANGE_ID_PATTERN)) -> RedactedJSONResponse:
        try:
            result = await _need(request, "runner").decide(change_id, body.approve)
        except AlreadyDecided as exc:
            raise AppError("already_decided", "That change was decided already",
                           {"result": exc.result.model_dump(mode="json") if exc.result is not None else None}) from None
        return _json(request, result.model_dump(mode="json"))

    return router


router = build_router()
