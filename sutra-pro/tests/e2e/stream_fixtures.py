"""Streamed Claude turns for the browser tests of the live chat (streaming design STR-13): a JSONL file the fake `claude` replays line by line (`file:<path>` scenario).

The lines are made from the captured real turn (`tests/fixtures/connectors/claude/stream_partials_tool_ok.jsonl`, STR-1): the envelope, the ids and the shape of every event
are the real ones, only the words, the tool calls and their results are the test's. So the connector, the accumulator and the page see what they see from the real CLI.

    path = write_turn(tmp / "tool.jsonl", [Think(), Tool("Read", {"file_path": "notes.txt"}, "1\\tscratch"), Text("The checklist has three items.")])
"""
from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CAPTURE = REPO / "tests" / "fixtures" / "connectors" / "claude" / "stream_partials_tool_ok.jsonl"


@dataclass
class Think:
    """A thinking block: presence only (its text never leaves the server)."""
    text: str = "Let me think about this."


@dataclass
class Tool:
    name: str
    input: dict
    result: str = ""
    is_error: bool = False


@dataclass
class Text:
    text: str
    pieces: int = 4


@dataclass
class Fail:
    """The turn ends with an error result instead of an answer."""
    message: str = "The model could not answer."


Step = Any


def _lines() -> list[dict]:
    return [json.loads(line) for line in CAPTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


def _split(text: str, pieces: int) -> list[str]:
    pieces = max(1, min(pieces, len(text)))
    size = max(1, -(-len(text) // pieces))
    return [text[i:i + size] for i in range(0, len(text), size)]


def write_turn(path: Path, steps: list[Step]) -> str:
    """Write the JSONL of a turn made of `steps`; returns the `file:<path>` scenario name for FAKE_CLAUDE_SEQUENCE."""
    base = _lines()
    session = str(uuid.uuid4())

    def retag(event: dict, msg: str | None = None) -> dict:
        out = copy.deepcopy(event)
        out["session_id"] = session
        out["uuid"] = str(uuid.uuid4())
        if msg is not None and "api_message_id" in out:
            out["api_message_id"] = msg
        return out

    out: list[dict] = [retag(base[0]), retag(base[1])]
    answer: list[str] = []
    failure = None
    index_of_message = 0
    for step in steps:
        if isinstance(step, Fail):
            failure = step.message
            continue
        index_of_message += 1
        msg = "msg_%024d" % index_of_message
        start = retag(base[2], msg)
        start["event"]["message"]["id"] = msg
        out.append(start)
        if isinstance(step, Think):
            out.append(retag({**base[3], "event": {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}}}, msg))
            out.append(retag({**base[3], "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": step.text}}}, msg))
            out.append(retag(base[12], msg))
        elif isinstance(step, Tool):
            tool_id = "toolu_%024d" % index_of_message
            block = copy.deepcopy(base[3])
            block["event"]["content_block"].update({"id": tool_id, "name": step.name, "input": {}})
            out.append(retag(block, msg))
            encoded = json.dumps(step.input)
            for piece in _split(encoded, 5):
                delta = copy.deepcopy(base[5])
                delta["event"]["delta"]["partial_json"] = piece
                out.append(retag(delta, msg))
            full = copy.deepcopy(base[11])
            full["message"]["id"] = msg
            full["message"]["content"] = [{"type": "tool_use", "id": tool_id, "name": step.name, "input": step.input, "caller": {"type": "direct"}}]
            out.append(retag(full, msg))
            out.append(retag(base[12], msg))
            delta_line = copy.deepcopy(base[13])
            out.append(retag(delta_line, msg))
            out.append(retag(base[14], msg))
            result = copy.deepcopy(base[16])
            result["message"]["content"] = [{"tool_use_id": tool_id, "type": "tool_result", "content": step.result, **({"is_error": True} if step.is_error else {})}]
            result["tool_result_meta"] = [{"id": tool_id}]
            out.append(retag(result))
            out.append(retag(base[17]))
        elif isinstance(step, Text):
            answer.append(step.text)
            out.append(retag(base[19], msg))
            for piece in _split(step.text, step.pieces):
                delta = copy.deepcopy(base[20])
                delta["event"]["delta"]["text"] = piece
                out.append(retag(delta, msg))
            full = copy.deepcopy(base[24])
            full["message"]["id"] = msg
            full["message"]["content"] = [{"type": "text", "text": step.text}]
            out.append(retag(full, msg))
            out.append(retag(base[25], msg))
            out.append(retag(base[26], msg))
            out.append(retag(base[27], msg))
    final = copy.deepcopy(base[28])
    final["session_id"] = session
    final["uuid"] = str(uuid.uuid4())
    final["result"] = failure if failure is not None else "".join(answer)
    if failure is not None:
        final.update({"is_error": True, "subtype": "error_during_execution", "terminal_reason": "error"})
    out.append(final)
    path.write_text("\n".join(json.dumps(line) for line in out) + "\n", encoding="utf-8")
    return "file:" + str(path)
