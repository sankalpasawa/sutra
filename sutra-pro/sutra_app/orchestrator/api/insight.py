"""Insight routes: what the chart is about, read-only (gap package chart-insight; docs/notes/GAP2-chart-insight.md). All are reads, so none needs a
token, and none writes.

    GET /api/chart/changes/{change_id}/impact   -> ChangeImpactOut   what a yes would do to a change waiting for approval, in words (404 not_found)
    GET /api/chart/notes                        -> ChartNotesOut     overlapping teams, teams with no purpose, teams nobody uses (up to 20, and the total)
    GET /api/find?q=                            -> {teams, counts, truncated, messages}   teams and divisions that match, then the chat search's messages

The impact of a change that is not waiting any more (decided, refused, stale) is empty: only a pending change has a 'what would a yes do'.
The notes and the find read the time from `services.clock` (the one clock: `now` is a parameter of the reads). `messages` of the find are the
existing chat search's rows (`ChatSearch`, at most 8), shown by the page as a second group, so the FTS table is not searched twice.
"""
from fastapi import APIRouter, Path, Query, Request

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.chart import ChartStore
from sutra_app.orchestrator.chart_health import ChartHealth
from sutra_app.orchestrator.chat_v2 import ChatSearch
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.reorg_preview import ChangeImpactOut, ReorgPreview
from sutra_app.orchestrator.team_find import TeamFind, words_of

__all__ = ["router", "build_router", "MESSAGE_HITS"]

CHANGE_ID_PATTERN = r"^chg-[0-9]{4,9}$"
MESSAGE_HITS = 8


def _chart(request: Request) -> ChartStore:
    store = getattr(services_of(request), "chart", None)
    if store is None:
        raise AppError("internal", "the chart store is not wired")
    return store


def _json(request: Request, data) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["insight"])

    @router.get("/chart/changes/{change_id}/impact", summary="What a yes would do to a change waiting for approval")
    async def get_impact(request: Request, change_id: str = Path(pattern=CHANGE_ID_PATTERN)) -> RedactedJSONResponse:
        store = _chart(request)

        def read() -> ChangeImpactOut:
            stored = store.record(change_id)
            if stored.out.status != "pending_approval" or stored.change is None:
                return ChangeImpactOut(change_id=change_id, status=stored.out.status)
            impact = ReorgPreview(services_of(request).db).describe(stored.change.model, store.head().model)
            return ChangeImpactOut(change_id=change_id, status=stored.out.status, lines=impact.lines, notes=impact.notes)

        return _json(request, (await run_blocking(read)).model_dump(mode="json"))

    @router.get("/chart/notes", summary="What has drifted in the org chart")
    async def get_notes(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        now = services.clock.now()
        return _json(request, (await run_blocking(lambda: ChartHealth(services.db).notes(now))).model_dump(mode="json"))

    @router.get("/find", summary="Find a team or its work across the org")
    async def get_find(request: Request, q: str = Query("", max_length=200)) -> RedactedJSONResponse:
        services = services_of(request)

        def read() -> dict:
            found = TeamFind(services.db).search(q).model_dump(mode="json")
            found["messages"] = ChatSearch(services.db).search(q, limit=MESSAGE_HITS) if words_of(q) else []
            return found

        return _json(request, await run_blocking(read))

    return router


router = build_router()
