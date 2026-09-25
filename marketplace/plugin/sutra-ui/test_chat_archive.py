"""test_chat_archive.py -- archive is a mark in Sutra's store, never a file move.

Founder, 2026-09-25: archived chats fold away in Recent; "no changes in the base
layers"; the x archives; an agent may archive on its own; nothing archives on a
timer; a chat that goes live comes back by itself; clicking an archived chat
reopens it; everything archived for now except the chats open in a terminal.

Pins the one rule in chat_archive.state, the three events, the terminal-open
reader, and that the API marks rows and never touches a transcript.

Run: .venv/bin/python -m pytest -q test_chat_archive.py
"""
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chat_archive as ca  # noqa: E402


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_UI_CHAT_ARCHIVE", str(tmp_path / "chat-archive.json"))
    monkeypatch.setattr(ca, "_CLAUDE_SESSIONS", tmp_path / "claude-sessions")
    yield tmp_path


def test_nothing_is_archived_by_default():
    assert ca.state("a", 100) == (False, None)


def test_archive_marks_and_names_who():
    ca.archive("a", "you", now=200)
    assert ca.state("a", 100) == (True, "you")
    ca.archive("b", "Shadow", now=200)
    assert ca.state("b", 100) == (True, "Shadow")


def test_a_write_after_archive_brings_the_chat_back_by_itself():
    ca.archive("a", now=200)
    assert ca.state("a", 250) == (False, None)      # went live: out of Archived


def test_unarchive_wins_over_an_older_archive():
    ca.archive("a", now=200)
    ca.unarchive("a", now=300)
    assert ca.state("a", 100) == (False, None)
    ca.archive("a", now=400)                        # and a newer archive wins again
    assert ca.state("a", 100) == (True, "you")


def test_baseline_archives_everything_older_except_kept():
    ca.baseline(keep={"open"}, now=500)
    assert ca.state("old", 100) == (True, None)     # swept by the baseline, no "by"
    assert ca.state("open", 100) == (False, None)   # open in a terminal: kept active
    assert ca.state("new", 600) == (False, None)    # touched after the sweep


def test_nothing_archives_on_a_timer():
    # No event, however old the chat: never archived.
    assert ca.state("ancient", 1) == (False, None)


def test_a_broken_store_hides_nothing(_store):
    Path(os.environ["SUTRA_UI_CHAT_ARCHIVE"]).write_text("{not json", encoding="utf-8")
    assert ca.state("a", 1) == (False, None)
    ca.archive("a", now=5)                          # and the next write repairs it
    assert ca.state("a", 1) == (True, "you")


def test_open_in_terminal_reads_live_claude_windows_only(_store):
    d = _store / "claude-sessions"
    d.mkdir()
    (d / "1.json").write_text(json.dumps({"pid": os.getpid(), "sessionId": "alive"}))
    (d / "2.json").write_text(json.dumps({"pid": 999999, "sessionId": "gone"}))
    (d / "3.json").write_text("{broken")
    assert ca.open_in_terminal() == {"alive"}


def test_baseline_default_keeps_terminal_open_chats(_store):
    d = _store / "claude-sessions"
    d.mkdir()
    (d / "1.json").write_text(json.dumps({"pid": os.getpid(), "sessionId": "mine"}))
    out = ca.baseline(now=500)
    assert out["kept"] == ["mine"]
    assert ca.state("mine", 1) == (False, None)
    assert ca.state("other", 1) == (True, None)


# ---- the API: rows carry the mark; archive never moves a file -------------

def test_api_marks_rows_and_never_relocates(monkeypatch):
    import app
    monkeypatch.setattr(app.sr, "resolve_path", lambda sid: Path("/p/%s.jsonl" % sid))
    moved = []
    monkeypatch.setattr(app.sr, "relocate", lambda *a: moved.append(a))
    r = app.api_session_archive("s1", by="Shadow")
    assert r["ok"] and r["archived"] and r["by"] == "Shadow"
    assert moved == [], "archive must not move the transcript"
    rows = app._with_archive([{"id": "s1", "mtime": 1}, {"id": "s2", "mtime": 1}])
    assert rows[0]["archived"] is True and rows[0]["archived_by"] == "Shadow"
    assert rows[1]["archived"] is False
    app.api_session_unarchive("s1")
    assert app._with_archive([{"id": "s1", "mtime": 1}])[0]["archived"] is False


def test_api_404_for_an_unknown_chat(monkeypatch):
    import app
    monkeypatch.setattr(app.sr, "resolve_path", lambda sid: None)
    with pytest.raises(app.HTTPException):
        app.api_session_archive("nope")
    with pytest.raises(app.HTTPException):
        app.api_session_unarchive("nope")
