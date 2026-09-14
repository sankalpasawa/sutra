"""test_model_catalog.py -- the rich model catalogue, and the flat list it must
NOT disturb.

Two properties, and the second is the one that would break other people:

  1. the catalogue carries what the new picker needs -- a main/more split, the
     effort values per model, a fast flag, and what "" resolves to;
  2. `models_by_provider` -- what the SEO Writer and every pre-catalogue client
     reads -- is byte-identical to what it was.

The ids themselves were verified against the real CLI (2.1.270, 2026-09-14)
with a probe that spends no model turn:

    printf '' | claude --model <id> -p --output-format text
      known    -> "Error: Input must be provided ... when using --print"
      unknown  -> '"<id>" isn't described by this version's model catalog'

That probe is NOT re-run here: it needs the operator's own Claude install and
several seconds per id, which is not a unit test. What IS pinned here is that
the catalogue offers exactly the ids that probe accepted, so a later edit
cannot slip an unverified one in without this file changing too.

Run: python -m pytest test_model_catalog.py -q
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import budget       # noqa: E402
import providers    # noqa: E402

#: Exactly what `printf '' | claude --model <id> -p` accepted on 2026-09-14.
VERIFIED_CLAUDE_IDS = {
    "best", "opus", "sonnet", "haiku", "fable",
    "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
    "claude-sonnet-4-6", "opus[1m]", "sonnet[1m]",
}


class TheFlatListIsUntouched(unittest.TestCase):
    """The whole point of adding a second view instead of changing the first."""

    def test_claudes_flat_list_is_exactly_what_it_was(self):
        self.assertEqual([m["id"] for m in providers.models_for("claude")],
                         ["", "fable", "opus", "sonnet", "haiku"])

    def test_models_by_provider_still_carries_the_flat_list(self):
        got = providers.all_models_by_provider()
        self.assertEqual([m["id"] for m in got["claude"]],
                         ["", "fable", "opus", "sonnet", "haiku"])
        self.assertIn("deepseek", got)
        self.assertNotIn("gemini", got, "a provider with no models must stay absent")

    def test_the_catalogue_did_not_leak_best_into_the_flat_list(self):
        """`best` is a catalogue-only id. A client reading the flat list must
        keep seeing `fable`, which is what it has always been sent."""
        flat = [m["id"] for m in providers.models_for("claude")]
        self.assertNotIn("best", flat)
        self.assertIn("fable", flat)


class TheCatalogueShape(unittest.TestCase):

    def test_claude_main_list_is_the_five_the_spec_names(self):
        cat = providers.model_catalog_for("claude")
        self.assertEqual([m["id"] for m in cat["models"]],
                         ["", "best", "opus", "sonnet", "haiku"])

    def test_claude_more_list_is_the_six_pinned_ids(self):
        cat = providers.model_catalog_for("claude")
        self.assertEqual([m["id"] for m in cat["more"]],
                         ["claude-opus-4-8", "claude-opus-4-7",
                          "claude-opus-4-6", "claude-sonnet-4-6",
                          "opus[1m]", "sonnet[1m]"])

    def test_every_offered_claude_id_was_verified_against_the_cli(self):
        """The pin that stops an unverified id being added quietly."""
        cat = providers.model_catalog_for("claude")
        offered = {m["id"] for m in cat["models"] + cat["more"]} - {""}
        self.assertTrue(offered <= VERIFIED_CLAUDE_IDS,
                        "offered but never probed: %s"
                        % sorted(offered - VERIFIED_CLAUDE_IDS))

    def test_every_claude_model_carries_the_cli_five_efforts(self):
        """From `claude --effort bogus`'s own rejection: low, medium, high,
        xhigh, max -- and the CLI accepts them on every model."""
        cat = providers.model_catalog_for("claude")
        for entry in cat["models"] + cat["more"]:
            self.assertEqual(entry["efforts"],
                             ["low", "medium", "high", "xhigh", "max"],
                             "%r" % entry["id"])

    def test_only_codex_declares_a_fast_switch(self):
        self.assertFalse(providers.model_catalog_for("claude")["fast"])
        self.assertFalse(providers.model_catalog_for("deepseek")["fast"])
        self.assertTrue(providers.model_catalog_for("codex")["fast"])
        self.assertTrue(providers.fast_supported("codex"))
        self.assertFalse(providers.fast_supported("claude"))
        self.assertFalse(providers.fast_supported("nope"))

    def test_claudes_default_is_empty_because_it_is_unknowable(self):
        """The same asymmetry budget.py documents: `claude` with no model
        selected resolves to whatever the operator configured, which nothing
        here can read. "" is the honest answer, not a gap."""
        self.assertEqual(providers.model_catalog_for("claude")["default"], "")

    def test_deepseeks_default_is_the_measured_one(self):
        self.assertEqual(providers.model_catalog_for("deepseek")["default"],
                         "deepseek-v4-flash")

    def test_deepseek_carries_no_efforts(self):
        """Measured, not pending: ACP's per-turn request has no options field
        at all (see providers._CLAUDE_TURN_OPTIONS)."""
        for entry in providers.model_catalog_for("deepseek")["models"]:
            self.assertEqual(entry["efforts"], [])

    def test_a_provider_with_no_models_has_no_catalogue(self):
        self.assertIsNone(providers.model_catalog_for("gemini"))
        self.assertNotIn("gemini", providers.all_model_catalog_by_provider())

    def test_the_disabled_deepseek_model_is_listed_and_not_selectable(self):
        """It must stay VISIBLE with its reason -- dropping it would hide that
        the model exists -- and stay unselectable."""
        entries = {m["id"]: m
                   for m in providers.model_catalog_for("deepseek")["models"]}
        vision = entries["deepseek-v4-flash-vision-exp"]
        self.assertFalse(vision["selectable"])
        self.assertIn("unavailable_reason", vision)

    def test_every_catalogue_entry_has_the_keys_the_client_reads(self):
        for pid, cat in providers.all_model_catalog_by_provider().items():
            self.assertEqual(sorted(cat), ["default", "fast", "models", "more"])
            for entry in cat["models"] + cat["more"]:
                for key in ("id", "name", "note", "efforts", "selectable"):
                    self.assertIn(key, entry, "%s/%s" % (pid, entry.get("id")))


class ASavedChoiceCannotBeRefusedLater(unittest.TestCase):
    """The failure this widening exists to prevent: an id the picker offers,
    written to settings.json, and then called unknown on the next read."""

    def test_every_catalogued_id_passes_clean_model(self):
        for pid, cat in providers.all_model_catalog_by_provider().items():
            for entry in cat["models"] + cat["more"]:
                if not entry["id"] or not entry["selectable"]:
                    continue
                self.assertEqual(providers.clean_model(entry["id"], pid),
                                 entry["id"], "%s/%s" % (pid, entry["id"]))

    def test_best_and_the_pinned_ids_are_selectable(self):
        allowed = providers.selectable_model_ids_for("claude")
        for mid in ("best", "claude-opus-4-8", "claude-opus-4-7",
                    "claude-opus-4-6", "claude-sonnet-4-6",
                    "opus[1m]", "sonnet[1m]"):
            self.assertIn(mid, allowed)

    def test_a_disabled_id_is_still_refused(self):
        self.assertIsNone(
            providers.clean_model("deepseek-v4-flash-vision-exp", "deepseek"))

    def test_an_unknown_id_is_still_refused(self):
        self.assertIsNone(providers.clean_model("claude-opus-9-9", "claude"))
        self.assertIsNone(providers.clean_model("best", "deepseek"),
                          "Claude's alias must not validate on DeepSeek")

    def test_every_catalogued_model_has_a_context_window(self):
        """Duplicated from test_budget on purpose: this file is where someone
        adds a model, so this is where the reminder has to fire."""
        for entry in (providers.model_catalog_for("claude")["models"]
                      + providers.model_catalog_for("claude")["more"]):
            if not entry["id"]:
                continue
            self.assertEqual(
                budget.window_for("claude", entry["id"])["source"], "declared",
                "%r has no declared window" % entry["id"])


if __name__ == "__main__":
    unittest.main()
