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

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402  (path insert must precede this import)

router = APIRouter(prefix="/api/org2", tags=["org2"])

FILED_MAX = 200          # placements returned per department (newest first)
DOCS_MAX = 200
LABEL_MAX = 60
DESKTOP_NAME = "Desktop"  # project_import.DESKTOP_NAME: the machine node under the root

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
    """Interim node kind (plan S27) until the engine stores one (S94)."""
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
    return {"id": v.get("id"), "title": v.get("title"), "purpose": v.get("purpose"),
            "status": v.get("status", "active"), "kind": v.get("kind", "standing"),
            "scope_in": v.get("scope_in") or []}


def _charters(ref: str):
    """(standing charter or None, the other charters) for a department. The
    standing one is the first active, non-superseded charter of kind standing,
    else the first active one; retired and superseded charters list after the
    active ones, so nothing is hidden."""
    views = [v for v in (E.charter_view(c) for c in E.charters_for(ref)) if v]
    sup = E.superseded_ids() if hasattr(E, "superseded_ids") else {}
    active = [v for v in views if v.get("status", "active") != "retired" and v.get("id") not in sup]
    standing = next((v for v in active if v.get("kind", "standing") == "standing"), None)
    if standing is None and active:
        standing = active[0]
    others = [v for v in views if standing is None or v.get("id") != standing.get("id")]
    others.sort(key=lambda v: (v.get("status", "active") != "active",
                               v.get("id") in sup, (v.get("title") or "").lower()))
    return standing, others


def _filed(ref: str):
    rows = []
    for p in E.all_placements():
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
    }


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
             for p in E.all_placements() if p.get("charter_id") == view.get("id")]
    filed.sort(key=lambda r: -(r["ts_ms"] or 0))
    return {
        "charter": _charter_row(view),
        "department": ({"ref": dref, "name": dept.get("name"), "status": dept.get("status", "active"),
                        "successor": next((s for s in succ if s), None)} if dept else None),
        "filed": filed[:FILED_MAX],
        "filed_n": len(filed),
    }
