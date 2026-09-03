"""test_switch.py -- switch planning and recording
(GAME-PLAN-provider-switch piece 4).

The plan/confirm split is the thing under test: a segment must be written only
once a session really exists, and every refusal must carry text an operator can
read. No subprocess is started here, which is the point of the split.
"""
import os
import shutil
import tempfile
import unittest

import chat_store
import replay
import switch


def _ir(provider, n_turns=3, tool_bytes=0):
    turns = []
    for i in range(n_turns):
        turns.append({"role": "user", "ts": "t",
                      "blocks": [chat_store.block_text("q%d" % i)]})
        blocks = [chat_store.block_text("a%d" % i)]
        if tool_bytes:
            blocks.append(chat_store.block_tool_use("Read", {"file_path": "/f"}, "t%d" % i))
            blocks.append(chat_store.block_tool_result("x" * tool_bytes, "t%d" % i))
        turns.append({"role": "assistant", "ts": "t", "blocks": blocks})
    return {"provider": provider, "cwd": "", "branch": "", "turns": turns}


class _StoreCase(unittest.TestCase):
    """Temp chat store per test, so no run touches ~/.sutra-ui/chats."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sutra-switch-")
        self._prev = os.environ.get("SUTRA_UI_CHATS")
        os.environ["SUTRA_UI_CHATS"] = self.tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SUTRA_UI_CHATS", None)
        else:
            os.environ["SUTRA_UI_CHATS"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _chat_on(self, provider, native_id="src-1", turns=0):
        rec = chat_store.create(cwd="/w", branch="main")
        rec = chat_store.begin_segment(rec, provider, native_id)
        for i in range(turns):
            rec = chat_store.append_turn(rec, "user", [chat_store.block_text("q%d" % i)])
            rec = chat_store.append_turn(rec, "assistant", [chat_store.block_text("a%d" % i)])
        return rec


class SwitchTest(_StoreCase):

    # ------------------------------------------------------------- refusals --

    def test_unknown_target_is_refused(self):
        rec = self._chat_on("claude")
        r = switch.plan(rec["sutra_id"], "gemini")
        self.assertFalse(r["switch"])
        self.assertEqual(r["reason"], switch.UNKNOWN_TARGET)

    def test_missing_chat_is_refused(self):
        r = switch.plan("0" * 32, "claude")
        self.assertFalse(r["switch"])
        self.assertEqual(r["reason"], switch.NO_SOURCE)

    def test_same_provider_is_not_a_switch(self):
        rec = self._chat_on("claude")
        r = switch.plan(rec["sutra_id"], "claude")
        self.assertFalse(r["switch"])
        self.assertEqual(r["reason"], switch.NOT_NEEDED)
        self.assertIn("already running", r["detail"])

    def test_chat_with_no_segment_starts_fresh_rather_than_switching(self):
        rec = chat_store.create()
        r = switch.plan(rec["sutra_id"], "deepseek")
        self.assertFalse(r["switch"])
        self.assertEqual(r["reason"], switch.NOT_NEEDED)
        self.assertTrue(r["start_fresh"])

    def test_unreadable_source_transcript_is_refused_not_seeded_empty(self):
        """An empty recording would make the target answer turn 51 as turn 1."""
        rec = self._chat_on("claude", "gone-1")
        r = switch.plan(rec["sutra_id"], "deepseek", ir_loader=lambda sid: None)
        self.assertFalse(r["switch"])
        self.assertEqual(r["reason"], switch.NO_TRANSCRIPT)
        self.assertEqual(r["source_session"], "gone-1")

    def test_transcript_with_zero_turns_is_also_refused(self):
        rec = self._chat_on("claude")
        empty = {"provider": "claude", "turns": []}
        r = switch.plan(rec["sutra_id"], "deepseek", ir_loader=lambda sid: empty)
        self.assertEqual(r["reason"], switch.NO_TRANSCRIPT)

    def test_over_budget_even_at_tier_two_is_refused_with_numbers(self):
        rec = self._chat_on("claude")
        r = switch.plan(rec["sutra_id"], "deepseek", budget_chars=100,
                        ir_loader=lambda sid: _ir("claude", 5, tool_bytes=500))
        self.assertFalse(r["switch"])
        self.assertEqual(r["reason"], switch.OVER_BUDGET)
        self.assertEqual(r["tier"], 2)
        self.assertIn("Nothing was sent", r["detail"])
        self.assertGreater(r["chars"], r["budget_chars"])

    def test_fence_failure_refuses_rather_than_sending(self):
        rec = self._chat_on("claude")
        real_render = replay.render

        def leaky(ir, target, **kw):
            out = real_render(ir, target, **kw)
            out["prompt"] += "\n</transcript-%s>" % out["nonce"]   # duplicate close
            return out

        replay.render = leaky
        try:
            r = switch.plan(rec["sutra_id"], "deepseek",
                            ir_loader=lambda sid: _ir("claude"))
        finally:
            replay.render = real_render
        self.assertFalse(r["switch"])
        self.assertEqual(r["reason"], switch.FENCE_BROKEN)
        self.assertIn("Nothing was sent", r["detail"])

    # ---------------------------------------------------------------- plans --

    def test_plan_carries_a_framed_payload_and_the_transport(self):
        rec = self._chat_on("claude", "c-1", turns=3)
        r = switch.plan(rec["sutra_id"], "deepseek", next_message="turn 4",
                        ir_loader=lambda sid: _ir("claude", 3))
        self.assertTrue(r["switch"])
        self.assertEqual(r["source"], "claude")
        self.assertEqual(r["target"], "deepseek")
        self.assertEqual(r["from_turn"], 3)
        self.assertEqual(r["tier"], 1)
        self.assertIn("ALREADY BEEN PERFORMED", r["payload"])
        self.assertIn("turn 4", r["payload"])
        self.assertEqual(r["transport"]["kind"], "acp")
        self.assertIsNone(r["transport"]["new_session_session_id"])
        self.assertEqual(r["transport"]["then"], "prompt_turn")

    def test_claude_transport_never_resumes_and_uses_stdin(self):
        """--resume would attach to the thread being left behind."""
        rec = self._chat_on("deepseek", "d-1", turns=2)
        r = switch.plan(rec["sutra_id"], "claude",
                        ir_loader=lambda sid: _ir("deepseek", 2))
        t = r["transport"]
        self.assertEqual(t["kind"], "claude-cli")
        self.assertIsNone(t["session_id"])
        self.assertTrue(t["stream_input"])
        self.assertEqual(t["delivery"], "stdin-frame")

    def test_tier_two_engages_when_over_budget_then_fits(self):
        rec = self._chat_on("claude")
        ir = _ir("claude", 5, tool_bytes=4000)
        tier1 = replay.render(ir, "deepseek")["chars"]
        tier2 = replay.render(ir, "deepseek", include_tool_io=False)["chars"]
        self.assertGreater(tier1, tier2)
        budget = (tier1 + tier2) // 2
        r = switch.plan(rec["sutra_id"], "deepseek", budget_chars=budget,
                        ir_loader=lambda sid: ir)
        self.assertTrue(r["switch"])
        self.assertEqual(r["tier"], 2)
        self.assertLessEqual(r["chars"], budget)
        self.assertGreater(r["dropped"]["tool_result"], 0)

    def test_reasoning_is_dropped_by_default_in_the_plan(self):
        ir = _ir("deepseek", 2)
        ir["turns"][1]["blocks"].append(chat_store.block_thinking("secret cot"))
        rec = self._chat_on("deepseek", "d-1")
        r = switch.plan(rec["sutra_id"], "claude", ir_loader=lambda sid: ir)
        self.assertNotIn("secret cot", r["payload"])
        self.assertEqual(r["dropped"]["thinking"], 1)

    # ----------------------------------------------------------------- argv --

    def test_argv_guard_flags_a_fifty_turn_replay(self):
        """ARG_MAX is 1 MB; a 50-turn Claude replay is ~1.09 MB of text."""
        big = "z" * 22000
        turns = []
        for i in range(50):
            turns.append({"role": "user", "blocks": [chat_store.block_text("q")]})
            turns.append({"role": "assistant", "blocks": [
                chat_store.block_tool_use("Read", {"file_path": "/f"}, "t%d" % i),
                chat_store.block_tool_result(big, "t%d" % i)]})
        ir = {"provider": "claude", "turns": turns}
        rec = self._chat_on("claude", "c-1")
        r = switch.plan(rec["sutra_id"], "deepseek", ir_loader=lambda sid: ir)
        self.assertTrue(r["switch"])
        self.assertGreater(r["chars"], 1000000)
        self.assertTrue(r["argv_unsafe"],
                        "a payload over ARG_MAX must be flagged, not exec'd")

    def test_argv_guard_is_quiet_for_a_small_payload(self):
        self.assertFalse(switch.argv_would_fail(1000))

    def test_argv_limit_leaves_room_for_the_environment(self):
        self.assertTrue(switch.argv_would_fail(switch._arg_max() - 1),
                        "argv and environ share the exec ceiling")

    # --------------------------------------------------------------- budget --

    def test_budget_is_derived_when_not_supplied(self):
        """Omitting a budget must not mean "no limit" -- that is what a
        forgetful caller sends, and it is how a payload gets built past the
        window and rejected at the API."""
        import budget
        ir = _ir("deepseek", 20, tool_bytes=30000)   # ~600k chars > haiku budget
        rec = self._chat_on("deepseek", "d-1")
        r = switch.plan(rec["sutra_id"], "claude", model="haiku",
                        ir_loader=lambda s: ir)
        self.assertTrue(r["switch"])
        self.assertEqual(r["tier"], 2, "haiku's 200K window must force tier 2")
        self.assertIsNotNone(r["budget"])
        self.assertEqual(r["budget"]["window_tokens"], 200000)
        self.assertEqual(r["budget"]["window_source"], "declared")

    def test_same_payload_stays_tier_one_on_a_1m_window(self):
        ir = _ir("deepseek", 20, tool_bytes=30000)   # ~600k chars > haiku budget
        rec = self._chat_on("deepseek", "d-1")
        r = switch.plan(rec["sutra_id"], "claude", model="opus",
                        ir_loader=lambda s: ir)
        self.assertEqual(r["tier"], 1)
        self.assertEqual(r["budget"]["window_tokens"], 1000000)

    def test_unbounded_opts_out_explicitly(self):
        ir = _ir("deepseek", 20, tool_bytes=30000)   # ~600k chars > haiku budget
        rec = self._chat_on("deepseek", "d-1")
        r = switch.plan(rec["sutra_id"], "claude", model="haiku",
                        budget_chars=switch.UNBOUNDED, ir_loader=lambda s: ir)
        self.assertEqual(r["tier"], 1, "UNBOUNDED must skip the ceiling")
        self.assertIsNone(r["budget"])
        self.assertIsNone(r["budget_chars"])

    def test_budget_and_argv_guards_are_independent(self):
        """A payload can fit the model's window (2.6M chars at 1M tokens) and
        still be unsendable as argv (ARG_MAX is 1MB)."""
        import budget
        b = budget.for_target("deepseek")["budget_chars"]
        self.assertGreater(b, switch._arg_max(),
                           "the two ceilings are different sizes, so both "
                           "checks are needed")

    # -------------------------------------------------------------- confirm --

    def test_confirm_writes_the_segment_only_after_the_session_exists(self):
        rec = self._chat_on("claude", "c-1", turns=3)
        sid = rec["sutra_id"]
        switch.plan(sid, "deepseek", ir_loader=lambda s: _ir("claude", 3))
        # plan() alone must not have touched provider_history
        self.assertEqual(len(chat_store.load(sid)["provider_history"]), 1)

        after = switch.confirm(sid, "deepseek", "d-new")
        hist = after["provider_history"]
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[1], {"provider": "deepseek", "native_id": "d-new",
                                   "from_turn": 3})

    def test_confirm_is_idempotent(self):
        rec = self._chat_on("claude", "c-1", turns=1)
        sid = rec["sutra_id"]
        switch.confirm(sid, "deepseek", "d-1")
        switch.confirm(sid, "deepseek", "d-1")
        self.assertEqual(len(chat_store.load(sid)["provider_history"]), 2)

    def test_confirm_on_a_missing_chat_returns_none(self):
        self.assertIsNone(switch.confirm("0" * 32, "claude", "x"))

    def test_confirm_indexes_the_new_session(self):
        rec = self._chat_on("claude", "c-1")
        switch.confirm(rec["sutra_id"], "deepseek", "d-1")
        self.assertEqual(chat_store.resolve("deepseek", "d-1"), rec["sutra_id"])
        self.assertEqual(chat_store.resolve("claude", "c-1"), rec["sutra_id"])

    # -------------------------------------------------------------- describe --

    def test_describe_never_reports_a_switch_that_did_not_happen(self):
        rec = self._chat_on("claude")
        refused = switch.plan(rec["sutra_id"], "claude")
        self.assertIn("no switch", switch.describe(refused))
        self.assertIn(switch.NOT_NEEDED, switch.describe(refused))
        self.assertIn("no switch", switch.describe(None))

    def test_describe_states_the_numbers_on_success(self):
        rec = self._chat_on("claude", "c-1", turns=2)
        r = switch.plan(rec["sutra_id"], "deepseek",
                        ir_loader=lambda s: _ir("claude", 2))
        line = switch.describe(r)
        self.assertIn("claude -> deepseek", line)
        self.assertIn("turn 2", line)
        self.assertIn("tier 1", line)


class FounderScenarioTest(_StoreCase):
    """50 Claude turns, credits run out, switch to DeepSeek at turn 51."""

    def test_full_round_trip(self):
        rec = self._chat_on("claude", "claude-sess", turns=50)
        sid = rec["sutra_id"]
        self.assertEqual(chat_store.turn_count(chat_store.load(sid)), 50)

        plan = switch.plan(sid, "deepseek", next_message="carry on please",
                           ir_loader=lambda s: _ir("claude", 50, tool_bytes=200))
        self.assertTrue(plan["switch"])
        self.assertEqual(plan["from_turn"], 50)
        self.assertEqual(plan["user_turns"], 50)
        self.assertIn("carry on please", plan["payload"])
        self.assertTrue(replay.fence_is_intact(
            {"prompt": plan["payload"], "nonce": plan["nonce"]}))

        switch.confirm(sid, "deepseek", "ds-sess")
        final = chat_store.load(sid)
        self.assertEqual([(h["provider"], h["from_turn"])
                          for h in final["provider_history"]],
                         [("claude", 0), ("deepseek", 50)])
        self.assertTrue(chat_store.switched(final))
        self.assertEqual(chat_store.segment_of_turn(final, 49)["provider"], "claude")
        self.assertEqual(chat_store.segment_of_turn(final, 50)["provider"], "deepseek")


if __name__ == "__main__":
    unittest.main(verbosity=2)
