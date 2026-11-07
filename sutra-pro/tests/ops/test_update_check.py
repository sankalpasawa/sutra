"""The owner-click update check (gap package welcome-settings, item 2): `ops/update_check.py`, `POST /api/ops/update-check`, `sutra-pro update-check`.

The feed is a fake `fetch(url, timeout) -> bytes` everywhere except the three tests that prove the default fetcher survives a bad server; those talk to
a throw-away server on 127.0.0.1 (never the real network). Every test that boots the app counts the requests that left it: none, until the owner asks.
"""
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sutra_app
from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.ops import cli, update_api, update_check
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"
TOKEN = "update-token-0123456789abcdef"
HEADERS = {"X-Sutra-Token": TOKEN}
PAGE = "https://github.com/sankalpasawa/sutra/releases/tag/"


def release(tag, *, draft=False, prerelease=False, url=True):
    item = {"tag_name": tag, "draft": draft, "prerelease": prerelease}
    if url:
        item["html_url"] = PAGE + tag
    return item


def feed(*releases):
    body = json.dumps(list(releases)).encode()
    return lambda url, timeout: body


def ask(current, *releases, how="command"):
    return update_check.check(current, fetch=feed(*releases), how=how)


# ============================================ the filter and the comparison ==================================================

def test_the_newest_sutra_pro_tag_wins_and_numbers_compare_as_numbers_not_text():
    a = ask("0.1.0", release("sutra-pro-v0.9.0"), release("sutra-pro-v0.10.0"), release("sutra-pro-v0.2.1"))
    assert (a.latest, a.newer, a.error) == ("0.10.0", True, None)
    assert a.notes_url == PAGE + "sutra-pro-v0.10.0" and a.url == a.notes_url


def test_a_v_tag_and_the_old_products_tags_are_never_read():
    a = ask("0.1.0", release("v9.9.9"), release("v9.9.9-desktop"), release("sutra-v7.0.0"), release("sutra-pro-9.0.0"), release("sutra-pro-v1.2"),
            release("sutra-pro-v01.2.3"), release("sutra-pro-v0.1.1\n"), release("sutra-pro-v0.1.1"))
    assert a.latest == "0.1.1"


def test_an_equal_version_is_up_to_date_and_an_older_feed_is_too():
    assert ask("0.1.0", release("sutra-pro-v0.1.0")).newer is False
    same = ask("0.1.0", release("sutra-pro-v0.1.0"))
    assert same.latest == "0.1.0" and same.error is None and update_check.sentence(same) == "You have 0.1.0: up to date."
    assert ask("0.3.0", release("sutra-pro-v0.2.0")).newer is False


def test_a_beta_is_offered_only_to_a_beta_and_a_draft_never():
    feed_all = (release("sutra-pro-v0.2.0-beta.1", prerelease=True), release("sutra-pro-v0.1.5"), release("sutra-pro-v0.3.0", draft=True))
    stable = ask("0.1.0", *feed_all)
    assert (stable.latest, stable.newer) == ("0.1.5", True)
    beta = ask("0.1.9-beta.1", *feed_all)
    assert (beta.latest, beta.newer) == ("0.2.0-beta.1", True)
    pep440 = ask("0.1.9b1", *feed_all)                                           # the wheel spells a beta the PEP 440 way
    assert pep440.latest == "0.2.0-beta.1"


def test_a_beta_is_older_than_its_own_stable_release():
    assert ask("0.2.0-beta.2", release("sutra-pro-v0.2.0")).newer is True
    assert ask("0.2.0", release("sutra-pro-v0.2.0-beta.3", prerelease=True)).newer is False
    assert ask("0.2.0-beta.1", release("sutra-pro-v0.2.0-beta.2", prerelease=True)).newer is True


def test_a_version_that_cannot_be_read_never_looks_newer():
    assert ask("dev", release("sutra-pro-v9.0.0")).newer is False
    assert ask("", release("sutra-pro-v9.0.0")).newer is False


def test_a_release_without_its_page_falls_back_to_the_list_and_a_foreign_link_is_not_followed():
    a = ask("0.1.0", release("sutra-pro-v0.2.0", url=False))
    assert a.notes_url == update_check.RELEASES_PAGE
    odd = json.dumps([{"tag_name": "sutra-pro-v0.2.0", "html_url": "https://evil.example/x"}]).encode()
    b = update_check.check("0.1.0", fetch=lambda u, t: odd, how="command")
    assert b.notes_url == update_check.RELEASES_PAGE


def test_the_one_line_is_for_the_owners_kind_of_install(tmp_path):
    assert update_check.install_kind("/Applications/Sutra Pro.app/Contents/MacOS/python", tmp_path, "darwin") == "mac-app"
    assert update_check.install_kind("C:\\Program Files\\Sutra Pro\\SutraPro.exe", tmp_path, "win32") == "windows-app"
    assert update_check.install_kind("/usr/bin/python3", tmp_path, "linux") == "command"
    (tmp_path / ".git").mkdir()
    assert update_check.install_kind("/usr/bin/python3", tmp_path, "linux") == "checkout"
    assert "dmg" in update_check.how_to_update("mac-app") and "exe" in update_check.how_to_update("windows-app")
    assert "uv tool install" in update_check.how_to_update("command") and "git pull" in update_check.how_to_update("checkout")
    assert update_check.check("0.1.0", fetch=feed(release("sutra-pro-v0.2.0")), how="mac-app").how == update_check.how_to_update("mac-app")


# ============================================ never raises ===================================================================

@pytest.mark.parametrize("exc", [urllib.error.URLError("no route"), ConnectionResetError(), TimeoutError(), OSError("x")])
def test_a_network_failure_is_an_answer_with_an_error_not_an_exception(exc):
    def fetch(url, timeout):
        raise exc
    a = update_check.check("0.1.0", fetch=fetch, how="command")
    assert a.error == "Could not reach GitHub. Check your connection and try again." and a.latest is None and a.newer is False


def test_an_http_error_names_its_status():
    def fetch(url, timeout):
        raise urllib.error.HTTPError(url, 403, "rate limited", {}, None)
    assert update_check.check("0.1.0", fetch=fetch, how="command").error == "GitHub answered 403. Try again later."


@pytest.mark.parametrize("body", [b"", b"not json", b'{"message": "API rate limit exceeded"}', b'"x"', b"null", b"\xff\xfe"])
def test_a_body_that_is_not_the_list_is_an_answer_with_an_error(body):
    a = update_check.check("0.1.0", fetch=lambda u, t: body, how="command")
    assert a.error == "The answer from GitHub could not be read." and a.latest is None


def test_an_empty_feed_and_a_feed_with_no_product_tag_say_so():
    assert "No Sutra Pro release" in ask("0.1.0").error
    assert "No Sutra Pro release" in ask("0.1.0", release("v1.0.0")).error


def test_an_unexpected_bug_in_the_fetcher_is_still_an_answer():
    def fetch(url, timeout):
        raise RuntimeError("boom")
    assert update_check.check("0.1.0", fetch=fetch, how="command").error == "The answer from GitHub could not be read."


# ============================================ the default fetcher against a server that misbehaves ===============================

@pytest.fixture
def server(monkeypatch):
    """A throw-away server on 127.0.0.1; `behave` picks what it does. Proxies are off so the request cannot leave the machine."""
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    mode = {"how": "ok", "seen": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            mode["seen"].append((self.path, dict(self.headers)))
            how = mode["how"]
            if how == "500":
                self.send_response(500)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps([release("sutra-pro-v0.2.0")]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body) + (4000 if how == "hangup" else 0)))
            self.end_headers()
            self.wfile.write(body[:20] if how == "hangup" else body)
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    mode["url"] = f"http://127.0.0.1:{httpd.server_address[1]}/releases"
    yield mode
    httpd.shutdown()
    httpd.server_close()


def test_the_default_fetcher_reads_the_feed_and_sends_nothing_but_the_request(server):
    a = update_check.check("0.1.0", url=server["url"], how="command")
    assert (a.latest, a.newer, a.error) == ("0.2.0", True, None)
    path, headers = server["seen"][0]
    assert path == "/releases"
    assert not any(name.lower() in ("cookie", "authorization", "x-sutra-token") for name in headers)
    assert headers["User-Agent"] == update_check.USER_AGENT


def test_a_server_that_hangs_up_in_the_middle_of_the_body_still_gives_an_answer(server):
    server["how"] = "hangup"
    a = update_check.check("0.1.0", url=server["url"], how="command")
    assert a.error is not None and a.latest is None and a.current == "0.1.0"


def test_a_server_error_still_gives_an_answer(server):
    server["how"] = "500"
    assert update_check.check("0.1.0", url=server["url"], how="command").error == "GitHub answered 500. Try again later."


def test_a_closed_port_still_gives_an_answer(server):
    url = server["url"].replace(str(server["url"].rsplit(":", 1)[1].split("/")[0]), "9")           # nothing listens on port 9
    assert update_check.check("0.1.0", url=url, how="command").error == "Could not reach GitHub. Check your connection and try again."


def test_a_body_larger_than_the_limit_is_refused(monkeypatch, server):
    monkeypatch.setattr(update_check, "MAX_BODY", 10)
    assert update_check.check("0.1.0", url=server["url"], how="command").error == "The answer from GitHub could not be read."


# ============================================ the route ======================================================================

def make_app(tmp_path, **changes):
    env_file = tmp_path / "x.env"
    env_file.write_text("")
    changes.setdefault("offline", False)
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=env_file, engine="fake", watch_ms=20, **changes)
    return create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher(lambda spec: []))


@pytest.fixture
def counted(monkeypatch):
    """Every request the app tries to make goes through here: the default fetcher is replaced by one that counts."""
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        return json.dumps([release("sutra-pro-v9.0.0")]).encode()
    monkeypatch.setattr(update_check, "default_fetch", fetch)
    return calls


def test_nothing_leaves_the_machine_until_the_owner_clicks(tmp_path, counted):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        for path in ("/api/ops/info", "/api/ops/welcome", "/api/health", "/api/ops/doctor", "/"):
            client.get(path)
        assert counted == []                                                       # boot and every page and read: zero requests
        body = client.post("/api/ops/update-check", headers=HEADERS).json()
    assert counted == [update_check.RELEASE_API]                                   # the click is exactly one
    assert body["newer"] is True and body["latest"] == "9.0.0" and body["current"] == sutra_app.__version__
    assert body["said"] == f"You have {sutra_app.__version__}; 9.0.0 is out." and body["how"] and body["error"] is None


def test_the_route_needs_the_token_and_a_get_does_not_start_it(tmp_path, counted):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/ops/update-check").status_code == 401
        assert client.post("/api/ops/update-check", headers={**HEADERS, "Origin": "http://evil.example"}).status_code == 403
        assert client.get("/api/ops/update-check").status_code == 405
    assert counted == []


def test_offline_refuses_with_the_stub_mode_sentence_and_makes_no_request(tmp_path, counted):
    app = make_app(tmp_path, offline=True)
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/api/ops/update-check", headers=HEADERS)
    assert response.status_code == 409 and response.json()["error"]["code"] == "offline"
    assert response.json()["error"]["message"] == update_api.OFFLINE_WORDS and "offline" in update_api.OFFLINE_WORDS
    assert counted == []


def test_a_feed_that_fails_is_a_200_with_the_sentence_not_an_error_page(tmp_path):
    app = make_app(tmp_path)

    def fetch(url, timeout):
        raise urllib.error.URLError("down")
    app.state.update_fetch = fetch
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/api/ops/update-check", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["error"] == response.json()["said"] == "Could not reach GitHub. Check your connection and try again."


# ============================================ the command ====================================================================

def test_the_command_is_registered_and_answers_in_json_with_no_request_made_by_importing_it(counted, capsys):
    assert "update-check" in cli.command_names()
    assert counted == []
    code = cli.main(["update-check", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["newer"] is True and out["latest"] == "9.0.0" and counted == [update_check.RELEASE_API]


def test_the_command_says_where_to_download_and_what_to_do(counted, capsys):
    assert cli.main(["update-check"]) == 0
    text = capsys.readouterr().out
    assert "9.0.0 is out" in text and PAGE + "sutra-pro-v9.0.0" in text


def test_the_command_exits_1_when_the_question_could_not_be_answered(monkeypatch, capsys):
    def fetch(url, timeout):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(update_check, "default_fetch", fetch)
    assert cli.main(["update-check"]) == 1
    assert "Could not reach GitHub" in capsys.readouterr().out


def test_the_command_refuses_offline_and_makes_no_request(counted, monkeypatch, capsys):
    monkeypatch.setenv("SUTRA_OFFLINE", "1")
    assert cli.main(["update-check"]) == 1
    assert "offline" in capsys.readouterr().err and counted == []
