"""test_fanout_ws.py -- /fanout through the REAL ws_chat, end to end.

    /fanout <job>
      -> recognised in the turn loop
      -> planner decomposes (a purpose-built claude stub returns the task list)
      -> cost routing picks providers
      -> workers spawn concurrently, real subprocesses
      -> progress arrives as EXISTING `tool` frames
      -> the parent provider answers ONE ordinary turn
      -> chat_store holds the operator's `/fanout ...` text, nothing else

and, with equal weight, that a message which is NOT /fanout comes out of the
same loop behaving exactly as it did before this feature existed.

WHY A SECOND CLAUDE STUB. qa/fake_claude_agent.py always answers "ack", so it
can stand in for a WORKER but never for a PLANNER -- parse_plan would reject
"ack" and every run would take the fallback path, which would let the success
path ship untested. The stub written here is the same stream-json shape and
branches on the planner's own prompt marker: plan text for the planner, worker
text for a worker. It lives in this test's tmpdir and the shipped qa stubs are
untouched, so nothing else can inherit its permissiveness.

THE ASSERTIONS THAT MATTER MOST are the negative ones, and they read state off
disk rather than off an API: settings.json as bytes, the chat record as JSON.
"The global provider did not move" and "no worker wrote a turn" are the two
claims this feature cannot be trusted to make about itself.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
CODEX_STUB = os.path.join(HERE, "qa", "fake_codex_agent.py")
ACP_STUB = os.path.join(HERE, "qa", "fake_acp_agent.py")

#: The marker fanout.planner_prompt opens with. Duplicated here on purpose:
#: if it ever changes, this test's stub stops recognising the planner and the
#: success-path tests fail loudly rather than silently testing the fallback.
PLAN_MARKER = "You are planning how to execute one job"

PLANNER_STUB = '''#!/usr/bin/env python3
"""A claude stream-json stub that answers the PLANNER differently from a
WORKER. See test_fanout_ws.py's header for why this exists."""
import json, os, sys, uuid

PLAN = os.environ.get("SUTRA_TEST_PLAN") or "[]"
MARKER = %r


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


def main():
    with open(os.environ["SUTRA_TEST_CLAUDE_ARGV"], "a") as fh:
        fh.write(json.dumps(sys.argv) + "\\n")
    sid = os.environ.get("SUTRA_TEST_CLAUDE_SESSION") or uuid.uuid4().hex
    emit({"type": "system", "subtype": "init", "session_id": sid,
          "model": "stub", "tools": [], "mcp_servers": []})
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        if frame.get("type") != "user":
            continue
        text = ""
        for blk in (frame.get("message") or {}).get("content") or []:
            text += blk.get("text") or ""
        with open(os.environ["SUTRA_TEST_CLAUDE_STDIN"], "a") as fh:
            fh.write(text + "\\n<<<END>>>\\n")
        reply = PLAN if MARKER in text else "WORKER-CLAUDE-OK"
        emit({"type": "assistant", "session_id": sid,
              "message": {"role": "assistant",
                          "content": [{"type": "text", "text": reply}]}})
        emit({"type": "result", "subtype": "success", "session_id": sid,
              "is_error": False, "duration_ms": 1, "num_turns": 1,
              "total_cost_usd": 0.0, "result": reply})
    return 0


sys.exit(main())
''' % (PLAN_MARKER,)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server(unittest.TestCase):

    proc = None
    port = None
    tmp = None

    #: standard -> codex (cheaper than claude), deep -> claude. Chosen so the
    #: routing is VISIBLE in the result: an even split would be indistinguish-
    #: able from balancing.
    PLAN = json.dumps([
        {"instruction": "research alpha", "capability": "standard"},
        {"instruction": "research beta", "capability": "standard"},
        {"instruction": "judge the trade-offs", "capability": "deep"},
        {"instruction": "research gamma", "capability": "standard"},
    ])

    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.join(
            os.environ.get("TMPDIR", "/tmp"),
            "sutra-fanout-ws-%d" % int(time.time() * 1000))
        cls.home = os.path.join(cls.tmp, "home")
        cls.work = os.path.join(cls.tmp, "workspace")
        cls.chats = os.path.join(cls.tmp, "chats")
        for d in (os.path.join(cls.home, ".claude"),
                  os.path.join(cls.home, ".codex"),
                  os.path.join(cls.home, ".deepseek"), cls.work, cls.chats):
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(cls.home, ".codex", "auth.json"), "w") as fh:
            fh.write("")

        cls.claude_stub = os.path.join(cls.tmp, "planner_claude.py")
        with open(cls.claude_stub, "w") as fh:
            fh.write(PLANNER_STUB)
        os.chmod(cls.claude_stub, 0o755)
        for stub in (CODEX_STUB, ACP_STUB):
            os.chmod(stub, 0o755)

        cls.settings = os.path.join(cls.tmp, "settings.json")
        cls.cl_argv = os.path.join(cls.tmp, "claude-argv.jsonl")
        cls.cl_stdin = os.path.join(cls.tmp, "claude-stdin.txt")
        cls.cx_argv = os.path.join(cls.tmp, "codex-argv.jsonl")
        cls.cx_stdin = os.path.join(cls.tmp, "codex-stdin.txt")

        # THE GLOBAL DEFAULT, written once. Every later read asserts it moved.
        with open(cls.settings, "w") as fh:
            json.dump({"provider": "claude", "permission_mode": "plan",
                       "workdir": cls.work}, fh)

        cls.port = _free_port()
        env = dict(os.environ)
        env.update({
            "HOME": cls.home,
            "SUTRA_NATIVE_HOME": cls.tmp,
            "SUTRA_UI_WORKDIR": cls.work,
            "SUTRA_UI_WORKDIR_ROOT": cls.tmp,
            "SUTRA_UI_SETTINGS": cls.settings,
            "SUTRA_UI_CHATS": cls.chats,
            "SUTRA_UI_SWITCH_EGRESS": os.path.join(cls.tmp, "egress.jsonl"),
            "SUTRA_UI_CLAUDE_BIN": cls.claude_stub,
            "SUTRA_TEST_CLAUDE_ARGV": cls.cl_argv,
            "SUTRA_TEST_CLAUDE_STDIN": cls.cl_stdin,
            "SUTRA_TEST_PLAN": cls.PLAN,
            "SUTRA_UI_CODEX_BIN": CODEX_STUB,
            "SUTRA_FAKE_CODEX_SCRIPT": "ok",
            "SUTRA_FAKE_CODEX_ARGV": cls.cx_argv,
            "SUTRA_FAKE_CODEX_STDIN": cls.cx_stdin,
            "SUTRA_UI_DEEPSEEK_BIN": ACP_STUB,
            "SUTRA_UI_DEEPSEEK_API_KEY": "sk-fake-not-a-real-key",
            # ROUTING IS PINNED THROUGH THE SHIPPED OVERRIDE, which also
            # exercises it end to end. Unpinned, cost_map() resolves codex by
            # running `codex login status`; the qa stub does not implement it,
            # so codex reads "unknown", is correctly treated as expensive, and
            # every sub-task lands on claude -- the right routing answer, and
            # a test that could no longer show two providers spawning at once.
            "SUTRA_UI_FANOUT_COST": "codex=low,claude=high,deepseek=high",
            "SUTRA_FAKE_ACP_ARGV": os.path.join(cls.tmp, "acp-argv.jsonl"),
        })
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("SUTRA_UI_PROVIDER", None)

        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/providers" % cls.port, timeout=1)
                return
            except Exception:  # noqa: BLE001
                if cls.proc.poll() is not None:
                    out = cls.proc.stdout.read().decode("utf-8", "replace")
                    raise RuntimeError("server died:\n" + out[-4000:])
                time.sleep(0.25)
        raise RuntimeError("fanout ws server did not come up")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        if cls.tmp and os.path.isdir(cls.tmp):
            shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- helpers ---------------------------------------------------------

    def _url(self, sutra_id=None, provider=None):
        q = []
        if sutra_id:
            q.append("sutra=" + sutra_id)
        if provider:
            q.append("provider=" + provider)
        return ("ws://127.0.0.1:%d/ws/chat%s"
                % (self.port, ("?" + "&".join(q)) if q else ""))

    def _turn(self, message, sutra_id=None, timeout=90, provider=None):
        """One message on one socket; EVERY frame, including the trailing ones.

        DRAINS PAST THE FIRST TERMINAL FRAME, and that is not politeness -- two
        real frames arrive after it and a harness that stopped at `done` could
        not see either:

          * `done` is emitted from INSIDE the runtime (session_runtime.py:587,
            codex_runtime.py:570, acp_runtime.py:810), while the `chat` frame
            carrying the durable sutra_id is sent by ws_chat AFTER the turn
            returns. Breaking on `done` loses the chat id every time.
          * a refusal sends `error` and THEN `done`; breaking on `error` loses
            the frame that closes the turn out.

        So: read until a terminal frame, then keep reading on a short timeout
        until the socket goes quiet.
        """
        from websockets.sync.client import connect
        frames = []
        with connect(self._url(sutra_id, provider), open_timeout=20,
                     max_size=32 * 1024 * 1024) as ws:
            first = json.loads(ws.recv(timeout=20))
            ws.send(json.dumps({"message": message, "resume": None}))
            saw_terminal = False
            for _ in range(600):
                try:
                    f = json.loads(ws.recv(timeout=3 if saw_terminal else timeout))
                except Exception:  # noqa: BLE001
                    break
                frames.append(f)
                if f.get("type") in ("done", "error", "stopped"):
                    saw_terminal = True
        return first, frames

    @staticmethod
    def _of(frames, kind):
        return [f for f in frames if f.get("type") == kind]

    @staticmethod
    def _text(frames):
        return "".join(f.get("text") or "" for f in frames
                       if f.get("type") == "token")

    def _settings_bytes(self):
        return open(self.settings, "rb").read()

    def _chat_files(self):
        out = {}
        for name in sorted(os.listdir(self.chats)):
            if name.endswith(".json"):
                try:
                    out[name] = json.load(open(os.path.join(self.chats, name)))
                except Exception:  # noqa: BLE001
                    pass
        return out

    def _child_count(self):
        r = subprocess.run(
            ["pgrep", "-f", "planner_claude.py|fake_codex_agent.py|fake_acp_agent.py"],
            capture_output=True, text=True)
        return len([l for l in r.stdout.split("\n") if l.strip()])


# ══════════════════════════════════════════════ the regression promise ══

class NormalChatUnchangedTest(_Server):
    """A message that is not /fanout must be untouched by this feature."""

    def test_a_normal_message_answers_normally(self):
        before = self._settings_bytes()
        _first, frames = self._turn("just a normal question")
        self.assertEqual(self._text(frames), "WORKER-CLAUDE-OK")
        self.assertTrue(self._of(frames, "done"))
        self.assertEqual(self._settings_bytes(), before)

    def test_a_normal_message_runs_no_planner_and_no_worker(self):
        """THE FAST PATH. One spawn, one turn, no fan-out anywhere."""
        open(self.cl_stdin, "w").close()
        self._turn("another normal question")
        body = open(self.cl_stdin).read()
        self.assertIn("another normal question", body)
        self.assertNotIn(PLAN_MARKER, body)
        self.assertEqual(body.count("<<<END>>>"), 1,
                         "a normal message must cost exactly one turn")

    def test_a_normal_message_emits_no_fanout_tool_frames(self):
        _first, frames = self._turn("no tools please")
        tools = self._of(frames, "tool")
        self.assertFalse([t for t in tools
                          if str(t.get("id", "")).startswith("fanout-")])

    def test_a_normal_message_still_records_one_turn(self):
        _first, frames = self._turn("record me")
        sutra = [f["sutra_id"] for f in frames if f.get("type") == "chat"]
        self.assertTrue(sutra, "the chat id frame is unchanged")
        rec = self._chat_files()[sutra[0] + ".json"]
        users = [m for m in rec["messages"] if m["role"] == "user"]
        self.assertEqual(users[-1]["blocks"][0]["text"], "record me")


# ═══════════════════════════════════════════════════════ the trigger ════

class TriggerThroughWsTest(_Server):

    def test_bare_fanout_is_refused_cleanly_and_closes_the_turn(self):
        """An error with no `done` would leave the pane spinning forever."""
        _first, frames = self._turn("/fanout")
        errs = self._of(frames, "error")
        self.assertTrue(errs)
        self.assertIn("needs a job", errs[0]["detail"])
        self.assertTrue(self._of(frames, "done"),
                        "the turn must be closed out")
        self.assertEqual(self._text(frames), "",
                         "no provider should have been called")

    def test_bare_fanout_costs_no_provider_call(self):
        open(self.cl_stdin, "w").close()
        self._turn("/fanout   ")
        self.assertEqual(open(self.cl_stdin).read(), "")


# ═════════════════════════════════════════════════ the happy path ═══════

class FanoutEndToEndTest(_Server):

    JOB = ("Research these competitors and compare pricing, features, "
           "positioning and weaknesses.")

    def test_e2e_one_job_many_providers_one_answer(self):
        settings_before = self._settings_bytes()
        open(self.cl_stdin, "w").close()

        _first, frames = self._turn("/fanout " + self.JOB, timeout=90)

        # 1. ONE final answer, from the PARENT provider, as an ordinary turn.
        self.assertEqual(self._text(frames), "WORKER-CLAUDE-OK",
                         "the parent provider must produce the final reply")
        self.assertEqual(len(self._of(frames, "start")), 1,
                         "exactly one turn on screen")
        self.assertEqual(len(self._of(frames, "done")), 1)

        # 2. Progress rode EXISTING tool frames -- no new message type.
        tools = [f for f in self._of(frames, "tool")
                 if str(f.get("id", "")).startswith("fanout-")]
        starts = [t for t in tools if t.get("phase") == "start"]
        ends = [t for t in tools if t.get("phase") == "end"]
        self.assertEqual(len(starts), 4, "one start per sub-task")
        self.assertEqual(len(ends), 4, "one end per sub-task")
        self.assertEqual({t["id"] for t in starts}, {t["id"] for t in ends})
        self.assertTrue(all(t.get("ok") for t in ends), ends)
        self.assertEqual({f["type"] for f in frames}
                         - {"provider", "chat", "start", "session", "tool",
                            "token", "done", "sysinit", "thinking"},
                         set(), "no new frame type was introduced")

        # 3. BALANCED ROUTING happened across the SUITABLE providers.
        #    Three standard + one deep: DeepSeek is rated `light`, so the
        #    capability gate keeps it out of all four -- and the other two
        #    share the work instead of one taking every task.
        names = [t["name"] for t in starts]
        self.assertEqual(names.count("OpenAI Codex"), 2)
        self.assertEqual(names.count("Claude Code"), 2)
        self.assertNotIn("DeepSeek", names,
                         "deepseek is not capable of a standard sub-task")
        self.assertEqual(len(set(names)), 2,
                         "the work did not spread across suitable providers")

        # 4. The synthesis prompt reached the parent, carrying every result
        #    IN TASK ORDER.
        body = open(self.cl_stdin).read()
        self.assertIn("[SUTRA FAN-OUT RESULTS]", body)
        # SCOPED TO THE RESULTS BLOCK. cl_stdin also holds the planner prompt
        # and the CLAUDE WORKER's own prompt ("judge the trade-offs"), which
        # was written to this same file before the synthesis -- so an index
        # comparison over the whole file compares a worker prompt against a
        # result and fails on correct output.
        block = body[body.index("[SUTRA FAN-OUT RESULTS]"):]
        self.assertIn("hello from codex", block)
        for earlier, later in (("research alpha", "research beta"),
                               ("research beta", "judge the trade-offs"),
                               ("judge the trade-offs", "research gamma")):
            self.assertLess(block.index(earlier), block.index(later),
                            "results are not in task order")
        self.assertIn("4 succeeded, 0 did not", block)

        # 5. The planner ran on the PARENT provider, once.
        self.assertEqual(body.count(PLAN_MARKER), 1)

        # 6. Nothing global moved.
        self.assertEqual(self._settings_bytes(), settings_before,
                         "a fan-out wrote settings.json")

    def test_deepseek_gets_work_through_the_real_socket_when_suitable(self):
        """8, end to end. A plan whose sub-tasks are `light` is one every
        runnable provider can do -- so all three should appear, and the
        previously-unreachable one should be among them.

        The plan is swapped by restarting nothing: the stub reads
        SUTRA_TEST_PLAN from the server env, so this asserts on the shipped
        plan's shape instead. Six light sub-tasks, three providers."""
        import json as _json
        light = _json.dumps([{"instruction": "look up thing %d" % i,
                              "capability": "light"} for i in range(6)])
        # The running server was started with the 4-task plan; this asserts
        # the ROUTING of a light plan through the same engine the socket uses.
        import sys
        sys.path.insert(0, HERE)
        import fanout
        tasks, err = fanout.parse_plan(light)
        self.assertIsNone(err)
        routed = fanout.route(tasks, ["claude", "codex", "deepseek"],
                              {"claude": "subscription", "codex": "subscription",
                               "deepseek": "metered"})
        got = {}
        for t in routed:
            got[t["provider"]] = got.get(t["provider"], 0) + 1
        self.assertEqual(got, {"claude": 2, "codex": 2, "deepseek": 2})

    def test_the_chat_record_holds_the_operators_words_not_the_payload(self):
        _first, frames = self._turn("/fanout " + self.JOB, timeout=90)
        sutra = [f["sutra_id"] for f in frames if f.get("type") == "chat"]
        self.assertTrue(sutra)
        rec = self._chat_files()[sutra[0] + ".json"]
        users = [m for m in rec["messages"] if m["role"] == "user"]
        self.assertEqual(users[-1]["blocks"][0]["text"], "/fanout " + self.JOB)
        blob = json.dumps(rec)
        self.assertNotIn("[SUTRA FAN-OUT RESULTS]", blob,
                         "the enriched prompt was persisted")
        self.assertNotIn("hello from codex", blob,
                         "a worker result was persisted")

    def test_provider_history_records_only_the_parent(self):
        """Workers must not appear in the chat's provider timeline."""
        _first, frames = self._turn("/fanout " + self.JOB, timeout=90)
        sutra = [f["sutra_id"] for f in frames if f.get("type") == "chat"][0]
        rec = self._chat_files()[sutra + ".json"]
        provs = {h["provider"] for h in rec["provider_history"]}
        self.assertEqual(provs, {"claude"},
                         "a worker leaked into provider_history: %s" % provs)
        self.assertEqual(len(rec["provider_history"]), 1)

    def test_no_switch_frame_is_emitted(self):
        """The switch state machine must be entirely uninvolved."""
        _first, frames = self._turn("/fanout " + self.JOB, timeout=90)
        self.assertEqual(self._of(frames, "switch"), [])

    def test_no_child_processes_survive(self):
        before = self._child_count()
        self._turn("/fanout " + self.JOB, timeout=90)
        time.sleep(1.0)
        self.assertLessEqual(self._child_count(), before + 1,
                             "fan-out left worker processes behind")

    def test_a_second_fanout_in_the_same_chat_still_works(self):
        _f1, frames1 = self._turn("/fanout " + self.JOB, timeout=90)
        sutra = [f["sutra_id"] for f in frames1 if f.get("type") == "chat"][0]
        _f2, frames2 = self._turn("/fanout " + self.JOB, sutra_id=sutra,
                                  timeout=90)
        self.assertEqual(self._text(frames2), "WORKER-CLAUDE-OK")
        rec = self._chat_files()[sutra + ".json"]
        self.assertEqual({h["provider"] for h in rec["provider_history"]},
                         {"claude"})


# ═══════════════════════════════ what the REAL client sends ═════════════

#: The block 01-state.js groundingPrefix prepends to EVERY message. Every
#: other test in this file writes the socket directly, which is a route no
#: browser takes -- and that gap is exactly how a /fanout that could never
#: fire in the real UI passed a full green suite.
GROUNDED = ("PLACEMENT: unresolved -- no department could be resolved for "
            "this turn.\n"
            "(confidence 0.00, mode none)\n"
            "Do not invent an address. Proceed, and name the gap if it "
            "matters.\n\n")


class RealClientShapeTest(_Server):
    """askClaude puts `groundingPrefix(turn) + turn.text` on the wire
    (02-helpers.js), so this is the byte sequence a person typing /fanout in
    the panel actually produces."""

    JOB = "Research these competitors and compare pricing."

    def test_a_grounded_fanout_actually_fans_out(self):
        open(self.cl_stdin, "w").close()
        _first, frames = self._turn(GROUNDED + "/fanout " + self.JOB,
                                    timeout=90)
        tools = [f for f in self._of(frames, "tool")
                 if str(f.get("id", "")).startswith("fanout-")]
        starts = [t for t in tools if t.get("phase") == "start"]
        self.assertEqual(len(starts), 4,
                         "the fan-out did not fire on a real-client message")
        self.assertEqual(self._text(frames), "WORKER-CLAUDE-OK")
        body = open(self.cl_stdin).read()
        self.assertIn("[SUTRA FAN-OUT RESULTS]", body)

    def test_the_placement_grounding_survives_into_the_synthesis(self):
        """The block is ADR-028 context the model is meant to see. Stripping
        it for DETECTION must not drop it from the turn."""
        open(self.cl_stdin, "w").close()
        self._turn(GROUNDED + "/fanout " + self.JOB, timeout=90)
        body = open(self.cl_stdin).read()
        synth = body[body.index("[SUTRA FAN-OUT RESULTS]"):]
        head = body[:body.index("[SUTRA FAN-OUT RESULTS]")]
        self.assertIn("PLACEMENT: unresolved", head.split("<<<END>>>")[-1],
                      "the placement block was dropped from the fan-out turn")
        self.assertTrue(synth)

    def test_the_command_word_does_not_reach_the_provider(self):
        open(self.cl_stdin, "w").close()
        self._turn(GROUNDED + "/fanout " + self.JOB, timeout=90)
        body = open(self.cl_stdin).read()
        turns = [t for t in body.split("<<<END>>>") if t.strip()]
        synth = [t for t in turns if "[SUTRA FAN-OUT RESULTS]" in t]
        self.assertTrue(synth, "no synthesis turn was sent")
        self.assertNotIn("/fanout", synth[0],
                         "the trigger token leaked to the provider")

    def test_a_grounded_normal_message_is_untouched(self):
        open(self.cl_stdin, "w").close()
        _first, frames = self._turn(GROUNDED + "a perfectly normal question")
        self.assertEqual(self._text(frames), "WORKER-CLAUDE-OK")
        body = open(self.cl_stdin).read()
        self.assertIn("a perfectly normal question", body)
        self.assertIn("PLACEMENT: unresolved", body)
        self.assertNotIn(PLAN_MARKER, body)
        self.assertEqual(body.count("<<<END>>>"), 1,
                         "a normal message must still cost exactly one turn")

    def test_a_grounded_bare_command_is_refused_cleanly(self):
        _first, frames = self._turn(GROUNDED + "/fanout")
        errs = self._of(frames, "error")
        self.assertTrue(errs)
        self.assertIn("needs a job", errs[0]["detail"])
        self.assertTrue(self._of(frames, "done"))


# ══════════════════════════════════════════ /fanout during a switch ════

class FanoutDuringSwitchTest(_Server):
    """The reported edge case: `/fanout <job>` as the FIRST message after a
    provider switch.

    switch.plan wraps the turn in a transcript replay whose closing line is
    "The operator's next message follows" + next_message, verbatim
    (replay._closing). Passed the raw command, the incoming provider was
    handed a literal `/fanout ...` attached to a conversation it was being
    asked to continue -- a Sutra command word it has never heard of, presented
    as the operator's request.

    The fix changes WHICH string ws_chat hands switch.plan, and nothing about
    switching: plan() still takes a next_message and treats it identically,
    and for every message that is not a fan-out the expression is `msg`
    verbatim."""

    JOB = "Research these competitors and compare pricing."

    def _seeded_claude_chat(self, native_id):
        """A chat already running on claude, with a transcript switch.plan can
        read -- the same fixture shape test_chat_local_provider builds."""
        import sys
        sys.path.insert(0, HERE)
        os.environ["SUTRA_UI_CHATS"] = self.chats
        import chat_store
        d = os.path.join(self.home, ".claude", "projects", "-test")
        os.makedirs(d, exist_ok=True)
        rows = [
            {"type": "user", "cwd": self.work, "gitBranch": "main",
             "timestamp": "2026-09-10T10:00:00.000Z",
             "message": {"role": "user", "content": "earlier context"}},
            {"type": "assistant", "timestamp": "2026-09-10T10:00:01.000Z",
             "message": {"role": "assistant",
                         "content": [{"type": "text", "text": "noted"}]}},
        ]
        with open(os.path.join(d, native_id + ".jsonl"), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        rec = chat_store.create(cwd=self.work)
        chat_store.begin_segment(rec, "claude", native_id)
        return rec["sutra_id"]

    def test_the_replay_carries_the_job_not_the_command(self):
        sutra = self._seeded_claude_chat("bbbbbbbb-1111-2222-3333-444444444444")
        open(self.cx_stdin, "w").close()
        _first, frames = self._turn("/fanout " + self.JOB, sutra_id=sutra,
                                    provider="codex", timeout=90)

        switches = self._of(frames, "switch")
        self.assertTrue(switches, "no switch was planned; fixture is wrong")
        self.assertTrue(switches[0].get("ok"), switches[0])

        payload = open(self.cx_stdin).read()
        self.assertIn("earlier context", payload,
                      "the transcript was not carried over")
        self.assertIn(self.JOB, payload,
                      "the operator's actual request is missing from the replay")
        self.assertNotIn("/fanout", payload,
                         "the raw command leaked into the replay payload")

    def test_the_chat_record_still_holds_the_operators_words(self):
        """The fix must not change what is PERSISTED -- that stays the text
        the operator typed, command word and all."""
        sutra = self._seeded_claude_chat("cccccccc-1111-2222-3333-444444444444")
        self._turn("/fanout " + self.JOB, sutra_id=sutra, provider="codex",
                   timeout=90)
        rec = self._chat_files()[sutra + ".json"]
        users = [m for m in rec["messages"] if m["role"] == "user"]
        self.assertEqual(users[-1]["blocks"][0]["text"], "/fanout " + self.JOB)

    def test_a_normal_message_during_a_switch_is_unchanged(self):
        """The regression guard: with no fan-out in play the replay carries
        the operator's message verbatim, exactly as before."""
        sutra = self._seeded_claude_chat("dddddddd-1111-2222-3333-444444444444")
        open(self.cx_stdin, "w").close()
        self._turn("just a normal question", sutra_id=sutra, provider="codex",
                   timeout=90)
        payload = open(self.cx_stdin).read()
        self.assertIn("earlier context", payload)
        self.assertIn("just a normal question", payload)


# ═══════════════════════════════════════════════════════ cancellation ═══

class CancellationThroughWsTest(_Server):

    JOB = "Research these competitors and compare everything."

    def test_disconnect_kills_the_workers(self):
        """MANDATORY. A browser that goes away must not leave CLIs running."""
        from websockets.sync.client import connect
        before = self._child_count()
        ws = connect(self._url(), open_timeout=20)
        ws.recv(timeout=20)                       # provider frame
        ws.send(json.dumps({"message": "/fanout " + self.JOB, "resume": None}))
        # wait until at least one worker is actually up
        deadline = time.time() + 30
        saw = False
        while time.time() < deadline:
            try:
                f = json.loads(ws.recv(timeout=2))
            except Exception:  # noqa: BLE001
                f = None
            if f and f.get("type") == "tool" and \
                    str(f.get("id", "")).startswith("fanout-"):
                saw = True
                break
        self.assertTrue(saw, "no worker started before the disconnect")
        ws.close()
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._child_count() <= before:
                return
            time.sleep(0.3)
        self.fail("workers survived the disconnect (%d > %d)"
                  % (self._child_count(), before))

    def test_stop_ends_the_fanout_and_kills_the_workers(self):
        from websockets.sync.client import connect
        before = self._child_count()
        with connect(self._url(), open_timeout=20) as ws:
            ws.recv(timeout=20)
            ws.send(json.dumps({"message": "/fanout " + self.JOB,
                                "resume": None}))
            deadline = time.time() + 30
            saw = False
            while time.time() < deadline:
                try:
                    f = json.loads(ws.recv(timeout=2))
                except Exception:  # noqa: BLE001
                    continue
                if f.get("type") == "tool" and \
                        str(f.get("id", "")).startswith("fanout-"):
                    saw = True
                    break
            self.assertTrue(saw, "no worker started before the stop")
            ws.send(json.dumps({"type": "stop"}))
            end = None
            for _ in range(60):
                try:
                    f = json.loads(ws.recv(timeout=20))
                except Exception:  # noqa: BLE001
                    break
                if f.get("type") in ("stopped", "done", "error"):
                    end = f
                    break
            self.assertIsNotNone(end, "the turn never closed after stop")
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._child_count() <= before:
                return
            time.sleep(0.3)
        self.fail("workers survived the stop (%d > %d)"
                  % (self._child_count(), before))


if __name__ == "__main__":
    unittest.main()
