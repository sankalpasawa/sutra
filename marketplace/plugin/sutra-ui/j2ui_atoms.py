"""j2ui_atoms.py -- a work atom for each slot step of an engine, in the J2 prototype's shape (UI port, package j2ui-work).

The page the app shows for a website department (the J2 prototype's j2_ui.html, copied byte for byte) draws a workflow as a
row, and under it one card for each of its work atoms: a goal, who builds it, what must exist, the check that proves it,
what the check found. Sutra has no such atom stored. What it has is an engine, its steps, and one row in steps.jsonl each
time a step ran, so an atom here is a step read as the page reads an atom. This module only reads: it writes nothing, makes
no model call, and invents nothing. Where the record holds no value the page's own empty form is used (an empty list, no
status, no output).

    legacy_atoms(ctx, engine)   the atoms of one engine, one for each slot step, in order (a gate and a rule decide whether a
                                start may happen: they are decisions, not work, and are no atom). The page's cards read these
    views(workflows)            atoms_v1: the prototype's own atom/1 view of every atom. j2_schema.py is the prototype's file,
                                copied byte for byte into j2ui_assets/ by the sync script and loaded from there, so a view is
                                the prototype's code and not a copy of its logic; without the file there are no views and the
                                page draws the plain cards

Only the step that files the engine's files (the template marks it) names them as its output; a step that reads, plans or
checks made no file.

A step's check is named in the owner's words: the step's name, then what its latest row's check noted ('Read the brief: the
brief has words'). The check's own id (brief_is_text) is an inside word and appears only as the atom's `target`, which the page
does not print.

An attempt is a run of the engine that ran the step: a step that works on each page in turn (Write a page) has one row for each
page in one run, and that is one attempt with several results, not several attempts.

The small readers (plain, cut, sentence, epoch, hhmmss, memoised) are shared by j2ui_work.py and j2ui_audit.py, the three modules
of this package, so that no string they emit says an inside word: a check's id (brief_is_text) is never a sentence.
"""
import importlib.util
import os
import re
from datetime import datetime
from pathlib import Path

import engine_runtime as R
import owner_words
import website_dept as W

ASSET = Path(__file__).resolve().parent / "j2ui_assets" / "j2_schema.py"
ID_LIKE = re.compile(r"^[a-z]+(_[a-z]+)+$")                  # brief_is_text: a check's id, never a sentence
ANSWER_MAX = 300                                             # a note on an atom card is a line, not a page
FILES_MAX = 200
_schema = None                                               # the atom/1 module once loaded; a test may set it
_LOADED = {}                                                 # path -> (mtime_ns, module): a changed file is read again


# ---- the small readers all three modules share ---------------------------------------------------------------------
def plain(text):
    """One line in the owner's words; '' for nothing. A check's id is not a line (an inside word) and reads as nothing."""
    text = " ".join(str(owner_words.plain(text) if text is not None else "").split())
    return "" if ID_LIKE.match(text) else text


def cut(text, n=300):
    """A line cut at a word boundary, never inside a word."""
    text = str(text or "")
    if len(text) <= n:
        return text
    head = text[:n]
    sp = head.rfind(" ")
    return (head[:sp] if sp > 0 and text[n] != " " else head).rstrip() + "…"


def sentence(name, notes):
    """A step's check as a sentence: its name, then what the latest row's check noted first ('Read the brief: the brief has
    words'), never the check's id. The step's name alone when the check noted nothing."""
    name = plain(name)
    note = next((plain(n) for n in notes or [] if plain(n)), "")
    return "%s: %s" % (name, note) if name and note else name or note


def epoch(iso):
    """Seconds since the epoch of a recorded time, or None."""
    try:
        return datetime.fromisoformat(str(iso)).timestamp()
    except (TypeError, ValueError):
        return None


def hhmmss(iso):
    """The clock part of a recorded time, as the chat prints it: 'HH:MM:SS'; '' when the record has none."""
    s = str(iso or "")
    return s[11:19] if len(s) >= 19 and s[10] in "T " else ""


def memoised(ctx, key, build, empty, label):
    """build(ctx) once for this read of the department (its memo), or `empty()` with a reason on ctx.reasons when it
    fails: a builder never raises, and a failure empties its own keys and nothing else."""
    memo = getattr(ctx, "memo", None)
    if isinstance(memo, dict) and key in memo:
        return memo[key]
    try:
        out = build(ctx)
    except Exception as e:  # noqa: BLE001 -- a wrong shape blanks the page, so a builder gives its empty one instead
        reasons = getattr(ctx, "reasons", None)
        if isinstance(reasons, list):
            reasons.append("%s: %s %s" % (label, type(e).__name__, cut(e, 120)))
        out = empty()
    if isinstance(memo, dict):
        memo[key] = out
    return out


# ---- atoms_v1: the prototype's own atom/1 views ---------------------------------------------------------------------
def schema():
    """The prototype's j2_schema module, loaded by path from j2ui_assets/ (where the sync script copies it), or None when the
    file is not there or cannot be read."""
    if _schema is not None:
        return _schema
    try:
        mtime = ASSET.stat().st_mtime_ns
        held = _LOADED.get(str(ASSET))
        if held and held[0] == mtime:
            return held[1]
        spec = importlib.util.spec_from_file_location("j2ui_j2_schema", str(ASSET))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LOADED[str(ASSET)] = (mtime, mod)
        return mod
    except Exception:  # noqa: BLE001 -- no vendored file, no views: the page draws its plain cards
        return None


def views(workflows):
    """{atom id: its atom/1 view} for every atom of the workflows, from the prototype's run_views; {} without the file."""
    mod = schema()
    if mod is None:
        return {}
    try:
        got, _warnings = mod.run_views(workflows)
        return {v["id"]: v for v in got}
    except Exception:  # noqa: BLE001
        return {}


# ---- the legacy atoms: one for each slot step ----------------------------------------------------------------------
def _engine(ctx, engine):
    if isinstance(engine, dict):
        return engine
    return next((e for e in getattr(ctx, "engines", None) or [] if e.get("name") == engine), None)


def _context(row):
    """The artifact versions the step read, as 'Site plan v2': only an entry that names both. A post it read is no version."""
    out = []
    for r in (row or {}).get("read") or []:
        if isinstance(r, dict) and r.get("art") and r.get("v") is not None:
            text = "%s v%s" % (r["art"], r["v"])
            if text not in out:
                out.append(text)
    return out


def _files(ctx, e):
    """The names of the files in the latest version of what the engine writes that one of the engine's own runs made. A name,
    never a path out of the version's folder; nothing is read of the files themselves."""
    art = next((a for a in getattr(ctx, "arts", None) or [] if a.get("name") == e.get("writes")), None)
    runs = {r.get("id") for r in e.get("runs") or []}
    mine = [v for v in (art or {}).get("versions") or [] if v.get("run") in runs]
    if not mine:
        return []
    root = W.vdir(ctx.ref, art["name"], mine[-1]["v"])
    names = []
    for here, _dirs, files in os.walk(str(root)):
        names += [os.path.relpath(os.path.join(here, f), str(root)) for f in files]
        if len(names) >= FILES_MAX:
            break
    return sorted(names)[:FILES_MAX]


def _filing(e, steps):
    """The ids of the steps that file the engine's files: the ones its template marks, else the last slot step, which is the one
    that files in every template the Library has. A step that reads, plans or checks made no file."""
    try:
        marked = {s["id"] for s in R.all_steps(e.get("name")) if s.get("files")}
    except Exception:  # noqa: BLE001 -- no template to read: the last step files
        marked = set()
    return marked or ({steps[-1]["id"]} if steps else set())


def _runs_of(rows):
    """The runs the rows belong to, in the order they began: a row with no run is a run of its own."""
    order = []
    for r in rows:
        key = r.get("run") or r.get("id")
        if key not in order:
            order.append(key)
    return order


def _atom(ctx, e, step, j, rows, files):
    aid = "%s.a%d" % (e["wid"], j)
    name = plain(step.get("name"))
    runs = _runs_of(rows)
    ordinal = {k: i for i, k in enumerate(runs, 1)}
    last = rows[-1] if rows else None
    latest = [r for r in rows if (r.get("run") or r.get("id")) == runs[-1]] if rows else []
    oks = [(r.get("check") or {}).get("ok") for r in latest]
    met = False if False in oks else True if oks and all(o is True for o in oks) else None
    check = sentence(name, (last.get("check") or {}).get("notes") if last else None)
    results = []
    for r in rows:
        ok = (r.get("check") or {}).get("ok")
        notes = [plain(n) for n in (r.get("check") or {}).get("notes") or [] if plain(n)]
        said = "; ".join(notes) or ("passed its check" if ok else "failed its check" if ok is False else "its check could not run")
        if r.get("item"):
            said = "%s: %s" % (" ".join(str(r["item"]).split()), said)
        results.append({"atom": aid, "check": sentence(name, notes), "type": "step-check", "target": step.get("id"), "expect": True,
                        "actual": ok, "pass": ok, "evidence": said, "attempt": ordinal[r.get("run") or r.get("id")], "of": len(runs),
                        "t": r.get("ended") or r.get("started"), "by": "code"})
    atom = {"id": aid, "goal": name, "constraints": [], "context": _context(last),
            "how": {"kind": "AI" if step.get("soft") else "code", "agent": e.get("name"), "steps": name},
            "expected_output": [{"text": check, "kind": "check", "met": met}],
            "verification": [{"text": check, "type": "step-check", "target": step.get("id"), "expect": True}],
            "results": results, "attempts": len(runs)}
    if met is True:
        atom["status"] = "passed"
    elif met is False and e.get("state") != "Running":
        atom["status"] = "failed"
    if last:
        answer = last.get("answer")
        note = next((plain(n) for n in (last.get("check") or {}).get("notes") or [] if plain(n)), "")
        atom["human_output"] = {"atom": aid, "attempt": len(runs),
                                "text": cut((plain(answer) if isinstance(answer, str) else "") or note or name, ANSWER_MAX)}
        atom["agent_output"] = {"atom": aid, "attempt": len(runs), "files": list(files), "section": ""}
    return atom


def legacy_atoms(ctx, engine):
    """The atoms of one engine, one for each slot step in order: W-1.a1, W-1.a2, ... Empty for an engine with no template to read
    its steps from, or no place in the line."""
    e = _engine(ctx, engine)
    if not e or not e.get("wid"):
        return []
    steps = [s for s in (e.get("steps_view") or {}).get("steps") or [] if s.get("mode") == "slot"]
    mine = [r for r in getattr(ctx, "steps", None) or [] if r.get("engine") == e.get("name")]
    files = _files(ctx, e) if mine else []
    filing = _filing(e, steps)
    return [_atom(ctx, e, s, j, [r for r in mine if r.get("step") == s.get("id")], files if s.get("id") in filing else [])
            for j, s in enumerate(steps, 1)]
