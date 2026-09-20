"""Shadow v4.1, the engine half (SHADOW-V3 section 13, founder 2026-09-21).

Three rulings, and this lane holds the two that live in the store:

  V4-7  THE FOUNDER'S WORDS SET THE TASK. A limit stated in a chat binds THAT
        task at once, even while it runs. `set_task_turns` is the one writer:
        a number (clamped like every other turn budget), or None for "no
        limit", which switches the turn check off for that task and nothing
        else. Undo puts back what was there. The default in task-limits.json
        is never touched from here, and neither is any other task.

  V4-9  DONE IS NOT A DEAD END. `reopen` takes a finished task (done, stopped,
        failed) back to running through the cap -- same record, same target
        chat -- with a fresh allowance counted from the reopen and the
        founder's new words as the check of this leg. The legal-transition
        table is NOT loosened: every existing caller that hops out of a
        terminal state by accident still raises.

Run: ./run-tests.sh test_shadow_v41_engine.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-v41-engine-")

import mission_engine                          # noqa: E402
import providers                               # noqa: E402
from mission_engine import MissionStore         # noqa: E402


class Base(unittest.TestCase):
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

    def task(self, kind="fix", state="running", target="s-worker-1",
             turns_used=0, **extra):
        m = self.store.create("make the login test pass", kind,
                              target_mode="existing", target_session=target,
                              done_when=[{"tier": "founder_confirm",
                                          "check": "the test passes"}])
        m = self.store.load(m["id"])
        m["state"] = state
        m["turns_used"] = turns_used
        m.update(extra)
        self.store.save(m)
        return self.store.load(m["id"])


# ----------------------------------------------------------------- LIMITS --
class TestWordsSetTheTask(Base):

    def test_01_a_number_binds_the_running_task_at_once(self):
        m = self.task(kind="fix", turns_used=3)
        self.assertEqual(m["max_turns"], 20)
        out = mission_engine.set_task_turns(self.store, m["id"], 60)
        self.assertEqual(out["max_turns"], 60)
        self.assertEqual(self.store.load(m["id"])["max_turns"], 60)
        self.assertEqual(self.store.load(m["id"])["state"], "running")

    def test_02_none_means_no_limit_and_the_turn_check_is_off(self):
        m = self.task(turns_used=19)
        out = mission_engine.set_task_turns(self.store, m["id"], None)
        self.assertTrue(out["no_turn_limit"])
        out["turns_used"] = 5000
        self.assertFalse(mission_engine.out_of_turns(out))

    def test_03_the_turn_check_still_binds_a_limited_task(self):
        m = self.task(turns_used=20)
        self.assertTrue(mission_engine.out_of_turns(m))
        m["turns_used"] = 19
        self.assertFalse(mission_engine.out_of_turns(m))

    def test_04_words_for_none_are_accepted(self):
        for word in ("none", "no limit", "unlimited", "NONE"):
            m = self.task(target="s-" + word.replace(" ", ""))
            out = mission_engine.set_task_turns(self.store, m["id"], word)
            self.assertTrue(out["no_turn_limit"], word)

    def test_05_junk_is_refused_and_nothing_is_written(self):
        m = self.task()
        for junk in ("twenty", "", [], {"n": 5}, True):
            with self.assertRaises(ValueError):
                mission_engine.set_task_turns(self.store, m["id"], junk)
        after = self.store.load(m["id"])
        self.assertEqual(after["max_turns"], 20)
        self.assertFalse(after.get("no_turn_limit"))

    def test_06_out_of_band_numbers_clamp_like_every_turn_budget(self):
        m = self.task()
        out = mission_engine.set_task_turns(self.store, m["id"], 5000)
        self.assertEqual(out["max_turns"], mission_engine.TURNS_CEILING)

    def test_07_a_number_the_task_has_already_spent_is_refused(self):
        """Otherwise the founder's own words would kill the task at its next
        turn as budget_exhausted."""
        m = self.task(turns_used=12)
        with self.assertRaises(ValueError):
            mission_engine.set_task_turns(self.store, m["id"], 12)
        self.assertEqual(self.store.load(m["id"])["max_turns"], 20)

    def test_08_a_kind_that_never_speaks_has_no_turn_limit_to_set(self):
        m = self.task(kind="watch")
        with self.assertRaises(ValueError):
            mission_engine.set_task_turns(self.store, m["id"], 10)

    def test_09_undo_puts_back_what_was_there(self):
        m = self.task()
        mission_engine.set_task_turns(self.store, m["id"], 45)
        mission_engine.set_task_turns(self.store, m["id"], None)
        back = mission_engine.undo_task_turns(self.store, m["id"])
        self.assertEqual(back["max_turns"], 45)
        self.assertFalse(back.get("no_turn_limit"))
        back = mission_engine.undo_task_turns(self.store, m["id"])
        self.assertEqual(back["max_turns"], 20)
        with self.assertRaises(ValueError):
            mission_engine.undo_task_turns(self.store, m["id"])

    def test_10_the_default_and_every_other_task_are_untouched(self):
        a = self.task(target="s-a")
        b = self.task(target="s-b")
        mission_engine.set_task_turns(self.store, a["id"], None)
        self.assertFalse(os.path.exists(mission_engine.limits_path()))
        self.assertEqual(mission_engine.turn_budget("fix"), 20)
        self.assertEqual(self.store.load(b["id"])["max_turns"], 20)
        self.assertFalse(self.store.load(b["id"]).get("no_turn_limit"))
        fresh = self.store.create("another", "fix", target_mode="new")
        self.assertEqual(fresh["max_turns"], 20)
        self.assertFalse(fresh.get("no_turn_limit"))

    def test_11_the_override_is_stamped_so_the_sheet_can_show_it(self):
        m = self.task()
        out = mission_engine.set_task_turns(self.store, m["id"], 33)
        self.assertEqual(out["limits_override"]["turns"], 33)
        out = mission_engine.set_task_turns(self.store, m["id"], None)
        self.assertEqual(out["limits_override"]["turns"], "none")
        self.assertEqual(mission_engine.limits_label(out),
                         "turns: no limit, this task")

    def test_12_an_unknown_task_is_a_value_error(self):
        with self.assertRaises(ValueError):
            mission_engine.set_task_turns(self.store, "m-nope", 10)


# ----------------------------------------------------------------- REOPEN --
class TestAFinishedTaskReopens(Base):

    def test_20_done_reopens_to_running_on_the_same_record(self):
        m = self.task(state="done", turns_used=7,
                      completion={"headline": "Done"})
        out = mission_engine.reopen(self.store, m["id"],
                                    "also cover the logout path")
        self.assertEqual(out["id"], m["id"])
        self.assertEqual(out["state"], "running")
        self.assertEqual(out["target_session"], "s-worker-1")
        self.assertEqual(out["turns_used"], 7)

    def test_21_the_allowance_counts_again_from_the_reopen(self):
        m = self.task(state="failed", turns_used=20)
        out = mission_engine.reopen(self.store, m["id"], "try once more")
        self.assertEqual(out["max_turns"], 40)
        self.assertFalse(mission_engine.out_of_turns(out))

    def test_22_stopped_and_failed_reopen_too(self):
        for state in ("stopped", "failed"):
            m = self.task(state=state, target="s-" + state,
                          ended_by="founder")
            out = mission_engine.reopen(self.store, m["id"], "keep going")
            self.assertEqual(out["state"], "running", state)
            self.assertNotIn("ended_by", out)

    def test_23_the_new_words_are_the_check_of_this_leg(self):
        m = self.task(state="done")
        m["done_when"][0]["met"] = True
        self.store.save(m)
        out = mission_engine.reopen(self.store, m["id"],
                                    "also cover the logout path")
        self.assertEqual(len(out["done_when"]), 1)
        self.assertIn("logout", out["done_when"][0]["check"])
        self.assertFalse(out["done_when"][0].get("met"))
        done, _ = mission_engine.evaluate_done_when(out, "", None)
        self.assertFalse(done, "a reopened task must not finish on old checks")
        self.assertEqual(out["reopened"][-1]["done_when"][0]["check"],
                         "the test passes")

    def test_24_shadow_reads_the_new_words(self):
        m = self.task(state="done")
        out = mission_engine.reopen(self.store, m["id"], "add a changelog line")
        says = out["founder_says"]
        self.assertEqual(says[-1]["text"], "add a changelog line")
        self.assertEqual(says[-1]["via"], "reopen")
        self.assertFalse(says[-1]["seen"])

    def test_25_hand_back_with_no_words_asks_the_founder_at_the_end(self):
        m = self.task(state="done")
        out = mission_engine.reopen(self.store, m["id"], "", via="hand_back")
        self.assertEqual(out["state"], "running")
        self.assertEqual(out["done_when"][0]["tier"], "founder_confirm")
        self.assertEqual(out["reopened"][-1]["via"], "hand_back")

    def test_26_over_the_cap_it_waits_its_turn(self):
        mission_engine.set_max_running(1)
        self.task(state="running", target="s-busy")
        m = self.task(state="done", target="s-mine")
        out = mission_engine.reopen(self.store, m["id"], "more")
        self.assertEqual(out["state"], "queued")

    def test_27_refused_when_another_running_task_has_the_chat(self):
        m = self.task(state="done", target="s-shared")
        other = self.task(state="running", target="s-shared")
        with self.assertRaises(ValueError) as ctx:
            mission_engine.reopen(self.store, m["id"], "more")
        self.assertIn(other["id"], str(ctx.exception))
        self.assertEqual(self.store.load(m["id"])["state"], "done")

    def test_28_only_a_finished_task_reopens(self):
        for state in ("draft", "running", "paused", "queued", "blocked"):
            m = self.task(state=state, target="s-" + state)
            with self.assertRaises(ValueError):
                mission_engine.reopen(self.store, m["id"], "more")

    def test_29_the_transition_table_is_not_loosened(self):
        """A stray hop out of a terminal state is still a bug at the call
        site: reopen is the one door."""
        for state in mission_engine.TERMINAL:
            self.assertEqual(mission_engine.TRANSITIONS[state], ())
        m = self.task(state="done")
        with self.assertRaises(ValueError):
            self.store.transition(m["id"], "running", "stray")

    def test_30_no_limit_survives_a_reopen(self):
        m = self.task(state="running")
        mission_engine.set_task_turns(self.store, m["id"], None)
        m = self.store.load(m["id"])
        m["state"] = "done"
        self.store.save(m)
        out = mission_engine.reopen(self.store, m["id"], "more")
        self.assertTrue(out["no_turn_limit"])
        self.assertFalse(mission_engine.out_of_turns(out))

    def test_31_the_record_keeps_every_leg(self):
        m = self.task(state="done", turns_used=4,
                      completion={"headline": "Done"})
        mission_engine.reopen(self.store, m["id"], "leg two")
        again = self.store.load(m["id"])
        again["state"] = "stopped"
        again["turns_used"] = 9
        self.store.save(again)
        out = mission_engine.reopen(self.store, m["id"], "leg three")
        self.assertEqual([r["from"] for r in out["reopened"]],
                         ["done", "stopped"])
        self.assertEqual([r["at_turn"] for r in out["reopened"]], [4, 9])
        self.assertEqual(out["reopened"][0]["completion"],
                         {"headline": "Done"})
        self.assertNotIn("completion", out)

    def test_32_a_task_that_never_got_a_chat_is_sent_to_retry(self):
        m = self.store.create("never provisioned", "fix", target_mode="new")
        m["state"] = "failed"
        self.store.save(m)
        with self.assertRaises(ValueError) as ctx:
            mission_engine.reopen(self.store, m["id"], "more")
        self.assertIn("Retry", str(ctx.exception))
        self.assertEqual(self.store.load(m["id"])["state"], "failed")


if __name__ == "__main__":
    unittest.main()
