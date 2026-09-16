"""AUTONOMY IS A REAL CONTROL: four levels, persisted, and each one binds.

WHAT WAS WRONG. The Shadow Settings "Autonomy" section drew a four-level
selector (L0 Watch / L1 Suggest / L2 Draft / L3 Act) and an "Ask me before the
very top tier" switch, and neither did anything. The client carried a constant

    const SH_LEVEL_NOW = "L3";

and drew every control `aria-disabled="true"` with `title="Not configurable
yet"`. The word `autonomy` appeared nowhere in any Shadow Python file. A
founder could read the page as a statement of how much rope Shadow had, change
nothing, and be right about the behaviour only by accident.

WHAT BINDS NOW, and this file is the proof for each:

    L0 Watch    run_mission pauses before composing anything. Nothing is said.
    L1 Suggest  every say is held for a founder yes.
    L2 Draft    the say goes, the WORKER is capped at `plan`.
    L3 Act      the say goes at the founder's own permission mode, after one
                confirmation per task when the top-tier switch is on.

THE TWO PROPERTIES THAT MATTER MORE THAN THE FEATURE:

  1 FLOORS ARE NOT NEGOTIABLE BY LEVEL. The autonomy gate is placed AFTER
    shadow_egress.floor_check in run_mission, deliberately, because SHADOW.md
    section 3 ranks floors above everything. A say that trips a floor pauses
    as `floor_confirm` at EVERY level including L3, and never leaves the
    engine. TestFloorsOutrankEveryLevel sweeps all four rather than trusting
    the placement to stay put.

  2 THE CEILING ONLY EVER NARROWS. L2 capping a worker at `plan` must never
    be able to hand one a mode WIDER than the founder's own setting resolved
    to. That cross-product lives in test_shadow_worker_permissions
    (test_17e); this file pins the store and the loop.

Run: ./run-tests.sh test_shadow_autonomy.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-autonomy-test-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_egress                           # noqa: E402
from mission_engine import MissionEngine, MissionStore   # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
SETTINGS = "/api/shadow/settings"
AUTONOMY = "/api/shadow/settings/autonomy"

#: A say that trips d52_destructive_git. Used to prove the floor still wins.
FLOORED = "clean the branch with git reset --hard"
#: ...and one that trips nothing, so the level is the only thing in play.
CLEAN = "read the config and report what it says"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    def running(self, objective=CLEAN, kind="fix"):
        """A mission sitting in `running`, ready for the loop."""
        m = self.store.create(objective, kind)
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        return m

    def drive(self, mid):
        """Run the real loop with a recording sayer. Returns (mission, said).

        The sayer and waiter are the same stubs test_mission_scheduler uses,
        so what is exercised here is mission_engine's own branch order, not a
        re-implementation of it.
        """
        said = []

        async def sayer(mission, text):
            said.append(text)
            return True

        async def waiter(mission):
            return True

        eng = MissionEngine(self.store, sayer, waiter, lambda m: "")
        out = asyncio.run(eng.run_mission(mid))
        return out, said


class TestTheStore(Base):

    def test_01_an_unconfigured_install_behaves_EXACTLY_as_before(self):
        """THE DEFAULT IS THE SHIPPED BEHAVIOUR, and both halves matter.

        L3 because defaulting to L0 would silently stop every existing
        founder's Shadow on update. The switch OFF for the same reason, and
        that half was got wrong first: shipping it on turned eleven green
        lanes red because missions that used to speak stopped to ask a
        question that had not existed before. A guard the founder can enable
        in one click beats a default that breaks their automation.
        """
        self.assertEqual(mission_engine.autonomy(), "L3")
        self.assertFalse(mission_engine.confirm_top_tier())
        self.assertTrue(mission_engine.worker_may_write())

    def test_01b_the_default_install_ACTS_without_being_asked(self):
        """The above, asserted as behaviour rather than as two constants --
        this is the test that would have caught the wrong default."""
        m = self.running()
        _out, said = self.drive(m["id"])
        self.assertTrue(said,
                        "a default install stopped to ask before acting")

    def test_02_every_level_round_trips(self):
        for lv in mission_engine.AUTONOMY_LEVELS:
            with self.subTest(level=lv):
                self.assertEqual(mission_engine.set_autonomy(lv), lv)
                self.assertEqual(mission_engine.autonomy(), lv)

    def test_03_an_unknown_level_is_REFUSED_not_clamped(self):
        """A level is an enum, not a point on a number line: there is no
        nearest legal answer to "L7", and inventing one would grant a
        permission the founder never chose."""
        for junk in ("L7", "act", "", None, 3, "l3"):
            with self.subTest(junk=junk):
                with self.assertRaises(ValueError):
                    mission_engine.set_autonomy(junk)

    def test_04_a_hand_edited_junk_file_degrades_to_the_default(self):
        """Never raises: this is read on the say path and on every spawn."""
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"autonomy": "L9"}))
        self.assertEqual(mission_engine.autonomy(), "L3")
        Path(mission_engine.limits_path()).write_text("{ not json")
        self.assertEqual(mission_engine.autonomy(), "L3")
        self.assertFalse(mission_engine.confirm_top_tier())

    def test_05_the_level_SURVIVES_a_fresh_read(self):
        """The restart proxy. The value is on disk under the shadow home, so
        a brand-new process reading the same home sees it -- which is what
        makes the selection survive an app restart rather than a reload."""
        mission_engine.set_autonomy("L1")
        mission_engine.set_confirm_top_tier(False)
        raw = json.loads(Path(mission_engine.limits_path()).read_text())
        self.assertEqual(raw["autonomy"], "L1")
        self.assertIs(raw["confirm_top_tier"], False)
        # re-read through the accessors, as a new process would
        self.assertEqual(mission_engine.autonomy(), "L1")
        self.assertFalse(mission_engine.confirm_top_tier())

    def test_06_autonomy_shares_the_limits_file_without_clobbering_it(self):
        """Three settings live in task-limits.json. A read-modify-write that
        dropped a sibling would be a data-loss bug, not a styling one."""
        mission_engine.set_max_running(7)
        mission_engine.set_turn_budget("fix", 11)
        mission_engine.set_autonomy("L2")
        mission_engine.set_confirm_top_tier(False)
        self.assertEqual(mission_engine.max_running(), 7)
        self.assertEqual(mission_engine.turn_budget("fix"), 11)
        self.assertEqual(mission_engine.autonomy(), "L2")

    def test_07_worker_may_write_is_the_L2_L3_line(self):
        for lv in ("L0", "L1", "L2"):
            mission_engine.set_autonomy(lv)
            self.assertFalse(mission_engine.worker_may_write(), lv)
        mission_engine.set_autonomy("L3")
        self.assertTrue(mission_engine.worker_may_write())


class TestTheLevelsBind(Base):

    def test_10_L0_never_says_and_pauses(self):
        """L0 WATCH. The `watch` template's never_say invariant, applied to
        every mission instead of one."""
        mission_engine.set_autonomy("L0")
        m = self.running()
        out, said = self.drive(m["id"])
        self.assertEqual(said, [], "L0 said something")
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "autonomy_hold")

    def test_11_L1_holds_every_say_for_a_yes(self):
        mission_engine.set_autonomy("L1")
        m = self.running()
        out, said = self.drive(m["id"])
        self.assertEqual(said, [], "an L1 suggestion must not be sent")
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "autonomy_suggest")
        self.assertTrue(out.get("pending_autonomy_say"),
                        "the founder must be shown what is proposed")

    def test_12_L2_speaks(self):
        """L2's restraint is the worker's `plan` ceiling, not silence: the
        instruction itself is safe to send."""
        mission_engine.set_autonomy("L2")
        m = self.running()
        _out, said = self.drive(m["id"])
        self.assertTrue(said, "L2 Draft must still drive the worker")

    def test_13_L3_with_the_switch_ON_asks_once(self):
        mission_engine.set_autonomy("L3")
        mission_engine.set_confirm_top_tier(True)
        m = self.running()
        out, said = self.drive(m["id"])
        self.assertEqual(said, [], "L3 must ask before its first act")
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "autonomy_top_tier")

    def test_14_the_top_tier_yes_is_remembered_for_the_rest_of_the_task(self):
        """ONCE PER MISSION, not per turn -- asking every turn would make L3
        indistinguishable from L1, which would make the four levels three."""
        mission_engine.set_autonomy("L3")
        mission_engine.set_confirm_top_tier(True)
        m = self.running()
        out, _ = self.drive(m["id"])
        self.assertEqual(out["pause_reason"], "autonomy_top_tier")
        # what the Resume route does when it spends the yes
        held = self.store.load(m["id"])
        held["top_tier_confirmed"] = True
        self.store.save(held)
        self.store.transition(m["id"], "running")
        out2, said2 = self.drive(m["id"])
        self.assertTrue(said2, "the confirmed task never got to act")
        self.assertNotEqual(out2.get("pause_reason"), "autonomy_top_tier",
                            "L3 asked twice for the same task")

    def test_15_L3_with_the_switch_OFF_acts_immediately(self):
        mission_engine.set_autonomy("L3")
        mission_engine.set_confirm_top_tier(False)
        m = self.running()
        _out, said = self.drive(m["id"])
        self.assertTrue(said, "with the switch off nothing should be asked")

    def test_16_the_level_is_read_LIVE_not_stamped_at_create(self):
        """A founder dropping to L0 is saying STOP. A stop that waited for
        the next task would be the setting failing in the only direction that
        matters. (Contrast max_turns, which IS stamped at create.)"""
        mission_engine.set_autonomy("L3")
        mission_engine.set_confirm_top_tier(False)
        m = self.running()                    # created while L3
        mission_engine.set_autonomy("L0")     # ...founder changes their mind
        out, said = self.drive(m["id"])
        self.assertEqual(said, [], "a task created at L3 spoke after L0")
        self.assertEqual(out["pause_reason"], "autonomy_hold")


class TestFloorsOutrankEveryLevel(Base):
    """SHADOW.md section 3: floors are precedence rank 1. No level may lower
    them, and the gate order in run_mission is what makes that true -- the
    floor check returns before the autonomy gate is ever reached."""

    def test_20_a_floored_say_is_held_at_EVERY_level(self):
        for lv in mission_engine.AUTONOMY_LEVELS:
            with self.subTest(level=lv):
                mission_engine.set_autonomy(lv)
                mission_engine.set_confirm_top_tier(False)
                m = self.running(objective=FLOORED)
                out, said = self.drive(m["id"])
                self.assertEqual(said, [],
                                 "a floored say left the engine at " + lv)
                self.assertEqual(out["state"], "paused")
                if lv == "L0":
                    # L0 never composes a say at all, so there is nothing to
                    # floor -- it is stopped EARLIER, which is stricter
                    self.assertEqual(out["pause_reason"], "autonomy_hold")
                else:
                    self.assertEqual(
                        out["pause_reason"], "floor_confirm",
                        "the floor must be the reported reason at " + lv)

    def test_21_the_floor_BEATS_autonomy_when_a_say_trips_both(self):
        """At L1 a floored say is both "held for a yes" and "floored". The
        founder must be told the FLOOR, because that is the fact that does
        not change whatever they pick in Settings -- reporting the softer
        reason would teach them that raising the level would clear it."""
        mission_engine.set_autonomy("L1")
        m = self.running(objective=FLOORED)
        out, _ = self.drive(m["id"])
        self.assertEqual(out["pause_reason"], "floor_confirm")
        self.assertNotEqual(out["pause_reason"], "autonomy_suggest")
        self.assertIn("reset --hard", out["pending_floor_say"])

    def test_22_L3_ACT_has_no_bypass(self):
        """The top level is the one a founder would expect to be able to
        override a floor. It cannot, and this asserts it from the outside
        rather than by reading the gate order."""
        mission_engine.set_autonomy("L3")
        mission_engine.set_confirm_top_tier(False)   # nothing else in the way
        for text in ("push it with git push --force",
                     "edit ~/Claude/Paisa/app.py",
                     "send the email to the client"):
            with self.subTest(say=text):
                self.assertTrue(shadow_egress.floor_check(text),
                                "fixture does not actually trip a floor")
                m = self.running(objective=text)
                out, said = self.drive(m["id"])
                self.assertEqual(said, [], "L3 pushed a floored say through")
                self.assertEqual(out["pause_reason"], "floor_confirm")

    def test_23_no_level_can_be_stored_that_disables_the_floor_check(self):
        """There is no "off" and no fifth level: the enum is the whole
        surface, so there is nothing to set that would skip the check."""
        self.assertEqual(mission_engine.AUTONOMY_LEVELS,
                         ("L0", "L1", "L2", "L3"))
        for junk in ("L4", "off", "none", "bypass"):
            with self.assertRaises(ValueError):
                mission_engine.set_autonomy(junk)


class TestTheRoute(Base):

    def test_30_the_settings_read_states_the_level_and_its_consequence(self):
        r = self.client.get(SETTINGS, headers=HDR)
        self.assertEqual(r.status_code, 200)
        a = r.json()["autonomy"]
        self.assertEqual(a["level"], "L3")
        self.assertEqual(a["levels"], ["L0", "L1", "L2", "L3"])
        self.assertFalse(a["confirm_top_tier"], "the switch defaults off")
        # the CONSEQUENCE, so the page states it rather than inferring it
        self.assertIn("worker_mode", a)
        self.assertIn("worker_may_write", a)

    def test_31_a_write_persists_and_the_next_read_agrees(self):
        r = self.client.post(AUTONOMY, json={"level": "L2"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["level"], "L2")
        self.assertFalse(r.json()["worker_may_write"])
        self.assertEqual(self.client.get(SETTINGS, headers=HDR)
                         .json()["autonomy"]["level"], "L2")
        self.assertEqual(mission_engine.autonomy(), "L2")

    def test_32_the_switch_writes_on_its_own(self):
        """Either key may be absent, so a toggle click never has to restate
        the level and risk stamping a stale one over another tab's change."""
        r = self.client.post(AUTONOMY, json={"confirm_top_tier": False},
                             headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["confirm_top_tier"])
        self.assertEqual(r.json()["level"], "L3", "the level moved on its own")

    def test_33_a_junk_level_is_a_400_not_a_silent_default(self):
        r = self.client.post(AUTONOMY, json={"level": "L9"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(mission_engine.autonomy(), "L3", "junk was stored")

    def test_34_an_empty_write_is_refused(self):
        self.assertEqual(
            self.client.post(AUTONOMY, json={}, headers=HDR).status_code, 400)

    def test_35_the_route_reports_what_it_is_HOLDING(self):
        """Lowering autonomy parks running tasks and does NOT un-park them on
        the way back up -- the founder resumes by hand. The count is the
        honest counterpart to that."""
        mission_engine.set_autonomy("L0")
        m = self.running()
        self.drive(m["id"])                   # -> paused autonomy_hold
        r = self.client.post(AUTONOMY, json={"level": "L3"}, headers=HDR)
        self.assertEqual(r.json()["held"], 1)
        self.assertEqual(self.store.load(m["id"])["state"], "paused",
                         "raising the level must not silently resume work")

    def test_36_the_flag_gates_both_verbs(self):
        providers.SETTINGS_PATH.write_text(json.dumps({"shadow.enabled": False}))
        self.assertEqual(self.client.get(SETTINGS, headers=HDR).status_code, 403)
        self.assertEqual(
            self.client.post(AUTONOMY, json={"level": "L1"},
                             headers=HDR).status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
