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
import re
import subprocess
import sys
import time
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
RULES_MAX = 24           # rule lines on the Identity card
CHAT_MAX = 60            # turns returned per chat, oldest first (a chat reads down)
GATE_MAX = 20            # of those, at most this many are gate rows
DONE_MAX = 400           # characters of the done line
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


def _routine_rows() -> Dict[str, Dict[str, Any]]:
    """{routine id: its record}. Read through routines.py's own store functions
    -- list_ids() and load() -- never by re-reading its files. A store that is
    absent or half-written is an empty map, not an error."""
    try:
        import routines
    except Exception:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for rid in routines.list_ids():
        try:
            rec = routines.load(rid)
        except Exception:
            continue
        if isinstance(rec, dict):
            out[rid] = rec
    return out


def _routine_cwds() -> Dict[str, str]:
    """{routine id: its working folder} -- the one field every department
    filter needs, off the records above."""
    return {rid: str(rec.get("cwd") or "") for rid, rec in _routine_rows().items()}


def _mtime_ms(path: str) -> int:
    try:
        return int(os.stat(path).st_mtime * 1000)
    except OSError:
        return 0


def _iso_ms(ms: Any) -> str:
    """A millisecond stamp written the way every other record on this screen
    writes a time, so one client formatter reads them all."""
    n = _int(ms)
    if not n:
        return ""
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(n / 1000.0))
    except (OverflowError, OSError, ValueError):
        return ""


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


# ----------------------------------------------------------------- IDENTITY --
# R1. Identity is the department's own answer to "what is this for, when is it
# done, what are the rules, what may it spend, and whose it is". Every line is
# a projection of the charter record and the task-limits store; nothing here is
# composed by this module, and a field the record does not carry comes back
# null so the card can say its quiet line instead of inventing one (PRD A11,
# A12; the four gaps F-1, F-12, F-13 are answered in LLD section 8).


def _text(v: Any) -> str:
    """One line of screen text out of whatever a record carries. A rule or a
    milestone may be stored as a plain string or as a small object; the object
    forms are read for the field that holds the words, and anything else is
    refused rather than JSON-dumped onto a card."""
    if isinstance(v, str):
        return " ".join(v.split())
    if isinstance(v, dict):
        for k in ("text", "rule", "label", "name", "title", "statement"):
            if isinstance(v.get(k), str) and v[k].strip():
                return " ".join(v[k].split())
    return ""


def _sentence(s: str) -> str:
    s = _text(s)
    return s if (not s or s[-1] in ".!?") else s + "."


def _standing_charter(ref: str) -> Optional[Dict[str, Any]]:
    """The one charter that speaks for the department, by org2_api._charters'
    own rule (org2_api.py:126-140): the first active, non-superseded charter of
    kind standing, else the first active one. That helper is module-private
    there, so the rule is applied here rather than imported -- and it is the
    ONLY charter reading this screen does."""
    try:
        views = [v for v in (E.charter_view(c) for c in E.charters_for(ref)) if v]
    except Exception:
        return None
    sup = E.superseded_ids() if hasattr(E, "superseded_ids") else {}
    active = [v for v in views
              if v.get("status", "active") != "retired" and v.get("id") not in sup]
    if not active:
        return None
    return next((v for v in active if v.get("kind", "standing") == "standing"), active[0])


def _done_line(charter: Optional[Dict[str, Any]]) -> Optional[str]:
    """When the department is done, from the milestones' own done_when lines.

    F-1: no charter has a "Done when" section -- `done_when` exists per
    milestone and per todo and nowhere else (lib/charters_seed.py:65-71). The
    card shows what is written there, joined, and nothing when none is."""
    if not charter:
        return None
    parts = []
    for m in (charter.get("milestones") or []):
        if isinstance(m, dict):
            one = _sentence(m.get("done_when") or "")
            if one:
                parts.append(one)
    line = " ".join(parts).strip()
    if not line:
        return None
    return line if len(line) <= DONE_MAX else line[:DONE_MAX - 1].rstrip() + "…"


def _rules(charter: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """The department's rules, each tagged.

    The tag vocabulary is go / ask / refuse / always (PRD A10). Today every
    line comes back `always`, and that is the honest answer, not a shortcut:
    a charter body carries `invariants` and `constraints` -- things that hold
    at all times -- and carries no go/ask/refuse ledger at all (F-1, F-13).
    The other three tags exist for the record that will carry them; this route
    never guesses one."""
    if not charter:
        return []
    out = []
    for key in ("invariants", "constraints"):
        for item in (charter.get(key) or []):
            text = _text(item)
            if text:
                out.append({"tag": "always", "text": text})
    return out[:RULES_MAX]


def _limits() -> Dict[str, Any]:
    """The founder's task limits AS STORED, through mission_engine's own
    locator. Not max_running()/turn_budget(), deliberately: those answer with
    the built-in default when nothing is set, and the card has to be able to
    tell "the founder set this" from "nothing has been set", which is the
    difference between a budget bar and the quiet line (A11)."""
    try:
        import mission_engine
        path = mission_engine.limits_path()
    except Exception:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _budget() -> Dict[str, Any]:
    """The budget line: how many tasks may run at once, and the per-kind turn
    budgets the founder has set. Global, not per department (PRD E5) -- stated
    on every department's card because it is the ceiling every one of them
    works under, not because it was measured here."""
    raw = _limits()
    ceiling = 0
    try:
        import mission_engine
        ceiling = int(mission_engine.RUNNING_CEILING)
    except Exception:
        ceiling = 0
    at_once = raw.get("running_at_once")
    turns = raw.get("turn_budget")
    return {
        "running_at_once": _int(at_once) if isinstance(at_once, (int, float)) else None,
        "ceiling": ceiling,
        "turn_budget": {str(k): _int(v) for k, v in turns.items()
                        if isinstance(v, (int, float))} if isinstance(turns, dict) else {},
    }


def _authority_name(charter: Optional[Dict[str, Any]]) -> str:
    """A person's name out of the charter's `authority` field.

    F-12: `authority` is `{}` on every charter on disk -- no writer populates
    it. The shape it will take is therefore not settled, so a string, a
    {name|owner|who} object and the first entry of a list are all read, and
    anything else is nothing rather than a guess."""
    if not charter:
        return ""
    a = charter.get("authority")
    if isinstance(a, list):
        a = a[0] if a else None
    if isinstance(a, str):
        return " ".join(a.split())
    if isinstance(a, dict):
        for k in ("name", "owner", "who", "holder"):
            if isinstance(a.get(k), str) and a[k].strip():
                return " ".join(a[k].split())
    return ""


def _git_user(cwd: Optional[str]) -> str:
    """`git config user.name` in the department's own folder, or "".

    The fallback owner (F-12). Run with a timeout and with stdin closed: this
    sits on a read route, and a git that waits for a credential prompt must
    not hold the card open."""
    try:
        r = subprocess.run(["git", "config", "user.name"],
                           cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
                           stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=3)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return " ".join(r.stdout.split()) if r.returncode == 0 else ""


def _owner(charter: Optional[Dict[str, Any]], cwd: Optional[str]) -> Dict[str, Any]:
    name = _authority_name(charter)
    if name:
        return {"source": "charter", "name": name}
    name = _git_user(cwd)
    if name:
        return {"source": "git", "name": name}
    return {"source": "none", "name": None}


def _at(rec: Dict[str, Any], key: str) -> str:
    """A record's own timestamp string, passed through untouched. The client
    shortens it for the turn; the whole stamp stays in the raw row."""
    v = rec.get(key)
    return v if isinstance(v, str) else ""


def _turn(who: str, to: str, mode: str, line: str, at: str,
          row: Dict[str, Any]) -> Dict[str, Any]:
    """One turn of a chat.

    `who` and `to` are the two ENDS of the chat -- the department's function
    and the person or function it is talking to. They are the model's names
    for the ends, not a stored author field: no record on disk carries one
    (F-13). `line` is the record's own words, never composed here beyond the
    verdict words below, and `row` is the record itself, which is what the
    Exact tab shows."""
    return {"who": who, "to": to, "mode": mode, "line": _text(line),
            "at": at, "row": row}


#: What the owner said back, per the proposal's own status. `pending` is not
#: here on purpose: an unanswered ask has no answer turn, it is still open.
ANSWERS = {
    "approved": "Stamped.",
    "rejected": "Refused.",
    "failed": "Stamped, and it did not apply.",
    "expired": "The window closed. Nothing happened.",
}


def _dept_proposals(ref: str, domains: Dict[str, Dict[str, Any]],
                    cwd: Optional[str]) -> List[Dict[str, Any]]:
    """Every proposal this department is the one to answer, oldest first --
    open and answered alike, which is what makes a chat a chat. The filter is
    `_ask_here`, the same one Now uses for the open ones."""
    try:
        import proposals
        rows = proposals.listing()
    except Exception:
        return []
    inside = _subtree_refs(ref, domains)
    routine_cwd = _routine_cwds()
    out = []
    for rec in rows:
        try:
            if _ask_here(rec, cwd, inside, routine_cwd):
                out.append(rec)
        except Exception:
            continue
    # The id breaks a tie on purpose: two asks written in the same millisecond
    # would otherwise come back in whatever order the directory listing had,
    # and a chat that re-orders itself on every refresh is a bug the reader
    # would blame on the records.
    out.sort(key=lambda r: ((r.get("created_ms") or 0), str(r.get("id") or "")))
    return out


def _gate_turns(cwd: Optional[str]) -> List[Dict[str, Any]]:
    """What the department went ahead with on its own, from the permission
    gate's own log in that folder (`.enforcement/permission-gate.jsonl`).

    F-13: this log carries ALLOW rows only -- there is no go/ask/refuse ledger
    anywhere in the system -- so these are the judgments that never reached the
    owner, which is exactly what belongs beside the ones that did. Only the
    tool name is put on screen; the matched pattern is a path-shaped string and
    stays in the raw row (A28)."""
    if not cwd:
        return []
    rows, _ = _jsonl(os.path.join(cwd, ".enforcement", "permission-gate.jsonl"), GATE_MAX)
    out = []
    for r in rows:
        if not isinstance(r, dict) or r.get("decision") != "allow":
            continue
        tool = _text(r.get("tool"))
        if not tool:
            continue
        out.append(_turn("Identity", "", "think",
                         "Went ahead without asking: " + tool, "", r))
    return out


def _owner_chat(props: List[Dict[str, Any]], owner: str,
                cwd: Optional[str]) -> List[Dict[str, Any]]:
    """What the owner has been asked and what they answered, with the
    judgments taken without them in between."""
    who = owner or "the owner"
    turns: List[Dict[str, Any]] = []
    for i, rec in enumerate(props):
        base = (rec.get("created_ms") or 0, i, 0)
        turns.append((base, _turn("Identity", who, "say", rec.get("summary") or "",
                                  _at(rec, "created_at"), rec)))
        answer = ANSWERS.get(str(rec.get("status") or ""))
        if answer:
            turns.append(((base[0], i, 1),
                          _turn(who, "Identity", "say", answer,
                                _at(rec, "decided_at"), rec)))
    for j, t in enumerate(_gate_turns(cwd)):
        ts = _int(t["row"].get("ts")) * 1000
        turns.append(((ts, len(props) + j, 0), t))
    turns.sort(key=lambda x: x[0])
    return [t for _k, t in turns][-CHAT_MAX:]


def _adaptation_chat(props: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The proposals themselves, as the exchange that carried them: what was
    put forward, and what Identity did with it."""
    turns = []
    for rec in props:
        turns.append(_turn("Adaptation", "Identity", "say",
                           rec.get("summary") or "", _at(rec, "created_at"), rec))
        answer = ANSWERS.get(str(rec.get("status") or ""))
        if answer:
            turns.append(_turn("Identity", "Adaptation", "say", answer,
                               _at(rec, "decided_at"), rec))
    return turns[-CHAT_MAX:]


@router.get("/{ref}/identity")
def identity(ref: str):
    """R1: the department's goal, when it is done, its rules, its budget, its
    owner, and the two chats Identity keeps."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    charter = _standing_charter(ref)
    owner = _owner(charter, cwd)
    props = _dept_proposals(ref, domains, cwd)
    goal = _text((charter or {}).get("purpose") or "")
    return {
        "goal": goal or None,
        "done": _done_line(charter),
        "rules": _rules(charter),
        "budget": _budget(),
        "owner": owner,
        "chats": {
            "owner": _owner_chat(props, owner.get("name") or "", cwd),
            "adaptation": _adaptation_chat(props),
        },
    }


# ---------------------------------------------------------------- ADAPTATION --
# R5. What the department has learned about itself: the changes that were put
# forward, and the asks that keep coming back. Both are readings of ONE store,
# the proposal log -- there is no learning record anywhere (PRD S4) -- so a
# pattern here is COUNTED on every read, never remembered.

PATTERN_MIN = 3                              # A13: three of a kind make a pattern
PATTERN_WINDOW_MS = 7 * 24 * 3600 * 1000     # A13: inside seven days
PROPOSALS_MAX = 12
PATTERNS_MAX = 8


def _ttl_ms() -> int:
    """How long an ask stays answerable, from the gate's own constant."""
    try:
        import proposals
        return int(proposals.TTL_SECONDS) * 1000
    except Exception:
        return 0


def _state_line(rec: Dict[str, Any]) -> str:
    """Where a proposal stands, in the same words the chat uses for it. An
    undecided one is still waiting, and its window says until when."""
    return ANSWERS.get(str(rec.get("status") or "")) or "Waits."


def _patterns(props: List[Dict[str, Any]], now_ms: int) -> List[Dict[str, Any]]:
    """The same ask, asked again and again.

    A13: one line per kind-and-summary seen PATTERN_MIN times or more inside
    the last seven days. Two of a kind is not a pattern, and an ask older than
    the window counts toward nothing -- which is why the answer shrinks again
    on its own once the asking stops."""
    groups: Dict[Any, List[int]] = {}
    for rec in props:
        made = _int(rec.get("created_ms"))
        if not made or now_ms - made > PATTERN_WINDOW_MS:
            continue
        summary = _text(rec.get("summary"))
        if not summary:
            continue
        groups.setdefault((str(rec.get("kind") or ""), summary), []).append(made)
    out = []
    for (kind, summary), stamps in groups.items():
        if len(stamps) < PATTERN_MIN:
            continue
        out.append({"kind": kind, "summary": summary, "count": len(stamps),
                    "since_ms": min(stamps)})
    out.sort(key=lambda r: (-r["count"], r["since_ms"]))
    return out[:PATTERNS_MAX]


def _adaptation_rows(props: List[Dict[str, Any]], patterns: List[Dict[str, Any]],
                     window_ms: int) -> List[Dict[str, Any]]:
    """Every change put forward, newest first: what it would change, what is
    behind it, and where it stands.

    The evidence column is the repeat count and nothing else -- a proposal row
    carries no evidence field (PRD S4), so the only thing the store can
    honestly put there is how often the same ask has come back. A change that
    stands alone shows no evidence rather than a sentence composed here."""
    hits = {(p["kind"], p["summary"]): p for p in patterns}
    rows = []
    for rec in reversed(props):                  # _dept_proposals reads oldest first
        summary = _text(rec.get("summary"))
        pat = hits.get((str(rec.get("kind") or ""), summary))
        rows.append({
            "id": rec.get("id"),
            "change": summary,
            "evidence": ("Asked %d times in seven days" % pat["count"]) if pat else "",
            "state": _state_line(rec),
            "open": str(rec.get("status") or "") == "pending",
            "created_ms": _int(rec.get("created_ms")),
            "window_ms": window_ms,
            "row": rec,
        })
    return rows[:PROPOSALS_MAX]


@router.get("/{ref}/adaptation")
def adaptation(ref: str):
    """R5: the changes put forward under this department and the patterns
    behind them, with the exchange that carried them as its chat."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    props = _dept_proposals(ref, domains, cwd)
    pats = _patterns(props, int(time.time() * 1000))
    return {
        "proposals": _adaptation_rows(props, pats, _ttl_ms()),
        "patterns": pats,
        "chat": _adaptation_chat(props),
    }


# ------------------------------------------------------------------ PRIORITY --
# R6. What the department took on, in the order it took it: the queue, and the
# ceiling it all runs under. The dispatch record is the only row in the system
# that says a unit of work was admitted and what it was routed to -- nothing in
# sutra-ui has ever read one (PRD F-3), so the reader below is new, and it is a
# reader: this module writes no marker of any kind.

KV_MAX_BYTES = 64 * 1024
QUEUE_MAX = 8


def _kv(path: str) -> Dict[str, str]:
    """A KEY=VALUE marker file as a map. Absent, oversized or unreadable is an
    empty map -- a department whose sessions left no record is quiet, not
    broken (PRD section J)."""
    if not os.path.isfile(path):
        return {}
    try:
        if os.path.getsize(path) > KV_MAX_BYTES:
            return {}
        out: Dict[str, str] = {}
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                key, sep, val = line.partition("=")
                if sep and key.strip():
                    out[key.strip()] = val.strip()
        return out
    except OSError:
        return {}


def _dispatch_rows(cwd: Optional[str], root: Optional[str]) -> List[Dict[str, str]]:
    """Every unit of work admitted under this department, newest first.

    One record per session at `.sutra/dispatch/<session>/dispatch-record`. The
    record carries no department (PRD F-3); the only thing it names that says
    WHERE the work went is its TOUCHES list, so that is the join -- the same
    one Running makes with the ledger's touches, resolved against the same
    folder."""
    out: List[Dict[str, str]] = []
    if not cwd or not root:
        return out
    base = os.path.join(root, ".sutra", "dispatch")
    try:
        sessions = os.listdir(base)
    except OSError:
        return out
    for sid in sessions:
        rec = _kv(os.path.join(base, sid, "dispatch-record"))
        if not rec:
            continue
        touches = [t for t in str(rec.get("TOUCHES") or "").split("|") if t.strip()]
        if not any(_under(cwd, _abs(root, t)) for t in touches):
            continue
        out.append(rec)
    out.sort(key=lambda r: -_int(r.get("TS")))
    return out


def _runs_as(rec: Dict[str, str]) -> str:
    """What a row runs as, in the record's own word. The dispatch record names
    a model, never a person (PRD F-3), so a row a person answers cannot be told
    apart here and is not guessed at."""
    return _text(rec.get("MODEL")) or _text(rec.get("PROVIDER"))


def _priority_chat(queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_turn("Priority", "Coordination", "say",
                  "Admitted: %s. Runs as %s." % (q["next"], q["runs_as"] or "nothing named"),
                  _iso_ms(q["when_ms"]), q["row"])
            for q in queue][:CHAT_MAX]


@router.get("/{ref}/priority")
def priority(ref: str):
    """R6: the queue this department is working down, and its budget."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    root = _workdir()
    recs = _dispatch_rows(cwd, root)
    queue = [{"next": _text(r.get("UNIT")), "runs_as": _runs_as(r),
              "when_ms": _int(r.get("TS")) * 1000, "row": r}
             for r in recs[:QUEUE_MAX] if _text(r.get("UNIT"))]
    top = recs[0] if recs else {}
    return {
        "queue": queue,
        "class": _text(top.get("CLASS")) or None,
        "model": _runs_as(top) or None,
        "budget": _budget(),
        "chat": _priority_chat(queue),
    }


# -------------------------------------------------------------- COORDINATION --
# R7. Who is holding something, and what changed hands. No record in the system
# names a holder or a hand-off (PRD F-6): the only marks that exist are a
# routine's own run lock, a session's heartbeat file, and the supersedes chain
# a placement leaves behind when the same work item is re-filed under another
# department. All three are READ here -- isdir, mtime, the chain -- and none is
# taken, released or written (LLD reuse row 14).

HELD_MAX = 8
HANDOFF_MAX = 6
#: A heartbeat file is touched while a session is alive. Older than this and
#: nobody is there, so it is not a holder -- a stale mark must not read as one.
HEARTBEAT_FRESH_MS = 15 * 60 * 1000
LABEL_MAX = 60
_EXT = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_SEP = re.compile(r"[-_]+")


def _label(work_id: Any) -> str:
    """A NAME for a filed item, never a path (founder, 2026-09-14). The rule is
    org2_api._label's (org2_api.py:49-63), applied here rather than imported --
    that helper is module-private there."""
    s = str(work_id or "").strip()
    if not s:
        return ""
    if "/" in s and " " not in s:
        seg = _EXT.sub("", s.rstrip("/").rsplit("/", 1)[-1])
        s = _SEP.sub(" ", seg).strip() or seg
    s = " ".join(s.split())
    return s if len(s) <= LABEL_MAX else s[:LABEL_MAX - 1].rstrip() + "…"


def _dept_name(ref: Any, domains: Dict[str, Dict[str, Any]]) -> str:
    return _text((domains.get(str(ref or "")) or {}).get("name"))


def _heartbeats(cwd: Optional[str], name: str) -> List[Dict[str, Any]]:
    """The sessions alive in this department's own folder.

    The file is empty and its name is a session id: the only thing it says is
    WHEN it was last touched. That is enough to answer "someone is working
    here" and not enough to answer "who", so the holder is stated as a session
    and no name is invented for it."""
    if not cwd:
        return []
    folder = os.path.join(cwd, ".claude", "heartbeats")
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    now = int(time.time() * 1000)
    out = []
    for n in names:
        ts = _mtime_ms(os.path.join(folder, n))
        if ts and 0 <= now - ts <= HEARTBEAT_FRESH_MS:
            out.append({"resource": name or "This department", "holder": "A session",
                        "since_ms": ts, "row": {"heartbeat": n, "mtime_ms": ts}})
    return out


def _locks_held(cwd: Optional[str], name: str) -> List[Dict[str, Any]]:
    """What is held right now, newest hold first."""
    held: List[Dict[str, Any]] = []
    try:
        import routines
        runs = str(routines.runs_dir())
    except Exception:
        runs = ""
    if runs and cwd:
        for rid, rec in _routine_rows().items():
            if not _under(cwd, rec.get("cwd")):
                continue
            lock = os.path.join(runs, rid, ".lock")
            if not os.path.isdir(lock):
                continue
            held.append({"resource": _text(rec.get("description")) or rid,
                         "holder": "Its own run", "since_ms": _mtime_ms(lock),
                         "row": {"id": rid, "enabled": rec.get("enabled"),
                                 "since_ms": _mtime_ms(lock)}})
    held.extend(_heartbeats(cwd, name))
    held.sort(key=lambda r: -(r["since_ms"] or 0))
    return held[:HELD_MAX]


def _handoffs(ref: str, domains: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Work that changed hands, newest first.

    A placement whose predecessor sat under a DIFFERENT department is that work
    item moving from the one to the other, and it is the only trace a hand-off
    leaves anywhere (PRD F-6). A move inside one department is not a hand-off
    and is left out."""
    try:
        places = E.all_placements()
    except Exception:
        return []
    by_id = {p.get("id"): p for p in places if isinstance(p, dict)}
    inside = _subtree_refs(ref, domains)
    out = []
    for p in places:
        prev = by_id.get(p.get("supersedes"))
        if not isinstance(prev, dict):
            continue
        src, dst = prev.get("domain_ref"), p.get("domain_ref")
        if not src or not dst or src == dst:
            continue
        if dst not in inside and src not in inside:
            continue
        a, b = _dept_name(src, domains), _dept_name(dst, domains)
        if not a or not b:
            continue
        out.append({"from": a, "to": b,
                    "what": _label((p.get("work_ref") or {}).get("id")),
                    "ts_ms": _int(p.get("ts_ms")), "row": p})
    out.sort(key=lambda r: -(r["ts_ms"] or 0))
    return out[:HANDOFF_MAX]


def _coordination_chat(held: List[Dict[str, Any]],
                       hand: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    turns = [_turn("Coordination", "Priority", "say",
                   "%s held by %s." % (h["resource"], h["holder"].lower()),
                   _iso_ms(h["since_ms"]), h["row"]) for h in held]
    turns += [_turn("Coordination", h["to"], "say",
                    "%s hands from %s to %s." % (h["what"], h["from"], h["to"]),
                    _iso_ms(h["ts_ms"]), h["row"]) for h in hand]
    return turns[:CHAT_MAX]


@router.get("/{ref}/coordination")
def coordination(ref: str):
    """R7: what this department is holding, and what changed hands."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    held = _locks_held(cwd, _dept_name(ref, domains))
    hand = _handoffs(ref, domains)
    return {"held": held, "handoffs": hand, "chat": _coordination_chat(held, hand)}


# --------------------------------------------------------------------- AUDIT --
# R8. What the checks say about this department. A CHECK IS A CHECK (A16): every
# row is one claim and what the record answered, and nothing here is scored,
# totalled or turned into a share -- there is no number on this card at all.
#
# The findings log is written by the daily governance audit, which is holding's
# own routine (PRD S6): most installs have never had one, so the read is
# best-effort by design and an absent file is an empty card, never a 500.

FINDINGS_MAX = 24
UNSEEN_MAX = 6
CLAIM_MAX = 200
FINDINGS_REL = ("holding", "observability", "governance-audit", "findings.jsonl")
#: A word with a slash in it, which is the only shape a path takes in a
#: finding's sentence. The leading slash is part of the match ON PURPOSE:
#: without it an absolute path elsewhere on the machine reads as a relative one
#: and is joined onto this department's folder, where every one of them would
#: then look like a hit. "323/332" matches too, so the caller checks for a letter.
_PATHISH = re.compile(r"/?[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+")
#: severity -> the dot's own word. Anything unrecognised reads ok rather than
#: alarming the owner over a word this screen does not know.
DOTS = {"critical": "block", "warn": "warn"}


def _pathish(token: str) -> bool:
    return any(c.isalpha() for c in token)


def _no_paths(text: str) -> str:
    """The same sentence with every path-shaped word replaced by the NAME at
    its end (founder, 2026-09-14: names, never paths). The whole path stays in
    the raw row, which is what an Exact tab is for (A28, A29)."""
    return _PATHISH.sub(
        lambda m: _label(m.group(0)) if _pathish(m.group(0)) else m.group(0), text)


def _finding_rows(cwd: Optional[str], root: Optional[str]):
    """(rows, unreadable lines) from the first findings log that exists -- the
    department's own folder first, then the folder the work runs in."""
    for base in (cwd, root):
        if not base:
            continue
        path = os.path.join(base, *FINDINGS_REL)
        if os.path.isfile(path):
            return _jsonl(path, 0)
    return [], 0


def _names_a_path_under(text: str, cwd: Optional[str], root: Optional[str]) -> bool:
    """Does this finding name something inside the department?

    No finding row carries a department, a domain or a path field (PRD S6): the
    only thing it names is whatever paths its own sentence spells. Those are
    resolved against the folder the work runs in and tested the way a ledger
    touch is -- the same heuristic, and the same honest limit (PRD F-3)."""
    for token in _PATHISH.findall(text):
        if _pathish(token) and _under(cwd, _abs(root or cwd or "", token)):
            return True
    return False


def _clip(line: str) -> str:
    return line if len(line) <= CLAIM_MAX else line[:CLAIM_MAX - 1].rstrip() + "…"


def _audit_chat(found: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    turns = [_turn("Audit", "Priority", "say",
                   'Flag: claimed "%s"; the record says %s' % (f["claim"], f["record"]),
                   f["last_seen"], f["row"])
             for f in found if f["dot"] != "ok"]
    if found and not turns:
        turns.append(_turn("Audit", "Priority", "say", "Every claim has its row.", "", {}))
    return turns[:CHAT_MAX]


@router.get("/{ref}/audit")
def audit(ref: str):
    """R8: the checks that name this department, newest first."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    root = _workdir()
    rows, skipped = _finding_rows(cwd, root)
    # The log is appended to on every audit day, so the same finding is written
    # again and again under one id. The LAST row for an id is where it stands.
    latest: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("id"):
            latest[str(r["id"])] = r
    found, unseen = [], []
    for r in latest.values():
        text = _text(r.get("text"))
        if not text or not _names_a_path_under(text, cwd, root):
            continue
        claim = _clip(_no_paths(text))
        status = str(r.get("status") or "")
        note = _clip(_no_paths(_text(r.get("note") or r.get("fix_note"))))
        found.append({
            "id": r.get("id"), "check": _text(r.get("check")), "claim": claim,
            "record": note or ("Fixed." if status == "fixed" else "Still open."),
            "dot": "ok" if status == "fixed" else DOTS.get(str(r.get("severity") or ""), "ok"),
            "first_seen": _text(r.get("first_seen")),
            "last_seen": _text(r.get("last_seen")), "row": r,
        })
        # Never looked at: still open, and not one word has been written
        # against it -- no note, no fix note, no reference to a fix.
        if status != "fixed" and not (note or r.get("fix_ref")):
            unseen.append({"claim": claim, "since": _text(r.get("first_seen")), "row": r})
    found.sort(key=lambda r: (r["last_seen"], str(r["id"] or "")), reverse=True)
    unseen.sort(key=lambda r: (r["since"], r["claim"]))
    found = found[:FINDINGS_MAX]
    return {"findings": found, "unseen": unseen[:UNSEEN_MAX], "skipped": skipped,
            "chat": _audit_chat(found)}
