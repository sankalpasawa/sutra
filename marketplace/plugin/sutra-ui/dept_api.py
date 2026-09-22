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
from datetime import datetime
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
#: The four words a rule may wear (A10). The charter's own `rules` carry one of
#: these; invariants and constraints can only ever be `always` (DS-1).
RULE_TAGS = ("go", "ask", "refuse", "always")
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
    ONLY charter reading this screen does.

    DS-2 (2026-09-21) adds one clause: a `role` charter is never the fallback.
    It speaks for a PERSON, not for the department, so a department whose only
    charter is a role has no goal -- which is true, and is what Identity says.
    A role belongs under People and nowhere else."""
    try:
        views = [v for v in (E.charter_view(c) for c in E.charters_for(ref)) if v]
    except Exception:
        return None
    sup = E.superseded_ids() if hasattr(E, "superseded_ids") else {}
    active = [v for v in views
              if v.get("status", "active") != "retired" and v.get("id") not in sup
              and str(v.get("kind") or "") != ROLE_KIND]
    if not active:
        return None
    return next((v for v in active if v.get("kind", "standing") == "standing"), active[0])


def _done_line(charter: Optional[Dict[str, Any]]) -> Optional[str]:
    """When the department is done.

    Two records, in order. The charter's OWN `done_when` lines first (DS-1,
    2026-09-21: the sidecar field the charter sheet writes and the org.charter
    proposal applies) -- that is the department saying it in its own words.
    When none is written, the milestones' per-milestone `done_when` lines, the
    only place the answer lived before (F-1). Nothing when both are empty."""
    if not charter:
        return None
    parts = [s for s in (_sentence(x) for x in (charter.get("done_when") or [])) if s]
    if not parts:
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
    """The department's rules, each tagged go / ask / refuse / always (A10).

    Two records, in order, and the first one that carries anything wins:

      1. the charter's own `rules` (DS-1, 2026-09-21) -- `[{tag, line}]` on the
         sidecar, written through the org.charter proposal. These carry a REAL
         tag, so a refuse reads as a refuse;
      2. otherwise `invariants` and `constraints` from the body, tagged
         `always` -- things that hold at all times, which is the only honest
         tag for them (F-1, F-13). This route never guesses one of the other
         three for a line that was not written with it.
    """
    if not charter:
        return []
    out = []
    for item in (charter.get("rules") or []):
        if not isinstance(item, dict):
            continue
        text = _text(item.get("line") or item.get("text"))
        tag = str(item.get("tag") or "always").strip().lower()
        if text and tag in RULE_TAGS:
            out.append({"tag": tag, "text": text})
    if out:
        return out[:RULES_MAX]
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


# ----------------------------------------------------------------- TEMPLATES --
# Slice I (DS-8, DS-9): which template each of the five functions runs in this
# department, and what else each function could run. Reads the repository
# folder and the picks file only (function_templates.py); the one writer of a
# pick is the approved org.template ask, applied in org2_apply.

@router.get("/{ref}/functions")
def functions(ref: str):
    """The picked template per function (the Default where none was picked)
    and every template of each function, as picker rows."""
    import function_templates as FT
    _domain(ref)
    picked = FT.picked(ref)
    out = {"picked": {}, "templates": {}}
    for fn in FT.FUNCTIONS:
        t = FT.get(picked[fn])
        out["picked"][fn] = FT.card(t) if t else None
        out["templates"][fn] = [FT.card(x) for x in FT.templates(fn)]
    return out


@router.get("/{ref}/functions/{function}/brief")
def function_brief(ref: str, function: str):
    """The picked template's chat brief, unfilled, for the card to fill from
    the Identity read it already holds (LLD-FUNCTIONS section 4)."""
    import function_templates as FT
    _domain(ref)
    fn = str(function or "").strip().lower()
    if fn not in FT.FUNCTIONS:
        raise HTTPException(status_code=404, detail="no function %s" % function)
    t = FT.get(FT.picked(ref)[fn]) or FT.get(FT.default_id(fn))
    if not t:
        raise HTTPException(status_code=404, detail="no template for %s" % fn)
    return {"template": FT.card(t), "brief": t.get("chat_brief") or "", "cwd": _dept_cwd(ref)}


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
        "births": _births(cwd),
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
        "births": _births(cwd),
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


# ------------------------------------------------------------------- ENGINES --
# R9-R12. The routines whose working folder falls under the department: what
# each one is, what it has done, what it filed, and the ONE ask this screen
# files of its own.
#
# The state WORD is derived, because no record carries one. A routine stores
# `enabled`, and while a run is in flight routines.py leaves a lock directory
# beside that run's folder (routines.py:566). Those two answer Paused, Running
# and Idle between them, and neither is written from here (PRD F-8).
#
# DRIFT from BUILD-PLAN reuse row 12 / S49, stated rather than hidden:
# routines.state() is NOT called. It writes a `.heartbeat` file into the routine
# store (routines.py:1246-1251) and shells `launchctl list` once per routine
# (routines.py:901-914) -- a read route may do neither, and a screen that paints
# on every render may afford neither. The readers state() itself composes --
# list_ids(), load(), runs() -- are called instead, so nothing is
# re-implemented, nothing is shelled out to, and nothing is written.

ENGINES_MAX = 24
RUNS_LIMIT = 10                              # run rows per read, newest first
RUNS_LIMIT_MAX = 50
ENGINE_FILED_MAX = 24
MAKES_MAX = 4                                # names on the Makes / Needs line
STEPS_MAX = 24                               # steps read off a registered workflow
#: A23: a routine minted by an approved ask is saved in the same moment the ask
#: is decided, and NO record links the two. The match is therefore the two
#: stamps landing inside this window -- far longer than the write takes, far
#: shorter than the gap between two separate decisions.
BIRTH_WINDOW_MS = 60 * 1000
#: Splits a stored string into the words a record can be named by. A routine id
#: and a workflow id are both `word-with-dashes`, so dots, dashes and
#: underscores are part of a word here and everything else is a boundary.
_WORDS = re.compile(r"[^A-Za-z0-9_.-]+")
#: What a run row's own two words become on screen. Anything the record says
#: that is not in here is shown as the record's own word rather than guessed at.
RUN_OUTCOMES = {"ok": "Done", "failed": "Failed", "timeout": "Ran out of time",
                "skipped": "Skipped"}
RUN_DOTS = {"ok": "ok", "failed": "block", "timeout": "block", "skipped": "warn"}
RUN_TRIGGERS = {"schedule": "On the schedule", "manual": "By hand"}


def _ms_iso(value: Any) -> int:
    """An ISO stamp as milliseconds, 0 when the record carries none or carries
    something that is not one. Both stores this reads write `now_iso()`
    (routines.py:161, proposals.py:78), which carries its own offset."""
    text = _text(value)
    if not text:
        return 0
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except (TypeError, ValueError, OverflowError, OSError):
        return 0


def _tokens(text: Any) -> set:
    return {w for w in _WORDS.split(_text(text)) if w}


def _runs_root() -> str:
    """Where routines.py keeps its run folders, asked of routines.py."""
    try:
        import routines
        return str(routines.runs_dir())
    except Exception:
        return ""


def _last_run(rid: str) -> Dict[str, Any]:
    """The newest run row, or {}. routines.runs() is the reader (reuse row 13);
    a store that was never written is an empty row, never an error."""
    try:
        import routines
        rows = routines.runs(rid, limit=1).get("runs") or []
    except Exception:
        return {}
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def _engine_state(rid: str, rec: Dict[str, Any], runs_root: str) -> str:
    """Paused, Running or Idle, in that order of precedence: a paused engine
    that left a stale lock behind is paused, not running."""
    if not bool(rec.get("enabled", True)):
        return "paused"
    if runs_root and os.path.isdir(os.path.join(runs_root, rid, ".lock")):
        return "running"
    last = _last_run(rid)
    if last.get("started_at") and not last.get("ended_at"):
        return "running"
    return "idle"


def _engine_name(rid: str, rec: Dict[str, Any]) -> str:
    """A NAME for an engine. The record's `description` is free text and some
    of them are a paragraph long, so it goes through the same clip every other
    name on this screen goes through (_label, org2_api's rule) rather than
    running off the row."""
    return _label(rec.get("description")) or rid


def _cadence(rec: Dict[str, Any]) -> str:
    """When it runs, in the record's own sentence. routines.py writes that
    sentence onto the record at save time (routines.py:304-326) precisely so it
    reads correctly outside the app; it is passed through, never re-phrased."""
    sched = rec.get("schedule")
    return _text(sched.get("human")) if isinstance(sched, dict) else ""


def _workflows() -> List[Dict[str, Any]]:
    """The workflows registered in the user kit, as the registry stores them
    (`<registry>/workflows/W-*.json`). No kit, an unreadable file or a file
    that is not a workflow is simply not a workflow -- never an error."""
    out: List[Dict[str, Any]] = []
    folder = os.path.join(E.HOME or "", "workflows")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        if not (name.startswith("W-") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or not _text(rec.get("id")):
            continue
        steps = []
        for s in (rec.get("steps") or [])[:STEPS_MAX]:
            if not isinstance(s, dict):
                continue
            steps.append({
                "id": _text(s.get("id")),
                "name": _text(s.get("name")) or _text(s.get("id")),
                "produces": [_text(p) for p in (s.get("produces") or []) if _text(p)],
                "needs": [_text(p) for p in (s.get("needs") or s.get("inputs") or [])
                          if _text(p)],
                "verify": _text(s.get("verify")),
            })
        out.append({"id": _text(rec.get("id")), "title": _text(rec.get("title")),
                    "goal": _text(rec.get("goal")), "steps": steps})
    return out


def _workflow_for(rid: str, rec: Dict[str, Any],
                  flows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The registered workflow an engine runs, when it runs one.

    No routine record references a workflow (PRD F-8). The only honest join is
    the engine's own instruction NAMING one, which is how the natural-language
    table in CLAUDE.md fires them, plus the case where the two carry the same
    id. Anything looser would put another engine's steps on this card."""
    if not flows:
        return None
    named = _tokens(rec.get("prompt"))
    for flow in flows:
        if flow["id"] == rid or flow["id"] in named:
            return flow
    return None


def _filed_by_engine(ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """{engine id: the work its runs filed, newest first}.

    A placement carries no run reference either; what it carries is `origin`,
    a free string the filer writes. A placement is this engine's when its
    origin NAMES the engine -- the engine's id as a whole word, never a
    substring, so `audit` cannot claim `governance-audit-daily`'s rows."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    wanted = {rid for rid in ids if rid}
    if not wanted:
        return out
    try:
        places = E.all_placements()
    except Exception:
        return out
    for p in places:
        if not isinstance(p, dict):
            continue
        hit = wanted & _tokens(p.get("origin"))
        if not hit:
            continue
        row = {"id": _text(p.get("id")),
               "label": _label((p.get("work_ref") or {}).get("id")),
               "ts_ms": _int(p.get("ts_ms")), "row": p}
        for rid in hit:
            out.setdefault(rid, []).append(row)
    for rid in list(out):
        out[rid].sort(key=lambda r: -(r["ts_ms"] or 0))
        out[rid] = out[rid][:ENGINE_FILED_MAX]
    return out


def _routine_creates() -> List[Dict[str, Any]]:
    """Every ask that ever asked for an engine to exist."""
    try:
        import proposals
        rows = proposals.listing()
    except Exception:
        return []
    return [r for r in rows
            if isinstance(r, dict) and r.get("kind") == "routine.create"]


def _birth(rid: str, rec: Dict[str, Any],
           creates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A23 / F-10: where the engine came from. `from_ask` when an approved
    routine.create was decided in the same minute the record was written; an
    ask that names another engine is never the match."""
    made = _ms_iso(rec.get("created_at"))
    for p in creates:
        args = p.get("args") if isinstance(p.get("args"), dict) else {}
        result = p.get("result") if isinstance(p.get("result"), dict) else {}
        for named in (_text(args.get("id")), _text(result.get("routine"))):
            if named and named != rid:
                break
        else:
            decided = _ms_iso(p.get("decided_at"))
            if made and decided and abs(made - decided) <= BIRTH_WINDOW_MS:
                return {"from_ask": True, "at": _text(rec.get("created_at")),
                        "at_ms": made}
    return {"from_ask": False, "at": _text(rec.get("created_at")), "at_ms": made}


def _engines_under(cwd: Optional[str]) -> List[Any]:
    """Every engine whose folder falls inside the department's, by name."""
    if not cwd:
        return []
    rows = [(rid, rec) for rid, rec in _routine_rows().items()
            if _under(cwd, rec.get("cwd"))]
    rows.sort(key=lambda x: (_text(x[1].get("description")).lower(), x[0]))
    return rows[:ENGINES_MAX]


def _engine_row(rid: str, rec: Dict[str, Any], runs_root: str,
                flows: List[Dict[str, Any]],
                filed: Dict[str, List[Dict[str, Any]]],
                creates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One engine, as the list row and the Engine tab both read it (A18, A19).

    `makes` prefers what the engine's runs actually filed over what its
    workflow says it will produce -- evidence before declaration -- and falls
    back to the declaration when nothing has been filed. `read_by` is None
    always: no record anywhere names who reads an engine's output, so the card
    says so in one quiet line rather than inventing a reader (PRD F-8)."""
    flow = _workflow_for(rid, rec, flows)
    steps = (flow or {}).get("steps") or []
    makes = [f["label"] for f in (filed.get(rid) or []) if f["label"]][:MAKES_MAX]
    if not makes:
        makes = [p for s in steps for p in s["produces"]][:MAKES_MAX]
    needs = [n for s in steps for n in s["needs"]][:MAKES_MAX]
    return {
        "id": rid,
        "name": _engine_name(rid, rec),
        "state": _engine_state(rid, rec, runs_root),
        "enabled": bool(rec.get("enabled", True)),
        "cwd": _norm(rec.get("cwd")),
        "runs_as": _text(rec.get("model")),
        "cadence": _cadence(rec),
        "made_by": _birth(rid, rec, creates),
        "needs": needs or None,
        "makes": makes or None,
        "read_by": None,
        "workflow": flow,
        "prompt": _text(rec.get("prompt")),
    }


@router.get("/{ref}/engines")
def engines(ref: str):
    """R9: every engine that runs in this department's folder, each with the
    state word its records add up to."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    rows = _engines_under(cwd)
    runs_root = _runs_root()
    flows = _workflows()
    filed = _filed_by_engine([rid for rid, _rec in rows])
    creates = _routine_creates()
    return {"engines": [_engine_row(rid, rec, runs_root, flows, filed, creates)
                        for rid, rec in rows]}


def _engine(ref: str, eid: str) -> Dict[str, Any]:
    """The engine record, or 404. An id that does not fall under this
    department is not this department's to read (LLD R10-R12): the ref in the
    path is the scope, and an engine outside it answers the same way an unknown
    department does."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    rec = _routine_rows().get(eid)
    if not rec or not _under(cwd, rec.get("cwd")):
        raise HTTPException(status_code=404, detail="no engine %s here" % eid)
    return rec


def _run_line(row: Dict[str, Any]) -> str:
    """One run in a sentence: what started it, and how it ended."""
    trigger = _text(row.get("trigger"))
    start = RUN_TRIGGERS.get(trigger, trigger.capitalize() or "Started")
    if row.get("started_at") and not row.get("ended_at"):
        return "%s: running." % start
    outcome = _text(row.get("outcome"))
    word = RUN_OUTCOMES.get(outcome, outcome.capitalize() or "Done")
    detail = _text(row.get("reason")) or _text(row.get("detail"))
    return ("%s: %s." % (start, word.lower())) + (" " + _clip(detail) if detail else "")


def _runs_chat(name: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What the engine reported, newest first, as the exchange it is: the
    engine tells Coordination how each run went. The run row itself is what
    the Exact tab shows."""
    return [_turn(name, "Coordination", "say", _run_line(r),
                  _at(r, "started_at"), r) for r in rows][:CHAT_MAX]


@router.get("/{ref}/engines/{eid}/runs")
def engine_runs(ref: str, eid: str, limit: int = RUNS_LIMIT):
    """R10: one engine's run rows, department-scoped. routines.runs() is the
    reader and its answer is passed through (reuse row 13); the only thing
    added is the chat those same rows make."""
    rec = _engine(ref, eid)
    try:
        want = int(limit)
    except (TypeError, ValueError):
        want = RUNS_LIMIT
    want = max(1, min(want, RUNS_LIMIT_MAX))
    try:
        import routines
        out = dict(routines.runs(eid, limit=want))
    except Exception:
        out = {"id": eid, "total": 0, "runs": [], "unreadable": 0, "never_run": True}
    rows = [r for r in (out.get("runs") or []) if isinstance(r, dict)]
    out["runs"] = rows
    out["chat"] = _runs_chat(_engine_name(eid, rec), rows)
    return out


@router.get("/{ref}/engines/{eid}/data")
def engine_data(ref: str, eid: str):
    """R11: the work this engine's runs filed. Nothing filed is an empty
    list, which the card reads as one quiet line (A21)."""
    _engine(ref, eid)
    return {"filed": _filed_by_engine([eid]).get(eid) or []}


@router.post("/{ref}/engines/{eid}/pause")
def engine_pause(ref: str, eid: str):
    """R12: the only write this screen has, and it writes an ASK.

    proposals.create() records the intent and applies nothing (proposals.py:111);
    `enabled` is untouched until the ask is stamped in Approvals, and only then
    does the state word change (A22). Nothing here calls routines.update."""
    rec = _engine(ref, eid)
    if not bool(rec.get("enabled", True)):
        raise HTTPException(status_code=400, detail="already paused")
    summary = "Pause %s" % _engine_name(eid, rec)
    try:
        import proposals
        row = proposals.create("routine.update",
                               {"id": eid, "patch": {"enabled": False}},
                               summary, session_id="dept")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"proposal": row, "summary": summary}


# ---------------------------------------------------------------- FILED WORK --
# R13. What this department has filed, and every version of each one.
#
# A placement is never edited. Re-filing the same work item -- a charter
# amendment, a re-home, a second pass over the same file -- writes a NEW
# placement whose `supersedes` names its predecessor (placement_engine.py:941).
# That chain IS the version history, and walking it is the only way to count
# versions: no row carries a number, and org2_api._filed (which this adapts --
# that helper is module-private there) drops the chain entirely.
#
# The row `id` is the WORK item's id, exactly as org2_api._filed writes it, so
# the department screen's Filed work rows and the Org screen's are the same
# rows under the same key; the placement's own id rides beside it.

FILED_MAX = 200                              # filed rows per department, newest first
VERSIONS_MAX = 24                            # versions walked back per work item
#: A24: the three words a version can carry, derived from TWO fields because no
#: record carries a state of its own. A row that some other row names in
#: `supersedes` is RETIRED. An unsuperseded row is the version in force, and
#: `phase` says whether the work it was filed for has closed: `post-close`
#: means it has (in use), anything else means it has not (waits).
#:
#: DRIFT, stated rather than hidden: placement_engine writes exactly two phases
#: (`pre-flight` at line 920, `post-close` at 1615/1773/1895/1969/2979), but a
#: third, `open`, sits on 87 rows of this machine's store, written by a filer
#: outside the engine. Those read `waits` too -- not because `open` was mapped,
#: but because the record does not say the work closed, and inventing the word
#: "in use" for a phase the engine does not define would be a guess.
PHASE_IN_USE = "post-close"
#: An ask a person SAW is one they answered. `expired` is not here: a window
#: that closed on its own was never looked at (proposals.py:144-146).
SEEN_STATUSES = ("approved", "rejected", "failed")
SEEN_MAX = 24
#: A25 / F-14, closed 2026-09-21 (DS-2): `role` is a charter kind the engine
#: accepts and the org.charter proposal writes. `unfilled` is what a role
#: charter's `person` says when nobody holds it -- a fact, not a blank.
ROLE_KIND = "role"
ROLE_UNFILLED = "unfilled"


def _placement_index(places: List[Any]):
    """({placement id: its row}, {placement ids some other row supersedes}).

    One pass over the whole log, because both answers need the whole log: the
    chain walks backwards by id, and "retired" is DERIVED from another row
    naming this one -- the same rule `superseded_ids()` applies to charters
    (placement_engine.py:2530), applied to placements."""
    by_id: Dict[str, Dict[str, Any]] = {}
    superseded = set()
    for p in places:
        if not isinstance(p, dict):
            continue
        pid = _text(p.get("id"))
        if pid:
            by_id[pid] = p
        sup = _text(p.get("supersedes"))
        if sup:
            superseded.add(sup)
    return by_id, superseded


def _current_rows(places: List[Any], superseded: set) -> List[Dict[str, Any]]:
    """The CURRENT row per work item, through the engine's own index.

    `_current_placements()` is org2_api._placements_now's reader too; when it
    cannot be read, an unsuperseded row IS the current one, which is the same
    answer (3,329 rows on this machine, 553 superseded, 2,776 current)."""
    fn = getattr(E, "_current_placements", None)
    if callable(fn):
        try:
            return [p for p in fn() if isinstance(p, dict)]
        except Exception:
            pass
    return [p for p in places if isinstance(p, dict)
            and _text(p.get("id")) not in superseded]


def _version_chain(pid: str, by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A placement and every row it supersedes, newest first. A chain that
    loops back on itself, or that names a row this store does not hold, stops
    there rather than spinning or guessing at a missing version."""
    out: List[Dict[str, Any]] = []
    seen = set()
    cur = by_id.get(pid)
    while isinstance(cur, dict):
        cid = _text(cur.get("id"))
        if not cid or cid in seen or len(out) >= VERSIONS_MAX:
            break
        seen.add(cid)
        out.append(cur)
        nxt = _text(cur.get("supersedes"))
        cur = by_id.get(nxt) if nxt else None
    return out


def _version_state(p: Dict[str, Any], superseded: set) -> str:
    if _text(p.get("id")) in superseded:
        return "retired"
    return "in use" if _text(p.get("phase")) == PHASE_IN_USE else "waits"


def _version_row(p: Dict[str, Any], superseded: set,
                 domains: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """One version. `made_by` is the filer's own word for itself (`origin`:
    matched, backfilled, hook), read as a NAME like every other name on this
    screen. `read_by` is None always -- no record anywhere names who reads a
    filed item, the same gap the engine card states (PRD F-8) -- so the card
    says so in one quiet line instead of inventing a reader."""
    return {
        "id": _text(p.get("id")),
        "state": _version_state(p, superseded),
        "made_by": _label(p.get("origin")),
        "read_by": None,
        "charter_id": _text(p.get("charter_id")),
        "where": _dept_name(p.get("domain_ref"), domains),
        "ts_ms": _int(p.get("ts_ms")),
        "row": p,
    }


@router.get("/{ref}/filed")
def filed(ref: str):
    """R13: the work filed under this department, each with its versions."""
    domains = _domain(ref)
    try:
        places = E.all_placements()
    except Exception:
        return {"filed": []}
    by_id, superseded = _placement_index(places)
    rows = []
    for p in _current_rows(places, superseded):
        if p.get("domain_ref") != ref:
            continue
        wr = p.get("work_ref") or {}
        chain = _version_chain(_text(p.get("id")), by_id)
        rows.append({
            "id": _text(wr.get("id")),
            "label": _label(wr.get("id")),
            "kind": _text(wr.get("kind")),
            "versions": len(chain) or 1,
            "placement_id": _text(p.get("id")),
            "charter_id": _text(p.get("charter_id")),
            "ts_ms": _int(p.get("ts_ms")),
            "history": [_version_row(q, superseded, domains) for q in chain],
        })
    rows.sort(key=lambda r: -(r["ts_ms"] or 0))
    return {"filed": rows[:FILED_MAX]}


# -------------------------------------------------------------------- PEOPLE --
# R14. Who answers for this department: the owner, and then the people the
# department names in its own right.
#
# F-12: `authority` is `{}` on every charter on disk, so the owner is the same
# one Identity resolves (component 3's rule, reused here rather than re-derived)
# and what that person's record says they STAMP is honestly nothing.
# F-14: a person of their own is a charter of kind `role`, and no charter
# carries that kind today (the store holds `standing` and `project` only), so
# the list is the owner alone until one is written -- read, never assumed.
# F-13's twin: NO proposal row names who decided it (proposals.py:189 writes
# `decided_at` and nothing else). The asks a person SAW are therefore the
# department's answered asks, attributed by exactly the rule Identity's owner
# chat already ships (`_owner_chat`): this department has one owner, and its
# asks were put to them.


def _stamps(charter: Optional[Dict[str, Any]]) -> str:
    """What this person's own record says is theirs to answer.

    For the owner that is the `authority` field, which is `{}` everywhere
    (F-12), so the answer is "" and the card shows its quiet line. For a role
    charter it is that charter's purpose -- the scope it was written to hold."""
    if not charter:
        return ""
    a = charter.get("authority")
    if isinstance(a, dict):
        for k in ("scope", "stamps", "decides", "covers"):
            if isinstance(a.get(k), str) and a[k].strip():
                return " ".join(a[k].split())
    return ""


def _seen_rows(props: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The asks that were answered here, newest answer first."""
    out = []
    for rec in props:
        status = str(rec.get("status") or "")
        if status not in SEEN_STATUSES:
            continue
        out.append({"id": rec.get("id"), "summary": _text(rec.get("summary")),
                    "answer": ANSWERS.get(status, ""), "at": _at(rec, "decided_at"),
                    "at_ms": _ms_iso(rec.get("decided_at")), "row": rec})
    out.sort(key=lambda r: -(r["at_ms"] or 0))
    return out[:SEEN_MAX]


def _roles(ref: str) -> List[Dict[str, Any]]:
    """The people this department names of its own: charters of kind `role`,
    active and not superseded (DS-2, 2026-09-21).

    The NAME is the role charter's own `person` -- the sidecar field the
    org.charter proposal writes -- and `unfilled` is a real answer, not a
    missing one: the role exists and nobody holds it. Only when no person is
    named at all does the card fall back to the charter's authority field and
    then to the role's title, so a row always has something to call itself.
    What the person runs is the role's purpose line."""
    try:
        views = [v for v in (E.charter_view(c) for c in E.charters_for(ref)) if v]
    except Exception:
        return []
    sup = E.superseded_ids() if hasattr(E, "superseded_ids") else {}
    out = []
    for v in views:
        if str(v.get("kind") or "") != ROLE_KIND:
            continue
        if v.get("status", "active") == "retired" or v.get("id") in sup:
            continue
        title = _text(v.get("title"))
        person = _text(v.get("person"))
        out.append({"charter_id": _text(v.get("id")), "title": title,
                    "name": person or _authority_name(v) or title,
                    "person": person,
                    "unfilled": person == ROLE_UNFILLED,
                    "stamps": _stamps(v) or _text(v.get("purpose")), "seen": []})
    out.sort(key=lambda r: (r["title"].lower(), r["charter_id"]))
    return out


@router.get("/{ref}/people")
def people(ref: str):
    """R14: the owner first, then the role charters (A25)."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    charter = _standing_charter(ref)
    owner = dict(_owner(charter, cwd))
    owner["stamps"] = _stamps(charter)
    owner["seen"] = _seen_rows(_dept_proposals(ref, domains, cwd))
    return {"owner": owner, "roles": _roles(ref)}


# -------------------------------------------------------------------- METERS --
# R15. What the department did this calendar month, and where each engine
# stands -- the last two readings the locked screen asks for.
#
# NOTHING stores a meter (PRD F-7, S10). Every reading below is COUNTED on each
# read off two stores this router already has: the engines' run rows and the
# department's own proposals. Three consequences, all of them deliberate:
#
#   1. A reading with no row behind it is NOT a zero. A department whose
#      engines never ran has no runs meter at all, and the card says "No
#      reading yet" (A27) rather than drawing an empty bar that would read as
#      "we did nothing this month".
#   2. The bar's ceiling is the department's OWN busiest month on record. No
#      record anywhere carries a target for runs, asks or refuses, so "busy or
#      quiet, for us" is the only thing a bar can honestly say -- and it says
#      it without printing a number (A28).
#   3. `Fit` is named by the locked screen's meter lines ("rules and slice
#      under 60% of a prompt") and has NO record anywhere: nothing measures how
#      much of an engine's instruction its rules take. It therefore never
#      carries a dot. Stated here rather than computed from something else that
#      happens to be a number.

METER_RUNS_LIMIT = 500       # run rows read per engine when counting a month
METER_MONTHS = 36            # months of history a ceiling may be looked for in
BIRTHS_MAX = 8               # birth lines per card
#: A13's own rule, reused: three asks of a kind is what this screen already
#: calls a lot, so it is where an engine's Asks meter turns.
METER_ASK_WARN = PATTERN_MIN
#: The locked screen's own meter line: spend under 40% of the budget.
METER_SPEND_WARN = 0.4
METER_LABELS = (("runs", "Runs"), ("asks", "Asks"),
                ("refuses", "Refuses"), ("spend", "Spend"))


def _month_of(ms: Any) -> str:
    """The calendar month a stamp falls in, local time (PRD F-2)."""
    n = _int(ms)
    if not n:
        return ""
    try:
        return time.strftime("%Y-%m", time.localtime(n / 1000.0))
    except (OverflowError, OSError, ValueError):
        return ""


def _add(buckets: Dict[str, float], ms: Any, amount: float = 1.0) -> None:
    """One row into its month's bucket. A row with no readable stamp belongs to
    no month and is counted nowhere -- it would otherwise land in whichever
    month the fallback picked and quietly inflate it."""
    key = _month_of(ms)
    if key:
        buckets[key] = buckets.get(key, 0.0) + amount


def _meter(key: str, label: str, buckets: Dict[str, float], month: str) -> Dict[str, Any]:
    """One bar: this month, and the biggest month on record beside it."""
    months = sorted(buckets)[-METER_MONTHS:]
    value = float(buckets.get(month) or 0.0)
    peak = max([buckets[m] for m in months] + [value]) if months else value
    return {"key": key, "label": label, "reading": bool(months),
            "value": round(value, 4), "of": round(peak, 4)}


def _engine_runs(rid: str) -> List[Dict[str, Any]]:
    """A month of one engine's run rows, through routines.runs() as every other
    run read on this screen goes (reuse row 13)."""
    try:
        import routines
        rows = routines.runs(rid, limit=METER_RUNS_LIMIT).get("runs") or []
    except Exception:
        return []
    return [r for r in rows if isinstance(r, dict)]


def _cost(row: Dict[str, Any]) -> Optional[float]:
    """What a run cost, when the row carries it. routines.py writes `cost_usd`
    off the model's own total (routines.py:645, 732); a row without one is not
    a free run, it is an unmeasured one, and returns None."""
    v = row.get("cost_usd")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _engine_meters(rid: str, rec: Dict[str, Any], rows: List[Dict[str, Any]],
                   ask_ids: List[str], month: str) -> List[Dict[str, str]]:
    """The meters a record can answer for ONE engine, as dots (A27).

    Only the answerable ones are returned, so a card with nothing to read shows
    its one quiet line rather than four grey dots that look like readings. Fit
    is never here -- see this section's note 3."""
    out: List[Dict[str, str]] = []
    mine = [r for r in rows if _month_of(_ms_iso(r.get("started_at"))) == month]
    if mine:
        outcomes = {_text(r.get("outcome")) for r in mine}
        dot = "block" if "failed" in outcomes else (
            "warn" if "timeout" in outcomes else "ok")
        out.append({"key": "tick", "label": "Tick", "dot": dot})
    asked = len([a for a in ask_ids if a == rid])
    if mine or asked:
        out.append({"key": "asks", "label": "Asks",
                    "dot": "warn" if asked >= METER_ASK_WARN else "ok"})
    costs = [c for c in (_cost(r) for r in mine) if c is not None]
    opts = rec.get("opts") if isinstance(rec.get("opts"), dict) else {}
    ceiling = opts.get("max_budget_usd")
    if costs and isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool) \
            and float(ceiling) > 0:
        share = sum(costs) / (float(ceiling) * len(costs))
        out.append({"key": "spend", "label": "Spend",
                    "dot": "warn" if share >= METER_SPEND_WARN else "ok"})
    return out


def _births(cwd: Optional[str]) -> List[Dict[str, Any]]:
    """Every engine here that an ask brought into being, newest first (A23).

    The match is slice D's `_birth` and nothing looser -- the two stamps inside
    one minute -- so an engine somebody wrote by hand is never called born."""
    creates = _routine_creates()
    out = []
    for rid, rec in _engines_under(cwd):
        b = _birth(rid, rec, creates)
        if not b.get("from_ask"):
            continue
        out.append({"id": rid, "name": _engine_name(rid, rec),
                    "at": b.get("at"), "at_ms": b.get("at_ms")})
    out.sort(key=lambda r: -(r["at_ms"] or 0))
    return out[:BIRTHS_MAX]


@router.get("/{ref}/meters")
def meters(ref: str):
    """R15: runs, asks, refuses and spend for the calendar month, and the same
    question asked of each engine (A27)."""
    domains = _domain(ref)
    cwd = _dept_cwd(ref, domains)
    month = _month_of(int(time.time() * 1000))
    props = _dept_proposals(ref, domains, cwd)
    asks: Dict[str, float] = {}
    refuses: Dict[str, float] = {}
    ask_ids: List[str] = []
    for rec in props:
        _add(asks, rec.get("created_ms"))
        args = rec.get("args") if isinstance(rec.get("args"), dict) else {}
        if _month_of(rec.get("created_ms")) == month:
            ask_ids.append(_text(args.get("id")))
        if str(rec.get("status") or "") == "rejected":
            _add(refuses, _ms_iso(rec.get("decided_at")) or _int(rec.get("created_ms")))
    runs: Dict[str, float] = {}
    spend: Dict[str, float] = {}
    per_engine = []
    for rid, rec in _engines_under(cwd):
        rows = _engine_runs(rid)
        for r in rows:
            started = _ms_iso(r.get("started_at"))
            _add(runs, started)
            cost = _cost(r)
            if cost is not None:
                _add(spend, started, cost)
        per_engine.append({"id": rid, "name": _engine_name(rid, rec),
                           "meters": _engine_meters(rid, rec, rows, ask_ids, month)})
    buckets = {"runs": runs, "asks": asks, "refuses": refuses, "spend": spend}
    return {
        "month": month,
        "meters": [_meter(k, label, buckets[k], month) for k, label in METER_LABELS],
        "runs": int(runs.get(month) or 0),
        "asks": int(asks.get(month) or 0),
        "refuses": int(refuses.get(month) or 0),
        "spend_usd": round(float(spend.get(month) or 0.0), 4) if spend else None,
        "engines": per_engine,
    }
