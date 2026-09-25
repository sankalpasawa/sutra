"""test_chat_archive.py -- archive is a mark in Sutra's store, never a file move.

Founder, 2026-09-25: archived chats fold away in Recent; "no changes in the base
layers"; the x archives; an agent may archive on its own; nothing archives on a
timer; a chat that goes live comes back by itself; clicking an archived chat
reopens it. Later the same day: "it should only be driven by the app and
nothing else" -- the baseline sweep and the terminal watch are gone; only an
archive mark from the app archives a chat.

Pins the one rule in chat_archive.state, the two events, that the removed sweep
stays removed, and that the API marks rows and never touches a transcript.

Run: .venv/bin/python -m pytest -q test_chat_archive.py
"""
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


def test_nothing_archives_on_a_timer():
    # No event, however old the chat: never archived.
    assert ca.state("ancient", 1) == (False, None)


def test_only_the_app_archives_no_sweep_no_terminal_watch():
    # The sweep and the terminal reader are gone for good (founder, 2026-09-25).
    assert not hasattr(ca, "baseline")
    assert not hasattr(ca, "open_in_terminal")
    assert "baseline" not in ca._empty()


def test_an_old_store_baseline_is_ignored(_store):
    # A store written by the removed sweep still loads, and its sweep archives
    # nothing: a chat with no mark of its own is active.
    Path(os.environ["SUTRA_UI_CHAT_ARCHIVE"]).write_text(
        '{"v": 1, "baseline": 500, "marks": {"m": {"at": 600, "by": "you"}}, "unarchived": {}}',
        encoding="utf-8")
    assert ca.state("swept", 100) == (False, None)
    assert ca.state("m", 100) == (True, "you")
    ca.archive("n", now=700)                        # a write drops the dead key
    assert "baseline" not in ca.load()


def test_a_broken_store_hides_nothing(_store):
    Path(os.environ["SUTRA_UI_CHAT_ARCHIVE"]).write_text("{not json", encoding="utf-8")
    assert ca.state("a", 1) == (False, None)
    ca.archive("a", now=5)                          # and the next write repairs it
    assert ca.state("a", 1) == (True, "you")


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


def test_api_has_no_archive_all():
    import app
    assert not hasattr(app, "api_chats_archive_all")
    assert all(getattr(r, "path", "") != "/api/chats/archive-all" for r in app.app.routes)


def test_api_404_for_an_unknown_chat(monkeypatch):
    import app
    monkeypatch.setattr(app.sr, "resolve_path", lambda sid: None)
    with pytest.raises(app.HTTPException):
        app.api_session_archive("nope")
    with pytest.raises(app.HTTPException):
        app.api_session_unarchive("nope")
