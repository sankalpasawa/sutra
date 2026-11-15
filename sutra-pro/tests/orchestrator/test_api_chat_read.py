"""Chat, atom and usage read routes (ORCH-3): shapes validated against the response models, query rules, error bodies, reads
without a token, redaction, `GET /api/atoms/log` in seq order."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_atoms_usage import RUN, apply, fn_event, opened, uin, view_event
from orchestrator.test_chat_store import ATOM_CARD, QUESTION, card, msg
from orchestrator.test_graph_store import World

from factories_atom import close_with
from sutra_app.library.gate import GATE
from sutra_app.orchestrator.api import atoms as atoms_api
from sutra_app.orchestrator.api import chat as chat_api
from sutra_app.orchestrator.api import usage as usage_api
from sutra_app.orchestrator.api.chat import MessagePage
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.api.usage import UsageList, UsageSummary
from sutra_app.orchestrator.atoms import AtomStore
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.models import AtomLogRow, AtomOut, ChatMessageOut, ChatSessionOut, NeedsYouOut
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.usage import UsageStore


@pytest.fixture
def world(db, clock):
    return World(db, clock)


def make_client(world, settings, *, wired=True, redact=None) -> TestClient:
    app = FastAPI()
    services = Services(settings=settings, version="test", db=world.db, redact=redact or Redactor(None, environ={}))
    if wired:
        services.chats = ChatStore(world.db)
        services.atoms = AtomStore(world.db, chats=services.chats, graph=world.store)
        services.usage = UsageStore(world.db, chats=services.chats)
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    for module in (chat_api, atoms_api, usage_api):
        app.include_router(module.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def client(world, settings):
    return make_client(world, settings)


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and set(body["error"]) == {"code", "message", "details"}
    return body["error"]


def say(world, session, *args, **kw):
    with world.db.tx() as tx:
        return ChatStore(world.db).post(tx, session, msg(session, *args, **kw))


# ---- chats ---------------------------------------------------------------------------------------------------------------------------

def test_the_session_list_matches_the_model_and_the_org_chat_carries_its_phase(client, world):
    response = client.get("/api/chats")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/json")
    found = [ChatSessionOut.model_validate(s) for s in response.json()]
    assert len(found) == len(world.session_of) and {s.id: s.phase for s in found}["cs_org"] == "ready"
    assert [s.phase for s in found if s.id != "cs_org"] == [None] * (len(found) - 1)
    assert set(response.json()[0]) == {"id", "node_id", "kind", "title", "writable", "status", "filed_under", "connector", "model",
                                       "provider_session_id", "last_message_id", "note", "phase", "direct_turn", "pinned", "pinned_model", "pinned_effort", "run_id"}


def test_the_list_filters_by_node_and_adds_archived_sessions_on_request(client, world):
    assert [s["node_id"] for s in client.get("/api/chats", params={"node_id": "web"}).json()] == ["web"]
    world.sql("UPDATE chat_sessions SET status = 'archived', writable = 0, filed_under = 'sales' WHERE id = ?", world.session_of["menu"])
    assert world.session_of["menu"] not in [s["id"] for s in client.get("/api/chats").json()]
    shown = client.get("/api/chats", params={"include": "archived"}).json()
    menu = next(s for s in shown if s["id"] == world.session_of["menu"])
    assert (menu["status"], menu["filed_under"], menu["writable"]) == ("archived", "sales", False)
    error_of(client.get("/api/chats", params={"include": "all"}), 422, "validation")
    error_of(client.get("/api/chats", params={"node_id": "a b"}), 422, "validation")


def test_one_session_and_the_error_bodies(client, world):
    ok = client.get(f"/api/chats/{world.session_of['web']}")
    assert ChatSessionOut.model_validate(ok.json()).node_id == "web"
    assert client.get("/api/chats/cs_org").json()["phase"] == "ready"
    error_of(client.get("/api/chats/cs_000000000fff"), 404, "not_found")
    error_of(client.get("/api/chats/bad%20id"), 422, "validation")


def test_messages_come_as_a_page_with_a_cursor(client, world):
    sid = world.session_of["web"]
    ids = [say(world, sid, f"line {i}", at=100 + i).id for i in range(5)]
    page = client.get(f"/api/chats/{sid}/messages").json()
    assert set(page) == {"messages", "next_after"} and page["next_after"] == ids[-1]
    assert MessagePage.model_validate(page) and [m["text"] for m in page["messages"]] == [f"line {i}" for i in range(5)]
    assert set(page["messages"][0]) == {"id", "session_id", "role", "who", "kind", "text", "card", "pause", "answered_by", "task_id", "state", "at"}
    part = client.get(f"/api/chats/{sid}/messages", params={"after": ids[1], "limit": 2}).json()
    assert [m["id"] for m in part["messages"]] == ids[2:4] and part["next_after"] == ids[3]
    empty = client.get(f"/api/chats/{sid}/messages", params={"after": ids[-1]}).json()
    assert empty == {"messages": [], "next_after": ids[-1]}


def test_message_query_limits_and_unknown_sessions(client, world):
    sid = world.session_of["web"]
    for params in ({"limit": 0}, {"limit": 501}, {"after": -1}, {"limit": "many"}):
        error_of(client.get(f"/api/chats/{sid}/messages", params=params), 422, "validation")
    error_of(client.get("/api/chats/cs_000000000fff/messages"), 404, "not_found")
    assert client.get(f"/api/chats/{sid}/messages", params={"limit": 500}).status_code == 200


def test_a_card_message_is_sent_as_a_typed_card_and_a_division_session_serves_its_lens(client, world):
    fn_session = world.session_of["web.identity"]
    with world.db.tx() as tx:
        ChatStore(world.db).post(tx, fn_session, card(fn_session, ATOM_CARD))
    [shown] = client.get(f"/api/chats/{fn_session}/messages").json()["messages"]
    assert ChatMessageOut.model_validate(shown).card.type == "atom" and shown["card"]["atom_id"] == "a-3f9a1c2b7d-01"
    t = world.task(1, "web", "done", scope="menu")
    say(world, world.session_of["web"], "scoped to menu", task_id=t)
    say(world, world.session_of["web"], "not scoped")
    lens = client.get(f"/api/chats/{world.session_of['menu']}/messages").json()["messages"]
    assert [m["text"] for m in lens] == ["scoped to menu"] and lens[0]["session_id"] == world.session_of["web"]


def test_needs_you_lists_open_questions_in_the_response_model(client, world):
    assert client.get("/api/needs-you").json() == []
    q = say(world, world.session_of["web"], QUESTION, kind="question")
    [item] = client.get("/api/needs-you").json()
    need = NeedsYouOut.model_validate(item)
    assert (need.message_id, need.kind, need.dept_id, need.dept_name, need.options) == (q.id, "question", "web", "Web", ["Warm", "Clean [adds 5 work credits]"])
    assert set(item) == {"message_id", "session_id", "kind", "dept_id", "dept_name", "text", "options", "asked_at", "waiting_s", "stale"}
    assert isinstance(item["waiting_s"], int) and item["waiting_s"] >= 0 and isinstance(item["stale"], bool)      # gap attention: age by the server clock


# ---- atoms ---------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def filled(world):
    """One closed function atom (with its ledger row), one open one, and a closed builder atom."""
    store = AtomStore(world.db, chats=ChatStore(world.db), graph=world.store)
    task = world.task(1, "web", "running")
    step = world.step(task, "W-1", "web")
    first = opened()
    apply(world.db, store, fn_event(first), task=task)
    apply(world.db, store, fn_event(close_with(first.atom, 0)), task=task)
    apply(world.db, store, fn_event(opened(id="a-3f9a1c2b7d-02", node_id="web.priority")), task=task)
    apply(world.db, store, view_event(step, "open"), task=task)
    apply(world.db, store, view_event(step, "closed", attempt=1, ts_closed=5100), task=task)
    return {"task": task, "step": step, "first": first.atom.id}


def test_atoms_list_in_the_response_model_with_the_display_word_and_filters(client, world, filled):
    found = client.get("/api/atoms").json()
    assert len(found) == 3 and all(AtomOut.model_validate(a) for a in found)
    assert {a["state"] for a in found} == {"open", "closed"} and {a["schema"] for a in found} == {"work-atom/0.3", "atom/1"}
    assert set(found[0]) == {"id", "schema", "node_id", "task_id", "state", "goal", "attempt", "ts_open", "ts_closed", "body", "usage"}
    assert [a["id"] for a in client.get("/api/atoms", params={"status": "closed", "node_id": "web.adaptation"}).json()] == [filled["first"]]
    assert len(client.get("/api/atoms", params={"task_id": filled["task"]}).json()) == 3
    assert len(client.get("/api/atoms", params={"limit": 1, "offset": 1}).json()) == 1
    for params in ({"status": "verified"}, {"limit": 0}, {"limit": 501}, {"offset": -1}):
        error_of(client.get("/api/atoms", params=params), 422, "validation")


def test_one_atom_by_stored_key_including_the_composite_builder_key(client, filled):
    assert client.get(f"/api/atoms/{filled['first']}").json()["state"] == "closed"
    built = client.get(f"/api/atoms/{RUN}:W-1.a1").json()
    assert (built["schema"], built["state"], built["body"]["id"]) == ("atom/1", "closed", "W-1.a1")
    error_of(client.get("/api/atoms/a-0000000000-99"), 404, "not_found")


def test_the_atom_log_pages_in_seq_order_and_log_is_not_taken_for_an_atom_id(client, filled):
    page = client.get("/api/atoms/log").json()
    assert [r["seq"] for r in page] == [1, 2] and all(AtomLogRow.model_validate(r) for r in page)
    assert (page[0]["atom_id"], page[0]["status"], page[1]["atom_id"]) == (filled["first"], "closed", f"{RUN}:W-1.a1")
    assert set(page[0]) == {"seq", "atom_id", "node_id", "status", "body", "ts"}
    assert [r["seq"] for r in client.get("/api/atoms/log", params={"after": 1}).json()] == [2]
    assert [r["seq"] for r in client.get("/api/atoms/log", params={"limit": 1}).json()] == [1]
    assert [r["atom_id"] for r in client.get("/api/atoms/log", params={"node_id": "web.adaptation"}).json()] == [filled["first"]]
    for params in ({"after": -1}, {"limit": 0}, {"limit": 501}):
        error_of(client.get("/api/atoms/log", params=params), 422, "validation")


# ---- usage ---------------------------------------------------------------------------------------------------------------------------

def test_usage_rows_and_totals_in_the_response_model_with_the_filters(client, world):
    store = UsageStore(world.db)
    t = world.task(1, "web", "running")
    store.record(uin(task_id=t, dept_id="web", fn="adaptation", call_ref="1", usd=0.5, tokens_in=10, tokens_out=2))
    store.record(uin(task_id=t, dept_id="web", fn="priority", call_ref="2", usd=0.25, tokens_in=20, tokens_out=3))
    store.record(uin(provider="stub", call_ref="3", how="stub", usd=None))
    body = client.get("/api/usage").json()
    assert UsageList.model_validate(body) and set(body) == {"rows", "totals"}
    assert len(body["rows"]) == 2 and body["totals"] == {"calls": 2, "usd": 0.75, "tokens_in": 30, "tokens_out": 5}
    assert set(body["rows"][0]) >= {"id", "at", "provider", "model", "purpose", "session_id", "node_id", "task_id", "dept_id", "fn", "step",
                                    "atom_id", "usd", "tokens_in", "tokens_out", "seconds", "ok", "how", "call_ref", "detail"}
    assert len(client.get("/api/usage", params={"include_stub": 1}).json()["rows"]) == 3
    assert client.get("/api/usage", params={"fn": "priority"}).json()["totals"]["calls"] == 1
    assert client.get("/api/usage", params={"task_id": t, "dept_id": "web"}).json()["totals"]["calls"] == 2
    page = client.get("/api/usage", params={"limit": 1}).json()
    assert len(page["rows"]) == 1 and page["totals"]["calls"] == 2
    assert [r["id"] for r in client.get("/api/usage", params={"after": 1}).json()["rows"]] == [2]


def test_usage_since_takes_seconds_or_an_iso_time_and_refuses_the_rest(client, world):
    UsageStore(world.db).record(uin(call_ref="1"))
    assert client.get("/api/usage", params={"since": "2026-11-04T00:00:00Z"}).json()["totals"]["calls"] == 1
    assert client.get("/api/usage", params={"since": "4102444800"}).json()["totals"]["calls"] == 0
    error = error_of(client.get("/api/usage", params={"since": "yesterday"}), 422, "validation")
    assert error["details"]["violations"][0]["path"] == "query.since"
    for params in ({"limit": 0}, {"limit": 501}, {"after": -1}, {"include_stub": "maybe"}):
        error_of(client.get("/api/usage", params=params), 422, "validation")


def test_usage_summary_groups_and_refuses_an_unknown_grouping(client, world):
    store = UsageStore(world.db)
    store.record(uin(dept_id="web", call_ref="1", tokens_in=10))
    store.record(uin(dept_id="web", call_ref="2", tokens_in=20))
    store.record(uin(dept_id=None, call_ref="3", tokens_in=5, provider="codex", usd=None))
    body = client.get("/api/usage/summary", params={"by": "dept"}).json()
    assert UsageSummary.model_validate(body) and set(body) == {"groups"}
    assert {g["key"]: g["calls"] for g in body["groups"]} == {"(none)": 1, "web": 2}
    assert set(body["groups"][0]) == {"key", "calls", "usd", "tokens_in", "tokens_out"}
    assert {g["key"] for g in client.get("/api/usage/summary", params={"by": "provider"}).json()["groups"]} == {"claude", "codex"}
    assert {g["key"] for g in client.get("/api/usage/summary", params={"by": "atom"}).json()["groups"]} == {"a-0000000001-01"}
    assert {g["key"] for g in client.get("/api/usage/summary").json()["groups"]} == {"(none)", "web"}                  # `by` defaults to dept
    error_of(client.get("/api/usage/summary", params={"by": "colour"}), 422, "validation")


def test_usage_summary_by_purpose_is_a_grouping_like_the_others_with_the_window_the_session_and_the_stub_switch(client, world):
    """D159: `by=purpose` is the ledger's open word for what a call was for; the rows have the shape of every other grouping."""
    store = UsageStore(world.db)
    sid = world.session_of["web"]
    store.record(uin(purpose="agent_turn", call_ref="1", usd=0.5, tokens_in=10, tokens_out=2))
    store.record(uin(purpose="judge", session_id=sid, call_ref="2", usd=0.25, tokens_in=20, tokens_out=3))
    store.record(uin(purpose="plan", session_id=sid, provider="codex", usd=None, call_ref="3", tokens_in=5, tokens_out=1))
    store.record(uin(purpose="chat_plan", provider="stub", call_ref="4", how="stub", usd=None, tokens_in=1, tokens_out=1))
    body = client.get("/api/usage/summary", params={"by": "purpose"}).json()
    assert UsageSummary.model_validate(body) and set(body) == {"groups"}
    assert [g["key"] for g in body["groups"]] == ["agent_turn", "judge", "plan"]                                         # key order; the stub row's purpose is left out
    assert all(set(g) == {"key", "calls", "usd", "tokens_in", "tokens_out"} for g in body["groups"])
    assert body["groups"][1] == {"key": "judge", "calls": 1, "usd": 0.25, "tokens_in": 20, "tokens_out": 3}
    assert body["groups"][2] == {"key": "plan", "calls": 1, "usd": None, "tokens_in": 5, "tokens_out": 1}               # Codex: tokens and no dollars
    stubbed = client.get("/api/usage/summary", params={"by": "purpose", "include_stub": 1}).json()
    assert [g["key"] for g in stubbed["groups"]] == ["agent_turn", "chat_plan", "judge", "plan"] and UsageSummary.model_validate(stubbed)
    assert [g["key"] for g in client.get("/api/usage/summary", params={"by": "purpose", "session_id": sid}).json()["groups"]] == ["judge", "plan"]
    # the window: epoch seconds or an ISO time, the same words as GET /api/usage; every grouping has it
    assert len(client.get("/api/usage/summary", params={"by": "purpose", "since": "2026-11-04T00:00:00Z"}).json()["groups"]) == 3
    assert client.get("/api/usage/summary", params={"by": "purpose", "since": "4102444800"}).json() == {"groups": []}
    assert client.get("/api/usage/summary", params={"by": "dept", "since": "4102444800"}).json() == {"groups": []}
    error = error_of(client.get("/api/usage/summary", params={"by": "purpose", "since": "yesterday"}), 422, "validation")
    assert error["details"]["violations"][0]["path"] == "query.since" and error["details"]["violations"][0]["code"] == "bad_time"
    error_of(client.get("/api/usage/summary", params={"by": "purpose", "since": "9" * 40}), 422, "validation")          # a number that is no time is refused, not a 500
    error_of(client.get("/api/usage/summary", params={"by": "purpose", "since": "1" * 41}), 422, "validation")          # and so is a longer one


# ---- all routes ------------------------------------------------------------------------------------------------------------------------

def test_every_route_is_a_read_that_needs_no_token(client):
    routes = [r for module in (chat_api, atoms_api, usage_api) for r in module.router.routes]
    assert routes and all(r.methods == {"GET"} for r in routes)
    assert client.get("/api/needs-you").status_code == 200 and client.get("/api/usage/summary").status_code == 200
    assert client.post("/api/atoms", json={}).status_code == 405


@pytest.mark.parametrize("path", ["/api/chats", "/api/chats/cs_org", "/api/chats/cs_org/messages", "/api/needs-you", "/api/atoms",
                                  "/api/atoms/log", "/api/atoms/a-0000000000-01", "/api/usage", "/api/usage/summary"])
def test_a_route_without_its_store_answers_internal_not_a_traceback(world, settings, path):
    error_of(make_client(world, settings, wired=False).get(path), 500, "internal")


def test_a_secret_in_a_message_a_goal_or_a_usage_detail_is_redacted(world, settings):
    secret = "tok-0123456789-secret"
    client = make_client(world, settings, redact=Redactor(None, environ={}, extra=[secret]))
    say(world, world.session_of["web"], f"the key is {secret}")
    assert secret not in client.get(f"/api/chats/{world.session_of['web']}/messages").text
    assert "[redacted]" in client.get(f"/api/chats/{world.session_of['web']}/messages").text
    UsageStore(world.db).record(uin(detail={"note": secret}))
    assert secret not in client.get("/api/usage").text and "[redacted]" in client.get("/api/usage").text
    store = AtomStore(world.db, chats=ChatStore(world.db), graph=world.store)
    t = opened(goal=f"use {secret} to open the form")
    apply(world.db, store, fn_event(t, card=False))
    assert secret not in client.get("/api/atoms").text and secret not in client.get("/api/atoms/log").text
    assert GATE.check("atom", t.atom)
