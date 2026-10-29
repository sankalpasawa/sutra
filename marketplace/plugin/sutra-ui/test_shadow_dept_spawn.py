"""test_shadow_dept_spawn.py -- the spawn hook (PRD A5.3.6): app._delegate_spawn decides the task's department before the worker is
provisioned, records the decision on the mission, and a failure in the decision never stops the spawn. The model is stubbed
(shadow_dept.CHOOSER) and the worker spawn is a recording fake; the mission store and the decision code are real."""
import pytest

from test_shadow_dept import org, reply, run  # noqa: F401  (the fixture)


@pytest.fixture
def spawner(org, monkeypatch):
    import app as app_module
    import shadow_runner
    spawned = []

    async def fake_spawn(build_args, cwd, manifest, register, env=None, publish=None, on_first_turn=None):
        spawned.append(manifest)
        return "worker-1"

    monkeypatch.setattr(shadow_runner, "spawn_delegate_session", fake_spawn)
    return type("Spawner", (), {"app": app_module, "spawned": spawned})


def _mission(spawner):
    store = spawner.app._mission_engine.MissionStore()
    m = store.create("Reply to the invoice dispute from the customer about last month's billing", "research",
                     manifest="Founder wrote this brief.")
    return store, m


def test_the_hook_decides_records_on_the_mission_and_the_task_still_spawns(org, spawner):
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use", ref=org.kids["Billing"], reason="Billing handles invoices")
    store, m = _mission(spawner)
    assert run(spawner.app._delegate_spawn(m)) == "worker-1"
    assert len(spawner.spawned) == 1
    stored = store.load(m["id"])
    assert stored["department_decision"]["final_action"] == "use"
    assert stored["department_ref"] == org.kids["Billing"]


def test_a_failing_decision_is_swallowed_and_the_task_still_spawns(org, spawner, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("the chooser is down")

    monkeypatch.setattr(org.sd, "decide_and_apply", boom)
    store, m = _mission(spawner)
    assert run(spawner.app._delegate_spawn(m)) == "worker-1"
    assert len(spawner.spawned) == 1
    assert "department_decision" not in (store.load(m["id"]) or {}) or not store.load(m["id"])["department_decision"]
