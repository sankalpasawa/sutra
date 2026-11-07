"""QA direct-chat bug 4: a direct turn that the process did not survive is marked at the next start.

A graceful stop stores 'Stopped before the model wrote anything.'; a SIGKILL, a crash or a power cut left the owner's line with no reply, no error and no
Retry, and nothing said that the turn had died. The owner's line of a direct turn now carries `src_ref = direct-ask:<id>`; the next start finds the ones with
no ending (`direct:<their id>` is the first message of every ending) and gives each the error line 'Interrupted: the app closed before the model answered.'
(Retry is offered by the page, as for any failed direct turn)."""
from __future__ import annotations

import pytest
from orchestrator.test_api_chat_v2 import H, rig, say, wait_for, world  # noqa: F401  (the fixtures of the chat v2 routes)
from orchestrator.test_direct_turn_endings import FakePort, done, partial

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.errors import CallCancelledError
from sutra_app.orchestrator.api import chat_v2 as chat_api
from sutra_app.orchestrator.chat_v2 import DIRECT_ASK, INTERRUPTED, recover_interrupted


def marks(world, sid):
    rows = world.db.conn().execute("SELECT id, role, kind, src_ref, text FROM chat_messages WHERE session_id = ? ORDER BY id", (sid,)).fetchall()
    return [dict(r) for r in rows]


def test_the_owner_line_of_a_direct_turn_is_marked_and_the_mark_does_not_show_in_the_page_shape(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    line = chat_api._store_user_line(services, sid, "write the menu")
    [row] = marks(world, sid)
    assert row["id"] == line and row["role"] == "user" and row["src_ref"].startswith(DIRECT_ASK) and len(row["src_ref"]) > len(DIRECT_ASK) + 8
    shown = chats.messages(sid)[0]
    assert shown.turn is None and "src_ref" not in shown.model_dump(mode="json")                # a line is not an answer: `turn` stays the replies' business
    other = chat_api._store_user_line(services, sid, "write the menu")                           # the same words again: its own mark
    assert marks(world, sid)[1]["src_ref"] != row["src_ref"] and other != line


def test_an_owner_line_with_no_ending_gets_the_interrupted_error_once_and_retry_can_find_its_line(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    line = chat_api._store_user_line(services, sid, "restart me mid-turn")                      # the process died here: no _answer, no ending
    assert recover_interrupted(world.db, chats) == 1
    last = chats.messages(sid)[-1]
    assert (last.role, last.kind, last.text, last.turn) == ("agent", "error", INTERRUPTED, line)
    assert INTERRUPTED == "Interrupted: the app closed before the model answered."
    assert marks(world, sid)[-1]["src_ref"] == f"direct:{line}"
    assert recover_interrupted(world.db, chats) == 0 and len(chats.messages(sid)) == 2          # a second start adds nothing


def test_turns_that_ended_any_way_and_lines_of_the_team_route_are_left_alone(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    for script in ([partial("Hi"), done("Hi")], [CallCancelledError("stopped")], [partial("half"), RuntimeError("no")]):
        user = chat_api._store_user_line(services, sid, "go")
        chat_api._answer(services, FakePort(*script), sid, user, ChatTurnIn(text="go"))        # a reply, a stop note, a failure: each is an ending
    say(world, sid, "a line for the team")                                                       # the team route's line has no mark and is not ours to answer
    before = len(chats.messages(sid))
    assert recover_interrupted(world.db, chats) == 0 and len(chats.messages(sid)) == before


def test_each_chat_with_a_dangling_line_is_marked_in_its_own_session(rig):
    client, world, chats, bus, services = rig
    web, menu = world.session_of["web"], world.session_of["menu"]
    a = chat_api._store_user_line(services, "cs_org", "org line")
    b = chat_api._store_user_line(services, web, "team line")
    c = chat_api._store_user_line(services, web, "newer team line")
    assert recover_interrupted(world.db, chats) == 3
    assert [m.turn for m in chats.messages("cs_org") if m.kind == "error"] == [a]
    assert [m.turn for m in chats.messages(web) if m.kind == "error"] == [b, c]
    assert chats.messages(menu) == [] or all(m.kind != "error" for m in chats.messages(menu))


def test_a_finished_turn_is_never_marked_by_a_later_call(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    client.post(f"/api/chats/{sid}/direct", json={"text": "hello there"}, headers=H)
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_api._running)
    assert recover_interrupted(world.db, chats) == 0
    assert [m.kind for m in chats.messages(sid)] == ["text", "text"]


def test_a_real_restart_marks_the_turn_the_last_run_left_and_the_page_sees_it_as_a_failed_turn_with_its_line(tmp_path):
    """Two starts on one data folder: the first ends with an owner's line that no turn answered (as after a kill -9), the second marks it at start-up."""
    from fastapi.testclient import TestClient
    from orchestrator.test_scripted_conversation import Scenario, make_scenario

    from sutra_app.orchestrator.testing.scripted import ScriptedConnector
    base = "http://127.0.0.1:8780"
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=base) as client:
        services = Scenario(client, app, ScriptedConnector()).services
        line = chat_api._store_user_line(services, "cs_org", "crash me then press Stop")
        assert [m["kind"] for m in client.get("/api/chats/cs_org/messages").json()["messages"]][-1] == "text"       # no ending yet
    app2, _ = make_scenario(tmp_path)
    with TestClient(app2, base_url=base) as client2:
        got = client2.get("/api/chats/cs_org/messages").json()["messages"]
        assert [(m["role"], m["kind"], m["text"], m.get("turn")) for m in got[-2:]] == [
            ("user", "text", "crash me then press Stop", None), ("agent", "error", INTERRUPTED, line)]
        assert client2.get("/api/chats/cs_org").json()["direct_turn"] is None                          # nothing answers: the page leaves the answering state
    app3, _ = make_scenario(tmp_path)
    with TestClient(app3, base_url=base) as client3:
        assert len(client3.get("/api/chats/cs_org/messages").json()["messages"]) == len(got)           # a third start adds nothing
