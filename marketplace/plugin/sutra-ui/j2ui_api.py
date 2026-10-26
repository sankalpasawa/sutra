"""j2ui_api.py -- the routes the J2 page calls, under /j2ui/{ref}/ (UI port, step C5).

The page is the J2 prototype's own, served at /j2ui/{ref}/ (j2ui_page, the shell's); after its one substitution it calls
relative URLs, so every endpoint it uses lives here, under the same base, for one department:

    GET   api/state api/runs api/map api/board api/artifacts api/artifact api/docs api/audits api/refs api/preview api/call
          site/{key}[/{path}] file/{name} shot/{n}
    POST  api/say api/reset api/output api/playbooks/clear api/lessons/clear

{ref} must be a runtime-2 department of kind website (j2ui_common.need); anything else is 404 {"error": "no such department"}
on every route. This module owns the state, runs and say routes; the rest are answered by the other packages' modules
(j2ui_work, j2ui_audit, j2ui_map, j2ui_board, j2ui_artifacts, j2ui_site), imported when a request needs them: a module that is
not there, or fails, answers the page's own empty shape, because a wrong shape blanks the page.

Every JSON body passes j2ui_common.clean (no private key, no path of this machine) and is sent no-store. Everything a model or an
engine wrote (a built site, an artifact, a preview) is sent with website_api.SAFE, here, so that does not depend on a delegate
remembering: the page's preview frames carry no sandbox of their own, and a built site that ran same-origin could read the panel's token.
"""
import importlib

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

import website_api
import j2ui_common as C
import j2ui_say as SAY
import j2ui_state as S

router = APIRouter(prefix="/j2ui", tags=["j2ui"])
NOSTORE = {"Cache-Control": "no-store"}
NO_DEPARTMENT = {"error": "no such department"}
NOT_FOUND = "not found"


def _mod(name):
    """An adapter module of another package, or None when it is not there (or does not even import)."""
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 -- a module that cannot be imported answers like one that is not there
        return None


def _json(body, status=200):
    return JSONResponse(C.clean(body), status_code=status, headers=NOSTORE)


def _reply(pair):
    """A (status, body) of j2ui_say as the response."""
    return _json(pair[1], pair[0])


def _text(body=NOT_FOUND, status=404):
    """A body the page's server would send as text (not found), with the headers everything served here carries."""
    return Response(body, status_code=status, media_type="text/plain", headers=dict(website_api.SAFE))


def _served(got):
    """A delegate's (status, body, mime, headers) as a response that carries website_api.SAFE whatever the delegate sent."""
    try:
        status, body, mime, headers = got
        return Response(body, status_code=int(status), media_type=mime, headers=dict(headers or {}, **website_api.SAFE))
    except Exception:  # noqa: BLE001 -- a malformed answer is a file that is not there
        return _text()


def _ctx(ref):
    """The department's read, or None when the J2 view is not for it."""
    try:
        C.need(ref)
    except C.NotJ2:
        return None
    return C.get_ctx(ref)


def _build(ctx, name, fn, kind, empty, *args):
    """What another package's module builds for a route: its answer when it is of the shape the page reads, else `empty`
    (the page's own empty form), with the reason noted on the read."""
    mod = _mod(name)
    if mod is None or not hasattr(mod, fn):
        return empty
    try:
        got = getattr(mod, fn)(ctx, *args)
    except Exception as exc:  # noqa: BLE001 -- a builder that fails leaves the page its empty shape, never a blank page
        ctx.reasons.append("%s.%s: %s" % (name, fn, type(exc).__name__))
        return empty
    return got if isinstance(got, kind) else empty


def _read(ref, fn):
    """A JSON GET: the department's read handed to `fn`, 404 when the J2 view is not for the department."""
    ctx = _ctx(ref)
    return _json(NO_DEPARTMENT, 404) if ctx is None else _json(fn(ctx))


# ---- the state ----------------------------------------------------------------------------------------------------------------
def _state(ctx, since):
    """api/state for the read: cleaned once per read, the slice of the chat cut per call."""
    base = ctx.memo.get("state_clean")
    if base is None:
        try:
            base = C.clean(S.build_state(ctx, 0))
        except Exception as exc:  # noqa: BLE001
            ctx.reasons.append("state: %s" % type(exc).__name__)
            base = C.EMPTY_STATE()
        ctx.memo["state_clean"] = base
    out = dict(base)
    out["chat"] = base["chat"][since:]
    return out


@router.get("/{ref}/api/state")
def api_state(ref: str, request: Request):
    ctx = _ctx(ref)
    if ctx is None:
        return _json(NO_DEPARTMENT, 404)
    try:
        since = max(0, int(request.query_params.get("since") or 0))
    except ValueError:
        return _json({"error": "bad since"}, 400)
    if not S.is_live_run(ctx, request.query_params.get("run")):
        return _json({"error": "no such run"}, 404)
    return JSONResponse(_state(ctx, since), headers=NOSTORE)


@router.get("/{ref}/api/runs")
def api_runs(ref: str):
    return _read(ref, S.runs)


# ---- what the other packages build ------------------------------------------------------------------------------------------------
@router.get("/{ref}/api/map")
def api_map(ref: str):
    return _read(ref, lambda c: _build(c, "j2ui_map", "build", dict, C.EMPTY_MAP("the map is not built")))


@router.get("/{ref}/api/board")
def api_board(ref: str):
    return _read(ref, lambda c: _build(c, "j2ui_board", "build", dict, C.EMPTY_BOARD()))


@router.get("/{ref}/api/artifacts")
def api_artifacts(ref: str):
    return _read(ref, lambda c: _build(c, "j2ui_artifacts", "listing", dict, C.EMPTY_ARTIFACTS()))


@router.get("/{ref}/api/docs")
def api_docs(ref: str):
    return _read(ref, lambda c: _build(c, "j2ui_work", "docs", dict, C.EMPTY_DOCS()))


@router.get("/{ref}/api/audits")
def api_audits(ref: str):
    return _read(ref, lambda c: _build(c, "j2ui_audit", "audits_condensed", list, []))


@router.get("/{ref}/api/refs")
def api_refs(ref: str):
    return _read(ref, lambda c: _build(c, "j2ui_audit", "refs", dict, C.EMPTY_REFS()))


@router.get("/{ref}/api/preview")
def api_preview(ref: str, request: Request):
    atom = request.query_params.get("atom") or ""
    return _read(ref, lambda c: _build(c, "j2ui_work", "preview", dict, C.EMPTY_PREVIEW(), atom))


@router.get("/{ref}/api/call")
def api_call(ref: str, request: Request):
    ctx = _ctx(ref)
    if ctx is None:
        return _json(NO_DEPARTMENT, 404)
    try:
        cid = int(request.query_params.get("id") or 0)
    except ValueError:
        cid = 0
    got = _build(ctx, "j2ui_work", "call", dict, None, cid)
    return _json({"error": "no such call"}, 404) if got is None else _json(got)


def _safe_name(name):
    """A name the page may ask for: a relative path with no '..', no drive or root, no backslash, no NUL."""
    n = str(name or "")
    return bool(n) and not n.startswith("/") and "\\" not in n and "\x00" not in n and ".." not in n.split("/") and ":" not in n.split("/")[0]


@router.get("/{ref}/api/artifact")
def api_artifact(ref: str, request: Request):
    ctx = _ctx(ref)
    if ctx is None:
        return _json(NO_DEPARTMENT, 404)
    name = request.query_params.get("name")
    if not _safe_name(name):
        return _text()
    got = _build(ctx, "j2ui_artifacts", "served", tuple, None, name)
    if not got or len(got) != 2:
        return _text()
    return Response(got[0], media_type=got[1], headers=dict(website_api.SAFE))


# ---- a built site, and the files the page asks for ----------------------------------------------------------------------------------------
def _site(ref, key, path):
    ctx = _ctx(ref)
    if ctx is None:
        return _json(NO_DEPARTMENT, 404)
    if path and not _safe_name(path):
        return _text()
    got = _build(ctx, "j2ui_site", "site", tuple, None, key, path)
    return _text() if got is None else _served(got)


@router.get("/{ref}/site/{key}")
def api_site(ref: str, key: str):
    return _site(ref, key, "")


@router.get("/{ref}/site/{key}/{path:path}")
def api_site_file(ref: str, key: str, path: str):
    return _site(ref, key, path)


@router.get("/{ref}/file/{name}")
def api_file(ref: str, name: str):
    ctx = _ctx(ref)
    if ctx is None:
        return _json(NO_DEPARTMENT, 404)
    got = _build(ctx, "j2ui_site", "file", tuple, None, name) if _safe_name(name) else None
    return _text() if got is None else _served(got)


@router.get("/{ref}/shot/{n}")
def api_shot(ref: str, n: str):
    ctx = _ctx(ref)
    if ctx is None:
        return _json(NO_DEPARTMENT, 404)
    got = _build(ctx, "j2ui_site", "shot", tuple, None, n) if _safe_name(n) else None
    return _text() if got is None else _served(got)


# ---- the owner's words, and the three that mean nothing -------------------------------------------------------------------------------------------
async def _body(request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 -- a body that is not JSON is an empty one
        return {}
    return body if isinstance(body, dict) else {}


def _known(ref):
    try:
        C.need(ref)
    except C.NotJ2:
        return False
    return True


@router.post("/{ref}/api/say")
async def api_say(ref: str, request: Request):
    body = await _body(request)
    if not _known(ref):
        return _json(NO_DEPARTMENT, 404)
    status, out = await run_in_threadpool(SAY.say_http, ref, str(body.get("text") or ""))
    return _json(out, status)


@router.post("/{ref}/api/reset")
async def api_reset(ref: str):
    return _reply(SAY.reset(ref)) if _known(ref) else _json(NO_DEPARTMENT, 404)


@router.post("/{ref}/api/output")
async def api_output(ref: str, request: Request):
    body = await _body(request)
    return _reply(SAY.output(ref, body)) if _known(ref) else _json(NO_DEPARTMENT, 404)


@router.post("/{ref}/api/playbooks/clear")
async def api_clear_playbooks(ref: str):
    return _reply(SAY.clear(ref, "playbooks")) if _known(ref) else _json(NO_DEPARTMENT, 404)


@router.post("/{ref}/api/lessons/clear")
async def api_clear_lessons(ref: str):
    return _reply(SAY.clear(ref, "lessons")) if _known(ref) else _json(NO_DEPARTMENT, 404)
