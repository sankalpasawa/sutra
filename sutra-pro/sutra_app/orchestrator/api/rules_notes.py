"""Standing rules, practice packs and owner notes (GAP2 rules-notes). Reads need no token; every write depends on `require_token` (D81).

    GET    /api/packs                      -> PackOut[]       the starter picks and the lines each one adds
    GET    /api/departments/{id}/rules     -> TeamRulesOut    the owner's rules for a team and its pick (404 not_found)
    PUT    /api/departments/{id}/rules     {rules?, pack?}    replaces the owner's list and/or the pick (422 `validation`, each refused line named)
    GET    /api/notes                      -> NotesOut        every note, grouped; an expired one says `expired`
    POST   /api/notes                      {group, text, expires?} -> 201 NoteOut   (422: a secret, a full group, a repeat, a past date)
    PUT    /api/notes/{id}                 {text?, expires?}  -> NoteOut
    DELETE /api/notes/{id}                 -> 204             forgets the note

The stores are built from `services.db` and `services.redact` on each call (they hold no state of their own), so a test `Services` needs no wiring.
Rules are read when a task starts and notes when a prompt is built; see `standing_rules.py` and `notes.py`.
"""
from typing import Any

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.notes import NoteIn, NotePatch, OwnerNotes
from sutra_app.orchestrator.owner_words import local_today
from sutra_app.orchestrator.standing_rules import RulesIn, StandingRules, packs_out

__all__ = ["router", "build_router"]

DEPT_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def _rules(request: Request) -> StandingRules:
    services = services_of(request)
    return StandingRules(services.db, services.redact)


def _notes(request: Request) -> OwnerNotes:
    services = services_of(request)
    return OwnerNotes(services.db, services.redact)


def _today(request: Request) -> str:
    return local_today(services_of(request).clock)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["rules-notes"])

    @router.get("/packs", summary="The practice packs a team can wear")
    async def get_packs(request: Request) -> RedactedJSONResponse:
        return _json(request, [_dump(p) for p in packs_out()])

    @router.get("/departments/{dept_id}/rules", summary="The standing rules of a team")
    async def get_rules(request: Request, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_rules(request).get, dept_id)))

    @router.put("/departments/{dept_id}/rules", summary="Replace the standing rules and/or the practice pick of a team", dependencies=[Depends(require_token)])
    async def put_rules(request: Request, body: RulesIn, dept_id: str = Path(pattern=DEPT_PATTERN)) -> RedactedJSONResponse:
        pack: Any = body.pack if "pack" in body.model_fields_set else False
        return _json(request, _dump(await run_blocking(lambda: _rules(request).put(dept_id, body.rules, pack=pack))))

    @router.get("/notes", summary="The owner's notes")
    async def get_notes(request: Request) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_notes(request).listing, _today(request))))

    @router.post("/notes", summary="Write a note", dependencies=[Depends(require_token)], status_code=201)
    async def post_note(request: Request, body: NoteIn) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_notes(request).add, body.group, body.text, body.expires, _today(request))), 201)

    @router.put("/notes/{note_id}", summary="Change a note", dependencies=[Depends(require_token)])
    async def put_note(request: Request, body: NotePatch, note_id: int = Path(ge=1, le=10**9)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_notes(request).edit, note_id, body, _today(request))))

    @router.delete("/notes/{note_id}", summary="Forget a note", dependencies=[Depends(require_token)], status_code=204)
    async def delete_note(request: Request, note_id: int = Path(ge=1, le=10**9)) -> Response:
        await run_blocking(_notes(request).forget, note_id)
        return Response(status_code=204)

    return router


router = build_router()
