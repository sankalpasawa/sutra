"""test_sutra_mcp.py -- the Apps frameworks tool on the panel's MCP server.

`sutra_app_check` is the read-only lane a building chat uses when its
permission mode refuses a bare Bash run (design v1 R1-P9): same runner, same
kit, same verdict as `python3 check.py`, confined to the modules home.

Isolation (I-T1): temp homes are set and cached modules popped before any import.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

MOD_HOME = tempfile.mkdtemp(prefix="mcp-modules-")
os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
os.environ["SUTRA_NATIVE_HOME"] = tempfile.mkdtemp(prefix="mcp-native-")
os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="mcp-shadow-")
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="mcp-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ["KIT_NO_RENDER"] = "1"
for _m in ("placement_engine", "org_api", "modules_api", "modules_events", "modules_pkg", "app", "check", "sutra_mcp"):
    sys.modules.pop(_m, None)

UI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(UI, "tests", "fixtures", "kit"))
sys.path.insert(0, UI)
import make_fixtures  # noqa: E402
import sutra_mcp  # noqa: E402


class AppCheckTool(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.folder = make_fixtures.make_pass("page", os.path.join(MOD_HOME, "late-loans"))

    def setUp(self):
        # re-assert per test: another suite collected in the same pytest process
        # binds its own temp home at import (the test_modules_api precedent)
        os.environ["SUTRA_MODULES_HOME"] = MOD_HOME

    def fn(self, args):
        return sutra_mcp.BY_NAME["sutra_app_check"]["fn"](args)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MOD_HOME, ignore_errors=True)

    def test_app_check_is_listed_with_a_schema(self):
        t = sutra_mcp.BY_NAME["sutra_app_check"]
        self.assertIn("id", t["schema"]["properties"])
        self.assertIn("path", t["schema"]["properties"])
        self.assertIn("check", t["description"].lower())

    def test_app_check_runs_the_kit_on_an_app_by_id_and_writes_the_block(self):
        out = self.fn({"id": "late-loans", "kind": "page"})
        self.assertFalse(out.get("isError"), out)
        text = out["content"][0]["text"]
        self.assertIn("must-fix pass", text)
        self.assertIn("render: not run", text)
        rec = open(os.path.join(self.folder, "APP.md"), encoding="utf-8").read()
        self.assertIn("## Checks\n\nkit ", rec)
        self.assertTrue(rec.splitlines()[0].startswith("frameworkKit:"), "the stamp line is untouched")

    def test_app_check_by_path_is_confined_to_the_modules_home(self):
        out = self.fn({"path": self.folder})
        self.assertFalse(out.get("isError"), out)
        out = self.fn({"path": tempfile.gettempdir()})
        self.assertTrue(out.get("isError"))
        out = self.fn({"id": "../etc"})
        self.assertTrue(out.get("isError"))

    def test_app_check_unknown_app_is_an_error_not_a_crash(self):
        out = self.fn({"id": "nope"})
        self.assertTrue(out.get("isError"))
        self.assertIn("module.json", out["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
