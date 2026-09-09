#!/usr/bin/env python3
"""test_switch_seed.py -- the client's `resume` seed must not survive a
provider change.

WHAT BROKE, MEASURED LIVE 2026-09-09
The browser keeps ONE session id per pane (01-state.js:1455 writes
s.claude_session from the `session` frame of WHICHEVER provider sent it) and
hands it back as `resume` on the next connect. Nothing in that id says which
provider minted it. On a Codex -> Claude switch the panel adopted the CODEX
thread id and spawned Claude with `--resume <codex id>`; Claude resolves ids in
its own tree, so the turn died with

    No conversation found with session ID: 01a08489-0565-7503-a6cf-edb45f3aa986

and -- because _demux_turn_inner adopts a native id only when the incoming one
is None (session_runtime.py:439) -- the foreign id then survived the turn and
was written onto the CLAUDE segment by switch.confirm. Two real chat records
ended up with every segment sharing one native_id, which a later switch would
have deduped into never reading the target's own transcript at all.

ASSERTED AGAINST THE REAL ARGV, not against build_agent_args' return value.
That distinction is the whole point and is the same one
TestDeepSeekSpawnedModel makes: the broken code computed `session_id=None`
correctly at app.py's claude arm and then REBUILT the argv with --resume at the
`not alive` arm below it, so a test that stopped short of the spawn would have
passed for the bug's entire life. qa/fake_claude_agent.py records the argv it
is actually launched with, from inside the launched process.

Runs entirely against stubs: no claude binary, no codex binary, no key, no
network, nothing billed.
"""
import json
import os
import shutil
import subprocess
import socket
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


#: A Codex thread id in the shape codex actually mints (measured: a hyphenated
#: hex UUID). Used as the SOURCE id throughout, so a leak is unmistakable in a
#: failure message.
CODEX_ID = "01a08489-0565-7503-a6cf-edb45f3aa986"

#: What the stub Claude reports as its own session when it starts fresh. Any
#: value distinguishable from CODEX_ID would do; a fixed one makes the
#: assertions readable.
CLAUDE_ID = "c1aude00-0000-4000-8000-000000000001"


def _rollout(path, thread_id, cwd, text="do the thing"):
    """A minimal but REAL codex rollout, in the on-disk shape verified against
    $CODEX_HOME/sessions on 2026-09-09. Written so switch.plan can actually
    read a transcript and build a payload -- a switch that refuses for lack of
    a source transcript would not exercise the seed path at all."""
    recs = [
        {"timestamp": "2026-09-09T10:00:00.000Z", "type": "session_meta",
         "payload": {"type": "session_meta", "session_id": thread_id,
                     "id": thread_id, "cwd": cwd,
                     "git": {"branch": "main", "commit_hash": "abc"}}},
        {"timestamp": "2026-09-09T10:00:01.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": text}]}},
        {"timestamp": "2026-09-09T10:00:02.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant",
                     "phase": "final_answer",
                     "content": [{"type": "output_text", "text": "done"}]}},
    ]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")


class _SeedCase(unittest.TestCase):
    """One server, one stub Claude, an isolated chat store and CODEX_HOME."""

    proc = None
    port = None
    tmpdir = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-seed-")
        sys.path.insert(0, os.path.join(HERE, "..", "lib"))
        sys.path.insert(0, HERE)
        import fixture_seed  # noqa: E402
        fixture_seed.seed(cls.tmpdir)

        cls.argv_path = os.path.join(cls.tmpdir, "claude-argv.json")
        cls.chats_dir = os.path.join(cls.tmpdir, "chats")
        cls.codex_home = os.path.join(cls.tmpdir, "codex-home")
        cls.workdir = os.path.join(cls.tmpdir, "workspace")
        os.makedirs(cls.chats_dir, exist_ok=True)
        os.makedirs(cls.workdir, exist_ok=True)

        # The source transcript the switch will read. Its cwd matches the
        # panel's workdir so nothing about the switch depends on a path the
        # test machine happens to have.
        _rollout(os.path.join(cls.codex_home, "sessions", "2026", "09", "09",
                              "rollout-2026-09-09T10-00-00-%s.jsonl" % CODEX_ID),
                 CODEX_ID, cls.workdir)

        # Pointed straight at the stub rather than through a generated `sh -c`
        # wrapper, for the reason TestDeepSeekSpawnedModel records: this
        # repo's path contains a space ("Joy Stephen").
        shim = os.path.join(HERE, "qa", "fake_claude_agent.py")
        os.chmod(shim, 0o755)

        cls.port = _free_port()
        env = dict(os.environ)
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env.pop("ANTHROPIC_API_KEY", None)   # ws_chat's own refusal, another test's job
        env["SUTRA_UI_WORKDIR"] = cls.workdir
        env["SUTRA_UI_CLAUDE_BIN"] = shim
        env["SUTRA_UI_CHATS"] = cls.chats_dir
        env["CODEX_HOME"] = cls.codex_home
        env["SUTRA_FAKE_CLAUDE_ARGV"] = cls.argv_path
        env["SUTRA_FAKE_CLAUDE_SESSION"] = CLAUDE_ID
        # The allow-list --resume is honoured for. CODEX_ID is deliberately
        # ABSENT: the stub refuses it exactly as the real binary does, which is
        # what makes a leak fail the test rather than pass unnoticed.
        env["SUTRA_FAKE_CLAUDE_KNOWN"] = CLAUDE_ID
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        else:
            raise RuntimeError("seed-leak server did not come up")

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

    # ------------------------------------------------------------- helpers --

    def _chat_store(self):
        """chat_store bound to THIS test's isolated store, in-process. The
        server writes the same directory, so a record made here is the record
        the switch reads."""
        os.environ["SUTRA_UI_CHATS"] = self.chats_dir
        sys.path.insert(0, HERE)
        import chat_store
        return chat_store

    def _chat_on(self, provider, native_id):
        cs = self._chat_store()
        rec = cs.create(cwd=self.workdir)
        cs.begin_segment(rec, provider, native_id)
        # One operator turn, so from_turn on the next segment is a real number
        # and the source transcript is not the only evidence a chat happened.
        rec = cs.load(rec["sutra_id"])
        cs.append_turn(rec, "user", [cs.block_text("do the thing")])
        return rec["sutra_id"]

    def _history(self, sutra_id):
        return self._chat_store().load(sutra_id).get("provider_history") or []

    def _run_turn(self, provider, sutra_id, resume, message="next please"):
        """One message on a pane. Returns (frames, spawns).

        `spawns` is EVERY argv the stub was launched with during this turn, not
        the last one. app.py replays a rejected-resume turn without --resume,
        so a turn that leaked its seed spawns twice and the second argv is
        clean -- reading only the last one passed while the bug was fully
        present (measured on this suite's first run)."""
        from websockets.sync.client import connect
        try:
            os.unlink(self.argv_path)
        except OSError:
            pass
        url = ("ws://127.0.0.1:%d/ws/chat?provider=%s&sutra=%s"
               % (self.port, provider, sutra_id))
        frames = []
        with connect(url, open_timeout=10) as ws:
            first = json.loads(ws.recv(timeout=10))
            self.assertEqual(first.get("type"), "provider", first)
            ws.send(json.dumps({"message": message, "resume": resume}))
            deadline = time.time() + 25
            while time.time() < deadline:
                try:
                    f = json.loads(ws.recv(timeout=10))
                except Exception:  # noqa: BLE001
                    break
                frames.append(f)
                if f.get("type") in ("done", "error"):
                    break
        spawns = []
        deadline = time.time() + 10
        while time.time() < deadline:
            spawns = self._spawns()
            if spawns:
                break
            time.sleep(0.2)
        return frames, spawns

    def _spawns(self):
        try:
            with open(self.argv_path, encoding="utf-8") as fh:
                return [json.loads(l) for l in fh if l.strip()]
        except (OSError, ValueError):
            return []

    @staticmethod
    def _resumes_in(spawns):
        """Every --resume value across every spawn, in order."""
        out = []
        for argv in spawns or []:
            try:
                out.append(argv[argv.index("--resume") + 1])
            except (ValueError, IndexError):
                pass
        return out


class SwitchDropsForeignSeed(_SeedCase):

    def test_1_provider_switch_does_not_spawn_the_target_with_the_source_id(self):
        """THE REPORTED FAILURE. codex -> claude, client re-sends the codex id."""
        sutra_id = self._chat_on("codex", CODEX_ID)
        frames, spawns = self._run_turn("claude", sutra_id, resume=CODEX_ID)

        self.assertTrue(spawns, "the stub was never spawned: %r" % (frames,))
        self.assertEqual(
            self._resumes_in(spawns), [],
            "claude was spawned with --resume after a provider change; the "
            "source provider's seed leaked into the target's argv: %r"
            % (spawns,))
        self.assertEqual(
            len(spawns), 1,
            "one clean spawn is expected; more than one means the turn was "
            "rejected and replayed: %r" % (spawns,))
        # and the turn must not carry the codex id's failure text
        errors = [f for f in frames if f.get("type") == "error"]
        self.assertFalse(
            [e for e in errors if CODEX_ID in str(e.get("detail") or "")],
            "the turn failed on the leaked codex id: %r" % (errors,))
        self.assertFalse(
            [f for f in frames if f.get("type") == "retry"],
            "a retry frame means the first spawn was rejected: %r" % (frames,))

    def test_2_successful_switch_records_the_targets_own_native_id(self):
        """The segment must name the session the TARGET created, not the source
        one. Both live records measured on 2026-09-09 got this wrong."""
        sutra_id = self._chat_on("codex", CODEX_ID)
        frames, _ = self._run_turn("claude", sutra_id, resume=CODEX_ID)

        # the switch itself was attempted and reported
        notes = [f for f in frames if f.get("type") == "switch"]
        self.assertTrue(notes, "no switch frame was sent: %r" % (frames,))
        self.assertTrue(notes[0].get("ok"),
                        "the switch was refused: %r" % (notes[0],))

        hist = self._history(sutra_id)
        self.assertEqual(len(hist), 2, "expected codex then claude: %r" % (hist,))
        self.assertEqual(hist[0]["provider"], "codex")
        self.assertEqual(hist[0]["native_id"], CODEX_ID)
        self.assertEqual(hist[1]["provider"], "claude")
        self.assertEqual(
            hist[1]["native_id"], CLAUDE_ID,
            "the claude segment must name claude's OWN session; got %r"
            % (hist[1]["native_id"],))
        self.assertNotEqual(
            hist[1]["native_id"], hist[0]["native_id"],
            "every segment shares one native_id -- a later switch would dedupe "
            "them and never read the target's transcript")

    def test_3_refused_switch_also_drops_the_seed(self):
        """The 10:17 live failure. The source transcript is MISSING, so the
        switch refuses -- but the provider still changed, so the seed is still
        stale and must still be dropped."""
        sutra_id = self._chat_on("codex", "01a00000-0000-7000-0000-000000000000")
        frames, spawns = self._run_turn(
            "claude", sutra_id, resume="01a00000-0000-7000-0000-000000000000")

        notes = [f for f in frames if f.get("type") == "switch"]
        self.assertTrue(notes, "no switch frame: %r" % (frames,))
        self.assertFalse(notes[0].get("ok"),
                         "this fixture has no source transcript, so the switch "
                         "must refuse: %r" % (notes[0],))

        self.assertTrue(spawns, "the stub was never spawned: %r" % (frames,))
        self.assertEqual(self._resumes_in(spawns), [],
                         "a REFUSED switch leaked its seed into argv: %r" % (spawns,))
        hist = self._history(sutra_id)
        self.assertEqual(hist[-1]["provider"], "claude")
        self.assertEqual(
            hist[-1]["native_id"], CLAUDE_ID,
            "a refused switch poisoned provider_history with the source id: %r"
            % (hist,))

    # -------------------------------------------------- the regression guard --

    def test_4_same_provider_claude_reconnect_still_resumes(self):
        """THE THING THAT MUST NOT CHANGE.

        switch.plan returns NOT_NEEDED for "chat is already running on
        claude", which is exactly an ordinary reconnect, and the seed must
        survive it. Without this assertion the fix could be written as "always
        drop the seed", which would cold-start claude on every reconnect and
        lose the thread -- the bug app.py's `not alive` resume arm exists to
        prevent."""
        sutra_id = self._chat_on("claude", CLAUDE_ID)
        frames, spawns = self._run_turn("claude", sutra_id, resume=CLAUDE_ID)

        notes = [f for f in frames if f.get("type") == "switch"]
        self.assertFalse(
            notes, "a same-provider reconnect is not a switch: %r" % (notes,))
        self.assertTrue(spawns, "the stub was never spawned: %r" % (frames,))
        self.assertEqual(
            self._resumes_in(spawns), [CLAUDE_ID],
            "an ordinary claude reconnect lost its resume seed: %r" % (spawns,))
        hist = self._history(sutra_id)
        self.assertEqual(len(hist), 1,
                         "a reconnect must not append a second segment: %r"
                         % (hist,))

    def test_5_a_chat_with_no_segment_keeps_its_seed(self):
        """The other NOT_NEEDED arm (`start_fresh=True`). A chat that has never
        been sent anywhere is not a provider change, so its seed is honoured
        exactly as before."""
        cs = self._chat_store()
        sutra_id = cs.create(cwd=self.workdir)["sutra_id"]
        frames, spawns = self._run_turn("claude", sutra_id, resume=CLAUDE_ID)

        self.assertFalse([f for f in frames if f.get("type") == "switch"],
                         "no segment means nothing to carry over: %r" % (frames,))
        self.assertTrue(spawns, "the stub was never spawned: %r" % (frames,))
        self.assertEqual(
            self._resumes_in(spawns), [CLAUDE_ID],
            "a chat with no segment lost its seed: %r" % (spawns,))


class StubFidelity(_SeedCase):
    """The stub has to REFUSE an unknown --resume, or tests 1-3 would pass
    whether or not the fix works. Asserted directly rather than assumed."""

    def test_the_stub_refuses_an_unknown_resume_like_the_real_binary(self):
        shim = os.path.join(HERE, "qa", "fake_claude_agent.py")
        env = dict(os.environ)
        env["SUTRA_FAKE_CLAUDE_KNOWN"] = CLAUDE_ID
        env.pop("SUTRA_FAKE_CLAUDE_ARGV", None)
        p = subprocess.run(
            [shim, "-p", "--resume", CODEX_ID],
            input="", capture_output=True, text=True, env=env, timeout=20)
        self.assertNotEqual(p.returncode, 0,
                            "an unknown --resume must exit non-zero")
        self.assertIn("No conversation found with session ID: %s" % CODEX_ID,
                      p.stderr)
        self.assertEqual(p.stdout.strip(), "",
                         "the real binary emits no stream-json on this path")

    def test_the_stub_accepts_a_known_resume_and_keeps_that_id(self):
        shim = os.path.join(HERE, "qa", "fake_claude_agent.py")
        env = dict(os.environ)
        env["SUTRA_FAKE_CLAUDE_KNOWN"] = CLAUDE_ID
        env.pop("SUTRA_FAKE_CLAUDE_ARGV", None)
        p = subprocess.run(
            [shim, "-p", "--resume", CLAUDE_ID],
            input="", capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        first = json.loads(p.stdout.strip().splitlines()[0])
        self.assertEqual(first["session_id"], CLAUDE_ID)



class DeepSeekSeedUnchanged(unittest.TestCase):
    """The same fix, on the OTHER target, and the proof it changed nothing for
    DeepSeek.

    DeepSeek's exposure is not argv -- build_acp_args has no --resume. It is
    app.py's `rt.new_session(..., session_id=session_id, ...)`: a foreign id
    there takes the session/load branch instead of session/new, which is the
    exact opposite of what switch._transport_for("deepseek") declares seeding
    to mean ("new_session_session_id: None -- forces session/new").

    ASSERTED THROUGH THE RECORDED NATIVE ID, which the existing stub already
    makes unambiguous and which needs no change to it:

        session/new   replies {"sessionId": "fake-session"}   (fake_acp_agent:190)
        session/load  replies with NO sessionId, so acp_runtime keeps the id it
                      ASKED for (acp_runtime.py:652)

    So the segment's native_id says which branch ran.
    """

    proc = None
    port = None
    tmpdir = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-seed-ds-")
        sys.path.insert(0, os.path.join(HERE, "..", "lib"))
        sys.path.insert(0, HERE)
        import fixture_seed  # noqa: E402
        fixture_seed.seed(cls.tmpdir)

        cls.chats_dir = os.path.join(cls.tmpdir, "chats")
        cls.codex_home = os.path.join(cls.tmpdir, "codex-home")
        cls.workdir = os.path.join(cls.tmpdir, "workspace")
        os.makedirs(cls.chats_dir, exist_ok=True)
        os.makedirs(cls.workdir, exist_ok=True)
        _rollout(os.path.join(cls.codex_home, "sessions", "2026", "09", "09",
                              "rollout-2026-09-09T10-00-00-%s.jsonl" % CODEX_ID),
                 CODEX_ID, cls.workdir)

        shim = os.path.join(HERE, "qa", "fake_acp_agent.py")
        os.chmod(shim, 0o755)

        cls.port = _free_port()
        env = dict(os.environ)
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env.pop("ANTHROPIC_API_KEY", None)
        env["SUTRA_UI_WORKDIR"] = cls.workdir
        env["SUTRA_UI_DEEPSEEK_BIN"] = shim
        env["SUTRA_UI_DEEPSEEK_API_KEY"] = "sk-fake-not-a-real-key"
        env["SUTRA_UI_CHATS"] = cls.chats_dir
        env["CODEX_HOME"] = cls.codex_home
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        else:
            raise RuntimeError("deepseek seed-leak server did not come up")

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

    def _cs(self):
        os.environ["SUTRA_UI_CHATS"] = self.chats_dir
        sys.path.insert(0, HERE)
        import chat_store
        return chat_store

    def _chat_on(self, provider, native_id):
        cs = self._cs()
        rec = cs.create(cwd=self.workdir)
        cs.begin_segment(rec, provider, native_id)
        rec = cs.load(rec["sutra_id"])
        cs.append_turn(rec, "user", [cs.block_text("do the thing")])
        return rec["sutra_id"]

    def _turn(self, sutra_id, resume):
        from websockets.sync.client import connect
        url = ("ws://127.0.0.1:%d/ws/chat?provider=deepseek&sutra=%s"
               % (self.port, sutra_id))
        frames = []
        with connect(url, open_timeout=10) as ws:
            first = json.loads(ws.recv(timeout=10))
            self.assertEqual(first.get("type"), "provider", first)
            ws.send(json.dumps({"message": "next please", "resume": resume}))
            deadline = time.time() + 25
            while time.time() < deadline:
                try:
                    f = json.loads(ws.recv(timeout=10))
                except Exception:  # noqa: BLE001
                    break
                frames.append(f)
                if f.get("type") in ("done", "error"):
                    break
        return frames

    def test_switch_to_deepseek_takes_session_new_not_the_foreign_id(self):
        sutra_id = self._chat_on("codex", CODEX_ID)
        frames = self._turn(sutra_id, resume=CODEX_ID)
        notes = [f for f in frames if f.get("type") == "switch"]
        self.assertTrue(notes and notes[0].get("ok"),
                        "the codex -> deepseek switch did not happen: %r" % (frames,))
        hist = self._cs().load(sutra_id).get("provider_history") or []
        self.assertEqual(hist[-1]["provider"], "deepseek")
        self.assertEqual(
            hist[-1]["native_id"], "fake-session",
            "deepseek's segment must name the session session/new created; a "
            "foreign id here means session/load ran with the codex id: %r"
            % (hist,))
        self.assertNotEqual(hist[-1]["native_id"], CODEX_ID)

    def test_same_provider_deepseek_reconnect_still_loads_its_own_session(self):
        """THE REGRESSION GUARD for DeepSeek. NOT_NEEDED, so the seed survives
        and session/load runs with DeepSeek's OWN id exactly as before."""
        sutra_id = self._chat_on("deepseek", "ds-own-session")
        frames = self._turn(sutra_id, resume="ds-own-session")
        self.assertFalse([f for f in frames if f.get("type") == "switch"],
                         "a same-provider reconnect is not a switch: %r" % (frames,))
        hist = self._cs().load(sutra_id).get("provider_history") or []
        self.assertEqual(len(hist), 1,
                         "a reconnect must not append a segment: %r" % (hist,))
        self.assertEqual(
            hist[0]["native_id"], "ds-own-session",
            "the reconnect lost its seed and started a new session (it would "
            "read 'fake-session' from session/new): %r" % (hist,))

if __name__ == "__main__":
    unittest.main(verbosity=2)
