"""Unit tests for sb_sidecar — no network, no real binary.

The PoC (atom a-78660f98-06) validated the live binary; these tests pin the
module's POLICY: edit-gate coupling, marker-fenced injection, fail-closed
pinning, env construction, and status shape.
"""

import os
import tempfile
import unittest
from unittest import mock

import providers
import sb_sidecar


class InjectTheme(unittest.TestCase):
    def test_no_injection_when_editing_disabled(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(providers, "editing_allowed", return_value=False):
                self.assertFalse(sb_sidecar.inject_theme(root))
            self.assertFalse(os.path.exists(os.path.join(root, "THEME.md")))

    def test_injects_once_when_editing_enabled(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(providers, "editing_allowed", return_value=True):
                self.assertTrue(sb_sidecar.inject_theme(root))
                path = os.path.join(root, "THEME.md")
                self.assertTrue(open(path).read().startswith(sb_sidecar.THEME_MARKER))
                # second call: recognized as ours, not rewritten
                before = os.stat(path).st_mtime_ns
                self.assertTrue(sb_sidecar.inject_theme(root))
                self.assertEqual(os.stat(path).st_mtime_ns, before)

    def test_never_overwrites_user_theme(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "THEME.md")
            with open(path, "w") as fh:
                fh.write("# my own theme\n")
            with mock.patch.object(providers, "editing_allowed", return_value=True):
                self.assertFalse(sb_sidecar.inject_theme(root))
            self.assertEqual(open(path).read(), "# my own theme\n")


class EnvConstruction(unittest.TestCase):
    def test_readonly_env(self):
        env = sb_sidecar._sb_env(True, 4321)
        self.assertEqual(env["SB_READ_ONLY"], "1")
        self.assertEqual(env["SB_PORT"], "4321")
        self.assertEqual(env["SB_HOSTNAME"], "127.0.0.1")
        self.assertEqual(env["SB_DISABLE_SERVICE_WORKER"], "1")
        self.assertEqual(env["SB_RUNTIME_API"], "0")

    def test_readwrite_env_has_no_readonly_flag(self):
        with mock.patch.dict(os.environ, {"SB_READ_ONLY": "1"}):
            env = sb_sidecar._sb_env(False, 4321)
        self.assertNotIn("SB_READ_ONLY", env)


class Pinning(unittest.TestCase):
    def test_missing_pin_fails_closed(self):
        with mock.patch.object(sb_sidecar.platform, "machine", return_value="x86_64"), \
             mock.patch.dict(sb_sidecar.SB_ASSETS["x86_64"], {"sha256": ""}), \
             mock.patch.object(sb_sidecar, "binary_path",
                               return_value="/nonexistent/sb-bin"):
            with self.assertRaises(RuntimeError):
                sb_sidecar.ensure_binary()

    def test_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sb_sidecar, "_bin_dir", return_value=tmp), \
                 mock.patch.object(sb_sidecar, "_bundled_binary", return_value=None), \
                 mock.patch.object(sb_sidecar.platform, "machine", return_value="arm64"), \
                 mock.patch.object(sb_sidecar.urllib.request, "urlretrieve",
                                   side_effect=lambda url, dst: open(dst, "wb").write(b"junk")):
                with self.assertRaises(RuntimeError) as ctx:
                    sb_sidecar.ensure_binary()
                self.assertIn("sha256 mismatch", str(ctx.exception))
                # the bad download must not survive
                self.assertEqual([f for f in os.listdir(tmp) if f.endswith(".zip")], [])


class StartPolicy(unittest.TestCase):
    def test_root_outside_home_refused(self):
        with mock.patch.object(providers, "workdir_allowed", return_value=False):
            with self.assertRaises(RuntimeError):
                sb_sidecar.start("/etc")

    def test_status_shape(self):
        st = sb_sidecar.status()
        for key in ("running", "port", "root", "readonly", "version", "error"):
            self.assertIn(key, st)
        self.assertEqual(st["version"], sb_sidecar.SB_VERSION)


if __name__ == "__main__":
    unittest.main()
