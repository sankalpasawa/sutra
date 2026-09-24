"""test_shadow_ask_has_result.py -- A DECISION POINT CARRIES WHAT IT IS ABOUT
(founder, 2026-09-23).

THE GAP. Shadow asked "should I save this as a file?" about a three-day
Australia plan that existed only in the worker's chat. The question was on
one surface and the material on another, so the founder had to open the
worker chat to answer a question Shadow had put to them -- the one thing
Shadow exists to make unnecessary.

WHAT IS PINNED. When the decider attaches evidence, its judgement stands
untouched: it chose what mattered and how much. When an ask arrives with
NOTHING attached, the bounded artifact preview the engine already computes
for completions is attached instead -- the same reader, the same ownership
rule, the same caps. Never the transcript.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_ask_has_result.py
"""
import os
import tempfile
import unittest

os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="shadow-ask-result-"))

import mission_engine                          # noqa: E402


ASK = {"id": "iv-1", "schema_version": 1,
       "question": "Should I save this as a file?",
       "context": "", "evidence": [],
       "fields": [{"key": "save", "type": "boolean", "label": "Save it",
                   "required": True, "options": [], "constraints": {}}],
       "submit_label": "Send to Shadow", "expires_at": None}

PLAN = ("Day 1 Sydney: harbour walk, Opera House tour\n"
        "Day 2 Blue Mountains: Three Sisters, Scenic World\n"
        "Day 3 Bondi: coastal walk, flight home")


class TheAskCarriesTheResult(unittest.TestCase):
    """_ask_with_result is the whole change; it is exercised directly, with
    the reader stubbed, so the lane tests the rule and not the filesystem."""

    def setUp(self):
        self.real = mission_engine.shadow_decision.preview_for
        self.calls = []

        def fake(mission, root):
            self.calls.append((mission.get("id"), root))
            return {"text": PLAN, "ref": "australia-3-day.md",
                    "truncated": False}
        mission_engine.shadow_decision.preview_for = fake

    def tearDown(self):
        mission_engine.shadow_decision.preview_for = self.real

    def _ask(self, iv, mission=None):
        return mission_engine._ask_with_result(
            iv, mission or {"id": "m-1"}, "/tmp/root")

    def test_an_ask_with_nothing_attached_gets_the_result(self):
        out = self._ask(dict(ASK))
        self.assertEqual(len(out["evidence"]), 1)
        self.assertIn("Day 1 Sydney", out["evidence"][0]["text"],
                      "the founder can read what they are deciding about")
        self.assertEqual(out["evidence"][0]["ref"], "australia-3-day.md",
                         "and where it came from")

    def test_the_question_is_untouched(self):
        out = self._ask(dict(ASK))
        self.assertEqual(out["question"], "Should I save this as a file?")
        self.assertEqual(out["fields"], ASK["fields"])
        self.assertEqual(out["id"], ASK["id"])

    def test_shadows_own_evidence_is_never_overridden(self):
        """The decider chose what mattered. That judgement stands."""
        mine = dict(ASK)
        mine["evidence"] = [{"kind": "output", "ref": "chosen.md",
                             "text": "just the two lines that matter"}]
        out = self._ask(mine)
        self.assertEqual(out["evidence"], mine["evidence"])
        self.assertEqual(self.calls, [], "the fallback did not even run")

    def test_nothing_produced_means_nothing_attached(self):
        mission_engine.shadow_decision.preview_for = lambda m, r: None
        out = self._ask(dict(ASK))
        self.assertEqual(out["evidence"], [],
                         "an ask about no artifact invents none")

    def test_a_reader_that_raises_leaves_the_ask_alone(self):
        def boom(m, r):
            raise RuntimeError("disk gone")
        mission_engine.shadow_decision.preview_for = boom
        out = self._ask(dict(ASK))
        self.assertEqual(out["question"], ASK["question"],
                         "a question the founder can see beats no question")

    def test_it_reads_the_mission_it_was_given(self):
        self._ask(dict(ASK), {"id": "m-77"})
        self.assertEqual(self.calls, [("m-77", "/tmp/root")],
                         "never another mission's artifact")

    def test_a_non_dict_ask_is_returned_untouched(self):
        self.assertIsNone(self._ask(None))


class WhenThereIsNoFileToRead(unittest.TestCase):
    """THE READ-ONLY WORKER (founder, 2026-09-23, mission m-8365d184b054).
    preview_for reads artifacts off disk; a worker with read permission only
    produces the plan in its REPLY and has nothing to save. Shadow saw that
    and said so -- "The 3-day plan exists only in the worker's reply" -- and
    then asked the founder to approve a plan they could not see."""

    def setUp(self):
        self.real = mission_engine.shadow_decision.preview_for
        mission_engine.shadow_decision.preview_for = lambda m, r: None

    def tearDown(self):
        mission_engine.shadow_decision.preview_for = self.real

    def _ask(self, reply):
        return mission_engine._ask_with_result(
            dict(ASK), {"id": "m-1"}, "/tmp/root", reply)

    def test_the_workers_reply_is_attached(self):
        out = self._ask(PLAN)
        self.assertEqual(len(out["evidence"]), 1)
        self.assertIn("Day 1 Sydney", out["evidence"][0]["text"])

    def test_it_names_no_file_because_there_is_none(self):
        self.assertEqual(self._ask(PLAN)["evidence"][0]["ref"], "",
                         "an excerpt is not a file and must not claim to be")

    def test_no_artifact_and_no_reply_invents_nothing(self):
        for empty in (None, "", "   "):
            self.assertEqual(self._ask(empty)["evidence"], [],
                             "nothing produced, nothing attached: %r" % empty)

    def test_the_excerpt_holds_the_bound_result_excerpt_has_always_held(self):
        long = "HEAD" + ("x" * 5000) + "TAIL"
        got = self._ask(long)["evidence"][0]["text"]
        self.assertEqual(got, mission_engine._excerpt(long),
                         "the same rule, not a second one")
        self.assertLess(len(got), 420, "and it is bounded")
        self.assertTrue(got.startswith("HEAD"), "head kept")
        self.assertTrue(got.endswith("TAIL"), "tail kept")
        self.assertIn(" ... ", got, "and the cut is visible")

    def test_an_artifact_still_wins_over_the_reply(self):
        mission_engine.shadow_decision.preview_for = (
            lambda m, r: {"text": "FROM THE FILE", "ref": "plan.md"})
        out = self._ask("from the reply")
        self.assertIn("FROM THE FILE", out["evidence"][0]["text"])
        self.assertEqual(out["evidence"][0]["ref"], "plan.md")

    def test_shadows_own_evidence_still_wins_over_both(self):
        mine = dict(ASK)
        mine["evidence"] = [{"kind": "output", "ref": "", "text": "CHOSEN"}]
        out = mission_engine._ask_with_result(
            mine, {"id": "m-1"}, "/tmp/root", "from the reply")
        self.assertEqual(out["evidence"], mine["evidence"])


class ItIsNotATranscriptDump(unittest.TestCase):
    """The reader is the completion's own, which is bounded and grounded --
    asserted here so a future change to it cannot quietly widen this."""

    def test_the_reader_is_the_bounded_artifact_preview(self):
        import shadow_decision
        self.assertTrue(callable(shadow_decision.preview_for))
        self.assertLessEqual(shadow_decision.PREVIEW_LINES, 40,
                             "a preview is a preview")
        self.assertLessEqual(shadow_decision.PREVIEW_CHARS, 4000)

    def test_it_reports_its_own_truncation(self):
        """`truncated` is what lets a surface say so, rather than showing a
        partial plan as though it were whole."""
        import inspect
        import shadow_decision
        self.assertIn("truncated", inspect.getsource(shadow_decision.preview_for))


class TheForwardingMechanismIsUNTOUCHED(unittest.TestCase):
    """POINTS 9 AND 10, pinned here so this change cannot quietly disturb
    the path it was explicitly told not to touch.

    THESE ARE SHADOW'S OWN VERDICTS, not a second classifier. `classify`
    reads the `forward` fence Shadow emits on the turn it was taking
    anyway; `_is_meta_only` is only the floor for a dropped fence. Both are
    asserted exactly as they behave today -- the founder's own live data
    showed 'What are you doing?' skipped and 'Actually, I made a mistake.
    Make this a 3-day trip.' consumed, and nothing here changes that.
    """

    def setUp(self):
        import shadow_forward
        self.fwd = shadow_forward

    def test_9_a_casual_message_is_not_forwarded(self):
        """Shadow said no; that verdict stands."""
        self.assertFalse(
            self.fwd.classify("What are you doing?", {"forward": False}),
            "a message Shadow classed as Shadow-only must not reach the worker")

    def test_9b_and_the_floor_agrees_when_the_fence_is_missing(self):
        for meta in ("What are you doing?",
                     "What's the status?",
                     "Did you give the instruction to the worker chat already?"):
            self.assertTrue(self.fwd._is_meta_only(meta), meta)

    def test_10_a_worker_affecting_correction_is_forwarded(self):
        self.assertTrue(
            self.fwd.classify("Actually, make this a 3-day trip.",
                              {"forward": True}),
            "Shadow said it affects the work; it must reach the worker")

    def test_10b_and_the_floor_forwards_when_it_cannot_tell(self):
        """The founder's rule for the ambiguous case: forward rather than
        silently drop."""
        for real in ("Actually, make this a 3-day trip.",
                     "I meant a 5-day trip.",
                     "Let's roam North India also."):
            self.assertFalse(self.fwd._is_meta_only(real), real)

    def test_this_change_touched_none_of_it(self):
        """_ask_with_result is presentation. It must not import, call or
        otherwise reach the forwarding lane."""
        import inspect
        src = inspect.getsource(mission_engine._ask_with_result)
        for banned in ("forward", "classify", "turn_queue", "enqueue",
                       "_is_meta_only"):
            self.assertNotIn(banned, src,
                             "the ask path must not touch %r" % banned)


if __name__ == "__main__":
    unittest.main()
