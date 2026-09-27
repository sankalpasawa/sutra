"""test_update_delta_live.py -- the delta update, live, on a real Mac.

test_update_e2e.py runs the whole pipeline against fixture releases, but it
has to shim `spctl`: an ad-hoc fixture bundle is never notarized. So no test
had run Gatekeeper on a rebuilt bundle. On 2026-09-27 a 377 KB delta
(2.304.3 -> 2.304.4) turned into a 257 MB download on the founder's Mac and
the reason was lost.

This test runs the INSTALLED app's own updater exactly as the Electron shell
spawns it (the bundle's python, `-m updates_cli stage`, cwd = the bundled
sutra-ui) against the REAL latest GitHub release, with real codesign and real
Gatekeeper. The only difference from the app: SUTRA_UPDATE_DIR points at a
temp dir, so nothing is armed and the user's stage is never touched.

Pass = the release was staged as a rebuilt bundle (artifact_kind "app") with
no fallback note, and the full image was never needed.

Opt-in (network, an installed app, a newer release):
    SUTRA_UPDATE_LIVE=1 python -m unittest test_update_delta_live
Skips when the installed app is already on the latest release.
"""
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(os.environ.get("SUTRA_LIVE_APP", "/Applications/Sutra.app"))
PAYLOAD = APP / "Contents" / "Resources" / "payload"
PY = PAYLOAD / "python" / "bin" / "python3"
UI = PAYLOAD / "plugin" / "sutra-ui"


def _installed():
    with open(APP / "Contents" / "Info.plist", "rb") as fh:
        return plistlib.load(fh).get("CFBundleShortVersionString")


@unittest.skipUnless(os.environ.get("SUTRA_UPDATE_LIVE") == "1", "live test: set SUTRA_UPDATE_LIVE=1")
@unittest.skipUnless(sys.platform == "darwin", "the delta lane is macOS only")
class DeltaLive(unittest.TestCase):

    def setUp(self):
        if not (PY.is_file() and (UI / "updates_cli.py").is_file()):
            self.skipTest("no installed Sutra.app at %s" % APP)
        self.stage = Path(tempfile.mkdtemp(prefix="sutra-delta-live-"))
        self.addCleanup(shutil.rmtree, self.stage, True)

    def cli(self, *args, timeout=900):
        env = dict(os.environ, SUTRA_UPDATE_DIR=str(self.stage), PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([str(PY), "-m", "updates_cli", *args], cwd=str(UI), env=env,
                           capture_output=True, text=True, timeout=timeout)
        self.assertTrue(p.stdout.strip(), "no answer from updates_cli %s: %s" % (args, p.stderr[-800:]))
        return json.loads(p.stdout)

    def test_installed_app_stages_the_real_release_as_a_delta(self):
        check = self.cli("check", timeout=120)
        desk = check.get("desktop") or {}
        if not desk.get("update_available"):
            self.skipTest("installed %s is already the latest release" % _installed())
        self.assertTrue(desk.get("delta"), "the latest release publishes no delta for this Mac: %s" % desk)

        out = self.cli("stage")
        self.assertTrue(out.get("staged"), out)
        self.assertIsNone(out.get("note"), "the delta lane fell back: %s" % out.get("note"))
        self.assertEqual(out.get("artifact_kind"), "app", out)
        self.assertGreaterEqual((out.get("delta") or {}).get("hops", 0), 1, out)

        staged = Path(out["dmg"])
        self.assertEqual(staged.parent.resolve(), self.stage.resolve(), "staged outside the temp dir")
        for cmd in (["codesign", "--verify", "--deep", "--strict", str(staged)],
                    ["spctl", "-a", "-t", "execute", "-v", str(staged)]):
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, "%s: %s" % (cmd[0], (p.stderr or p.stdout)[-500:]))
        self.assertFalse(list(self.stage.glob("*.dmg")), "the full image was downloaded")
        self.assertFalse((self.stage / "delta-misses.jsonl").exists(), "a delta miss was logged")


if __name__ == "__main__":
    unittest.main()
