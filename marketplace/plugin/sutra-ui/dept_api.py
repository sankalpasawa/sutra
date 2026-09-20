"""dept_api.py -- read-only aggregates for the department screen (20-dept.js).

holding/plans/department-screen/LLD.md: the department screen is what the Org
structure screen shows when a department is selected. Every card on it is a
PROJECTION of a record that already exists; this router is the read side.

SAFETY (the same contract org_api.py and org2_api.py carry; test_forbidden_calls
scans this file too):
  - Calls ONLY the engine READERS: load_domains, live_refs, charters_for,
    charter_view, all_placements, _current_placements. Never a mutator.
  - Writes NOTHING but a proposal. The one POST this module will ever grow
    (LLD.md R12, slice D) calls proposals.create() and nothing else; an
    approval applies it elsewhere, exactly as the Org screen's pencil does.
  - routines.py and mission_engine.py are read through their public functions
    (state(), runs(), MissionStore.list()); they are never re-implemented here.
  - A missing store file is an EMPTY answer, never a 500 (PRD.md section J).
    A 404 is reserved for a department ref that does not exist.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402  (path insert must precede this import)

router = APIRouter(prefix="/api/dept", tags=["dept"])

ASKS_MAX = 40            # asks returned per department, newest first
RUNNING_MAX = 24         # open atom rows returned per department
WAITS_MAX = 40           # queued or blocked tasks returned per department
LEDGER_MAX_BYTES = 4 * 1024 * 1024   # refuse to walk a runaway ledger (org_api's own ceiling)

#: The two task states that mean "not moving, and someone has to do something".
#: mission_engine's states are draft/brief_confirm/running/queued/paused/blocked/
#: done/failed/stopped -- there is no literal "waiting" state the PRD's A8 names;
#: "queued" is the nearest and "blocked" is the other half of the same question.
WAIT_STATES = ("queued", "blocked")

#: Proposal kinds whose effect leaves this machine. A window that closes on one
#: of these is not a window on an undo, so the screen warns and asks twice
#: (PRD A32). The list mirrors proposals.KINDS' own two outbound kinds.
IRREVERSIBLE_KINDS = ("pr.create", "app.publish")


def _norm(path: Any) -> str:
    """One absolute, symlink-resolved spelling of a path, or "" for nothing.

    Both sides of every prefix test go through here: a department's stored cwd
    and the touch, lock or ledger path being tested against it. `realpath("")`
    answers the PROCESS's cwd, which would make every path look like a match,
    so the empty case returns "" and is refused by the caller."""
    s = str(path or "").strip()
    if not s:
        return ""
    try:
        return os.path.realpath(os.path.expanduser(s))
    except (OSError, ValueError):
        return ""


def _under(cwd: Optional[str], path: Any) -> bool:
    """True when `path` names something inside the department's cwd."""
    target = _norm(path)
    if not cwd or not target:
        return False
    return target == cwd or target.startswith(cwd + os.sep)


def _dept_cwd(ref: str, domains: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[str]:
    """The working directory a department's records fall under (LLD component 2).

    The department's own `cwd` when it carries one, else the nearest ancestor's,
    which in practice is the machine row -- the only node the importer reliably
    gives a cwd (org_api.py:241). Above the machine there is none, and the answer
    is None: the Now, Running, Waits and Engines lists are then honestly empty
    rather than showing another department's work (PRD F-3, BUILD-PLAN risk 1).
    """
    rows = E.load_domains() if domains is None else domains
    seen = set()
    cur: Optional[str] = ref
    while cur and cur in rows and cur not in seen:
        seen.add(cur)
        cwd = _norm(rows[cur].get("cwd"))
        if cwd:
            return cwd
        cur = rows[cur].get("parent_ref")
    return None


def _domain(ref: str) -> Dict[str, Any]:
    """The department row, or 404. A ref that does not exist is the ONE thing
    this router refuses; everything else answers 200 with an empty list."""
    domains = E.load_domains()
    row = domains.get(ref)
    if not row:
        raise HTTPException(status_code=404, detail="no department %s" % ref)
    return domains


def _subtree_refs(ref: str, domains: Dict[str, Dict[str, Any]]) -> set:
    """`ref` and everything under it, live or not -- an ask naming a retired
    child is still an ask this department owns."""
    kids: Dict[str, List[str]] = {}
    for r, d in domains.items():
        pr = d.get("parent_ref")
        if pr:
            kids.setdefault(pr, []).append(r)
    out, stack, seen = set(), [ref], set()
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        out.add(x)
        stack.extend(kids.get(x, []))
    return out


def _routine_cwds() -> Dict[str, str]:
    """{routine id: its working folder}. Read through routines.py's own store
    functions -- list_ids() and load() -- never by re-reading its files. A
    store that is absent or half-written is an empty map, not an error."""
    try:
        import routines
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for rid in routines.list_ids():
        try:
            out[rid] = str(routines.load(rid).get("cwd") or "")
        except Exception:
            continue
    return out


@router.get("/ping")
def ping():
    return {"ok": True}


def _ask_here(rec: Dict[str, Any], cwd: Optional[str], inside: set,
              routine_cwd: Dict[str, str]) -> bool:
    """Is this open ask the department's to answer? No proposal row carries a
    department (PRD F-3), so each kind is matched on what it DOES name:
    a routine kind on that routine's working folder, an org kind on the
    department it acts upon, and the two outbound kinds on the folder they
    would publish from."""
    kind = str(rec.get("kind") or "")
    args = rec.get("args") or {}
    if kind.startswith("routine."):
        return _under(cwd, routine_cwd.get(str(args.get("id") or "")))
    if kind.startswith("org."):
        return any(args.get(k) in inside for k in ("ref", "parent", "target"))
    return _under(cwd, args.get("cwd") or args.get("path") or args.get("repo"))


def _ask_row(rec: Dict[str, Any], window_ms: int) -> Dict[str, Any]:
    kind = str(rec.get("kind") or "")
    return {
        "id": rec.get("id"),
        "kind": kind,
        "summary": rec.get("summary") or "",
        "args": rec.get("args") or {},
        "created_ms": rec.get("created_ms") or 0,
        "window_ms": window_ms,
        # What happens when the window closes with nobody acting: proposals
        # expire, and an expired proposal applies NOTHING (proposals.py:144).
        # Stated rather than computed, because it is the same for every kind.
        "default": "Nothing happens",
        "irreversible": kind in IRREVERSIBLE_KINDS,
    }


@router.get("/{ref}/now")
def now(ref: str):
    """R2: the open asks this department is the one to answer."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    inside = _subtree_refs(ref, domains)
    try:
        import proposals
        rows = proposals.pending()
        window_ms = int(proposals.TTL_SECONDS) * 1000
    except Exception:
        # The gate module is the Stamp/Refuse path too; when it cannot be read
        # the card is empty and read-only rather than broken (PRD section J).
        return {"asks": [], "skipped": 0, "decidable": False}
    routine_cwd = _routine_cwds()
    asks, skipped = [], 0
    for rec in rows:
        try:
            if _ask_here(rec, cwd, inside, routine_cwd):
                asks.append(_ask_row(rec, window_ms))
        except Exception:
            skipped += 1
    asks.sort(key=lambda r: -(r["created_ms"] or 0))
    return {"asks": asks[:ASKS_MAX], "skipped": skipped, "decidable": True}


def _workdir() -> Optional[str]:
    """The folder the atom ledger is written into, or None.

    org_api._automation_root() raises a 400 when the workdir is unset or
    outside the allowed root; this screen must not go red over a setting it
    does not own, so the same two checks answer None and the card shows its
    quiet line instead (PRD section J, BUILD-PLAN risk 2)."""
    try:
        import providers
        wd = str(providers.load_settings().get("workdir") or "").strip()
        if not wd or not providers.workdir_allowed(wd):
            return None
        return wd if os.path.isdir(wd) else None
    except Exception:
        return None


def _jsonl(path: str, limit: int):
    """(rows, unreadable lines). The bounded-tail idiom org_api._read_jsonl_tail
    uses, called fresh here so this module never imports org_api: a runaway file
    is refused by size, a corrupt line is counted and skipped, and a missing
    file is an empty list rather than an error."""
    if not os.path.isfile(path):
        return [], 0
    try:
        if os.path.getsize(path) > LEDGER_MAX_BYTES:
            return [], 0
        rows, skipped = [], 0
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    skipped += 1
        return rows[-limit:] if limit else rows, skipped
    except OSError:
        return [], 0


def _abs(root: str, path: Any) -> str:
    """A ledger touch is written RELATIVE to the folder the work ran in (the
    rows read 'holding/bin/', not '/Users/.../holding/bin/'), so it is joined
    onto that folder before any prefix test. An absolute touch is left alone."""
    s = str(path or "").strip()
    if not s:
        return ""
    return s if os.path.isabs(s) else os.path.join(root, s)


def _int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


@router.get("/{ref}/running")
def running(ref: str):
    """R3: the work items open right now that touch this department.

    The ledger is append-only and a work item is written to it more than once
    (open, then closed or abandoned), so the LAST row per id is the one that
    says what it is doing now."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    root = _workdir()
    if not cwd or not root:
        return {"running": [], "skipped": 0}
    rows, skipped = _jsonl(os.path.join(root, ".sutra", "atom-ledger.jsonl"), 0)
    latest: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("id"):
            latest[str(r["id"])] = r
    out = []
    for r in latest.values():
        if str(r.get("status") or "") != "open":
            continue
        touches = [t for t in (r.get("touches") or []) if _under(cwd, _abs(root, t))]
        if not touches:
            continue
        out.append({"sid": r.get("sid"), "id": r.get("id"),
                    "goal": str(r.get("goal") or ""), "status": "open",
                    "touches": touches, "ts": _int(r.get("ts"))})
    out.sort(key=lambda r: -(r["ts"] or 0))
    return {"running": out[:RUNNING_MAX], "skipped": skipped}


def _dept_sessions(cwd: Optional[str], root: Optional[str]) -> set:
    """The sessions that have worked in this department, from the ledger.

    A task row carries no department and no folder of its own (PRD F-3): the
    only thing it names that any other record also names is its target session.
    A session that has touched a path under the department HAS worked here, and
    that is the join. A task whose session has never touched the department is
    left out rather than guessed at."""
    sids = set()
    if not cwd or not root:
        return sids
    rows, _ = _jsonl(os.path.join(root, ".sutra", "atom-ledger.jsonl"), 0)
    for r in rows:
        if not isinstance(r, dict):
            continue
        if any(_under(cwd, _abs(root, t)) for t in (r.get("touches") or [])):
            sid = str(r.get("sid") or "")
            if sid:
                sids.add(sid)
    return sids


@router.get("/{ref}/waits")
def waits(ref: str):
    """R4: the tasks that are not moving and are this department's to unblock."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    root = _workdir()
    try:
        import mission_engine
        rows = mission_engine.MissionStore().list(states=WAIT_STATES)
    except Exception:
        return {"waits": [], "skipped": 0}
    sids = _dept_sessions(cwd, root)
    out, skipped = [], 0
    for m in rows:
        if not isinstance(m, dict):
            skipped += 1
            continue
        target = str(m.get("target_session") or "")
        if not (_under(cwd, m.get("cwd")) or (target and target in sids)):
            continue
        out.append({"id": m.get("id"), "objective": str(m.get("objective") or ""),
                    "state": m.get("state"), "target_session": m.get("target_session")})
    return {"waits": out[:WAITS_MAX], "skipped": skipped}
