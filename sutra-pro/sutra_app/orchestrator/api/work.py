"""The Work routes (Devin parity DV-2; SUTRA_WORK_V1). Mounted by `create_app` only while the flag is on, so with it off none of these paths exists (404 from the framework, before any token check).

    GET  /api/work           ?tag=&q=&status=&limit=&offset=   -> [{kind, id, title, status, status_word, team, created_at, ended_at, tags, link}]  (newest first)
    GET  /api/work/tags                                         -> [{tag, count}]
    PUT  /api/work/{kind}/{id}/tags   {tags: [word]}            -> {tags}            kind is task or project; the whole set is replaced (token)
    GET  /api/projects/{id}/summary                             -> "How did it go?": what a project cost and where it got stuck, by code (needs SUTRA_NODES_V1 too)

Reads need no token, as everywhere; the write needs the launch token. Errors are the app's envelope.
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.work import WorkService

__all__ = ["build_router", "TagsBody"]


class TagsBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tags: list[str]


async def work_enabled(request: Request) -> None:
    if not services_of(request).settings.work_v1:
        raise NotFound("that")


def _service(request: Request) -> WorkService:
    services = services_of(request)
    return WorkService(services.db, redact=getattr(services.redact, "scrub", None), projects=bool(services.settings.nodes_v1))


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(tags=["work"], dependencies=[Depends(work_enabled)])

    @router.get("/api/work", summary="Everything Sutra did, newest first")
    async def work(request: Request, tag: str = Query("", max_length=40), q: str = Query("", max_length=200), status: str = Query("", max_length=30),
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000)) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.items(tag=tag, q=q, status=status, limit=limit, offset=offset)))

    @router.get("/api/work/tags", summary="Every tag in use and how many items have it")
    async def tags(request: Request) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(service.all_tags))

    @router.put("/api/work/{kind}/{item_id}/tags", summary="Replace the tags of a task or a project", dependencies=[Depends(require_token)])
    async def put_tags(request: Request, kind: Literal["task", "project"], item_id: str, body: TagsBody) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, {"tags": await run_blocking(lambda: service.set_tags(kind, item_id, body.tags))})

    @router.get("/api/projects/{project_id}/summary", summary="How did it go? What a project cost and where it got stuck")
    async def summary(request: Request, project_id: str) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.summary(project_id)))

    return router
