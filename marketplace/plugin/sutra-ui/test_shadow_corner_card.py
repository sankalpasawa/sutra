""""Corner card on every screen" -- the durable Presence setting, end to end.

The row in Shadow Settings > Presence was a switch with nothing behind it. It
flipped S.shadowHideSession -- a browser-lifetime flag -- so turning the card
off and reloading brought it straight back. The settings page said so in its
own comment: "memory-only ... this does not make them durable and does not
pretend to". This lane is the store that changed that, at the levels it has to
be true at or it is not a setting at all:

  STORE      shadow_presence.corner_card() prefers a persisted value over the
             default, refuses a non-boolean rather than coercing it, survives
             a restart, and NEVER raises -- a corrupt file must cost the
             founder their preference, not their only way to reach Shadow.

  SEPARATION the standing choice is not the session dismissal and not the
             per-app hide. Three different questions -- "at all", "not right
             now", "not on this app" -- sharing one file and never one key.

  ROUTE      GET /api/shadow/settings reports the live value (the overlay's
             boot awaits THIS payload, so it must be there); POST
             /api/shadow/settings/presence writes it, refuses junk, and is
             gated like every other Shadow write.

Run: ./run-tests.sh test_shadow_corner_card.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-card-test-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import providers                               # noqa: E402
import shadow_presence                         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
PRESENCE = "/api/shadow/settings/presence"


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


# ------------------------------------------------------------------ STORE --
class TestTheStore(Base):

    def test_01_unset_is_shown(self):
        """An install nobody has configured shows the card -- and the file is
        not created merely by asking.

        THE DEFAULT IS NOT NEUTRAL. The dot is how a founder reaches Shadow
        at all, so an absent key must mean shown; defaulting the other way
        would hide the entry point on every fresh install.
        """
        self.assertIs(shadow_presence.corner_card(), True)
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "a READ must not create the store")

    def test_02_set_then_read_across_a_fresh_resolver(self):
        """Persistence, not memory: the value is read back off disk, which is
        what makes it survive a reload."""
        self.assertIs(shadow_presence.set_corner_card(False), False)
        self.assertIs(shadow_presence.corner_card(), False)
        on_disk = json.loads(Path(shadow_presence.presence_path()).read_text())
        self.assertIs(on_disk["corner_card"], False)

    def test_03_it_goes_back_on(self):
        """The setting is a switch, not a one-way door."""
        shadow_presence.set_corner_card(False)
        self.assertIs(shadow_presence.set_corner_card(True), True)
        self.assertIs(shadow_presence.corner_card(), True)

    def test_04_junk_is_refused_not_guessed(self):
        """A write that cannot be understood says so.

        0, "false" and "off" are the dangerous ones: each has an obvious
        coercion, and each would store the OPPOSITE of what some caller
        meant. None of them may be guessed at.
        """
        for junk in (0, 1, "true", "false", "off", "", None, [], {}, "yes"):
            with self.assertRaises(ValueError, msg=repr(junk)):
                shadow_presence.set_corner_card(junk)
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "a refused write must leave no file behind")

    def test_05_a_corrupt_store_costs_the_default_not_an_exception(self):
        """corner_card() is answered inside the settings GET that the
        overlay's boot awaits. It degrades."""
        Path(shadow_presence.presence_path()).write_text("{not json")
        self.assertIs(shadow_presence.corner_card(), True)
        Path(shadow_presence.presence_path()).write_text(
            json.dumps({"corner_card": "banana"}))
        self.assertIs(shadow_presence.corner_card(), True)

    def test_06_the_hide_list_in_the_same_file_survives_a_write(self):
        """Read-modify-write. presence.json holds two unrelated Presence
        answers -- the standing choice and the per-app hide list -- and
        moving one must not clear the other, in either order."""
        shadow_presence.set_app_hidden("photo-gallery", True)
        shadow_presence.set_corner_card(False)
        self.assertEqual(shadow_presence.hidden_apps(), ["photo-gallery"])
        self.assertIs(shadow_presence.corner_card(), False)

        shadow_presence.set_app_hidden("photo-gallery", False)
        self.assertIs(shadow_presence.corner_card(), False,
                      "a hide write must not clear the standing choice")

    def test_07_the_store_lives_under_the_shadow_home(self):
        """Redirecting the home redirects the preference -- the property that
        keeps a test from writing a choice into the operator's install."""
        self.assertTrue(
            os.path.realpath(shadow_presence.presence_path()).startswith(
                os.path.realpath(self.tmp.name) + os.sep))

    def test_08_a_separate_process_reads_back_what_the_route_wrote(self):
        """THE RESTART CLAIM, ASSERTED RATHER THAN CLICKED.

        test_02 proves the value survives a fresh RESOLVER; this proves it
        survives a fresh INTERPRETER, which is what "quit and relaunch the
        app" means. The distinction is not pedantic: every in-process test
        here would still pass if the answer were cached in a module global
        that happened to be warm, and that cache is exactly the bug a founder
        would meet as "I turned it off and after a restart it was back".

        So the write goes through the ROUTE the switch actually uses, and the
        read happens in a subprocess sharing nothing with this one but the
        directory on disk.
        """
        r = self.client.post(PRESENCE, json={"corner_card": False},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)

        import subprocess
        import sys
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            [sys.executable, "-c",
             "import shadow_presence; print(shadow_presence.corner_card())"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)), timeout=60)
        self.assertEqual(out.returncode, 0,
                         "the fresh process could not even read the setting: "
                         "%s" % out.stderr[-400:])
        self.assertEqual(out.stdout.strip(), "False",
                         "a new process must read the founder's choice off "
                         "disk, not fall back to the default (stderr: %s)"
                         % out.stderr[-200:])


# ------------------------------------------------------------- SEPARATION --
class TestTheThreeQuestions(Base):
    """"At all", "not right now" and "not on this app" are three questions.
    One flag answering two of them is the bug this feature replaced."""

    def test_20_the_standing_choice_is_not_the_per_app_hide(self):
        """Hiding the card on one app must not turn the setting off."""
        shadow_presence.set_app_hidden("photo-gallery", True)
        self.assertIs(shadow_presence.corner_card(), True,
                      "a per-app hide is not a standing choice")
        self.assertTrue(shadow_presence.app_hidden("photo-gallery"))

    def test_21_the_standing_choice_does_not_hide_any_app(self):
        """And turning the setting off is not a hide on every app: it is a
        different answer, kept in a different key, so turning it back on
        restores exactly the hide list that was there before."""
        shadow_presence.set_app_hidden("photo-gallery", True)
        shadow_presence.set_corner_card(False)
        shadow_presence.set_corner_card(True)
        self.assertEqual(shadow_presence.hidden_apps(), ["photo-gallery"])

    def test_22_the_session_dismissal_is_never_stored(self):
        """The card's own hide control lives in the browser for one page
        load. The server has never known it and must not start: nothing in
        the store may encode it."""
        shadow_presence.set_corner_card(False)
        on_disk = json.loads(Path(shadow_presence.presence_path()).read_text())
        self.assertEqual(set(on_disk), {"corner_card"},
                         "only the standing choice was written")


# ------------------------------------------------------------------ ROUTE --
class TestTheRoute(Base):

    def test_30_the_get_reports_the_live_value(self):
        """The overlay's boot awaits THIS payload before it may mount, so the
        value has to be on it -- a presence GET of its own would make that
        two round-trips to learn one boolean."""
        r = self.client.get("/api/shadow/settings", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIs(r.json()["presence"]["corner_card"], True)

        shadow_presence.set_corner_card(False)
        r = self.client.get("/api/shadow/settings", headers=HDR)
        self.assertIs(r.json()["presence"]["corner_card"], False,
                      "the GET must report the stored value, not the default")

    def test_31_the_post_writes_and_answers_with_what_was_stored(self):
        """The switch repaints from this answer, never the optimistic value."""
        r = self.client.post(PRESENCE, json={"corner_card": False},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIs(r.json()["corner_card"], False)
        self.assertIs(shadow_presence.corner_card(), False)

    def test_32_post_refuses_junk_and_a_missing_field(self):
        for body in ({}, {"corner_card": "off"}, {"corner_card": 0},
                     {"corner_card": None}, {"card": True}):
            r = self.client.post(PRESENCE, json=body, headers=HDR)
            self.assertEqual(r.status_code, 400, "%r -> %s" % (body, r.text))
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "a refused write must leave no file behind")

    def test_33_one_route_one_field(self):
        """The cap route earns its shape by being one route, one field. This
        one keeps it: a body naming another setting moves nothing."""
        self.client.post(PRESENCE, json={"corner_card": False}, headers=HDR)
        r = self.client.post(PRESENCE,
                             json={"corner_card": True, "running_at_once": 19},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("running_at_once", r.json())
        import mission_engine
        self.assertNotEqual(mission_engine.max_running(), 19,
                            "this route must not write a task limit")

    def test_34_the_write_is_ledgered(self):
        """Every Shadow write leaves a row. The summary says which way it
        went, because "presence changed" tells a reader nothing."""
        import shadow_ledger
        self.client.post(PRESENCE, json={"corner_card": False}, headers=HDR)
        rows = shadow_ledger.read_latest("actions")
        said = [r.get("summary", "") for r in rows
                if r.get("kind") == "setting"]
        self.assertTrue(any("corner card" in s and "off" in s for s in said),
                        "no ledger row named the change: %r" % (said[-3:],))

    def test_35_the_route_is_flag_gated_like_every_other_shadow_write(self):
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": False}))
        r = self.client.post(PRESENCE, json={"corner_card": False},
                             headers=HDR)
        self.assertEqual(r.status_code, 403, r.text)

    def test_36_a_cross_origin_write_is_refused_without_the_panel_token(self):
        r = self.client.post(PRESENCE, json={"corner_card": False},
                             headers={"Origin": "http://evil.example"})
        self.assertIn(r.status_code, (400, 401, 403),
                      "an untokened write was accepted: %s" % r.text)
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "a refused write must leave no file behind")


if __name__ == "__main__":
    unittest.main()
