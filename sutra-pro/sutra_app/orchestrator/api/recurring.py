"""Recurring work routes (gap package routines-limits; docs/notes/GAP2-routines-limits.md). Reads need no token; every write depends on `require_token`.

    GET    /api/recurring                 -> RecurringOut[]   (oldest first: team, words, schedule in words, on or paused and why, the next due time,
                                             the last run, `never_fired_on_schedule`)
    POST   /api/recurring                 {dept_id, text, schedule} -> 201 RecurringOut
    PUT    /api/recurring/{id}            {text?, schedule?, enabled?} -> RecurringOut   (a new cadence, or switching on, starts from now)
    DELETE /api/recurring/{id}            -> {"deleted": id}   (its history goes with it; the tasks it made stay)
    POST   /api/recurring/{id}/run        -> 201 RunOut   (run now: a team that is busy is 409, not skipped quietly)
    GET    /api/recurring/{id}/runs?limit= -> RunOut[]   (newest first; each says started or skipped and why, and how the task ended)

`schedule` is {every: hour|day|weekdays|week, hour, minute, weekday} and nothing else: a free cron line, or a cadence below one an hour,
is a 422 that says why. The router reads `request.app.state.services.recurring` (a `Recurring`).
"""
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from sutra_app.library.types import violations_from_validation_error
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError, validation_error
from sutra_app.orchestrator.recurring import MAX_TEXT, Recurring
from sutra_app.orchestrator.schedule import Schedule

__all__ = ["router", "build_router", "RecurringIn", "RecurringPatch", "REC_ID_PATTERN"]

REC_ID_PATTERN = r"^rec_[0-9a-f]{12}$"


class RecurringIn(BaseModel):
    """The body of `POST /api/recurring`. Closed: another key is a 422. `schedule` is checked by `Schedule` in the route, so a refusal
    carries the sentence that says why."""

    model_config = ConfigDict(extra="forbid", strict=True)
    dept_id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=MAX_TEXT * 2)
    schedule: dict[str, Any]


class RecurringPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str | None = Field(None, max_length=MAX_TEXT * 2)
    schedule: dict[str, Any] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _something_changes(self) -> "RecurringPatch":
        if self.text is None and self.schedule is None and self.enabled is None:
            raise ValueError("send text, schedule or enabled")
        return self


def _service(request: Request) -> Recurring:
    found = getattr(services_of(request), "recurring", None)
    if found is None:
        raise AppError("internal", "the scheduler is not wired")
    return found


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def _schedule(raw: dict[str, Any]) -> Schedule:
    try:
        return Schedule.model_validate(raw)
    except ValidationError as exc:
        found = violations_from_validation_error(exc)
        raise validation_error([v.model_copy(update={"path": f"schedule.{v.path}" if v.path else "schedule"}) for v in found],
                               found[0].message if found else "That schedule is not allowed") from None


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["recurring"])

    @router.get("/recurring", summary="The standing tasks and their schedules")
    async def list_recurring(request: Request) -> RedactedJSONResponse:
        found = await run_blocking(_service(request).listing)
        return _json(request, [r.model_dump(mode="json") for r in found])

    @router.post("/recurring", summary="Give a team a standing task on a schedule", dependencies=[Depends(require_token)], status_code=201)
    async def create_recurring(request: Request, body: RecurringIn) -> RedactedJSONResponse:
        service = _service(request)
        schedule = _schedule(body.schedule)
        made = await run_blocking(lambda: service.create(body.dept_id, body.text, schedule))
        return _json(request, made.model_dump(mode="json"), 201)

    @router.put("/recurring/{rec_id}", summary="Change a standing task", dependencies=[Depends(require_token)])
    async def change_recurring(request: Request, body: RecurringPatch, rec_id: str = Path(pattern=REC_ID_PATTERN)) -> RedactedJSONResponse:
        service = _service(request)
        schedule = _schedule(body.schedule) if body.schedule is not None else None
        made = await run_blocking(lambda: service.update(rec_id, text=body.text, schedule=schedule, enabled=body.enabled))
        return _json(request, made.model_dump(mode="json"))

    @router.delete("/recurring/{rec_id}", summary="Remove a standing task", dependencies=[Depends(require_token)])
    async def delete_recurring(request: Request, rec_id: str = Path(pattern=REC_ID_PATTERN)) -> RedactedJSONResponse:
        await run_blocking(_service(request).delete, rec_id)
        return _json(request, {"deleted": rec_id})

    @router.post("/recurring/{rec_id}/run", summary="Run a standing task now", dependencies=[Depends(require_token)], status_code=201)
    async def run_recurring(request: Request, rec_id: str = Path(pattern=REC_ID_PATTERN)) -> RedactedJSONResponse:
        run = await run_blocking(_service(request).run_now, rec_id)
        await services_of(request).tasks.start_ready()
        return _json(request, run.model_dump(mode="json"), 201)

    @router.get("/recurring/{rec_id}/runs", summary="What each due time came to")
    async def recurring_runs(request: Request, rec_id: str = Path(pattern=REC_ID_PATTERN), limit: int = Query(20, ge=1, le=200)) -> RedactedJSONResponse:
        found = await run_blocking(lambda: _service(request).runs(rec_id, limit))
        return _json(request, [r.model_dump(mode="json") for r in found])

    return router


router = build_router()
