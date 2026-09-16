"""Shadow v4 step 7 (C7): "How Shadow behaves" -- the founder's own words.

One verbose text, in the SAME task-limits store 2.278.12 gave the numbers
(mission_engine.limits_path), read at every Shadow boot and appended to the
context under HOW SHADOW BEHAVES. Three levels, like test_shadow_run_limit:

  STORE   mission_engine.behaves() / set_behaves(): persisted, trimmed to
          BEHAVES_MAX_CHARS, never raises on a corrupt file.
  BOOT    shadow_session.standing_context() carries the text when set and
          nothing extra when empty; a failing limits read never erases the
          standing instructions block.
  ROUTE   GET /api/shadow/settings reports it; POST /api/shadow/settings/
          behaves writes it and refuses junk.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_settings.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-behaves-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_ledger                           # noqa: E402
import shadow_session                          # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
ROUTE = "/api/shadow/settings/behaves"
TEXT = ("Check in every 3 turns. Never use the word mission with me. "
        "When two tasks conflict, ask before starting the second.")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()


class TestTheStore(Base):

    def test_01_unset_is_empty_and_creates_no_file(self):
        self.assertEqual(mission_engine.behaves(), "")
        self.assertFalse(os.path.exists(mission_engine.limits_path()))

    def test_02_set_then_read_survives_a_fresh_read(self):
        stored = mission_engine.set_behaves("  " + TEXT + "\n")
        self.assertEqual(stored, TEXT, "trimmed, otherwise verbatim")
        self.assertEqual(mission_engine.behaves(), TEXT)
        on_disk = json.loads(Path(mission_engine.limits_path()).read_text())
        self.assertEqual(on_disk["behaves"], TEXT)

    def test_03_lives_beside_the_numbers_not_in_a_second_store(self):
        mission_engine.set_max_running(3)
        mission_engine.set_behaves(TEXT)
        on_disk = json.loads(Path(mission_engine.limits_path()).read_text())
        self.assertEqual(on_disk["running_at_once"], 3)
        self.assertEqual(on_disk["behaves"], TEXT)
        self.assertEqual(mission_engine.max_running(), 3,
                         "writing the text must not disturb the cap")

    def test_04_long_text_is_cut_at_the_ceiling(self):
        long = "x" * (mission_engine.BEHAVES_MAX_CHARS + 500)
        self.assertEqual(len(mission_engine.set_behaves(long)),
                         mission_engine.BEHAVES_MAX_CHARS)

    def test_05_non_text_is_refused_not_coerced(self):
        for junk in (None, 12, ["a"], {"b": 1}):
            with self.assertRaises(ValueError):
                mission_engine.set_behaves(junk)

    def test_06_junk_on_disk_reads_as_empty_never_raises(self):
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"behaves": 42}))
        self.assertEqual(mission_engine.behaves(), "")
        Path(mission_engine.limits_path()).write_text("{not json")
        self.assertEqual(mission_engine.behaves(), "")

    def test_07_clearing_stores_empty(self):
        mission_engine.set_behaves(TEXT)
        self.assertEqual(mission_engine.set_behaves(""), "")
        self.assertEqual(mission_engine.behaves(), "")


class TestTheBoot(Base):

    def test_10_the_text_rides_the_boot_context_under_its_heading(self):
        mission_engine.set_behaves(TEXT)
        ctx = shadow_session.standing_context()
        self.assertIn("HOW SHADOW BEHAVES", ctx)
        self.assertIn(TEXT, ctx)
        self.assertIn("STANDING INSTRUCTIONS", ctx,
                      "the block the text joins is still there")

    def test_11_empty_text_adds_nothing(self):
        ctx = shadow_session.standing_context()
        self.assertNotIn("HOW SHADOW BEHAVES", ctx)

    def test_12_a_broken_limits_read_never_erases_standing_instructions(self):
        shadow_ledger.append("instructions", {
            "text": "always answer in one line", "precedence": "d_ledger",
            "confirmed": True, "scope": "global"})
        orig = mission_engine._read_limits

        def boom():
            raise OSError("limits unreadable")

        mission_engine._read_limits = boom
        try:
            ctx = shadow_session.standing_context()
        finally:
            mission_engine._read_limits = orig
        self.assertIn("STANDING INSTRUCTIONS", ctx)
        self.assertIn("always answer in one line", ctx)
        self.assertNotIn("HOW SHADOW BEHAVES", ctx)

    def test_13_precedence_line_names_what_outranks_it(self):
        mission_engine.set_behaves(TEXT)
        ctx = shadow_session.standing_context()
        head = ctx[ctx.index("HOW SHADOW BEHAVES"):]
        self.assertIn("floors", head[:400])
        self.assertIn("task", head[:400])


class TestTheRoute(Base):

    def test_20_get_reports_the_text_and_the_ceiling(self):
        mission_engine.set_behaves(TEXT)
        doc = self.client.get("/api/shadow/settings", headers=HDR).json()
        self.assertEqual(doc["behaves"], TEXT)
        self.assertEqual(doc["behaves_max"], mission_engine.BEHAVES_MAX_CHARS)

    def test_21_post_writes_and_echoes(self):
        r = self.client.post(ROUTE, json={"behaves": TEXT}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["behaves"], TEXT)
        self.assertEqual(mission_engine.behaves(), TEXT)

    def test_22_post_refuses_a_missing_key_and_a_non_string(self):
        r = self.client.post(ROUTE, json={}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(ROUTE, json={"behaves": 7}, headers=HDR)
        self.assertEqual(r.status_code, 400)

    def test_23_post_is_ledgered_as_a_setting(self):
        self.client.post(ROUTE, json={"behaves": TEXT}, headers=HDR)
        acts = shadow_ledger.read("actions", 10)
        self.assertTrue(any(a.get("kind") == "setting"
                            and "behaves" in (a.get("summary") or "")
                            for a in acts), acts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
