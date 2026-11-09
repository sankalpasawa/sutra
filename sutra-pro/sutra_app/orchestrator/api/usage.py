"""Usage routes (orchestrator 6.2). Both are reads, so they need no token.

    GET /api/usage?task_id=&dept_id=&fn=&session_id=&since=&include_stub=&after=&limit=   -> {rows: UsageOut[], totals}
    GET /api/usage/summary?by=dept|fn|provider|day|atom|session&session_id=&include_stub=   -> {groups: [{key, calls, usd, tokens_in, tokens_out}]}

`totals` cover every matching row, not just the page (`limit` default 50, max 500; `after` is a row id). `since` is epoch
seconds or an ISO time like 2026-11-04T10:00:06Z. Stub rows are left out of rows, totals and groups unless `include_stub=1`.
The router reads `request.app.state.services.usage` (a `UsageStore`).
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field

from sutra_app.library.base import Value
from sutra_app.library.types import violation
from sutra_app.orchestrator.api.chat import ID_PATTERN, respond
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError, validation_error
from sutra_app.orchestrator.models import UsageOut, UsageTotals
from sutra_app.orchestrator.usage import UsageStore, parse_since

__all__ = ["router", "build_router", "UsageList", "UsageGroupOut", "UsageSummary"]


class UsageList(Value):
    rows: Annotated[list[UsageOut], Field(max_length=500)]
    totals: UsageTotals


class UsageGroupOut(UsageTotals):
    key: str


class UsageSummary(Value):
    groups: Annotated[list[UsageGroupOut], Field(max_length=500)]


def _store(request: Request) -> UsageStore:
    store = getattr(services_of(request), "usage", None)
    if store is None:
        raise AppError("internal", "the usage store is not wired")
    return store


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/usage", tags=["usage"])

    @router.get("", summary="Usage rows with totals")
    async def get_usage(
        request: Request,
        task_id: str | None = Query(None, pattern=ID_PATTERN),
        dept_id: str | None = Query(None, pattern=ID_PATTERN),
        fn: str | None = Query(None, pattern=ID_PATTERN),
        session_id: str | None = Query(None, pattern=ID_PATTERN),
        since: str | None = Query(None, max_length=40, description="epoch seconds or 2026-11-04T10:00:06Z"),
        include_stub: bool = Query(False),
        after: int = Query(0, ge=0, le=2**53 - 1),
        limit: int = Query(50, ge=1, le=500),
    ) -> RedactedJSONResponse:
        try:
            floor = parse_since(since) if since is not None else None
        except ValueError as exc:
            raise validation_error([violation("query.since", "bad_time", str(exc))]) from None
        rows, totals = await run_blocking(lambda: _store(request).rows(
            task_id=task_id, dept_id=dept_id, fn=fn, since=floor, include_stub=include_stub, after=after, limit=limit, session_id=session_id))
        return respond(request, UsageList(rows=rows, totals=totals))

    @router.get("/summary", summary="Usage grouped by department, function, provider, day, atom or chat session")
    async def get_summary(
        request: Request,
        by: Literal["dept", "fn", "provider", "day", "atom", "session"] = Query("dept"),
        session_id: str | None = Query(None, pattern=ID_PATTERN),
        include_stub: bool = Query(False),
    ) -> RedactedJSONResponse:
        groups = await run_blocking(lambda: _store(request).summary(by, include_stub=include_stub, session_id=session_id))
        return respond(request, UsageSummary(groups=[UsageGroupOut(**g) for g in groups]))

    return router


router = build_router()
