"""Chat read routes (orchestrator 6.2). All are reads, so they need no token. The writes (`POST /api/chats/{sid}/messages`, retry)
belong to the agent routes.

    GET /api/chats?node_id=&include=archived        -> ChatSessionOut[]   (active sessions; `include=archived` adds the archived ones)
    GET /api/chats/{sid}                            -> ChatSessionOut     (404 not_found; `phase` is set for cs_org)
    GET /api/chats/{sid}/messages?after=&limit=     -> {messages: ChatMessageOut[], next_after}   (oldest first; limit 1..500, default 200)
    GET /api/needs-you                              -> NeedsYouOut[]      (open department questions and pending approvals)

`next_after` is the id to pass as `after` next time: the last message returned, or `after` itself when nothing new came.
The router reads `request.app.state.services.chats` (a `ChatStore`).
"""
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field

from sutra_app.library.base import Value
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.models import ChatMessageOut

__all__ = ["router", "build_router", "MessagePage", "ID_PATTERN"]

ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"       # every id in a URL (design 6.1)


class MessagePage(Value):
    messages: Annotated[list[ChatMessageOut], Field(max_length=500)]
    next_after: Annotated[int, Field(ge=0)]


def _store(request: Request) -> ChatStore:
    store = getattr(services_of(request), "chats", None)
    if store is None:
        raise AppError("internal", "the chat store is not wired")
    return store


def respond(request: Request, data: Any) -> RedactedJSONResponse:
    """`data` (a model, or a list of models) as a redacted JSON body."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    elif isinstance(data, list):
        data = [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in data]
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["chats"])

    @router.get("/chats", summary="The chat sessions")
    async def list_chats(
        request: Request,
        node_id: str | None = Query(None, pattern=ID_PATTERN, description="only the sessions of this node"),
        include: str | None = Query(None, pattern="^archived$", description="archived: add the sessions of merged-away nodes"),
    ) -> RedactedJSONResponse:
        found = await run_blocking(lambda: _store(request).sessions(node_id=node_id, include_archived=include == "archived"))
        return respond(request, found)

    @router.get("/chats/{sid}", summary="One chat session")
    async def get_chat(request: Request, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        return respond(request, await run_blocking(lambda: _store(request).session(sid)))

    @router.get("/chats/{sid}/messages", summary="The messages of a session, oldest first")
    async def get_messages(
        request: Request,
        sid: str = Path(pattern=ID_PATTERN),
        after: int = Query(0, ge=0, description="only messages with an id above this"),
        limit: int = Query(200, ge=1, le=500),
    ) -> RedactedJSONResponse:
        found = await run_blocking(lambda: _store(request).messages(sid, after=after, limit=limit))
        return respond(request, MessagePage(messages=found, next_after=found[-1].id if found else after))

    @router.get("/needs-you", summary="What waits for the owner")
    async def get_needs_you(request: Request) -> RedactedJSONResponse:
        return respond(request, await run_blocking(lambda: _store(request).needs_you()))

    return router


router = build_router()
