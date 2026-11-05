"""CN-1: the environment allowlist (PASS_NAMES, child_env) and the process runner (connectors design 3.1, 4, 5.4)."""
import os
import re
import signal
import sys
import threading
import time

import pytest

from sutra_app.connectors import env as envmod
from sutra_app.connectors import process as proc
from sutra_app.connectors.env import PASS_NAMES, child_env, is_secret_name
from sutra_app.connectors.errors import CliMissingError, InvalidRequestError, ProviderError
from sutra_app.connectors.process import Command, ExitInfo, ProcessRunner

# ===================================================================================================================
# environment
# ===================================================================================================================

FOREIGN = {
    "ANTHROPIC_API_KEY": "k1", "OPENAI_API_KEY": "k2", "GITHUB_TOKEN": "k3", "CODEX_API_KEY": "k4", "CLAUDECODE": "1",
    "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_CODE_SSE_PORT": "1", "ANTHROPIC_BASE_URL": "http://gw", "OPENAI_BASE_URL": "http://x",
    "SUTRA_TOKEN": "t", "SUTRA_DATA_DIR": "/d", "SHELL": "/bin/zsh", "TERM": "xterm", "PYTHONPATH": "/x", "AWS_SECRET_ACCESS_KEY": "s",
}


def test_allowlist_drops_keys_tokens_claude_code_and_sutra_and_keeps_path_and_home():
    source = {**FOREIGN, "PATH": "/usr/bin", "HOME": "/home/me"}
    got = child_env("claude", environ=source)
    assert got == {"PATH": "/usr/bin", "HOME": "/home/me"}


def test_allowlist_passes_login_dirs_locale_proxy_and_certificates():
    source = {"CLAUDE_CONFIG_DIR": "/c", "CODEX_HOME": "/x", "XDG_CONFIG_HOME": "/xc", "XDG_DATA_HOME": "/xd", "XDG_CACHE_HOME": "/xe",
              "XDG_STATE_HOME": "/xs", "HTTPS_PROXY": "p", "https_proxy": "p2", "NO_PROXY": "n", "no_proxy": "n2", "ALL_PROXY": "a",
              "all_proxy": "a2", "HTTP_PROXY": "h", "http_proxy": "h2", "SSL_CERT_FILE": "/f", "SSL_CERT_DIR": "/d", "LANG": "en",
              "LC_ALL": "C", "LC_CTYPE": "UTF-8", "TMPDIR": "/t", "USER": "u", "LOGNAME": "u"}
    assert child_env("codex", environ=source) == source


def test_child_env_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "/from/process")
    monkeypatch.setenv("OPENAI_API_KEY", "nope")
    got = child_env("codex")
    assert got["CODEX_HOME"] == "/from/process" and "OPENAI_API_KEY" not in got


def test_pass_names_is_a_tuple_with_the_login_directories():
    assert isinstance(PASS_NAMES, tuple) and all(isinstance(n, str) for n in PASS_NAMES)
    assert {"CLAUDE_CONFIG_DIR", "CODEX_HOME", "PATH", "HOME", "XDG_CONFIG_HOME"} <= set(PASS_NAMES)
    assert len(set(PASS_NAMES)) == len(PASS_NAMES)
    assert {"https_proxy", "http_proxy", "no_proxy", "all_proxy"} <= set(PASS_NAMES)


def test_pass_names_holds_no_credential_looking_name():
    assert not [n for n in PASS_NAMES if re.search(r"KEY|TOKEN|SECRET|PASSWORD", n, re.I)]
    assert not [n for n in PASS_NAMES if n.startswith(("SUTRA_", "ANTHROPIC_", "OPENAI_", "CLAUDE_CODE_"))]


def test_child_env_is_built_from_pass_names_and_nothing_else():
    everything = {n: "v" for n in PASS_NAMES}
    assert set(child_env("claude", environ={**everything, **FOREIGN})) == set(PASS_NAMES)
    assert child_env("claude", environ={}) == {}


def test_extra_env_is_added_after_the_allowlist():
    got = child_env("claude", {"ANTHROPIC_BASE_URL": "http://gw", "FAKE_PYTHON": "/py", "HOME": "/override"}, environ={"HOME": "/h"})
    assert got == {"HOME": "/override", "ANTHROPIC_BASE_URL": "http://gw", "FAKE_PYTHON": "/py"}


@pytest.mark.parametrize("name", ["OPENAI_API_KEY", "GITHUB_TOKEN", "x_secret", "DB_PASSWORD", "ApiKey"])
def test_extra_env_secret_names_are_refused(name):
    with pytest.raises(ValueError, match="looks like a secret"):
        child_env("codex", {name: "x"}, environ={})


def test_extra_env_never_passes_sutra_names():
    assert child_env("claude", {"SUTRA_FAKE_PYTHON": "/py", "SUTRA_DATA_DIR": "/d", "FAKE_PYTHON": "/py"}, environ={}) == {"FAKE_PYTHON": "/py"}


@pytest.mark.parametrize("name,value", [("", "x"), ("A=B", "x"), ("A\0B", "x"), ("OK", 5), ("OK", "a\0b")])
def test_extra_env_malformed_entries_are_refused(name, value):
    with pytest.raises(ValueError):
        child_env("claude", {name: value}, environ={})


def test_child_env_needs_a_provider_name():
    with pytest.raises(ValueError, match="provider"):
        child_env("", environ={})


def test_is_secret_name():
    assert is_secret_name("my_token") and is_secret_name("PASSWORD2") and not is_secret_name("CODEX_HOME")
    assert envmod.SECRET_PATTERN.search("x_KEY_y")


# ===================================================================================================================
# process runner
# ===================================================================================================================

FAST = ((signal.SIGINT, 0.6), (signal.SIGTERM, 0.6), (getattr(signal, "SIGKILL", 9), 3.0))


@pytest.fixture
def runner():
    r = ProcessRunner(ladder=FAST)
    yield r
    r.stop_all()


def py(code, tmp_path, stdin=None, env=None, cleanup=(), provider="claude"):
    return Command(argv=(sys.executable, "-u", "-c", code), cwd=str(tmp_path), env=env if env is not None else child_env("claude"),
                   stdin_text=stdin, cleanup=cleanup, provider=provider)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_dead(pid, seconds=4.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


def test_lines_come_through_in_order_and_the_exit_is_clean(runner, tmp_path):
    info = []
    got = []
    with runner.start(py("print('a'); print('b'); print('c')", tmp_path)) as p:
        got = list(p.lines())
        info.append(p.wait())
    assert got == ["a", "b", "c"]
    e = info[0]
    assert (e.returncode, e.reason, e.ladder, e.ok, e.signal_name, e.pid) == (0, "exit", (), True, None, p.pid)
    assert e.seconds >= 0 and e.stderr_tail == ""


def test_run_feeds_on_line_and_returns_the_exit(runner, tmp_path):
    seen = []
    info = runner.run(py("print('x'); print('y')", tmp_path), on_line=seen.append)
    assert seen == ["x", "y"] and info.ok


def test_noise_lines_pass_untouched(runner, tmp_path):
    code = ("import sys\nsys.stdout.buffer.write(b'{\"a\":1}\\n\\nnot json at all\\r\\n\\xff\\xfe bad bytes\\n  {\"b\":2}\\nno newline at end')")
    got = []
    runner.run(py(code, tmp_path), on_line=got.append)
    assert got == ['{"a":1}', "", "not json at all", "\ufffd\ufffd bad bytes", '  {"b":2}', "no newline at end"]


def test_a_nonzero_exit_and_stderr_are_reported(runner, tmp_path):
    info = runner.run(py("import sys; sys.stderr.write('boom\\n'); sys.exit(3)", tmp_path))
    assert (info.returncode, info.reason, info.ok, info.stderr_tail) == (3, "exit", False, "boom\n")


def test_a_child_killed_by_a_signal_reports_it(runner, tmp_path):
    info = runner.run(py("import os, signal; os.kill(os.getpid(), signal.SIGKILL)", tmp_path))
    assert (info.returncode, info.signal_name, info.reason, info.ok) == (-9, "SIGKILL", "exit", False)


def test_stderr_tail_is_capped_but_counts_everything(runner, tmp_path):
    code = "import sys\nfor i in range(200):\n    sys.stderr.write('e' * 999 + '\\n')\nsys.stderr.write('THE-END')"
    info = runner.run(py(code, tmp_path))
    assert len(info.stderr_tail.encode()) <= proc.STDERR_TAIL_BYTES
    assert info.stderr_tail.endswith("THE-END") and info.stderr_bytes == 200 * 1000 + 7


def test_one_megabyte_of_stdin_does_not_deadlock_against_a_child_that_echoes_it(runner, tmp_path):
    code = "import sys\nwhile True:\n    c = sys.stdin.buffer.read(65536)\n    if not c: break\n    sys.stdout.buffer.write(c)\n    sys.stdout.buffer.flush()"
    text = "".join(("x" * 1023) + "\n" for _ in range(1024))
    got = []
    info = runner.run(py(code, tmp_path, stdin=text), on_line=got.append, timeout_s=30)
    assert info.ok and len(got) == 1024 and got[0] == "x" * 1023


def test_a_child_that_floods_stderr_before_reading_stdin_does_not_deadlock(runner, tmp_path):
    code = ("import sys\nsys.stderr.write('e' * 1_000_000)\nsys.stderr.flush()\n"
            "print(len(sys.stdin.read()))")
    got = []
    info = runner.run(py(code, tmp_path, stdin="y" * 1_000_000), on_line=got.append, timeout_s=30)
    assert got == ["1000000"] and info.ok and info.stderr_bytes == 1_000_000


def test_a_child_that_never_reads_its_stdin_is_not_an_error(runner, tmp_path):
    info = runner.run(py("print('done')", tmp_path, stdin="z" * 3_000_000), timeout_s=30)
    assert info.ok


def test_without_stdin_text_the_child_sees_end_of_input(runner, tmp_path):
    got = []
    runner.run(py("import sys; print(repr(sys.stdin.read()))", tmp_path, stdin=None), on_line=got.append, timeout_s=10)
    assert got == ["''"]


def test_stdin_is_utf8(runner, tmp_path):
    got = []
    runner.run(py("import sys; print(sys.stdin.buffer.read().decode('utf-8'))", tmp_path, stdin="héllo \u2014 ✓"), on_line=got.append)
    assert got == ["héllo \u2014 ✓"]


def test_the_environment_is_exactly_the_one_given_and_the_cwd_is_used(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("LEAK_FROM_PARENT", "1")
    got = []
    runner.run(py("import os; print('LEAK_FROM_PARENT' in os.environ, os.environ.get('ONLY'), os.path.realpath(os.getcwd()))",
                  tmp_path, env={"ONLY": "yes", "PATH": os.environ["PATH"]}), on_line=got.append)
    assert got == [f"False yes {os.path.realpath(tmp_path)}"]


def test_a_long_line_is_cut_and_the_next_line_is_intact(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(proc, "MAX_LINE_BYTES", 1000)
    got = []
    runner.run(py("print('a' * 5000); print('b'); print('c' * 1000); print('d' * 1001)", tmp_path), on_line=got.append)
    assert got == ["a" * 1000, "b", "c" * 1000, "d" * 1000]


# ---- start errors and validation -------------------------------------------------------------------------------------

def test_a_missing_executable_is_cli_missing_and_cleanup_still_runs(runner, tmp_path):
    f = tmp_path / "prompt.txt"
    f.write_text("secret")
    cmd = Command(argv=("definitely-not-a-cli-xyz",), cwd=str(tmp_path), env={"PATH": "/usr/bin"}, cleanup=(str(f),), provider="codex")
    with pytest.raises(CliMissingError) as e:
        runner.start(cmd)
    assert e.value.provider == "codex" and e.value.detail["cli"] == "definitely-not-a-cli-xyz"
    assert not f.exists()


def test_a_file_that_cannot_be_executed_is_a_provider_error(runner, tmp_path):
    f = tmp_path / "noexec"
    f.write_text("#!/bin/sh\n")
    f.chmod(0o600)
    with pytest.raises(ProviderError, match="could not be started"):
        runner.start(Command(argv=(str(f),), cwd=str(tmp_path), env={}))


def test_a_missing_working_directory_is_an_invalid_request_and_cleanup_runs(runner, tmp_path):
    f = tmp_path / "schema.json"
    f.write_text("{}")
    with pytest.raises(InvalidRequestError, match="working directory"):
        runner.start(Command(argv=(sys.executable, "-c", "pass"), cwd=str(tmp_path / "nope"), env={}, cleanup=(str(f),)))
    assert not f.exists()


@pytest.mark.parametrize("kw", [{"timeout_s": 0}, {"timeout_s": -1}, {"idle_timeout_s": 0}])
def test_deadlines_must_be_positive(runner, tmp_path, kw):
    with pytest.raises(InvalidRequestError, match="positive"):
        runner.start(py("pass", tmp_path), **kw)


@pytest.mark.parametrize("argv,env", [((), {}), (("",), {}), ((sys.executable, 5), {}), ((sys.executable,), {"A": 1}), ((sys.executable, "a\0b"), {})])
def test_command_validates_argv_and_env(tmp_path, argv, env):
    with pytest.raises(InvalidRequestError):
        Command(argv=argv, cwd=str(tmp_path), env=env)


def test_command_normalises_its_fields(tmp_path):
    c = Command(argv=[sys.executable, "-c"], cwd=tmp_path, env={"A": "1"}, cleanup=[tmp_path / "x"])
    assert c.argv == (sys.executable, "-c") and c.cwd == str(tmp_path) and c.cleanup == (str(tmp_path / "x"),)


def test_the_cancel_ladder_needs_a_signal():
    with pytest.raises(ValueError):
        ProcessRunner(ladder=())


# ---- deadlines -------------------------------------------------------------------------------------------------------

def test_total_deadline_ends_a_chatty_child_and_says_so(runner, tmp_path):
    code = "import time\nwhile True:\n    print('tick')\n    time.sleep(0.05)"
    got = []
    t0 = time.monotonic()
    info = runner.run(py(code, tmp_path), on_line=got.append, timeout_s=0.5, idle_timeout_s=5)
    assert info.reason == "total_timeout" and not info.ok and info.ladder[0] == "SIGINT"
    assert got and time.monotonic() - t0 < 4


def test_idle_deadline_ends_a_silent_child_after_its_last_line(runner, tmp_path):
    code = "import time\nprint('init')\ntime.sleep(60)"
    got = []
    t0 = time.monotonic()
    info = runner.run(py(code, tmp_path), on_line=got.append, idle_timeout_s=0.4, timeout_s=30)
    assert info.reason == "idle_timeout" and got == ["init"] and time.monotonic() - t0 < 4


def test_lines_reset_the_idle_clock(runner, tmp_path):
    code = "import time\nfor i in range(8):\n    print(i)\n    time.sleep(0.1)"
    info = runner.run(py(code, tmp_path), idle_timeout_s=0.5, timeout_s=30)
    assert info.ok and info.reason == "exit"


def test_stderr_does_not_reset_the_idle_clock(runner, tmp_path):
    code = "import sys, time\nwhile True:\n    sys.stderr.write('x\\n')\n    time.sleep(0.05)"
    info = runner.run(py(code, tmp_path), idle_timeout_s=0.4, timeout_s=30)
    assert info.reason == "idle_timeout"


def test_no_deadline_means_none_applies(runner, tmp_path):
    assert runner.run(py("import time; time.sleep(0.3)", tmp_path)).ok


# ---- the cancel ladder -----------------------------------------------------------------------------------------------

def start_ready(runner, tmp_path, body):
    """A child that prints READY once its signal handlers are set; returns the process and its line iterator."""
    p = runner.start(py(body, tmp_path))
    lines = p.lines()
    assert next(lines) == "READY"
    return p, lines


def test_sigint_ends_a_child_that_obeys_it_and_nothing_more_is_sent(runner, tmp_path):
    p, _ = start_ready(runner, tmp_path, "import time, sys\nprint('READY')\ntime.sleep(60)")
    assert p.cancel() is True
    e = p.wait()
    assert e.reason == "cancelled" and e.ladder == ("SIGINT",) and e.seconds < 5


def test_ladder_goes_sigint_then_sigterm_against_a_child_that_ignores_sigint(runner, tmp_path):
    p, _ = start_ready(runner, tmp_path, "import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\nprint('READY')\ntime.sleep(60)")
    p.cancel()
    e = p.wait()
    assert e.ladder == ("SIGINT", "SIGTERM") and e.returncode == -signal.SIGTERM and e.reason == "cancelled"


def test_ladder_ends_in_sigkill_against_a_child_that_ignores_both(runner, tmp_path):
    p, _ = start_ready(runner, tmp_path, "import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\n"
                                           "signal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('READY')\ntime.sleep(60)")
    t0 = time.monotonic()
    p.cancel()
    e = p.wait()
    assert e.ladder == ("SIGINT", "SIGTERM", "SIGKILL") and e.returncode == -signal.SIGKILL
    assert 1.1 <= time.monotonic() - t0 < 6              # it waited for each rung (0.6 s each) before the next


def test_the_default_ladder_is_the_documented_one():
    assert proc.LADDER == ((signal.SIGINT, 5.0), (signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0))
    assert ProcessRunner()._ladder == proc.LADDER


def test_cancel_returns_false_when_nothing_is_running(runner, tmp_path):
    p = runner.start(py("print('x')", tmp_path))
    assert p.wait().ok
    assert p.cancel() is False
    assert p.wait().reason == "exit" and p.wait().ladder == ()


def test_cancel_from_another_thread_ends_the_line_loop(runner, tmp_path):
    p = runner.start(py("import time\nprint('READY')\ntime.sleep(60)", tmp_path))
    seen = []
    t = threading.Thread(target=lambda: seen.extend(p.lines()))
    t.start()
    time.sleep(0.3)
    assert p.running
    assert p.cancel() is True
    t.join(5)
    assert not t.is_alive() and seen == ["READY"] and p.wait().reason == "cancelled"


def test_the_first_reason_wins_when_a_deadline_and_a_cancel_overlap(runner, tmp_path):
    p, _ = start_ready(runner, tmp_path, "import time\nprint('READY')\ntime.sleep(60)")
    p.cancel("idle_timeout")
    p.cancel("cancelled")
    assert p.wait().reason == "idle_timeout"


def test_a_grandchild_dies_with_the_group_on_cancel(runner, tmp_path):
    code = ("import subprocess, sys, time\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "print(g.pid)\nsys.stdout.flush()\ntime.sleep(60)")
    p = runner.start(py(code, tmp_path))
    gpid = int(next(p.lines()))
    assert alive(gpid)
    p.cancel()
    p.wait()
    assert wait_dead(gpid)


def test_a_grandchild_left_behind_by_a_finished_child_is_killed_and_does_not_hold_the_stream_open(runner, tmp_path):
    code = ("import subprocess, sys\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "print(g.pid)")
    got = []
    t0 = time.monotonic()
    info = runner.run(py(code, tmp_path), on_line=got.append, timeout_s=20)
    assert info.ok and time.monotonic() - t0 < 6
    assert wait_dead(int(got[0]))


def test_a_grandchild_outside_the_group_that_holds_stdout_cannot_hang_the_reader(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(proc, "READER_GRACE_S", 0.5)
    code = ("import subprocess, sys\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'], start_new_session=True)\n"
            "print(g.pid)")
    got = []
    info = runner.run(py(code, tmp_path), on_line=got.append, timeout_s=20)
    assert info.ok and alive(int(got[0]))      # run() came back although the grandchild still holds the pipe
    assert wait_dead(int(got[0]), 6)


# ---- cleanup, context manager, stop_all ------------------------------------------------------------------------------

def test_cleanup_files_and_folders_are_removed_after_a_normal_run(runner, tmp_path):
    f, d = tmp_path / "prompt.txt", tmp_path / "work"
    f.write_text("p")
    d.mkdir()
    (d / "inner.json").write_text("{}")
    seen = []
    runner.run(py("import time; time.sleep(0.2); print('go')", tmp_path, cleanup=(f, d, tmp_path / "never-existed")),
               on_line=lambda line: seen.append((f.exists(), d.exists())))
    assert seen == [(True, True)]              # still there while the child runs
    assert not f.exists() and not d.exists()


def test_cleanup_runs_after_a_timeout_too(runner, tmp_path):
    f = tmp_path / "mcp.json"
    f.write_text("{}")
    info = runner.run(py("import time; time.sleep(60)", tmp_path, cleanup=(f,)), timeout_s=0.3)
    assert info.reason == "total_timeout" and not f.exists()


def test_a_callback_that_raises_cancels_the_child(runner, tmp_path):
    p_holder = []

    def boom(line):
        p_holder.append(line)
        raise RuntimeError("parser gave up")

    with pytest.raises(RuntimeError, match="parser gave up"):
        runner.run(py("import time\nprint('one')\ntime.sleep(60)", tmp_path), on_line=boom)
    assert runner.live() == [] and p_holder == ["one"]


def test_leaving_the_with_block_early_cancels_the_child(runner, tmp_path):
    with runner.start(py("import time\nprint('one')\ntime.sleep(60)", tmp_path)) as p:
        assert next(p.lines()) == "one"
    e = p.wait()
    assert e.reason == "cancelled" and not p.running


def test_live_children_are_tracked_and_stop_all_ends_them_all(runner, tmp_path):
    ps = [runner.start(py("import time\nprint('READY')\ntime.sleep(60)", tmp_path)) for _ in range(2)]
    for p in ps:
        assert next(p.lines()) == "READY"
    assert set(runner.live()) == set(ps)
    assert runner.stop_all() == 2
    assert runner.live() == [] and all(p.wait().reason == "cancelled" for p in ps)
    assert runner.stop_all() == 0


def test_exit_info_signal_name_for_unknown_and_positive_codes():
    base = dict(reason="exit", stderr_tail="", seconds=0.0, pid=1)
    assert ExitInfo(returncode=2, **base).signal_name is None
    assert ExitInfo(returncode=None, **base).signal_name is None
    assert ExitInfo(returncode=-2, **base).signal_name == "SIGINT"
    assert ExitInfo(returncode=-200, **base).signal_name == "SIG200"
    assert not ExitInfo(returncode=0, **{**base, "reason": "cancelled"}).ok
