"""The owner's note to an agent (D132): POST /api/chats/{sid}/steer stores the line in the agent's session of the live run and writes the agent's entry of
`<run>/node_context.json`, which the engine appends to that agent's system prompt from its next call."""
from __future__ import annotations

import json
import stat

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import TEnv, ev, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.engine.events import EventWriter
from sutra_app.engine.hooks import ADDENDUM_HEADING, EventHooks
from sutra_app.orchestrator.api import agent as agent_api
from sutra_app.orchestrator.api import agent_chats
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = {"X-Sutra-Token": "test-token-0123456789abcdef"}


@pytest.fixture
def client(tenv):  # noqa: F811
    app = FastAPI()
    services = Services(settings=tenv.settings, version="t", db=tenv.db, redact=Redactor(None, environ={"MY_API_TOKEN": "hunter2hunter2"}))
    services.tasks, services.chats = tenv.service, tenv.chats
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(agent_chats.build_router())
    app.include_router(agent_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


def session_of(t: TEnv, node_id: str) -> str:
    return t.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", node_id)


def context(t: TEnv, task_id: str) -> dict:
    return json.loads((t.run_dir(task_id) / "node_context.json").read_text())


def code(r, status):
    assert r.status_code == status, r.text
    return r.json()["error"]["code"]


def test_a_note_to_a_function_agent_is_stored_marked_and_written_for_the_engine(client, tenv):  # noqa: F811
    task = tenv.started()
    sid = session_of(tenv, "web.audit")
    r = client.post(f"/api/chats/{sid}/steer", json={"text": "  Check the footer links too.  "}, headers=TOKEN)
    assert r.status_code == 200 and r.json()["applies"] == "next_call" and r.json()["session_id"] == sid
    line = tenv.chats.messages(sid)[-1]
    assert (line.id, line.role, line.who, line.text, line.steer, line.task_id) == (r.json()["message_id"], "user", "user", "Check the footer links too.", True, task)
    assert line.model_dump(mode="json")["steer"] is True
    assert context(tenv, task) == {"audit": "Owner's note: Check the footer links too."}
    path = tenv.run_dir(task) / "node_context.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and not list(path.parent.glob(".node_context*"))
    client.post(f"/api/chats/{sid}/steer", json={"text": "And the\nmenu page."}, headers=TOKEN)
    other = client.post(f"/api/chats/{session_of(tenv, 'web.priority')}/steer", json={"text": "Keep prices round."}, headers=TOKEN)
    assert other.status_code == 200
    assert context(tenv, task) == {"audit": "Owner's note: Check the footer links too.\nOwner's note: And the menu page.", "priority": "Owner's note: Keep prices round."}


def test_the_engines_next_call_carries_the_note_under_node_context(client, tenv, tmp_path):  # noqa: F811
    task = tenv.started()
    client.post(f"/api/chats/{session_of(tenv, 'web.audit')}/steer", json={"text": "Check the footer."}, headers=TOKEN)
    writer = EventWriter(tmp_path)
    hooks = EventHooks(writer, lambda: None, node_context_file=tenv.run_dir(task) / "node_context.json")
    assert hooks.system_addendum("audit") == ADDENDUM_HEADING + "Owner's note: Check the footer." and hooks.system_addendum("identity") == ""
    client.post(f"/api/chats/{session_of(tenv, 'web.audit')}/steer", json={"text": "Then the header."}, headers=TOKEN)
    assert hooks.system_addendum("audit").endswith("Owner's note: Then the header.")                 # re-read on every call
    writer.close()


def test_a_note_to_a_builder_is_keyed_by_its_name_and_lands_in_its_step_session(client, tenv):  # noqa: F811
    task = tenv.started()
    tenv.write_events(task, ev("step", step="W-3", name="Menu page", status="running"))
    tenv.drain(task)
    sid = tenv.one("SELECT chat_session_id FROM graph_nodes WHERE task_id = ? AND step_ref = 'W-3'", task)
    assert client.post(f"/api/chats/{sid}/steer", json={"text": "Use the cafe's green."}, headers=TOKEN).status_code == 200
    assert context(tenv, task) == {"W-3": "Owner's note: Use the cafe's green."} and tenv.chats.messages(sid)[-1].steer is True


def test_a_note_is_capped_at_two_thousand_characters_and_the_oldest_notes_go_first():
    from sutra_app.orchestrator.agent_sessions import compose_notes
    first = compose_notes("", "a" * 1500)
    second = compose_notes(first, "b" * 1500)
    assert second == "Owner's note: " + "b" * 1500 and len(second) <= 2000
    third = compose_notes(compose_notes("", "x" * 900), "y" * 900)
    assert third.count("Owner's note:") == 2 and len(third) <= 2000
    assert len(compose_notes("", "z" * 2000)) == 2000 and compose_notes("", "z" * 2000).endswith("z")


def test_a_note_over_the_cap_is_refused_before_anything_is_stored(client, tenv):  # noqa: F811
    task = tenv.started()
    sid = session_of(tenv, "web.audit")
    long = client.post(f"/api/chats/{sid}/steer", json={"text": "n" * 2001}, headers=TOKEN)
    assert code(long, 422) == "validation" and "2000" in long.json()["error"]["message"]
    assert code(client.post(f"/api/chats/{sid}/steer", json={"text": "   "}, headers=TOKEN), 422) == "validation"
    assert tenv.chats.messages(sid) == [] and not (tenv.run_dir(task) / "node_context.json").exists()


def test_a_secret_in_a_note_never_reaches_the_chat_or_the_agent(client, tenv):  # noqa: F811
    task = tenv.started()
    sid = session_of(tenv, "web.audit")
    client.post(f"/api/chats/{sid}/steer", json={"text": "use sk-proj-REPRO1234567890abcdefghij and hunter2hunter2 for the test"}, headers=TOKEN)
    stored, written = tenv.chats.messages(sid)[-1].text, (tenv.run_dir(task) / "node_context.json").read_text()
    for text in (stored, written):
        assert "sk-proj-REPRO" not in text and "hunter2hunter2" not in text and "redacted" in text


def test_only_the_token_an_agent_chat_and_a_live_run_take_a_note(client, tenv):  # noqa: F811
    task = tenv.started()
    sid = session_of(tenv, "web.audit")
    assert code(client.post(f"/api/chats/{sid}/steer", json={"text": "x"}), 401) == "bad_token"
    assert code(client.post(f"/api/chats/{session_of(tenv, 'web')}/steer", json={"text": "x"}, headers=TOKEN), 422) == "rules"             # a team chat is written to directly
    assert code(client.post("/api/chats/cs_000000000fff/steer", json={"text": "x"}, headers=TOKEN), 404) == "not_found"
    assert code(client.post(f"/api/chats/{sid}/messages", json={"text": "hello"}, headers=TOKEN), 403) == "read_only"                  # an ordinary message stays refused
    tenv.projector.mark_ended(task, "done", "ok")
    gone = client.post(f"/api/chats/{sid}/steer", json={"text": "too late"}, headers=TOKEN)
    assert code(gone, 409) == "not_running" and "over" in gone.json()["error"]["message"]
    assert not (tenv.run_dir(task) / "node_context.json").exists() and tenv.chats.messages(sid) == []


def test_a_note_to_a_function_agent_that_has_not_spoken_in_this_run_rolls_its_session_so_it_lands_in_this_run(client, tenv):  # noqa: F811
    first = tenv.started(title="Cafe page")
    tenv.write_events(first, ev("say", id=1, who="audit", text="Nothing wrong", next="identity"))
    tenv.drain(first)
    old = session_of(tenv, "web.audit")
    tenv.projector.mark_ended(first, "done", "ok")
    second = tenv.new(text="Menu page please", title="Menu page").id
    tenv.run(tenv.service.start_ready())
    tenv.write_events(second, ev("run.started", pid=tenv.row(second).pid, schema="events/1", mock=True, seed="none"))
    tenv.drain(second)
    r = client.post(f"/api/chats/{old}/steer", json={"text": "Be strict this time."}, headers=TOKEN)
    assert r.status_code == 200 and r.json()["session_id"] != old and session_of(tenv, "web.audit") == r.json()["session_id"]
    assert [m.text for m in tenv.chats.messages(old)] == ["Nothing wrong"] and tenv.chats.messages(r.json()["session_id"])[-1].steer is True
    assert context(tenv, second) == {"audit": "Owner's note: Be strict this time."}
    again = client.post(f"/api/chats/{old}/steer", json={"text": "x"}, headers=TOKEN)                 # the old, archived chat is no longer the agent's
    assert code(again, 409) == "not_running"
