"""The limits routes (gap package routines-limits; docs/notes/GAP2-routines-limits.md). Reads need no token; every write depends on `require_token`.

    GET  /api/limits            -> {spend, guard}
                                   spend {limit, spent, pct, level none|ok|warn|over, line, unpriced_calls, month, month_ends_at}
                                   guard {enabled, level none|ok|warn|hold, holding, line, top, windows}
    PUT  /api/limits            {monthly_usd?: number|null, guard_enabled?: bool} -> {spend, guard}
                                (0 or null clears the limit; a negative or non-finite number, or more than 100000, is a 422; raising a limit
                                or switching the guard off starts the tasks that waited for it)
    POST /api/limits/continue   -> {spend, guard}   (one Continue: work proceeds until the windows that hold it reset; nothing to continue is not an error)

A held task is not an error and not a route: it stays queued with the reason as its waiting detail (limits.py). The router reads
`request.app.state.services.limits` (a `Limits`) and `.tasks`.
"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.limits import MAX_LIMIT_USD, Limits

__all__ = ["router", "build_router", "LimitsPatch"]


class LimitsPatch(BaseModel):
    """The body of `PUT /api/limits`. Closed. A key that is not sent is kept; `monthly_usd` sent as null (or 0) clears the limit."""

    model_config = ConfigDict(extra="forbid", strict=True)
    monthly_usd: float | None = Field(None, ge=0, le=MAX_LIMIT_USD, allow_inf_nan=False)
    guard_enabled: bool | None = None

    @model_validator(mode="after")
    def _something_changes(self) -> "LimitsPatch":
        if not self.model_fields_set & {"monthly_usd", "guard_enabled"}:
            raise ValueError("send monthly_usd or guard_enabled")
        if self.guard_enabled is None and "guard_enabled" in self.model_fields_set:
            raise ValueError("guard_enabled is true or false")
        return self


def _service(request: Request) -> Limits:
    found = getattr(services_of(request), "limits", None)
    if found is None:
        raise AppError("internal", "the limits are not wired")
    return found


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


async def _start_waiting(request: Request) -> None:
    """A limit may just have lifted: start what waited for it (the one place that decides is `start_ready`)."""
    tasks = getattr(services_of(request), "tasks", None)
    if tasks is not None:
        await tasks.start_ready()


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["limits"])

    @router.get("/limits", summary="The monthly spending limit and the plan-window guard, as they stand")
    async def get_limits(request: Request) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_service(request).state))

    @router.put("/limits", summary="Set the monthly limit or the guard switch", dependencies=[Depends(require_token)])
    async def put_limits(request: Request, body: LimitsPatch) -> RedactedJSONResponse:
        service = _service(request)
        sent = body.model_fields_set
        state = await run_blocking(lambda: service.update(
            monthly_usd=body.monthly_usd if "monthly_usd" in sent else "keep", guard_enabled=body.guard_enabled if "guard_enabled" in sent else None))
        await _start_waiting(request)
        return _json(request, state)

    @router.post("/limits/continue", summary="Let work proceed until the plan window that holds it resets", dependencies=[Depends(require_token)])
    async def post_continue(request: Request) -> RedactedJSONResponse:
        state = await run_blocking(_service(request).continue_now)
        await _start_waiting(request)
        return _json(request, state)

    return router


router = build_router()
