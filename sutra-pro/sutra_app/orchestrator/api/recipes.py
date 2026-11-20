"""The Recipes routes (Devin parity DV-3; SUTRA_RECIPES_V1). Mounted by `create_app` only while the flag is on: with it off none of these paths exists (404 from the framework, before any token check).

    GET  /api/recipes            ?archived=0|1                       -> [{id, title, kind: own|starter, status, version, overview, updated_at}]   (the owner's, then the four starters)
    GET  /api/recipes/{id}       ?version=n                          -> the recipe with its body and its versions
    POST /api/recipes            {title, body, note?}                -> 201 {id, version}                  (token)
    PUT  /api/recipes/{id}       {title?, body, note?}               -> {id, version}                      a new version (token)
    POST /api/recipes/{id}/revert    {version}                       -> {id, version}                      a new version with the words of an old one (token)
    POST /api/recipes/{id}/archive   {archived}                      -> {id, status}                       (token)
    POST /api/recipes/{id}/copy  {}                                  -> 201 {id, version}                  an ordinary recipe with the words of this one (token)
    GET  /api/recipes/{id}/export                                    -> text/markdown                      the recipe as a file
    POST /api/recipes/import     {markdown}                          -> {title, body, draft: true}         a DRAFT to read and save: nothing is saved (token)
    POST /api/recipes/{id}/start {blanks, client_id, budget?}        -> 202 {message_id, turn, duplicate}  the recipe becomes a request in the org chat, planned and asked as any request (token)
    POST /api/projects/{id}/save-as-recipe {}                        -> {title, body, draft: true}         a draft made by code from a project; needs SUTRA_NODES_V1 too (token)

Reads need no token; every write needs the launch token. Errors are the app's envelope.
"""
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound
from sutra_app.orchestrator.ids import ORG_SESSION_ID
from sutra_app.orchestrator.recipes import RecipeService, parse_markdown

__all__ = ["build_router"]


class RecipeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str | None = None
    body: dict[str, Any]
    note: str = Field("", max_length=200)


class CreateIn(RecipeIn):
    title: str


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=1)


class ArchiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    archived: bool


class EmptyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    markdown: str = Field(max_length=30_000)


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    blanks: list[str] = Field(default_factory=list, max_length=9)
    client_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    budget: int | None = Field(None, ge=1, le=100_000)


async def recipes_enabled(request: Request) -> None:
    if not services_of(request).settings.recipes_v1:
        raise NotFound("that")


def _service(request: Request) -> RecipeService:
    services = services_of(request)
    return RecipeService(services.db, redact=getattr(services.redact, "scrub", None), projects=bool(services.settings.nodes_v1))


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(tags=["recipes"], dependencies=[Depends(recipes_enabled)])

    @router.get("/api/recipes", summary="The recipes: the owner's, then the starters")
    async def recipes(request: Request, archived: bool = Query(False)) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.list(archived=archived)))

    # fixed paths before `{recipe_id}` ones
    @router.post("/api/recipes/import", summary="Read a recipe file into a draft; nothing is saved", dependencies=[Depends(require_token)])
    async def import_file(request: Request, body: ImportIn) -> RedactedJSONResponse:
        service = _service(request)
        found = parse_markdown(body.markdown)
        from sutra_app.orchestrator.recipes import clean_body, clean_title
        found["title"] = clean_title(found["title"], service.redact)
        found["body"] = clean_body(found["body"], service.redact)          # the draft the owner sees already passed the same checks as a saved recipe
        return _json(request, {**found, "draft": True})

    @router.post("/api/recipes", summary="Save a new recipe", dependencies=[Depends(require_token)])
    async def create(request: Request, body: CreateIn) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.create(body.title, body.body, body.note)), 201)

    @router.get("/api/recipes/{recipe_id}", summary="One recipe, with its words and its versions")
    async def one(request: Request, recipe_id: str, version: int | None = Query(None, ge=1)) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.get(recipe_id, version)))

    @router.put("/api/recipes/{recipe_id}", summary="Change a recipe: a new version", dependencies=[Depends(require_token)])
    async def change(request: Request, recipe_id: str, body: RecipeIn) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.update(recipe_id, body.title, body.body, body.note)))

    @router.post("/api/recipes/{recipe_id}/revert", summary="Go back to an earlier version (as a new version)", dependencies=[Depends(require_token)])
    async def revert(request: Request, recipe_id: str, body: VersionIn) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.revert(recipe_id, body.version)))

    @router.post("/api/recipes/{recipe_id}/archive", summary="Put a recipe away, or bring it back", dependencies=[Depends(require_token)])
    async def archive(request: Request, recipe_id: str, body: ArchiveIn) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.archive(recipe_id, body.archived)))

    @router.post("/api/recipes/{recipe_id}/copy", summary="Make an ordinary copy of a recipe (the way to change a starter)", dependencies=[Depends(require_token)])
    async def copy(request: Request, recipe_id: str, body: EmptyIn) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.copy_of(recipe_id)), 201)

    @router.get("/api/recipes/{recipe_id}/export", summary="The recipe as a Markdown file")
    async def export(request: Request, recipe_id: str) -> Response:
        service = _service(request)
        title, text = await run_blocking(lambda: service.export(recipe_id))
        safe = "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")[:60] or "recipe"
        return Response(text, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{safe}.md"', "Cache-Control": "no-store"})

    @router.post("/api/recipes/{recipe_id}/start", summary="Start a recipe: it becomes a request, planned and asked as any request", dependencies=[Depends(require_token)])
    async def start(request: Request, recipe_id: str, body: StartIn) -> RedactedJSONResponse:
        service = _service(request)
        runner = getattr(services_of(request), "runner", None)
        if runner is None:
            raise AppError("internal", "the chat agent is not wired")
        if (found := await run_blocking(runner.line_of, body.client_id)) is not None:                  # the same send again starts nothing
            return _json(request, {"duplicate": True, "message_id": found, "client_id": body.client_id})
        title, text = await run_blocking(lambda: service.request_text(recipe_id, body.blanks))
        try:
            accepted = await runner.post_user_message(ORG_SESSION_ID, text, None, budget=body.budget, client_id=body.client_id)
        except AlreadyDecided:
            return _json(request, {"duplicate": True, "message_id": await run_blocking(runner.line_of, body.client_id), "client_id": body.client_id})
        return _json(request, {**accepted.model_dump(mode="json"), "duplicate": False, "client_id": body.client_id, "recipe": title}, 202)

    @router.post("/api/projects/{project_id}/save-as-recipe", summary="A draft recipe from a project, made by code; nothing is saved", dependencies=[Depends(require_token)])
    async def save_as(request: Request, project_id: str, body: EmptyIn) -> RedactedJSONResponse:
        service = _service(request)
        return _json(request, await run_blocking(lambda: service.draft_from_project(project_id)))

    return router
