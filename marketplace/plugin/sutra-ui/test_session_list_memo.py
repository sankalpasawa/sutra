"""test_session_list_memo.py -- a rail refresh costs stats, not parses.

THE SLOWNESS THIS PINS (founder, 2026-09-15: "the Mac app is a little slow").
Measured live on the founder's machine, backend at 58-85% CPU with nobody
touching the app, five worker threads running flat out:

    list_sessions(limit=2000)   5.4 s   1494 rows, every transcript header
                                        re-read and re-parsed on every call
    list_agents(<open pane>)    0.9 s   113 agent transcripts fully re-parsed
                                        every 1.5 s while any agent is live

Both are asked for repeatedly: the rail refreshes on every write to a chat
Shadow is driving (four headless runtimes were writing at the time) and the
open pane refreshes its agent fold on every subagent write. Neither call has
to read a file whose (mtime_ns, size) has not moved. This file pins that:

  1. a second identical list_sessions() opens NO transcript;
  2. a title record appended to one transcript changes ONLY that row, and
     the rows handed out are copies (a caller decorating a row must not
     decorate the memo);
  3. a second identical list_agents() parses NO transcript, an agent that
     grew is re-parsed alone, and `running` still follows the clock.

Reads only. No server, no CLI, no network.

Run: .venv/bin/python -m pytest -q test_session_list_memo.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import session_reader as sr  # noqa: E402

SID_A = "aaaaaaaa-1111-4111-8111-111111111111"
SID_B = "bbbbbbbb-2222-4222-8222-222222222222"


def _rec(role, text, **extra):
    d = {"type": role, "message": {"role": role, "content": text},
         "timestamp": "t", "cwd": "/w", "gitBranch": "main"}
    d.update(extra)
    return json.dumps(d) + "\n"


def _task_call(prompt, description):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "c1", "name": "Task",
         "input": {"prompt": prompt, "description": description, "subagent_type": "Explore"}}]},
        "timestamp": "t"}) + "\n"


def _bump(p):
    """Make sure mtime moves even when two writes land in the same tick."""
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


class _Opens:
    """Counts Path.open calls on transcript files. Implementation-agnostic:
    whatever memo shape session_reader picks, an unchanged file must not be opened."""

    def __init__(self):
        self.paths = []
        self._orig = Path.open

    def __enter__(self):
        spy = self

        def _open(self_, *a, **k):
            if str(self_).endswith(".jsonl"):
                spy.paths.append(str(self_))
            return spy._orig(self_, *a, **k)
        self._patch = mock.patch.object(Path, "open", _open)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()


def _roots(tmp):
    projects = Path(tmp) / "projects"
    (projects / "proj").mkdir(parents=True)
    empty = Path(tmp) / "none"
    return mock.patch.multiple(sr, PROJECTS=projects, GEMINI_ROOT=empty / "g", CODEX_ROOT=empty / "c")


def _reset():
    for name in dir(sr):
        if name.endswith("_CACHE") and isinstance(getattr(sr, name), dict):
            getattr(sr, name).clear()


# ------------------------------------------------------------ list_sessions --

def test_second_list_sessions_opens_no_transcript():
    with tempfile.TemporaryDirectory() as tmp, _roots(tmp):
        for sid, text in ((SID_A, "first chat"), (SID_B, "second chat")):
            (sr.PROJECTS / "proj" / (sid + ".jsonl")).write_text(_rec("user", text), encoding="utf-8")
        _reset()
        with _Opens() as first:
            rows1 = sr.list_sessions(limit=50)
        assert sorted(r["title"] for r in rows1) == ["first chat", "second chat"]
        assert len(first.paths) >= 2, "the first list must read the titles"
        with _Opens() as second:
            rows2 = sr.list_sessions(limit=50)
        assert second.paths == [], "nothing changed: no transcript may be opened"
        assert rows2 == rows1


def test_a_rename_reaches_only_its_own_row_and_rows_are_copies():
    with tempfile.TemporaryDirectory() as tmp, _roots(tmp):
        pa = sr.PROJECTS / "proj" / (SID_A + ".jsonl")
        pb = sr.PROJECTS / "proj" / (SID_B + ".jsonl")
        pa.write_text(_rec("user", "first chat"), encoding="utf-8")
        pb.write_text(_rec("user", "second chat"), encoding="utf-8")
        _reset()
        rows = sr.list_sessions(limit=50)
        row_a = next(r for r in rows if r["id"] == SID_A)
        row_a["decorated"] = True                     # what app.py does to every row
        with pa.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "custom-title", "customTitle": "Renamed"}) + "\n")
        _bump(pa)
        with _Opens() as again:
            rows = sr.list_sessions(limit=50)
        assert again.paths == [str(pa)], "only the transcript that moved is re-read"
        by_id = {r["id"]: r for r in rows}
        assert by_id[SID_A]["title"] == "Renamed"
        assert by_id[SID_A]["title_source"] == "custom"
        assert by_id[SID_B]["title"] == "second chat"
        assert "decorated" not in by_id[SID_A], "a row handed out is a copy, not the memo"


# -------------------------------------------------------------- list_agents --

def _agents_tree(tmp, n=3):
    parent = sr.PROJECTS / "proj" / (SID_A + ".jsonl")
    parent.write_text(_rec("user", "parent chat")
                      + _task_call("scan the tree for gates", "Scan gates"), encoding="utf-8")
    sub = sr.PROJECTS / "proj" / SID_A / "subagents"
    sub.mkdir(parents=True)
    files = []
    for i in range(n):
        f = sub / ("agent-%02d.jsonl" % i)
        prompt = "scan the tree for gates" if i == 0 else "agent %d prompt" % i
        f.write_text(_rec("user", prompt) + _rec("assistant", "step one"), encoding="utf-8")
        files.append(f)
    return parent, files


def test_second_list_agents_parses_nothing_and_a_grown_agent_is_parsed_alone():
    with tempfile.TemporaryDirectory() as tmp, _roots(tmp):
        parent, files = _agents_tree(tmp)
        _reset()
        with mock.patch.object(sr, "_parse_transcript", wraps=sr._parse_transcript) as parse:
            first = sr.list_agents(SID_A)
            assert len(first) == 3
            assert parse.call_count == 3, "the first listing parses every agent once"
            parse.reset_mock()
            second = sr.list_agents(SID_A)
            assert parse.call_count == 0, "nothing changed: no agent transcript is parsed"
            assert second == first
            # one agent takes another step
            with files[1].open("a", encoding="utf-8") as fh:
                fh.write(_rec("assistant", "step two"))
            _bump(files[1])
            parse.reset_mock()
            third = sr.list_agents(SID_A)
            assert parse.call_count == 1, "only the agent that grew is re-parsed"
            grown = next(a for a in third if a["id"] == files[1].stem)
            assert grown["steps"] == 2
            assert next(a for a in third if a["id"] == files[0].stem)["steps"] == 1


def test_list_agents_title_follows_the_parent_and_running_follows_the_clock():
    with tempfile.TemporaryDirectory() as tmp, _roots(tmp):
        parent, files = _agents_tree(tmp, n=2)
        _reset()
        first = sr.list_agents(SID_A)
        a0 = next(a for a in first if a["id"] == files[0].stem)
        assert a0["title"] == "Scan gates", "matched to the parent's Task description"
        assert a0["agent_type"] == "Explore"
        a1 = next(a for a in first if a["id"] == files[1].stem)
        assert a1["title"] == "agent 1 prompt", "no Task yet: derived from the prompt"
        # the parent later records the Task that spawned agent 1
        with parent.open("a", encoding="utf-8") as fh:
            fh.write(_task_call("agent 1 prompt", "Second agent"))
        _bump(parent)
        second = sr.list_agents(SID_A)
        assert next(a for a in second if a["id"] == files[1].stem)["title"] == "Second agent"
        # liveness is a function of the clock, never of the memo
        assert all(a["running"] for a in second), "just written: active"
        old = time.time() - 10 * 60
        for f in files:
            os.utime(f, (old, old))
        third = sr.list_agents(SID_A)
        assert not any(a["running"] for a in third), "ten minutes silent: not running"
