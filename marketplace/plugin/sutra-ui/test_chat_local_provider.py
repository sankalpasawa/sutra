#!/usr/bin/env python3
"""test_chat_local_provider.py -- one chat may run on Codex while the GLOBAL
default stays Claude, and that choice sticks without settings.json moving.

THE CONTRACT THIS PINS, in the founder's own terms:

    Settings.provider = claude          <- never written by anything here
    Chat A            = codex           <- provider_history[-1], per chat
    Chat B            = claude          <- untouched by A's switch
    a new chat        = claude          <- the global default still governs

WHAT WAS ACTUALLY BROKEN, and why N is the load-bearing test. The browser holds
`sutra_id` in memory only (02-helpers.js:341) and claudeWsUrl sent no
?provider=, so every reconnect resolved through active_provider_detail() -- the
GLOBAL default. A chat switched to Codex therefore reverted to Claude on the
next connect; and because ?sutra= was still sent, switch.plan() saw
active_segment=codex against target=claude and replayed the ENTIRE conversation
back to Claude. A silent un-switch that cost a full carry-over, with no error
frame anywhere. `test_N_*` is the regression test for exactly that, and it
asserts the ABSENCE of a switch frame rather than only the presence of the
right provider -- reverting and re-switching would produce the right provider
too, at the price the bug was made of.

WHAT IS ASSERTED AGAINST WHAT. The chat-local provider is read back from the
store the SERVER writes, never from what the client was told. settings.json is
read as bytes off disk, because "the global default did not move" is the one
claim this feature cannot be trusted to make about itself. And the carried-over
context is asserted against the stdin the codex stub was ACTUALLY fed -- the
same discipline test_switch_retry applies to argv.

Runs entirely against stubs: no claude, codex or deepseek binary, no key, no
network, nothing billed.
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
CODEX_STUB = os.path.join(HERE, "qa", "fake_codex_agent.py")
CLAUDE_STUB = os.path.join(HERE, "qa", "fake_claude_agent.py")
ACP_STUB = os.path.join(HERE, "qa", "fake_acp_agent.py")

#: Claude-shaped ids, so a leak names itself in any failure message.
CLAUDE_SRC = "c1a70000-0000-4000-8000-0000000000a1"
CLAUDE_NEW = "c1a7bbbb-0000-4000-8000-0000000000b2"
#: The fact planted in the source transcript. Its presence in codex's stdin is
#: what proves the conversation moved, rather than the switch merely claiming to.
FACT = "ZEBRA-1"


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server(unittest.TestCase):
    """One uvicorn per class, all three providers stubbed, global default
    pinned to claude in a settings.json this test owns."""

    proc = None
    port = None
    tmpdir = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-chatlocal-")
        sys.path.insert(0, os.path.join(HERE, "..", "lib"))
        sys.path.insert(0, HERE)
        import fixture_seed  # noqa: E402
        fixture_seed.seed(cls.tmpdir)

        for stub in (CODEX_STUB, CLAUDE_STUB, ACP_STUB):
            if os.path.exists(stub):
                os.chmod(stub, 0o755)

        cls.home = os.path.join(cls.tmpdir, "home")
        cls.work = os.path.join(cls.tmpdir, "workspace")
        cls.chats = os.path.join(cls.tmpdir, "chats")
        cls.settings = os.path.join(cls.tmpdir, "settings.json")
        cls.cx_argv = os.path.join(cls.tmpdir, "codex-argv.jsonl")
        cls.cl_argv = os.path.join(cls.tmpdir, "claude-argv.jsonl")
        cls.cx_stdin = os.path.join(cls.tmpdir, "codex-stdin.txt")
        # ~/.claude is claude's readiness probe (providers._describe: a config
        # DIRECTORY, not a credential file), so it has to exist before the
        # first connect or the global default would be dropped as unrunnable
        # and the fallback would silently answer codex -- which is the exact
        # confusion this file is written to detect.
        for d in (os.path.join(cls.home, ".codex"),
                  os.path.join(cls.home, ".claude"), cls.work, cls.chats):
            os.makedirs(d, exist_ok=True)
        # existence-only readiness probe; providers never opens it
        with open(os.path.join(cls.home, ".codex", "auth.json"), "w") as fh:
            fh.write("")

        # THE GLOBAL DEFAULT, written ONCE here and never again. Every later
        # read of this file is an assertion that the feature left it alone.
        with open(cls.settings, "w") as fh:
            json.dump({"provider": "claude", "permission_mode": "plan",
                       "workdir": cls.work}, fh)

        cls.port = _free_port()
        env = dict(os.environ)
        env["HOME"] = cls.home
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env["SUTRA_UI_WORKDIR"] = cls.work
        env["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        env["SUTRA_UI_SETTINGS"] = cls.settings
        env["SUTRA_UI_CHATS"] = cls.chats
        env["SUTRA_UI_SWITCH_EGRESS"] = os.path.join(cls.tmpdir, "egress.jsonl")
        env.pop("ANTHROPIC_API_KEY", None)
        # SUTRA_UI_PROVIDER would OUTRANK settings.json (providers.py:1938) and
        # make every "the global default is claude" assertion vacuous.
        env.pop("SUTRA_UI_PROVIDER", None)
        env["SUTRA_UI_CODEX_BIN"] = CODEX_STUB
        env["SUTRA_FAKE_CODEX_SCRIPT"] = "ok"
        env["SUTRA_FAKE_CODEX_ARGV"] = cls.cx_argv
        env["SUTRA_FAKE_CODEX_STDIN"] = cls.cx_stdin
        env["SUTRA_UI_CLAUDE_BIN"] = CLAUDE_STUB
        env["SUTRA_FAKE_CLAUDE_ARGV"] = cls.cl_argv
        env["SUTRA_FAKE_CLAUDE_SESSION"] = CLAUDE_NEW
        env["SUTRA_FAKE_CLAUDE_KNOWN"] = CLAUDE_SRC + "," + CLAUDE_NEW
        env["SUTRA_UI_DEEPSEEK_BIN"] = ACP_STUB
        env["SUTRA_UI_DEEPSEEK_API_KEY"] = "sk-fake-not-a-real-key"

        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:  # noqa: BLE001
                if cls.proc.poll() is not None:
                    out = cls.proc.stdout.read().decode("utf-8", "replace")
                    raise RuntimeError("server died:\n" + out[-4000:])
                time.sleep(0.25)
        else:
            raise RuntimeError("chat-local server did not come up")

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

    # ------------------------------------------------------------- fixtures --

    def _claude_transcript(self, session_id):
        """A Claude source transcript where session_reader.PROJECTS finds it."""
        d = os.path.join(self.home, ".claude", "projects", "-test")
        os.makedirs(d, exist_ok=True)
        recs = [
            {"type": "user", "cwd": self.work, "gitBranch": "main",
             "timestamp": "2026-09-09T10:00:00.000Z",
             "message": {"role": "user", "content": "FACT: token is " + FACT}},
            {"type": "assistant", "timestamp": "2026-09-09T10:00:01.000Z",
             "message": {"role": "assistant",
                         "content": [{"type": "text", "text": "noted"}]}},
        ]
        with open(os.path.join(d, session_id + ".jsonl"), "w") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    def _cs(self):
        os.environ["SUTRA_UI_CHATS"] = self.chats
        sys.path.insert(0, HERE)
        import chat_store
        return chat_store

    def _chat_on(self, provider, native_id, with_transcript=True):
        if provider == "claude" and with_transcript:
            self._claude_transcript(native_id)
        cs = self._cs()
        rec = cs.create(cwd=self.work)
        cs.begin_segment(rec, provider, native_id)
        return rec["sutra_id"]

    def _chat_on_indexed(self, provider, native_id, tries=25):
        """A chat whose reverse-index row is CONFIRMED present before the pane
        is driven.

        WHY THIS IS NEEDED, and it is a real property of the store rather than
        a slow disk. chat_store._reindex() is read-modify-write over one shared
        _index.json, and here TWO processes write it: this test, and the
        server, whose switch.confirm() from the PREVIOUS test can still be in
        flight. The server reads the index, this test adds a row, the server
        writes its older copy back -- and the row is gone. The recovery under
        test then finds nothing, so the switch silently forks, which is the
        exact failure these tests exist to catch and would have reported as a
        product bug.

        Only the test races: in the running panel the server is the only
        writer. So this is fixed here, by confirming the row and restoring it
        if a late write clobbered it, rather than by serialising the store.
        """
        a = self._chat_on(provider, native_id)
        cs = self._cs()
        for _ in range(tries):
            if cs.resolve(provider, native_id) == a:
                return a
            rec = cs.load(a)
            if rec is not None:
                cs.save(rec)          # re-add the row a late write dropped
            time.sleep(0.1)
        self.fail("the index row for %s:%s never settled" % (provider, native_id))

    def _hist(self, sutra_id, settle=0.6):
        """provider_history, after letting any post-`done` write land."""
        time.sleep(settle)
        cs = self._cs()
        return [(h["provider"], h["native_id"])
                for h in (cs.load(sutra_id) or {}).get("provider_history") or []]

    def _settings_provider(self):
        """The GLOBAL default, read as bytes off disk. Not through the API and
        not through providers.load_settings(): the claim under test is about
        the FILE, and any accessor could paper over a write to it."""
        with open(self.settings, encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("provider")

    # -------------------------------------------------------------- driving --

    def _clear_recordings(self):
        for p in (self.cx_argv, self.cl_argv, self.cx_stdin):
            try:
                os.unlink(p)
            except OSError:
                pass

    def _codex_stdin(self):
        try:
            with open(self.cx_stdin, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def _url(self, sutra_id=None, provider=None):
        """The socket URL. `provider=None` is the case that matters most --
        it is what every ordinary turn sends once a chat has switched, and
        therefore what exercises the chat-local resolution."""
        q = []
        if provider:
            q.append("provider=" + provider)
        if sutra_id:
            q.append("sutra=" + sutra_id)
        return ("ws://127.0.0.1:%d/ws/chat%s"
                % (self.port, ("?" + "&".join(q)) if q else ""))

    def _pane(self, sutra_id=None, provider=None, messages=(), resume=None):
        """One pane, N messages on ONE socket. Returns (provider_frame, turns)."""
        from websockets.sync.client import connect
        turns = []
        with connect(self._url(sutra_id, provider), open_timeout=20,
                     max_size=32 * 1024 * 1024) as ws:
            first = json.loads(ws.recv(timeout=20))
            for msg in messages:
                ws.send(json.dumps({"message": msg, "resume": resume}))
                frames = []
                for _ in range(60):
                    try:
                        f = json.loads(ws.recv(timeout=40))
                    except Exception:  # noqa: BLE001
                        break
                    frames.append(f)
                    if f.get("type") in ("done", "error"):
                        break
                turns.append(frames)
        return first, turns

    @staticmethod
    def _last_session(turns):
        """The native session id the last turn ended on -- what a real browser
        keeps per pane (01-state.js:1455) and hands back as `resume` on the
        next connect. Threaded through these tests deliberately: without it a
        codex reconnect starts a FRESH thread, and begin_segment records a new
        same-provider segment for it, which is correct behaviour
        (test_chat_store.test_same_provider_new_session_is_a_new_segment) but
        not what a real client produces."""
        for frames in reversed(turns or []):
            ids = [f["id"] for f in frames if f.get("type") == "session"]
            if ids:
                return ids[-1]
        return None

    @staticmethod
    def _switches(frames):
        return [f for f in frames if f.get("type") == "switch"]

    @staticmethod
    def _sessions(frames):
        return [f["id"] for f in frames if f.get("type") == "session"]


# ============================================ the global default still rules =

class GlobalDefaultGoverns(_Server):
    """A. and E. -- nothing about this feature moves a chat that never asked."""

    def test_A_a_new_chat_uses_the_settings_provider(self):
        """A. No ?sutra=, no ?provider= -- the global default answers, and says
        that is where the answer came from."""
        first, _ = self._pane(messages=[])
        self.assertEqual(first.get("type"), "provider", first)
        self.assertEqual(first.get("id"), "claude", first)
        self.assertEqual(first.get("source"), "settings", first)

    def test_E_a_new_chat_is_unaffected_by_another_chats_switch(self):
        """E. Chat A moves to codex; a chat opened afterwards still gets the
        global default. The two must not share a resolution path."""
        a = self._chat_on("claude", CLAUDE_SRC)
        self._pane(a, "codex", ["carry on"])
        self._hist(a)

        first, _ = self._pane(messages=[])
        self.assertEqual(first.get("id"), "claude", first)
        self.assertEqual(first.get("source"), "settings", first)

    def test_D_another_existing_chat_is_unaffected(self):
        """D. Chat B never asked for anything, so it resolves globally even
        though it carries a ?sutra= of its own."""
        a = self._chat_on("claude", CLAUDE_SRC)
        b = self._chat_on("claude", "c1a70000-0000-4000-8000-0000000000b0")
        self._pane(a, "codex", ["carry on"])
        self._hist(a)

        first, _ = self._pane(b, None, [])
        self.assertEqual(first.get("id"), "claude", first)
        self.assertEqual(self._hist(b), [("claude",
                                          "c1a70000-0000-4000-8000-0000000000b0")])

    def test_a_chat_with_no_segment_yet_falls_through_to_the_default(self):
        """A chat record can exist before anything has been sent. It has no
        provider of its own, so the global default is the correct answer --
        not an error and not a refusal."""
        cs = self._cs()
        rec = cs.create(cwd=self.work)
        first, _ = self._pane(rec["sutra_id"], None, [])
        self.assertEqual(first.get("id"), "claude", first)
        self.assertEqual(first.get("source"), "settings", first)


# ================================================ the in-chat switch itself ==

class InChatSwitch(_Server):
    """B, C, F, G, H, M, N -- the whole sticky-switch lifecycle."""

    def test_B_an_explicit_request_creates_the_codex_segment(self):
        """B. ?provider=codex on a claude chat switches it, and the segment
        recorded is CODEX's own id -- not the claude one it was seeded from."""
        self._clear_recordings()
        a = self._chat_on("claude", CLAUDE_SRC)
        _, turns = self._pane(a, "codex", ["implement this"])

        sw = self._switches(turns[0])
        self.assertTrue(sw and sw[0].get("ok"),
                        "no successful switch frame: %r"
                        % (sw or [f.get("type") for f in turns[0]],))
        self.assertEqual(sw[0]["source"], "claude")
        self.assertEqual(sw[0]["target"], "codex")

        hist = self._hist(a)
        self.assertEqual([h[0] for h in hist], ["claude", "codex"], hist)
        self.assertNotEqual(hist[1][1], CLAUDE_SRC,
                            "the claude id was written onto the codex segment")

    def test_C_the_global_default_did_not_move(self):
        """C. THE CORE CONSTRAINT. An in-chat switch must not write settings."""
        a = self._chat_on("claude", CLAUDE_SRC)
        self.assertEqual(self._settings_provider(), "claude")
        self._pane(a, "codex", ["implement this"])
        self._hist(a)
        self.assertEqual(self._settings_provider(), "claude",
                         "an in-chat switch rewrote the GLOBAL provider")

    def test_H_the_conversation_is_carried_to_codex(self):
        """H. The fact planted in claude's transcript reaches codex's stdin.

        Asserted against what the STUB WAS FED, not against the switch frame's
        own character count -- a frame can claim a carry-over that never left
        the process."""
        self._clear_recordings()
        a = self._chat_on("claude", CLAUDE_SRC)
        _, turns = self._pane(a, "codex", ["implement this"])
        sw = self._switches(turns[0])
        self.assertTrue(sw and sw[0].get("ok"), sw)

        fed = self._codex_stdin()
        self.assertIn(FACT, fed,
                      "the prior conversation never reached codex")
        self.assertIn("implement this", fed,
                      "the operator's own message did not ride along")

    def test_the_operators_message_is_stored_verbatim_not_the_payload(self):
        """The chat record keeps what the operator typed. Storing the wrapped
        recording would make the NEXT switch read a copy of the whole prior
        conversation out of the record it is supposed to be summarising."""
        a = self._chat_on("claude", CLAUDE_SRC)
        self._pane(a, "codex", ["implement this"])
        self._hist(a)
        cs = self._cs()
        users = [m for m in (cs.load(a) or {}).get("messages") or []
                 if m.get("role") == "user"]
        self.assertTrue(users, "no user turn was recorded")
        text = "".join(b.get("text", "") for b in users[-1].get("blocks") or [])
        self.assertEqual(text, "implement this")
        self.assertNotIn(FACT, text, "the replay payload was stored as the turn")

    def test_F_subsequent_turns_stay_on_codex(self):
        """F + N. A LATER SOCKET WITH NO ?provider= AT ALL -- the ordinary case
        once a chat has switched -- must resolve to codex from the chat's own
        record, and must NOT switch again.

        The absent switch frame is the real assertion. Reverting to claude and
        switching back would also end on codex, at the cost of a full replay
        and a third segment; only this proves that did not happen."""
        self._clear_recordings()
        a = self._chat_on("claude", CLAUDE_SRC)
        _, first_turns = self._pane(a, "codex", ["implement this"])
        cx = self._last_session(first_turns)
        self.assertTrue(cx, "codex never reported a session id")
        self._hist(a)

        first, turns = self._pane(a, None, ["and now this"], resume=cx)
        self.assertEqual(first.get("id"), "codex", first)
        self.assertEqual(first.get("source"), "chat-history", first)
        self.assertEqual(self._switches(turns[0]), [],
                         "the chat was already on codex -- this replayed anyway")
        self.assertEqual([h[0] for h in self._hist(a)], ["claude", "codex"],
                         "an extra segment was written for an ordinary turn")

    def test_N_the_chat_local_provider_survives_a_reconnect(self):
        """N. Three separate sockets, none of them naming a provider after the
        first. This is the reload / restart / dropped-socket case, and it is
        the regression test for the silent un-switch."""
        self._clear_recordings()
        a = self._chat_on("claude", CLAUDE_SRC)
        _, turns = self._pane(a, "codex", ["implement this"])
        cx = self._last_session(turns)
        self._hist(a)

        for n in range(2):
            first, turns = self._pane(a, None, ["turn %d" % n], resume=cx)
            self.assertEqual(first.get("id"), "codex",
                             "reconnect %d fell back to the global default" % n)
            self.assertEqual(self._switches(turns[0]), [],
                             "reconnect %d replayed the conversation" % n)
            cx = self._last_session(turns) or cx
            self._hist(a)

        self.assertEqual([h[0] for h in self._hist(a)], ["claude", "codex"])

    def test_G_an_explicit_request_switches_back(self):
        """G. codex -> claude is a switch like any other, and claude gets a
        FRESH session rather than resuming the thread it was left on."""
        self._clear_recordings()
        a = self._chat_on("claude", CLAUDE_SRC)
        self._pane(a, "codex", ["implement this"])
        self._hist(a)

        _, turns = self._pane(a, "claude", ["back to you"])
        sw = self._switches(turns[0])
        self.assertTrue(sw and sw[0].get("ok"),
                        "no switch back to claude: %r"
                        % (sw or [f.get("type") for f in turns[0]],))
        self.assertEqual(sw[0]["source"], "codex")
        self.assertEqual(sw[0]["target"], "claude")

        hist = self._hist(a)
        self.assertEqual([h[0] for h in hist], ["claude", "codex", "claude"], hist)
        self.assertEqual(len({h[1] for h in hist}), 3,
                         "an id was reused across segments: %r" % (hist,))

    def test_M_asking_for_the_provider_already_running_replays_nothing(self):
        """M. ?provider=codex on a chat ALREADY on codex is not a switch. No
        replay, no frame, no second segment."""
        self._clear_recordings()
        a = self._chat_on("claude", CLAUDE_SRC)
        _, first_turns = self._pane(a, "codex", ["implement this"])
        cx = self._last_session(first_turns)
        self._hist(a)

        _, turns = self._pane(a, "codex", ["more of the same"], resume=cx)
        self.assertEqual(self._switches(turns[0]), [],
                         "a same-provider request replayed the conversation")
        self.assertEqual([h[0] for h in self._hist(a)], ["claude", "codex"])


# ======================================= the chat opened from the rail =======

class RailOpenedChatSwitch(_Server):
    """A chat opened from the transcript rail has NO sutra id in the browser,
    and switching it must still switch IT -- not fork a new one.

    THE SHAPE OF THE BUG, measured on the founder's disk 2026-09-09. The
    browser learns a chat's sutra id only from a `provider` or `chat` frame,
    and both need a socket that does not exist until the first message is sent.
    So the first message after opening a rail chat carries `resume` (the rail
    attaches a native session id to every listed transcript) and NO ?sutra=.
    Four things then went wrong at once:

      * seed_switch is bool(sutra_id) -> false, so switch.plan never ran and
        the conversation was carried nowhere;
      * _seed_is_another_providers short-circuits on an empty sutra_id, so the
        CLAUDE seed was adopted on a CODEX pane;
      * codex echoes the id it was resumed with as its own thread id, so the
        claude id survived the turn;
      * chat_store.resolve(codex, <claude id>) missed, so a BRAND NEW chat
        record was created and the claude id written onto its codex segment.

    Two such records exist on disk: a fork, no context, and a segment naming a
    session that lives only in the other provider's tree.

    Every test here drives the socket the way that pane does -- provider set,
    sutra id ABSENT, resume present -- because passing ?sutra= is precisely
    what the browser could not do.
    """

    #: Bumped per test. chat_store's reverse index is keyed
    #: "<provider>:<native_id>", so two tests sharing one claude id would share
    #: one index row -- and the second _chat_on would silently re-point it at
    #: its own chat, making the FIRST test's recovery resolve to the wrong
    #: record. That is a fixture collision, not a product behaviour, and a
    #: unique id per test is what keeps these assertions about the code.
    _seq = 0

    def _fresh_claude_id(self):
        RailOpenedChatSwitch._seq += 1
        return "c1a70000-0000-4000-8000-%012d" % RailOpenedChatSwitch._seq

    def setUp(self):
        """Let the PREVIOUS test's server-side writes land before this one
        touches the store.

        _chat_on_indexed below confirms its index row, but confirming is not
        enough on its own: switch.confirm() from the previous test can still be
        in flight and lands AFTER the check, clobbering the row with an older
        copy of the index (read-modify-write, two writers). Waiting for the
        chats directory to stop changing closes that window at its source
        rather than racing it.
        """
        deadline = time.time() + 6
        last = None
        stable = 0
        while time.time() < deadline and stable < 2:
            try:
                names = sorted(os.listdir(self.chats))
                snap = tuple((n, os.path.getmtime(os.path.join(self.chats, n)))
                             for n in names)
            except OSError:
                snap = None
            stable = stable + 1 if snap == last else 0
            last = snap
            time.sleep(0.2)

    def _chat_count(self):
        return len([f for f in os.listdir(self.chats)
                    if f.endswith(".json") and not f.startswith("_")])

    def _hist_when(self, sutra_id, segments, timeout=6.0):
        """provider_history once it has `segments` entries, or whatever it has
        when the clock runs out.

        POLLED RATHER THAN SLEPT. The segment is written after the `done`
        frame, so _hist's fixed 0.6s settle is a race the suite loses under
        sequential load -- these tests passed alone and failed in the class,
        which is the signature of a fixture timing bug rather than a defect.
        Bounded, and it returns the short history on timeout so the assertion
        that follows reports what was actually recorded.
        """
        cs = self._cs()
        deadline = time.time() + timeout
        hist = []
        while time.time() < deadline:
            hist = [(h["provider"], h["native_id"])
                    for h in (cs.load(sutra_id) or {}).get("provider_history") or []]
            if len(hist) >= segments:
                return hist
            time.sleep(0.15)
        return hist

    def test_the_existing_chat_is_switched_not_forked(self):
        """THE HEADLINE. One chat before, one chat after."""
        self._clear_recordings()
        src = self._fresh_claude_id()
        a = self._chat_on_indexed("claude", src)
        before = self._chat_count()

        # No sutra_id -- exactly what a rail-opened pane sends.
        _, turns = self._pane(None, "codex", ["Using Codex, implement this"],
                              resume=src)

        hist = self._hist_when(a, 2)
        self.assertEqual(self._chat_count(), before,
                         "the switch forked a new chat record")
        self.assertEqual([h[0] for h in hist], ["claude", "codex"],
                         "the existing chat did not gain a codex segment: %r" % (hist,))

    def test_the_conversation_is_carried_over(self):
        """A switch that loses the conversation is the failure the whole
        carry-over exists to prevent -- and with no sutra id it lost it
        silently, with no switch frame to say so."""
        self._clear_recordings()
        src = self._fresh_claude_id()
        self._chat_on_indexed("claude", src)
        _, turns = self._pane(None, "codex", ["Using Codex, implement this"],
                              resume=src)

        sw = self._switches(turns[0])
        self.assertTrue(sw and sw[0].get("ok"),
                        "no carry-over on a rail-opened switch: %r"
                        % (sw or [f.get("type") for f in turns[0]],))
        self.assertEqual(sw[0]["source"], "claude")
        self.assertEqual(sw[0]["target"], "codex")
        self.assertIn(FACT, self._codex_stdin(),
                      "the prior conversation never reached codex")

    def test_the_claude_seed_is_never_written_onto_a_codex_segment(self):
        """The poisoning itself. codex accepts a foreign id in SILENCE, so the
        only way to catch this is to look at what was recorded."""
        self._clear_recordings()
        src = self._fresh_claude_id()
        a = self._chat_on_indexed("claude", src)
        self._pane(None, "codex", ["Using Codex, implement this"],
                   resume=src)

        hist = self._hist_when(a, 2)
        codex_ids = [n for p, n in hist if p == "codex"]
        self.assertTrue(codex_ids, "no codex segment was written at all")
        self.assertNotIn(src, codex_ids,
                         "the claude session id was recorded as a codex thread")
        self.assertEqual(len({n for _, n in hist}), len(hist),
                         "an id is shared across segments: %r" % (hist,))

    def test_the_chat_id_is_sent_back_so_the_next_connect_carries_it(self):
        """Recovering the id server-side is only half the fix: without telling
        the client, every later connect would have to re-recover it, and could
        only do so for as long as the pane still held a resumable seed."""
        self._clear_recordings()
        src = self._fresh_claude_id()
        a = self._chat_on_indexed("claude", src)
        _, turns = self._pane(None, "codex", ["Using Codex, implement this"],
                              resume=src)

        chat_frames = [f for f in turns[0] if f.get("type") == "chat"]
        self.assertTrue(chat_frames, "the client was never told which chat this is")
        self.assertEqual(chat_frames[0].get("sutra_id"), a,
                         "the client was told the WRONG chat")

    def test_a_rail_opened_same_provider_message_still_just_resumes(self):
        """THE CASE THAT MUST NOT CHANGE. Opening a claude chat from the rail
        and simply typing is not a switch: the recovered id makes plan()
        answer NOT_NEEDED, the seed survives, and claude resumes its own
        thread rather than starting a new one."""
        self._clear_recordings()
        a = self._chat_on_indexed("claude", CLAUDE_SRC)
        _, turns = self._pane(None, None, ["just carry on"], resume=CLAUDE_SRC)

        self.assertEqual(self._switches(turns[0]), [],
                         "an ordinary rail-opened turn replayed the conversation")
        self.assertEqual(self._hist(a), [("claude", CLAUDE_SRC)],
                         "an ordinary turn wrote a new segment")

    def test_an_unrecognised_seed_still_starts_a_chat_of_its_own(self):
        """A seed no chat records -- a transcript from the terminal, say --
        must behave exactly as before: nothing to recover, so a chat is minted
        the way it always was. The recovery is additive, not a gate."""
        self._clear_recordings()
        before = self._chat_count()
        self._pane(None, "codex", ["hello"],
                   resume="ffffffff-0000-4000-8000-00000000ffff")
        time.sleep(0.6)
        self.assertEqual(self._chat_count(), before + 1,
                         "an unrecognised seed no longer mints a chat")


# ============================================ the refresh / reconnect path ===

class ReconnectAfterRefresh(_Server):
    """A chat switched to Codex must come back on Codex after a reload.

    THE FAILURE THIS PINS, measured live: the pane reconnected and the thread
    showed "OpenAI Codex -> Claude Code, turns 1-2 carried over" -- a real
    carry-over, for a switch nobody requested.

    The browser holds sutra_id in memory only, so a refresh empties it. The
    pane then reconnects with NO ?sutra=, and _chat_local_provider is keyed
    entirely on that parameter: it returns on `if not sutra_id` and never reads
    provider_history at all. Resolution fell through to the GLOBAL default, and
    the in-loop seed recovery then found the chat AFTER active_id was already
    claude -- so switch.plan(sutra_id, "claude") saw an active codex segment
    against a claude target and did what it was told.

    GET /api/sessions now carries each row's sutra_id (chat_store.resolve, the
    existing reverse index), the rail stores it, and ?sutra= is present again on
    the very first reconnect.
    """

    def _rows(self):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/sessions?limit=200" % self.port,
                timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def _row_for(self, native_id, sutra_id, tries=25):
        """The listed row for `native_id`, once it names `sutra_id`.

        RETRIED BECAUSE THE HARNESS RACES, not because the endpoint is slow.
        chat_store._reindex() is read-modify-write over one shared _index.json
        and here two processes write it -- this test, and the server, whose
        switch.confirm() from a SIBLING test can still be in flight. The server
        writes back an index it read before this row existed and the row
        disappears; the endpoint then honestly reports sutra_id: None for a
        chat that does exist. Re-saving the record restores it.

        Only the test races: in the running panel the server is the only
        writer, which is why this is handled here and not in chat_store.
        """
        cs = self._cs()
        for _ in range(tries):
            row = {r["id"]: r for r in self._rows()}.get(native_id)
            if row is not None and row.get("sutra_id") == sutra_id:
                return row
            rec = cs.load(sutra_id)
            if rec is not None:
                cs.save(rec)          # re-add the row a late write dropped
            time.sleep(0.1)
        return {"id": native_id, "sutra_id": None}

    def test_the_session_list_names_the_chat_each_transcript_belongs_to(self):
        """The one new fact on the wire. Without it the client cannot send
        ?sutra= on the connect that decides the provider."""
        src = "c1a70000-0000-4000-8000-00000000e001"
        a = self._chat_on_indexed("claude", src)
        row = self._row_for(src, a)
        self.assertEqual(row.get("sutra_id"), a,
                         "the row does not name its chat: %r" % (row,))

    def test_a_transcript_written_outside_the_panel_is_not_sutras_chat(self):
        """REVERSED on the owner's ruling, 2026-09-09. This used to assert that a transcript
        written outside the panel still LISTS, carrying sutra_id: None -- honest, and exactly the
        behaviour he asked to be rid of. /api/sessions fills Sutra's own Chats folder, and it was
        filling it with every conversation he had ever had in VS Code or a terminal (20,255 of
        them on his disk, one of which was a Sutra chat).

        The invariant this class exists to protect is untouched and is asserted by its sibling
        above: a row that IS listed still names the chat it belongs to, which is what puts ?sutra=
        on the first reconnect. Nothing about resolving or opening a foreign transcript BY ID
        changed -- session_reader still sees every file, which is what test_app.py's
        TestChatsAreSutrasOwn pins."""
        src = "c1a70000-0000-4000-8000-00000000e002"
        self._claude_transcript(src)
        rows = {r["id"]: r for r in self._rows()}
        self.assertNotIn(src, rows,
                         "a transcript no Sutra chat claims does not belong in Sutra's list")

    def test_reconnecting_with_the_recovered_id_keeps_codex(self):
        """THE HEADLINE. The client sends the ?sutra= it read off the rail, and
        the chat comes back on codex with NO switch frame.

        The absent switch frame is the assertion that matters: reverting to
        claude and replaying back would also end on codex eventually, at
        exactly the cost this bug was made of."""
        src = "c1a70000-0000-4000-8000-00000000e003"
        a = self._chat_on_indexed("claude", src)
        _, turns = self._pane(None, "codex", ["Using Codex, do this"], resume=src)
        # The segment is written after the `done` frame; poll for it rather
        # than sleeping a fixed amount, so the reconnect below is asserted
        # against a chat that has actually moved.
        cs, deadline = self._cs(), time.time() + 6
        while time.time() < deadline:
            hist = (cs.load(a) or {}).get("provider_history") or []
            if len(hist) >= 2:
                break
            time.sleep(0.15)
        self.assertEqual([h["provider"] for h in hist], ["claude", "codex"],
                         "the chat never moved to codex: %r" % (hist,))

        # --- the refresh: the browser forgets sutra_id, the rail re-supplies it
        # ANY listed row of this chat supplies the id -- the rail keys
        # S.sutraId by native session id, and a switched chat has a row per
        # transcript. The claude one is asserted here because the QA codex stub
        # speaks the protocol but writes no rollout, so there is no codex file
        # on disk for list_sessions to find in this harness. The codex arm of
        # the listing has its own coverage in test_codex_listing.py.
        row = self._row_for(src, a)
        self.assertEqual(row.get("sutra_id"), a,
                         "no listed row names this chat, so the client cannot "
                         "send ?sutra= and the reconnect resolves globally")

        first, turns2 = self._pane(a, None, ["and now this"])
        self.assertEqual(first.get("id"), "codex",
                         "the reconnect fell back to the global default")
        self.assertEqual(first.get("source"), "chat-history",
                         "codex was not resolved from the chat's own record")
        self.assertEqual(self._switches(turns2[0]), [],
                         "the reconnect replayed codex -> claude")

    def test_settings_is_still_claude_throughout(self):
        self.assertEqual(self._settings_provider(), "claude")


# ==================================================== readiness is the gate ==

class ReadinessGoverns(_Server):
    """I. A provider that is not Ready to use is never a valid target -- and
    the refusal comes from the ONE readiness mechanism, not a second one."""

    def _first_frame(self, sutra_id, provider):
        from websockets.sync.client import connect
        with connect(self._url(sutra_id, provider), open_timeout=20) as ws:
            return json.loads(ws.recv(timeout=20))

    def test_I_a_provider_with_no_adapter_is_refused(self):
        """gemini is catalogued and has no chat adapter, so it is not runnable
        and cannot be a chat-local target."""
        a = self._chat_on("claude", CLAUDE_SRC)
        f = self._first_frame(a, "gemini")
        self.assertEqual(f.get("type"), "error", f)
        self.assertEqual(f.get("code"), "provider-missing", f)

    def test_I_an_unknown_provider_is_refused(self):
        a = self._chat_on("claude", CLAUDE_SRC)
        f = self._first_frame(a, "not-a-provider")
        self.assertEqual(f.get("type"), "error", f)
        self.assertEqual(f.get("code"), "unknown-provider", f)

    def test_a_refused_target_writes_no_segment(self):
        """A refusal must leave the chat exactly as it was. A segment naming a
        provider that never ran would make active_segment() lie, and every
        later plan() would answer NOT_NEEDED against a session that does not
        exist."""
        a = self._chat_on("claude", CLAUDE_SRC)
        self._first_frame(a, "gemini")
        self.assertEqual(self._hist(a), [("claude", CLAUDE_SRC)])

    def test_a_recorded_provider_that_stopped_being_runnable_falls_back(self):
        """A chat pinned to a provider that has since become unusable must
        still open -- on the global default -- and must SAY the recorded
        choice was dropped, through the same `ignored` list a dropped Settings
        choice already uses."""
        cs = self._cs()
        rec = cs.create(cwd=self.work)
        # gemini is never runnable here, so this stands in for "codex was
        # signed out after the segment was written" without needing to break
        # the codex stub for the whole class.
        rec.setdefault("provider_history", []).append(
            {"provider": "gemini", "native_id": "g-1", "from_turn": 0})
        cs.save(rec)

        first, _ = self._pane(rec["sutra_id"], None, [])
        self.assertEqual(first.get("type"), "provider", first)
        self.assertEqual(first.get("id"), "claude", first)
        self.assertNotEqual(first.get("source"), "chat-history", first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
