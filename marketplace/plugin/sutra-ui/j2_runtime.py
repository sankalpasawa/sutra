"""J2 lifecycle contract over the Native department record.

The existing engine runtime owns execution.  This module owns the eight-step
lifecycle, its durable events, and the safe projection shown to the operator.
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


class J2Error(ValueError):
    """A stable J2 boundary error."""


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
    current = events(ref)
    previous = next((item for item in current if item.get("idempotency_key") == row["idempotency_key"]), None)
    if previous:
        return previous
    row.setdefault("schema_version", SCHEMA_VERSION)
    row.setdefault("event_id", "evt-" + uuid.uuid4().hex[:12])
    row.setdefault("identity_revision", int((W.dept(ref) or {}).get("identity_revision") or 1))
    row.setdefault("occurred_at", W.now())
    row.setdefault("visibility", ["agent_activity"])
    with W._lock(ref):
        latest = events(ref)
        previous = next((item for item in latest if item.get("idempotency_key") == row["idempotency_key"]), None)
        if previous:
            return previous
        latest.append(row)
        W._write(_path(ref, "j2-events.json"), latest)
    return row


def _emit(ref, cycle, step, journey, actor, recipient, action, state, summary, suffix, payload=None):
    return append_event(ref, {
        "idempotency_key": "%s/%s/%s/%s" % (ref, cycle, step, suffix),
        "department_ref": ref,
        "cycle_id": cycle,
        "step": step,
        "journey": journey,
        "actor": actor,
        "recipient": recipient,
        "action": action,
        "state": state,
        "summary": summary,
        "payload": payload or {},
    })


def _ready(dept):
    return any(isinstance(e, dict) and e.get("kind") == "j2_ready" for e in dept.get("events") or [])


def _identity_gaps(dept):
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


def _identity_question(gaps):
    first = gaps[0]
    return {
        "goal": "What goal must this department achieve?",
        "done-when": "What evidence will prove this department is done?",
        "rules": "What may this department do, ask about, or refuse?",
        "record": "Where should this department file its work and evidence?",
    }[first]


def start(ref):
    """Start J2 once. Template routes reach Coordination; organic routes wait on Adaptation."""
    if os.environ.get("J2_FLOW_V1") != "1":
        raise J2Error("J2_FLOW_DISABLED")
    dept = W.dept(ref)
    if not dept or not _ready(dept):
        raise J2Error("J2_NOT_READY")
    existing = _state(ref)
    if existing:
        return existing
    cycle = "cycle-" + uuid.uuid4().hex[:10]
    gaps = _identity_gaps(dept)
    if gaps:
        question = _identity_question(gaps)
        aid = "a-j2-" + uuid.uuid4().hex[:8]
        W._put_ask(ref, {"id": aid, "kind": "j2_identity", "text": question, "status": "pending",
                         "created": W.now(), "cycle_id": cycle, "missing": gaps[0]})
        _emit(ref, cycle, 1, "J2.a", "Identity", "User", "identity.questioned", "waiting",
              question, "identity-question", {"missing": gaps})
        return _save_state(ref, {"cycle_id": cycle, "step": 1, "journey": "J2.a", "state": "waiting",
                                 "open_ask": aid, "updated_at": W.now()})

    _emit(ref, cycle, 1, "J2.a", "Identity", "Adaptation", "identity.assessed", "complete",
          "Identity is sufficient to start.", "identity-assessed",
          {"goal": dept.get("goal"), "done_when": dept.get("done")})
    if dept.get("kind") == "organic" and not (dept.get("engines") or []):
        _emit(ref, cycle, 2, "J2.b", "Identity", "Adaptation", "proposal.requested", "running",
              "Shape the first workflow from the stamped Identity.", "proposal-requested",
              {"source": "shaped", "goal": dept.get("goal")})
        return _save_state(ref, {"cycle_id": cycle, "step": 2, "journey": "J2.b", "state": "adapting",
                                 "updated_at": W.now()})

    workflow = list(dept.get("engines") or [name for name, *_ in W.engines_of(dept)])
    _emit(ref, cycle, 2, "J2.b", "Adaptation", "Priority", "proposal.created", "pending",
          "Proposed the department's Library workflow.", "proposal-created",
          {"source": "library", "template_ref": dept.get("template_ref"), "workflow": workflow})
    _emit(ref, cycle, 3, "J2.c", "Priority", "Root", "proposal.granted", "granted",
          "Granted within the current envelope.", "proposal-granted", {"workflow": workflow})
    _emit(ref, cycle, 5, "J2.e", "Root", "Adaptation", "workflow.validated", "complete",
          "The workflow meets Sutra's registered standards.", "workflow-validated", {"workflow": workflow})
    _emit(ref, cycle, 5, "J2.e", "Root", "Coordination", "workflow.registered", "complete",
          "Registered the workflow on the department record.", "workflow-registered", {"workflow": workflow})
    return _save_state(ref, {"cycle_id": cycle, "step": 6, "journey": "J2.f", "state": "ready",
                             "updated_at": W.now()})


def status(ref):
    dept = W.dept(ref)
    if not dept:
        raise J2Error("NO_DEPARTMENT")
    state = _state(ref) or {"cycle_id": None, "step": None, "journey": None,
                            "state": "not_started" if _ready(dept) else "not_ready", "updated_at": None}
    return dict(state, department_ref=ref, enabled=os.environ.get("J2_FLOW_V1") == "1",
                event_count=len(events(ref)))


def stop(ref):
    dept = W.dept(ref)
    if not dept:
        raise J2Error("NO_DEPARTMENT")
    current = _state(ref) or start(ref)
    if current.get("state") == "stopped":
        return current
    cycle = current["cycle_id"]
    _emit(ref, cycle, current.get("step") or 1, current.get("journey") or "J2.a", "User", "Identity",
          "cycle.stopped", "stopped", "The user stopped new J2 admissions.", "cycle-stopped")
    W.set_stopped(ref, True)
    return _save_state(ref, dict(current, state="stopped", updated_at=W.now()))


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
        })
    for row in R.board(ref):
        payload = _clean(row.get("payload") or {})
        summary = str(payload.get("why") or payload.get("done") or payload.get("objective") or payload.get("word") or row.get("msg_type") or "Message")
        rows.append({
            "id": "board-%s" % row.get("n"), "at": row.get("at"), "actor": row.get("src"),
            "recipient": ", ".join(str(x) for x in row.get("dst") or []), "action": _board_action(row),
            "state": "recorded", "summary": summary, "step": None, "journey": None,
            "evidence_refs": [], "payload": payload,
        })
    rows.sort(key=lambda item: (str(item.get("at") or ""), str(item.get("id") or "")))
    return rows
