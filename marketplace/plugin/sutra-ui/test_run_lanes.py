"""The developer lanes run what they report (PRD-FIVE-FUNCTIONS M0.1, SM-2).

run-tests.sh ran every test file as a script. A file with no __main__ block defines its tests and calls none of them,
so its lane said PASS over nothing: eleven such files, test_j2.py among them. These tests hold the runner to its word:
a pytest lane prints pytest's own count, a broken assert is a FAIL, a lane that collects nothing is a FAIL, and the
department suite runs the J1 and J2 tests.

The lanes are run in a copy of the runner beside a throwaway test file, never by breaking a real one.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run-tests.sh"
SUITES = HERE / "qa" / "walks" / "suites.sh"
# the files that had no __main__ block when M0.1 was built; each must now report a count above 0
NO_MAIN = ["test_chat_archive.py", "test_chat_search.py", "test_dept_api.py", "test_function_templates.py", "test_j1.py",
           "test_j2.py", "test_j2_api.py", "test_library_api.py", "test_session_list_memo.py", "test_skill_categories.py",
           "test_update_swap_nesting.py"]


def _run(runner, *lanes):
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    got = subprocess.run(["bash", str(runner), *lanes], capture_output=True, text=True, env=env, timeout=600)
    return got.returncode, got.stdout + got.stderr


def _tests_in(path):
    return len(re.findall(r"^\s*(?:async\s+)?def test_", Path(path).read_text(), re.M))


@pytest.fixture
def lab(tmp_path):
    """A copy of the runner, the app's interpreter beside it, and room for a test file of the test's own."""
    shutil.copy(RUNNER, tmp_path / "run-tests.sh")
    if (HERE / ".venv").exists():
        os.symlink(HERE / ".venv", tmp_path / ".venv")
    return tmp_path


def test_a_lane_with_no_main_block_runs_under_pytest_and_prints_its_count():
    """`./run-tests.sh test_j2.py` printing PASS with no count, as it did over nothing, must fail."""
    code, out = _run(RUNNER, "test_j2.py")
    assert code == 0, out
    line = next(l for l in out.splitlines() if l.startswith("test_j2.py"))
    assert re.search(r"PASS\s+%d passed$" % _tests_in(HERE / "test_j2.py"), line), line


def test_a_broken_assert_is_a_failed_lane(lab):
    (lab / "test_broken.py").write_text("def test_one():\n    assert 1 == 2\n")
    code, out = _run(lab / "run-tests.sh", "test_broken.py")
    assert code == 1 and re.search(r"test_broken\.py\s+FAIL", out), out


def test_a_lane_that_collects_nothing_is_a_failed_lane(lab):
    """pytest's exit 5: a class pytest cannot collect leaves the file with no test to run."""
    (lab / "test_empty.py").write_text("class TestNothing:\n    def __init__(self):\n        pass\n\n    def test_one(self):\n        pass\n")
    code, out = _run(lab / "run-tests.sh", "test_empty.py")
    assert code == 1 and "FAIL  no tests collected" in out, out


def test_a_main_block_lane_and_a_plain_script_lane_keep_their_own_counts(lab):
    (lab / "test_unit.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n\n"
                                      "if __name__ == '__main__':\n    unittest.main()\n")
    (lab / "test_plain.py").write_text("N = 3\nprint('%d checks, 0 failed' % N)\n")
    code, out = _run(lab / "run-tests.sh", "test_unit.py", "test_plain.py")
    assert code == 0, out
    assert re.search(r"test_unit\.py\s+PASS\s+Ran 1 test$", out, re.M), out
    assert re.search(r"test_plain\.py\s+PASS\s+3 checks$", out, re.M), out


def test_every_file_with_no_main_block_reports_a_count_above_zero():
    """Each of the eleven reports how much it ran, whether it passes or not: a lane that ran nothing must fail."""
    code, out = _run(RUNNER, *NO_MAIN)
    blocks = re.split(r"^(?=test_\S+\.py\s)", out, flags=re.M)
    for name in NO_MAIN:
        block = next((b for b in blocks if b.startswith(name)), "")
        counts = [int(n) for n in re.findall(r"(\d+) (?:passed|checks)", block)]
        assert counts and counts[0] > 0, (name, block[:400])


def test_the_department_suite_runs_the_j1_and_j2_tests_and_a_red_one_reds_it():
    """A suite that leaves J1 and J2 out, or prints their result without letting it fail the run, must fail."""
    text = SUITES.read_text()
    line = next((l for l in text.splitlines() if "test_j2.py" in l and "pytest" in l), "")
    for name in ("test_j2.py", "test_j2_api.py", "test_j1.py"):
        assert name in line, line
    assert line.lstrip().startswith("lane ") and line.rstrip().endswith("|| RC=1"), line
