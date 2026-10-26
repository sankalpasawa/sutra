"""j2ui_board.py -- the J2 page's Board tab (schema board/1), from the department's questions.json.

The page lists the questions a builder or a function put to the one that knows, and what came back. In Sutra those are the
coordination.question entries Coordination files in questions.json (W3-BOARD, PRD M4.9, wave 3): {schema, id, asked_by,
to, about, question, answer, answered_by, status, artifact_update, used_by, cycle, slot, attempt, run}. Until that file
exists the board is empty and the tab stays hidden (has_board false). Sutra's FIPA board posts are not board/1: they feed
the Detailed chat, the Timeline and the Map's speaks-to lines, not this tab.

Each entry becomes the prototype's own (j2_board.new_entry at the pin): engine names are written as their workflow, W-k
(ctx.wid), functions as their lower-case id, and asked_by_role says whether one of the five asked or a builder.
Nothing is invented: an answered_from the record does not say is None, and the page prints "not recorded". Reads only; no
model call; never raises (a torn or odd file is an empty board with its reason in ctx.reasons).
"""
import re

import owner_words
import website_dept as W

SCHEMA = "board/1"
STATUSES = ("open", "answered", "unanswered", "refused")
ROLES = ("function", "builder")
FUNCS = ("identity", "adaptation", "priority", "coordination", "audit")
KEYS = ("id", "asked_by", "atom", "to", "about", "question", "answer", "answered_by", "status", "artifact_update", "used_by", "cycle",
        "attempt", "asked_by_role", "answered_from")
_WID = re.compile(r"W-\d+")


def _reason(ctx, why):
    rs = getattr(ctx, "reasons", None)
    if isinstance(rs, list) and why not in rs:
        rs.append(why)


def _who(ctx, name):
    """A name as the page shows it: an engine as its workflow (W-k), a function as its lower-case id, the owner as user.
    A name the contract does not know (Root, an id already written as W-k) stays as it is; nothing becomes None."""
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    who = getattr(ctx, "who", None)
    try:
        got = who(name) if callable(who) else None
    except Exception:  # noqa: BLE001 -- an unknown name stays as written
        got = None
    return got or (name.lower() if name.lower() in FUNCS else name)


def _text(value):
    """Machine-written text in the owner's words ('' for none); an entry's id and names are never passed through here."""
    return owner_words.plain(str(value)) if isinstance(value, str) else ""


def _version(update):
    """The version an answer filed, when the entry's artifact_update names one."""
    if not isinstance(update, dict):
        return None
    v = update.get("v", update.get("version"))
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _from(ctx, e, answered_by, status):
    """Where the answer came from: what the entry says, else the one that answered it (a function, or a workflow with the
    version it filed); None when nothing says."""
    given = e.get("answered_from")
    if isinstance(given, dict) and (given.get("function") or given.get("workflow")):
        out = {}
        if given.get("function"):
            out["function"] = str(_who(ctx, str(given["function"])))
        if given.get("workflow"):
            out["workflow"] = str(_who(ctx, str(given["workflow"])))
            out["version"] = given.get("version") if isinstance(given.get("version"), int) else _version(e.get("artifact_update"))
        return out
    if status != "answered" or not answered_by:
        return None
    if answered_by in FUNCS:
        return {"function": answered_by}
    return {"workflow": answered_by, "version": _version(e.get("artifact_update"))} if _WID.fullmatch(answered_by) else None


def entry(ctx, e):
    """One questions.json entry as the page's board entry, or None when it is not one (no id, or a status the board does
    not have)."""
    if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not e["id"].strip() or e.get("status") not in STATUSES:
        return None
    asked = str(e.get("asked_by") or "")
    answered_by = _who(ctx, e.get("answered_by"))
    try:
        attempt = int(e.get("attempt") or 1)
    except (TypeError, ValueError):
        attempt = 1
    used = e.get("used_by")
    update = e.get("artifact_update")
    return {"id": e["id"].strip(), "asked_by": _who(ctx, asked) or "", "atom": _who(ctx, e.get("atom")), "to": _who(ctx, e.get("to")) or "",
            "about": _text(e.get("about")), "question": _text(e.get("question")),
            "answer": _text(e.get("answer")) or None, "answered_by": answered_by, "status": e["status"],
            "artifact_update": update if isinstance(update, dict) and update else None,
            "used_by": [_who(ctx, u) for u in used if isinstance(u, str) and u.strip()] if isinstance(used, list) else [],
            "cycle": e.get("cycle") if isinstance(e.get("cycle"), str) else None, "attempt": attempt,
            "asked_by_role": "function" if asked.strip().lower() in FUNCS else "builder",
            "answered_from": _from(ctx, e, answered_by, e["status"])}


def _build(ctx):
    raw = W._read(W.ddir(ctx.ref) / "questions.json", None)
    rows = raw.get("entries") if isinstance(raw, dict) else raw
    if rows is None:
        return {"schema": SCHEMA, "entries": []}
    if not isinstance(rows, list):
        _reason(ctx, "questions.json is not a list of entries")
        return {"schema": SCHEMA, "entries": []}
    out = [x for x in (entry(ctx, e) for e in rows) if x]
    if len(out) != len(rows):
        _reason(ctx, "questions.json holds %d entries the board does not show" % (len(rows) - len(out)))
    return {"schema": SCHEMA, "entries": out}


def build(ctx):
    """{'schema': 'board/1', 'entries': [...]}, memoised on ctx.memo; the empty board when the file is absent or unreadable."""
    memo = getattr(ctx, "memo", None)
    memo = memo if isinstance(memo, dict) else {}
    if "board" not in memo:
        try:
            memo["board"] = _build(ctx)
        except Exception as exc:  # noqa: BLE001 -- the page needs the shape: the empty board, and why
            _reason(ctx, "the board could not be read: %s" % exc)
            memo["board"] = {"schema": SCHEMA, "entries": []}
    return memo["board"]
