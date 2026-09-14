"""PLAN-100 S43-S50 (+S54): the mission engine against a mock session."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import providers
import mission_engine
from mission_engine import MissionStore, MissionEngine, evaluate_done_when


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def engine(self, transcripts=None, say_ok=True, waiter_result=True):
        self.says = []

        async def sayer(m, text):
            self.says.append(text)
            return say_ok

        async def waiter(m):
            return waiter_result

        def reader(m):
            if transcripts is None:
                return " ".join(self.says)
            i = min(len(self.says) - 1, len(transcripts) - 1)
            return transcripts[i] if transcripts else ""

        return MissionEngine(self.store, sayer, waiter, reader)


class TestStore(Base):
    def test_01_create_and_legal_transitions(self):
        m = self.store.create("fix the nav test", "fix")
        self.assertEqual(m["state"], "draft")
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        with self.assertRaises(ValueError):
            self.store.transition(m["id"], "queued")  # running -> queued illegal

    def test_02_seq_ties_store_to_ledger(self):
        import shadow_ledger
        m = self.store.create("x" * 10, "fix")
        self.store.transition(m["id"], "brief_confirm")
        rows = [r for r in shadow_ledger.read("missions", 50)
                if r.get("mission_id") == m["id"] and r.get("seq")]
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["seq"], self.store.load(m["id"])["seq"])

    def test_03_amend_bumps_version_keeps_budget(self):
        m = self.store.create("objective one", "feature")
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        mm = self.store.load(m["id"])
        mm["turns_used"] = 7
        self.store.save(mm)
        # running missions stay running on amend detour; queued go back
        m2 = self.store.create("objective two", "feature")
        self.store.transition(m2["id"], "brief_confirm")
        self.store.transition(m2["id"], "queued")
        amended = self.store.amend(m2["id"], objective="tighter objective")
        self.assertEqual(amended["version"], 2)
        self.assertEqual(amended["state"], "brief_confirm")
        kept = self.store.amend(m["id"], objective="still mission one")
        self.assertEqual(kept["turns_used"], 7,
                         "amend never resets the budget")

    def test_04_confirm_check_is_the_only_founder_confirm_writer(self):
        m = self.store.create("ship it", "feature",
                              done_when=[{"tier": "founder_confirm",
                                          "check": "founder says yes"}])
        ok, results = evaluate_done_when(m, "founder says yes in transcript")
        self.assertFalse(ok, "transcript text must never satisfy the tier")
        self.store.confirm_check(m["id"], 0)
        m = self.store.load(m["id"])
        ok, _ = evaluate_done_when(m, "")
        self.assertTrue(ok)
        with self.assertRaises(ValueError):
            self.store.confirm_check(m["id"], 5)

    def test_05_updated_at_is_on_every_listed_mission_and_advances(self):
        """The freshness stamp the task card reads.

        The card's "last updated" row is this field and nothing else, so two
        things have to hold: every mission the list endpoint hands the UI
        carries it in a shape Date.parse understands, and a write MOVES it.
        A stamp that never moved would make a wedged task read as fresh --
        the exact lie the row exists to prevent.
        """
        m = self.store.create("stamp the record", "fix")
        self.assertIn("updated_at", m, "a new mission is born stamped")

        for row in self.store.list():
            self.assertRegex(
                row["updated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
                "the UI parses this stamp as a UTC instant")

        first = self.store.load(m["id"])["updated_at"]
        # _now() is second-granularity, so hold the clock still and assert the
        # WRITE is what re-stamps -- not the passage of wall-clock time.
        orig_now = mission_engine._now
        try:
            mission_engine._now = lambda: "2026-09-15T12:00:00Z"
            self.store.transition(m["id"], "brief_confirm")
        finally:
            mission_engine._now = orig_now
        after = self.store.load(m["id"])["updated_at"]
        self.assertEqual(after, "2026-09-15T12:00:00Z",
                         "save() must re-stamp updated_at on every write")
        self.assertNotEqual(after, first, "the stamp moved with the record")


class TestLoop(Base):
    def _running(self, template="fix", done_when=None, objective="do the thing"):
        m = self.store.create(objective, template, done_when=done_when)
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        return m

    def test_05_loop_reaches_done_via_contains(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "ALL GREEN"}])
        eng = self.engine(transcripts=["working on it", "tests ALL GREEN"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "done")
        self.assertEqual(self.store.load(m["id"])["turns_used"], 2)

    def test_06_max_turns_fails_deterministically(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER-THERE"}])
        mm = self.store.load(m["id"])
        mm["max_turns"] = 3
        self.store.save(mm)
        # vary the say each turn so ping-pong does not fire first
        eng = self.engine(transcripts=["a", "b", "c", "d"])
        n = {"i": 0}
        orig = eng._next_say
        def varied(mission):
            n["i"] += 1
            return "%s #%d" % (orig(mission), n["i"])
        eng._next_say = varied
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "failed")
        self.assertIn("max turns", self._last_note(m["id"]))

    def test_07_ping_pong_stops(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER"}])
        eng = self.engine(transcripts=["same", "same", "same"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "stopped")
        self.assertIn("ping-pong", self._last_note(m["id"]))

    def test_08_founder_stop_honored_mid_loop(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER"}])
        eng = self.engine()
        async def stopping_waiter(mission):
            eng2 = MissionEngine(self.store, None, None, None)
            eng2.founder_stop(mission["id"])
            return True
        eng.waiter = stopping_waiter
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "stopped")

    def test_09_intervention_pauses_and_resume_continues(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "FINISHED"}])
        eng = self.engine(transcripts=["nothing yet", "FINISHED"])
        calls = {"n": 0}
        async def intervening_waiter(mission):
            calls["n"] += 1
            if calls["n"] == 1:
                MissionEngine(self.store, None, None, None)\
                    .founder_intervened(mission["id"])
            return True
        eng.waiter = intervening_waiter
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_intervened")
        MissionEngine(self.store, None, None, None).resume(m["id"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "done")

    def test_10_founder_confirm_pending_pauses_not_completes(self):
        m = self._running(done_when=[
            {"tier": "contains_artifact", "check": "SHIPPED"},
            {"tier": "founder_confirm", "check": "founder approves"}])
        eng = self.engine(transcripts=["SHIPPED"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_confirm")

    def test_11_watch_template_never_says(self):
        m = self.store.create("watch session s-1", "watch")
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        eng = self.engine()
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "running")
        self.assertEqual(self.says, [], "watch missions must not speak")

    def test_12_waiter_timeout_fails_not_hangs(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER"}])
        eng = self.engine(waiter_result=False)
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "failed")
        self.assertIn("timed out", self._last_note(m["id"]))

    def test_13_flag_dark_stops_the_loop(self):
        m = self._running()
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": False}))
        eng = self.engine()
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "stopped")

    def _last_note(self, mid):
        import shadow_ledger
        rows = [r for r in shadow_ledger.read("missions", 100)
                if r.get("mission_id") == mid]
        return rows[-1].get("note", "")


class TestBlockedState(Base):
    """V5 slice 1: blocked exists, is non-terminal, and carries its reason.

    Nothing in the loop routes into blocked yet -- these pin the state
    machine and the reason field only.
    """

    def _running(self, goal_id=None, objective="ship the retry fix"):
        m = self.store.create(objective, "fix", goal_id=goal_id)
        self.store.transition(m["id"], "brief_confirm")
        return self.store.transition(m["id"], "running")

    def test_14_blocked_is_declared_and_not_terminal(self):
        self.assertIn("blocked", mission_engine.STATES)
        self.assertNotIn("blocked", mission_engine.TERMINAL,
                         "blocked must never mean the chat is dead")

    def test_15_blocked_exits_are_resume_and_abandon_only(self):
        self.assertEqual(mission_engine.TRANSITIONS["blocked"],
                         ("running", "stopped"))
        self.assertIn("blocked", mission_engine.TRANSITIONS["running"])
        # the existing terminals keep their dead ends -- that is G1, and
        # this slice does not open them
        for dead in ("done", "failed", "stopped"):
            self.assertEqual(mission_engine.TRANSITIONS[dead], (),
                             "%s must stay exit-less" % dead)

    def test_16_block_persists_its_reason_and_ledgers_it(self):
        m = self._running()
        out = self.store.block(m["id"], "budget exhausted",
                               "20 turns used, check 3 unmet")
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out["block_reason"], "budget exhausted")
        reloaded = self.store.load(m["id"])
        self.assertEqual(reloaded["state"], "blocked")
        self.assertEqual(reloaded["block_reason"], "budget exhausted",
                         "the reason must survive a reload")
        self.assertIn("check 3 unmet", self._last_note(m["id"]))
        with self.assertRaises(ValueError):
            self.store.block(m["id"], "")      # a blocker needs a reason

    def test_17_resuming_clears_the_reason(self):
        m = self._running()
        self.store.block(m["id"], "ping-pong")
        resumed = self.store.transition(m["id"], "running", "founder answered")
        self.assertEqual(resumed["state"], "running")
        self.assertNotIn("block_reason", resumed,
                         "a running mission must not carry a stale blocker")
        self.assertNotIn("block_reason", self.store.load(m["id"]))

    def test_18_blocked_can_be_abandoned_but_not_failed(self):
        m = self._running()
        self.store.block(m["id"], "chat error")
        with self.assertRaises(ValueError):
            self.store.transition(m["id"], "failed")
        self.assertEqual(
            self.store.transition(m["id"], "stopped", "founder abandoned"
                                  )["state"], "stopped")

    def test_20_a_goal_attempt_blocks_where_a_solo_mission_fails(self):
        """The slice-3 boundary, at the engine level: `goal_id` is the only
        switch between the new blocked path and the historical terminal one.
        """
        for goal_id, expected in ((None, "failed"), ("g-abc123", "blocked")):
            m = self.store.create("do the thing", "fix", goal_id=goal_id,
                                  done_when=[{"tier": "contains_artifact",
                                              "check": "NOPE"}])
            self.store.transition(m["id"], "brief_confirm")
            self.store.transition(m["id"], "running")
            mm = self.store.load(m["id"])
            mm["max_turns"] = 2
            self.store.save(mm)
            out = asyncio.run(self.engine(
                transcripts=["a", "b"]).run_mission(m["id"]))
            self.assertEqual(out["state"], expected,
                             "goal_id=%r" % (goal_id,))
            self.assertIn("max turns", self._last_note(m["id"]),
                          "the ledger note is identical either way")
        self.assertEqual(out["block_reason"], "budget_exhausted")

    def test_21_ping_pong_blocks_a_goal_attempt_and_stops_a_solo_one(self):
        for goal_id, expected in ((None, "stopped"), ("g-abc123", "blocked")):
            m = self.store.create("do the thing", "fix", goal_id=goal_id)
            self.store.transition(m["id"], "brief_confirm")
            self.store.transition(m["id"], "running")
            out = asyncio.run(self.engine().run_mission(m["id"]))
            self.assertEqual(out["state"], expected,
                             "goal_id=%r" % (goal_id,))
            self.assertIn("ping-pong", self._last_note(m["id"]))
        self.assertEqual(out["block_reason"], "ping_pong")

    def test_22_an_external_block_stops_the_loop_mid_flight(self):
        """A mission blocked from outside must stop driving the chat rather
        than keep saying into it."""
        m = self._running("g-abc123")
        store = self.store

        async def sayer(mission, text):
            return True

        async def waiter(mission):
            store.block(mission["id"], "stalled", "blocked mid-turn")
            return True

        eng = mission_engine.MissionEngine(store, sayer, waiter,
                                           lambda mm: "")
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out["block_reason"], "stalled")

    def test_19_launching_the_loop_on_a_blocked_mission_refuses(self):
        # the runner must never drive a blocked mission; the loop's state
        # guard is what enforces it
        m = self._running()
        self.store.block(m["id"], "budget exhausted")
        eng = self.engine()
        with self.assertRaises(ValueError):
            asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(self.store.load(m["id"])["state"], "blocked",
                         "a refused launch must not change the state")

    def _last_note(self, mid):
        import shadow_ledger
        rows = [r for r in shadow_ledger.read("missions", 100)
                if r.get("mission_id") == mid]
        return rows[-1].get("note", "")


class TestBriefIsNeverDeliveredTwice(Base):
    """The duplicate-manifest fix (founder, 2026-09-13).

    spawn_delegate_session sends the manifest and waits out the whole first
    agentic turn before it hands back a session id. Turn 0 here then sent the
    SAME manifest into the SAME session -- 30s of duplicate model work per
    delegated task, measured on mission m-e14f6acc41aa (2026-09-12).

    `manifest_delivered` is the switch, and it is stamped by provision_target
    and nowhere else, so these tests pin BOTH sides: a spawned delegate is
    never re-briefed, and an existing-target mission is untouched.
    """

    MANIFEST = "You are a delegate session. Objective: pin this path."

    def _engine(self, transcript):
        """Explicit about all three injectables -- what was said, whether a
        boundary was waited on, and what the target 'replied'."""
        self.says = []
        self.waits = []

        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            self.waits.append(m["turns_used"])
            return True

        def reader(m):
            return transcript

        return MissionEngine(self.store, sayer, waiter, reader)

    def _mission(self, briefed, done_when=None):
        m = self.store.create("ship the thing", "fix", target_mode="new",
                              target_session="sess-1",
                              done_when=done_when, manifest=self.MANIFEST)
        if briefed:
            mm = self.store.load(m["id"])
            mm["manifest_delivered"] = True
            self.store.save(mm)
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        return m

    def test_20_a_spawned_delegate_is_never_re_briefed(self):
        m = self._mission(True, [{"tier": "contains_artifact",
                                  "check": "ALL GREEN"}])
        eng = self._engine("the spawn turn already said ALL GREEN")
        out = asyncio.run(eng.run_mission(m["id"]))
        # THE WHOLE POINT: nothing was sent at all
        self.assertEqual(self.says, [],
                         "the brief was already delivered at spawn")
        self.assertNotIn(self.MANIFEST, self.says)
        # ...and nothing was waited on: that boundary already happened
        self.assertEqual(self.waits, [])
        # the spawn turn still COUNTS, and is still evaluated
        self.assertEqual(out["state"], "done")
        self.assertEqual(self.store.load(m["id"])["turns_used"], 1)

    def test_21_an_existing_target_mission_is_unchanged(self):
        """The control: no flag -> turn 0 is the manifest, as before."""
        m = self._mission(False, [{"tier": "contains_artifact",
                                   "check": "ALL GREEN"}])
        eng = self._engine("ALL GREEN")
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(self.says, [self.MANIFEST],
                         "an unbriefed target must still get the brief")
        self.assertEqual(self.waits, [0],
                         "and its boundary is still waited on")
        self.assertEqual(out["state"], "done")
        self.assertEqual(self.store.load(m["id"])["turns_used"], 1)

    def test_22_turn_one_still_drives_and_is_not_the_manifest(self):
        """Skipping turn 0's say must not skip the mission: when the spawn
        turn did NOT finish the job, turn 1 is composed and sent normally."""
        m = self._mission(True, [{"tier": "contains_artifact",
                                  "check": "NEVER-THERE"}])
        mm = self.store.load(m["id"])
        mm["max_turns"] = 2
        self.store.save(mm)
        eng = self._engine("still working")
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(len(self.says), 1,
                         "exactly one real say: turn 1, not turn 0")
        self.assertNotIn(self.MANIFEST, self.says,
                         "and it is NEVER the manifest again")
        self.assertIn("Continue toward", self.says[0])
        self.assertEqual(self.waits, [1], "turn 1 waits on its own boundary")
        self.assertEqual(out["state"], "failed")   # budget, as before

    def test_23_provision_target_is_what_stamps_it(self):
        m = self.store.create("ship the thing", "fix", target_mode="new",
                              manifest=self.MANIFEST)
        self.assertFalse(self.store.load(m["id"]).get("manifest_delivered"),
                         "nothing is briefed until a spawner briefs it")

        async def spawner(mission):
            return "sess-spawned"

        eng = MissionEngine(self.store, None, None, None)
        sid = asyncio.run(eng.provision_target(m["id"], spawner))
        self.assertEqual(sid, "sess-spawned")
        out = self.store.load(m["id"])
        self.assertEqual(out["target_session"], "sess-spawned")
        self.assertTrue(out["manifest_delivered"],
                        "the spawner's contract is send-manifest-and-wait")

    def test_24_a_retry_clone_is_briefed_again(self):
        """A clone is a NEW session that has heard nothing, so the flag must
        not ride along with the brief it copies."""
        m = self._mission(True)
        self.store.transition(m["id"], "failed", "for the test")
        clone = mission_engine.clone_for_retry(self.store, m["id"])
        self.assertEqual(clone["manifest"], self.MANIFEST,
                         "the brief itself IS copied")
        self.assertFalse(clone.get("manifest_delivered"),
                         "but a fresh delegate has not been told it")
        self.assertIsNone(clone["target_session"])


if __name__ == "__main__":
    unittest.main()
