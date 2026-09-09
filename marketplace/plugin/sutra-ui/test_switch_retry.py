#!/usr/bin/env python3
"""test_switch_retry.py -- 4B: a failed switch must not consume the carry-over,
and a foreign provider's session id must never be adopted.

TWO DEFECTS, BOTH MEASURED ON A LIVE SERVER BEFORE THIS LANDED.

1. A FAILED TARGET RE-OPENED THE SEED DOOR. A target that dies before
   thread.started leaves session_id None, and `seed_switch` was already spent
   ("once per connection, whatever happens"), so message two adopted the
   client's foreign id, passed it to codex as `resume`, and switch.confirm
   wrote it onto a CODEX segment:

       provider_history=[('claude','5e550001-...'), ('codex','5e550001-...')]

   That segment then made active_segment() report codex, so every later plan()
   returned NOT_NEEDED and the chat could NEVER carry over again. No error
   frame anywhere -- codex reports the id it was resumed WITH as its own
   thread.started id (codex_runtime.py:522), so a foreign id is accepted in
   silence. Claude rejects the same input loudly; codex has no such immune
   response, which is why these tests exercise codex specifically.

2. THE CARRY-OVER WAS SPENT ON A SWITCH THAT NEVER HAPPENED. The payload was
   built, the target never read it, no segment was written -- and yet the next
   message ran with no history and said nothing about it, which is the exact
   failure the switch marker exists to make visible.

WHAT IS ASSERTED AGAINST WHAT. provider_history is read from the store the
server writes, and `resume` presence is read from the argv the stub was
ACTUALLY launched with (appended one line per spawn), never from what the code
intended -- the distinction TestDeepSeekSpawnedModel and qa/fake_claude_agent
both exist for.

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

#: A claude-shaped source id, used as the SOURCE throughout so a leak names
#: itself in any failure message.
CLAUDE_SRC = "5e550001-0000-4000-8000-00000000c1a0"
#: What the stub claude reports when it starts fresh.
CLAUDE_NEW = "c1aude00-0000-4000-8000-00000000beef"


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server(unittest.TestCase):
    """One uvicorn per class, with all three providers stubbed.

    `codex_script` is class-level because the stub reads it from the SERVER's
    environment, fixed for the life of the process -- so a case needing a
    different script needs its own class, the constraint test_codex_chat
    already documents.
    """

    proc = None
    port = None
    tmpdir = None
    codex_script = "ok"

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-4b-")
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
        cls.cx_argv = os.path.join(cls.tmpdir, "codex-argv.jsonl")
        cls.cl_argv = os.path.join(cls.tmpdir, "claude-argv.jsonl")
        cls.cx_stdin = os.path.join(cls.tmpdir, "codex-stdin.txt")
        for d in (os.path.join(cls.home, ".codex"), cls.work, cls.chats):
            os.makedirs(d, exist_ok=True)
        # existence-only readiness probe; providers never opens it
        with open(os.path.join(cls.home, ".codex", "auth.json"), "w") as fh:
            fh.write("")

        cls.port = _free_port()
        env = dict(os.environ)
        env["HOME"] = cls.home
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env["SUTRA_UI_WORKDIR"] = cls.work
        env["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        env["SUTRA_UI_SETTINGS"] = os.path.join(cls.tmpdir, "settings.json")
        env["SUTRA_UI_CHATS"] = cls.chats
        env["SUTRA_UI_SWITCH_EGRESS"] = os.path.join(cls.tmpdir, "egress.jsonl")
        env.pop("ANTHROPIC_API_KEY", None)
        env["SUTRA_UI_CODEX_BIN"] = CODEX_STUB
        env["SUTRA_FAKE_CODEX_SCRIPT"] = cls.codex_script
        env["SUTRA_FAKE_CODEX_ARGV"] = cls.cx_argv
        env["SUTRA_FAKE_CODEX_STDIN"] = cls.cx_stdin
        env["SUTRA_UI_CLAUDE_BIN"] = CLAUDE_STUB
        env["SUTRA_FAKE_CLAUDE_ARGV"] = cls.cl_argv
        env["SUTRA_FAKE_CLAUDE_SESSION"] = CLAUDE_NEW
        # CLAUDE_SRC is resumable so a legitimate same-provider reconnect works;
        # nothing here makes a FOREIGN id resumable on the codex side.
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
            raise RuntimeError("4B server did not come up")

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
             "message": {"role": "user", "content": "FACT: token is ZEBRA-1"}},
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

    def _hist(self, sutra_id, settle=0.6):
        """provider_history, after letting any post-`done` write land."""
        time.sleep(settle)
        cs = self._cs()
        return [(h["provider"], h["native_id"])
                for h in (cs.load(sutra_id) or {}).get("provider_history") or []]

    # -------------------------------------------------------------- driving --

    def _spawns(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                return [json.loads(l) for l in fh if l.strip()]
        except (OSError, ValueError):
            return []

    def _clear_recordings(self):
        for p in (self.cx_argv, self.cl_argv, self.cx_stdin):
            try:
                os.unlink(p)
            except OSError:
                pass

    def _codex_resumes(self):
        """Every `resume <id>` codex was actually spawned with, across EVERY
        spawn -- not just the last. A leaked id can be followed by a clean
        retry spawn, and only the last recording would show it."""
        out = []
        for argv in self._spawns(self.cx_argv):
            if "resume" in argv:
                out.append(argv[argv.index("resume") + 1])
        return out

    def _claude_resumes(self):
        out = []
        for argv in self._spawns(self.cl_argv):
            if "--resume" in argv:
                out.append(argv[argv.index("--resume") + 1])
        return out

    def _pane(self, provider, sutra_id, messages, resume=None):
        """One pane, N messages on ONE socket. Returns a list of frame lists."""
        from websockets.sync.client import connect
        url = ("ws://127.0.0.1:%d/ws/chat?provider=%s&sutra=%s"
               % (self.port, provider, sutra_id))
        turns = []
        with connect(url, open_timeout=20, max_size=32 * 1024 * 1024) as ws:
            first = json.loads(ws.recv(timeout=20))
            self.assertEqual(first.get("type"), "provider", first)
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
        return turns

    @staticmethod
    def _switches(frames):
        return [f for f in frames if f.get("type") == "switch"]

    @staticmethod
    def _sessions(frames):
        return [f["id"] for f in frames if f.get("type") == "session"]


# ==================================================== target SUCCEEDS =======

class TargetSucceeds(_Server):
    codex_script = "ok"

    def test_A_successful_claude_to_codex(self):
        """A. Seed consumed, target fresh, only the target's real id recorded,
        and the next message neither switches nor replays again."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        turns = self._pane("codex", sid, ["carry on", "and again"],
                           resume=CLAUDE_SRC)

        sw1, sw2 = self._switches(turns[0]), self._switches(turns[1])
        self.assertTrue(sw1 and sw1[0].get("ok"), turns[0])
        self.assertEqual(sw1[0]["source"], "claude")
        self.assertEqual(sw1[0]["target"], "codex")
        self.assertEqual(sw2, [],
                         "the carry-over must be consumed on success -- a "
                         "second switch on the same connection would replay "
                         "the whole history again: %r" % (sw2,))

        thread = self._sessions(turns[0])[0]
        self.assertNotEqual(thread, CLAUDE_SRC,
                            "codex echoed the source id back as its own")
        # msg1 starts fresh (no `resume`), msg2 continues codex's OWN thread.
        # The source id must appear in neither.
        self.assertEqual(self._codex_resumes(), [thread],
                         "codex must resume its own thread on msg2 and nothing "
                         "else: %r" % (self._codex_resumes(),))
        self.assertNotIn(CLAUDE_SRC, self._codex_resumes())
        hist = self._hist(sid)
        self.assertEqual(hist, [("claude", CLAUDE_SRC), ("codex", thread)],
                         "provider_history must name the target's own session "
                         "and nothing else: %r" % (hist,))

    def test_C2_a_successful_switch_writes_exactly_one_target_segment(self):
        """C, second half. One valid segment, and the payload is delivered
        once -- asserted on the stdin the stub actually received."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        turns = self._pane("codex", sid, ["carry on"], resume=CLAUDE_SRC)
        self.assertTrue(self._switches(turns[0])[0].get("ok"))
        hist = self._hist(sid)
        codex_segs = [h for h in hist if h[0] == "codex"]
        self.assertEqual(len(codex_segs), 1, hist)
        with open(self.cx_stdin, encoding="utf-8") as fh:
            prompt = fh.read()
        self.assertEqual(prompt.count("You are taking over an in-progress"), 1,
                         "the replay preamble must appear once, not twice")
        self.assertIn("FACT: token is ZEBRA-1", prompt)

    def test_F_same_provider_reconnect_still_resumes(self):
        """F. codex -> codex is a reconnect, not a switch: NOT_NEEDED keeps the
        seed and the thread continues."""
        self._clear_recordings()
        own = "01a08191-7175-7f62-aaaabbbbccccdddd"
        sid = self._chat_on("codex", own)
        turns = self._pane("codex", sid, ["hello"], resume=own)
        self.assertEqual(self._switches(turns[0]), [],
                         "a same-provider reconnect is not a switch")
        self.assertEqual(self._codex_resumes(), [own],
                         "codex lost its own thread on reconnect: %r"
                         % (self._codex_resumes(),))
        self.assertEqual(self._hist(sid), [("codex", own)],
                         "a reconnect must not append a segment")

    def test_F_claude_same_provider_reconnect_unchanged(self):
        """F. Claude is frozen: its own id is still adopted and resumed."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        turns = self._pane("claude", sid, ["hello"], resume=CLAUDE_SRC)
        self.assertEqual(self._switches(turns[0]), [])
        self.assertEqual(self._claude_resumes(), [CLAUDE_SRC],
                         "claude reconnect lost its resume seed: %r"
                         % (self._claude_resumes(),))
        self.assertEqual(self._hist(sid), [("claude", CLAUDE_SRC)])

    def test_F_deepseek_same_provider_reconnect_unchanged(self):
        """F. DeepSeek is frozen. session/load echoes no sessionId, so
        acp_runtime keeps the id it ASKED for (acp_runtime.py:652) -- meaning
        the recorded id proves the seed survived and session/load ran."""
        self._clear_recordings()
        sid = self._chat_on("deepseek", "ds-own-session")
        turns = self._pane("deepseek", sid, ["hello"], resume="ds-own-session")
        self.assertEqual(self._switches(turns[0]), [])
        self.assertEqual(self._hist(sid), [("deepseek", "ds-own-session")],
                         "the deepseek reconnect started a new session (it "
                         "would read 'fake-session' from session/new)")

    def test_E_a_foreign_recorded_seed_is_never_passed_to_codex(self):
        """E. THE SILENT ONE. The chat records CLAUDE_SRC under claude; the
        client then offers it on a CODEX pane.

        Codex would ACCEPT it -- it reports the id it was resumed with as its
        own thread.started id -- so before the guard this produced a codex
        segment naming a session that does not exist in codex's tree, with no
        error frame at all."""
        self._clear_recordings()
        own = "01a08191-7175-7f62-1111222233334444"
        cs = self._cs()
        self._claude_transcript(CLAUDE_SRC)
        rec = cs.create(cwd=self.work)
        cs.begin_segment(rec, "claude", CLAUDE_SRC)   # foreign id, RECORDED
        rec = cs.load(rec["sutra_id"])
        cs.begin_segment(rec, "codex", own)           # then switched to codex
        sid = rec["sutra_id"]

        turns = self._pane("codex", sid, ["hello"], resume=CLAUDE_SRC)
        self.assertEqual(self._switches(turns[0]), [],
                         "already on codex -- NOT_NEEDED, not a switch")
        self.assertNotIn(CLAUDE_SRC, self._codex_resumes(),
                         "the claude id was handed to codex as a resume id: %r"
                         % (self._codex_resumes(),))
        reported = self._sessions(turns[0])
        self.assertNotIn(CLAUDE_SRC, reported,
                         "codex echoed the foreign id back as its own thread")
        hist = self._hist(sid)
        self.assertEqual(
            [h for h in hist if h[0] == "codex" and h[1] == CLAUDE_SRC], [],
            "a codex segment was written naming a claude session: %r" % (hist,))

    def test_H_repeated_switching_does_not_compound(self):
        """H. claude -> codex -> claude -> codex, every segment's id belonging
        to its own provider and the payload not growing per hop."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        chars, last = [], CLAUDE_SRC
        for target in ("codex", "claude", "codex"):
            turns = self._pane(target, sid, ["carry on"], resume=last)
            sw = self._switches(turns[0])
            self.assertTrue(sw and sw[0].get("ok"),
                            "hop to %s failed: %r" % (target, sw or turns[0]))
            chars.append(sw[0]["chars"])
            got = self._sessions(turns[0])
            self.assertTrue(got, "no session id from %s" % target)
            last = got[0]
            self._hist(sid)   # let the segment land before the next plan()

        hist = self._hist(sid)
        self.assertEqual([h[0] for h in hist],
                         ["claude", "codex", "claude", "codex"], hist)
        self.assertEqual(len({h[1] for h in hist}), 4,
                         "an id was reused across segments: %r" % (hist,))
        for prov, nid in hist:
            if prov == "codex":
                self.assertTrue(nid.startswith("01a"),
                                "not a codex-shaped id on a codex segment: %r"
                                % (nid,))
            else:
                self.assertFalse(nid.startswith("01a"),
                                 "a codex id on a %s segment: %r" % (prov, nid))
        # one extra turn per hop, not 1.8x per hop
        self.assertLess(max(chars), min(chars) * 1.5,
                        "the payload is compounding across hops: %r" % (chars,))


# ================================== target DIES before thread.started =======

class TargetNeverStarts(_Server):
    """codex dies BEFORE thread.started, so it never establishes a native
    session -- the one failure shape no other canned script can produce."""

    codex_script = "no-thread"

    def test_B_no_target_segment_and_no_foreign_id_adopted(self):
        """B. The switch did not happen, so nothing is recorded and nothing
        foreign is adopted."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        turns = self._pane("codex", sid, ["carry on"], resume=CLAUDE_SRC)

        sw = self._switches(turns[0])
        self.assertTrue(sw and sw[0].get("ok"),
                        "the payload must be built for this to mean anything")
        self.assertTrue([f for f in turns[0] if f["type"] == "error"],
                        "a dead target must be reported: %r" % (turns[0],))
        self.assertEqual(self._sessions(turns[0]), [],
                         "the stub dies before thread.started")
        self.assertEqual(
            self._hist(sid), [("claude", CLAUDE_SRC)],
            "a target that never started still altered provider_history")
        self.assertEqual(self._codex_resumes(), [],
                         "a foreign id reached codex: %r" % (self._codex_resumes(),))

    def test_C1_the_carry_over_survives_and_retries_on_the_same_connection(self):
        """C, first half. THE 4B FIX. Before it, message two got no switch
        frame at all: seed_switch was spent, so the turn ran with no history
        and said nothing -- while the green marker from message one was still
        on screen."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        turns = self._pane("codex", sid, ["carry on", "carry on again"],
                           resume=CLAUDE_SRC)

        sw1, sw2 = self._switches(turns[0]), self._switches(turns[1])
        self.assertTrue(sw1 and sw1[0].get("ok"), turns[0])
        self.assertTrue(
            sw2 and sw2[0].get("ok"),
            "the carry-over was consumed by a switch that never happened, so "
            "message two ran without history and without a switch frame: %r"
            % (sw2 or [f["type"] for f in turns[1]],))
        self.assertEqual(sw2[0]["source"], "claude",
                         "the source must still be claude -- a bogus codex "
                         "segment would make this NOT_NEEDED forever")
        self.assertEqual(self._hist(sid), [("claude", CLAUDE_SRC)])
        self.assertEqual(self._codex_resumes(), [])

    def test_D_retry_after_reconnect_is_safe(self):
        """D. A fresh connection re-arms by itself (seed_switch = bool(sutra_id)),
        and must still write nothing and adopt nothing."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        self._pane("codex", sid, ["carry on"], resume=CLAUDE_SRC)
        turns = self._pane("codex", sid, ["after reconnect"], resume=CLAUDE_SRC)

        sw = self._switches(turns[0])
        self.assertTrue(sw and sw[0].get("ok"),
                        "the reconnect must still attempt the carry-over: %r"
                        % (sw or [f["type"] for f in turns[0]],))
        self.assertEqual(sw[0]["source"], "claude")
        self.assertEqual(self._hist(sid), [("claude", CLAUDE_SRC)],
                         "a bogus segment survived the reconnect")
        self.assertEqual(self._codex_resumes(), [])

    def test_D_the_original_provider_is_still_reachable(self):
        """D, other half. Going back to claude must see the chat as never
        having left it -- so no switch, and claude resumes its own thread."""
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        self._pane("codex", sid, ["carry on"], resume=CLAUDE_SRC)
        self._hist(sid)
        turns = self._pane("claude", sid, ["back on claude"], resume=CLAUDE_SRC)

        self.assertEqual(self._switches(turns[0]), [],
                         "the chat never left claude, so this is a reconnect")
        self.assertEqual(self._claude_resumes(), [CLAUDE_SRC])
        self.assertEqual(self._hist(sid), [("claude", CLAUDE_SRC)])

    def test_G_a_deterministic_refusal_is_not_re_attempted(self):
        """G. ONE-SWITCH-PER-CONNECTION STILL HOLDS for every non-failure path.

        This chat's source transcript does not exist, so plan() refuses with
        NO_TRANSCRIPT -- a refusal no retry can change. It must be announced
        once and never again, or every message on the connection would carry a
        fresh refusal banner.

        Only a BUILT payload arms the re-attempt, which is why this stays
        consumed alongside NOT_NEEDED / UNKNOWN_TARGET / OVER_BUDGET /
        FENCE_BROKEN."""
        self._clear_recordings()
        sid = self._chat_on("claude", "99999999-0000-4000-8000-00000000dead",
                            with_transcript=False)
        turns = self._pane("codex", sid, ["one", "two", "three"],
                           resume=None)

        sw1 = self._switches(turns[0])
        self.assertTrue(sw1, "the refusal must be announced once: %r" % (turns[0],))
        self.assertFalse(sw1[0].get("ok"))
        self.assertEqual(sw1[0].get("reason"), "source-transcript-unreadable",
                         sw1[0])
        for n in (1, 2):
            self.assertEqual(
                self._switches(turns[n]), [],
                "a deterministic refusal was re-announced on message %d: %r"
                % (n + 1, self._switches(turns[n])))


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ============================ session established, THEN the turn fails =======

class TargetFailsAfterSession(_Server):
    """The invariant that makes "cannot duplicate a replay" true.

    The `failed` script emits thread.started BEFORE it fails
    (qa/fake_codex_agent.py:205 runs ahead of the script dispatch), so the
    target DOES establish a native session and only then reports turn.failed.
    That is the one shape neither other class can produce, and it is the shape
    the re-arm must refuse: the payload HAS been delivered and read, and a
    segment HAS been written, so re-planning the switch would send the whole
    recording a second time into a thread that already holds it.

    TWO INDEPENDENT GUARDS HOLD THIS, and this test pins the load-bearing one.
    The re-arm requires `switch_planned and session_id is None`, and a target
    that established a session leaves session_id SET -- so the `session_id is
    None` half is what refuses here, and dropping it is the edit this test
    catches. `switch_planned = False` inside `if session_id:` is a second,
    deliberately redundant guard for something whose failure mode is delivering
    a 600 KB recording twice; on every path traced, session_id never returns to
    None after a switch established one, so that clear is belt-and-braces
    rather than the thing doing the work.
    """

    codex_script = "failed"

    def test_a_session_established_then_failing_does_not_re_arm(self):
        self._clear_recordings()
        sid = self._chat_on("claude", CLAUDE_SRC)
        turns = self._pane("codex", sid, ["carry on", "carry on again"],
                           resume=CLAUDE_SRC)

        # the switch was planned and the payload built
        sw1 = self._switches(turns[0])
        self.assertTrue(sw1 and sw1[0].get("ok"),
                        "the payload must be built for this to mean anything: %r"
                        % (sw1 or [f["type"] for f in turns[0]],))
        self.assertEqual(sw1[0]["source"], "claude")
        self.assertEqual(sw1[0]["target"], "codex")

        # the target DID establish a native session, and then failed
        thread = self._sessions(turns[0])
        self.assertTrue(thread, "the target must report a thread for this test "
                                "to cover anything: %r"
                                % ([f["type"] for f in turns[0]],))
        thread = thread[0]
        self.assertNotEqual(thread, CLAUDE_SRC,
                            "codex echoed the source id back as its own")
        self.assertTrue([f for f in turns[0] if f["type"] == "error"],
                        "the turn was supposed to fail: %r"
                        % ([f["type"] for f in turns[0]],))

        # provider_history holds the VALID target session
        hist = self._hist(sid)
        self.assertEqual(hist, [("claude", CLAUDE_SRC), ("codex", thread)],
                         "the established session must be recorded, and named "
                         "by the id codex reported: %r" % (hist,))

        # THE INVARIANT: message two neither re-arms, re-switches nor replays
        self.assertEqual(
            self._switches(turns[1]), [],
            "a failure AFTER the session existed re-armed the carry-over -- "
            "the payload would be delivered twice into a thread that already "
            "holds it: %r" % (self._switches(turns[1]),))
        with open(self.cx_stdin, encoding="utf-8") as fh:
            last_prompt = fh.read()
        self.assertNotIn(
            "You are taking over an in-progress", last_prompt,
            "message two re-delivered the replay payload: %r"
            % (last_prompt[:200],))
        self.assertNotIn(CLAUDE_SRC, self._codex_resumes(),
                         "the source id reached codex: %r"
                         % (self._codex_resumes(),))
        self.assertEqual(
            self._hist(sid), hist,
            "message two altered provider_history -- it should have resumed "
            "the same thread, which begin_segment treats as idempotent")
