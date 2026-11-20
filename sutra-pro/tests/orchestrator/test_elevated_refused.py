"""An elevated Windows process refuses new nodes (MAN-15, D295): what it writes would belong to the administrator. Monkeypatched platform: nothing real is elevated."""
import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app import oslayer
from sutra_app.orchestrator.projects import ProjectStep


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def test_an_elevated_process_makes_no_node_and_says_why_in_plain_words(rig):
    rig.projects._elevated = lambda: True
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    assert reservation.ok is False and "administrator" in reservation.why and tasks == {}
    project = rig.project(reservation.project_id)
    assert project["status"] == "failed" and rig.sql("SELECT count(*) FROM agent_nodes").fetchone()[0] == 0 and rig.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0
    assert [r["action"] for r in rig.audit("system.elevated")] == ["system.elevated"] and [r["action"] for r in rig.audit("plan.refused")] == ["plan.refused"]


def test_a_normal_process_is_not_refused(rig):
    rig.projects._elevated = lambda: False
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    assert reservation.ok and len(tasks) == 2


def test_the_real_check_is_false_off_windows_and_follows_the_platform_call_on_windows(monkeypatch):
    monkeypatch.setattr(oslayer, "IS_WINDOWS", False)
    assert oslayer.is_elevated() is False
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)
    import types
    fake = types.SimpleNamespace(windll=types.SimpleNamespace(shell32=types.SimpleNamespace(IsUserAnAdmin=lambda: 1)))
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake)
    assert oslayer.is_elevated() is True
    assert ProjectStep("a1", "web").scope == ()
