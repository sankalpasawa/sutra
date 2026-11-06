"""Chat storage v2 (work package ABS-6): the migration, segments, blocks, search, owner archive, the persisted choice."""
from __future__ import annotations

import pytest
from orchestrator.test_chat_store import msg, post
from orchestrator.test_graph_store import World

from sutra_app.library.gate import GATE
from sutra_app.orchestrator import schema
from sutra_app.orchestrator.chat_v2 import ChatArchive, ChatChoices, ChatSearch, ChatSegments
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.records import ChatMessage, ChatSession


@pytest.fixture
def world(db, clock):
    return World(db, clock)


@pytest.fixture
def chats(db):
    return ChatStore(db)


# ---- the migration -----------------------------------------------------------------------------------------------------------------

def test_upgrading_a_populated_v1_file_keeps_every_row_and_adds_the_new_things(settings, events, clock):
    old = Database(settings.db_path, events, clock=clock)
    old.migrate([schema.DDL_V1])
    assert old.version() == 1
    c = old.conn()
    c.execute("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('root','root','Root',1,0),('web','department','Web',2,0)")
    c.execute("INSERT INTO chat_sessions(id, node_id, kind, title, writable, connector, model, last_message_id, created_at, updated_at)"
              " VALUES ('cs_org','root','org','Org',1,'claude','sonnet',2,1,9),('cs_aaaaaaaaaaaa','web','department','Web',1,'',  '',0,2,2)")
    for n, text in enumerate(("find the zebra", "the answer is on the shelf"), 1):
        c.execute("INSERT INTO chat_messages(session_id, role, who, text, at) VALUES ('cs_org', ?, ?, ?, ?)", ("user" if n == 1 else "agent", "user" if n == 1 else "sutra", text, n))
    c.execute("INSERT INTO usage_ledger(at, provider, purpose, session_id) VALUES (1, 'claude', 'chat', 'cs_org')")
    before = [tuple(r) for r in c.execute("SELECT id, node_id, kind, title, writable, status, connector, model, last_message_id, created_at, updated_at FROM chat_sessions ORDER BY id")]
    assert old.migrate() == schema.SCHEMA_VERSION
    c = old.conn()
    after = [tuple(r) for r in c.execute("SELECT id, node_id, kind, title, writable, status, connector, model, last_message_id, created_at, updated_at FROM chat_sessions ORDER BY id")]
    assert after == before
    assert c.execute("SELECT count(*) FROM chat_messages").fetchone()[0] == 2 and c.execute("SELECT count(*) FROM usage_ledger").fetchone()[0] == 1
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT pinned FROM chat_sessions WHERE id = 'cs_org'").fetchone()[0] == ""
    assert [r["session_id"] for r in c.execute("SELECT session_id FROM chat_search WHERE chat_search MATCH 'zebra'")] == ["cs_org"]     # backfilled
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name = 'chat_sessions_active'").fetchone() is not None
    c.execute("INSERT INTO chat_sessions(id, node_id, kind, title, status, created_at, updated_at) VALUES ('cs_old_abcdefabcdef','legacy','legacy','Old','archived',0,0)")
    old.close()


def test_an_older_app_is_refused_a_newer_file(db):
    from sutra_app.orchestrator.errors import AppError  # noqa: F401
    from sutra_app.orchestrator.db import SchemaError
    db.conn().execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION + 1}")
    with pytest.raises(SchemaError):
        db.migrate()
    db.conn().execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION}")


# ---- segments ----------------------------------------------------------------------------------------------------------------------

def test_a_segment_is_added_per_provider_change_and_not_per_turn(db, world, chats):
    sid = world.session_of["web"]
    post(db, chats, sid, "one", who="user")
    chats.set_provider(sid, "claude", "sonnet", "p-1")
    chats.set_provider(sid, "claude", "sonnet", "p-1")
    post(db, chats, sid, "two", who="user")
    chats.set_provider(sid, "codex", "gpt", "p-2")
    chats.set_provider(sid, "claude", "sonnet", "p-3")
    segs = ChatSegments(db).segments(sid)
    assert [(s["seq"], s["connector"], s["provider_session_id"]) for s in segs] == [(1, "claude", "p-1"), (2, "codex", "p-2"), (3, "claude", "p-3")]
    assert [s["from_message_id"] for s in segs][:2] == [1, 2]


# ---- blocks ------------------------------------------------------------------------------------------------------------------------

def test_blocks_round_trip_through_a_stored_message(db, world, chats):
    sid = world.session_of["web"]
    blocks = [{"type": "tool_use", "kind": "run", "name": "Bash", "text": "ls"}, {"type": "tool_result", "kind": "run", "name": "Bash", "text": "a\nb", "truncated": True}]
    with db.tx() as tx:
        out = chats.post(tx, sid, GATE.check("chat_message", ChatMessage(kind="text", session_id=sid, role="agent", who="sutra", text="done", blocks=blocks, at=5)))
    stored = chats.blocks(out.id)
    assert [b["type"] for b in stored] == ["tool_use", "tool_result"] and stored[1]["truncated"] is True and stored[0]["kind"] == "run"
    assert chats.blocks(999) == []


def test_a_message_without_blocks_stores_none_and_the_model_refuses_an_unknown_type(db, world, chats):
    sid = world.session_of["web"]
    out = post(db, chats, sid, "plain")
    assert chats.blocks(out.id) == []
    with pytest.raises(Exception):
        ChatMessage(kind="text", session_id=sid, role="agent", who="sutra", text="x", blocks=[{"type": "image"}], at=1)
    with pytest.raises(Exception):
        ChatMessage(kind="text", session_id=sid, role="agent", who="sutra", text="x", blocks=[{"type": "text", "surprise": 1}], at=1)


# ---- search ------------------------------------------------------------------------------------------------------------------------

def test_search_finds_messages_and_titles_with_a_snippet(db, world, chats):
    sid = world.session_of["web"]
    post(db, chats, sid, "the quarterly zebra report is ready", who="user")
    rows = ChatSearch(db).search("zebra")
    assert [(r["session_id"], r["title"]) for r in rows] == [(sid, "web")] and "zebra" in rows[0]["snippet"] and rows[0]["message_id"] > 0
    assert ChatSearch(db).search("web")[0]["message_id"] == 0              # a title match
    assert ChatSearch(db).search("zeb")[0]["session_id"] == sid           # the last word is a prefix
    assert ChatSearch(db).search("   ") == [] and ChatSearch(db).search('"; DROP') == []


def test_search_is_scoped_in_sql_and_hides_archived_chats(db, world, chats):
    a, b = world.session_of["web"], world.session_of["menu"]
    post(db, chats, a, "needle in web", who="user")
    post(db, chats, b, "needle in menu", who="user")
    s = ChatSearch(db)
    assert {r["session_id"] for r in s.search("needle")} == {a, b}
    assert {r["session_id"] for r in s.search("needle", scope="node:web")} == {a}
    assert {r["session_id"] for r in s.search("needle", scope="dept:menu")} == {b}
    with db.tx() as tx:
        ChatArchive(db).archive(tx, a)
    assert {r["session_id"] for r in s.search("needle")} == {b}
    assert {r["session_id"] for r in s.search("needle", include_archived=True)} == {a, b}
    assert {r["session_id"] for r in s.search("needle", scope="node:web")} == set()
    with pytest.raises(AppError):
        s.search("needle", scope="node:x' OR 1=1")


def test_a_merged_away_session_is_not_found_outside_its_scope(db, world, chats):
    a = world.session_of["web"]
    post(db, chats, a, "secret plan", who="user")
    world.sql("UPDATE chat_sessions SET status='archived', writable=0, filed_under='menu' WHERE id = ?", a)
    assert ChatSearch(db).search("secret") == []
    assert [r["session_id"] for r in ChatSearch(db).search("secret", scope="node:menu", include_archived=True)] == [a]


def test_search_returns_at_most_fifty(db, world, chats):
    sid = world.session_of["web"]
    for i in range(60):
        post(db, chats, sid, f"needle {i}", who="user")
    assert len(ChatSearch(db).search("needle")) == 50


def test_an_edited_message_is_searched_by_its_new_text(db, world, chats):
    sid = world.session_of["web"]
    out = post(db, chats, sid, "old words", who="user")
    world.sql("UPDATE chat_messages SET text = 'fresh words' WHERE id = ?", out.id)
    assert ChatSearch(db).search("old") == [] and ChatSearch(db).search("fresh")[0]["message_id"] == out.id


# ---- archive -----------------------------------------------------------------------------------------------------------------------

def test_archive_is_a_mark_that_keeps_every_message_and_frees_the_slot(db, world, chats):
    sid = world.session_of["web"]
    post(db, chats, sid, "hello", who="user")
    with db.tx() as tx:
        assert ChatArchive(db).archive(tx, sid) is True
        assert ChatArchive(db).archive(tx, sid) is False
    s = chats.session(sid)
    assert (s.status, s.writable) == ("archived", False) and len(chats.messages(sid)) == 1
    fresh = db.conn().execute("SELECT id FROM chat_sessions WHERE node_id = 'web' AND status = 'active'").fetchall()
    assert len(fresh) == 1 and fresh[0]["id"] != sid                       # archiving started the replacement chat
    assert db.conn().execute("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'").fetchone()[0] == fresh[0]["id"]
    post(db, chats, fresh[0]["id"], "new chat", who="user")
    with db.tx() as tx, pytest.raises(AppError):
        ChatArchive(db).unarchive(tx, sid)                                  # the node has a new, used open chat
    world.sql("UPDATE chat_sessions SET status = 'archived' WHERE id = ?", fresh[0]["id"])
    with db.tx() as tx:
        assert ChatArchive(db).unarchive(tx, sid) is True
    assert chats.session(sid).status == "active" and chats.session(sid).writable is True


def test_archiving_a_node_chat_keeps_the_node_with_one_active_chat_and_the_choice(db, world, chats):
    sid = world.session_of["web"]
    with db.tx() as tx:
        ChatChoices(db).set(tx, sid, "codex")
    with db.tx() as tx:
        ChatArchive(db).archive(tx, sid)
    active = db.conn().execute("SELECT id, writable, pinned FROM chat_sessions WHERE node_id = 'web' AND status = 'active'").fetchall()
    assert len(active) == 1 and active[0]["writable"] == 1 and active[0]["pinned"] == "codex"
    assert db.conn().execute("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'").fetchone()[0] == active[0]["id"]
    import json
    assert json.loads(db.conn().execute("SELECT body FROM graph_nodes WHERE id = 'web'").fetchone()[0])["chat_session_id"] == active[0]["id"]


def test_an_unused_replacement_steps_aside_when_the_archived_chat_comes_back(db, world, chats):
    sid = world.session_of["web"]
    with db.tx() as tx:
        ChatArchive(db).archive(tx, sid)
    with db.tx() as tx:
        assert ChatArchive(db).unarchive(tx, sid) is True
    active = db.conn().execute("SELECT id FROM chat_sessions WHERE node_id = 'web' AND status = 'active'").fetchall()
    assert [r["id"] for r in active] == [sid]
    assert db.conn().execute("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'").fetchone()[0] == sid


def test_the_org_chat_and_merged_or_imported_chats_cannot_change_state(db, world):
    with db.tx() as tx, pytest.raises(AppError):
        ChatArchive(db).archive(tx, "cs_org")
    world.sql("INSERT INTO chat_sessions(id, node_id, kind, title, status, created_at, updated_at) VALUES ('cs_old_abcdefabcdef','legacy','legacy','Old','archived',0,0)")
    with db.tx() as tx, pytest.raises(AppError):
        ChatArchive(db).unarchive(tx, "cs_old_abcdefabcdef")
    with db.tx() as tx, pytest.raises(NotFound):
        ChatArchive(db).archive(tx, "cs_000000000fff")


def test_a_legacy_session_record_must_be_archived_and_read_only():
    ok = ChatSession(kind="legacy", id="cs_old_abcdefabcdef", node_id="legacy", title="Old", writable=False, status="archived", created_at=1, updated_at=1)
    assert GATE.check("chat_session", ok)
    with pytest.raises(Exception):
        ChatSession(kind="legacy", id="cs_old_abcdefabcdef", node_id="legacy", title="Old", writable=True, status="archived", created_at=1, updated_at=1)
    with pytest.raises(Exception):
        ChatSession(kind="legacy", id="cs_old_abcdefabcdef", node_id="legacy", title="Old", writable=False, status="active", created_at=1, updated_at=1)


# ---- the persisted choice ----------------------------------------------------------------------------------------------------------

def test_the_choice_is_stored_cleared_and_validated(db, world):
    sid = world.session_of["web"]
    choices = ChatChoices(db)
    assert choices.get(sid) == ""
    with db.tx() as tx:
        choices.set(tx, sid, "codex")
    assert choices.get(sid) == "codex"
    with db.tx() as tx:
        choices.set(tx, sid, None)
    assert choices.get(sid) == ""
    with db.tx() as tx, pytest.raises(AppError):
        choices.set(tx, sid, "gemini")
    with db.tx() as tx, pytest.raises(NotFound):
        choices.set(tx, "cs_000000000fff", "claude")
