"""Decide for me (MAN-8, D294, D295): the Gatekeeper's rule table answers the questions it may, in the transaction that makes the project, each answer audited as `decided_by
rule:decide_for_me`. It never raises credits, never answers a permission of the computer, tier 6 is never granted or asked, and a node's words cannot turn it on."""
import json
import time

import pytest
from fastapi.testclient import TestClient
from orchestrator.projects_rig import PRig  # noqa: F401
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_projects_adopt import BASE as APP_BASE
from orchestrator.test_projects_adopt import HEADERS, NO_REQUESTS, make_app, rows
from orchestrator.test_scripted_conversation import ORG

from sutra_app.orchestrator.gatekeeper import DECIDE_FOR_ME, RULE_TABLE, decide_for_me_answer, on_scope_violation

T0 = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def decided(rig):
    return [r for r in rig.audit("gate.decided")]


def test_every_row_of_the_rule_table_answers_as_it_says():
    assert {name for name, _, _ in RULE_TABLE} == {"tiers_0_3", "tier_4_github", "scope_wide_or_missing", "credits_raise", "estimate_within_ceiling", "scope_violation", "sutra_tools", "tier_6", "system_permission"}
    for tier in (1, 2, 3):
        assert decide_for_me_answer("tier", tier).decision == "allow_project"
    assert decide_for_me_answer("tier", 4).decision == "allow_project"                                       # read-only GitHub, for this project only
    assert decide_for_me_answer("scope", 2).decision == "allow_once" and "apart from other writers" in decide_for_me_answer("scope", 2).why
    assert decide_for_me_answer("plan_estimate", 5, estimate=800, ceiling=1000).decision == "allow_once"
    assert decide_for_me_answer("plan_estimate", 5, estimate=1000, ceiling=1000).decision == "allow_once"
    assert decide_for_me_answer("plan_estimate", 5, estimate=1001, ceiling=1000) is None                    # over the ceiling: the owner decides
    assert decide_for_me_answer("plan_estimate", 5, estimate=10, ceiling=None) is None                      # no ceiling: never
    assert decide_for_me_answer("tier", 5) is None and decide_for_me_answer("credits", 5) is None             # credits are never raised
    assert decide_for_me_answer("tier", 6) is None and decide_for_me_answer("scope", 6) is None              # tier 6 is never granted
    assert decide_for_me_answer("system", 1) is None and decide_for_me_answer("system", 2) is None           # never a permission of the computer (D295)
    assert decide_for_me_answer("mystery", 1) is None and on_scope_violation() == "quarantine"


def test_with_decide_for_me_on_the_questions_are_answered_at_once_and_no_gate_is_held(rig):
    rig.projects._output_of = lambda dept: "edit"
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", [])], needs={"a2": ("github",)}, scope={"a1": ("site/", "docs/", "assets/")},
                                     estimates={"a1": 300, "a2": 300, "a3": 300}, decide_for_me=True)
    project = rig.project(reservation.project_id)
    assert project["status"] == "running" and project["decide_for_me"] == 1 and rig.store.approvals(reservation.project_id, status="open") == []
    answered = rig.store.approvals(reservation.project_id)
    assert {(a.request["kind"], a.status, a.decided_by) for a in answered} == {("tier", "allowed_project", DECIDE_FOR_ME), ("scope", "allowed_once", DECIDE_FOR_ME), ("plan_estimate", "allowed_once", DECIDE_FOR_ME)}
    assert len(decided(rig)) == 3 and all(f"decided_by {DECIDE_FOR_ME}" in r["reason"] and r["actor"] == "gatekeeper" for r in decided(rig))
    assert json.loads(rig.sql("SELECT grants_json FROM agent_nodes WHERE plan_ref = 'a2'").fetchone()[0])["tool_profile"] == "github"
    assert len(rig.start()) >= 1 and rig.t.launcher.started                                                  # nothing was held; the writers are kept apart, so they start one after another (MAN-10)


def test_credits_over_the_ceiling_stay_a_question_for_the_owner_even_with_decide_for_me(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 900, "a2": 900}, decide_for_me=True)         # 1800 > the ceiling of 1000
    [open_one] = rig.store.approvals(reservation.project_id, status="open")
    assert open_one.request["kind"] == "plan_estimate" and open_one.tier == 5 and rig.project(reservation.project_id)["status"] == "awaiting_approval" and rig.start() == []
    assert decided(rig) == []


def test_the_owners_own_budget_is_the_ceiling_and_never_raised(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 900, "a2": 900}, budget=600, decide_for_me=True)
    assert rig.project(reservation.project_id)["budget_credits"] == 1200                                    # the ceiling: two slices of the owner's 600 each
    assert rig.store.approvals(reservation.project_id) == []                                                  # the owner's number is the answer: no estimate question (D300), nothing for a rule to raise


def test_a_system_permission_question_is_never_answered_by_the_rule_table(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], decide_for_me=True)
    with rig.t.db.tx() as tx:
        asked = rig.store.open_approval(tx, project_id=reservation.project_id, node_id=rig.node_of(tasks["a1"])["id"], tier=2, request={"kind": "system", "item": "files"}, expires_at=T0 + 86_400)
        rig.projects._decide_by_rule(tx, reservation.project_id)
    assert rig.store.get_approval(asked.id).status == "open" and decided(rig) == []


def test_a_rule_can_answer_only_for_a_project_that_asked_for_it(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)})                    # Decide for me is off
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    with pytest.raises(Exception) as error:
        with rig.t.db.tx() as tx:
            rig.store.decide(tx, asked.id, "allow_project", decided_by=DECIDE_FOR_ME)
    assert "Decide for me is on" in str(error.value) and rig.store.get_approval(asked.id).status == "open"


def test_the_switch_comes_with_the_request_and_reaches_the_workers_as_their_own_setting(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=APP_BASE) as client:
        services = app.state.services
        connector.push(decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")),
                       assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote", depends_on=("a1",))), {"kind": "node_plan", "steps": [{"ref": "a2", "scope": [], "needs": ["github"]}]})
        response = client.post(f"/api/chats/{ORG}/messages", json={"text": "A page and a quote", "decide_for_me": True}, headers=HEADERS)
        assert response.status_code == 202, response.text
        deadline = time.time() + 10
        while services.runner.busy and time.time() < deadline:
            time.sleep(0.02)
        project = rows(services, "SELECT * FROM projects")[0]
        assert project["decide_for_me"] == 1 and project["status"] in ("running", "done") and rows(services, "SELECT * FROM approvals")[0]["decided_by"] == DECIDE_FOR_ME
        settings = [json.loads(r["settings_json"] or "{}") for r in rows(services, "SELECT settings_json FROM tasks")]
        assert settings and all(s.get("J2_DECIDE_FOR_ME") == "1" for s in settings)


def test_without_the_switch_nothing_is_decided_for_the_owner(tmp_path):
    app, connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=APP_BASE) as client:
        services = app.state.services
        connector.push(decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")),
                       assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote", depends_on=("a1",))), {"kind": "node_plan", "steps": [{"ref": "a2", "scope": [], "needs": ["github"]}]})
        client.post(f"/api/chats/{ORG}/messages", json={"text": "A page and a quote"}, headers=HEADERS)
        deadline = time.time() + 10
        while services.runner.busy and time.time() < deadline:
            time.sleep(0.02)
        assert rows(services, "SELECT * FROM projects")[0]["decide_for_me"] == 0 and rows(services, "SELECT status FROM approvals")[0]["status"] == "open"
        assert all("J2_DECIDE_FOR_ME" not in json.loads(r["settings_json"] or "{}") for r in rows(services, "SELECT settings_json FROM tasks")) and NO_REQUESTS


# ---- turning it on later (P2, D319) -----------------------------------------------------------------------------------------------------

def test_turning_decide_for_me_on_answers_the_open_questions_at_once_and_the_project_starts(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)})
    assert rig.project(reservation.project_id)["status"] == "awaiting_approval" and rig.start() == []
    assert rig.projects.owner_turned_on("sales") == 1
    assert rig.project(reservation.project_id)["status"] == "running" and rig.store.approvals(reservation.project_id, status="open") == []
    assert [a.decided_by for a in rig.store.approvals(reservation.project_id)] == [DECIDE_FOR_ME] and len(rig.start()) == 2
    assert rig.audit("project.decide_for_me") and rig.projects.owner_turned_on("sales") == 0                          # a project that is on already is not touched again


def test_turning_it_on_does_not_answer_what_the_table_may_not_and_turning_it_off_changes_nothing(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 900, "a2": 900})           # over the project ceiling
    assert rig.projects.owner_turned_on("web") == 1
    assert rig.project(reservation.project_id)["status"] == "awaiting_approval" and len(rig.store.approvals(reservation.project_id, status="open")) == 1
    other, more = rig.request([("b1", "dev", []), ("b2", "legal", [])], request_id="req-2", needs={"b2": ("github",)}, decide_for_me=True)
    assert rig.project(other.project_id)["decide_for_me"] == 1                                                         # off later: this one stays as it was made


def test_a_project_of_another_team_is_not_touched(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)})
    assert rig.projects.owner_turned_on("ops") == 0 and rig.project(reservation.project_id)["status"] == "awaiting_approval"
