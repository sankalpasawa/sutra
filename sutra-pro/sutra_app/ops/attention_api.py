"""The owner's quiet hours and hourly cap (gap package routines-limits; docs/notes/GAP2-routines-limits.md). A read is open on loopback; the write needs the token.

    GET /api/ops/attention    -> {quiet_hours: {start, end} | null, nudges_per_hour, default_nudges_per_hour, max_nudges_per_hour, quiet_now}
    PUT /api/ops/attention    {quiet_hours?: {start, end} | null, nudges_per_hour?: int} -> the same answer
                              (null clears the window; start == end, a time that is not HH:MM and a boolean rate are 422; a rate past the
                              ceiling is stopped at it, like a stepper)

`quiet_now` is the server's reading at this moment; the page keeps its own twin of the rule because it cannot ask on every ping
(sutra_app/ops/attention_prefs.py). The router is mounted by `create_app` with the orchestrator's (main.ROUTERS).
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sutra_app.library.types import violation
from sutra_app.ops.attention_prefs import (
    ATTENTION_FILE, DEFAULT_NUDGES_PER_HOUR, MAX_NUDGES_PER_HOUR, AttentionPrefs, UNSET, clamp_nudges, clean_quiet_hours, window_active,
)
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import validation_error

__all__ = ["router", "build_router", "AttentionPatch"]


class AttentionPatch(BaseModel):
    """The body of `PUT /api/ops/attention`. Closed. A key that is not sent is kept; `quiet_hours` sent as null clears the window."""

    model_config = ConfigDict(extra="forbid", strict=True)
    quiet_hours: dict[str, Any] | None = None
    nudges_per_hour: int | None = Field(None, ge=-1_000_000, le=1_000_000)           # out-of-range numbers are clamped by clamp_nudges, not refused

    @model_validator(mode="after")
    def _something_changes(self) -> "AttentionPatch":
        sent = self.model_fields_set
        if not sent & {"quiet_hours", "nudges_per_hour"}:
            raise ValueError("send quiet_hours or nudges_per_hour")
        if "nudges_per_hour" in sent and self.nudges_per_hour is None:
            raise ValueError("nudges_per_hour is a whole number from 0 to 10")
        return self


def _prefs(request: Request) -> AttentionPrefs:
    return AttentionPrefs(services_of(request).settings.data_dir / ATTENTION_FILE)


def _answer(request: Request) -> dict[str, Any]:
    services = services_of(request)
    found = AttentionPrefs(services.settings.data_dir / ATTENTION_FILE).read()
    now = datetime.fromtimestamp(services.clock.now())                                  # the owner's own clock, local time
    return {**found, "default_nudges_per_hour": DEFAULT_NUDGES_PER_HOUR, "max_nudges_per_hour": MAX_NUDGES_PER_HOUR,
            "quiet_now": window_active(found["quiet_hours"], now)}


def _json(request: Request, data: Any) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/ops", tags=["ops"])

    @router.get("/attention", summary="Quiet hours and the hourly cap for desktop notices")
    async def get_attention(request: Request) -> RedactedJSONResponse:
        return _json(request, await run_blocking(_answer, request))

    @router.put("/attention", summary="Set quiet hours or the hourly cap", dependencies=[Depends(require_token)])
    async def put_attention(request: Request, body: AttentionPatch) -> RedactedJSONResponse:
        sent = body.model_fields_set
        changes: dict[str, Any] = {}
        try:
            if "quiet_hours" in sent:
                changes["quiet_hours"] = None if body.quiet_hours is None else clean_quiet_hours(body.quiet_hours)
        except ValueError as exc:
            raise validation_error([violation("quiet_hours", "invalid", str(exc))], str(exc)) from None
        try:
            if "nudges_per_hour" in sent:
                changes["nudges_per_hour"] = clamp_nudges(body.nudges_per_hour)
        except ValueError as exc:
            raise validation_error([violation("nudges_per_hour", "invalid", str(exc))], str(exc)) from None
        prefs = _prefs(request)
        await run_blocking(lambda: prefs.write(quiet_hours=changes.get("quiet_hours", UNSET), nudges_per_hour=changes.get("nudges_per_hour", UNSET)))
        return _json(request, await run_blocking(_answer, request))

    return router


router = build_router()
