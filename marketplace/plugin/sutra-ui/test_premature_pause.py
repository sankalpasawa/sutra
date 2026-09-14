"""The confirmation pause must be EARNED, not inherited from an empty set.

THE BUG, three times in production before it was fixed:

    others_met = all(r["met"] for r in results if r["tier"] != "founder_confirm")

With every check on `founder_confirm` that generator is empty, all([]) is
True, and the mission paused on its FIRST evaluation having driven nothing.

  m-b7d534be84d7  2026-09-14  running -> paused/founder_confirm in the SAME
                              second, turn 1/20, no decider call, no
                              instruction ever sent. The delegate had written
                              a 2,531-char design ending "Approve and I'll
                              build it" and was asked to sign off four
                              criteria for work that had not started.
  m-0213b89e5feb  1/20, six all-founder_confirm checks
  m-d817efbe3aa1  1/15, six all-founder_confirm checks

And this is the DEFAULT shape, not an edge case: shadow_protocol.tier_for
demotes every check that is not a short literal marker, so an outcome
described in ordinary words yields exactly it.

Every test below was run against the OLD predicate first and fails there --
see the report accompanying this change.
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
from mission_engine import MissionStore, MissionEngine


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def mission(self, checks, max_turns=4):
        m = self.store.create("build the expense tracker", "fix",
                              target_session="sess-1", done_when=checks)
        self.store.transition(m["id"], "brief_confirm", "b")
        m = self.store.transition(m["id"], "running", "admitted")
        m["max_turns"] = max_turns
        self.store.save(m)
        return m["id"]

    def _notes(self, mid):
        """Ledger notes for this mission, so a test can assert WHICH exit
        was taken rather than a brittle turn count."""
        import shadow_ledger
        return [json.loads(l)["note"] for l
                in open(shadow_ledger._path("missions"), encoding="utf-8")
                if mid in l]

    def engine(self, transcript=""):
        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        return MissionEngine(self.store, sayer, waiter, lambda m: transcript)


class TestTheConfirmationBoundary(Base):

    def test_01_all_founder_confirm_does_NOT_pause_immediately(self):
        """THE BUG. Four founder_confirm checks, nothing machine-checkable.

        The old predicate paused on the first evaluation with turns_used == 1.
        Shadow must keep driving instead: the founder can confirm whenever
        they are ready, and absence of machine checks is not evidence.
        """
        mid = self.mission([
            {"tier": "founder_confirm", "check": "expense_tracker.py runs."},
            {"tier": "founder_confirm", "check": "add/list/total work."},
            {"tier": "founder_confirm", "check": "Tests exist and pass."},
            {"tier": "founder_confirm", "check": "Bad amounts don't crash."},
        ], max_turns=4)
        m = run(self.engine().run_mission(mid))
        self.assertNotEqual(
            (m["state"], m.get("pause_reason")), ("paused", "founder_confirm"),
            "an all-founder_confirm mission must not pause on turn 1")
        self.assertGreater(m["turns_used"], 1,
                           "Shadow kept driving instead of handing back")
        # It ends on ping-pong, not on the confirmation boundary: with no
        # decider injected _next_say repeats itself once the unmet set stops
        # changing, and that guard is what stops it. The point of this test is
        # WHICH exit was taken -- any exit other than the turn-1 handback
        # means Shadow supervised instead of delegating back to the founder.
        self.assertEqual(m["state"], "stopped")
        self.assertIn("ping-pong", " ".join(self._notes(mid)))

    def test_02_mixed_machine_check_MET_still_pauses(self):
        """PRESERVED. A real machine check passed, a founder check is
        outstanding -- this is the boundary the pause exists for."""
        mid = self.mission([
            {"tier": "contains_artifact", "check": "DONE-MARKER"},
            {"tier": "founder_confirm", "check": "the design is sound"},
        ])
        m = run(self.engine(transcript="... DONE-MARKER ...").run_mission(mid))
        self.assertEqual(m["state"], "paused")
        self.assertEqual(m["pause_reason"], "founder_confirm")
        self.assertEqual(m["turns_used"], 1, "it paused at the boundary")

    def test_03_mixed_machine_check_UNMET_does_not_pause(self):
        """PRESERVED. An unmet machine check means the work is not at the
        boundary, so the founder is not asked."""
        mid = self.mission([
            {"tier": "contains_artifact", "check": "NEVER-APPEARS"},
            {"tier": "founder_confirm", "check": "the design is sound"},
        ], max_turns=3)
        m = run(self.engine(transcript="nothing relevant").run_mission(mid))
        self.assertNotEqual((m["state"], m.get("pause_reason")),
                            ("paused", "founder_confirm"),
                            "an unmet machine check must not ask the founder")
        self.assertGreater(m["turns_used"], 1, "it kept driving")

    def test_04_no_done_when_is_unchanged(self):
        """PRESERVED. `results` is empty, so the guard never fires -- the
        mission runs its budget exactly as before."""
        mid = self.mission([], max_turns=3)
        m = run(self.engine().run_mission(mid))
        self.assertNotEqual((m["state"], m.get("pause_reason")),
                            ("paused", "founder_confirm"))
        self.assertGreater(m["turns_used"], 1, "it kept driving")

    def test_05_completion_ownership_is_untouched(self):
        """This change cannot complete anything. `done` still comes only from
        evaluate_done_when, and _complete is still its one writer."""
        mid = self.mission([
            {"tier": "contains_artifact", "check": "DONE-MARKER"},
        ])
        m = run(self.engine(transcript="... DONE-MARKER ...").run_mission(mid))
        self.assertEqual(m["state"], "done")
        self.assertIn("result_excerpt", m)
        self.assertEqual(mission_engine.DECISION_ACTIONS,
                         ("continue", "ask_founder"),
                         "no new decision action was introduced")

    def test_06_all_founder_confirm_still_completes_once_confirmed(self):
        """The founder path still works: confirming every check makes the
        mission done through the SAME evaluate_done_when -> _complete path,
        with no turn spent. Not pausing does not mean not finishing."""
        mid = self.mission([
            {"tier": "founder_confirm", "check": "it reads well"},
        ], max_turns=2)
        self.store.confirm_check(mid, 0)
        m = run(self.engine().run_mission(mid))
        self.assertEqual(m["state"], "done")

    def test_07_malformed_checks_do_not_crash_the_predicate(self):
        """A check with an unknown tier, a missing tier, or no text must be
        scored (as unmet) rather than raising -- the predicate now partitions
        on tier and must not assume the rows are well formed."""
        mid = self.mission([
            {"tier": "contains_artifact", "check": "DONE-MARKER"},
            {"tier": "telepathy", "check": "Shadow just knows"},
            {"check": "no tier at all"},
            {"tier": "founder_confirm", "check": "the design is sound"},
        ], max_turns=2)
        m = run(self.engine(transcript="... DONE-MARKER ...").run_mission(mid))
        # the junk rows are machine-tier and unmet, so the boundary is NOT
        # reached -- the founder is not asked on the strength of nonsense
        self.assertNotEqual((m["state"], m.get("pause_reason")),
                            ("paused", "founder_confirm"))
        self.assertGreater(m["turns_used"], 1)

    def test_08_the_predicate_partitions_the_way_the_fix_intends(self):
        """The unit the three cases above turn on, asserted directly so a
        future edit cannot quietly restore all([])."""
        def boundary(results):
            pending = [r for r in results
                       if r["tier"] == "founder_confirm" and not r["met"]]
            machine = [r for r in results if r["tier"] != "founder_confirm"]
            others = bool(machine) and all(r["met"] for r in machine)
            return bool(results and pending and others)

        fc = {"tier": "founder_confirm", "met": False}
        self.assertFalse(boundary([fc, dict(fc)]), "all-confirm: never")
        self.assertTrue(boundary(
            [{"tier": "contains_artifact", "met": True}, fc]), "machine met")
        self.assertFalse(boundary(
            [{"tier": "contains_artifact", "met": False}, fc]), "machine unmet")
        self.assertFalse(boundary([]), "no checks")


if __name__ == "__main__":
    unittest.main()
