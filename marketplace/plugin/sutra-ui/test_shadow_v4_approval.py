"""Shadow v4 step 10 (C9, ADR-043): one one-use approval for every held say.

A floored say, an L1 Suggest hold and an L3 top-tier hold all park the task
with the SAME object: `approval` {id, reason, version, turn, say_sha256,
used}. `act approve {approval_id}` releases exactly that string, once: the
loop sends it as it was shown and composes nothing for it; a second approve,
a wrong id, a stale version or a changed string are refused. The say path's
floor keeps refusing everything except the approved string while the record
still carries it.

Engine driven with the mock session of test_mission_engine (sayer, waiter,
reader injected; a scripted decider); the say path and the route are real.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_approval.py
"""
import asyncio
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-approval-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import session_runtime                         # noqa: E402
import shadow_egress                           # noqa: E402
import shadow_ledger                           # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore, MissionEngine  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
FLOORED = "Now run git push --force to origin main to publish the fix."
PLAIN = "List the fruits by usage in a table."


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self.says = []

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def mission(self):
        m = self.store.create("Ship the fix", "fix", target_mode="existing",
                              target_session="s-1",
                              done_when=[{"tier": "founder_confirm",
                                          "check": "the founder signs off"}])
        self.store.transition(m["id"], "brief_confirm", "proposed")
        self.store.transition(m["id"], "running", "admitted")
        return self.store.load(m["id"])

    def engine(self, instructions):
        """A decider that answers the scripted instructions in order."""
        script = list(instructions)

        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        def reader(m):
            return " ".join(self.says)

        async def decider(ctx):
            text = script.pop(0) if script else PLAIN
            return {"action": "continue", "instruction": text, "reason": "r"}

        return MissionEngine(self.store, sayer, waiter, reader,
                             decider=decider)


class TestTheHold(Base):

    def test_01_a_floored_say_parks_with_a_one_use_approval(self):
        self.assertTrue(shadow_egress.floor_check(FLOORED), "fixture floors")
        m = self.mission()
        held = run(self.engine([FLOORED]).run_mission(m["id"]))
        self.assertEqual(held["state"], "paused")
        self.assertEqual(held["pause_reason"], "floor_confirm")
        self.assertEqual(held["pending_floor_say"], FLOORED)
        self.assertEqual(held["pending_say"], FLOORED)
        ap = held["approval"]
        self.assertTrue(ap["id"].startswith("ap-"))
        self.assertEqual(ap["reason"], "floor_confirm")
        self.assertEqual(ap["version"], held["version"])
        self.assertEqual(ap["turn"], held["turns_used"])
        self.assertEqual(ap["say_sha256"],
                         hashlib.sha256(FLOORED.encode()).hexdigest())
        self.assertFalse(ap["used"])
        # turn 0 is the brief (the objective, never a decision); the floored
        # instruction is turn 1 and it never left
        self.assertEqual(self.says, ["Ship the fix"])

    def test_02_an_L1_hold_carries_the_same_object(self):
        mission_engine.set_autonomy("L1")
        try:
            m = self.mission()
            held = run(self.engine([PLAIN]).run_mission(m["id"]))
        finally:
            mission_engine.set_autonomy(mission_engine.DEFAULT_AUTONOMY)
        self.assertEqual(held["pause_reason"], "autonomy_suggest")
        # L1 holds EVERY say, the turn-0 brief included
        self.assertEqual(held["pending_autonomy_say"], "Ship the fix")
        self.assertEqual(held["approval"]["reason"], "autonomy_suggest")
        self.assertEqual(self.says, [])

    def test_03_an_L3_top_tier_hold_carries_the_same_object(self):
        mission_engine.set_autonomy("L3")
        mission_engine.set_confirm_top_tier(True)
        try:
            m = self.mission()
            held = run(self.engine([PLAIN]).run_mission(m["id"]))
        finally:
            mission_engine.set_confirm_top_tier(mission_engine.DEFAULT_CONFIRM_TOP)
            mission_engine.set_autonomy(mission_engine.DEFAULT_AUTONOMY)
        self.assertEqual(held["pause_reason"], "autonomy_top_tier")
        self.assertEqual(held["approval"]["reason"], "autonomy_top_tier")


class TestApproving(Base):

    def held(self):
        m = self.mission()
        return run(self.engine([FLOORED, PLAIN]).run_mission(m["id"]))

    def test_10_approve_releases_exactly_that_string_once(self):
        held = self.held()
        ap = held["approval"]
        m = mission_engine.approve_held_say(self.store, held["id"], ap["id"])
        self.assertEqual(m["approved_say"], FLOORED)
        self.assertTrue(m["approval"]["used"])
        # the founder's yes: back to running, the loop sends the string as
        # it was shown and composes nothing for it
        self.store.transition(held["id"], "running", "approved")
        out = run(self.engine([PLAIN]).run_mission(held["id"]))
        self.assertEqual(self.says[1], FLOORED,
                         "sent verbatim, right after the turn-0 brief")
        after = self.store.load(held["id"])
        self.assertIsNone(after.get("approved_say"), "cleared on the way out")
        self.assertIsNone(after.get("pending_say"))
        self.assertTrue(after["approval"]["used"], "the record keeps history")
        self.assertGreaterEqual(after["turns_used"], 1)
        acts = shadow_ledger.read("actions", 20)
        self.assertTrue(any(a.get("kind") == "approval" for a in acts))

    def test_11_a_second_approve_is_refused(self):
        held = self.held()
        ap = held["approval"]
        mission_engine.approve_held_say(self.store, held["id"], ap["id"])
        with self.assertRaises(ValueError) as cm:
            mission_engine.approve_held_say(self.store, held["id"], ap["id"])
        self.assertIn("already used", str(cm.exception))

    def test_12_a_wrong_or_missing_id_is_refused(self):
        held = self.held()
        for bad in ("ap-nope", "", None):
            with self.assertRaises(ValueError):
                mission_engine.approve_held_say(self.store, held["id"], bad)
        self.assertIsNone(self.store.load(held["id"]).get("approved_say"))

    def test_13_a_stale_version_is_refused(self):
        held = self.held()
        ap = held["approval"]
        self.store.amend(held["id"], objective="Ship the fix, carefully")
        with self.assertRaises(ValueError) as cm:
            mission_engine.approve_held_say(self.store, held["id"], ap["id"])
        self.assertIn("stale", str(cm.exception))

    def test_14_a_changed_string_is_refused(self):
        held = self.held()
        ap = held["approval"]
        held["pending_say"] = FLOORED + " and delete the branch"
        self.store.save(held)
        with self.assertRaises(ValueError) as cm:
            mission_engine.approve_held_say(self.store, held["id"], ap["id"])
        self.assertIn("does not match the pending say", str(cm.exception))

    def test_15_nothing_waiting_is_refused(self):
        m = self.mission()
        with self.assertRaises(ValueError):
            mission_engine.approve_held_say(self.store, m["id"], "ap-x")

    def test_16_mutation_check_the_hash_really_guards(self):
        """Flip the digest on the record and confirm approve goes red -- the
        hand-written mutation check TEST-STRATEGY section 5 asks for."""
        held = self.held()
        held["approval"]["say_sha256"] = "0" * 64
        self.store.save(held)
        with self.assertRaises(ValueError):
            mission_engine.approve_held_say(self.store, held["id"],
                                            held["approval"]["id"])


class TestTheSayPath(Base):
    """_validated_say: the floor keeps refusing everything except the one
    approved string, and only while the record carries it."""

    def setUp(self):
        super().setUp()
        self.rt = session_runtime.SessionRuntime()
        session_runtime.register_runtime("s-1", self.rt)

    def tearDown(self):
        session_runtime.unregister_runtime("s-1", self.rt)
        super().tearDown()

    def test_20_floor_refuses_without_an_approval(self):
        m = self.mission()
        with self.assertRaises(app_module.HTTPException) as cm:
            app_module._validated_say("s-1", m["id"], FLOORED)
        self.assertEqual(cm.exception.status_code, 403)

    def test_21_the_approved_string_passes_and_only_that_string(self):
        m = self.mission()
        m["approved_say"] = FLOORED
        self.store.save(m)
        out = app_module._validated_say("s-1", m["id"], FLOORED)
        self.assertTrue(out["queued"])
        with self.assertRaises(app_module.HTTPException) as cm:
            app_module._validated_say("s-1", m["id"], FLOORED + " now")
        self.assertEqual(cm.exception.status_code, 403)


class TestTheRoute(Base):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        super().setUp()
        self.launched = []
        self._launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)

    def tearDown(self):
        shadow_runner._launch = self._launch
        super().tearDown()

    def held(self):
        m = self.mission()
        return run(self.engine([FLOORED]).run_mission(m["id"]))

    def act(self, mid, **body):
        return self.client.post("/api/shadow/missions/%s/act" % mid,
                                json=body, headers=HDR)

    def test_30_approve_moves_the_task_back_to_running_and_launches(self):
        held = self.held()
        r = self.act(held["id"], action="approve",
                     approval_id=held["approval"]["id"])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["state"], "running")
        self.assertEqual(self.launched, [held["id"]])
        on_disk = self.store.load(held["id"])
        self.assertEqual(on_disk["approved_say"], FLOORED)
        self.assertTrue(on_disk["approval"]["used"])

    def test_31_a_wrong_id_is_409_and_nothing_launches(self):
        held = self.held()
        r = self.act(held["id"], action="approve", approval_id="ap-nope")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.launched, [])
        self.assertEqual(self.store.load(held["id"])["state"], "paused")

    def test_32_a_second_approve_is_409(self):
        held = self.held()
        self.act(held["id"], action="approve",
                 approval_id=held["approval"]["id"])
        r = self.act(held["id"], action="approve",
                     approval_id=held["approval"]["id"])
        self.assertEqual(r.status_code, 409)

    def test_33_at_capacity_is_409_and_the_yes_is_not_spent_twice(self):
        held = self.held()
        mission_engine.set_max_running(1)
        try:
            other = self.mission()          # one running task fills the cap
            r = self.act(held["id"], action="approve",
                         approval_id=held["approval"]["id"])
        finally:
            mission_engine.set_max_running(mission_engine.MAX_RUNNING)
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.json()["detail"]["at_capacity"])
        self.assertEqual(self.store.load(held["id"])["state"], "paused")
        self.assertEqual(self.launched, [])
        self.assertIsNotNone(other)


if __name__ == "__main__":
    unittest.main(verbosity=2)
