"""shadow_dept_api.py -- POST /api/shadow/tasks/{mid}/department (PRD amendment A5, A5.3.6).

Decide, and optionally apply, the create-or-reuse decision for a draft or running task, earlier than the start hook would. The body
is dept.request (its mission_id, when given, is the task in the path); the answer is dept.decision. A task has one decision:
asking again returns it, unless it waits on the owner's yes and the body carries confirmed: true."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import layer_schema as S
import mission_engine
import providers
import shadow_dept
from interface_http import InterfaceRoute

router = APIRouter(route_class=InterfaceRoute)


@router.post("/api/shadow/tasks/{mid}/department")
async def task_department(mid: str, request: Request):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    try:
        body = await request.json()
    except ValueError:
        body = None
    S.check("dept.request", body)
    if body.get("mission_id") not in (None, mid):
        raise HTTPException(400, "the body names another task")
    mission = mission_engine.MissionStore().load(mid)
    if mission is None:
        raise HTTPException(404, "no such task")
    decision = await shadow_dept.decide_and_apply(mission, apply_it=body.get("apply", True), confirmed=body.get("confirmed", False))
    return JSONResponse(S.check("dept.decision", decision))
