"""Department-scoped HTTP boundary for the J2 lifecycle."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

import j2_runtime as J
from interface_http import InterfaceRoute


router = APIRouter(tags=["j2"], route_class=InterfaceRoute)
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
def j2_events(ref: str, after: int = 0, after_seq: Optional[int] = None, after_board: Optional[int] = None):
    """The ledger and the board, merged in time. Paged by two cursors, one per source (after_seq for the ledger,
    after_board for the board), so a row written between two reads is never repeated or skipped. `after` is the old
    single cursor, a place in the merged list; it is kept for a screen that still sends it."""
    _call(J.status, ref)
    if after_seq is None and after_board is None:
        page = J.activity_page(ref)
        cursor = max(0, int(after or 0))
        return dict(page, events=page["events"][cursor:], cursor=len(page["events"]))
    page = J.activity_page(ref, after_seq or 0, after_board or 0)
    return dict(page, cursor=None)


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
    """The owner's words for Identity's open question; accepted once. Answers with the cycle as /j2 reads it, so the
    card that sent the words shows what came of them (the next question, or none)."""
    _call(J.answer, ref, await _text(request))
    return _call(J.status, ref)


@_routes("post", "/asks/{ask_id}/answer")
async def j2_answer_ask(ref: str, ask_id: str, request: Request):
    _call(J.answer, ref, await _text(request), ask_id)
    return _call(J.status, ref)
