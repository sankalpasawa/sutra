"""test_update_install_guard.py -- refusing an update the machine cannot install.

The failure this pins actually happened. A user ran Sutra straight out of the
installer window for weeks: the app opened, worked, and never said it had not
been installed. A disk image is read-only, so every update was impossible, and
when one was finally attempted the only thing said was

    /Volumes/Sutra 2.238.0 is not writable by this user -- install the DMG manually

after a 240MB download. Two defects in one line: the reason was a permission
bit rather than the cause, and it was learned last rather than first.

So this file pins both halves:

  1. install_blocker() names the disk image in words a person can act on, and
     stays quiet for a normal install and for a source checkout.
  2. Both download routes ask it BEFORE they fetch anything, so a machine that
     can never install is told immediately and never downloads at all -- the
     automatic path included, which would otherwise re-download every tick
     forever.

Run: .venv/bin/python -m pytest -q test_update_install_guard.py
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import updates  # noqa: E402


class Blocker(unittest.TestCase):
    """What install_blocker() says, and when it says nothing."""

    def test_01_running_from_a_disk_image_is_named_in_plain_words(self):
        msg = updates.install_blocker(Path("/Volumes/Sutra 2.238.0/Sutra.app"))
        self.assertIsNotNone(msg)
        # The cause, not the symptom.
        self.assertIn("disk image", msg)
        self.assertIn("read-only", msg)
        # And the fix, in the order a person does it.
        self.assertIn("Applications", msg)
        self.assertIn("Quit", msg)
        # Never the thing that confused the user.
        self.assertNotIn("not writable by this user", msg)

    def test_02_a_normal_install_is_not_blocked(self):
        with mock.patch.object(updates.os, "access", return_value=True):
            self.assertIsNone(updates.install_blocker(Path("/Applications/Sutra.app")))

    def test_03_a_source_checkout_is_not_blocked(self):
        """app_bundle() is None outside a .app; git updates that install."""
        with mock.patch.object(updates, "app_bundle", return_value=None):
            self.assertIsNone(updates.install_blocker())

    def test_04_an_unwritable_normal_folder_still_refuses_but_says_where(self):
        with mock.patch.object(updates.os, "access", return_value=False):
            msg = updates.install_blocker(Path("/Applications/Sutra.app"))
        self.assertIsNotNone(msg)
        self.assertIn("/Applications", msg)
        self.assertIn("cannot write", msg)

    def test_05_the_default_argument_reads_the_running_bundle(self):
        with mock.patch.object(updates, "app_bundle",
                               return_value=Path("/Volumes/Sutra 9.9.9/Sutra.app")):
            self.assertIn("disk image", updates.install_blocker())

    def test_06_install_desktop_refuses_with_the_same_sentence(self):
        """The installer asks install_blocker() rather than carrying a second
        copy of the rule, so the message cannot depend on which path reached it.

        A real directory is needed: install_desktop sanity-checks that the
        target is an actual .app before it ever asks about writability, and
        that order is correct -- a bogus path is a different bug.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp, "Sutra.app")
            (bundle / "Contents").mkdir(parents=True)
            with mock.patch.object(updates, "install_blocker",
                                   return_value="Sutra is running from the "
                                                "installer disk image.") as blocker:
                with self.assertRaises(RuntimeError) as caught:
                    updates.install_desktop("/tmp/whatever.dmg", app_path=bundle)
            blocker.assert_called_once()
        self.assertIn("disk image", str(caught.exception))


class CheckedBeforeTheDownload(unittest.TestCase):
    """The ordering defect: the user paid for a 240MB download to be refused."""

    def setUp(self):
        import org_api
        self.org_api = org_api

    def _blocked(self):
        return mock.patch.object(
            self.org_api.updates, "install_blocker",
            return_value="Sutra is running from the installer disk image.")

    def test_10_manual_button_refuses_without_downloading(self):
        from fastapi import HTTPException
        with self._blocked(), mock.patch.object(
                self.org_api.updates, "download_and_verify") as dl:
            with self.assertRaises(HTTPException) as caught:
                self.org_api.api_updates_desktop()
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("disk image", caught.exception.detail)
        dl.assert_not_called()

    def test_11_automatic_staging_refuses_without_downloading(self):
        """Left unguarded this is the worse one: it runs on a schedule, so it
        would re-fetch the whole DMG every tick on a machine that can never
        install it, forever, with nobody watching."""
        from fastapi import HTTPException
        request = mock.Mock()
        with mock.patch.object(self.org_api, "_desktop_control", return_value=None), \
                self._blocked(), \
                mock.patch.object(self.org_api.updates, "stage_desktop") as stage:
            with self.assertRaises(HTTPException) as caught:
                self.org_api.api_updates_stage(request)
        self.assertEqual(caught.exception.status_code, 400)
        stage.assert_not_called()

    def test_12_an_installable_machine_still_downloads(self):
        """The guard must not become a way to never update."""
        with mock.patch.object(self.org_api.updates, "install_blocker", return_value=None), \
                mock.patch.object(self.org_api.updates, "download_and_verify",
                                  return_value={"dmg": "/tmp/x.dmg", "version": "9.9.9"}) as dl, \
                mock.patch.object(self.org_api.updates, "install_desktop",
                                  return_value={"scheduled": True}):
            out = self.org_api.api_updates_desktop()
        dl.assert_called_once()
        self.assertEqual(out["version"], "9.9.9")


class ShellGuard(unittest.TestCase):
    """main.js has to ASK before it boots, or the backend it starts is the one
    that cannot update. Read as text: Electron's app object is not importable
    here, and the check is worth pinning anyway."""

    def setUp(self):
        self.src = Path(HERE, "electron", "main.js").read_text(encoding="utf-8")

    def test_20_boot_asks_first(self):
        i_boot = self.src.index("async function boot() {")
        i_ask = self.src.index("await ensureInstalled()", i_boot)
        i_backend = self.src.index("backend = startBackend()", i_boot)
        self.assertLess(i_ask, i_backend,
                        "the install check must run before the backend starts")

    def test_21_it_offers_to_move_rather_than_only_complaining(self):
        self.assertIn("moveToApplicationsFolder", self.src)
        self.assertIn("Move to Applications", self.src)

    def test_22_ditto_not_cp_for_the_fallback_copy(self):
        """A plain recursive copy breaks the code signature inside a .app and
        the copy will not launch with Gatekeeper awake."""
        self.assertIn("/usr/bin/ditto", self.src)

    def test_23_do_not_ask_again_is_honoured(self):
        self.assertIn("checkboxLabel", self.src)
        self.assertIn("skip-move-to-applications", self.src)
        # The async dialog is the only form that reports the checkbox.
        self.assertIn("await dialog.showMessageBox(", self.src)

    def test_24_a_dev_checkout_is_never_prompted(self):
        self.assertIn("!app.isPackaged", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
