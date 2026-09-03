"""Characterization of the Shadow delegate spawn path + its Claude-only guard.

WHY THIS EXISTS
---------------
`shadow_runner.spawn_delegate_session` had ZERO test coverage -- the only two
references in the tree were its own definition and app.py's three call sites
-- so the ACP delegate refactor would have had no safety net at all. These
tests pin what the CLAUDE path does today, at the joints that refactor has to
cut:

  the argv     _shadow_args emits Claude's flag vocabulary, PLAN MODE included
               -- that flag is the delegate's entire v1 safety story ("real
               turns, visible work, no unsupervised writes")
  the guard    a non-Claude active provider is REFUSED here, instead of being
               handed Claude's argv and left to fail in the child's parser
  the boot     first turn = the manifest, and the session id comes OUT of that
               turn's frames (Claude has no pre-turn handshake; ACP does)
  the wiring   register(sid, rt) reaches the registry _validated_say resolves
               through, the observer is attached, DELEGATES[sid] is set, one
               ledger row is written
  THE PUMP     a queued say reaches the child AND its _turn_boundary lands in
               shadow_runner._BOUNDARIES[sid] -- the frame a mission waiter
               blocks on. A headless delegate has no websocket loop draining
               its TurnQueue; _pump IS that drain. It is also the piece an ACP
               port cannot reuse (send_user_frame + demux_turn collapse into
               one prompt_turn call), which is why it is pinned by behaviour
               here and not by reading the source.
  the failure  a child that dies without a `result` raises, kills its group,
               and registers NOTHING

What is deliberately NOT pinned: the exact flag ORDER inside build_agent_args
(test_runtime_characterization.py owns the argv contract), and the delegate's
transcript location (session_reader.read_session already resolves Claude's
tree and DeepSeek's, so it is not part of this seam).

stdlib only: unittest + asyncio driven by asyncio.run(), matching
test_stream_readline.py. No server, no uvicorn -- this is the in-process seam.

Run: .venv/bin/python -m unittest test_shadow_delegate -v
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

# IMPORT-TIME ISOLATION, before `import app` below. app.py runs
# WORKDIR_READY = _ensure_workdir() at module level, and providers /
# shadow_ledger resolve their paths from env, so an unguarded import of this
# test file would create ~/sutra-ui-workspace and read the operator's real
# ~/.sutra-ui/settings.json. Plain assignment, not setdefault: an inherited
# value from the surrounding shell would defeat the point.
_ENV_TMP = tempfile.mkdtemp(prefix="shadow-delegate-env-")
os.environ["SUTRA_UI_WORKDIR"] = os.path.join(_ENV_TMP, "workspace")
os.environ["SUTRA_UI_WORKDIR_ROOT"] = _ENV_TMP
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ["SUTRA_NATIVE_HOME"] = os.path.join(_ENV_TMP, "native")
os.environ["SUTRA_SHADOW_HOME"] = os.path.join(_ENV_TMP, "shadow")

import app                      # noqa: E402  (env above must be set first)
import providers                # noqa: E402
import session_runtime          # noqa: E402
import shadow_ledger            # noqa: E402
import shadow_runner            # noqa: E402


# The fake CLI: Claude's stream-json, just enough of it. Shape lifted from
# test_shadow_runner.FAKE (already proven against the real demux) -- init,
# text_delta, result, one process serving many turns. argv[1] is a log file:
# every message it receives is appended as one JSON line, which is how the
# tests below see WHICH turns arrived and in what order.
FAKE_OK = r"""#!/usr/bin/env python3
import json, os, sys
log = sys.argv[1]
sid = "delegate-fake-%d" % os.getpid()
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
    with open(log, "a") as handle:
        handle.write(json.dumps({"msg": msg}) + "\n")
    emit({"type": "system", "subtype": "init", "session_id": sid,
          "model": "fake", "tools": [], "mcp_servers": [],
          "slash_commands": [], "permissionMode": "plan", "cwd": os.getcwd()})
    emit({"type": "stream_event", "session_id": sid,
          "event": {"delta": {"type": "text_delta",
                              "text": "echo: " + msg[:60]}}})
    emit({"type": "result", "subtype": "success", "is_error": False,
          "session_id": sid, "duration_ms": 1, "num_turns": 1,
          "total_cost_usd": 0.0})
"""

# Accepts the manifest turn and then dies WITHOUT a `result`. Reading the line
# first is deliberate: it keeps the failure on the demux/EOF path (got_result
# False -> RuntimeError) rather than turning into a BrokenPipeError out of
# send_user_frame, which is a different bug with a different owner.
FAKE_DEAD = r"""#!/usr/bin/env python3
import sys
sys.stdin.readline()
"""


def _write_fake(directory, body, name):
    path = os.path.join(directory, name)
    with open(path, "w") as handle:
        handle.write(body)
    os.chmod(path, 0o755)
    return path


async def _reap(proc):
    """Wait a killed child out INSIDE the loop that owns it. asyncio.run()
    closes the loop without closing subprocess transports, so a child reaped
    only in tearDown resurfaces as `Event loop is closed` out of
    BaseSubprocessTransport.__del__ -- noise that would sit on top of every
    future run of this file."""
    if proc is None:
        return
    try:
        await asyncio.wait_for(proc.wait(), 5)
    except Exception:
        pass


class _RecordingRuntime(session_runtime.SessionRuntime):
    """Real runtime, with the spawned process kept reachable.

    Patched over session_runtime.SessionRuntime for the failure test, where
    spawn_delegate_session's own error path calls clear() and the test is
    otherwise left with no handle to reap. It also pins the seam: the
    transport class is resolved off the session_runtime MODULE at call time
    (`import session_runtime as srt; rt = srt.SessionRuntime()`), which is
    the hook a provider-aware spawner would use to hand back an AcpRuntime.
    """

    procs = []

    async def spawn(self, args, cwd, key, env=None):
        proc = await super().spawn(args, cwd, key, env=env)
        _RecordingRuntime.procs.append(proc)
        return proc


class TestShadowArgsGuard(unittest.TestCase):
    """_shadow_args: what it builds for Claude, and what it refuses.

    providers.active_provider_detail / provider_by_id are patched on the LIVE
    module and restored (the no-importlib.reload convention test_shadow_flag.py
    documents: reloading providers mid-suite replaces state other test files
    hold references to).
    """

    def setUp(self):
        self._detail = providers.active_provider_detail
        self._by_id = providers.provider_by_id

    def tearDown(self):
        providers.active_provider_detail = self._detail
        providers.provider_by_id = self._by_id

    def _pretend(self, pid, name, bin_path="/usr/local/bin/x"):
        providers.active_provider_detail = lambda: {
            "id": pid, "source": "settings", "ignored": []}
        providers.provider_by_id = lambda p: (
            None if pid is None else
            {"id": pid, "name": name, "bin_path": bin_path,
             "runnable": True, "reason": None})

    def test_01_claude_builds_the_persistent_plan_mode_argv(self):
        self._pretend("claude", "Claude Code", "/opt/homebrew/bin/claude")
        args = app._shadow_args()
        self.assertEqual(args[0], "/opt/homebrew/bin/claude",
                         "the ACTIVE provider's binary, not CLAUDE_BIN")
        self.assertEqual(args[1], "-p")
        # PLAN MODE. The delegate's whole v1 safety promise is this flag; an
        # ACP port has to carry it as session/set_session_mode instead, and
        # losing it silently means delegates that write unsupervised.
        self.assertIn("--permission-mode", args)
        self.assertEqual(args[args.index("--permission-mode") + 1], "plan")
        # PERSISTENT process: turns arrive as stdin frames, so one process
        # serves the manifest AND every later say from the pump.
        self.assertIn("--input-format", args)
        self.assertEqual(args[args.index("--input-format") + 1], "stream-json")
        self.assertIn("--output-format", args)
        self.assertEqual(args[args.index("--output-format") + 1], "stream-json")
        # No thread to resume and no model pinned: a delegate is always born
        # cold, on whatever the CLI defaults to.
        self.assertNotIn("--resume", args)
        self.assertNotIn("--model", args)
        # msg="" is passed but must never reach argv as a positional -- an
        # empty prompt would make the child answer before the manifest lands.
        self.assertNotIn("", args)

    def test_02_a_non_claude_provider_is_refused_not_mis_flagged(self):
        """The bug this guard closes: DeepSeek's binary + Claude's flags.

        Before the guard, `provider: deepseek` produced
        `deepseek -p --input-format stream-json ...`, which that CLI rejects
        in its argv parser -- reaching the operator as "delegate session
        failed to boot" with a parse error, and pointing at nothing they
        could act on.
        """
        self._pretend("deepseek", "DeepSeek", "/opt/homebrew/bin/deepseek")
        with self.assertRaises(app.HTTPException) as caught:
            app._shadow_args()
        self.assertEqual(caught.exception.status_code, 503)
        detail = caught.exception.detail
        self.assertIn("Claude only", detail)
        self.assertIn("deepseek", detail, "name the provider that was active")
        self.assertIn("Switch to Claude", detail, "say what fixes it")
        # str() is what survives into the mission record on the promoted /
        # retried path (start_mission_async does str(exc)[:200]), so the
        # reason must fit inside that truncation.
        self.assertLessEqual(len(str(caught.exception)), 200,
                             "the refusal is truncated away in the mission "
                             "file -- shorten it")

    def test_03_the_guard_is_a_named_set_not_a_literal(self):
        """The ACP delegate path replaces this guard; the set is where it
        lands. Also asserts it has NOT been widened to providers.ADAPTERS,
        which answers a different question (can a CHAT PANE run this) and
        would re-open the bug."""
        self.assertEqual(app.SHADOW_PROVIDERS, frozenset({"claude"}))
        self.assertNotEqual(app.SHADOW_PROVIDERS, providers.ADAPTERS)

    def test_04_no_usable_provider_still_says_so(self):
        self._pretend(None, None)
        with self.assertRaises(app.HTTPException) as caught:
            app._shadow_args()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("no usable provider", caught.exception.detail)


class TestSpawnDelegateSession(unittest.TestCase):
    """spawn_delegate_session against a fake CLI, in process."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shadow-delegate-")
        self.log = os.path.join(self.tmp, "turns.jsonl")
        self.fake = _write_fake(self.tmp, FAKE_OK, "fake-claude")
        self.dead = _write_fake(self.tmp, FAKE_DEAD, "dead-claude")
        self.registered = []
        self.sids = []

    def tearDown(self):
        # A leaked delegate is a live subprocess, so this is not optional.
        for _sid, rt in self.registered:
            try:
                rt.kill_group()
                rt.clear()
            except Exception:
                pass
        for sid in self.sids:
            session_runtime.RUNTIMES.pop(sid, None)
            shadow_runner.DELEGATES.pop(sid, None)
            shadow_runner._BOUNDARIES.pop(sid, None)
            shadow_runner._RECENT_TEXT.pop(sid, None)
            shadow_runner._LAST_FRAME_TS.pop(sid, None)
        shadow_runner._OBSERVED.clear()

    def _register(self, sid, rt):
        """Records the call AND calls through, so the test can reach the
        runtime (spawn_delegate_session returns only the id) while still
        exercising the real registry the say path resolves against."""
        self.registered.append((sid, rt))
        self.sids.append(sid)
        session_runtime.register_runtime(sid, rt)

    def _build_args(self, binary):
        calls = []

        def build_args():
            calls.append(1)
            return [sys.executable, binary, self.log]
        build_args.calls = calls
        return build_args

    def _turns(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as handle:
            return [json.loads(line)["msg"] for line in handle if line.strip()]

    def test_10_boot_wiring_and_the_pump(self):
        build_args = self._build_args(self.fake)
        manifest = "You are a delegate session. Objective: pin this path."

        async def go():
            sid = await shadow_runner.spawn_delegate_session(
                build_args, self.tmp, manifest, self._register)
            # THE BOOT QUEUE IS EMPTY: attach_observer runs AFTER the manifest
            # turn's demux, so the boot boundary is not in it. A mission's
            # first waiter therefore blocks on the first PUMPED turn, never on
            # a leftover from the spawn.
            boundaries = shadow_runner._BOUNDARIES[sid]
            self.assertTrue(boundaries.empty(), "boot boundary must not queue")
            # THE PUMP: this is exactly what _validated_say does -- payload on
            # the TurnQueue, then set the event. Nothing else drains this queue
            # for a headless delegate.
            rt = self.registered[0][1]
            rt.turn_queue.put({"message": "SAY-ONE", "_source": "shadow"},
                              source="shadow")
            rt.queue_event.set()
            frame = await asyncio.wait_for(boundaries.get(), 20)
            proc = rt.proc
            rt.kill_group()
            await _reap(proc)
            return sid, frame

        sid, frame = asyncio.run(go())

        # 1. the child's own session id came back, out of the turn's frames
        self.assertTrue(sid.startswith("delegate-fake-"), sid)
        # 2. build_args() called EXACTLY once -- argv is spawn-time, not
        #    per-turn (an ACP port must keep it that way; session/new is too)
        self.assertEqual(len(build_args.calls), 1)
        # 3. the first turn was the manifest, the second was the pumped say
        self.assertEqual(self._turns(), [manifest, "SAY-ONE"])
        # 4. registered where the say path looks
        self.assertEqual([s for s, _ in self.registered], [sid])
        self.assertIs(session_runtime.lookup_runtime(sid),
                      self.registered[0][1])
        # 5. ours to clean up when the mission goes terminal
        self.assertIs(shadow_runner.DELEGATES[sid], self.registered[0][1])
        # 6. the boundary a mission waiter consumes, from the PUMPED turn
        self.assertEqual(frame["type"], "_turn_boundary")
        self.assertEqual(frame["session"], sid)
        self.assertTrue(frame["got_result"])
        self.assertIsNone(frame["error"])
        # 7. the observer is live: streamed text feeds the mission reader,
        #    and the frame clock feeds check_stalls
        self.assertIn("echo: SAY-ONE", shadow_runner._RECENT_TEXT[sid])
        self.assertIn(sid, shadow_runner._LAST_FRAME_TS)
        # 8. one ledger row, naming the mode it was spawned in
        rows = [r for r in shadow_ledger.read("actions", 50)
                if r.get("kind") == "spawn" and sid in (r.get("summary") or "")]
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("plan mode", rows[0]["summary"])

    def test_11_a_child_that_never_results_raises_and_leaks_nothing(self):
        build_args = self._build_args(self.dead)
        _RecordingRuntime.procs = []
        original = session_runtime.SessionRuntime
        session_runtime.SessionRuntime = _RecordingRuntime

        async def go():
            with self.assertRaises(RuntimeError) as caught:
                await shadow_runner.spawn_delegate_session(
                    build_args, self.tmp, "manifest", self._register)
            # the error path already kill_group()'d and clear()'d; only the
            # transport still needs closing, and only this loop can do it
            for proc in _RecordingRuntime.procs:
                await _reap(proc)
            return str(caught.exception)

        try:
            detail = asyncio.run(go())
        finally:
            session_runtime.SessionRuntime = original
        # kill_group() ran on the failure path: the child is not still up
        self.assertEqual(len(_RecordingRuntime.procs), 1)
        self.assertIsNotNone(_RecordingRuntime.procs[0].returncode)
        self.assertIn("failed to boot", detail)
        # Nothing half-born: no registry entry, no delegate to kill later, no
        # observer bookkeeping for a session that never existed.
        self.assertEqual(self.registered, [])
        self.assertEqual(
            [k for k in shadow_runner.DELEGATES if k and "dead" in str(k)], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
