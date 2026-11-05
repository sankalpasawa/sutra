"""The live smoke of the whole app (work package GAP-LIVE, gap G07, decision D8).

Two kinds of test live here:

  * the OFFLINE ones check `scripts/live_smoke.py` itself (the ceiling, the counting, the judging of the eight open items, the
    report) and run a dry run against the fake CLIs (`--fakes`, J2's mock engine). They run in the default gate.
  * `test_whole_app_with_the_real_clis` is the same run as `scripts/live_smoke.py`, against the real CLIs on the owner's logins. It
    carries the `live` marker and runs only with SUTRA_LIVE=1 (and only on the owner's go-ahead):

        SUTRA_LIVE=1 scripts/py -m pytest tests/live -q -rs            # the ceiling is $5 and 120 calls; SUTRA_LIVE_MAX_USD changes it
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
FAKES = REPO / "tests" / "fakes"


def _load():
    spec = importlib.util.spec_from_file_location("live_smoke", REPO / "scripts" / "live_smoke.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["live_smoke"] = mod                     # dataclasses look the module up by name
    spec.loader.exec_module(mod)
    return mod


ls = _load()


def _keep_offline_tests_in_the_gate() -> None:
    """`tests/conftest.py` skips a test when "live" is among its keywords, and the folder `tests/live` puts that word on EVERY test
    in it, so without this the offline checks below would never run in the gate. A plugin registered while this module is
    imported (it looks up the running pytest config in the importing frame) removes that folder-made skip from the tests that
    carry no `live` marker of their own. The marked test keeps its skip. If the config is not found the tests simply stay skipped.
    Better fix, for the owner of tests/conftest.py: look the marker up with `item.get_closest_marker` instead of `item.keywords`."""
    frame, config = sys._getframe(1), None
    while frame is not None and config is None:
        found = frame.f_locals.get("config")
        config = found if isinstance(found, pytest.Config) else None
        frame = frame.f_back
    if config is None or config.pluginmanager.has_plugin("live-smoke-offline-tests"):
        return

    class Plugin:
        @pytest.hookimpl(trylast=True)
        def pytest_collection_modifyitems(self, config, items):
            if os.environ.get("SUTRA_LIVE") == "1":
                return
            for item in items:
                if getattr(item, "module", None) is sys.modules[__name__] and item.get_closest_marker("live") is None:
                    item.own_markers[:] = [m for m in item.own_markers
                                           if not (m.name == "skip" and str(m.kwargs.get("reason", "")).startswith("set SUTRA_LIVE"))]

    config.pluginmanager.register(Plugin(), "live-smoke-offline-tests")


_keep_offline_tests_in_the_gate()


# ---- the ceiling -------------------------------------------------------------------------------------------------------------

def test_the_cost_ceiling_trips_after_the_call_that_crosses_it_and_every_guard_after_that_raises():
    meter = ls.Meter(max_usd=1.0, max_calls=100)
    meter.add("claude", 0.6)
    meter.guard()
    assert meter.tripped is None
    meter.add("claude", 0.6)
    assert "cost ceiling" in meter.tripped
    with pytest.raises(ls.CeilingExceeded, match="cost ceiling"):
        meter.guard()


def test_spending_exactly_the_ceiling_does_not_trip_and_a_zero_ceiling_allows_free_calls():
    meter = ls.Meter(max_usd=0, max_calls=10)
    meter.add("claude", 0.0)
    meter.add("codex", None, 5, 5)
    meter.guard()
    assert meter.tripped is None
    capped = ls.Meter(max_usd=0.5, max_calls=10)
    capped.add("claude", 0.5)
    assert capped.tripped is None


def test_the_call_ceiling_trips_on_the_call_over_it_and_guard_before_a_call_refuses_the_call_that_would_cross_it():
    meter = ls.Meter(max_usd=100, max_calls=2)
    meter.add("claude", 0.0)
    meter.add("claude", 0.0)
    assert meter.tripped is None
    with pytest.raises(ls.CeilingExceeded, match="call ceiling"):
        meter.guard(before_call=True)                   # two calls were made: a third is not started
    again = ls.Meter(max_usd=100, max_calls=2)
    again.add("claude", 0.0)
    again.add("claude", 0.0)
    again.add("claude", 0.0)
    assert "call ceiling" in again.tripped


def test_the_time_limit_trips_through_the_injected_clock_and_the_callbacks_run_once():
    now = [100.0]
    meter = ls.Meter(10, 10, deadline=160.0, clock=lambda: now[0])
    seen = []
    meter.on_trip(seen.append)
    meter.guard()
    now[0] = 161.0
    with pytest.raises(ls.CeilingExceeded, match="time limit"):
        meter.guard()
    with pytest.raises(ls.CeilingExceeded):
        meter.guard()
    assert len(seen) == 1 and "time limit" in seen[0]


def test_tokens_are_kept_per_provider_and_calls_per_step():
    meter = ls.Meter(10, 10)
    meter.step = "a"
    meter.add("claude", 0.1, 10, 2)
    meter.step = "b"
    meter.add("codex", None, 7, 3)
    meter.add("codex", None, 1, 1)
    snap = meter.snapshot()
    assert snap["calls"] == 3 and snap["usd"] == 0.1
    assert snap["tokens"] == {"claude": {"in": 10, "out": 2}, "codex": {"in": 8, "out": 4}}
    assert meter.by_step["a"]["calls"] == 1 and meter.by_step["b"]["calls"] == 2


def test_the_usage_sink_counts_each_stored_row_once_skips_stub_rows_and_passes_the_transaction_on():
    meter = ls.Meter(10, 10)
    calls = []

    class Store:
        def record(self, row, *, tx=None):
            calls.append(tx)
            return row.ledger_id

    store = Store()
    ls.attach_usage_sink(meter, store)
    row = lambda ledger_id, provider="claude": SimpleNamespace(ledger_id=ledger_id, provider=provider, usd=0.25, tokens_in=10, tokens_out=None)   # noqa: E731
    assert store.record(row(1)) == 1
    store.record(row(1))                                  # a replayed engine line returns the same ledger id
    store.record(row(2), tx="tx")
    store.record(row(3, "stub"))
    assert meter.calls == 2 and meter.usd == 0.5 and meter.tokens["claude"] == {"in": 20, "out": 0}
    assert calls == [None, None, "tx", None]


def test_a_connector_spawn_is_counted_with_its_cost_and_the_call_over_the_ceiling_is_never_started(tmp_path):
    from sutra_app.connectors.claude import ClaudeConnector
    from sutra_app.connectors.models import ConnectorConfig
    usage = json.dumps({"input_tokens": 120, "output_tokens": 30})
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=str(FAKES / "claude"), python=sys.executable,
                          extra_env={"FAKE_PYTHON": sys.executable, "FAKE_COST_USD": "0.25", "FAKE_USAGE": usage,
                                     "FAKE_CLI_STATE": str(tmp_path / "state")})
    meter = ls.Meter(max_usd=5, max_calls=1)
    connector = ClaudeConnector(cfg)
    from sutra_app.connectors.base import ModelConnector
    before = ModelConnector._spawn
    with ls.metered_connectors(meter):
        connector.call_text("Say hi.", effort="low", timeout=30)
        assert meter.calls == 1 and meter.usd == pytest.approx(0.25) and meter.tokens["claude"] == {"in": 120, "out": 30}
        with pytest.raises(ls.CeilingExceeded):
            connector.call_text("Say hi again.", effort="low", timeout=30)
    assert ModelConnector._spawn is before
    calls = (tmp_path / "state" / "calls.jsonl").read_text().splitlines()
    assert sum(1 for line in calls if json.loads(line).get("kind") == "call") == 1       # the second call never reached the CLI


# ---- the helpers --------------------------------------------------------------------------------------------------------------

def test_make_png_is_a_valid_solid_red_png():
    data = ls.make_png(4, 3, (220, 30, 30))
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR" and int.from_bytes(data[16:20], "big") == 4 and int.from_bytes(data[20:24], "big") == 3
    idat = data.index(b"IDAT")
    size = int.from_bytes(data[idat - 4:idat], "big")
    raw = zlib.decompress(data[idat + 4:idat + 4 + size])
    assert len(raw) == 3 * (1 + 4 * 3) and raw[1:4] == bytes((220, 30, 30))
    assert data.endswith(b"IEND\xaeB`\x82")


def test_the_answers_come_in_order_the_last_repeats_and_the_limit_stops_them():
    answers = ls.AnswerList(("a", "b"), limit=3)
    assert [answers.next() for _ in range(3)] == ["a", "b", "b"]
    assert answers.exhausted
    assert "Little Fig" in ls.ANSWERS[0] and ls.AnswerList().limit == 6


def test_verify_failed_is_counted_by_check_and_can_be_limited_to_some_runs():
    rows = [
        {"atom_id": "r1:W-1", "status": "verify_failed", "body": {"verify": {"template": "reply-valid", "exit_code": 1}}},
        {"atom_id": "r1:W-2", "status": "verify_failed", "body": {"verify": {"template": "reply-valid", "exit_code": 1}}},
        {"atom_id": "r2:W-1", "status": "verify_failed", "body": {"verify": {"template": "charter-stamp", "exit_code": 1}}},
        {"atom_id": "r1:W-3", "status": "closed", "body": {"verify": {"template": "reply-valid", "exit_code": 0}}},
        {"atom_id": "r1:W-4", "status": "verify_failed", "body": {}},
    ]
    assert ls.verify_failed_by_check(rows) == {"?": 1, "charter-stamp": 1, "reply-valid": 2}
    assert ls.verify_failed_by_check(rows, ("r2",)) == {"charter-stamp": 1}
    assert ls.verify_failed_by_check(rows, ("r",)) == {}                 # a run id is matched whole, not as a prefix


def test_touches_miss_lines_are_counted_across_run_folders_and_bad_lines_are_ignored(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.mkdir(), b.mkdir()
    (a / "trace.jsonl").write_text('{"type": "layer.touches_miss", "data": {}}\nnot json\n{"type": "atom.refused"}\n[1]\n'
                                   '{"type": "layer.touches_miss"}\n')
    (b / "trace.jsonl").write_text('{"type": "layer.touches_miss"}\n')
    assert ls.count_touches_miss([a, b, c]) == 3


def test_the_audit_verdict_comes_from_the_last_audit_and_a_recheck_is_not_an_audit(tmp_path):
    audits = [{"cycle": 1, "all_pass": False, "results": [{"verdict": "FAIL"}, {"verdict": "PASS"}]},
              {"kind": "recheck", "all_pass": False},
              {"cycle": 2, "all_pass": True, "results": [{"verdict": "PASS"}, {"verdict": "PASS"}]}]
    (tmp_path / "audits.json").write_text(json.dumps(audits))
    got = ls.audit_summary(tmp_path)
    assert got["audits"] == 2 and got["verdict"] == "PASS" and got["verdicts"] == {"PASS": 2}
    assert got["failed_then_passed"] is True and got["first_audit_failed"] is True
    (tmp_path / "audits.json").write_text(json.dumps(audits[:1]))
    assert ls.audit_summary(tmp_path)["verdict"] == "FAIL"
    assert ls.audit_summary(tmp_path / "nowhere") == {"audits": 0, "verdict": "none"}


def test_a_site_renders_when_it_is_a_whole_page_and_the_browser_agrees(tmp_path):
    assert ls.site_renders(tmp_path) == {"exists": False, "renders": False, "browser": "none"}
    site = tmp_path / "site"
    site.mkdir()
    (site / "v1.html").write_text("<html><body>" + "x" * 300 + "</body></html>")
    assert ls.site_renders(tmp_path)["renders"] is True
    (site / "v2.html").write_text("<html><body>tiny</body></html>")          # the newest file is the one judged
    os.utime(site / "v1.html", (1, 1))
    assert ls.site_renders(tmp_path)["renders"] is False
    os.utime(site / "v2.html", (1, 1))
    os.utime(site / "v1.html", None)
    ok = lambda *a, **k: SimpleNamespace(returncode=0, stdout="<html><body>" + "y" * 300 + "</body></html>")      # noqa: E731
    bad = lambda *a, **k: SimpleNamespace(returncode=1, stdout="")                                                 # noqa: E731
    got = ls.site_renders(tmp_path, chrome="chrome", runner=ok)
    assert got["renders"] is True and got["browser"] == "ok"
    got = ls.site_renders(tmp_path, chrome="chrome", runner=bad)
    assert got["renders"] is False and got["browser"].startswith("failed")


def test_the_notes_section_is_appended_once_and_then_replaced_in_place():
    first = ls.splice_section("# Notes\n\nbuilt things\n", "## Results\n1\n")
    assert first.startswith("# Notes\n\nbuilt things\n\n") and first.count(ls.NOTES_BEGIN) == 1 and "## Results\n1" in first
    second = ls.splice_section(first + "\ntail\n", "## Results\n2\n")
    assert second.count(ls.NOTES_BEGIN) == 1 and "## Results\n2" in second and "## Results\n1" not in second
    assert second.startswith("# Notes\n\nbuilt things") and second.rstrip().endswith("tail")
    assert ls.splice_section("", "x").count(ls.NOTES_BEGIN) == 1                         # an empty file still gets the block


def test_junit_results_are_read_as_passed_failed_or_skipped():
    xml = ('<testsuites><testsuite><testcase classname="a.b" name="t1"/><testcase classname="a.b" name="t2"><failure/></testcase>'
           '<testcase classname="a.b" name="t3"><skipped/></testcase><testcase classname="a.b" name="t4"><error/></testcase></testsuite></testsuites>')
    assert ls.parse_junit(xml) == {"a.b::t1": "passed", "a.b::t2": "failed", "a.b::t3": "skipped", "a.b::t4": "failed"}


def test_the_command_line_defaults_to_the_documented_ceiling_and_refuses_an_unknown_step():
    args = ls.parse_args([])
    assert (args.max_usd, args.max_calls, args.fakes, args.only, args.skip) == (5.0, 120, False, [], [])
    args = ls.parse_args(["--fakes", "--max-usd", "0", "--only", "app,t1", "--skip", "t1"])
    assert args.fakes and args.max_usd == 0 and args.only == ["app", "t1"] and args.skip == ["t1"]
    with pytest.raises(SystemExit):
        ls.parse_args(["--only", "nope"])
    with pytest.raises(SystemExit):
        ls.parse_args(["--max-usd", "-1"])
    assert [s for s, _, _ in ls.STEPS] == ["doctor", "suites", "app", "t1", "followup", "t9", "t14", "image", "tools", "budget"]


# ---- the eight open items ------------------------------------------------------------------------------------------------------

def by_n(items):
    return {i["n"]: i for i in items}


GOOD = {
    "suites": {"tests": {
        "t.lib::test_chart_change_request_native[claude]": "passed", "t.lib::test_chart_change_request_native[codex]": "passed",
        "t.cn::test_native_schema_round_trip[codex]": "passed", "t.cn::test_native_schema_round_trip[claude]": "passed",
        "t.lib::test_a_corrected_schema_is_accepted_and_the_reply_parses[codex]": "passed"}},
    "followup": {"seeded": True, "status": "done", "outcome": "ok"},
    "replies": {"function_atoms": 30, "reply_valid_failed": 1, "verify_failed_by_check": {"reply-valid": 1}, "touches_miss": 0},
    "image": {"claude": {"status": "ok", "ok_color": True, "detail": "red"}, "codex": {"status": "ok", "ok_color": True, "detail": "red"}},
    "tools": {"claude": {"status": "ok", "ok_tool": True, "detail": "1 call"}, "codex": {"status": "ok", "ok_tool": True, "detail": "1 call"}},
    "budget": {"outcome": "stopped", "detail": "stopped"},
    "browser": {"chrome": "Chrome 156"},
}


def test_every_item_is_confirmed_when_the_evidence_is_good_except_the_browser_which_cannot_be_tested():
    items = by_n(ls.judge_items(GOOD))
    assert [items[n]["status"] for n in range(1, 8)] == [ls.CONFIRMED] * 7
    assert items[8]["status"] == ls.NOT_TESTABLE and "Safari" in items[8]["why"] and "Chrome 156" in items[8]["why"]
    assert len(items) == 8 and all(i["title"] for i in items.values())


def test_a_dry_run_confirms_nothing():
    items = ls.judge_items(GOOD, fakes=True)
    assert {i["status"] for i in items} == {ls.NOT_TESTABLE} and len(items) == 8


def test_no_evidence_at_all_is_not_testable_everywhere():
    assert {i["status"] for i in ls.judge_items({})} == {ls.NOT_TESTABLE}


def test_a_failed_union_schema_says_to_flip_chart_ops_transport_and_a_failed_codex_schema_names_its_switch():
    ev = dict(GOOD, suites={"tests": {"x::test_chart_change_request_native[codex]": "failed", "x::test_native_schema_round_trip[codex]": "failed"}})
    items = by_n(ls.judge_items(ev))
    assert items[1]["status"] == ls.FALLBACK and "CHART_OPS_TRANSPORT" in items[1]["switch"] and "codex" in items[1]["why"]
    assert items[7]["status"] == ls.FALLBACK and "native_schema=False" in items[7]["switch"]
    skipped = by_n(ls.judge_items(dict(GOOD, suites={"tests": {"x::test_chart_change_request_native[claude]": "skipped"}})))
    assert skipped[1]["status"] == ls.NOT_TESTABLE and skipped[7]["status"] == ls.NOT_TESTABLE


def test_the_follow_up_is_confirmed_when_it_ends_well_and_needs_the_old_condition_back_when_it_crashes():
    def judge(**fu):
        return by_n(ls.judge_items(dict(GOOD, followup=fu)))[2]
    assert judge(seeded=True, status="done_with_open_items")["status"] == ls.CONFIRMED
    bad = judge(seeded=True, status="crashed", outcome="rehydrate failed")
    assert bad["status"] == ls.FALLBACK and "realization == 0" in bad["switch"] and "rehydrate.py" in bad["switch"]
    assert judge(seeded=True, status="done", rehydrate_refused=True)["status"] == ls.CONFIRMED
    assert judge(seeded=True, status="stopped", rehydrate_refused=True)["status"] == ls.FALLBACK
    assert judge(seeded=True, status="stopped")["status"] == ls.NOT_TESTABLE
    assert judge(seeded=False, status="done")["status"] == ls.NOT_TESTABLE


def test_the_reply_failure_rate_decides_between_confirmed_and_loosening_the_classes():
    def judge(judged, failed, miss=0):
        return by_n(ls.judge_items(dict(GOOD, replies={"function_atoms": judged, "reply_valid_failed": failed,
                                                       "verify_failed_by_check": {"reply-valid": failed}, "touches_miss": miss}))) [3]
    assert judge(30, 3)["status"] == ls.CONFIRMED                       # exactly the 10% allowed
    low = judge(30, 4)
    assert low["status"] == ls.FALLBACK and "L5" in low["switch"] and "13%" in low["why"]
    assert judge(0, 0)["status"] == ls.NOT_TESTABLE
    assert "touches_miss" in judge(30, 0, miss=2)["why"]


def test_image_and_tool_failures_name_the_cli_and_the_switch_and_a_missing_cli_is_not_a_failure():
    ev = dict(GOOD, image={"claude": {"status": "ok", "ok_color": False, "detail": "not red"}, "codex": {"status": "ok", "ok_color": True, "detail": "red"}},
              tools={"claude": {"status": "skipped", "detail": "not installed"}, "codex": {"status": "fail", "ok_tool": False, "detail": "no tool"}})
    items = by_n(ls.judge_items(ev))
    assert items[4]["status"] == ls.FALLBACK and "claude: not red" in items[4]["why"] and "images=False" in items[4]["switch"]
    assert items[5]["status"] == ls.FALLBACK and "codex: no tool" in items[5]["why"] and "claude" not in items[5]["why"]
    only = by_n(ls.judge_items(dict(GOOD, tools={"claude": {"status": "skipped"}, "codex": {"status": "skipped"}}, image={})))
    assert only[4]["status"] == ls.NOT_TESTABLE and only[5]["status"] == ls.NOT_TESTABLE


def test_the_budget_flag_is_confirmed_when_accepted_or_honoured_and_a_fallback_when_it_breaks_the_call():
    def judge(outcome):
        return by_n(ls.judge_items(dict(GOOD, budget={"outcome": outcome, "detail": "d"})))[6]
    assert judge("stopped")["status"] == ls.CONFIRMED and judge("accepted")["status"] == ls.CONFIRMED
    broke = judge("error")
    assert broke["status"] == ls.FALLBACK and "claude.py" in broke["switch"]
    assert judge("not_run")["status"] == ls.NOT_TESTABLE


def test_the_markdown_carries_the_eight_items_the_steps_the_runs_and_a_stop_reason():
    report = {"mode": "live", "started": "2026-11-04T10:00:00", "seconds": 61.0, "ceiling": {"max_usd": 5.0, "max_calls": 120},
              "totals": {"calls": 7, "usd": 1.5, "tokens": {"codex": {"in": 4, "out": 2}}}, "aborted": "cost ceiling: x",
              "items": ls.judge_items(GOOD),
              "steps": [{"id": "app", "status": "aborted", "seconds": 3.0, "calls": 7, "usd": 1.5, "error": "boom | pipe", "problems": [], "notes": [],
                         "detail": {"run": {"status": "done", "atoms_by_state": {"closed": 3}, "verify_failed_by_check": {}, "touches_miss": 0,
                                            "audit": {"verdict": "PASS"}, "site": {"renders": True}}}}]}
    md = ls.render_markdown(report)
    assert md.count("**confirmed**") == 7 and "**not testable**" in md and "Stopped: cost ceiling: x" in md
    assert "| app | aborted | 3 | 7 | 1.5000 | boom / pipe |" in md and "| app | done | {'closed': 3} | none | 0 | PASS | True |" in md
    assert "codex: 4 in / 2 out" in md and "$1.5000 of $5" in md


def test_the_exit_code_tells_aborted_from_failed_from_clean():
    steps = lambda *s: {"aborted": None, "steps": [{"status": x} for x in s]}      # noqa: E731
    assert ls.exit_code(steps("ok", "skipped")) == 0
    assert ls.exit_code(steps("ok", "fail")) == 1 and ls.exit_code(steps("error")) == 1
    assert ls.exit_code({"aborted": "x", "steps": [{"status": "fail"}]}) == 3


# ---- the dry run against the fake CLIs ------------------------------------------------------------------------------------------

def test_the_dry_run_goes_through_every_path_against_the_fake_clis_without_a_model_and_exits_zero(tmp_path):
    out = tmp_path / "out"
    code = ls.main(["--fakes", "--max-usd", "0", "--out", str(out), "--only", "doctor,app,followup,image,tools,budget"])
    report = json.loads((out / "live-smoke-report.json").read_text())
    steps = {s["id"]: s for s in report["steps"]}
    assert code == 0 and report["mode"] == "fakes" and report["aborted"] is None
    assert [s["status"] for s in report["steps"]] == ["ok"] * 6
    app = steps["app"]["detail"]["run"]
    assert app["status"] == "done" and app["open_atoms_at_end"] == 0 and all(app["function_atoms"].get(fn, 0) >= 1 for fn in ls.FUNCTIONS)
    assert app["audit"]["verdict"] == "PASS" and app["site"]["renders"] is True
    assert steps["app"]["calls"] == 3 and report["totals"]["usd"] == 0                     # the chat agent's three fake calls, free
    assert steps["followup"]["detail"]["seeded"] is True and steps["followup"]["detail"]["run"]["status"] == "done"
    assert set(steps["image"]["detail"]["results"]) == {"claude", "codex"} and steps["budget"]["detail"]["outcome"] in ("accepted", "stopped")
    assert {i["status"] for i in report["items"]} == {ls.NOT_TESTABLE} and len(report["items"]) == 8
    assert (out / "live-smoke-report.md").read_text().startswith("## Live smoke results (fakes")
    assert not (REPO / "docs" / "notes" / "GAP-LIVE.md").exists() or ls.NOTES_BEGIN not in (REPO / "docs" / "notes" / "GAP-LIVE.md").read_text()


def test_the_ceiling_stops_a_dry_run_cleanly_skips_the_rest_and_exits_three(tmp_path):
    out = tmp_path / "out"
    code = ls.main(["--fakes", "--max-usd", "0", "--max-calls", "1", "--out", str(out), "--only", "app,t1,image"])
    report = json.loads((out / "live-smoke-report.json").read_text())
    assert code == 3 and "call ceiling" in report["aborted"]
    assert [s["status"] for s in report["steps"]] == ["aborted", "skipped", "skipped"]
    assert "Stopped: call ceiling" in (out / "live-smoke-report.md").read_text()
    db = out / "data" / "db.sqlite3"
    import sqlite3
    left = sqlite3.connect(db).execute("SELECT count(*) FROM tasks WHERE status IN ('starting','running','waiting_user','queued')").fetchone()[0]
    assert left == 0                                                                        # nothing is left running


def test_a_step_that_finds_no_cli_is_skipped_not_passed_and_the_items_stay_not_testable(tmp_path, monkeypatch):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))                       # neither claude nor codex can be found: no model can be called
    out = tmp_path / "out"
    code = ls.main(["--max-usd", "1", "--out", str(out), "--notes", "-", "--only", "image,budget"])
    report = json.loads((out / "live-smoke-report.json").read_text())
    assert code == 0 and [s["status"] for s in report["steps"]] == ["skipped", "skipped"] and report["totals"]["calls"] == 0
    items = {i["n"]: i["status"] for i in report["items"]}
    assert items[4] == items[6] == ls.NOT_TESTABLE and report["mode"] == "live"
    assert all("not installed" in str(s["notes"]) for s in report["steps"])


def test_the_notes_file_is_written_only_when_asked_and_a_second_run_replaces_the_section(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("# as built\n")
    args = ["--fakes", "--max-usd", "0", "--only", "budget", "--notes", str(notes)]
    ls.main(args + ["--out", str(tmp_path / "o1")])
    ls.main(args + ["--out", str(tmp_path / "o2")])
    text = notes.read_text()
    assert text.startswith("# as built\n") and text.count(ls.NOTES_BEGIN) == 1 and text.count("## Live smoke results") == 1


# ---- the real run (only with SUTRA_LIVE=1, only on the owner's go-ahead) ------------------------------------------------------------

@pytest.mark.live
def test_whole_app_with_the_real_clis(tmp_path):
    """The whole app on the owner's logins: the coffee-shop brief through the real chat agent and engine, then the other steps. The
    assertions of the package: Done or done-with-open-items, at least one atom per function, no atom open, usage rows carry atom ids,
    cost within the ceiling. (The four live suites are run by pytest itself, so the `suites` step is left out here.)"""
    max_usd = float(os.environ.get("SUTRA_LIVE_MAX_USD", "5"))
    out = tmp_path / "smoke"
    code = ls.main(["--max-usd", str(max_usd), "--max-calls", "120", "--out", str(out), "--notes", "-", "--skip", "suites"])
    report = json.loads((out / "live-smoke-report.json").read_text())
    print((out / "live-smoke-report.md").read_text())
    assert not report["aborted"], report["aborted"]
    assert report["totals"]["usd"] <= max_usd and report["totals"]["calls"] <= 120
    steps = {s["id"]: s for s in report["steps"]}
    assert steps["app"]["status"] == "ok", steps["app"]
    run = steps["app"]["detail"]["run"]
    assert run["status"] in ("done", "done_with_open_items")
    assert all(run["function_atoms"].get(fn, 0) >= 1 for fn in ls.FUNCTIONS), run["function_atoms"]
    assert run["open_atoms_at_end"] == 0
    assert run["engine_calls"] > 0 and run["engine_usage_rows_without_atom"] == 0
    assert code in (0, 1)
    failed = [s["id"] for s in report["steps"] if s["status"] in ("fail", "error")]
    assert not failed, failed


def test_the_script_runs_as_a_program_and_prints_its_usage():
    done = subprocess.run([sys.executable, str(REPO / "scripts" / "live_smoke.py"), "--help"], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "PYTHONPATH": str(REPO)})
    assert done.returncode == 0 and "--max-usd" in done.stdout and "--fakes" in done.stdout
