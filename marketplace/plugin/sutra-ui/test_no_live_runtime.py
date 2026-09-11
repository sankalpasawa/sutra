"""A missing runtime is a retryable precondition, not a failed attempt.

FIRST FLIGHT, 2026-09-11, goal g-35fadb0ea2ac ("Goa vs Pondicherry"). The
founder chatted in a real session, opened Shadow, picked that chat, created
the goal and pressed Start. Start admitted the mission, the runner said its
first turn, `_validated_say` found no entry in session_runtime.RUNTIMES for
the target session -- because that registry is populated when a turn
COMPLETES on the socket that is open right now, and the founder had
navigated away from the pane -- and the say raised. Every raise looked the
same to the runner, so the mission went `failed` at turn 0/20 and the goal
went `blocked` with the uninterpretable reason "attempt m-c690ba7ad7fa
failed". Nothing had been sent, nothing had been spent, and the chat was
completely untouched.

These tests pin the honest shape of that path end to end:

  * the precondition is TYPED (session_runtime.NoLiveRuntime), so callers
    can tell "nothing to speak through" from "the say was turned down";
  * the HTTP say arm still answers 404, unchanged;
  * the runner returns the blocker id rather than a bare False;
  * the engine parks a GOAL attempt as `blocked/no_live_runtime` and leaves
    a STANDALONE mission terminal exactly as it always was;
  * the goal survives, keeps its chat, spends nothing, and Resume works.
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import goal_lifecycle
import mission_engine
import providers
import session_runtime
import shadow_ledger
import shadow_runner
from goal_store import GoalStore
from mission_engine import MissionEngine, MissionStore

SID = "8b5963da-ed83-47cf-8cde-ac7016019218"     # the real first-flight chat

#: A loop that SURVIVES its neighbours. Several suites in this repo call
#: asyncio.run(), which closes the loop and leaves none current -- so on 3.9
#: the next asyncio.get_event_loop() raises "There is no current event loop"
#: and whether these tests pass depends on file ORDER rather than on
#: behaviour. Own one loop, keep it current, never hand back a closed one.
_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)




class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self.goals = GoalStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def engine(self, say_returns):
        """An engine whose sayer returns exactly what the test dictates."""
        self.said = []

        async def sayer(m, text):
            self.said.append(text)
            return say_returns

        async def waiter(m):
            return True

        def reader(m):
            return ""

        return MissionEngine(self.store, sayer, waiter, reader)

    def goal_with_attempt(self):
        g = self.goals.create(
            outcome="Chat produces a recommendation between Goa and "
                    "Pondicherry with 3 reasons and a final choice",
            target_session=SID,
            done_when=[{"tier": "contains_artifact", "check": "three reasons"},
                       {"tier": "contains_artifact", "check": "a final choice"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal_lifecycle.on_attempt_start(m)
        self.store.transition(m["id"], "running", "admitted")
        return g["id"], m["id"]


class TestTheSentinel(Base):
    """The type is the contract."""

    def test_01_it_names_a_deterministic_blocker_not_a_message(self):
        exc = session_runtime.NoLiveRuntime(SID)
        self.assertEqual(exc.reason, "no_live_runtime",
                         "a stable id the UI can map, never free text")
        self.assertEqual(exc.session_id, SID)
        self.assertIn(SID, str(exc), "and it still says which chat")

    def test_02_it_is_distinguishable_from_every_other_refusal(self):
        self.assertTrue(issubclass(session_runtime.NoLiveRuntime, Exception))
        self.assertFalse(
            isinstance(ValueError("no live runtime for session x"),
                       session_runtime.NoLiveRuntime),
            "callers must not have to match on message text")

    def test_03_it_lives_beside_the_registry_it_reports_on(self):
        self.assertIsNone(session_runtime.lookup_runtime(SID),
                          "nothing registered in a clean process")
        src = Path(__file__).with_name("session_runtime.py").read_text()
        self.assertLess(src.index("def lookup_runtime"),
                        src.index("class NoLiveRuntime"),
                        "the sentinel sits with RUNTIMES, so neither app nor "
                        "shadow_runner has to import the other")


class TestTheSayer(Base):
    """The runner reports WHICH kind of non-delivery it was."""

    def _sayer(self, raiser):
        def validated_say(sid, mid, text, dedupe_key=None):
            raise raiser
        sayer, _waiter, _reader = shadow_runner.make_bindings(validated_say)
        return sayer

    def test_04_a_missing_runtime_returns_the_blocker_id(self):
        sayer = self._sayer(session_runtime.NoLiveRuntime(SID))
        out = run(
            sayer({"id": "m-1", "target_session": SID, "turns_used": 0}, "hi"))
        self.assertEqual(out, "no_live_runtime")
        self.assertIsNot(out, False, "a str, so the engine can branch on it")

    def test_05_every_other_refusal_is_still_a_plain_false(self):
        sayer = self._sayer(RuntimeError("the say itself was rejected"))
        out = run(
            sayer({"id": "m-1", "target_session": SID, "turns_used": 0}, "hi"))
        self.assertIs(out, False, "unchanged for real refusals")

    def test_06_a_delivered_say_is_still_true(self):
        sayer, _w, _r = shadow_runner.make_bindings(
            lambda sid, mid, text, dedupe_key=None: None)
        out = run(
            sayer({"id": "m-1", "target_session": SID, "turns_used": 0}, "hi"))
        self.assertIs(out, True)

    def test_07_the_ledger_records_it_as_not_delivered(self):
        sayer = self._sayer(session_runtime.NoLiveRuntime(SID))
        run(
            sayer({"id": "m-7", "target_session": SID, "turns_used": 0}, "hi"))
        rows = [json.loads(l) for l in
                open(shadow_ledger._path("actions"), encoding="utf-8")]
        hit = [r for r in rows if r.get("mission_id") == "m-7"]
        self.assertEqual(len(hit), 1)
        self.assertIn("NOT DELIVERED", hit[0]["summary"])
        self.assertIn("no_live_runtime", hit[0]["summary"])
        self.assertNotIn("REFUSED", hit[0]["summary"],
                         "the audit trail must not call this a refusal")


class TestTheEngine(Base):
    """A named precondition parks the attempt; a refusal still kills it."""

    def test_08_a_goal_attempt_blocks_and_keeps_its_chat(self):
        gid, mid = self.goal_with_attempt()
        eng = self.engine(say_returns="no_live_runtime")
        m = run(eng.run_mission(mid))
        self.assertEqual(m["state"], "blocked",
                         "NOT failed -- the attempt is retryable")
        self.assertEqual(m["block_reason"], "no_live_runtime")
        self.assertEqual(m["target_session"], SID, "same chat, never cloned")
        self.assertNotIn(m["state"], mission_engine.TERMINAL)

    def test_09_nothing_was_spent(self):
        _gid, mid = self.goal_with_attempt()
        eng = self.engine(say_returns="no_live_runtime")
        m = run(eng.run_mission(mid))
        self.assertEqual(m["turns_used"], 0,
                         "the say never left, so no turn was consumed")
        self.assertTrue(all(not c.get("met") for c in m["done_when"]))

    def test_10_a_standalone_mission_is_unchanged(self):
        """The historical contract: no goal, no blocking."""
        m = self.store.create(objective="x", template="fix",
                              target_mode="existing", target_session=SID)
        self.store.transition(m["id"], "brief_confirm", "b")
        self.store.transition(m["id"], "running", "admitted")
        eng = self.engine(say_returns="no_live_runtime")
        out = run(
            eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "failed")
        self.assertIn(out["state"], mission_engine.TERMINAL)

    def test_11_a_real_refusal_still_fails(self):
        gid, mid = self.goal_with_attempt()
        eng = self.engine(say_returns=False)
        m = run(eng.run_mission(mid))
        self.assertEqual(m["state"], "failed", "False is unchanged")
        goal_lifecycle.on_attempt_end(m)   # the funnel the runner calls
        self.assertEqual(self.goals.load(gid)["block_reason"],
                         "attempt %s failed" % mid,
                         "and it still reads as the generic failure it is")

    def test_12_an_empty_string_is_not_a_blocker(self):
        """Only a NAMED reason parks the attempt; falsy stays a refusal."""
        _gid, mid = self.goal_with_attempt()
        eng = self.engine(say_returns="")
        m = run(eng.run_mission(mid))
        self.assertEqual(m["state"], "failed")


class TestTheGoal(Base):
    """What the founder is left holding."""

    def _blocked_goal(self):
        gid, mid = self.goal_with_attempt()
        eng = self.engine(say_returns="no_live_runtime")
        m = run(eng.run_mission(mid))
        goal_lifecycle.on_attempt_end(m)
        return gid, mid

    def test_13_the_goal_blocks_with_the_deterministic_reason(self):
        gid, _mid = self._blocked_goal()
        g = self.goals.load(gid)
        self.assertEqual(g["state"], "blocked")
        self.assertEqual(g["block_reason"], "no_live_runtime",
                         'not "attempt m-... failed" -- the panel maps this')
        self.assertEqual(g["target_session"], SID)

    def test_14_the_goal_spent_nothing(self):
        gid, _mid = self._blocked_goal()
        p = self.goals.progress(gid)
        self.assertEqual(p["checks_met"], 0)
        self.assertEqual(p["checks_total"], 2, "the outcome is intact")
        self.assertEqual(p["turns_used"], 0)

    def test_15_resume_is_possible_and_stays_in_the_same_chat(self):
        gid, first = self._blocked_goal()
        m2 = goal_lifecycle.resume_goal(gid)
        self.assertNotEqual(m2["id"], first, "a fresh attempt")
        self.assertEqual(m2["target_session"], SID,
                         "the SAME chat -- no clone, no new chat")
        self.assertEqual(m2["goal_id"], gid)
        self.assertEqual(len(self.goals.load(gid)["attempts"]), 2)

    def test_16_the_attempt_row_records_how_it_ended(self):
        gid, mid = self._blocked_goal()
        row = self.goals.load(gid)["attempts"][-1]
        self.assertEqual(row["mission_id"], mid)
        self.assertEqual(row["ended_state"], "blocked")
        self.assertIsNotNone(row["ended_at"])

    def test_17_the_goal_is_never_abandoned_by_machine_trouble(self):
        gid, _mid = self._blocked_goal()
        self.assertNotIn(self.goals.load(gid)["state"], ("stopped", "done"),
                         "only an explicit founder stop abandons a goal")


class TestTheSayEndpoint(unittest.TestCase):
    """The HTTP arm's answer is unchanged: still a 404."""

    def test_18_the_endpoint_still_translates_to_404(self):
        src = Path(__file__).with_name("app.py").read_text()
        i = src.index("def _validated_say")
        self.assertIn("raise NoLiveRuntime(sid)", src[i:i + 1500],
                      "the one say path raises the typed precondition")
        j = src.index("message and mission_id are required")
        arm = src[j:j + 500]
        self.assertIn("except NoLiveRuntime", arm)
        self.assertIn("404", arm, "the wire contract did not move")


if __name__ == "__main__":
    unittest.main()
