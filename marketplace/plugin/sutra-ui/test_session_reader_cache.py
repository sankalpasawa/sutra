"""test_session_reader_cache.py -- the incremental transcript memo behind
GET /api/sessions/{sid} (speed unit, 2026-09-15): an appended file is read
from where the last read stopped, a rewritten or shrunk file is parsed from
zero, a half-written last line waits, and the answer always equals a full parse.

Run: .venv/bin/python -m pytest -q test_session_reader_cache.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import session_reader as sr  # noqa: E402


def _rec(role, text, ts="t", **extra):
    d = {"type": role, "message": {"role": role, "content": text}, "timestamp": ts, "cwd": "/w", "gitBranch": "main"}
    d.update(extra)
    return json.dumps(d) + "\n"


def _tool_call(cid, name, inp):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": cid, "name": name, "input": inp}]}, "timestamp": "t"}) + "\n"


def _tool_result(cid, out):
    return json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": cid, "content": out}]}}) + "\n"


def _bump(p):
    """Make sure mtime moves even when two writes land in the same tick."""
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def test_append_equals_full_parse_and_reads_only_the_tail():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s.jsonl"
        p.write_text(_rec("user", "hello") + _tool_call("c1", "Bash", {"command": "ls"}), encoding="utf-8")
        sr._PARSE_CACHE.clear()
        a = sr._parse_transcript_incremental(p)
        assert [m["role"] for m in a["messages"]] == ["user", "assistant"]
        assert a["messages"][1]["calls"][0].get("output") is None, "no result yet"
        assert a == sr._parse_transcript(p)
        first_offset = sr._PARSE_CACHE[str(p)]["offset"]
        # the result for c1 and a new turn arrive later
        with p.open("a", encoding="utf-8") as fh:
            fh.write(_tool_result("c1", "a b c") + _rec("assistant", "done"))
        _bump(p)
        b = sr._parse_transcript_incremental(p)
        assert b == sr._parse_transcript(p), "incremental == full parse after an append"
        assert b["messages"][1]["calls"][0]["output"] == "a b c", "a later result is attached to the earlier call"
        assert sr._PARSE_CACHE[str(p)]["offset"] > first_offset
        # nothing changed: the memo answers without re-reading (offset unchanged, same answer)
        c = sr._parse_transcript_incremental(p)
        assert c == b


def test_partial_last_line_waits_for_the_writer():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s.jsonl"
        full = _rec("user", "one")
        p.write_text(full + '{"type":"user","message":{"role":"user","content":"tw', encoding="utf-8")
        sr._PARSE_CACHE.clear()
        a = sr._parse_transcript_incremental(p)
        assert [m["text"] for m in a["messages"]] == ["one"], "the half-written record is not a turn yet"
        with p.open("a", encoding="utf-8") as fh:
            fh.write('o"},"timestamp":"t"}\n')
        _bump(p)
        b = sr._parse_transcript_incremental(p)
        assert [m["text"] for m in b["messages"]] == ["one", "two"]
        assert b == sr._parse_transcript(p)


def test_rewrite_or_shrink_reparses_from_zero():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s.jsonl"
        p.write_text(_rec("user", "alpha") + _rec("user", "beta") + _rec("user", "gamma"), encoding="utf-8")
        sr._PARSE_CACHE.clear()
        sr._parse_transcript_incremental(p)
        p.write_text(_rec("user", "only"), encoding="utf-8")           # shrunk
        _bump(p)
        a = sr._parse_transcript_incremental(p)
        assert [m["text"] for m in a["messages"]] == ["only"]
        # same size, different content, newer mtime: still a re-parse, never an append
        p.write_text(_rec("user", "othr"), encoding="utf-8")
        time.sleep(0.01); _bump(p)
        st = os.stat(p)
        # force the memo to look like an older, equal-size snapshot to prove the rule is mtime OR size
        sr._PARSE_CACHE[str(p)]["mtime_ns"] = st.st_mtime_ns + 5
        b = sr._parse_transcript_incremental(p)
        assert [m["text"] for m in b["messages"]] == ["othr"]


def test_read_session_uses_the_memo_and_returns_fresh_dicts(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        proj.mkdir()
        p = proj / "abc.jsonl"
        p.write_text(_rec("user", "hi") + _tool_call("c9", "Read", {"file_path": "/x"}), encoding="utf-8")
        monkeypatch.setattr(sr, "PROJECTS", Path(tmp))
        sr._PARSE_CACHE.clear()
        one = sr.read_session("abc")
        one["messages"][0]["text"] = "mutated by a caller"
        two = sr.read_session("abc")
        assert two["messages"][0]["text"] == "hi", "the memo is never handed out"
        assert two["id"] == "abc" and two["cwd"] == "/w"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
