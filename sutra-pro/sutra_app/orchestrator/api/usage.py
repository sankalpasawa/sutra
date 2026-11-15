"""Usage routes (orchestrator 6.2). Both are reads, so they need no token.

    GET /api/usage?task_id=&dept_id=&fn=&session_id=&since=&include_stub=&after=&limit=   -> {rows: UsageOut[], totals}
    GET /api/usage/summary?by=dept|fn|provider|day|atom|session|purpose&session_id=&since=&include_stub=   -> {groups: [{key, calls, usd, tokens_in, tokens_out}]}

`totals` cover every matching row, not just the page (`limit` default 50, max 500; `after` is a row id). `since` is epoch
seconds or an ISO time like 2026-11-04T10:00:06Z; on the summary it is the window of every grouping (the rows at or after it). Stub rows are
left out of rows, totals and groups unless `include_stub=1`. The groups are in key order and hold at most 500 keys; a call without a value for
the key is the group `(none)`.

`by=purpose` is what the calls were for, the ledger's own open word: `agent_turn` (an agent's work), `plan` and `judge` (the late judge, D145),
`agent_chat` (a function's answer to a question in its chat, D147), `change`, `summary`, `template`, `review`, `chat`, `chat_plan` (the chat
agent) and `connector_test`; a purpose this list does not know is a group like any other (D159). A group's `usd` is null when none of its rows
has a price (Codex reports tokens only), as in every other grouping.
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


def _floor(since: str | None) -> int | None:
    """`since` as epoch seconds, None when it was not given; a time that is none is a 422 naming `query.since`."""
    try:
        return parse_since(since) if since is not None else None
    except ValueError as exc:
        raise validation_error([violation("query.since", "bad_time", str(exc))]) from None


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
        floor = _floor(since)
        rows, totals = await run_blocking(lambda: _store(request).rows(
            task_id=task_id, dept_id=dept_id, fn=fn, since=floor, include_stub=include_stub, after=after, limit=limit, session_id=session_id))
        return respond(request, UsageList(rows=rows, totals=totals))

    @router.get("/summary", summary="Usage grouped by department, function, provider, day, atom, chat session or purpose")
    async def get_summary(
        request: Request,
        by: Literal["dept", "fn", "provider", "day", "atom", "session", "purpose"] = Query("dept"),
        session_id: str | None = Query(None, pattern=ID_PATTERN),
        since: str | None = Query(None, max_length=40, description="epoch seconds or 2026-11-04T10:00:06Z"),
        include_stub: bool = Query(False),
    ) -> RedactedJSONResponse:
        floor = _floor(since)
        groups = await run_blocking(lambda: _store(request).summary(by, include_stub=include_stub, session_id=session_id, since=floor))
        return respond(request, UsageSummary(groups=[UsageGroupOut(**g) for g in groups]))

    return router


router = build_router()
