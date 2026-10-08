"""J2: the department's life, on its record.

J1 ends with the department made. J2 is the five functions working toward the identity's goal (the department page,
section J2): Identity finds the identity good enough, Adaptation proposes the workflows, Priority grants, refuses or
counters, Identity closes a conflict, Root checks and registers, Coordination orders and the workflows run, Audit reads
the result, and the loop goes on until done-when holds.

The functions do that work on the department's one board, in engine_runtime. This module is the lifecycle's own record
and its covering: one cycle per department, the step it stands on, and an append-only ledger of what happened. The
ledger is written where the thing happens (a post on the board, a run row, a filed version), by the hooks below, so it
cannot say something the department did not do.
"""
import copy
import os
import uuid

import engine_runtime as R
import website_dept as W


SCHEMA_VERSION = "j2.event.v1"
ACTORS = {"Root", "Identity", "Adaptation", "Priority", "Coordination", "Audit", "User"}
RULE_TAGS = {"go", "ask", "refuse", "always"}
PRIVATE_KEYS = {"private_reasoning", "reasoning", "chain_of_thought", "scratchpad", "secret", "token", "password"}
JOURNEY = {1: "J2.a", 2: "J2.b", 3: "J2.c", 4: "J2.d", 5: "J2.e", 6: "J2.f", 7: "J2.g", 8: "J2.h"}
REPAIRS = 2                     # how often Root's check may send a workflow back before Identity tells the owner (J2.4)


class J2Error(ValueError):
    """A stable J2 boundary error."""


def enabled():
    """On unless switched off: a department born while it is off runs as it did before J2, and is never held."""
    return os.environ.get("J2_FLOW_V1", "1").strip().lower() not in ("0", "false", "off")


def _path(ref, name):
    return W.ddir(ref) / name


def events(ref):
    return W._read(_path(ref, "j2-events.json"), [])


def _state(ref):
    return W._read(_path(ref, "j2-state.json"), None)


def _save_state(ref, row):
    with W._lock(ref):
        W._write(_path(ref, "j2-state.json"), row)
    return row


def _set(ref, **more):
    """Move the cycle: the step it stands on, and the plain word for its state."""
    with W._lock(ref):
        state = _state(ref)
        if not state:
            return None
        state.update(more)
        if "step" in more:
            state["journey"] = JOURNEY.get(more["step"], state.get("journey"))
        state["updated_at"] = W.now()
        W._write(_path(ref, "j2-state.json"), state)
        return state


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if str(k).lower() not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def append_event(ref, event):
    """Append one valid event, once, before the next actor is woken."""
    row = _clean(copy.deepcopy(event or {}))
    if row.get("department_ref") != ref:
        raise J2Error("DEPARTMENT_MISMATCH")
    required = ("idempotency_key", "cycle_id", "step", "journey", "actor", "recipient", "action", "state", "summary")
    missing = [key for key in required if row.get(key) in (None, "")]
    if missing:
        raise J2Error("INVALID_EVENT: " + ", ".join(missing))
    with W._lock(ref):
        latest = events(ref)
        previous = next((item for item in latest if item.get("idempotency_key") == row["idempotency_key"]), None)
        if previous:
            return previous
        row.setdefault("schema_version", SCHEMA_VERSION)
        row.setdefault("event_id", "evt-" + uuid.uuid4().hex[:12])
        row.setdefault("identity_revision", int((W.dept(ref) or {}).get("identity_revision") or 1))
        row.setdefault("occurred_at", W.now())
        row.setdefault("visibility", ["agent_activity"])
        row.setdefault("evidence_refs", [])
        row.setdefault("correlation_id", row["cycle_id"])
        same = [item for item in latest if item.get("cycle_id") == row["cycle_id"]]
        row.setdefault("causation_id", same[-1]["event_id"] if same else None)
        row["seq"] = len(latest) + 1                    # the ledger's own order: clocks tick in seconds, events do not
        latest.append(row)
        W._write(_path(ref, "j2-events.json"), latest)
    return row


def note(ref, step, actor, recipient, action, state, summary, key, payload=None, **more):
    """One event of the running cycle, or nothing when the department has no cycle (born before J2, or J2 off)."""
    cur = _state(ref)
    if not cur or not cur.get("cycle_id"):
        return None
    row = {"idempotency_key": "%s/%s/%s/%s" % (ref, cur["cycle_id"], step, key), "department_ref": ref,
           "cycle_id": cur["cycle_id"], "step": step, "journey": JOURNEY.get(step, "J2"), "actor": actor,
           "recipient": recipient, "action": action, "state": state, "summary": str(summary)[:400], "payload": payload or {}}
    row.update({k: v for k, v in more.items() if v is not None})
    return append_event(ref, row)


def _ready(dept):
    return any(isinstance(e, dict) and e.get("kind") == "j2_ready" for e in dept.get("events") or [])


# ---- the cycle ---------------------------------------------------------------------------------------------------
def active(ref):
    """The department lives its J2 cycle: the flag is on, a cycle exists, and nobody stopped it."""
    cur = _state(ref) if enabled() else None
    return bool(cur and cur.get("cycle_id") and cur.get("state") not in ("stopped", "done"))


def holding(ref):
    """A workflow runs only once Root has registered it (step 5). A department with no cycle is never held."""
    cur = _state(ref) if enabled() else None
    if not cur or not cur.get("cycle_id") or cur.get("state") == "done":
        return None
    if cur.get("state") == "stopped":
        return "the department's J2 cycle is stopped"
    if int(cur.get("step") or 1) < 6:
        return "waits for the workflow to be granted and registered"
    return None


def done(ref):
    return ((_state(ref) or {}).get("state") == "done") if enabled() else False


def _identity_gaps(dept):
    """Identity's own standard, as code can read it (J2.a): a goal, a done-when, rules that each say go, ask, refuse or
    always, and a record to file in. Whether the first words name anything to build from is the AI's reading, in
    Identity's take step."""
    gaps = []
    if not str(dept.get("goal") or "").strip():
        gaps.append("goal")
    if not str(dept.get("done") or "").strip():
        gaps.append("done-when")
    rules = dept.get("rules") or []
    if not rules or any(not str(r.get("line") or "").strip() or r.get("tag") not in RULE_TAGS for r in rules):
        gaps.append("rules")
    if not W.ddir(dept["ref"]).is_dir():
        gaps.append("record")
    return gaps


QUESTION = {"goal": "What goal must this department achieve?",
            "done-when": "What evidence will prove this department is done?",
            "rules": "What may this department do, ask about, or refuse?",
            "record": "Where should this department file its work and evidence?"}


def _ask_gap(ref, dept, cur):
    gaps = _identity_gaps(dept)
    if not gaps:
        return None
    question = QUESTION[gaps[0]]
    aid = "a-j2-" + uuid.uuid4().hex[:8]
    W._put_ask(ref, {"id": aid, "kind": "j2_identity", "text": question, "status": "pending", "created": W.now(),
                     "cycle_id": cur["cycle_id"], "missing": gaps[0], "answer": "words"})
    note(ref, 1, "Identity", "User", "identity.questioned", "waiting", question, "identity-question-" + aid, {"missing": gaps})
    try:
        R.post(ref, "Identity", R.OWNER, "inform", {"word": "question", "done": question})
    except Exception:  # noqa: BLE001 -- the ask is on the record whether or not the chat carries it
        pass
    return _set(ref, step=1, state="waiting", open_ask=aid)


def begin(ref):
    """Start the department's cycle, once. Called when J1 hands over (D1: J2 is the department's own life, and nobody
    presses a button for it), and by Start for a department born before that. A stopped cycle starts again."""
    with W._lock(ref):
        dept = W.dept(ref)
        cur = _state(ref)
        if cur and cur.get("state") != "stopped":
            return cur
        if cur:
            return resume(ref)
        cur = _save_state(ref, {"cycle_id": "cycle-" + uuid.uuid4().hex[:10], "step": 1, "journey": "J2.a",
                                "state": "assessing", "open_ask": None, "workflow": [], "repairs": 0, "updated_at": W.now()})
        return _ask_gap(ref, dept, cur) or cur


def start(ref):
    """The Start button's boundary: valid only after J1's hand-over, and the same answer however often it is pressed."""
    if not enabled():
        raise J2Error("J2_FLOW_DISABLED")
    dept = W.dept(ref)
    if not dept:
        raise J2Error("NO_DEPARTMENT")
    if not _ready(dept):
        raise J2Error("J2_NOT_READY")
    return begin(ref)


def answer(ref, text, ask_id=None):
    """The owner's words for Identity's open question: written to the identity, and the standard is read again (J2.1:
    one question at a time, until it is met). Returns the cycle's state."""
    text = " ".join(str(text or "").split())[:2000]
    if not text:
        raise J2Error("EMPTY_ANSWER")
    with W._lock(ref):
        dept = W.dept(ref)
        if not dept:
            raise J2Error("NO_DEPARTMENT")
        cur = _state(ref)
        aid = (cur or {}).get("open_ask")
        ask = next((a for a in W.asks(ref) if a["id"] == aid and a.get("kind") == "j2_identity"), None)
        if not cur or not ask or (ask_id and ask_id != aid):
            raise J2Error("NO_OPEN_QUESTION")
        if ask["status"] != "pending":
            raise J2Error("ALREADY_HANDLED")
        missing = ask.get("missing")
        if missing == "goal":
            dept["goal"] = text
        elif missing == "done-when":
            dept["done"] = text
        elif missing == "rules":
            dept["rules"] = [r for r in dept.get("rules") or [] if str(r.get("line") or "").strip() and r.get("tag") in RULE_TAGS]
            dept["rules"].append({"id": "u-" + uuid.uuid4().hex[:6], "tag": "go", "line": text, "since": W.now(), "from": text})
        dept["identity_revision"] = int(dept.get("identity_revision") or 1) + 1
        W.save_dept(ref, dept)
        ask.update({"status": "stamped", "decided": W.now(), "by": "the owner", "answered": text})
        W._put_ask(ref, ask)
        note(ref, 1, "User", "Identity", "ask.answered", "complete", "The owner answered: %s" % text[:200], "answer-" + aid,
             {"missing": missing})
        cur = _set(ref, state="assessing", open_ask=None)
        return _ask_gap(ref, W.dept(ref), cur) or cur


def waiting_on_owner(ref):
    cur = _state(ref) if enabled() else None
    return bool(cur and cur.get("state") == "waiting" and cur.get("open_ask")
                and any(a["id"] == cur["open_ask"] and a.get("kind") == "j2_identity" and a["status"] == "pending" for a in W.asks(ref)))


def status(ref):
    dept = W.dept(ref)
    if not dept:
        raise J2Error("NO_DEPARTMENT")
    state = _state(ref) or {"cycle_id": None, "step": None, "journey": None,
                            "state": "not_started" if _ready(dept) else "not_ready", "updated_at": None}
    return dict(state, department_ref=ref, enabled=enabled(), event_count=len(events(ref)),
                done_when=dept.get("done"), goal_reached=state.get("state") == "done")


def stop(ref):
    """The owner's Stop: no new admissions, the department is off, and the record says who did it. A department that
    never started is stopped without a cycle of work being run first."""
    with W._lock(ref):
        dept = W.dept(ref)
        if not dept:
            raise J2Error("NO_DEPARTMENT")
        cur = _state(ref)
        if cur and cur.get("state") == "stopped":
            return cur
        if not cur:
            cur = _save_state(ref, {"cycle_id": "cycle-" + uuid.uuid4().hex[:10], "step": 1, "journey": "J2.a",
                                    "state": "assessing", "open_ask": None, "workflow": [], "repairs": 0, "updated_at": W.now()})
        note(ref, int(cur.get("step") or 1), "User", "Identity", "cycle.stopped", "stopped", "The owner stopped the department.",
             "cycle-stopped-" + uuid.uuid4().hex[:6])
        cur = _set(ref, state="stopped", was=cur.get("state"))
    W.set_stopped(ref, True)
    return _state(ref)


def resume(ref):
    """Start again after a Stop: the cycle goes on from the step it stood on."""
    with W._lock(ref):
        cur = _state(ref)
        if not cur or cur.get("state") != "stopped":
            return cur
        back = cur.get("was") if cur.get("was") not in (None, "stopped") else ("running" if int(cur.get("step") or 1) >= 6 else "assessing")
        note(ref, int(cur.get("step") or 1), "User", "Identity", "cycle.resumed", back, "The owner started the department again.",
             "cycle-resumed-" + uuid.uuid4().hex[:6])
        cur = _set(ref, state=back, was=None)
    if (W.dept(ref) or {}).get("stopped"):
        W.set_stopped(ref, False)
    return _state(ref)


# ---- the hooks: the ledger is written where the thing happens ------------------------------------------------------
def on_post(ref, row):
    """A post on the department's board that is a move of the lifecycle becomes its event. Never raises."""
    try:
        if not active(ref):
            return
        src, dst, act = row.get("src"), list(row.get("dst") or []), row.get("msg_type")
        pl = row.get("payload") or {}
        word, key = pl.get("word"), "post-%s" % row.get("n")
        names = [e.get("name") for e in pl.get("engines") or [] if isinstance(e, dict)]
        if word == "line":
            if src == "Identity" and dst == ["Adaptation"] and act == "request":
                note(ref, 2, "Identity", "Adaptation", "proposal.requested", "running",
                     "Reshape the workflow: Root's check refused it." if pl.get("faults") else "Propose what the department does next.",
                     key, {"faults": pl.get("faults") or []})
                _set(ref, step=2, state="adapting")
            elif src == "Adaptation" and dst == ["Priority"] and act == "propose":
                note(ref, 2, "Adaptation", "Priority", "proposal.created", "pending",
                     "Proposed the workflow %s (%s)." % (" -> ".join(names), "from the Library" if pl.get("source") == "library" else "shaped for this goal"),
                     key, {"source": pl.get("source"), "workflow": names, "hop": row.get("hop")}, proposal_ref=row.get("thread"))
                _set(ref, step=3, state="bargaining")
            elif src == "Priority" and act == "accept-proposal":
                note(ref, 3, "Priority", "Adaptation", "proposal.granted", "granted", str(pl.get("why") or "Granted within the envelope."),
                     key, {"hop": row.get("hop")}, proposal_ref=row.get("thread"))
            elif src == "Priority" and act == "reject-proposal":
                note(ref, 3, "Priority", "Adaptation", "proposal.refused", "refused", str(pl.get("why") or "Refused."),
                     key, {"hop": row.get("hop")}, proposal_ref=row.get("thread"), reason_codes=["envelope"])
            elif src == "Priority" and act == "propose":
                note(ref, 3, "Priority", "Adaptation", "proposal.countered", "waiting", str(pl.get("why") or "Countered."),
                     key, {"keep": pl.get("keep") or [], "hop": row.get("hop")}, proposal_ref=row.get("thread"), reason_codes=["envelope"])
        elif word == "conflict" and dst == ["Identity"]:
            note(ref, 4, src, "Identity", "conflict.raised", "waiting", str(pl.get("why") or "The bargain did not close."),
                 key, {"workflow": names, "bound": pl.get("bound")}, proposal_ref=pl.get("for"))
            _set(ref, step=4, state="closing")
        elif word == "finding" and src == "Audit":
            note(ref, 7, "Audit", "Identity", "audit.finding_filed", "recorded", str(pl.get("claim") or "A finding."),
                 key, {"severity": pl.get("severity"), "findings": len(pl.get("findings") or [])},
                 evidence_refs=[{"artifact": "Live site", "version": pl.get("about_version")}])
            _set(ref, step=8, state="pursuing")
        elif src == "Identity" and R.OWNER in dst and act == "request":
            note(ref, int((_state(ref) or {}).get("step") or 1), "Identity", "User", "ask.created", "waiting",
                 str(pl.get("objective") or pl.get("word") or "An ask.")[:300], key, {"word": word})
        elif src == R.OWNER and act in ("accept-proposal", "reject-proposal"):
            note(ref, int((_state(ref) or {}).get("step") or 1), "User", "Identity", "ask.answered", "complete",
                 "The owner %s." % ("stamped it" if act == "accept-proposal" else "refused it"), key, {"word": word})
    except Exception:  # noqa: BLE001 -- the ledger never fails the post it records
        return


def on_run(ref, row, when):
    """A workflow's run: its slot, its start, how it ended. Never raises."""
    try:
        if not active(ref) or row.get("system"):
            return
        eng, rid = row.get("engine"), row.get("id")
        if when == "started":
            note(ref, 6, "Coordination", eng, "slot.assigned", "assigned", "%s has the next turn." % eng, "slot-%s" % rid,
                 {"slot": row.get("slot")}, run_ref=rid, workflow_ref=eng)
            note(ref, 6, eng, "Coordination", "run.started", "running", "%s started." % eng, "run-started-%s" % rid,
                 {"slot": row.get("slot")}, run_ref=rid, workflow_ref=eng)
            return
        status_ = row.get("status")
        spend = row.get("spend") or {}
        env = {"calls_used": spend.get("calls"), "money_used": spend.get("usd")}
        if status_ == "ok":
            wrote = row.get("wrote") or {}
            if wrote.get("art"):
                note(ref, 6, eng, "Coordination", "artifact.filed", "filed", "%s v%s filed." % (wrote["art"], wrote.get("v")),
                     "filed-%s" % rid, {}, run_ref=rid, workflow_ref=eng,
                     evidence_refs=[{"artifact": wrote["art"], "version": wrote.get("v")}])
            note(ref, 6, eng, "Coordination", "run.completed", "complete", str(row.get("what") or "%s finished." % eng),
                 "run-ended-%s" % rid, {}, run_ref=rid, workflow_ref=eng, envelope=env)
        elif status_ == "failed":
            note(ref, 6, eng, "Coordination", "run.failed", "failed", str(row.get("what") or "%s failed." % eng),
                 "run-ended-%s" % rid, {}, run_ref=rid, workflow_ref=eng, envelope=env, reason_codes=["check.failed"])
        elif status_ in ("waiting", "asked"):
            note(ref, 6, eng, "Coordination", "workflow.blocked", "waiting", str(row.get("what") or "%s waits." % eng),
                 "run-ended-%s" % rid, {"on": "the model" if status_ == "waiting" else "the owner"}, run_ref=rid, workflow_ref=eng)
    except Exception:  # noqa: BLE001 -- the ledger never fails the run it records
        return


def on_held(ref, engine, slot, why):
    """Priority held a workflow at its envelope (J2.5). Never raises."""
    try:
        if active(ref):
            note(ref, 6, "Priority", engine, "envelope.held", "held", str(why or "%s is past its envelope." % engine),
                 "held-%s" % slot, {"slot": slot}, workflow_ref=engine, reason_codes=["envelope"])
    except Exception:  # noqa: BLE001
        return


def registered(ref, engines, source, by="Root"):
    """Root's check passed: the workflow is on the department's record, and the work may run (step 5 to step 6)."""
    names = [e if isinstance(e, str) else e.get("name") for e in engines]
    with W._lock(ref):
        dept = W.dept(ref)
        versions = list(dept.get("workflows") or [])
        version = len(versions) + 1
        versions.append({"version": version, "engines": names, "source": source, "registered": W.now(), "by": by})
        dept["workflows"] = versions                 # the department's own record: nothing here is written to the Library
        W.save_dept(ref, dept)
    key = "workflow-v%d" % version
    note(ref, 5, "Root", "Adaptation", "workflow.validated", "complete", "The workflow meets Sutra's standards.", key + "-validated",
         {"workflow": names, "checks": ["engines known", "each reads what one before it wrote", "names unique"]},
         workflow_ref="workflow/%d" % version)
    note(ref, 5, "Root", "Coordination", "workflow.registered", "complete", "Registered %s on the department's record, version %d."
         % (" -> ".join(names), version), key + "-registered", {"workflow": names, "source": source, "version": version},
         workflow_ref="workflow/%d" % version)
    return _set(ref, step=6, state="running", workflow=names, repairs=0)


def refused(ref, engines, faults):
    """Root's check failed (J2.4): nothing is registered; the reasons go back. Returns how often that has now happened."""
    names = [e if isinstance(e, str) else e.get("name") for e in engines]
    cur = _state(ref) or {}
    n = int(cur.get("repairs") or 0) + 1
    if names:
        note(ref, 5, "Root", "Adaptation", "workflow.blocked", "refused", "Root's check refused the workflow: %s." % "; ".join(faults)[:300],
             "workflow-refused-%d" % n, {"workflow": names, "faults": list(faults)}, reason_codes=["standards"])
    else:
        note(ref, 2, "Adaptation", "Identity", "workflow.blocked", "refused", "The shaped line did not pass its check: %s." % "; ".join(faults)[:300],
             "workflow-refused-%d" % n, {"workflow": [], "faults": list(faults)}, reason_codes=["check.failed"])
    _set(ref, step=5, state="reshaping", repairs=n)
    return n


def ruled(ref, ruling, why, engines):
    names = [e if isinstance(e, str) else e.get("name") for e in engines or []]
    note(ref, 4, "Identity", "Adaptation" if ruling != "ask" else "User", "identity.ruled", ruling, str(why or ruling)[:300],
         "ruled-" + uuid.uuid4().hex[:6], {"ruling": ruling, "workflow": names})
    if ruling == "drop":
        _set(ref, step=4, state="blocked")
    elif ruling == "ask":
        _set(ref, step=4, state="waiting")


def assessed(ref, dept, key="first"):
    note(ref, 1, "Identity", "Adaptation", "identity.assessed", "complete", "The identity is good enough to start on.",
         "identity-assessed-" + str(key), {"sufficient": True, "done_when": dept.get("done"), "rules": len(dept.get("rules") or [])})


def questioned(ref, question, key):
    note(ref, 1, "Identity", "User", "identity.questioned", "waiting", question, "identity-question-" + str(key), {})
    _set(ref, step=1, state="waiting")


def audited(ref, version, findings):
    """Audit read what went out and found nothing to put right: done-when is read from that (step 8). Returns True when
    the goal is reached now, so Identity says so once."""
    if not active(ref):
        return False
    dept = W.dept(ref) or {}
    ev = [{"artifact": "Live site", "version": version}]
    note(ref, 7, "Audit", "Identity", "audit.finding_filed", "recorded", "Audit read Live site v%s and found nothing to put right." % version,
         "audit-clean-v%s" % version, {"severity": "none", "findings": int(findings or 0)}, evidence_refs=ev)
    if findings:
        return False
    note(ref, 8, "Identity", "User", "goal.reached", "done", "Done-when holds: %s." % str(dept.get("done") or "").rstrip("."),
         "goal-reached-v%s" % version, {"done_when": dept.get("done")}, evidence_refs=ev)
    _set(ref, step=8, state="done")
    return True


# ---- what the screen reads ----------------------------------------------------------------------------------------
def _board_action(row):
    msg = row.get("msg_type")
    word = str((row.get("payload") or {}).get("word") or "")
    if msg == "propose":
        return "proposal.created"
    if msg == "accept-proposal":
        return "proposal.accepted"
    if msg in ("reject-proposal", "refuse"):
        return "proposal.refused"
    if msg == "request" and "owner" in [str(x).lower() for x in row.get("dst") or []]:
        return "ask.created"
    if word == "finding":
        return "audit.finding_filed"
    return "board." + str(msg or "message")


def activity(ref):
    """Safe chronological activity derived from canonical J2 events and the real board."""
    rows = []
    for event in events(ref):
        rows.append({
            "id": event["event_id"], "at": event.get("occurred_at"), "actor": event["actor"],
            "recipient": event["recipient"], "action": event["action"], "state": event["state"],
            "summary": event["summary"], "step": event.get("step"), "journey": event.get("journey"),
            "evidence_refs": event.get("evidence_refs") or [], "payload": _clean(event.get("payload") or {}),
            "seq": int(event.get("seq") or 0),
        })
    for row in R.board(ref):
        payload = _clean(row.get("payload") or {})
        summary = str(payload.get("why") or payload.get("done") or payload.get("objective") or payload.get("word") or row.get("msg_type") or "Message")
        rows.append({
            "id": "board-%s" % row.get("n"), "at": row.get("at"), "actor": row.get("src"),
            "recipient": ", ".join(str(x) for x in row.get("dst") or []), "action": _board_action(row),
            "state": "recorded", "summary": summary, "step": None, "journey": None,
            "evidence_refs": [], "payload": payload, "seq": int(row.get("n") or 0),
        })
    # by the second, then each source in its own order: two rows of one second keep the order they were written in
    rows.sort(key=lambda item: (str(item.get("at") or ""), 0 if str(item.get("id")).startswith("board-") else 1, item.get("seq") or 0))
    return rows
