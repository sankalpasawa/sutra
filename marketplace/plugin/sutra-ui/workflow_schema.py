"""workflow_schema.py -- the code behind Root's standards (PRD amendment A1.14, M7.1).

Every department workflow conforms to one schema (layer_schema's `workflow`), and Root holds it to the standards in
layer_schema.WORKFLOW_STANDARDS: a Library line as its kind brings it, a fitted one, a line Adaptation shapes, a line
made with no template. The standards are code, here, and this is the only place they are: Root's check at registration
(engine_runtime._root_checks), the birth of a department (website_dept.create and setup_make), the grown line of an
engine the owner adds (website_dept.add_engine), the proposal Adaptation puts up and every write of a registration all
call `run`. layer_schema.validate_workflow delegates to it after its own shape row.

    STANDARD_CHECKS   {standard id: fn(wf, dept, ctx) -> (passed, why)}, exactly the ids of WORKFLOW_STANDARDS
    run(wf, stage, dept=None, ctx=None)   [{check, passed, why}] for the standards whose source and stage apply, in order

`wf` is a workflow value (layer_schema.as_workflow builds one from today's engine lists); `dept` is the department's
record (its kind, its done-when items, its registered workflows); `ctx` is what the stage reads beside them:
    price     the latest row of the thread's prices.jsonl (fits_room); none means Priority priced nothing here
    line      Coordination's line, and grown the engines the owner added, left_out the ones the plan left out (write)
    joining   the engine the owner adds (grow): where it repeats an output, it is the one named at fault (one_output)
A passing row says the standard's own words (WORKFLOW_STANDARDS' says); a failing row says what is wrong, in the owner's
plain words, naming the engines. Nothing here writes, posts or calls a model.

The Library, the artifact templates and the definitions are the runtime's: they are looked up when a standard runs (the
runtime is reloaded by tests), so this module holds no state.
"""
import re

import layer_schema as S
from layers import R

#: each standard's own words, as WORKFLOW_STANDARDS says them: what a passing row says
SAYS = {sid: says for sid, says, _, _ in S.WORKFLOW_STANDARDS}

#: said when a kind with no line yet is born (organic: Adaptation shapes its line from the owner's words)
NO_LINE_AT_BIRTH = "this kind starts with no engines: Adaptation shapes its line, so no standard applies at birth"

#: the names the departments keep: a function's, Root's and the Owner's (A1.14, names_unique)
_KEPT = tuple(a for a in S.ACTORS if a != "Engine")


def _engines(wf):
    return [e for e in (wf or {}).get("engines") or [] if isinstance(e, dict)]


def _name(e):
    return " ".join(str(e.get("name") or "").split())[:40]


def _kind(wf, dept):
    return (wf or {}).get("kind") or (dept or {}).get("kind")


def _first(wf, dept):
    """The artifact the kind's first engine reads: the Brief, or the Request for Root; the Brief for a kind unknown."""
    return S.first_input(_kind(wf, dept)) or "Brief"


def _reads(e, first):
    return " ".join(str(e.get("reads") or first).split())


def _writes(e):
    return " ".join(str(e.get("writes") or _name(e)).split())[:40]


def _ok(sid):
    return True, SAYS[sid]


def _fail(notes):
    return False, "; ".join(notes)


# ---- the standards, each (wf, dept, ctx) -> (passed, why) ------------------------------------------------------------
def names_an_engine(wf, dept, ctx):
    return _ok("names_an_engine") if (wf or {}).get("engines") else (False, "the workflow names no engine")


def engines_known(wf, dept, ctx):
    known = R.defs()["engines"]
    notes = ["the Library has no engine named %s" % _name(e) for e in _engines(wf)
             if _name(e) and (known.get(_name(e)) or {}).get("kind") != "work"]
    return _fail(notes) if notes else _ok("engines_known")


def each_engine_named(wf, dept, ctx):
    notes = ["engine %d has no name" % (i + 1) for i, e in enumerate(_engines(wf)) if not _name(e)]
    return _fail(notes) if notes else _ok("each_engine_named")


def names_unique(wf, dept, ctx):
    kind, seen, notes = _kind(wf, dept), [], []
    for e in _engines(wf):
        n = _name(e)
        if not n:
            continue
        if n in seen:
            notes.append("%s is named twice" % n)
        elif n.casefold() in {k.casefold() for k in _KEPT}:
            notes.append("%s is a name a function, Root or the Owner keeps" % n)
        elif n == "Setup" and kind != "root":
            notes.append("Setup is Root's own engine, not one for a department's line")
        seen.append(n)
    return _fail(notes) if notes else _ok("names_unique")


def names_new(wf, dept, ctx):
    """No name is one the Library already has, by name or by the slug its template file would take; an engine at level 1
    is the Library's own and keeps its name, what it reads and what it writes."""
    lib, notes = R.defs()["engines"], []
    for e in _engines(wf):
        n = _name(e)
        if not n:
            continue
        if e.get("level") == 1:
            base = lib.get(n)
            if not base:
                notes.append("%s is said to be a Library engine, and the Library has none named so" % n)
            elif (e.get("reads") and e["reads"] != base.get("reads")) or (e.get("writes") and e["writes"] != base.get("writes")):
                notes.append("%s keeps the Library's name, so it keeps what the Library has it read and write" % n)
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
        if n in lib or not slug or (R.TEMPLATES_DIR / (slug + ".json")).exists() or (R.user_templates_dir() / (slug + ".json")).exists():
            notes.append("the Library already has an engine named %s" % n)
    return _fail(notes) if notes else _ok("names_new")


def first_reads_input(wf, dept, ctx):
    es, first = _engines(wf), _first(wf, dept)
    if es and _reads(es[0], first) != first:
        return False, "%s, the first engine, reads %s, and the first engine reads %s" % (_name(es[0]) or "engine 1", _reads(es[0], first), first)
    return _ok("first_reads_input")


def reads_known(wf, dept, ctx):
    """Each engine reads the first artifact or what one before it wrote. The first engine is first_reads_input's, at the
    stages that standard runs; at the others (a grown line) it is held to the same here."""
    first, notes = _first(wf, dept), []
    written = {first}
    judged = (ctx or {}).get("stage") in _stages("first_reads_input")
    for i, e in enumerate(_engines(wf)):
        n = _name(e)
        if not n:
            continue
        r = _reads(e, first)
        if r not in written and not (i == 0 and judged):
            notes.append("%s reads %s, which nothing before it writes" % (n, r))
        written.add(_writes(e))
    return _fail(notes) if notes else _ok("reads_known")


def one_output(wf, dept, ctx):
    """Each engine writes something not yet written; the later writer is the one at fault. At the grow stage ctx['joining']
    names the engine that joins the line: where it writes what another engine writes, the fault is the joining engine's,
    wherever the line places it (an engine that reads the Brief goes first, and the department's own would be named)."""
    joining = (ctx or {}).get("joining")
    written, notes = {_first(wf, dept): None}, []
    for e in _engines(wf):
        n = _name(e)
        if not n:
            continue
        w = _writes(e)
        if w in written:
            note = "%s writes %s, which is already written" % (joining if written[w] == joining and joining else n, w)
            if note not in notes:
                notes.append(note)
        else:
            written[w] = n
    return _fail(notes) if notes else _ok("one_output")


def items_covered(wf, dept, ctx):
    """Every done-when item is covered by an engine of the line. A workflow that names no covers is read as the default
    as_workflow gives it (every item to the last engine). At the proposal stage a failure is a warning, passed."""
    items = [i["id"] for i in (dept or {}).get("done_items") or [] if isinstance(i, dict) and i.get("id")]
    names = {_name(e) for e in _engines(wf)} - {""}
    covers = (wf or {}).get("covers")
    if not isinstance(covers, dict) or not covers:
        covers = {i: [_name(_engines(wf)[-1])] for i in items} if _engines(wf) else {}
    out = [i for i in items if not [n for n in covers.get(i) or [] if n in names]]
    if not out:
        return _ok("items_covered")
    why = "; ".join("%s is covered by no engine of the plan" % i for i in out)
    return (True, "warning: " + why) if (ctx or {}).get("stage") == "proposal" else (False, why)


def required_kept(wf, dept, ctx):
    required = R.required_engines({"kind": _kind(wf, dept)}) if _kind(wf, dept) else []
    have = {_name(e) for e in _engines(wf)}
    out = [n for n in required if n not in have]
    if out:
        return False, "the plan leaves out %s, which this kind of department requires" % R._names(out)
    return _ok("required_kept")


def size_in_range(wf, dept, ctx):
    """One engine or more; no hard cap (Q11): Priority's room bounds it. More than six says why."""
    n = len(_engines(wf))
    if not n:
        return False, "the workflow has no engine"
    if n > 6 and not str((wf or {}).get("why") or "").strip():
        return False, "the plan is %d engines long, and more than six says why" % n
    return _ok("size_in_range")


def check_exists(wf, dept, ctx):
    """Each engine's output has a check: its artifact template's, or the Default template's (a shaped engine's artifact
    is filed under the Default, as born_template files it)."""
    import artifacts
    default = artifacts.default_template() or {}
    notes = []
    for e in _engines(wf):
        if not _name(e):
            continue
        w = _writes(e)
        t = artifacts.get(w) or {}
        if not (t.get("checks") or default.get("checks")):
            notes.append("%s writes %s, and nothing checks it" % (_name(e), w))
    return _fail(notes) if notes else _ok("check_exists")


def fits_room(wf, dept, ctx):
    """Priority priced the plan and it fits today's room. With no price (Priority writes none here), it is not priced."""
    p = (ctx or {}).get("price")
    if not isinstance(p, dict):
        return True, "not priced here"
    est, room = p.get("estimate") or {}, p.get("room") or {}
    over = [what for what, k in (("calls", "calls"), ("USD", "usd")) if isinstance(est.get(k), (int, float)) and isinstance(room.get(k), (int, float))
            and est[k] > room[k]]
    if p.get("answer") == "accept" or not over:
        return _ok("fits_room")
    return False, "Priority priced the plan at %s calls and %s USD, and today's room is %s calls and %s USD" % (
        est.get("calls"), est.get("usd"), room.get("calls"), room.get("usd"))


def line_is_registered(wf, dept, ctx):
    """Coordination's line is a registered plan plus the engines the owner added: every engine on the line is one a
    registered workflow names, one the owner added, one the plan left out, or one the department's record holds. The last
    is the line a department was born with, which stands until Coordination writes its table after a registration (the
    write that carries the registration is made first), so a plan that keeps three of four engines is not at fault for
    the fourth being on the line a moment longer."""
    ctx = ctx or {}
    line = [str(n) for n in ctx.get("line") or []]
    if not line:
        return True, "Coordination has set no line yet"
    named = {_name(e) for e in _engines(wf)} | {str(n) for n in (dept or {}).get("engines") or []}
    for w in (dept or {}).get("workflows") or []:
        named |= set((w or {}).get("engines") or []) if isinstance(w, dict) else set()
    named |= {str(n) for n in ctx.get("grown") or []} | {str(n) for n in ctx.get("left_out") or []}
    out = [n for n in line if n not in named]
    if out:
        return False, "the line holds %s, which no registered plan names and the owner did not add" % R._names(out)
    return _ok("line_is_registered")


STANDARD_CHECKS = {
    "names_an_engine": names_an_engine, "engines_known": engines_known, "each_engine_named": each_engine_named,
    "names_unique": names_unique, "names_new": names_new, "first_reads_input": first_reads_input, "reads_known": reads_known,
    "one_output": one_output, "items_covered": items_covered, "required_kept": required_kept, "size_in_range": size_in_range,
    "check_exists": check_exists, "fits_room": fits_room, "line_is_registered": line_is_registered,
}


def _stages(sid):
    return next(stages for i, _, _, stages in S.WORKFLOW_STANDARDS if i == sid)


def applies(sid, wf, stage):
    """Whether a standard runs on this workflow at this stage: its stage and its source apply, and names_an_engine at
    birth only for a kind whose line is not empty."""
    _, _, sources, stages = next(s for s in S.WORKFLOW_STANDARDS if s[0] == sid)
    if stage not in stages:
        return False
    src = (wf or {}).get("source")
    if src in S.SOURCES and src not in sources:
        return False
    return not (sid == "names_an_engine" and stage == "birth" and not (wf or {}).get("engines"))


def run(wf, stage, dept=None, ctx=None):
    """[{check, passed, why}] for the standards whose source and stage apply, in WORKFLOW_STANDARDS order. A workflow with
    no engine runs names_an_engine alone and fails it; at birth a kind with an empty line runs no standard, and the one
    row says so."""
    if not isinstance(wf, dict) or stage not in S.STAGES:
        return []
    ctx = dict(ctx or {}, stage=stage)
    if not wf.get("engines"):
        if stage == "birth":
            return [{"check": "workflow_meets_standards", "passed": True, "why": NO_LINE_AT_BIRTH}]
        return [{"check": "names_an_engine", "passed": False, "why": "the workflow names no engine"}] if applies("names_an_engine", wf, stage) else []
    rows = []
    for sid, _, _, _ in S.WORKFLOW_STANDARDS:
        if applies(sid, wf, stage):
            passed, why = STANDARD_CHECKS[sid](wf, dept, ctx)
            rows.append({"check": sid, "passed": bool(passed), "why": why})
    return rows
