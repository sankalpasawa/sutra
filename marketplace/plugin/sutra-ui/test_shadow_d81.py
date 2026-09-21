"""D81 (founder, 2026-09-21): nothing in the background, two chats per task.

"I don't want anything to be in the background of the conversations with the
app. All the conversations with the app should happen in the Sutra chat UI
and should be shown there." And on where the judge speaks: "either it should
happen in Shadow Chat or it should happen in Worker Chat."

What this lane pins:
  - route_decision has NO fallback: a dead task chat is REVIVED through the
    injected `revive` (app._ensure_task_chat) and asked again; when nothing
    can bring it back the turn is undecided (None) and the ledger says so.
    Never a substitute process.
  - the judge is a turn in the task's own Shadow chat (TaskChat.judge ->
    shadow_judge prompt in, shadow_judge verdict out), routed by mission id
    (route_judgement); the engine offers the mission id to a judge that
    takes it and calls the classic three-argument judge exactly as before.
  - app.py binds neither make_decider nor make_judge any more.

Faked at the process boundary only (the scripted claude of
test_shadow_v4_task_chat), never at the engine or the store.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_d81.py
"""
import asyncio
import inspect
import tempfile
import unittest
from pathlib import Path

from test_shadow_v4_task_chat import (   # noqa: E402 -- the shared fakes
    Base, FakeRuntime, build_args, run)

import mission_engine                    # noqa: E402
import shadow_judge                      # noqa: E402
import shadow_ledger                     # noqa: E402
import shadow_task_chat as stc           # noqa: E402


def decision(text):
    return ('```json\n{"action": "continue", "instruction": "%s", '
            '"reason": "r"}\n```' % text)


VERDICT = '```json\n{"verdict": "met", "reason": "hunk 3 does it"}\n```'


def ledger_summaries():
    return [a.get("summary", "") for a in shadow_ledger.read("actions", 20)]


class TestRoutingHasNoFallback(Base):

    def test_01_a_live_task_chat_decides_and_revive_is_not_called(self):
        c, rt = self.chat(["READY", decision("from the chat")])
        self.start(c)
        calls = []

        async def revive(mid):
            calls.append(mid)
            return c

        ctx = {"mission_id": self.mission["id"], "outcome": "x",
               "checks": [], "turns_used": 1, "max_turns": 12}
        d = run(stc.route_decision(ctx, revive=revive))
        self.assertEqual(d["instruction"], "from the chat")
        self.assertEqual(calls, [], "a live chat needs no revival")

    def test_02_a_dead_task_chat_is_REVIVED_and_decides(self):
        c, rt = self.chat(["READY"])
        self.start(c)
        c.stop()
        calls = []
        c2, rt2 = self.chat(["READY", decision("from the revived chat")],
                            sid="tc-fake-2")

        async def revive(mid):
            calls.append(mid)
            # inside the router's own loop, so start it here, not via run()
            await c2.start(build_args, "/tmp/shadow-home", self.mission,
                           publish=lambda sid: "chat-2")
            return c2

        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        d = run(stc.route_decision(ctx, revive=revive))
        self.assertEqual(d["instruction"], "from the revived chat")
        self.assertEqual(calls, [self.mission["id"]], "revived exactly once")
        self.assertTrue(any("task chat revived" in s for s in ledger_summaries()),
                        ledger_summaries())

    def test_03_no_chat_and_no_revive_is_UNDECIDED_not_a_one_shot(self):
        ctx = {"mission_id": "m-nobody", "outcome": "x", "checks": []}
        d = run(stc.route_decision(ctx))
        self.assertIsNone(d)
        self.assertTrue(any("undecided" in s for s in ledger_summaries()),
                        ledger_summaries())

    def test_04_a_revive_that_raises_leaves_the_turn_undecided(self):
        async def revive(mid):
            raise RuntimeError("no session to resume")

        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        d = run(stc.route_decision(ctx, revive=revive))
        self.assertIsNone(d)
        self.assertTrue(any("could not be revived" in s
                            for s in ledger_summaries()), ledger_summaries())

    def test_05_a_revive_that_returns_a_dead_chat_is_undecided(self):
        c, rt = self.chat(["READY"])

        async def revive(mid):
            return c                    # never started: not alive

        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        self.assertIsNone(run(stc.route_decision(ctx, revive=revive)))
        self.assertTrue(any("did not come back alive" in s
                            for s in ledger_summaries()), ledger_summaries())

    def test_06_a_chat_with_no_decision_is_undecided_not_answered_elsewhere(self):
        c, rt = self.chat(["READY", "I have no idea."])
        self.start(c)
        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        self.assertIsNone(run(stc.route_decision(ctx)))
        self.assertTrue(any("returned no decision" in s
                            for s in ledger_summaries()), ledger_summaries())

    def test_07_a_chat_that_fails_mid_turn_is_undecided_and_ledgered(self):
        c, rt = self.chat(["READY"])
        self.start(c)

        async def boom(*a, **k):
            raise RuntimeError("stream broke")
        rt.demux_turn = boom
        ctx = {"mission_id": self.mission["id"], "outcome": "x", "checks": []}
        self.assertIsNone(run(stc.route_decision(ctx)))
        self.assertTrue(any("turn failed" in s for s in ledger_summaries()),
                        ledger_summaries())

    def test_08_the_router_has_no_fallback_parameter_at_all(self):
        params = inspect.signature(stc.route_decision).parameters
        self.assertNotIn("fallback", params)
        self.assertIn("revive", params)
        self.assertNotIn("fallback", inspect.getsource(stc.route_decision)
                         .split('"""')[-1],
                         "the body names no fallback either")


class TestJudgeInTheTaskChat(Base):

    def test_10_judge_is_a_turn_in_THIS_conversation(self):
        c, rt = self.chat(["READY", VERDICT])
        self.start(c)
        v = run(c.judge("the table has 10 rows", "--- diff ---\n+10 rows",
                        "Top 10 fruits"))
        self.assertEqual(v.state, "met")
        self.assertIn("hunk 3", v.reason)
        sent = rt.sent[1]
        self.assertTrue(sent.startswith("You are settling ONE completion "
                                        "check by reading evidence."), sent)
        self.assertIn("the table has 10 rows", sent)
        self.assertIn("+10 rows", sent, "the evidence, as text")
        self.assertIn("Top 10 fruits", sent)
        self.assertEqual(rt.sid, c.session_id, "the SAME session, no spawn")

    def test_11_a_reply_that_is_not_a_verdict_is_None(self):
        c, rt = self.chat(["READY", "Looks fine to me."])
        self.start(c)
        self.assertIsNone(run(c.judge("c", "e", "o")))

    def test_12_route_judgement_finds_the_chat_by_mission_id(self):
        c, rt = self.chat(["READY", VERDICT])
        self.start(c)
        v = run(stc.route_judgement("c", "e", "o",
                                    mission_id=self.mission["id"]))
        self.assertEqual(v.state, "met")

    def test_13_route_judgement_with_no_chat_says_nothing(self):
        self.assertIsNone(run(stc.route_judgement("c", "e", "o",
                                                  mission_id="m-nobody")))
        self.assertTrue(any("judgement is undecided" in s
                            for s in ledger_summaries()), ledger_summaries())

    def test_14_route_judgement_revives_a_dead_chat(self):
        c, rt = self.chat(["READY", VERDICT], sid="tc-fake-3")

        async def revive(mid):
            await c.start(build_args, "/tmp/shadow-home", self.mission,
                          publish=lambda sid: "chat-3")
            return c

        v = run(stc.route_judgement("c", "e", "o",
                                    mission_id=self.mission["id"],
                                    revive=revive))
        self.assertEqual(v.state, "met")


class TestEngineOffersTheMissionId(unittest.TestCase):

    def run_judges(self, judge, checks):
        loop = mission_engine.MissionEngine.__new__(mission_engine.MissionEngine)
        loop.judge = judge
        loop.probe_root = tempfile.mkdtemp()
        loop._save_field = lambda m, k, v, skip_if=None: None
        loop._judge_evidence = lambda m: "the evidence"
        m = {"id": "m-1", "objective": "o", "done_when": checks}
        loop_ = asyncio.new_event_loop()
        try:
            loop_.run_until_complete(loop._run_judges(m))
        finally:
            loop_.close()
        return m["done_when"]

    def test_20_a_judge_that_takes_mission_id_gets_it(self):
        seen = []

        async def judge(check, evidence, outcome, mission_id=None):
            seen.append(mission_id)
            return shadow_judge.Verdict("met", "r")
        rows = self.run_judges(judge, [{"tier": "judge", "check": "c"}])
        self.assertEqual(seen, ["m-1"])
        self.assertTrue(rows[0]["met"])

    def test_21_the_classic_three_argument_judge_is_called_as_before(self):
        seen = []

        async def judge(check, evidence, outcome):
            seen.append((check, evidence, outcome))
            return shadow_judge.Verdict("unmet", "no")
        rows = self.run_judges(judge, [{"tier": "judge", "check": "c"}])
        self.assertEqual(seen, [("c", "the evidence", "o")])
        self.assertFalse(rows[0]["met"])


class TestAppBindsNoHeadlessProcess(unittest.TestCase):

    def test_30_app_wires_both_lanes_through_the_task_chat(self):
        src = Path(__file__).with_name("app.py").read_text()
        self.assertNotIn("shadow_runner.make_decider(", src,
                         "the one-shot decider is retired from the app (D81)")
        self.assertNotIn("shadow_runner.make_judge(", src,
                         "the headless judge is retired from the app (D81)")
        self.assertIn("shadow_task_chat.route_decision(", src)
        self.assertIn("shadow_task_chat.route_judgement(", src)
        self.assertEqual(2, src.count("revive=_revive_task_chat"),
                         "both lanes revive through the same door")
        self.assertEqual(1, src.count("set_default_decider("))
        self.assertEqual(1, src.count("set_default_judge("))
        self.assertIn("set_default_judge(_routed_judge)", src)

    def test_31_revive_goes_through_ensure_task_chat(self):
        src = Path(__file__).with_name("app.py").read_text()
        body = src[src.index("async def _revive_task_chat"):
                   src.index("async def _routed(context)")]
        self.assertIn("_ensure_task_chat(m)", body,
                      "--resume of the recorded session, else a fresh start")


if __name__ == "__main__":
    unittest.main()
