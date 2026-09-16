"""test_shadow_presence.py -- "Hide for this app": Presence, per app, durable.

  CLAIM      Enabling it hides the Shadow Presence dot for the app the founder
             has open; disabling it restores it; and the choice survives a
             reload AND a full app restart.

  STORE      shadow_presence.py over <shadow_home>/presence.json, the same
             json_store + shadow_home pattern mission_engine's task-limits.json
             and delegate-offers.json use.

  ROUTE      GET /api/shadow/settings reports presence.hidden_apps and
             GET /api/shadow/status reports presence_hidden_apps; POST
             /api/shadow/settings/presence/app writes one app per call with a
             verb body ({"hide": id} / {"show": id}), refuses junk, refuses
             both verbs at once, and ledgers the write.

WHAT USED TO BE HERE, AND WHY IT IS NOT: the row flipped S.shadowQuiet, the
nudge mute. The label named one thing, the switch did another, and the other
died at reload. test_shadow_home.js pinned that wiring; that assertion is
rewritten alongside this lane rather than kept, because it encoded the defect.

THE ID IS SHAPE-CHECKED, NOT EXISTENCE-CHECKED -- see the route docstring in
app.py. test_14 pins the shape rule against modules_api's own, so the copy of
the pattern in shadow_presence cannot drift away from the folder names it is
supposed to describe.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-presence-test-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import providers                               # noqa: E402
import shadow_presence                         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
APP = "/api/shadow/settings/presence/app"
SETTINGS = "/api/shadow/settings"
STATUS = "/api/shadow/status"


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

    def presence(self):
        r = self.client.get(SETTINGS, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["presence"]


# ------------------------------------------------------------------ STORE --
class TestTheStore(Base):

    def test_01_unset_is_hidden_nowhere(self):
        self.assertEqual(shadow_presence.hidden_apps(), [])
        self.assertFalse(shadow_presence.app_hidden("photo-gallery"))

    def test_02_a_read_does_not_create_the_file(self):
        """An install nobody has configured must be byte-identical to one
        from before this setting existed."""
        shadow_presence.hidden_apps()
        shadow_presence.app_hidden("photo-gallery")
        self.assertFalse(os.path.exists(shadow_presence.presence_path()))

    def test_03_set_then_read_survives_a_fresh_resolver(self):
        shadow_presence.set_app_hidden("photo-gallery", True)
        self.assertEqual(shadow_presence.hidden_apps(), ["photo-gallery"])
        self.assertTrue(shadow_presence.app_hidden("photo-gallery"))
        # the value is on disk, not in a module global
        self.assertEqual(
            json.loads(Path(shadow_presence.presence_path()).read_text()),
            {"hidden_apps": ["photo-gallery"]})

    def test_04_unhiding_removes_the_entry(self):
        """DISABLING CLEARS IT, rather than storing a false. A list whose
        members mean "hidden" has no use for an entry meaning "not hidden",
        and keeping one would make hidden_apps() answer wrongly to anything
        that read membership instead of the value."""
        shadow_presence.set_app_hidden("photo-gallery", True)
        left = shadow_presence.set_app_hidden("photo-gallery", False)
        self.assertEqual(left, [])
        self.assertEqual(
            json.loads(Path(shadow_presence.presence_path()).read_text()),
            {"hidden_apps": []})
        self.assertFalse(shadow_presence.app_hidden("photo-gallery"))

    def test_05_one_app_does_not_hide_another(self):
        """THE WHOLE POINT OF PER-APP. If this ever fails the setting has
        quietly become the corner-card switch."""
        shadow_presence.set_app_hidden("photo-gallery", True)
        self.assertTrue(shadow_presence.app_hidden("photo-gallery"))
        self.assertFalse(shadow_presence.app_hidden("recipe-box"))
        shadow_presence.set_app_hidden("recipe-box", True)
        self.assertEqual(shadow_presence.hidden_apps(),
                         ["photo-gallery", "recipe-box"])
        shadow_presence.set_app_hidden("photo-gallery", False)
        self.assertEqual(shadow_presence.hidden_apps(), ["recipe-box"])

    def test_06_hiding_twice_is_not_two_entries(self):
        shadow_presence.set_app_hidden("photo-gallery", True)
        self.assertEqual(shadow_presence.set_app_hidden("photo-gallery", True),
                         ["photo-gallery"])
        # and showing something never hidden is not an error
        self.assertEqual(shadow_presence.set_app_hidden("recipe-box", False),
                         ["photo-gallery"])

    def test_07_junk_raises_rather_than_being_sanitised(self):
        for bad in ("", "   ", None, 5, "Photo-Gallery", "../escape",
                    "-leading", "x", "a" * 42, "has space"):
            with self.assertRaises(ValueError, msg="accepted %r" % (bad,)):
                shadow_presence.set_app_hidden(bad, True)
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "a refused write must write nothing")

    def test_08_a_junk_id_is_never_hidden_and_never_raises(self):
        """app_hidden is asked on the mount path for whatever the client had
        open; every string needs an answer, and a bad one's answer is no."""
        self.assertFalse(shadow_presence.app_hidden("../escape"))
        self.assertFalse(shadow_presence.app_hidden(None))
        self.assertFalse(shadow_presence.app_hidden(""))

    def test_09_a_corrupt_file_costs_the_list_not_the_dot(self):
        Path(shadow_presence.presence_path()).write_text("{not json")
        self.assertEqual(shadow_presence.hidden_apps(), [])
        self.assertFalse(shadow_presence.app_hidden("photo-gallery"))

    def test_10_a_hand_edited_junk_entry_costs_only_itself(self):
        Path(shadow_presence.presence_path()).write_text(json.dumps(
            {"hidden_apps": ["photo-gallery", "../escape", 7, "recipe-box"]}))
        self.assertEqual(shadow_presence.hidden_apps(),
                         ["photo-gallery", "recipe-box"])

    def test_11_a_wrong_shaped_key_degrades(self):
        Path(shadow_presence.presence_path()).write_text(
            json.dumps({"hidden_apps": "photo-gallery"}))
        self.assertEqual(shadow_presence.hidden_apps(), [])

    def test_12_the_two_keys_in_this_file_do_not_clobber_each_other(self):
        """corner_card and hidden_apps share presence.json. Every writer
        read-modify-writes the whole dict; if one ever stops, the founder
        loses a setting they did not touch."""
        shadow_presence.set_corner_card(False)
        shadow_presence.set_app_hidden("photo-gallery", True)
        self.assertIs(shadow_presence.corner_card(), False)
        self.assertEqual(shadow_presence.hidden_apps(), ["photo-gallery"])
        shadow_presence.set_corner_card(True)
        self.assertEqual(shadow_presence.hidden_apps(), ["photo-gallery"],
                         "a corner-card write erased the per-app hides")
        shadow_presence.set_app_hidden("photo-gallery", False)
        self.assertIs(shadow_presence.corner_card(), True,
                      "a per-app write erased the corner-card choice")

    def test_13_a_separate_process_reads_back_what_was_written(self):
        """THE RESTART CLAIM, ASSERTED RATHER THAN CLICKED.

        test_03 proves the value survives a fresh RESOLVER; this proves it
        survives a fresh INTERPRETER, which is what "restart the app" means.
        A module-level global or a cached dict would pass test_03 and fail
        here, which is exactly the difference the objective turns on.
        """
        shadow_presence.set_app_hidden("photo-gallery", True)
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            [sys.executable, "-c",
             "import shadow_presence; print(shadow_presence.hidden_apps());"
             " print(shadow_presence.app_hidden('photo-gallery'))"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(out.stdout.split("\n")[0].strip(),
                         "['photo-gallery']",
                         "a new process must read the founder's hide list off "
                         "disk (stderr: %s)" % out.stderr[-300:])
        self.assertEqual(out.stdout.split("\n")[1].strip(), "True")

    def test_14_the_id_rule_matches_the_one_apps_validate_with(self):
        """shadow_presence copies modules_api.ID_RE rather than importing it
        (modules_api pulls FastAPI + placement_engine; this store is imported
        by a bare interpreter above). A copy is fine; a copy that DRIFTS is
        not -- an id the Apps registry accepts must be storable here."""
        import modules_api
        self.assertEqual(shadow_presence._APP_ID.pattern,
                         modules_api.ID_RE.pattern)
        self.assertIsInstance(shadow_presence._APP_ID, type(re.compile("")))


# ------------------------------------------------------------------ ROUTE --
class TestTheRoute(Base):

    def test_30_post_writes_what_the_settings_read_reports(self):
        """The whole feature in one assertion: the route writes, and the page
        that draws the switch reads back what was written."""
        r = self.client.post(APP, json={"hide": "photo-gallery"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["hidden_apps"], ["photo-gallery"])
        self.assertIs(r.json()["hidden"], True)
        self.assertEqual(r.json()["app_id"], "photo-gallery")
        self.assertEqual(self.presence()["hidden_apps"], ["photo-gallery"])

    def test_31_show_removes_it_again(self):
        self.client.post(APP, json={"hide": "photo-gallery"}, headers=HDR)
        r = self.client.post(APP, json={"show": "photo-gallery"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIs(r.json()["hidden"], False)
        self.assertEqual(r.json()["hidden_apps"], [])
        self.assertEqual(self.presence()["hidden_apps"], [])

    def test_32_the_status_route_reports_it_too(self):
        """The overlay's boot reads settings, but status is the Shadow read
        that answers with nothing else attached, and it must not disagree."""
        self.client.post(APP, json={"hide": "photo-gallery"}, headers=HDR)
        r = self.client.get(STATUS, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["presence_hidden_apps"], ["photo-gallery"])
        self.assertEqual(r.json()["presence_hidden_apps"],
                         self.presence()["hidden_apps"])

    def test_33_an_unconfigured_install_reports_an_empty_list(self):
        self.assertEqual(self.presence()["hidden_apps"], [])
        self.assertEqual(
            self.client.get(STATUS, headers=HDR).json()["presence_hidden_apps"],
            [])

    def test_34_junk_and_missing_verbs_are_refused(self):
        for body in ({}, {"hide": ""}, {"hide": "../escape"},
                     {"hide": "Photo-Gallery"}, {"show": None},
                     {"hidden_apps": ["photo-gallery"]},
                     {"app_id": "photo-gallery", "hidden": True}):
            r = self.client.post(APP, json=body, headers=HDR)
            self.assertEqual(r.status_code, 400, "accepted %r: %s"
                             % (body, r.text))
        self.assertEqual(self.presence()["hidden_apps"], [],
                         "a refused write must store nothing")

    def test_35_both_verbs_at_once_is_refused_rather_than_ordered(self):
        r = self.client.post(APP, json={"hide": "photo-gallery",
                                        "show": "recipe-box"}, headers=HDR)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("not both", r.text)
        self.assertEqual(self.presence()["hidden_apps"], [])

    def test_36_one_route_one_field_the_corner_card_is_untouched(self):
        """The sibling route owns corner_card and this one must not move it
        -- the two settings answer different questions."""
        self.client.post("/api/shadow/settings/presence",
                         json={"corner_card": False}, headers=HDR)
        self.client.post(APP, json={"hide": "photo-gallery"}, headers=HDR)
        p = self.presence()
        self.assertIs(p["corner_card"], False)
        self.assertEqual(p["hidden_apps"], ["photo-gallery"])

    def test_37_the_write_is_ledgered_as_a_setting(self):
        import shadow_ledger
        self.client.post(APP, json={"hide": "photo-gallery"}, headers=HDR)
        rows = [r for r in shadow_ledger.read("actions")
                if r.get("kind") == "setting"]
        self.assertTrue(any("photo-gallery" in (r.get("summary") or "")
                            for r in rows),
                        "no ledger row named the app that was hidden: %s"
                        % rows[-3:])

    def test_38_the_flag_off_refuses(self):
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": False}))
        r = self.client.post(APP, json={"hide": "photo-gallery"}, headers=HDR)
        self.assertEqual(r.status_code, 403, r.text)

    def test_39_a_browser_origin_without_the_panel_token_is_refused(self):
        r = self.client.post(APP, json={"hide": "photo-gallery"},
                             headers={"Origin": "http://127.0.0.1:8330"})
        self.assertIn(r.status_code, (401, 403), r.text)
        self.assertEqual(self.presence()["hidden_apps"], [])


if __name__ == "__main__":
    unittest.main()
