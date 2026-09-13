"""test_shadow_app_state.py -- one liveness rule for both Shadow session readers.

Finding (2026-09-10): shadow_app_state said sessions_live=0 while
shadow_sessions_list showed 3 active. Both call session_reader.liveness(),
which answers active | idle | stale; app_state counted "live", a value the
helper never returns. Pinned here so the two readers can never disagree.

Isolation: the shadow tools register only when the flag is on AND
SUTRA_MCP_SHADOW=1 at IMPORT, so this module re-imports sutra_mcp under
those two conditions -- and pops ONLY sutra_mcp from the module cache. Popping
`providers` too (the test_sutra_mcp precedent) hands every module collected
after this one a second providers object, and a test that patches
providers.SETTINGS_PATH then patches the wrong one (test_shadow_session broke
that way in the whole-directory run, 2026-09-13). The settings path is
pointed at an empty temp file only for the duration of the import.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

UI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, UI)

os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="appstate-shadow-"))
_SETTINGS = Path(tempfile.mkdtemp(prefix="appstate-settings-")) / "settings.json"
_SETTINGS.write_text("{}", encoding="utf-8")   # shadow is ON unless explicitly false

import providers  # noqa: E402

_prev_flag = os.environ.get("SUTRA_MCP_SHADOW")
_prev_path = providers.SETTINGS_PATH
os.environ["SUTRA_MCP_SHADOW"] = "1"
providers.SETTINGS_PATH = _SETTINGS
try:
    sys.modules.pop("sutra_mcp", None)
    import sutra_mcp  # noqa: E402
finally:
    providers.SETTINGS_PATH = _prev_path
    if _prev_flag is None:
        os.environ.pop("SUTRA_MCP_SHADOW", None)
    else:
        os.environ["SUTRA_MCP_SHADOW"] = _prev_flag


def _rows(now):
    return [
        {"id": "s-active-1", "title": "a", "mtime": now - 5},
        {"id": "s-active-2", "title": "b", "mtime": now - 20},
        {"id": "s-idle", "title": "c", "mtime": now - 600},
        {"id": "s-stale", "title": "d", "mtime": now - 90000},
    ]


class AppStateLiveness(unittest.TestCase):

    def setUp(self):
        self.assertIn("shadow_app_state", sutra_mcp.BY_NAME,
                      "shadow tools must be registered for this test")
        # call-time gate: shadow_enabled() must read ON while the tool runs
        self._path = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = _SETTINGS

    def tearDown(self):
        providers.SETTINGS_PATH = self._path

    def _call(self, name):
        res = sutra_mcp.BY_NAME[name]["fn"]({})
        return json.loads(res["content"][0]["text"])

    def _stubbed(self, now):
        """Sessions and provider state are inputs here, not the subject."""
        p = sutra_mcp._providers
        return (mock.patch.object(sutra_mcp._session_reader, "list_sessions",
                                  lambda **kw: _rows(now)),
                mock.patch.object(p, "active_provider_detail",
                                  lambda: {"id": "claude", "source": "test"}),
                mock.patch.object(p, "load_settings",
                                  lambda: {"permission_mode": "default"}),
                mock.patch.object(p, "effective_permission_mode",
                                  lambda mode: mode))

    def test_app_state_counts_active_sessions(self):
        now = time.time()
        a, b, c, d = self._stubbed(now)
        with a, b, c, d:
            state = self._call("shadow_app_state")
        self.assertEqual(state["sessions_total"], 4)
        self.assertEqual(state["sessions_live"], 2)
        self.assertEqual(state["sessions_idle"], 1)

    def test_both_readers_agree_on_live(self):
        """The invariant the finding violated: app_state.sessions_live equals
        the number of sessions_list rows whose liveness is "active"."""
        now = time.time()
        a, b, c, d = self._stubbed(now)
        with a, b, c, d:
            state = self._call("shadow_app_state")
            listed = self._call("shadow_sessions_list")
        active = [r for r in listed if r["liveness"] == "active"]
        self.assertEqual(len(active), 2)
        self.assertEqual(state["sessions_live"], len(active))
        self.assertNotIn("live", {r["liveness"] for r in listed},
                         "liveness never answers 'live'; app_state must not count it")


if __name__ == "__main__":
    unittest.main()
