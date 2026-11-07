"""The first-run welcome (gap package welcome-settings, item 1): `GET /api/ops/welcome`, `POST /api/ops/welcome/seen`.

Real app on the scripted connector (offline, no model call) or, for the readings, an online app whose connector status and doctor report are set
by the test. Nothing here starts a CLI or touches the network.
"""
import json
import sqlite3

from fastapi.testclient import TestClient

from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.ops import api as ops_api
from sutra_app.ops import doctor, welcome
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"
TOKEN = "welcome-token-0123456789abcdef"
HEADERS = {"X-Sutra-Token": TOKEN}
SIGNED_IN = {"installed": True, "signed_in": True, "billing": "subscription", "detail": "", "health": {"state": "ok"}}
SIGNED_OUT = {"installed": True, "signed_in": False, "billing": "unknown", "detail": "not signed in", "health": {"state": "signed_out"}}


def make_app(tmp_path, **changes):
    env_file = tmp_path / "x.env"
    env_file.write_text("")
    changes.setdefault("offline", True)
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=env_file, engine="fake", watch_ms=20, **changes)
    connector = ScriptedConnector()
    return create_app(settings, connector=connector, launcher=FakeLauncher(lambda spec: [])), connector


def report(*checks):
    return doctor.Report(list(checks))


def fake_doctor(monkeypatch, *checks):
    monkeypatch.setattr(ops_api.doctor, "run", lambda settings, *, offline=False, **kw: report(*checks))


def test_a_new_data_folder_has_not_seen_the_card_and_offline_says_the_stub_answers(tmp_path, monkeypatch):
    monkeypatch.delenv("SUTRA_PRO_DESKTOP", raising=False)           # set when the desktop app itself runs the suite
    app, _ = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        body = client.get("/api/ops/welcome").json()
    assert body["seen"] is False
    models = body["facts"]["models"]
    assert [m["name"] for m in models] == ["stub"] and models[0]["state"] == "stub" and "stub" in models[0]["why"].lower()
    data = body["facts"]["data"]
    assert data["dir"] == str(tmp_path / "data") and data["db_bytes"] > 0 and data["free_bytes"] > 0 and data["backup"] == "sutra-pro backup"
    assert body["facts"]["egress"] == {"scrub": True, "api_key_refused": True, "only_your_cli": True, "auto_update": {"on": True, "desktop": False}}
    assert body["facts"]["autonomy"]["asks"] is True and isinstance(body["facts"]["autonomy"]["budget"], int)


def test_a_doctor_failure_becomes_a_fix_line_and_a_ready_model_has_none(tmp_path, monkeypatch):
    app, connector = make_app(tmp_path, offline=False)
    connector.set_status({"claude": SIGNED_OUT, "codex": SIGNED_IN})
    fake_doctor(monkeypatch,
                doctor.Check("claude", "claude", "warn", "2.1.308: not signed in (the other CLI can serve)", "run `claude auth login`"),
                doctor.Check("codex", "codex", "ok", "0.9 signed in", ""))
    with TestClient(app, base_url=BASE) as client:
        models = {m["name"]: m for m in client.get("/api/ops/welcome").json()["facts"]["models"]}
    assert models["claude"]["state"] == "not_ready" and models["claude"]["fix"] == "run `claude auth login`"
    assert "not signed in" in models["claude"]["why"]
    assert models["codex"] == {"name": "codex", "state": "ready", "why": "", "fix": ""}


def test_a_provider_that_is_cooling_down_is_blocked_with_its_reason_and_no_fix(tmp_path, monkeypatch):
    app, connector = make_app(tmp_path, offline=False)
    connector.set_status({"claude": {**SIGNED_IN, "health": {"state": "quota", "reason": "usage limit reached"}}, "codex": SIGNED_IN})
    fake_doctor(monkeypatch)
    with TestClient(app, base_url=BASE) as client:
        models = {m["name"]: m for m in client.get("/api/ops/welcome").json()["facts"]["models"]}
    assert models["claude"] == {"name": "claude", "state": "blocked", "why": "usage limit reached", "fix": ""}


def test_got_it_is_stored_in_the_database_and_survives_a_new_app_over_the_same_file(tmp_path):
    app, _ = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/ops/welcome/seen", headers=HEADERS).json() == {"seen": True}
        assert client.get("/api/ops/welcome").json() == {"seen": True, "facts": None}
        first = app.state.services.db.conn().execute("SELECT value FROM meta WHERE key = ?", (welcome.META_KEY,)).fetchone()[0]
        assert client.post("/api/ops/welcome/seen", headers=HEADERS).status_code == 200          # a double click is harmless: the first time stays
        assert app.state.services.db.conn().execute("SELECT value FROM meta WHERE key = ?", (welcome.META_KEY,)).fetchone()[0] == first
    again, _ = make_app(tmp_path)                                                                  # another process, the same data folder
    with TestClient(again, base_url=BASE) as client:
        assert client.get("/api/ops/welcome").json()["seen"] is True
    row = sqlite3.connect(str(again.state.services.settings.db_path)).execute("SELECT value FROM meta WHERE key = 'welcome_seen_at'").fetchone()
    assert row is not None and row[0] == first


def test_got_it_needs_the_token_and_the_page_origin(tmp_path):
    app, _ = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        none = client.post("/api/ops/welcome/seen")
        wrong = client.post("/api/ops/welcome/seen", headers={"X-Sutra-Token": "not-the-token-not-the-token"})
        foreign = client.post("/api/ops/welcome/seen", headers={**HEADERS, "Origin": "http://evil.example"})
        assert (none.status_code, wrong.status_code, foreign.status_code) == (401, 401, 403)
        assert none.json()["error"]["code"] == "bad_token"
        assert client.get("/api/ops/welcome").json()["seen"] is False                              # none of them stored anything


def test_the_answer_holds_no_token_and_no_key(tmp_path, monkeypatch):
    monkeypatch.setenv("J2_OVERRIDE_KEY", "override-key-AAAA1111BBBB2222")
    app, _ = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        text = client.get("/api/ops/welcome").text
    assert TOKEN not in text and "override-key" not in text
    assert "token" not in json.loads(text)["facts"]["egress"]


def test_a_card_that_stays_hidden_runs_no_doctor_probe(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, offline=False)
    calls = []
    monkeypatch.setattr(ops_api.doctor, "run", lambda settings, *, offline=False, **kw: calls.append(offline) or report())
    with TestClient(app, base_url=BASE) as client:
        client.post("/api/ops/welcome/seen", headers=HEADERS)
        calls.clear()
        client.get("/api/ops/welcome")
    assert calls == []
