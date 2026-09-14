"""A mission is RUNNING when execution begins, not when turn one ends.

THE BUG (founder, 2026-09-14): "chat appears, worker visibly talking in it,
card still says QUEUED, turn 0 of 20 -- it flips to RUNNING on Shadow's
SECOND interaction."

It was the backend, and it was late by the whole first turn. Ledger for
m-b697c6ac8ee7:

    t+  0.0s  brief_confirm  proposed
    t+  1.0s  spawn          session adda99dd spawned + published as a chat
    t+ 95.0s  spawn          session adda99dd provisioned
    t+ 95.0s  running        admitted            <- 94s late
    t+101.0s  decision       (the "second interaction")

`spawn_delegate_session` publishes the chat from its frame hook the moment
the CLI announces a session id, but it does not RETURN until demux_turn
finishes -- the end of the entire first agentic turn. provision_target
therefore returns late, and start_mission, the only caller of the scheduler
on that path, admitted only then. Eight real starts: 7, 10, 12, 14, 15, 31,
44, 95 seconds; median 15.

THE FIX: admit at session adoption, where the chat is already published
(app._publish_delegate_chat step 1b), through the EXISTING authority --
MissionScheduler.start, which is idempotent and still owns the cap. No new
state, no second admitter, and the LAUNCH is not moved (the pump and the
observer must still attach after the spawn turn).

Run: .venv/bin/python -m unittest test_shadow_early_admit -v
"""
import asyncio
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-admit-")
os.environ["SUTRA_UI_CHATS"] = tempfile.mkdtemp(prefix="shadow-admit-chats-")

import app as app_module  # noqa: E402
import mission_engine  # noqa: E402
import shadow_runner  # noqa: E402


def _wipe():
    """Each test gets an empty store: the cap test deliberately fills every
    execution slot, and a leftover `running` row would silently starve any
    test that ran after it."""
    import glob
    import shadow_ledger
    for p in glob.glob(os.path.join(shadow_ledger.shadow_home(),
                                    "missions", "*.json")):
        try:
            os.remove(p)
        except OSError:
            pass


def _mission(objective="admit me", mode="new"):
    store = mission_engine.MissionStore()
    m = store.create(objective, "fix", target_mode=mode, target_session=None,
                     done_when=[], manifest="say READY")
    store.transition(m["id"], "brief_confirm", "proposed")
    return store, m["id"]


class AdmissionHappensAtAdoption(unittest.TestCase):
    """publish(sid) is the moment a real process has taken the brief."""

    def setUp(self):
        _wipe()
        shadow_runner.DELEGATES.clear()

    def test_the_row_is_running_the_moment_the_session_is_adopted(self):
        store, mid = _mission()
        self.assertEqual(store.load(mid)["state"], "brief_confirm")
        publish = app_module._publish_delegate_chat(store.load(mid))
        publish("sess-adopt-1")
        m = store.load(mid)
        self.assertEqual(
            m["state"], "running",
            "execution has begun -- a live process has the brief and has "
            "announced its id -- so the record must say running, not wait "
            "out the whole first turn")
        self.assertEqual(m["target_session"], "sess-adopt-1")

    def test_the_ledger_says_admitted_not_some_new_word(self):
        store, mid = _mission()
        app_module._publish_delegate_chat(store.load(mid))("sess-adopt-2")
        rows = [r for r in mission_engine.shadow_ledger.read("missions")
                if r.get("mission_id") == mid]
        self.assertTrue(
            any(r.get("state") == "running" and "admitted" in (r.get("note") or "")
                for r in rows),
            "the existing scheduler note must be what lands: %r" % (rows,))

    def test_a_later_start_mission_is_a_no_op_for_the_state(self):
        """start_mission still runs; it simply finds the state settled."""
        store, mid = _mission()
        app_module._publish_delegate_chat(store.load(mid))("sess-adopt-3")
        before = store.load(mid)
        again = mission_engine.MissionScheduler(store).start(mid)
        self.assertEqual(again["state"], "running")
        self.assertEqual(again["seq"], before["seq"],
                         "idempotent: no second transition was written")

    def test_the_cap_is_not_bypassed(self):
        """A full cap must leave the row alone -- a queued mission must never
        be a mission with a live worker."""
        store = mission_engine.MissionStore()
        for i in range(mission_engine.MAX_RUNNING):
            f = store.create("filler %d" % i, "fix", target_mode="new",
                             target_session="filler-%d" % i, done_when=[])
            store.transition(f["id"], "brief_confirm", "proposed")
            store.transition(f["id"], "running", "admitted")
        store2, mid = _mission("over the cap")
        app_module._publish_delegate_chat(store2.load(mid))("sess-capped")
        self.assertEqual(
            store2.load(mid)["state"], "brief_confirm",
            "with every slot taken, early admission must decline and leave "
            "the decision to the existing late path")

    def test_an_existing_target_mission_is_untouched_here(self):
        """provision/publish is the new-chat path; nothing else changes."""
        store, mid = _mission("existing", mode="existing")
        store.load(mid)
        self.assertEqual(store.load(mid)["state"], "brief_confirm")


class AFailureAfterAdoptionIsStillRecorded(unittest.IsolatedAsyncioTestCase):
    """The narrow widening of start_mission_async's guard."""

    def setUp(self):
        _wipe()
        shadow_runner.DELEGATES.clear()

    async def _settle(self, store, mid, limit=200):
        for _ in range(limit):
            await asyncio.sleep(0.01)
            if store.load(mid)["state"] in mission_engine.TERMINAL:
                return

    async def test_a_spawn_that_dies_after_adoption_ends_as_failed(self):
        store, mid = _mission("dies after adoption")

        async def boom(mission):
            # exactly what really happens: adopt (publish -> running), then
            # demux_turn comes back empty and spawn_delegate_session raises
            app_module._publish_delegate_chat(store.load(mid))("sess-orphan")
            raise RuntimeError("delegate session failed to boot")

        shadow_runner.start_mission_async(
            mid, lambda *a, **k: None, provisioner=boom)
        await self._settle(store, mid)
        self.assertEqual(
            store.load(mid)["state"], "failed",
            "a running row whose delegate was reaped is this mission's "
            "failure and must be recorded, not left at RUNNING forever")

    async def test_a_HEALTHY_running_mission_is_never_downgraded(self):
        """The race rule the original comment protects: a duplicate starter's
        failure is not the mission's failure."""
        store, mid = _mission("healthy")
        app_module._publish_delegate_chat(store.load(mid))("sess-healthy")
        shadow_runner.DELEGATES["sess-healthy"] = object()   # a live worker

        async def boom(mission):
            raise RuntimeError("the DUPLICATE starter fell over")

        shadow_runner.start_mission_async(
            mid, lambda *a, **k: None, provisioner=boom)
        for _ in range(40):
            await asyncio.sleep(0.01)
        self.assertEqual(
            store.load(mid)["state"], "running",
            "a mission with a live delegate must survive somebody else's "
            "exception")


class TheStateVocabularyIsUnchanged(unittest.TestCase):
    """No state was invented and no transition was redesigned."""

    def setUp(self):
        _wipe()
        shadow_runner.DELEGATES.clear()

    def test_the_canonical_states_still_exist(self):
        for s in ("brief_confirm", "queued", "running", "paused", "blocked",
                  "done", "failed", "stopped"):
            self.assertIn(s, mission_engine.STATES)

    def test_the_lifecycle_exits_are_still_legal(self):
        T = mission_engine.TRANSITIONS
        self.assertIn("paused", T["running"])      # pause
        self.assertIn("running", T["paused"])      # resume
        self.assertIn("done", T["running"])        # done
        self.assertIn("failed", T["running"])      # failed
        self.assertIn("blocked", T["running"])     # needs-you
        self.assertIn("running", T["blocked"])     # answered -> back to work

    def test_admission_is_still_the_schedulers_job_alone(self):
        store, mid = _mission("who admits")
        sched = mission_engine.MissionScheduler(store)
        m = sched.start(mid)
        self.assertEqual(m["state"], "running")
        self.assertEqual(sched.start(mid)["state"], "running")   # idempotent


if __name__ == "__main__":
    unittest.main()
