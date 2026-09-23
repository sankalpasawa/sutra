"""test_shadow_ask_evidence.py -- IF SHADOW ASKS YOU TO JUDGE SOMETHING, IT
SHOWS YOU THE SOMETHING (founder, 2026-09-23).

THE GAP. Shadow asked the founder "are these the ten you wanted?" and the
ten were nowhere on the surface the founder was reading. The intervention
schema in the decide prompt documented `question`, `context`, `fields` and
`confirms_check` -- never `evidence` -- so Shadow did not know the key
existed, even though shadow_intervention has always validated it and the
pane has always rendered it. The founder was being asked to sign off work
they could not see.

WHAT IS PINNED HERE is the relationship, not an amount:

    generated output -> surfaced context -> the question

How MUCH is Shadow's judgement about the question it is asking, which is
why nothing below asserts a length, a line count, or that any particular
kind of output is always shown. What is asserted is that the material
SURVIVES the path from Shadow's answer to the founder's screen, and that
an ask needing no evidence is unchanged.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_ask_evidence.py
"""
import os
import tempfile
import unittest

os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="shadow-ask-evidence-"))

import shadow_intervention                   # noqa: E402
import shadow_runner                         # noqa: E402


class ShadowIsToldTheKeyExists(unittest.TestCase):
    """Asserted on the RENDERED prompt: a key documented nowhere is a key
    Shadow never emits, which is the whole of the original bug."""

    def setUp(self):
        self.prompt = shadow_runner._DECIDE_PROMPT

    def test_the_intervention_schema_names_evidence(self):
        self.assertIn("evidence", self.prompt)

    def test_it_says_to_show_what_is_being_judged(self):
        self.assertIn("IF YOU ARE ASKING THEM TO JUDGE SOMETHING, SHOW IT "
                      "TO THEM", self.prompt)

    def test_how_much_is_left_to_shadow(self):
        """The founder's rule: no universal 'always show everything'."""
        self.assertIn("HOW MUCH IS YOUR CALL", self.prompt)
        self.assertIn("Never paste a whole artifact to be safe", self.prompt)

    def test_it_is_optional(self):
        self.assertIn("`evidence` is\nOPTIONAL", self.prompt)

    def test_the_limits_it_states_are_the_ones_enforced(self):
        """A prompt that promises more than the validator keeps would have
        Shadow writing evidence that is silently cut."""
        self.assertIn("Up to %d pieces, %d characters each"
                      % (shadow_intervention.EVIDENCE_MAX,
                         shadow_intervention.EVIDENCE_TEXT_MAX),
                      self.prompt)


class TheMaterialSurvivesTheValidator(unittest.TestCase):

    def _ask(self, **extra):
        raw = {"question": "Are these the ten stories you wanted?",
               "fields": [{"key": "list_ok", "type": "boolean",
                           "label": "These are the ten I wanted."}]}
        raw.update(extra)
        return shadow_intervention.validate_request(raw)

    def test_the_lines_reach_the_founder_verbatim(self):
        lines = "1. First story\n2. Second story\n3. Third story"
        iv = self._ask(evidence=[{"kind": "output", "ref": "news.md",
                                  "text": lines}])
        self.assertEqual(len(iv["evidence"]), 1)
        self.assertEqual(iv["evidence"][0]["text"], lines,
                         "not summarised, not reformatted")
        self.assertEqual(iv["evidence"][0]["ref"], "news.md",
                         "and it says where it came from")

    def test_a_bare_string_is_accepted_as_a_note(self):
        iv = self._ask(evidence=["1. First\n2. Second"])
        self.assertEqual(iv["evidence"][0]["kind"], "note")
        self.assertTrue(iv["evidence"][0]["text"])

    def test_an_ask_that_needs_none_is_unchanged(self):
        iv = self._ask()
        self.assertEqual(iv["evidence"], [],
                         "no evidence is a legal ask, not a broken one")
        self.assertTrue(iv["question"])
        self.assertEqual(len(iv["fields"]), 1)

    def test_the_caps_hold(self):
        many = [{"kind": "output", "text": "x" * 5000}
                for _ in range(shadow_intervention.EVIDENCE_MAX + 6)]
        iv = self._ask(evidence=many)
        self.assertLessEqual(len(iv["evidence"]),
                             shadow_intervention.EVIDENCE_MAX)
        for e in iv["evidence"]:
            self.assertLessEqual(len(e["text"]),
                                 shadow_intervention.EVIDENCE_TEXT_MAX)

    def test_empty_pieces_are_dropped_not_drawn_blank(self):
        iv = self._ask(evidence=[{"kind": "output", "text": "", "ref": ""},
                                 {"kind": "output", "text": "real"}])
        self.assertEqual([e["text"] for e in iv["evidence"]], ["real"])

    def test_evidence_alone_does_not_make_an_intervention(self):
        """The form is still what makes it answerable -- evidence is
        context for a question, never a question."""
        self.assertIsNone(shadow_intervention.validate_request(
            {"question": "look at this", "evidence": ["some output"]}))

    def test_it_rides_with_a_check_sign_off(self):
        """The case that prompted this: a founder_confirm sign-off on
        output the founder has to be able to read."""
        iv = self._ask(evidence=[{"kind": "output", "text": "1.\n2.\n3."}],
                       confirms_check={"index": 0, "field": "list_ok"})
        self.assertTrue(iv["evidence"])
        self.assertIsNotNone(iv["confirms_check"])


if __name__ == "__main__":
    unittest.main()
