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
import j2ui_atoms as A

KEYS = ("workflows", "atoms_v1", "sections", "agents", "lanes", "style", "conflicts", "audits", "conditions", "rubric",
        "workable", "call_log", "report")


def empty():
    """Every key at its empty value, the one the page draws as 'nothing yet'."""
    return {"workflows": [], "atoms_v1": {}, "sections": [], "agents": {}, "lanes": [], "style": None, "conflicts": [],
            "audits": [], "conditions": None, "rubric": [], "workable": None, "call_log": [], "report": None}


# ---- the builders: each gives its group of keys, and is looked up by name when it runs, so a failure stays its own ----
def _workflows(ctx):
    return []


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
