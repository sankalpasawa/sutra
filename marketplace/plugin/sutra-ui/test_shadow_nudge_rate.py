""""Nudges per hour" -- the durable Presence rate, end to end.

The row in Shadow Settings > Presence drew a stepper whose buttons were
aria-disabled and carried no action hook, printing the JS constant
SH_PILLS_PER_HOUR. It was honest about being inert -- "Stated, not settable:
there is no writer" -- and it was still a number the founder could not move.
This lane is the store that changed that, at the levels it has to be true at
or it is not a setting at all:

  STORE      shadow_presence.nudges_per_hour() prefers a persisted value over
             the default, CLAMPS an out-of-band number, REFUSES junk rather
             than coercing it, and NEVER raises -- a corrupt file must cost
             the founder their chosen rate, not their Presence.

  ZERO       0 is a stored value meaning "never unasked", not an absent one.
             Every layer here is checked for the falsy-is-unset bug, which is
             the one way a rate of 0 silently becomes a rate of 3.

  RESTART    the claim the row makes is that the number survives quitting the
             app. That is asserted in a SUBPROCESS, not in this interpreter --
             the same distinction test_shadow_run_limit.py:128 draws, and for
             the same reason: every in-process test would still pass if the
             value were cached in a module global that happened to be warm.

  ROUTE      GET /api/shadow/settings reports the live value and its band (the
             overlay's boot awaits THIS payload, so it must be there); POST
             /api/shadow/settings/presence writes it, moves exactly one field
             per request, refuses junk, and is gated like every other Shadow
             write.

Run: ./run-tests.sh test_shadow_nudge_rate.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-nudge-test-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import json_store                              # noqa: E402
import providers                               # noqa: E402
import shadow_presence                         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
PRESENCE = "/api/shadow/settings/presence"
SETTINGS = "/api/shadow/settings"
HERE = os.path.dirname(os.path.abspath(__file__))


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

    def test_01_unset_is_the_default(self):
        """An install nobody has configured enforces the rate the code always
        enforced -- and the file is not created merely by asking."""
        self.assertEqual(shadow_presence.nudges_per_hour(), 3)
        self.assertEqual(shadow_presence.NUDGES_PER_HOUR_DEFAULT, 3)
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "a READ must not create the store")

    def test_02_set_then_read_across_a_fresh_resolver(self):
        """Persistence, not memory: the value is read back off disk, which is
        what makes it survive a reload."""
        self.assertEqual(shadow_presence.set_nudges_per_hour(7), 7)
        self.assertEqual(shadow_presence.nudges_per_hour(), 7)
        self.assertEqual(
            json_store.read_json(shadow_presence.presence_path(), {}),
            {"nudges_per_hour": 7})

    def test_03_zero_is_a_value_not_an_absence(self):
        """THE FALSY BUG, PINNED. 0 means "never interrupt me unasked" and is
        a real stored setting. A reader written as `raw or DEFAULT` turns it
        back into 3, which is the loudest possible misreading of the quietest
        possible request -- so both the round-trip and the on-disk shape are
        asserted."""
        self.assertEqual(shadow_presence.set_nudges_per_hour(0), 0)
        self.assertEqual(shadow_presence.nudges_per_hour(), 0)
        self.assertEqual(
            json_store.read_json(shadow_presence.presence_path(), {})
            .get("nudges_per_hour"), 0)

    def test_04_out_of_band_numbers_clamp(self):
        """A stepper held past an end stops at the end rather than erroring --
        clamp_running's rule, which this mirrors."""
        self.assertEqual(shadow_presence.set_nudges_per_hour(99),
                         shadow_presence.MAX_NUDGES_PER_HOUR)
        self.assertEqual(shadow_presence.set_nudges_per_hour(-4),
                         shadow_presence.MIN_NUDGES_PER_HOUR)
        self.assertEqual(shadow_presence.MIN_NUDGES_PER_HOUR, 0)

    def test_05_junk_is_refused_not_guessed(self):
        """A write that cannot be understood says so. Storing 3 because the
        caller sent "three" is worse than refusing it."""
        for bad in ("three", None, [], {}, "", object()):
            with self.assertRaises(ValueError, msg="accepted %r" % (bad,)):
                shadow_presence.clamp_nudges(bad)

    def test_06_a_boolean_is_junk_here(self):
        """WHERE THIS PARTS COMPANY WITH clamp_running. int(True) is 1, so a
        client that sent a switch's value onto the stepper's field would
        silently store "one an hour" and look like it worked."""
        for bad in (True, False):
            with self.assertRaises(ValueError):
                shadow_presence.clamp_nudges(bad)

    def test_07_a_corrupt_store_costs_the_default_not_an_exception(self):
        """This is read inside the settings GET the overlay's boot awaits."""
        Path(shadow_presence.presence_path()).write_text("{not json")
        self.assertEqual(shadow_presence.nudges_per_hour(), 3)
        json_store.write_json(shadow_presence.presence_path(),
                              {"nudges_per_hour": "loud"})
        self.assertEqual(shadow_presence.nudges_per_hour(), 3,
                         "a hand-edited junk value costs itself, not a raise")

    def test_08_the_other_presence_keys_survive_a_rate_write(self):
        """Three keys share presence.json, so every writer read-modify-writes.
        Setting a rate must not clear the standing choice or the hide list --
        and setting those must not clear the rate."""
        shadow_presence.set_corner_card(False)
        shadow_presence.set_app_hidden("photo-gallery", True)
        shadow_presence.set_nudges_per_hour(1)
        self.assertIs(shadow_presence.corner_card(), False)
        self.assertEqual(shadow_presence.hidden_apps(), ["photo-gallery"])
        self.assertEqual(shadow_presence.nudges_per_hour(), 1)
        shadow_presence.set_corner_card(True)
        self.assertEqual(shadow_presence.nudges_per_hour(), 1,
                         "a corner-card write erased the rate")

    def test_09_the_store_lives_under_the_shadow_home(self):
        """Redirecting the Shadow home redirects this too -- which is what
        keeps a test from writing a preference into the live install."""
        self.assertEqual(
            os.path.realpath(os.path.dirname(shadow_presence.presence_path())),
            os.path.realpath(self.tmp.name))
        self.assertTrue(
            shadow_presence.presence_path().endswith("presence.json"))


# ---------------------------------------------------------------- RESTART --
class TestItSurvivesARestart(Base):

    def test_10_a_separate_process_reads_back_what_the_route_wrote(self):
        """THE RELOAD-AND-RESTART CLAIM, ASSERTED RATHER THAN CLICKED.

        test_02 proves the value survives a fresh RESOLVER; this proves it
        survives a fresh INTERPRETER, which is what "restart the app" means.
        The distinction is not pedantic: every in-process test above would
        still pass if the rate were cached in a module global that happened to
        be warm, and that cache is exactly the bug a founder would meet as "I
        set it to 1 and after a restart it was 3 again".

        So the write goes through the ROUTE -- the stepper's own endpoint --
        and the read happens in a subprocess that shares nothing with this one
        but the directory on disk.
        """
        r = self.client.post(PRESENCE, json={"nudges_per_hour": 1}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)

        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = HERE
        out = subprocess.run(
            [sys.executable, "-c",
             "import shadow_presence; print(shadow_presence.nudges_per_hour())"],
            capture_output=True, text=True, env=env, cwd=HERE, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        self.assertEqual(out.stdout.strip(), "1",
                         "a new process must read the founder's rate off disk, "
                         "not fall back to the default (stderr: %s)"
                         % out.stderr[-200:])

    def test_11_zero_survives_a_restart_too(self):
        """The falsy case again, across the boundary that matters. A founder
        who asked for silence must not be spoken to by the next launch."""
        r = self.client.post(PRESENCE, json={"nudges_per_hour": 0}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = HERE
        out = subprocess.run(
            [sys.executable, "-c",
             "import shadow_presence; print(shadow_presence.nudges_per_hour())"],
            capture_output=True, text=True, env=env, cwd=HERE, timeout=60)
        self.assertEqual(out.stdout.strip(), "0", out.stderr[-200:])


# ------------------------------------------------------------------ ROUTE --
class TestTheRoute(Base):

    def test_12_the_settings_get_reports_the_rate_and_its_band(self):
        """The overlay's boot awaits this payload and the browser keeps no
        default of its own, so the number and the ends it may be moved between
        both have to be here."""
        shadow_presence.set_nudges_per_hour(6)
        r = self.client.get(SETTINGS, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()["presence"]
        self.assertEqual(p["nudges_per_hour"], 6)
        self.assertEqual(p["nudges_per_hour_min"],
                         shadow_presence.MIN_NUDGES_PER_HOUR)
        self.assertEqual(p["nudges_per_hour_max"],
                         shadow_presence.MAX_NUDGES_PER_HOUR)

    def test_13_the_route_stores_and_answers_with_the_stored_value(self):
        """The answer is what the row repaints from, so a clamped write must
        come back clamped rather than echoing what was sent."""
        r = self.client.post(PRESENCE, json={"nudges_per_hour": 99},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["nudges_per_hour"],
                         shadow_presence.MAX_NUDGES_PER_HOUR)
        self.assertEqual(body["min"], shadow_presence.MIN_NUDGES_PER_HOUR)
        self.assertEqual(body["max"], shadow_presence.MAX_NUDGES_PER_HOUR)
        self.assertEqual(shadow_presence.nudges_per_hour(),
                         shadow_presence.MAX_NUDGES_PER_HOUR)

    def test_14_one_write_moves_one_field(self):
        """Two settings reach the founder through this route, and a body must
        name exactly one of them. Both is a 400 and neither is a 400 -- what a
        write can move stays a constant per request, so the answer the client
        repaints from is never a partial one."""
        r = self.client.post(PRESENCE,
                             json={"corner_card": False, "nudges_per_hour": 2},
                             headers=HDR)
        self.assertEqual(r.status_code, 400, r.text)
        r = self.client.post(PRESENCE, json={}, headers=HDR)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(shadow_presence.nudges_per_hour(), 3,
                         "a refused write stored something")
        self.assertIs(shadow_presence.corner_card(), True)

    def test_15_the_corner_card_write_still_works_unchanged(self):
        """The sibling setting on this route keeps its own shape and its own
        answer -- adding a second field must not have moved the first."""
        r = self.client.post(PRESENCE, json={"corner_card": False},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"corner_card": False})
        self.assertIs(shadow_presence.corner_card(), False)

    def test_16_junk_is_a_400_and_stores_nothing(self):
        for bad in ("three", None, True, [2]):
            r = self.client.post(PRESENCE, json={"nudges_per_hour": bad},
                                 headers=HDR)
            self.assertEqual(r.status_code, 400,
                             "accepted %r: %s" % (bad, r.text))
        self.assertEqual(shadow_presence.nudges_per_hour(), 3)

    def test_17_the_write_is_gated_like_every_other_shadow_write(self):
        providers.SETTINGS_PATH.write_text(json.dumps({"shadow.enabled": False}))
        r = self.client.post(PRESENCE, json={"nudges_per_hour": 1}, headers=HDR)
        self.assertEqual(r.status_code, 403, r.text)
        self.assertEqual(shadow_presence.nudges_per_hour(), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
