"""The owner console's routes (GAP-CONSOLE, gaps G11 and G12): `/api/ops/info`, `/doctor`, `/usage` and `/diagnostics`.

Real app on the scripted connector and the fake launcher (offline, no model call): `answered` from the orchestrator's scripted
conversation makes the Web team with one finished run, one Atom log row and one Claude usage row; further usage rows are inserted
with SQL at times the test chooses, and `usage_report` is called with a fixed "now" so the periods are exact.
"""
import io
import json
import logging
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

_LIBRARY_TESTS = str(Path(__file__).resolve().parents[1] / "library")      # the atom builders the scripted conversation uses
if _LIBRARY_TESTS not in sys.path:
    sys.path.append(_LIBRARY_TESTS)

from fastapi.testclient import TestClient
from orchestrator.test_scripted_conversation import ATOM, TOKEN, Scenario, answered, first_script, later_script, new_team

from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.ops import api as ops_api
from sutra_app.ops import doctor
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"
HEADERS = {"X-Sutra-Token": TOKEN}
FAKE_KEY = "fake-key-AAAA1111BBBB2222"
FAKE_TOKEN = "fake-token-CCCC3333DDDD4444"
NOW = int(datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc).timestamp())
DAY = 86400
MIDNIGHT = NOW - NOW % DAY
CLAUDE_DETAIL = json.dumps({"usd_basis": "reported", "billing": "subscription"})
CODEX_DETAIL = json.dumps({"usd_basis": "unknown", "billing": "unknown"})


def make_app(tmp_path, *, env_text="", **changes):
    env_file = tmp_path / "x.env"
    env_file.write_text(env_text)
    changes.setdefault("offline", True)
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=env_file, engine="fake", watch_ms=20, **changes)
    connector = ScriptedConnector()
    made = []

    def script_for(spec):
        made.append(spec.run_id)
        return (first_script if len(made) == 1 else later_script)(spec)

    return create_app(settings, connector=connector, launcher=FakeLauncher(script_for)), connector


@pytest.fixture
def world(tmp_path):
    app, connector = make_app(tmp_path)
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as client:
        yield Scenario(client, app, connector)


@pytest.fixture
def done(world):
    """The Web team with one finished run: one Atom log row, one Claude usage row (usd 0.02, 300 in, 60 out)."""
    answered(world)
    return world


def add_usage(c, at, provider="claude", usd=None, tin=None, tout=None, dept="web", fn=None, atom=None, node=None, detail=None, ref=None):
    c.db.conn().execute(
        "INSERT INTO usage_ledger(at, provider, model, purpose, dept_id, fn, atom_id, node_id, usd, tokens_in, tokens_out, ok, how, call_ref, detail_json)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,1,'native',?,?)", (at, provider, "m", "agent_turn", dept, fn, atom, node, usd, tin, tout, ref, detail))


def at_of_first_row(c, at):
    c.db.conn().execute("UPDATE usage_ledger SET at = ?", (at,))


def unzip(response) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


# ============================================ info ===========================================================================

def test_info_names_the_version_schema_folders_sizes_and_counts(done):
    info = done.client.get("/api/ops/info").json()
    settings = done.services.settings
    assert info["app"] == "Sutra Pro" and info["version"] == done.services.version
    assert info["schema"] == info["schema_expected"] == 2
    assert info["data_dir"] == str(settings.data_dir) and info["db_path"] == str(settings.db_path) and info["log_path"] == str(settings.log_path)
    assert info["db_bytes"] >= settings.db_path.stat().st_size > 0
    assert info["free_bytes"] > 0 and info["uptime_s"] >= 0
    assert info["atom_log"] == {"rows": 1, "last_seq": 1} and info["usage_rows"] == 1
    assert (info["connector"], info["engine"], info["offline"]) == ("auto", "fake", True)


def test_live_tasks_counts_the_runs_that_are_not_over(world):
    assert world.client.get("/api/ops/info").json()["live_tasks"] == 0
    task = new_team(world)
    world.until("the task to run", lambda: world.task_status(task) in ("running", "starting", "waiting_user"))
    assert world.client.get("/api/ops/info").json()["live_tasks"] == 1


def test_the_engine_settings_source_is_defaults_then_the_file_then_the_environment(world, monkeypatch):
    monkeypatch.delenv("J2_BUDGET", raising=False)
    assert world.client.get("/api/ops/info").json()["engine_settings"]["source"] == "defaults"
    (world.services.settings.data_dir / "engine.json").write_text(json.dumps({"budget": 77, "fixes": 1}))
    found = world.client.get("/api/ops/info").json()["engine_settings"]
    assert found["source"] == "data/engine.json" and found["fields"] == ["budget", "fixes"] and found["file_exists"] is True
    assert "77" not in json.dumps(found)                                    # field names only, never their values
    monkeypatch.setenv("J2_BUDGET", "50")
    found = world.client.get("/api/ops/info").json()["engine_settings"]
    assert found["source"] == "data/engine.json + the process environment" and found["env"] == ["J2_BUDGET"]


def test_a_broken_engine_file_is_reported_not_raised(world):
    (world.services.settings.data_dir / "engine.json").write_text("{ not json")
    found = world.client.get("/api/ops/info")
    assert found.status_code == 200 and found.json()["engine_settings"]["problem"]


# ============================================ doctor =========================================================================

def fake_doctor(monkeypatch, calls):
    real = doctor.run

    def run(settings, *, offline=False, **kw):
        calls.append(offline)
        return real(settings, offline=True)
    monkeypatch.setattr(ops_api.doctor, "run", run)


def test_the_doctor_answers_all_fourteen_checks_without_a_model_call(world, monkeypatch):
    calls = []
    fake_doctor(monkeypatch, calls)
    body = world.client.get("/api/ops/doctor").json()
    assert [c["id"] for c in body["checks"]] == list(doctor.CHECK_IDS)
    assert set(body) >= {"ok", "summary", "checks", "checked_at", "cached", "age_s", "ttl_s"}
    assert calls == [True]                                                   # follows the app's own mode: this app is offline


def test_the_doctor_runs_online_when_the_app_is_online(tmp_path, monkeypatch):
    app, connector = make_app(tmp_path, offline=False)
    calls = []
    fake_doctor(monkeypatch, calls)
    with TestClient(app, base_url=BASE) as client:
        client.get("/api/ops/doctor")
    assert calls == [False]


def test_the_port_check_describes_the_running_server(world, monkeypatch):
    fake_doctor(monkeypatch, [])
    port = next(c for c in world.client.get("/api/ops/doctor").json()["checks"] if c["id"] == "port")
    assert port["status"] == "ok" and "this server listens on 127.0.0.1:" in port["detail"]


def test_the_doctor_is_cached_for_thirty_seconds_and_refresh_skips_the_cache(world, monkeypatch):
    calls = []
    fake_doctor(monkeypatch, calls)
    clock = {"t": 1000.0}
    monkeypatch.setattr(ops_api, "_now", lambda: clock["t"])
    first = world.client.get("/api/ops/doctor").json()
    clock["t"] += 29.5
    second = world.client.get("/api/ops/doctor").json()
    assert (first["cached"], second["cached"], len(calls)) == (False, True, 1)
    assert second["age_s"] == 29.5 and second["ttl_s"] == 30 and second["checked_at"] == first["checked_at"]
    assert world.client.get("/api/ops/doctor", params={"refresh": 1}).json()["cached"] is False and len(calls) == 2
    clock["t"] += 30.0
    assert world.client.get("/api/ops/doctor").json()["cached"] is False and len(calls) == 3


# ============================================ usage by period ================================================================

def seed(c):
    """Row 1 (the run's Claude call) today; then Claude 0.50 two days ago, Codex (no dollar figure) ten days ago, Claude 1.00 forty days ago,
    a stub call today, and two more atoms so the top list has to be cut."""
    at_of_first_row(c, NOW - 3600)
    c.db.conn().execute("UPDATE usage_ledger SET fn = 'identity', detail_json = ?", (CLAUDE_DETAIL,))
    add_usage(c, NOW - 2 * DAY, usd=0.5, tin=1000, tout=100, fn="audit", atom="a-aud-01", node="web.audit", detail=CLAUDE_DETAIL, ref="s1")
    add_usage(c, NOW - 10 * DAY, provider="codex", tin=2000, tout=300, fn="adaptation", atom="a-ada-01", detail=CODEX_DETAIL, ref="s2")
    add_usage(c, NOW - 40 * DAY, usd=1.0, tin=10, tout=5, fn="audit", atom="a-old-01", detail=CLAUDE_DETAIL, ref="s3")
    add_usage(c, NOW - 60, provider="stub", usd=0.0, tin=5, tout=5, fn="audit", atom="a-stub-01", ref="s4")
    for n in range(10):
        add_usage(c, NOW - 100 * (n + 1), usd=0.001 * (n + 1), fn="priority", atom=f"a-many-{n:02d}", detail=CLAUDE_DETAIL, ref=f"m{n}")
    return c


def test_period_start_is_utc_midnight_counting_today(world):
    assert ops_api.period_start("today", NOW) == MIDNIGHT
    assert ops_api.period_start("7d", NOW) == MIDNIGHT - 6 * DAY
    assert ops_api.period_start("30d", NOW) == MIDNIGHT - 29 * DAY
    assert ops_api.period_start("all", NOW) is None
    assert ops_api.period_start("today", MIDNIGHT) == MIDNIGHT and ops_api.period_start("today", MIDNIGHT - 1) == MIDNIGHT - DAY


def test_each_period_counts_its_own_rows_and_all_counts_everything(done):
    seed(done)
    calls = {p: ops_api.usage_report(done.services, p, False, NOW)["totals"]["calls"] for p in ("today", "7d", "30d", "all")}
    assert calls == {"today": 11, "7d": 12, "30d": 13, "all": 14}
    report = ops_api.usage_report(done.services, "7d", False, NOW)
    assert report["since"] == "2026-10-29T00:00:00Z" and report["period"] == "7d"
    assert ops_api.usage_report(done.services, "all", False, NOW)["since"] is None


def test_a_row_exactly_at_the_start_of_the_period_counts_and_one_second_earlier_does_not(done):
    at_of_first_row(done, MIDNIGHT)
    assert ops_api.usage_report(done.services, "today", False, NOW)["totals"]["calls"] == 1
    at_of_first_row(done, MIDNIGHT - 1)
    assert ops_api.usage_report(done.services, "today", False, NOW)["totals"]["calls"] == 0


def test_stub_rows_are_left_out_unless_asked_for(done):
    seed(done)
    without = ops_api.usage_report(done.services, "today", False, NOW)
    with_stub = ops_api.usage_report(done.services, "today", True, NOW)
    assert with_stub["totals"]["calls"] == without["totals"]["calls"] + 1 and with_stub["include_stub"] is True
    assert "stub" not in [p["key"] for p in without["providers"]] and "stub" in [p["key"] for p in with_stub["providers"]]
    assert all(a["atom_id"] != "a-stub-01" for a in without["atoms"])


def test_totals_sum_usd_and_tokens_and_a_part_nobody_reported_stays_null(done):
    seed(done)
    totals = ops_api.usage_report(done.services, "30d", False, NOW)["totals"]
    assert totals["usd"] == pytest.approx(0.02 + 0.5 + sum(0.001 * n for n in range(1, 11)))
    assert totals["tokens_in"] == 300 + 1000 + 2000 and totals["tokens_out"] == 60 + 100 + 300
    only_codex = ops_api.usage_report(done.services, "all", False, NOW)["providers"]
    codex = next(p for p in only_codex if p["key"] == "codex")
    assert (codex["usd"], codex["tokens_in"], codex["tokens_out"], codex["calls"]) == (None, 2000, 300, 1)


def test_providers_carry_the_basis_of_the_dollar_figure_and_claude_is_notional(done):
    seed(done)
    providers = {p["key"]: p for p in ops_api.usage_report(done.services, "all", False, NOW)["providers"]}
    assert providers["claude"]["usd_basis"] == ["reported"] and providers["claude"]["billing"] == ["subscription"]
    assert providers["claude"]["notional"] is True and providers["codex"]["notional"] is False
    assert providers["codex"]["usd_basis"] == ["unknown"]


def test_a_provider_with_two_bases_is_one_row_with_both(done):
    seed(done)
    add_usage(done, NOW - 5, provider="codex", usd=0.3, tin=1, tout=1, fn="priority", detail=json.dumps({"usd_basis": "rate_card", "billing": "api_key"}), ref="q")
    codex = next(p for p in ops_api.usage_report(done.services, "all", False, NOW)["providers"] if p["key"] == "codex")
    assert sorted(codex["usd_basis"]) == ["rate_card", "unknown"] and codex["calls"] == 2 and codex["usd"] == 0.3 and codex["tokens_in"] == 2001


def test_days_are_utc_dates_in_order_with_their_sums(done):
    seed(done)
    days = ops_api.usage_report(done.services, "30d", False, NOW)["days"]
    assert [d["key"] for d in days] == ["2026-10-25", "2026-11-02", "2026-11-04"]
    assert days[1] == {"key": "2026-11-02", "calls": 1, "usd": 0.5, "tokens_in": 1000, "tokens_out": 100}
    assert days[2]["calls"] == 11


def test_teams_and_functions_are_grouped_with_the_team_name(done):
    seed(done)
    report = ops_api.usage_report(done.services, "all", False, NOW)
    assert [t["key"] for t in report["teams"]] == ["web"] and report["teams"][0]["name"] == "Web" and report["teams"][0]["calls"] == 14
    by_fn = {f["fn"]: f for f in report["functions"]}
    assert set(by_fn) == {"identity", "audit", "adaptation", "priority"}
    assert by_fn["audit"]["dept"] == "web" and by_fn["audit"]["name"] == "Web" and by_fn["audit"]["calls"] == 2 and by_fn["audit"]["usd"] == 1.5
    assert by_fn["priority"]["calls"] == 10 and by_fn["identity"]["usd"] == 0.02


def test_a_call_without_a_team_is_grouped_under_none(done):
    add_usage(done, NOW - 5, usd=0.1, dept=None, fn=None, ref="n")
    report = ops_api.usage_report(done.services, "all", False, NOW)
    assert "(none)" in [t["key"] for t in report["teams"]]
    assert {"dept": "(none)", "name": "(none)", "fn": "(none)"}.items() <= next(f for f in report["functions"] if f["dept"] == "(none)").items()


def test_the_top_atoms_are_ten_by_cost_with_their_links(done):
    seed(done)
    atoms = ops_api.usage_report(done.services, "all", False, NOW)["atoms"]
    assert len(atoms) == ops_api.TOP_ATOMS == 10
    assert [a["atom_id"] for a in atoms[:3]] == ["a-old-01", "a-aud-01", ATOM]          # 1.00, 0.50, 0.02
    costs = [a["usd"] for a in atoms]
    assert costs == sorted(costs, reverse=True)
    top = atoms[1]
    assert top["team_href"] == "/d/web/?tab=audit" and top["node_href"] == "/?pane=graph&node=web.audit" and top["fn"] == "audit"
    assert atoms[0]["node_href"] is None                                                    # no node on that row


def test_atoms_without_a_dollar_figure_come_last_by_tokens_and_calls_without_an_atom_are_not_listed(done):
    for n, tokens in enumerate((10, 900, 50)):
        add_usage(done, NOW - n, provider="codex", tin=tokens, tout=0, fn="audit", atom=f"a-cx-{n}", ref=f"c{n}")
    add_usage(done, NOW - 7, usd=9.0, fn="audit", atom=None, ref="noatom")
    ids = [a["atom_id"] for a in ops_api.usage_report(done.services, "all", False, NOW)["atoms"]]
    assert ids == [ATOM, "a-cx-1", "a-cx-2", "a-cx-0"]


def test_an_atom_with_a_function_that_has_no_tab_gets_no_team_link(done):
    add_usage(done, NOW - 5, usd=0.4, fn="chat", atom="a-odd-01", ref="odd")
    odd = next(a for a in ops_api.usage_report(done.services, "all", False, NOW)["atoms"] if a["atom_id"] == "a-odd-01")
    assert odd["team_href"] is None


def test_the_usage_route_takes_period_and_include_stub_and_refuses_a_bad_period(done):
    seed(done)
    add_usage(done, int(done.services.clock.now()) - 5, provider="stub", usd=0.0, tin=1, tout=1, ref="route-stub")
    fine = done.client.get("/api/ops/usage", params={"period": "all"})
    assert fine.status_code == 200 and fine.json()["totals"]["calls"] == 14
    assert done.client.get("/api/ops/usage", params={"period": "all", "include_stub": 1}).json()["totals"]["calls"] == 16
    assert done.client.get("/api/ops/usage").json()["period"] == "all"
    bad = done.client.get("/api/ops/usage", params={"period": "year"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation"


def test_an_empty_ledger_gives_zeros_and_empty_lists(world):
    report = world.client.get("/api/ops/usage", params={"period": "today"}).json()
    assert report["totals"] == {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None}
    assert (report["providers"], report["days"], report["teams"], report["functions"], report["atoms"]) == ([], [], [], [], [])


# ============================================ diagnostics ====================================================================

EXPECTED = {"info.json", "doctor.json", "server-log-tail.txt", "settings.json", "schema-versions.json", "departments.json", "README.txt"}


@pytest.fixture
def quiet_doctor(monkeypatch):
    fake_doctor(monkeypatch, [])


def test_the_diagnostics_zip_needs_the_token_header_though_it_is_a_get(world, quiet_doctor):
    assert world.client.get("/api/ops/diagnostics").status_code == 401
    refused = world.client.get("/api/ops/diagnostics", headers={"X-Sutra-Token": "wrong-token-0123456789"})
    assert refused.status_code == 401 and refused.json()["error"]["code"] == "bad_token"
    twice = world.client.get("/api/ops/diagnostics", headers=[("X-Sutra-Token", TOKEN), ("X-Sutra-Token", TOKEN)])
    assert twice.status_code == 401
    foreign = world.client.get("/api/ops/diagnostics", headers={**HEADERS, "Origin": "http://evil.example"})
    assert foreign.status_code == 403 and foreign.json()["error"]["code"] == "bad_origin"
    same = world.client.get("/api/ops/diagnostics", headers={**HEADERS, "Origin": BASE})
    assert same.status_code == 200


def test_the_diagnostics_zip_holds_exactly_the_listed_members(done, quiet_doctor):
    response = done.client.get("/api/ops/diagnostics", headers=HEADERS)
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith('attachment; filename="sutra-pro-diagnostics-') and response.headers["cache-control"] == "no-store"
    members = unzip(response)
    assert set(members) == EXPECTED
    info = json.loads(members["info.json"])
    assert info["version"] == done.services.version and info["atom_log"]["rows"] == 1
    assert json.loads(members["doctor.json"])["checks"][0]["id"] == "python"
    settings = json.loads(members["settings.json"])
    assert settings == done.services.settings.public() and "token" not in settings and "override_key" not in settings
    versions = json.loads(members["schema-versions.json"])
    assert versions["database_user_version"] == 2 and versions["engine_settings"] == "engine-settings/1" and "atom" in versions["library"]


def test_the_zip_lists_department_folders_with_their_sizes_and_no_file_content(done, quiet_doctor):
    folder = done.services.settings.departments_dir / "zz-team"
    (folder / "site").mkdir(parents=True)
    (folder / "site" / "index.html").write_text("SITE-FILE-MARKER" + "x" * 1200)
    (folder / "chat.jsonl").write_text("CHAT-MARKER the owner said a private thing\n")
    members = unzip(done.client.get("/api/ops/diagnostics", headers=HEADERS))
    rows = {d["id"]: d for d in json.loads(members["departments.json"])}
    assert rows["zz-team"]["files"] == 2 and rows["zz-team"]["bytes"] == 1216 + len("CHAT-MARKER the owner said a private thing\n")
    assert "web" in rows
    everything = "\n".join(members.values())
    assert "SITE-FILE-MARKER" not in everything and "CHAT-MARKER" not in everything and "private thing" not in everything


def test_the_log_tail_is_the_last_two_thousand_lines(done, quiet_doctor):
    path = done.services.settings.log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"line {n}\n" for n in range(2500)))
    text = unzip(done.client.get("/api/ops/diagnostics", headers=HEADERS))["server-log-tail.txt"]
    lines = text.splitlines()
    assert len(lines) == 2000 and lines[0] == "line 500" and lines[-1] == "line 2499"


def test_without_a_log_file_the_member_says_so(done, quiet_doctor):
    done.services.settings.log_path.unlink(missing_ok=True)
    assert unzip(done.client.get("/api/ops/diagnostics", headers=HEADERS))["server-log-tail.txt"] == "(no server.log lines yet)\n"


def test_no_planted_key_or_token_survives_anywhere_in_the_zip(tmp_path, monkeypatch, quiet_doctor):
    monkeypatch.setenv("SOME_SERVICE_TOKEN", FAKE_TOKEN)
    app, connector = make_app(tmp_path, env_text=f"FAKE_SERVICE_PASSKEY={FAKE_KEY}\n")
    with TestClient(app, base_url=BASE) as client:
        settings = app.state.services.settings
        settings.log_path.parent.mkdir(parents=True, exist_ok=True)
        settings.log_path.write_text(
            f"1 INFO x - key in the env file: {FAKE_KEY}\n"
            f"2 INFO x - token in the environment: {FAKE_TOKEN}\n"
            f"3 INFO x - the launch token {TOKEN}\n"
            "4 INFO x - GET header X-Sutra-Token: leaked-by-header-0001\n"
            "5 INFO x - sent api_key=planted-api-key-0002 and Authorization: Bearer planted-bearer-0003\n"
            "6 INFO x - model key sk-ant-api03-PLANTED0004PLANTED0005 was used\n"
            "7 INFO x - tokens_in=300 tokens_out=60 is just a count\n")
        (settings.data_dir / "engine.json").write_text(json.dumps({"test_email": "owner@example.com"}))
        response = client.get("/api/ops/diagnostics", headers=HEADERS)
    members = unzip(response)
    blob = response.content + "\n".join(members.values()).encode()
    for secret in (FAKE_KEY, FAKE_TOKEN, TOKEN, "leaked-by-header-0001", "planted-api-key-0002", "planted-bearer-0003", "PLANTED0004"):
        assert secret not in blob.decode("utf-8", "replace"), secret
    tail = members["server-log-tail.txt"]
    assert "[redacted]" in tail and "tokens_in=300 tokens_out=60 is just a count" in tail
    assert "owner@example.com" not in "\n".join(members.values())                         # engine.json values are not part of the bundle


def test_scrub_text_uses_the_redactor_first_and_then_the_patterns():
    assert ops_api.scrub_text("a hidden value", lambda t: t.replace("hidden", "[redacted]")) == "a [redacted] value"
    assert ops_api.scrub_text("Bearer abcdefgh12345678") == "Bearer [redacted]"
    assert ops_api.scrub_text("password: hunter2hunter2") == "password: [redacted]"
    assert ops_api.scrub_text('{"api_key": "abc123abc123"}') == '{"api_key": "[redacted]"}'
    assert ops_api.scrub_text("tokens_in=300 token_count=5 a sk-short") == "tokens_in=300 token_count=5 a sk-short"


def test_tail_lines_handles_a_short_file_a_missing_file_and_bad_bytes(tmp_path):
    short = tmp_path / "s.log"
    short.write_text("a\nb\n")
    assert ops_api.tail_lines(short, 5) == ["a", "b"] and ops_api.tail_lines(short, 1) == ["b"]
    assert ops_api.tail_lines(tmp_path / "nope.log") == []
    bad = tmp_path / "b.log"
    bad.write_bytes(b"ok\n\xff\xfe broken\n")
    assert ops_api.tail_lines(bad)[0] == "ok" and "broken" in ops_api.tail_lines(bad)[1]


def test_a_secret_in_a_json_answer_is_redacted_like_every_other_route(tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_SERVICE_TOKEN", FAKE_TOKEN)
    app, connector = make_app(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    with TestClient(app, base_url=BASE) as client:
        (app.state.services.settings.data_dir / "engine.json").write_text("{" + f'"chrome": "/x/{FAKE_TOKEN}"' + "}")
        found = client.get("/api/ops/info")
    assert FAKE_TOKEN not in found.text


def test_the_router_is_exported_and_create_app_mounts_it(world):
    assert world.app.state.ops_api is True
    assert {r.path for r in ops_api.router.routes} == {"/api/ops/info", "/api/ops/doctor", "/api/ops/usage", "/api/ops/diagnostics"}
    assert all(r.methods == {"GET"} for r in ops_api.router.routes)
    assert logging.getLogger("sutra_app.ops.api") is ops_api.log
