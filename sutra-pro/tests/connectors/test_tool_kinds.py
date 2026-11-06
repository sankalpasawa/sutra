"""Tool-kind classification and typed block events (work package ABS-5)."""
from __future__ import annotations

import pytest

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.models import ConnectorEvent
from sutra_app.connectors.tool_kinds import KINDS, classify, title_of
from test_chat_port import make


@pytest.mark.parametrize("name,kind", [("Bash", "run"), ("Edit", "edit"), ("Write", "edit"), ("Read", "read"), ("Grep", "search"),
                                       ("Glob", "search"), ("WebFetch", "web"), ("WebSearch", "web"), ("mcp__sutra__x", "other"),
                                       ("BrandNewTool", "other"), ("", "other"), (None, "other")])
def test_claude_names(name, kind):
    assert classify(name) == kind and kind in KINDS


@pytest.mark.parametrize("name,kind", [("command_execution", "run"), ("file_change", "edit"), ("web_search", "web"), ("mystery", "other")])
def test_codex_item_types(name, kind):
    assert classify(name, provider="codex") == kind


def test_classify_never_raises_on_odd_input():
    assert classify(object()) == "other" and title_of("Bash", ["not", "a", "dict"]) == "Bash"


def test_titles_are_the_command_the_file_or_the_query():
    assert title_of("Bash", {"command": "ls   -la\n/tmp"}) == "ls -la /tmp"
    assert title_of("Read", {"file_path": "/a/b/notes.md"}) == "notes.md"
    assert title_of("WebSearch", {"query": "q"}) == "q"
    assert len(title_of("Bash", {"command": "x" * 500})) == 161


def test_the_port_turns_tool_events_into_typed_blocks_and_the_result_keeps_them(tmp_path):
    port, router, *_ = make(tmp_path)
    events = [ConnectorEvent(kind="tool_call", data={"id": "t1", "name": "Bash", "input": {"command": "ls"}}),
              ConnectorEvent(kind="tool_result", data={"tool_use_id": "t1", "content": "a\nb", "truncated": True, "is_error": False}),
              ConnectorEvent(kind="tool_call", data={"id": "t2", "name": "Zap", "input": {}})]
    kinds: dict = {}
    mapped = [port._map(e, False, kinds, "claude").data for e in events]
    assert mapped[0] == {"type": "tool_use", "kind": "run", "name": "Bash", "text": "ls"}
    assert mapped[1]["kind"] == "run" and mapped[1]["name"] == "Bash" and mapped[1]["truncated"] is True
    assert mapped[2]["kind"] == "other"


def test_a_stream_collects_blocks_into_turn_done(tmp_path):
    port = make(tmp_path)[0]
    done = list(port.stream("cs_k1", ChatTurnIn(text="hi")))[-1]
    assert isinstance(done.data["blocks"], list)
