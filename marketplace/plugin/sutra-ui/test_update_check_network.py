"""test_update_check_network.py -- the Updates check never turns a bad network into a 500.

Found 2026-10-07 on the Windows app: Settings > Updates sometimes said

    Could not check. /api/updates -> 500

The check reads two things from GitHub. A connection that drops part-way through
a response body raises http.client.IncompleteRead, which is an HTTPException and
NOT an OSError, so it slipped past `except (URLError, ValueError, OSError)` in
both readers, out of all_state(), and FastAPI answered 500. Reproduced against
the installed app's own Python with a server that promises 500 bytes and hangs
up after 18.

Pinned here:
  1. Every http.client failure from either GitHub read is reported as that
     component's error, with the rest of the answer intact.
  2. all_state() never raises, whatever a component throws -- the failing
     component's row says "check failed" and the other rows still render.
  3. A check against a GitHub that drops mid-body returns a full answer (through
     a socket server that really does hang up).

Run: .venv/bin/python -m pytest -q test_update_check_network.py
"""
import http.client
import os
import socket
import sys
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import updates  # noqa: E402


HTTP_FAILURES = [
    http.client.IncompleteRead(b"{\"tag", 482),
    http.client.BadStatusLine("garbage"),
    http.client.LineTooLong("header line"),
    http.client.HTTPException("anything else http.client raises"),
]


class ReadersSurviveHttpClientErrors(unittest.TestCase):

    def test_desktop_reader_reports_instead_of_raising(self):
        for exc in HTTP_FAILURES:
            with self.subTest(exc=type(exc).__name__), \
                    mock.patch.object(updates, "_get_json", side_effect=exc):
                got = updates._latest_desktop()
                self.assertIn("could not reach GitHub", got["error"])

    def test_plugin_reader_reports_instead_of_raising(self):
        for exc in HTTP_FAILURES:
            with self.subTest(exc=type(exc).__name__), \
                    mock.patch.object(updates.urllib.request, "urlopen", side_effect=exc):
                version, err = updates._latest_plugin()
                self.assertIsNone(version)
                self.assertIn("could not reach GitHub", err)

    def test_non_dict_payloads_are_errors_not_crashes(self):
        with mock.patch.object(updates, "_get_json", return_value=["not", "a", "release"]):
            self.assertIn("could not reach GitHub", updates._latest_desktop()["error"])

    def test_checksum_reader_treats_a_cut_body_as_unreadable(self):
        with mock.patch.object(updates.urllib.request, "urlopen",
                               side_effect=http.client.IncompleteRead(b"", 64)):
            self.assertIsNone(updates._published_sha256("https://example.invalid/x.sha256"))


class AllStateNeverRaises(unittest.TestCase):

    def test_each_component_fails_alone(self):
        boom = RuntimeError("something nobody has met yet")
        for name in ("desktop_state", "plugin_state", "pending_state"):
            with self.subTest(component=name), \
                    mock.patch.object(updates, "desktop_state", return_value={"component": "desktop", "ok": 1}), \
                    mock.patch.object(updates, "plugin_state", return_value={"component": "plugin", "ok": 1}), \
                    mock.patch.object(updates, "pending_state", return_value={"pending": False, "ok": 1}), \
                    mock.patch.object(updates, name, side_effect=boom):
                got = updates.all_state()
                failed = {"desktop_state": "desktop", "plugin_state": "plugin",
                          "pending_state": "staged"}[name]
                self.assertIn("something nobody has met yet", got[failed]["error"])
                for other in {"desktop", "plugin", "staged"} - {failed}:
                    self.assertEqual(got[other].get("ok"), 1)

    def test_failed_component_still_renders_as_a_managed_row(self):
        # The panel shows "check failed" only for managed rows; an unmanaged one
        # would read "updates on its own", which would hide the failure.
        with mock.patch.object(updates, "desktop_state", side_effect=OSError("x")), \
                mock.patch.object(updates, "plugin_state", side_effect=OSError("y")), \
                mock.patch.object(updates, "pending_state", return_value={"pending": False}):
            got = updates.all_state()
        self.assertTrue(got["desktop"]["managed"])
        self.assertTrue(got["plugin"]["managed"])


def _hang_up_mid_body_server():
    """A 'GitHub' that promises 500 bytes, sends 18, and closes."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            try:
                c.recv(65536)
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                          b"Content-Length: 500\r\n\r\n{\"tag_name\": \"v2.3")
            finally:
                c.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv


class RouteAnswers200WhenGitHubDropsMidBody(unittest.TestCase):

    def test_end_to_end(self):
        srv = _hang_up_mid_body_server()
        url = "http://127.0.0.1:%d" % srv.getsockname()[1]
        try:
            with mock.patch.object(updates, "RELEASE_API", url), \
                    mock.patch.object(updates, "_installed_desktop_version", return_value="2.306.0"), \
                    mock.patch.object(updates, "_installed_app", return_value="C:/fake/Sutra"), \
                    mock.patch.object(updates, "_latest_plugin", return_value=("2.306.23", None)), \
                    mock.patch.object(updates, "pending_state", return_value={"pending": False}):
                got = updates.all_state()
        finally:
            srv.close()
        self.assertTrue(got["desktop"]["managed"])
        self.assertEqual(got["desktop"]["installed"], "2.306.0")
        self.assertIn("IncompleteRead", got["desktop"]["error"])
        self.assertFalse(got["desktop"]["update_available"])
        self.assertEqual(got["plugin"]["latest"], "2.306.23")


if __name__ == "__main__":
    unittest.main()
