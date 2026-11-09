"""Chat routes v2 (work package ABS-7): search, archive, providers and choice, upload, the direct streamed chat, the partial event."""
from __future__ import annotations

import base64
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_chat_store import msg
from orchestrator.test_graph_store import World

from sutra_app.connectors.chat_models import ChatEvent
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.factory import build_router
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.orchestrator.api import chat as chat_api
from sutra_app.orchestrator.api import chat_v2
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.attachments import Attachments
from sutra_app.orchestrator.chats import ChatStore, ChatTranscripts
from sutra_app.orchestrator.events import PARTIAL, EventBus
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = "test-token-0123456789abcdef"
H = {"X-Sutra-Token": TOKEN}


@pytest.fixture
def world(db, clock):
    return World(db, clock)


@pytest.fixture
def rig(world, settings, tmp_path):
    chats = ChatStore(world.db)
    bus = EventBus(clock=world.db._clock)
    # a private work root: the default is the machine-wide <tempdir>/sutra-app-<uid>/work, where a session.json or system.txt of an earlier
    # run (the session ids are the same every run) would be read back and a test of what the route writes there would pass without the write
    config = ConnectorConfig(data_dir=settings.data_dir, work_root=tmp_path / "work")
    router = build_router(settings.model_copy(update={"connector": "stub"}), transcripts=ChatTranscripts(chats), session_hook=chats.set_provider,
                          config=config)
    attachments = Attachments(settings.data_dir)
    services = Services(settings=settings, version="t", db=world.db, redact=Redactor(None, environ={}))
    services.chats, services.bus = chats, bus
    services.chat_port, services.attachments = RouterChatPort(router, attachments=attachments.store), attachments
    app = FastAPI()
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    for module in (chat_v2, chat_api):                    # the real order: chat_v2 first, so /chats/search is not a session id
        app.include_router(module.build_router())
    client = TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)
    yield client, world, chats, bus, services
    router.close()


def say(world, sid, text, who="user"):
    with world.db.tx() as tx:
        ChatStore(world.db).post(tx, sid, msg(sid, text, who=who))


def wait_for(cond, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def error_code(r, status):
    assert r.status_code == status, r.text
    return r.json()["error"]["code"]


# ---- search ------------------------------------------------------------------------------------------------------------------------

def test_search_returns_rows_and_search_is_not_taken_for_a_session(rig):
    client, world, *_ = rig
    sid = world.session_of["web"]
    say(world, sid, "the zebra plan")
    r = client.get("/api/chats/search", params={"q": "zebra"})
    assert r.status_code == 200 and r.json()["results"][0]["session_id"] == sid and set(r.json()["results"][0]) == {"session_id", "message_id", "title", "snippet", "at", "archived"}
    assert client.get("/api/chats/search", params={"q": "zebra", "scope": "node:menu"}).json()["results"] == []
    assert error_code(client.get("/api/chats/search", params={"q": "x", "scope": "bad scope"}), 422) == "validation"


def test_search_needs_no_token_but_hides_archived_chats_until_asked(rig):
    client, world, *_ = rig
    sid = world.session_of["web"]
    say(world, sid, "needle")
    assert client.post(f"/api/chats/{sid}/archive").status_code == 401
    assert client.post(f"/api/chats/{sid}/archive", headers=H).json() == {"session_id": sid, "archived": True}
    assert client.get("/api/chats/search", params={"q": "needle"}).json()["results"] == []
    assert len(client.get("/api/chats/search", params={"q": "needle", "include": "archived"}).json()["results"]) == 1
    assert client.post(f"/api/chats/{sid}/unarchive", headers=H).json()["archived"] is False
    assert len(client.get("/api/chats/search", params={"q": "needle"}).json()["results"]) == 1
    assert error_code(client.post("/api/chats/cs_org/archive", headers=H), 422) == "rules"
    assert error_code(client.post("/api/chats/cs_000000000fff/archive", headers=H), 404) == "not_found"


# ---- providers and choice ----------------------------------------------------------------------------------------------------------

def test_providers_lists_the_pill_and_an_unrunnable_choice_is_refused(rig):
    client, world, *_ = rig
    sid = world.session_of["web"]
    r = client.get(f"/api/chats/{sid}/providers")
    assert r.status_code == 200 and r.json()["providers"] == [] and r.json()["chosen"] is None          # a stub-only router offers no claude or codex
    assert (r.json()["kind"], r.json()["agent"], r.json()["own"]) == ("department", None, None)         # D131: what the chat is, its own pick (none) and what it resolves to
    assert r.json()["effective"]["source"] == "default"
    assert error_code(client.put(f"/api/chats/{sid}/choice", json={"provider": "codex"}, headers=H), 422) == "validation"
    assert error_code(client.put(f"/api/chats/{sid}/choice", json={"provider": "gemini"}, headers=H), 422) == "validation"
    assert error_code(client.put(f"/api/chats/{sid}/choice", json={"provider": "codex"}), 401) == "bad_token"


def test_clearing_a_choice_is_accepted(rig):
    client, world, *_ = rig
    sid = world.session_of["web"]
    r = client.put(f"/api/chats/{sid}/choice", json={"provider": None}, headers=H)
    assert r.status_code == 200 and r.json()["provider"] is None


def test_the_choice_route_passes_model_and_effort_and_a_refusal_names_the_valid_ones(rig):
    """welcome-settings, item 4: PUT /choice {provider, model, effort}; the 422 carries the port's sentence with the models it offers."""
    from sutra_app.connectors.chat_models import Choice
    from sutra_app.connectors.errors import InvalidRequestError
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    seen = []

    class Port:
        def choose(self, session_id, provider, model=None, effort=None):
            seen.append((session_id, provider, model, effort))
            if model == "opuss":
                raise InvalidRequestError("opuss is not a model claude offers. Choose one of: best, opus, sonnet")
            return Choice(session_id=session_id, provider=provider, model=model, effort=effort)

    services.chat_port = Port()
    ok = client.put(f"/api/chats/{sid}/choice", json={"provider": "claude", "model": "opus", "effort": "max"}, headers=H)
    assert ok.status_code == 200 and {k: ok.json()[k] for k in ("session_id", "provider", "model", "effort")} == {"session_id": sid, "provider": "claude", "model": "opus", "effort": "max"}
    assert ok.json()["source"] == "own" and ok.json()["effective"] == {"provider": "claude", "model": "opus", "effort": "max", "source": "own"}
    assert client.put(f"/api/chats/{sid}/choice", json={"provider": "claude"}, headers=H).json()["effort"] is None
    bad = client.put(f"/api/chats/{sid}/choice", json={"provider": "claude", "model": "opuss"}, headers=H)
    assert error_code(bad, 422) == "validation" and "best, opus, sonnet" in bad.json()["error"]["message"]
    assert error_code(client.put(f"/api/chats/{sid}/choice", json={"provider": "claude", "effort": "ultra"}, headers=H), 422) == "validation"
    assert error_code(client.put(f"/api/chats/{sid}/choice", json={"provider": "claude", "model": "opus", "effort": "max"}), 401) == "bad_token"
    assert seen == [(sid, "claude", "opus", "max"), (sid, "claude", None, None), (sid, "claude", "opuss", None)]      # the refused and the unauthorised never passed on


# ---- attachments -------------------------------------------------------------------------------------------------------------------

def test_an_upload_stores_the_file_once_and_refuses_what_is_not_a_kind_we_take(rig):
    client, world, *_ = rig
    sid = world.session_of["web"]
    blob = base64.b64encode(b"hello notes").decode()
    a = client.post(f"/api/chats/{sid}/attachments", json={"name": "notes.txt", "content_b64": blob}, headers=H)
    b = client.post(f"/api/chats/{sid}/attachments", json={"name": "again.txt", "content_b64": blob}, headers=H)
    assert a.status_code == 200 and a.json()["id"] == b.json()["id"] and a.json()["kind"] == "text"
    assert error_code(client.post(f"/api/chats/{sid}/attachments", json={"name": "a.exe", "content_b64": base64.b64encode(b"MZ").decode()}, headers=H), 422) == "validation"
    assert error_code(client.post(f"/api/chats/{sid}/attachments", json={"name": "a.txt", "content_b64": "***"}, headers=H), 422) == "validation"
    assert error_code(client.post(f"/api/chats/{sid}/attachments", json={"name": "a.txt", "content_b64": blob}), 401) == "bad_token"


# ---- the direct chat ---------------------------------------------------------------------------------------------------------------

def test_a_direct_turn_stores_the_user_line_then_one_reply_and_streams_partials_that_are_not_replayed(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    seen = []
    real = bus.publish_one
    bus.publish_one = lambda type_, data=None: (seen.append((type_, data)), real(type_, data))[1]
    r = client.post(f"/api/chats/{sid}/direct", json={"text": "hello there"}, headers=H)
    assert r.status_code == 202 and r.json()["turn"] == "started"
    assert wait_for(lambda: len(chats.messages(sid)) == 2)
    user, agent = chats.messages(sid)
    assert (user.role, user.text, agent.role, agent.kind, agent.state) == ("user", "hello there", "agent", "text", "ok") and agent.text
    partials = [d for t, d in seen if t == PARTIAL]
    assert chats.messages(sid)[1].turn == user.id and chats.messages(sid)[0].turn is None          # the reply names the line it answers
    assert "turn" not in chats.messages(sid)[0].model_dump(mode="json")
    assert partials and "".join(p["delta"] for p in partials) == agent.text and all(p["session_id"] == sid and p["message_id"] == user.id for p in partials)
    assert all(e.type != PARTIAL for e in bus.replay(0).events)               # a reconnect gets the stored message, never half of one


def test_a_direct_chat_needs_the_token_a_writable_team_chat_and_one_turn_at_a_time(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": "x"}), 401) == "bad_token"
    assert error_code(client.post(f"/api/chats/{sid}/direct/stop", json={}), 401) == "bad_token"
    assert error_code(client.post("/api/chats/cs_000000000fff/direct", json={"text": "x"}, headers=H), 404) == "not_found"
    assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": ""}, headers=H), 422) == "validation"
    assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": "x", "attachments": ["0" * 64]}, headers=H), 404) == "not_found"
    chat_v2._running.add(sid)
    try:
        assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": "x"}, headers=H), 409) == "busy"
    finally:
        chat_v2._running.discard(sid)


def test_partial_is_a_control_event_never_in_the_ring(rig):
    _, _, _, bus, _ = rig
    before = bus.head
    ev = bus.publish_one(PARTIAL, {"session_id": "cs_org", "delta": "x"})
    assert ev.seq == 0 and bus.head == before and bus.replay(0).events == ()


def test_the_org_chat_can_be_asked_directly_when_the_owner_chooses_it(rig):
    client, world, chats, bus, services = rig
    r = client.post("/api/chats/cs_org/direct", json={"text": "what can you do?"}, headers=H)       # D115: an opt-in, beside the staged path
    assert r.status_code == 202
    assert wait_for(lambda: len(chats.messages("cs_org")) >= 2 and "cs_org" not in chat_v2._running)
    assert [m.role for m in chats.messages("cs_org")][-2:] == ["user", "agent"]


def test_stop_says_whether_a_turn_was_running(rig):
    client, world, *_ = rig
    sid = world.session_of["web"]
    r = client.post(f"/api/chats/{sid}/direct/stop", headers=H)
    assert r.status_code == 200 and r.json() == {"session_id": sid, "stopped": False}          # nothing is answering
    assert error_code(client.post("/api/chats/cs_000000000fff/direct/stop", headers=H), 404) == "not_found"


def test_archiving_a_teams_chat_leaves_the_team_a_working_active_chat(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    assert client.post(f"/api/chats/{sid}/archive", headers=H).status_code == 200
    row = world.db.conn().execute("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'").fetchone()
    assert row[0] != sid
    listed = client.get("/api/chats").json()
    assert row[0] in {c.get("id") or c.get("session_id") for c in listed} and sid not in {c.get("id") or c.get("session_id") for c in listed}
    assert world.db.conn().execute("SELECT status, writable FROM chat_sessions WHERE id = ?", (row[0],)).fetchone()[:] == ("active", 1)
    r = client.post(f"/api/chats/{row[0]}/direct", json={"text": "still there?"}, headers=H)
    assert r.status_code == 202
    assert wait_for(lambda: len(chats.messages(row[0])) == 2)


def test_a_message_to_an_archived_chat_is_refused_saying_it_was_archived(rig):
    """QA direct-chat P3: a second tab that still showed the chat as live got 'This chat cannot be asked directly', which says nothing of the cause."""
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    assert client.post(f"/api/chats/{sid}/archive", headers=H).status_code == 200
    r = client.post(f"/api/chats/{sid}/direct", json={"text": "still there?"}, headers=H)
    assert r.status_code == 403 and r.json()["error"]["code"] == "read_only"
    assert r.json()["error"]["message"] == "This chat was archived. Open the team's current chat to write."
    assert chats.messages(sid) == []
    org = client.post("/api/chats/cs_org/direct", json={"text": "hi"}, headers=H)               # a chat that is live but not for the model keeps its own words
    assert org.status_code == 202
    assert wait_for(lambda: "cs_org" not in chat_v2._running)


def test_a_credential_typed_in_a_direct_chat_is_never_stored(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "my key sk-abcdefgh12345678 ok"}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2)
    user = chats.messages(sid)[0]
    assert "sk-abcdefgh12345678" not in user.text and "[redacted:openai-key]" in user.text


# ---- QA direct-chat bug 7: a message over the cap is refused in words -------------------------------------------------------------------------------

def test_a_direct_message_over_8000_characters_is_refused_with_a_sentence_that_names_the_limit(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    r = client.post(f"/api/chats/{sid}/direct", json={"text": "x" * 8500}, headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert r.json()["error"]["message"] == "Messages can be up to 8000 characters; this one has 8500."
    violation = r.json()["error"]["details"]["violations"][0]
    assert violation["path"] == "text" and "8000" in violation["message"]
    assert chats.messages(sid) == [] and sid not in chat_v2._running               # nothing was stored or started


def test_the_cap_counts_characters_not_bytes_and_the_longest_message_is_taken(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "é" * 8000}, headers=H).status_code == 202          # 16 000 bytes, 8 000 characters
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_v2._running)
    over = client.post(f"/api/chats/{sid}/direct", json={"text": "é" * 8001}, headers=H)
    assert over.status_code == 422 and over.json()["error"]["message"].endswith("this one has 8001.")


def test_a_message_far_over_the_cap_is_still_refused_by_the_model_check(rig):
    client, world, *_ = rig
    sid = world.session_of["web"]
    assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": "x" * 250_000}, headers=H), 422) == "validation"


# ---- QA direct-chat bug 3: a page that did not start the turn can learn that the chat is answering ---------------------------------------------------

def test_the_session_says_which_line_the_running_direct_turn_answers_and_not_before_or_after(rig):
    from sutra_app.orchestrator import direct_running
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    assert client.get(f"/api/chats/{sid}").json()["direct_turn"] is None
    assert {s["id"]: s["direct_turn"] for s in client.get("/api/chats").json()}[sid] is None
    assert direct_running.begin(sid)
    try:
        assert client.get(f"/api/chats/{sid}").json()["direct_turn"] is None         # claimed, the owner's line not stored yet: nothing to name
        direct_running.attach(sid, 41)
        assert client.get(f"/api/chats/{sid}").json()["direct_turn"] == 41
        assert {s["id"]: s["direct_turn"] for s in client.get("/api/chats").json()}[sid] == 41
        assert client.get("/api/chats/cs_org").json()["direct_turn"] is None          # another chat is not answering
    finally:
        direct_running.end(sid)
    assert client.get(f"/api/chats/{sid}").json()["direct_turn"] is None


def test_the_session_names_a_real_running_direct_turn_until_its_reply_is_stored(rig):
    """The real route, with a port that waits for the test: while it waits the session names the owner's line; when it is stored the name is gone."""
    import threading
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    gate, started = threading.Event(), threading.Event()

    class Waiting:
        def stream(self, sid_, turn):
            started.set()
            gate.wait(10)
            yield ChatEvent(kind="turn_done", data={"text": "done", "provider": "claude", "model": None, "usd": None, "blocks": [], "switched": None})

        def set_system(self, *a):
            return None

        def stop(self, sid_):
            return False

    services.chat_port = Waiting()
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "slow one"}, headers=H).status_code == 202
    assert started.wait(10)
    line = chats.messages(sid)[0]
    assert client.get(f"/api/chats/{sid}").json()["direct_turn"] == line.id
    assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": "again"}, headers=H), 409) == "busy"
    gate.set()
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_v2._running)
    assert client.get(f"/api/chats/{sid}").json()["direct_turn"] is None
    assert chats.messages(sid)[1].turn == line.id


def test_the_old_name_of_the_running_set_is_the_same_set(rig):
    from sutra_app.orchestrator import direct_running
    assert chat_v2._running is direct_running.RUNNING
