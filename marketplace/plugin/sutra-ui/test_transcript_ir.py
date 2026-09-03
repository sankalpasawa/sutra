"""test_transcript_ir.py -- provider-neutral transcript IR
(GAME-PLAN-provider-switch piece 2).

Fixtures are written to a temp dir in the on-disk shapes verified against real
transcripts on 2026-09-02, so the suite does not depend on the founder's
~/.claude or ~/.gemini trees. One separate smoke test reads the real trees when
they exist and skips when they do not.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import chat_store
import transcript_ir


def _w(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


class ClaudeIRTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sutra-ir-claude-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, records):
        p = self.tmp / "s.jsonl"
        _w(p, records)
        return p

    def test_text_thinking_tool_use_and_result_all_survive(self):
        p = self._file([
            {"type": "user", "cwd": "/w", "gitBranch": "main", "timestamp": "t0",
             "message": {"content": "read the file"}},
            {"type": "assistant", "timestamp": "t1", "message": {"content": [
                {"type": "thinking", "thinking": "which file"},
                {"type": "text", "text": "reading it"},
                {"type": "tool_use", "id": "tu1", "name": "Read",
                 "input": {"file_path": "/a", "limit": 10}},
            ]}},
            {"type": "user", "timestamp": "t2", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "tu1",
                 "content": "line one\nline two"},
            ]}},
        ])
        ir = transcript_ir.from_claude_file(p)
        self.assertEqual(ir["provider"], "claude")
        self.assertEqual(ir["cwd"], "/w")
        self.assertEqual(ir["branch"], "main")
        self.assertEqual([t["role"] for t in ir["turns"]], ["user", "assistant"])
        kinds = [b["type"] for b in ir["turns"][1]["blocks"]]
        self.assertEqual(kinds, ["thinking", "text", "tool_use", "tool_result"])

    def test_tool_result_is_spliced_after_its_own_call(self):
        p = self._file([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "a", "name": "A", "input": {}},
                {"type": "tool_use", "id": "b", "name": "B", "input": {}},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "B-out"},
                {"type": "tool_result", "tool_use_id": "a", "content": "A-out"},
            ]}},
        ])
        blocks = transcript_ir.from_claude_file(p)["turns"][0]["blocks"]
        self.assertEqual([b["type"] for b in blocks],
                         ["tool_use", "tool_result", "tool_use", "tool_result"])
        self.assertEqual(blocks[1]["text"], "A-out")
        self.assertEqual(blocks[3]["text"], "B-out")

    def test_full_input_is_kept_not_summarised(self):
        """session_reader keeps one key capped at 600 chars; replay needs all."""
        big = {"command": "x" * 2000, "description": "y" * 2000, "extra": 1}
        p = self._file([{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t", "name": "Bash", "input": big}]}}])
        blk = transcript_ir.from_claude_file(p)["turns"][0]["blocks"][0]
        self.assertEqual(blk["input"], big)

    def test_tool_result_is_not_truncated(self):
        """_RESULT_CAP is 8000 in the render parser; there is no cap here."""
        payload = "z" * 30000
        p = self._file([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t", "name": "Read", "input": {}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t", "content": payload}]}},
        ])
        blocks = transcript_ir.from_claude_file(p)["turns"][0]["blocks"]
        self.assertEqual(len(blocks[1]["text"]), 30000)

    def test_results_only_record_is_not_a_turn(self):
        p = self._file([
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "x", "content": "out"}]}},
        ])
        self.assertEqual(transcript_ir.from_claude_file(p)["turns"], [])

    def test_synthetic_user_injection_is_skipped(self):
        p = self._file([
            {"type": "user", "message": {"content": "<system-reminder>hi</system-reminder>"}},
            {"type": "user", "message": {"content": "real question"}},
        ])
        turns = transcript_ir.from_claude_file(p)["turns"]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["blocks"][0]["text"], "real question")

    def test_sutra_routing_preamble_is_stripped(self):
        """Sutra's own governance block must not be replayed as operator text."""
        p = self._file([{"type": "user", "message": {
            "content": "PLACEMENT: D0 Root | \"Root Charter\"\n\nwhat is the plan"}}])
        turns = transcript_ir.from_claude_file(p)["turns"]
        self.assertEqual(turns[0]["blocks"][0]["text"], "what is the plan")

    def test_image_result_leaves_a_visible_placeholder(self):
        p = self._file([
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t", "name": "Read", "input": {}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t",
                 "content": [{"type": "image", "source": {}}]}]}},
        ])
        blocks = transcript_ir.from_claude_file(p)["turns"][0]["blocks"]
        self.assertEqual(blocks[1]["text"], "[image]")

    def test_missing_file_yields_empty_ir_not_an_exception(self):
        ir = transcript_ir.from_claude_file(self.tmp / "nope.jsonl")
        self.assertEqual(ir["turns"], [])
        self.assertEqual(ir["provider"], "claude")

    def test_corrupt_lines_are_skipped(self):
        p = self.tmp / "s.jsonl"
        with open(p, "w") as fh:
            fh.write("{not json\n")
            fh.write(json.dumps({"type": "user", "message": {"content": "ok"}}) + "\n")
        self.assertEqual(len(transcript_ir.from_claude_file(p)["turns"]), 1)


class DeepSeekIRTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sutra-ir-ds-"))
        # .../tmp/<project>/chats/<file>.jsonl -- the project name is read from
        # the grandparent, so the fixture must have that depth.
        self.chats = self.tmp / "myproj" / "chats"
        self.chats.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, records):
        p = self.chats / "session-x.jsonl"
        _w(p, records)
        return p

    def test_thought_fragments_join_into_one_block(self):
        """thoughts is per-token, each fragment carrying a full timestamp:
        91.2% of the stored field is scaffolding."""
        frags = [{"subject": "", "description": w, "timestamp": "2026-08-31T15:08:55.974Z"}
                 for w in ("The", " user", " asked")]
        p = self._file([{"id": "m1", "type": "gemini", "timestamp": "t",
                         "content": "answer", "thoughts": frags}])
        blocks = transcript_ir.from_deepseek_file(p)["turns"][0]["blocks"]
        self.assertEqual(blocks[0]["type"], "thinking")
        self.assertEqual(blocks[0]["text"], "The user asked")
        self.assertEqual(blocks[1]["type"], "text")

    def test_tool_calls_become_a_use_result_pair(self):
        p = self._file([{"id": "m1", "type": "gemini", "content": "", "toolCalls": [
            {"id": "c1", "name": "write_file", "args": {"path": "/a"},
             "resultDisplay": "wrote 3 lines", "status": "ok"}]}])
        blocks = transcript_ir.from_deepseek_file(p)["turns"][0]["blocks"]
        self.assertEqual([b["type"] for b in blocks], ["tool_use", "tool_result"])
        self.assertEqual(blocks[0]["input"], {"path": "/a"})
        self.assertEqual(blocks[1]["text"], "wrote 3 lines")
        self.assertFalse(blocks[1]["is_error"])

    def test_error_status_marks_the_result(self):
        p = self._file([{"id": "m1", "type": "gemini", "content": "", "toolCalls": [
            {"id": "c1", "name": "read_file", "args": {},
             "resultDisplay": "no such file", "status": "error"}]}])
        blocks = transcript_ir.from_deepseek_file(p)["turns"][0]["blocks"]
        self.assertTrue(blocks[1]["is_error"])

    def test_result_display_dict_falls_back_to_filediff(self):
        p = self._file([{"id": "m1", "type": "gemini", "content": "", "toolCalls": [
            {"id": "c1", "name": "write_file", "args": {},
             "resultDisplay": {"fileName": "a", "fileDiff": "--- a\n+++ b"}}]}])
        blocks = transcript_ir.from_deepseek_file(p)["turns"][0]["blocks"]
        self.assertEqual(blocks[1]["text"], "--- a\n+++ b")

    def test_function_response_envelope_is_the_last_fallback(self):
        p = self._file([{"id": "m1", "type": "gemini", "content": "", "toolCalls": [
            {"id": "c1", "name": "t", "args": {},
             "result": [{"functionResponse": {"response": {"output": "env-out"}}}]}]}])
        blocks = transcript_ir.from_deepseek_file(p)["turns"][0]["blocks"]
        self.assertEqual(blocks[1]["text"], "env-out")

    def test_last_write_wins_by_id(self):
        """A turn's record is rewritten in place as its tool calls run."""
        p = self._file([
            {"id": "m1", "type": "gemini", "content": "partial", "toolCalls": [
                {"id": "c1", "name": "A", "args": {}, "resultDisplay": "one"}]},
            {"id": "m1", "type": "gemini", "content": "final", "toolCalls": [
                {"id": "c1", "name": "A", "args": {}, "resultDisplay": "one"},
                {"id": "c2", "name": "B", "args": {}, "resultDisplay": "two"}]},
        ])
        turns = transcript_ir.from_deepseek_file(p)["turns"]
        self.assertEqual(len(turns), 1, "the same id must not produce two turns")
        texts = [b["text"] for b in turns[0]["blocks"] if b["type"] == "text"]
        self.assertEqual(texts, ["final"])
        self.assertEqual(sum(1 for b in turns[0]["blocks"]
                             if b["type"] == "tool_use"), 2)

    def test_set_snapshot_carries_messages(self):
        p = self._file([
            {"$set": {"messages": [
                {"id": "m0", "type": "user", "content": [{"text": "from snapshot"}]}]}},
            {"id": "m1", "type": "gemini", "content": "reply"},
        ])
        turns = transcript_ir.from_deepseek_file(p)["turns"]
        self.assertEqual([t["role"] for t in turns], ["user", "assistant"])
        self.assertEqual(turns[0]["blocks"][0]["text"], "from snapshot")

    def test_user_content_block_list_has_no_type_key(self):
        p = self._file([{"id": "m1", "type": "user",
                         "content": [{"text": "a"}, {"text": "b"}]}])
        turns = transcript_ir.from_deepseek_file(p)["turns"]
        self.assertEqual(turns[0]["blocks"][0]["text"], "a\nb")

    def test_project_cwd_is_resolved_from_the_grandparent_dir(self):
        p = self._file([{"id": "m1", "type": "user", "content": "q"}])
        ir = transcript_ir.from_deepseek_file(p, {"myproj": "/real/path"})
        self.assertEqual(ir["cwd"], "/real/path")

    def test_records_without_id_are_ignored(self):
        p = self._file([{"type": "user", "content": "no id"},
                        {"id": "m1", "type": "user", "content": "has id"}])
        turns = transcript_ir.from_deepseek_file(p)["turns"]
        self.assertEqual(len(turns), 1)


class StatsTest(unittest.TestCase):

    def test_stats_splits_tool_conversation_and_reasoning(self):
        ir = {"provider": "claude", "turns": [
            {"role": "user", "blocks": [chat_store.block_text("a" * 10)]},
            {"role": "assistant", "blocks": [
                chat_store.block_thinking("b" * 20),
                chat_store.block_tool_use("Read", {"k": "v"}, "t"),
                chat_store.block_tool_result("c" * 100, "t"),
            ]},
        ]}
        s = transcript_ir.stats(ir)
        self.assertEqual(s["user_turns"], 1)
        self.assertEqual(s["conversation_chars"], 10)
        self.assertEqual(s["reasoning_chars"], 20)
        self.assertEqual(s["chars"]["tool_result"], 100)
        self.assertEqual(s["chars"]["tool_use"], len(json.dumps({"k": "v"})))
        self.assertEqual(s["tool_chars"], 100 + len(json.dumps({"k": "v"})))
        self.assertEqual(s["total_chars"], s["conversation_chars"]
                         + s["reasoning_chars"] + s["tool_chars"])

    def test_chars_per_user_turn_is_zero_with_no_user_turn(self):
        s = transcript_ir.stats({"provider": "claude", "turns": []})
        self.assertEqual(s["chars_per_user_turn"], 0)
        self.assertEqual(s["total_chars"], 0)


class RealTreeSmokeTest(unittest.TestCase):
    """Read-only against the real trees. Skips when they are absent."""

    def test_real_claude_transcript_parses(self):
        import session_reader
        files = list(session_reader.PROJECTS.glob("*/*.jsonl")) \
            if session_reader.PROJECTS.exists() else []
        if not files:
            self.skipTest("no Claude transcripts on this machine")
        files.sort(key=lambda p: p.stat().st_size, reverse=True)
        ir = transcript_ir.from_claude_file(files[0])
        s = transcript_ir.stats(ir)
        self.assertGreater(s["user_turns"], 0, "largest transcript parsed to no turns")
        self.assertGreater(s["total_chars"], 0)

    def test_real_deepseek_transcript_parses(self):
        import session_reader
        files = list(session_reader.GEMINI_ROOT.glob("tmp/*/chats/*.jsonl")) \
            if session_reader.GEMINI_ROOT.exists() else []
        if not files:
            self.skipTest("no DeepSeek transcripts on this machine")
        files.sort(key=lambda p: p.stat().st_size, reverse=True)
        ir = transcript_ir.from_deepseek_file(files[0])
        s = transcript_ir.stats(ir)
        self.assertGreater(len(ir["turns"]), 0, "largest transcript parsed to no turns")
        self.assertGreater(s["total_chars"], 0)



class NestingTest(unittest.TestCase):
    """Prior replays must not survive into the next one
    (found in live testing 2026-09-02)."""

    def _replay_turn(self, nonce="a1b2c3d4e5f60718", inner="earlier turns"):
        text = ("You are taking over an in-progress working session from a "
                "different assistant (Claude Code).\n\n<transcript-%s>\n%s\n"
                "</transcript-%s>\nThat is the end of the recording."
                % (nonce, inner, nonce))
        return {"role": "user", "ts": "t1",
                "blocks": [chat_store.block_text(text)]}

    def test_a_replay_turn_is_recognised(self):
        self.assertTrue(transcript_ir.is_replay_turn(self._replay_turn()))

    def test_an_operator_turn_is_never_mistaken_for_one(self):
        for text in ("add a fence to the replay",
                     "You are taking over the deploy rota",
                     "see <transcript-0000000000000000> in the doc"):
            t = {"role": "user", "ts": "t",
                 "blocks": [chat_store.block_text(text)]}
            self.assertFalse(transcript_ir.is_replay_turn(t),
                             "%r must not be treated as a replay" % text)

    def test_both_signals_are_required(self):
        """Either alone appears in this repo's own design doc."""
        fence_only = {"role": "user", "ts": "t", "blocks": [
            chat_store.block_text("<transcript-aaaaaaaaaaaaaaaa> alone")]}
        preamble_only = {"role": "user", "ts": "t", "blocks": [
            chat_store.block_text("You are taking over an in-progress working "
                                  "session, no fence here")]}
        self.assertFalse(transcript_ir.is_replay_turn(fence_only))
        self.assertFalse(transcript_ir.is_replay_turn(preamble_only))

    def test_assistant_turns_are_never_replays(self):
        t = dict(self._replay_turn())
        t["role"] = "assistant"
        self.assertFalse(transcript_ir.is_replay_turn(t))

    def test_strip_replays_keeps_everything_else(self):
        ir = {"provider": "deepseek", "turns": [
            self._replay_turn(),
            {"role": "assistant", "ts": "t2",
             "blocks": [chat_store.block_text("answer")]},
            {"role": "user", "ts": "t3",
             "blocks": [chat_store.block_text("next question")]},
        ]}
        out = transcript_ir.strip_replays(ir)
        self.assertEqual(len(out["turns"]), 2)
        self.assertEqual(out["turns"][0]["role"], "assistant")

    def test_combine_merges_sessions_in_time_order(self):
        a = {"provider": "claude", "cwd": "/w", "turns": [
            {"role": "user", "ts": "2026-09-02T10:00:00Z",
             "blocks": [chat_store.block_text("first")]},
            {"role": "user", "ts": "2026-09-02T10:30:00Z",
             "blocks": [chat_store.block_text("third")]},
        ]}
        b = {"provider": "deepseek", "turns": [
            {"role": "user", "ts": "2026-09-02T10:15:00Z",
             "blocks": [chat_store.block_text("second")]},
        ]}
        out = transcript_ir.combine([a, b], provider="claude")
        self.assertEqual(
            [t["blocks"][0]["text"] for t in out["turns"]],
            ["first", "second", "third"],
            "a resumed session's later turns must not jump ahead of the other "
            "provider's earlier ones")
        self.assertEqual(out["cwd"], "/w")

    def test_combine_drops_every_nested_replay(self):
        a = {"provider": "claude", "turns": [
            {"role": "user", "ts": "t0", "blocks": [chat_store.block_text("real")]}]}
        b = {"provider": "deepseek", "turns": [
            self._replay_turn(nonce="1111111111111111"),
            {"role": "assistant", "ts": "t2",
             "blocks": [chat_store.block_text("reply")]}]}
        out = transcript_ir.combine([a, b])
        texts = " ".join(bl.get("text", "") for t in out["turns"]
                         for bl in t["blocks"])
        self.assertNotIn("<transcript-", texts,
                         "a stale fence inside the payload defeats the nonce")
        self.assertNotIn("You are taking over", texts)
        self.assertEqual(len(out["turns"]), 2)

    def test_combine_tolerates_missing_sessions(self):
        out = transcript_ir.combine([None, {"provider": "x", "turns": []}, None])
        self.assertEqual(out["turns"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
