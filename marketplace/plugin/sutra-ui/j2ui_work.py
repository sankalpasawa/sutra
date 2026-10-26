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
import j2ui_audit as X
import owner_words
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
    """The workflows' atoms (one for each slot step of the engine), the prototype's atom/1 view of each, no sections (a website
    has none), and who builds each workflow. The atoms are made first and set on the workflows together, so a failure leaves
    the workflows as they were."""
    made = {w["id"]: A.legacy_atoms(ctx, next((e for e in ctx.engines if e.get("wid") == w["id"]), None)) for w in workflows}
    for w in workflows:
        w["atoms"] = made[w["id"]]
    return {"atoms_v1": A.views(workflows), "sections": [], "agents": {w["id"]: w["agent"] for w in workflows}}


# ---- W4: one lane for each agent ---------------------------------------------------------------------------------------
LANE_STATUS = {"quiet": "idle", "working": "working", "waiting": "waiting", "waiting_on_you": "waiting", "fault": "blocked"}
LANE_LINE = 140                                              # the page's own cut of what an agent is doing


def _last_msg(ctx, who):
    """The id of the agent's last chat message, or None."""
    return next((m.get("id") for m in reversed(getattr(ctx, "chat", None) or []) if m.get("who") == who), None)


def _line(text, words=None):
    """What a run or an ask said, in the owner's words up to the words of theirs it ends with, cut to a line."""
    return A.cut(owner_words.kept(str(text or ""), words), LANE_LINE)


def _function_lane(ctx, node):
    state = node.get("state")
    on = "you" if state == "waiting_on_you" else node.get("waits_on")
    return {"id": node["fn"], "name": node["name"], "status": LANE_STATUS.get(state, "idle"), "on": on,
            "doing": node.get("line") or "", "last_msg": _last_msg(ctx, node["fn"])}


def _workflow_lane(ctx, w, e):
    """A workflow's agent. Working while the engine runs; waiting on you while an ask for it waits (the owner holds the turn,
    whatever the workflow's own word is); blocked when the workflow is held, unfunded or failed without one; else idle, with
    the line its last run said. The numbers are the record's: Priority's calls limit and the runs' retries, never the
    prototype's constants."""
    name = e["name"]
    ask = next((a for a in ctx.asks if a.get("engine") == name and a.get("status") == "pending"), None)
    runs = [r for r in e.get("runs") or [] if isinstance(r, dict)]
    on = None
    if e.get("state") == "Running":
        status, doing = "working", "making %s" % e["writes"] if e.get("writes") else "working"
    elif ask:
        status, on, doing = "waiting", "you", _line(ask.get("text"), ask.get("words"))
    elif w["status"] in ("held", "unfunded", "failed"):
        status, doing = "blocked", "%s: %s" % (w["status"], w["last_check"] or w["name"])
    else:
        last = runs[-1] if runs else None
        status, doing = "idle", _line(last.get("what"), last.get("words")) if last else ""
    env = w["envelope"]
    return {"id": w["id"], "name": w["agent"], "status": status, "on": on, "doing": doing, "last_msg": _last_msg(ctx, w["id"]),
            "progress": {"section": "", "attempts": w["calls_used"], "attempt_limit": env["model_call_limit"],
                         "retries": int(runs[-1].get("retries") or 0) if runs else 0, "retry_limit": env["retry_limit"],
                         "write_lock": False, "last_check": w["last_check"] or "not run yet"}}


def _lanes(ctx, workflows):
    """The five functions, the validator (Root's check, which is code), then a lane for each workflow, in that order. A
    function's status is its node's (functions_view); what it is doing is the node's line."""
    lanes = [_function_lane(ctx, n) for n in (getattr(ctx, "fv", None) or {}).get("functions") or []]
    lanes.append({"id": "validator", "name": "Validator", "status": "idle", "on": None, "doing": "code: checks and registers workflows",
                  "last_msg": _last_msg(ctx, "validator")})
    by_wid = {e.get("wid"): e for e in ctx.engines}
    return lanes + [_workflow_lane(ctx, w, by_wid[w["id"]]) for w in workflows]


def _audit(ctx):
    """What Audit read, the check engine's recorded conditions, and no rubric or workable verdict nobody gave (j2ui_audit)."""
    return {"audits": X.build_audits(ctx), "conditions": X.build_conditions(ctx), "rubric": [], "workable": X.build_workable(ctx)}


def _conflicts(ctx):
    """The bargains in which Priority asked for less or said no, and any taken to Identity (j2ui_audit)."""
    return X.build_conflicts(ctx)


# ---- W7: the call log, and the answers for documents, previews and calls ------------------------------------------------
LINK_GRACE_S = 1                                             # a post is stamped to the second, so it may land a second after its step


def _fn(ctx, engine):
    """Who made a call: the function, lower case, or its W-k when it is a workflow's engine."""
    return (ctx.wid(engine) if callable(getattr(ctx, "wid", None)) else None) or str(engine or "").lower()


def _step_name(ctx, row):
    """The name of the step a row is of: from its engine's template when the engine is in the line, else the Library's."""
    for e in getattr(ctx, "engines", None) or []:
        for s in (e.get("steps_view") or {}).get("steps") or []:
            if s.get("id") == row.get("step"):
                return A.plain(s.get("name"))
    try:
        return A.plain((R.step_def(row.get("step"))[1] or {}).get("name"))
    except Exception:  # noqa: BLE001 -- a step the Library no longer has is named by its id
        return A.plain(row.get("step"))


def _call_row(ctx, i, row):
    """One call of the log, from the step row that made it. What the model was given and said is not stored, so the prompt is
    nothing, the tokens and the model are not recorded, and the reply is the line the step's own record has."""
    answer = row.get("answer")
    notes = [A.plain(n) for n in (row.get("check") or {}).get("notes") or [] if A.plain(n)]
    said = A.cut(A.plain(answer) if isinstance(answer, str) else "", A.ANSWER_MAX) or (notes[0] if notes else "")
    stamp = row.get("ended") or row.get("started")
    return {"id": i, "fn": _fn(ctx, row.get("engine")), "step": ctx.step_at(stamp) if callable(getattr(ctx, "step_at", None)) else None,
            "cycle": (ctx.cur or {}).get("round") or 1, "t": A.hhmmss(stamp), "seconds": round(int(row.get("ms") or 0) / 1000, 2),
            "model": None, "tokens": None, "chars": {"prompt": 0, "reply": len(answer) if isinstance(answer, str) else 0},
            "inputs": [["step", _step_name(ctx, row)]], "reply": {"say": said} if said else None, "reason": ""}


def _times(ctx):
    """When each thing a chat message is made from was recorded, by the registry's key: ('b', n) a post of the department's
    board, ('r', n) one of Root's, ('a', id) an ask, ('x', id) the answer to an ask, ('e', seq) an event of the ledger."""
    return {"b": {p.get("n"): p.get("at") for p in ctx.posts}, "r": {p.get("n"): p.get("at") for p in getattr(ctx, "root_posts", None) or []},
            "a": {a.get("id"): a.get("created") for a in ctx.asks},
            "x": {a.get("id"): (a.get("chosen") or {}).get("at") or a.get("decided") for a in ctx.asks},
            "e": {e.get("seq"): e.get("occurred_at") for e in ctx.events}}


def _link(ctx, rows):
    """Set `calls: [id]` on a function's message when exactly one call of that function brackets the message's time: the call
    began no later and ended no more than a second before. A message that matches two calls or none is left alone, and so is
    one that already has them: a link is never a guess."""
    spans = [(r, A.epoch(s.get("started")), A.epoch(s.get("ended"))) for r, s in rows]
    spans = [(r, a, b) for r, a, b in spans if a is not None and b is not None]
    if not spans:
        return
    times = _times(ctx)
    when = {i: times.get(key[0], {}).get(key[1]) for key, i in (getattr(ctx, "msg_of", None) or {}).items()}
    for m in getattr(ctx, "chat", None) or []:
        at = A.epoch(when.get(m.get("id")))
        if at is None or m.get("who") in (None, "user", "validator") or "calls" in m:
            continue
        hit = [r["id"] for r, a, b in spans if r["fn"] == m.get("who") and a <= at <= b + LINK_GRACE_S]
        if len(hit) == 1:
            m["calls"] = hit


def _calls(ctx):
    """The AI calls of the department, one for each step row that made any, oldest first, and the messages they belong to."""
    made = [r for r in ctx.steps if int(r.get("calls") or 0) > 0]
    rows = [(_call_row(ctx, i, r), r) for i, r in enumerate(made, 1)]
    _link(ctx, rows)
    return [r for r, _ in rows]


def _doc():
    return {"asked": False, "text": None, "workflows": []}


def docs(ctx):
    """api/docs: a website team writes no PRD, HLD or LLD, so none was asked for ('Not asked for in this run.')."""
    return {"prd": _doc(), "hld": _doc(), "lld": _doc()}


def preview(ctx, atom_id):
    """api/preview: what an atom built, as a page. Sutra keeps no section anchor, so there is none to show."""
    return {"anchor": None, "html": None}


def call(ctx, call_id):
    """api/call: the full prompt and reply of a call. Sutra stores neither, so there is nothing to give (the router answers 404)."""
    return None


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
