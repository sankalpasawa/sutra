"""test_chat_search.py -- /api/sessions?q= searches titles, folders, headers.

Founder, 2026-09-24: "titles, folders, headers. That's it." The rail holds at
most 2,000 rows, so the search has to ask the server, and the server has to
walk EVERY chat in scope -- not one page -- or it misses exactly the old chat
you are looking for. These pin the matcher, the walk, and that the ordinary
unsearched list is untouched.

Run: .venv/bin/python -m pytest -q test_chat_search.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app  # noqa: E402


def _row(i, **kw):
    r = {"id": "s%d" % i, "title": "chat %d" % i, "cwd": "/w/other", "project": "-w-other",
         "source": "claude", "mtime": 1000 - i}
    r.update(kw)
    return r


POOL = [
    _row(0, title="Paisa KYC flow"),
    _row(1, cwd="/Users/a/Claude/paisa"),
    _row(2, title="Refund", _dept={"ref": "d5", "name": "Paisa"}),
    _row(3, title="nightly", _rtn={"routine": "daily-paisa-sync"}),
    _row(4, title="Billu invoices", cwd="/w/billu"),
    _row(5, title="unrelated", branch="paisa"),
] + [_row(10 + i) for i in range(300)] + [_row(999, title="very old PAISA note", mtime=1)]


def _join_depts(rows):
    for r in rows:
        r["department"] = r.pop("_dept", None)
    return rows


def _join_routines(rows):
    for r in rows:
        r["routine"] = r.pop("_rtn", None)
    return rows


def _wire(monkeypatch, every=True):
    pool = [dict(r) for r in POOL]
    seen = {}

    def list_sessions(limit, offset):
        seen["limit"] = limit
        return [dict(r) for r in pool[offset:offset + limit]]
    monkeypatch.setattr(app, "_list_every_chat", lambda: every)
    monkeypatch.setattr(app.sr, "list_sessions", list_sessions)
    monkeypatch.setattr(app, "_with_departments", _join_depts)
    monkeypatch.setattr(app.routine_links, "attach", _join_routines)
    monkeypatch.setattr(app.chat_store, "resolve", lambda *a: None)
    monkeypatch.setattr(app.shadow_runner, "driving", lambda *a: False)
    return seen


def test_matcher_covers_title_and_both_headers():
    m = app._chat_matches
    assert m({"title": "Paisa KYC"}, "paisa")
    assert m({"department": {"name": "Paisa"}}, "paisa")
    assert m({"routine": {"routine": "daily-paisa-sync"}}, "paisa")


def test_folders_never_match_rows_show_departments():
    # founder 2026-09-25: "It should show departments and not folders"
    assert not app._chat_matches({"title": "x", "cwd": "/x/paisa"}, "paisa")
    assert not app._chat_matches({"title": "Shadow boot", "cwd": "/u/.sutra-ui/shadow/workdir"}, "workdir")
    assert not app._chat_matches({"title": "x", "project": "-Users-a-paisa-x"}, "paisa")


def test_matcher_ignores_everything_else():
    assert not app._chat_matches({"title": "x", "branch": "paisa", "source": "paisa"}, "paisa")
    assert not app._chat_matches({"title": None, "department": None, "routine": None}, "paisa")


def test_search_walks_every_chat_not_one_page(monkeypatch):
    seen = _wire(monkeypatch)
    ids = [r["id"] for r in app.api_sessions(limit=100, offset=0, q="  PAISA ")]
    assert ids == ["s0", "s2", "s3", "s999"]      # s999 past the first 300; s1 is folder-only
    assert seen["limit"] >= app.CHAT_SEARCH_POOL


def test_search_rows_carry_the_joined_headers_once(monkeypatch):
    _wire(monkeypatch)
    rows = app.api_sessions(limit=100, offset=0, q="paisa")
    by = {r["id"]: r for r in rows}
    assert by["s2"]["department"] == {"ref": "d5", "name": "Paisa"}
    assert by["s3"]["routine"] == {"routine": "daily-paisa-sync"}
    assert all("_dept" not in r and "_rtn" not in r for r in rows)


def test_search_respects_limit(monkeypatch):
    _wire(monkeypatch)
    assert len(app.api_sessions(limit=2, offset=0, q="paisa")) == 2


def test_no_query_is_the_unchanged_page(monkeypatch):
    seen = _wire(monkeypatch)
    rows = app.api_sessions(limit=100, offset=0, q="")
    assert len(rows) == 100 and seen["limit"] == 100
    assert rows[0]["id"] == "s0"


def test_scoped_list_searches_only_sutra_chats(monkeypatch):
    _wire(monkeypatch, every=False)
    owned = [(1, "claude", "s0", Path("/p/s0.jsonl")), (2, "claude", "s4", Path("/p/s4.jsonl"))]
    monkeypatch.setattr(app, "_owned_transcripts", lambda: owned)
    monkeypatch.setattr(app.sr, "_gemini_project_cwd_map", lambda: {})
    rows_by_id = {r["id"]: r for r in POOL}
    monkeypatch.setattr(app, "_session_row", lambda src, p, pc: dict(rows_by_id[p.stem]))
    ids = [r["id"] for r in app.api_sessions(limit=100, offset=0, q="paisa")]
    assert ids == ["s0"]
