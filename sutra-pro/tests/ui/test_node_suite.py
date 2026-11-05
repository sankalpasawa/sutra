"""Runs every node unit test of the UI (`tests/ui/js/*.test.js`) inside the pytest run, so the merge gate sees them.

The gate runs `pytest` and nothing else for JavaScript under `tests/ui/js`, so this file is what makes a failing
`node --test` file fail a merge (docs/design/ui.md section 10, UI-3). The suite is skipped when `node` is not installed.

`node --test` is always given explicit file paths: a directory argument fails (UI design F14), and with no argument at all
node would search the whole working directory for anything that looks like a test.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS_TESTS = ROOT / "tests" / "ui" / "js"
NODE = shutil.which("node")
MINIMUM_NODE_MAJOR = 20  # node:test is stable from 20
TIMEOUT_S = 120
SUITE_FILES = ("ctx.test.js", "events.test.js")  # UI-3's own; other packages add theirs next to them

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def node_major() -> int:
    out = subprocess.run([NODE, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    match = re.fullmatch(r"v(\d+)\.\d+\.\d+.*", out)
    return int(match.group(1)) if match else 0


def js_test_files(folder: Path = JS_TESTS) -> list[Path]:
    """Every `*.test.js` directly inside `folder`, in name order."""
    return sorted(folder.glob("*.test.js"))


def run_node_tests(files: list[Path], *, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    """`node --test <files>` with the TAP reporter (a stable summary), colours off. Never runs with an empty list."""
    assert files, "no test file to run: node would then search the whole working directory"
    env = {**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0"}
    env.pop("NODE_OPTIONS", None)  # a developer's own flags must not change what the gate runs
    return subprocess.run(
        [NODE, "--test", "--test-reporter=tap", *map(str, files)],
        capture_output=True, text=True, cwd=cwd, env=env, timeout=TIMEOUT_S,
    )


def summary(out: str) -> dict[str, int]:
    return {key: int(value) for key, value in re.findall(r"^# (tests|pass|fail|skipped|cancelled) (\d+)$", out, re.MULTILINE)}


def tail(proc: subprocess.CompletedProcess, limit: int = 6000) -> str:
    text = proc.stdout + proc.stderr
    return text if len(text) <= limit else "...\n" + text[-limit:]


def test_node_is_new_enough_for_the_test_runner():
    assert node_major() >= MINIMUM_NODE_MAJOR, f"node {MINIMUM_NODE_MAJOR} or newer is needed for `node --test`"


def test_the_unit_test_files_of_this_package_exist():
    names = {path.name for path in js_test_files()}
    assert set(SUITE_FILES) <= names, f"missing from {JS_TESTS}: {set(SUITE_FILES) - names}"
    assert all(path.is_file() for path in js_test_files())


def test_every_node_unit_test_passes():
    files = js_test_files()
    proc = run_node_tests(files)
    assert proc.returncode == 0, f"node --test failed:\n{tail(proc)}"
    counts = summary(proc.stdout)
    assert counts.get("tests", 0) > 0, f"node ran no test:\n{tail(proc)}"
    assert counts.get("fail", -1) == 0 and counts.get("cancelled", -1) == 0, tail(proc)


# ------------------------------------------------------------------------------------------------------------------
# The runner itself: it must see a failing file, and it must not run what it was not given
# ------------------------------------------------------------------------------------------------------------------
def write(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


PASSING = 'const test = require("node:test"); test("ok", () => {});\n'
FAILING = 'const test = require("node:test"); const assert = require("node:assert"); test("bad", () => assert.equal(1, 2));\n'


def test_a_passing_file_exits_zero_and_is_counted(tmp_path):
    ok = write(tmp_path, "ok.test.js", PASSING)
    proc = run_node_tests([ok], cwd=tmp_path)
    assert proc.returncode == 0, tail(proc)
    assert summary(proc.stdout).get("tests") == 1


def test_a_failing_file_makes_the_run_fail_even_beside_a_passing_one(tmp_path):
    ok = write(tmp_path, "ok.test.js", PASSING)
    bad = write(tmp_path, "bad.test.js", FAILING)
    proc = run_node_tests([ok, bad], cwd=tmp_path)
    assert proc.returncode != 0
    counts = summary(proc.stdout)
    assert counts.get("fail") == 1 and counts.get("pass") == 1, tail(proc)


def test_a_file_that_cannot_load_is_a_failure_not_a_pass(tmp_path):
    broken = write(tmp_path, "broken.test.js", "this is not javascript (\n")
    assert run_node_tests([broken], cwd=tmp_path).returncode != 0


def test_only_the_given_files_run(tmp_path):
    ok = write(tmp_path, "ok.test.js", PASSING)
    write(tmp_path, "other.test.js", FAILING)  # next to it, but not given
    write(tmp_path / "deep" / "nested", "deeper.test.js", FAILING)
    proc = run_node_tests([ok], cwd=tmp_path)
    assert proc.returncode == 0, tail(proc)


def test_the_runner_refuses_an_empty_list():
    with pytest.raises(AssertionError, match="no test file"):
        run_node_tests([])


def test_the_file_list_holds_only_dot_test_dot_js_files_directly_inside_the_folder(tmp_path):
    write(tmp_path, "b.test.js", PASSING)
    write(tmp_path, "a.test.js", PASSING)
    write(tmp_path, "helper.js", "module.exports = {};\n")
    write(tmp_path, "c.test.mjs", PASSING)
    write(tmp_path / "sub", "d.test.js", PASSING)
    assert [path.name for path in js_test_files(tmp_path)] == ["a.test.js", "b.test.js"]
    assert js_test_files(tmp_path / "missing") == []
