#!/usr/bin/env python3
"""WORKER OUTPUT COMES BACK THROUGH SHADOW (founder, 2026-09-21, pass 9).

THE ARCHITECTURE THE FOUNDER ASKED FOR, in their own words:

    WORKER -> SHADOW INTERPRETS/SUMMARIZES -> FOUNDER

Until now the founder read the WORKER'S OWN SENTENCE, written by the worker
about its own work -- "I'll pull current India cricket news and write it to a
file" -- with its subject shifted deterministically by the UI. That was
correct attribution and it read like a translation, because it was one.

WHERE THE SUMMARY COMES FROM, and this is the whole design constraint: the
decider ALREADY takes a Shadow turn on every worker boundary, already reads
the worker's latest output, and already answers as Shadow. `update` is one
more optional key in that same reply. No second model call, no second
conversation, no parallel system.

WHAT THESE TESTS PIN:

  the key is OPTIONAL and STRICT      an absent, empty, over-long or
                                      machinery-shaped update is not carried,
                                      and the caller behaves exactly as it
                                      did before the key existed
  it rides BOTH decision shapes       a turn that ends in a question is the
                                      turn the founder most needs a sentence
                                      about
  it is APPEND-ONLY and STAMPED       `at_turn` is the turn whose output
                                      Shadow read, so the UI can place it
  it CHANGES NOTHING ELSE             no check, no state, no completion, no
                                      instruction

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_update.py
"""
import unittest

import mission_engine
import shadow_runner


class TheUpdateValidator(unittest.TestCase):
    def test_a_plain_sentence_is_carried(self):
        self.assertEqual(
            mission_engine.validate_update(
                "I've got the 10-day plan. I need your call on the pace."),
            "I've got the 10-day plan. I need your call on the pace.")

    def test_whitespace_is_collapsed_to_one_paragraph(self):
        self.assertEqual(
            mission_engine.validate_update("I've got\n\n  the plan.\t Done."),
            "I've got the plan. Done.")

    def test_absent_and_empty_are_silence(self):
        for raw in (None, "", "   ", 7, [], {}):
            self.assertIsNone(mission_engine.validate_update(raw))

    def test_machinery_is_refused(self):
        """THE FLOOR. These are the shapes that mean the model pasted the
        worker's output instead of reading it."""
        for raw in ('{"results": [{"title": "x"}]}',
                    "```json\n{}\n```",
                    "See https://espncricinfo.com/story/1 for the report",
                    "10 tool calls - Web search 6, fetched 3",
                    "Wrote it {like this}"):
            self.assertIsNone(mission_engine.validate_update(raw), raw)

    def test_an_over_long_update_is_refused(self):
        """A founder-facing line is one short paragraph; anything longer is
        the transcript arriving by another route."""
        self.assertIsNone(mission_engine.validate_update(
            "x" * (mission_engine.SHADOW_UPDATE_MAX + 1)))
        self.assertIsNotNone(mission_engine.validate_update(
            "x" * mission_engine.SHADOW_UPDATE_MAX))


class TheDecisionCarriesIt(unittest.TestCase):
    CONT = {"action": "continue", "instruction": "keep going",
            "reason": "more to do"}
    ASK = {"action": "ask_founder", "reason": "need the pace",
           "ask_kind": "taste"}

    def test_a_continue_carries_it(self):
        d = mission_engine.validate_decision(
            dict(self.CONT, update="I've got the plan."))
        self.assertEqual(d["update"], "I've got the plan.")

    def test_an_ask_founder_carries_it(self):
        d = mission_engine.validate_decision(
            dict(self.ASK, update="I need your call on the pace."))
        self.assertEqual(d["update"], "I need your call on the pace.")

    def test_without_it_the_decision_is_byte_identical(self):
        """ADDITIVE, like `standing` and `intervention` before it."""
        self.assertEqual(mission_engine.validate_decision(self.CONT),
                         mission_engine.validate_decision(
                             dict(self.CONT, update="")))
        self.assertNotIn("update",
                         mission_engine.validate_decision(self.CONT))

    def test_a_malformed_update_does_not_fail_the_decision(self):
        """The instruction is still worth sending; Shadow is asked again
        next turn."""
        d = mission_engine.validate_decision(
            dict(self.CONT, update='{"pasted": "payload"}'))
        self.assertIsNotNone(d)
        self.assertEqual(d["instruction"], "keep going")
        self.assertNotIn("update", d)


class TheRecord(unittest.TestCase):
    def setUp(self):
        self.runner = mission_engine.MissionEngine.__new__(
            mission_engine.MissionEngine)

    def adopt(self, m, update, turn=None):
        if turn is not None:
            m["turns_used"] = turn
        self.runner._adopt_update(m, {"update": update} if update else {})
        return m

    def test_it_is_appended_with_the_turn_it_is_about(self):
        m = {"turns_used": 3}
        self.adopt(m, "I've got the plan.")
        self.assertEqual(m["shadow_updates"][-1]["text"], "I've got the plan.")
        self.assertEqual(m["shadow_updates"][-1]["at_turn"], 3)
        self.assertTrue(m["shadow_updates"][-1]["at"])

    def test_turns_accumulate_in_order(self):
        m = {"turns_used": 1}
        self.adopt(m, "First.")
        self.adopt(m, "Second.", turn=2)
        self.adopt(m, "Third.", turn=3)
        self.assertEqual([r["text"] for r in m["shadow_updates"]],
                         ["First.", "Second.", "Third."])

    def test_one_line_per_turn(self):
        """A decider that answers twice for the same turn replaces its own
        line rather than stacking two."""
        m = {"turns_used": 2}
        self.adopt(m, "First try.")
        self.adopt(m, "Second try.")
        self.assertEqual([r["text"] for r in m["shadow_updates"]],
                         ["Second try."])

    def test_no_update_writes_nothing(self):
        m = {"turns_used": 1}
        self.adopt(m, None)
        self.assertNotIn("shadow_updates", m)

    def test_it_touches_nothing_else(self):
        m = {"turns_used": 1, "state": "running", "done_when": [{"met": False}],
             "last_instruction": "go"}
        before = {k: v for k, v in m.items() if k != "shadow_updates"}
        self.adopt(m, "I've got the plan.")
        after = {k: v for k, v in m.items() if k != "shadow_updates"}
        self.assertEqual(before, after,
                         "an update must change no state, check or instruction")

    def test_the_list_is_bounded(self):
        m = {"turns_used": 0}
        for i in range(mission_engine.MissionEngine.SHADOW_UPDATES_MAX + 20):
            self.adopt(m, "line %d" % i, turn=i)
        self.assertEqual(len(m["shadow_updates"]),
                         mission_engine.MissionEngine.SHADOW_UPDATES_MAX)
        self.assertTrue(m["shadow_updates"][-1]["text"].endswith(
            str(mission_engine.MissionEngine.SHADOW_UPDATES_MAX + 19)))


class ThePromptAsksForIt(unittest.TestCase):
    def setUp(self):
        self.text = shadow_runner.render_decide_prompt(
            {"outcome": "x", "checks": [], "turns_used": 1, "max_turns": 5})

    def test_both_shapes_offer_the_key(self):
        self.assertEqual(self.text.count('"update":'), 2,
                         "continue and ask_founder must both offer it")

    def test_it_says_who_the_reader_is(self):
        self.assertIn("ONLY THING THE FOUNDER READS", self.text)

    def test_it_forbids_pasting_and_claiming(self):
        for rule in ("paste the worker's output",
                     "say a check passed",
                     "invent progress"):
            self.assertIn(rule, self.text)

    def test_silence_is_offered(self):
        self.assertIn("OMIT THE KEY", self.text)


class TheRequestSetsTheLevel(unittest.TestCase):
    """PASS 10 (founder, 2026-09-21). "The worker's output is evidence. The
    artifact is the deliverable." Shadow's message must describe the result
    at the level of the ORIGINAL REQUEST -- not summarise whichever sentence
    happened to come last out of the worker.

    The decide turn is where that judgement is made, so it is the decide
    turn that gains the context and the rules."""

    def prompt(self, **over):
        ctx = {"outcome": "Make a file of 10 lines about alien species",
               "checks": [], "turns_used": 1, "max_turns": 5}
        ctx.update(over)
        return shadow_runner.render_decide_prompt(ctx)

    def test_the_three_request_shapes_are_named(self):
        t = self.prompt()
        self.assertIn("ANSWER THE REQUEST, NOT THE LAST SENTENCE", t)
        for shape in ("they asked for a FILE",
                      "they asked to be TOLD something",
                      "they asked for BOTH"):
            self.assertIn(shape, t)

    def test_it_forbids_pasting_the_file(self):
        """The founder inspects the file in the artifact surface; Shadow's
        message names it. (The rule is wrapped in the prompt, so the match
        is on the words rather than the line.)"""
        flat = " ".join(self.prompt().split())
        self.assertIn("Do not paste the file's contents", flat)
        self.assertIn("they open it in the artifact surface", flat)

    def test_an_in_chat_answer_must_be_in_the_update(self):
        self.assertIn("the answer IS the update", self.prompt())

    def test_the_artifact_floor_is_stated(self):
        """CASE 4: worker prose is not proof that a file exists."""
        t = self.prompt()
        self.assertIn("is NOT proof that\nit exists", t)
        self.assertIn("unless THE FILES\n    block above lists it as present", t)

    def test_a_count_may_not_be_invented(self):
        self.assertIn("state a count the blocks above do not give you",
                      self.prompt())


class TheArtifactStateBlock(unittest.TestCase):
    def test_a_present_file_reports_its_counts(self):
        self.assertEqual(
            shadow_runner._artifact_state_text(
                [{"path": "alien-species.txt", "exists": True, "lines": 10,
                  "distinct_non_empty_lines": 10}]),
            "- alien-species.txt  present (10 lines, "
            "10 distinct non empty lines)")

    def test_an_absent_file_says_so_in_words(self):
        """The line Shadow reads when the worker claims it wrote a file that
        is not there."""
        self.assertEqual(
            shadow_runner._artifact_state_text(
                [{"path": "alien-species.txt", "exists": False}]),
            "- alien-species.txt  NOT PRESENT")

    def test_owning_nothing_is_stated_rather_than_left_blank(self):
        for rows in (None, [], [{}], [{"exists": True}]):
            self.assertEqual(shadow_runner._artifact_state_text(rows),
                             "(none recorded)")

    def test_no_contents_ever_travel(self):
        """Shadow is asked to DESCRIBE the result, not to quote it -- so the
        block carries counts and never text (shadow_decision.state_for)."""
        text = shadow_runner._artifact_state_text(
            [{"path": "a.txt", "exists": True, "lines": 3,
              "text": "line one\nline two\nline three"}])
        self.assertNotIn("line one", text)

    def test_the_block_is_rendered_into_the_prompt(self):
        t = shadow_runner.render_decide_prompt(
            {"outcome": "x", "checks": [], "turns_used": 1, "max_turns": 5,
             "artifact_state": [{"path": "a.txt", "exists": False}]})
        self.assertIn("THE FILES THIS TASK OWNS", t)
        self.assertIn("- a.txt  NOT PRESENT", t)

    def test_a_task_that_owns_nothing_still_renders(self):
        t = shadow_runner.render_decide_prompt(
            {"outcome": "x", "checks": [], "turns_used": 1, "max_turns": 5})
        self.assertIn("(none recorded)", t)


class TheStateReader(unittest.TestCase):
    """shadow_decision.state_for: counts only, ownership only, never raises."""

    def test_a_mission_that_owns_nothing_sees_nothing(self):
        import shadow_decision
        self.assertEqual(shadow_decision.state_for({"id": "m-1"}, "."), [])

    def test_it_never_raises_on_a_junk_record(self):
        import shadow_decision
        for bad in (None, {}, {"id": None}, {"done_when": "not a list"}):
            self.assertEqual(shadow_decision.state_for(bad, "."), [])

    def test_the_engine_wrapper_swallows_everything(self):
        self.assertEqual(mission_engine._artifact_state({"id": "m-1"}, "."), [])
        self.assertEqual(mission_engine._artifact_state(None, None), [])


class TheCapFitsAnInChatAnswer(unittest.TestCase):
    def test_ten_lines_fit(self):
        """CASE 2: "give me 10 lines ..." -- the answer IS the update, so the
        ceiling has to hold one."""
        ten = "\n".join("Line %d: a sourced sentence about the research."
                        % i for i in range(1, 11))
        self.assertIsNotNone(mission_engine.validate_update(ten))

    def test_and_it_is_still_a_ceiling(self):
        self.assertIsNone(mission_engine.validate_update(
            "x" * (mission_engine.SHADOW_UPDATE_MAX + 1)))

    def test_the_shape_rules_still_hold_at_the_larger_size(self):
        """The cap is not the only floor: a long paste is still refused for
        being a paste."""
        self.assertIsNone(mission_engine.validate_update(
            "Here it is: " + '{"results": [1, 2, 3]}' + " x" * 200))


if __name__ == "__main__":
    unittest.main()
