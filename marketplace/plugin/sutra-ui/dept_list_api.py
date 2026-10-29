"""dept_list_api.py -- GET /api/native/_departments and POST /api/native/{root}/departments (PRD amendment A5, A5.3.6).

The listing is the cheap read of dept_read (three small files for each department, cached); the POST is the create-or-reuse
decision for any caller, in words: decide, and apply unless the body says not to. Both answer through the interface (dept.listing,
dept.decision), and the body is checked as dept.request, so a body that does not fit is 422 NOT_IN_SCHEMA.

`_departments` cannot be a ref (a ref starts with a letter or a digit), and the app includes this router before the {ref} routes."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import dept_read
import layer_schema as S
import shadow_dept
import website_dept as W
from interface_http import InterfaceRoute

router = APIRouter(route_class=InterfaceRoute)


@router.get("/api/native/_departments")
async def departments(root: str = ""):
    """The departments under a Root (every one without `root`), as dept.listing."""
    return JSONResponse(S.check("dept.listing", {"departments": dept_read.rows(root or None), "root_ref": root or None,
                                                 "as_of": W.now()}))


@router.post("/api/native/{root}/departments")
async def decide_department(root: str, request: Request):
    """Decide whether the words belong to a department of this Root, or to a new one, and apply it (apply: false only previews).
    A create that a rule holds for the owner waits until the body carries confirmed: true."""
    try:
        body = await request.json()
    except ValueError:
        body = None
    S.check("dept.request", body)
    try:
        rd = W.dept(root)
    except ValueError:
        rd = None
    if not rd:
        raise HTTPException(404, "no such Root")
    if rd.get("kind") != "root":
        raise HTTPException(409, "not a Root")
    mission = None
    if body.get("mission_id"):
        import mission_engine
        mission = mission_engine.MissionStore().load(body["mission_id"])
    decision = await shadow_dept.decide_and_apply(mission, words=body["words"], root_ref=root, apply_it=body.get("apply", True),
                                                  confirmed=body.get("confirmed", False))
    return JSONResponse(S.check("dept.decision", decision))
