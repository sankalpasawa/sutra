"""The doctor (GAP-OPS-1, gaps G08): fourteen checks, each with a status and a fix hint; offline skips the CLI and browser checks."""
import json
import os
import shutil
import socket
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sutra_app.config import Settings
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.ops import doctor
from sutra_app.ops.lock import InstanceLock
from sutra_app.orchestrator.db import Database

FAKES = Path(__file__).resolve().parents[1] / "fakes"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_settings(tmp_path, **changes):
    return Settings.load({}, data_dir=tmp_path / "data", env_file=tmp_path / "x.env", token="t" * 20, **changes)


def check(report, check_id):
    return next(c for c in report.checks if c.id == check_id)


def run(settings, **kw):
    kw.setdefault("offline", True)
    kw.setdefault("environ", {})
    kw.setdefault("ports", [free_port()])
    kw.setdefault("platform", "linux")
    return doctor.run(settings, **kw)


def fake_config(tmp_path, **env):
    extra = {"FAKE_CLI_STATE": str(tmp_path / "fake-state"), "FAKE_PYTHON": sys.executable, "FAKE_CLAUDE_VERSION": "2.1.308",
             "FAKE_CODEX_VERSION": "0.146.0", "FAKE_MAX_SECONDS": "20", **env}
    return ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=str(FAKES / "claude"),
                           codex_exe=str(FAKES / "codex"), gh_exe=str(FAKES / "gh"), python=sys.executable, extra_env=extra)


def migrated_db(settings):
    settings.ensure_dirs()
    db = Database(settings.db_path, lambda events: None)
    db.migrate()
    db.close()


def test_there_are_fourteen_checks_in_a_fixed_order_and_a_clean_offline_machine_passes(tmp_path):
    report = run(make_settings(tmp_path))
    assert [c.id for c in report.checks] == list(doctor.CHECK_IDS) and len(doctor.CHECK_IDS) == 14
    assert report.ok and report.counts()["fail"] == 0
    assert [c.id for c in report.checks if c.status == "skip"] == ["claude", "codex", "gh", "chrome", "browser"]
    assert report.lines()[-1] == "9 ok, 0 warning(s), 0 failed, 5 skipped"


def test_a_problem_line_carries_its_fix_and_the_report_serialises(tmp_path):
    settings = make_settings(tmp_path)
    settings.env_file.write_text("A=1\n")
    settings.env_file.chmod(0o644)
    report = run(settings)
    line = check(report, "env_file").line()
    assert line.startswith("[WARN] .env file:") and "-> fix: chmod 600" in line
    doc = report.to_dict()
    assert doc["ok"] is True and doc["summary"]["warn"] == 1 and len(doc["checks"]) == 14
    assert set(doc["checks"][0]) == {"id", "title", "status", "detail", "fix"}
    json.dumps(doc)


def test_python_older_than_3_11_fails(tmp_path):
    bad = check(run(make_settings(tmp_path), python_version=(3, 10, 9)), "python")
    assert bad.status == "fail" and "3.10.9" in bad.detail and "3.11" in bad.fix
    assert check(run(make_settings(tmp_path), python_version=(3, 11, 0)), "python").status == "ok"


def test_the_data_folder_is_ok_when_missing_but_creatable_or_private_and_warns_when_open(tmp_path):
    settings = make_settings(tmp_path)
    assert "will be created" in check(run(settings), "data_dir").detail
    settings.data_dir.mkdir(mode=0o700)
    assert check(run(settings), "data_dir").status == "ok"
    settings.data_dir.chmod(0o755)
    found = check(run(settings), "data_dir")
    assert found.status == "warn" and "755" in found.detail and found.fix.startswith("chmod 700")
    assert list(settings.data_dir.iterdir()) == []                      # the write probe left nothing behind


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root can write anywhere, and Windows has no POSIX permission bits")
def test_a_data_folder_that_cannot_be_written_or_is_not_a_folder_fails(tmp_path):
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir(mode=0o500)
    try:
        assert check(run(settings), "data_dir").status == "fail"
    finally:
        settings.data_dir.chmod(0o700)
    shutil.rmtree(settings.data_dir)
    settings.data_dir.write_text("a file")
    assert "not a folder" in check(run(settings), "data_dir").detail


def test_less_than_a_gigabyte_free_fails(tmp_path):
    settings = make_settings(tmp_path)
    assert check(run(settings), "disk").status == "ok" and doctor.MIN_FREE_BYTES == 1024 ** 3
    low = check(run(settings, min_free=shutil.disk_usage(tmp_path).free + 1024 ** 3), "disk")
    assert low.status == "fail" and "GB free on the disk" in low.detail and "free some space" in low.fix


def test_the_database_may_be_absent_older_current_but_never_newer_or_broken(tmp_path):
    settings = make_settings(tmp_path)
    assert "none yet" in check(run(settings), "database").detail
    migrated_db(settings)
    current = check(run(settings), "database")
    assert current.status == "ok" and "schema version 2" in current.detail
    conn = sqlite3.connect(settings.db_path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    newer = check(run(settings), "database")
    assert newer.status == "fail" and "99" in newer.detail and "update the app" in newer.fix
    conn = sqlite3.connect(settings.db_path)
    conn.execute("PRAGMA user_version = 0")
    conn.close()
    older = check(run(settings), "database")
    assert older.status == "ok" and "will be upgraded" in older.detail
    settings.db_path.write_bytes(b"this is not a database at all" * 20)
    assert check(run(settings), "database").status == "fail"


def test_the_env_file_may_be_absent_must_be_private_when_there(tmp_path):
    settings = make_settings(tmp_path)
    absent = check(run(settings), "env_file")
    assert absent.status == "ok" and "optional" in absent.detail and "config init" in absent.detail
    settings.env_file.write_text("A=1\n")
    settings.env_file.chmod(0o600)
    assert check(run(settings), "env_file").status == "ok"
    settings.env_file.chmod(0o664)
    assert check(run(settings), "env_file").status == "warn"


def provider(**kw):
    base = dict(installed=True, version=None, billing="subscription", signed_in=True, method="claude.ai", detail="")
    return SimpleNamespace(**{**base, **kw})


def judged(monkeypatch, tmp_path, claude, codex):
    monkeypatch.setattr(doctor, "_provider_statuses", lambda settings, cfg: {"claude": claude, "codex": codex})
    return run(make_settings(tmp_path), offline=False, config=fake_config(tmp_path), which=lambda exe: None, exists=lambda p: False)


def test_both_cli_signed_in_with_the_tested_versions_is_ok(monkeypatch, tmp_path):
    report = judged(monkeypatch, tmp_path, provider(version="2.1.308"), provider(version="0.146.0", method="ChatGPT"))
    assert (check(report, "claude").status, check(report, "codex").status) == ("ok", "ok")
    assert "2.1.308 signed in, claude.ai" in check(report, "claude").detail


def test_a_different_cli_version_is_a_warning_that_names_the_tested_one(monkeypatch, tmp_path):
    report = judged(monkeypatch, tmp_path, provider(version="2.2.0"), provider(version="0.146.0"))
    found = check(report, "claude")
    assert found.status == "warn" and "tested with 2.1.308" in found.detail and "2.1.308" in found.fix


def test_one_broken_cli_is_a_warning_while_the_other_can_serve_and_both_broken_fail(monkeypatch, tmp_path):
    out = judged(monkeypatch, tmp_path, provider(signed_in=False, version="2.1.308"), provider(version="0.146.0"))
    assert check(out, "claude").status == "warn" and "other CLI can serve" in check(out, "claude").detail
    assert "claude auth login" in check(out, "claude").fix and check(out, "codex").status == "ok"
    both = judged(monkeypatch, tmp_path, provider(signed_in=False), provider(installed=False))
    assert (check(both, "claude").status, check(both, "codex").status) == ("fail", "fail")
    assert "not found on PATH" in check(both, "codex").detail and "codex login" in check(both, "codex").fix
    assert not both.ok


def test_an_api_key_login_is_refused_and_an_unknown_answer_is_not_trusted(monkeypatch, tmp_path):
    keyed = judged(monkeypatch, tmp_path, provider(billing="api_key", method="API key", version="2.1.308"), provider(signed_in=None, detail="odd output"))
    assert "API key, which is refused (D34)" in check(keyed, "claude").detail
    assert "could not tell" in check(keyed, "codex").detail and check(keyed, "codex").status == "fail"


def test_a_missing_provider_in_the_status_counts_as_not_installed(monkeypatch, tmp_path):
    report = judged(monkeypatch, tmp_path, None, provider(version="0.146.0"))
    assert check(report, "claude").status == "warn" and "not found" in check(report, "claude").detail


def test_a_probe_that_raises_fails_both_cli_checks_without_crashing_the_report(monkeypatch, tmp_path):
    def boom(settings, cfg):
        raise OSError("no exec")
    monkeypatch.setattr(doctor, "_provider_statuses", boom)
    report = run(make_settings(tmp_path), offline=False, config=fake_config(tmp_path), which=lambda exe: None)
    assert check(report, "claude").status == check(report, "codex").status == "fail" and "OSError" in check(report, "claude").detail


def test_the_real_probe_over_the_fake_clis_reads_version_and_login(tmp_path):
    report = run(make_settings(tmp_path), offline=False, config=fake_config(tmp_path), which=shutil.which, exists=lambda p: False)
    assert check(report, "claude").status == "ok" and "2.1.308" in check(report, "claude").detail
    assert check(report, "codex").status == "ok" and "0.146.0" in check(report, "codex").detail
    assert check(report, "gh").status == "ok" and "signed in" in check(report, "gh").detail


def test_the_real_probe_sees_a_signed_out_claude_an_api_key_codex_and_a_signed_out_gh(tmp_path):
    cfg = fake_config(tmp_path, FAKE_CLAUDE_AUTH="signed_out", FAKE_CODEX_AUTH="api_key", FAKE_GH_AUTH="signed_out")
    report = run(make_settings(tmp_path), offline=False, config=cfg, which=shutil.which, exists=lambda p: False)
    assert check(report, "claude").status == "fail" and "not signed in" in check(report, "claude").detail
    assert check(report, "codex").status == "fail" and "refused" in check(report, "codex").detail
    assert check(report, "gh").status == "warn"


def test_gh_is_optional(tmp_path):
    cfg = fake_config(tmp_path)
    report = run(make_settings(tmp_path), offline=False, config=cfg, which=lambda exe: None, exists=lambda p: False)
    assert check(report, "gh").status == "skip" and "optional" in check(report, "gh").detail


def test_chrome_found_on_a_standard_path_or_missing_with_the_audit_warning(tmp_path):
    standard = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    found = check(run(make_settings(tmp_path), offline=False, config=fake_config(tmp_path), which=lambda e: None, exists=lambda p: p == standard,
                      platform="darwin", plist_path=tmp_path / "none.plist"), "chrome")
    assert found.status == "ok" and found.detail == standard
    gone = check(run(make_settings(tmp_path), offline=False, config=fake_config(tmp_path), which=lambda e: None, exists=lambda p: False), "chrome")
    assert gone.status == "warn" and "Audit will judge from code only" in gone.detail and "config set chrome" in gone.fix


def test_a_chrome_path_in_the_settings_is_used_and_a_wrong_one_is_named(tmp_path):
    settings = make_settings(tmp_path)
    chrome = tmp_path / "my-chrome"
    chrome.write_text("")
    (settings.data_dir).mkdir(parents=True)
    (settings.data_dir / "engine.json").write_text(json.dumps({"chrome": str(chrome)}))
    assert check(run(settings, offline=False, config=fake_config(tmp_path), which=lambda e: None), "chrome").detail == str(chrome)
    (settings.data_dir / "engine.json").write_text(json.dumps({"chrome": "/nowhere/chrome"}))
    wrong = check(run(settings, offline=False, config=fake_config(tmp_path), which=lambda e: None, exists=lambda p: False), "chrome")
    assert wrong.status == "warn" and "/nowhere/chrome" in wrong.detail


def test_the_port_check_finds_a_free_port_and_fails_when_the_range_is_taken(tmp_path):
    taken = []
    for _ in range(2):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        taken.append(sock)
    try:
        busy = [s.getsockname()[1] for s in taken]
        found = check(run(make_settings(tmp_path), ports=[*busy, free_port()]), "port")
        assert found.status == "ok" and str(busy[0]) not in found.detail.split(" is free")[0]
        full = check(run(make_settings(tmp_path), ports=busy), "port")
        assert full.status == "fail" and "every port" in full.detail
        explicit = check(run(make_settings(tmp_path), environ={"SUTRA_PORT": str(busy[0])}), "port")
        assert explicit.status == "warn" and "SUTRA_PORT" in explicit.detail
        assert check(run(make_settings(tmp_path), environ={"SUTRA_PORT": str(free_port())}), "port").status == "ok"
    finally:
        for sock in taken:
            sock.close()


def test_a_second_instance_is_a_warning_and_this_process_holding_the_folder_is_not(tmp_path):
    settings = make_settings(tmp_path)
    assert check(run(settings), "instance").status == "ok"
    held = InstanceLock(settings.data_dir)
    assert held.acquire()
    held.update(8791)
    try:
        assert "this process" in check(run(settings), "instance").detail
        (settings.data_dir / "app.pid").write_text("1 8791\n")           # as if another process (pid 1) held it
        found = check(run(settings), "instance")
        assert found.status == "warn" and "http://127.0.0.1:8791/" in found.detail and "sutra-pro stop" in found.fix
    finally:
        held.release()


def test_the_seed_library_is_checked_and_synced_without_overwriting(tmp_path):
    settings = make_settings(tmp_path)
    assert "first run seeds" in check(run(settings), "library").detail
    assert len(doctor.sync_seed_library(settings.data_dir)) == 26             # no library yet: the whole seed
    library = settings.data_dir / "library"
    assert check(run(settings), "library").status == "ok" and doctor.missing_seed_templates(settings.data_dir) == []
    gone = library / "hld" / "risks"
    shutil.rmtree(gone)
    edited = library / "prd" / "goals" / "still-point-yoga-goals" / "v1" / "meta.json"
    edited.write_text('{"mine": true}')
    index = json.loads((library / "index.json").read_text())
    index["templates"] = [t for t in index["templates"] if t["section_slug"] != "problem"]
    (library / "index.json").write_text(json.dumps(index))
    missing = check(run(settings), "library")
    assert missing.status == "warn" and "2 seed template(s)" in missing.detail and "config sync-library" in missing.fix
    added = doctor.sync_seed_library(settings.data_dir)
    assert sorted(added) == ["hld/risks/still-point-yoga-risks", "prd/problem/still-point-yoga-problem"]
    assert edited.read_text() == '{"mine": true}'                            # nothing that existed was touched
    assert doctor.sync_seed_library(settings.data_dir) == [] and check(run(settings), "library").status == "ok"
    assert len(json.loads((library / "index.json").read_text())["templates"]) == 26


def test_the_default_browser_check(tmp_path):
    import plistlib

    def plist(bundle):
        path = tmp_path / f"{bundle}.plist"
        path.write_bytes(plistlib.dumps({"LSHandlers": [{"LSHandlerURLScheme": "https", "LSHandlerRoleAll": bundle}]}))
        return path
    standard = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    common = dict(offline=False, config=fake_config(tmp_path), which=lambda e: None, platform="darwin")
    chromium = check(run(make_settings(tmp_path), plist_path=plist("com.google.chrome"), exists=lambda p: False, **common), "browser")
    assert chromium.status == "ok" and "Chrome-based" in chromium.detail
    safari_with_chrome = check(run(make_settings(tmp_path), plist_path=plist("com.apple.safari"), exists=lambda p: p == standard, **common), "browser")
    assert safari_with_chrome.status == "ok" and "opens Chrome instead" in safari_with_chrome.detail
    safari = check(run(make_settings(tmp_path), plist_path=plist("com.apple.safari"), exists=lambda p: False, **common), "browser")
    assert safari.status == "warn" and "only Chrome is measured" in safari.detail
    assert check(run(make_settings(tmp_path), **{**common, "platform": "linux"}, exists=lambda p: False), "browser").status == "skip"


def test_a_broken_engine_json_fails_the_settings_check(tmp_path):
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "engine.json").write_text('{"budget": 0}')
    bad = check(run(settings), "settings")
    assert bad.status == "fail" and "engine.json" in bad.detail and "config set" in bad.fix and not run(settings).ok
    (settings.data_dir / "engine.json").write_text("{not json")
    assert check(run(settings), "settings").status == "fail"
    dept = settings.data_dir / "departments" / "web"
    dept.mkdir(parents=True)
    (settings.data_dir / "engine.json").write_text("{}")
    (dept / "engine.json").write_text('{"send_mode": "sometimes"}')
    assert check(run(settings), "settings").status == "fail"


def test_send_mode_live_needs_the_whole_smtp_login(tmp_path):
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "engine.json").write_text('{"send_mode": "live"}')
    bad = check(run(settings), "settings")
    assert bad.status == "fail" and "J2_SMTP_HOST" in bad.detail and "config init" in bad.fix
    smtp = {"J2_SMTP_HOST": "h", "J2_SMTP_PORT": "587", "J2_SMTP_USER": "u", "J2_SMTP_PASSWORD": "p", "J2_SMTP_FROM": "f"}
    assert check(run(settings, environ=smtp), "settings").status == "ok"
    settings.env_file.write_text("".join(f"{k}={v}\n" for k, v in smtp.items()))
    assert check(run(settings), "settings").status == "ok"
    settings.env_file.write_text("".join(f"{k}={v}\n" for k, v in smtp.items() if k != "J2_SMTP_FROM"))
    assert "J2_SMTP_FROM" in check(run(settings), "settings").detail
    (settings.data_dir / "engine.json").write_text("{}")
    dept = settings.data_dir / "departments" / "web"
    dept.mkdir(parents=True)
    (dept / "engine.json").write_text('{"send_mode": "live"}')            # a department file counts too
    assert check(run(settings), "settings").status == "fail"


def test_a_check_that_raises_becomes_a_failed_check(monkeypatch, tmp_path):
    def boom(settings):
        raise ValueError("kaput")
    monkeypatch.setattr(doctor, "_check_database", boom)
    report = run(make_settings(tmp_path))
    found = check(report, "database")
    assert found.status == "fail" and "ValueError: kaput" in found.detail and len(report.checks) == 14
