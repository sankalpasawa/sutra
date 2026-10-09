"""test_update_manual_button.py -- Settings -> "Download & install" (POST /api/updates/desktop).

THE BUG (2026-10-09). The delta lane (2026-09-25) made download_and_verify()
return {"kind": "app", "app": <rebuilt bundle>, "dmg": None} when the small
update works. This route still passed got["dmg"] to install_desktop(), so a
successful delta became Path(None) -> TypeError -> HTTP 500, and the button
could only ever finish by falling back to the full ~260 MB DMG.

Pins: the route hands install_desktop the rebuilt bundle for a delta, the image
for a full download, and install_desktop refuses an empty artifact with a
RuntimeError (which the route turns into a 400) rather than a TypeError.

Run: python -m unittest -v test_update_manual_button
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import updates  # noqa: E402


class ManualButtonRoute(unittest.TestCase):

    def setUp(self):
        import org_api
        self.api = org_api

    def _press(self, got):
        calls = []

        def fake_install(artifact, **kw):
            calls.append((artifact, kw))
            return {"scheduled": True}

        with mock.patch.object(updates, "install_blocker", return_value=None), \
                mock.patch.object(updates, "download_and_verify", return_value=got), \
                mock.patch.object(updates, "install_desktop", side_effect=fake_install):
            res = self.api.api_updates_desktop()
        return res, calls

    def test_a_delta_installs_the_rebuilt_bundle_not_none(self):
        res, calls = self._press({"kind": "app", "app": "/tmp/w/Sutra-2.306.24.app",
                                  "dmg": None, "version": "2.306.24"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "/tmp/w/Sutra-2.306.24.app")
        self.assertEqual(calls[0][1].get("version"), "2.306.24")
        self.assertTrue(calls[0][1].get("relaunch"))
        self.assertEqual(res["version"], "2.306.24")

    def test_a_full_image_still_installs_the_image(self):
        _, calls = self._press({"kind": "dmg", "dmg": "/tmp/w/Sutra-arm64.dmg",
                                "version": "2.306.24"})
        self.assertEqual(calls[0][0], "/tmp/w/Sutra-arm64.dmg")

    def test_windows_shape_without_a_kind_installs_the_setup_exe(self):
        # download_and_verify's Windows return carries no "kind".
        _, calls = self._press({"dmg": r"C:\u\Sutra-Setup-x64.exe", "version": "2.306.24"})
        self.assertEqual(calls[0][0], r"C:\u\Sutra-Setup-x64.exe")


class InstallDesktopRefusesNothing(unittest.TestCase):
    """An empty artifact is a RuntimeError the route reports, never a TypeError
    that escapes as a 500."""

    @unittest.skipIf(sys.platform == "win32", "the macOS leg; Windows has its own guard")
    def test_none_artifact_is_a_runtime_error(self):
        app = os.path.join(HERE, "Fixture.app")
        with mock.patch.object(updates, "install_blocker", return_value=None), \
                mock.patch.object(updates, "app_bundle", return_value=None), \
                mock.patch("pathlib.Path.is_dir", return_value=True):
            with self.assertRaises(RuntimeError):
                updates.install_desktop(None, app_path=app)


if __name__ == "__main__":
    unittest.main()
