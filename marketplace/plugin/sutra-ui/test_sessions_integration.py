"""A real chat turn must populate Sutra's own session store.

test_sessions_store.py proves the store's contract in isolation; that is not the
same claim. This drives the actual /ws/chat socket against the scripted fake CLI
and asserts the conversation landed in Sutra's records -- identity minted,
provider handle bound, both turns transcribed. Without this, every wiring bug
between app.py and sessions_store.py is invisible.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request

from test_runtime_characterization import FAKE, VENV_PY, HERE, _free_port

import sessions_store as ss


class SessionsIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-sessint-")
        cls.sessions = os.path.join(cls.tmpdir, "sessions")
        cls.fake = os.path.join(cls.tmpdir, "fake-claude")
        with open(cls.fake, "w") as f:
            f.write(FAKE)
        os.chmod(cls.fake, 0o755)
        cls._saved = {k: os.environ.get(k) for k in
                      ("SUTRA_UI_SETTINGS", "SUTRA_UI_CLAUDE_BIN",
                       "SUTRA_UI_WORKDIR_ROOT", "SUTRA_UI_SESSIONS",
                       "SUTRA_UI_PROVIDER", "SUTRA_UI_PERMISSION_MODE")}
        os.environ["SUTRA_UI_SETTINGS"] = os.path.join(cls.tmpdir, "settings.json")
        os.environ["SUTRA_UI_CLAUDE_BIN"] = cls.fake
        os.environ["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        os.environ["SUTRA_UI_SESSIONS"] = cls.sessions
        os.environ.pop("SUTRA_UI_PROVIDER", None)
        os.environ.pop("SUTRA_UI_PERMISSION_MODE", None)
        cls.port = _free_port()
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=dict(os.environ),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("server did not come up")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
        for k, v in cls._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _turn(self, message, sutra_session=None, timeout=20):
        from websockets.sync.client import connect
        payload = {"message": message}
        if sutra_session:
            payload["sutra_session"] = sutra_session
        frames = []
        with connect("ws://127.0.0.1:%d/ws/chat" % self.port,
                     open_timeout=10, close_timeout=5) as ws:
            ws.send(json.dumps(payload))
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw = ws.recv(timeout=max(0.1, deadline - time.time()))
                except Exception:
                    break
                fr = json.loads(raw)
                frames.append(fr)
                if fr.get("type") in ("done", "error"):
                    break
        return frames

    # ---------------------------------------------------------------- tests

    def test_turn_creates_a_sutra_session_and_binds_the_handle(self):
        frames = self._turn("hello there")
        kinds = [f["type"] for f in frames]
        self.assertIn("sutra_session", kinds, kinds)
        self.assertLess(kinds.index("start"), kinds.index("sutra_session"),
                        "sutra_session must not precede start")

        sid = [f for f in frames if f["type"] == "sutra_session"][0]["id"]
        self.assertTrue(ss.is_sutra_id(sid))

        meta = ss.read(sid)
        self.assertIsNotNone(meta, "session was announced but not stored")
        # the provider's own id, recorded as a HANDLE rather than as identity
        claude_id = [f for f in frames if f["type"] == "session"][0]["id"]
        self.assertEqual(meta["handles"].get("claude"), claude_id)
        self.assertNotEqual(meta["id"], claude_id)

    def test_both_turns_are_transcribed(self):
        frames = self._turn("transcribe me")
        sid = [f for f in frames if f["type"] == "sutra_session"][0]["id"]
        turns = ss.transcript(sid)
        roles = [t["role"] for t in turns]
        self.assertEqual(roles[:2], ["user", "assistant"], turns)
        self.assertEqual(turns[0]["text"], "transcribe me")
        self.assertTrue(turns[1]["text"], "assistant reply was not recorded")
        # what the operator saw is what was stored
        streamed = "".join(f.get("text", "") for f in frames
                           if f["type"] in ("token", "text"))
        self.assertEqual(turns[1]["text"], streamed)

    def test_reopening_with_a_sutra_id_reuses_that_session(self):
        first = self._turn("first message")
        sid = [f for f in first if f["type"] == "sutra_session"][0]["id"]
        second = self._turn("second message", sutra_session=sid)
        sid2 = [f for f in second if f["type"] == "sutra_session"][0]["id"]
        self.assertEqual(sid, sid2, "a carried id must not mint a new session")
        roles = [t["role"] for t in ss.transcript(sid)]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"])

    def test_forged_sutra_id_does_not_create_or_escape(self):
        """A client-supplied id is untrusted input: it reaches a filesystem path."""
        for forged in ("s_../../etc/passwd", "not-a-sutra-id", "s_" + "z" * 20):
            frames = self._turn("probe", sutra_session=forged)
            got = [f for f in frames if f["type"] == "sutra_session"]
            self.assertTrue(got, "server should still mint its own id")
            self.assertNotEqual(got[0]["id"], forged, forged)
            self.assertTrue(ss.is_sutra_id(got[0]["id"]))

    def test_resume_plan_reflects_what_actually_happened(self):
        frames = self._turn("plan me")
        sid = [f for f in frames if f["type"] == "sutra_session"][0]["id"]
        self.assertEqual(ss.resume_plan(sid, "claude")[0], "native")
        # the point of the whole exercise: another provider can still continue it
        kind, ref = ss.resume_plan(sid, "deepseek")
        self.assertEqual((kind, ref), ("replay", sid))

    def test_session_survives_a_store_that_cannot_be_written(self):
        """Bookkeeping must never cost the operator a turn."""
        os.chmod(self.sessions, 0o500)          # read-only store
        try:
            frames = self._turn("still works")
            kinds = [f["type"] for f in frames]
            self.assertIn("done", kinds, "a read-only store broke the turn")
            self.assertNotIn("error", kinds, kinds)
        finally:
            os.chmod(self.sessions, 0o700)


if __name__ == "__main__":
    unittest.main(verbosity=2)
