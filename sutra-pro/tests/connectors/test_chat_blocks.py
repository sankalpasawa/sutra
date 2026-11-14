"""`BlockAccumulator` (streaming design D218, work package STR-5): block ids, per-message index scoping, tool id matching, restart, the fold, freeze, the stored shape and
the settle map; and a replay of the real captured streams through the parser and the accumulator together."""
from __future__ import annotations

import json

import pytest

from sutra_app.connectors.base import TurnPlan
from sutra_app.connectors.chat_blocks import BLOCK_TEXT_MAX, FOLD_NAME, MAX_ELEMENTS, TEXT_TOTAL_MAX, BlockAccumulator
from sutra_app.connectors.claude import ClaudeParser
from sutra_app.connectors.codex import CodexParser
from sutra_app.connectors.models import ConnectorEvent, RouteContext
from sutra_app.orchestrator.live_redact import holdback_factory
from sutra_app.orchestrator.redact import Redactor


def ev(event_kind, /, **data):
    return ConnectorEvent(kind=event_kind, data=data)


def feed(acc, *events):
    out = []
    for e in events:
        out.extend(acc.feed(e))
    return out


def kinds(events):
    return [(e.kind, e.block_id) for e in events]


def text_block(index=0):
    return ev("block_start", index=index, type="text")


def delta(text):
    return ev("text_delta", text=text, kind="text")


def tool_start(tid, name="Read", index=1):
    return ev("block_start", index=index, type="tool_use", tool_id=tid, name=name)


# ---- text -------------------------------------------------------------------------------------------------------------------------

def test_a_streamed_text_block_starts_deltas_with_offsets_and_ends():
    acc = BlockAccumulator()
    out = feed(acc, ev("message_boundary"), text_block(), delta("Hel"), delta("lo"), ev("block_stop", index=0))
    assert kinds(out) == [("start", "b1"), ("delta", "b1"), ("delta", "b1"), ("end", "b1")]
    assert [e.data["offset"] for e in out if e.kind == "delta"] == [0, 3] and [e.data["delta"] for e in out if e.kind == "delta"] == ["Hel", "lo"]
    assert out[-1].data == {"status": "ok", "is_error": False, "truncated": False}
    assert acc.text() == "Hello" and acc.stored_blocks(ordered=True) == [{"type": "text", "kind": "other", "text": "Hello"}] and acc.stored_order() == ["b1"]


def test_a_delta_without_any_block_event_opens_a_text_block_from_the_first_real_byte():
    acc = BlockAccumulator()
    out = feed(acc, delta("a"), delta("b"))
    assert kinds(out) == [("start", "b1"), ("delta", "b1"), ("delta", "b1")] and out[0].data["type"] == "text"


def test_tool_input_deltas_are_never_a_pages_business():
    acc = BlockAccumulator()
    assert feed(acc, ev("text_delta", text='{"file_path": "/x"}', kind="json")) == []


def test_the_whole_text_event_is_dropped_when_deltas_of_that_message_were_seen_and_kept_otherwise():
    acc = BlockAccumulator()
    out = feed(acc, ev("message_boundary"), text_block(), delta("streamed"), ev("text", text="streamed"), ev("block_stop", index=0))
    assert [e.kind for e in out] == ["start", "delta", "end"] and acc.stored_blocks() == []                 # legacy list: no text block for a streamed message
    out = feed(acc, ev("message_boundary"), ev("text", text="whole, never streamed"))                      # the next message had no deltas
    assert [e.kind for e in out] == ["start", "end"] and out[-1].data["text"] == "whole, never streamed"
    assert acc.stored_blocks() == [{"type": "text", "kind": "other", "text": "whole, never streamed"}]
    assert [b["text"] for b in acc.stored_blocks(ordered=True)] == ["streamed", "whole, never streamed"]


def test_a_block_start_that_got_no_delta_takes_the_whole_message_instead_of_leaving_an_empty_block():
    acc = BlockAccumulator()
    out = feed(acc, ev("message_boundary"), text_block(), ev("text", text="all at once"), ev("block_stop", index=0))
    assert kinds(out) == [("start", "b1"), ("end", "b1")] and acc.stored_order() == ["b1"] and acc.text() == "all at once"


def test_two_assistant_messages_that_both_have_index_zero_do_not_collide():
    acc = BlockAccumulator()
    out = feed(acc, ev("message_boundary"), text_block(0), delta("one"), ev("block_stop", index=0),
               ev("message_boundary"), text_block(0), delta("two"), ev("block_stop", index=0))
    assert [e.block_id for e in out if e.kind == "start"] == ["b1", "b2"] and acc.text() == "onetwo"
    assert [b["text"] for b in acc.stored_blocks(ordered=True)] == ["one", "two"] and acc.stored_order() == ["b1", "b2"]


def test_saw_partial_is_per_message_not_per_turn():
    acc = BlockAccumulator()
    feed(acc, ev("message_boundary"), text_block(), delta("first message streamed"), ev("block_stop", index=0))
    feed(acc, ev("message_boundary"), ev("text", text="second message arrives whole"))
    assert acc.text() == "first message streamedsecond message arrives whole"


# ---- tools ------------------------------------------------------------------------------------------------------------------------

def test_a_tool_block_starts_with_its_name_only_and_gets_title_and_target_from_the_tool_call_that_matches_its_id():
    acc = BlockAccumulator(folder="/work/folder")
    out = feed(acc, ev("message_boundary"), tool_start("toolu_1"))
    assert kinds(out) == [("start", "b1")] and out[0].data == {"type": "tool_use", "kind": "read", "name": "Read"}      # no title yet: nothing is invented
    out = feed(acc, ev("tool_call", id="toolu_1", name="Read", input={"file_path": "/work/folder/src/a.py"}))
    assert kinds(out) == [("update", "b1")] and out[0].data == {"title": "Reading src/a.py", "target": "src/a.py"}      # relative to the turn's folder
    assert feed(acc, ev("block_stop", index=1)) == [] and acc.open_blocks() == ["b1"]                             # the input is complete, the tool is still running
    out = feed(acc, ev("tool_result", tool_use_id="toolu_1", content="1\tline", truncated=False, is_error=False))
    assert kinds(out) == [("end", "b1")] and out[0].data["status"] == "ok" and out[0].data["kind"] == "read"
    assert acc.open_blocks() == []


def test_a_tool_call_never_creates_a_second_block_for_an_id_that_is_open():
    acc = BlockAccumulator()
    feed(acc, tool_start("t1"), ev("tool_call", id="t1", name="Read", input={"file_path": "/a/b.txt"}), ev("tool_call", id="t1", name="Read", input={"file_path": "/a/b.txt"}))
    assert [b["block_id"] for b in acc.snapshot()] == ["b1"]


def test_a_tool_call_without_a_block_start_opens_the_block_with_its_title():
    acc = BlockAccumulator(folder="/w")
    out = feed(acc, ev("tool_call", id="t9", name="Bash", input={"command": "ls -la"}))
    assert [e.kind for e in out] == ["start", "update"] and out[1].data == {"title": "Running ls -la", "target": "ls -la"}


def test_block_stop_input_is_the_fallback_when_no_assistant_message_came():
    acc = BlockAccumulator(folder="/w")
    feed(acc, tool_start("t1"))
    out = feed(acc, ev("block_stop", index=1, input={"file_path": "/w/x.py"}))
    assert kinds(out) == [("update", "b1")] and out[0].data["target"] == "x.py"


def test_an_error_result_ends_the_block_in_error_and_keeps_the_result_for_the_store():
    acc = BlockAccumulator()
    feed(acc, tool_start("t1", "Bash"), ev("tool_call", id="t1", name="Bash", input={"command": "false"}))
    out = feed(acc, ev("tool_result", tool_use_id="t1", content="boom", truncated=True, is_error=True))
    assert out[0].data["status"] == "error" and out[0].data["is_error"] is True and out[0].data["truncated"] is True
    blocks = acc.stored_blocks(ordered=True)
    assert [b["type"] for b in blocks] == ["tool_use", "tool_result"] and blocks[1]["is_error"] is True and blocks[1]["truncated"] is True and acc.stored_order() == ["b1", "b1"]


def test_a_result_for_an_unknown_id_is_not_a_live_event_and_is_kept_in_the_legacy_list():
    acc = BlockAccumulator()
    assert feed(acc, ev("tool_result", tool_use_id="nobody", content="x")) == []
    assert acc.stored_blocks()[0]["type"] == "tool_result"


def test_thinking_is_presence_only():
    acc = BlockAccumulator()
    out = feed(acc, ev("message_boundary"), ev("block_start", index=0, type="thinking"), ev("text_delta", text="secret thoughts", kind="thinking"), ev("block_stop", index=0))
    assert kinds(out) == [("start", "b1"), ("end", "b1")] and out[0].data["type"] == "thinking"
    assert acc.stored_blocks(ordered=True) == [{"type": "thinking", "kind": "other", "text": ""}] and "secret" not in json.dumps(acc.snapshot())


def test_titles_and_targets_pass_the_redactor_and_are_cut():
    acc = BlockAccumulator(redact=lambda t: t.replace("hunter2-password", "[redacted]"))
    out = feed(acc, ev("tool_call", id="t", name="Bash", input={"command": "echo hunter2-password " + "x" * 400}))
    assert "hunter2" not in json.dumps([e.data for e in out]) and all(len(e.data.get("title", "")) <= 200 for e in out)


def test_codex_style_command_item_starts_with_the_command_and_completes_in_one_event():
    acc = BlockAccumulator(provider="codex", folder="/w")
    out = feed(acc, ev("block_start", index=None, type="tool_use", tool_id="item_0", name="command_execution", input={"command": "/bin/zsh -lc \"ls -la\""}))
    assert [e.kind for e in out] == ["start", "update"] and out[1].data["title"] == "Running ls -la" and out[0].data["kind"] == "run"
    out = feed(acc, ev("tool_call", type="command_execution", id="item_0"),
               ev("block_stop", index=None, tool_id="item_0", completed=True, input={"command": "ls -la"}, exit_code=2, output="nope", truncated=False))
    assert kinds(out) == [("end", "b1")] and out[0].data["status"] == "error"
    assert [b["type"] for b in acc.stored_blocks(ordered=True)] == ["tool_use", "tool_result"]


def test_an_agent_message_between_tools_is_a_whole_text_block():
    acc = BlockAccumulator(provider="codex")
    feed(acc, ev("text", text="I will look."), ev("block_start", index=None, type="tool_use", tool_id="i1", name="command_execution", input={"command": "ls"}),
         ev("block_stop", index=None, tool_id="i1", completed=True, exit_code=0, output="a", input={"command": "ls"}), ev("text", text="Done."))
    assert [b["type"] for b in acc.stored_blocks(ordered=True)] == ["text", "tool_use", "tool_result", "text"]


# ---- restart, freeze, finalize ------------------------------------------------------------------------------------------------

def test_restart_moves_the_blocks_to_an_earlier_try_and_block_ids_keep_counting():
    acc = BlockAccumulator(provider="claude", folder="/w")
    feed(acc, ev("message_boundary"), text_block(), delta("half"), tool_start("t1", "Edit"), ev("tool_call", id="t1", name="Edit", input={"file_path": "/w/a.py"}))
    out = acc.restart("Claude had a server error", "codex")
    assert [e.kind for e in out] == ["restart"] and out[0].data == {"provider": "codex", "reason": "Claude had a server error", "after_side_effects": True}
    earlier = acc.earlier_attempts()
    assert len(earlier) == 1 and earlier[0]["provider"] == "claude" and earlier[0]["lines"] == ["Editing a.py"] and earlier[0]["after_side_effects"] is True
    assert acc.stored_blocks(ordered=True) == [] and acc.text() == ""
    out = feed(acc, ev("message_boundary"), text_block(), delta("fresh"))
    assert [e.block_id for e in out if e.kind == "start"] == ["b3"]                        # b1 and b2 belonged to the earlier try: never reused
    assert acc.provider == "codex"


def test_an_attempt_that_only_read_files_is_not_marked_as_possibly_changing_them():
    acc = BlockAccumulator(folder="/w")
    feed(acc, tool_start("t1", "Read"), ev("tool_call", id="t1", name="Read", input={"file_path": "/w/a"}))
    assert acc.restart("x", "claude")[0].data["after_side_effects"] is False


def test_restart_with_nothing_before_it_records_no_earlier_try():
    acc = BlockAccumulator()
    acc.restart("x", "claude")
    assert acc.earlier_attempts() == []


def test_freeze_drops_everything_after_it_and_finalize_ends_open_tools_interrupted():
    acc = BlockAccumulator(folder="/w")
    feed(acc, ev("message_boundary"), text_block(), delta("seen"), tool_start("t1"), ev("tool_call", id="t1", name="Read", input={"file_path": "/w/a"}))
    acc.freeze()
    assert feed(acc, delta("never shown"), tool_start("t2"), ev("tool_result", tool_use_id="t1", content="x")) == []
    out = acc.finalize("interrupted")
    assert {(e.block_id, e.data["status"]) for e in out} == {("b1", "ok"), ("b2", "interrupted")}
    assert acc.text() == "seen" and acc.frozen


def test_finalize_ok_ends_a_tool_without_a_result_as_ok_and_open_text_as_ok():
    acc = BlockAccumulator()
    feed(acc, text_block(), delta("x"), tool_start("t1"))
    assert {e.data["status"] for e in acc.finalize("ok")} == {"ok"}


def test_finalize_releases_the_held_tail_of_a_text_filter_unless_frozen():
    r = Redactor(environ={}, extra=("hunter2-password",))
    live = BlockAccumulator(text_filter=holdback_factory(r))
    out = feed(live, text_block(), delta("the hunter2"))
    assert "".join(e.data["delta"] for e in out if e.kind == "delta") == "the "
    done = live.finalize("ok")
    assert [e.data["delta"] for e in done if e.kind == "delta"] == ["hunter2"] and live.text() == "the hunter2"
    stopped = BlockAccumulator(text_filter=holdback_factory(r))
    feed(stopped, text_block(), delta("the hunter2"))
    stopped.freeze()
    assert [e.kind for e in stopped.finalize("interrupted") if e.kind == "delta"] == [] and stopped.text() == "the "


def test_stored_text_is_exactly_the_emitted_text_with_a_secret_split_across_deltas():
    r = Redactor(environ={}, extra=("hunter2-password",))
    acc = BlockAccumulator(text_filter=holdback_factory(r))
    out = feed(acc, text_block(), delta("my pass"), delta("word is hunter2-"), delta("password, ok"), ev("block_stop", index=0))
    shown = "".join(e.data["delta"] for e in out if e.kind == "delta")
    assert "hunter2-password" not in shown and shown == acc.text() == "my password is [redacted], ok"


# ---- the fold and the caps ------------------------------------------------------------------------------------------------------

def many_tools(acc, n, result=True):
    out = []
    for i in range(n):
        out += feed(acc, tool_start(f"t{i}", "Read", index=i), ev("tool_call", id=f"t{i}", name="Read", input={"file_path": f"/w/f{i}.txt"}))
        if result:
            out += feed(acc, ev("tool_result", tool_use_id=f"t{i}", content="x", truncated=False, is_error=False))
    return out


def test_tool_units_fold_after_the_cap_and_never_split_a_call_from_its_result():
    acc = BlockAccumulator(folder="/w", max_elements=20)
    out = many_tools(acc, 50)
    blocks = acc.stored_blocks(ordered=True)
    assert len(blocks) <= 20
    types = [b["type"] for b in blocks]
    assert types.count("tool_use") == types.count("tool_result") + 1                  # every unit is a pair, except the fold block, which has no result
    fold = [b for b in blocks if b["name"] == FOLD_NAME]
    assert len(fold) == 1 and fold[0]["truncated"] is True and fold[0]["text"].endswith("more tool calls not listed")
    shown = len([b for b in blocks if b["type"] == "tool_use"]) - 1
    assert fold[0]["text"] == f"{50 - shown} more tool calls not listed"
    assert len(acc.stored_order()) == len(blocks)
    live_fold = [e for e in out if e.kind == "update" and "more tool calls" in e.data.get("title", "")]
    assert live_fold and live_fold[-1].data["title"] == fold[0]["text"]               # the live fold item says what the stored one says


def test_a_folded_call_that_gets_its_tool_call_later_is_counted_once():
    acc = BlockAccumulator(max_elements=8)
    for i in range(6):
        feed(acc, tool_start(f"t{i}", index=i))
    for i in range(6):
        feed(acc, ev("tool_call", id=f"t{i}", name="Read", input={"file_path": f"/w/{i}"}))
    fold = [b for b in acc.stored_blocks(ordered=True) if b["name"] == FOLD_NAME]
    assert len(fold) == 1 and fold[0]["text"] == f"{6 - (len([1 for b in acc.stored_blocks(ordered=True) if b['type'] == 'tool_use']) - 1)} more tool calls not listed"


def test_default_cap_keeps_a_long_turn_under_the_read_model_limit_of_500():
    acc = BlockAccumulator(folder="/w")
    many_tools(acc, 600)
    assert len(acc.stored_blocks(ordered=True)) <= MAX_ELEMENTS and MAX_ELEMENTS < 500


def test_text_past_the_cap_is_appended_to_the_last_text_block():
    acc = BlockAccumulator(max_elements=6)
    feed(acc, ev("message_boundary"), text_block(), delta("a"), ev("block_stop", index=0))
    many_tools(acc, 3)
    out = feed(acc, ev("message_boundary"), text_block(0), delta("tail"))
    assert [e.kind for e in out] == ["delta"] and out[0].block_id == "b1"
    assert acc.stored_blocks(ordered=True)[0]["text"] == "atail"


def test_a_long_text_is_cut_into_blocks_of_at_most_the_block_limit_and_the_total_is_capped():
    acc = BlockAccumulator()
    feed(acc, text_block(), delta("x" * (TEXT_TOTAL_MAX + 5000)))
    blocks = acc.stored_blocks(ordered=True)
    assert all(len(b["text"]) <= BLOCK_TEXT_MAX for b in blocks) and sum(len(b["text"]) for b in blocks) == TEXT_TOTAL_MAX
    assert blocks[-1].get("truncated") is True and len(acc.stored_order()) == len(blocks) == 2


def test_stored_order_always_matches_the_stored_blocks_one_to_one():
    acc = BlockAccumulator(folder="/w")
    feed(acc, ev("message_boundary"), ev("block_start", index=0, type="thinking"), ev("block_stop", index=0), text_block(1), delta("hi"), ev("block_stop", index=1))
    many_tools(acc, 3)
    feed(acc, ev("message_boundary"), text_block(0), delta("bye"))
    assert len(acc.stored_order()) == len(acc.stored_blocks(ordered=True)) and acc.stored_order()[0] == "b1"


def test_the_legacy_list_is_what_the_port_always_returned():
    acc = BlockAccumulator()
    feed(acc, ev("tool_call", id="t1", name="Bash", input={"command": "ls"}), ev("tool_result", tool_use_id="t1", content="a\nb", truncated=True, is_error=False),
         ev("tool_call", id="t2", name="Zap", input={}))
    got = acc.stored_blocks()
    assert got[0] == {"type": "tool_use", "kind": "run", "name": "Bash", "text": "ls"}
    assert got[1]["kind"] == "run" and got[1]["name"] == "Bash" and got[1]["truncated"] is True and got[2]["kind"] == "other"


# ---- the real captured streams, parser and accumulator together ----------------------------------------------------------------

def plan(kind, partials):
    return TurnPlan(prompt="x", ctx=RouteContext(), model="m", effort="low", partials=partials, kind=kind)


def replay(fixtures, rel, parser, acc):
    out = []
    for line in fixtures.text(rel).split("\n")[:-1]:
        for event in parser.feed(line):
            out.extend(acc.feed(event))
    return out


def test_the_real_claude_tool_turn_becomes_a_tool_line_with_a_relative_target_then_text(fixtures):
    acc = BlockAccumulator(folder="/scratch/probe/folder", provider="claude")
    out = replay(fixtures, "claude/stream_partials_tool_ok.jsonl", ClaudeParser(plan("chat", True)), acc)
    assert kinds(out)[:1] == [("start", "b1")] and out[0].data == {"type": "tool_use", "kind": "read", "name": "Read"}
    update = next(e for e in out if e.kind == "update")
    assert update.data == {"title": "Reading notes.txt", "target": "notes.txt"}                                  # `/scratch/probe/folder/notes.txt` relative to the folder
    assert [e.kind for e in out if e.block_id == "b1"] == ["start", "update", "end"]
    text_events = [e for e in out if e.block_id == "b2"]
    assert text_events[0].kind == "start" and text_events[0].data["type"] == "text" and text_events[-1].kind == "end"
    answer = json.loads(fixtures.text("claude/stream_partials_tool_ok.jsonl").split("\n")[-2])["result"]
    assert "".join(e.data["delta"] for e in text_events if e.kind == "delta") == acc.text() == answer and "launch checklist" in answer
    assert [b["type"] for b in acc.stored_blocks(ordered=True)] == ["tool_use", "tool_result", "text"] and acc.stored_order() == ["b1", "b1", "b2"]
    assert [b["type"] for b in acc.stored_blocks()] == ["tool_use", "tool_result"]                                 # the legacy list has no streamed text block


def test_the_real_codex_turn_becomes_a_command_line_and_a_whole_answer(fixtures):
    acc = BlockAccumulator(folder="/scratch/probe/folder", provider="codex")
    out = replay(fixtures, "codex/exec_tool_items_ok.jsonl", CodexParser(plan("chat", False)), acc)
    start = next(e for e in out if e.kind == "start" and e.data["type"] == "tool_use")
    assert start.data["kind"] == "run" and start.data["name"] == "command_execution"
    update = next(e for e in out if e.kind == "update")
    assert update.data["title"] == "Running sed -n '1,120p' notes.txt"
    ended = [e for e in out if e.kind == "end"]
    assert ended[0].data["status"] == "ok" and ended[-1].data["text"].startswith("The launch checklist")           # the answer arrives whole
    assert not [e for e in out if e.kind == "delta"]
