"""A project's files, instructions and earlier-context memory (D451). Reads need no token; every write depends on `require_token` (D81). `{dept}` is a team: a project is a team (D426).

    GET    /api/teams/{dept}/files                  -> {files, totals, mode, limits}                the project's files, how they reach a chat (whole or excerpts) and every limit
    POST   /api/teams/{dept}/files                  {name, content_b64} -> 201 FileOut              upload straight to the project (a repeat is the same row, `already: true`)
    POST   /api/teams/{dept}/files/promote          {attachment_id, name?} -> FileOut               "Add to project": a file a chat or a request carried becomes a project file
    PATCH  /api/teams/{dept}/files/{fid}            {enabled?, name?} -> FileOut                    the switch "Use in this project", and a rename
    DELETE /api/teams/{dept}/files/{fid}            -> 204                                          remove one (the bytes go when nothing else uses them)
    DELETE /api/teams/{dept}/files                  -> 204                                          "Remove all files"
    POST   /api/teams/{dept}/attachments            {name, content_b64} -> AttachmentRef            store a file for ONE request (the start box): not in the project until promoted
    GET    /api/teams/{dept}/instructions           -> {text, rev, updated_at, max_chars}
    PUT    /api/teams/{dept}/instructions           {text, rev?} -> the same                         422 too long or secret-shaped; 409 `busy` with `details.stale` when `rev` is not current
    GET    /api/teams/{dept}/memory                 -> {enabled, entries, rev, max_entries, entry_chars}   newest first
    PUT    /api/teams/{dept}/memory                 {entries: [{n?, text, on}], rev?} -> the same    the owner's whole list; 409 stale
    POST   /api/teams/{dept}/memory                 {text} -> 201 EntryOut                           one line of the owner's own
    DELETE /api/teams/{dept}/memory/{n}             -> the memory
    PUT    /api/teams/{dept}/memory/settings        {enabled} -> the memory                          memory on or off
    GET    /api/teams/{dept}/context?message=       -> the exact text a chat and a run would be given now, with sizes and parts (the preview; nothing is sent)

Responses go through the redactor like the other team routes. The stores are built from `services.db` on each call.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sutra_app.connectors.errors import ConnectorError
from sutra_app.orchestrator import project_delivery
from sutra_app.orchestrator.api.chat_v2 import UploadIn
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.attachments import Attachments
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.project_files import ProjectFiles
from sutra_app.orchestrator.project_memory import ProjectMemory

__all__ = ["router", "build_router"]

DEPT_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"


class PromoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attachment_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str | None = Field(None, max_length=200)


class FilePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    name: str | None = Field(None, max_length=200)


class InstructionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=100_000)                  # the 4,000-character rule is the store's, with the sentence the owner reads
    rev: str | None = Field(None, min_length=1, max_length=64)


class EntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=5_000)


class EntryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int | None = None
    text: str = Field(max_length=5_000)
    on: bool = True


class MemoryPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: list[EntryItem] = Field(max_length=200)
    rev: str | None = Field(None, min_length=1, max_length=64)


class MemorySettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def _attachments(request: Request) -> Attachments:
    services = services_of(request)
    return getattr(services, "attachments", None) or Attachments(services.settings.data_dir)


def _files(request: Request) -> ProjectFiles:
    services = services_of(request)
    return ProjectFiles(services.db, _attachments(request).store, clock=services.clock)


def _memory(request: Request) -> ProjectMemory:
    services = services_of(request)
    return ProjectMemory(services.db, services.redact, clock=services.clock)


def _blob(body: UploadIn) -> bytes:
    try:
        return base64.b64decode(body.content_b64, validate=True)
    except (ValueError, binascii.Error):
        raise AppError("validation", "that file could not be read") from None


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/teams", tags=["project context"])
    guard = [Depends(require_token)]

    # ---- files -----------------------------------------------------------------------------------------------------------------------------------------

    @router.get("/{dept_id}/files", summary="The files of a project")
    async def get_files(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_files(request).list, dept_id)))

    @router.post("/{dept_id}/files", summary="Add a file to a project", dependencies=guard, status_code=201)
    async def post_file(request: Request, body: UploadIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        blob = _blob(body)

        def add() -> Any:
            ref = _attachments(request).upload(body.name, blob)
            return _files(request).add(dept_id, ref)
        try:
            return _json(request, _dump(await run_blocking(add)), 201)
        except ConnectorError as exc:
            raise AppError("validation", exc.user_message()) from None

    @router.post("/{dept_id}/files/promote", summary="Keep a file a chat or a request carried with the project", dependencies=guard)
    async def promote(request: Request, body: PromoteIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_files(request).promote, dept_id, body.attachment_id, body.name)))

    @router.patch("/{dept_id}/files/{file_id}", summary="Switch a file on or off for the project, or rename it", dependencies=guard)
    async def patch_file(request: Request, body: FilePatchIn, dept_id: str = Path(pattern=DEPT_PATTERN), file_id: str = Path(pattern=r"^pf_[0-9a-f]{12}$")) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(lambda: _files(request).patch(dept_id, file_id, enabled=body.enabled, name=body.name))))

    @router.delete("/{dept_id}/files/{file_id}", summary="Remove a file from a project", dependencies=guard, status_code=204)
    async def delete_file(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN), file_id: str = Path(pattern=r"^pf_[0-9a-f]{12}$")) -> Response:
        await run_blocking(_files(request).remove, dept_id, file_id)
        return Response(status_code=204)

    @router.delete("/{dept_id}/files", summary="Remove every file of a project", dependencies=guard, status_code=204)
    async def delete_files(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN)) -> Response:
        await run_blocking(_files(request).remove_all, dept_id)
        return Response(status_code=204)

    @router.post("/{dept_id}/attachments", summary="Store a file for one request to a project", dependencies=guard)
    async def post_attachment(request: Request, body: UploadIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        blob = _blob(body)
        await run_blocking(_files(request).list, dept_id)                      # 404 for a project that is not there
        try:
            ref = await run_blocking(_attachments(request).upload, body.name, blob)
        except ConnectorError as exc:
            raise AppError("validation", exc.user_message()) from None
        return _json(request, ref.model_dump(mode="json"))

    # ---- instructions ----------------------------------------------------------------------------------------------------------------------------------

    @router.get("/{dept_id}/instructions", summary="The instructions of a project")
    async def get_instructions(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_memory(request).instructions, dept_id)))

    @router.put("/{dept_id}/instructions", summary="Write the instructions of a project", dependencies=guard)
    async def put_instructions(request: Request, body: InstructionsIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_memory(request).put_instructions, dept_id, body.text, body.rev)))

    # ---- memory ----------------------------------------------------------------------------------------------------------------------------------------

    @router.get("/{dept_id}/memory", summary="What a project remembers of its earlier work")
    async def get_memory(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_memory(request).memory, dept_id)))

    @router.put("/{dept_id}/memory/settings", summary="Turn a project's memory on or off", dependencies=guard)
    async def put_memory_settings(request: Request, body: MemorySettingsIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_memory(request).set_enabled, dept_id, body.enabled)))

    @router.put("/{dept_id}/memory", summary="Replace the memory of a project with the owner's list", dependencies=guard)
    async def put_memory(request: Request, body: MemoryPutIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        items = [{"n": e.n, "text": e.text, "on": e.on} for e in body.entries]
        return _json(request, _dump(await run_blocking(_memory(request).put_memory, dept_id, items, body.rev)))

    @router.post("/{dept_id}/memory", summary="Add a line to a project's memory", dependencies=guard, status_code=201)
    async def post_memory(request: Request, body: EntryIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_memory(request).add_entry, dept_id, body.text)), 201)

    @router.delete("/{dept_id}/memory/{n}", summary="Take a line out of a project's memory", dependencies=guard)
    async def delete_memory(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN), n: int = Path(ge=1, le=10**9)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_memory(request).delete_entry, dept_id, n)))

    # ---- what will be sent -----------------------------------------------------------------------------------------------------------------------------

    @router.get("/{dept_id}/context", summary="Exactly what a chat and a run of the project would be given now")
    async def get_context(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN), message: str = Query("", max_length=8000)) -> RedactedJSONResponse:
        services = services_of(request)

        def read() -> dict:
            _files(request).list(dept_id)                                       # 404 for a project that is not there
            return project_delivery.preview(services.db, _attachments(request).store, services.redact, services.clock, dept_id, message)
        return _json(request, await run_blocking(read))

    return router


router = build_router()
