"""test_budget.py -- the per-model context ceiling
(GAME-PLAN-provider-switch piece 5).

The Haiku case is the one this module exists for: the panel offers haiku in its
model picker and its window is a fifth of its siblings', so a provider-keyed
budget would be five times too generous and the failure would land at the API
after the payload had been built and sent.
"""
import unittest

import budget
import providers


class WindowTest(unittest.TestCase):

    def test_haiku_is_not_given_its_siblings_window(self):
        """THE trap this module exists for."""
        self.assertEqual(budget.window_for("claude", "haiku")["tokens"], 200000)
        self.assertEqual(budget.window_for("claude", "opus")["tokens"], 1000000)
        self.assertEqual(budget.window_for("claude", "sonnet")["tokens"], 1000000)

    def test_haiku_budget_is_five_times_smaller(self):
        big = budget.for_target("claude", "opus")["budget_chars"]
        small = budget.for_target("claude", "haiku")["budget_chars"]
        self.assertGreater(big, small * 4,
                           "a provider-keyed budget would miss this entirely")

    def test_deepseek_window_is_declared_not_assumed(self):
        """Verified by a live GET /models on 2026-09-02: every current V4
        model reports 1M."""
        w = budget.window_for("deepseek")
        self.assertEqual(w["tokens"], 1000000)
        self.assertEqual(w["source"], "declared")

    def test_claude_model_id_is_ignored_for_deepseek(self):
        """Sutra's picker sets a CLAUDE model; it must not pick DeepSeek's
        window."""
        self.assertEqual(budget.window_for("deepseek", "haiku")["tokens"], 1000000)

    def test_cli_default_falls_to_the_floor_and_says_so(self):
        """providers.MODELS ships "" as a real option and nothing here can tell
        which model it resolves to."""
        w = budget.window_for("claude", "")
        self.assertEqual(w["tokens"], budget.FLOOR_WINDOW)
        self.assertEqual(w["source"], "assumed-floor")
        note = budget.for_target("claude", "")["note"]
        self.assertIn("no model is selected", note)
        self.assertIn("Settings", note, "the note must say how to fix it")

    def test_unknown_model_id_falls_to_the_floor(self):
        w = budget.window_for("claude", "some-future-model")
        self.assertEqual(w["source"], "assumed-floor")

    def test_unknown_target_falls_to_the_floor(self):
        self.assertEqual(budget.window_for("gemini")["source"], "assumed-floor")

    def test_floor_is_the_smallest_declared_window(self):
        self.assertEqual(budget.FLOOR_WINDOW, min(budget.CLAUDE_WINDOWS.values()))

    def test_every_catalogued_model_has_a_window_or_is_the_default(self):
        """Pins the window table to the picker, so a new model entry cannot
        silently inherit a wrong ceiling."""
        for m in providers.MODELS:
            mid = m["id"]
            if mid == "":
                continue   # "CLI default" is the documented floor case
            self.assertIn(mid, budget.CLAUDE_WINDOWS,
                          "model %r is in the picker but has no declared "
                          "context window" % mid)


class ArithmeticTest(unittest.TestCase):

    def test_reply_room_is_reserved(self):
        b = budget.for_target("claude", "opus")
        self.assertLess(b["usable_tokens"],
                        b["window_tokens"] - budget.REPLY_RESERVE_TOKENS + 1)
        self.assertEqual(b["reply_reserve_tokens"], budget.REPLY_RESERVE_TOKENS)

    def test_token_estimate_is_conservative_not_the_prose_figure(self):
        """The payload is ~80% tool I/O; code and JSON tokenize denser than
        prose, so 4 chars/token would understate and understating overruns."""
        self.assertLess(budget.CHARS_PER_TOKEN, 4.0)
        self.assertEqual(budget.estimate_tokens(3000), 1000)

    def test_token_estimate_rounds_up(self):
        """Rounding down can pass a payload that does not fit."""
        self.assertEqual(budget.estimate_tokens(1), 1)
        self.assertEqual(budget.estimate_tokens(4), 2)
        self.assertEqual(budget.estimate_tokens(0), 0)
        self.assertEqual(budget.estimate_tokens(-5), 0)

    def test_budget_is_labelled_an_estimate(self):
        self.assertTrue(budget.for_target("claude", "opus")["estimate"],
                        "no tokenizer is in the loop; the result must say so")

    def test_usable_is_discounted_below_the_reserve_math(self):
        b = budget.for_target("claude", "opus")
        raw = b["window_tokens"] - b["reply_reserve_tokens"]
        self.assertLess(b["usable_tokens"], raw,
                        "an estimated token count needs margin of its own")

    def test_fits_reports_headroom_both_ways(self):
        b = budget.for_target("claude", "opus")
        ok = budget.fits(1000, b)
        self.assertTrue(ok["fits"])
        self.assertGreater(ok["headroom_chars"], 0)
        over = budget.fits(b["budget_chars"] + 1, b)
        self.assertFalse(over["fits"])
        self.assertEqual(over["headroom_chars"], -1)

    def test_fits_can_derive_its_own_budget(self):
        r = budget.fits(1000, target="claude", model="haiku")
        self.assertTrue(r["fits"])
        self.assertEqual(r["window_tokens"], 200000)


class RealPayloadTest(unittest.TestCase):
    """The founder's 50-turn scenario against each window."""

    #: 50 turns x 21,871 median chars per user turn (transcript_ir.stats over
    #: 24 real transcripts).
    FIFTY_TURN_CHARS = 50 * 21871

    def test_fifty_turns_fits_a_1m_window_at_tier_one(self):
        for model in ("opus", "sonnet"):
            r = budget.fits(self.FIFTY_TURN_CHARS, target="claude", model=model)
            self.assertTrue(r["fits"], "%s should hold a 50-turn replay" % model)

    def test_fifty_turns_does_not_fit_haiku(self):
        r = budget.fits(self.FIFTY_TURN_CHARS, target="claude", model="haiku")
        self.assertFalse(r["fits"],
                         "200K cannot hold a 50-turn full-fidelity replay; "
                         "tier 2 must engage")

    def test_fifty_turns_fits_deepseek(self):
        r = budget.fits(self.FIFTY_TURN_CHARS, target="deepseek")
        self.assertTrue(r["fits"])

    def test_conversation_only_fits_even_haiku(self):
        """Tier 2 is what makes the small window usable: conversation is 20.2%
        of a Claude transcript."""
        r = budget.fits(int(self.FIFTY_TURN_CHARS * 0.202),
                        target="claude", model="haiku")
        self.assertTrue(r["fits"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
