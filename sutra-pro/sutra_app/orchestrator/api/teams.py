"""The owner's projects (named projects, D426): make, rename and delete (hide) a team without a model call. Every route takes the token.

    POST   /api/teams            {name, folder?, access?: "edit"|"read"}  -> 201 {team: DepartmentOut, folder, access}
    PATCH  /api/teams/{dept_id}  {name}                                   -> 200 DepartmentOut
    DELETE /api/teams/{dept_id}                                           -> 200 {"hidden": true}
    GET    /api/teams/last                                                -> {dept}   the project last picked on Attention, "" for Let Sutra choose
    PUT    /api/teams/last       {dept}                                   -> {dept}

A refusal names the field it is about in `details.field` (`name` or `folder`) so the Create project box shows it under that field.
`/api/teams/{dept}/agents` (agent_chats.py) is another route under the same prefix; `/api/projects` belongs to SUTRA_NODES_V1.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from sutra_app.engine.spec import DEPT_ID_RE
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.team_admin import TeamAdmin, team_admin_of

__all__ = ["router", "build_router"]


class TeamIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=2000)                     # the 80-character rule is TeamAdmin's, with the sentence the owner reads
    folder: Optional[str] = Field(None, max_length=1100)
    access: str = Field("edit", max_length=8)


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=2000)


class PickIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dept: str = Field(max_length=40)


def _admin(request: Request) -> TeamAdmin:
    return team_admin_of(services_of(request))


def _json(request: Request, data: Any, status: int = 200) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(status_code=status, content=scrub(data) if callable(scrub) else data)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/teams", tags=["teams"])
    guard = [Depends(require_token)]

    @router.post("", summary="Make a project (a team and its folder)", dependencies=guard)
    async def post_team(request: Request, body: TeamIn) -> RedactedJSONResponse:
        made = await run_blocking(_admin(request).create, body.name, body.folder or None, body.access)
        return _json(request, {"team": made.team.model_dump(mode="json"), "folder": made.folder, "access": made.access}, 201)

    @router.get("/last", summary="The project last picked on Attention (\"\" = Let Sutra choose)")
    async def get_last(request: Request) -> RedactedJSONResponse:
        return _json(request, {"dept": await run_blocking(_admin(request).last_pick)})

    @router.put("/last", summary="Keep the project picked on Attention", dependencies=guard)
    async def put_last(request: Request, body: PickIn) -> RedactedJSONResponse:
        return _json(request, {"dept": await run_blocking(_admin(request).set_last_pick, body.dept)})

    @router.patch("/{dept_id}", summary="Rename a project", dependencies=guard)
    async def patch_team(request: Request, body: RenameIn, dept_id: str = Path(pattern=DEPT_ID_RE)) -> RedactedJSONResponse:
        team = await run_blocking(_admin(request).rename, dept_id, body.name)
        return _json(request, team.model_dump(mode="json"))

    @router.delete("/{dept_id}", summary="Delete (hide) a project; its runs and files stay", dependencies=guard)
    async def delete_team(request: Request, dept_id: str = Path(pattern=DEPT_ID_RE)) -> RedactedJSONResponse:
        await run_blocking(_admin(request).hide, dept_id)
        return _json(request, {"hidden": True})

    return router


router = build_router()
