"""The picks of a run's agents (D131): `<run>/choices.json` is rebuilt from the database at task start, on every change of a pick that reaches a live run,
and at start-up; the routes that change a pick (an agent chat's pill, the run's, the team's) are checked like a chat's pill and rewrite the file."""
from __future__ import annotations

import sys
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.connectors.agent_picks import CHOICES_FILE, AgentPicks
from sutra_app.connectors.chat_models import Choice
from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.connectors.models import Pick
from sutra_app.engine.port import CallTag
from sutra_app.orchestrator.api import chat as chat_api
from sutra_app.orchestrator.api import chat_v2, tasks as tasks_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.chat_v2 import ChatChoices
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = {"X-Sutra-Token": "test-token-0123456789abcdef"}


def choices_of(t: TEnv, task_id: str) -> dict:
    return json.loads((t.run_dir(task_id) / CHOICES_FILE).read_text())


def session_of(t: TEnv, node_id: str) -> str:
    return t.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", node_id)


def pick(t: TEnv, sid: str, provider="claude", model=None, effort=None) -> None:
    with t.db.tx() as tx:
        ChatChoices(t.db).set_pick(tx, sid, provider, model, effort)


class Port:
    """What the routes ask of the chat port: a pill check that knows two models, and a policy default."""

    seen: list

    def __init__(self) -> None:
        self.seen = []
        self.routers = 0

    def check_choice(self, provider, model=None, effort=None):
        self.seen.append((provider, model, effort))
        if provider == "codex":
            raise InvalidRequestError("codex cannot run: not signed in", detail={"why_not": "not signed in"})
        if model not in (None, "sonnet", "haiku"):
            raise InvalidRequestError(f"{model} is not a model claude offers. Choose one of: haiku, sonnet", detail={"models": ["haiku", "sonnet"]})
        if effort not in (None, "low", "high"):
            raise InvalidRequestError(f"sonnet does not accept the effort {effort}. Choose one of: low, high", detail={"efforts": ["low", "high"]})
        return Choice(session_id="", provider=provider, model=model, effort=effort)

    def choose(self, *a, **k):                         # a direct chat: the router session is made here, never for an agent
        self.routers += 1
        return Choice(session_id=a[0], provider=a[1], model=a[2] if len(a) > 2 else None, effort=a[3] if len(a) > 3 else None)

    def default_pick(self, function=""):
        return Pick(provider="claude", model="sonnet", effort="high")

    def providers(self, sid=None):
        return []


@pytest.fixture
def api(tenv):  # noqa: F811
    app = FastAPI()
    services = Services(settings=tenv.settings, version="t", db=tenv.db, redact=Redactor(None, environ={}))
    services.tasks, services.chats, services.chat_port = tenv.service, tenv.chats, Port()
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    for module in (chat_v2, chat_api, tasks_api):
        app.include_router(module.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False), services.chat_port


def code(r, status):
    assert r.status_code == status, r.text
    return r.json()["error"]["code"]


# ---- the file ----------------------------------------------------------------------------------------------------------------------

def test_a_run_with_no_picks_starts_with_an_empty_choices_file(tenv):  # noqa: F811
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    body = choices_of(tenv, task.id)
    assert (body["schema"], body["default"], body["agents"]) == ("agent-choices/1", None, {}) and (sys.platform.startswith("win") or (tenv.run_dir(task.id) / CHOICES_FILE).stat().st_mode & 0o777 == 0o600)


def test_the_file_holds_the_team_pick_as_default_and_each_agents_own_pick(tenv):  # noqa: F811
    pick(tenv, session_of(tenv, "web"), "claude", "sonnet", "high")                        # the team chat's pill
    pick(tenv, session_of(tenv, "web.identity"), "codex", "gpt-5.6-luna", "medium")
    pick(tenv, session_of(tenv, "web.audit"), "claude", None, "max")
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    body = choices_of(tenv, task.id)
    assert body["default"] == {"provider": "claude", "model": "sonnet", "effort": "high", "from": "team"}
    assert body["agents"] == {"audit": {"provider": "claude", "model": None, "effort": "max"},
                              "identity": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "medium"}}
    seen = AgentPicks(tenv.run_dir(task.id) / CHOICES_FILE)                               # the engine's reader gets the same answers
    assert seen.for_tag(CallTag(function="identity")).provider == "codex" and seen.for_tag(CallTag(function="priority")).model == "sonnet"


def test_the_run_pick_replaces_the_team_pick_as_default(tenv):  # noqa: F811
    pick(tenv, session_of(tenv, "web"), "claude", "sonnet", "high")
    task = tenv.new()
    with tenv.db.tx() as tx:
        tenv.store.set_pick(tx, task.id, Pick(provider="claude", model="haiku", effort="low"))
    tenv.run(tenv.service.start_ready())
    assert choices_of(tenv, task.id)["default"] == {"provider": "claude", "model": "haiku", "effort": "low", "from": "run"}


def test_a_builders_pick_is_keyed_by_its_name_and_a_team_role_is_left_out(tenv):  # noqa: F811
    task_id = tenv.started()
    row = tenv.row(task_id)
    with tenv.db.tx() as tx:
        tenv.taskgraph.ensure_step(tx, row, "W-3", label="Menu")
        tenv.taskgraph.ensure_step(tx, row, "team:Analyst", label="Analyst")
    pick(tenv, tenv.one("SELECT chat_session_id FROM graph_nodes WHERE task_id = ? AND step_ref = 'W-3'", task_id), "claude", "haiku", "low")
    pick(tenv, tenv.one("SELECT chat_session_id FROM graph_nodes WHERE task_id = ? AND step_ref = 'team:Analyst'", task_id), "claude", "haiku", "low")
    assert tenv.service.refresh_choices(task_id=task_id) == 1
    assert choices_of(tenv, task_id)["agents"] == {"W-3": {"provider": "claude", "model": "haiku", "effort": "low"}}


def test_a_change_rewrites_the_file_of_a_live_run_only_and_an_identical_body_touches_nothing(tenv):  # noqa: F811
    task_id = tenv.started()
    path = tenv.run_dir(task_id) / CHOICES_FILE
    assert tenv.service.refresh_choices(dept_id="web") == 0                                 # nothing changed: nothing written
    pick(tenv, session_of(tenv, "web"), "claude", "opus", None)
    assert tenv.service.refresh_choices(dept_id="web") == 1 and choices_of(tenv, task_id)["default"]["model"] == "opus"
    before = path.stat().st_mtime_ns
    assert tenv.service.refresh_choices(task_id=task_id) == 0 and path.stat().st_mtime_ns == before
    tenv.projector.mark_ended(task_id, "done", "ok")
    pick(tenv, session_of(tenv, "web"), "claude", "haiku", None)
    assert tenv.service.refresh_choices(task_id=task_id) == 0 and choices_of(tenv, task_id)["default"]["model"] == "opus"      # a finished run keeps its file


def test_start_up_rebuilds_the_file_of_every_live_run_from_the_database(tenv):  # noqa: F811
    task_id = tenv.started()
    pick(tenv, session_of(tenv, "web.priority"), "claude", "haiku", "low")
    (tenv.run_dir(task_id) / CHOICES_FILE).unlink()                                         # lost, or written by a server that was not told
    assert tenv.service.reconcile_choices() == 1
    assert choices_of(tenv, task_id)["agents"] == {"priority": {"provider": "claude", "model": "haiku", "effort": "low"}}
    assert tenv.service.reconcile_choices() == 0


# ---- the routes --------------------------------------------------------------------------------------------------------------------

def test_an_agent_chat_stores_its_pick_without_a_router_session_and_the_live_runs_file_follows(api, tenv):  # noqa: F811
    client, port = api
    task_id = tenv.started()
    sid = session_of(tenv, "web.identity")
    r = client.put(f"/api/chats/{sid}/choice", json={"provider": "claude", "model": "haiku", "effort": "low"}, headers=TOKEN)
    assert r.status_code == 200 and r.json()["source"] == "own"
    assert r.json()["effective"] == {"provider": "claude", "model": "haiku", "effort": "low", "source": "own"}
    assert port.routers == 0 and port.seen == [("claude", "haiku", "low")]                  # checked, not chosen: an engine call is one-shot
    assert ChatChoices(tenv.db).pick(sid) == Pick(provider="claude", model="haiku", effort="low")
    assert choices_of(tenv, task_id)["agents"]["identity"] == {"provider": "claude", "model": "haiku", "effort": "low"}
    assert "chat.choice" in [e.type for e in tenv.env.events.events]
    cleared = client.put(f"/api/chats/{sid}/choice", json={"provider": None}, headers=TOKEN).json()
    assert cleared["provider"] is None and cleared["source"] == "default" and cleared["effective"]["model"] == "sonnet"
    assert choices_of(tenv, task_id)["agents"] == {}


def test_an_agent_chat_refusal_names_the_valid_ones_and_stores_nothing(api, tenv):  # noqa: F811
    client, _ = api
    sid = session_of(tenv, "web.audit")
    bad = client.put(f"/api/chats/{sid}/choice", json={"provider": "claude", "model": "opuss"}, headers=TOKEN)
    assert code(bad, 422) == "validation" and "haiku, sonnet" in bad.json()["error"]["message"]
    assert code(client.put(f"/api/chats/{sid}/choice", json={"provider": "claude", "model": "sonnet", "effort": "max"}, headers=TOKEN), 422) == "validation"
    assert code(client.put(f"/api/chats/{sid}/choice", json={"provider": "codex"}, headers=TOKEN), 422) == "validation"
    assert code(client.put(f"/api/chats/{sid}/choice", json={"provider": "claude"}), 401) == "bad_token"
    assert ChatChoices(tenv.db).pick(sid) == Pick()


def test_the_teams_pill_is_the_default_of_agents_without_a_pick_and_an_archived_agent_chat_cannot_change(api, tenv):  # noqa: F811
    from sutra_app.orchestrator.chat_v2 import ChatArchive
    client, _ = api
    task_id = tenv.started()
    team = session_of(tenv, "web")
    agent = session_of(tenv, "web.priority")
    client.put(f"/api/chats/{team}/choice", json={"provider": "claude", "model": "haiku"}, headers=TOKEN)        # a direct chat: choose() as before
    assert choices_of(tenv, task_id)["default"] == {"provider": "claude", "model": "haiku", "effort": None, "from": "team"}
    got = client.get(f"/api/chats/{agent}/providers").json()
    assert (got["kind"], got["agent"], got["own"]) == ("function", "priority", None)
    assert got["effective"] == {"provider": "claude", "model": "haiku", "effort": None, "source": "team"}
    with tenv.db.tx() as tx:
        ChatArchive(tenv.db, tenv.graph).archive(tx, agent)
    assert code(client.put(f"/api/chats/{agent}/choice", json={"provider": "claude"}, headers=TOKEN), 409) == "busy"


def test_the_run_pick_route_stores_checks_clears_and_refuses_a_finished_run(api, tenv):  # noqa: F811
    client, port = api
    task_id = tenv.started()
    r = client.put(f"/api/tasks/{task_id}/choice", json={"provider": "claude", "model": "haiku", "effort": "low"}, headers=TOKEN)
    assert r.status_code == 200 and r.json() == {"task_id": task_id, "own": {"provider": "claude", "model": "haiku", "effort": "low"}}
    assert choices_of(tenv, task_id)["default"] == {"provider": "claude", "model": "haiku", "effort": "low", "from": "run"}
    said = [e.data for e in tenv.env.events.events if e.type == "chat.choice" and e.data.get("task_id") == task_id]            # one event for the page, the bus's own (D131)
    assert said == [{"session_id": None, "task_id": task_id, "run_id": tenv.row(task_id).run_id, "provider": "claude", "model": "haiku", "effort": "low", "source": "run"}]
    assert code(client.put(f"/api/tasks/{task_id}/choice", json={"provider": "claude", "model": "opuss"}, headers=TOKEN), 422) == "validation"
    assert code(client.put(f"/api/tasks/{task_id}/choice", json={"provider": "claude"}), 401) == "bad_token"
    assert client.put(f"/api/tasks/{task_id}/choice", json={"provider": None}, headers=TOKEN).json()["own"] is None
    assert choices_of(tenv, task_id)["default"] is None
    assert code(client.put("/api/tasks/tsk_000000000999/choice", json={"provider": None}, headers=TOKEN), 404) == "not_found"
    tenv.projector.mark_ended(task_id, "done", "ok")
    assert code(client.put(f"/api/tasks/{task_id}/choice", json={"provider": "claude"}, headers=TOKEN), 409) == "busy"


def test_the_pill_reads_the_chats_model_and_effort_from_the_database_when_session_json_is_gone(api, tenv):  # noqa: F811
    from sutra_app.connectors.chat_models import ProviderPill
    client, port = api
    port.providers = lambda sid=None: [ProviderPill(name="claude", ready=True), ProviderPill(name="codex", ready=True)]       # no stored session state: chat_model is None
    sid = session_of(tenv, "web.identity")
    pick(tenv, sid, "claude", "haiku", "low")
    got = client.get(f"/api/chats/{sid}/providers").json()
    by = {p["name"]: p for p in got["providers"]}
    assert (by["claude"]["chosen"], by["claude"]["chat_model"], by["claude"]["chat_effort"]) == (True, "haiku", "low")
    assert (by["codex"]["chosen"], by["codex"]["chat_model"]) == (False, None)
    assert got["own"] == {"provider": "claude", "model": "haiku", "effort": "low"} and got["chosen"] == "claude" and got["agent"] == "identity"


def test_the_pill_changes_one_select_at_a_time_the_other_is_kept_while_the_provider_is(api, tenv):  # noqa: F811
    client, _ = api
    sid = session_of(tenv, "web.identity")
    put = lambda body: client.put(f"/api/chats/{sid}/choice", json=body, headers=TOKEN)          # noqa: E731
    put({"provider": "claude", "model": "sonnet", "effort": "high"})
    assert put({"provider": "claude", "effort": "low"}).json()["effective"] == {"provider": "claude", "model": "sonnet", "effort": "low", "source": "own"}
    assert put({"provider": "claude", "model": "haiku"}).json()["effective"]["effort"] == "low"           # a model change keeps the effort that suits it
    assert put({"provider": "claude", "effort": "low", "model": "sonnet"}).status_code == 200
    from sutra_app.connectors.models import Pick as P
    assert ChatChoices(tenv.db).pick(sid) == P(provider="claude", model="sonnet", effort="low")
    real = client.app.state.services.chat_port.check_choice

    def strict(provider, model=None, effort=None):                                 # haiku does not accept the effort high
        if (model, effort) == ("haiku", "high"):
            raise InvalidRequestError("haiku does not accept the effort high. Choose one of: low")
        return real(provider, model, effort)

    client.app.state.services.chat_port.check_choice = strict
    put({"provider": "claude", "model": "sonnet", "effort": "high"})
    assert put({"provider": "claude", "model": "haiku"}).json()["effective"] == {"provider": "claude", "model": "haiku", "effort": None, "source": "own"}      # the kept effort did not suit
    assert code(put({"provider": "claude", "model": "haiku", "effort": "high"}), 422) == "validation"                                                         # the owner's own pair is refused
    assert put({"provider": None}).json()["source"] == "default" and ChatChoices(tenv.db).pick(sid) == Pick()
