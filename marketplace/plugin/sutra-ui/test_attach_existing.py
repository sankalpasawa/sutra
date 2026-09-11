"""Phase 2: Shadow attaches to an EXISTING founder chat -- D1-D16.

The capability is small. The regression surface is not, which is why this
file is mostly about what must NOT change.

ESTABLISHED BY LIVE EXPERIMENT, not assumed (claude 2.1.268, 2026-09-11,
three runs against a throwaway session in a temp cwd):

  EXP 1  `--resume <sid>` from the session's own cwd -> exit 0, the SAME
         session id in every frame, no new .jsonl, one `sessionId` inside
         the file, both user turns in order.
  EXP 2  the same resume from the WRONG cwd -> also exit 0 on this version,
         appending to the ORIGINAL transcript. Not relied on: the session's
         own cwd is used regardless, because the wrong one hands the
         runtime the wrong project, memory path and tool scope.
  EXP 3  `--resume <unknown id>` -> exit 1, no `system/init` frame, stderr
         "No conversation found with session ID: ...". Hence the on-disk
         check before anything is spawned.

Every test below is named for the invariant it defends, so a failure says
which promise broke rather than which line moved.
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
import session_reader
import session_runtime
import shadow_runner
from mission_engine import MissionStore

SID = "aaaaaaaa-1111-4222-8333-444444444444"     # a founder-owned chat
OTHER = "bbbbbbbb-1111-4222-8333-444444444444"

#: A loop that SURVIVES its neighbours. Several suites in this repo call
#: asyncio.run(), which closes the loop and leaves none current -- so on 3.9
#: the next asyncio.get_event_loop() raises "There is no current event loop"
#: and whether these tests pass depends on file ORDER rather than on
#: behaviour. Own one loop, keep it current, never hand back a closed one.
_LOOP = None


def _ensure_loop():
    """Make our loop the current one. Called from setUp as well as run():
    FakeRt builds an asyncio.Event(), and on 3.9 that reads the CURRENT
    loop -- so a neighbour's asyncio.run() having closed it is enough to
    break construction before a single await happens."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_LOOP)
    return _LOOP


def run(coro):
    return _ensure_loop().run_until_complete(coro)




class FakeRt:
    """A SessionRuntime stand-in: only what these paths actually touch."""

    def __init__(self, alive=True):
        self._alive = alive
        self.killed = False
        self.cleared = False
        self.subscribers = []
        self.spawned = None
        self.queue_event = asyncio.Event()
        self.turn_queue = None

    @property
    def alive(self):
        return self._alive and not self.killed

    async def spawn(self, args, cwd, key, env=None):
        self.spawned = {"args": list(args), "cwd": cwd, "env": env}
        return object()

    def subscribe(self, cb):
        self.subscribers.append(cb)

    def kill_group(self):
        self.killed = True

    def clear(self):
        self.cleared = True


class Base(unittest.TestCase):
    def setUp(self):
        _ensure_loop()
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig_settings = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings

        # a real cwd for the target session, and a transcript on disk
        self.cwd = Path(self.tmp.name) / "project"
        self.cwd.mkdir()
        self._orig_resolve = session_reader.resolve_path
        self._orig_head = session_reader.head_meta
        session_reader.resolve_path = lambda sid: (
            Path(self.tmp.name) / (sid + ".jsonl") if sid == SID else None)
        session_reader.head_meta = lambda sid: (
            {"title": "Goa vs Pondicherry", "cwd": str(self.cwd)}
            if sid == SID else {"title": "", "cwd": ""})

        self.registered = []
        self.spawned_rts = []
        self._orig_pump = shadow_runner.start_pump
        shadow_runner.start_pump = lambda rt, sid: self.spawned_rts.append(
            (sid, rt))
        self._orig_SR = session_runtime.SessionRuntime
        session_runtime.SessionRuntime = lambda: FakeRt()

        session_runtime.RUNTIMES.clear()
        shadow_runner.ATTACHED.clear()
        shadow_runner.DELEGATES.clear()
        shadow_runner._OBSERVED.clear()
        shadow_runner._BOUNDARIES.clear()
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig_settings
        session_reader.resolve_path = self._orig_resolve
        session_reader.head_meta = self._orig_head
        shadow_runner.start_pump = self._orig_pump
        session_runtime.SessionRuntime = self._orig_SR
        session_runtime.RUNTIMES.clear()
        shadow_runner.ATTACHED.clear()
        shadow_runner.DELEGATES.clear()
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # the argv builder the app passes in, minus fastapi/provider resolution
    def build_args(self, sid):
        return ["/bin/claude", "--input-format", "stream-json",
                "--output-format", "stream-json", "--verbose",
                "--permission-mode", "plan", "--resume", sid]

    def attach(self, sid=SID):
        return run(
            shadow_runner.ensure_runtime(
                sid, self.build_args,
                lambda s, rt: (self.registered.append((s, rt)),
                               session_runtime.register_runtime(s, rt))))


# ---------------------------------------------------------------- D1, D2 --
class TestTheFounderAlwaysWins(Base):

    def test_D1_a_live_runtime_is_returned_untouched(self):
        """INVARIANT 1. No spawn, no re-register, no second observer."""
        pane = FakeRt()
        session_runtime.register_runtime(SID, pane)
        shadow_runner.attach_observer(SID, pane)
        before = len(pane.subscribers)

        got = self.attach()

        self.assertIs(got, pane, "the founder's own runtime, not a new one")
        self.assertIsNone(pane.spawned, "nothing was spawned over it")
        self.assertEqual(self.registered, [], "and nothing was re-registered")
        self.assertEqual(len(pane.subscribers), before, "no second observer")
        self.assertNotIn(SID, shadow_runner.ATTACHED,
                         "a pane Shadow did not spawn is not Shadow's to reap")
        self.assertFalse(pane.killed)

    def test_D1b_a_dead_registered_runtime_does_not_win(self):
        dead = FakeRt(alive=False)
        session_runtime.register_runtime(SID, dead)
        got = self.attach()
        self.assertIsNot(got, dead, "a corpse must not be handed to the say")
        self.assertIs(shadow_runner.ATTACHED[SID], got)

    def test_D2_a_pane_arriving_reaps_shadows_attached_runtime(self):
        """INVARIANT 12: exactly one live runtime per session survives."""
        mine = self.attach()
        self.assertTrue(mine.alive)

        pane = FakeRt()                       # the founder opens the chat
        session_runtime.register_runtime(SID, pane)   # ws_chat order: register
        shadow_runner.attach_observer(SID, pane)      # ...then observe

        self.assertTrue(mine.killed, "Shadow's process stepped aside")
        self.assertNotIn(SID, shadow_runner.ATTACHED)
        self.assertIs(session_runtime.lookup_runtime(SID), pane,
                      "and the founder's entry was NOT evicted")
        self.assertFalse(pane.killed)

    def test_D2b_reap_is_idempotent_and_a_noop_for_unattached(self):
        self.assertIsNone(shadow_runner.reap_attached("never-attached"))
        self.attach()
        self.assertIsNotNone(shadow_runner.reap_attached(SID))
        self.assertIsNone(shadow_runner.reap_attached(SID))

    def test_D2c_reapping_does_not_evict_a_pane_that_took_the_key(self):
        mine = self.attach()
        pane = FakeRt()
        session_runtime.register_runtime(SID, pane)   # pane owns the key now
        shadow_runner.reap_attached(SID)
        self.assertTrue(mine.killed)
        self.assertIs(session_runtime.lookup_runtime(SID), pane,
                      "unregister_runtime's identity guard still holds")


# ------------------------------------------------------------ D3, D4, D13 --
class TestTeardown(Base):

    def test_D3_terminal_teardown_kills_a_delegate_not_an_attachment(self):
        """INVARIANT 2. The founder's chat outlives every mission."""
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        i = src.index('if m and m["state"] in mission_engine.TERMINAL:')
        branch = src[i:i + 700]
        self.assertIn("DELEGATES.pop(", branch)
        self.assertNotIn("ATTACHED.pop(", branch,
                         "an attached founder chat is never reaped by a "
                         "finishing mission")
        self.assertNotIn("ATTACHED[", branch)
        self.assertNotIn("reap_attached", branch)

    def test_D4_the_blocked_branch_reaps_nothing(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        i = src.index('elif m and m["state"] == "blocked":')
        branch = src[i:i + 900]
        self.assertNotIn("kill_group", branch)
        self.assertNotIn("ATTACHED.pop", branch)

    def test_D13_an_attached_chat_is_never_filed_as_a_delegate(self):
        """INVARIANT 13/14: DELEGATES membership silences auto-watch."""
        self.attach()
        self.assertIn(SID, shadow_runner.ATTACHED)
        self.assertNotIn(SID, shadow_runner.DELEGATES,
                         "app._shadow_auto_watch skips DELEGATES -- filing an "
                         "attached chat there would unwatch the founder's own "
                         "conversation")


# ----------------------------------------------------------------- D5, D6 --
class TestNothingElseMoved(Base):

    def test_D5_the_delegate_spawn_path_is_unchanged(self):
        """INVARIANT 3. Same order, same registry effects, same cleanup."""
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        i = src.index("async def spawn_delegate_session")
        body = src[i:src.index("\ndef ", i + 10)]
        for step in ["srt.SessionRuntime()", "await rt.spawn(",
                     "await rt.send_user_frame(manifest)",
                     "await rt.demux_turn(", "register(sid, rt)",
                     "attach_observer(sid, rt)", "DELEGATES[sid] = rt",
                     "start_pump(rt, sid)"]:
            self.assertIn(step, body, step)
        order = [body.index(s) for s in
                 ["await rt.spawn(", "await rt.send_user_frame(manifest)",
                  "register(sid, rt)", "attach_observer(sid, rt)",
                  "DELEGATES[sid] = rt", "start_pump(rt, sid)"]]
        self.assertEqual(order, sorted(order), "call order is unchanged")
        self.assertIn("delegate session failed to boot", body)
        self.assertIn("rt.kill_group()", body, "boot-failure cleanup kept")
        self.assertNotIn("--resume", body,
                         "a NEW delegate never resumes anything")

    def test_D5b_the_pump_is_one_body_shared_by_both(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        self.assertEqual(src.count("async def _pump("), 1,
                         "extracted once, not copied")
        self.assertEqual(src.count("    start_pump(rt, sid)"), 1,
                         "the delegate path calls it once")
        self.assertIn("    start_pump(rt, session_id)", src,
                      "and the attach path calls the same one")

    def test_D6_ws_chat_was_not_touched(self):
        """INVARIANT 4. The whole point of attaching in Shadow's own module."""
        src = Path(__file__).with_name("app.py").read_text()
        i = src.index("async def ws_chat(")
        body = src[i:src.index('@app.websocket("/ws/term")', i)]
        for gone in ["ensure_runtime", "reap_attached", "ATTACHED"]:
            self.assertNotIn(gone, body, "ws_chat must stay untouched")
        self.assertIn("register_runtime(session_id, rt)", body)
        self.assertIn("shadow_runner.attach_observer(session_id, rt)", body)

    def test_D6b_shadow_args_is_unchanged_when_no_session_is_given(self):
        src = Path(__file__).with_name("app.py").read_text()
        self.assertIn("def _shadow_args(session_id=None):", src)
        self.assertIn('build_agent_args(prov["bin_path"], "", "plan",\n'
                      "                            session_id=session_id, "
                      "stream_input=True)", src)
        # the delegate spawner still calls it with no argument at all
        self.assertIn("_shadow_args, _shadow_workdir_for_delegates()", src)


# ------------------------------------------------------------------- D7 ---
class TestAdmission(Base):

    def test_D7_attach_happens_before_the_attempt_exists(self):
        """INVARIANT 5 + 7: a chat Shadow cannot reach spends nothing."""
        src = Path(__file__).with_name("app.py").read_text()
        i = src.index('if action == "start":')
        arm = src[i:i + 700]
        self.assertLess(arm.index("_ensure_target_runtime"),
                        arm.index("start_first_attempt"),
                        "refuse BEFORE an attempt is created")
        j = src.index('if action == "resume":')
        arm2 = src[j:j + 700]
        self.assertLess(arm2.index("_ensure_target_runtime"),
                        arm2.index("resume_goal"))

    def test_D7b_the_cap_and_queue_are_untouched(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        i = src.index("def start_mission_async")
        j = src.find("\ndef ", i)
        body = src[i:j if j > 0 else len(src)]
        self.assertIn("mission_engine.MAX_RUNNING", body)
        self.assertNotIn("ensure_runtime", body,
                         "admission/queueing logic gained nothing")


# ------------------------------------------------------- D9, D10, D11, D14 --
class TestTheSessionItself(Base):

    def test_D9_no_new_chat_and_no_new_transcript(self):
        """INVARIANT 7 + 9. One audit row is written and nothing else: no
        transcript, no chat record, and no turn in the founder's chat."""
        rt = self.attach()
        created = [p for p in Path(self.tmp.name).rglob("*") if p.is_file()]
        names = [p.name for p in created]
        self.assertNotIn(SID + ".jsonl", names, "no transcript was created")
        self.assertEqual([n for n in names if "chat" in n.lower()], [],
                         "and no chat record")
        # the ONLY thing attaching writes is its audit row
        self.assertEqual(sorted(n for n in names if n.endswith(".jsonl")),
                         ["actions.jsonl"])
        self.assertIsNone(rt.turn_queue,
                          "and sent no turn -- the first say is the mission's")

    def test_D10_the_session_id_is_the_same_string_end_to_end(self):
        """INVARIANT 8, and EXP 1 says the CLI keeps it too."""
        rt = self.attach()
        self.assertEqual(self.registered[0][0], SID)
        self.assertIs(shadow_runner.ATTACHED[SID], rt)
        self.assertIs(session_runtime.lookup_runtime(SID), rt)
        self.assertIn("--resume", rt.spawned["args"])
        k = rt.spawned["args"].index("--resume")
        self.assertEqual(rt.spawned["args"][k + 1], SID,
                         "resumed by the very id the mission targets")

    def test_D11_it_resumes_in_the_sessions_own_cwd(self):
        rt = self.attach()
        self.assertEqual(rt.spawned["cwd"], str(self.cwd),
                         "head_meta's cwd, never the delegate workdir")

    def test_D14_a_dead_id_is_refused_before_anything_is_spawned(self):
        """INVARIANT 15 + EXP 3. No resume-free fallback, ever."""
        with self.assertRaises(session_runtime.NoLiveRuntime):
            self.attach(OTHER)                 # resolve_path -> None
        self.assertEqual(self.spawned_rts, [], "nothing was spawned")
        self.assertNotIn(OTHER, shadow_runner.ATTACHED)
        self.assertIsNone(session_runtime.lookup_runtime(OTHER))

    def test_D14b_an_unknown_cwd_is_refused_too(self):
        session_reader.head_meta = lambda sid: {"title": "x", "cwd": ""}
        with self.assertRaises(session_runtime.NoLiveRuntime):
            self.attach()
        self.assertEqual(self.spawned_rts, [], "never guess a project")

    def test_D14c_a_vanished_cwd_is_refused(self):
        session_reader.head_meta = lambda sid: {
            "title": "x", "cwd": str(self.cwd / "gone")}
        with self.assertRaises(session_runtime.NoLiveRuntime):
            self.attach()

    def test_D14d_an_empty_session_id_is_refused(self):
        for bad in ("", None):
            with self.assertRaises(session_runtime.NoLiveRuntime):
                self.attach(bad)

    def test_D14e_there_is_no_resume_free_spawn_anywhere_in_attach(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        i = src.index("async def ensure_runtime")
        # bounded at the NEXT def, not at reap_attached: settle_confirmation
        # was later inserted between the two, and it legitimately reads
        # evidence_text. This assertion is about ensure_runtime alone.
        body = src[i:src.index("\ndef ", i)]
        self.assertIn("build_args(session_id)", body)
        self.assertEqual(body.count("rt.spawn("), 1, "exactly one spawn")
        self.assertNotIn("send_user_frame", body,
                         "attaching must not put a turn in the chat")


# ------------------------------------------------------------------ D12 ---
class TestFounderTakeover(Base):
    """New coverage: founder_takeover had NO tests before this change."""

    def _running(self, sid=SID):
        m = self.store.create(objective="o", template="fix",
                              target_mode="existing", target_session=sid)
        self.store.transition(m["id"], "brief_confirm", "b")
        return self.store.transition(m["id"], "running", "admitted")

    def test_D12_a_founder_turn_still_pauses_the_running_mission(self):
        m = self._running()
        hit = shadow_runner.founder_takeover(SID)
        self.assertIsNotNone(hit)
        after = self.store.load(m["id"])
        self.assertEqual(after["state"], "paused")
        self.assertEqual(after["pause_reason"], "founder_intervened")

    def test_D12b_takeover_reaps_shadows_attached_runtime(self):
        mine = self.attach()
        self._running()
        shadow_runner.founder_takeover(SID)
        self.assertTrue(mine.killed, "reap-on-takeover (founder decision)")
        self.assertNotIn(SID, shadow_runner.ATTACHED)

    def test_D12c_takeover_never_touches_a_delegate(self):
        drt = FakeRt()
        shadow_runner.DELEGATES[SID] = drt
        self._running()
        shadow_runner.founder_takeover(SID)
        self.assertFalse(drt.killed, "delegates are reaped by teardown only")

    def test_D12d_takeover_on_an_unattached_chat_is_harmless(self):
        self.assertIsNone(shadow_runner.founder_takeover("no-such-session"))

    def test_D12e_a_mission_on_another_session_is_not_paused(self):
        m = self._running(OTHER)
        shadow_runner.founder_takeover(SID)
        self.assertEqual(self.store.load(m["id"])["state"], "running")


# ------------------------------------------------------------- D8, D15, D16 --
class TestIntegrityAndHygiene(Base):

    def test_D8_evidence_assembly_is_untouched_by_attaching(self):
        """INVARIANT 6: attach adds no evidence source and no say path."""
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        i = src.index("async def ensure_runtime")
        # bounded at the NEXT def, not at reap_attached: settle_confirmation
        # was later inserted between the two, and it legitimately reads
        # evidence_text. This assertion is about ensure_runtime alone.
        body = src[i:src.index("\ndef ", i)]
        for forbidden in ["evidence_text", "evidence_messages", "_RECENT_TEXT",
                          "done_when", "say_tag"]:
            self.assertNotIn(forbidden, body, forbidden)
        # and the say chain still has exactly one writer of the tag
        app = Path(__file__).with_name("app.py").read_text()
        self.assertEqual(app.count("shadow_egress.say_tag("), 2,
                         "_validated_say and _delegate_manifest, as before")

    def test_D15_the_registry_guard_still_holds(self):
        a, b = FakeRt(), FakeRt()
        session_runtime.register_runtime(SID, a)
        session_runtime.register_runtime(SID, b)
        session_runtime.unregister_runtime(SID, a)      # the loser
        self.assertIs(session_runtime.lookup_runtime(SID), b)
        session_runtime.unregister_runtime(SID, b)
        self.assertIsNone(session_runtime.lookup_runtime(SID))

    def test_D16_no_css_or_ui_surface_was_touched(self):
        """INVARIANT 10 + 11."""
        here = Path(__file__).parent
        css = (here / "static" / "panel.css").read_text()
        self.assertNotIn("attach", css.lower().split("slice 11")[-1][:4000])
        js = (here / "static" / "js" / "18-goal-workspace.js").read_text()
        self.assertNotIn("ensure_runtime", js)
        self.assertNotIn("ATTACHED", js)

    def test_D16b_the_attachment_is_ledgered(self):
        import shadow_ledger
        self.attach()
        shadow_runner.reap_attached(SID)
        rows = [json.loads(l) for l in
                open(shadow_ledger._path("actions"), encoding="utf-8")]
        kinds = [r["summary"] for r in rows]
        self.assertTrue(any("attached to existing session" in k for k in kinds))
        self.assertTrue(any("released attached session" in k for k in kinds))


if __name__ == "__main__":
    unittest.main()
