"""test_provider_settings.py -- the per-provider switches: what is published,
what is stored, and what is NEVER touched.

The load-bearing property is the last one. These switches live under a NEW
top-level `provider_settings` key, and a bug here that reached
`permission_mode`, `workdir` or `model_by_provider` would change what a chat
runs as. So several tests below do nothing but read the raw file back and
assert the other keys are exactly as they were.

The second property is that a value equal to its default is ABSENT rather than
written -- the schema already carries the defaults, and a file that restates
them is two copies of one fact that can drift.

Run: python -m pytest test_provider_settings.py -q
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import providers   # noqa: E402


class TempSettings(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sutra-provset-test-")
        self._old = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(self.dir) / "settings.json"

    def tearDown(self):
        providers.SETTINGS_PATH = self._old
        shutil.rmtree(self.dir, ignore_errors=True)

    def raw(self):
        try:
            return json.loads(providers.SETTINGS_PATH.read_text())
        except OSError:
            return {}

    def write_raw(self, data):
        providers.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        providers.SETTINGS_PATH.write_text(json.dumps(data))


class TheSchema(TempSettings):

    def test_only_providers_with_switches_appear(self):
        schema = providers.provider_settings_schema()
        self.assertEqual(sorted(schema), ["claude", "codex"])

    def test_claude_declares_the_three_verified_switches(self):
        keys = [r["key"] for r in providers.provider_settings_schema()["claude"]]
        self.assertEqual(keys, ["chrome", "subagents", "workflows"])

    def test_claude_memory_was_dropped_rather_than_shipped(self):
        """The CLI has no memory lever that means only "memory" -- `--bare`
        also drops hooks, LSP, plugin sync, attribution and CLAUDE.md
        discovery. A switch labelled Memory that did seven other things would
        be worse than none, so it is absent until the CLI has one."""
        keys = [r["key"] for r in providers.provider_settings_schema()["claude"]]
        self.assertNotIn("memory", keys)

    def test_codex_declares_memory_and_subagents(self):
        keys = [r["key"] for r in providers.provider_settings_schema()["codex"]]
        self.assertEqual(keys, ["memory", "subagents"])

    def test_every_row_is_a_boolean_with_a_label_and_a_default(self):
        for pid, rows in providers.provider_settings_schema().items():
            for row in rows:
                self.assertEqual(sorted(row),
                                 ["default", "desc", "key", "label", "type"])
                self.assertEqual(row["type"], "boolean")
                self.assertIsInstance(row["default"], bool)
                self.assertTrue(row["label"] and row["desc"], "%s/%s"
                                % (pid, row["key"]))

    def test_the_defaults_are_the_clis_own_behaviour(self):
        """An untouched machine must behave exactly as it does today."""
        self.assertEqual(providers.provider_settings("claude"),
                         {"chrome": False, "subagents": True, "workflows": True})
        self.assertEqual(providers.provider_settings("codex"),
                         {"memory": True, "subagents": True})

    def test_the_published_schema_is_a_copy(self):
        """A caller mutating the response must not edit the module's table."""
        got = providers.provider_settings_schema()
        got["claude"][0]["default"] = "tampered"
        self.assertIs(providers.provider_settings_schema()["claude"][0]["default"],
                      False)


class TheReader(TempSettings):

    def test_it_always_answers_every_key(self):
        """What the spawn path needs: no caller ever has to remember a
        default or handle a missing one."""
        self.write_raw({"provider_settings": {"claude": {"chrome": True}}})
        self.assertEqual(providers.provider_settings("claude"),
                         {"chrome": True, "subagents": True, "workflows": True})

    def test_a_provider_with_no_schema_answers_empty(self):
        self.assertEqual(providers.provider_settings("deepseek"), {})
        self.assertEqual(providers.provider_settings("gemini"), {})
        self.assertEqual(providers.provider_settings("nope"), {})

    def test_junk_in_the_file_is_dropped_not_carried(self):
        """The file is hand-editable and is written by older and newer builds,
        so every level has to survive anything."""
        for junk in ("not a dict", 7, None, [], {"claude": "nope"},
                     {"claude": {"chrome": "yes"}}, {"nope": {"a": True}},
                     {"claude": {"unknown_key": True}}):
            self.write_raw({"provider_settings": junk})
            self.assertEqual(providers.provider_settings("claude"),
                             {"chrome": False, "subagents": True,
                              "workflows": True},
                             "junk %r leaked" % (junk,))

    def test_a_missing_file_is_all_defaults(self):
        self.assertEqual(providers.provider_settings("codex"),
                         {"memory": True, "subagents": True})


class TheWriter(TempSettings):

    def test_a_non_default_is_stored(self):
        providers.save_provider_settings({"claude": {"chrome": True}})
        self.assertEqual(self.raw()["provider_settings"],
                         {"claude": {"chrome": True}})

    def test_a_default_is_absence_not_a_row(self):
        providers.save_provider_settings({"claude": {"chrome": True,
                                                     "subagents": False}})
        providers.save_provider_settings({"claude": {"chrome": False}})
        self.assertEqual(self.raw()["provider_settings"],
                         {"claude": {"subagents": False}})

    def test_returning_everything_to_default_removes_the_key_entirely(self):
        providers.save_provider_settings({"claude": {"chrome": True}})
        providers.save_provider_settings({"claude": {"chrome": False}})
        self.assertNotIn("provider_settings", self.raw())

    def test_it_is_a_patch_not_a_replacement(self):
        providers.save_provider_settings({"claude": {"chrome": True}})
        providers.save_provider_settings({"codex": {"memory": False}})
        self.assertEqual(self.raw()["provider_settings"],
                         {"claude": {"chrome": True},
                          "codex": {"memory": False}})
        providers.save_provider_settings({"claude": {"subagents": False}})
        self.assertEqual(self.raw()["provider_settings"]["claude"],
                         {"chrome": True, "subagents": False})

    def test_only_non_defaults_are_published(self):
        providers.save_provider_settings({"claude": {"chrome": True,
                                                     "workflows": True}})
        self.assertEqual(providers.stored_provider_settings(),
                         {"claude": {"chrome": True}})

    def test_load_settings_carries_the_same_non_defaults(self):
        out = providers.save_provider_settings({"codex": {"subagents": False}})
        self.assertEqual(out["provider_settings"],
                         {"codex": {"subagents": False}})

    def test_an_untouched_machine_publishes_nothing(self):
        self.assertEqual(providers.stored_provider_settings(), {})
        self.assertEqual(providers.load_settings()["provider_settings"], {})


class TheRefusals(TempSettings):

    def test_an_unknown_provider_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            providers.save_provider_settings({"deepseek": {"chrome": True}})
        self.assertIn("no per-provider settings", str(ctx.exception))

    def test_an_unknown_key_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            providers.save_provider_settings({"claude": {"telepathy": True}})
        self.assertIn("unknown setting", str(ctx.exception))

    def test_a_non_boolean_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            providers.save_provider_settings({"claude": {"chrome": "yes"}})
        self.assertIn("true or false", str(ctx.exception))

    def test_a_non_dict_is_refused(self):
        for bad in ("nope", 7, [1], {"claude": "nope"}):
            with self.assertRaises(ValueError):
                providers.save_provider_settings(bad)

    def test_a_refused_patch_writes_nothing(self):
        """Validated BEFORE writing, so nothing is half-applied."""
        providers.save_provider_settings({"claude": {"chrome": True}})
        before = self.raw()
        with self.assertRaises(ValueError):
            providers.save_provider_settings({"claude": {"chrome": False,
                                                         "nope": True}})
        self.assertEqual(self.raw(), before)


class NothingElseIsTouched(TempSettings):
    """The reason this has its own write path instead of living inside
    save_settings()."""

    EXISTING = {
        "provider": "claude",
        "permission_mode": "dontAsk",
        "workdir": "/tmp/somewhere",
        "model": "opus",
        "model_by_provider": {"claude": "opus", "deepseek": "deepseek-v4-pro"},
        "onboarded": True,
        "chat_scope": "all",
        "flags": {"something": True},
        "unsafe_modes_acknowledged": True,
        "deepseek_key": {"mask": "sk-…abcd"},
        "shadow.enabled": False,
        "an_unknown_key_from_a_newer_build": [1, 2, 3],
    }

    def test_every_other_key_survives_a_write(self):
        self.write_raw(dict(self.EXISTING))
        providers.save_provider_settings({"claude": {"chrome": True}})
        after = self.raw()
        after.pop("provider_settings")
        self.assertEqual(after, self.EXISTING)

    def test_the_permission_mode_is_not_disturbed(self):
        self.write_raw(dict(self.EXISTING))
        providers.save_provider_settings({"codex": {"memory": False}})
        self.assertEqual(providers.load_settings()["permission_mode"], "dontAsk")

    def test_a_key_from_a_newer_build_is_put_back_verbatim(self):
        """A file written by a build that knows more than this one must not be
        pruned by a round trip through here."""
        self.write_raw(dict(self.EXISTING))
        providers.save_provider_settings({"claude": {"workflows": False}})
        self.assertEqual(self.raw()["an_unknown_key_from_a_newer_build"],
                         [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
