"""website_api.py -- the routes of the website department (website_dept.py).

The read-only department API (dept_api.py) is untouched: this router is the
department's own record and the owner's three controls. Creating the org, its
root department and the website department goes through the app's one door for
structure: each is FILED as a proposal and applied by org2_apply after the
owner's command, the same path the Org screen's pencil uses, so the audit trail
is the one Approvals already shows.
"""
import html
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402
import founding  # noqa: E402
import website_dept as W  # noqa: E402

router = APIRouter(prefix="/api/native", tags=["native"])


@router.get("/ping")
def ping():
    return {"ok": True, "motor": W._read(W.home() / "motor.json", {})}


@router.get("/depts")
def depts():
    return {"depts": [{"ref": d["ref"], "name": d["name"], "stopped": d.get("stopped"), "kind": d.get("kind") or "website",
                       "parent": d.get("parent")} for d in W.list_depts()]}


@router.post("/found")
async def found(request: Request):
    """A new organisation with its one Root, On: a department of the kind root, which spawns every other department
    (founder, 2026-09-28: "root can always spawn off new departments. There will be one root for one organizational
    structure"). Words for the first department, if given, go to Root as its first request; Root asks the owner."""
    body: Dict[str, Any] = await request.json()
    org_name = " ".join(str(body.get("org") or "").split())[:80]
    owner = " ".join(str(body.get("owner") or "the owner").split())[:80]
    first = " ".join(str(body.get("first") or "").split())[:2000]
    if not org_name:
        raise HTTPException(400, detail="name the organisation")
    try:
        out = founding.found_structure(org_name, owner=owner)
        if first:
            rq, _ = W.owner_ask(out["root"], first)
            out["asked"] = rq["id"] if isinstance(rq, dict) else True
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    return out


def _need(ref):
    d = W.dept(ref)
    if not d:
        raise HTTPException(404, detail="no website department here")
    return d


@router.get("/{ref}/map")
def map_(ref: str):
    _need(ref)
    return W.map_view(ref)


@router.get("/{ref}/status")
def status(ref: str):
    _need(ref)
    return W.status(ref)


@router.get("/{ref}/health")
def health(ref: str):
    _need(ref)
    return W.health(ref)


async def _text(request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return " ".join(str((body or {}).get("text") or "").split())[:2000], (body or {})


@router.post("/{ref}/goal")
async def goal(ref: str, request: Request):
    _need(ref)
    text, _ = await _text(request)
    try:
        row = W.give_goal(ref, text)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    return {"ok": True, "brief": row}


@router.post("/{ref}/ask")
async def ask(ref: str, request: Request):
    _need(ref)
    text, body = await _text(request)
    about = str(body.get("about") or "").strip() or None
    try:
        rq, row = W.owner_ask(ref, text, about=about)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    return {"ok": True, "request": rq, "brief": row}


@router.get("/{ref}/chat")
def chat(ref: str, about: str = "", fn: str = ""):
    """The one chat with Root: whole on a Root, scoped on a department (or to `about`); with `fn`, one function's own
    chat from the record, which exists from birth and is never started (founder, 2026-09-29)."""
    _need(ref)
    rt = W._runtime(ref)
    if not rt:
        return {"root": None, "about": None, "turns": [], "asks": [], "departments": []}
    if fn:
        try:
            return rt.fn_chat_view(ref, fn)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc))
    return rt.chat_view(ref, about=about or None)


@router.post("/{ref}/asks/{aid}")
async def decide(ref: str, aid: str, request: Request):
    _need(ref)
    _, body = await _text(request)
    try:
        return W.decide_ask(ref, aid, bool(body.get("approve")))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))


@router.post("/{ref}/stop")
def stop(ref: str):
    _need(ref)
    return W.set_stopped(ref, True)


@router.post("/{ref}/resume")
def resume(ref: str):
    _need(ref)
    return W.set_stopped(ref, False)


@router.post("/{ref}/putback")
async def putback(ref: str, request: Request):
    _need(ref)
    _, body = await _text(request)
    name = next((a for a in W.artifacts_of(W.dept(ref)) if W.slug(a) == body.get("slug")), None)
    try:
        return W.put_back(ref, name or "", int(body.get("v") or 0))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))


@router.post("/{ref}/envelope")
async def envelope(ref: str, request: Request):
    """The owner's own limits for one engine, from Priority's card."""
    _need(ref)
    _, body = await _text(request)
    try:
        calls = body.get("calls")
        usd = body.get("usd")
        return {"ok": True, "envelope": W.set_envelope(ref, str(body.get("engine") or ""),
                                                      None if calls in (None, "") else int(calls),
                                                      None if usd in (None, "") else float(usd))}
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, detail=str(exc))


@router.post("/{ref}/ladder")
async def ladder(ref: str, request: Request):
    """One engine's own ladder numbers, from its Settings tab."""
    rt = _rt(ref)
    _, body = await _text(request)
    nums = {k: body[k] for k in ("runs", "differing", "trial", "misses") if body.get(k) not in (None, "")}
    try:
        return {"ok": True, "numbers": rt.set_numbers(ref, str(body.get("engine") or ""), nums)}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))


@router.post("/{ref}/host")
async def host(ref: str, request: Request):
    """Where the site is served from: the owner's answer to the question the first publish asks."""
    _need(ref)
    text, body = await _text(request)
    try:
        return {"ok": True, "host": W.set_host(ref, body.get("host") or text)}
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))


@router.get("/{ref}/engine/{name}")
def engine(ref: str, name: str):
    _need(ref)
    e = W.engine_view(ref, name)
    if not e:
        raise HTTPException(404, detail="no such engine")
    return e


def _rt(ref):
    """The engine runtime's reads, for a department that runs on it (engine_runtime.py); 404 for every other."""
    _need(ref)
    rt = W._runtime(ref)
    if not rt:
        raise HTTPException(404, detail="this department does not run on the engine runtime")
    return rt


@router.get("/{ref}/steps/{name}")
def steps(ref: str, name: str):
    """An engine or a function as its steps: the rung each runs on, its check, and what its rows say."""
    v = _rt(ref).steps_view(ref, name)
    if not v:
        raise HTTPException(404, detail="no such engine")
    return v


@router.get("/{ref}/board")
def board(ref: str):
    """The department's one board: every thread, every post, and the ideas that are parked."""
    rt = _rt(ref)
    out = rt.board_view(ref)
    out["ideas"] = list(reversed(rt.ideas(ref)))[:20]
    return out


@router.post("/{ref}/hold")
async def hold(ref: str, request: Request):
    """The owner pins a step on its rung, or lets it go."""
    rt = _rt(ref)
    _, body = await _text(request)
    try:
        return rt.hold(ref, str(body.get("step") or ""), bool(body.get("held", True)))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))


@router.get("/{ref}/artifact/{slug}")
def artifact(ref: str, slug: str):
    _need(ref)
    name = next((a for a in W.artifacts_of(W.dept(ref)) if W.slug(a) == slug), None)
    if not name:
        raise HTTPException(404, detail="no such artifact")
    import artifacts
    return {"name": name, "slug": slug, "versions": list(reversed(W.versions(ref, name))), "template": artifacts.view(name)}


@router.get("/{ref}/trace/{slug}/{v}")
def trace(ref: str, slug: str, v: int):
    _need(ref)
    name = next((a for a in W.artifacts_of(W.dept(ref)) if W.slug(a) == slug), None)
    if not name:
        raise HTTPException(404, detail="no such artifact")
    return {"chain": W.trace(ref, name, v)}


#: What the department made is shown, never run: no script, no form, no frame
#: of its own, and an opaque origin, so a page a model wrote can never read the
#: panel it is previewed in.
SAFE = {"Content-Security-Policy": "sandbox; script-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}


def _page(title, body):
    return HTMLResponse(headers=SAFE, content="<!doctype html><meta charset=utf-8><title>%s</title><style>body{font:15px/1.6 system-ui;margin:24px;color:#1c1a17}"
                        "table{border-collapse:collapse}td,th{border:1px solid #e2e0dd;padding:6px 10px;text-align:left}"
                        "pre{white-space:pre-wrap}</style>%s" % (html.escape(title), body))


@router.get("/{ref}/preview/{slug}/{v}/{path:path}")
def preview(ref: str, slug: str, v: int, path: str = "index.html"):
    """Anything made, seen as itself: a page rendered, a plan as a table, a brief as text."""
    d = _need(ref)
    name = next((a for a in W.artifacts_of(W.dept(ref)) if W.slug(a) == slug), None)
    if not name or not any(r["v"] == v for r in W.versions(ref, name)):
        raise HTTPException(404, detail="no such version")
    files = W.read_files(ref, name, v)
    if name == "Brief":
        return _page("Brief v%d" % v, "<pre>%s</pre>" % html.escape(files.get("brief.md", "")))
    if name == "Site plan":
        plan = json.loads(files.get("site-plan.json", "{}"))
        rows = "".join("<tr><td><b>%s</b></td><td>%s</td><td>%s</td></tr>" % (html.escape(p.get("title", "")), html.escape(p.get("slug", "")),
                                                                       html.escape(p.get("purpose", ""))) for p in plan.get("pages", []))
        return _page("Site plan v%d" % v, "<h2>%s</h2><p>%s</p><table><tr><th>Page</th><th>Address</th><th>Purpose</th></tr>%s</table>"
                     % (html.escape(plan.get("site_name", "")), html.escape(plan.get("tagline", "")), rows))
    if name == "Pages":
        files, _, _ = W.engine_check(ref, d, {"v": v})
    target = path or "index.html"
    if target not in files:
        raise HTTPException(404, detail="no such file in this version")
    media = "text/css" if target.endswith(".css") else "text/html"
    return Response(files[target], media_type=media, headers=SAFE)


@router.get("/{ref}/site/{path:path}")
def site(ref: str, path: str = "index.html"):
    _need(ref)
    base = W.live_dir(ref).resolve()
    target = (base / (path or "index.html")).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(404, detail="not on the live site")
    return FileResponse(str(target), headers=SAFE)
