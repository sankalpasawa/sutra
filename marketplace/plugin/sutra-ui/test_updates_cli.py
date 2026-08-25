"""test_updates_cli.py -- the shell's tokenless update path (attach mode).

Pins three things:
  1. The verb surface and JSON/exit contract, END TO END as a subprocess, for
     the network-free verbs -- exactly how the Electron shell spawns it.
  2. That the network verbs route to the same updates.py functions the HTTP
     layer uses (in-process, monkeypatched -- no network).
  3. The new cross-process _state_lock: a held lock makes a writer refuse
     with a reason instead of corrupting the manifest.

Run: .venv/bin/python -m pytest -q test_updates_cli.py
"""
import contextlib
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import updates  # noqa: E402
import updates_cli  # noqa: E402


def _cli_subprocess(args, update_dir):
    env = dict(os.environ, SUTRA_UPDATE_DIR=update_dir, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, "-m", "updates_cli", *args],
        cwd=HERE, env=env, capture_output=True, text=True, timeout=30)


class SubprocessContract(unittest.TestCase):
    """The argv surface the shell depends on, proven as a real child process."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="updates-cli-test-")

    def test_staged_with_nothing_staged(self):
        r = _cli_subprocess(["staged"], self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"pending": False})

    def test_resolve_with_no_manifest(self):
        r = _cli_subprocess(["resolve"], self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"pending": False})

    def test_arm_with_nothing_staged_is_a_json_error_exit_1(self):
        r = _cli_subprocess(["arm", "--wait-pid", str(os.getpid())], self.tmp)
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout)
        self.assertIn("no staged update", out["error"])

    def test_stdout_is_exactly_one_json_object(self):
        r = _cli_subprocess(["staged"], self.tmp)
        self.assertEqual(len([l for l in r.stdout.splitlines() if l.strip()]), 1)


class VerbRouting(unittest.TestCase):
    """Each verb calls the same function the HTTP layer calls."""

    def test_check_routes_to_all_state(self):
        with mock.patch.object(updates, "all_state", return_value={"desktop": {"managed": False}}):
            with mock.patch("builtins.print") as p:
                rc = updates_cli.main(["check"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(p.call_args[0][0]), {"desktop": {"managed": False}})

    def test_stage_routes_to_stage_desktop(self):
        with mock.patch.object(updates, "stage_desktop",
                               return_value={"staged": True, "version": "9.9.9"}):
            with mock.patch("builtins.print") as p:
                rc = updates_cli.main(["stage"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(p.call_args[0][0])["version"], "9.9.9")

    def test_arm_routes_with_args(self):
        with mock.patch.object(updates, "arm_desktop",
                               return_value={"scheduled": True}) as arm:
            rc = updates_cli.main(["arm", "--wait-pid", "123", "--relaunch"])
        self.assertEqual(rc, 0)
        arm.assert_called_once_with(123, wait_start=None, relaunch=True)

    def test_runtime_error_becomes_error_json_exit_1(self):
        with mock.patch.object(updates, "stage_desktop",
                               side_effect=RuntimeError("offline")):
            with mock.patch("builtins.print") as p:
                rc = updates_cli.main(["stage"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(p.call_args[0][0]), {"error": "offline"})


class StateLock(unittest.TestCase):
    """The cross-process mutex the CLI writer class made necessary."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="updates-lock-test-")
        self.env = mock.patch.dict(os.environ, {"SUTRA_UPDATE_DIR": self.tmp})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_lock_is_exclusive_and_refuses_with_a_reason(self):
        lock_path = os.path.join(self.tmp, ".lock")
        os.makedirs(self.tmp, exist_ok=True)
        holder = open(lock_path, "a")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                with updates._state_lock(timeout=0.3):
                    pass
            self.assertIn("in use by another process", str(ctx.exception))
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()

    def test_lock_acquires_when_free_and_releases(self):
        with updates._state_lock(timeout=1.0):
            pass
        with updates._state_lock(timeout=1.0):
            pass  # a second acquisition proves the first released

    def test_public_writers_take_the_lock(self):
        """Every public writer runs its body under _state_lock -- probed, not
        assumed, so a refactor that drops a wrapper fails here."""
        calls = []

        @contextlib.contextmanager
        def probe(timeout=5.0):
            calls.append("lock")
            yield

        with mock.patch.object(updates, "_state_lock", probe):
            updates.resolve_pending()                      # no manifest path
            with mock.patch.object(updates, "desktop_state",
                                   return_value={"managed": False, "reason": "test"}):
                updates.stage_desktop()                    # unmanaged short-circuit
            with self.assertRaises(RuntimeError):
                updates.arm_desktop(os.getpid())           # nothing staged
        self.assertEqual(calls, ["lock", "lock", "lock"])


if __name__ == "__main__":
    unittest.main()
