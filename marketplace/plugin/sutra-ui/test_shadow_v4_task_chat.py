"""Shadow v4 step 8 (C1, ADR-043): one Shadow chat per task.

shadow_task_chat.TaskChat is the second of the two AIs: it boots with the
Shadow persona plus a TASK CONTEXT block, carries no Shadow tools, talks to
the founder about its task, writes the worker's brief, and decides the next
instruction in its own conversation. route_decision hands the engine's turn
to that chat when it is alive and to the one-shot decider otherwise, so the
pre-v4 path stays byte-identical as the fallback.

Faked at the process boundary only (FakeRuntime = a scripted claude), never
at the engine or the store.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_task_chat.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-taskchat-")

import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_ledger                           # noqa: E402
import shadow_runner                           # noqa: E402
import shadow_task_chat as stc                 # noqa: E402
from mission_engine import MissionStore        # noqa: E402


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeRuntime:
    """A scripted claude: one reply per turn, in order; announces its id."""

    def __init__(self, replies, sid="tc-fake-1"):
        self.replies = list(replies)
        self.sid = sid
        self.sent = []
        self.spawned = None
        self.alive = False
        self.killed = False

    async def spawn(self, args, cwd, key, env=None):
        self.spawned = {"args": list(args), "cwd": cwd, "key": key, "env": env}
        self.alive = True

    async def send_user_frame(self, text):
        self.sent.append(text)

    async def demux_turn(self, collect, sid):
        await collect({"type": "session", "id": self.sid})
        await collect({"type": "token",
                       "text": self.replies.pop(0) if self.replies else ""})
        return (self.sid, 0.0, True, None, None)

    def kill_group(self):
        self.alive = False
        self.killed = True

    def clear(self):
        pass


def build_args(session_id=None):
    args = ["claude", "-p", "--input-format", "stream-json"]
    if session_id:
        args += ["--resume", session_id]
    return args


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        stc.TASK_CHATS.clear()
        self.store = MissionStore()
        m = self.store.create("Top 10 fruits in the market", "research",
                              target_mode="new",
                              done_when=[{"tier": "founder_confirm",
                                          "check": "a table by usage"}])
        self.mission = self.store.load(m["id"])
        self.published = []

    def tearDown(self):
        stc.TASK_CHATS.clear()
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def chat(self, replies, sid="tc-fake-1"):
        rt = FakeRuntime(replies, sid=sid)
        c = stc.TaskChat(self.mission["id"], new_runtime=lambda: rt)
        return c, rt

    def start(self, c, env=None, register=None):
        return run(c.start(build_args, "/tmp/shadow-home", self.mission,
                           register=register,
                           publish=lambda sid: self.published.append(sid) or "chat-1",
                           env=env))


class TestBoot(Base):

    def test_01_boot_carries_persona_standing_context_and_task_context(self):
        c, rt = self.chat(["READY"])
        sid = self.start(c)
        self.assertEqual(sid, "tc-fake-1")
        boot = rt.sent[0]
        self.assertTrue(boot.startswith("[Shadow boot]"))
        self.assertIn("You are Shadow", boot, "SHADOW.md persona")
        self.assertIn("TASK CONTEXT", boot)
        self.assertIn("Top 10 fruits in the market", boot)
        self.assertIn("a table by usage", boot)
        self.assertIn("never propose a second task", boot)

    def test_02_boot_never_carries_shadow_tools(self):
        c, rt = self.chat(["READY"])
        self.start(c, env={"SUTRA_MCP_SHADOW": "1", "OTHER": "x"})
        self.assertNotIn("SUTRA_MCP_SHADOW", rt.spawned["env"] or {})
        self.assertEqual((rt.spawned["env"] or {}).get("OTHER"), "x")

    def test_03_boot_registers_publishes_and_ledgers(self):
        seen = []
        c, rt = self.chat(["READY"])
        self.start(c, register=lambda sid, r: seen.append((sid, r)))
        self.assertEqual(seen, [("tc-fake-1", rt)])
        self.assertEqual(self.published, ["tc-fake-1"], "published once")
        self.assertEqual(c.sutra_id, "chat-1")
        self.assertIs(stc.get(self.mission["id"]), c)
        self.assertTrue(c.alive)
        acts = shadow_ledger.read("actions", 10)
        self.assertTrue(any("task chat tc-fake-1 spawned" in a["summary"]
                            for a in acts))

    def test_04_boot_refuses_with_the_flag_off(self):
        Path(providers.SETTINGS_PATH).write_text(
            json.dumps({"shadow.enabled": False}))
        c, rt = self.chat(["READY"])
        with self.assertRaises(RuntimeError):
            self.start(c)
        self.assertIsNone(stc.get(self.mission["id"]))

    def test_05_behaves_text_rides_the_boot(self):
        mission_engine.set_behaves("Check in every 3 turns.")
        c, rt = self.chat(["READY"])
        self.start(c)
        self.assertIn("HOW SHADOW BEHAVES", rt.sent[0])
        self.assertIn("Check in every 3 turns.", rt.sent[0])


class TestTurns(Base):

    def test_10_talk_parses_a_mission_fence_like_the_now_chat(self):
        fence = "```mission\n" + json.dumps({
            "objective": "Top 10 fruits, by usage", "template": "research",
            "target_mode": "new"}) + "\n```"
        c, rt = self.chat(["READY", "Sharper.\n" + fence])
        self.start(c)
        display, blocks = run(c.talk("make it about usage"))
        self.assertEqual(display, "Sharper.")
        self.assertEqual(blocks["mission"]["objective"],
                         "Top 10 fruits, by usage")
        self.assertEqual(rt.sent[1], "make it about usage")

    def test_11_brief_returns_the_fence_and_the_prompt_carries_the_facts(self):
        c, rt = self.chat(["READY",
                           "Here.\n```brief\nObjective: \"Top 10 fruits in "
                           "the market\". Repo: ~/Claude/x.\n```"])
        self.start(c)
        text = run(c.brief(self.mission, {
            "repo": "~/Claude/x",
            "rules": ["always answer in one line"],
            "floors": ["destructive git operations"]}))
        self.assertTrue(text.startswith("Objective:"))
        ask = rt.sent[1]
        self.assertIn("~/Claude/x", ask)
        self.assertIn("always answer in one line", ask)
        self.assertIn("destructive git operations", ask)
        self.assertIn("verbatim", ask)

    def test_12_brief_without_a_fence_is_empty_so_the_template_wins(self):
        c, rt = self.chat(["READY", "I would rather not."])
        self.start(c)
        self.assertEqual(run(c.brief(self.mission, {})), "")

    def test_13_decide_sends_the_steering_prompt_and_returns_the_json(self):
        reply = ('```json\n{"action": "continue", "instruction": "list the '
                 'fruits by usage", "reason": "next step"}\n```')
        c, rt = self.chat(["READY", reply])
        self.start(c)
        ctx = {"mission_id": self.mission["id"], "outcome": "Top 10 fruits",
               "checks": [{"tier": "founder_confirm",
                           "check": "a table by usage", "met": False}],
               "turns_used": 1, "max_turns": 12,
               "last_instruction": "start", "last_response": "which fruits?"}
        d = run(c.decide(ctx))
        self.assertEqual(d["action"], "continue")
        self.assertEqual(d["instruction"], "list the fruits by usage")
        prompt = rt.sent[1]
        self.assertEqual(prompt, shadow_runner.render_decide_prompt(ctx))
        self.assertIn("which fruits?", prompt)
        self.assertIn("#0 [ ] (founder_confirm) a table by usage", prompt)

    def test_14_turns_on_a_dead_chat_raise(self):
        c, rt = self.chat(["READY"])
        self.start(c)
        c.stop()
        self.assertTrue(rt.killed)
        self.assertIsNone(stc.get(self.mission["id"]))
        with self.assertRaises(RuntimeError):
            run(c.talk("hello"))


class TestResume(Base):

    def test_20_resume_spawns_with_the_recorded_session_id(self):
        c, rt = self.chat(["READY"])
        self.start(c)
        c.stop()
        rt2 = FakeRuntime([], sid="tc-fake-1")
        c._new_runtime = lambda: rt2
        sid = run(c.resume(build_args, "/tmp/shadow-home"))
        self.assertEqual(sid, "tc-fake-1")
        self.assertIn("--resume", rt2.spawned["args"])
        self.assertIn("tc-fake-1", rt2.spawned["args"])
        self.assertEqual(len(rt2.sent), 0, "nothing is said on resume")
        self.assertTrue(c.alive)
        self.assertIs(stc.get(self.mission["id"]), c)

    def test_21_resume_without_a_session_refuses(self):
        c = stc.TaskChat(self.mission["id"], new_runtime=lambda: FakeRuntime([]))
        with self.assertRaises(RuntimeError):
            run(c.resume(build_args, "/tmp/shadow-home"))


class TestRouting(Base):

    def decision(self, text):
        return ('```json\n{"action": "continue", "instruction": "%s", '
                '"reason": "r"}\n```' % text)

    def test_30_a_live_task_chat_decides(self):
        c, rt = self.chat(["READY", self.decision("from the chat")])
        self.start(c)
        calls = []

        async def fallback(ctx):
            calls.append(ctx)
            return {"action": "continue", "instruction": "from the one-shot",
                    "reason": "r"}

        ctx = {"mission_id": self.mission["id"], "outcome": "x",
               "checks": [], "turns_used": 1, "max_turns": 12}
        d = run(stc.route_decision(ctx, fallback))
        self.assertEqual(d["instruction"], "from the chat")
        self.assertEqual(calls, [], "the one-shot was not consulted")

    def test_31_no_task_chat_means_the_one_shot(self):
        async def fallback(ctx):
            return {"action": "continue", "instruction": "from the one-shot",
                    "reason": "r"}

        ctx = {"mission_id": "m-nobody", "outcome": "x", "checks": []}
        d = run(stc.route_decision(ctx, fallback))
        self.assertEqual(d["instruction"], "from the one-shot")

    def test_32_a_dead_task_chat_falls_back(self):
        c, rt = self.chat(["READY"])
        self.start(c)
        c.stop()

        async def fallback(ctx):
            return {"action": "continue", "instruction": "from the one-shot",
                    "reason": "r"}

        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        d = run(stc.route_decision(ctx, fallback))
        self.assertEqual(d["instruction"], "from the one-shot")

    def test_33_a_chat_that_fails_mid_turn_falls_back_and_is_ledgered(self):
        c, rt = self.chat(["READY"])
        self.start(c)

        async def boom(*a, **k):
            raise RuntimeError("stream broke")
        rt.demux_turn = boom

        async def fallback(ctx):
            return {"action": "continue", "instruction": "from the one-shot",
                    "reason": "r"}

        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        d = run(stc.route_decision(ctx, fallback))
        self.assertEqual(d["instruction"], "from the one-shot")
        acts = shadow_ledger.read("actions", 10)
        self.assertTrue(any("fallback to the one-shot" in a["summary"]
                            for a in acts), acts)

    def test_34_a_chat_with_no_decision_falls_back(self):
        c, rt = self.chat(["READY", "I have no idea."])
        self.start(c)

        async def fallback(ctx):
            return {"action": "ask_founder", "reason": "one-shot asks"}

        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        d = run(stc.route_decision(ctx, fallback))
        self.assertEqual(d["action"], "ask_founder")


class TestEngineContext(Base):

    def test_40_decision_context_names_the_mission(self):
        async def sayer(m, t):
            return True

        async def waiter(m, **k):
            return True

        eng = mission_engine.MissionEngine(self.store, sayer, waiter,
                                           lambda m: "")
        ctx = eng._decision_context(self.mission, "worker said")
        self.assertEqual(ctx["mission_id"], self.mission["id"])
        self.assertEqual(ctx["outcome"], "Top 10 fruits in the market")


if __name__ == "__main__":
    unittest.main(verbosity=2)
