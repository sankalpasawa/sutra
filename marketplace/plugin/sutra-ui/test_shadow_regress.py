"""The Shadow regression gate's own rules (shadow_regress.py).

A failure that was there before is known; one that was not is a regression;
a file new since the baseline must pass outright; a test that stopped
failing is reported as fixed. And it finds the files it is meant to guard.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_regress.py
"""
import os
import tempfile
import unittest

import shadow_regress as sr


def res(**files):
    return {"files": {k: {"failed": v} for k, v in files.items()}}


class Compare(unittest.TestCase):
    def test_01_a_known_failure_is_not_a_regression(self):
        d = sr.compare(res(a=["a::t1"]), res(a=["a::t1"]))
        self.assertEqual(d["regressed"], [])
        self.assertEqual(d["known"], ["a::t1"])

    def test_02_a_new_failure_is(self):
        d = sr.compare(res(a=["a::t1"]), res(a=["a::t1", "a::t2"]))
        self.assertEqual(d["regressed"], ["a::t2"])

    def test_03_a_new_file_must_pass_outright(self):
        d = sr.compare(res(a=[]), res(a=[], b=["b::t1"]))
        self.assertEqual(d["new_files_failing"], ["b::t1"])
        self.assertEqual(d["regressed"], [])

    def test_04_fixed_is_reported(self):
        d = sr.compare(res(a=["a::t1"]), res(a=[]))
        self.assertEqual(d["fixed"], ["a::t1"])

    def test_05_a_file_not_run_this_time_is_not_judged(self):
        d = sr.compare(res(a=["a::t1"], b=["b::t9"]), res(a=["a::t1"]))
        self.assertEqual(d, {"regressed": [], "new_files_failing": [],
                             "fixed": [], "known": ["a::t1"]})


class Discover(unittest.TestCase):
    def test_10_it_finds_the_shadow_files_and_their_neighbours(self):
        root = tempfile.mkdtemp(prefix="regress-")
        files = {
            "test_shadow_x.py": "import unittest\n",
            "test_engine.py": "import mission_engine\n",
            "test_other.py": "import json\n",
            "test_shadow_y.js": "",
            "test_goal.js": 'read("static/js/16-shadow-home.js")',
            "test_misc.js": "",
            "helper.py": "import mission_engine\n",
        }
        for name, body in files.items():
            with open(os.path.join(root, name), "w") as fh:
                fh.write(body)
        py, js = sr.discover(root)
        self.assertEqual(py, ["test_engine.py", "test_shadow_x.py"])
        self.assertEqual(js, ["test_goal.js", "test_shadow_y.js"])

    def test_11_the_real_folder_includes_todays_tests(self):
        py, js = sr.discover()
        for f in ("test_shadow_costs.py", "test_shadow_tap.py",
                  "test_mission_engine.py"):
            self.assertIn(f, py)
        for f in ("test_shadow_costs.js", "test_shadow_tap.js"):
            self.assertIn(f, js)
        self.assertNotIn("test_shadow_regress.py", py,
                         "the gate does not run itself")


if __name__ == "__main__":
    unittest.main()
