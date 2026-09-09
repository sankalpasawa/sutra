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


class CodexIRTest(unittest.TestCase):
    """Fixtures in the on-disk shapes verified against the 13 real rollouts in
    $CODEX_HOME/sessions on 2026-09-09 (311 records, codex-cli 0.153.2)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sutra-ir-codex-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, records):
        p = self.tmp / "rollout-2026-09-09T00-00-00-thread.jsonl"
        _w(p, records)
        return p

    # Record builders, so a fixture reads as the conversation it represents
    # rather than as four levels of nesting.
    @staticmethod
    def _meta(cwd="/w", branch="main", ts="2026-09-09T00:00:00.000Z"):
        payload = {"type": "session_meta", "session_id": "thread", "cwd": cwd}
        if branch is not None:
            payload["git"] = {"branch": branch, "commit_hash": "abc"}
        return {"timestamp": ts, "type": "session_meta", "payload": payload}

    @staticmethod
    def _msg(role, text, ts="2026-09-09T00:00:01.000Z", phase=None):
        kind = "output_text" if role == "assistant" else "input_text"
        payload = {"type": "message", "role": role,
                   "content": [{"type": kind, "text": text}]}
        if phase:
            payload["phase"] = phase
        return {"timestamp": ts, "type": "response_item", "payload": payload}

    @staticmethod
    def _call(call_id, inp, name="exec", ts="2026-09-09T00:00:02.000Z"):
        return {"timestamp": ts, "type": "response_item", "payload": {
            "type": "custom_tool_call", "id": "ctc_" + call_id,
            "call_id": call_id, "name": name, "input": inp,
            "status": "completed"}}

    @staticmethod
    def _out(call_id, text, ts="2026-09-09T00:00:03.000Z"):
        return {"timestamp": ts, "type": "response_item", "payload": {
            "type": "custom_tool_call_output", "id": "ctco_" + call_id,
            "call_id": call_id,
            "output": [{"type": "input_text", "text": text}]}}

    # ------------------------------------------------------------- the flow --

    def test_user_assistant_and_tool_flow_all_survive(self):
        p = self._file([
            self._meta(),
            self._msg("user", "read the file"),
            self._msg("assistant", "reading it", phase="commentary"),
            self._call("c1", 'const r = await tools.exec_command({"cmd":"ls"});'),
            self._out("c1", "a.txt\nb.txt"),
            self._msg("assistant", "two files", phase="final_answer"),
        ])
        ir = transcript_ir.from_codex_file(p)
        self.assertEqual(ir["provider"], "codex")
        self.assertEqual([t["role"] for t in ir["turns"]], ["user", "assistant"])
        self.assertEqual([b["type"] for b in ir["turns"][1]["blocks"]],
                         ["text", "tool_use", "tool_result", "text"])

    def test_assistant_items_fold_into_one_turn_per_operator_turn(self):
        """Codex's stream is per-API-item, so an unfolded parser would emit a
        turn header per record -- fourteen for one reply that ran ten commands."""
        p = self._file([
            self._msg("user", "q1"),
            self._msg("assistant", "part one"),
            self._call("c1", "x"), self._out("c1", "out1"),
            self._msg("assistant", "part two"),
            self._msg("user", "q2"),
            self._msg("assistant", "second reply"),
        ])
        turns = transcript_ir.from_codex_file(p)["turns"]
        self.assertEqual([t["role"] for t in turns],
                         ["user", "assistant", "user", "assistant"])
        self.assertEqual(len(turns[1]["blocks"]), 4)
        self.assertEqual(len(turns[3]["blocks"]), 1,
                         "an operator turn must close the reply before it")

    # -------------------------------------------------------- what is dropped --

    def test_developer_role_is_never_an_operator_turn(self):
        """THE TRAP THE `<`-PREFIX RULE DOES NOT CATCH. Codex writes its own
        system instructions as developer messages, and one measured record
        opens "You are `/root`, the primary agent…" with no leading tag. A
        parser filtering only on `<` would replay it as operator speech."""
        p = self._file([
            self._msg("developer", "You are `/root`, the primary agent in a "
                                   "team of agents collaborating on a task."),
            self._msg("developer", "<skills_instructions>\n## Skills"),
            self._msg("user", "the real question"),
        ])
        turns = transcript_ir.from_codex_file(p)["turns"]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["blocks"][0]["text"], "the real question")

    def test_angle_bracket_user_injection_is_skipped(self):
        p = self._file([
            self._msg("user", "<environment_context>\n  <cwd>/w</cwd>"),
            self._msg("user", "<recommended_plugins> here is a list"),
            self._msg("user", "actually typed this"),
        ])
        turns = transcript_ir.from_codex_file(p)["turns"]
        self.assertEqual([t["blocks"][0]["text"] for t in turns],
                         ["actually typed this"])

    def test_sutra_routing_preamble_is_stripped(self):
        """PLACEMENT appears in 10 real rollout records, so the shared
        _strip_preamble applies here exactly as it does to the other two."""
        p = self._file([self._msg(
            "user", 'PLACEMENT: unresolved -- no department\n\nwhat is the plan')])
        turns = transcript_ir.from_codex_file(p)["turns"]
        self.assertEqual(turns[0]["blocks"][0]["text"], "what is the plan")

    def test_reasoning_emits_nothing_and_never_leaks_encrypted_content(self):
        """summary is [] in 16/16 records; encrypted_content is an opaque blob,
        not readable thought, and must not reach another vendor's model."""
        p = self._file([
            self._msg("user", "q"),
            {"timestamp": "2026-09-09T00:00:02.000Z", "type": "response_item",
             "payload": {"type": "reasoning", "id": "rs_1", "summary": [],
                         "encrypted_content": "gAAAAABqoFpWekqF-SECRET-BLOB"}},
            self._msg("assistant", "a"),
        ])
        ir = transcript_ir.from_codex_file(p)
        blob = json.dumps(ir)
        self.assertNotIn("SECRET-BLOB", blob)
        self.assertNotIn("encrypted_content", blob)
        self.assertEqual(transcript_ir.stats(ir)["reasoning_chars"], 0)
        self.assertEqual([b["type"] for b in ir["turns"][1]["blocks"]], ["text"])

    def test_event_msg_records_are_ignored_and_do_not_double_render(self):
        """response_item is a strict superset; reading both streams would
        render every message twice."""
        p = self._file([
            self._msg("user", "say hi"),
            {"timestamp": "2026-09-09T00:00:02.000Z", "type": "event_msg",
             "payload": {"type": "item_completed", "item": {
                 "type": "UserMessage", "id": "u1",
                 "content": [{"type": "text", "text": "say hi"}]}}},
            {"timestamp": "2026-09-09T00:00:03.000Z", "type": "event_msg",
             "payload": {"type": "item_completed", "item": {
                 "type": "AgentMessage", "id": "a1", "text": "hi"}}},
            self._msg("assistant", "hi"),
        ])
        turns = transcript_ir.from_codex_file(p)["turns"]
        self.assertEqual([t["role"] for t in turns], ["user", "assistant"])
        self.assertEqual(len(turns[1]["blocks"]), 1)

    # ------------------------------------------------------------ tool input --

    def test_string_tool_input_survives_instead_of_becoming_empty(self):
        """chat_store.block_tool_use replaces a non-dict input with {}, and
        codex's input is a string 15/15 -- so a raw pass would drop every tool
        input in the transcript while still reporting success."""
        script = ('const r = await tools.exec_command({"cmd":"sed -n \'1,240p\' '
                  '/tmp/a"});\ntext(r.output);\n')
        p = self._file([self._call("c1", script)])
        blk = transcript_ir.from_codex_file(p)["turns"][0]["blocks"][0]
        self.assertEqual(blk["input"], {"input": script})
        self.assertGreater(transcript_ir.stats(
            transcript_ir.from_codex_file(p))["chars"]["tool_use"], 100)

    def test_json_object_tool_input_keeps_its_real_keys(self):
        """The classic function_call.arguments shape must not be buried under
        a wrapper key."""
        p = self._file([self._call("c1", '{"cmd": "ls", "timeout": 30}',
                                  name="shell")])
        blk = transcript_ir.from_codex_file(p)["turns"][0]["blocks"][0]
        self.assertEqual(blk["input"], {"cmd": "ls", "timeout": 30})
        self.assertEqual(blk["name"], "shell")

    def test_non_object_json_input_is_still_wrapped_not_dropped(self):
        """A string that parses to a list or a number is not a tool input dict;
        wrapping keeps it rather than letting block_tool_use empty it."""
        p = self._file([self._call("c1", "[1, 2, 3]")])
        blk = transcript_ir.from_codex_file(p)["turns"][0]["blocks"][0]
        self.assertEqual(blk["input"], {"input": "[1, 2, 3]"})

    def test_dict_tool_input_passes_through_unchanged(self):
        p = self._file([self._call("c1", {"cmd": "ls"})])
        blk = transcript_ir.from_codex_file(p)["turns"][0]["blocks"][0]
        self.assertEqual(blk["input"], {"cmd": "ls"})

    # -------------------------------------------------------------- pairing --

    def test_output_is_spliced_after_its_own_call_by_call_id(self):
        """Out of order on purpose: the output arrives on a later record, as a
        Claude tool_result does, so order in the file must not decide pairing."""
        p = self._file([
            self._call("a", "A-in"), self._call("b", "B-in"),
            self._out("b", "B-out"), self._out("a", "A-out"),
        ])
        blocks = transcript_ir.from_codex_file(p)["turns"][0]["blocks"]
        self.assertEqual([b["type"] for b in blocks],
                         ["tool_use", "tool_result", "tool_use", "tool_result"])
        self.assertEqual(blocks[1]["text"], "A-out")
        self.assertEqual(blocks[3]["text"], "B-out")
        self.assertEqual(blocks[1]["tool_use_id"], "a")

    def test_an_orphan_output_adds_no_block(self):
        p = self._file([self._call("a", "in"), self._out("zzz", "nobody")])
        blocks = transcript_ir.from_codex_file(p)["turns"][0]["blocks"]
        self.assertEqual([b["type"] for b in blocks], ["tool_use"])

    def test_tool_output_is_not_truncated_by_this_module(self):
        payload = "z" * 30000
        p = self._file([self._call("a", "in"), self._out("a", payload)])
        blocks = transcript_ir.from_codex_file(p)["turns"][0]["blocks"]
        self.assertEqual(len(blocks[1]["text"]), 30000)

    def test_a_recognised_type_with_no_branch_cannot_become_a_tool_result(self):
        """The trap the canary would otherwise walk someone into.

        test_no_unrecognised_response_item_type_in_a_real_rollout tells whoever
        meets an unmeasured type to add it to _CODEX_ITEM_TYPES. While the
        output branch was the bare TAIL of the if-chain, doing that sent the new
        record straight into it -- `results[call_id] = ...` overwrote the real
        result for that call. Measured before the guard landed: a `web_search`
        record replaced a command's output with "".

        So this adds a recognised-but-unhandled type the way a future
        maintainer would, and asserts it is inert.
        """
        original = transcript_ir._CODEX_ITEM_TYPES
        transcript_ir._CODEX_ITEM_TYPES = original + ("web_search",)
        try:
            p = self._file([
                self._call("a", "ls"),
                self._out("a", "real output"),
                # Same call_id, so it lands on exactly the entry it would have
                # clobbered rather than merely being ignored elsewhere.
                {"timestamp": "2026-09-09T00:00:04.000Z",
                 "type": "response_item",
                 "payload": {"type": "web_search", "call_id": "a",
                             "query": "HIJACKED"}},
            ])
            blocks = transcript_ir.from_codex_file(p)["turns"][0]["blocks"]
        finally:
            transcript_ir._CODEX_ITEM_TYPES = original

        self.assertEqual([b["type"] for b in blocks],
                         ["tool_use", "tool_result"],
                         "the extra type produced a block of its own")
        self.assertEqual(blocks[1]["text"], "real output",
                         "a recognised type with no parser branch overwrote "
                         "the real tool result")
        self.assertNotIn("HIJACKED", json.dumps(blocks))

    def test_failed_command_is_not_marked_is_error(self):
        """MEASURED, NOT AN OVERSIGHT: custom_tool_call_output carries no
        status field at all, and the call's own status is "completed" even for
        a command that failed. Pinned so a later reader does not "fix" it by
        parsing the output prose."""
        p = self._file([self._call("a", "in"),
                        self._out("a", "Script failed\nexit code 3")])
        blocks = transcript_ir.from_codex_file(p)["turns"][0]["blocks"]
        self.assertFalse(blocks[1]["is_error"])

    # ----------------------------------------------------------- meta / resume --

    def test_session_meta_supplies_cwd_and_branch(self):
        p = self._file([self._meta(cwd="/repo", branch="deepseek-provider"),
                        self._msg("user", "q")])
        ir = transcript_ir.from_codex_file(p)
        self.assertEqual(ir["cwd"], "/repo")
        self.assertEqual(ir["branch"], "deepseek-provider")

    def test_missing_git_block_is_an_empty_branch_not_an_error(self):
        """3 of 13 real rollouts ran outside a repository."""
        p = self._file([self._meta(cwd="/tmp/scratch", branch=None),
                        self._msg("user", "q")])
        ir = transcript_ir.from_codex_file(p)
        self.assertEqual(ir["cwd"], "/tmp/scratch")
        self.assertEqual(ir["branch"], "")

    def test_resumed_records_in_one_file_do_not_duplicate(self):
        """A resumed thread APPENDS to the file it started in -- verified on a
        real rollout carrying two task_started events and one session_meta. The
        second turn writes only its new records, so there is no last-write-wins
        to do and no turn may appear twice."""
        p = self._file([
            self._meta(),
            {"timestamp": "2026-09-09T00:00:01.000Z", "type": "event_msg",
             "payload": {"type": "task_started", "turn_id": "t1"}},
            self._msg("user", "Reply with exactly the word: SUTRA",
                      ts="2026-09-09T00:00:02.000Z"),
            self._msg("assistant", "SUTRA", ts="2026-09-09T00:00:03.000Z"),
            {"timestamp": "2026-09-09T00:00:04.000Z", "type": "event_msg",
             "payload": {"type": "task_started", "turn_id": "t2"}},
            self._msg("user", "What word did you just reply with?",
                      ts="2026-09-09T00:00:05.000Z"),
            self._msg("assistant", "SUTRA", ts="2026-09-09T00:00:06.000Z"),
        ])
        turns = transcript_ir.from_codex_file(p)["turns"]
        self.assertEqual([t["role"] for t in turns],
                         ["user", "assistant", "user", "assistant"])
        self.assertEqual(transcript_ir.stats(
            transcript_ir.from_codex_file(p))["user_turns"], 2)

    # -------------------------------------------------------------- robustness --

    def test_multi_item_content_is_joined(self):
        rec = {"timestamp": "t", "type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "a"},
                        {"type": "input_text", "text": "b"}]}}
        turns = transcript_ir.from_codex_file(self._file([rec]))["turns"]
        self.assertEqual(turns[0]["blocks"][0]["text"], "a\nb")

    def test_image_content_leaves_a_visible_placeholder(self):
        rec = {"timestamp": "t", "type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_image", "image_url": "data:…"},
                        {"type": "input_text", "text": "what is this"}]}}
        turns = transcript_ir.from_codex_file(self._file([rec]))["turns"]
        self.assertEqual(turns[0]["blocks"][0]["text"], "[image]\nwhat is this")

    def test_missing_file_yields_empty_ir_not_an_exception(self):
        ir = transcript_ir.from_codex_file(self.tmp / "nope.jsonl")
        self.assertEqual(ir["turns"], [])
        self.assertEqual(ir["provider"], "codex")

    def test_corrupt_and_malformed_records_are_skipped(self):
        p = self.tmp / "r.jsonl"
        with open(p, "w") as fh:
            fh.write("{not json\n")
            fh.write(json.dumps(["not", "a", "dict"]) + "\n")
            fh.write(json.dumps({"type": "response_item"}) + "\n")
            fh.write(json.dumps({"type": "response_item",
                                 "payload": "not a dict"}) + "\n")
            fh.write(json.dumps({"type": "response_item",
                                 "payload": {"type": "unknown_future_thing"}}) + "\n")
            fh.write(json.dumps(self._msg("user", "ok")) + "\n")
        turns = transcript_ir.from_codex_file(p)["turns"]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["blocks"][0]["text"], "ok")

    def test_empty_assistant_text_adds_no_turn(self):
        p = self._file([self._msg("assistant", "   ")])
        self.assertEqual(transcript_ir.from_codex_file(p)["turns"], [])

    # ------------------------------------------------------------- nesting --

    def test_a_codex_recorded_replay_is_detected_and_stripped(self):
        """The round trip that makes carry-over safe in both directions. A
        replay Sutra sent to codex is recorded by codex as an ordinary user
        message, and the NEXT switch must not wrap it again -- stale fences
        inside a live one are what fence_is_intact fails closed on."""
        import replay
        prior = {"provider": "claude", "turns": [
            {"role": "user", "ts": "t0",
             "blocks": [chat_store.block_text("do the thing")]},
            {"role": "assistant", "ts": "t1",
             "blocks": [chat_store.block_text("done")]}]}
        payload = replay.render(prior, "codex")["prompt"]

        p = self._file([
            self._meta(),
            self._msg("developer", "You are `/root`, the primary agent"),
            self._msg("user", payload, ts="2026-09-09T00:00:02.000Z"),
            self._msg("assistant", "carrying on", ts="2026-09-09T00:00:03.000Z"),
        ])
        ir = transcript_ir.from_codex_file(p)
        self.assertTrue(transcript_ir.is_replay_turn(ir["turns"][0]),
                        "a replay codex recorded must be recognised as one")
        stripped = transcript_ir.strip_replays(ir)
        self.assertEqual([t["role"] for t in stripped["turns"]], ["assistant"])

        # and the next hop's fence must come out clean
        out = replay.render(transcript_ir.combine([stripped], provider="codex"),
                            "claude")
        self.assertTrue(replay.fence_is_intact(out),
                        "a stale fence survived into the next payload")

    def test_codex_turns_merge_with_the_other_providers_by_timestamp(self):
        """All three trees write YYYY-MM-DDTHH:MM:SS.mmmZ, so combine's
        lexicographic sort orders across providers with no special case."""
        p = self._file([self._msg("user", "codex turn",
                                  ts="2026-09-09T10:15:00.000Z")])
        cx = transcript_ir.from_codex_file(p)
        other = {"provider": "claude", "turns": [
            {"role": "user", "ts": "2026-09-09T10:00:00.000Z",
             "blocks": [chat_store.block_text("first")]},
            {"role": "user", "ts": "2026-09-09T10:30:00.000Z",
             "blocks": [chat_store.block_text("third")]}]}
        out = transcript_ir.combine([other, cx])
        self.assertEqual([t["blocks"][0]["text"] for t in out["turns"]],
                         ["first", "codex turn", "third"])


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

    @staticmethod
    def _codex_rollouts():
        import session_reader
        if not session_reader.CODEX_ROOT.exists():
            return []
        return list(session_reader.CODEX_ROOT.glob("sessions/**/rollout-*.jsonl"))

    def test_real_codex_rollout_parses(self):
        files = self._codex_rollouts()
        if not files:
            self.skipTest("no Codex rollouts on this machine")
        files.sort(key=lambda p: p.stat().st_size, reverse=True)
        ir = transcript_ir.from_codex_file(files[0])
        s = transcript_ir.stats(ir)
        self.assertGreater(s["user_turns"], 0,
                           "largest rollout parsed to no operator turns")
        self.assertGreater(s["total_chars"], 0)
        # 98.2% of a real rollout's replayable text is tool I/O, so a parse
        # that lost the tool blocks would still look plausible on turn counts
        # alone. This is the assertion that would not.
        self.assertGreater(s["tool_chars"], 0,
                           "the largest rollout carries tool activity and this "
                           "parse found none")

    def test_real_codex_rollout_resolves_by_its_thread_id(self):
        """The filename-embedded id equals session_meta.session_id in 13/13
        rollouts, which is what lets resolution skip opening any file."""
        import session_reader
        files = self._codex_rollouts()
        if not files:
            self.skipTest("no Codex rollouts on this machine")
        # A UUID is five hyphen-separated groups, and the id is the tail of the
        # stem after the `rollout-<ISO timestamp>-` prefix.
        sid = "-".join(files[0].stem.split("-")[-5:])
        self.assertEqual(session_reader.codex_resolve_path(sid), files[0])
        # and the shared dispatcher reaches it, without disturbing the two
        # trees it checks first
        ir = transcript_ir.load(sid)
        self.assertIsNotNone(ir, "load() did not reach the codex tree")
        self.assertEqual(ir["provider"], "codex")

    def test_no_unrecognised_response_item_type_in_a_real_rollout(self):
        """THE CANARY, and the one unmeasured risk in the Codex parser.

        models_cache.json declares `tool_mode: code_mode_only` for the two
        current models but `None` for gpt-5.5. If a model emits its tool calls
        as some other response_item type -- the classic `function_call` /
        `local_shell_call` shapes, say -- from_codex_file would drop them and
        produce a replay with NO TOOL ACTIVITY that still reports success,
        losing 98.2% of the content silently.

        Guessing at those wire formats is what this codebase refuses to do
        about a provider it has not measured. Failing the moment such a record
        appears on disk is the honest alternative: it turns a silent
        content-loss bug into a test failure naming the type to go and measure.
        """
        files = self._codex_rollouts()
        if not files:
            self.skipTest("no Codex rollouts on this machine")
        unknown = {}
        for f in files:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(d, dict) or d.get("type") != "response_item":
                        continue
                    p = d.get("payload")
                    if not isinstance(p, dict):
                        continue
                    t = p.get("type")
                    if t not in transcript_ir._CODEX_ITEM_TYPES:
                        unknown.setdefault(t, 0)
                        unknown[t] += 1
        self.assertEqual(unknown, {},
                         "these response_item types are on disk and are being "
                         "dropped by from_codex_file: %r -- measure them and add "
                         "them to _CODEX_ITEM_TYPES, because a dropped tool "
                         "record is a replay that silently omits the work"
                         % (unknown,))



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
