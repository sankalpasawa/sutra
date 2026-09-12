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
        w = budget.window_for("deepseek", "deepseek-v4-pro")
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
        self.assertEqual(
            budget.FLOOR_WINDOW,
            min(w for windows in budget.WINDOWS.values() for w in windows.values()))

    def test_every_catalogued_model_has_a_window_or_is_the_default(self):
        """Pins the window table to the picker, so a new model entry cannot
        silently inherit a wrong ceiling.

        EVERY provider that has a picker, not just Claude's. A DeepSeek entry
        added to the catalogue without a window here would resolve through the
        unknown-model path, and this is the thing that says so at test time
        instead of at a rejected request."""
        for spec in providers._CATALOG:
            pid = spec["id"]
            for m in providers.models_for(pid):
                mid = m["id"]
                if mid == "":
                    continue   # "CLI default" -- see the empty-id tests below
                self.assertIn(mid, budget.WINDOWS.get(pid, {}),
                              "%s model %r is in the picker but has no "
                              "declared context window" % (pid, mid))

    def test_no_provider_declares_a_window_for_a_model_it_does_not_offer(self):
        """The other direction. A window left behind after a model is retired
        is a claim about something the panel can no longer run, and the next
        person to read the table would believe it."""
        for pid, windows in budget.WINDOWS.items():
            offered = providers.model_ids_for(pid)
            for mid in windows:
                self.assertIn(mid, offered,
                              "%s declares a window for %r, which is not in "
                              "its model list" % (pid, mid))

    def test_deepseeks_cli_default_is_its_real_window_not_the_floor(self):
        """4.2, THE REGRESSION GUARD. "" is not an edge case for DeepSeek -- it
        is the shipped default, what every session runs on until someone picks
        something else.

        Before the table was keyed by model, window_for("deepseek", ...) ignored
        the model and returned a flat 1M. Keying by model WITHOUT a declared
        per-provider default would have sent "" down the unknown path to
        FLOOR_WINDOW: 200K instead of 1M, an 800K under-count feeding the switch
        and compaction paths, reported by nothing."""
        w = budget.window_for("deepseek", "")
        self.assertEqual(w["tokens"], 1000000,
                         "DeepSeek's CLI default fell to the floor")
        self.assertEqual(w["source"], "provider-default")
        self.assertNotEqual(w["tokens"], budget.FLOOR_WINDOW)
        # and the arithmetic downstream, which is where it would have bitten
        self.assertGreater(budget.for_target("deepseek", "")["budget_chars"],
                           budget.for_target("claude", "")["budget_chars"] * 4)

    def test_a_provider_default_is_declared_for_every_provider_whose_default_is_knowable(self):
        """Makes the floor-drop impossible rather than merely caught.

        A provider with a picker resolves "" one of two ways: to a window it
        declares as its default, or to the floor. The floor is only honest when
        the panel genuinely cannot know what the CLI will pick. Claude is that
        case and is exempt BY NAME here -- so adding a fifth provider with a
        picker fails this test until someone states which case it is, rather
        than silently inheriting the pessimistic one."""
        # The CLI's own configured default, which this panel cannot know.
        #
        # CLAUDE IS THE ONLY MEMBER, and it is the only one that can be: its ""
        # spans a five-fold range (opus and sonnet hold 1M, haiku 200K), so
        # without knowing the model there is no honest number to state.
        #
        # codex was exempt here from 2026-09-08 to 2026-09-09 on an argument
        # that has since expired in both halves. It read: codex publishes no
        # model roster at all, so "" cannot be resolved; and the exemption is
        # inert anyway because switch._transport_for("codex") returns None, so
        # a switch TO codex is refused before any ceiling is computed. Neither
        # holds now -- codex_models.py asks `model/list` over RPC and falls
        # back to $CODEX_HOME/models_cache.json, and codex became a real switch
        # target -- so the floor stopped being caution and became a 22%
        # under-count on a live path.
        #
        # What made it knowable was narrower than a roster: every model codex
        # offered declared the same effective window (272,000 x 95% =
        # 258,400), so "" resolved to 258,400 whichever model the server
        # picked. That stopped being true on 2026-09-12 (spark at 121,600),
        # and the answer is per model now: budget.window_for asks the
        # discovered roster for a selected model, and "" keeps this default
        # until the roster marks a default -- see
        # test_every_visible_codex_model_resolves_to_its_own_declared_window.
        UNKNOWABLE_DEFAULT = {"claude"}
        for spec in providers._CATALOG:
            pid = spec["id"]
            if not providers.models_for(pid) or pid in UNKNOWABLE_DEFAULT:
                continue
            self.assertIn(pid, budget.DEFAULT_WINDOWS,
                          "%s offers a model picker but does not declare what "
                          '"" resolves to, so it would silently take the %d '
                          "floor" % (pid, budget.FLOOR_WINDOW))

    def test_codex_reports_its_enforced_window_not_the_floor(self):
        """4A. 258,400 is what codex ENFORCES, not the 272,000 raw window.

        Before this landed, a switch TO codex was sized against the 200K floor
        -- a 22% under-count that made tier 2 shed tool I/O sooner than the
        provider required. The direction was safe (degraded success, never a
        rejected request) and it was still wrong."""
        w = budget.window_for("codex", "")
        self.assertEqual(w["tokens"], 258400)
        self.assertEqual(w["source"], "provider-default")
        self.assertNotEqual(w["tokens"], budget.FLOOR_WINDOW)
        b = budget.for_target("codex", "")
        self.assertEqual(b["window_tokens"], 258400)
        # the derivation the operator sees after a tier-2 switch
        self.assertEqual(b["usable_tokens"],
                         int((258400 - budget.REPLY_RESERVE_TOKENS)
                             * budget.USABLE_FRACTION))
        self.assertEqual(b["budget_chars"],
                         int(b["usable_tokens"] * budget.CHARS_PER_TOKEN))
        self.assertIn("known model, not a guess", b["note"])

    def test_codex_ignores_another_providers_model_id(self):
        """Same guard test_claude_model_id_is_ignored_for_deepseek makes: a
        stray id from another provider must not select a window."""
        for foreign in ("haiku", "opus", "deepseek-v4-pro"):
            w = budget.window_for("codex", foreign)
            self.assertEqual(w["tokens"], 258400, foreign)
            self.assertEqual(w["source"], "provider-default", foreign)

    def test_codex_declares_no_per_model_window_table(self):
        """Deliberate: codex's roster is DISCOVERED per account, so a per-model
        table would claim windows for ids models_for("codex") does not offer in
        a fresh process, and would go stale the day a fourth model ships."""
        self.assertNotIn("codex", budget.WINDOWS)
        self.assertIn("codex", budget.DEFAULT_WINDOWS)

    def test_every_visible_codex_model_resolves_to_its_own_declared_window(self):
        """THE CANARY, second form.

        Until 2026-09-12 this asserted that every visible codex model agreed
        on ONE effective window, which is what made a single default honest.
        gpt-5.3-codex-spark then appeared at 121,600 beside 258,400 and it
        fired, as designed. The contract now: whatever codex's OWN cache
        declares per model is what window_for returns for that model, source
        `declared` -- so a new model with a new window can never be sized by
        the default. Reads codex's cache when it is present and skips
        otherwise; never an account or a network call."""
        import json
        import os
        import codex_models
        home = os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")
        path = os.path.join(home, "models_cache.json")
        if not os.path.exists(path):
            self.skipTest("no codex models cache on this machine")
        with open(path, encoding="utf-8", errors="replace") as fh:
            blob = json.load(fh)
        declared = {}
        for m in blob.get("models") or []:
            if m.get("visibility") != "list":
                continue
            cw, pct = m.get("context_window"), m.get(
                "effective_context_window_percent")
            if isinstance(cw, int) and isinstance(pct, int):
                declared[m.get("slug")] = int(cw * pct / 100)
        if not declared:
            self.skipTest("cache declares no visible model windows")
        codex_models._reset_for_tests()      # the file path, not a stale roster
        self.addCleanup(codex_models._reset_for_tests)
        for slug, tokens in declared.items():
            w = budget.window_for("codex", slug)
            self.assertEqual((w["tokens"], w["source"]), (tokens, "declared"),
                             "%s: codex declares %d, budget resolved %r"
                             % (slug, tokens, w))
        # the cache file marks no default, so "" still resolves to the
        # provider default rather than to any one model's window
        self.assertEqual(budget.window_for("codex", "")["tokens"],
                         budget.DEFAULT_WINDOWS["codex"])

    def test_the_other_providers_windows_are_untouched_by_4a(self):
        """Frozen: 4A adds one DEFAULT_WINDOWS key and nothing else."""
        self.assertEqual(budget.WINDOWS["claude"],
                         {"opus": 1000000, "sonnet": 1000000, "haiku": 200000})
        self.assertEqual(budget.DEFAULT_WINDOWS["deepseek"], 1000000)
        self.assertEqual(budget.window_for("claude", "opus")["tokens"], 1000000)
        self.assertEqual(budget.window_for("claude", "haiku")["tokens"], 200000)
        self.assertEqual(budget.window_for("claude", "")["source"],
                         "assumed-floor")
        self.assertEqual(budget.window_for("deepseek", "")["tokens"], 1000000)
        self.assertEqual(budget.window_for("deepseek", "")["source"],
                         "provider-default")
        # and the floor is derived from WINDOWS only, so a DEFAULT_WINDOWS
        # addition cannot move it
        self.assertEqual(budget.FLOOR_WINDOW, 200000)
        self.assertEqual(budget.window_for("gemini")["source"], "assumed-floor")
        self.assertEqual(budget.window_for("nope-not-a-provider")["tokens"],
                         budget.FLOOR_WINDOW)

    def test_claudes_cli_default_still_falls_to_the_floor(self):
        """The exemption above is not a loophole: Claude's "" is genuinely
        unknowable to this panel, so the floor stays the honest answer and this
        pins that it did not drift into a guess."""
        w = budget.window_for("claude", "")
        self.assertEqual(w["source"], "assumed-floor")
        self.assertEqual(w["tokens"], budget.FLOOR_WINDOW)


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
