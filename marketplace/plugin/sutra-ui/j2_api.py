"""Department-scoped HTTP boundary for the J2 lifecycle."""
from fastapi import APIRouter, HTTPException

import j2_runtime as J


router = APIRouter(prefix="/api/dept", tags=["j2"])


def _call(fn, *args):
    try:
        return fn(*args)
    except J.J2Error as exc:
        code = str(exc).split(":", 1)[0]
        status = 404 if code == "NO_DEPARTMENT" else 409
        raise HTTPException(status_code=status, detail={"code": code}) from exc


@router.get("/{ref}/j2")
def j2_status(ref: str):
    return _call(J.status, ref)


@router.get("/{ref}/j2/events")
def j2_events(ref: str, after: int = 0):
    _call(J.status, ref)
    rows = J.activity(ref)
    cursor = max(0, int(after or 0))
    return {"events": rows[cursor:], "cursor": len(rows)}


@router.post("/{ref}/j2/start")
def j2_start(ref: str):
    return _call(J.start, ref)


@router.post("/{ref}/j2/stop")
def j2_stop(ref: str):
    return _call(J.stop, ref)
