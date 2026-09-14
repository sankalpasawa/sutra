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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
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

    def test_every_manifest_write_happens_under_the_lock(self):
        """stage, arm and resolve each WRITE pending-update.json, and every one
        of those writes happens while _state_lock is held -- probed, not
        assumed, so a refactor that moves a write outside the lock fails here.
        (Reads may run unlocked: writes are atomic renames.)"""
        depth = {"n": 0}
        real_lock = updates._state_lock

        @contextlib.contextmanager
        def probe(timeout=5.0):
            with real_lock(timeout):
                depth["n"] += 1
                try:
                    yield
                finally:
                    depth["n"] -= 1

        writes = []
        real_write = updates._write_json

        def spy(path, obj):
            writes.append((Path(path).name, depth["n"] > 0))
            return real_write(path, obj)

        def fake_download(dest_dir=None):
            p = Path(dest_dir) / "Sutra-arm64.dmg"
            p.write_bytes(b"image 9.9.9")
            return {"dmg": str(p), "version": "9.9.9", "dir": dest_dir}

        with mock.patch.object(updates, "_state_lock", probe), \
                mock.patch.object(updates, "_write_json", spy), \
                mock.patch.object(updates, "desktop_state", return_value={
                    "managed": True, "update_available": True,
                    "latest": "9.9.9", "error": None}), \
                mock.patch.object(updates, "_latest_desktop", return_value={
                    "version": "9.9.9", "asset": "Sutra-arm64.dmg",
                    "sha256_url": None}), \
                mock.patch.object(updates, "download_and_verify", fake_download), \
                mock.patch.object(updates, "install_desktop",
                                  return_value={"scheduled": True}):
            self.assertTrue(updates.stage_desktop()["staged"])     # commit
            self.assertTrue(updates.arm_desktop(os.getpid())["scheduled"])  # installing
            with open(updates._result_path(), "w") as fh:          # helper failed
                json.dump({"ok": False, "version": "9.9.9", "stage": "mount",
                           "error": "could not mount"}, fh)
            self.assertEqual(updates.resolve_pending()["action"], "arm")  # recorded

        manifest = [held for name, held in writes if name == "pending-update.json"]
        self.assertEqual(len(manifest), 3, writes)
        self.assertTrue(all(manifest), "a manifest write ran without the lock: %s" % writes)


OLD, NEW = "2.271.4", "2.271.5"


class StageDoesNotHoldTheLock(unittest.TestCase):
    """THE BUG (2026-09-14). stage_desktop held the state lock for the whole
    ~400MB download. 2.271.5 started downloading while 2.271.4 was staged; the
    countdown armed 2.271.4, waited 5s for the lock, and the banner said
    "Sutra 2.271.4 could not be applied. the update state is in use by another
    process". The same download was also writing over 2.271.4's DMG, because
    both used the name Sutra-arm64.dmg."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="updates-stage-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = mock.patch.dict(os.environ, {"SUTRA_UPDATE_DIR": self.tmp})
        env.start()
        self.addCleanup(env.stop)
        self.root = updates.stage_dir()
        self.started = threading.Event()
        self.release = threading.Event()
        self.addCleanup(self.release.set)      # never leave a download thread parked
        self.lock_free_during_download = None
        for name, kw in (
                ("desktop_state", {"return_value": {
                    "managed": True, "update_available": True,
                    "latest": NEW, "error": None}}),
                ("_latest_desktop", {"return_value": {
                    "version": NEW, "asset": "Sutra-arm64.dmg", "sha256_url": None}}),
                ("download_and_verify", {"side_effect": self._fake_download}),
                ("install_desktop", {"return_value": {"scheduled": True}})):
            p = mock.patch.object(updates, name, **kw)
            setattr(self, "mock_" + name, p.start())
            self.addCleanup(p.stop)
        # Registered LAST so it runs FIRST: a download thread must finish while
        # SUTRA_UPDATE_DIR still points at the temp dir. If the env override is
        # restored under a parked thread, its commit resolves stage_dir() to
        # the REAL ~/Library/Application Support/Sutra/updates and writes a
        # bogus manifest there (this happened once, on a failing run).
        self._threads = []
        self.addCleanup(self._drain_threads)

    def _drain_threads(self):
        self.release.set()
        for t in self._threads:
            t.join(15)
            if t.is_alive():
                raise RuntimeError("a stage thread outlived its test; refusing "
                                   "to restore the real update dir under it")

    # -- helpers ---------------------------------------------------------------

    def _fake_download(self, dest_dir=None):
        """Stands in for the network download + spctl: writes the image, proves
        the lock is free while it runs, then parks until the test releases it."""
        dmg = Path(dest_dir) / "Sutra-arm64.dmg"
        dmg.write_bytes(b"new image " + NEW.encode())
        self.lock_free_during_download = self._lock_is_free()
        self.started.set()
        self.release.wait(10)
        return {"dmg": str(dmg), "version": NEW, "dir": dest_dir}

    def _lock_is_free(self):
        fh = open(self.root / ".lock", "a")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            return True
        except OSError:
            return False
        finally:
            fh.close()

    def _stage_old(self, **overrides):
        """2.271.4 staged under the pre-fix unversioned name, as on the user's Mac."""
        dmg = self.root / "Sutra-arm64.dmg"
        payload = b"old image " + OLD.encode()
        dmg.write_bytes(payload)
        man = {"state": "staged", "version": OLD, "dmg": str(dmg),
               "sha256": hashlib.sha256(payload).hexdigest(), "sha256_url": None,
               "asset": "Sutra-arm64.dmg", "staged_at": 1, "armed_at": None,
               "lease_until": None, "arm_attempts": 0, "spawn_failures": 0,
               "install_failures": 0, "last_error": None}
        man.update(overrides)
        updates._write_json(updates._pending_path(), man)
        return dmg, man["sha256"]

    def _stage_in_thread(self):
        out = {}

        def run():
            try:
                out["result"] = updates.stage_desktop()
            except Exception as exc:        # surfaced by the assertion below
                out["error"] = exc

        t = threading.Thread(target=run, daemon=True)
        self._threads.append(t)
        t.start()
        self.assertTrue(self.started.wait(5), "the download never started")
        return t, out

    def _finish(self, t, out):
        self.release.set()
        t.join(10)
        self.assertFalse(t.is_alive(), "stage_desktop did not finish")
        self.assertNotIn("error", out, out.get("error"))
        return out["result"]

    def _leftover_downloads(self):
        return list(self.root.glob(".download-*"))

    # -- tests -----------------------------------------------------------------

    def test_arm_and_resolve_do_not_wait_on_a_download(self):
        old_dmg, old_sha = self._stage_old()
        t, out = self._stage_in_thread()
        self.assertTrue(self.lock_free_during_download,
                        "the state lock is held across the download")

        t0 = time.monotonic()
        r = updates.resolve_pending(installed_version="2.271.3")
        self.assertLess(time.monotonic() - t0, 1.0, "resolve waited on the download")
        self.assertEqual((r["action"], r["version"]), ("arm", OLD))

        t0 = time.monotonic()
        a = updates.arm_desktop(os.getpid())
        self.assertLess(time.monotonic() - t0, 1.0, "arm waited on the download")
        self.assertTrue(a["scheduled"])
        self.assertEqual(a["version"], OLD)
        # The in-flight download has not touched the image being installed.
        self.assertEqual(hashlib.sha256(old_dmg.read_bytes()).hexdigest(), old_sha)

        res = self._finish(t, out)
        # A live install wins: the new download is discarded, the armed DMG kept.
        self.assertFalse(res["staged"])
        self.assertIn("already waiting", res["reason"])
        man = updates.read_pending()
        self.assertEqual((man["version"], man["state"], man["dmg"]),
                         (OLD, "installing", str(old_dmg)))
        self.assertEqual(hashlib.sha256(old_dmg.read_bytes()).hexdigest(), old_sha)
        self.assertEqual(self._leftover_downloads(), [])

    def test_a_finished_download_replaces_a_merely_staged_older_build(self):
        old_dmg, _ = self._stage_old()
        self.release.set()
        res = updates.stage_desktop()
        self.assertTrue(self.lock_free_during_download)
        self.assertEqual((res["staged"], res["version"]), (True, NEW))
        man = updates.read_pending()
        self.assertEqual((man["version"], man["state"]), (NEW, "staged"))
        final = Path(man["dmg"])
        self.assertEqual(final.name, "Sutra-arm64-%s.dmg" % NEW)
        self.assertEqual(final.parent.resolve(), self.root.resolve())
        self.assertEqual(man["sha256"], hashlib.sha256(final.read_bytes()).hexdigest())
        self.assertFalse(old_dmg.exists(), "the superseded image was left behind")
        self.assertEqual(self._leftover_downloads(), [])
        # And the staged record is armable: _verify_staged accepts it.
        self.assertTrue(updates.arm_desktop(os.getpid())["scheduled"])

    def test_a_live_install_is_not_downloaded_over(self):
        old_dmg, old_sha = self._stage_old(state="installing",
                                           lease_until=int(time.time()) + 300)
        res = updates.stage_desktop()
        self.assertFalse(res["staged"])
        self.mock_download_and_verify.assert_not_called()
        self.assertEqual(hashlib.sha256(old_dmg.read_bytes()).hexdigest(), old_sha)

    def test_same_version_staged_elsewhere_during_the_download_is_kept(self):
        t, out = self._stage_in_thread()
        theirs = self.root / ("Sutra-arm64-%s.dmg" % NEW)
        theirs.write_bytes(b"their verified image")
        with updates._state_lock(timeout=1.0):      # the other process's commit
            updates._write_json(updates._pending_path(), {
                "state": "staged", "version": NEW, "dmg": str(theirs),
                "sha256": hashlib.sha256(b"their verified image").hexdigest(),
                "staged_at": 2})
        before = updates.read_pending()
        res = self._finish(t, out)
        self.assertTrue(res["already"])
        self.assertEqual(res["discarded"], NEW)
        self.assertEqual(updates.read_pending(), before)
        self.assertEqual(theirs.read_bytes(), b"their verified image")
        self.assertEqual(self._leftover_downloads(), [])

    def test_a_crashed_download_dir_is_swept_but_a_live_one_is_not(self):
        stale = self.root / ".download-stale"
        stale.mkdir()
        (stale / "Sutra-arm64.dmg").write_bytes(b"half")
        old = time.time() - updates.STALE_DOWNLOAD_SECONDS - 60
        os.utime(stale / "Sutra-arm64.dmg", (old, old))
        os.utime(stale, (old, old))
        live = self.root / ".download-live"
        live.mkdir()
        (live / "Sutra-arm64.dmg").write_bytes(b"still arriving")
        updates._sweep_stale_downloads(self.root)
        self.assertFalse(stale.exists())
        self.assertTrue(live.exists())


class BusyIsNotAFailure(unittest.TestCase):
    """The shell can only avoid reporting a busy lock as a failed install if
    the CLI says, in a field, that the lock was the only problem."""

    def test_busy_lock_is_flagged_busy(self):
        with mock.patch.object(updates, "arm_desktop",
                               side_effect=updates.StateBusy(updates.STATE_BUSY_MESSAGE)):
            with mock.patch("builtins.print") as p:
                rc = updates_cli.main(["arm", "--wait-pid", "1"])
        self.assertEqual(rc, 1)
        out = json.loads(p.call_args[0][0])
        self.assertIs(out["busy"], True)
        self.assertIn("in use by another process", out["error"])

    def test_busy_is_still_a_runtime_error(self):
        """Every existing `except RuntimeError` (the HTTP routes) still catches it."""
        self.assertTrue(issubclass(updates.StateBusy, RuntimeError))


if __name__ == "__main__":
    unittest.main()
