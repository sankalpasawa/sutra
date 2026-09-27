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
import org2_apply  # noqa: E402
import proposals  # noqa: E402
import website_dept as W  # noqa: E402

router = APIRouter(prefix="/api/native", tags=["native"])

ROOT_PURPOSE = ("Makes, changes and ends this organisation's departments from the Library's templates; "
                "its authority ends at the owner")
ROOT_RULES = [{"tag": "ask", "line": "A new department is stamped by the owner"},
              {"tag": "always", "line": "A child's rules can only tighten this one's"}]
TEMPLATE = "product-build"          # the Library's use-case template for a department that builds a product


def _apply(kind, args, summary):
    """File the request as a proposal and apply it on the owner's command."""
    rec = proposals.create(kind, args, summary)
    rec = proposals.decide(rec["id"], True, apply_fn=org2_apply.apply_request)
    if rec.get("status") != "approved":
        raise HTTPException(400, detail=str((rec.get("result") or {}).get("error") or rec.get("status")))
    return rec["result"]


def _child(domains, parent, name):
    for ref, d in E.live_refs(domains).items():
        if d.get("parent_ref") == parent and (d.get("name") or "").lower() == name.lower():
            return ref
    return None


def _ensure(parent, name, summary):
    ref = _child(E.load_domains(), parent, name)
    if ref:
        return ref, False
    out = _apply("org.create", {"parent": parent, "name": name}, summary)
    return out["ref"], True


def _charter(ref, purpose, done, rules, summary):
    return _apply("org.charter", {"ref": ref, "purpose": purpose, "done_when": done, "rules": rules}, summary)


@router.get("/ping")
def ping():
    return {"ok": True, "motor": W._read(W.home() / "motor.json", {})}


@router.get("/depts")
def depts():
    return {"depts": [{"ref": d["ref"], "name": d["name"], "stopped": d.get("stopped")} for d in W.list_depts()]}


@router.post("/found")
async def found(request: Request):
    """A new organisation with its root department, and under the root a website
    department with the Library's templates picked, waiting for its goal."""
    body: Dict[str, Any] = await request.json()
    org_name = " ".join(str(body.get("org") or "").split())[:80]
    dept_name = " ".join(str(body.get("dept") or "Website").split())[:80]
    owner = " ".join(str(body.get("owner") or "the owner").split())[:80]
    if not org_name:
        raise HTTPException(400, detail="name the organisation")
    roots = E.active_roots(E.load_domains())
    if not roots:
        raise HTTPException(400, detail="the registry has no root")
    org, org_new = _ensure(roots[0], org_name, "Found %s as a new organisation" % org_name)
    if org_new:
        _charter(org, "%s, as one organisation run on Sutra" % org_name, [], [], "Write %s's charter" % org_name)
    root, root_new = _ensure(org, "Root", "Give %s its root department" % org_name)
    if root_new:
        _charter(root, ROOT_PURPOSE, [], ROOT_RULES, "Write the root department's charter")
    ref, new = _ensure(root, dept_name, "The root department spins out %s" % dept_name)
    if new or not W.dept(ref):
        _charter(ref, "A live website for %s" % org_name, ["Every page checked and live"], W.RULES,
                 "Write %s's charter" % dept_name)
        picks = {}
        for fn in ("identity", "adaptation", "priority", "coordination", "audit"):
            tid = "%s/%s" % (fn, TEMPLATE)
            _apply("org.template", {"ref": ref, "function": fn, "template": tid}, "%s runs the %s template" % (fn.title(), TEMPLATE))
            picks[fn] = tid
        d, _ = W.create(ref, "%s %s" % (org_name, dept_name), None, owner=owner, parent=root)
        d["templates"] = picks
        d["org"] = {"ref": org, "name": org_name}
        d["root"] = root
        W.save_dept(ref, d)
    return {"org": org, "root": root, "ref": ref, "created": bool(new)}


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
    text, _ = await _text(request)
    try:
        rq, row = W.owner_ask(ref, text)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    return {"ok": True, "request": rq, "brief": row}


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
    name = next((a for a in W.ARTIFACTS if W.slug(a) == body.get("slug")), None)
    try:
        return W.put_back(ref, name or "", int(body.get("v") or 0))
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
    name = next((a for a in W.ARTIFACTS if W.slug(a) == slug), None)
    if not name:
        raise HTTPException(404, detail="no such artifact")
    return {"name": name, "slug": slug, "versions": list(reversed(W.versions(ref, name)))}


@router.get("/{ref}/trace/{slug}/{v}")
def trace(ref: str, slug: str, v: int):
    _need(ref)
    name = next((a for a in W.ARTIFACTS if W.slug(a) == slug), None)
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
    name = next((a for a in W.ARTIFACTS if W.slug(a) == slug), None)
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
