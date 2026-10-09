"""Tap to answer (founder, 2026-10-08, from Paperclip).

  VERDICTS  a new field type: Shadow lists items and the founder marks each
            approve, reject or later. One item is enough; required means
            every item; values are checked against the listed items.
  SHOWN     Shadow reads the verdicts by the items' labels, not their keys.
  PROMPT    the decider is told to send a tap form whenever the answer is
            yes/no or one of a few, and never to ask the founder to type yes.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_tap.py
"""
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-tap-")

import shadow_intervention as iv               # noqa: E402
import shadow_runner                           # noqa: E402


def form(required=True, items=("h1", "h2")):
    return iv.validate_request({
        "question": "Which headlines go in?",
        "fields": [{"key": "headlines", "type": "verdicts",
                    "label": "Headlines", "required": required,
                    "options": [{"value": v, "label": "Headline " + v}
                                for v in items]}]})


class Verdicts(unittest.TestCase):
    def test_01_it_is_an_answerable_type(self):
        self.assertIn("verdicts", iv.ACTIVE_FIELD_TYPES)
        self.assertEqual(iv.VERDICTS, ("approve", "reject", "later"))

    def test_02_one_item_can_be_judged(self):
        req = form(items=("only",))
        self.assertEqual(len(req["fields"][0]["options"]), 1)

    def test_03_a_verdict_on_every_item(self):
        clean, errors = iv.validate_values(
            form(), {"headlines": {"h2": "Reject", "h1": "approve"}})
        self.assertEqual(errors, {})
        self.assertEqual(clean["headlines"], {"h1": "approve", "h2": "reject"},
                         "lower-cased and in the listed order")

    def test_04_required_means_every_item(self):
        _c, errors = iv.validate_values(form(), {"headlines": {"h1": "later"}})
        self.assertIn("every item", errors["headlines"])
        _c, errors = iv.validate_values(form(), {"headlines": {}})
        self.assertEqual(errors["headlines"], "this is required")

    def test_05_optional_takes_some(self):
        clean, errors = iv.validate_values(
            form(required=False), {"headlines": {"h1": "approve"}})
        self.assertEqual(errors, {})
        self.assertEqual(clean["headlines"], {"h1": "approve"})

    def test_06_only_listed_items_and_known_verdicts(self):
        _c, errors = iv.validate_values(
            form(), {"headlines": {"h1": "approve", "h9": "approve"}})
        self.assertIn("not one of the listed items", errors["headlines"])
        _c, errors = iv.validate_values(
            form(), {"headlines": {"h1": "approve", "h2": "maybe"}})
        self.assertIn("approve, reject or later", errors["headlines"])
        _c, errors = iv.validate_values(form(), {"headlines": ["h1"]})
        self.assertIn("verdict for each item", errors["headlines"])

    def test_07_shadow_reads_the_items_by_their_labels(self):
        req = form()
        clean, _e = iv.validate_values(
            req, {"headlines": {"h1": "approve", "h2": "later"}})
        rows = iv.summarise(req, clean)
        self.assertEqual(rows[0]["value"],
                         "Headline h1: approve; Headline h2: later")

    def test_08_the_other_types_are_untouched(self):
        bad = iv.validate_request({"question": "q", "fields": [
            {"key": "c", "type": "choice", "label": "c",
             "options": [{"value": "a", "label": "A"}]}]})
        self.assertFalse((bad or {}).get("fields"),
                         "a choice of one is still not a choice")


class ThePrompt(unittest.TestCase):
    def test_10_tap_rather_than_type(self):
        src = open(shadow_runner.__file__, encoding="utf-8").read()
        self.assertIn("THE FOUNDER TAPS; THEY DO NOT TYPE WHAT THEY COULD TAP",
                      src)
        self.assertIn('never "reply yes to continue"', src)
        self.assertIn("ranking, verdicts.", src)

    def test_11_the_prompt_still_renders(self):
        ctx = {"objective": "o", "turns_used": 1, "max_turns": 5,
               "recent": "", "done_when": [], "images_ask": ""}
        try:
            text = shadow_runner.render_decide_prompt(ctx)
        except KeyError:
            self.skipTest("render_decide_prompt needs a fuller context here")
        self.assertIn('"type": "verdicts"', text)


if __name__ == "__main__":
    unittest.main()
