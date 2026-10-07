"""Behavioral contract for J2: one department working toward its Identity."""
import importlib

import pytest


@pytest.fixture
def j2(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")

    import website_dept as W
    import engine_runtime as R
    import j2_runtime as J

    for module in (W, R, J):
        importlib.reload(module)
    return W, R, J


def _department(j2, *, kind="website", sufficient=True):
    W, _, _ = j2
    d, _ = W.create("dref-j2", "Finance highlights", "Publish verified finance news", kind=kind)
    d["goal"] = "Publish five verified finance-news highlights each morning" if sufficient else ""
    d["done"] = "Five current highlights are filed with dated source evidence" if sufficient else ""
    d["rules"] = [
        {"id": "rule-local", "tag": "go", "line": "Work inside the department record"},
        {"id": "rule-send", "tag": "ask", "line": "Ask before publishing outside"},
    ]
    d["events"] = [{"kind": "j2_ready", "route": kind}]
    if kind == "organic":
        d["engines"] = []
        d["template_ref"] = None
    else:
        d["template_ref"] = {"id": "department/website", "version": 1}
    W.save_dept(d["ref"], d)
    return d


def test_j2_requires_feature_flag_and_j1_handoff(j2, monkeypatch):
    W, _, J = j2
    d = _department(j2)
    monkeypatch.setenv("J2_FLOW_V1", "0")
    with pytest.raises(J.J2Error, match="J2_FLOW_DISABLED"):
        J.start(d["ref"])

    monkeypatch.setenv("J2_FLOW_V1", "1")
    row = W.dept(d["ref"])
    row["events"] = []
    W.save_dept(d["ref"], row)
    with pytest.raises(J.J2Error, match="J2_NOT_READY"):
        J.start(d["ref"])


def test_j2_insufficient_identity_asks_once_and_starts_no_work(j2):
    W, _, J = j2
    d = _department(j2, sufficient=False)

    first = J.start(d["ref"])
    second = J.start(d["ref"])

    assert first["state"] == second["state"] == "waiting"
    assert first["step"] == 1
    assert len([e for e in J.events(d["ref"]) if e["action"] == "identity.questioned"]) == 1
    asks = [a for a in W.asks(d["ref"]) if a["kind"] == "j2_identity" and a["status"] == "pending"]
    assert len(asks) == 1
    assert not [e for e in J.events(d["ref"]) if e["action"].startswith("proposal.")]


def test_j2_template_route_records_steps_one_to_five_once(j2):
    _, _, J = j2
    d = _department(j2)

    one = J.start(d["ref"])
    two = J.start(d["ref"])

    assert one == two
    assert one["state"] == "ready"
    assert one["step"] == 6
    assert [e["action"] for e in J.events(d["ref"])] == [
        "identity.assessed",
        "proposal.created",
        "proposal.granted",
        "workflow.validated",
        "workflow.registered",
    ]
    proposal = J.events(d["ref"])[1]
    assert proposal["actor"] == "Adaptation"
    assert proposal["recipient"] == "Priority"
    assert proposal["payload"]["source"] == "library"


def test_j2_organic_route_waits_for_adaptation_to_shape_the_line(j2):
    _, _, J = j2
    d = _department(j2, kind="organic")

    state = J.start(d["ref"])

    assert state["state"] == "adapting"
    assert state["step"] == 2
    assert [e["action"] for e in J.events(d["ref"])] == [
        "identity.assessed", "proposal.requested"
    ]
    assert J.events(d["ref"])[1]["recipient"] == "Adaptation"


def test_j2_event_append_is_idempotent_and_rejects_wrong_department(j2):
    _, _, J = j2
    d = _department(j2)
    event = {
        "idempotency_key": "dref-j2/cycle-1/3/1/counter",
        "department_ref": d["ref"],
        "identity_revision": 1,
        "cycle_id": "cycle-1",
        "step": 3,
        "journey": "J2.c",
        "actor": "Priority",
        "recipient": "Adaptation",
        "action": "proposal.countered",
        "state": "waiting",
        "summary": "Use two sources to fit the call envelope.",
    }

    assert J.append_event(d["ref"], event)["event_id"] == J.append_event(d["ref"], event)["event_id"]
    assert len(J.events(d["ref"])) == 1
    with pytest.raises(J.J2Error, match="DEPARTMENT_MISMATCH"):
        J.append_event("another-dept", event)


def test_j2_activity_projects_real_board_exchanges_without_private_reasoning(j2):
    _, R, J = j2
    d = _department(j2)
    R.post(d["ref"], "Adaptation", "Priority", "propose",
           {"word": "workflow", "why": "Goal needs current sources", "private_reasoning": "never show"})

    rows = [row for row in J.activity(d["ref"]) if row["actor"] == "Adaptation"]

    assert rows[0]["actor"] == "Adaptation"
    assert rows[0]["recipient"] == "Priority"
    assert rows[0]["action"] == "proposal.created"
    assert "private_reasoning" not in str(rows[0])
    assert rows[0]["summary"] == "Goal needs current sources"


def test_j2_stop_is_visible_and_idempotent(j2):
    _, _, J = j2
    d = _department(j2)
    J.start(d["ref"])

    first = J.stop(d["ref"])
    second = J.stop(d["ref"])

    assert first == second
    assert first["state"] == "stopped"
    assert len([e for e in J.events(d["ref"]) if e["action"] == "cycle.stopped"]) == 1
