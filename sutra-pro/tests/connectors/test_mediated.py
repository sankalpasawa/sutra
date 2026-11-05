"""Claude-held Gmail, Drive and Slack, shown only (work package CN-8, connectors design 3.9, CD16, plugin ADR-035)."""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.process import ExitInfo
from sutra_app.connectors.tools.mediated import (
    KNOWN, MIN_INTERVAL_S, MediatedConnectors, MediatedItem, MediatedReport, RefreshTooSoon, parse_claude_mcp_list,
)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ScriptRunner:
    """Stands in for ProcessRunner: prints `text`, returns `info`; counts and records its commands."""

    def __init__(self, text="", returncode=0, reason="exit", gate=None):
        self.text, self.returncode, self.reason, self.gate = text, returncode, reason, gate
        self.commands, self.entered = [], threading.Event()

    def run(self, cmd, *, on_line=None, timeout_s=None, idle_timeout_s=None):
        self.commands.append((cmd, timeout_s))
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        for line in self.text.splitlines():
            on_line(line)
        return ExitInfo(returncode=self.returncode, reason=self.reason, stderr_tail="", seconds=0.0, pid=1)


def by_name(report):
    return {i["name"]: i for i in report["items"]}


def make(fake, tmp_path, **kw):
    return MediatedConnectors(ConnectorConfig(**fake.config_kwargs(tmp_path)), **kw)


# ---- the parser ----------------------------------------------------------------------------------------------------------------------

def test_parser_reads_the_hand_written_sample(fixtures):
    proof, rows = parse_claude_mcp_list(fixtures.text("handwritten/claude_mcp_list.txt"))
    assert proof is True
    assert rows == {"gmail": "Connected", "drive": "Needs authentication", "slack": "Connected · tools fetch failed"}


def test_local_servers_and_empty_output_prove_nothing(fixtures):
    for name in ("claude_mcp_list_local.txt", "claude_mcp_list_empty.txt"):
        assert parse_claude_mcp_list(fixtures.text(f"handwritten/{name}")) == (False, {})
    assert parse_claude_mcp_list("") == (False, {})


def test_proof_does_not_depend_on_the_strict_row_format():
    proof, rows = parse_claude_mcp_list("claude.ai Gmail\nclaude.ai Weird thing without colon\n")
    assert proof is True and rows == {"gmail": ""}
    proof, rows = parse_claude_mcp_list("claude.ai Some Other Connector: https://x - ✔ Connected\n")
    assert proof is True and rows == {}


def test_parser_matches_names_loosely_and_keeps_the_first_row():
    _, rows = parse_claude_mcp_list("claude.ai Google Drive: u - ✔ Connected\nclaude.ai Drive copy: u - ! Needs authentication\n"
                                    "claude.ai SLACK: u - Connected\n")
    assert rows == {"drive": "Connected", "slack": "Connected"}


# ---- statuses -------------------------------------------------------------------------------------------------------------------

def test_before_any_refresh_everything_is_unknown_and_nothing_ran(fake, tmp_path):
    m = make(fake, tmp_path)
    snap = m.snapshot()
    assert fake.calls("claude") == []
    assert [i["status"] for i in snap["items"]] == ["unknown"] * 3 and all(i["observed_at"] is None for i in snap["items"])
    assert "Not checked yet" in snap["items"][0]["note"]


def test_payload_shape_and_no_account(fake, tmp_path):
    report = make(fake, tmp_path).refresh()
    assert set(report) == {"truth_class", "account_known", "items"}
    assert report["truth_class"] == "observed" and report["account_known"] is False
    assert [i["name"] for i in report["items"]] == ["Gmail", "Google Drive", "Slack"]
    assert all(set(i) == {"name", "via", "status", "observed_at", "note"} and i["via"] == "claude" for i in report["items"])
    assert "@" not in json.dumps(report) and "account" not in json.dumps(report["items"]).lower()
    MediatedReport.model_validate(report)
    with pytest.raises(ValueError):
        MediatedItem(name="x", status="added", observed_at=None, note="", extra=1)


def test_sample_gives_added_with_the_probe_attributed_to_claude(fake, tmp_path):
    items = by_name(make(fake, tmp_path).refresh())
    assert all(i["status"] == "added" and i["observed_at"] for i in items.values())
    assert items["Google Drive"]["note"] == "Added in Claude. Claude's last check reported: Needs authentication."
    assert items["Slack"]["note"].endswith("Connected · tools fetch failed.")


def test_not_added_needs_proof_that_the_list_arrived(fake, tmp_path):
    runner = ScriptRunner("claude.ai Gmail: https://g - ✔ Connected\nplaywright: npx x - ✔ Connected\n")
    items = by_name(make(fake, tmp_path, runner=runner).refresh())
    assert [items[n]["status"] for n in ("Gmail", "Google Drive", "Slack")] == ["added", "not_added", "not_added"]
    assert "Not added in Claude" in items["Slack"]["note"]


@pytest.mark.parametrize("kind", ["local", "empty"])
def test_no_claude_ai_rows_is_unknown_never_not_added(fake, tmp_path, kind):
    fake.set(FAKE_CLAUDE_MCP=kind)
    report = make(fake, tmp_path).refresh()
    assert [i["status"] for i in report["items"]] == ["unknown"] * 3
    assert "offline, signed out, or none added" in report["items"][0]["note"]


def test_failures_are_unknown_with_a_reason(fake, tmp_path):
    cases = [
        (ScriptRunner("claude.ai Gmail: u - Connected", returncode=3), "exit 3"),
        (ScriptRunner("claude.ai Gmail: u - Connected", returncode=None, reason="total_timeout"), "did not answer in time"),
        (ScriptRunner("", returncode=0), "listed no connectors"),
    ]
    for runner, fragment in cases:
        report = make(fake, tmp_path, runner=runner).refresh()
        assert {i["status"] for i in report["items"]} == {"unknown"} and fragment in report["items"][0]["note"]


def test_a_missing_claude_is_unknown(tmp_path, fake):
    cfg = ConnectorConfig(**{**fake.config_kwargs(tmp_path), "claude_exe": str(tmp_path / "no-claude")})
    report = MediatedConnectors(cfg).refresh()
    assert {i["status"] for i in report["items"]} == {"unknown"} and "not installed" in report["items"][0]["note"]


def test_a_failed_check_replaces_the_earlier_answer(fake, tmp_path):
    clock, mono = Clock(), Clock()
    ok = ScriptRunner("claude.ai Gmail: u - Connected")
    m = make(fake, tmp_path, runner=ok, clock=clock, monotonic=mono)
    assert by_name(m.refresh())["Gmail"]["status"] == "added"
    mono.t += MIN_INTERVAL_S
    m._runner = ScriptRunner("", returncode=1)
    assert by_name(m.refresh())["Gmail"]["status"] == "unknown"
    assert by_name(m.snapshot())["Gmail"]["status"] == "unknown"


def test_known_connectors_are_gmail_drive_slack():
    assert [name for name, _ in KNOWN.values()] == ["Gmail", "Google Drive", "Slack"]


# ---- the limit and single flight -----------------------------------------------------------------------------------------------------

def test_a_second_refresh_inside_sixty_seconds_is_refused(fake, tmp_path):
    mono = Clock()
    runner = ScriptRunner("claude.ai Gmail: u - Connected")
    m = make(fake, tmp_path, runner=runner, monotonic=mono)
    m.refresh()
    mono.t += 59.0
    with pytest.raises(RefreshTooSoon) as info:
        m.refresh()
    assert info.value.retry_after_s == pytest.approx(1.0) and len(runner.commands) == 1
    assert m.snapshot()["items"][0]["status"] == "added"                    # snapshot never counts against the limit
    mono.t += 1.0
    m.refresh()
    assert len(runner.commands) == 2 and MIN_INTERVAL_S == 60.0


def test_a_failed_refresh_also_starts_the_interval(fake, tmp_path):
    mono = Clock()
    runner = ScriptRunner("", returncode=1)
    m = make(fake, tmp_path, runner=runner, monotonic=mono)
    m.refresh()
    with pytest.raises(RefreshTooSoon):
        m.refresh()
    assert len(runner.commands) == 1


def test_concurrent_refreshes_share_one_run(fake, tmp_path):
    gate = threading.Event()
    runner = ScriptRunner("claude.ai Gmail: u - Connected", gate=gate)
    m = make(fake, tmp_path, runner=runner)
    results = []
    first = threading.Thread(target=lambda: results.append(m.refresh()))
    first.start()
    assert runner.entered.wait(5)
    second = threading.Thread(target=lambda: results.append(m.refresh()))
    second.start()
    time.sleep(0.2)                                                          # the second caller is now waiting on the first
    gate.set()
    first.join(5)
    second.join(5)
    assert len(runner.commands) == 1 and len(results) == 2 and results[0] == results[1]


def test_waiting_callers_see_the_leader_error(fake, tmp_path):
    gate = threading.Event()

    class Boom(ScriptRunner):
        def run(self, cmd, **kw):
            super().run(cmd, **kw)
            raise KeyError("boom")
    runner = Boom("", gate=gate)
    m = make(fake, tmp_path, runner=runner)
    errors = []

    def go():
        try:
            m.refresh()
        except KeyError as exc:
            errors.append(exc)
    threads = [threading.Thread(target=go)]
    threads[0].start()
    assert runner.entered.wait(5)
    threads.append(threading.Thread(target=go))
    threads[1].start()
    time.sleep(0.2)
    gate.set()
    for t in threads:
        t.join(5)
    assert len(errors) == 2 and len(runner.commands) == 1
    assert m._flight is None                                                 # the flight is cleared, so a later refresh can run


# ---- the child ---------------------------------------------------------------------------------------------------------------------------

def test_child_argv_stdin_cwd_and_env(fake, tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "CLAUDE_CODE_X", "SUTRA_TOKEN"):
        monkeypatch.setenv(name, "v")
    monkeypatch.chdir(tmp_path)
    make(fake, tmp_path).refresh()
    [call] = fake.calls("claude")
    assert call["argv"] == ["mcp", "list"] and call["op"] == "mcp_list"
    assert call["stdin"] is None                                              # stdin was /dev/null, nothing was written
    assert os.path.realpath(call["cwd"]) != os.path.realpath(str(tmp_path)) and call["cwd_entries"] == []
    assert not os.path.exists(call["cwd"])                                    # the empty working directory is removed afterwards
    visible = fake.visible_env_keys(call)
    assert visible <= {"PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE"}
    assert not [k for k in visible if k.startswith(("ANTHROPIC", "GITHUB", "CLAUDE_CODE", "SUTRA"))]


def test_the_runner_gets_the_total_timeout_and_a_fixed_command(fake, tmp_path):
    runner = ScriptRunner("claude.ai Gmail: u - Connected")
    make(fake, tmp_path, runner=runner, timeout_s=12.0).refresh()
    cmd, timeout = runner.commands[0]
    assert timeout == 12.0 and cmd.argv[1:] == ("mcp", "list") and cmd.stdin_text is None and cmd.provider == "claude"
