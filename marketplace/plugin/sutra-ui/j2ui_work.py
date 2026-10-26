"""j2ui_work.py -- the page's work content: workflows, atoms, lanes, audits, conflicts, call log (UI port, package j2ui-work).

The department screen of a website team is the J2 prototype's page, copied as it is. Its Workflows, Audit, Conflicts and
Agents tabs read thirteen keys of the state it polls; this module builds those thirteen from one read of the department
(the Ctx j2ui_common hands out) and from nothing else. It is a projection: it writes no file and no record, makes no model
call, posts nothing and speaks as no function. Where Sutra holds no value the page's own empty form is used, so a tab says
what it says for an empty run and never a figure nobody recorded.

    build(ctx)       the thirteen keys, each always present: workflows, atoms_v1, sections, agents, lanes, style,
                     conflicts, audits, conditions, rubric, workable, call_log, report
    docs(ctx)        what api/docs answers: three documents, none asked for
    preview(ctx, a)  what api/preview answers for an atom: no anchor, no html
    call(ctx, id)    what api/call answers: Sutra stores no prompt and no reply, so there is none to give

A builder never raises. Each group of keys is built in a try of its own: a group that fails is empty, a reason goes on
ctx.reasons, and every other group is filled. The result is memoised on ctx.memo, so one rebuild serves every endpoint of a
poll. Strings the record wrote pass owner_words (said yes, asked for less, said no); the owner's own words are not
rewritten, and no string says an act's id or a check's id.
"""
import engine_runtime as R
import j2ui_atoms as A
import website_dept as W

STATUSES = ("registered", "held", "running", "done", "failed", "unfunded")      # the page's six words for a workflow, and no other
KEYS = ("workflows", "atoms_v1", "sections", "agents", "lanes", "style", "conflicts", "audits", "conditions", "rubric",
        "workable", "call_log", "report")


def empty():
    """Every key at its empty value, the one the page draws as 'nothing yet'."""
    return {"workflows": [], "atoms_v1": {}, "sections": [], "agents": {}, "lanes": [], "style": None, "conflicts": [],
            "audits": [], "conditions": None, "rubric": [], "workable": None, "call_log": [], "report": None}


# ---- W2: a workflow for each engine of the registered line --------------------------------------------------------------
def _runs(e):
    return [r for r in e.get("runs") or [] if isinstance(r, dict)]


def _status(ctx, e):
    """The page's word for the engine's workflow, from the record: running; unfunded when an ask about its limit waits; held
    when any other ask for it waits (the map says Waits), or its last run was skipped, interrupted or is waiting; failed when
    its template is missing or its last run failed; done when its last run passed; registered when it has not run."""
    name, state = e.get("name"), e.get("state")
    pending = [a for a in ctx.asks if a.get("engine") == name and a.get("status") == "pending"]
    runs = _runs(e)
    if state == "Running":
        return "running"
    if any(a.get("kind") == "envelope" for a in pending):
        return "unfunded"
    if pending or state == "Waits":
        return "held"
    if state == "Missing":
        return "failed"
    if not runs:
        return "registered"
    return {"ok": "done", "failed": "failed"}.get(runs[-1].get("status"), "held")


def _last_row(ctx, e):
    """The engine's latest step row, and the name of its step."""
    rows = [r for r in ctx.steps if r.get("engine") == e.get("name")]
    if not rows:
        return None, ""
    names = {s.get("id"): s.get("name") for s in (e.get("steps_view") or {}).get("steps") or []}
    return rows[-1], names.get(rows[-1].get("step")) or ""


def _last_check(ctx, e):
    """The check of the engine's latest step, as a sentence: the step, then what its check noted. '' before it has run."""
    row, name = _last_row(ctx, e)
    return A.sentence(name, (row.get("check") or {}).get("notes")) if row else ""


def _completion(e):
    """What shows the engine's work is complete: its last slot step's check, as a sentence."""
    slots = [s for s in (e.get("steps_view") or {}).get("steps") or [] if s.get("mode") == "slot"]
    last = slots[-1] if slots else None
    return A.sentence(last.get("name"), ((last.get("last") or {}).get("notes"))) if last else ""


def _purpose(e):
    """What the engine does: its template's description in the owner's words; else what it reads and what it writes."""
    desc = A.plain((e.get("steps_view") or {}).get("description"))
    if desc:
        return desc
    reads, writes = e.get("reads"), e.get("writes")
    return ("Reads %s and writes %s" % (reads, writes)) if reads and writes else ("Writes %s" % writes) if writes else ""


def _version(ctx, e):
    """The latest version of what the engine writes, or None."""
    art = next((a for a in ctx.arts if a.get("name") == e.get("writes")), None)
    vs = (art or {}).get("versions") or []
    return vs[-1].get("v") if vs else None


def _workflow(ctx, e, line):
    name, wid, env = e.get("name"), e.get("wid"), e.get("env") or {}
    runs = _runs(e)
    return {"id": wid, "proposal_id": W.slug(name), "name": name, "covers": [], "fixes": [], "purpose": _purpose(e),
            "cost": sum(int((r.get("spend") or {}).get("calls") or 0) for r in runs), "estimate": None,
            "envelope": {"money_limit": env.get("usd"), "model_call_limit": env.get("calls"),
                         "time_limit_minutes": e.get("window_min") or None, "retry_limit": len(R.WAITS), "stop_loss": ""},
            "charged": True, "calls_used": env.get("used_calls") or 0, "retries_used": sum(int(r.get("retries") or 0) for r in runs),
            "outputs": [W.slug(e["writes"])] if e.get("writes") else [], "completion_check": _completion(e),
            "dependencies": [W.slug(o["name"]) for o in line if o is not e and e.get("reads") and o.get("writes") == e.get("reads")],
            "status": _status(ctx, e), "cycle": (ctx.cur or {}).get("round") or 1, "section": "", "revises": "",
            "agent": "%s %s" % (wid, name), "last_check": _last_check(ctx, e), "version": _version(ctx, e), "atoms": []}


def _workflows(ctx):
    """One workflow for each engine of the registered line, in the line's order. Nothing before Root's check registers a plan
    (the page says so); an engine the plan left out is no workflow (the Map draws it as a hollow branch box)."""
    if not getattr(ctx, "planned", False):
        return []
    line = [e for e in ctx.engines if e.get("in_line") and e.get("wid")]
    return [_workflow(ctx, e, line) for e in line]


# ---- the builders: each gives its group of keys, and is looked up by name when it runs, so a failure stays its own ----


def _atoms(ctx, workflows):
    return {"atoms_v1": {}, "sections": [], "agents": {}}


def _lanes(ctx, workflows):
    return []


def _audit(ctx):
    return {"audits": [], "conditions": None, "rubric": [], "workable": None}


def _conflicts(ctx):
    return []


def _calls(ctx):
    return []


def _build(ctx):
    out = empty()
    # (label, keys, how to build them from what is built already); a group's failure empties its keys and nothing more
    groups = (("workflows", lambda: {"workflows": _workflows(ctx)}),
              ("atoms", lambda: _atoms(ctx, out["workflows"])),
              ("lanes", lambda: {"lanes": _lanes(ctx, out["workflows"])}),
              ("audits", lambda: _audit(ctx)),
              ("conflicts", lambda: {"conflicts": _conflicts(ctx)}),
              ("call log", lambda: {"call_log": _calls(ctx)}))
    for label, make in groups:
        try:
            got = make()
        except Exception as e:  # noqa: BLE001 -- a wrong shape blanks the page; this group's keys stay empty instead
            reasons = getattr(ctx, "reasons", None)
            if isinstance(reasons, list):
                reasons.append("%s: %s %s" % (label, type(e).__name__, A.cut(e, 120)))
            continue
        out.update({k: v for k, v in got.items() if k in KEYS})
    return out


def build(ctx):
    return A.memoised(ctx, "j2ui_work.build", _build, empty, "work")
