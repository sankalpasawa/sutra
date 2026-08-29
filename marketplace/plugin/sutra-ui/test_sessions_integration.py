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

    def _turn(self, message, sutra_session=None, resume=None, timeout=20):
        from websockets.sync.client import connect
        payload = {"message": message}
        if sutra_session:
            payload["sutra_session"] = sutra_session
        if resume:
            payload["resume"] = resume
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

    # ---- reopening must not fragment the store ---------------------------

    def test_reopening_by_provider_handle_reuses_the_session(self):
        """THE BUG THIS EXISTS FOR. Identity was supposed to travel on the wire:
        the socket announces a sutra_session id and the client hands it back.
        Nothing in the client read that frame, so the id never came back and
        every reopen minted a NEW record -- one conversation shattered into a
        record per pane, each holding whatever turns that pane carried.

        A reopen always carries the PROVIDER's id, because that is what --resume
        needs. Recognising the conversation by its handle is what makes identity
        hold even when the wire round trip does not."""
        first = self._turn("original message")
        sid = [f["id"] for f in first if f["type"] == "sutra_session"][0]
        claude_id = [f["id"] for f in first if f["type"] == "session"][0]

        before = len(ss.listing())
        # a client that has forgotten (or never knew) the sutra id, but does
        # resume the provider thread -- exactly what the panel sent for months
        second = self._turn("continued message", resume=claude_id)
        sid2 = [f["id"] for f in second if f["type"] == "sutra_session"][0]

        self.assertEqual(sid2, sid, "reopening minted a second record")
        self.assertEqual(len(ss.listing()), before, "the store grew on a reopen")
        roles = [t["role"] for t in ss.transcript(sid)]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"],
                         "the continued turns landed somewhere else")

    def test_a_resumed_turn_still_binds_the_provider_handle(self):
        """bind_handle used to live only inside the `session` frame observer,
        and that frame is emitted only when the id CHANGES. A resumed pane sends
        its id up and the CLI echoes the same one back, so no frame fired and a
        CONTINUED conversation never recorded a handle -- resume_plan answered
        "replay" for it forever, which re-sends the whole transcript and is paid
        for in tokens. The one case the store exists for was the one that failed."""
        first = self._turn("bind me")
        sid = [f["id"] for f in first if f["type"] == "sutra_session"][0]
        claude_id = [f["id"] for f in first if f["type"] == "session"][0]

        # a fresh store record, resumed -- no `session` frame will be emitted
        fresh = ss.create(title="carried over", provider="claude")["id"]
        frames = self._turn("second turn", sutra_session=fresh, resume=claude_id)
        self.assertFalse([f for f in frames if f["type"] == "session"],
                         "the fake echoed a changed id; this test proves nothing")

        meta = ss.read(fresh)
        self.assertEqual(meta["handles"].get("claude"), claude_id,
                         "a resumed turn recorded no provider handle")
        self.assertEqual(ss.resume_plan(fresh, "claude"), ("native", claude_id))

    # ---- the HTTP surface ------------------------------------------------

    def _get(self, path):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (self.port, path), timeout=10) as r:
            return r.status, json.loads(r.read())

    def _post(self, path, body=None):
        data = json.dumps(body or {}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path), data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())

    def test_api_lists_sessions_the_chat_created(self):
        frames = self._turn("listed please")
        sid = [f for f in frames if f["type"] == "sutra_session"][0]["id"]
        _, body = self._get("/api/sutra/sessions")
        self.assertIn(sid, [r["id"] for r in body["sessions"]])

    def test_api_returns_one_session_with_its_transcript(self):
        frames = self._turn("with transcript")
        sid = [f for f in frames if f["type"] == "sutra_session"][0]["id"]
        _, body = self._get("/api/sutra/sessions/" + sid)
        self.assertEqual(body["id"], sid)
        self.assertEqual(body["transcript"][0]["text"], "with transcript")
        self.assertIn("claude", body["handles"])

    def test_api_create_rename_delete_round_trip(self):
        _, made = self._post("/api/sutra/sessions", {"title": "made by hand"})
        sid = made["id"]
        self.assertTrue(ss.is_sutra_id(sid))
        self._post("/api/sutra/sessions/%s/rename" % sid, {"title": "renamed"})
        _, got = self._get("/api/sutra/sessions/" + sid)
        self.assertEqual(got["title"], "renamed")
        _, gone = self._post("/api/sutra/sessions/%s/delete" % sid)
        self.assertTrue(gone["ok"])
        self.assertTrue(gone["provider_transcript_kept"])

    def test_api_resume_plan_states_what_would_happen(self):
        frames = self._turn("plan via http")
        sid = [f for f in frames if f["type"] == "sutra_session"][0]["id"]
        _, native = self._get("/api/sutra/sessions/%s/resume-plan?provider=claude" % sid)
        self.assertEqual(native["kind"], "native")
        _, replay = self._get("/api/sutra/sessions/%s/resume-plan?provider=deepseek" % sid)
        self.assertEqual(replay["kind"], "replay")
        self.assertGreater(replay["turns"], 0, "the UI needs the count to warn")

    def test_api_refuses_a_traversal_id(self):
        import urllib.error
        for bad in ("s_..%2F..%2Fetc", "notasutraid"):
            try:
                self._get("/api/sutra/sessions/" + bad)
                self.fail("accepted %r" % bad)
            except urllib.error.HTTPError as e:
                self.assertIn(e.code, (400, 404), bad)

    def test_api_refuses_a_cwd_outside_home(self):
        import urllib.error
        try:
            self._post("/api/sutra/sessions", {"cwd": "/etc"})
            self.fail("accepted a cwd outside home")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)



# A fake that behaves like the real CLI on a fork: `--resume X --fork-session`
# answers under a NEW session id, because the fork is a separate thread.
FAKE_FORK = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
resume = args[args.index("--resume") + 1] if "--resume" in args else None
fork = "--fork-session" in args
sid = ("forked-%d" % os.getpid()) if fork else (resume or "base-%d" % os.getpid())
def emit(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    try:
        frame = json.loads(line)
    except ValueError:
        continue
    try:
        msg = frame["message"]["content"][0]["text"]
    except Exception:
        msg = ""
    emit({"type": "system", "subtype": "init", "session_id": sid,
          "model": "fake-model", "tools": [], "mcp_servers": [],
          "slash_commands": [], "permissionMode": "plan", "cwd": os.getcwd()})
    emit({"type": "assistant", "session_id": sid,
          "message": {"role": "assistant",
                      "content": [{"type": "text", "text": "reply to " + msg}]}})
    emit({"type": "result", "subtype": "success", "session_id": sid,
          "is_error": False, "result": "ok"})
"""


class ForkSession(unittest.TestCase):
    """`--fork-session` mints a new provider session. Sutra must follow it.

    It did not: the id was captured only when none was held, and resuming had
    already set one -- so the pane kept naming the ORIGINAL thread and
    everything said into the fork was written to a session nothing referenced
    again.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-fork-")
        cls.fake = os.path.join(cls.tmpdir, "fake-claude")
        with open(cls.fake, "w") as f:
            f.write(FAKE_FORK)
        os.chmod(cls.fake, 0o755)
        cls._saved = {k: os.environ.get(k) for k in
                      ("SUTRA_UI_SETTINGS", "SUTRA_UI_CLAUDE_BIN",
                       "SUTRA_UI_WORKDIR_ROOT", "SUTRA_UI_SESSIONS")}
        os.environ["SUTRA_UI_SETTINGS"] = os.path.join(cls.tmpdir, "settings.json")
        os.environ["SUTRA_UI_CLAUDE_BIN"] = cls.fake
        os.environ["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        os.environ["SUTRA_UI_SESSIONS"] = os.path.join(cls.tmpdir, "sessions")
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

    def test_a_fork_pane_does_not_re_fork_on_every_turn(self):
        """The other half of the fork fix. forked_from keyed only on the SOURCE
        id, and adopting the changed session id rewrites session_id to the newly
        minted fork -- so on the next message the guard was asked about an id it
        had never seen. A pane whose fork toggle stayed set therefore forked
        again on every turn, each message landing in its own fresh thread with
        no memory of the last, which is precisely what forking exists to avoid.

        The client keeps the toggle set (S.turnOpts is sticky), so this is the
        normal path, not an edge case."""
        from websockets.sync.client import connect
        seen = []
        with connect("ws://127.0.0.1:%d/ws/chat" % self.port,
                     open_timeout=10, close_timeout=5) as ws:
            payloads = [{"message": "original"}]
            payloads += [{"message": "forked %d" % i,
                          "opts": {"fork_session": True}} for i in range(1, 4)]
            for payload in payloads:
                ws.send(json.dumps(payload))
                deadline = time.time() + 20
                while time.time() < deadline:
                    try:
                        fr = json.loads(ws.recv(timeout=max(0.1, deadline - time.time())))
                    except Exception:
                        break
                    seen.append(fr)
                    if fr.get("type") in ("done", "error"):
                        break
        ids = [f["id"] for f in seen if f.get("type") == "session"]
        forks = sorted({i for i in ids if i.startswith("forked-")})
        self.assertEqual(len(forks), 1,
                         "the pane forked %d times across three messages: %s"
                         % (len(forks), forks))
        self.assertTrue(ids[-1].startswith("forked-"),
                        "the pane left the fork it created: %s" % (ids,))

    def test_fork_is_followed_not_dropped(self):
        from websockets.sync.client import connect
        seen = []
        with connect("ws://127.0.0.1:%d/ws/chat" % self.port,
                     open_timeout=10, close_timeout=5) as ws:
            for payload in ({"message": "original"},
                            {"message": "forked", "opts": {"fork_session": True}}):
                ws.send(json.dumps(payload))
                deadline = time.time() + 20
                while time.time() < deadline:
                    try:
                        fr = json.loads(ws.recv(timeout=max(0.1, deadline - time.time())))
                    except Exception:
                        break
                    seen.append(fr)
                    if fr.get("type") in ("done", "error"):
                        break
        ids = [f["id"] for f in seen if f.get("type") == "session"]
        self.assertGreaterEqual(len(ids), 2,
                                "no second session frame -- the fork was dropped")
        self.assertTrue(ids[-1].startswith("forked-"),
                        "pane still names the original thread: %r" % (ids,))

        # and Sutra's own record follows the fork
        sutra_ids = [f["id"] for f in seen if f.get("type") == "sutra_session"]
        meta = ss.read(sutra_ids[0])
        self.assertEqual(meta["handles"]["claude"], ids[-1],
                         "store still points at the pre-fork thread")


if __name__ == "__main__":
    unittest.main(verbosity=2)
