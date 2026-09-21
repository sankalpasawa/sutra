#!/usr/bin/env python3
"""A REPLY FROM NEEDS YOU PUTS THE WORKER BACK TO WORK (founder, 2026-09-21).

THE BUG. A mission at NEEDS YOU is `paused`, and run_mission has already left
its loop -- the top of the loop returns the moment it reads a paused state.
When the founder replied with a change, `_apply_task_fence` amended the
mission and `_invalidate_for_revision` released the pause by writing
`running` back onto the record. Nothing restarted the loop. The record then
read: running, v2, new objective, old decision superseded -- with no loop
driving it. Shadow said "I'll build that into its next instruction" and there
was never a next instruction.

WHAT THESE TESTS PIN, and the distinction is the whole point:

  REPLY   changes the work. Same mission, new revision, pending decision
          superseded, and the loop is RELAUNCHED so the worker executes the
          revised task. The reply does not satisfy anything.

  CONFIRM answers the question. It satisfies the check through
          confirm_check / settle_confirmation and lets the mission complete.
          It is a different door and this change does not touch it.

ASSERTED AT THE LAUNCH BOUNDARY, not on rendered text. `launch` is injected,
so what is asserted is that the runner was CALLED, for this mission id, after
the revision landed -- which is the fact the founder could not get from any
amount of conversation.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_reply_resumes.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import providers
import mission_engine
from mission_engine import MissionStore

import app


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self.launched = []

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def launch(self, mid, *a, **k):
        self.launched.append(mid)

    def europe(self, state="paused"):
        m = self.store.create(
            "Make a plan for a Europe trip.", "research",
            target_mode="new", target_session="sess-1",
            done_when=[{"tier": "founder_confirm",
                        "check": "The Europe plan matches the trip you want."}])
        self.store.transition(m["id"], "brief_confirm", "s")
        self.store.transition(m["id"], "running", "s")
        m = self.store.load(m["id"])
        m["turns_used"] = 3
        m["decision"] = {"question": "Does the Europe plan match?"}
        m["state"] = state
        if state == "paused":
            m["pause_reason"] = "founder_confirm"
        self.store.save(m)
        return m["id"]

    LONDON = {"mission": {
        "objective": "Make a plan for a Europe trip with 5 days in London.",
        "template": "research",
        "done_when": [{"tier": "founder_confirm",
                       "check": "The plan gives London 5 days and still works."}]}}

    def reply(self, mid, text="I want to spend 5 days in London, "
                             "adjust the plan accordingly.",
              blocks=None, was=None):
        """The NEEDS YOU reply, through the same calls the chat route makes."""
        was = was if was is not None else self.store.load(mid)["state"]
        blocks = self.LONDON if blocks is None else blocks
        app._record_founder_talk(mid, text, blocks)
        app._apply_task_fence(mid, blocks)
        return app.resume_after_revision(mid, was, store=self.store,
                                         launch=self.launch)


class TestTheReplyPutsTheWorkerBackToWork(Base):
    def test_the_worker_is_actually_launched(self):
        """THE BUG ITSELF. Everything else about the revision already
        worked; this is the call that was missing."""
        mid = self.europe()
        self.assertTrue(self.reply(mid))
        self.assertEqual(self.launched, [mid])

    def test_it_is_the_same_mission(self):
        mid = self.europe()
        self.reply(mid)
        self.assertEqual(self.launched, [mid])
        self.assertEqual(len(self.store.list()), 1,
                         "a second mission was created")

    def test_the_mission_carries_a_new_revision(self):
        mid = self.europe()
        before = self.store.load(mid)["version"]
        self.reply(mid)
        self.assertEqual(self.store.load(mid)["version"], before + 1)

    def test_the_worker_gets_the_new_constraint(self):
        mid = self.europe()
        self.reply(mid)
        m = self.store.load(mid)
        self.assertIn("London", m["objective"])
        self.assertTrue(any("London" in (c.get("check") or "")
                            for c in m["done_when"]))

    def test_the_founders_own_words_reach_the_worker_verbatim(self):
        """The forwarding lane carries the sentence itself, so the worker
        has what the founder said and not only Shadow's restatement."""
        mid = self.europe()
        self.reply(mid)
        says = self.store.load(mid)["founder_says"]
        self.assertTrue(any("5 days in London" in s["text"] for s in says))

    def test_the_pending_decision_is_superseded(self):
        mid = self.europe()
        self.reply(mid)
        self.assertIsNone(self.store.load(mid).get("decision"))

    def test_the_old_check_cannot_satisfy_the_new_revision(self):
        mid = self.europe()
        m = self.store.load(mid)
        m["done_when"][0]["met"] = True
        m["done_when"][0]["confirmed_by"] = "founder"
        self.store.save(m)
        self.reply(mid)
        for c in self.store.load(mid)["done_when"]:
            self.assertNotIn("met", c)
            self.assertNotIn("confirmed_by", c)

    def test_the_task_is_running_again(self):
        """The UI reads this: NEEDS YOU -> RUNNING while the worker runs."""
        mid = self.europe()
        self.reply(mid)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "running")
        self.assertIsNone(m.get("pause_reason"))

    def test_the_superseded_work_stays_visible_as_history(self):
        mid = self.europe()
        self.reply(mid)
        rows = self.store.load(mid)["revisions"]
        self.assertEqual(len(rows), 1)
        self.assertIn("Europe", rows[0]["objective"])
        self.assertNotIn("London", rows[0]["objective"])

    def test_the_budget_already_spent_stays_spent(self):
        mid = self.europe()
        self.reply(mid)
        self.assertEqual(self.store.load(mid)["turns_used"], 3)


class TestItLaunchesOnlyWhenItShould(Base):
    def test_a_task_already_running_is_not_relaunched(self):
        """Its loop is live and reads the new revision at the top of its
        next iteration. A second launch would be a second driver."""
        mid = self.europe("running")
        self.assertFalse(self.reply(mid, was="running"))
        self.assertEqual(self.launched, [])

    def test_a_draft_is_not_launched_by_a_fence(self):
        """Amend puts a draft in brief_confirm and Start is the founder's."""
        m = self.store.create("Plan something.", "research",
                              target_mode="new", target_session="s")
        self.assertFalse(self.reply(m["id"], was="draft"))
        self.assertEqual(self.launched, [])

    def test_a_reply_that_changes_nothing_launches_nothing(self):
        """Prose with no `mission` fence is conversation. It reaches
        founder_says and moves no state, so there is nothing to resume."""
        mid = self.europe()
        self.assertFalse(self.reply(mid, blocks={}))
        self.assertEqual(self.launched, [])
        self.assertEqual(self.store.load(mid)["state"], "paused")

    def test_a_terminal_task_is_never_launched(self):
        mid = self.europe()
        m = self.store.load(mid)
        m["state"] = "done"
        self.store.save(m)
        self.assertFalse(app.resume_after_revision(
            mid, "paused", store=self.store, launch=self.launch))
        self.assertEqual(self.launched, [])

    def test_a_launch_failure_costs_the_resume_and_nothing_else(self):
        def boom(*a, **k):
            raise RuntimeError("no runtime")
        mid = self.europe()
        app._apply_task_fence(mid, self.LONDON)
        self.assertFalse(app.resume_after_revision(
            mid, "paused", store=self.store, launch=boom))
        # the revision still stands; only the resume was lost
        self.assertIn("London", self.store.load(mid)["objective"])


class TestConfirmIsUntouched(Base):
    """CONFIRM ACCEPTS; REPLY CHANGES. The founder was explicit that both
    must keep working, so this pins the other door."""

    def test_confirm_still_satisfies_the_check(self):
        mid = self.europe()
        self.store.confirm_check(mid, 0, by="founder")
        m = self.store.load(mid)
        self.assertTrue(m["done_when"][0]["met"])
        self.assertEqual(m["done_when"][0]["confirmed_by"], "founder")

    def test_confirm_does_not_revise_the_mission(self):
        mid = self.europe()
        before = self.store.load(mid)["version"]
        self.store.confirm_check(mid, 0, by="founder")
        m = self.store.load(mid)
        self.assertEqual(m["version"], before,
                         "a confirmation bumped the revision")
        self.assertIsNone(m.get("revisions"),
                          "a confirmation superseded work it had accepted")

    def test_confirm_leaves_the_objective_alone(self):
        mid = self.europe()
        self.store.confirm_check(mid, 0, by="founder")
        self.assertIn("Europe", self.store.load(mid)["objective"])
        self.assertNotIn("London", self.store.load(mid)["objective"])


class TestTheRevisedMissionCompletesAsItself(Base):
    def test_the_completion_describes_the_revised_state(self):
        mid = self.europe()
        self.reply(mid)
        m = self.store.load(mid)
        results = [{"check": c["check"], "tier": c["tier"], "met": True}
                   for c in m["done_when"]]
        c = mission_engine.completion_summary(m, results)
        self.assertIn("London", c["objective"])
        self.assertTrue(any("London" in line for line in c["completed"]))
        self.assertIn("Europe", c["was"])
        self.assertEqual(c["revised"], 1)

    def test_no_superseded_check_is_reported_as_completed(self):
        mid = self.europe()
        m = self.store.load(mid)
        m["done_when"][0]["met"] = True
        self.store.save(m)
        self.reply(mid)
        m = self.store.load(mid)
        results = [{"check": c["check"], "tier": c["tier"],
                    "met": bool(c.get("met"))} for c in m["done_when"]]
        c = mission_engine.completion_summary(m, results)
        self.assertEqual(c["completed"], [],
                         "a verdict from the old revision survived into the "
                         "new revision's result")


if __name__ == "__main__":
    unittest.main()
