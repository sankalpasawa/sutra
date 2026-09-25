"""test_updates_windows.py -- the Windows desktop app can find, stage and install
its own update.

The failure this pins was reported by a customer on 2026-09-25: the Windows
build never updated. Nothing errored. updates.py only knew a macOS .app, so on
Windows desktop_state() answered `managed: False`, the shell's update-state
turned that into `update_available: false`, and the Settings row read "up to
date" while newer releases sat on GitHub with a Sutra-Setup-x64.exe attached.

So this file pins the Windows leg end to end, runnable on any OS by flipping
updates._IS_WIN:

  1. the install is found from the exe the shell names, never from a guess
  2. the check reads the installer asset and reports the real version gap
  3. a portable copy is told, in words, to install once instead
  4. staging lives under %LOCALAPPDATA% and never touches POSIX-only calls
  5. the checksum is REQUIRED (the installer is unsigned; it is the only gate)
  6. the helper runs the NSIS installer silently, after the app exits, into
     the same folder, and reports in the shape resolve_pending() reads
  7. the shell hands python its version, exe and import shims on both spawns
  8. the plugin update runs `claude` by full path, so an npm .cmd shim runs

On a real Windows box (the release-windows.yml runner) the PowerShell parser
also checks the helper script.

Run: .venv/bin/python -m pytest -q test_updates_windows.py
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import updates  # noqa: E402


def _release(tag="v2.305.0-desktop"):
    base = "https://github.com/sankalpasawa/sutra/releases/download/%s/" % tag
    names = ["Sutra-arm64.dmg", "Sutra-arm64.dmg.sha256",
             "Sutra-x86_64.dmg", "Sutra-x86_64.dmg.sha256",
             "Sutra-Setup-x64.exe", "Sutra-Setup-x64.exe.sha256",
             "Sutra-x64.exe", "Sutra-x64.exe.sha256"]
    return {"tag_name": tag, "html_url": "https://example/rel",
            "assets": [{"name": n, "browser_download_url": base + n, "size": 1000}
                       for n in names]}


class _WinCase(unittest.TestCase):
    """A fake Windows install in a temp dir, with _IS_WIN on."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sutra-win-test-"))
        self.root = self.tmp / "Programs" / "Sutra"
        self.ui = self.root / "resources" / "payload" / "plugin" / "sutra-ui"
        self.ui.mkdir(parents=True)
        (self.ui / "updates.py").write_text("# fake\n")
        self.exe = self.root / "Sutra.exe"
        self.exe.write_bytes(b"MZ")
        (self.root / "Uninstall Sutra.exe").write_bytes(b"MZ")
        self.local = self.tmp / "LocalAppData"
        self.local.mkdir()
        env = {k: v for k, v in os.environ.items()
               if k not in ("SUTRA_UPDATE_DIR", "PORTABLE_EXECUTABLE_FILE",
                            "SUTRA_DESKTOP_EXE", "SUTRA_DESKTOP_VERSION")}
        env.update({"SUTRA_DESKTOP_EXE": str(self.exe),
                    "SUTRA_DESKTOP_VERSION": "2.304.1",
                    "LOCALAPPDATA": str(self.local)})
        self._patches = [
            mock.patch.object(updates, "_IS_WIN", True),
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(updates, "_HERE", self.ui / "updates.py"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class Detect(_WinCase):
    def test_01_install_is_the_folder_of_the_exe_the_shell_names(self):
        self.assertEqual(updates.win_install(), self.root)

    def test_02_a_named_exe_this_file_does_not_live_under_is_not_an_install(self):
        """A source checkout that inherited the variable must not look installed."""
        other = self.tmp / "Elsewhere" / "Sutra.exe"
        other.parent.mkdir()
        other.write_bytes(b"MZ")
        with mock.patch.dict(os.environ, {"SUTRA_DESKTOP_EXE": str(other)}):
            self.assertIsNone(updates.win_install())

    def test_03_no_named_exe_means_no_install(self):
        del os.environ["SUTRA_DESKTOP_EXE"]
        self.assertIsNone(updates.win_install())

    def test_04_arch_does_not_need_os_uname(self):
        with mock.patch.object(updates.os, "uname", side_effect=AttributeError("uname"), create=True), \
             mock.patch.object(updates.platform, "machine", return_value="AMD64"):
            self.assertEqual(updates._arch(), "x86_64")


class Check(_WinCase):
    def test_05_the_reported_bug_an_installed_windows_app_is_managed(self):
        with mock.patch.object(updates, "_get_json", return_value=_release()):
            s = updates.desktop_state()
        self.assertTrue(s["managed"], s)
        self.assertEqual(s["installed"], "2.304.1")
        self.assertEqual(s["latest"], "2.305.0")
        self.assertTrue(s["update_available"])
        self.assertEqual(s["asset"], "Sutra-Setup-x64.exe")
        self.assertIsNone(s["error"])
        self.assertEqual(s["app_path"], str(self.root))

    def test_06_the_installer_is_the_asset_never_the_portable_or_a_dmg(self):
        with mock.patch.object(updates, "_get_json", return_value=_release()):
            latest = updates._latest_desktop()
        self.assertTrue(latest["download_url"].endswith("/Sutra-Setup-x64.exe"))
        self.assertTrue(latest["sha256_url"].endswith("/Sutra-Setup-x64.exe.sha256"))

    def test_07_a_release_without_the_installer_says_so(self):
        rel = _release()
        rel["assets"] = [a for a in rel["assets"] if "Setup" not in a["name"]]
        with mock.patch.object(updates, "_get_json", return_value=rel):
            s = updates.desktop_state()
        self.assertIn("Sutra-Setup-x64.exe", s["error"])
        self.assertFalse(s["update_available"] and not s["error"])

    def test_32_macos_delta_assets_are_never_offered_to_windows(self):
        rel = _release()
        for n in ("Sutra-x86_64.manifest.json", "Sutra-x86_64.delta.tar.xz"):
            rel["assets"].append({"name": n, "browser_download_url": "u/" + n, "size": 1})
        with mock.patch.object(updates, "_get_json", return_value=rel), \
             mock.patch.object(updates.platform, "machine", return_value="AMD64"):
            self.assertFalse(updates._latest_desktop()["delta"])

    def test_08_no_version_from_the_shell_is_unmanaged_not_up_to_date(self):
        del os.environ["SUTRA_DESKTOP_VERSION"]
        s = updates.desktop_state()
        self.assertFalse(s["managed"])


class Blocker(_WinCase):
    def test_09_a_normal_install_is_not_blocked(self):
        self.assertIsNone(updates.install_blocker())

    def test_10_the_portable_exe_is_told_to_install_once(self):
        with mock.patch.dict(os.environ, {"PORTABLE_EXECUTABLE_FILE": r"C:\Downloads\Sutra-x64.exe"}):
            msg = updates.install_blocker()
        self.assertIsNotNone(msg)
        self.assertIn("portable", msg)
        self.assertIn("Sutra-Setup-x64.exe", msg)

    def test_11_a_folder_without_the_uninstaller_is_treated_as_portable(self):
        (self.root / "Uninstall Sutra.exe").unlink()
        self.assertIn("portable", updates.install_blocker() or "")

    def test_31_an_all_users_install_is_refused_by_a_real_write_probe(self):
        """os.access(dir, W_OK) is always True on Windows, so it is not asked."""
        with mock.patch.object(updates.os, "access", return_value=True), \
             mock.patch.object(updates.tempfile, "mkstemp", side_effect=PermissionError(13, "denied")):
            msg = updates.install_blocker()
        self.assertIn(str(self.root), msg or "")
        self.assertIn("Only for me", msg or "")

    def test_29_a_beta_never_takes_the_stable_installer(self):
        """macOS refuses this by bundle-id continuity; Windows has no signature
        to compare, so the exe name is the identity."""
        beta = self.root / "Sutra Beta.exe"
        beta.write_bytes(b"MZ")
        with mock.patch.dict(os.environ, {"SUTRA_DESKTOP_EXE": str(beta)}):
            msg = updates.install_blocker()
        self.assertIn("stable", msg or "")


class Stage(_WinCase):
    def test_12_stage_dir_is_under_localappdata_and_skips_posix_ownership(self):
        with mock.patch.object(updates.os, "getuid", side_effect=AssertionError("posix only"),
                               create=True):
            d = updates.stage_dir()
        self.assertEqual(d, self.local / "Sutra" / "updates")
        self.assertTrue(d.is_dir())

    def test_30_beta_stages_apart_from_stable(self):
        """A shared manifest would let a beta launch arm stable's update."""
        beta = self.root / "Sutra Beta.exe"
        beta.write_bytes(b"MZ")
        with mock.patch.dict(os.environ, {"SUTRA_DESKTOP_EXE": str(beta)}):
            self.assertEqual(updates.stage_dir(), self.local / "Sutra Beta" / "updates")

    def test_33_a_portable_copy_never_downloads_by_any_route(self):
        """The HTTP route asked install_blocker first; the sidecar did not."""
        state = {"managed": True, "update_available": True, "latest": "2.305.0",
                 "installed": "2.304.1", "error": None}
        with mock.patch.dict(os.environ, {"PORTABLE_EXECUTABLE_FILE": r"C:\x\Sutra-x64.exe"}), \
             mock.patch.object(updates, "desktop_state", return_value=state), \
             mock.patch.object(updates, "download_and_verify",
                               side_effect=AssertionError("downloaded")):
            with self.assertRaises(RuntimeError) as cm:
                updates.stage_desktop()
        self.assertIn("portable", str(cm.exception))

    def test_34_arm_hands_the_staged_installer_to_the_helper_with_a_long_lease(self):
        sd = updates.stage_dir()
        exe = sd / "Sutra-Setup-x64-2.305.0.exe"
        exe.write_bytes(b"MZ-setup")
        updates._write_json(updates._pending_path(), {
            "state": "staged", "version": "2.305.0", "dmg": str(exe),
            "sha256": hashlib.sha256(b"MZ-setup").hexdigest(), "sha256_url": None,
            "asset": "Sutra-Setup-x64.exe", "install_failures": 0})
        with mock.patch.object(updates.subprocess, "Popen") as po:
            r = updates.arm_desktop(4242, relaunch=True)
        self.assertTrue(r["scheduled"])
        env = po.call_args.kwargs["env"]
        self.assertEqual(env["SETUP"], str(exe))
        self.assertEqual(env["RESULT"], str(sd / "install-result.json"))
        man = updates.read_pending()
        self.assertEqual(man["state"], "installing")
        # 120 s shell wait + 32 s leftovers + up to 600 s installer
        self.assertGreaterEqual(man["lease_until"] - man["armed_at"], 752)

    def test_13_commit_retires_older_staged_installers(self):
        sd = updates.stage_dir()
        old = sd / "Sutra-Setup-x64-2.300.0.exe"
        old.write_bytes(b"old")
        work = sd / ".download-x"
        work.mkdir()
        got = work / "Sutra-Setup-x64.exe"
        got.write_bytes(b"new")
        r = updates._commit_stage({"dmg": str(got)}, "2.305.0", "d" * 64,
                                  {"asset": "Sutra-Setup-x64.exe", "sha256_url": "u"},
                                  replaceable=None)
        self.assertTrue(r["staged"])
        self.assertFalse(old.exists())
        self.assertTrue(r["dmg"].endswith("Sutra-Setup-x64-2.305.0.exe"))


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Verify(_WinCase):
    def _latest(self, sha_url="https://x/Sutra-Setup-x64.exe.sha256"):
        return {"version": "2.305.0", "asset": "Sutra-Setup-x64.exe",
                "download_url": "https://x/Sutra-Setup-x64.exe", "size": 0,
                "sha256_url": sha_url, "error": None}

    def _fetch(self, url, path, want_bytes=0):
        Path(path).write_bytes(b"installer-bytes")

    def test_14_checksum_passes_and_gatekeeper_is_not_asked(self):
        digest = hashlib.sha256(b"installer-bytes").hexdigest()
        with mock.patch.object(updates, "_latest_desktop", return_value=self._latest()), \
             mock.patch.object(updates, "_fetch_dmg", side_effect=self._fetch), \
             mock.patch.object(updates.urllib.request, "urlopen",
                               return_value=_Resp(("%s  Sutra-Setup-x64.exe\n" % digest).encode())), \
             mock.patch.object(updates, "_run", side_effect=AssertionError("spctl on Windows")):
            got = updates.download_and_verify(dest_dir=str(self.tmp / "dl"))
        self.assertTrue(got["dmg"].endswith("Sutra-Setup-x64.exe"))
        self.assertEqual(got["version"], "2.305.0")

    def test_15_an_unreadable_checksum_refuses_the_unsigned_installer(self):
        with mock.patch.object(updates, "_latest_desktop", return_value=self._latest()), \
             mock.patch.object(updates, "_fetch_dmg", side_effect=self._fetch), \
             mock.patch.object(updates.urllib.request, "urlopen",
                               side_effect=updates.urllib.error.URLError("offline")):
            with self.assertRaises(RuntimeError) as cm:
                updates.download_and_verify(dest_dir=str(self.tmp / "dl"))
        self.assertIn("checksum", str(cm.exception))

    def test_16_a_release_with_no_checksum_file_is_refused(self):
        with mock.patch.object(updates, "_latest_desktop", return_value=self._latest(sha_url=None)), \
             mock.patch.object(updates, "_fetch_dmg", side_effect=self._fetch):
            with self.assertRaises(RuntimeError) as cm:
                updates.download_and_verify(dest_dir=str(self.tmp / "dl"))
        self.assertIn("checksum", str(cm.exception))


class Install(_WinCase):
    def _setup_exe(self):
        p = self.local / "Sutra-Setup-x64-2.305.0.exe"
        p.write_bytes(b"MZ-setup")
        return p

    def _spawn(self, relaunch=True, popen=None):
        calls = []

        def fake(argv, **kw):
            calls.append((argv, kw))
            if popen:
                return popen(argv, **kw)
            return mock.Mock()
        with mock.patch.object(updates.subprocess, "Popen", side_effect=fake):
            r = updates.install_desktop(str(self._setup_exe()), wait_pid=4242,
                                        relaunch=relaunch, version="2.305.0",
                                        result_path=str(self.local / "install-result.json"))
        return r, calls

    def test_17_helper_is_powershell_detached_with_every_input_named(self):
        r, calls = self._spawn()
        self.assertTrue(r["scheduled"])
        argv, kw = calls[-1]
        self.assertTrue(argv[0].lower().endswith("powershell.exe"), argv)
        self.assertIn("-File", argv)
        script = Path(argv[argv.index("-File") + 1])
        self.assertTrue(script.is_file())
        env = kw["env"]
        self.assertEqual(env["APP_DIR"], str(self.root))
        self.assertEqual(env["APP_EXE"], str(self.exe))
        self.assertEqual(env["WAIT_PID"], "4242")
        self.assertEqual(env["RELAUNCH"], "1")
        self.assertEqual(env["EXPECT_VERSION"], "2.305.0")
        self.assertTrue(env["SETUP"].endswith("Sutra-Setup-x64-2.305.0.exe"))
        self.assertEqual(env["RESULT"], str(self.local / "install-result.json"))
        self.assertTrue(kw["creationflags"] & 0x00000008, "DETACHED_PROCESS")
        # Never inside the install folder: a process's cwd pins that directory
        # while the installer removes the old version.
        self.assertEqual(Path(kw["cwd"]), script.parent)

    def test_18_quit_without_relaunch_does_not_reopen(self):
        _, calls = self._spawn(relaunch=False)
        self.assertEqual(calls[-1][1]["env"]["RELAUNCH"], "0")

    def test_19_a_job_that_forbids_breakaway_still_gets_its_helper(self):
        seen = []

        def popen(argv, **kw):
            seen.append(kw["creationflags"])
            if kw["creationflags"] & 0x01000000:
                raise OSError(5, "Access is denied")
            return mock.Mock()
        r, calls = self._spawn(popen=popen)
        self.assertTrue(r["scheduled"])
        self.assertEqual(len(seen), 2)
        self.assertFalse(seen[1] & 0x01000000)

    def test_20_refuses_anything_but_an_exe(self):
        bad = self.local / "Sutra.dmg"
        bad.write_bytes(b"x")
        with mock.patch.object(updates.subprocess, "Popen") as po:
            with self.assertRaises(RuntimeError):
                updates.install_desktop(str(bad), wait_pid=1, version="2.305.0")
        po.assert_not_called()

    def test_21_portable_refuses_before_spawning(self):
        with mock.patch.dict(os.environ, {"PORTABLE_EXECUTABLE_FILE": r"C:\x\Sutra-x64.exe"}), \
             mock.patch.object(updates.subprocess, "Popen") as po:
            with self.assertRaises(RuntimeError) as cm:
                updates.install_desktop(str(self._setup_exe()), wait_pid=1, version="2.305.0")
        self.assertIn("portable", str(cm.exception))
        po.assert_not_called()


class HelperScript(unittest.TestCase):
    S = updates._WIN_INSTALLER

    def test_22_installer_runs_silently_as_an_update_into_the_same_folder(self):
        self.assertIn("'--updated'", self.S)
        self.assertIn("'/S'", self.S)
        self.assertIn("'--force-run'", self.S)
        # NSIS takes /D= only as the LAST argument, unquoted.
        self.assertRegex(self.S, r"\$argList \+= \('/D=' \+ \$env:APP_DIR\)")
        self.assertLess(self.S.index("'--force-run'"), self.S.index("'/D='"))

    def test_23_waits_for_the_app_and_its_folder_before_installing(self):
        self.assertLess(self.S.index("WAIT_PID"), self.S.index("Process]::Start"))
        self.assertLess(self.S.index("procs-alive"), self.S.index("Process]::Start"))

    def test_35_a_sutra_reopened_after_the_helper_started_is_never_killed(self):
        """Only leftovers of the app that quit are stopped. A Sutra.exe newer
        than the helper is the user opening it again: leave it and the folder."""
        self.assertIn("$helperStart", self.S)
        self.assertLess(self.S.index("'app-reopened'"), self.S.index("Stop-Process"))
        self.assertIn("$psi.WorkingDirectory", self.S)

    def test_24_result_is_bom_free_json_in_the_shape_resolve_reads(self):
        self.assertIn("UTF8Encoding($false)", self.S)
        for k in ("ok", "stage", "version", "error", "ts"):
            self.assertRegex(self.S, r"\b%s\s*=" % k)

    def test_25_a_result_in_that_shape_resolves_as_applied(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            with mock.patch.dict(os.environ, {"SUTRA_UPDATE_DIR": str(tmp / "u")}):
                updates._write_json(updates._pending_path(), {
                    "state": "installing", "version": "2.305.0",
                    "dmg": str(tmp / "u" / "x.exe"), "lease_until": 0})
                (tmp / "u" / "install-result.json").write_text(json.dumps(
                    {"ok": True, "stage": "installed", "version": "2.305.0",
                     "error": "", "ts": 1}), encoding="utf-8")
                r = updates.resolve_pending("2.304.1")
            self.assertEqual(r.get("applied"), "2.305.0")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell parser only on Windows")
    def test_26_powershell_parses_the_helper(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            script = tmp / "install.ps1"
            script.write_text(self.S, encoding="utf-8-sig")
            cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::"
                   "ParseFile('%s',[ref]$null,[ref]$e); if ($e.Count) { $e | ForEach-Object "
                   "{ $_.ToString() }; exit 1 }" % str(script).replace("'", "''"))
            p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Plugin(unittest.TestCase):
    def test_27_claude_runs_by_full_path_so_an_npm_cmd_shim_works(self):
        shim = r"C:\Users\u\AppData\Roaming\npm\claude.cmd"
        argvs = []

        def run(argv, **kw):
            argvs.append(argv)
            return mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(updates.shutil, "which", return_value=shim), \
             mock.patch.object(updates.subprocess, "run", side_effect=run), \
             mock.patch.object(updates, "_installed_plugin_version", return_value="2.304.1"):
            updates.install_plugin()
        self.assertEqual([a[0] for a in argvs], [shim, shim])


class Shell(unittest.TestCase):
    MAIN = Path(HERE, "electron", "main.js").read_text(encoding="utf-8")

    def test_28_both_python_spawns_carry_the_windows_env(self):
        m = re.search(r"function winPythonEnv\(\)\s*\{(.*?)\n\}", self.MAIN, re.S)
        self.assertIsNotNone(m, "winPythonEnv() missing")
        body = m.group(1)
        for want in ("win32", "wincompat", "SUTRA_DESKTOP_VERSION", "SUTRA_DESKTOP_EXE"):
            self.assertIn(want, body)
        start = self.MAIN[self.MAIN.index("function startBackend()"):]
        start = start[:start.index("\n}\n")]
        self.assertIn("...winPythonEnv()", start)
        cli = self.MAIN[self.MAIN.index("function updateCli("):]
        cli = cli[:cli.index("\n}\n")]
        self.assertIn("...winPythonEnv()", cli)


if __name__ == "__main__":
    unittest.main()
