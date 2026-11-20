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
