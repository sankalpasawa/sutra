"""The chat agent's routes (ORCH-7): posting in a chat, retry, the decision route. A real `TurnRunner` behind a `TestClient` that stays
open (`with`), so the turn runs on the client's own loop while the test polls the database."""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import assignments, change_reply, decide, draft
from orchestrator.test_turn_runner import RunnerEnv, merge_reply

from sutra_app.orchestrator.agent.ports import ConnectorFailure
from sutra_app.orchestrator.api import agent as agent_api
from sutra_app.orchestrator.api import chart as chart_api
from sutra_app.orchestrator.api import chat as chat_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.models import Accepted, ChangeResult, Delivery
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"


def make_app(r: RunnerEnv, *, wired: bool = True) -> FastAPI:
    app = FastAPI()
    services = Services(settings=r.settings, version="test", db=r.db, redact=Redactor(None, environ={}))
    services.chats, services.chart, services.tasks, services.connector = r.chats, r.chart, r.service, r.connector
    if wired:
        services.runner = r.runner
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(agent_api.build_router())          # BEFORE the chart router: its decision route finishes the request
    app.include_router(chart_api.build_router())
    app.include_router(chat_api.build_router())
    return app


@pytest.fixture
def renv(db, settings, clock, events):
    return RunnerEnv(db, settings, clock, events)


@pytest.fixture
def auth(renv):
    return {TOKEN: renv.settings.token}


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and set(body["error"]) == {"code", "message", "details"}
    return body["error"]


def settle(r: RunnerEnv, timeout: float = 10.0) -> None:
    end = time.time() + timeout
    while r.runner.busy and time.time() < end:
        time.sleep(0.01)
    assert not r.runner.busy


def post(client, sid, text, headers, **extra):
    return client.post(f"/api/chats/{sid}/messages", json={"text": text, **extra}, headers=headers)


def test_posting_needs_the_token(renv):
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        error_of(post(client, "cs_org", "hi", {}), 401, "bad_token")
        error_of(post(client, "cs_org", "hi", {TOKEN: "wrong-token-wrong-token"}), 401, "bad_token")
        error_of(client.post("/api/chats/cs_org/retry"), 401, "bad_token")
        error_of(client.post("/api/chart/changes/chg-0002/decision", json={"approve": True}), 401, "bad_token")


def test_an_org_chat_post_is_accepted_at_once_and_the_turn_runs_behind(renv, auth):
    renv.connector.push(decide())
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        response = post(client, "cs_org", "  A page please  ", auth)
        assert response.status_code == 202, response.text
        accepted = Accepted.model_validate(response.json())
        assert accepted.turn == "started"
        settle(renv)
        messages = client.get("/api/chats/cs_org/messages").json()["messages"]
        assert [m["text"] for m in messages if m["who"] == "user"] == ["A page please"]
        assert any(m["kind"] == "card" and m["card"]["type"] == "task" for m in messages)
        assert client.get("/api/chats/cs_org").json()["phase"] == "working"
    assert renv.tasks_of(f"req-{accepted.message_id}")


LEAK = "sk-proj-REPRO1234567890abcdefghij"


def test_a_credential_in_the_org_chat_is_stored_replaced_and_so_is_the_team_s_first_line_and_task(renv, auth):
    renv.connector.push(decide())
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        accepted = Accepted.model_validate(post(client, "cs_org", f"use {LEAK} for the build", auth).json())
        settle(renv)
        shown = client.get("/api/chats/cs_org/messages").text
        assert LEAK not in shown and "use [redacted:openai-key] for the build" in shown
    [task] = renv.tasks_of(f"req-{accepted.message_id}")
    assert task["user_text"] == "use [redacted:openai-key] for the build"
    team_session = renv.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", task["dept_id"])
    assert [m.text for m in renv.messages(team_session) if m.who == "user"] == ["use [redacted:openai-key] for the build"]
    assert LEAK not in "\n".join(renv.db.conn().iterdump()) and all(LEAK not in str(call) for call in renv.connector.calls)


def test_a_credential_in_a_team_chat_post_is_stored_replaced(renv, auth):
    session = renv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'sales'")
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        assert post(client, session, f"Quote Ana, our key is {LEAK}", auth).status_code == 200
    assert LEAK not in "\n".join(renv.db.conn().iterdump())
    assert [m.text for m in renv.messages(session) if m.who == "user"] == ["Quote Ana, our key is [redacted:openai-key]"]


def test_no_connector_is_503_before_anything_is_stored(renv, auth):
    renv.connector.set_status({"claude": {"installed": False}, "codex": {"installed": False}})
    before = len(renv.messages())
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        error = error_of(post(client, "cs_org", "A page please", auth), 503, "cli_missing")
        assert "Nothing was changed" in error["message"]
        renv.connector.set_status({"claude": {"installed": True, "signed_in": False}})
        error_of(post(client, "cs_org", "A page please", auth), 503, "provider_unavailable")
    assert len(renv.messages()) == before


def test_bad_bodies_and_unknown_chats(renv, auth):
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        error_of(client.post("/api/chats/cs_org/messages", json={"text": ""}, headers=auth), 422, "validation")
        error_of(client.post("/api/chats/cs_org/messages", json={"text": "x", "extra": 1}, headers=auth), 422, "validation")
        error_of(client.post("/api/chats/cs_org/messages", json={"text": "x" * 8001}, headers=auth), 422, "validation")
        error_of(post(client, "cs_nothere0000", "hi", auth), 404, "not_found")
        error_of(post(client, "bad id", "hi", auth), 422, "validation")
        error_of(client.post("/api/chats/cs_org/messages", json={"text": "x", "choice": {"message_id": 1, "option": "a"}}, headers=auth), 422, "validation")


def test_function_step_and_archived_chats_are_read_only(renv, auth):
    function_session = renv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web.identity'")
    task = renv.new("web", "Some work")
    step_session = renv.one("SELECT chat_session_id FROM graph_nodes WHERE task_id = ?", task.id)
    renv.sql("UPDATE chat_sessions SET status = 'archived', writable = 0, filed_under = 'web' WHERE node_id = 'leads'")
    archived = renv.one("SELECT id FROM chat_sessions WHERE node_id = 'leads'")
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        for sid in (function_session, step_session, archived):
            error_of(post(client, sid, "hello", auth), 403, "read_only")


def test_a_department_post_goes_to_the_team_and_a_busy_team_is_409(renv, auth):
    session = renv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'sales'")
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        response = post(client, session, "Please write a quote for Ana", auth)
        assert response.status_code == 200, response.text
        delivery = Delivery.model_validate(response.json())
        assert delivery.delivered == "follow_up"
        error_of(post(client, session, "and another", auth), 409, "busy")
    assert renv.connector.calls == []                                     # the chat agent is not involved in a team chat


def test_the_queue_limit_is_429(renv, auth):
    import asyncio
    gate = {}

    async def slow(call):
        await gate["event"].wait()
        return decide("smalltalk", "none", reuse=())
    renv.connector.push(*[slow] * 7)
    app = make_app(renv)
    with TestClient(app, base_url="http://127.0.0.1:8780") as client:
        gate["event"] = client.portal.call(asyncio.Event) if hasattr(client, "portal") and client.portal else None
        assert gate["event"] is not None
        codes = [post(client, "cs_org", f"request {i}", auth).status_code for i in range(1, 8)]
        assert codes == [202] * 6 + [429]
        error_of(post(client, "cs_org", "again", auth), 429, "too_many_pending")
        client.portal.call(gate["event"].set)
        settle(renv)


def test_retry_runs_the_failed_request_again(renv, auth):
    renv.connector.push(ConnectorFailure("unavailable", "down"), decide())
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        error_of(client.post("/api/chats/cs_org/retry", headers=auth), 404, "not_found")
        first = Accepted.model_validate(post(client, "cs_org", "A page please", auth).json())
        settle(renv)
        assert renv.user_state(first.message_id) == "error"
        renv.connector.set_status({})
        error_of(client.post("/api/chats/cs_org/retry", headers=auth), 503, "provider_unavailable")
        assert renv.user_state(first.message_id) == "error"
        renv.connector.set_status({"stub": {"installed": True, "signed_in": True}})
        response = client.post("/api/chats/cs_org/retry", headers=auth)
        assert response.status_code == 202 and Accepted.model_validate(response.json()).message_id == first.message_id
        settle(renv)
        assert renv.user_state(first.message_id) == "ok" and renv.tasks_of(f"req-{first.message_id}")
        error_of(client.post("/api/chats/cs_org/retry", headers=auth), 404, "not_found")


def test_the_decision_route_finishes_the_request_and_a_second_answer_is_409(renv, auth):
    renv.connector.push(decide("new_task", "rearrange", reuse=()), merge_reply("quotes", "leads"), assignments(draft("a1", "sales", title="Price list")))
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        first = Accepted.model_validate(post(client, "cs_org", "Merge leads into quotes and write the price list", auth).json())
        settle(renv)
        [pending] = renv.chart.pending()
        response = client.post(f"/api/chart/changes/{pending.id}/decision", json={"approve": True}, headers=auth)
        assert response.status_code == 200, response.text
        assert ChangeResult.model_validate(response.json()).status == "applied"
        assert [r["title"] for r in renv.tasks_of(f"req-{first.message_id}")] == ["Price list"]
        error = error_of(client.post(f"/api/chart/changes/{pending.id}/decision", json={"approve": True}, headers=auth), 409, "already_decided")
        assert error["details"]["result"]["status"] == "applied"


def test_the_decision_route_validates_its_input(renv, auth):
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        error_of(client.post("/api/chart/changes/chg-0002/decision", json={"approve": "yes"}, headers=auth), 422, "validation")
        error_of(client.post("/api/chart/changes/chg-0002/decision", json={"approve": True, "x": 1}, headers=auth), 422, "validation")
        error_of(client.post("/api/chart/changes/nope/decision", json={"approve": True}, headers=auth), 422, "validation")
        error_of(client.post("/api/chart/changes/chg-0099/decision", json={"approve": True}, headers=auth), 404, "not_found")


def test_an_answer_to_a_card_button_goes_through_the_post_route(renv, auth):
    renv.connector.push(decide("chart_request", "rearrange", reuse=()), merge_reply("quotes", "leads"))
    with TestClient(make_app(renv), base_url="http://127.0.0.1:8780") as client:
        post(client, "cs_org", "Merge leads into quotes", auth)
        settle(renv)
        card = next(m for m in renv.messages() if m.kind == "card")
        response = post(client, "cs_org", "Yes", auth, choice={"message_id": card.id, "option": "yes"})
        assert response.status_code == 202, response.text
        settle(renv)
        error_of(post(client, "cs_org", "Yes", auth, choice={"message_id": card.id, "option": "yes"}), 409, "already_decided")
        error_of(post(client, "cs_org", "Maybe", auth, choice={"message_id": card.id, "option": "maybe"}), 422, "validation")
    assert renv.chart.head().model.node("leads") is None


def test_an_unwired_runner_is_a_500_not_a_crash(renv, auth):
    with TestClient(make_app(renv, wired=False), base_url="http://127.0.0.1:8780", raise_server_exceptions=False) as client:
        error_of(post(client, "cs_org", "hi", auth), 500, "internal")
        error_of(client.post("/api/chats/cs_org/retry", headers=auth), 500, "internal")
