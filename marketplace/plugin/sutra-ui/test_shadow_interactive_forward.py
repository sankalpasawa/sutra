#!/usr/bin/env python3
"""THE INTERACTIVE FORWARDING LANE (founder, 2026-09-21).

WHAT THIS FILE PINS. A founder line that can change the work reaches the
WORKER'S OWN INPUT QUEUE on the request that carried it -- not on the next
steering turn, and not after a decider has re-authored it. A founder line
that is a question for Shadow reaches the worker never, and costs it no turn.

ASSERTED AT THE QUEUE, NEVER AT THE UI. Every delivery assertion below reads
`rt.turn_queue` -- the actual boundary the pump drains into the worker
session -- because the failure this lane exists to fix looked exactly like
success from the chat pane: the founder saw Shadow answer, and the worker
was never told. A test that watched an event or a record would have passed
against the broken build.

WHAT IT DELIBERATELY DOES NOT ASSERT. Whether a given sentence is worker-
relevant is SHADOW'S judgement, taken on the turn it was already taking
(shadow_task_chat's `forward` fence). Scripting a model and asserting its
verdict would be testing the script. So the verdicts here are supplied, and
what is asserted is the plumbing around them -- plus the FALLBACK classifier,
which is deterministic, is exercised against the founder's own examples, and
is the only part of classification this code actually owns.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_interactive_forward.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import providers
import session_runtime
import shadow_egress
import shadow_forward
import shadow_runner
from mission_engine import MissionStore

import app


class FakeEvent:
    def __init__(self):
        self.set_count = 0

    def set(self):
        self.set_count += 1


class FakeRuntime:
    """A worker session reduced to the only two things this lane touches.

    The TurnQueue is the REAL one, not a list: its lane priority and its
    dedupe set are two of the guarantees under test, and a stand-in would
    have asserted the stand-in.
    """

    def __init__(self):
        self.turn_queue = session_runtime.TurnQueue()
        self.queue_event = FakeEvent()

    def drain(self):
        out = []
        while True:
            payload = self.turn_queue.get()
            if payload is None:
                return out
            out.append(payload)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self.rt = FakeRuntime()
        self._orig_lookup = app.lookup_runtime
        app.lookup_runtime = lambda sid: (self.rt if sid == "sess-1" else None)

    def tearDown(self):
        app.lookup_runtime = self._orig_lookup
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def running(self):
        m = self.store.create("Find the latest Valentino Rossi news.",
                              "research", target_mode="new",
                              target_session="sess-1")
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        m["manifest_delivered"] = True
        m["turns_used"], m["max_turns"] = 2, 25
        self.store.save(m)
        return m["id"]

    def said(self, mid, text, worker):
        """The founder says one thing, with Shadow's verdict supplied."""
        app._record_founder_talk(mid, text, {"forward": {"worker": worker}})

    def rows(self, mid):
        return self.store.load(mid)["founder_says"]

    def fwd(self, mid):
        return [r.get("fwd") for r in self.rows(mid)]

    def bodies(self):
        """The founder-visible part of every payload the worker was handed."""
        out = []
        for payload in self.rt.drain():
            msg = payload["message"]
            out.append(msg.split("\n\n", 1)[1] if "\n\n" in msg else msg)
        return out


# --------------------------------------------------- 1. classification ----
class TestClassification(Base):
    """The FALLBACK classifier, against the founder's own two lists.

    This runs when Shadow's fence is missing or unparseable. Its rule is
    "forward unless every sentence is plainly a question about Shadow", and
    these are the exact sentences the founder wrote the rule from.
    """

    FORWARD = ("Use official sources only.",
               "Actually make it 20 lines instead of 10.",
               "Don't include salary estimates.",
               "Name the file foo.txt instead.",
               "Focus only on 2026.",
               "Yes, go ahead and create it.")

    HOLD = ("What's the status?",
            "How many turns have we used?",
            "Why are you asking me this?",
            "What did you just do?",
            "Shadow, explain that to me.")

    def test_the_founders_forward_examples_forward(self):
        for text in self.FORWARD:
            self.assertTrue(shadow_forward.classify(text),
                            "should reach the worker: %r" % text)

    def test_the_founders_shadow_only_examples_do_not(self):
        for text in self.HOLD:
            self.assertFalse(shadow_forward.classify(text),
                             "should NOT reach the worker: %r" % text)

    def test_shadow_outranks_the_fallback_in_both_directions(self):
        """The fence is the primary; the fallback only answers without one."""
        self.assertFalse(shadow_forward.classify(
            "Use official sources only.", {"forward": {"worker": False}}))
        self.assertTrue(shadow_forward.classify(
            "What's the status?", {"forward": {"worker": True}}))

    def test_a_malformed_fence_falls_through_to_the_fallback(self):
        for blocks in ({}, {"forward": {}}, {"forward": {"worker": "yes"}},
                       {"forward": "true"}, None):
            self.assertTrue(shadow_forward.classify(
                "Use official sources only.", blocks), blocks)

    def test_ambiguous_forwards_rather_than_being_dropped(self):
        """The founder's rule for the unclear case, asserted directly."""
        for text in ("2026 only.", "the second one", "no, the other file",
                     "hmm, maybe drop that", "official ones"):
            self.assertTrue(shadow_forward.classify(text), repr(text))

    def test_a_question_carrying_a_constraint_forwards(self):
        """Per sentence, never whole-message: the constraint must survive."""
        self.assertTrue(shadow_forward.classify(
            "What's the status? Also use official sources only."))

    def test_an_empty_line_is_not_a_forward(self):
        for text in ("", "   ", "\n"):
            self.assertFalse(shadow_forward.classify(text), repr(text))


# ------------------------------------------------ 2. ordering + shape -----
class TestOrderingAndCoalescing(Base):
    def test_two_worker_lines_reach_the_worker_in_order(self):
        mid = self.running()
        self.said(mid, "Use official F1 sources.", True)
        self.said(mid, "Only use 2026 data.", True)
        _i, payload = shadow_forward.deliverable(self.store.load(mid))
        self.assertIn("Use official F1 sources.\nOnly use 2026 data.", payload)

    def test_three_rapid_lines_coalesce_into_one_turn_in_order(self):
        mid = self.running()
        for text in ("Use official F1 sources.", "Only use 2026 data.",
                     "Actually focus on Verstappen."):
            self.said(mid, text, True)
        app.forward_to_worker(mid)
        bodies = self.bodies()
        self.assertEqual(len(bodies), 1, "three lines must cost ONE turn")
        self.assertEqual(bodies[0], "Use official F1 sources.\n"
                                    "Only use 2026 data.\n"
                                    "Actually focus on Verstappen.")

    def test_a_correction_is_kept_whole_never_resolved_away(self):
        """Coalescing joins; it must not decide which line wins."""
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        self.said(mid, "Actually, any source is fine.", True)
        app.forward_to_worker(mid)
        body = self.bodies()[0]
        self.assertEqual(body, "Use official sources only.\n"
                               "Actually, any source is fine.")

    def test_shadow_only_lines_are_never_coalesced_into_worker_context(self):
        """The founder's test 13, and the one a naive join would fail."""
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        self.said(mid, "What's the status?", False)
        self.said(mid, "Focus only on 2026.", True)
        app.forward_to_worker(mid)
        body = self.bodies()[0]
        self.assertEqual(body, "Use official sources only.\n"
                               "Focus only on 2026.")
        self.assertNotIn("status", body)

    def test_mixed_traffic_delivers_only_the_relevant_ones_in_order(self):
        mid = self.running()
        for text, worker in (("How many turns have we used?", False),
                             ("Name the file foo.txt instead.", True),
                             ("Why are you asking me this?", False),
                             ("Focus only on 2026.", True)):
            self.said(mid, text, worker)
        app.forward_to_worker(mid)
        self.assertEqual(self.bodies(),
                         ["Name the file foo.txt instead.\n"
                          "Focus only on 2026."])

    def test_ordering_holds_under_rapid_interleaved_submission(self):
        """Strict FIFO with the queue drained between arrivals, which is the
        concurrent case: each line dispatches before the next one lands."""
        mid = self.running()
        want = []
        for n in range(12):
            worker = n % 3 != 0
            text = "line %d" % n
            self.said(mid, text, worker)
            app.forward_to_worker(mid)
            if worker:
                want.append(text)
        got = [b for b in self.bodies()]
        self.assertEqual("\n".join(got).split("\n"), want)


# ------------------------------------------------------- 3. delivery ------
class TestDelivery(Base):
    def test_a_status_question_never_reaches_the_worker(self):
        mid = self.running()
        self.said(mid, "What's the status?", False)
        self.assertIsNone(app.forward_to_worker(mid))
        self.assertEqual(len(self.rt.turn_queue), 0)
        self.assertEqual(self.fwd(mid), [shadow_forward.FWD_SKIP])
        self.assertEqual(self.rt.queue_event.set_count, 0,
                         "a Shadow-only line must not even wake the pump")

    def test_a_worker_line_is_on_the_queue_before_the_call_returns(self):
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        self.assertEqual(len(self.rt.turn_queue), 0, "not yet dispatched")
        self.assertEqual(app.forward_to_worker(mid), [0])
        self.assertEqual(len(self.rt.turn_queue), 1)
        self.assertEqual(self.rt.queue_event.set_count, 1)

    def test_it_lands_on_the_shadow_lane_not_the_operator_lane(self):
        """The founder's constraint AND the boundary-waiter hazard."""
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        app.forward_to_worker(mid)
        self.assertEqual(len(self.rt.turn_queue._operator), 0)
        self.assertEqual(len(self.rt.turn_queue._shadow), 1)

    def test_a_queued_say_is_not_overtaken_by_a_later_founder_line(self):
        """FIFO against Shadow's own traffic, which the operator lane breaks."""
        mid = self.running()
        self.rt.turn_queue.put({"message": "SAY FIRST"}, source="shadow")
        self.said(mid, "Use official sources only.", True)
        app.forward_to_worker(mid)
        self.assertEqual(self.rt.turn_queue.get()["message"], "SAY FIRST")

    def test_the_worker_gets_the_founders_words_verbatim(self):
        mid = self.running()
        self.said(mid, "Actually make it 20 lines instead of 10.", True)
        app.forward_to_worker(mid)
        msg = self.rt.drain()[0]["message"]
        self.assertIn("Actually make it 20 lines instead of 10.", msg)
        self.assertIn(shadow_forward.FORWARD_PREAMBLE, msg)

    def test_nothing_is_delivered_unless_the_mission_is_running(self):
        for state in ("draft", "brief_confirm", "paused", "stopped", "done"):
            with self.subTest(state=state):
                mid = self.running()
                m = self.store.load(mid)
                m["state"] = state
                self.store.save(m)
                self.said(mid, "Use official sources only.", True)
                self.assertIsNone(app.forward_to_worker(mid))
                self.assertEqual(len(self.rt.turn_queue), 0)

    def test_a_watch_mission_still_never_speaks(self):
        mid = self.running()
        m = self.store.load(mid)
        m["invariants"] = ["never_say"]
        self.store.save(m)
        self.said(mid, "Use official sources only.", True)
        self.assertIsNone(app.forward_to_worker(mid))
        self.assertEqual(len(self.rt.turn_queue), 0)

    def test_a_line_never_leaks_into_another_mission(self):
        a, b = self.running(), self.running()
        self.said(a, "Only mission A hears this.", True)
        app.forward_to_worker(b)
        self.assertEqual(len(self.rt.turn_queue), 0)
        app.forward_to_worker(a)
        self.assertIn("Only mission A hears this.", self.bodies()[0])


# ------------------------------------- 4. lifecycle, retry, recovery ------
class TestLifecycleAndRecovery(Base):
    def test_the_lifecycle_runs_queued_dispatched_consumed(self):
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        self.assertEqual(self.fwd(mid), [shadow_forward.FWD_QUEUED])
        app.forward_to_worker(mid)
        self.assertEqual(self.fwd(mid), [shadow_forward.FWD_DISPATCHED])
        shadow_runner._forward_consumed(self.rt.drain()[0])
        self.assertEqual(self.fwd(mid), [shadow_forward.FWD_CONSUMED])

    def test_a_retry_of_the_same_forward_delivers_once(self):
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        app.forward_to_worker(mid)
        for _ in range(4):
            self.assertIsNone(app.forward_to_worker(mid))
        self.assertEqual(len(self.rt.turn_queue), 1)

    def test_a_consumed_line_is_never_sent_again(self):
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        app.forward_to_worker(mid)
        shadow_runner._forward_consumed(self.rt.drain()[0])
        app.forward_to_worker(mid)
        self.assertEqual(len(self.rt.turn_queue), 0)

    def test_a_dispatched_line_survives_a_restart_and_is_redelivered(self):
        """The queue was in memory; the process died before the pump ran.

        Through flush_forwards, which is the production restart path -- _launch
        calls it on every start, resume and re-adoption. An ORDINARY call must
        NOT re-offer a dispatched row (it would coalesce into the next payload
        under a new dedupe key and deliver twice), so the restart case has to
        come through the restart door. That asymmetry is the feature.
        """
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        app.forward_to_worker(mid)
        self.assertEqual(self.fwd(mid), [shadow_forward.FWD_DISPATCHED])
        self.rt = FakeRuntime()         # the restart: a brand-new queue
        shadow_runner.flush_forwards(mid)
        self.assertIn("Use official sources only.", self.bodies()[0])

    def test_an_ordinary_call_never_re_sends_a_dispatched_line(self):
        """The duplicate this lane must not produce: a row still sitting on a
        live queue must not ride along inside the NEXT coalesced payload."""
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        app.forward_to_worker(mid)
        self.said(mid, "Focus only on 2026.", True)
        app.forward_to_worker(mid)
        self.assertEqual(self.bodies(),
                         ["Use official sources only.", "Focus only on 2026."])

    def test_a_consumed_line_does_not_come_back_after_a_restart(self):
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        app.forward_to_worker(mid)
        shadow_runner._forward_consumed(self.rt.drain()[0])
        self.rt = FakeRuntime()
        shadow_runner.flush_forwards(mid)
        self.assertEqual(len(self.rt.turn_queue), 0)

    def test_a_dead_worker_loses_nothing(self):
        """No live runtime: the line stays pending and is delivered later."""
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        app.lookup_runtime = lambda sid: None
        self.assertIsNone(app.forward_to_worker(mid))
        self.assertEqual(self.fwd(mid), [shadow_forward.FWD_QUEUED])
        app.lookup_runtime = lambda sid: self.rt
        app.forward_to_worker(mid)
        self.assertIn("Use official sources only.", self.bodies()[0])

    def test_the_launch_flush_is_bound_and_redelivers(self):
        """shadow_runner._launch calls this on every start/resume/re-adopt."""
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        self.assertIsNotNone(shadow_runner.FORWARD_FLUSH["fn"])
        shadow_runner.flush_forwards(mid)
        self.assertIn("Use official sources only.", self.bodies()[0])

    def test_consuming_a_frame_that_carries_no_rows_is_a_no_op(self):
        shadow_runner._forward_consumed({"message": "an ordinary say"})
        shadow_runner._forward_consumed(None)


# --------------------------------------- 5. the architecture it must not --
#                                            disturb
class TestExistingArchitectureIntact(Base):
    def test_a_forward_is_excluded_from_the_evidence_a_check_reads(self):
        """THE LEAK THIS TAG EXISTS TO CLOSE. Untagged, a founder asking for
        a thing would satisfy a contains_artifact check on that thing."""
        mid = self.running()
        self.said(mid, "Include the VR46 team status.", True)
        app.forward_to_worker(mid)
        msg = self.rt.drain()[0]["message"]
        self.assertTrue(shadow_egress.is_shadow_authored(msg))
        self.assertTrue(msg.startswith(shadow_egress.SAY_TAG_MARK))

    def test_a_forward_is_distinguishable_from_a_say(self):
        """Both are excluded from evidence; the worker must still tell them
        apart, because one carries Shadow's authority and one does not."""
        mid = self.running()
        self.assertNotEqual(shadow_egress.founder_tag(mid),
                            shadow_egress.say_tag(mid))
        self.assertIn("founder", shadow_egress.founder_tag(mid))

    def test_the_worker_is_told_it_is_information_not_a_new_task(self):
        mid = self.running()
        self.said(mid, "Focus only on 2026.", True)
        app.forward_to_worker(mid)
        msg = self.rt.drain()[0]["message"]
        self.assertIn("NOT a new task", msg)
        self.assertIn("verbatim", msg)

    def test_every_line_still_reaches_the_decider_forwarded_or_not(self):
        """The invariant test_shadow_v4_unified_input pinned: `seen` is the
        decider's cursor and this lane does not touch it."""
        mid = self.running()
        self.said(mid, "What's the status?", False)
        self.said(mid, "Focus only on 2026.", True)
        app.forward_to_worker(mid)
        rows = self.rows(mid)
        self.assertEqual([r["seen"] for r in rows], [False, False])
        self.assertEqual([r["text"] for r in rows],
                         ["What's the status?", "Focus only on 2026."])

    def test_forwarding_composes_no_instruction_and_spends_no_turn(self):
        mid = self.running()
        before = self.store.load(mid)
        self.said(mid, "Focus only on 2026.", True)
        app.forward_to_worker(mid)
        after = self.store.load(mid)
        self.assertEqual(after["turns_used"], before["turns_used"])
        self.assertEqual(after.get("last_instruction"),
                         before.get("last_instruction"))
        self.assertEqual(after.get("standing_instructions"),
                         before.get("standing_instructions"))
        self.assertEqual(after["done_when"], before["done_when"])
        self.assertEqual(after["state"], "running")

    def test_a_row_predating_the_lane_is_never_delivered(self):
        """Backward compatibility: no `fwd` means no verdict was ever taken,
        and a verdict is never guessed at after the fact."""
        mid = self.running()
        m = self.store.load(mid)
        m["founder_says"] = [{"text": "an old line", "seen": False}]
        self.store.save(m)
        self.assertIsNone(app.forward_to_worker(mid))
        self.assertEqual(len(self.rt.turn_queue), 0)

    def test_the_floor_still_applies_and_a_floored_line_does_not_loop(self):
        mid = self.running()
        self.said(mid, "Use official sources only.", True)
        m = self.store.load(mid)
        original = shadow_egress.floor_check
        shadow_egress.floor_check = lambda text: ["a_floor"]
        try:
            self.assertIsNone(app.forward_to_worker(mid))
        finally:
            shadow_egress.floor_check = original
        self.assertEqual(len(self.rt.turn_queue), 0)
        self.assertEqual(self.fwd(mid), [shadow_forward.FWD_SKIP],
                         "a floored line must not be re-floored forever")
        self.assertEqual(self.rows(mid)[0]["seen"], False,
                         "...and Shadow must still see it")
        self.assertEqual(m["id"], mid)


# ------------------------------------------- 6. the acceptance scenario ---
class TestTheAcceptanceScenario(Base):
    """The founder's own run, asserted at the worker-input boundary.

        "Find the latest Valentino Rossi news."   <- the objective
        "Also include VR46 team status."
        "And give me the most recent item first."

    All of it reaches the worker without a single steering turn in between.
    """

    def test_all_three_intents_reach_the_worker_with_no_orchestration_turn(self):
        mid = self.running()
        before = self.store.load(mid)

        self.said(mid, "Also include VR46 team status.", True)
        app.forward_to_worker(mid)
        self.said(mid, "And give me the most recent item first.", True)
        app.forward_to_worker(mid)

        delivered = "\n".join(self.bodies())
        self.assertIn("Also include VR46 team status.", delivered)
        self.assertIn("And give me the most recent item first.", delivered)
        self.assertLess(delivered.index("VR46"),
                        delivered.index("most recent"))

        after = self.store.load(mid)
        self.assertEqual(after["turns_used"], before["turns_used"],
                         "no steering turn was required to deliver any of it")
        self.assertEqual(after["objective"], before["objective"])

    def test_the_same_three_coalesce_when_they_arrive_together(self):
        mid = self.running()
        self.said(mid, "Also include VR46 team status.", True)
        self.said(mid, "And give me the most recent item first.", True)
        app.forward_to_worker(mid)
        self.assertEqual(self.bodies(),
                         ["Also include VR46 team status.\n"
                          "And give me the most recent item first."])


if __name__ == "__main__":
    unittest.main()
