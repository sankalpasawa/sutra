"""A proposed check gets a tier whose SEMANTICS it can actually satisfy.

LIVE FLIGHT, goal g-d804849d1400, 2026-09-11. Shadow proposed, under
`contains_artifact`:

    "An explicit winner named as the final choice -- the word 'Python' or
     'Go' stated as the pick, not a 'depends' or 'both work' hedge"
    "Three distinct concrete reasons listed for that pick, each tied to a
     specific tradeoff (perf, ecosystem, team, deploy, etc.) rather than
     generic praise"

`contains_artifact` is a literal substring test (mission_engine:284). A
criterion DESCRIPTION cannot appear verbatim in a transcript, so both were
structurally unsatisfiable. The chat answered correctly -- "## Winner:
**Python**" with three concrete reasons, and its last turn even says "Both
checks were satisfied" -- and both still evaluated False. The unmet list
never changed, so the follow-up say repeated itself and the ping-pong guard
correctly ended the attempt at 2/20 turns.

The evaluator was right; the input was wrong. These tests pin the boundary
that now refuses to produce that input, and pin that the evaluator itself
did not move.
"""
import json
import unittest

import mission_engine
import shadow_protocol as sp

# the two real ones, verbatim
SEMANTIC_1 = ("An explicit winner named as the final choice — the word "
              "'Python' or 'Go' stated as the pick, not a 'depends' or "
              "'both work' hedge")
SEMANTIC_2 = ("Three distinct concrete reasons listed for that pick, each "
              "tied to a specific tradeoff (perf, ecosystem, team, deploy, "
              "etc.) rather than generic praise")


class TestLiteralShape(unittest.TestCase):
    """What can plausibly appear VERBATIM in a transcript."""

    def test_01_markers_are_literal(self):
        for s in ("Final choice:", "## Winner", "OK", "referral webhook 200",
                  "BUILD GREEN", "exit code 0", "Deployment complete"):
            self.assertTrue(sp.is_literal_artifact(s), s)

    def test_02_criterion_descriptions_are_not(self):
        for s in (SEMANTIC_1, SEMANTIC_2):
            self.assertFalse(sp.is_literal_artifact(s), s[:50])

    def test_03_length_and_word_count_bound_it(self):
        self.assertTrue(sp.is_literal_artifact("a" * 60))
        self.assertFalse(sp.is_literal_artifact("a" * 61), "60 char ceiling")
        self.assertTrue(sp.is_literal_artifact("w " * 7 + "w"))
        self.assertFalse(sp.is_literal_artifact("w " * 8 + "w"), "8 words")

    def test_04_a_dash_or_a_criterion_word_disqualifies(self):
        for s in ("the winner — named outright", "the pick, not a hedge",
                  "three distinct reasons", "must be stated",
                  "at least one reason", "concrete tradeoffs listed"):
            self.assertFalse(sp.is_literal_artifact(s), s)

    def test_05_empty_is_not_an_artifact(self):
        for s in ("", "   ", None):
            self.assertFalse(sp.is_literal_artifact(s))


class TestTierFor(unittest.TestCase):
    """The six cases, one answer each, no silent pass-through."""

    def test_06_literal_contains_artifact_is_unchanged(self):
        self.assertEqual(sp.tier_for("Final choice:", "contains_artifact"),
                         "contains_artifact",
                         "the machine-checkable case must keep working")

    def test_07_semantic_contains_artifact_is_re_tiered(self):
        """UNCHANGED RULE, NEW DESTINATION (D-SH-1, 2026-09-20). A criterion
        DESCRIPTION can never appear verbatim in a transcript, so it is still
        refused `contains_artifact`. Where it lands afterwards is now the
        judge rather than the founder -- neither of these strings is taste."""
        for s in (SEMANTIC_1, SEMANTIC_2):
            self.assertEqual(sp.tier_for(s, "contains_artifact"), "judge")

    def test_08_a_missing_tier_defaults_to_the_JUDGE(self):
        """It defaulted to contains_artifact, then to founder_confirm, and
        now to `judge`. The second default was measured on the founder's live
        install as the reason 9 of 9 checks reached their desk: every one of
        them arrived with no tier at all."""
        for missing in (None, "", "   "):
            self.assertEqual(sp.tier_for("anything at all", missing), "judge")

    def test_09_verify_IS_available_to_a_proposal_when_it_carries_a_probe(self):
        """REVERSED 2026-09-20 (D-SH-1). The note that removed `verify` said
        "no production caller passes a verifier". That stopped being true on
        2026-09-17 when probes shipped -- app.py passes _shadow_verifier at
        four call sites -- and the exclusion stayed behind, demoting the most
        trustworthy tier there is to a signature."""
        self.assertIn("verify", sp.PROPOSAL_TIERS)
        self.assertEqual(
            sp.tier_for("the referral test passes", "verify",
                        {"kind": "command_succeeds", "argv": ["pytest"]}),
            "verify")
        # ...and WITHOUT a probe it is still demoted: a `verify` with nothing
        # behind it would claim Shadow checked something it never looked at.
        self.assertEqual(sp.tier_for("run the referral test", "verify"),
                         "judge")

    def test_10_an_unknown_tier_is_never_silently_accepted(self):
        for junk in ("telepathy", "CONTAINS_ARTIFACT", "contains-artifact",
                     "founderConfirm", 7, {"t": 1}):
            self.assertEqual(sp.tier_for("x", junk), "judge", junk)

    def test_11_founder_confirm_is_kept_only_when_it_IS_the_founders(self):
        """A BARE `founder_confirm` IS NO LONGER ENOUGH (D-SH-1). Honouring
        the label alone would leave the 9-of-9 door open under a new name, so
        a check routed to a signature has to look like a founder's question.
        One that genuinely is and does not look like it still gets there: the
        judge answers `cannot_tell` and it arrives one call later."""
        self.assertEqual(sp.tier_for(SEMANTIC_1, "founder_confirm"), "judge")
        self.assertEqual(sp.tier_for("the copy reads well", "founder_confirm"),
                         "founder_confirm")
        self.assertEqual(sp.tier_for("the spacing looks right"),
                         "founder_confirm")

    def test_12_every_answer_is_a_tier_the_evaluator_implements(self):
        for check in ("short", SEMANTIC_1, "a" * 300):
            for want in (None, "verify", "contains_artifact",
                         "founder_confirm", "judge", "nonsense"):
                self.assertIn(sp.tier_for(check, want), sp.PROPOSAL_TIERS)


class TestThroughTheProtocol(unittest.TestCase):
    """The boundary, end to end, as a reply arrives."""

    def _goal(self, done_when):
        _d, blocks = sp.parse_reply("```goal\n" + json.dumps({
            "outcome": "the chat picks a language", "done_when": done_when})
            + "\n```")
        return blocks["goal"]

    def test_13_the_live_flights_proposal_is_re_tiered(self):
        g = self._goal([{"tier": "contains_artifact", "check": SEMANTIC_1},
                        {"tier": "contains_artifact", "check": SEMANTIC_2}])
        self.assertEqual([c["tier"] for c in g["done_when"]],
                         ["judge", "judge"])
        self.assertEqual([c["check"] for c in g["done_when"]],
                         [SEMANTIC_1, SEMANTIC_2],
                         "the founder's requirement is PRESERVED, not dropped")

    def test_14_a_re_tier_is_visible_not_silent(self):
        g = self._goal([{"tier": "contains_artifact", "check": SEMANTIC_1}])
        self.assertEqual(g["done_when"][0]["proposed_tier"],
                         "contains_artifact",
                         "the card can tell the founder what changed")

    def test_15_a_literal_check_carries_no_re_tier_marker(self):
        g = self._goal([{"tier": "contains_artifact", "check": "Final choice:"}])
        self.assertEqual(g["done_when"][0]["tier"], "contains_artifact")
        self.assertNotIn("proposed_tier", g["done_when"][0])

    def test_16_a_mixed_proposal_keeps_each_row_on_its_own_merits(self):
        g = self._goal([{"tier": "contains_artifact", "check": "BUILD GREEN"},
                        {"tier": "contains_artifact", "check": SEMANTIC_2},
                        {"check": "staging smoke passed"},
                        {"tier": "verify", "check": "run the migration"}])
        self.assertEqual([c["tier"] for c in g["done_when"]],
                         ["contains_artifact", "judge", "judge", "judge"])

    def test_17_unusable_rows_are_still_dropped_never_coerced(self):
        g = self._goal(["just make it work", {}, {"check": "  "},
                        {"tier": "contains_artifact"}])
        self.assertEqual(g["done_when"], [],
                         "the honesty rule from slice 8 is unchanged")


class TestTheEvaluatorDidNotMove(unittest.TestCase):
    """The fix is at the boundary. Verification semantics are untouched."""

    def test_18_contains_artifact_is_still_a_literal_substring_test(self):
        m = {"done_when": [{"tier": "contains_artifact", "check": "Winner"}]}
        done, res = mission_engine.evaluate_done_when(m, "the Winner is Go")
        self.assertTrue(done)
        done, res = mission_engine.evaluate_done_when(m, "the winner is Go")
        self.assertFalse(done, "case-sensitive, exactly as before")

    def test_19_founder_confirm_still_never_auto_passes(self):
        m = {"done_when": [{"tier": "founder_confirm", "check": SEMANTIC_1}]}
        done, _r = mission_engine.evaluate_done_when(
            m, SEMANTIC_1 + " and the winner is Python")
        self.assertFalse(done,
                         "even with the text present -- only the founder")
        m["done_when"][0]["met"] = True
        done, _r = mission_engine.evaluate_done_when(m, "")
        self.assertTrue(done, "and their confirmation is what sets it")

    def test_20_verify_still_scores_through_an_injected_verifier(self):
        m = {"done_when": [{"tier": "verify", "check": "x"}]}
        self.assertFalse(mission_engine.evaluate_done_when(m, "")[0])
        self.assertTrue(mission_engine.evaluate_done_when(
            m, "", verifier=lambda c: True)[0],
            "the tier itself is unchanged -- only proposals cannot ask for it")

    def test_21_a_founder_authored_post_is_not_policed_here(self):
        """Explicit tiers sent straight to the API keep working: the
        validation added here lives ONLY at Shadow's proposal boundary."""
        src = open(__file__.replace("test_proposal_tiers.py", "app.py"),
                   encoding="utf-8").read()
        i = src.index("async def api_shadow_goal_create")
        body = src[i:i + 2000]
        self.assertNotIn("tier_for", body)
        self.assertNotIn("is_literal_artifact", body)


if __name__ == "__main__":
    unittest.main()
