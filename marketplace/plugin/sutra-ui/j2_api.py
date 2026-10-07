"""Department-scoped HTTP boundary for the J2 lifecycle."""
from fastapi import APIRouter, HTTPException, Request

import j2_runtime as J


router = APIRouter(tags=["j2"])
#: The screen reads /api/dept/{ref}/j2; the J2 PRD names /api/departments/{ref}/j2. Both are the same routes.
PREFIXES = ("/api/dept", "/api/departments")


def _routes(method, tail):
    def wrap(fn):
        for prefix in PREFIXES:
            getattr(router, method)(prefix + "/{ref}" + tail)(fn)
        return fn
    return wrap


def _call(fn, *args):
    try:
        return fn(*args)
    except J.J2Error as exc:
        code = str(exc).split(":", 1)[0]
        status = 404 if code == "NO_DEPARTMENT" else 400 if code == "EMPTY_ANSWER" else 409
        raise HTTPException(status_code=status, detail={"code": code}) from exc


@_routes("get", "/j2")
def j2_status(ref: str):
    return _call(J.status, ref)


@_routes("get", "/j2/events")
def j2_events(ref: str, after: int = 0):
    _call(J.status, ref)
    rows = J.activity(ref)
    cursor = max(0, int(after or 0))
    return {"events": rows[cursor:], "cursor": len(rows)}


@_routes("post", "/j2/start")
def j2_start(ref: str):
    return _call(J.start, ref)


@_routes("post", "/j2/stop")
def j2_stop(ref: str):
    return _call(J.stop, ref)


@_routes("post", "/j2/resume")
def j2_resume(ref: str):
    _call(J.status, ref)
    return _call(J.resume, ref) or _call(J.status, ref)


async def _text(request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return str((body or {}).get("text") or "")


@_routes("post", "/j2/answer")
async def j2_answer(ref: str, request: Request):
    """The owner's words for Identity's open question; accepted once."""
    return _call(J.answer, ref, await _text(request))


@_routes("post", "/asks/{ask_id}/answer")
async def j2_answer_ask(ref: str, ask_id: str, request: Request):
    return _call(J.answer, ref, await _text(request), ask_id)
