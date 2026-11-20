"""A refusal the probe could not see (MAN-15, D295): a node that ends on EPERM or WinError 5 `needs_system_permission`: it is not retried and it raises ONE card for the project. An ordinary
crash is retried as before."""
import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.conductor import NEEDS_SYSTEM_PERMISSION


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def running(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", [])])
    rig.start()
    for task_id in tasks.values():
        rig.go(task_id)
    return reservation, tasks


@pytest.mark.parametrize("outcome", ["EPERM: operation not permitted, open '/Users/x/Desktop/site/index.html'", "PermissionError: [WinError 5] Access is denied: 'C:\\\\work\\\\a.txt'"])
def test_a_node_that_ends_on_a_refusal_of_the_computer_needs_a_permission_and_is_not_retried(rig, outcome):
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome=outcome, handoff=False)
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["state"] == "failed" and node["failure_reason"] == NEEDS_SYSTEM_PERMISSION and node["attempt"] == 1 and rig.audit("node.retry") == []
    [question] = [a for a in rig.store.approvals(reservation.project_id, status="open") if a.request.get("kind") == "system"]
    assert question.tier == 2 and question.request["late"] == 1 and question.node_id == node["id"]
    assert [r["action"] for r in rig.audit("system.late_denied")] == ["system.late_denied"] and [r["action"] for r in rig.audit("system.asked")] == ["system.asked"]
    assert len(rig.sql("SELECT * FROM chat_messages WHERE src_ref = ?", f"project:{reservation.project_id}#late").fetchall()) == 1


def test_a_second_refusal_in_the_same_project_raises_no_second_card(rig):
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome="EPERM: operation not permitted", handoff=False)
    rig.finish(tasks["a2"], status="crashed", outcome="EPERM: operation not permitted", handoff=False)
    assert len([a for a in rig.store.approvals(reservation.project_id) if a.request.get("kind") == "system"]) == 1
    assert len(rig.audit("system.late_denied")) == 2 and len(rig.audit("system.asked")) == 1
    assert rig.sql("SELECT state FROM agent_nodes WHERE plan_ref = 'a3'").fetchone()[0] == "running"       # the step that was not refused goes on


def test_an_ordinary_crash_is_still_retried_once(rig):
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome="the model said something odd", handoff=False)
    assert rig.sql("SELECT attempt, state FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[:] == (2, "queued") and rig.audit("system.late_denied") == []


def test_check_again_on_a_late_card_really_probes_and_stays_open_while_the_folder_still_refuses(rig, tmp_path):
    from sutra_app.syspermissions import MacAdapter, Need

    class Blocked(MacAdapter):
        blocked = True

        def probe(self, folder, *, write):
            return [Need("files_folders", "write", "Desktop")] if self.blocked else []
    rig.projects._folder_of = lambda: str(tmp_path)
    rig.projects._adapter = adapter = Blocked(home=tmp_path)
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome="EPERM: operation not permitted", handoff=False)
    snapshot = rig.t.run(rig.projects.system_check(reservation.project_id, "unknown"))
    assert len(snapshot["system_cards"]) == 1 and [r["action"] for r in rig.audit("system.still_needed")] == ["system.still_needed"]
    adapter.blocked = False
    snapshot = rig.t.run(rig.projects.system_check(reservation.project_id, "unknown"))
    assert snapshot["system_cards"] == [] and [r["action"] for r in rig.audit("system.cleared")] == ["system.cleared"]


# ---- P3, m1, m2, m3 ---------------------------------------------------------------------------------------------------------------------

def blocked_then_allowed(rig, tmp_path):
    from sutra_app.syspermissions import MacAdapter, Need

    class Switch(MacAdapter):
        blocked = True

        def probe(self, folder, *, write):
            return [Need("files_folders", "write", "Desktop")] if self.blocked else []
    rig.projects._folder_of = lambda: str(tmp_path)
    rig.projects._adapter = adapter = Switch(home=tmp_path)
    return adapter


def test_after_the_late_card_clears_the_failed_step_gets_one_fresh_attempt_that_does_not_spend_its_retry(rig, tmp_path):
    adapter = blocked_then_allowed(rig, tmp_path)
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome="EPERM: operation not permitted", handoff=False)
    adapter.blocked = False
    rig.t.run(rig.projects.system_check(reservation.project_id, "unknown"))
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["attempt"] == 2 and node["state"] in ("queued", "leased") and [r["action"] for r in rig.audit("node.restarted")] == ["node.restarted"] and rig.audit("node.retry") == []
    rig.start()
    rig.go(node["task_id"])
    rig.finish(node["task_id"], status="crashed", outcome="a real crash", handoff=False)                         # its own retry is still there
    assert rig.sql("SELECT attempt FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0] == 3 and [r["action"] for r in rig.audit("node.retry")] == ["node.retry"]


def test_the_late_restart_happens_once_for_each_node(rig, tmp_path):
    adapter = blocked_then_allowed(rig, tmp_path)
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome="EPERM: operation not permitted", handoff=False)
    adapter.blocked = False
    rig.t.run(rig.projects.system_check(reservation.project_id, "unknown"))
    with rig.t.db.tx() as tx:
        assert rig.projects.conductor.restart_after_permission(tx, rig.sql("SELECT id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0]) is False


def test_a_late_card_that_runs_out_or_meets_a_sleep_does_not_stop_the_healthy_steps(rig):
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome="EPERM: operation not permitted", handoff=False)
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE_NOW + 5)
    rig.t.run(rig.projects.tick(now=BASE_NOW + 10))
    done = rig.t.run(rig.projects.tick(now=BASE_NOW + 5000))                                                        # a sleep with the late card open
    assert done["refused"] == [] and rig.project(reservation.project_id)["status"] == "running" and rig.node_states(tasks)["a2"] == "running"
    rig.sql("UPDATE approvals SET expires_at = ?", BASE_NOW + 5001)
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE_NOW + 5990)
    done = rig.t.run(rig.projects.tick(now=BASE_NOW + 6000))                                                        # and the 24 h end only ends the card
    assert done["refused"] == [] and rig.node_states(tasks)["a3"] == "running" and rig.project(reservation.project_id)["status"] == "running"
    assert rig.sql("SELECT status FROM approvals").fetchone()[0] == "expired"


def test_the_generic_answer_route_refuses_a_permission_question_and_points_to_check_and_skip(rig, tmp_path):
    from sutra_app.orchestrator.errors import AppError
    reservation, tasks = running(rig)
    rig.finish(tasks["a1"], status="crashed", outcome="EPERM: operation not permitted", handoff=False)
    [asked] = [a for a in rig.store.approvals(reservation.project_id, status="open")]
    with pytest.raises(AppError) as error:
        rig.t.run(rig.projects.answer(reservation.project_id, asked.id, "allow_once"))
    assert error.value.code == "validation" and "Check again or Skip" in str(error.value) and rig.store.get_approval(asked.id).status == "open"


BASE_NOW = 1793786400
