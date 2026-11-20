"""The human gate (MAN-8, D270, D306, D308): a question is answered once, the plan is evaluated again with what was allowed, the grants of the nodes that have not started are rewritten
(never a node that runs), the project starts when nothing is left to ask, and a no or a run-out ends it with "not approved"."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.nodes_store import AlreadyDecided

BASE = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def asking_github(rig, **kw):
    return rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)}, **kw)


def answer(rig, project_id, approval_id, decision, by="owner"):
    return rig.t.run(rig.projects.answer(project_id, approval_id, decision, by=by))


def grant(rig, ref):
    return json.loads(rig.sql("SELECT grants_json FROM agent_nodes WHERE plan_ref = ?", ref).fetchone()[0])


def test_a_plan_that_needs_github_holds_every_node_and_starts_nothing_until_the_owner_answers(rig):
    reservation, tasks = asking_github(rig)
    assert rig.project(reservation.project_id)["status"] == "awaiting_approval" and set(rig.node_states(tasks).values()) == {"awaiting_approval"}
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    assert asked.tier == 4 and asked.request["kind"] == "tier" and asked.node_id == rig.node_of(tasks["a2"])["id"]
    assert rig.start() == [] and rig.t.launcher.started == []
    assert grant(rig, "a2")["tool_profile"] == "none" and 4 not in grant(rig, "a2")["tiers"]
    [card] = rig.projects.approval_cards(reservation.project_id)
    assert card.kind == "tier" and card.options == ["allow_once", "allow_project", "deny"] and "GitHub" in card.question


@pytest.mark.parametrize("decision", ["allow_once", "allow_project"])
def test_an_allow_rewrites_the_grant_of_the_waiting_node_and_the_project_starts(rig, decision):
    reservation, tasks = asking_github(rig)
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    before = grant(rig, "a2")
    snapshot = answer(rig, reservation.project_id, asked.id, decision)
    after = grant(rig, "a2")
    assert after["tool_profile"] == "github" and 4 in after["tiers"] and after["id"] != before["id"] and grant(rig, "a1") == json.loads(rig.sql("SELECT grants_json FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0])
    assert snapshot["project"]["status"] == "running" and snapshot["approvals"] == [] and set(rig.node_states(tasks).values()) <= {"queued", "leased", "planned"}
    assert len(rig.t.launcher.started) == 2                                                               # the answer started them
    issued = [r for r in rig.audit("grant.issued") if r["node_id"] == rig.node_of(tasks["a2"])["id"]]
    assert len(issued) == 2 and [r["action"] for r in rig.audit("gate.decided")] == ["gate.decided"] and "decided_by owner" in rig.audit("gate.decided")[0]["reason"]


def test_a_node_that_has_spawned_is_never_given_a_new_grant(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", [])], needs={"a3": ("github",)})
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    rig.sql("UPDATE agent_nodes SET state = 'running' WHERE plan_ref = 'a1'")                              # a1 is out of the way of the gate: it has spawned
    before = rig.sql("SELECT grants_json FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0]
    rig.sql("UPDATE agent_nodes SET grants_json = json_set(grants_json, '$.id', 'gr_spawned') WHERE plan_ref = 'a1'")
    answer(rig, reservation.project_id, asked.id, "allow_once")
    assert json.loads(rig.sql("SELECT grants_json FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0])["id"] == "gr_spawned" and before


def test_a_no_to_one_steps_question_cancels_only_that_step_and_the_others_run(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", []), ("a4", "hr", ["a3"]), ("a5", "dev", [])], needs={"a3": ("github",)}, budget=60)
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    snapshot = answer(rig, reservation.project_id, asked.id, "deny")
    assert snapshot["project"]["status"] == "running" and rig.node_states(tasks)["a3"] == "cancelled"
    assert rig.node_states(tasks)["a4"] == "cancelled" and rig.t.status(tasks["a3"]) == "cancelled" and "not approved: you said no" in rig.t.row(tasks["a3"]).outcome
    assert "did not finish" in rig.t.row(tasks["a4"]).outcome                                                           # the step that waited for it is cancelled in plain words
    started = {s.task_id for s, *_ in rig.t.launcher.started}
    assert tasks["a3"] not in started and tasks["a4"] not in started and {tasks["a1"], tasks["a2"], tasks["a5"]} <= started
    for ref in ("a1", "a2", "a5"):
        rig.go(tasks[ref])
        rig.finish(tasks[ref])
    assert rig.project(reservation.project_id)["status"] == "done_with_open_items"


def test_a_no_to_the_estimate_stops_the_whole_project_with_not_approved(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 400, "a2": 400})
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    snapshot = answer(rig, reservation.project_id, asked.id, "deny")
    assert snapshot["project"]["status"] == "stopped" and snapshot["project"]["stop_reason"].startswith("not approved")
    assert set(rig.node_states(tasks).values()) == {"cancelled"} and rig.start() == [] and rig.t.launcher.started == []


def test_a_no_under_the_stop_all_policy_stops_the_project(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)})
    rig.sql("UPDATE projects SET failure_policy = 'stop_all' WHERE id = ?", reservation.project_id)
    answer(rig, reservation.project_id, rig.store.approvals(reservation.project_id)[0].id, "deny")
    assert rig.project(reservation.project_id)["status"] == "stopped"


def test_the_answer_is_final_a_repeat_is_a_no_op_another_answer_is_409_and_an_expired_question_says_so(rig):
    reservation, tasks = asking_github(rig)
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    answer(rig, reservation.project_id, asked.id, "allow_once")
    audit = len(rig.audit())
    assert answer(rig, reservation.project_id, asked.id, "allow_once")["project"]["status"] == "running" and len(rig.audit()) == audit
    with pytest.raises(AlreadyDecided):
        answer(rig, reservation.project_id, asked.id, "deny")
    other, more = rig.request([("b1", "dev", []), ("b2", "legal", [])], request_id="req-2", needs={"b2": ("github",)})
    [late] = rig.store.approvals(other.project_id, status="open")
    rig.t.run(rig.projects.tick(now=BASE + 90_000))                                                         # 24 h and more: the question ran out
    with pytest.raises(AppError) as error:
        answer(rig, other.project_id, late.id, "allow_once")
    assert "ran out" in str(error.value)


def test_a_question_of_another_project_is_404(rig):
    first, _ = asking_github(rig)
    second, _ = rig.request([("b1", "dev", []), ("b2", "legal", [])], request_id="req-2", needs={"b2": ("github",)})
    [mine] = rig.store.approvals(first.project_id, status="open")
    with pytest.raises(AppError) as error:
        answer(rig, second.project_id, mine.id, "allow_once")
    assert error.value.code == "not_found"


def test_the_plan_estimate_is_tier_5_and_is_answered_allow_once_or_deny_only(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 400, "a2": 400})
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    assert asked.tier == 5 and asked.request["kind"] == "plan_estimate" and asked.request["credits"] == 800 and asked.request["limit"] == 400
    with pytest.raises(AppError) as error:
        answer(rig, reservation.project_id, asked.id, "allow_project")
    assert error.value.code == "validation" and rig.project(reservation.project_id)["status"] == "awaiting_approval"
    [card] = rig.projects.approval_cards(reservation.project_id)
    assert card.options == ["allow_once", "deny"] and "800" in card.question
    assert answer(rig, reservation.project_id, asked.id, "allow_once")["project"]["status"] == "running"


def test_two_questions_the_project_waits_for_both(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)}, estimates={"a1": 400, "a2": 400})
    questions = rig.store.approvals(reservation.project_id, status="open")
    assert {q.request["kind"] for q in questions} == {"tier", "plan_estimate"}
    first = next(q for q in questions if q.request["kind"] == "tier")
    assert answer(rig, reservation.project_id, first.id, "allow_project")["project"]["status"] == "awaiting_approval" and rig.start() == []
    second = next(q for q in questions if q.request["kind"] == "plan_estimate")
    assert answer(rig, reservation.project_id, second.id, "allow_once")["project"]["status"] == "running"


def test_the_allowed_tool_reaches_the_run_through_the_node_block_of_task_json_and_only_for_that_node(rig):
    reservation, tasks = asking_github(rig)
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    answer(rig, reservation.project_id, asked.id, "allow_once")
    blocks = {ref: json.loads((rig.t.run_dir(task_id) / "task.json").read_text(encoding="utf-8"))["node"] for ref, task_id in tasks.items()}
    assert blocks["a2"]["tool_profile"] == "github" and blocks["a1"]["tool_profile"] == "none"


def test_a_rewritten_grant_keeps_the_words_output_auto(rig):
    rig.projects._output_name = lambda dept: "auto"
    reservation, tasks = asking_github(rig)
    answer(rig, reservation.project_id, rig.store.approvals(reservation.project_id)[0].id, "allow_once")
    issued = [r for r in rig.audit("grant.issued") if r["node_id"] == rig.node_of(tasks["a2"])["id"]]
    assert len(issued) == 2 and all("output auto (decided in the run)" in r["reason"] for r in issued) and "tools github" in issued[1]["reason"]


# ---- the app's own data is a question to the owner, never a planner's say (D325) ----------------------------------------------------------------

def test_a_planner_need_for_the_apps_own_data_is_a_question_the_grant_does_not_hold_it_before_and_decide_for_me_never_answers_it(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a1": ("sutra",)}, decide_for_me=True)
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    assert asked.request["kind"] == "sutra_tools" and asked.tier == 1 and asked.node_id == rig.node_of(tasks["a1"])["id"]
    assert grant(rig, "a1")["tool_profile"] == "none"
    assert rig.project(reservation.project_id)["status"] == "awaiting_approval" and rig.audit("gate.decided") == [] and rig.start() == []
    [card] = rig.projects.approval_cards(reservation.project_id)
    assert card.options == ["allow_once", "deny"] and "app's own data" in card.question


def test_only_an_allow_by_the_owner_gives_the_sutra_tools_and_a_no_cancels_only_that_step(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a1": ("sutra",)})
    answer(rig, reservation.project_id, rig.store.approvals(reservation.project_id)[0].id, "allow_once")
    assert grant(rig, "a1")["tool_profile"] == "sutra"
    other, more = rig.request([("b1", "dev", []), ("b2", "legal", [])], request_id="req-2", needs={"b1": ("sutra", "github")})
    assert grant_of(rig, "b1")["tool_profile"] == "none"                                              # neither tool is held before the owner answers
    for approval in rig.store.approvals(other.project_id, status="open"):
        answer(rig, other.project_id, approval.id, "deny" if approval.request["kind"] == "sutra_tools" else "allow_once")
    assert rig.sql("SELECT state FROM agent_nodes WHERE plan_ref = 'b1'").fetchone()[0] == "cancelled"
    assert rig.project(other.project_id)["status"] == "running"


def test_a_plan_node_that_asks_for_sutra_is_never_given_it_by_its_role_alone(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a1": ("sutra",), "a2": ("sutra",)})
    assert grant(rig, "a1")["tool_profile"] == "none" and grant(rig, "a2")["tool_profile"] == "none"
    assert len(rig.store.approvals(reservation.project_id, status="open")) == 2


def grant_of(rig, ref):
    return json.loads(rig.sql("SELECT grants_json FROM agent_nodes WHERE plan_ref = ?", ref).fetchone()[0])
