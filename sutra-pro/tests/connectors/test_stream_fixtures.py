"""What the real streamed turns look like (work package STR-1): facts about `claude/stream_partials_tool_ok.jsonl` and `codex/exec_tool_items_ok.jsonl`, and what the
connectors' parsers make of them today. The facts are the ones the streaming design depends on (docs/design/streaming/capture-notes.md); if a new CLI version
changes one, a recapture fails here first and the design is re-read, instead of the UI being wrong."""
from __future__ import annotations

import json

from sutra_app.connectors.base import TurnPlan
from sutra_app.connectors.claude import ClaudeParser
from sutra_app.connectors.codex import CodexParser
from sutra_app.connectors.models import RouteContext
from sutra_app.connectors.process import ExitInfo

CLAUDE = "claude/stream_partials_tool_ok.jsonl"
CODEX = "codex/exec_tool_items_ok.jsonl"


def objs(fixtures, rel):
    return [json.loads(l) for l in fixtures.text(rel).split("\n")[:-1]]


def ended():
    return ExitInfo(returncode=0, reason="exit", stderr_tail="", seconds=0.1, pid=1)


def plan(partials):
    return TurnPlan(prompt="hello", ctx=RouteContext(), model="sonnet", effort="low", partials=partials, kind="chat")


# ---- Claude -----------------------------------------------------------------------------------------------------------------------

def inner(o):
    return o.get("event", {}).get("type") if o.get("type") == "stream_event" else None


def test_claude_a_tool_block_starts_with_id_and_name_and_an_empty_input(fixtures):
    start = next(o["event"] for o in objs(fixtures, CLAUDE) if inner(o) == "content_block_start" and o["event"]["content_block"]["type"] == "tool_use")
    block = start["content_block"]
    assert block["name"] == "Read" and block["id"].startswith("toolu_") and block["input"] == {} and start["index"] == 0


def test_claude_the_complete_assistant_message_arrives_before_content_block_stop(fixtures):
    """The ordering the design assumed the other way round: the assistant message (with the whole tool input) comes BEFORE the block's stop event, so the
    title and target of a tool line are known at the `tool_call` event, not at content_block_stop."""
    seq = [(i, o["type"], inner(o)) for i, o in enumerate(objs(fixtures, CLAUDE))]
    for message in ("tool_use", "text"):
        start = next(i for i, t, e in seq if e == "content_block_start" and _block_type(fixtures, i) == message)
        assistant = next(i for i, t, e in seq if t == "assistant" and i > start)
        stop = next(i for i, t, e in seq if e == "content_block_stop" and i > start)
        assert start < assistant < stop, message


def _block_type(fixtures, i):
    return objs(fixtures, CLAUDE)[i]["event"]["content_block"]["type"]


def test_claude_input_json_deltas_add_up_to_the_assistant_tool_input_and_arrive_in_one_burst(fixtures):
    L = objs(fixtures, CLAUDE)
    joined = "".join(o["event"]["delta"]["partial_json"] for o in L if inner(o) == "content_block_delta" and o["event"]["delta"]["type"] == "input_json_delta")
    use = next(b for o in L if o["type"] == "assistant" for b in o["message"]["content"] if b["type"] == "tool_use")
    assert json.loads(joined) == use["input"] and use["input"]["file_path"].endswith("notes.txt")


def test_claude_each_message_has_its_own_message_start_and_stop_and_indexes_restart_at_zero(fixtures):
    L = objs(fixtures, CLAUDE)
    kinds = [inner(o) for o in L if o["type"] == "stream_event"]
    assert kinds.count("message_start") == kinds.count("message_stop") == 2
    assert [o["event"]["index"] for o in L if inner(o) == "content_block_start"] == [0, 0]     # two assistant messages, both with index 0: indexes are per message
    types = {o["event"]["content_block"]["type"] for o in L if inner(o) == "content_block_start"}
    assert types == {"tool_use", "text"}                                                          # effort low: no thinking block in this capture


def test_claude_the_tool_result_comes_as_a_user_message_with_the_tool_use_id(fixtures):
    L = objs(fixtures, CLAUDE)
    use = next(b for o in L if o["type"] == "assistant" for b in o["message"]["content"] if b["type"] == "tool_use")
    result = next(b for o in L if o["type"] == "user" for b in o["message"]["content"] if b["type"] == "tool_result")
    assert result["tool_use_id"] == use["id"] and "launch checklist" in result["content"]


def test_claude_result_text_is_the_final_message_only(fixtures):
    L = objs(fixtures, CLAUDE)
    final = L[-1]
    texts = [b["text"] for o in L if o["type"] == "assistant" for b in o["message"]["content"] if b["type"] == "text"]
    assert final["type"] == "result" and final["result"] == texts[-1] and len(texts) == 1


def test_claude_the_parser_today_turns_the_stream_into_deltas_a_tool_call_a_result_and_the_whole_text(fixtures):
    parser = ClaudeParser(plan(True))
    events = [e for line in fixtures.text(CLAUDE).split("\n")[:-1] for e in parser.feed(line)]
    kinds = [(e.kind, e.data.get("kind")) for e in events]
    assert kinds[0] == ("started", None)
    assert [k for k, _ in kinds].count("tool_call") == 1 and [k for k, _ in kinds].count("tool_result") == 1
    assert [d for k, d in kinds if k == "text_delta"].count("json") >= 1 and [d for k, d in kinds if k == "text_delta"].count("text") >= 1
    texts = "".join(e.data["text"] for e in events if e.kind == "text_delta" and e.data.get("kind") == "text")
    whole = next(e.data["text"] for e in events if e.kind == "text")
    assert texts == whole                                  # the deltas add up to the whole message that follows them
    assert parser.finish(ended()).text == whole


def test_claude_without_partials_no_delta_is_produced(fixtures):
    parser = ClaudeParser(plan(False))
    kinds = [e.kind for line in fixtures.text(CLAUDE).split("\n")[:-1] for e in parser.feed(line)]
    assert "text_delta" not in kinds and kinds.count("text") == 1


# ---- Codex ------------------------------------------------------------------------------------------------------------------------

def test_codex_agent_messages_arrive_whole_and_only_commands_have_a_start_event(fixtures):
    L = objs(fixtures, CODEX)
    items = [(o["type"], o["item"]["type"], o["item"]["id"]) for o in L if "item" in o]
    assert not [1 for t, k, _ in items if k == "agent_message" and t != "item.completed"]          # an answer is one completed item, never started or updated
    assert [t for t, k, _ in items if k == "agent_message"].count("item.completed") >= 1
    assert [t for t, k, _ in items if k == "command_execution"] == ["item.started", "item.completed"]
    assert not any(o["type"] == "item.updated" for o in L)


def test_codex_a_command_starts_in_progress_with_no_output_and_completes_with_exit_code_and_output(fixtures):
    L = objs(fixtures, CODEX)
    start = next(o["item"] for o in L if o["type"] == "item.started")
    done = next(o["item"] for o in L if o["type"] == "item.completed" and o["item"]["type"] == "command_execution")
    assert start["status"] == "in_progress" and start["aggregated_output"] == "" and start["exit_code"] is None and start["id"] == done["id"]
    assert done["exit_code"] == 0 and "launch checklist" in done["aggregated_output"] and "notes.txt" in done["command"]


def test_codex_the_parser_today_has_text_and_tool_call_events_but_no_start_event_and_no_output(fixtures):
    parser = CodexParser(plan(False))
    events = [e for line in fixtures.text(CODEX).split("\n")[:-1] for e in parser.feed(line)]
    kinds = [e.kind for e in events]
    assert kinds[0] == "started" and kinds.count("tool_call") == 1 and kinds[-1] == "text"          # item.started is ignored; the command appears only once it has completed
    call = next(e for e in events if e.kind == "tool_call")
    assert call.data == {"type": "command_execution", "id": call.data["id"]} and "command" not in call.data
    assert parser.finish(ended()).text.startswith("The launch checklist")
