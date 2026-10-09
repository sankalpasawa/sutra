"""test_update_e2e_windows.py -- the Windows delta lane, end to end, against fixture releases.

Windows had no incremental update until 2026-10-09: every update downloaded the
whole 240 MB Sutra-Setup-x64.exe. The delta lane now rebuilds the install
folder from the installed one plus a pack, and the PowerShell helper renames it
into place. This file runs that for real on Windows, the way test_update_e2e.py
does on a Mac.

WHAT RUNS FOR REAL: the `updates_cli` subprocess (check / stage / arm
--wait-pid / resolve), the HTTP download from a local release server speaking
GitHub's two shapes, the manifest and pack fetch with their published
checksums, updates_delta reconstruction, the detached PowerShell helper waiting
on a real pid, the uninstaller carried across, the two-rename swap, the
FileVersion gate read from a real PE (this Python's own exe stands in for
Sutra.exe), rollback, and the Apps-list entry rewrite (under a throwaway
registry key, via SUTRA_TEST_UNINSTALL_KEY, never the real list).

Scenarios: delta end to end; a modified install falls back to the full
installer and logs why; a FileVersion mismatch after the swap puts the old
install back; an install left aside by a crashed swap is restored first.

Windows only. Run (from sutra-ui, with the wincompat shims on the path):
  PYTHONPATH=electron/wincompat python -m unittest -v test_update_e2e_windows
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import updates  # noqa: E402
import updates_delta as ud  # noqa: E402
from test_update_e2e import REPO, ReleaseServer, sidecar  # noqa: E402

IS_WIN = sys.platform == "win32"
ARCH = "win-x64"
BUNDLE_ID = "os.sutra.ui"
RND = random.Random(11)
ASAR = bytes(RND.getrandbits(8) for _ in range(1_500_000))
V1 = "1.0.0"


def _file_version(path):
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "(Get-Item -LiteralPath '%s').VersionInfo.FileVersion" % path],
                       capture_output=True, text=True, timeout=60)
    return p.stdout.strip()


EXE = Path(getattr(sys, "_base_executable", "") or sys.executable)
V2 = _file_version(EXE) if IS_WIN else ""
USABLE = IS_WIN and re.fullmatch(r"\d+(\.\d+)+", V2 or "") and updates._newer(V2, V1)


def make_tree(dest, exe_tail, asar, extra):
    """An install folder shaped like electron-builder's, without the uninstaller
    (a release tree never has one; NSIS writes it at install time)."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "resources" / "payload" / "plugin").mkdir(parents=True)
    (dest / "locales").mkdir()
    (dest / "Sutra.exe").write_bytes(EXE.read_bytes() + exe_tail)
    (dest / "resources" / "channel").write_text("stable\n")
    (dest / "resources" / "app.asar").write_bytes(asar)
    (dest / "locales" / "en-US.pak").write_bytes(b"pak" * 1000)
    for rel, data in extra.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return dest


def tree_v1(dest):
    return make_tree(dest, b"\x00v1-overlay" * 50, ASAR,
                     {"resources/payload/plugin/app.py": b"print('v1')\n" * 200,
                      "resources/payload/plugin/gone.py": b"# removed in v2\n"})


def tree_v2(dest):
    asar = bytearray(ASAR)
    asar[1000:1016] = b"v2-changed-bytes"
    return make_tree(dest, b"", bytes(asar),
                     {"resources/payload/plugin/app.py": b"print('v1')\n" * 199 + b"print('v2')\n",
                      "resources/payload/plugin/added.py": b"# new in v2\n"})


@unittest.skipUnless(USABLE, "Windows only, with a Python exe that carries a FileVersion")
class WindowsDeltaEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="sutra-e2e-win-"))
        cls.v1 = tree_v1(cls.root / "v1")
        cls.v2 = tree_v2(cls.root / "v2")
        cls.releases = {}
        for ver in (V2, "999.0.0"):          # 999.0.0: same tree, wrong FileVersion
            d = cls.root / ("release-" + ver)
            d.mkdir()
            setup = d / updates.WIN_SETUP_ASSET
            setup.write_bytes(b"MZ not a real installer " * 4000)
            man = ud.build_manifest(cls.v2, ver, ARCH, "stable", BUNDLE_ID,
                                    tag="v%s-desktop" % ver, previous_version=V1)
            mp = d / ("Sutra-%s.manifest.json" % ARCH)
            mp.write_text(json.dumps(man, sort_keys=True, separators=(",", ":")))
            pk = d / ("Sutra-%s.delta.tar.xz" % ARCH)
            ud.build_pack(cls.v1, cls.v2, man, pk, from_version=V1)
            cls.releases[ver] = {"files": [setup, mp, pk, sidecar(setup), sidecar(mp), sidecar(pk)],
                                 "setup": setup, "pack": pk, "man": man}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(prefix="case-", dir=str(self.root)))
        self.installed = self.case / "Programs" / "Sutra"
        shutil.copytree(self.v1, self.installed)
        (self.installed / "Uninstall Sutra.exe").write_bytes(b"MZ uninstaller")
        self.stage = self.case / "updates"
        self.server = ReleaseServer()
        self.reg = r"HKCU:\Software\SutraUpdateTest\%s" % uuid.uuid4().hex
        self.waiters = []

    def tearDown(self):
        self.server.close()
        for w in self.waiters:
            if w.poll() is None:
                w.kill()
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Remove-Item -LiteralPath '%s' -Recurse -Force -ErrorAction SilentlyContinue"
                        % self.reg], capture_output=True, timeout=60)

    # ---- helpers
    def env(self):
        env = dict(os.environ)
        env.update({
            "SUTRA_UI_RELEASE_API": self.server.base,
            "SUTRA_UI_RELEASE_DOWNLOAD": self.server.base,
            "SUTRA_UI_DESKTOP_REPO": REPO,
            "SUTRA_UPDATE_DIR": str(self.stage),
            "SUTRA_UI_WIN_INSTALL": str(self.installed),
            "SUTRA_DESKTOP_EXE": str(self.installed / "Sutra.exe"),
            "SUTRA_DESKTOP_VERSION": V1,
            "SUTRA_TEST_UNINSTALL_KEY": self.reg,
            "PYTHONPATH": str(HERE / "electron" / "wincompat"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        env.pop("PORTABLE_EXECUTABLE_FILE", None)
        return env

    def cli(self, *args, expect=0):
        p = subprocess.run([sys.executable, "-m", "updates_cli", *args], cwd=str(HERE),
                           env=self.env(), capture_output=True, text=True, timeout=600)
        out = json.loads(p.stdout.strip().splitlines()[-1])
        if expect is not None:
            self.assertEqual(p.returncode, expect, out)
        return out

    def publish(self, ver):
        self.server.publish("v%s-desktop" % ver, self.releases[ver]["files"])

    def fake_apps_entry(self):
        key = self.reg + r"\{sutra-test}"
        cmd = ("New-Item -Path '{k}' -Force | Out-Null; "
               "Set-ItemProperty -LiteralPath '{k}' -Name DisplayName -Value 'Sutra {v}'; "
               "Set-ItemProperty -LiteralPath '{k}' -Name DisplayVersion -Value '{v}'; "
               "Set-ItemProperty -LiteralPath '{k}' -Name UninstallString "
               "-Value '\"{u}\" /currentuser'").format(
                   k=key, v=V1, u=self.installed / "Uninstall Sutra.exe")
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return key

    def read_apps_entry(self, key):
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "$k = Get-ItemProperty -LiteralPath '%s'; $k.DisplayName; $k.DisplayVersion" % key],
                           capture_output=True, text=True, timeout=60)
        return p.stdout.split()

    def waiter(self):
        w = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        self.waiters.append(w)
        return w

    def arm_and_wait(self):
        w = self.waiter()
        out = self.cli("arm", "--wait-pid", str(w.pid))
        self.assertTrue(out.get("scheduled"), out)
        self.log_path = out.get("log")
        w.kill()
        w.wait()
        result = self.stage / "install-result.json"
        for _ in range(240):
            if result.exists():
                break
            time.sleep(0.5)
        self.assertTrue(result.exists(), "the helper never reported back: %s" % self.helper_log())
        return json.loads(result.read_text(encoding="utf-8"))

    def helper_log(self):
        p = Path(getattr(self, "log_path", None) or "")
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
        return "(no log at %s)" % p

    def assert_tree(self, path, tree, uninstaller=True):
        man = ud.build_manifest(tree, "x", ARCH, "stable", BUNDLE_ID)
        probe = self.case / "probe"
        if probe.exists():
            shutil.rmtree(probe)
        shutil.copytree(path, probe)
        u = probe / "Uninstall Sutra.exe"
        self.assertEqual(u.is_file(), uninstaller, "uninstaller presence")
        if u.exists():
            u.unlink()
        self.assertEqual(ud.verify_tree(probe, man), [])

    def leftovers(self):
        parent = self.installed.parent
        return sorted(p.name for p in parent.iterdir() if p.name != self.installed.name)

    # ---- scenarios
    def test_delta_end_to_end(self):
        self.publish(V2)
        key = self.fake_apps_entry()
        chk = self.cli("check")
        self.assertTrue(chk.get("ok", True), chk)
        st = self.cli("stage")
        self.assertTrue(st.get("staged"), st)
        man = json.loads((self.stage / "pending-update.json").read_text(encoding="utf-8"))
        self.assertEqual(man["artifact_kind"], "app", man)
        self.assertEqual(man["version"], V2)
        # The 96 KB "installer" was never fetched: only the manifest and the pack.
        self.assertEqual(self.server.hits(updates.WIN_SETUP_ASSET), [])
        self.assertTrue(self.server.hits("Sutra-%s.delta.tar.xz" % ARCH))

        res = self.arm_and_wait()
        self.assertTrue(res.get("ok"), "%s\n%s" % (res, self.helper_log()))
        self.assert_tree(self.installed, self.v2)
        self.assertEqual(self.leftovers(), [], "no .sutra-new / .sutra-old left beside the install")
        self.assertEqual(self.read_apps_entry(key), ["Sutra", V2, V2])
        out = self.cli("resolve", "--installed", V2)
        self.assertFalse((self.stage / "pending-update.json").exists(), out)

    def test_modified_install_falls_back_to_the_full_installer(self):
        self.publish(V2)
        (self.installed / "resources" / "app.asar").write_bytes(b"edited by hand")
        st = self.cli("stage")
        self.assertTrue(st.get("staged"), st)
        man = json.loads((self.stage / "pending-update.json").read_text(encoding="utf-8"))
        self.assertEqual(man["artifact_kind"], "dmg")
        self.assertTrue(man["dmg"].lower().endswith(".exe"), man)
        misses = (self.stage / "delta-misses.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(misses[-1])["to"], V2)

    def test_wrong_file_version_puts_the_old_install_back(self):
        self.publish("999.0.0")
        st = self.cli("stage")
        self.assertTrue(st.get("staged"), st)
        res = self.arm_and_wait()
        self.assertFalse(res.get("ok"), res)
        self.assertEqual(res.get("stage"), "version", res)
        self.assertEqual((self.installed / "resources" / "payload" / "plugin" / "gone.py").read_bytes(),
                         b"# removed in v2\n")
        self.assertTrue((self.installed / "Uninstall Sutra.exe").is_file())
        self.assertEqual(self.leftovers(), [])

    def test_an_install_left_aside_by_a_crash_is_restored_first(self):
        """The helper died between its two renames last time: the install sits
        at <app>.sutra-old and nothing is at <app>. Run the helper script
        directly (arm refuses a missing install, rightly) and check it puts
        the install back before swapping."""
        staged = self.case / "staged.app"
        shutil.copytree(self.v2, staged)
        aside = Path(str(self.installed) + ".sutra-old")
        os.rename(self.installed, aside)
        script = self.case / "install.ps1"
        script.write_text(updates._WIN_INSTALLER, encoding="utf-8")
        result = self.case / "result.json"
        w = self.waiter()
        w.kill()
        w.wait()
        env = self.env()
        env.update({"SETUP": str(staged), "ARTIFACT_KIND": "app", "APP_DIR": str(self.installed),
                    "APP_EXE": str(self.installed / "Sutra.exe"), "LOG": str(self.case / "install.log"),
                    "WAIT_PID": str(w.pid), "RELAUNCH": "0", "EXPECT_VERSION": V2,
                    "RESULT": str(result)})
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", str(script)], env=env, capture_output=True, text=True, timeout=600)
        log = (self.case / "install.log").read_text(encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0, log + p.stdout + p.stderr)
        self.assertIn("left aside by an earlier attempt", log)
        self.assertTrue(json.loads(result.read_text(encoding="utf-8"))["ok"])
        self.assert_tree(self.installed, self.v2)
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
