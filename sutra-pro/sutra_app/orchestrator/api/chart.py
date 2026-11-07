"""Chart routes (orchestrator 6.2): the live chart, its change log, and the two ways to change it by hand.

    GET  /api/chart                                -> ChartView
    GET  /api/chart/changes?after=&limit=&newest=  -> ChartChangeOut[]     (oldest first; `after` is a seq cursor; limit 1..500, default 50;
                                                      `newest=true`: the last `limit` rows, still oldest first, for a page that shows the latest)
    POST /api/chart/changes                        -> a library `chart_change` JSON + `dry_run` (actor `user`; needs the token)
                                                      200 ChangeResult | 202 pending approval | 409 stale_chart | 422 validation / rules
    POST /api/chart/changes/{change_id}/decision   -> {approve: bool}      (needs the token) 200 ChangeResult | 404 | 409 already_decided

The chat agent changes the chart through `ChartStore` directly; these routes serve the UI's reads and a person (or a script) who
wants to change the chart without the agent. The `id` of a posted change is only a proposal: the store gives the row its real id
(`chg-<seq>`), which the answer carries. Reads need no token; every POST depends on `require_token`.
"""
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict

from sutra_app.library.gate import GATE, GateError
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.chart import ChartStore
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, from_gate_error
from sutra_app.orchestrator.models import ChangeContext, ChangeResult

__all__ = ["router", "build_router", "DecisionIn"]

ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"       # every id in a URL (design 6.1)
CHANGE_ID_PATTERN = r"^chg-[0-9]{4,9}$"


class DecisionIn(BaseModel):
    """`{approve: true|false}`, closed: any other key is a 422."""

    model_config = ConfigDict(extra="forbid", strict=True)
    approve: bool


def _store(request: Request) -> ChartStore:
    store = getattr(services_of(request), "chart", None)
    if store is None:
        raise AppError("internal", "the chart store is not wired")
    return store


def _data(request: Request, data: Any) -> Any:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return scrub(data) if callable(scrub) else data


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    return RedactedJSONResponse(status_code=status, content=_data(request, data))


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/chart", tags=["chart"])

    @router.get("", summary="The org chart")
    async def get_chart(request: Request) -> RedactedJSONResponse:
        view = await run_blocking(lambda: _store(request).view())
        return _json(request, _dump(view))

    @router.get("/changes", summary="The change log, oldest first")
    async def get_changes(
        request: Request,
        after: int = Query(0, ge=0, description="return rows with a seq above this"),
        limit: int = Query(50, ge=1, le=500),
        newest: bool = Query(False, description="the last `limit` rows above `after`, still oldest first"),
    ) -> RedactedJSONResponse:
        rows = await run_blocking(lambda: _store(request).history(after, limit, newest=newest))
        return _json(request, [_dump(row) for row in rows])

    @router.post("/changes", summary="Change the chart by hand", dependencies=[Depends(require_token)])
    async def post_change(request: Request, body: dict[str, Any]) -> RedactedJSONResponse:
        payload = dict(body)
        dry_run = payload.pop("dry_run", False)
        if not isinstance(dry_run, bool):
            raise AppError("validation", "dry_run is true or false", {"violations": [{"path": "dry_run", "code": "bool_type", "message": "dry_run is true or false"}]})
        try:
            change = GATE.check("chart_change", payload)
        except GateError as exc:
            raise from_gate_error(exc) from None
        store = _store(request)
        if dry_run:
            result: ChangeResult = await run_blocking(lambda: store.preview(change))
            return _json(request, _dump(result), 202 if result.status == "pending_approval" else 200)
        ctx = ChangeContext(session_id="cs_org", request_id=change.model.task_id[:40])
        result = await run_blocking(lambda: store.apply(change, actor="user", ctx=ctx))
        if result.status == "stale":
            raise AppError("stale_chart", "The chart changed while this was planned. Read it again and send the change again.", {"result": _dump(result)})
        return _json(request, _dump(result), 202 if result.status == "pending_approval" else 200)

    @router.post("/changes/{change_id}/decision", summary="Answer a pending approval", dependencies=[Depends(require_token)])
    async def post_decision(request: Request, body: DecisionIn, change_id: str = Path(pattern=CHANGE_ID_PATTERN)) -> RedactedJSONResponse:
        store = _store(request)
        try:
            result = await run_blocking(lambda: store.decide(change_id, body.approve))
        except AlreadyDecided as exc:
            first = _dump(exc.result) if exc.result is not None else None
            raise AppError("already_decided", "That change was decided already", {"result": first}) from None
        return _json(request, _dump(result))

    return router


router = build_router()
