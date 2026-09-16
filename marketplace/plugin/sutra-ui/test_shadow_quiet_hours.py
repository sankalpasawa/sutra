""""Quiet hours" -- the durable Presence window, end to end.

The row in Shadow Settings > Presence printed the literal string "not set" and
carried no action hook, and the settings page said why in its own comment:
"QUIET HOURS has nothing behind it -- no field, no clock, no scheduler". This
lane is the feature that replaced that, at the levels it has to be true at or
it is not a setting at all:

  STORE      shadow_presence.quiet_hours() prefers a persisted window over
             None, REFUSES a malformed one rather than coercing it, survives a
             restart, and NEVER raises -- a hand-edited file must cost the
             founder their quiet hours, not their Presence. Clearing DELETES
             the key, so "cleared" and "never set" are one state on disk.

  CLOCK      window_active() is the whole rule: inclusive start, exclusive
             end, and it WRAPS MIDNIGHT. It is driven here from
             test_quiet_hours_cases.json -- the same table test_shadow_home.js
             runs against the JS twin (shadowQuietWindowNow in
             static/js/15-shadow-overlay.js). The rule is written twice
             because the client cannot round-trip per pill; the shared table
             is what stops the two copies drifting.

  ROUTE      GET /api/shadow/settings reports the window and the server's
             reading of it; POST /api/shadow/settings/quiet-hours writes it,
             clears it on an explicit null, refuses junk and a missing field,
             and is gated like every other Shadow write.

Run: ./run-tests.sh test_shadow_quiet_hours.py
"""
import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-quiet-test-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import providers                               # noqa: E402
import shadow_presence                         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
QUIET = "/api/shadow/settings/quiet-hours"
PRESENCE = "/api/shadow/settings/presence"

#: THE SHARED CASE TABLE. Read from disk rather than written inline, because
#: test_shadow_home.js reads this same file: one table, two lanes, no drift.
#: Adding a case here adds it to both at once -- which is the point, and the
#: reason not to inline "just one more" case in either lane.
CASES = json.loads(
    (Path(__file__).parent / "test_quiet_hours_cases.json").read_text())


def _at(hhmm):
    """A datetime standing at a wall-clock time. The date is arbitrary and
    deliberately not today: the rule reads .hour/.minute only, and pinning a
    fixed date is what keeps this lane from passing or failing by the hour it
    happens to be run at."""
    h, m = hhmm.split(":")
    return datetime.datetime(2026, 3, 17, int(h), int(m))


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

    def test_01_unset_is_none_and_creates_nothing(self):
        """An install nobody has configured has no quiet hours -- and asking
        must not be what creates the file.

        A READ THAT WRITES is how an unconfigured install stops being
        distinguishable from a configured one, and this store's whole
        clear-is-a-delete design rests on that distinction holding.
        """
        self.assertIsNone(shadow_presence.quiet_hours())
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "reading an unset window created the store")

    def test_02_round_trip(self):
        """What is set is what comes back, in the canonical shape."""
        out = shadow_presence.set_quiet_hours({"start": "21:00",
                                               "end": "08:00"})
        self.assertEqual(out, {"start": "21:00", "end": "08:00"})
        self.assertEqual(shadow_presence.quiet_hours(),
                         {"start": "21:00", "end": "08:00"})

    def test_03_on_disk_shape(self):
        """The file holds the window under its own key, beside its siblings
        rather than instead of them."""
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        raw = json.loads(Path(shadow_presence.presence_path()).read_text())
        self.assertEqual(raw["quiet_hours"],
                         {"start": "21:00", "end": "08:00"})

    def test_04_change_replaces_rather_than_merges(self):
        """Changing the window is a replacement, not a patch: a founder who
        moved the start has not kept the old one."""
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        shadow_presence.set_quiet_hours({"start": "22:30", "end": "06:15"})
        self.assertEqual(shadow_presence.quiet_hours(),
                         {"start": "22:30", "end": "06:15"})

    def test_05_clear_deletes_the_key(self):
        """CLEAR IS A DELETE, not a stored null and not a 00:00-00:00
        sentinel.

        This is the founder's own instruction and it is also the store's own
        rule (QUIET_HOURS_DEFAULT): an install whose founder cleared the
        window must be byte-identical to one that never set it, so there is
        exactly one shape that reads back as "not set". A sentinel would give
        "cleared" a second spelling, and every reader downstream -- the GET,
        the row, the gate -- would have to know both.
        """
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        self.assertIsNone(shadow_presence.set_quiet_hours(None))
        self.assertIsNone(shadow_presence.quiet_hours())
        raw = json.loads(Path(shadow_presence.presence_path()).read_text())
        self.assertNotIn("quiet_hours", raw,
                         "clearing left a sentinel behind: %r" % (raw,))

    def test_06_read_modify_write_keeps_the_siblings(self):
        """Four settings share presence.json. Setting one must not cost the
        other three -- in BOTH directions, since either could be written
        second."""
        shadow_presence.set_corner_card(False)
        shadow_presence.set_nudges_per_hour(7)
        shadow_presence.set_app_hidden("photo-gallery", True)
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        self.assertIs(shadow_presence.corner_card(), False)
        self.assertEqual(shadow_presence.nudges_per_hour(), 7)
        self.assertEqual(shadow_presence.hidden_apps(), ["photo-gallery"])
        # and now the other direction: a sibling write must not eat the window
        shadow_presence.set_corner_card(True)
        shadow_presence.set_nudges_per_hour(2)
        self.assertEqual(shadow_presence.quiet_hours(),
                         {"start": "21:00", "end": "08:00"})

    def test_07_clearing_keeps_the_siblings(self):
        """And a CLEAR is a read-modify-write too -- popping one key, not
        truncating the file."""
        shadow_presence.set_corner_card(False)
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        shadow_presence.set_quiet_hours(None)
        self.assertIs(shadow_presence.corner_card(), False,
                      "clearing the window cleared the corner card too")

    def test_08_junk_is_refused_not_guessed(self):
        """Every malformed window in the shared table raises, and none of them
        reaches the disk.

        REFUSING RATHER THAN COERCING is the module's stated line and it
        matters more here than anywhere else in this file: a window stored as
        something other than what was typed silences Shadow at hours the
        founder never chose -- by definition, hours when they are not watching
        it happen and cannot notice.
        """
        for case in CASES["invalid"]:
            with self.subTest(why=case["why"]):
                with self.assertRaises(ValueError):
                    shadow_presence.clean_quiet_hours(case["value"])
                with self.assertRaises(ValueError):
                    shadow_presence.set_quiet_hours(case["value"])
        self.assertFalse(os.path.exists(shadow_presence.presence_path()),
                         "a refused write still created the store")

    def test_09_start_equal_end_is_refused(self):
        """Called out on its own because it is the case with two honest
        readings -- zero-length, or all day -- and no way to tell them apart.
        The founder who wants silence that never lifts has a control that says
        so: nudges per hour at 0."""
        with self.assertRaises(ValueError) as cm:
            shadow_presence.clean_quiet_hours({"start": "22:00",
                                               "end": "22:00"})
        self.assertIn("differ", str(cm.exception))

    def test_10_a_corrupt_store_costs_the_window_not_the_read(self):
        """NEVER RAISES. A hand-edited file degrades to "no quiet hours", and
        the direction is deliberate: degrading this way means Shadow SPEAKS
        when it was unsure, which the founder can see and correct. Degrading
        the other way is silence they have no way to notice."""
        path = Path(shadow_presence.presence_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        for junk in ('{not json',
                     '{"quiet_hours": 7}',
                     '{"quiet_hours": {"start": "9pm", "end": "x"}}',
                     '{"quiet_hours": {"start": "21:00"}}',
                     '{"quiet_hours": {"start": "22:00", "end": "22:00"}}',
                     '{"quiet_hours": ["21:00", "08:00"]}'):
            with self.subTest(junk=junk):
                path.write_text(junk)
                self.assertIsNone(shadow_presence.quiet_hours())
                self.assertIs(shadow_presence.quiet_now(), False)

    def test_11_extra_keys_are_dropped_not_stored(self):
        """A client echoing back a richer payload is not punished for it, but
        nothing unrecognised reaches the disk."""
        out = shadow_presence.set_quiet_hours(
            {"start": "21:00", "end": "08:00", "enabled": True})
        self.assertEqual(out, {"start": "21:00", "end": "08:00"})
        raw = json.loads(Path(shadow_presence.presence_path()).read_text())
        self.assertEqual(set(raw["quiet_hours"]), {"start", "end"})

    def test_12_the_store_lives_under_the_shadow_home(self):
        """So a test that redirects the home redirects this too, and can never
        write a window into the operator's install."""
        self.assertTrue(
            os.path.realpath(shadow_presence.presence_path()).startswith(
                os.path.realpath(self.tmp.name)),
            shadow_presence.presence_path())

    def test_13_survives_a_full_process_restart(self):
        """THE CLAIM THE WHOLE FEATURE RESTS ON, and the only test here that
        can actually prove it.

        Every other assertion in this class could pass against a value cached
        in a module global that happened to be warm -- which is exactly the
        bug a founder meets as "I set my quiet hours and after a restart
        Shadow was talking at 3am again". So the write goes through the ROUTE
        the control actually uses, and the read happens in a subprocess
        sharing nothing with this one but the directory on disk.
        """
        r = self.client.post(QUIET, headers=HDR, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}})
        self.assertEqual(r.status_code, 200, r.text)

        import subprocess
        import sys
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            [sys.executable, "-c",
             "import json, shadow_presence;"
             " print(json.dumps(shadow_presence.quiet_hours()))"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)), timeout=60)
        self.assertEqual(out.returncode, 0,
                         "the fresh process could not read the window: %s"
                         % out.stderr[-400:])
        self.assertEqual(json.loads(out.stdout.strip()),
                         {"start": "21:00", "end": "08:00"},
                         "a new process must read the founder's window off "
                         "disk (stderr: %s)" % out.stderr[-200:])

    def test_14_a_clear_survives_a_full_process_restart_too(self):
        """Clearing is a write like any other, and it has the same claim to
        prove. A clear that only held in memory would leave the founder
        silenced by a window they had already deleted."""
        self.client.post(QUIET, headers=HDR, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}})
        r = self.client.post(QUIET, headers=HDR, json={"quiet_hours": None})
        self.assertEqual(r.status_code, 200, r.text)

        import subprocess
        import sys
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            [sys.executable, "-c",
             "import json, shadow_presence;"
             " print(json.dumps(shadow_presence.quiet_hours()))"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)), timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        self.assertIsNone(json.loads(out.stdout.strip()),
                          "a cleared window came back after a restart")


# ------------------------------------------------------------------ CLOCK --
class TestTheClock(Base):
    """The wrap-around rule, driven from the table the JS lane also runs."""

    def test_30_the_shared_case_table(self):
        """ONE RULE, TWO IMPLEMENTATIONS, one table. Every row of
        test_quiet_hours_cases.json runs here and in test_shadow_home.js
        against shadowQuietWindowNow, so the Python and JS copies cannot drift
        apart without a lane going red."""
        self.assertTrue(CASES["active"], "the shared table is empty")
        for case in CASES["active"]:
            window = CASES["windows"][case["window"]]
            with self.subTest(window=case["window"], at=case["at"],
                              why=case["why"]):
                self.assertIs(
                    shadow_presence.window_active(window, _at(case["at"])),
                    case["quiet"], case["why"])

    def test_31_the_table_covers_the_cases_that_matter(self):
        """A table both lanes trust has to be worth trusting. This pins the
        four cases the rule is actually hard at, so a future edit cannot
        quietly delete the coverage rather than fix the code."""
        wrap = [c for c in CASES["active"] if c["window"] == "wrap"]
        ats = {c["at"] for c in wrap}
        for needed in ("21:00", "00:00", "07:59", "08:00"):
            self.assertIn(needed, ats,
                          "the shared table lost the %s case" % needed)
        self.assertTrue(
            any(c["value"] == {"start": "10:00", "end": "10:00"}
                for c in CASES["invalid"]),
            "the shared table lost the start == end case")

    def test_32_unset_is_never_quiet(self):
        self.assertIs(shadow_presence.window_active(None, _at("03:00")), False)
        self.assertIs(shadow_presence.quiet_now(_at("03:00")), False)

    def test_33_quiet_now_reads_the_stored_window(self):
        """quiet_now is window_active over whatever is on disk -- one rule,
        not a second one that happens to agree."""
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        self.assertIs(shadow_presence.quiet_now(_at("23:30")), True)
        self.assertIs(shadow_presence.quiet_now(_at("09:00")), False)

    def test_34_only_the_wall_clock_is_read(self):
        """The window names a TIME OF DAY, not an instant: the same hour on a
        different date answers the same. That is what makes it survive a date
        change, and it is also why no timezone is stored."""
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        for day in (1, 15, 31):
            self.assertIs(
                shadow_presence.quiet_now(
                    datetime.datetime(2026, 12, day, 23, 30)), True)


# ------------------------------------------------------------------ ROUTE --
class TestTheRoute(Base):

    def test_50_get_reports_null_when_unset(self):
        r = self.client.get("/api/shadow/settings", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        pres = r.json()["presence"]
        self.assertIsNone(pres["quiet_hours"])
        self.assertIs(pres["quiet_now"], False)

    def test_51_get_reports_the_window_beside_its_siblings(self):
        """The window joins the presence block without displacing anything --
        the overlay's boot reads this same payload for three other keys."""
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        pres = self.client.get("/api/shadow/settings",
                               headers=HDR).json()["presence"]
        self.assertEqual(pres["quiet_hours"],
                         {"start": "21:00", "end": "08:00"})
        for sibling in ("corner_card", "hidden_apps", "nudges_per_hour"):
            self.assertIn(sibling, pres,
                          "the window displaced %s" % sibling)

    def test_52_post_writes_and_answers_with_what_was_stored(self):
        r = self.client.post(QUIET, headers=HDR, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["quiet_hours"],
                         {"start": "21:00", "end": "08:00"})
        self.assertIn("quiet_now", body)
        self.assertIsInstance(body["quiet_now"], bool)
        self.assertEqual(shadow_presence.quiet_hours(),
                         {"start": "21:00", "end": "08:00"})

    def test_53_post_null_clears(self):
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        r = self.client.post(QUIET, headers=HDR, json={"quiet_hours": None})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["quiet_hours"])
        self.assertIs(r.json()["quiet_now"], False)
        self.assertIsNone(shadow_presence.quiet_hours())

    def test_54_clearing_twice_is_fine(self):
        """The gesture is "make it so", not "toggle": a second clear is a
        founder confirming a state, not an error."""
        for _ in range(2):
            r = self.client.post(QUIET, headers=HDR,
                                 json={"quiet_hours": None})
            self.assertEqual(r.status_code, 200, r.text)

    def test_55_a_missing_field_is_a_400_not_a_clear(self):
        """ABSENT IS NOT NULL. `{"quiet_hours": null}` is the founder pressing
        clear; a body with no quiet_hours key at all is a client bug. Treating
        absence as a clear would let a malformed request silently delete the
        setting, which is the one failure a settings route must not have.
        """
        shadow_presence.set_quiet_hours({"start": "21:00", "end": "08:00"})
        for body in ({}, {"start": "21:00", "end": "08:00"},
                     {"corner_card": False}):
            with self.subTest(body=body):
                r = self.client.post(QUIET, headers=HDR, json=body)
                self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(shadow_presence.quiet_hours(),
                         {"start": "21:00", "end": "08:00"},
                         "a refused write moved the setting")

    def test_56_junk_is_a_400_in_the_stores_own_words(self):
        """The clamp is in the store and the route hands its sentence back --
        a hand-written POST is not an <input type=time>, so the browser's
        restraint is not the thing being relied on."""
        for case in CASES["invalid"]:
            with self.subTest(why=case["why"]):
                r = self.client.post(QUIET, headers=HDR,
                                     json={"quiet_hours": case["value"]})
                self.assertEqual(r.status_code, 400, r.text)
        self.assertIsNone(shadow_presence.quiet_hours())

    def test_57_the_presence_route_still_refuses_a_window(self):
        """The two routes stay separate. /settings/presence holds itself to
        exactly one of corner_card / nudges_per_hour, and a window is neither
        -- so it is a 400 there and nothing is written."""
        r = self.client.post(PRESENCE, headers=HDR, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIsNone(shadow_presence.quiet_hours())

    def test_58_the_write_is_ledgered(self):
        """A settings write leaves a trail, and the summary names the window
        rather than saying something changed."""
        import shadow_ledger
        self.client.post(QUIET, headers=HDR, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}})
        rows = [r for r in shadow_ledger.read_latest("actions")
                if r.get("kind") == "setting"]
        self.assertTrue(any("21:00" in (r.get("summary") or "")
                            and "08:00" in (r.get("summary") or "")
                            for r in rows),
                        "no ledger row named the window: %r" % (rows[-3:],))

    def test_59_the_clear_is_ledgered_as_a_clear(self):
        import shadow_ledger
        self.client.post(QUIET, headers=HDR, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}})
        self.client.post(QUIET, headers=HDR, json={"quiet_hours": None})
        rows = [r for r in shadow_ledger.read_latest("actions")
                if r.get("kind") == "setting"]
        self.assertTrue(any("cleared" in (r.get("summary") or "")
                            for r in rows),
                        "a clear left no trail: %r" % (rows[-3:],))

    def test_60_the_flag_gates_the_write(self):
        """Every Shadow write is gated the same way, and this one is not an
        exception because it looks like a view preference."""
        Path(providers.SETTINGS_PATH).write_text(
            json.dumps({"shadow.enabled": False}))
        r = self.client.post(QUIET, headers=HDR, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}})
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIsNone(shadow_presence.quiet_hours())

    def test_61_the_panel_token_is_required(self):
        """The CSRF guard every other settings write sits behind."""
        r = self.client.post(QUIET, json={
            "quiet_hours": {"start": "21:00", "end": "08:00"}},
            headers={"Origin": "http://evil.example"})
        self.assertIn(r.status_code, (400, 401, 403), r.text)
        self.assertIsNone(shadow_presence.quiet_hours())


if __name__ == "__main__":
    unittest.main(verbosity=1)
