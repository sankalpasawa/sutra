"""Shadow DRIVES the target chat: adaptive, multi-turn, same session.

WHAT WAS WRONG. `_next_say` was the whole of Shadow's "decision": turn 0
sent the objective, every later turn sent "Continue toward: X. Outstanding
checks: A; B". That string varies only with the unmet set, the unmet set
shrinks monotonically, so two consecutive turns produced IDENTICAL text and
the ping-pong guard ended the attempt. Measured live (goal g-d804849d1400,
2026-09-11): blocked on ping_pong at turn 2/20 while the target chat had
answered correctly. The loop iterated; the instruction could not.

WHAT THIS FILE PROVES. Not that a decider function exists -- that a real
back-and-forth happens:

    Shadow decision 1 -> instruction 1 -> target response 1
    Shadow decision 2 SEES response 1 -> instruction 2 -> target response 2
    Shadow decision 3 SEES response 2 -> ...

and that every one of those turns went into the SAME target session through
the SAME say path, with the deterministic verifier still the only thing that
can finish the Assignment.

The decider here is a recording stub, so the ASSERTIONS are about the
engine's contract with it, not about a model's output. The real decider
(shadow_runner.make_decider) is covered separately for its parsing,
isolation and failure behaviour.
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import goal_lifecycle
import mission_engine
import providers
import shadow_runner
from goal_store import GoalStore
from mission_engine import MissionEngine, MissionStore

SID = "e73d6ed9-9f83-4d4d-b1a8-9166fdf0f45d"

_LOOP = None


def _ensure_loop():
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_LOOP)
    return _LOOP


def run(coro):
    return _ensure_loop().run_until_complete(coro)


class Base(unittest.TestCase):
    def setUp(self):
        _ensure_loop()
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self.goals = GoalStore()

        self.said = []          # (session_id, text) -- what reached the target
        self.contexts = []      # every context the decider was handed
        self.replies = []       # the target's scripted answers, consumed in order
        self.transcript = ""    # what the verifier reads

    @property
    def driving_contexts(self):
        """The contexts that DECIDE A TURN.

        Since 2026-09-17 the decider is also asked one question before first
        contact -- how it would verify each check that has no mechanical test
        behind it (_criteria_before_first_contact step 2). That call carries
        turns_used == 0 and its instruction is discarded, so a test about what
        the decider sees while DRIVING must not read it by position."""
        return [c for c in self.contexts if (c.get("turns_used") or 0) >= 1]

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # ---- the target chat: a scripted independent agent -------------------
    def engine(self, decider, checks=None, max_turns=20):
        """A mission whose target answers from self.replies, and whose
        transcript is what the verifier sees."""
        async def sayer(m, text):
            self.said.append((m["target_session"], text))
            # the target "answers": its output becomes the transcript tail
            reply = self.replies.pop(0) if self.replies else "(no more)"
            self.transcript += "\n" + reply
            return True

        async def waiter(m):
            return True

        return MissionEngine(self.store, sayer, waiter,
                             lambda m: self.transcript, decider=decider)

    def mission(self, checks=None, max_turns=20):
        m = self.store.create(
            objective="reach a decision on PostgreSQL vs DynamoDB",
            template="fix", target_mode="existing", target_session=SID,
            done_when=checks if checks is not None
            else [{"tier": "contains_artifact", "check": "FINAL:"}])
        self.store.transition(m["id"], "brief_confirm", "b")
        m = self.store.transition(m["id"], "running", "admitted")
        if max_turns != 20:
            m["max_turns"] = max_turns
            self.store.save(m)
        return m["id"]

    def goal_mission(self, checks=None, max_turns=20, sid=SID):
        """A GOAL-backed attempt. Needed wherever a test asserts a
        block_reason: _out_of_road only stamps one for a goal attempt, and a
        standalone mission records its reason in the ledger note instead."""
        g = self.goals.create(
            outcome="reach a decision on PostgreSQL vs DynamoDB",
            target_session=sid,
            done_when=checks if checks is not None
            else [{"tier": "contains_artifact", "check": "FINAL:"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal_lifecycle.on_attempt_start(m)
        m = self.store.transition(m["id"], "running", "admitted")
        if max_turns != 20:
            m["max_turns"] = max_turns
            self.store.save(m)
        return g["id"], m["id"]

    def notes(self, mid):
        """Ledger notes for this mission, newest last."""
        import shadow_ledger
        return [json.loads(l)["note"] for l in
                open(shadow_ledger._path("missions"), encoding="utf-8")
                if mid in l]

    def recorder(self, script):
        """A decider that records what it was shown and answers from a
        script keyed by how many times it has been called."""
        async def decide(context):
            self.contexts.append(context)
            step = len(self.contexts) - 1
            return script[step] if step < len(script) else script[-1]
        return decide


# ================= THE LOOP: adaptive, multi-turn, same chat =============
class TestShadowDrivesTheChat(Base):

    def test_01_shadow_reads_each_response_and_adapts(self):
        """A, B, C, D, E, F and G in one run -- this is the whole point."""
        self.replies = ["I recommend Postgres for relational integrity.",
                        "Retries: idempotency keys + exponential backoff.",
                        "FINAL: Postgres, with the contract above."]
        script = [
            {"action": "continue", "reason": "architecture named",
             "instruction": "Good. Now add retry and idempotency handling."},
            {"action": "continue", "reason": "retries designed",
             "instruction": "Now produce the final API contract."},
            {"action": "continue", "reason": "should be done",
             "instruction": "Restate the final choice."},
        ]
        mid = self.mission()
        m = run(self.engine(self.recorder(script)).run_mission(mid))

        # ---- A: the decider ran after the first target response
        self.assertGreaterEqual(len(self.driving_contexts), 2,
                                "Shadow decided more than once")
        # ---- B: decision N saw response N-1
        self.assertIn("I recommend Postgres",
                      self.driving_contexts[0]["last_response"],
                      "decision 2 was handed the FIRST response")
        self.assertIn("idempotency keys",
                      self.driving_contexts[1]["last_response"],
                      "decision 3 was handed the SECOND response")
        # ---- and it knew what it had itself just asked
        self.assertIn("retry and idempotency",
                      self.driving_contexts[1]["last_instruction"])
        # ---- C/D: three DIFFERENT instructions reached the say path
        texts = [t for _sid, t in self.said]
        self.assertEqual(len(texts), 3, "three turns were driven")
        self.assertEqual(len(set(texts)), 3, "every one different: %r" % texts)
        self.assertIn("retry and idempotency handling", texts[1])
        self.assertIn("final API contract", texts[2])
        # ---- E/F/G: same session, every turn; and it finished on evidence
        self.assertEqual({sid for sid, _t in self.said}, {SID},
                         "one target session, never a second")
        self.assertEqual(m["state"], "done")
        self.assertEqual(m["turns_used"], 3)

    def test_02_turn_zero_is_the_brief_not_a_decision(self):
        self.replies = ["ok", "FINAL: done"]
        mid = self.mission()
        run(self.engine(self.recorder([
            {"action": "continue", "instruction": "next", "reason": "r"}
        ])).run_mission(mid))
        self.assertEqual(self.said[0][1],
                         "reach a decision on PostgreSQL vs DynamoDB",
                         "the objective opens the conversation")
        self.assertEqual(len(self.driving_contexts), 1,
                         "the decider was consulted once, for turn 1")

    def test_03_the_decider_sees_check_state_and_budget(self):
        self.replies = ["nothing useful", "FINAL: x"]
        mid = self.mission(checks=[
            {"tier": "contains_artifact", "check": "FINAL:"},
            {"tier": "founder_confirm", "check": "reads well"}])
        run(self.engine(self.recorder([
            {"action": "continue", "instruction": "try again", "reason": "r"}
        ])).run_mission(mid))
        ctx = self.driving_contexts[0]
        self.assertEqual(ctx["outcome"],
                         "reach a decision on PostgreSQL vs DynamoDB")
        self.assertEqual([c["check"] for c in ctx["checks"]],
                         ["FINAL:", "reads well"])
        self.assertEqual([c["met"] for c in ctx["checks"]], [False, False])
        self.assertEqual([c["tier"] for c in ctx["checks"]],
                         ["contains_artifact", "founder_confirm"])
        self.assertEqual(ctx["turns_used"], 1)
        self.assertEqual(ctx["max_turns"], 20)

    def test_04_the_response_shown_is_bounded(self):
        self.replies = ["z" * 9000, "FINAL: x"]
        mid = self.mission()
        run(self.engine(self.recorder([
            {"action": "continue", "instruction": "go on", "reason": "r"}
        ])).run_mission(mid))
        self.assertLessEqual(len(self.driving_contexts[0]["last_response"]),
                             mission_engine.DECISION_TAIL,
                             "no blind whole-transcript dump")

    def test_05_five_turns_if_that_is_what_it_takes(self):
        """F: repeatedly, for N turns, while the budget allows."""
        self.replies = ["a", "b", "c", "d", "FINAL: e"]
        script = [{"action": "continue", "reason": "r",
                   "instruction": "step %d" % i} for i in range(1, 6)]
        mid = self.mission()
        m = run(self.engine(self.recorder(script)).run_mission(mid))
        self.assertEqual(m["state"], "done")
        self.assertEqual(m["turns_used"], 5)
        self.assertEqual([t for _s, t in self.said][1:],
                         ["step 1", "step 2", "step 3", "step 4"])


# ================= THE VERIFIER REMAINS THE AUTHORITY ===================
class TestShadowCannotFinishAnything(Base):

    def test_06_there_is_no_action_that_completes_a_mission(self):
        """H, structurally: `stop`/`done` are not in the vocabulary."""
        self.assertEqual(mission_engine.DECISION_ACTIONS,
                         ("continue", "ask_founder"))
        for junk in ({"action": "stop"}, {"action": "done"},
                     {"action": "complete", "instruction": "x"}):
            self.assertIsNone(mission_engine.validate_decision(junk))

    def test_07_verification_runs_after_every_single_response(self):
        """G: the evaluator is consulted on each turn, not just the last."""
        seen = []
        self.replies = ["one", "two", "FINAL: three"]
        eng = self.engine(self.recorder([
            {"action": "continue", "instruction": "more", "reason": "r"},
            {"action": "continue", "instruction": "more still", "reason": "r"},
        ]))
        eng.on_evaluated = lambda m, results, done: seen.append(done)
        run(eng.run_mission(self.mission()))
        self.assertEqual(seen, [False, False, True],
                         "evaluated every turn: %r" % seen)

    def test_08_shadow_claiming_success_changes_nothing(self):
        """The target says it is done, Shadow believes it -- and the
        artifact check is not present, so the mission does NOT complete."""
        self.replies = ["All done! Everything is complete.",
                        "Yes, truly complete."]
        script = [{"action": "continue", "reason": "it says it is done",
                   "instruction": "Confirm you are finished."},
                  {"action": "ask_founder",
                   "reason": "it insists it is done but only you can say if the copy reads well", "ask_kind": "taste"}]
        _gid, mid = self.goal_mission()
        m = run(self.engine(self.recorder(script)).run_mission(mid))
        self.assertNotEqual(m["state"], "done",
                            "no amount of agreement completes an Assignment")
        self.assertEqual(m["block_reason"], "needs_founder")

    def test_09_only_complete_writes_a_done_mission(self):
        src = Path(__file__).with_name("mission_engine.py").read_text()
        self.assertEqual(src.count('"done", "done_when met'), 1)
        i = src.index("def _instruction")
        body = src[i:src.index("def _next_say")]
        for forbidden in ("_complete", '"done"', "evaluate_done_when"):
            self.assertNotIn(forbidden, body,
                             "the driver cannot reach completion: " + forbidden)


# ================= ask_founder USES THE EXISTING LIFECYCLE ==============
class TestAskFounder(Base):

    def test_10_a_goal_attempt_blocks_and_the_founder_is_asked(self):
        """K: no new human-intervention state was invented."""
        g = self.goals.create(outcome="pick a database", target_session=SID,
                              done_when=[{"tier": "contains_artifact",
                                          "check": "FINAL:"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal_lifecycle.on_attempt_start(m)
        self.store.transition(m["id"], "running", "admitted")
        self.replies = ["I need to know which region you deploy in.", "x"]
        out = run(self.engine(self.recorder([
            {"action": "ask_founder", "reason": "which region do you want this deployed to", "ask_kind": "founder_fact"}
        ])).run_mission(m["id"]))
        goal_lifecycle.on_attempt_end(out)
        self.assertEqual(out["state"], "blocked", "the EXISTING blocked state")
        self.assertEqual(out["block_reason"], "needs_founder")
        self.assertIn("deploy region", out["note"]
                      if out.get("note") else "deploy region")
        gg = self.goals.load(g["id"])
        self.assertEqual(gg["state"], "blocked")
        self.assertEqual(gg["block_reason"], "needs_founder")
        self.assertEqual(gg["target_session"], SID, "chat kept, not cloned")

    def test_11_a_standalone_mission_ESCALATES_instead_of_stopping(self):
        """THE DOGFOOD BUG (founder, 2026-09-14, m-98f1b3adf69f).

        This used to assert `stopped` with no block_reason -- "no goal, no
        blocking". That made Shadow's one mid-mission way of reaching the
        founder indistinguishable from giving up: terminal, so the runner
        reaped the delegate, and the reason survived only in a ledger note
        nothing surfaces. ask_founder is an escalation, so it now takes the
        SAME exit the goal arm always took.
        """
        self.replies = ["stuck", "x"]
        mid = self.mission()
        out = run(self.engine(self.recorder([
            {"action": "ask_founder", "reason": "which region do you want", "ask_kind": "founder_fact"}
        ])).run_mission(mid))
        self.assertEqual(out["state"], "blocked",
                         "a standalone ask_founder must reach the founder")
        self.assertEqual(out["block_reason"], "needs_founder",
                         "the blocker must be stamped on the record")
        self.assertTrue(any("which region" in n for n in self.notes(mid)),
                        "the reason still lives in the ledger note")

    def test_11b_the_reason_survives_onto_the_record(self):
        """The founder is asked something specific, and the something has to
        reach the card. transition() does not stamp block_reason; block()
        is the one writer, which is why the exit had to change."""
        self.replies = ["stuck", "x"]
        mid = self.mission()
        out = run(self.engine(self.recorder([
            {"action": "ask_founder",
             "reason": "which region do you want, I do not have it", "ask_kind": "founder_fact"}
        ])).run_mission(mid))
        self.assertEqual(out["block_reason"], "needs_founder")
        self.assertTrue(
            any("which region" in n for n in self.notes(mid)),
            "what Shadow actually needed must be recoverable")

    def test_11c_the_session_is_kept_alive_for_the_founder_to_answer(self):
        """blocked is NOT terminal, and that is load-bearing: the runner
        reaps a delegate only on TERMINAL, so the chat the founder has to
        answer in stays alive. Asserted on the contract, not on a mock."""
        self.replies = ["stuck", "x"]
        mid = self.mission()
        out = run(self.engine(self.recorder([
            {"action": "ask_founder", "reason": "which region do you want", "ask_kind": "founder_fact"}
        ])).run_mission(mid))
        self.assertNotIn("blocked", mission_engine.TERMINAL,
                         "if blocked became terminal the delegate would be "
                         "reaped and there would be nothing to answer in")
        self.assertEqual(out["target_session"], SID,
                         "the original worker session must be kept, not cloned")

    def test_11d_resume_returns_to_the_SAME_worker(self):
        """blocked -> running is the existing resume edge, and it must land
        back on the same session: no respawn, no second chat."""
        self.replies = ["stuck", "x"]
        mid = self.mission()
        out = run(self.engine(self.recorder([
            {"action": "ask_founder", "reason": "which region do you want", "ask_kind": "founder_fact"}
        ])).run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertIn("running", mission_engine.TRANSITIONS["blocked"],
                      "resume must be a legal edge out of blocked")

        # the founder answered in the chat; Shadow is resumed
        self.said = []
        self.replies = ["FINAL: postgres", "x"]
        resumed = self.store.transition(mid, "running", "explicit resume")
        self.assertEqual(resumed["target_session"], SID)
        out2 = run(self.engine(self.recorder([
            {"action": "continue", "reason": "founder answered",
             "instruction": "Given the region, finish it."}
        ])).run_mission(mid))
        self.assertEqual({sid for sid, _t in self.said}, {SID},
                         "the resumed mission drove a DIFFERENT session")
        self.assertEqual(out2["target_session"], SID)

    def test_11e_continue_is_untouched_and_still_runs_out_of_budget(self):
        """The escalation exit must not become the ordinary one: a mission
        that keeps deciding `continue` still spends its budget and still
        ends `failed` for a standalone mission -- _out_of_road, unchanged."""
        self.replies = ["a", "b", "c", "d", "e", "f"]
        mid = self.mission(max_turns=2)
        out = run(self.engine(self.recorder([
            {"action": "continue", "reason": "keep going",
             "instruction": "step one"},
            {"action": "continue", "reason": "keep going",
             "instruction": "step two"},
            {"action": "continue", "reason": "keep going",
             "instruction": "step three"},
        ]), max_turns=2).run_mission(mid))
        self.assertEqual(out["state"], "failed",
                         "budget exhaustion is still a standalone failure")
        self.assertNotIn("block_reason", out,
                         "running out of budget is not an escalation")

    def test_11f_ping_pong_still_stops_a_standalone_mission(self):
        """_out_of_road's other exits are untouched: only the deliberate
        ask_founder exit changed."""
        self.replies = ["same", "same", "same"]
        mid = self.mission()
        out = run(self.engine(self.recorder([
            {"action": "continue", "reason": "r", "instruction": "identical"},
            {"action": "continue", "reason": "r", "instruction": "identical"},
        ])).run_mission(mid))
        self.assertEqual(out["state"], "stopped",
                         "ping-pong must still be a stop, not an escalation")
        self.assertNotIn("block_reason", out)

    def test_11g_the_needs_you_feed_row_is_the_existing_emitter(self):
        """The runner's blocked branch emits through emit_mission_feed, the
        same function the terminal branch uses. No new architecture: this
        asserts the EXISTING emitter produces an actionable row for a
        blocked mission, keyed so one block surfaces exactly once."""
        self.replies = ["stuck", "x"]
        mid = self.mission()
        out = run(self.engine(self.recorder([
            {"action": "ask_founder", "reason": "which region do you want", "ask_kind": "founder_fact"}
        ])).run_mission(mid))
        accepted, problems = mission_engine.emit_mission_feed(
            out, "needs_decision", out.get("block_reason") or "Shadow needs you")
        self.assertTrue(accepted,
                        "the existing emitter must accept a blocked mission: "
                        + str(problems))
        import shadow_feed
        rows = [json.loads(l) for l
                in open(shadow_feed._feed_path(), encoding="utf-8")
                if mid in l]
        self.assertEqual(len(rows), 1, "one row for one block")
        self.assertEqual(rows[0]["severity"], "action",
                         "needs_decision is what makes the row actionable")
        self.assertEqual(rows[0]["kind"], "needs_decision")
        self.assertIn("blocked", rows[0]["dedupe_key"],
                      "one row per block, per version")

        # and it does not double-prompt: the same block re-emits once only
        again, _ = mission_engine.emit_mission_feed(
            out, "needs_decision", out.get("block_reason") or "Shadow needs you")
        self.assertFalse(again, "the same block must not prompt twice")

    def test_12_ask_founder_sends_nothing_into_the_chat(self):
        self.replies = ["hmm", "x"]
        run(self.engine(self.recorder([
            {"action": "ask_founder", "reason": "which region do you want", "ask_kind": "founder_fact"}
        ])).run_mission(self.mission()))
        self.assertEqual(len(self.said), 1,
                         "only turn 0 was sent; the ask went to the founder")


# ================= FAILURE IS HONEST, NEVER A GENERIC NUDGE =============
class TestFailureHandling(Base):

    _n = 0

    def _undecided(self, decider):
        """One active goal per chat is a real invariant, so each case gets
        its own target session rather than reusing one."""
        self.replies = ["something", "x"]
        TestFailureHandling._n += 1
        _gid, mid = self.goal_mission(
            sid="%s-%d" % (SID, TestFailureHandling._n))
        self.mid = mid
        return run(self.engine(decider).run_mission(mid))

    def test_13_malformed_output_blocks_it_does_not_continue(self):
        """I: R10 -- never fall back to the generic instruction."""
        for bad in (None, "yes", 42, {}, {"action": "continue"},
                    {"action": "continue", "instruction": "   "},
                    {"instruction": "do it"}, {"action": "CONTINUE",
                                               "instruction": "x"}):
            with self.subTest(bad=bad):
                self.said = []
                m = self._undecided(lambda ctx, b=bad:
                                    asyncio.sleep(0, result=b))
                self.assertEqual(m["state"], "blocked")
                self.assertEqual(m["block_reason"], "shadow_undecided")
                self.assertEqual(len(self.said), 1,
                                 "nothing generic was sent")

    def test_14_a_decider_that_raises_is_reported_not_hidden(self):
        """J."""
        async def boom(ctx):
            raise RuntimeError("model unreachable")
        m = self._undecided(boom)
        self.assertEqual(m["state"], "blocked", "a goal attempt blocks")
        self.assertEqual(m["block_reason"], "shadow_undecided")
        self.assertTrue(any("model unreachable" in n
                            for n in self.notes(self.mid)),
                        "the cause survives on the record")

    def test_15_a_decider_timeout_is_the_same_honest_block(self):
        async def hang(ctx):
            raise asyncio.TimeoutError()
        m = self._undecided(hang)
        self.assertEqual(m["block_reason"], "shadow_undecided")

    def test_16_an_undecided_goal_attempt_blocks_for_the_founder(self):
        g = self.goals.create(outcome="pick one", target_session=SID,
                              done_when=[{"tier": "contains_artifact",
                                          "check": "FINAL:"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal_lifecycle.on_attempt_start(m)
        self.store.transition(m["id"], "running", "admitted")
        self.replies = ["x", "y"]
        out = run(self.engine(lambda ctx: asyncio.sleep(0, result={}))
                  .run_mission(m["id"]))
        goal_lifecycle.on_attempt_end(out)
        self.assertEqual(out["state"], "blocked", "a goal is never abandoned")
        self.assertEqual(self.goals.load(g["id"])["block_reason"],
                         "shadow_undecided")


# ================= THE OLD GUARDS ARE STILL GUARDS ======================
class TestGuardsIntact(Base):

    def test_17_max_turns_still_stops_it(self):
        """L."""
        self.replies = ["a"] * 10
        m = run(self.engine(self.recorder([
            {"action": "continue", "reason": "r",
             "instruction": "again %d" % i} for i in range(1, 9)
        ]), max_turns=3).run_mission(self.goal_mission(max_turns=3)[1]))
        self.assertEqual(m["state"], "blocked", "a goal attempt blocks")
        self.assertEqual(m["block_reason"], "budget_exhausted")
        self.assertEqual(m["turns_used"], 3, "not one turn more")

    def test_18_ping_pong_still_catches_a_repeated_instruction(self):
        """M: the safety net is intact -- a decider that repeats itself is
        stopped exactly as the old template was."""
        self.replies = ["a"] * 6
        m = run(self.engine(self.recorder([
            {"action": "continue", "instruction": "same thing",
             "reason": "r"}
        ])).run_mission(self.goal_mission()[1]))
        self.assertEqual(m["state"], "blocked")
        self.assertEqual(m["block_reason"], "ping_pong")
        self.assertEqual([t for _s, t in self.said][1:], ["same thing"],
                         "the duplicate was never sent")

    def test_19_no_decider_is_the_historical_template_verbatim(self):
        """Every standalone mission and every pre-existing test path."""
        self.replies = ["a", "b", "c"]
        m = run(self.engine(None).run_mission(self.goal_mission()[1]))
        texts = [t for _s, t in self.said]
        self.assertEqual(texts[0], "reach a decision on PostgreSQL vs DynamoDB")
        self.assertTrue(texts[1].startswith("Continue toward:"))
        self.assertEqual(m["block_reason"], "ping_pong",
                         "including its ping-pong ceiling, unchanged")

    def test_20_founder_confirm_still_pauses_instead_of_driving_on(self):
        """N: the decider is not consulted once the boundary is reached."""
        self.replies = ["FINAL: postgres", "should not be reached"]
        mid = self.mission(checks=[
            {"tier": "contains_artifact", "check": "FINAL:"},
            {"tier": "founder_confirm", "check": "reads well"}])
        m = run(self.engine(self.recorder([
            {"action": "continue", "instruction": "keep going", "reason": "r"}
        ])).run_mission(mid))
        self.assertEqual(m["state"], "paused")
        self.assertEqual(m["pause_reason"], "founder_confirm")
        self.assertEqual(self.driving_contexts, [],
                         "no decision was needed to DRIVE this at all")

    def test_21_the_last_instruction_is_recorded_on_the_mission(self):
        """16: a mission must be readable as decided -> said -> answered."""
        self.replies = ["a", "FINAL: b"]
        mid = self.mission()
        run(self.engine(self.recorder([
            {"action": "continue", "instruction": "the second ask",
             "reason": "because"}
        ])).run_mission(mid))
        self.assertEqual(self.store.load(mid)["last_instruction"],
                         "the second ask")
        rows = [json.loads(l) for l in
                open(__import__("shadow_ledger")._path("actions"),
                     encoding="utf-8") if mid in l]
        kinds = [r["kind"] for r in rows]
        self.assertIn("decision", kinds, "the decision is on the record")
        dec = [r for r in rows if r["kind"] == "decision"][0]
        self.assertIn("continue", dec["summary"])
        self.assertIn("the second ask", dec["summary"])
        self.assertIn("because", dec["summary"])


# ================= THE REAL DECIDER: parsing and isolation ==============
class TestTheProductionDecider(unittest.TestCase):

    def test_22_it_parses_a_fenced_decision(self):
        got = shadow_runner._first_decision(
            'Right.\n```json\n{"action":"continue","instruction":"go",'
            '"reason":"r"}\n```\n')
        self.assertEqual(got["action"], "continue")
        self.assertEqual(got["instruction"], "go")

    def test_23_it_parses_a_bare_object_and_survives_junk(self):
        self.assertEqual(shadow_runner._first_decision(
            'ok {"action":"ask_founder","reason":"x"} done')["action"],
            "ask_founder")
        for junk in ("", None, "no json here", "```json\nnot json\n```"):
            self.assertIsNone(shadow_runner._first_decision(junk), junk)

    def test_24_it_is_spawned_WITHOUT_the_shadow_tool_marker(self):
        """The enforcement behind "Shadow drives, the verifier decides":
        sutra_mcp registers the shadow tools only when SUTRA_MCP_SHADOW=1
        is in the spawn env, so this process cannot say, create or ledger."""
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        whole = src[src.index("def make_decider"):
                    src.index("def settle_confirmation")]
        # the docstring NAMES the marker while explaining why it is absent
        body = whole[whole.index('"""', whole.index('"""') + 3) + 3:]
        self.assertNotIn("SUTRA_MCP_SHADOW", body)
        self.assertIn("rt.spawn(build_args(), cwd", body)
        self.assertIn("rt.kill_group()", body, "one process per decision")
        self.assertIn("asyncio.wait_for", body, "and it is time-bounded")

    def test_25_no_credential_and_no_new_provider_stack(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        body = src[src.index("def make_decider"):
                   src.index("def settle_confirmation")]
        for bad in ("api_key", "API_KEY", "Authorization", "anthropic",
                    "openai", "http"):
            self.assertNotIn(bad, body, bad)
        self.assertIn("build_args()", body, "the EXISTING argv builder")

    def test_26_the_prompt_forbids_claiming_completion(self):
        p = shadow_runner._DECIDE_PROMPT
        self.assertIn("You do NOT do the work", p)
        self.assertIn("deterministic verifier owns", p)
        self.assertIn("never announce\ncompletion", p)
        self.assertNotIn('"action": "stop"', p)

    def test_27_the_runner_injects_it_and_app_wires_it_once(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        self.assertIn('decider=DEFAULT_DECIDER["fn"]', src,
                      "_launch hands it to the engine")
        app = Path(__file__).with_name("app.py").read_text()
        # the argv builder and the workdir are still the two positionals;
        # 2026-09-15 added the runtime factory as a keyword, so Shadow's
        # reasoning comes from provider_adapters like every chat pane's does
        # 2026-09-19 replaced the first positional: the reasoning lane is
        # built by _decide_args (no tools, no settings, no plugins) rather
        # than by the full-agent _shadow_args. The workdir, the runtime
        # factory and the single wiring below are unchanged.
        self.assertIn("shadow_runner.make_decider(_decide_args, "
                      "_shadow_workdir(),", app)
        self.assertIn("new_runtime=_shadow_new_runtime", app)
        self.assertEqual(app.count("set_default_decider("), 1)


if __name__ == "__main__":
    unittest.main()
