"""Task and run routes (orchestrator 6.2). Reads need no token; every POST depends on `require_token`.

    POST /api/tasks                  {dept_id, text, scope_id?, title?, settings?, follows?} -> 201 TaskOut  (no chat agent: the follow-up path;
                                     `settings` holds only the seven allowed J2_* keys, `follows` names a task of the same department)
    GET  /api/tasks?dept_id=&status= -> TaskOut[]   (newest first; limit 1..500, default 50)
    GET  /api/tasks/{id}             -> TaskOut     (404)
    GET  /api/runs/{run_id}          -> RunRef      (404)
    POST /api/tasks/{id}/stop        -> 200 TaskOut (the stop ladder; 409 `busy` when the task has ended)
    PUT  /api/tasks/{id}/choice      {provider, model?, effort?} -> {task_id, own}   (the run's pick for the agents that have none of their own, D131; a null
                                     provider clears it; checked like a chat's pill; 409 `busy` for a task that has ended)
    POST /api/tasks/{id}/retry       -> 201 TaskOut (a new task, `parent_task_id` = id; it starts fresh, never seeded; 409 unless the task
                                     stopped, crashed or was cancelled)

The router reads `request.app.state.services.tasks` (a `TaskService`).
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from sutra_app.connectors.errors import ConnectorError
from sutra_app.connectors.models import Pick
from sutra_app.orchestrator.agent_sessions import pick_dict
from sutra_app.orchestrator.api.chat_v2 import ChoiceIn
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.models import TASK_STATUSES
from sutra_app.orchestrator.tasks import TaskService

__all__ = ["router", "build_router", "TaskIn", "ID_PATTERN"]

ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,120}$"       # every id in a URL (design 6.1)
TASK_ID_PATTERN = r"^tsk_[0-9a-f]{12}$"


class TaskIn(BaseModel):
    """The body of `POST /api/tasks`. Closed: another key is a 422. `settings` is checked by the service (the seven keys)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    dept_id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=100_000)
    scope_id: str | None = Field(None, min_length=1, max_length=60)
    title: str | None = Field(None, min_length=1, max_length=200)
    settings: dict[str, Any] | None = None
    follows: str | None = Field(None, pattern=TASK_ID_PATTERN)


def _service(request: Request) -> TaskService:
    found = getattr(services_of(request), "tasks", None)
    if found is None:
        raise AppError("internal", "the task service is not wired")
    return found


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["tasks"])

    @router.post("/tasks", summary="Give a team a task", dependencies=[Depends(require_token)], status_code=201)
    async def post_task(request: Request, body: TaskIn) -> RedactedJSONResponse:
        service = _service(request)
        text = body.text.strip()

        def create() -> str:
            with service.db.tx() as tx:
                created = service.create(tx, dept_id=body.dept_id, text=text, title=body.title, scope_id=body.scope_id,
                                         follows=body.follows, settings=body.settings)
                return created.id

        task_id = await run_blocking(create)
        await service.start_ready()
        return _json(request, _dump(await run_blocking(service.store.get, task_id)), 201)

    @router.get("/tasks", summary="Tasks, newest first")
    async def list_tasks(
        request: Request,
        dept_id: str | None = Query(None, pattern=ID_PATTERN),
        status: Literal[TASK_STATUSES] | None = Query(None),                                  # type: ignore[valid-type]
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0, le=2**53 - 1),
    ) -> RedactedJSONResponse:
        found = await run_blocking(lambda: _service(request).store.listing(dept_id=dept_id, status=status, limit=limit, offset=offset))
        return _json(request, [_dump(task) for task in found])

    @router.get("/tasks/{task_id}", summary="One task")
    async def get_task(request: Request, task_id: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await run_blocking(_service(request).store.get, task_id)))

    @router.get("/runs/{run_id}", summary="Where a run lives")
    async def get_run(request: Request, run_id: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        found = await run_blocking(_service(request).store.run_ref, run_id)
        if found is None:
            raise NotFound("that run")
        return _json(request, _dump(found))

    @router.post("/tasks/{task_id}/stop", summary="Stop a task", dependencies=[Depends(require_token)])
    async def stop_task(request: Request, task_id: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await _service(request).stop(task_id)))

    @router.put("/tasks/{task_id}/choice", summary="Choose the model for the agents of this run", dependencies=[Depends(require_token)])
    async def choose_for_run(request: Request, body: ChoiceIn, task_id: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        service = _service(request)
        port = getattr(services_of(request), "chat_port", None)
        if port is None:
            raise AppError("internal", "the chat port is not wired")

        def run() -> Pick:
            row = service.store.row(task_id)
            if not row.live:
                raise AppError("busy", "That run is over. Its choice can no longer change.")
            port.check_choice(body.provider, body.model, body.effort)
            with service.db.tx() as tx:
                pick = service.store.set_pick(tx, task_id, Pick(provider=body.provider or "", model=body.model if body.provider else None,
                                                                effort=body.effort if body.provider else None))
                tx.emit("task.choice", {"task_id": task_id, "run_id": row.run_id, "provider": pick.provider or None, "model": pick.model, "effort": pick.effort})
            service.refresh_choices(task_id=task_id)
            return pick

        try:
            pick = await run_blocking(run)
        except ConnectorError as exc:
            raise AppError("validation", exc.user_message()) from None
        return _json(request, {"task_id": task_id, "own": pick_dict(pick)})

    @router.post("/tasks/{task_id}/retry", summary="Try a task again, fresh", dependencies=[Depends(require_token)], status_code=201)
    async def retry_task(request: Request, task_id: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        return _json(request, _dump(await _service(request).retry(task_id)), 201)

    return router


router = build_router()
