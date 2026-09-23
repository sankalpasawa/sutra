"""The Library: the kinds a department is built from, read in one place.

A PROJECTION, like dept_api.py. Every row here already exists somewhere else --
a template file, a routine record, a line in the work-atom ledger -- and this
module only arranges them into shelves. It has NO writer: picking from a shelf
leaves through the proposal path the department card already uses
(org2_api's org.template request), so there is one write path and one audit
trail. test_library_api.py greps this file for writers and fails if one
appears.

Shape (LLD, holding/plans/library-program/LLD.md):

    GET /api/library/ping
    GET /api/library/shelves                     every shelf + counts
    GET /api/library/shelf/{id}                  {head, about, list}
    GET /api/library/shelf/{id}/item/{item_id}   one row opened

`about` is {ways, settings, parts}; `list` is {tag_label, tags, rows}. A row
carries its own tags, so the browser filters what it already holds (LIB-5).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # same guard dept_api uses
    sys.path.insert(0, HERE)

import function_templates as FT  # noqa: E402

router = APIRouter(prefix="/api/library", tags=["library"])

FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")

#: One line per function, in the words the screen uses (Native terms, D78).
FUNCTION_LINE = {
    "identity": "What a department is for, and what it may do.",
    "adaptation": "How a department changes itself when what it meets changes.",
    "priority": "What a department does next, and why that before the rest.",
    "coordination": "How a department works with the ones around it.",
    "audit": "What proves a department did what it said it would.",
}

#: The seven shelves. Two groups: the five functions, then the parts (LIB-1).
SHELVES = (
    ("identity", "Identity", "Function", "functions"),
    ("adaptation", "Adaptation", "Function", "functions"),
    ("priority", "Priority", "Function", "functions"),
    ("coordination", "Coordination", "Function", "functions"),
    ("audit", "Audit", "Function", "functions"),
    ("engines", "Engines", "Part", "parts"),
    ("work-atom", "Work atom", "Part", "parts"),
)

#: The second tab is named for what it lists (LIB-3, open founder call).
LIST_TAB = {"engines": "Engines", "work-atom": "Skills"}

# ── the ways one is made ────────────────────────────────────────────────────
# Each way says what you do and what LANDS, and every "lands" line names a
# real path: an ask the owner stamps, or the record read at the next paint.

FUNCTION_WAYS = [
    {"name": "From a ready-made one",
     "does": "Pick one in the next tab and name the department.",
     "lands": "Lands as an ask you stamp; the department runs on it from the next effect."},
    {"name": "In the function's chat",
     "does": "Say what it should do. The chat writes the fields it changed.",
     "lands": "Lands as an ask you stamp, one per field."},
    {"name": "From the department above",
     "does": "Starts as the parent's, then tightened for this one.",
     "lands": "May add or tighten, never loosen what the parent set."},
    {"name": "Empty",
     "does": "The base floor and nothing else, filled in as the department runs.",
     "lands": "Runs on Default until something else is picked."},
]

ENGINE_WAYS = [
    {"name": "From work that repeated",
     "does": "Adaptation sees the same work atom three times and proposes the engine.",
     "lands": "Lands as an ask carrying the runs it came from."},
    {"name": "From a ready-made one",
     "does": "Pick one in the next tab, name the folder and the moment it fires.",
     "lands": "Lands as an ask, then runs on its own schedule."},
    {"name": "In any chat",
     "does": "Ask for it in words. The chat files the engine and its check.",
     "lands": "Lands as an ask; nothing runs before it is stamped."},
    {"name": "By hand",
     "does": "Write the record in the department's folder.",
     "lands": "Shows on the department's card at the next read."},
]

WORK_ATOM_WAYS = [
    {"name": "You write it",
     "does": "In Now, or in the department. A goal and the check that ends it.",
     "lands": "Opens at once. Your own work needs no stamp."},
    {"name": "Priority proposes it",
     "does": "The function reads the done line against what is filed and names the gap.",
     "lands": "Lands next on the list, with the reason it was ordered there."},
    {"name": "An engine opens one",
     "does": "Every run opens its own, so a run can be counted rather than claimed.",
     "lands": "Closes when the run's check flips, and links to what changed."},
    {"name": "A chat opens one",
     "does": "Before a chat changes anything it opens one saying what it is about to do.",
     "lands": "Closes on the check it declared, not on the chat saying it is done."},
]

# ── what governs the making ─────────────────────────────────────────────────
# Every setting here is a rule the code actually enforces, with where it lives.

FUNCTION_SETTINGS = [
    {"name": "Starts on", "decides": "Which one a new department runs on before anybody picks",
     "now": "Default", "source": "function_templates.picked"},
    {"name": "Always derive", "decides": "A department writes its own child even when it changes nothing",
     "now": "on", "source": "the builders law (A13)"},
    {"name": "May loosen", "decides": "Whether a child can drop a line the one above it set",
     "now": "off", "source": "test_function_templates narrowing"},
    {"name": "Who stamps", "decides": "Who has to say yes before a pick takes effect",
     "now": "the owner", "source": "org2_api request check"},
    {"name": "Changing one", "decides": "Whether a pick is an ask or takes effect at once",
     "now": "an ask", "source": "org.template proposal"},
]

ENGINE_SETTINGS = [
    {"name": "Starts", "decides": "Whether a new engine is on the moment it is stamped",
     "now": "off", "source": "the routine record's enabled field"},
    {"name": "Tries", "decides": "How many failed runs before it stops itself",
     "now": "3", "source": "the routine record's max_attempts"},
    {"name": "Stops itself", "decides": "Whether it goes quiet after those tries",
     "now": "on", "source": "the routine record's auto_disabled"},
    {"name": "May do", "decides": "What a run may change without coming back to you",
     "now": "read only", "source": "the routine record's permission mode"},
    {"name": "Reports to", "decides": "Where the run lands when it is finished",
     "now": "the department", "source": "the routine record's working folder"},
]

WORK_ATOM_SETTINGS = [
    {"name": "Needs a check", "decides": "Whether one can be opened without a check that flips",
     "now": "no", "source": "sutra-atom open"},
    {"name": "Names its files", "decides": "Whether it must say which files it will touch",
     "now": "yes", "source": "the dispatch envelope"},
    {"name": "Closes by", "decides": "What may close one: the check, or a person saying so",
     "now": "the check", "source": "sutra-atom close"},
    {"name": "Reopens", "decides": "Whether a failed check reopens it instead of filing it",
     "now": "yes", "source": "the verify result"},
]

# ── what one is made of ─────────────────────────────────────────────────────
# For a function these are the template record's own fields, so the part list
# is derived, not authored: FIELD_PART maps field -> (screen name, caption).

FIELD_PART = [
    ("floor", "Floor", "always", "What it must always do, whatever else is picked."),
    ("choices", "Choices", "its own", "What it decides for itself."),
    ("reads", "Reads", "may look at", "What it is allowed to look at."),
    ("may_propose", "May ask for", "proposes", "What it may put to the owner."),
    ("schedule", "When it runs", "schedule", "The moment it acts."),
    ("checks", "Checks", "proves", "What proves it ran right."),
    ("chat_brief", "Its brief", "opens with",
     "The words its chat opens with, with this department's own fields filled in."),
]

ENGINE_PARTS = [
    {"name": "Its name", "caption": "title", "says": "What it is called on the department's card."},
    {"name": "Its folder", "caption": "works in", "says": "The one folder a run may read and write."},
    {"name": "When it fires", "caption": "schedule", "says": "A clock, or a moment in the work."},
    {"name": "Its instruction", "caption": "body", "says": "The one thing a run does, in plain words."},
    {"name": "Done when", "caption": "verify", "says": "The check that flips at the end of a run."},
    {"name": "May do", "caption": "without asking", "says": "Read, write in its folder, or file an ask."},
    {"name": "Tries", "caption": "before it stops", "says": "How many failed runs before it goes quiet."},
    {"name": "Its runs", "caption": "history", "says": "Every run, what it changed, what the check said."},
]

WORK_ATOM_PARTS = [
    {"name": "Its goal", "caption": "one line", "says": "The outcome somebody could see."},
    {"name": "Done when", "caption": "the check", "says": "The one check that flips."},
    {"name": "Who does it", "caption": "owner", "says": "A person, a chat or an engine. Always one."},
    {"name": "What it touches", "caption": "files", "says": "What it may change while it is open."},
    {"name": "Its ref", "caption": "id", "says": "The short name everything else points at."},
    {"name": "Where it is", "caption": "state", "says": "Open, waiting on you, filed, or reopened."},
    {"name": "What it left", "caption": "evidence", "says": "The check's own output, kept."},
]

#: The work atom shelf holds no skills, on purpose (PRD, never #3).
WORK_ATOM_NOTE = ("No skills here. A work atom says what is to be true when it is "
                  "finished, never who knows how. That is the engine's business, and "
                  "keeping it out is what lets the same work atom be done by a person "
                  "today and an engine next month.")

FUNCTION_NOTE = ("A department never runs on one of these directly. It writes its own "
                 "child of the one you pick, even when it changes nothing, and that "
                 "child is what runs. A child may add a line or tighten one. It may "
                 "not drop one.")

ENGINE_NOTE = ("An engine is the only part of a department that makes things. The five "
               "functions judge, order and report. When a chat is asked to build "
               "something, this is what it hands the work to.")


def _text(v: Any) -> str:
    return "" if v is None else str(v)


def _lines(v: Any) -> List[str]:
    if isinstance(v, list):
        return [_text(x) for x in v if _text(x)]
    t = _text(v)
    return [t] if t else []


# ── the function shelves ────────────────────────────────────────────────────

def _use_map() -> Dict[str, List[str]]:
    """{template id: [department ref, ...]} from the picks file. A pick nobody
    made is simply absent; the Default a department falls back to is not a
    pick and is not counted here."""
    out: Dict[str, List[str]] = {}
    try:
        picks = FT.read_picks()
    except Exception:
        return out
    if not isinstance(picks, dict):
        return out
    for ref, per_fn in picks.items():
        if not isinstance(per_fn, dict):
            continue
        for _fn, rec in per_fn.items():
            tid = (rec or {}).get("template") if isinstance(rec, dict) else None
            if tid:
                out.setdefault(str(tid), []).append(str(ref))
    return out


def _template_row(t: Dict[str, Any], uses: Dict[str, List[str]]) -> Dict[str, Any]:
    tid = _text(t.get("id"))
    parent = t.get("derives_from")
    use_case = _text(t.get("use_case"))
    tags = [_use_tag(use_case), "base" if not parent else "from " + _short(parent)]
    where = uses.get(tid) or []
    return {
        "id": tid,
        "name": _text(t.get("name")) or tid,
        "sub": tid,
        "use": use_case,
        "tags": [x for x in tags if x],
        "right": "%d always" % len(_lines(t.get("floor"))),
        "state": "in-use" if where else "ready",
        "action": "Use",
        "where": where,
    }


def _short(template_id: Any) -> str:
    tid = _text(template_id)
    return tid.split("/", 1)[1] if "/" in tid else tid


def _use_tag(use_case: str) -> str:
    """The row's own use-case tag, in one or two words, from the template's
    own sentence -- never a second vocabulary."""
    low = use_case.lower()
    if "moves money" in low or "money" in low:
        return "money"
    if "builds" in low or "ships a product" in low or "product" in low:
        return "product"
    if "any department" in low:
        return "any department"
    return "other"


def _function_shelf(fn: str) -> Dict[str, Any]:
    rows_src = FT.templates(fn)
    uses = _use_map()
    rows = [_template_row(t, uses) for t in rows_src]
    default = next((t for t in rows_src if not t.get("derives_from")), rows_src[0] if rows_src else {})
    parts = []
    for field, name, caption, says in FIELD_PART:
        val = default.get(field) if default else None
        example = ""
        if field == "chat_brief":
            example = ""
        elif isinstance(val, list) and val:
            example = _text(val[0])
        else:
            example = _text(val)
        parts.append({"name": name, "caption": caption, "says": says, "example": example})
    tags = []
    for r in rows:
        for tg in r["tags"]:
            if tg not in tags and not tg.startswith("from ") and tg != "base":
                tags.append(tg)
    in_use = sorted({ref for r in rows for ref in r["where"]})
    return {
        "head": {
            "id": fn, "name": fn.capitalize(), "kind": "Function",
            "line": FUNCTION_LINE.get(fn, ""),
            "count_line": "%d ready-made%s" % (
                len(rows), " · on %d departments" % len(in_use) if in_use else ""),
            "tabs": ["About", "Templates"],
        },
        "about": {"ways": FUNCTION_WAYS, "settings": FUNCTION_SETTINGS,
                  "parts": parts, "note": FUNCTION_NOTE},
        "list": {"tag_label": "Fits", "tags": tags, "rows": rows, "note": FUNCTION_NOTE},
    }


# ── the engines shelf ───────────────────────────────────────────────────────

def _routine_rows() -> List[Dict[str, Any]]:
    """Every engine record, read through routines.py's own functions, as
    dept_api reads them. A box with no routine store answers with none."""
    out: List[Dict[str, Any]] = []
    try:
        import routines  # noqa: WPS433 (same lazy import dept_api uses)
    except Exception:
        return out
    try:
        ids = list(routines.list_ids())
    except Exception:
        return out
    for rid in ids:
        try:
            rec = routines.load(rid)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        out.append({
            "id": _text(rec.get("id") or rid),
            "name": _text(rec.get("title")) or _text(rid),
            "sub": _text(rec.get("cwd")),
            "use": _text(rec.get("body"))[:120],
            "tags": [t for t in [_text(rec.get("schedule")) or "on a word"] if t],
            "right": "running" if rec.get("enabled") else "stopped",
            "state": "in-use" if rec.get("enabled") else "ready",
            "action": "Open",
            "where": [],
        })
    return out


def _workflow_rows() -> List[Dict[str, Any]]:
    """The workflow records that ship with the Native user kit. Read as files
    from the kit's own folder; a box without the kit shows none."""
    rows: List[Dict[str, Any]] = []
    home = os.path.join(os.path.expanduser("~"), ".sutra-native", "user-kit", "workflows")
    try:
        names = sorted(os.listdir(home))
    except OSError:
        return rows
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(home, name), encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue
        rows.append({
            "id": _text(rec.get("id") or name[:-5]),
            "name": _text(rec.get("name") or rec.get("title")) or name[:-5],
            "sub": name[:-5],
            "use": _text(rec.get("description") or rec.get("goal"))[:140],
            "tags": ["on a chat's word"],
            "right": "shipped",
            "state": "ready",
            "action": "Use",
            "where": [],
        })
    return rows


def _engines_shelf() -> Dict[str, Any]:
    rows = _workflow_rows() + _routine_rows()
    running = sum(1 for r in rows if r["state"] == "in-use")
    tags: List[str] = []
    for r in rows:
        for tg in r["tags"]:
            if tg not in tags:
                tags.append(tg)
    return {
        "head": {
            "id": "engines", "name": "Engines", "kind": "Part",
            "line": ("What a department runs without being asked each time. A folder it "
                     "works in, a moment it fires, one instruction, and a check that says "
                     "whether the run counted."),
            "count_line": "%d ready-made · %d running" % (len(rows), running),
            "tabs": ["About", "Engines"],
        },
        "about": {"ways": ENGINE_WAYS, "settings": ENGINE_SETTINGS,
                  "parts": ENGINE_PARTS, "note": ENGINE_NOTE},
        "list": {"tag_label": "Fires", "tags": tags, "rows": rows, "note": ENGINE_NOTE},
    }


# ── the work atom shelf ─────────────────────────────────────────────────────

def _ledger_path() -> str:
    return os.path.join(_project_root(), ".sutra", "atom-ledger.jsonl")


def _project_root() -> str:
    """The repo this app was started in, the way dept_api resolves it: the
    working folder, never a path this module composes from a name."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _work_atom_rows(limit: int = 3) -> List[Dict[str, Any]]:
    """The most recent closed work atoms, from the ledger. Examples, not a
    catalogue: a work atom is written, never picked (PRD)."""
    rows: List[Dict[str, Any]] = []
    try:
        with open(_ledger_path(), encoding="utf-8") as fh:
            lines = fh.readlines()[-400:]
    except OSError:
        return rows
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("status") != "closed":
            continue
        goal = _text(rec.get("goal"))
        if not goal:
            continue
        verify = rec.get("verify") if isinstance(rec.get("verify"), dict) else {}
        rows.append({
            "id": _text(rec.get("id")),
            "name": goal[:70],
            "sub": _text(rec.get("id")),
            "use": "Done when: %s" % (_text(verify.get("template")) or "a check that flips"),
            "tags": [_text(verify.get("template")) or "a check"],
            "right": "filed",
            "state": "in-use",
            "action": "Open",
            "where": _lines(rec.get("touches")),
        })
        if len(rows) >= limit:
            break
    return rows


def _skill_rows() -> List[Dict[str, Any]]:
    """Every skill this box can reach, as shelf rows, categorised by what it
    DOES (skill_categories.py). Founder, 2026-09-23: "I want the skills to be
    transferred in the library in the work atom" -- so the skills live here,
    beside the thing they are used on, and the tag is the category."""
    rows: List[Dict[str, Any]] = []
    try:
        import skills_catalog
        import skill_categories
    except Exception:
        return rows
    try:
        items = skills_catalog.discover_all(project_dir=None)["items"]
    except Exception:
        return rows
    skill_categories.annotate(items)
    for e in items:
        name = _text(e.get("slash") or e.get("name"))
        rows.append({
            "id": _text(e.get("name")) or name,
            "name": name,
            "sub": _text(e.get("source")),
            "use": _text(e.get("description"))[:150],
            "tags": [t for t in [_text(e.get("category")), _text(e.get("moment"))] if t],
            "right": _text(e.get("category_how")) if e.get("category_how") != "named" else "named",
            "state": "ready" if e.get("runnable") else "to-build",
            "action": "Open",
            "where": [],
        })
    rows.sort(key=lambda r: ((r["tags"][0] if r["tags"] else "z"), r["name"]))
    return rows


def _work_atom_shelf() -> Dict[str, Any]:
    examples = _work_atom_rows()
    skills = _skill_rows()
    # the examples move into About: the second tab is the SKILLS a work atom
    # draws on, which is what the founder asked the shelf to carry.
    cats: List[str] = []
    for r in skills:
        c = r["tags"][0] if r["tags"] else ""
        if c and c not in cats:
            cats.append(c)
    return {
        "head": {
            "id": "work-atom", "name": "Work atom", "kind": "Part",
            "line": ("One goal with one check that flips. Everything a department does is "
                     "one of these, whether you wrote it, a function proposed it, or an "
                     "engine opened it on a run."),
            "count_line": "%d parts · %d skills to draw on" % (len(WORK_ATOM_PARTS), len(skills)),
            "tabs": ["About", "Skills"],
        },
        "about": {"ways": WORK_ATOM_WAYS, "settings": WORK_ATOM_SETTINGS,
                  "parts": WORK_ATOM_PARTS, "note": WORK_ATOM_NOTE,
                  "examples": examples},
        "list": {"tag_label": "Does", "tags": cats, "rows": skills,
                 "note": ("A work atom names what must be true when it is finished. These "
                          "are the ways of working it may draw on: the ones it declares "
                          "when it opens, and the ones it actually used when it closes. A "
                          "declared skill never refuses anything, because refusing is a "
                          "rule's job.")},
    }


# ── the shelves ─────────────────────────────────────────────────────────────

def shelf(shelf_id: str) -> Optional[Dict[str, Any]]:
    """One shelf, or None when the id is not one of the seven."""
    sid = str(shelf_id or "")
    if sid in FUNCTIONS:
        return _function_shelf(sid)
    if sid == "engines":
        return _engines_shelf()
    if sid == "work-atom":
        return _work_atom_shelf()
    return None


def _counts(sid: str) -> Dict[str, Any]:
    try:
        payload = shelf(sid)
    except Exception as exc:  # a shelf that cannot read says so, never 500s
        return {"rows": 0, "error": str(exc)[:200]}
    rows = ((payload or {}).get("list") or {}).get("rows") or []
    return {"rows": len(rows), "error": ""}


@router.get("/ping")
def ping():
    return {"ok": True, "shelves": len(SHELVES)}


@router.get("/shelves")
def shelves():
    out = []
    for sid, name, kind, group in SHELVES:
        c = _counts(sid)
        out.append({
            "id": sid, "name": name, "kind": kind, "group": group,
            "line": FUNCTION_LINE.get(sid, ""),
            "rows": c["rows"], "error": c["error"],
            "list_tab": LIST_TAB.get(sid, "Templates"),
        })
    return {"shelves": out, "groups": [
        {"id": "functions", "name": "Functions"}, {"id": "parts", "name": "Parts"}]}


@router.get("/shelf/{shelf_id}")
def shelf_get(shelf_id: str):
    try:
        payload = shelf(shelf_id)
    except Exception as exc:
        return {"error": "this shelf cannot read its record: %s" % str(exc)[:200],
                "head": {}, "about": {}, "list": {"rows": [], "tags": []}}
    if payload is None:
        return {"error": "no shelf by that name", "head": {}, "about": {},
                "list": {"rows": [], "tags": []}}
    payload["error"] = ""
    return payload


@router.get("/shelf/{shelf_id}/item/{item_id:path}")
def shelf_item(shelf_id: str, item_id: str):
    """One row opened. On a function shelf that means what the template adds to
    its parent (the narrowing rule made visible) and where it is in use."""
    sid = str(shelf_id or "")
    if sid not in FUNCTIONS:
        payload = shelf(sid) or {}
        for r in ((payload.get("list") or {}).get("rows") or []):
            if r.get("id") == item_id:
                return {"id": item_id, "keeps": [], "adds": [], "where": r.get("where") or [],
                        "lines": [r.get("use") or ""]}
        return {"error": "no row by that name", "id": item_id, "keeps": [], "adds": [], "where": []}
    t = FT.get(item_id)
    if not t:
        return {"error": "no template by that name", "id": item_id,
                "keeps": [], "adds": [], "where": []}
    floor = _lines(t.get("floor"))
    parent = FT.get(t.get("derives_from")) if t.get("derives_from") else None
    keeps = _lines(parent.get("floor")) if parent else []
    adds = [ln for ln in floor if ln not in keeps]
    uses = _use_map().get(_text(t.get("id"))) or []
    return {"id": _text(t.get("id")), "name": _text(t.get("name")),
            "keeps": keeps, "adds": adds, "where": uses,
            "parent": _text(t.get("derives_from")) or "", "error": ""}
