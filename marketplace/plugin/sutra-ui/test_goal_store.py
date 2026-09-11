"""V5 slice 2: the persistent Goal store.

Store-only. Nothing here touches the mission engine, the scheduler, the
feed or any surface -- if a test in this file needs one of those, the slice
boundary has been crossed.
"""
import os
import tempfile
import unittest

import goal_store
from goal_store import GoalStore


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self.store = GoalStore()

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def _goal(self, outcome="ship the connector retry fix", session="s-1",
              done_when=None):
        return self.store.create(outcome, session, done_when=done_when)


class TestCreateAndPersist(Base):
    def test_01_create_lands_in_draft_with_the_full_schema(self):
        g = self._goal(done_when=[{"tier": "contains_artifact",
                                   "check": "retry:"}])
        self.assertTrue(g["id"].startswith("g-"))
        self.assertEqual(g["state"], "draft")
        self.assertEqual(g["target_session"], "s-1")
        self.assertEqual(g["outcome"], "ship the connector retry fix")
        self.assertEqual(g["done_when"],
                         [{"tier": "contains_artifact", "check": "retry:"}])
        self.assertIsNone(g["current_mission_id"])
        self.assertEqual(g["attempts"], [])
        self.assertEqual(g["learned"], [],
                         "reserved by schema, written by no code yet")
        for field in ("created_at", "created_ns", "updated_at", "seq",
                      "history"):
            self.assertIn(field, g)

    def test_02_record_survives_a_reload_by_a_fresh_store(self):
        g = self._goal(done_when=[{"tier": "verify", "check": "build"}])
        self.store.transition(g["id"], "working", "founder started it")
        self.store.bind_mission(g["id"], "m-abc123", "first attempt")
        fresh = GoalStore().load(g["id"])
        self.assertEqual(fresh["state"], "working")
        self.assertEqual(fresh["current_mission_id"], "m-abc123")
        self.assertEqual(fresh["done_when"],
                         [{"tier": "verify", "check": "build"}])
        self.assertEqual(len(fresh["attempts"]), 1)
        self.assertEqual(fresh["attempts"][0]["attempt"], 1)
        self.assertTrue(len(fresh["history"]) >= 3,
                        "create + transition + bind are all on the record")

    def test_03_goals_live_in_their_own_sibling_directory(self):
        g = self._goal()
        path = os.path.join(self.tmp.name, "goals", g["id"] + ".json")
        self.assertTrue(os.path.exists(path), path)
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp.name, "missions",
                                        g["id"] + ".json")),
            "a goal must never be written into the mission store")

    def test_04_create_refuses_a_goal_with_no_outcome_or_no_chat(self):
        with self.assertRaises(ValueError):
            self.store.create("", "s-9")
        with self.assertRaises(ValueError):
            self.store.create("do the thing", "")

    def test_05_load_of_an_unknown_goal_is_none_not_a_raise(self):
        self.assertIsNone(self.store.load("g-nope"))

    def test_06_list_filters_by_state_and_session(self):
        a = self._goal("outcome A", "s-1")
        b = self._goal("outcome B", "s-2")
        self.store.transition(b["id"], "working")
        self.assertEqual([g["id"] for g in self.store.list()],
                         [a["id"], b["id"]], "oldest created first")
        self.assertEqual([g["id"] for g in self.store.list(states=("draft",))],
                         [a["id"]])
        self.assertEqual(
            [g["id"] for g in self.store.list(target_session="s-2")],
            [b["id"]])


class TestStateModel(Base):
    def test_07_state_vocabulary_is_exactly_the_v5_six(self):
        self.assertEqual(goal_store.STATES,
                         ("draft", "working", "verifying", "blocked",
                          "done", "stopped"))
        self.assertEqual(goal_store.TERMINAL, ("done", "stopped"))
        self.assertEqual(goal_store.ACTIVE,
                         ("draft", "working", "verifying", "blocked"))

    def test_08_the_v5_lifecycle_path_is_legal(self):
        g = self._goal()
        self.assertEqual(
            self.store.transition(g["id"], "working")["state"], "working")
        self.assertEqual(
            self.store.transition(g["id"], "verifying")["state"], "verifying")
        # a failed check sends it back to working, not to a terminal
        self.assertEqual(
            self.store.transition(g["id"], "working")["state"], "working")
        self.assertEqual(
            self.store.transition(g["id"], "blocked")["state"], "blocked")
        # answered or extended -> the same goal resumes
        self.assertEqual(
            self.store.transition(g["id"], "working")["state"], "working")
        self.assertEqual(
            self.store.transition(g["id"], "done")["state"], "done")

    def test_09_blocked_is_not_terminal_and_can_be_abandoned(self):
        self.assertNotIn("blocked", goal_store.TERMINAL)
        g = self._goal()
        self.store.transition(g["id"], "working")
        self.store.transition(g["id"], "blocked")
        self.assertEqual(
            self.store.transition(g["id"], "stopped",
                                  "founder abandoned")["state"], "stopped")

    def test_10_illegal_hops_raise_and_terminals_are_exit_less(self):
        g = self._goal()
        with self.assertRaises(ValueError):
            self.store.transition(g["id"], "done")      # draft -> done
        with self.assertRaises(ValueError):
            self.store.transition(g["id"], "verifying")  # draft -> verifying
        self.store.transition(g["id"], "working")
        with self.assertRaises(ValueError):
            self.store.transition(g["id"], "draft")     # no way back
        for dead in goal_store.TERMINAL:
            self.assertEqual(goal_store.TRANSITIONS[dead], (),
                             "%s must stay exit-less" % dead)
        self.store.transition(g["id"], "done")
        with self.assertRaises(ValueError):
            self.store.transition(g["id"], "working")
        self.assertEqual(self.store.load(g["id"])["state"], "done",
                         "a refused transition must not change the state")

    def test_11_transitions_are_recorded_on_the_goal(self):
        g = self._goal()
        self.store.transition(g["id"], "working", "founder tapped Start")
        row = self.store.load(g["id"])["history"][-1]
        self.assertEqual((row["from"], row["to"]), ("draft", "working"))
        self.assertIn("tapped Start", row["note"])
        self.assertTrue(row["ts"])


class TestSessionBinding(Base):
    def test_12_a_goal_is_bound_to_one_chat(self):
        g = self._goal(session="01a081")
        self.assertEqual(self.store.load(g["id"])["target_session"], "01a081")
        self.assertEqual(
            self.store.active_for_session("01a081")["id"], g["id"])
        self.assertIsNone(self.store.active_for_session("someone-else"))

    def test_13_one_active_goal_per_chat_is_enforced(self):
        g1 = self._goal("outcome A", "s-1")
        with self.assertRaises(ValueError) as caught:
            self._goal("outcome B", "s-1")
        self.assertIn("one active goal per chat", str(caught.exception))
        # a different chat is unaffected
        self._goal("outcome C", "s-2")
        # ...and every non-terminal state still holds the chat
        self.store.transition(g1["id"], "working")
        with self.assertRaises(ValueError):
            self._goal("outcome D", "s-1")
        self.store.transition(g1["id"], "blocked")
        with self.assertRaises(ValueError):
            self._goal("outcome E", "s-1")

    def test_14_a_terminal_goal_releases_its_chat(self):
        g1 = self._goal("outcome A", "s-1")
        self.store.transition(g1["id"], "stopped", "abandoned")
        g2 = self._goal("outcome B", "s-1")
        self.assertNotEqual(g1["id"], g2["id"])
        self.assertEqual(self.store.active_for_session("s-1")["id"], g2["id"])
        self.assertEqual(len(self.store.list(target_session="s-1")), 2,
                         "the finished goal is archived, never deleted")


class TestAttemptBinding(Base):
    def test_15_bind_sets_the_live_mission_and_opens_an_attempt(self):
        g = self._goal()
        self.store.transition(g["id"], "working")
        out = self.store.bind_mission(g["id"], "m-111", "first try")
        self.assertEqual(out["current_mission_id"], "m-111")
        self.assertEqual(len(out["attempts"]), 1)
        row = out["attempts"][0]
        self.assertEqual(row["mission_id"], "m-111")
        self.assertEqual(row["attempt"], 1)
        self.assertTrue(row["started_at"])
        self.assertIsNone(row["ended_at"])
        self.assertIsNone(row["ended_state"])

    def test_16_attempts_accumulate_across_tries(self):
        g = self._goal()
        self.store.transition(g["id"], "working")
        self.store.bind_mission(g["id"], "m-111")
        self.store.release_mission(g["id"], "failed", "max turns")
        self.store.transition(g["id"], "blocked")
        self.store.transition(g["id"], "working")
        out = self.store.bind_mission(g["id"], "m-222")
        self.assertEqual(out["current_mission_id"], "m-222")
        self.assertEqual([a["attempt"] for a in out["attempts"]], [1, 2])
        self.assertEqual(out["attempts"][0]["ended_state"], "failed")
        self.assertIn("max turns", out["attempts"][0]["note"])
        self.assertIsNone(out["attempts"][1]["ended_at"])
        self.assertEqual(self.store.attempt_count(g["id"]), 2)
        # and it all survives a reload
        fresh = GoalStore().load(g["id"])
        self.assertEqual([a["attempt"] for a in fresh["attempts"]], [1, 2])
        self.assertEqual(fresh["current_mission_id"], "m-222")

    def test_17_one_live_attempt_at_a_time(self):
        g = self._goal()
        self.store.transition(g["id"], "working")
        self.store.bind_mission(g["id"], "m-111")
        # re-binding the same mission is a no-op, not an error
        self.assertEqual(
            self.store.bind_mission(g["id"], "m-111")["current_mission_id"],
            "m-111")
        with self.assertRaises(ValueError):
            self.store.bind_mission(g["id"], "m-222")
        with self.assertRaises(ValueError):
            self.store.bind_mission(g["id"], "")

    def test_18_release_needs_a_live_attempt_and_clears_the_binding(self):
        g = self._goal()
        self.store.transition(g["id"], "working")
        with self.assertRaises(ValueError):
            self.store.release_mission(g["id"], "failed")
        self.store.bind_mission(g["id"], "m-111")
        out = self.store.release_mission(g["id"], "done", "verified")
        self.assertIsNone(out["current_mission_id"])
        self.assertEqual(out["attempts"][0]["ended_state"], "done")
        self.assertEqual(out["state"], "working",
                         "releasing an attempt must not move the goal")

    def test_19_a_terminal_goal_takes_no_new_attempts(self):
        g = self._goal()
        self.store.transition(g["id"], "stopped")
        with self.assertRaises(ValueError):
            self.store.bind_mission(g["id"], "m-999")


class TestStaleWriteGuard(Base):
    def test_20_an_older_holder_refuses_instead_of_clobbering(self):
        g = self._goal()
        first = self.store.load(g["id"])
        stale = self.store.load(g["id"])
        first["outcome"] = "the winning write"
        self.store.save(first)
        stale["outcome"] = "the losing write"
        with self.assertRaises(ValueError) as caught:
            self.store.save(stale)
        self.assertIn("stale write", str(caught.exception))
        self.assertEqual(self.store.load(g["id"])["outcome"],
                         "the winning write")

    def test_21_seq_and_updated_at_advance_on_every_write(self):
        g = self._goal()
        self.assertEqual(g["seq"], 1)
        again = self.store.save(self.store.load(g["id"]))
        self.assertEqual(again["seq"], 2)
        self.assertTrue(again["updated_at"])

    def test_22_save_refuses_a_record_with_no_id(self):
        with self.assertRaises(ValueError):
            self.store.save({"outcome": "no id here"})
        with self.assertRaises(ValueError):
            self.store.save("not a record")


if __name__ == "__main__":
    unittest.main()
