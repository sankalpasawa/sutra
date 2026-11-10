"""The owner's question to a function and its answer as lines of the function's chat (D148): `ChatMessageOut.ask` says which part a line plays, read from
its `src_ref` like `steer`, and it is left out of the wire for every other line. The question is `ask:<id>`, the answer `ask:<id>:records` or
`ask:<id>:model`; `agent_ask.py` writes them (tests/orchestrator/test_agent_ask.py), this file proves how they are read back."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_chat_store import msg
from orchestrator.test_graph_store import World

from sutra_app.orchestrator.api import chat as chat_api
from sutra_app.orchestrator.api.chat import MessagePage
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.chats import ASK_REF, STEER_REF, ChatStore, _ask_of
from sutra_app.orchestrator.models import ChatMessageOut
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services


@pytest.fixture
def world(db, clock):
    return World(db, clock)


@pytest.fixture
def chats(db):
    return ChatStore(db)


def say(world, chats, session, text, **over):
    with world.db.tx() as tx:
        return chats.post(tx, session, msg(session, text, **over))


# ---- the reading of a src_ref ------------------------------------------------------------------------------------------------------

def test_the_prefix_is_the_one_the_port_writes():
    assert ASK_REF == "ask:"


@pytest.mark.parametrize("src_ref,part", [
    ("ask:0123456789abcdef", "q"), ("ask:0123456789abcdef:records", "records"), ("ask:0123456789abcdef:model", "model"),
    ("ask:1", "q"), ("ask:x:records", "records"), ("ask:x:model", "model"),
    (None, None), ("", None), ("steer:0123456789abcdef", None), ("direct:12", None), ("direct-note:12", None),
    ("req:7:tsk_0123456789ab", None), ("choice:5", None), ("j2-20261104-100000-ab12#chat:3", None),
    ("xask:1", None), ("Ask:1", None), (" ask:1", None), ("records", None), ("model", None),
])
def test_ask_of_reads_the_part_a_line_plays(src_ref, part):
    assert _ask_of(src_ref) == part


def test_a_steer_note_is_not_an_ask_and_an_ask_is_not_a_steer(world, chats):
    session = world.session_of["web"]
    note = say(world, chats, session, "Check the footer.", who="user", src_ref=f"{STEER_REF}0123456789abcdef")
    question = say(world, chats, session, "Why?", who="user", src_ref=f"{ASK_REF}0123456789abcdef")
    assert (note.steer, note.ask) == (True, None) and (question.steer, question.ask) == (False, "q")


# ---- the store gives it back on every read -----------------------------------------------------------------------------------------

def test_every_read_of_the_store_carries_the_part_of_each_line(world, chats):
    session = world.session_of["web"]
    q = say(world, chats, session, "Why did W-2 pass?", who="user", src_ref="ask:aaaaaaaaaaaaaaaa")
    a = say(world, chats, session, "From the records: W-2 passed.", who="audit", src_ref="ask:aaaaaaaaaaaaaaaa:records")
    q2 = say(world, chats, session, "And W-3?", who="user", src_ref="ask:bbbbbbbbbbbbbbbb")
    m = say(world, chats, session, "W-3 passed with 0.91.", who="audit", src_ref="ask:bbbbbbbbbbbbbbbb:model")
    other = say(world, chats, session, "A line of the run.", who="audit", src_ref="run-1#chat:4")
    assert [x.ask for x in (q, a, q2, m, other)] == ["q", "records", "q", "model", None]
    assert [x.ask for x in chats.messages(session)] == ["q", "records", "q", "model", None]
    assert [x.ask for x in chats.last_messages(session, 3)] == ["q", "model", None]
    assert chats.message(a.id).ask == "records" and chats.message(m.id).ask == "model" and chats.message(other.id).ask is None
    assert [x.ask for x in chats.messages(session, after=a.id)] == ["q", "model", None]


def test_the_lines_keep_their_roles_so_the_transcript_still_reads_user_then_agent(world, chats):
    session = world.session_of["web"]
    q = say(world, chats, session, "Why?", who="user", src_ref="ask:cccccccccccccccc")
    a = say(world, chats, session, "Because.", who="audit", src_ref="ask:cccccccccccccccc:model")
    assert (q.role, q.who, a.role, a.who) == ("user", "user", "agent", "audit")


# ---- the wire: left out when absent, as steer is --------------------------------------------------------------------------------------

def test_ask_is_left_out_of_the_wire_when_absent_and_present_when_set(world, chats):
    session = world.session_of["web"]
    plain = say(world, chats, session, "A line.", who="audit")
    q = say(world, chats, session, "Why?", who="user", src_ref="ask:dddddddddddddddd")
    a = say(world, chats, session, "From the records: x.", who="audit", src_ref="ask:dddddddddddddddd:records")
    assert "ask" not in plain.model_dump(mode="json") and "ask" not in json.loads(plain.model_dump_json())
    assert q.model_dump(mode="json")["ask"] == "q" and a.model_dump(mode="json")["ask"] == "records"
    assert json.loads(a.model_dump_json())["ask"] == "records"
    for gone in ("steer", "turn", "passed_on", "blocks"):
        assert gone not in q.model_dump(mode="json")                     # the other optional keys stay out of an ordinary line, too


def test_the_model_accepts_only_the_three_parts():
    base = {"id": 1, "session_id": "cs_000000000001", "role": "agent", "who": "audit", "kind": "text", "text": "x", "at": "2026-11-04T10:00:00Z"}
    assert ChatMessageOut(**base).ask is None
    for part in ("q", "records", "model"):
        assert ChatMessageOut(**base, ask=part).ask == part
    with pytest.raises(ValueError):
        ChatMessageOut(**base, ask="note")


def test_a_message_round_trips_through_its_own_wire_form(world, chats):
    session = world.session_of["web"]
    a = say(world, chats, session, "From the records: x.", who="audit", src_ref="ask:eeeeeeeeeeeeeeee:records")
    assert ChatMessageOut.model_validate(json.loads(a.model_dump_json())) == a


# ---- the route and the event ------------------------------------------------------------------------------------------------------------

def test_the_messages_route_shows_ask_on_the_lines_that_have_it_and_nothing_on_the_others(world, chats, settings):
    app = FastAPI()
    services = Services(settings=settings, version="test", db=world.db, redact=Redactor(None, environ={}))
    services.chats = chats
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(chat_api.build_router())
    client = TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)
    session = world.session_of["web"]
    say(world, chats, session, "A line of the run.", who="audit", src_ref="run-1#chat:1")
    say(world, chats, session, "Why?", who="user", src_ref="ask:ffffffffffffffff")
    say(world, chats, session, "AI answer.", who="audit", src_ref="ask:ffffffffffffffff:model")
    response = client.get(f"/api/chats/{session}/messages")
    assert response.status_code == 200
    page = MessagePage.model_validate(response.json())
    assert [m.ask for m in page.messages] == [None, "q", "model"]
    wire = response.json()["messages"]
    assert ["ask" in m for m in wire] == [False, True, True] and [m.get("ask") for m in wire] == [None, "q", "model"]


def test_the_chat_message_event_carries_ask_so_the_panel_can_draw_both_lines_at_once(world, chats, events):
    session = world.session_of["web"]
    events.batches.clear()
    say(world, chats, session, "Why?", who="user", src_ref="ask:abababababababab")
    say(world, chats, session, "From the records: x.", who="audit", src_ref="ask:abababababababab:records")
    sent = [e for e in events.events if e.type == "chat.message"]
    assert [e.data["message"].get("ask") for e in sent] == ["q", "records"]
