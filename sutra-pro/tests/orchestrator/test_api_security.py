"""The security rules of the whole app (ORCH-8, orchestrator 6.1, S3-web-03, S3-web-14): the write token (header only), the Origin and Host
checks, the route walk over every router and plug-in, and redaction in every response type. The client always speaks to
`http://127.0.0.1:8780`, the address the app is designed for."""
import json

import pytest
from fastapi.testclient import TestClient
from orchestrator.test_scripted_conversation import HEADERS, TOKEN, Scenario, make_scenario, new_team
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.orchestrator.api.deps import require_token
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"
SAFE = {"GET", "HEAD", "OPTIONS"}
WRITES = [("PUT", "/api/engine/settings", {}), ("POST", "/api/chats/cs_org/retry", None), ("POST", "/api/schemas/validate", {"family": "x", "payload": {}}),
          ("PUT", "/api/connectors/sessions/cs_x/provider", {"provider": None}), ("POST", "/api/tasks", {"dept_id": "web", "text": "x"})]


@pytest.fixture
def app_client(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        yield app, client


def code_of(response) -> str | None:
    try:
        return response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None


# ============================================ the write token ================================================================

@pytest.mark.parametrize("method, path, body", WRITES)
def test_a_write_without_the_token_is_401_bad_token(app_client, method, path, body):
    _, client = app_client
    response = client.request(method, path, json=body)
    assert response.status_code == 401 and code_of(response) == "bad_token"


@pytest.mark.parametrize("method, path, body", WRITES)
def test_the_same_token_in_a_cookie_or_the_url_does_not_count(app_client, method, path, body):
    _, client = app_client
    client.cookies.set("X-Sutra-Token", TOKEN)
    client.cookies.set("token", TOKEN)
    assert client.request(method, path, json=body).status_code == 401
    assert client.request(method, path, json=body, params={"token": TOKEN, "X-Sutra-Token": TOKEN}).status_code == 401


def test_a_wrong_or_repeated_token_is_refused(app_client):
    _, client = app_client
    assert client.put("/api/engine/settings", json={}, headers={"X-Sutra-Token": TOKEN + "x"}).status_code == 401
    assert client.put("/api/engine/settings", json={}, headers={"X-Sutra-Token": ""}).status_code == 401
    twice = client.build_request("PUT", "/api/engine/settings", json={}, headers=[("x-sutra-token", TOKEN), ("x-sutra-token", TOKEN)])
    assert client.send(twice).status_code == 401


def test_a_write_with_the_header_goes_through(app_client):
    _, client = app_client
    assert client.put("/api/engine/settings", json={}, headers=HEADERS).status_code == 200
    for method, path, body in WRITES:
        assert code_of(client.request(method, path, json=body, headers=HEADERS)) not in ("bad_token", "bad_origin")      # past the guard


def test_reads_need_no_token(app_client):
    _, client = app_client
    for path in ("/api/health", "/api/config", "/api/chart", "/api/graph", "/api/chats", "/api/needs-you", "/api/connectors/status",
                 "/api/schemas", "/api/departments", "/api/tasks", "/api/atoms", "/api/usage"):
        assert client.get(path).status_code == 200, path


# ============================================ Origin and Host ================================================================

def test_origin_must_be_this_app_and_an_absent_origin_is_fine(app_client):
    _, client = app_client
    put = lambda origin: client.put("/api/engine/settings", json={}, headers={**HEADERS, **({"Origin": origin} if origin is not None else {})})
    assert put(None).status_code == 200
    assert put(BASE).status_code == 200
    for foreign in ("http://evil.example", "http://127.0.0.1:9999", "http://localhost:8780", "https://127.0.0.1:8780", "null", ""):
        response = put(foreign)
        assert response.status_code == 403 and code_of(response) == "bad_origin", foreign


def test_the_origin_is_checked_after_the_token(app_client):
    _, client = app_client
    response = client.put("/api/engine/settings", json={}, headers={"Origin": "http://evil.example"})
    assert code_of(response) == "bad_token"


def test_a_foreign_host_is_400_bad_host_on_every_kind_of_request(app_client):
    _, client = app_client
    for host in ("evil.example", "127.0.0.1.evil.example", "localhost:abc", "[::1]:8780", ""):
        for method, path in (("GET", "/api/health"), ("PUT", "/api/engine/settings"), ("GET", "/"), ("GET", "/api/events")):
            response = client.request(method, path, headers={**HEADERS, "Host": host})
            assert response.status_code == 400 and code_of(response) == "bad_host", (host, method, path)


def test_localhost_with_any_port_is_a_good_host(app_client):
    _, client = app_client
    for host in ("localhost", "LOCALHOST:8780", "127.0.0.1", "127.0.0.1:1"):
        assert client.get("/api/health", headers={"Host": host}).status_code == 200, host


def test_no_cors_headers_are_ever_sent(app_client):
    _, client = app_client
    response = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert not [h for h in response.headers if h.lower().startswith("access-control-")]
    assert "access-control-allow-origin" not in client.options("/api/health", headers={"Origin": BASE, "Access-Control-Request-Method": "GET"}).headers


# ============================================ the route walk =================================================================

def walk(routes):
    """Every route of the app, flat. FastAPI 0.162 includes a router lazily (`_IncludedRouter`); its effective routes carry the path,
    the methods and the dependency tree, include-level dependencies and prefix already applied. A Starlette Route or Mount is yielded as is."""
    for route in routes:
        if hasattr(route, "effective_candidates"):
            yield from walk(route.effective_candidates())
        elif getattr(route, "dependant", None) is not None:
            yield route
        elif getattr(route, "starlette_route", None) is not None:
            yield route.starlette_route
        else:
            yield route
            if isinstance(route, Mount):
                yield from walk(route.routes)


def is_api(route) -> bool:
    return getattr(route, "dependant", None) is not None


def dependency_calls(route) -> set:
    found = set()

    def visit(dependant):
        for sub in dependant.dependencies:
            if sub.call is not None:
                found.add(sub.call)
            visit(sub)
    visit(route.dependant)
    return found


def test_every_route_that_writes_has_the_one_guard_in_its_dependency_tree(app_client):
    app, _ = app_client
    assert app.state.services.require_token is require_token
    writers, readers = [], 0
    for route in walk(app.routes):
        if is_api(route):
            if set(route.methods) - SAFE:
                assert require_token in dependency_calls(route), f"{sorted(route.methods)} {route.path} is not guarded"
                writers.append(route.path)
            else:
                readers += 1
    assert readers > 30 and len(writers) >= 20                                                           # the walk really saw the app
    assert {"/api/chats/{sid}/messages", "/api/tasks", "/api/engine/settings", "/api/schemas/validate", "/api/chart/changes"} <= set(writers)
    assert any(path.startswith("/api/connectors") for path in writers)


def test_no_plain_route_or_mount_accepts_anything_but_a_read(app_client):
    app, _ = app_client
    plain = [route for route in walk(app.routes) if not is_api(route)]
    assert plain                                                                                        # the openapi route and the static mount are in there
    for route in plain:
        if isinstance(route, Route):
            assert not (set(route.methods or ()) - SAFE), f"{route.path} accepts {route.methods}"
        elif isinstance(route, Mount):
            assert isinstance(route.app, StaticFiles), f"{route.path} is a mount of {route.app!r}"       # StaticFiles answers GET and HEAD only
        else:
            pytest.fail(f"an unexpected kind of route: {route!r}")


def test_a_write_to_the_static_mount_is_refused(app_client):
    _, client = app_client
    response = client.post("/ui/anything.js", headers=HEADERS)
    assert response.status_code in (404, 405)


def test_a_new_write_route_without_the_guard_would_be_found(app_client):
    """The walk is not a rubber stamp: an unguarded POST added to the app is seen by the same check."""
    app, _ = app_client

    @app.post("/api/unguarded")
    def unguarded():
        return {}
    found = [r for r in walk(app.routes) if is_api(r) and r.path == "/api/unguarded"]
    assert found and require_token not in dependency_calls(found[0])


# ============================================ secrets never leave ============================================================

SECRET = "sk-fake-secret-value-0123456789"
ENV_VALUE = "env-file-value-9876543210"
KEY = "override-key-abcdef-123456"


@pytest.fixture
def secretive(tmp_path, monkeypatch):
    env = tmp_path / "secrets.env"
    env.write_text(f"SOME_LOCAL_SETTING={ENV_VALUE}\n")
    monkeypatch.setenv("FAKE_SERVICE_API_KEY", SECRET)
    settings = Settings.load({"J2_OVERRIDE_KEY": KEY, "FAKE_SERVICE_API_KEY": SECRET}, data_dir=tmp_path / "data", token=TOKEN, env_file=env,
                             engine="fake", watch_ms=20)
    connector = ScriptedConnector()
    app = create_app(settings, connector=connector, launcher=FakeLauncher())
    with TestClient(app, base_url=BASE) as client:
        yield Scenario(client, app, connector)


def plant(c: Scenario) -> str:
    """Put every secret into the stores, past the stores' own redaction, so only the response layer can hide it."""
    text = f"leaked {SECRET} and {ENV_VALUE} and {KEY} and {TOKEN}"
    with c.db.tx() as tx:
        tx.conn.execute("UPDATE chat_messages SET text = ? WHERE id = 1", (text,))
    return text


def test_a_json_body_never_shows_a_secret_a_dotenv_value_the_override_key_or_the_token(secretive):
    c = secretive
    plant(c)
    body = c.client.get("/api/chats/cs_org/messages")
    assert body.status_code == 200 and "[redacted]" in body.text
    for needle in (SECRET, ENV_VALUE, KEY, TOKEN):
        assert needle not in body.text


def test_an_error_envelope_and_the_config_never_show_them_either(secretive):
    c = secretive
    refused = c.client.post("/api/chats/cs_org/messages", json={"text": f"{SECRET} {KEY}"})
    assert refused.status_code == 401
    config = c.client.get("/api/config").text
    for needle in (SECRET, ENV_VALUE, KEY, TOKEN):
        assert needle not in refused.text and needle not in config


def test_the_event_stream_never_carries_a_secret_or_the_token(secretive):
    c = secretive
    c.services.bus.publish_one("chat.message", {"session_id": "cs_org", "message": {"text": f"{SECRET} {KEY} {ENV_VALUE} {TOKEN}"}})
    text = c.client.get("/api/events", params={"after": 0, "once": 1}).text
    assert "chat.message" in text and "[redacted]" in text
    for needle in (SECRET, ENV_VALUE, KEY, TOKEN):
        assert needle not in text


def test_a_plain_text_response_of_the_engine_is_redacted_too(secretive):
    c = secretive
    task = new_team(c)
    page = c.run_dir(task) / "site"
    page.mkdir(exist_ok=True)
    (page / "index.html").write_text(f"<p>{SECRET} {KEY} {ENV_VALUE}</p>")
    run_id = c.one("SELECT run_id FROM tasks WHERE id = ?", task)
    response = c.client.get("/api/code", params={"dept": "web", "run": run_id, "deck": "work:website"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/plain") and "[redacted]" in response.text
    for needle in (SECRET, ENV_VALUE, KEY):
        assert needle not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_page_with_the_boot_block_is_the_one_place_the_token_is_given(secretive):
    """The pages hand the token to the browser (the boot block); nothing else does. The pages are not the API: they carry no secret."""
    c = secretive
    home = c.client.get("/")
    assert home.status_code == 200 and TOKEN in home.text
    for needle in (SECRET, ENV_VALUE, KEY):
        assert needle not in home.text
    for path in ("/api/health", "/api/chart", "/api/graph", "/api/needs-you", "/api/connectors/status", "/openapi.json"):
        assert TOKEN not in c.client.get(path).text, path


def test_the_log_file_never_shows_the_token(secretive):
    from sutra_app.orchestrator.wiring import configure_logging, make_redactor
    import logging
    c = secretive
    handler = configure_logging(c.services.settings, make_redactor(c.services.settings))
    try:
        logging.getLogger("sutra_app.test").warning("the token is %s and the key %s", TOKEN, KEY)
        try:
            raise RuntimeError(f"boom {SECRET}")
        except RuntimeError:
            logging.getLogger("sutra_app.test").exception("failed")
        handler.flush()
        text = c.services.settings.log_path.read_text()
        assert "[redacted]" in text and TOKEN not in text and KEY not in text and SECRET not in text
    finally:
        root = logging.getLogger()
        for h in [h for h in root.handlers if getattr(h, "_sutra_app", False)]:
            root.removeHandler(h)
            h.close()
