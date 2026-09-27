"""test_website_motor.py -- the motor and the line, in plain unittest.

test_website_dept.py is the full suite and needs pytest. This file is the part
that must also run where pytest is not installed: the release pipelines, and
above all the Windows one, where the motor's lock takes a different path
(msvcrt, not fcntl) that no Mac can exercise.

Run: python test_website_motor.py
"""
import importlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

REF = "dref-motor0001"
GOAL = "A website for City Care Hospital: departments, doctors, how to book."


class TestTheMotor(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="website-motor-")
        self.prior = {k: os.environ.get(k) for k in ("SUTRA_NATIVE_DEPT_HOME", "SUTRA_WEBSITE_OFFLINE")}
        os.environ["SUTRA_NATIVE_DEPT_HOME"] = self.home
        os.environ["SUTRA_WEBSITE_OFFLINE"] = "1"
        import website_dept
        self.W = importlib.reload(website_dept)

    def tearDown(self):
        self.W.stop_motor()
        for k, v in self.prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    def test_1_one_motor_per_record_and_the_next_takes_over(self):
        W = self.W
        self.assertTrue(W.hold_motor(), "the first app is the motor")
        self.assertTrue(W.hold_motor(), "and stays it")
        first = W._LOCK["fd"]
        W._LOCK["fd"] = None                       # a second app on the same record
        try:
            self.assertFalse(W.hold_motor(), "the second may not tick")
        finally:
            W._LOCK["fd"] = first
        W.stop_motor()                             # the first closes
        self.assertTrue(W.hold_motor(), "and the next takes over")

    def test_2_the_line_runs_to_the_first_publish_ask_then_publishes_on_a_stamp(self):
        W = self.W
        W.create(REF, "City Care Hospital Website", None)
        self.assertEqual(W.due(REF)[2], "nothing due")
        W.give_goal(REF, GOAL)
        self.assertEqual(W.run_until_idle(REF), 3)
        asks = W.status(REF)["asks"]
        self.assertEqual([a["kind"] for a in asks], ["publish"])
        W.decide_ask(REF, asks[0]["id"], True)
        self.assertEqual(W.run_until_idle(REF), 1)
        self.assertTrue((W.live_dir(REF) / "index.html").is_file())
        self.assertEqual(W.run_until_idle(REF), 0, "a slot never runs twice")

    def test_3_an_ask_grows_the_site_and_put_back_takes_it_away_again(self):
        W = self.W
        W.create(REF, "City Care Hospital Website", None)
        W.give_goal(REF, GOAL)
        W.run_until_idle(REF)
        W.decide_ask(REF, W.status(REF)["asks"][0]["id"], True)
        W.run_until_idle(REF)
        W.owner_ask(REF, "Add a Careers page")
        self.assertEqual(W.run_until_idle(REF), 4)
        self.assertTrue((W.live_dir(REF) / "careers.html").is_file())
        W.put_back(REF, "Live site", 1)
        self.assertFalse((W.live_dir(REF) / "careers.html").exists())
        states = {c["name"]: c["state"] for c in W.health(REF)["checks"]}
        self.assertEqual((states["Slots"], states["Versions"]), ("ok", "ok"))

    def test_4_a_run_cut_off_by_a_closed_app_runs_once_more(self):
        W = self.W
        W.create(REF, "City Care Hospital Website", None)
        W.give_goal(REF, GOAL)
        name, inp, slot = W.due(REF)
        W._put_run(REF, {"id": "r-cut", "engine": name, "system": False, "slot": slot, "status": "running",
                         "started": W.now(), "ended": None, "what": "reading", "wrote": None, "chain": None,
                         "spend": {"calls": 0, "usd": 0.0}, "retries": 0})
        self.assertTrue(W.hold_motor())            # the app reopens: the motor recovers
        rows = [r for r in W.runs(REF) if r.get("slot") == slot]
        self.assertEqual([r["status"] for r in rows], ["interrupted"])
        W.run_until_idle(REF)
        rows = [r for r in W.runs(REF) if r.get("slot") == slot]
        self.assertEqual([r["status"] for r in rows], ["interrupted", "ok"])
        self.assertEqual(rows[1]["retries"], 1)


class TestWhoMayStartIt(unittest.TestCase):
    """Found 2026-09-28: a lane of the release gates started the app, the app
    started the motor, and the motor took its lock in the operator's live
    home. These are the three things that were missing."""
    KEYS = ("SUTRA_NATIVE_DEPT_HOME", "SUTRA_WEBSITE_OFFLINE", "SUTRA_MOTOR", "SUTRA_MOTOR_OFF",
            "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS")

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="website-motor-")
        self.prior = {k: os.environ.get(k) for k in self.KEYS}
        for k in self.KEYS:
            os.environ.pop(k, None)
        os.environ["SUTRA_NATIVE_DEPT_HOME"] = self.home
        os.environ["SUTRA_WEBSITE_OFFLINE"] = "1"
        import website_dept
        self.W = importlib.reload(website_dept)

    def tearDown(self):
        self.W.stop_motor()
        for k, v in self.prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    def test_5_the_motor_starts_on_the_launchers_word_and_no_other(self):
        W = self.W
        self.assertTrue(W.under_test(), "this process is a test, and the detector says so")
        self.assertFalse(W.start_motor(), "no word, no motor")
        os.environ["SUTRA_MOTOR"] = "1"
        self.assertFalse(W.start_motor(), "the word inside a test process is not the word")
        self.assertIsNone(W._MOTOR["thread"])
        self.assertFalse(os.path.exists(os.path.join(self.home, "motor.lock")), "and nothing was touched")
        W.under_test = lambda: False                # the app itself
        W.TICK_S = 0.05
        os.environ["SUTRA_MOTOR_OFF"] = "1"
        self.assertFalse(W.start_motor(), "the off switch outranks the word")
        os.environ.pop("SUTRA_MOTOR_OFF")
        self.assertTrue(W.start_motor(), "the app, with the word: the motor starts")
        self.assertFalse(W.start_motor(), "once")
        self.assertTrue(self.until(lambda: os.path.isfile(os.path.join(self.home, "motor.json"))),
                        "and it ticks in the home it was started for")
        thread = W._MOTOR["thread"]
        W.stop_motor()
        self.assertFalse(thread.is_alive(), "stopped means stopped: nothing ticks after stop_motor returns")
        self.assertIsNone(W._LOCK["fd"], "and the record is let go")

    def test_8_a_running_motor_never_follows_the_environment_to_another_home(self):
        # The fault this file's own first draft had: a motor thread outlived its
        # test's temp home, the environment moved on, and the thread landed on
        # the operator's live home in 5 runs of 30.
        W = self.W
        W.under_test = lambda: False
        W.TICK_S = 0.05
        os.environ["SUTRA_MOTOR"] = "1"
        other = tempfile.mkdtemp(prefix="website-motor-other-")
        try:
            self.assertTrue(W.start_motor())
            self.assertTrue(self.until(lambda: os.path.isfile(os.path.join(self.home, "motor.json"))))
            thread = W._MOTOR["thread"]
            os.environ["SUTRA_NATIVE_DEPT_HOME"] = other
            self.assertTrue(self.until(lambda: not thread.is_alive()), "the home moved: the motor stops")
            self.assertEqual(os.listdir(other), [], "and it never touched the other home")
        finally:
            os.environ["SUTRA_NATIVE_DEPT_HOME"] = self.home
            W.stop_motor()
            shutil.rmtree(other, ignore_errors=True)

    @staticmethod
    def until(cond, wait_s=3.0):
        import time
        end = time.time() + wait_s
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.01)
        return bool(cond())

    def test_6_a_test_may_not_touch_the_live_records_home(self):
        W = self.W
        os.environ.pop("SUTRA_NATIVE_DEPT_HOME")
        with self.assertRaises(RuntimeError):
            W.home()
        with self.assertRaises(RuntimeError):
            W.hold_motor()
        os.environ["SUTRA_NATIVE_DEPT_HOME"] = ""   # set and empty is still the default
        with self.assertRaises(RuntimeError):
            W.home()
        os.environ["SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS"] = "1"
        # As paths, not as text: Windows writes the same folder with the other slash.
        self.assertEqual(W.home(), Path(os.path.expanduser("~/.sutra-ui/native")), "unless it says so, by name")

    def test_7_every_launcher_says_the_word_and_the_beta_has_its_own_home(self):
        here = os.path.dirname(os.path.abspath(__file__))
        if not os.path.isfile(os.path.join(here, "electron", "main.js")):
            self.skipTest("the shell's source is not beside this file (a packaged payload)")
        main = open(os.path.join(here, "electron", "main.js"), encoding="utf-8").read()
        self.assertIn('SUTRA_MOTOR: "1"', main[main.index("function startBackend()"):])
        beta = main[main.index("function betaEnv()"):]
        beta = beta[:beta.index("\n}\n")]
        self.assertIn('SUTRA_NATIVE_DEPT_HOME: path.join(ui, "native")', beta)
        for launcher in ("run.sh", "sutra-ui.sh", "install.sh"):
            text = open(os.path.join(here, launcher), encoding="utf-8").read()
            self.assertIn("SUTRA_MOTOR=1", text, launcher)
        dept = open(os.path.join(here, "website_dept.py"), encoding="utf-8").read()
        self.assertIn('os.environ.get("SUTRA_NATIVE_DEPT_HOME", "~/.sutra-ui/native")', dept,
                      "the form test_channel_isolation.py can see")


if __name__ == "__main__":
    unittest.main(verbosity=1)
