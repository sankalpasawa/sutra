"""The limits routes (gap package routines-limits): the token on every write, the validation of the limit, raising it starts what waited, Continue."""
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.connectors.models import Quota, QuotaWindow
from sutra_app.orchestrator.api import limits as limits_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.limits import Limits
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"
NOW = int(datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc).timestamp())


def make_client(t: TEnv, tmp_path, *, quotas=None, wired: bool = True) -> TestClient:
    app = FastAPI()
    services = Services(settings=t.settings, version="test", db=t.db, redact=Redactor(None, environ={}))
    services.tasks = t.service
    if wired:
        services.limits = Limits(tmp_path / "limits.json", t.db, quotas=lambda: quotas or {}, clock=t.clock)
        t.service.start_gate = services.limits.gate
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(limits_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def client(tenv, tmp_path):
    return make_client(tenv, tmp_path)


@pytest.fixture
def auth(tenv):
    return {TOKEN: tenv.settings.token}


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return body["error"]


def test_the_answer_has_both_readings_and_needs_no_token(client):
    body = client.get("/api/limits").json()
    assert set(body) == {"spend", "guard"}
    assert body["spend"]["level"] == "none" and body["spend"]["limit"] is None and body["spend"]["spent"] == 0
    assert body["guard"] == {"enabled": False, "level": "none", "holding": False, "top": None, "line": "", "windows": []}


@pytest.mark.parametrize("resets_at", [(NOW + 86400) * 1000, 1.0e12])
def test_a_plan_window_with_an_impossible_reset_time_does_not_make_the_answer_a_500(tenv, tmp_path, resets_at):
    odd = Quota(status="warning", windows=[QuotaWindow(key="seven_day", label="Weekly", used=0.9, resets_at=resets_at)], seen_at=NOW - 5)
    client = make_client(tenv, tmp_path, quotas={"claude": odd})
    got = client.get("/api/limits")
    assert got.status_code == 200, got.text
    assert got.json()["guard"]["level"] == "none" and got.json()["guard"]["holding"] is False


def test_every_write_needs_the_token(client, auth):
    for method, path, body in (("put", "/api/limits", {"monthly_usd": 5}), ("post", "/api/limits/continue", None)):
        kwargs = {"json": body} if body is not None else {}
        error_of(getattr(client, method)(path, **kwargs), 401, "bad_token")
        error_of(getattr(client, method)(path, headers={TOKEN: "wrong-token-wrong-token"}, **kwargs), 401, "bad_token")
    assert client.get("/api/limits").json()["spend"]["limit"] is None


def test_put_sets_the_limit_and_the_switch_and_keeps_what_it_is_not_given(client, auth):
    first = client.put("/api/limits", json={"monthly_usd": 10}, headers=auth)
    assert first.status_code == 200 and first.json()["spend"]["limit"] == 10 and first.json()["spend"]["level"] == "ok"
    second = client.put("/api/limits", json={"guard_enabled": True}, headers=auth).json()
    assert second["spend"]["limit"] == 10 and second["guard"]["enabled"] is True
    cleared = client.put("/api/limits", json={"monthly_usd": None}, headers=auth).json()
    assert cleared["spend"]["limit"] is None and cleared["guard"]["enabled"] is True
    assert client.put("/api/limits", json={"monthly_usd": 12.5}, headers=auth).json()["spend"]["limit"] == 12.5
    assert client.put("/api/limits", json={"monthly_usd": 0}, headers=auth).json()["spend"]["limit"] is None        # 0 clears, as the old app's


@pytest.mark.parametrize("body", [{"monthly_usd": -1}, {"monthly_usd": 100001}, {"monthly_usd": "ten"}, {"monthly_usd": True},
                                  {"guard_enabled": "yes"}, {"guard_enabled": None}, {}, {"other": 1}])
def test_a_negative_or_absurd_or_unknown_value_is_a_422_and_changes_nothing(client, auth, body):
    client.put("/api/limits", json={"monthly_usd": 7}, headers=auth)
    error_of(client.put("/api/limits", json=body, headers=auth), 422, "validation")
    assert client.get("/api/limits").json()["spend"]["limit"] == 7


def test_a_number_that_is_not_finite_is_a_422(client, auth):
    for raw in (b'{"monthly_usd": 1e999}', b'{"monthly_usd": NaN}', b'{"monthly_usd": Infinity}'):
        response = client.put("/api/limits", content=raw, headers={**auth, "content-type": "application/json"})
        assert response.status_code == 422, raw
    assert client.get("/api/limits").json()["spend"]["limit"] is None


def test_the_limit_can_be_the_largest_allowed(client, auth):
    assert client.put("/api/limits", json={"monthly_usd": 100000}, headers=auth).json()["spend"]["limit"] == 100000


def test_raising_the_limit_starts_the_task_that_waited_for_it(tenv, tmp_path, auth):
    client = make_client(tenv, tmp_path)
    client.put("/api/limits", json={"monthly_usd": 1}, headers=auth)
    tenv.sql("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (?,?,?,?)", NOW - 60, "claude", "test", 5.0)
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert tenv.status(task.id) == "queued"
    assert client.get("/api/limits").json()["spend"]["level"] == "over"
    answer = client.put("/api/limits", json={"monthly_usd": 50}, headers=auth).json()
    assert answer["spend"]["level"] == "ok"
    assert tenv.status(task.id) == "starting"                                                  # the route followed the change with start_ready


def test_continue_with_nothing_holding_is_not_an_error(client, auth):
    answer = client.post("/api/limits/continue", headers=auth)
    assert answer.status_code == 200 and answer.json()["guard"]["level"] == "none"


def test_continue_lets_a_held_task_start(tenv, tmp_path, auth):
    held = {"claude": Quota(status="warning", seen_at=NOW, windows=[QuotaWindow(key="seven_day", label="Weekly", used=0.9, resets_at=NOW + 86400)])}
    client = make_client(tenv, tmp_path, quotas=held)
    client.put("/api/limits", json={"guard_enabled": True}, headers=auth)
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert tenv.status(task.id) == "queued" and client.get("/api/limits").json()["guard"]["holding"] is True
    answer = client.post("/api/limits/continue", headers=auth).json()
    assert answer["guard"]["holding"] is False and answer["guard"]["top"]["continued"] is True
    assert tenv.status(task.id) == "starting"


def test_an_unwired_limits_service_is_a_500_not_a_crash(tenv, tmp_path):
    error_of(make_client(tenv, tmp_path, wired=False).get("/api/limits"), 500, "internal")
