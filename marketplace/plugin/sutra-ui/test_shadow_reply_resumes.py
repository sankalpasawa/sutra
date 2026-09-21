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


class TestAReplyWithNoFenceStillResumes(Base):
    """PASS 8 (founder, 2026-09-21): THE OTHER HALF OF THE DEAD END.

    The lane above covers the reply Shadow WRAPPED IN A `mission` FENCE --
    the task is amended, the pause is released by _invalidate_for_revision,
    and resume_after_revision relaunches. But Shadow answers most replies
    CONVERSATIONALLY, with no fence at all. On that path nothing amended, so
    nothing released the pause; forward_to_worker returned immediately
    because "a mission that is not running has no worker listening"; and the
    task sat at NEEDS YOU forever with the founder's words on the record and
    no loop to read them.

    `resume_after_reply` is the last-resort door for exactly that shape, and
    the distinction it turns on is Shadow's own forwarding verdict:

        a STATUS QUESTION leaves the worker exactly as it is
        NEW DIRECTION releases the pause and starts the loop

    Asserted at the launch boundary, like everything else in this file.
    """

    #: Shadow answered in words: no `mission` fence, and its `forward`
    #: verdict says the worker needs to hear this.
    DIRECTION = {"forward": {"worker": True}}
    #: ...and the same reply classified as a question about the work.
    STATUS = {"forward": {"worker": False}}

    def talk(self, mid, text, blocks, was=None, reason=None):
        """A founder line through the calls the chat route makes, minus the
        fence -- which is the whole point of this lane."""
        m = self.store.load(mid)
        was = was if was is not None else m["state"]
        reason = reason if reason is not None else m.get("pause_reason")
        app._record_founder_talk(mid, text, blocks)
        return app.resume_after_reply(mid, was, reason, text, blocks,
                                      store=self.store, launch=self.launch)

    def test_new_direction_at_needs_you_relaunches_the_worker(self):
        mid = self.europe()
        self.assertTrue(self.talk(mid, "Let's roam North India also.",
                                  self.DIRECTION))
        self.assertEqual(self.launched, [mid])
        self.assertEqual(self.store.load(mid)["state"], "running",
                         "the pause must be released")

    def test_the_founders_words_are_on_the_record_for_the_decider(self):
        """NOTHING COMPOSES AN INSTRUCTION HERE. The line is queued on
        `founder_says`, which is what the decider reads at the top of the
        resumed turn -- with the existing plan in front of it."""
        mid = self.europe()
        self.talk(mid, "Let's roam North India also.", self.DIRECTION)
        says = self.store.load(mid)["founder_says"]
        self.assertEqual(says[-1]["text"], "Let's roam North India also.")
        self.assertFalse(says[-1]["seen"], "the decider has not read it yet")
        self.assertEqual(says[-1]["fwd"], "queued",
                         "and it is queued for the worker")

    def test_a_status_question_leaves_the_worker_alone(self):
        """"alright where are we at right now with this?" is not an
        instruction, and answering it must not restart anything."""
        mid = self.europe()
        self.assertFalse(self.talk(mid, "alright where are we at right now?",
                                   self.STATUS))
        self.assertEqual(self.launched, [], "nothing may be launched")
        self.assertEqual(self.store.load(mid)["state"], "paused",
                         "and the task stays where it was")

    def test_a_status_question_is_still_recorded(self):
        mid = self.europe()
        self.talk(mid, "where are we at?", self.STATUS)
        says = self.store.load(mid)["founder_says"]
        self.assertEqual(says[-1]["text"], "where are we at?")
        self.assertEqual(says[-1]["fwd"], "skip",
                         "recorded, and not queued for the worker")

    def test_a_running_task_is_not_touched(self):
        """A message while the worker is RUNNING goes through the ordinary
        forward path; this door must not fire and must not restart it."""
        mid = self.europe(state="running")
        self.assertFalse(self.talk(mid, "Let's roam North India also.",
                                   self.DIRECTION, was="running", reason=None))
        self.assertEqual(self.launched, [])

    def test_a_take_over_pause_is_not_resumed_behind_the_founder(self):
        """`founder_intervened` has its own door -- Hand back to Shadow --
        and resuming it from a chat line is the bug park_hold prevents."""
        mid = self.europe()
        m = self.store.load(mid)
        m["pause_reason"] = "founder_intervened"
        self.store.save(m)
        self.assertFalse(self.talk(mid, "Let's roam North India also.",
                                   self.DIRECTION))
        self.assertEqual(self.launched, [])

    def test_it_defers_to_the_fence_path(self):
        """A reply Shadow DID fence is handled by resume_after_revision, which
        leaves the mission running -- so this door must find nothing to do and
        must not launch a second time."""
        mid = self.europe()
        was = self.store.load(mid)["state"]
        self.reply(mid)                          # the fenced path, launches
        self.assertEqual(self.launched, [mid])
        self.assertFalse(app.resume_after_reply(
            mid, was, "founder_confirm", "I want 5 days in London.",
            self.LONDON, store=self.store, launch=self.launch))
        self.assertEqual(self.launched, [mid], "no duplicate execution")

    def test_no_duplicate_launch_when_a_loop_is_already_live(self):
        mid = self.europe()

        class _Live:
            def done(self):
                return False

        app.shadow_runner.RUNNING[mid] = _Live()
        try:
            self.assertFalse(self.talk(mid, "Let's roam North India also.",
                                       self.DIRECTION))
            self.assertEqual(self.launched, [])
        finally:
            app.shadow_runner.RUNNING.pop(mid, None)

    def test_a_missing_forward_fence_defaults_to_resuming(self):
        """THE FLOOR, not an opinion: a dropped fence must never silently
        swallow "actually make it 20 lines". shadow_forward._is_meta_only
        answers, defaulting to forward."""
        mid = self.europe()
        self.assertTrue(self.talk(mid, "Let's roam North India also.", {}))
        self.assertEqual(self.launched, [mid])

    def test_confirm_is_a_different_door_and_is_untouched(self):
        """CONFIRM answers the question; a reply changes the work. This lane
        must not turn one into the other."""
        mid = self.europe()
        self.talk(mid, "Let's roam North India also.", self.DIRECTION)
        m = self.store.load(mid)
        self.assertFalse(
            (m.get("done_when") or [{}])[0].get("met"),
            "a reply must not satisfy the check the way Confirm does")


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
