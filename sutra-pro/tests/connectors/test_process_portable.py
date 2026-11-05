"""The process runner on a REAL child, on every system (D101): what the fake claude and codex cannot show on Windows.

The fakes are POSIX shell wrappers (tests/fakes), so on Windows their tests skip; these tests use the Python interpreter as the child
and say what the runner promises on any system: lines, stdin, an environment that is exactly the allowlist (which on Windows must
still be enough for a program to start), UTF-8, a timeout that ends the child AND what it started, and the lookup of a program the
way the system's own shell would (a `.cmd` shim from npm on Windows).
"""
import os
import signal
import sys
import textwrap
import time
from pathlib import Path

import pytest

from sutra_app import oslayer
from sutra_app.connectors.env import child_env
from sutra_app.connectors.errors import CliMissingError
from sutra_app.connectors.process import LADDER, Command, ProcessRunner

FAST = ((signal.SIGINT, 0.6), (signal.SIGTERM, 0.6), (oslayer.SIGKILL, 3.0))


def command(code: str, cwd: Path, *, stdin: str | None = None, extra: dict[str, str] | None = None) -> Command:
    return Command(argv=(sys.executable, "-c", code), cwd=str(cwd), env=child_env("test", extra), stdin_text=stdin)


def wait_until(predicate, seconds=15.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_a_child_prints_lines_and_ends_with_exit_zero(tmp_path):
    seen = []
    info = ProcessRunner().run(command("print('one'); print('two')", tmp_path), on_line=seen.append, timeout_s=60)
    assert seen == ["one", "two"] and info.ok and info.reason == "exit" and info.returncode == 0


def test_stdin_text_reaches_the_child_and_utf8_comes_back_whole(tmp_path):
    code = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read() + '\\n'.encode())"
    seen = []
    ProcessRunner().run(command(code, tmp_path, stdin="héllo → ✓ and a über line"), on_line=seen.append, timeout_s=60)
    assert seen == ["héllo → ✓ and a über line"], "the bytes of a model's output are decoded as UTF-8 whatever the console's code page is"


def test_the_environment_is_exactly_the_allowlist_plus_extra(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-for-the-child")
    monkeypatch.setenv("SUTRA_TOKEN", "not-for-the-child")
    monkeypatch.setenv("SOME_RANDOM_THING", "nor-this")
    code = "import os, json; print(json.dumps(sorted(os.environ)))"
    seen = []
    ProcessRunner().run(command(code, tmp_path, extra={"MARKER_FOR_THE_TEST": "1"}), on_line=seen.append, timeout_s=60)
    import json
    names = {name.upper() for name in json.loads(seen[0])}
    assert "MARKER_FOR_THE_TEST" in names and "PATH" in names
    assert not names & {"ANTHROPIC_API_KEY", "SUTRA_TOKEN", "SOME_RANDOM_THING"}
    if oslayer.IS_WINDOWS:
        assert "SYSTEMROOT" in names, "without it Python and Node do not start properly on Windows"


FAMILY = textwrap.dedent("""
    import subprocess, sys, time
    grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    print(grandchild.pid, flush=True)
    time.sleep(120)
""")


def test_a_total_timeout_ends_the_child_and_what_it_started(tmp_path):
    runner = ProcessRunner(ladder=FAST)
    with runner.start(command(FAMILY, tmp_path), timeout_s=2.0) as proc:
        grandchild = int(next(iter(proc.lines())))
        assert oslayer.pid_alive(grandchild)
        info = proc.wait()
    assert info.reason == "total_timeout" and not info.ok
    assert wait_until(lambda: not oslayer.pid_alive(grandchild)), "no orphans: the grandchild ends with the tree"


def test_a_cancel_ends_the_child_and_what_it_started(tmp_path):
    runner = ProcessRunner(ladder=FAST)
    with runner.start(command(FAMILY, tmp_path)) as proc:
        grandchild = int(next(iter(proc.lines())))
        assert proc.cancel() is True
        info = proc.wait()
    assert info.reason == "cancelled"
    assert wait_until(lambda: not oslayer.pid_alive(grandchild))


def test_a_silent_child_is_ended_by_the_idle_timeout(tmp_path):
    runner = ProcessRunner(ladder=FAST)
    info = runner.run(command("import time; time.sleep(60)", tmp_path), idle_timeout_s=1.0)
    assert info.reason == "idle_timeout"


def test_stop_all_ends_every_live_child(tmp_path):
    runner = ProcessRunner(ladder=FAST)
    proc = runner.start(command("import time; time.sleep(60)", tmp_path))
    assert runner.live() == [proc] or runner.live()
    assert runner.stop_all() >= 1
    assert proc.wait().reason in ("cancelled", "exit", "idle_timeout", "total_timeout")


def test_a_program_that_is_not_there_is_a_cli_missing_error(tmp_path):
    with pytest.raises(CliMissingError):
        ProcessRunner().start(Command(argv=("sutra-pro-no-such-program-anywhere",), cwd=str(tmp_path), env=child_env("test")), timeout_s=5)


def test_the_default_ladder_is_the_one_the_system_can_follow():
    names = [oslayer.signal_name(sig) for sig, _ in LADDER]
    if oslayer.IS_WINDOWS:
        assert names == ["SIGTERM", "SIGKILL"], "no interrupt step for a child that has no console"
    else:
        assert names == ["SIGINT", "SIGTERM", "SIGKILL"]


@pytest.mark.skipif(not oslayer.IS_WINDOWS, reason="a .cmd shim is how npm installs a command on Windows")
def test_a_cmd_shim_is_found_through_pathext_the_way_the_shell_finds_it(tmp_path):
    """CreateProcess alone would find `claude.exe` and never `claude.cmd`; the runner resolves the name on the child's PATH first."""
    shim = tmp_path / "fakeclaude.cmd"
    shim.write_bytes(f'@echo off\r\n"{sys.executable}" -c "print(\'from the shim\')"\r\n'.encode("ascii"))
    env = child_env("test", {})
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    seen = []
    info = ProcessRunner().run(Command(argv=("fakeclaude",), cwd=str(tmp_path), env=env), on_line=seen.append, timeout_s=60)
    assert seen == ["from the shim"] and info.ok
