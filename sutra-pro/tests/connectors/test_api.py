"""`/api/connectors/*` (CN-9, connectors design 6, S3-web-03, S3-web-15): a FastAPI app over a real `Router` whose CLIs are the fakes."""
from __future__ import annotations

import itertools
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sutra_app.connectors.api import MAX_POLICY_BYTES, PREFIX, TEST_PROMPT, build_api_router, status_for
from sutra_app.connectors.errors import CliMissingError, ConnectorError, EnvelopeExceededError, QuotaError, ServerError
from sutra_app.connectors.factory import build_router
from sutra_app.connectors.models import AskRequest, ConnectorConfig
from sutra_app.connectors.policy import load_default_policy, user_policy_path
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.orchestrator.api.deps import install_error_handlers, require_token

TOKEN = "t" * 24
HEADERS = {"X-Sutra-Token": TOKEN}


class Events:
    def __init__(self):
        self.items = []

    def __call__(self, type_, data):
        self.items.append((type_, data))

    def of(self, type_):
        return [d for t, d in self.items if t == type_]


@pytest.fixture
def make(fake, tmp_path):
    """make(connector, offline) -> a TestClient with .router, .events, .sink, .cfg. Every router is closed at the end."""
    made = []

    def build(connector="auto", offline=False):
        cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
        events, sink = Events(), MemoryUsageSink()
        router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector=connector, offline=offline), config=cfg, events=events,
                              usage_sink=sink)
        app = FastAPI()
        app.state.services = SimpleNamespace(settings=SimpleNamespace(token=TOKEN))
        install_error_handlers(app)
        api = build_api_router(router=router, write_guard=require_token)
        app.include_router(api)
        client = TestClient(app)
        client.api = api
        client.router, client.events, client.sink, client.cfg = router, events, sink, cfg
        made.append(router)
        return client

    yield build
    for router in made:
        router.close()


@pytest.fixture
def client(make):
    return make()


def url(path):
    return f"{PREFIX}{path}"


def error_of(response):
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}
    assert isinstance(body["error"]["code"], str) and isinstance(body["error"]["message"], str) and isinstance(body["error"]["details"], dict)
    return body["error"]


# ---- the guard ------------------------------------------------------------------------------------------------------------------

def test_building_the_router_without_a_write_guard_is_a_type_error(client):
    with pytest.raises(TypeError):
        build_api_router(router=client.router)                       # type: ignore[call-arg]
    with pytest.raises(TypeError, match="callable"):
        build_api_router(router=client.router, write_guard="yes")      # type: ignore[arg-type]


def test_every_write_route_has_the_write_guard_in_its_dependency_tree(client):
    def calls(dependant):
        found = [dependant.call]
        for sub in dependant.dependencies:
            found += calls(sub)
        return found

    routes = [r for r in client.api.routes if isinstance(r, APIRoute) and r.path.startswith(PREFIX)]
    writes = [r for r in routes if r.methods & {"PUT", "POST", "DELETE", "PATCH"}]
    reads = [r for r in routes if not r.methods & {"PUT", "POST", "DELETE", "PATCH"}]
    assert len(writes) == 7 and len(reads) == 6
    for route in writes:
        assert require_token in calls(route.dependant), (route.methods, route.path)
    for route in reads:
        assert require_token not in calls(route.dependant), route.path


WRITES = [("PUT", "/policy"), ("POST", "/claude/test"), ("POST", "/codex/sign-in"), ("DELETE", "/codex/sign-in/abc"),
          ("PUT", "/sessions/s1/provider"), ("POST", "/mediated/refresh"), ("PUT", "/claude/path")]


@pytest.mark.parametrize("method,path", WRITES)
def test_a_write_without_the_token_is_refused_before_anything_runs(client, fake, method, path):
    started = len(fake.calls())
    for headers, code in (({}, "bad_token"), ({"X-Sutra-Token": "wrong" * 5}, "bad_token")):
        response = client.request(method, url(path), headers=headers, content=b"{}")
        assert response.status_code == 401 and error_of(response)["code"] == code
    assert len(fake.calls()) == started
    assert not user_policy_path(client.cfg.data_dir).exists()


def test_a_write_from_another_origin_is_refused(client):
    response = client.put(url("/sessions/s1/provider"), headers={**HEADERS, "Origin": "http://evil.example"}, json={"provider": None})
    assert response.status_code == 403 and error_of(response)["code"] == "bad_origin"


def test_reads_need_no_token(client):
    for path in ("/status", "/models", "/policy", "/tools", "/mediated"):
        assert client.get(url(path)).status_code == 200, path


# ---- status ---------------------------------------------------------------------------------------------------------------------

def test_status_has_the_documented_shape(client):
    body = client.get(url("/status?refresh=0")).json()
    assert set(body) == {"mode", "policy", "providers", "tools", "mediated"}
    assert body["mode"] == "live" and body["mediated"] == "/api/connectors/mediated"
    assert body["policy"] == {"version": 1, "source": "default", "error": None}
    assert [p["name"] for p in body["providers"]] == ["claude", "codex"]
    claude = body["providers"][0]
    assert {"installed", "version", "signed_in", "method", "billing", "plan", "account", "health", "quota", "models", "today"} <= set(claude)
    assert claude["installed"] is True and claude["signed_in"] is True and claude["version"] == "2.1.308"
    assert claude["health"] == {"state": "ok", "until": None, "reason": None}
    assert claude["today"] == {"calls": 0, "tokens": 0, "usd": 0.0}
    assert all(set(m) == {"slug", "label"} for m in claude["models"]) and claude["models"]
    assert body["tools"] == {"sutra": True, "github": True}


def test_status_shows_signed_out_and_the_github_tool_off(make, fake):
    fake.auth(claude="signed_out", gh="signed_out")
    body = make().get(url("/status")).json()
    assert body["providers"][0]["signed_in"] is False and body["providers"][0]["health"]["state"] == "signed_out"
    assert body["tools"]["github"] is False


def test_status_refresh_asks_the_clis_again(client, fake):
    def model_cli_calls():
        return len(fake.calls("claude")) + len(fake.calls("codex"))

    client.get(url("/status"))
    before = model_cli_calls()
    client.get(url("/status"))
    assert model_cli_calls() == before                              # cached
    client.get(url("/status?refresh=1"))
    assert model_cli_calls() > before


def test_status_while_offline_lists_only_the_stub_and_runs_no_cli(make, fake):
    body = make(offline=True).get(url("/status")).json()
    assert body["mode"] == "offline" and [p["name"] for p in body["providers"]] == ["stub"]
    assert body["tools"] == {"sutra": True, "github": False}
    assert fake.calls() == []


def test_status_names_a_policy_file_that_was_not_used(make):
    path = user_policy_path(make().cfg.data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    body = make().get(url("/status")).json()
    assert body["policy"]["source"] == "default" and "not valid JSON" in body["policy"]["error"]


# ---- models, tools ----------------------------------------------------------------------------------------------------------------

def test_models_of_one_provider(client):
    models = client.get(url("/models?provider=codex")).json()["models"]
    assert models and all({"slug", "label", "efforts", "images", "listed"} <= set(m) for m in models)
    assert "provider" not in models[0]


def test_models_without_a_provider_lists_all_with_their_provider(client):
    models = client.get(url("/models")).json()["models"]
    assert {m["provider"] for m in models} == {"claude", "codex"}


def test_models_of_an_unknown_provider_is_a_404_envelope(client):
    response = client.get(url("/models?provider=gemini"))
    assert response.status_code == 404 and error_of(response)["code"] == "not_found"


def test_tools_lists_the_profiles_and_read_only_tools(client):
    body = client.get(url("/tools")).json()
    assert body["profiles"] == ["none", "sutra", "sutra+github"]
    assert body["tools"] and all(set(t) == {"name", "description", "read_only"} and t["read_only"] is True for t in body["tools"])


# ---- policy -----------------------------------------------------------------------------------------------------------------------

def test_policy_get_returns_the_policy_in_force(client):
    assert client.get(url("/policy")).json() == load_default_policy().model_dump(mode="json")


def test_policy_put_validates_stores_adopts_and_returns(client):
    policy = load_default_policy().model_dump(mode="json")
    policy["defaults"]["order"] = ["codex", "claude"]
    response = client.put(url("/policy"), headers=HEADERS, json=policy)
    assert response.status_code == 200 and response.json()["defaults"]["order"] == ["codex", "claude"]
    stored = json.loads(user_policy_path(client.cfg.data_dir).read_text())
    assert stored["defaults"]["order"] == ["codex", "claude"]
    assert client.get(url("/policy")).json()["defaults"]["order"] == ["codex", "claude"]
    status = client.get(url("/status")).json()["policy"]
    assert status == {"version": 1, "source": "file", "error": None}
    assert client.router.plan(AskRequest(user="x")).order == ("codex", "claude")          # the running router follows the file


def test_policy_put_adopts_the_codex_sandbox_and_rates(client):
    policy = load_default_policy().model_dump(mode="json")
    policy["providers"]["codex"]["sandbox"] = "workspace-write"
    policy["rates"] = {"codex": {"gpt-5.6-luna": {"in_per_mtok": 1.0, "cached_in_per_mtok": 0.1, "out_per_mtok": 4.0}}}
    assert client.put(url("/policy"), headers=HEADERS, json=policy).status_code == 200
    codex = client.router.connectors["codex"]
    assert codex.sandbox == "workspace-write" and codex.rates["gpt-5.6-luna"].out_per_mtok == 4.0


def test_policy_put_invalid_is_422_policy_invalid_and_writes_nothing(client):
    policy = load_default_policy().model_dump(mode="json")
    policy["defaults"]["order"] = ["claude", "gemini"]
    response = client.put(url("/policy"), headers=HEADERS, json=policy)
    error = error_of(response)
    assert response.status_code == 422 and error["code"] == "policy_invalid"
    assert error["details"]["errors"] and any("gemini" in line or "order" in line for line in error["details"]["errors"])
    assert error["details"]["kind"] == "unavailable"
    assert not user_policy_path(client.cfg.data_dir).exists()
    assert client.get(url("/status")).json()["policy"]["source"] == "default"


def test_policy_put_with_the_removed_api_key_switch_says_why(client):
    policy = load_default_policy().model_dump(mode="json")
    policy["allow_api_key_billing"] = True
    response = client.put(url("/policy"), headers=HEADERS, json=policy)
    assert response.status_code == 422 and "allow_api_key_billing" in error_of(response)["message"]


def test_policy_put_that_is_not_json_is_422_policy_invalid(client):
    response = client.put(url("/policy"), headers=HEADERS, content=b"{nope")
    assert response.status_code == 422 and error_of(response)["code"] == "policy_invalid"
    assert not user_policy_path(client.cfg.data_dir).exists()


def test_policy_put_larger_than_the_cap_is_refused(client):
    response = client.put(url("/policy"), headers=HEADERS, content=b" " * (MAX_POLICY_BYTES + 1))
    assert response.status_code == 422 and error_of(response)["code"] == "policy_invalid" and "larger than" in error_of(response)["message"]


# ---- the test button ----------------------------------------------------------------------------------------------------------------

def test_test_endpoint_makes_one_tiny_call_and_reports_it(make, fake):
    fake.reply(text="ok")
    client = make()
    response = client.post(url("/claude/test"), headers=HEADERS)
    body = response.json()
    assert response.status_code == 200 and body["ok"] is True and body["provider"] == "claude" and body["reply"] == "ok"
    assert body["seconds"] >= 0 and body["tokens_in"] >= 0 and body["tokens_out"] >= 0 and "usd" in body and body["model"]
    calls = fake.model_calls()
    assert [c["cli"] for c in calls] == ["claude"]
    assert TEST_PROMPT in calls[0]["stdin"]
    row = client.sink.rows[0]
    assert len(client.sink.rows) == 1 and row.purpose == "connector_test" and row.provider == "claude" and row.ok is True


def test_test_endpoint_can_test_codex(client, fake):
    response = client.post(url("/codex/test"), headers=HEADERS)
    assert response.status_code == 200 and response.json()["provider"] == "codex"
    assert [c["cli"] for c in fake.model_calls()] == ["codex"]


def test_test_endpoint_counts_cached_input_in_tokens_in(make, fake):
    fake.usage(input_tokens=50, cached_input_tokens=20, output_tokens=3)
    body = make().post(url("/codex/test"), headers=HEADERS).json()
    assert body["tokens_in"] == 50 and body["tokens_out"] == 3


def test_a_failed_test_is_the_envelope_with_the_kind_and_never_falls_back(make, fake):
    fake.sequence("quota")
    client = make()
    response = client.post(url("/claude/test"), headers=HEADERS)
    error = error_of(response)
    assert response.status_code == 429 and error["code"] == "quota" and error["details"]["kind"] == "quota"
    assert error["details"]["provider"] == "claude" and error["message"]
    assert [c["cli"] for c in fake.model_calls()] == ["claude"]       # codex was not asked in its place
    assert client.sink.rows[0].ok is False


def test_test_endpoint_refuses_offline_and_runs_nothing(make, fake):
    offline = make(offline=True)
    response = offline.post(url("/claude/test"), headers=HEADERS)
    assert response.status_code == 409 and error_of(response)["code"] == "offline" and error_of(response)["details"]["kind"] == "unavailable"
    assert fake.calls() == []


def test_test_endpoint_for_a_provider_that_is_not_configured_is_404(make, fake):
    only_claude = make(connector="claude")
    response = only_claude.post(url("/codex/test"), headers=HEADERS)
    assert response.status_code == 404 and error_of(response)["code"] == "not_found"
    assert fake.model_calls() == []


@pytest.mark.parametrize("err,status", [
    (QuotaError(provider="claude"), 429), (ServerError("boom", provider="claude"), 503), (CliMissingError(provider="codex"), 503),
    (EnvelopeExceededError("no more"), 429)])
def test_status_for_follows_the_kind_and_the_code(err, status):
    assert status_for(err) == status


def test_status_for_the_other_kinds():
    class Timeout(ConnectorError):
        code, kind = "timeout", "timeout"

    class Bad(ConnectorError):
        code, kind = "invalid_json", "bad_output"

    class Invalid(ConnectorError):
        code, kind = "invalid_request", "bad_output"

    assert (status_for(Timeout()), status_for(Bad()), status_for(Invalid())) == (504, 502, 422)


# ---- Codex sign-in ------------------------------------------------------------------------------------------------------------------

def tick(client):
    """Moves Codex's clock 3 s on every look, so the 2 s throttle of the sign-in poll never holds a test up."""
    ticks = itertools.count(1000, 3)
    client.router.connectors["codex"]._clock = lambda: float(next(ticks))
    return client


def test_sign_in_start_poll_and_success_publish_the_health(make, fake):
    fake.auth(codex="signed_out")
    ticking = tick(make())
    assert ticking.get(url("/status")).json()["providers"][1]["health"]["state"] == "signed_out"
    started = ticking.post(url("/codex/sign-in"), headers=HEADERS)
    body = started.json()
    assert started.status_code == 200 and set(body) == {"id", "url", "code", "expires_in"} and body["expires_in"] == 900
    assert body["url"].startswith("https://") and body["code"]
    path = url(f"/codex/sign-in/{body['id']}")
    assert ticking.get(path).json()["state"] == "pending"
    fake.approve_device_auth()
    deadline = time.time() + 10
    state = "pending"
    while state == "pending" and time.time() < deadline:
        state = ticking.get(path).json()["state"]
        time.sleep(0.05)
    assert state == "signed_in"
    assert ticking.router.health.state("codex").state == "ok"          # the cached `signed out` was dropped
    assert {"provider": "codex", "state": "ok", "until": None, "reason": None} in ticking.events.of("connector.health")


def test_sign_in_delete_stops_the_child_and_is_204(make, fake):
    fake.auth(codex="signed_out")
    ticking = tick(make())
    sid = ticking.post(url("/codex/sign-in"), headers=HEADERS).json()["id"]
    deleted = ticking.delete(url(f"/codex/sign-in/{sid}"), headers=HEADERS)
    assert deleted.status_code == 204 and deleted.content == b""
    assert ticking.get(url(f"/codex/sign-in/{sid}")).json() == {"state": "failed", "reason": "cancelled"}
    assert ticking.delete(url(f"/codex/sign-in/{sid}"), headers=HEADERS).status_code == 204       # already over: still fine


def test_sign_in_with_an_unknown_id_is_404(client):
    assert error_of(client.get(url("/codex/sign-in/nope")))["code"] == "not_found"
    response = client.delete(url("/codex/sign-in/nope"), headers=HEADERS)
    assert response.status_code == 404 and error_of(response)["code"] == "not_found"


def test_sign_in_is_refused_offline(make):
    offline = make(offline=True)
    assert offline.post(url("/codex/sign-in"), headers=HEADERS).status_code == 409
    assert error_of(offline.get(url("/codex/sign-in/x")))["code"] == "offline"


def test_sign_in_without_the_codex_connector_is_503(make):
    only_claude = make(connector="claude")
    response = only_claude.post(url("/codex/sign-in"), headers=HEADERS)
    assert response.status_code == 503 and error_of(response)["code"] == "provider_unavailable"


# ---- pin ----------------------------------------------------------------------------------------------------------------------------

def test_pin_sets_and_clears_the_chats_provider(client):
    response = client.put(url("/sessions/cs_1/provider"), headers=HEADERS, json={"provider": "codex"})
    assert response.status_code == 204 and response.content == b""
    assert client.router._pins == {"cs_1": "codex"}
    assert client.put(url("/sessions/cs_1/provider"), headers=HEADERS, json={"provider": None}).status_code == 204
    assert client.router._pins == {}


def test_pin_rejects_a_bad_body_with_the_validation_envelope(client):
    for body in ({"provider": "gemini"}, {}, {"provider": "codex", "extra": 1}):
        response = client.put(url("/sessions/cs_1/provider"), headers=HEADERS, json=body)
        assert response.status_code == 422 and error_of(response)["code"] == "validation", body
    assert client.router._pins == {}


def test_pin_rejects_a_bad_session_id_and_an_unconfigured_provider(make):
    only_claude = make(connector="claude")
    bad_id = only_claude.put(url("/sessions/a.b/provider"), headers=HEADERS, json={"provider": "claude"})
    assert bad_id.status_code == 422 and error_of(bad_id)["code"] == "invalid_request"
    missing = only_claude.put(url("/sessions/cs_1/provider"), headers=HEADERS, json={"provider": "codex"})
    assert missing.status_code == 422 and "not a configured provider" in error_of(missing)["message"]


# ---- Claude-held connectors -----------------------------------------------------------------------------------------------------------

def test_mediated_starts_unknown_and_refresh_observes_then_waits_a_minute(client):
    first = client.get(url("/mediated")).json()
    assert first["truth_class"] == "observed" and first["account_known"] is False
    assert [i["status"] for i in first["items"]] == ["unknown"] * 3
    refreshed = client.post(url("/mediated/refresh"), headers=HEADERS)
    assert refreshed.status_code == 200 and {i["name"] for i in refreshed.json()["items"]} == {"Gmail", "Google Drive", "Slack"}
    assert all(i["via"] == "claude" and i["status"] != "unknown" for i in refreshed.json()["items"])
    assert client.get(url("/mediated")).json() == refreshed.json()
    again = client.post(url("/mediated/refresh"), headers=HEADERS)
    error = error_of(again)
    assert again.status_code == 429 and error["code"] == "refresh_too_soon" and error["details"]["kind"] == "rate_limited"
    assert 1 <= error["details"]["retry_after_s"] <= 60 and again.headers["retry-after"] == str(error["details"]["retry_after_s"])


def test_mediated_refresh_is_refused_offline(make, fake):
    offline = make(offline=True)
    assert error_of(offline.post(url("/mediated/refresh"), headers=HEADERS))["code"] == "offline"
    assert fake.calls() == []


# ---- the CLI file the owner chose (GAP-providers) ------------------------------------------------------------------------------------

@pytest.fixture
def finder(monkeypatch, tmp_path):
    """The process as Finder starts it: launchd's PATH, a home with no CLI, no Homebrew folder (this machine may have a real claude)."""
    from sutra_app.connectors import discover
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    monkeypatch.setenv("HOME", str(tmp_path / "finder-home"))
    monkeypatch.setattr(discover, "KNOWN_DIRS", tuple(d for d in discover.KNOWN_DIRS if d not in discover.SYSTEM_DIRS))


def shim(folder, fake, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(f'#!/bin/sh\nexec "{fake.exe(name)}" "$@"\n', encoding="utf-8")
    path.chmod(0o755)
    return path


def test_choosing_the_file_stores_it_and_the_running_router_follows_at_once(make, fake, tmp_path, finder):
    client = make()
    client.router.connectors["claude"].cfg = client.cfg.model_copy(update={"claude_exe": str(tmp_path / "gone" / "claude")})
    client.router.health.forget_installed("claude")
    assert client.get(url("/status")).json()["providers"][0]["installed"] is False
    chosen = shim(tmp_path / "picked", fake, "claude")
    response = client.put(url("/claude/path"), headers=HEADERS, json={"path": str(chosen)})
    assert response.status_code == 200, response.text
    assert response.json() == {"provider": "claude", "path": str(chosen), "installed": True, "signed_in": True, "detail": "signed in"}
    assert json.loads((client.cfg.data_dir / "connectors" / "bins.json").read_text(encoding="utf-8"))["bins"] == {"claude": str(chosen)}
    assert client.router.connectors["claude"].cfg.claude_exe == str(chosen)
    assert client.events.of("connector.health")[-1]["provider"] == "claude"
    forgot = client.put(url("/claude/path"), headers=HEADERS, json={"path": None})
    assert forgot.status_code == 200 and forgot.json()["path"] is None and forgot.json()["installed"] is False
    assert json.loads((client.cfg.data_dir / "connectors" / "bins.json").read_text(encoding="utf-8"))["bins"] == {}
    assert fake.model_calls() == []


def test_a_file_that_cannot_be_the_command_is_refused_with_the_reason_and_nothing_changes(client, tmp_path, finder):
    before = client.router.connectors["claude"].cfg.claude_exe
    refused = client.put(url("/claude/path"), headers=HEADERS, json={"path": str(tmp_path / "nowhere" / "claude")})
    error = error_of(refused)
    assert refused.status_code == 422 and error["code"] == "invalid_request" and "There is no file at" in error["message"]
    wrong = client.put(url("/codex/path"), headers=HEADERS, json={"path": "/bin/sh"})
    assert wrong.status_code == 422 and "Choose the file named codex" in error_of(wrong)["message"]
    assert client.router.connectors["claude"].cfg.claude_exe == before
    assert not (client.cfg.data_dir / "connectors" / "bins.json").exists()


def test_the_path_route_refuses_an_unknown_provider_a_bad_body_and_offline(make):
    client = make()
    assert error_of(client.put(url("/stub/path"), headers=HEADERS, json={"path": None}))["code"] == "not_found"
    for body in ({}, {"path": 3}, {"path": "/x/claude", "extra": 1}, {"path": "/" + "a" * 1100}):
        response = client.put(url("/claude/path"), headers=HEADERS, json=body)
        assert response.status_code == 422 and error_of(response)["code"] == "validation", body
    offline = make(offline=True).put(url("/claude/path"), headers=HEADERS, json={"path": None})
    assert offline.status_code == 409 and error_of(offline)["code"] == "offline"


# ---- the envelope everywhere ----------------------------------------------------------------------------------------------------------

def test_every_refusal_has_the_envelope_shape(make, fake):
    client = make()
    refusals = [
        client.get(url("/models?provider=x")), client.put(url("/policy"), content=b"{}"), client.put(url("/policy"), headers=HEADERS, content=b"[]"),
        client.get(url("/codex/sign-in/zz")), client.put(url("/sessions/s/provider"), headers=HEADERS, json={"provider": 3}),
        client.post(url("/mediated/refresh"), headers=HEADERS), client.post(url("/mediated/refresh"), headers=HEADERS),
        make(offline=True).post(url("/claude/test"), headers=HEADERS),
    ]
    assert sorted({r.status_code for r in refusals}) == [200, 401, 404, 409, 422, 429]
    for response in refusals:
        if response.status_code != 200:
            error_of(response)
