"""PLAN-100 S38/S39/S41: verify tool, mission_update, feed contract stub."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))

import shadow_feed
import shadow_ledger


def _item(**over):
    base = {"item_id": "f-1", "producer": "shadow", "kind": "needs_decision",
            "title": "Mission m-1 needs a yes", "deep_link": "sutra://shadow/t-1",
            "dedupe_key": "m-1:brief", "state": "new"}
    base.update(over)
    return base


class TestFeedContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_01_valid_item_accepted_once(self):
        ok, problems = shadow_feed.emit(_item())
        self.assertTrue(ok, problems)
        ok, problems = shadow_feed.emit(_item())
        self.assertFalse(ok)
        self.assertIn("duplicate dedupe_key", problems)

    def test_02_missing_required_field_rejected(self):
        bad = _item()
        del bad["deep_link"]
        ok, problems = shadow_feed.emit(bad)
        self.assertFalse(ok)
        self.assertTrue(any("deep_link" in p for p in problems))

    def test_03_unknown_fields_rejected(self):
        ok, problems = shadow_feed.emit(_item(surprise="x"))
        self.assertFalse(ok)

    def test_04_unknown_state_rejected(self):
        ok, problems = shadow_feed.emit(_item(state="vibing"))
        self.assertFalse(ok)


class TestMissionUpdateAndVerify(unittest.TestCase):
    def _run(self, code, flag=True):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"shadow.enabled": flag}))
            env = dict(os.environ, SUTRA_UI_SETTINGS=str(settings),
                       SUTRA_MCP_SHADOW="1", SUTRA_SHADOW_HOME=tmp)
            out = subprocess.run([sys.executable, "-c", code],
                                 capture_output=True, text=True,
                                 cwd=HERE, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            return out.stdout.strip().splitlines()[-1]

    def test_05_mission_update_appends_and_validates(self):
        line = self._run("; ".join([
            "import json, sutra_mcp",
            "t = sutra_mcp.BY_NAME['shadow_mission_update']",
            "print(json.dumps(t['fn']({'mission_id': 'm-9', 'state': 'running'})))",
        ]))
        self.assertIn("m-9", line)
        line = self._run("; ".join([
            "import json, sutra_mcp",
            "t = sutra_mcp.BY_NAME['shadow_mission_update']",
            "print(json.dumps(t['fn']({'mission_id': 'm-9', 'state': 'flying'})))",
        ]))
        self.assertIn("refused", line)

    def test_06_verify_ledger_has(self):
        line = self._run("; ".join([
            "import json, sutra_mcp",
            "u = sutra_mcp.BY_NAME['shadow_mission_update']",
            "u['fn']({'mission_id': 'm-7', 'state': 'done'})",
            "v = sutra_mcp.BY_NAME['shadow_verify']",
            "print(json.dumps(v['fn']({'mode': 'ledger_has', 'kind': 'missions', 'needle': 'm-7'})))",
        ]))
        self.assertIn("true", line.lower())


if __name__ == "__main__":
    unittest.main()
