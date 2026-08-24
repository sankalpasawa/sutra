"""The update channel is founder-owned (2026-08-24).

Three pins, per the codex consult on the inversion:
  1. the DEFAULT: with no env override, both channels point at the founder's
     repo — a silent revert of this default re-routes every user's updates
     through a repo the founder does not control;
  2. the OVERRIDE: SUTRA_UI_DESKTOP_REPO still wins, because dev/QA flows
     depend on it;
  3. the BEHAVIOR: _latest_desktop() actually asks the founder's repo — a
     correct constant read by the wrong call site would still strand users.

DESKTOP_REPO binds at import time, so every pin reloads the module.
Run: .venv/bin/python -m pytest -q test_update_channel.py
"""
import importlib
import os
import unittest

import updates


def _reload_without_env():
    saved = os.environ.pop("SUTRA_UI_DESKTOP_REPO", None)
    importlib.reload(updates)
    return saved


def _restore_env(saved):
    if saved is not None:
        os.environ["SUTRA_UI_DESKTOP_REPO"] = saved
    else:
        os.environ.pop("SUTRA_UI_DESKTOP_REPO", None)
    importlib.reload(updates)


class UpdateChannel(unittest.TestCase):
    def test_1_desktop_channel_defaults_to_the_founders_repo(self):
        saved = _reload_without_env()
        try:
            self.assertEqual(updates.DESKTOP_REPO, "sankalpasawa/sutra")
        finally:
            _restore_env(saved)

    def test_2_plugin_channel_is_the_same_repo(self):
        saved = _reload_without_env()
        try:
            self.assertEqual(updates.PLUGIN_REPO, "sankalpasawa/sutra")
        finally:
            _restore_env(saved)

    def test_3_env_override_still_wins(self):
        saved = os.environ.get("SUTRA_UI_DESKTOP_REPO")
        os.environ["SUTRA_UI_DESKTOP_REPO"] = "example/elsewhere"
        try:
            importlib.reload(updates)
            self.assertEqual(updates.DESKTOP_REPO, "example/elsewhere")
        finally:
            _restore_env(saved)

    def test_4_latest_desktop_actually_asks_the_founders_repo(self):
        saved = _reload_without_env()
        asked = []
        real = updates._get_json
        updates._get_json = lambda url: (asked.append(url), {"tag_name": "v0.0.0-desktop", "assets": []})[1]
        try:
            updates._latest_desktop()
            self.assertEqual(
                asked,
                ["https://api.github.com/repos/sankalpasawa/sutra/releases/latest"],
                "the call site must hit the founder's repo, not merely define it")
        finally:
            updates._get_json = real
            _restore_env(saved)


if __name__ == "__main__":
    unittest.main()
