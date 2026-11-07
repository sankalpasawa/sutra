"""The insight routes (gap package chart-insight): the impact of a pending change, the chart notes and the find. All are reads: no token, no write."""
import pytest
from factories_org import add_op, merge_op, rename_op
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_chart_store import Env

from sutra_app.library.gate import GATE
from sutra_app.orchestrator.api import insight as insight_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.chart_health import ChartNotesOut
from sutra_app.orchestrator.records import ChatMessage
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.reorg_preview import ChangeImpactOut
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.team_find import TeamFindOut


@pytest.fixture
def built(db, settings, clock, events):
    env = Env(db, settings, clock, events).build()
    env.apply(rename_op("quotes", purpose="Pricing pages we send to buyers"))
    return env


def make_client(env, settings, clock, *, wired=True) -> TestClient:
    app = FastAPI()
    services = Services(settings=settings, version="test", db=env.db, redact=Redactor(None, environ={}), clock=clock)
    if wired:
        services.chart = env.chart
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(insight_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def client(built, settings, clock):
    return make_client(built, settings, clock)


def error_of(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# ---- the impact of a pending change --------------------------------------------------------------------------------------------------

def test_a_pending_merge_answers_what_a_yes_would_do(client, built):
    pending = built.apply(merge_op("quotes", "leads"))
    assert pending.status == "pending_approval"
    response = client.get(f"/api/chart/changes/{pending.id}/impact")
    assert response.status_code == 200
    out = ChangeImpactOut.model_validate(response.json())
    assert out.status == "pending_approval" and out.change_id == pending.id
    assert any("becomes read-only history under Quotes" in line for line in out.lines) and out.notes == []


def test_a_change_that_is_not_waiting_any_more_has_no_impact_to_say(client, built):
    pending = built.apply(merge_op("quotes", "leads"))
    built.chart.decide(pending.id, True)
    out = ChangeImpactOut.model_validate(client.get(f"/api/chart/changes/{pending.id}/impact").json())
    assert (out.status, out.lines, out.notes) == ("applied", [], [])


def test_a_pending_change_the_chart_moved_on_from_says_so(client, built):
    pending = built.apply(merge_op("quotes", "leads"))
    built.apply(rename_op("menu", name="Dishes"))
    out = ChangeImpactOut.model_validate(client.get(f"/api/chart/changes/{pending.id}/impact").json())
    assert out.lines == [] and out.notes == ["The chart changed since you were asked: a yes would be refused"]


def test_an_unknown_change_is_404_and_a_malformed_id_is_422(client):
    error_of(client.get("/api/chart/changes/chg-9999/impact"), 404, "not_found")
    error_of(client.get("/api/chart/changes/not-a-change/impact"), 422, "validation")


def test_the_impact_route_writes_nothing_and_needs_no_token(client, built):
    pending = built.apply(merge_op("quotes", "leads"))
    before = built.one("SELECT count(*) FROM chart_changes"), built.one("SELECT count(*) FROM org_charts")
    assert client.get(f"/api/chart/changes/{pending.id}/impact").status_code == 200
    assert (built.one("SELECT count(*) FROM chart_changes"), built.one("SELECT count(*) FROM org_charts")) == before
    assert client.post(f"/api/chart/changes/{pending.id}/impact").status_code == 405


# ---- the notes -----------------------------------------------------------------------------------------------------------------------

def test_the_notes_are_read_with_the_services_clock(client, built, clock):
    out = ChartNotesOut.model_validate(client.get("/api/chart/notes").json())
    assert any(n.kind == "no_purpose" and n.words == "Sales has no purpose written" for n in out.notes)
    assert not any(n.kind == "quiet" for n in out.notes)
    clock.advance(70 * 86400)
    out = ChartNotesOut.model_validate(client.get("/api/chart/notes").json())
    assert {n.words for n in out.notes if n.kind == "quiet"} >= {"Sales has had nothing for 70 days", "Web has had nothing for 70 days"}


def test_an_unwired_chart_is_a_500_internal_not_a_crash(built, settings, clock):
    error_of(make_client(built, settings, clock, wired=False).get("/api/chart/changes/chg-0001/impact"), 500, "internal")


# ---- the find ------------------------------------------------------------------------------------------------------------------------

def test_the_find_answers_teams_and_then_the_messages_of_the_chat_search(client, built):
    session = built.session_of("quotes")
    with built.db.tx() as tx:
        msg = GATE.check("chat_message", ChatMessage(kind="text", session_id=session, role="user", who="user", text="Please send the pricing sheet", at=tx.now()), ctx=tx.ctx)
        built.chats.post(tx, session, msg)
    body = client.get("/api/find", params={"q": "pricing"}).json()
    assert set(body) == {"teams", "counts", "truncated", "messages"}
    out = TeamFindOut.model_validate({k: body[k] for k in ("teams", "counts", "truncated")})
    assert [(r.node_id, r.matched_on) for r in out.teams] == [("quotes", ["purpose"])]
    assert [(m["session_id"], m["archived"]) for m in body["messages"]] == [(session, False)] and "pricing" in body["messages"][0]["snippet"].lower()


def test_a_query_of_one_character_finds_nothing_in_either_group(client):
    for q in ("", "p", " a "):
        assert client.get("/api/find", params={"q": q}).json() == {"teams": [], "counts": {"department": 0, "division": 0}, "truncated": False, "messages": []}


def test_a_query_that_is_too_long_is_a_422(client):
    error_of(client.get("/api/find", params={"q": "x" * 201}), 422, "validation")


def test_a_merged_away_division_is_not_in_the_find(client, built):
    built.apply(merge_op("quotes", "leads"), approved=True)
    assert [r["node_id"] for r in client.get("/api/find", params={"q": "leads"}).json()["teams"]] == []
    built.apply(add_op("$n", "division", "Leads again", "sales"))
    assert [r["node_id"] for r in client.get("/api/find", params={"q": "leads"}).json()["teams"]] == ["leads-again"]
