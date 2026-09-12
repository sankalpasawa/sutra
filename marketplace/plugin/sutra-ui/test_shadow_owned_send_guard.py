"""ws_chat refuses to become a SECOND writer on a Shadow-owned session.

THE INVARIANT
-------------
    FOR ANY CLAUDE SESSION ID, at most ONE Sutra runtime writes to it.

Before this guard, opening a chat Shadow had started and typing into it put a
second `claude --resume <sid>` on the same transcript: ws_chat builds its own
SessionRuntime per socket (app.py) and never consults the registry, and
attach_observer's reap covers ATTACHED only -- never a delegate. That
transcript is the file done_when is evaluated against, so the corruption is
not cosmetic.

WHY THIS LANE RUNS A REAL SERVER. The guard lives inside ws_chat, and the
thing it must prevent is a SPAWN. Asserting it in-process would prove the
function returns early; asserting it across a real socket proves no CLI was
started, which is the actual product promise ("do not start another Claude
process merely because the user opened the Chat"). The server is started with
a seeded shadow home, so ownership is established the way a RESTART
establishes it -- through recover_on_boot() rebuilding the fence from mission
state on disk -- which exercises F1-a end to end rather than by poking a dict.

NO CLI IS EVER SPAWNED IN THE REFUSAL TESTS, and that is the point: every
assertion lands before the spawn block. The one test that must prove a normal
chat is UNAFFECTED stops at the handshake frame for the same reason -- the
provider frame is sent before any binary runs (the pattern test_app.py's
provider-param class already uses).

ONE SERVER PER CLASS, and that is load-bearing. setUpClass lives on Base, so
each subclass starts its OWN uvicorn with its OWN seeded shadow home (verified:
three ports, three mission ids). Classes run in alphabetical order, which puts
TestOwnershipEnds -- the one that STOPS the mission -- before
TestTheSendIsRefused; sharing a server would make the refusal tests pass or
fail on ordering rather than on behaviour. Keep any new class as a Base
subclass rather than folding tests into an existing one for speed.

Run: ./run-tests.sh test_shadow_owned_send_guard.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):
    VENV_PY = sys.executable

OWNED_SID = "shadow-owned-0001"
PLAIN_SID = "an-ordinary-chat-0002"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _seed_shadow_home(root):
    """A mission that says Shadow owns OWNED_SID, exactly as one looks on disk
    after the app died with a delegate in flight.

    target_mode "new" + a target_session + a non-terminal state IS the
    ownership record -- there is no separate store, which is the whole point of
    F1-a. Written with MissionStore so the shape can never drift from the
    writer the app itself uses.
    """
    os.environ["SUTRA_SHADOW_HOME"] = root
    sys.path.insert(0, HERE)
    import importlib
    import mission_engine
    importlib.reload(mission_engine)
    store = mission_engine.MissionStore()
    m = store.create("drive the owned chat", "fix", target_mode="new",
                     target_session=OWNED_SID)
    store.transition(m["id"], "brief_confirm", "seed")
    store.transition(m["id"], "running", "seed")
    # a second mission on an ATTACHED (founder-owned) chat, to prove the guard
    # does not fence one
    m2 = store.create("assist in the founder's chat", "fix",
                      target_mode="existing", target_session=PLAIN_SID)
    store.transition(m2["id"], "brief_confirm", "seed")
    store.transition(m2["id"], "running", "seed")
    return m["id"]


class Base(unittest.TestCase):

    proc = None
    port = None
    tmpdir = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-shadowguard-")
        cls.shadow_home = os.path.join(cls.tmpdir, "shadow")
        cls.mission_id = _seed_shadow_home(cls.shadow_home)

        cls.port = _free_port()
        env = dict(os.environ)
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env["SUTRA_SKIP_PROJECT_IMPORT"] = "1"
        env["SUTRA_SHADOW_HOME"] = cls.shadow_home
        env["SUTRA_UI_WORKDIR"] = os.path.join(cls.tmpdir, "workspace")
        env["SUTRA_UI_CHATS"] = os.path.join(cls.tmpdir, "chats")
        env["SUTRA_UI_SETTINGS"] = os.path.join(cls.tmpdir, "settings.json")
        env.pop("ANTHROPIC_API_KEY", None)
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/shadow/status" % cls.port,
                    timeout=1)
                break
            except Exception:       # noqa: BLE001
                if cls.proc.poll() is not None:
                    out = cls.proc.stdout.read().decode("utf-8", "replace")
                    raise RuntimeError("server died:\n" + out[-2000:])
                time.sleep(0.25)
        else:
            raise RuntimeError("shadow-guard server did not come up")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        if cls.tmpdir and os.path.isdir(cls.tmpdir):
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # ---------------------------------------------------------------- utils --
    def _send(self, payload, query=""):
        """Open a pane socket, send one message, return the frames that come
        back before the socket goes quiet."""
        from websockets.sync.client import connect
        url = "ws://127.0.0.1:%d/ws/chat%s" % (self.port, query)
        frames = []
        with connect(url, open_timeout=10) as ws:
            # the handshake frame (provider), then our message
            try:
                frames.append(json.loads(ws.recv(timeout=10)))
            except Exception:       # noqa: BLE001
                pass
            ws.send(json.dumps(payload))
            deadline = time.time() + 8
            while time.time() < deadline:
                try:
                    frames.append(json.loads(ws.recv(timeout=3)))
                except Exception:   # noqa: BLE001
                    break
        return frames

    def _errors(self, frames):
        return [f for f in frames if f.get("type") == "error"]


class TestTheSendIsRefused(Base):

    def test_01_sending_to_a_shadow_owned_session_is_refused(self):
        """CONTRACT 4/C. Server-side, not a disabled textarea."""
        frames = self._send({"message": "let me help", "resume": OWNED_SID})
        errs = self._errors(frames)
        self.assertTrue(errs, "a send into a Shadow-driven chat must be "
                              "refused, not quietly answered")
        detail = " ".join(e.get("detail", "") for e in errs)
        self.assertIn("Shadow", detail)
        # it says what the founder CAN do, not only what they cannot
        self.assertIn("read along", detail.lower())

    def test_02_the_refusal_happens_on_the_resume_seed_alone(self):
        """THE PATH THE OLD CODE SPAWNED ON. A pane opened from the rail
        arrives with `resume` set and the socket's session_id still None, so a
        guard reading only session_id would miss exactly the case that matters.
        """
        frames = self._send({"message": "hello", "resume": OWNED_SID})
        self.assertTrue(self._errors(frames))
        # and nothing was streamed back -- no turn ran
        self.assertEqual([f for f in frames if f.get("type") == "token"], [])

    def test_03_no_claude_process_is_started_by_the_refused_send(self):
        """The product promise: opening/typing must not spawn a second
        runtime. Asserted on the SERVER's own process tree."""
        before = self._child_count()
        self._send({"message": "still nothing", "resume": OWNED_SID})
        time.sleep(0.5)
        self.assertEqual(self._child_count(), before,
                         "a refused send spawned a child process")

    def _child_count(self):
        out = subprocess.run(["pgrep", "-P", str(self.proc.pid)],
                             capture_output=True, text=True).stdout
        return len([l for l in out.splitlines() if l.strip()])

    def test_03b_the_same_server_accepts_an_unowned_session(self):
        """THE DIFFERENTIAL, on ONE server: the refusal above must be caused by
        OWNERSHIP and nothing else. Same socket, same handler, same seeded
        home -- only the session id differs, and only the owned one is fenced.
        Without this pair, an unrelated error frame could make test_01 look
        like a working guard.
        """
        owned = self._send({"message": "x", "resume": OWNED_SID})
        plain = self._send({"message": "x", "resume": PLAIN_SID})
        mark = "Shadow is working"
        self.assertTrue(
            [e for e in self._errors(owned) if mark in e.get("detail", "")],
            "the owned session must be refused")
        self.assertEqual(
            [e for e in self._errors(plain) if mark in e.get("detail", "")], [],
            "an unowned session on the SAME server must not be")

    def test_04_the_mission_is_not_paused_by_a_refused_send(self):
        """The guard runs BEFORE founder_takeover. Typing into a chat Shadow
        STARTED is a collision, not a takeover -- pausing the mission would be
        the wrong answer and would strand the goal."""
        self._send({"message": "nope", "resume": OWNED_SID})
        time.sleep(0.3)
        raw = urllib.request.urlopen(
            "http://127.0.0.1:%d/api/shadow/missions" % self.port,
            timeout=5).read()
        missions = json.loads(raw)["missions"]
        mine = [m for m in missions if m["id"] == self.mission_id][0]
        self.assertNotEqual(mine.get("pause_reason"), "founder_intervened",
                            "a refused send must not read as a takeover")


class TestOrdinaryChatsAreUnaffected(Base):

    def test_10_an_unowned_session_is_not_refused_by_the_guard(self):
        """REGRESSION FENCE. Normal chats must behave exactly as before.

        A chat Shadow merely ATTACHED to (target_mode "existing") is the
        founder's own and stays typeable -- that is what target_mode
        discriminates, and why this slice does not delete it.
        """
        frames = self._send({"message": "ordinary turn", "resume": PLAIN_SID})
        refusals = [e for e in self._errors(frames)
                    if "Shadow is working" in e.get("detail", "")]
        self.assertEqual(refusals, [],
                         "an attached founder chat must not be fenced")

    def test_11_the_session_list_reports_ownership_honestly(self):
        """The pane's indicator and the server's guard read the SAME fact, so
        they cannot disagree. Shape only -- the field must exist on every row
        and be a bool."""
        raw = urllib.request.urlopen(
            "http://127.0.0.1:%d/api/sessions?limit=5" % self.port,
            timeout=10).read()
        rows = json.loads(raw)
        for r in rows:
            self.assertIn("shadow_driving", r)
            self.assertIsInstance(r["shadow_driving"], bool)


class TestOwnershipEnds(Base):

    def test_20_after_the_mission_ends_the_chat_accepts_sends(self):
        """CONTRACT 5/D. Ownership is the only thing that ends; afterwards it
        is an ordinary chat. Driven through the app's own stop action, which
        is the path that does NOT go through release_delegate -- so this also
        pins that the restart fence expires instead of outliving the work."""
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/shadow/missions/%s/act"
            % (self.port, self.mission_id),
            data=json.dumps({"action": "stop"}).encode(),
            headers={"content-type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10).read()

        frames = self._send({"message": "mine now", "resume": OWNED_SID})
        refusals = [e for e in self._errors(frames)
                    if "Shadow is working" in e.get("detail", "")]
        self.assertEqual(refusals, [],
                         "a finished mission must release the chat")


class TestTakeOver(Base):
    """The chat strip's Take over: Shadow steps back, the founder types.

    Distinct from Stop, which ends the task. This ends only SHADOW'S TURN at
    it -- so the mission survives (paused) while ownership does not, which is
    what makes the composer usable without ever allowing two writers.
    """

    def test_30_take_over_releases_ownership_and_unlocks_the_send(self):
        before = self._send({"message": "mine", "resume": OWNED_SID})
        self.assertTrue([e for e in self._errors(before)
                         if "Shadow is working" in e.get("detail", "")],
                        "precondition: the chat starts fenced")

        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/shadow/missions/%s/act"
            % (self.port, self.mission_id),
            data=json.dumps({"action": "take_over"}).encode(),
            headers={"content-type": "application/json"}, method="POST")
        body = json.loads(urllib.request.urlopen(req, timeout=10).read())

        # the TASK is kept, only Shadow's turn at it ended
        self.assertEqual(body["state"], "paused")
        self.assertEqual(body.get("pause_reason"), "founder_intervened")
        self.assertEqual(body.get("target_session"), OWNED_SID,
                         "the chat is still the mission's")

        after = self._send({"message": "mine now", "resume": OWNED_SID})
        self.assertEqual([e for e in self._errors(after)
                          if "Shadow is working" in e.get("detail", "")], [],
                         "the founder must be able to send after taking over")

    def test_31_the_row_stops_reporting_a_driven_chat(self):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/shadow/missions/%s/act"
            % (self.port, self.mission_id),
            data=json.dumps({"action": "take_over"}).encode(),
            headers={"content-type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10).read()
        rows = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/api/sessions?limit=50" % self.port,
            timeout=10).read())
        for r in rows:
            if r.get("id") == OWNED_SID:
                self.assertFalse(r["shadow_driving"])
                self.assertIsNone(r["shadow_task"])


class TestTheRowCarriesTheTask(Base):
    """The strip's facts come from the server, not from the pane's guesswork."""

    def test_40_shadow_task_is_absent_on_an_ordinary_chat(self):
        rows = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/api/sessions?limit=50" % self.port,
            timeout=10).read())
        for r in rows:
            self.assertIn("shadow_task", r)
            if not r["shadow_driving"]:
                self.assertIsNone(r["shadow_task"],
                                  "an ordinary chat must carry no task")


if __name__ == "__main__":
    unittest.main(verbosity=2)
