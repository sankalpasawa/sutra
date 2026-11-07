"""Import of the old app's chats (work package ABS-12; absorb design section 4, D113). Fixtures only; the real old folder is never read."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from sutra_app import oslayer
from sutra_app.config import Settings
from sutra_app.ops import cli, import_old, lock
from sutra_app.orchestrator.db import Database

ID_A = "a" * 32
ID_B = "b" * 32
ID_C = "c" * 32
ID_D = "d" * 32
SECRET = "sk-abcdefgh12345678"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith(("SUTRA_", "J2_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("SUTRA_ENV_FILE", str(tmp_path / "none.env"))


def blk(role, *blocks, ts="2026-10-01T10:00:00Z"):
    return {"role": role, "ts": ts, "blocks": list(blocks), "provider": "claude", "native_id": "n", "turn": 1}


def text(t):
    return {"type": "text", "text": t}


@pytest.fixture
def old(tmp_path):
    root = tmp_path / "old-chats"
    root.mkdir()
    docs = {
        ID_A: {"sutra_id": ID_A, "title": "Plan the cafe site", "cwd": "/work/cafe-site", "created": "2026-10-01T09:00:00Z", "updated": "2026-10-01T11:00:00Z",
               "provider_history": [{"provider": "claude", "native_id": "x", "from_turn": 0}, {"provider": "codex", "native_id": "y", "from_turn": 2}],
               "messages": [blk("user", text("hello")),
                            blk("assistant", {"type": "thinking", "text": "hmm"}, text(f"key {SECRET} here"), {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                                {"type": "tool_use", "name": "Bash", "input": {}}, {"type": "tool_use", "name": "Read", "input": {}},
                                {"type": "tool_result", "content": "SECRET OUTPUT"}),
                            blk("assistant", {"type": "tool_use", "name": "Edit", "input": {}})]},
        ID_B: {"sutra_id": ID_B, "title": "legacy shape", "cwd": "", "created": "2026-09-01T00:00:00Z", "updated": "2026-09-01T00:00:00Z", "provider_history": [],
               "messages": [{"role": "user", "text": "old style question", "ts": "2026-09-01T00:00:00Z"}, {"role": "assistant", "text": "old style answer", "ts": "2026-09-01T00:01:00Z"}]},
        ID_C: {"sutra_id": ID_C, "title": "empty", "cwd": "/x/y", "created": "2026-08-01T00:00:00Z", "updated": "2026-08-01T00:00:00Z", "provider_history": [], "messages": []},
        ID_D: {"sutra_id": ID_D, "title": "deepseek one", "cwd": "/a/b", "created": "2026-07-01T00:00:00Z", "updated": "2026-07-01T00:00:00Z",
               "provider_history": [{"provider": "deepseek", "native_id": "z", "from_turn": 0}], "messages": [blk("user", text("hi")), blk("assistant", text("hello"))]},
    }
    for sid, doc in docs.items():
        (root / f"{sid}.json").write_text(json.dumps(doc), encoding="utf-8")
    (root / "_index.json").write_text(json.dumps({"claude:1": ID_A}), encoding="utf-8")
    (root / "broken.json").write_text("{nope", encoding="utf-8")
    return root


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def run(args, capsys):
    code = cli.main(["import-old-chats", *args])
    return code, capsys.readouterr()


def rows(db_path: Path, sql: str, *args):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def test_the_dry_run_counts_and_says_what_is_flattened_and_writes_nothing(old, tmp_path, capsys):
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data)], capsys)
    assert code == 0 and "Old chats in" in out.out and "4 (3 with messages), 6 messages" in out.out
    assert "2 turn(s) of tool calls become one note each" in out.out and "1 thinking block(s) are dropped" in out.out
    assert "Could not read 1 file(s): broken.json" in out.out and "Dry run: nothing was written" in out.out and "Not imported:" in out.out
    assert not data.exists()


def test_apply_makes_archived_read_only_legacy_chats_and_leaves_the_old_folder_byte_identical(old, tmp_path, capsys):
    before = tree(old)
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and tree(old) == before
    sessions = {r["id"]: r for r in rows(data / "db.sqlite3", "SELECT * FROM chat_sessions")}
    assert set(sessions) == {"cs_old_" + c * 12 for c in "abcd"}
    a = sessions["cs_old_" + "a" * 12]
    assert (a["kind"], a["node_id"], a["status"], a["writable"], a["connector"], a["title"]) == ("legacy", "legacy", "archived", 0, "codex", "Plan the cafe site")
    assert a["note"] == "Imported from old Sutra, folder cafe-site"
    assert sessions["cs_old_" + "d" * 12]["connector"] == "" and sessions["cs_old_" + "b" * 12]["connector"] == ""      # deepseek and no history: history only


@pytest.mark.skipif(oslayer.IS_WINDOWS, reason="asserts POSIX permission bits")
def test_apply_into_a_missing_data_folder_makes_it_private_whatever_the_umask(old, tmp_path, capsys):
    data = tmp_path / "fresh" / "data"
    previous = os.umask(0o022)
    try:
        code, _ = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    finally:
        os.umask(previous)
    assert code == 0 and data.stat().st_mode & 0o777 == 0o700
    assert not [p for p in data.rglob("*") if p.is_dir() and p.stat().st_mode & 0o077]       # nothing it created is open to other users


def test_apply_into_a_missing_data_folder_holds_the_instance_lock_while_it_writes(old, tmp_path, capsys, monkeypatch):
    data = tmp_path / "fresh" / "data"
    seen: list[bool] = []
    real = import_old.import_chats

    def watch(db, chats, redactor):
        seen.append(lock.is_locked(data))                       # a server that starts now must be refused, as for a folder that exists
        return real(db, chats, redactor)

    monkeypatch.setattr(import_old, "import_chats", watch)
    code, _ = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and seen == [True] and not lock.is_locked(data)


def test_messages_are_mapped_notes_collapse_tools_and_thinking_is_dropped(old, tmp_path, capsys):
    data = tmp_path / "data"
    run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    msgs = rows(data / "db.sqlite3", "SELECT role, who, kind, text, src_ref, at FROM chat_messages WHERE session_id = ? ORDER BY id", "cs_old_" + "a" * 12)
    assert [(m["role"], m["kind"]) for m in msgs] == [("user", "text"), ("agent", "text"), ("agent", "note"), ("agent", "note")]
    assert msgs[0]["who"] == "user" and msgs[1]["who"] == "old Sutra" and msgs[0]["src_ref"] == f"old:{ID_A}:0"
    assert msgs[2]["text"] == "Tools used: Bash x2, Read" and msgs[3]["text"] == "Tools used: Edit"
    blob = json.dumps(msgs)
    assert "hmm" not in blob and "SECRET OUTPUT" not in blob and '"command"' not in blob                    # thinking, tool output and tool input never arrive
    assert msgs[0]["at"] == 1790848800


def test_a_legacy_message_is_a_text_message_and_an_empty_chat_is_an_empty_archived_session(old, tmp_path, capsys):
    data = tmp_path / "data"
    run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    legacy = rows(data / "db.sqlite3", "SELECT role, text FROM chat_messages WHERE session_id = ? ORDER BY id", "cs_old_" + "b" * 12)
    assert legacy == [{"role": "user", "text": "old style question"}, {"role": "agent", "text": "old style answer"}]
    assert rows(data / "db.sqlite3", "SELECT count(*) AS n FROM chat_messages WHERE session_id = ?", "cs_old_" + "c" * 12)[0]["n"] == 0


def test_texts_are_scrubbed_before_they_are_stored(old, tmp_path, capsys):
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    blob = json.dumps(rows(data / "db.sqlite3", "SELECT text FROM chat_messages"))
    assert SECRET not in blob and "[redacted:openai-key]" in blob and "Credential shapes scrubbed: openai-key 1" in out.out


def test_a_second_run_changes_nothing(old, tmp_path, capsys):
    data = tmp_path / "data"
    run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    first = rows(data / "db.sqlite3", "SELECT id, session_id, src_ref, text FROM chat_messages ORDER BY id")
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and "0 message(s) added" in out.out and "4 already there" in out.out
    assert rows(data / "db.sqlite3", "SELECT id, session_id, src_ref, text FROM chat_messages ORDER BY id") == first


def test_apply_takes_a_backup_when_a_database_exists_and_not_before_one_does(old, tmp_path, capsys):
    data = tmp_path / "data"
    run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert not (data / "backups").exists()                                              # nothing to back up the first time
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and len(list((data / "backups").glob("sutra-pro-backup-*.tar.gz"))) == 1 and "Backup written first" in out.out


def test_apply_refuses_while_another_instance_holds_the_data_folder(old, tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    held = lock.InstanceLock(data)
    assert held.acquire()
    try:
        code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    finally:
        held.release()
    assert code == 1 and "stop it first" in out.err and not (data / "db.sqlite3").exists()


def test_imported_chats_are_found_by_search_under_older_chats(old, tmp_path, capsys):
    from sutra_app.orchestrator.chat_v2 import ChatSearch
    data = tmp_path / "data"
    run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    db = Database(data / "db.sqlite3", lambda e: None)
    try:
        assert ChatSearch(db).search("cafe") == []                                       # archived: hidden until asked
        hit, = ChatSearch(db).search("cafe", include_archived=True)
        assert hit["session_id"] == "cs_old_" + "a" * 12 and hit["archived"] is True
        assert ChatSearch(db).search("old style answer", include_archived=True)[0]["session_id"] == "cs_old_" + "b" * 12
    finally:
        db.close()


def test_a_missing_source_is_refused_and_the_command_is_registered(tmp_path, capsys):
    code, out = run(["--source", str(tmp_path / "nope")], capsys)
    assert code == 1 and "there is no folder" in out.err
    assert "import-old-chats" in cli.command_names()


def test_json_output_has_the_counts(old, tmp_path, capsys):
    code, out = run(["--source", str(old), "--data-dir", str(tmp_path / "data"), "--json"], capsys)
    doc = json.loads(out.out)
    assert code == 0 and (doc["chats"], doc["non_empty"], doc["messages"], doc["notes"], doc["thinking_dropped"], doc["applied"]) == (4, 3, 6, 2, 1, False)


# ---- chats the store cannot hold (QA ops-cli): none of them may stop the import or end it with a traceback ---------------------------

CUT = "\\ud83d"          # the JSON escape of half an emoji: what JavaScript leaves when it cuts a string between the two halves


def add_chat(root: Path, name: str, sid, **doc) -> None:
    """A chat file beside the fixture's four; `doc` overrides its fields. The text `{CUT}` anywhere in it is written as the escape of half an emoji."""
    body = json.dumps({"sutra_id": sid, "title": "extra", "cwd": "", "created": "2026-10-01T09:00:00Z", "updated": "2026-10-01T09:00:00Z", "provider_history": [],
                       "messages": [{"role": "user", "ts": "2026-10-01T09:00:00Z", "blocks": [text("extra hello")]}], **doc})
    (root / name).write_text(body.replace("{CUT}", CUT), encoding="utf-8")


def session_ids(db_path: Path) -> set[str]:
    return {r["id"] for r in rows(db_path, "SELECT id FROM chat_sessions")}


@pytest.mark.parametrize("bad_id", [12345678901234567890, True, 1.5, None, ["a" * 32], "a" * 12 + "\n", "ABCDEF" * 3])
def test_an_id_that_is_not_a_hex_string_makes_the_file_unreadable_not_a_crash_and_the_rest_import(old, tmp_path, capsys, bad_id):
    add_chat(old, "bbbb-bad-id.json", bad_id)                    # sorts between the good chats, so a crash would leave some of them out
    chats, bad = import_old.read_chats(old)
    assert [c.sutra_id for c in chats] == [ID_A, ID_B, ID_C, ID_D] and sorted(bad) == ["bbbb-bad-id.json", "broken.json"]
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data)], capsys)
    assert code == 0 and "Could not read 2 file(s): bbbb-bad-id.json, broken.json" in out.out
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and "Traceback" not in out.err and out.err == "" and session_ids(data / "db.sqlite3") == {"cs_old_" + c * 12 for c in "abcd"}


def test_a_string_cut_inside_an_emoji_is_repaired_reported_and_a_whole_emoji_is_left_alone(old, tmp_path, capsys):
    add_chat(old, "e" * 32 + ".json", "e" * 32, title="cut title {CUT}", messages=[{"role": "user", "blocks": [text("tail {CUT}")]}])
    add_chat(old, "f" * 32 + ".json", "f" * 32, title="whole \U0001F600", messages=[{"role": "user", "blocks": [text("pair \U0001F600 and cut {CUT}")]}])
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data)], capsys)
    assert code == 0 and "6 (" in out.out and "2 chat(s) hold a lone surrogate half" in out.out and "stored as U+FFFD" in out.out
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and out.err == ""
    db = data / "db.sqlite3"
    assert rows(db, "SELECT title FROM chat_sessions WHERE id = ?", "cs_old_" + "e" * 12) == [{"title": "cut title \ufffd"}]
    assert rows(db, "SELECT text FROM chat_messages WHERE session_id = ?", "cs_old_" + "e" * 12) == [{"text": "tail \ufffd"}]
    assert rows(db, "SELECT title FROM chat_sessions WHERE id = ?", "cs_old_" + "f" * 12) == [{"title": "whole \U0001F600"}]
    assert rows(db, "SELECT text FROM chat_messages WHERE session_id = ?", "cs_old_" + "f" * 12) == [{"text": "pair \U0001F600 and cut \ufffd"}]


@pytest.mark.parametrize("when", ["1969-12-31T23:59:59Z", "0001-01-01T00:00:00Z", "1969-12-31T23:59:59", "1900-06-01T00:00:00+02:00"])
def test_a_time_before_1970_reads_as_unknown_like_an_unreadable_one_and_the_chat_imports(old, tmp_path, capsys, when):
    add_chat(old, "9" * 32 + ".json", "9" * 32, created=when, updated=when, messages=[{"role": "user", "ts": when, "blocks": [text("old time")]}])
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and out.err == ""
    session, = rows(data / "db.sqlite3", "SELECT created_at, updated_at FROM chat_sessions WHERE id = ?", "cs_old_" + "9" * 12)
    assert session == {"created_at": 0, "updated_at": 0}
    assert rows(data / "db.sqlite3", "SELECT at, text FROM chat_messages WHERE session_id = ?", "cs_old_" + "9" * 12) == [{"at": 0, "text": "old time"}]


def test_epoch_gives_the_fallback_for_negative_overflowing_and_unparseable_times():
    assert import_old._epoch("2026-10-01T10:00:00Z") == 1790848800
    assert import_old._epoch("1969-12-31T23:59:59Z", 7) == 7 and import_old._epoch("0001-01-01T00:00:00Z", 7) == 7
    assert import_old._epoch("garbage", 5) == 5 and import_old._epoch("", 5) == 5 and import_old._epoch(None, 5) == 5     # type: ignore[arg-type]
    assert import_old._epoch("1970-01-01T00:00:00Z", 5) == 0


class RefusingGate:
    """The real gate, except that it refuses the chat titled `poison`: a payload the store will not hold, for a reason nobody predicted."""

    def __init__(self, real):
        self._real = real

    def check(self, family, model, **kw):
        if family == "chat_session" and model.title == "poison":
            raise ValueError("refused for the test")
        return self._real.check(family, model, **kw)


def test_a_chat_the_store_refuses_is_skipped_and_named_the_rest_import_and_a_rerun_ends_the_same_way(old, tmp_path, capsys, monkeypatch):
    add_chat(old, "bbbb-poison.json", "1" * 32, title="poison")
    monkeypatch.setattr(import_old, "GATE", RefusingGate(import_old.GATE))
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 0 and out.err == "" and "Imported 4 chat(s) (0 already there), 8 message(s) added." in out.out
    assert "Could not store 1 chat(s): bbbb-poison.json" in out.out
    assert session_ids(data / "db.sqlite3") == {"cs_old_" + c * 12 for c in "abcd"}
    assert not rows(data / "db.sqlite3", "SELECT 1 FROM chat_messages WHERE src_ref LIKE ?", "old:" + "1" * 32 + "%")       # nothing of it is half stored
    code, again = run(["--source", str(old), "--data-dir", str(data), "--apply", "--json"], capsys)
    payload = json.loads(again.out)
    assert code == 0 and payload["unstorable"] == ["bbbb-poison.json"] and payload["chats_present"] == 4 and payload["messages_added"] == 0


def test_the_dry_run_names_the_chats_the_store_would_refuse_and_still_writes_nothing(old, tmp_path, capsys, monkeypatch):
    add_chat(old, "bbbb-poison.json", "1" * 32, title="poison")
    monkeypatch.setattr(import_old, "GATE", RefusingGate(import_old.GATE))
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data)], capsys)
    assert code == 0 and "Could not store 1 chat(s): bbbb-poison.json" in out.out and "Dry run: nothing was written" in out.out and not data.exists()
    code, out = run(["--source", str(old), "--data-dir", str(data), "--json"], capsys)
    assert json.loads(out.out)["unstorable"] == ["bbbb-poison.json"]


@pytest.mark.parametrize("error", [sqlite3.OperationalError("disk I/O error"), OSError(28, "No space left on device")])
def test_a_failure_of_the_store_ends_with_a_sentence_and_exit_1_not_a_traceback(old, tmp_path, capsys, monkeypatch, error):
    def fail(db, chats, redactor):
        raise error

    monkeypatch.setattr(import_old, "import_chats", fail)
    data = tmp_path / "data"
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 1 and out.err.startswith("sutra-pro: the import stopped") and str(error) in out.err and "run it again" in out.err
    assert not lock.is_locked(data)


def test_a_damaged_database_stops_the_import_at_the_backup_with_a_sentence(old, tmp_path, capsys):
    data = tmp_path / "data"
    run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    with open(data / "db.sqlite3", "r+b") as handle:
        for n in range(6):
            handle.seek(8192 + n * 3000)
            handle.write(b"\xff" * 200)
    code, out = run(["--source", str(old), "--data-dir", str(data), "--apply"], capsys)
    assert code == 1 and out.err.startswith("sutra-pro: the import stopped") and "integrity check" in out.err and "Imported" not in out.out


def test_a_dry_run_whose_rehearsal_cannot_run_still_answers_and_says_so(old, tmp_path, capsys, monkeypatch):
    def no_room(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(import_old, "rehearse", no_room)
    code, out = run(["--source", str(old), "--data-dir", str(tmp_path / "data")], capsys)
    assert code == 0 and "could not run" in out.out and "No space left on device" in out.out and "Dry run: nothing was written" in out.out
    assert out.err == ""
