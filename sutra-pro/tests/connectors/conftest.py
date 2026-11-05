"""Fixtures for tests/connectors (work package CN-2): the fake claude, codex and gh, and the captured fixtures.

    def test_x(fake, tmp_path):
        fake.sequence("quota", "ok_plain").reply(text="pong")            # claude is out of quota, the next call answers
        cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))            # claude_exe, codex_exe, gh_exe, extra_env point at the fakes
        ...
        assert [c["scenario"] for c in fake.model_calls()] == ["quota", "ok_plain"]
        assert fake.calls("claude")[0]["argv"][0] == "-p"

`fake` is a FakeCli; its docstring and tests/fakes/fake_cli.py list every FAKE_* variable and scenario. Nothing here imports
sutra_app, so these fixtures work before any connector module exists. Helpers are fixtures (not importable names) because a plain
`import conftest` is ambiguous between the several conftest.py files of the suite.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent.parent
FAKES_DIR = TESTS_DIR / "fakes"
FIXTURES_DIR = TESTS_DIR / "fixtures" / "connectors"

# a fake that nobody kills (a failed test, a connector that lost track of its child) ends by itself after this many seconds
DEFAULT_MAX_SECONDS = "20"


class Fixtures:
    """Read access to tests/fixtures/connectors."""

    root = FIXTURES_DIR

    def path(self, rel):
        return FIXTURES_DIR / rel

    def text(self, rel):
        return (FIXTURES_DIR / rel).read_text(encoding="utf-8")

    def json(self, rel):
        return json.loads(self.text(rel))

    def lines(self, rel):
        """A JSONL fixture as a list: a dict for each JSON object line, the raw string for any other line (noise, blank)."""
        out = []
        for raw in self.text(rel).split("\n")[:-1]:
            try:
                obj = json.loads(raw)
            except ValueError:
                obj = None
            out.append(obj if isinstance(obj, dict) else raw)
        return out

    def manifest(self):
        return self.json("MANIFEST.json")


class FakeCli:
    """One test's fake claude, codex and gh, their settings and their call log.

    Setters return self, so they chain. They only fill the FAKE_* environment (self.vars): hand env() to ConnectorConfig.extra_env,
    to subprocess.run(env=...) or use run(). A connector builds its child environment from an allowlist and drops SUTRA_* names, so
    the interpreter for the wrappers travels as FAKE_PYTHON (SUTRA_FAKE_PYTHON is set as well for direct use).
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.state_dir = self.root / "fake-state"
        self.python = sys.executable
        self.vars = {"FAKE_MAX_SECONDS": DEFAULT_MAX_SECONDS}
        self._bin = None
        self._procs = []

    # ---- the executables
    def exe(self, name):
        if name not in ("claude", "codex", "gh"):
            raise KeyError(name)
        return str(FAKES_DIR / name)

    claude = property(lambda self: self.exe("claude"))
    codex = property(lambda self: self.exe("codex"))
    gh = property(lambda self: self.exe("gh"))

    @property
    def bin_dir(self):
        """A directory holding claude, codex and gh (forwarding to the fakes): put it on PATH to find them with shutil.which."""
        if self._bin is None:
            self._bin = self.root / "fake-bin"
            self._bin.mkdir(parents=True, exist_ok=True)
            for name in ("claude", "codex", "gh"):
                script = self._bin / name
                script.write_text('#!/bin/sh\nexec "%s" "$@"\n' % self.exe(name))
                script.chmod(0o755)
        return str(self._bin)

    # ---- settings
    def set(self, **env):
        """Set FAKE_* variables by name: fake.set(FAKE_LINE_DELAY="0.05"). A value of None removes the variable."""
        for name, value in env.items():
            if value is None:
                self.vars.pop(name, None)
            else:
                self.vars[name] = str(value)
        return self

    def sequence(self, *scenarios, cli=None):
        """The scenarios of the next model calls, one each (the last repeats). cli="claude" or "codex": that CLI's own sequence."""
        name = "FAKE_CLI_SEQUENCE" if cli is None else "FAKE_%s_SEQUENCE" % cli.upper()
        return self.set(**{name: ",".join(scenarios)})

    def auth(self, claude=None, codex=None, gh=None):
        """signed_in | signed_out | api_key | console | error for each CLI given."""
        return self.set(FAKE_CLAUDE_AUTH=claude, FAKE_CODEX_AUTH=codex, FAKE_GH_AUTH=gh)

    def reply(self, json=None, text=None):
        """The reply of the ok scenarios: a JSON value (structured output) and/or text."""
        import json as _json
        return self.set(FAKE_REPLY_JSON=None if json is None else _json.dumps(json), FAKE_REPLY_TEXT=text)

    def cost(self, usd):
        return self.set(FAKE_COST_USD=usd)

    def usage(self, **tokens):
        """This call's token amounts under the CLI's own key names, e.g. input_tokens=10, output_tokens=2."""
        import json as _json
        return self.set(FAKE_USAGE=_json.dumps(tokens))

    # ---- environments
    def env(self, **extra):
        """The FAKE_* variables (state directory and interpreter included) as a dict of strings."""
        out = {"FAKE_CLI_STATE": str(self.state_dir), "FAKE_PYTHON": self.python, "SUTRA_FAKE_PYTHON": self.python}
        out.update(self.vars)
        out.update({k: str(v) for k, v in extra.items()})
        return out

    def process_env(self, **extra):
        """A small complete environment for subprocess.run(env=...): PATH, HOME and the FAKE_* variables."""
        base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", str(self.root)), "LANG": "en_US.UTF-8"}
        base.update(self.env(**extra))
        return base

    def config_kwargs(self, root=None):
        """Keyword arguments for ConnectorConfig: every executable is a fake and the FAKE_* variables are its extra_env (without the
        SUTRA_FAKE_PYTHON of env(): a connector drops SUTRA_* names, and FAKE_PYTHON tells the wrappers which interpreter to use)."""
        root = Path(root) if root is not None else self.root
        return {"data_dir": root / "data", "work_root": root / "work", "claude_exe": self.claude, "codex_exe": self.codex,
                "gh_exe": self.gh, "python": self.python, "extra_env": {k: v for k, v in self.env().items() if not k.startswith("SUTRA_")}}

    # ---- running
    def popen(self, cli, *args, cwd=None, env=None, stdin=subprocess.PIPE):
        proc = subprocess.Popen([self.exe(cli), *args], stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                cwd=str(cwd) if cwd else None, env=env if env is not None else self.process_env())
        self._procs.append(proc)
        return proc

    def run(self, cli, *args, input=None, cwd=None, env=None, timeout=60):
        """Run one fake to the end -> CompletedProcess (text). Without input the child gets an empty stdin, never ours."""
        proc = subprocess.run([self.exe(cli), *args], input=input if input is not None else "", capture_output=True, text=True, timeout=timeout,
                              cwd=str(cwd) if cwd else None, env=env if env is not None else self.process_env())
        return proc

    def feed(self, proc, text):
        """Write the prompt to a process started with popen and close its stdin. After this, `communicate()` still works
        (subprocess raises on a pipe the caller already closed, so the closed pipe is detached from the process object)."""
        proc.stdin.write(text)
        proc.stdin.flush()
        proc.stdin.close()
        proc.stdin = None

    def finish(self, proc, timeout=15.0):
        """-> (stdout, stderr) of a process started with popen, read to the end whatever was read before (communicate() would lose what
        readline() already buffered). A process that is still running after `timeout` seconds is killed."""
        timer = threading.Timer(timeout, proc.kill)
        timer.start()
        try:
            out, err = proc.stdout.read(), proc.stderr.read()
            proc.wait()
        finally:
            timer.cancel()
        return out, err

    def close(self):
        """Kill the processes started with popen that are still running (the fixture does this at the end of every test)."""
        for proc in self._procs:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if pipe:
                        pipe.close()
                except Exception:
                    pass

    # ---- the call log (FAKE_CLI_STATE)
    def _read_jsonl(self, name):
        out = []
        try:
            text = (self.state_dir / name).read_text(encoding="utf-8")
        except OSError:
            return out
        for raw in text.split("\n"):
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
        return out

    def calls(self, cli=None, kind=None, op=None):
        """Every invocation so far, oldest first: the calls.jsonl record plus exit, t_end and signal once the process ended."""
        ends = {rec["n"]: rec for rec in self._read_jsonl("exits.jsonl")}
        out = []
        for rec in self._read_jsonl("calls.jsonl"):
            end = ends.get(rec["n"], {})
            rec = dict(rec, exit=end.get("exit"), t_end=end.get("t_end"), signal=end.get("signal"))
            if (cli is None or rec["cli"] == cli) and (kind is None or rec["kind"] == kind) and (op is None or rec["op"] == op):
                out.append(rec)
        return sorted(out, key=lambda r: r["n"])

    def model_calls(self, cli=None):
        """The invocations that consumed a scenario (claude -p, codex exec, codex exec resume)."""
        return self.calls(cli, kind="call")

    def last_call(self, cli=None, kind=None):
        found = self.calls(cli, kind)
        return found[-1] if found else None

    @staticmethod
    def visible_env_keys(call):
        """The environment names a connector passed to the fake: the logged env_keys without the FAKE_* names that drive the fake."""
        return {k for k in call["env_keys"] if not k.startswith(("FAKE_", "SUTRA_FAKE_"))}

    def sessions(self):
        try:
            return json.loads((self.state_dir / "sessions.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def wait_for(self, count, cli=None, kind="call", timeout=10.0):
        """Wait until `count` matching invocations are logged (a fake started in the background) -> the matching records."""
        deadline = time.time() + timeout
        while True:
            found = self.calls(cli, kind)
            if len(found) >= count:
                return found
            if time.time() > deadline:
                raise AssertionError("expected %d logged invocations, saw %d: %r" % (count, len(found), found))
            time.sleep(0.02)

    def approve_device_auth(self):
        """Let a running `codex login --device-auth` finish as if the owner had entered the code."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "device_auth_approve").write_text("")


POSIX_ONLY = ("the fake claude, codex and gh are POSIX shell wrappers whose expectations are POSIX signal semantics (D104); on Windows the "
              "connector layer is covered by tests/connectors/test_process_portable.py and the packaged app by scripts/prove_windows_app.py")


@pytest.fixture
def fake(tmp_path):
    if sys.platform == "win32":
        pytest.skip(POSIX_ONLY)
    handle = FakeCli(tmp_path)
    yield handle
    handle.close()


@pytest.fixture(scope="module")
def make_fake(tmp_path_factory):
    """For a module-scoped fixture that needs a FakeCli (the function-scoped `fake` cannot serve one): make_fake() -> a new handle."""
    if sys.platform == "win32":
        pytest.skip(POSIX_ONLY)
    handles = []

    def make(name="fake"):
        handles.append(FakeCli(tmp_path_factory.mktemp(name)))
        return handles[-1]

    yield make
    for handle in handles:
        handle.close()


@pytest.fixture(scope="session")
def fixtures():
    return Fixtures()


@pytest.fixture(scope="session")
def fakes_dir():
    return FAKES_DIR
