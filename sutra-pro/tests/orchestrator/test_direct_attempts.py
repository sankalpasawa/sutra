"""Attempt-scoped refs, the owner's `client_id`, `superseded` replies and the ordered-blocks marker (streaming design D216, D220, D212; work package STR-3).

`chat_messages` is unique on (session_id, src_ref), so a retry of an owner line cannot reuse the refs its first try stored: from attempt 2 every ending
row carries `.N`. The readers of the refs (the `Ending` pattern, `chats._turn_of`/`_attempt_of`, `recover_interrupted`, the composer's reconcile) change
together; this file holds the table over every shape and the behaviour that depends on it."""
from __future__ import annotations

import itertools
import json

import pytest
from orchestrator.test_api_chat_v2 import H, rig, say, wait_for, world  # noqa: F401  (the fixtures of the chat v2 routes)
from orchestrator.test_direct_turn_endings import FakePort, done, partial
from pydantic import ValidationError

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.errors import CallCancelledError
from sutra_app.orchestrator import chats as chats_mod
from sutra_app.orchestrator import direct_turns
from sutra_app.orchestrator.api import chat_v2 as chat_api
from sutra_app.orchestrator.chat_v2 import attempts_stored, find_owner_line, next_attempt, recover_interrupted
from sutra_app.orchestrator.chats import ChatTranscripts


# ---- the table of every ref shape ----------------------------------------------------------------------------------------------------------

TAILS = ("", "note", "error", "switch")


@pytest.mark.parametrize("tail,attempt,owner", list(itertools.product(TAILS, (1, 2, 3, 9, 10, 99), (1, 7, 123456789012345))))
def test_every_ref_shape_is_written_valid_and_read_back_by_every_reader(tail, attempt, owner):
    ref = direct_turns.ref_of(owner, tail, attempt)
    prefix = "direct" + ("-" + tail if tail else "") + f":{owner}"
    assert ref == prefix + (f".{attempt}" if attempt > 1 else "")                       # attempt 1 is the historical shape, byte for byte
    direct_turns.Ending(kind="text", text="x", src_ref=ref)                              # the Ending pattern accepts it
    assert chats_mod._turn_of(ref) == owner and chats_mod._attempt_of(ref) == attempt    # chats reads the owner and the try


@pytest.mark.parametrize("bad", ["direct:0", "direct:01", "direct:5.1", "direct:5.0", "direct:5.100", "direct:5.", "direct:5..2", "direct-ask:5",
                                 "direct-other:5", "direct:5.2.3", "direct:", "direct:abc", "direct:5 .2", " direct:5", "direct:5.2\n"])
def test_refs_outside_the_shape_are_refused_by_the_pattern_and_read_as_no_turn(bad):
    with pytest.raises(ValidationError):
        direct_turns.Ending(kind="text", text="x", src_ref=bad)
    assert chats_mod._turn_of(bad) is None and chats_mod._attempt_of(bad) is None


def test_the_attempt_range_is_enforced_when_a_ref_is_built():
    for bad in (0, 100, -1, True, 2.0):
        with pytest.raises(ValueError):
            direct_turns.ref_of(5, "", bad)


def test_client_ids_are_parsed_from_owner_refs_only_and_validated():
    assert chats_mod._client_of("direct-ask:abcd1234") == "abcd1234" and chats_mod._client_of("direct:5") is None
    assert chats_mod._client_of("direct-ask:") is None and chats_mod._client_of(None) is None
    assert direct_turns.owner_ref("abc_DEF-123") == "direct-ask:abc_DEF-123"
    for bad in ("short", "a" * 65, "has space1", "dot.dot.dot", "", None, 12345678):
        assert direct_turns.valid_client_id(bad) is False
        with pytest.raises(ValueError):
            direct_turns.owner_ref(bad)


# ---- retries store their reply ---------------------------------------------------------------------------------------------------------------

def rows(world, sid):
    return [dict(r) for r in world.db.conn().execute("SELECT id, kind, role, src_ref, text, meta_json FROM chat_messages WHERE session_id = ? ORDER BY id", (sid,))]


def test_a_retry_after_a_failed_turn_lands_its_reply_under_its_own_refs(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    user = chat_api._store_user_line(services, sid, "go")
    chat_api._answer(services, FakePort(partial("half an answ"), RuntimeError("boom")), sid, user, ChatTurnIn(text="go"))
    assert attempts_stored(world.db.conn(), sid, user) == [1] and next_attempt(world.db.conn(), sid, user) == 2
    chat_api._answer(services, FakePort(partial("the whole answer"), done("the whole answer")), sid, user, ChatTurnIn(text="go"), attempt=2)
    refs = [r["src_ref"] for r in rows(world, sid) if r["role"] == "agent"]
    assert refs == [f"direct:{user}", f"direct-error:{user}", f"direct:{user}.2"]
    assert attempts_stored(world.db.conn(), sid, user) == [1, 2] and next_attempt(world.db.conn(), sid, user) == 3
    shown = chats.messages(sid)
    assert [(m.attempt, m.superseded) for m in shown if m.role == "agent"] == [(1, True), (1, True), (2, False)]
    assert all(m.turn == user for m in shown if m.role == "agent")


def test_a_retry_after_a_stopped_turn_lands_its_reply(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    user = chat_api._store_user_line(services, sid, "go")
    chat_api._answer(services, FakePort(partial("part"), CallCancelledError("stopped")), sid, user, ChatTurnIn(text="go"))
    chat_api._answer(services, FakePort(done("fine")), sid, user, ChatTurnIn(text="go"), attempt=next_attempt(world.db.conn(), sid, user))
    last = chats.messages(sid)[-1]
    assert (last.kind, last.text, last.attempt, last.superseded) == ("text", "fine", 2, False)
    assert [m.superseded for m in chats.messages(sid) if m.role == "agent"] == [True, True, False]


def test_a_second_retry_supersedes_the_first_one_too(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    user = chat_api._store_user_line(services, sid, "go")
    for n in (1, 2, 3):
        chat_api._answer(services, FakePort(done(f"try {n}")), sid, user, ChatTurnIn(text="go"), attempt=n)
    agents = [m for m in chats.messages(sid) if m.role == "agent"]
    assert [(m.text, m.attempt, m.superseded) for m in agents] == [("try 1", 1, True), ("try 2", 2, True), ("try 3", 3, False)]


def test_a_replayed_owner_line_is_the_same_line_not_a_second_one_nor_a_crash(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    first = chat_api._store_user_line(services, sid, "go", client_id="client-0001")
    again = chat_api._store_user_line(services, sid, "go", client_id="client-0001")
    assert again == first and len([r for r in rows(world, sid) if r["role"] == "user"]) == 1
    assert find_owner_line(world.db.conn(), sid, "client-0001") == first and find_owner_line(world.db.conn(), sid, "client-0002") is None
    shown = chats.messages(sid)[0]
    assert shown.client_id == "client-0001" and shown.attempt is None and shown.turn is None
    assert chat_api._post(services, sid, role="user", who="user", kind="text", text="x", src_ref="direct-ask:client-0001") is None        # `_post` says None, it does not raise


def test_recover_interrupted_treats_a_reply_of_any_attempt_as_an_answer(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    a = chat_api._store_user_line(services, sid, "one", client_id="client-aaaa")
    b = chat_api._store_user_line(services, sid, "two", client_id="client-bbbb")
    chat_api._answer(services, FakePort(done("a2")), sid, a, ChatTurnIn(text="one"), attempt=2)        # only a retry's reply is stored for line a
    assert recover_interrupted(world.db, chats) == 1                                                    # line b only
    assert [m.turn for m in chats.messages(sid) if m.kind == "error"] == [b]


def test_a_longer_owner_id_never_widens_the_like_to_another_line(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    ids = [chat_api._store_user_line(services, sid, f"line {n}") for n in range(12)]
    small, big = min(ids), max(ids)
    chat_api._answer(services, FakePort(done("x")), sid, small, ChatTurnIn(text="x"), attempt=2)
    assert attempts_stored(world.db.conn(), sid, small) == [2]
    assert attempts_stored(world.db.conn(), sid, big) == []


# ---- superseded stays out of the model's history -------------------------------------------------------------------------------------------

def test_superseded_replies_are_not_carried_to_the_model_but_stay_in_the_transcript(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    user = chat_api._store_user_line(services, sid, "question")
    chat_api._answer(services, FakePort(done("the first answer")), sid, user, ChatTurnIn(text="question"))
    chat_api._answer(services, FakePort(done("the better answer")), sid, user, ChatTurnIn(text="question"), attempt=2)
    carried = [m.text for m in ChatTranscripts(chats).messages(sid, 20)]
    assert "the better answer" in carried and "the first answer" not in carried and "question" in carried
    assert "the first answer" in [m.text for m in chats.messages(sid)]                      # the transcript keeps it (it may have changed files)
    assert "the first answer" in [m.text for m in chats.last_messages(sid, 20)]


# ---- additive fields and the sibling key -----------------------------------------------------------------------------------------------------

def test_ordered_is_a_sibling_key_of_the_blocks_and_round_trips_into_the_message(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    user = chat_api._store_user_line(services, sid, "go")
    blocks = [{"type": "text", "kind": "other", "text": "Reading."}, {"type": "tool_use", "kind": "read", "name": "Read", "text": "a.py"},
              {"type": "text", "kind": "other", "text": "Done."}]
    endings = direct_turns.finished(user, {"text": "Reading.Done.", "blocks": blocks}, ordered=True)
    chat_api._post_all(services, sid, endings)
    stored = [r for r in rows(world, sid) if r["src_ref"] == f"direct:{user}"][0]
    meta = json.loads(stored["meta_json"])
    assert meta["ordered"] is True and [b["type"] for b in meta["blocks"]] == ["text", "tool_use", "text"]
    shown = [m for m in chats.messages(sid) if m.role == "agent"][0]
    assert shown.ordered is True and [b.type for b in shown.blocks] == ["text", "tool_use", "text"] and shown.attempt == 1 and shown.superseded is False


def test_a_legacy_reply_is_not_ordered_and_the_wire_shape_keeps_its_old_keys(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    user = chat_api._store_user_line(services, sid, "go")
    chat_api._answer(services, FakePort(done("plain", blocks=[{"type": "text", "kind": "other", "text": ""}])), sid, user, ChatTurnIn(text="go"))
    reply = [m for m in chats.messages(sid) if m.role == "agent"][0]
    wire = reply.model_dump(mode="json")
    assert reply.ordered is False and "ordered" not in wire and "superseded" not in wire and wire["attempt"] == 1
    owner = chats.messages(sid)[0].model_dump(mode="json")
    assert "attempt" not in owner and "superseded" not in owner and "client_id" in owner               # the owner's line shows its id; no other row does


def test_text_stored_twice_is_bounded_by_the_message_cap():
    big = "x" * (direct_turns.MAX_TEXT + 5000)
    blocks = [{"type": "text", "kind": "other", "text": big[:100_000]}, {"type": "text", "kind": "other", "text": big[100_000:200_000]}]
    ending = direct_turns.finished(1, {"text": big, "blocks": blocks}, ordered=True)[-1]
    assert len(ending.text) == direct_turns.MAX_TEXT
    assert sum(len(b["text"]) for b in ending.blocks) <= direct_turns.MAX_TEXT            # the blocks never hold more than the cap: at most 2x per message


def test_stopped_and_failed_keep_the_blocks_on_the_row_they_store_and_name_the_attempt():
    blocks = [{"type": "tool_use", "kind": "run", "name": "Bash", "text": "ls"}]
    s = direct_turns.stopped(5, "wrote this", 3, blocks=blocks, ordered=True)
    assert [(e.kind, e.src_ref, bool(e.blocks), e.ordered) for e in s] == [("text", "direct:5.3", True, True), ("note", "direct-note:5.3", False, False)]
    f = direct_turns.failed(5, "", "no", 2, blocks=blocks, ordered=True)
    assert [(e.kind, e.src_ref, bool(e.blocks)) for e in f] == [("error", "direct:5.2", True)]
    e = direct_turns.stopped(5, "", 2, blocks=blocks, ordered=True)
    assert [(x.kind, x.text, x.src_ref, bool(x.blocks)) for x in e] == [("note", direct_turns.STOPPED_EMPTY, "direct:5.2", True)]
    assert direct_turns.stopped(5, "")[0].blocks == [] and direct_turns.finished(5, {"text": "t"}, 2)[-1].src_ref == "direct:5.2"
