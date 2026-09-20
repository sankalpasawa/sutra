"""org2_api.py -- read-only aggregates for the new Org screen (19-org2.js).

BUILD-PLAN.md (holding/departments/experience/org) step 36: one call returns a
department's list column and its charter, so the screen makes one round trip
per selection instead of five.

SAFETY (same contract as org_api.py; test_forbidden_calls.py scans this file):
  - Calls ONLY the engine readers: load_domains, live_refs, domain_path,
    charters_for, charter_view, superseded_ids, all_placements. Never a mutator.
  - Writes nothing. No environment mutation. The registry root is whatever the
    engine bound at import (org_api.registry_root() is the same answer).
  - Documents are joined through workspace_api's own helpers (the placement
    rows whose work_ref is a markdown path under the workdir), imported lazily
    so a broken workspace import can never take the department read down.
"""
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402  (path insert must precede this import)

router = APIRouter(prefix="/api/org2", tags=["org2"])

FILED_MAX = 200          # placements returned per department (newest first)
DOCS_MAX = 200
LABEL_MAX = 60
SEARCH_MAX = 200         # departments a search or a filter may return
ONE_LINE_MAX = 60        # a charter purpose shorter than this, with no second sentence, is "one line"
DESKTOP_NAME = "Desktop"  # project_import.DESKTOP_NAME: the machine node under the root
KINDS = ("root", "machine", "organisation", "department")
STATES = ("active", "no-charter", "one-line")
REQUEST_KINDS = ("org.rename", "org.move", "org.create", "org.charter")   # org2_apply.KINDS; pinned here so the route needs no import
PAGE_EXT = (".html", ".htm")

_SEP = re.compile(r"[-_]+")
_EXT = re.compile(r"\.[A-Za-z0-9]{1,6}$")


def _label(work_id: Any) -> str:
    """A NAME for a filed item, never a path (founder: names, not paths).
    A path keeps its last segment, loses its extension and reads dashes and
    underscores as spaces; free text is whitespace-normalised; both are cut
    at LABEL_MAX with an ellipsis."""
    s = str(work_id or "").strip()
    if not s:
        return ""
    if "/" in s and " " not in s:
        seg = s.rstrip("/").rsplit("/", 1)[-1]
        seg = _EXT.sub("", seg)
        s = _SEP.sub(" ", seg).strip() or seg
    s = " ".join(s.split())
    return s if len(s) <= LABEL_MAX else s[:LABEL_MAX - 2].rstrip() + "…"


def _root_ref(live: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """The company root among the live rows: a parent-less row, and when the
    registry holds more than one (the stray root of 2026-09-13), the one with
    the largest live subtree."""
    parentless = [r for r, d in live.items()
                  if not d.get("parent_ref") or d.get("parent_ref") not in live]
    if not parentless:
        return None
    kids: Dict[str, List[str]] = {}
    for r, d in live.items():
        pr = d.get("parent_ref")
        if pr in live:
            kids.setdefault(pr, []).append(r)

    def size(ref: str) -> int:
        n, stack, seen = 0, [ref], set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            n += 1
            stack.extend(kids.get(x, []))
        return n
    return max(parentless, key=lambda r: (size(r), -(live[r].get("ts_minted_ms") or 0)))


def _kind(ref: str, d: Dict[str, Any], live: Dict[str, Dict[str, Any]], root_ref: Optional[str]) -> str:
    """The stored `node_kind` (engine, plan S94) when the row carries one; the
    interim rule (S27) only for rows minted before the field existed and not
    yet backfilled."""
    stored = d.get("node_kind")
    if stored in KINDS:
        return stored
    pr = d.get("parent_ref")
    if not pr or pr not in live:
        return "root"
    if pr == root_ref:
        if d.get("name") == DESKTOP_NAME or d.get("cwd") or "import" in str(d.get("origin") or "").lower():
            return "machine"
        return "organisation"
    return "department"


def _chain(ref: str, domains: Dict[str, Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    seen = set()
    cur: Optional[str] = ref
    while cur and cur in domains and cur not in seen:
        seen.add(cur)
        names.append(domains[cur].get("name") or "")
        cur = domains[cur].get("parent_ref")
    return list(reversed(names))


def _charter_row(v: Dict[str, Any]) -> Dict[str, Any]:
    """What the screen shows of one charter. `done_when`, `rules` and `person`
    are the sidecar fields DS-1/DS-2 added: the charter sheet prefills from
    them, so they ride the read the sheet already makes rather than a second
    round trip. Absent on every charter written before them, hence the [] / ""
    defaults rather than a key that comes back missing."""
    return {"id": v.get("id"), "title": v.get("title"), "purpose": v.get("purpose"),
            "status": v.get("status", "active"), "kind": v.get("kind", "standing"),
            "scope_in": v.get("scope_in") or [],
            "done_when": list(v.get("done_when") or []),
            "rules": [{"tag": str(r.get("tag") or "always"), "line": str(r.get("line") or r.get("text") or "")}
                      for r in (v.get("rules") or []) if isinstance(r, dict)],
            "person": str(v.get("person") or "")}


def _charters(ref: str):
    """(standing charter or None, the other charters) for a department. The
    standing one is the first active, non-superseded charter of kind standing,
    else the first active one; retired and superseded charters list after the
    active ones, so nothing is hidden.

    DS-2 (2026-09-21): a `role` charter is never the standing one -- it speaks
    for a person, not for the department -- but it still LISTS, so nothing is
    hidden from the Org screen either."""
    views = [v for v in (E.charter_view(c) for c in E.charters_for(ref)) if v]
    sup = E.superseded_ids() if hasattr(E, "superseded_ids") else {}
    active = [v for v in views if v.get("status", "active") != "retired" and v.get("id") not in sup
              and str(v.get("kind") or "") != "role"]
    standing = next((v for v in active if v.get("kind", "standing") == "standing"), None)
    if standing is None and active:
        standing = active[0]
    others = [v for v in views if standing is None or v.get("id") != standing.get("id")]
    others.sort(key=lambda v: (v.get("status", "active") != "active",
                               v.get("id") in sup, (v.get("title") or "").lower()))
    return standing, others


def _placements_now():
    """CURRENT placement rows only. all_placements() is the append-only log, so
    after a charter amendment or a re-home the same work would list twice
    (the superseded row and its successor); the engine's current index keeps
    one row per work item."""
    fn = getattr(E, "_current_placements", None)
    try:
        return list(fn()) if callable(fn) else E.all_placements()
    except Exception:
        return E.all_placements()


def _filed(ref: str):
    rows = []
    for p in _placements_now():
        if p.get("domain_ref") != ref:
            continue
        wr = p.get("work_ref") or {}
        rows.append({"id": wr.get("id"), "kind": wr.get("kind"), "label": _label(wr.get("id")),
                     "charter_id": p.get("charter_id"), "ts_ms": p.get("ts_ms") or 0})
    rows.sort(key=lambda r: -(r["ts_ms"] or 0))
    return rows


def _docs_for(ref: str) -> List[Dict[str, Any]]:
    """Markdown documents filed under `ref` that exist on disk, newest first,
    through workspace_api's own join (the same rows its tree shows). Any
    failure returns an empty list: the department read must never depend on
    the workdir being configured."""
    try:
        import workspace_api as W  # noqa: WPS433  (lazy: pulls org_api and the app modules)
        root = W._root()
        out, seen = [], set()
        for p in W._doc_placements(E.all_placements()):
            if p.get("domain_ref") != ref:
                continue
            rel = W._norm_rel(p["work_ref"]["id"], root)
            key = rel.lower()
            if key in seen:
                continue
            seen.add(key)
            target = W._join_resolve(root, rel)
            if target is None or not os.path.isfile(target):
                continue
            out.append({"path": rel, "title": W._doc_title(target, rel),
                        "mtime": int(os.stat(target).st_mtime)})
        out.sort(key=lambda x: -x["mtime"])
        return out[:DOCS_MAX]
    except Exception:
        return []


@router.get("/ping")
def ping():
    return {"ok": True}


@router.get("/department/{ref}")
def department(ref: str):
    """Everything the list column and the charter view need for one department."""
    domains = E.load_domains()
    d = domains.get(ref)
    if not d:
        raise HTTPException(status_code=404, detail="no department %s" % ref)
    live = E.live_refs(domains)
    root_ref = _root_ref(live)
    children = sorted(
        [{"ref": r, "name": x.get("name")} for r, x in live.items() if x.get("parent_ref") == ref],
        key=lambda c: (c["name"] or "").lower())
    standing, others = _charters(ref)
    filed = _filed(ref)
    parent = domains.get(d.get("parent_ref") or "") if d.get("parent_ref") else None
    successors = [{"ref": s, "name": (domains.get(s) or {}).get("name")}
                  for s in (d.get("successor_refs") or [])]
    return {
        "ref": ref,
        "name": d.get("name"),
        "kind": _kind(ref, d, live, root_ref),
        "status": d.get("status", "active"),
        "parent": ({"ref": d.get("parent_ref"), "name": parent.get("name")} if parent else None),
        "address": _chain(ref, domains),
        "children": children,
        "charter": _charter_row(standing) if standing else None,
        "charters": [_charter_row(v) for v in others],
        "filed": filed[:FILED_MAX],
        "filed_n": len(filed),
        "docs": _docs_for(ref),
        "successors": successors,
        "ts_minted_ms": d.get("ts_minted_ms"),
        "retired_at_ms": d.get("retired_at_ms"),
        "retire_reason_code": d.get("retire_reason_code"),
        # plan S52: the registry's history length at this read. The screen keeps
        # the value it loaded the tree with (META.domain_index_lines); a later
        # read that differs means another session changed the tree since.
        "index_lines": len(E._read_jsonl(E.DOMAIN_INDEX)),
    }


def _one_line(v: Optional[Dict[str, Any]]) -> bool:
    p = " ".join(str((v or {}).get("purpose") or "").split())
    return bool(v) and 0 < len(p) < ONE_LINE_MAX and ". " not in p


def _subtree(ref: str, live: Dict[str, Dict[str, Any]]) -> List[str]:
    kids: Dict[str, List[str]] = {}
    for r, d in live.items():
        kids.setdefault(d.get("parent_ref"), []).append(r)
    out, stack, seen = [], [ref], set()
    while stack:
        x = stack.pop()
        if x in seen or x not in live:
            continue
        seen.add(x)
        out.append(x)
        stack.extend(kids.get(x, []))
    return out


def _standing(ref: str):
    try:
        return _charters(ref)[0]
    except Exception:
        return None


def _standing_map() -> Dict[str, Optional[Dict[str, Any]]]:
    """{domain_ref: standing charter view or None} for EVERY department in one
    pass over the charter files (speed unit, 2026-09-15). filter and health
    used to call _standing() per row, and each call re-walked all ~180 charter
    bodies: 76 rows x 180 files. One walk, grouped by domain_ref, then the
    same standing rule as _charters(): first active, non-superseded standing
    charter, else the first active one."""
    sup = E.superseded_ids() if hasattr(E, "superseded_ids") else {}
    by_dom: Dict[str, List[Dict[str, Any]]] = {}
    for fn in E.charter_body_files():
        v = E.charter_view(fn[:-len(".json")])
        if v and v.get("domain_ref"):
            by_dom.setdefault(v["domain_ref"], []).append(v)
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for ref, views in by_dom.items():
        views.sort(key=lambda v: v.get("id") or "")
        active = [v for v in views if v.get("status", "active") != "retired" and v.get("id") not in sup]
        standing = next((v for v in active if v.get("kind", "standing") == "standing"), None)
        out[ref] = standing if standing is not None else (active[0] if active else None)
    return out


@router.get("/filter")
def filter_departments(kind: str = "", state: str = "", where: str = ""):
    """The live departments that match every given axis (plan S76): `kind` and
    `state` are comma lists over KINDS and STATES, `where` narrows to one
    subtree. Refs only: the screen already holds the names. An empty query
    matches everything, so the funnel can be cleared with the same call."""
    kinds = [k for k in kind.split(",") if k]
    states = [s for s in state.split(",") if s]
    bad = [k for k in kinds if k not in KINDS] + [s for s in states if s not in STATES]
    if bad:
        raise HTTPException(status_code=400, detail="unknown filter value %s" % ", ".join(bad))
    domains = E.load_domains()
    live = E.live_refs(domains)
    root_ref = _root_ref(live)
    pool = _subtree(where, live) if where else list(live.keys())
    if where and not pool:
        raise HTTPException(status_code=404, detail="no department %s" % where)
    out = []
    smap = _standing_map() if states else {}
    for r in pool:
        d = live[r]
        if kinds and _kind(r, d, live, root_ref) not in kinds:
            continue
        if states:
            standing = smap.get(r)
            ok = ("active" in states and d.get("status", "active") == "active") \
                or ("no-charter" in states and standing is None) \
                or ("one-line" in states and _one_line(standing))
            if not ok:
                continue
        out.append(r)
        if len(out) >= SEARCH_MAX:
            break
    return {"refs": out, "n": len(out)}


@router.get("/search")
def search(q: str = ""):
    """Departments whose charter title or purpose, filed work or documents
    mention `q` (plan S74). Names are matched on the screen already; they are
    included here too so one answer covers the whole ask."""
    needle = " ".join(q.split()).lower()
    if len(needle) < 2:
        return {"refs": [], "n": 0}
    domains = E.load_domains()
    live = E.live_refs(domains)
    hits: Dict[str, bool] = {}
    for r, d in live.items():
        if needle in str(d.get("name") or "").lower():
            hits[r] = True
    for p in E.all_placements():
        r = p.get("domain_ref")
        if r in live and r not in hits and needle in _label((p.get("work_ref") or {}).get("id")).lower():
            hits[r] = True
    for fn in E.charter_body_files():                     # one pass over the charters, not one per department
        v = E.charter_view(fn[:-len(".json")])
        r = v.get("domain_ref") if v else None
        if r in live and r not in hits and (needle in str(v.get("title") or "").lower()
                                            or needle in str(v.get("purpose") or "").lower()):
            hits[r] = True
    refs = list(hits.keys())[:SEARCH_MAX]
    return {"refs": refs, "n": len(refs)}


@router.get("/health/{ref}")
def health(ref: str):
    """What the Health panel shows for one subtree, as names: departments with
    no standing charter, charters that are one line, and sibling overlaps the
    engine's MECE report finds inside the subtree (plan S84-S86)."""
    domains = E.load_domains()
    live = E.live_refs(domains)
    if ref not in live:
        raise HTTPException(status_code=404, detail="no department %s" % ref)
    refs = _subtree(ref, live)
    inside = set(refs)
    unowned, one_line = [], []
    smap = _standing_map()
    for r in refs:
        standing = smap.get(r)
        if standing is None:
            unowned.append({"ref": r, "name": live[r].get("name")})
        elif _one_line(standing):
            one_line.append({"ref": r, "name": live[r].get("name"), "title": standing.get("title")})
    overlaps = []
    try:
        rep = E.mece_report((live[ref].get("tenant_id") or "T-local"))
        for o in rep.get("overlaps") or []:
            if o.get("a") in inside or o.get("b") in inside:
                overlaps.append({"a": o.get("a_name"), "b": o.get("b_name"), "similarity": o.get("similarity")})
    except Exception:
        overlaps = []
    return {"ref": ref, "name": live[ref].get("name"), "unowned": unowned, "one_line": one_line,
            "overlaps": overlaps, "checked": len(refs)}


class RequestBody(BaseModel):
    kind: str
    args: Dict[str, Any] = {}
    summary: str = ""


def _request_check(kind: str, args: Dict[str, Any]):
    """Shape only. The tree is re-read at APPLY time (org2_apply), so a rename
    of a department retired between the request and the approval is refused
    then, with the reason in the proposal's result."""
    if kind not in REQUEST_KINDS:
        raise HTTPException(status_code=400, detail="unknown request %r; one of: %s" % (kind, ", ".join(REQUEST_KINDS)))
    domains = E.load_domains()
    live = E.live_refs(domains)
    need = {"org.rename": ("ref", "name"), "org.move": ("ref", "target"), "org.create": ("parent", "name"),
            "org.charter": ("ref", "purpose")}[kind]
    for k in need:
        if not str(args.get(k) or "").strip():
            raise HTTPException(status_code=400, detail="%s needs %s" % (kind, k))
    for k in ("ref", "target", "parent"):
        if k in need and args.get(k) not in live:
            raise HTTPException(status_code=404, detail="no live department %s" % args.get(k))
    if kind == "org.move":
        if args["target"] in _subtree(args["ref"], live):
            raise HTTPException(status_code=400, detail="a department cannot move under itself")
        if live[args["ref"]].get("parent_ref") == args["target"]:
            raise HTTPException(status_code=400, detail="it is already there")
    if kind == "org.charter":
        # DS-1/DS-2: the kind and the rule tags are closed sets, so a bad one is
        # refused HERE, to the person filing it, instead of surfacing as a
        # failed apply in Approvals hours later.
        if args.get("kind") and str(args["kind"]).strip().lower() not in E.CHARTER_KINDS:
            raise HTTPException(status_code=400, detail="a charter kind is one of: %s"
                                % ", ".join(E.CHARTER_KINDS))
        for key, fn in (("done_when", E.normalize_done_when), ("rules", E.normalize_rules)):
            if key in args:
                try:
                    args[key] = fn(args[key])
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc))
    if kind == "org.charter" and args.get("charter_id"):
        v = E.charter_view(str(args["charter_id"]))
        if not v:
            raise HTTPException(status_code=404, detail="no charter %s" % args["charter_id"])
        if v.get("domain_ref") != args["ref"]:
            raise HTTPException(status_code=400, detail="that charter belongs to another department")
    if kind in ("org.rename", "org.create"):
        # the same sibling-name rule the applier enforces, so the requester hears
        # it now rather than the approver later (DeepSeek review P1-7)
        me = args.get("ref") if kind == "org.rename" else None
        parent = live[args["ref"]].get("parent_ref") if kind == "org.rename" else args["parent"]
        want = " ".join(str(args["name"]).split()).lower()
        for r, x in live.items():
            if r != me and x.get("parent_ref") == parent and (x.get("name") or "").lower() == want:
                raise HTTPException(status_code=400, detail="%s already has a department named %s"
                                    % ((live.get(parent) or {}).get("name") or "the root", " ".join(str(args["name"]).split())))
    return live


@router.post("/request", status_code=201)
def request(body: RequestBody):
    """File a rename, a move or a new sub-department as a PROPOSAL (plan S60,
    S70, S72). Nothing is applied here: the record waits in Approvals and an
    approval applies it through org2_apply. The summary is composed server-side
    from names, so what the approver reads is never client text."""
    import proposals   # the panel's own gate; lazy so a broken store cannot take the reads down
    args = dict(body.args or {})
    live = _request_check(body.kind, args)
    name_of = lambda r: (live.get(r) or {}).get("name") or r   # noqa: E731
    if body.kind == "org.rename":
        summary = "Rename %s to %s" % (name_of(args["ref"]), " ".join(str(args["name"]).split()))
    elif body.kind == "org.move":
        summary = "Move %s under %s" % (name_of(args["ref"]), name_of(args["target"]))
    elif body.kind == "org.charter":
        # DS-2: a role reads differently to the approver than a department's
        # own charter does -- it names a person -- so the summary says which.
        if str(args.get("kind") or "").strip().lower() == "role":
            who = " ".join(str(args.get("person") or "").split()) or "nobody yet"
            summary = "%s a role under %s for %s" % (
                "Edit" if args.get("charter_id") else "Write", name_of(args["ref"]), who)
        else:
            summary = ("Edit the charter of %s" if args.get("charter_id") else "Write the charter of %s") % name_of(args["ref"])
    else:
        summary = "New department %s under %s" % (" ".join(str(args["name"]).split()), name_of(args["parent"]))
    try:
        rec = proposals.create(body.kind, args, summary, session_id="org2")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"proposal": rec, "summary": summary}


def _page_html(rel: str, theme: Optional[str]) -> str:
    """One .html under the workdir, wrapped the way an app page is: the panel's
    tokens first, the theme stamped, the same CSP on the response (plan S56).
    Resolution goes through org_api._fs_resolve, the one workdir guard."""
    import org_api      # lazy: the fs helpers, not the router
    if not rel or not rel.lower().endswith(PAGE_EXT):
        raise HTTPException(status_code=400, detail="only an .html page opens here")
    root, target = org_api._fs_resolve(rel)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="%s is not a file" % rel)
    if os.path.getsize(target) > org_api.FS_MAX_READ:
        raise HTTPException(status_code=413, detail="%s is too large to open here" % rel)
    with open(target, "r", encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    import modules_api
    theme = theme if theme in ("dark", "light") else ""
    head = ('<meta charset="utf-8"><meta name="color-scheme" content="dark light">'
            '<style id="sutra-tokens">%s</style>' % modules_api.TOKEN_CSS)
    if theme:
        head += '<script>document.documentElement.setAttribute("data-theme","%s")</script>' % theme
    return head + body


@router.get("/page")
def page(path: str = "", theme: str = ""):
    import modules_api
    html = _page_html(path, theme)
    return HTMLResponse(html, headers={
        "Content-Security-Policy": modules_api.PAGE_CSP,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store, max-age=0",
    })


@router.get("/charter/{cid}")
def charter(cid: str):
    """One charter with its owner and what is filed under it (the Other
    charters rows of the list column open here)."""
    view = E.charter_view(cid)
    if not view:
        raise HTTPException(status_code=404, detail="no charter %s" % cid)
    domains = E.load_domains()
    dref = view.get("domain_ref")
    dept = domains.get(dref) or {}
    succ = [(domains.get(s) or {}).get("name") for s in (dept.get("successor_refs") or [])]
    filed = [{"id": (p.get("work_ref") or {}).get("id"), "label": _label((p.get("work_ref") or {}).get("id")),
              "ts_ms": p.get("ts_ms") or 0}
             for p in _placements_now() if p.get("charter_id") == view.get("id")]
    filed.sort(key=lambda r: -(r["ts_ms"] or 0))
    return {
        "charter": _charter_row(view),
        "department": ({"ref": dref, "name": dept.get("name"), "status": dept.get("status", "active"),
                        "successor": next((s for s in succ if s), None)} if dept else None),
        "filed": filed[:FILED_MAX],
        "filed_n": len(filed),
    }
