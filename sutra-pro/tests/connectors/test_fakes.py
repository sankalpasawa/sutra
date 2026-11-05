"""The fake claude, codex and gh, the harness in conftest.py and the captured fixtures (work package CN-2).

Most tests run tests/fakes/fake_cli.py in-process (fast); the ones that need a real process (the sh wrappers, signals, timing,
concurrency, the call log of a child) go through the wrappers. Nothing here calls a real model."""
from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent.parent
ROOT = TESTS.parent
FAKES = TESTS / "fakes"
FIXTURES = TESTS / "fixtures" / "connectors"
DESIGN = ROOT / "docs" / "design" / "connectors.md"
NOTES = ROOT / "docs" / "notes" / "CN-2.md"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fake_cli = _load("fake_cli", FAKES / "fake_cli.py")
capture = _load("capture_connector_fixtures", ROOT / "scripts" / "capture_connector_fixtures.py")


# ------------------------------------------------------------------------------------------------ helpers
class Seen:
    """What one run of a fake printed."""

    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err
        self.lines = fake_cli.parse_lines(out)

    @property
    def events(self):
        return [l for l in self.lines if isinstance(l, dict)]

    def of_type(self, kind):
        return [e for e in self.events if e.get("type") == kind]

    @property
    def result(self):
        found = self.of_type("result")
        return found[-1] if found else None

    @property
    def assistant(self):
        found = self.of_type("assistant")
        return found[0] if found else None

    @property
    def types(self):
        return [e.get("type") for e in self.events]


def go(fake, cli, *argv, stdin="", cwd=None, env=None, **extra):
    """Run a fake in-process with the handle's environment (FAKE_* extras as keywords; env={"NAME": None} removes a variable)."""
    environ = fake.process_env(**extra)
    for key, value in (env or {}).items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = value
    out, err = io.StringIO(), io.StringIO()
    data = stdin.encode() if isinstance(stdin, str) else stdin
    code = fake_cli.Run(cli, list(argv), env=environ, stdin=data, stdout=out, stderr=err, cwd=str(cwd or fake.root)).run()
    return Seen(code, out.getvalue(), err.getvalue())


def ask_claude(fake, *flags, stdin="hello", **kw):
    return go(fake, "claude", "-p", "--output-format", "stream-json", "--verbose", *flags, stdin=stdin, **kw)


def ask_codex(fake, *flags, resume=None, stdin="hello", **kw):
    argv = ["exec"] + (["resume"] if resume else []) + ["--json"] + list(flags) + ([resume] if resume else []) + ["-"]
    return go(fake, "codex", *argv, stdin=stdin, **kw)


SID = "11111111-2222-4333-8444-555555555555"
TID = "01aaaaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee"
SCHEMA = '{"type":"object","properties":{"answer":{"type":"string"}}}'


def fixture_lines(rel):
    return fake_cli.parse_lines((FIXTURES / rel).read_text(encoding="utf-8"))


def ids_in(lines, key):
    found = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == key and isinstance(v, str):
                    found.add(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(lines)
    return found


# ------------------------------------------------------------------------------------------------ the wrappers
@pytest.mark.parametrize("cli", ["claude", "codex", "gh"])
def test_wrapper_is_a_two_line_sh_script(cli):
    path = FAKES / cli
    lines = path.read_text().splitlines()
    assert os.access(str(path), os.X_OK)
    assert lines[0] == "#!/bin/sh" and len(lines) == 2
    assert lines[1].startswith("exec ") and ('fake_cli.py" %s "$@"' % cli) in lines[1]
    assert "${SUTRA_FAKE_PYTHON:-${FAKE_PYTHON:-python3}}" in lines[1]
    assert ' -E -S "$(dirname "$0")/fake_cli.py"' in lines[1]                  # no PYTHON* variables, no site-packages: quick and hermetic


@pytest.mark.parametrize(("cli", "expected"), [("claude", "2.1.308 (Claude Code)"), ("codex", "codex-cli 0.146.0"), ("gh", "gh version 2.87.3")])
def test_wrapper_runs_the_fake_for_its_own_name(fake, cli, expected):
    res = fake.run(cli, "--version")
    assert res.returncode == 0 and res.stdout.startswith(expected)


def test_sutra_fake_python_wins_then_fake_python_then_python3(fake, tmp_path):
    env = fake.process_env(SUTRA_FAKE_PYTHON=str(tmp_path / "no-such-python"))
    res = fake.run("claude", "--version", env=env)
    assert res.returncode != 0 and "no-such-python" in res.stderr           # SUTRA_FAKE_PYTHON was the one used
    env = fake.process_env()
    env.pop("SUTRA_FAKE_PYTHON")
    assert fake.run("claude", "--version", env=env).returncode == 0          # FAKE_PYTHON
    env.pop("FAKE_PYTHON")
    if shutil.which("python3"):
        assert fake.run("claude", "--version", env=env).stdout.startswith("2.1.308")       # python3 from PATH


def test_fake_cli_needs_only_the_standard_library_and_python_39():
    source = (FAKES / "fake_cli.py").read_text()
    tree = ast.parse(source, feature_version=(3, 9))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0}
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}


def test_unknown_program_name_and_scenario_listing_on_the_command_line():
    proc = subprocess.run([sys.executable, str(FAKES / "fake_cli.py"), "nope"], capture_output=True, text=True)
    assert proc.returncode == 2 and "usage" in proc.stderr
    proc = subprocess.run([sys.executable, str(FAKES / "fake_cli.py"), "--scenarios", "codex"], capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.split() == fake_cli.scenario_names("codex")


# ------------------------------------------------------------------------------------------------ the fixtures and the manifest
def manifest():
    return json.loads((FIXTURES / "MANIFEST.json").read_text())["files"]


def test_manifest_lists_every_fixture_file_and_nothing_else():
    listed = {e["path"] for e in manifest()}
    on_disk = {str(p.relative_to(FIXTURES)) for p in FIXTURES.rglob("*") if p.is_file() and p.name not in ("MANIFEST.json", "README.md")}
    assert listed == on_disk


def test_every_manifest_entry_says_how_it_came_about():
    for e in manifest():
        assert e["origin"] in ("captured", "derived", "handwritten"), e["path"]
        if e["origin"] == "captured":
            assert e["cli"] and e["command"] and e["shows"], e["path"]
        elif e["origin"] == "derived":
            assert (FIXTURES / e["base"]).is_file() and e["change"] and e["wording_source"], e["path"]
        else:
            assert e["source"] and e["shows"] and e["wording_source"], e["path"]
            assert e["path"].startswith("handwritten/")


def test_recorded_after_names_an_existing_fixture_and_derived_files_inherit_it():
    entries = {e["path"]: e for e in manifest()}
    for e in entries.values():
        if "recorded_after" in e:
            assert e["recorded_after"] in entries
    assert fake_cli.recorded_after("claude/stream_resume_plain_ok.jsonl") == "claude/stream_structured_ok.jsonl"
    assert fake_cli.recorded_after("codex/exec_resume_plain_ok.jsonl") == "codex/exec_structured_ok.jsonl"
    assert fake_cli.recorded_after("derived/claude_plain_not_json.jsonl") == "claude/stream_structured_ok.jsonl"     # through its base
    assert fake_cli.recorded_after("derived/claude_overloaded.jsonl") is None
    assert fake_cli.recorded_after("claude/stream_structured_ok.jsonl") is None


def test_jsonl_fixtures_are_json_lines_except_the_declared_noise():
    for path in FIXTURES.rglob("*.jsonl"):
        for n, raw in enumerate(path.read_text().split("\n")[:-1]):
            if path.name == "claude_noise_lines.jsonl" and n in (1, 2):
                assert not raw.startswith("{")
                continue
            assert isinstance(json.loads(raw), dict), (path, n)


def test_fixtures_hold_no_identity_and_no_local_path():
    allowed_paths = ("/Users/me/", "/scratch/probe", "/work")
    for path in FIXTURES.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        for needle in ("tchan" "drakar", "tis" "hant", "@gmail", "/private/var", "/home/", "claude-501"):
            assert needle not in text, (path, needle)
        for found in re.findall(r"/Users/[A-Za-z0-9_.-]+/", text):
            assert found == "/Users/me/", (path, found)
    assert allowed_paths


def test_fixture_readme_describes_all_three_origins_and_the_fakes():
    text = (FIXTURES / "README.md").read_text()
    for word in ("captured", "derived", "handwritten", "tests/fakes", "capture_connector_fixtures.py"):
        assert word in text


def test_notes_file_exists_and_stays_within_sixty_lines():
    assert NOTES.is_file() and len(NOTES.read_text().splitlines()) <= 60


# ------------------------------------------------------------------------------------------------ scenarios replay their fixtures
FILE_SCENARIOS = [(cli, name, scn.file) for cli in ("claude", "codex") for name, scn in fake_cli.table(cli).items() if scn.file and not scn.base]
EXPECTED_EXIT = {
    "claude": {"ok_structured": 0, "ok_plain": 0, "not_logged_in": 1, "mcp_connected": 1, "tool_profile": 1, "session_lost": 1, "control_interrupt": 0,
               "quota": 1, "billing_error": 1, "overloaded": 1, "server_error": 1, "invalid_request": 1, "model_not_found": 1, "login_expired": 1,
               "structured_failed": 1, "error_during_execution": 1, "truncated_no_result": 137, "plain_not_json": 0, "plain_json_in_fence": 0,
               "plain_json_wrong_shape": 0, "noise_lines": 0},
    "codex": {"ok_structured": 0, "ok_plain": 0, "not_signed_in": 1, "usage_limit": 1, "rate_limited_429": 1, "server_error_500": 1,
              "schema_rejected_400": 1, "model_unsupported_400": 1, "reply_not_json": 0, "reply_wrong_shape": 0, "reply_in_fence": 0,
              "truncated_no_turn_end": 137, "empty_reply": 0, "unknown_item_type": 0},
}
COUNTER_KEYS = {"total_cost_usd", "usage", "modelUsage"}


def normalised(lines, old_ids, new_id, drop_events):
    """Lines made comparable: ids unified, the cumulative counters (checked on their own) removed, stream_event lines optionally dropped."""
    out = []
    for item in lines:
        if isinstance(item, str):
            out.append(item)
            continue
        if drop_events and item.get("type") == "stream_event":
            continue
        text = json.dumps({k: v for k, v in item.items() if k not in COUNTER_KEYS}, sort_keys=True)
        for old in list(old_ids) + [new_id]:
            text = text.replace(old, "ID")
        out.append(text)
    return out


@pytest.mark.parametrize(("cli", "name", "rel"), FILE_SCENARIOS, ids=["%s-%s" % (c, n) for c, n, _ in FILE_SCENARIOS])
def test_each_scenario_replays_its_fixture(fake, cli, name, rel):
    fake.sequence(name)
    res = ask_claude(fake) if cli == "claude" else ask_codex(fake)
    call = fake.model_calls(cli)[-1]
    fixture = fixture_lines(rel)
    key = "session_id" if cli == "claude" else "thread_id"
    got = normalised(res.lines, set(), call["session_id"], False)
    want = normalised(fixture, ids_in(fixture, key), call["session_id"], cli == "claude")
    assert got == want
    assert res.code == EXPECTED_EXIT[cli][name]
    assert call["scenario"] == name
    if ids_in(fixture, key):
        assert call["session_id"] in res.out and not (ids_in(fixture, key) - {call["session_id"]}) & set(re.findall(r"[0-9a-f]{8}-[0-9a-f-]{27}", res.out))


def test_every_stream_fixture_of_the_manifest_is_a_scenario():
    replayed = {scn.file for cli in ("claude", "codex") for scn in fake_cli.table(cli).values() if scn.file}
    streams = {e["path"] for e in manifest() if e["path"].endswith(".jsonl") and e["path"].split("/")[0] in ("claude", "codex", "derived")}
    assert streams - {"codex/rollout_token_count.jsonl"} == replayed            # the rollout is not a stream: the fake takes its token_count line as a template
    assert "codex/rollout_token_count.jsonl" in streams


def test_probe_fixtures_of_cli_errors_are_scenarios_with_their_exit_and_stderr(fake):
    probes = {p["id"]: p for p in json.loads((FIXTURES / "cli_errors.json").read_text())["probes"]}
    for cli, name, probe_id in (("claude", "invalid_json_schema", "claude_invalid_json_schema"), ("claude", "system_prompt_file_missing", "claude_system_prompt_file_missing"),
                                ("codex", "output_schema_file_invalid", "codex_output_schema_file_invalid"),
                                ("codex", "output_schema_file_missing", "codex_output_schema_file_missing"),
                                ("codex", "missing_working_directory", "codex_missing_working_directory")):
        scn = fake_cli.resolve(cli, name, False)
        assert scn.probe == probe_id and probes[probe_id]["exit"] in (1, 2)


def test_scenario_names_accept_stems_aliases_and_row_ids_and_reject_the_rest():
    assert fake_cli.canonical("claude", "stream_structured_ok") == "ok_structured"
    assert fake_cli.canonical("claude", "claude_quota_rejected") == "quota"
    assert fake_cli.canonical("claude", "quota_rejected") == "quota"
    assert fake_cli.canonical("codex", "exec_not_signed_in") == "not_signed_in"
    assert fake_cli.canonical("codex", "codex_usage_limit") == "usage_limit"
    assert fake_cli.canonical("codex", "quota") == "usage_limit" and fake_cli.canonical("claude", "usage_limit") == "quota"
    assert fake_cli.canonical("codex", "overloaded") == "server_error_500"
    assert fake_cli.canonical("claude", "C7") == "quota" and fake_cli.canonical("codex", "X6") == "usage_limit"
    with pytest.raises(fake_cli.FakeError, match="unknown scenario 'nope'.*known: "):
        fake_cli.canonical("claude", "nope")


SHARED_NAMES = ["ok", "ok_structured", "ok_plain", "quota", "overloaded", "not_logged_in", "not_signed_in", "server_error", "rate_limited", "billing_error",
                "model_not_found", "hang", "hang_silent", "slow", "noise", "crash", "truncated_exit0", "empty_reply", "bad_flag", "session_lost"]


@pytest.mark.parametrize("name", SHARED_NAMES, ids=["name-" + n for n in SHARED_NAMES])      # an id of exactly "slow" would switch the test off (tests/conftest.py)
def test_the_names_of_a_shared_sequence_exist_for_both_clis(name):
    for cli in ("claude", "codex"):
        assert fake_cli.canonical(cli, name) in fake_cli.table(cli) or name == "ok"
        assert name in fake_cli.scenario_names(cli) or fake_cli.canonical(cli, name) == name


def test_every_row_of_the_error_tables_has_a_scenario_or_is_listed_as_needing_none():
    text = DESIGN.read_text()
    spec_rows = set(re.findall(r"^\| ([CX]\d+) \|", text, re.M))
    assert {"C1", "C25", "X1", "X18"} <= spec_rows and len(spec_rows) == 43
    mapped = set(fake_cli.ROWS["claude"]) | set(fake_cli.ROWS["codex"])
    without = set(fake_cli.ROWS_WITHOUT_SCENARIO["claude"]) | set(fake_cli.ROWS_WITHOUT_SCENARIO["codex"])
    for row in spec_rows:
        assert row in without or row in mapped or any(m.startswith(row) and m[len(row):].isalpha() for m in mapped), row
    for row, name in {**fake_cli.ROWS["claude"], **fake_cli.ROWS["codex"]}.items():
        cli = "claude" if row.startswith("C") else "codex"
        assert name in fake_cli.table(cli), row
    for row in without:
        assert row not in mapped


def err_of(seen):
    return (seen.assistant or {}).get("error")


def text_of(seen):
    return " ".join(b.get("text", "") for b in (seen.assistant or {}).get("message", {}).get("content", []))


CLAUDE_ROWS = {
    "C4": lambda s: err_of(s) == "authentication_failed" and "Not logged in" in text_of(s) and s.result["is_error"] and s.result["subtype"] == "success" and s.code == 1,
    "C5": lambda s: err_of(s) == "authentication_failed" and "Login expired" in text_of(s),
    "C6a": lambda s: err_of(s) == "oauth_org_not_allowed" and s.result["is_error"],
    "C6b": lambda s: err_of(s) == "account_on_hold" and s.result["is_error"],
    "C6c": lambda s: err_of(s) == "verification_required" and s.result["is_error"],
    "C7": lambda s: err_of(s) == "rate_limit" and s.of_type("rate_limit_event")[0]["rate_limit_info"]["status"] == "rejected"
    and s.of_type("rate_limit_event")[0]["rate_limit_info"]["resetsAt"] and "hit your limit" in text_of(s),
    "C8": lambda s: err_of(s) == "rate_limit" and not s.of_type("rate_limit_event") and "hit your limit" not in text_of(s) and s.result["api_error_status"] == 429,
    "C9": lambda s: err_of(s) == "billing_error",
    "C10": lambda s: err_of(s) == "overloaded" and s.result["api_error_status"] == 529,
    "C11": lambda s: err_of(s) == "server_error" and s.result["api_error_status"] == 500,
    "C12": lambda s: err_of(s) == "invalid_request",
    "C13": lambda s: err_of(s) == "model_not_found",
    "C14": lambda s: err_of(s) == "max_output_tokens" and "partial" in text_of(s),
    "C15": lambda s: s.result["subtype"] == "error_max_structured_output_retries" and "structured_output" not in s.result and s.result["is_error"],
    "C16": lambda s: s.result["subtype"] == "error_during_execution" and s.result["num_turns"] == 0 and "No conversation found with session ID: " in s.err,
    "C17": lambda s: s.result["subtype"] == "error_during_execution" and s.result["num_turns"] == 1 and s.result["is_error"],
    "C18": lambda s: s.result["subtype"] == "error_max_budget_usd" and s.result["is_error"],
    "C19a": lambda s: "error" not in s.assistant and s.result["is_error"] and s.result["api_error_status"] == 401,
    "C19b": lambda s: "error" not in s.assistant and s.result["is_error"] and s.result["api_error_status"] == 403,
    "C19c": lambda s: "error" not in s.assistant and s.result["is_error"] and s.result["api_error_status"] is None and "Not logged in" in s.result["result"],
    "C19d": lambda s: "error" not in s.assistant and s.result["is_error"] and s.result["api_error_status"] == 429,
    "C19e": lambda s: "error" not in s.assistant and s.result["is_error"] and s.result["api_error_status"] == 503,
    "C20": lambda s: s.result is None and s.code == 137 and s.assistant is not None,
    "C21": lambda s: s.result is None and s.code == 0 and s.assistant is not None,
    "C24": lambda s: s.result["is_error"] is False and s.result["result"] == "" and "structured_output" not in s.result and text_of(s) == "",
    "C25": lambda s: any(isinstance(l, str) and l.startswith("Warning") for l in s.lines) and "" in s.lines and s.result["result"] == "ok" and s.code == 0,
}
CLAUDE_ROWS_STDERR = {
    "C2": lambda s: s.out == "" and s.err.startswith("error: unknown option '--") and s.code == 1,
    "C3a": lambda s: s.out == "" and "--json-schema is not valid JSON" in s.err and s.code == 1,
    "C3b": lambda s: s.out == "" and "System prompt file not found" in s.err and s.code == 1,
}


@pytest.mark.parametrize("row", sorted(CLAUDE_ROWS))
def test_claude_row_scenarios_show_the_condition_of_their_row(fake, row):
    fake.sequence(row)
    seen = ask_claude(fake)
    assert CLAUDE_ROWS[row](seen), (row, seen.out[:600], seen.err)


@pytest.mark.parametrize("row", sorted(CLAUDE_ROWS_STDERR))
def test_claude_command_line_rows_print_only_to_stderr(fake, row):
    fake.sequence(row)
    seen = ask_claude(fake)
    assert CLAUDE_ROWS_STDERR[row](seen), (row, seen.err)


def error_texts(seen):
    failed = seen.of_type("turn.failed")
    return [e["error"]["message"] for e in failed]


CODEX_ROWS = {
    "X5": lambda s: any("401" in e["message"] for e in s.of_type("error")) and "Unauthorized" in error_texts(s)[0] and s.code == 1,
    "X5c": lambda s: not s.of_type("error") and "401" in error_texts(s)[0] and "Unauthorized" in error_texts(s)[0] and s.code == 1,
    "X6": lambda s: "usage limit" in error_texts(s)[0] and s.code == 1,
    "X7": lambda s: "429" in error_texts(s)[0] and "Too Many Requests" in error_texts(s)[0],
    "X8": lambda s: "exceeded retry limit, last status: 500" in error_texts(s)[0],
    "X9": lambda s: "400" in error_texts(s)[0] and "schema" in error_texts(s)[0],
    "X10": lambda s: "400" in error_texts(s)[0] and "model" in error_texts(s)[0],
    "X11": lambda s: error_texts(s) and not any(w in error_texts(s)[0] for w in ("401", "429", "usage limit", "400", "retry limit", "Unauthorized")),
    "X13": lambda s: s.types == ["thread.started", "turn.started"] and s.code == 137,
    "X14": lambda s: s.types == ["thread.started", "turn.started"] and s.code == 0,
    "X17": lambda s: "turn.completed" in s.types and not any(e.get("item", {}).get("type") == "agent_message" for e in s.events),
    "X18": lambda s: [e["item"]["type"] for e in s.of_type("item.completed")] == ["command_execution", "agent_message"] and s.code == 0,
}
CODEX_ROWS_STDERR = {
    "X2": lambda s: s.out == "" and s.err.startswith("error: unexpected argument '--") and s.code == 2,
    "X12": lambda s: s.out == "" and "no rollout found for thread id" in s.err and s.code == 1,
}


@pytest.mark.parametrize("row", sorted(CODEX_ROWS))
def test_codex_row_scenarios_show_the_condition_of_their_row(fake, row):
    fake.sequence(row)
    seen = ask_codex(fake)
    assert CODEX_ROWS[row](seen), (row, seen.out[:600], seen.err)


@pytest.mark.parametrize("row", sorted(CODEX_ROWS_STDERR))
def test_codex_command_line_rows_print_only_to_stderr(fake, row):
    fake.sequence(row)
    seen = ask_codex(fake, resume=TID) if row == "X12" else ask_codex(fake)
    assert CODEX_ROWS_STDERR[row](seen), (row, seen.err)


def test_codex_x3_rows_come_from_the_argument_checks_of_the_fake_itself(fake, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    seen = ask_codex(fake, "--output-schema", str(bad))
    assert seen.out == "" and seen.code == 1 and "Output schema file %s is not valid JSON" % bad in seen.err
    seen = ask_codex(fake, "--output-schema", str(tmp_path / "missing.json"))
    assert seen.code == 1 and "Failed to read output schema file" in seen.err and "No such file or directory" in seen.err
    seen = ask_codex(fake, "-C", str(tmp_path / "no-dir"))
    assert seen.code == 1 and seen.err == "Error: No such file or directory (os error 2)\n"
    assert fake.model_calls("codex")[-1]["scenario"] == "(argument error)"
    for name, needle in (("output_schema_file_invalid", "Output schema file"), ("output_schema_file_missing", "Failed to read output schema"),
                         ("missing_working_directory", "No such file or directory")):          # the same texts as scenarios, for a connector that never writes the file
        fake.sequence(name)
        seen = ask_codex(fake)
        assert seen.code == 1 and needle in seen.err and seen.out == ""


def test_resolve_hands_out_a_fresh_scenario_every_time():
    for cli in ("claude", "codex"):
        for name in ("ok_plain", "bad_flag", "hang", "quota"):
            first, second = fake_cli.resolve(cli, name, False), fake_cli.resolve(cli, name, False)
            shared = fake_cli.table(cli)[fake_cli.canonical(cli, name)]
            assert first is not second and first is not shared and first.patch is not shared.patch
    assert fake_cli.resolve("claude", "ok", False).file == "claude/stream_resume_plain_ok.jsonl"
    assert fake_cli.resolve("claude", "ok", True).file == "claude/stream_structured_ok.jsonl"
    assert fake_cli.resolve("codex", "ok", True).file == "codex/exec_structured_ok.jsonl" and fake_cli.resolve("codex", "ok", False).file == "codex/exec_resume_plain_ok.jsonl"
    assert fake_cli.resolve("claude", "hang", True).file == "claude/stream_structured_ok.jsonl" and fake_cli.resolve("claude", "hang", True).hang_after == 1


def test_the_state_of_one_run_does_not_leak_into_the_next_through_the_tables(fake):
    fake.sequence("session_lost")
    ask_claude(fake, "--resume", SID)
    assert fake_cli.table("claude")["session_lost"].exit is None
    fake.sequence("bad_flag", cli="claude")
    ask_claude(fake)
    assert fake_cli.table("claude")["bad_flag"].exit is None and fake_cli.table("claude")["bad_flag"].patch == []


# ------------------------------------------------------------------------------------------------ sequences
def test_default_scenario_is_ok_plain_or_ok_structured_when_a_schema_is_sent(fake):
    seen = ask_claude(fake)
    assert seen.result["result"] == "ok" and "structured_output" not in seen.result and seen.code == 0
    seen = ask_claude(fake, "--json-schema", SCHEMA)
    assert seen.result["structured_output"] == {"answer": "ok"}
    assert [c["scenario"] for c in fake.model_calls()] == ["ok", "ok"]
    seen = ask_codex(fake, "--output-schema", str(FIXTURES / "handwritten" / "gh" / "repo.json"))
    assert json.loads(seen.of_type("item.completed")[0]["item"]["text"]) == {"answer": "ok"}
    assert ask_codex(fake).of_type("item.completed")[0]["item"]["text"] == "ok"


def test_the_sequence_gives_one_scenario_per_model_call_and_the_last_repeats(fake):
    fake.sequence("quota", "ok_plain", "overloaded")
    codes = [ask_claude(fake).code for _ in range(5)]
    assert codes == [1, 0, 1, 1, 1]
    assert [c["scenario"] for c in fake.model_calls()] == ["quota", "ok_plain", "overloaded", "overloaded", "overloaded"]
    assert json.loads((fake.state_dir / "counters.json").read_text())["seq:shared"] == 5


def test_repeat_syntax_and_blank_entries(fake):
    assert fake_cli.parse_sequence("quota*2, ok_plain,,") == ["quota", "quota", "ok_plain"]
    assert fake_cli.parse_sequence("*3") == ["*3"] and fake_cli.parse_sequence(None) == []
    assert fake_cli.parse_sequence("file:/tmp/a*b.jsonl,quota*x,ok_plain*0") == ["file:/tmp/a*b.jsonl", "quota*x"]       # only a number after the star repeats
    fake.set(FAKE_CLI_SEQUENCE="overloaded*2,ok_plain")
    assert [ask_claude(fake).code for _ in range(4)] == [1, 1, 0, 0]


def test_status_commands_do_not_consume_the_sequence(fake):
    fake.sequence("quota", "ok_plain")
    go(fake, "claude", "auth", "status")
    go(fake, "claude", "--version")
    go(fake, "claude", "--help")
    go(fake, "codex", "login", "status")
    go(fake, "codex", "debug", "models")
    assert ask_claude(fake).code == 1                                          # still the first scenario
    assert ask_claude(fake).code == 0
    kinds_seen = [c["kind"] for c in fake.calls()]
    assert kinds_seen.count("probe") == 5 and kinds_seen.count("call") == 2


def test_one_sequence_counts_the_model_calls_of_both_clis_in_order(fake):
    fake.sequence("quota", "ok_plain", "server_error_500")
    first = ask_claude(fake)
    second = ask_codex(fake)
    third = ask_claude(fake)
    assert first.of_type("assistant")[0]["error"] == "rate_limit"
    assert second.of_type("item.completed")[0]["item"]["text"] == "ok"
    assert third.code == 1 and third.assistant["error"] == "server_error"                  # the codex name is mapped for claude


def test_per_cli_sequences_have_their_own_counters_and_win_over_the_shared_one(fake):
    fake.sequence("ok_plain", "ok_plain")
    fake.sequence("quota", "ok_plain", cli="claude")
    fake.sequence("usage_limit", "ok_plain", cli="codex")
    assert [ask_claude(fake).code, ask_codex(fake).code, ask_codex(fake).code, ask_claude(fake).code] == [1, 1, 0, 0]
    assert [c["scenario"] for c in fake.model_calls("codex")] == ["usage_limit", "ok_plain"]
    counters = json.loads((fake.state_dir / "counters.json").read_text())
    assert counters["seq:claude"] == 2 and counters["seq:codex"] == 2 and "seq:shared" not in counters


def test_an_unknown_scenario_is_a_setup_error_that_names_the_known_ones_and_is_logged(fake):
    fake.sequence("nope")
    seen = ask_claude(fake)
    assert seen.code == 64 and seen.out == ""
    assert "fake claude: unknown scenario 'nope'; known: " in seen.err and "ok_plain" in seen.err and "C7" in seen.err
    call = fake.model_calls("claude")[0]
    assert "unknown scenario 'nope'" in call["error"] and call["exit"] == 64


def test_several_scenarios_need_a_state_directory_and_one_does_not(fake):
    environ = {k: v for k, v in fake.process_env().items() if k != "FAKE_CLI_STATE"}
    environ["FAKE_CLI_SEQUENCE"] = "quota,ok_plain"
    out, err = io.StringIO(), io.StringIO()
    code = fake_cli.Run("claude", ["-p", "--output-format", "stream-json", "--verbose"], env=environ, stdin=b"x", stdout=out, stderr=err).run()
    assert code == 64 and "needs FAKE_CLI_STATE" in err.getvalue()
    environ["FAKE_CLI_SEQUENCE"] = "quota"
    out, err = io.StringIO(), io.StringIO()
    code = fake_cli.Run("claude", ["-p", "--output-format", "stream-json", "--verbose"], env=environ, stdin=b"x", stdout=out, stderr=err).run()
    assert code == 1 and "authentication_failed" not in out.getvalue() and "rate_limit" in out.getvalue()
    assert not (fake.state_dir / "calls.jsonl").exists()                         # stateless: nothing is logged


def test_signed_out_turns_ok_into_the_not_signed_in_stream_but_an_explicit_scenario_wins(fake):
    fake.auth(claude="signed_out", codex="signed_out")
    assert ask_claude(fake).assistant["error"] == "authentication_failed"
    seen = ask_codex(fake)
    assert seen.code == 1 and seen.of_type("turn.failed") and "401" in error_texts(seen)[0]
    fake.sequence("ok_plain", "ok")
    assert ask_claude(fake).result["result"] == "ok"
    assert ask_claude(fake).assistant["error"] == "authentication_failed"


def test_file_scenario_replays_any_jsonl_file_and_needs_an_absolute_path(fake, tmp_path):
    stream = tmp_path / "mine.jsonl"
    stream.write_text(json.dumps({"type": "system", "subtype": "init", "session_id": "old"}) + "\n" + json.dumps({"type": "result", "is_error": True, "session_id": "old"}) + "\n")
    fake.sequence("file:" + str(stream))
    seen = ask_claude(fake, "--session-id", SID)
    assert [e["session_id"] for e in seen.events] == [SID, SID] and seen.code == 1
    fake.sequence("file:relative.jsonl")
    seen = ask_claude(fake)
    assert seen.code == 64 and "absolute path" in seen.err


# ------------------------------------------------------------------------------------------------ session ids, cumulative counters
def test_session_id_is_rewritten_everywhere_for_session_id_resume_and_synthetic(fake):
    seen = ask_claude(fake, "--session-id", SID, "--include-partial-messages", "--json-schema", SCHEMA)
    assert {e["session_id"] for e in seen.events if "session_id" in e} == {SID}
    assert SID in seen.out and "092c7b68" not in seen.out
    seen = ask_claude(fake, "--resume", SID)
    assert {e["session_id"] for e in seen.events if "session_id" in e} == {SID}
    first, second = ask_claude(fake), ask_claude(fake)
    ids = [first.result["session_id"], second.result["session_id"]]
    assert ids == ["00000000-0000-4000-8000-000000000003", "00000000-0000-4000-8000-000000000004"]
    assert fake.model_calls()[0]["session_id"] == SID
    fake.sequence("session_lost")
    lost = ask_claude(fake, "--resume", SID)
    assert lost.result["session_id"] == SID and lost.result["errors"] == ["No conversation found with session ID: " + SID]
    assert lost.err == "No conversation found with session ID: %s\n" % SID


def test_thread_id_is_rewritten_for_codex_resume_and_synthetic_for_a_new_thread(fake):
    seen = ask_codex(fake)
    assert seen.events[0] == {"type": "thread.started", "thread_id": "00000000-0000-7000-8000-000000000001"}
    seen = ask_codex(fake, resume=TID)
    assert seen.events[0] == {"type": "thread.started", "thread_id": TID}
    fake.sequence("session_lost")
    seen = ask_codex(fake, resume=TID)
    assert seen.err == "Error: thread/resume: thread/resume failed: no rollout found for thread id %s (code -32600)\n" % TID


def test_claude_counters_are_cumulative_for_a_session_and_the_per_turn_usage_is_not(fake):
    fake.sequence("ok_structured", "ok_plain", "ok_plain")
    first = ask_claude(fake, "--session-id", SID, "--json-schema", SCHEMA)
    second = ask_claude(fake, "--resume", SID)
    third = ask_claude(fake, "--resume", SID)
    assert first.result["total_cost_usd"] == pytest.approx(0.0097459)
    assert second.result["total_cost_usd"] == pytest.approx(0.0190348)                       # 0.009746 + 0.009289: the captured numbers
    assert third.result["total_cost_usd"] == pytest.approx(0.0190348 + 0.0092889)
    model_usage = second.result["modelUsage"]["claude-sonnet-5-5"]
    assert (model_usage["inputTokens"], model_usage["outputTokens"], model_usage["cacheReadInputTokens"], model_usage["cacheCreationInputTokens"]) == (6, 57, 1728, 4570)
    assert model_usage["costUSD"] == second.result["total_cost_usd"]
    for seen in (second, third):                                                              # result.usage stays the turn's own
        usage = seen.result["usage"]
        assert (usage["input_tokens"], usage["cache_creation_input_tokens"], usage["cache_read_input_tokens"], usage["output_tokens"]) == (4, 2294, 649, 4)
    assert fake.sessions()["claude:" + SID]["turns"] == 3
    assert third.result["modelUsage"]["claude-sonnet-5-5"]["inputTokens"] == 10


def test_a_one_shot_call_and_a_second_session_start_from_zero(fake):
    fake.sequence("ok_plain")
    one, two = ask_claude(fake), ask_claude(fake)
    assert one.result["total_cost_usd"] == pytest.approx(0.0092889) == pytest.approx(two.result["total_cost_usd"])
    other = ask_claude(fake, "--session-id", SID)
    again = ask_claude(fake, "--resume", "99999999-2222-4333-8444-555555555555")
    assert other.result["total_cost_usd"] == pytest.approx(0.0092889) == pytest.approx(again.result["total_cost_usd"])
    assert one.result["modelUsage"]["claude-sonnet-5-5"]["inputTokens"] == 4
    assert len([k for k in fake.sessions() if k.startswith("claude:")]) == 4


def test_cost_and_usage_overrides_are_this_calls_amounts_and_add_to_the_session(fake):
    fake.cost(0.5).usage(input_tokens=100, output_tokens=7)
    first = ask_claude(fake, "--session-id", SID)
    second = ask_claude(fake, "--resume", SID)
    assert first.result["total_cost_usd"] == 0.5 and second.result["total_cost_usd"] == 1.0
    assert second.result["usage"]["input_tokens"] == 100 and second.result["usage"]["cache_read_input_tokens"] == 0
    assert second.result["usage"]["iterations"][0]["output_tokens"] == 7
    assert second.assistant["message"]["usage"]["output_tokens"] == 7
    mu = second.result["modelUsage"]["claude-sonnet-5-5"]
    assert (mu["inputTokens"], mu["outputTokens"], mu["cacheReadInputTokens"], mu["cacheCreationInputTokens"], mu["costUSD"]) == (200, 14, 0, 0, 1.0)


def test_errors_cost_nothing_but_report_the_session_total(fake):
    fake.sequence("ok_plain", "overloaded")
    ask_claude(fake, "--session-id", SID)
    failed = ask_claude(fake, "--resume", SID)
    assert failed.result["total_cost_usd"] == pytest.approx(0.0092889) and failed.result["modelUsage"] == {}


def test_codex_usage_is_cumulative_for_a_thread_and_the_rollout_carries_the_turn(fake, tmp_path):
    home = tmp_path / "codex-home"
    fake.sequence("ok_structured", "ok_plain")
    first = ask_codex(fake, "-C", str(tmp_path), "--output-schema", str(FIXTURES / "handwritten" / "gh" / "repo.json"), env={"CODEX_HOME": str(home)})
    thread = first.events[0]["thread_id"]
    second = ask_codex(fake, resume=thread, env={"CODEX_HOME": str(home)})
    usage = lambda s: s.of_type("turn.completed")[0]["usage"]
    assert usage(first) == {"input_tokens": 12168, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 15, "reasoning_output_tokens": 0}
    assert usage(second) == {"input_tokens": 24342, "cached_input_tokens": 10368, "cache_write_input_tokens": 0, "output_tokens": 20, "reasoning_output_tokens": 0}
    rollout = list(home.glob("sessions/*/*/*/rollout-*-%s.jsonl" % thread))
    assert len(rollout) == 1
    every_line = [json.loads(l) for l in rollout[0].read_text().splitlines()]
    assert [l.get("type") for l in every_line] == ["session_meta", "event_msg", None, "event_msg", None]        # a reader has to pick the token counts out
    assert every_line[0]["payload"]["id"] == thread
    rows = [l["payload"] for l in every_line if l["payload"].get("type") == "token_count"]
    assert [r["info"]["last_token_usage"]["input_tokens"] for r in rows] == [12168, 12174]
    assert [r["info"]["total_token_usage"]["input_tokens"] for r in rows] == [12168, 24342]
    assert rows[1]["info"]["last_token_usage"]["cached_input_tokens"] == 10368 and rows[1]["info"]["last_token_usage"]["output_tokens"] == 5
    assert rows[1]["info"]["total_token_usage"]["total_tokens"] == 24362
    assert rows[1]["rate_limits"]["primary"]["window_minutes"] == 43200 and rows[1]["rate_limits"]["plan_type"] == "go"


def test_codex_ok_plain_as_a_first_turn_shows_its_own_turn_not_the_captured_cumulative(fake):
    fake.sequence("ok_plain")
    usage = ask_codex(fake).of_type("turn.completed")[0]["usage"]
    assert usage == {"input_tokens": 12174, "cached_input_tokens": 10368, "cache_write_input_tokens": 0, "output_tokens": 5, "reasoning_output_tokens": 0}


def test_codex_usage_override_is_this_turns_amount_and_adds_to_the_thread(fake):
    fake.usage(input_tokens=50, cached_input_tokens=20, output_tokens=3, reasoning_output_tokens=1)
    first, second = ask_codex(fake, resume=TID), ask_codex(fake, resume=TID)
    totals = lambda s: s.of_type("turn.completed")[0]["usage"]
    assert totals(first) == {"input_tokens": 50, "cached_input_tokens": 20, "cache_write_input_tokens": 0, "output_tokens": 3, "reasoning_output_tokens": 1}
    assert totals(second) == {"input_tokens": 100, "cached_input_tokens": 40, "cache_write_input_tokens": 0, "output_tokens": 6, "reasoning_output_tokens": 2}


def test_model_alias_and_full_name_are_reported_as_the_model(fake):
    seen = ask_claude(fake, "--model", "opus")
    assert seen.of_type("system")[0]["model"] == "claude-opus-5-5"
    assert list(seen.result["modelUsage"]) == ["claude-opus-5-5"] and seen.assistant["message"]["model"] == "claude-opus-5-5"
    seen = ask_claude(fake, "--model", "claude-haiku-9")
    assert list(seen.result["modelUsage"]) == ["claude-haiku-9"]
    seen = ask_claude(fake, "--model", "mystery")
    assert list(seen.result["modelUsage"]) == ["claude-sonnet-5-5"]
    assert ask_claude(fake, "--model", "sonnet").of_type("system")[0]["model"] == "claude-sonnet-5-5"


def test_claude_version_override_reaches_the_init_event(fake):
    assert ask_claude(fake, FAKE_CLAUDE_VERSION="9.9.9").of_type("system")[0]["claude_code_version"] == "9.9.9"
    assert ask_claude(fake).of_type("system")[0]["claude_code_version"] == "2.1.308"


# ------------------------------------------------------------------------------------------------ replies
def test_reply_json_replaces_every_place_a_structured_reply_lives(fake):
    obj = {"answer": "pong", "n": [1, 2]}
    fake.reply(json=obj)
    seen = ask_claude(fake, "--include-partial-messages", "--json-schema", SCHEMA)
    assert seen.result["structured_output"] == obj and json.loads(seen.result["result"]) == obj
    assert seen.result["result"] == json.dumps(obj, separators=(",", ":"))
    tool = seen.assistant["message"]["content"][0]
    assert tool["input"] == obj and list(seen.assistant["wire_tool_inputs"].values()) == [obj]
    pieces = [e["event"]["delta"]["partial_json"] for e in seen.of_type("stream_event") if e["event"].get("delta", {}).get("type") == "input_json_delta"]
    assert pieces[0] == "" and json.loads("".join(pieces)) == obj and len(pieces) == 3
    seen = ask_codex(fake, "--output-schema", str(FIXTURES / "handwritten" / "gh" / "repo.json"))
    assert json.loads(seen.of_type("item.completed")[0]["item"]["text"]) == obj


def test_reply_text_and_json_on_a_plain_scenario(fake):
    fake.reply(text="pong")
    seen = ask_claude(fake)
    assert seen.result["result"] == "pong" and text_of(seen) == "pong" and "structured_output" not in seen.result
    assert ask_codex(fake).of_type("item.completed")[0]["item"]["text"] == "pong"
    fake.reply(json={"a": 1})
    seen = ask_claude(fake)
    assert seen.result["result"] == '{"a":1}' and text_of(seen) == '{"a":1}'
    assert ask_codex(fake).of_type("item.completed")[0]["item"]["text"] == '{"a":1}'


def test_when_both_are_set_text_fills_text_fields_and_json_the_structured_ones(fake):
    fake.reply(json={"answer": "j"}, text="t")
    seen = ask_claude(fake, "--json-schema", SCHEMA)
    assert seen.result["structured_output"] == {"answer": "j"} and seen.result["result"] == "t"
    assert seen.assistant["message"]["content"][0]["input"] == {"answer": "j"}


def test_a_blank_reply_text_is_a_reply_and_an_unset_one_is_not(fake):
    fake.reply(text="")
    assert ask_claude(fake).result["result"] == ""
    fake.reply(text=None)
    assert ask_claude(fake).result["result"] == "ok"


def test_only_ok_scenarios_take_a_reply_error_scenarios_keep_their_own(fake):
    fake.reply(text="pong", json={"answer": "x"})
    for name in ("quota", "plain_not_json", "empty_reply", "structured_failed", "login_expired"):
        fake.sequence(name)
        seen = ask_claude(fake)
        assert "pong" not in seen.out, name
    fake.sequence("empty_reply")
    assert ask_claude(fake).result["result"] == ""
    fake.sequence("reply_not_json", "usage_limit", "empty_reply")
    for _ in range(3):
        assert "pong" not in ask_codex(fake).out
    fake.sequence("noise", "noise_lines")
    for name in ("noise", "noise_lines"):
        assert ask_claude(fake).result["result"] == "pong", name


def test_codex_reply_replaces_the_last_agent_message_only(fake):
    fake.sequence("unknown_item_type")
    fake.reply(text="pong")
    seen = ask_codex(fake)
    items = [e["item"] for e in seen.of_type("item.completed")]
    assert items[0]["type"] == "command_execution" and items[0]["command"] == "ls" and items[1]["text"] == "pong"


def test_a_bad_reply_json_or_usage_json_is_a_setup_error(fake):
    assert go(fake, "claude", "-p", "--output-format", "stream-json", "--verbose", stdin="x", FAKE_REPLY_JSON="{nope").code == 64
    seen = go(fake, "claude", "-p", "--output-format", "stream-json", "--verbose", stdin="x", FAKE_USAGE="[1")
    assert seen.code == 64 and "FAKE_USAGE is not valid JSON" in seen.err
    seen = go(fake, "claude", "-p", "--output-format", "stream-json", "--verbose", stdin="x", FAKE_USAGE="[1]")
    assert seen.code == 64 and "FAKE_USAGE must be a JSON object" in seen.err
    seen = go(fake, "claude", "-p", "--output-format", "stream-json", "--verbose", stdin="x", FAKE_PATCH="{}")
    assert seen.code == 64 and "FAKE_PATCH must be a JSON list" in seen.err
    seen = go(fake, "claude", "-p", "--output-format", "stream-json", "--verbose", stdin="x", FAKE_COST_USD="cheap")
    assert seen.code == 64 and "FAKE_COST_USD='cheap' is not a number" in seen.err


def test_patch_edits_the_lines_and_a_patch_that_matches_nothing_is_an_error(fake):
    patch = [{"match": {"type": "result"}, "set": {"is_error": True, "usage.output_tokens": 3}, "delete": ["stop_reason"]},
             {"match": {"type": "rate_limit_event"}, "set": {"rate_limit_info.status": "allowed_warning"}},
             {"match": {"type": "assistant", "message.content.0.type": "text"}, "set": {"message.content.0.text": "edited"}}]
    seen = ask_claude(fake, FAKE_PATCH=json.dumps(patch))
    assert seen.result["is_error"] is True and seen.result["usage"]["output_tokens"] == 3 and "stop_reason" not in seen.result
    assert seen.of_type("rate_limit_event")[0]["rate_limit_info"]["status"] == "allowed_warning" and seen.code == 1
    assert text_of(seen) == "edited"
    seen = ask_claude(fake, FAKE_PATCH=json.dumps([{"match": {"type": "nothing"}, "drop": True}]))
    assert seen.code == 64 and 'FAKE_PATCH: the edit {"type":"nothing"} matched no line' in seen.err
    seen = ask_claude(fake, FAKE_PATCH=json.dumps([{"match": {"type": "rate_limit_event"}, "drop": True}]))
    assert "rate_limit_event" not in seen.types and seen.code == 0
    seen = ask_claude(fake, FAKE_PATCH=json.dumps([{"match": {"type": "result"}, "set": {"no.such.parent": 1}}]))
    assert seen.code == 64 and "cannot set no.such.parent" in seen.err
    assert ask_claude(fake, FAKE_PATCH=json.dumps([{"match": {"type": "result"}, "delete": ["no.such.key"]}])).code == 0       # deleting what is not there is fine


def test_exit_code_override(fake):
    assert ask_claude(fake, FAKE_EXIT_CODE="7").code == 7
    assert ask_codex(fake, FAKE_EXIT_CODE="0").code == 0
    fake.sequence("quota")
    assert ask_claude(fake, FAKE_EXIT_CODE="0").code == 0


# ------------------------------------------------------------------------------------------------ partial messages
def test_without_the_partials_flag_there_are_no_stream_events_with_it_the_structured_ones_stay(fake):
    fake.sequence("ok_structured")
    assert not ask_claude(fake).of_type("stream_event")
    assert len(ask_claude(fake, "--include-partial-messages").of_type("stream_event")) == 8        # the captured stream has eight


def test_a_plain_reply_with_partials_gets_synthetic_events_in_the_real_order(fake):
    fake.reply(text="abcdefghi")
    seen = ask_claude(fake, "--include-partial-messages", "--session-id", SID)
    types = [e["event"]["type"] if e["type"] == "stream_event" else e["type"] for e in seen.events if e["type"] in ("stream_event", "assistant", "result")]
    assert types == ["message_start", "content_block_start", "content_block_delta", "content_block_delta", "content_block_delta", "assistant",
                     "content_block_stop", "message_delta", "message_stop", "result"]
    deltas = [e["event"]["delta"] for e in seen.of_type("stream_event") if e["event"]["type"] == "content_block_delta"]
    assert [d["type"] for d in deltas] == ["text_delta"] * 3 and "".join(d["text"] for d in deltas) == "abcdefghi"
    uuids = [e["uuid"] for e in seen.of_type("stream_event")]
    assert len(set(uuids)) == len(uuids) and all(e["session_id"] == SID for e in seen.of_type("stream_event"))
    assert seen.of_type("stream_event")[0]["event"]["message"]["usage"]["output_tokens"] == 4
    assert ask_claude(fake, "--session-id", SID).of_type("stream_event") == []


def test_partials_are_not_synthesised_for_errors_or_empty_text(fake):
    fake.sequence("quota", "empty_reply")
    assert ask_claude(fake, "--include-partial-messages").of_type("stream_event") == []
    seen = ask_claude(fake, "--include-partial-messages")
    kinds_seen = [e["event"]["type"] for e in seen.of_type("stream_event")]
    assert kinds_seen == ["message_start", "content_block_start", "content_block_stop", "message_delta", "message_stop"]


# ------------------------------------------------------------------------------------------------ the output formats and the argument checks of the fakes
def test_output_formats_text_json_and_stream_json(fake):
    seen = go(fake, "claude", "-p", "--output-format", "text", stdin="x")
    assert seen.out == "ok\n" and seen.code == 0
    seen = go(fake, "claude", "-p", "--output-format", "json", stdin="x")
    assert json.loads(seen.out)["result"] == "ok" and len(seen.out.splitlines()) == 1
    seen = go(fake, "claude", "-p", stdin="x")                                  # print mode prints text by default
    assert seen.out == "ok\n"
    fake.sequence("quota")
    seen = go(fake, "claude", "-p", "--output-format", "text", stdin="x")
    assert seen.code == 1 and "hit your limit" in seen.out
    seen = go(fake, "claude", "-p", "--output-format", "yaml", stdin="x")
    assert seen.code == 1 and "Allowed choices are text, json, stream-json" in seen.err and seen.out == ""


def test_claude_refuses_what_the_real_cli_refuses(fake, tmp_path):
    seen = go(fake, "claude", "-p", "--output-format", "stream-json", stdin="x")
    assert seen.code == 1 and "requires --verbose" in seen.err and seen.out == ""
    seen = ask_claude(fake, "--json-schema", "{not json")
    assert seen.code == 1 and "Error: --json-schema is not valid JSON: JSON Parse error" in seen.err and seen.out == ""
    seen = ask_claude(fake, "--system-prompt-file", str(tmp_path / "gone.txt"))
    assert seen.code == 1 and seen.err == "Error: System prompt file not found: %s\n" % (tmp_path / "gone.txt") and seen.out == ""
    present = tmp_path / "there.txt"
    present.write_text("be brief")
    assert ask_claude(fake, "--system-prompt-file", str(present)).code == 0
    assert all(c["scenario"] in ("(argument error)", "ok") for c in fake.model_calls())


def test_a_bad_effort_only_warns_and_the_call_goes_on(fake):
    seen = ask_claude(fake, "--effort", "turbo")
    assert seen.code == 0 and seen.result["result"] == "ok"
    assert seen.err == ("Warning: Unknown --effort value 'turbo' — ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.\n")
    assert ask_claude(fake, "--effort", "low").err == ""


def test_claude_print_flag_is_required_and_unknown_commands_are_refused_and_logged(fake):
    seen = go(fake, "claude", "chat")
    assert seen.code == 2 and "unsupported command chat" in seen.err
    seen = go(fake, "claude", "--output-format", "stream-json", "--verbose")
    assert seen.code == 2
    assert [c["op"] for c in fake.calls("claude")] == ["other", "other"]
    seen = go(fake, "codex", "apply")
    assert seen.code == 2 and "unsupported command apply" in seen.err
    seen = go(fake, "gh", "pr", "create")
    assert seen.code == 2 and "unsupported command pr create" in seen.err
    assert [c["op"] for c in fake.calls()][-2:] == ["other", "other"]


def test_codex_resume_takes_neither_sandbox_nor_cd_like_the_real_cli(fake, tmp_path):
    for flags, shown in ((["-s", "read-only"], "-s"), (["--sandbox", "read-only"], "-s"), (["-C", str(tmp_path)], "-C"), (["--cd", str(tmp_path)], "-C")):
        seen = ask_codex(fake, *flags, resume=TID)
        assert seen.code == 2 and seen.out == "" and ("error: unexpected argument '%s' found" % shown) in seen.err
        assert "Usage: codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]" in seen.err
    assert ask_codex(fake, "-c", 'sandbox_mode="read-only"', resume=TID).code == 0
    assert ask_codex(fake, "-s", "read-only", "-C", str(tmp_path)).code == 0                 # a fresh exec takes both


def test_codex_sandbox_value_is_checked(fake):
    seen = ask_codex(fake, "-s", "everything")
    assert seen.code == 2 and "invalid value 'everything' for '--sandbox <SANDBOX_MODE>'" in seen.err
    for mode in ("read-only", "workspace-write", "danger-full-access"):
        assert ask_codex(fake, "-s", mode).code == 0


def test_bad_flag_complains_about_the_first_long_option_or_the_one_named(fake):
    fake.sequence("bad_flag")
    seen = ask_claude(fake, "--model", "sonnet")
    assert seen.err == "error: unknown option '--output-format'\n" and seen.code == 1
    seen = ask_claude(fake, FAKE_BAD_FLAG="--turbo")
    assert seen.err == "error: unknown option '--turbo'\n"
    seen = go(fake, "claude", "-p", "hi", stdin="")
    assert seen.err == "error: unknown option '--no-such-flag'\n"
    seen = ask_codex(fake, FAKE_BAD_FLAG="--turbo")
    assert seen.code == 2 and "unexpected argument '--turbo' found" in seen.err and "tip: to pass '--turbo' as a value, use '-- --turbo'" in seen.err
    assert "--no-such-flag" not in seen.err


# ------------------------------------------------------------------------------------------------ status, help and version commands
def test_claude_auth_status_for_each_mode(fake):
    seen = go(fake, "claude", "auth", "status")
    doc = json.loads(seen.out)
    assert seen.code == 0 and doc["loggedIn"] is True and doc["authMethod"] == "claude.ai" and doc["subscriptionType"] == "max" and seen.err == ""
    assert seen.out == (FIXTURES / "claude" / "auth_status_signed_in.json").read_text()
    fake.auth(claude="signed_out")
    seen = go(fake, "claude", "auth", "status")
    assert seen.code == 1 and json.loads(seen.out) == {"loggedIn": False, "authMethod": "none", "apiProvider": "firstParty", "analyticsDisabled": False,
                                                       "projectsDirectory": "/scratch/probe/claude-empty-cfg/projects", "configDirectory": "/scratch/probe/claude-empty-cfg"}
    for mode in ("api_key", "console"):
        fake.auth(claude=mode)
        doc = json.loads(go(fake, "claude", "auth", "status").out)
        assert doc["loggedIn"] is True and doc["authMethod"] == mode and not {"email", "orgId", "orgName", "subscriptionType"} & set(doc)
    fake.auth(claude="error")
    seen = go(fake, "claude", "auth", "status")
    assert seen.code == 2 and seen.out == "" and "could not read" in seen.err
    fake.auth(claude="mystery")
    seen = go(fake, "claude", "auth", "status")
    assert seen.code == 64 and "FAKE_CLAUDE_AUTH='mystery'; use one of signed_in, signed_out, api_key, console, error" in seen.err


def test_codex_login_status_for_each_mode_prints_to_stderr(fake):
    seen = go(fake, "codex", "login", "status")
    assert (seen.code, seen.out, seen.err) == (0, "", "Logged in using ChatGPT\n")
    fake.auth(codex="signed_out")
    assert go(fake, "codex", "login", "status").err == "Not logged in\n" and go(fake, "codex", "login", "status").code == 1
    fake.auth(codex="api_key")
    seen = go(fake, "codex", "login", "status")
    assert seen.code == 0 and "API key" in seen.err and "ChatGPT" not in seen.err
    fake.auth(codex="error")
    assert go(fake, "codex", "login", "status").code == 2
    fake.auth(codex="console")
    assert go(fake, "codex", "login", "status").code == 64


def test_auth_from_config_follows_the_marker_file_of_the_config_directory(fake, tmp_path):
    cfg, home = tmp_path / "claude-cfg", tmp_path / "codex-home"
    cfg.mkdir()
    home.mkdir()
    extra = {"FAKE_AUTH_FROM_CONFIG": "1"}
    assert go(fake, "claude", "auth", "status", env={"CLAUDE_CONFIG_DIR": str(cfg)}, **extra).code == 1
    assert go(fake, "claude", "auth", "status", **extra).code == 1                           # no config directory at all
    (cfg / "fake-login").write_text("")
    assert go(fake, "claude", "auth", "status", env={"CLAUDE_CONFIG_DIR": str(cfg)}, **extra).code == 0
    assert go(fake, "codex", "login", "status", env={"CODEX_HOME": str(home)}, **extra).code == 1
    (home / "fake-login").write_text("")
    assert go(fake, "codex", "login", "status", env={"CODEX_HOME": str(home)}, **extra).code == 0
    fake.auth(codex="signed_out")                                                                  # without the switch the variable decides
    assert go(fake, "codex", "login", "status", env={"CODEX_HOME": str(home)}).code == 1
    seen = go(fake, "codex", "exec", "--json", "-", stdin="x", env={"CODEX_HOME": str(tmp_path / "other")}, **extra)
    assert "401" in seen.out                                                                       # empty config directory: the signed-out stream


def test_gh_auth_status_token_and_version(fake):
    seen = go(fake, "gh", "auth", "status")
    assert seen.code == 0 and seen.out.startswith("github.com\n") and "Token: gho_****" in seen.out and seen.err == ""
    fake.auth(gh="signed_out")
    seen = go(fake, "gh", "auth", "status")
    assert seen.code == 1 and seen.out == "" and "You are not logged into any GitHub hosts" in seen.err
    seen = go(fake, "gh", "auth", "token")
    assert seen.out == "gho_FAKE_TOKEN_DO_NOT_USE_0000000000000000\n"
    assert go(fake, "gh", "--version").out.splitlines()[0] == "gh version 2.87.3 (2026-02-23)"
    fake.auth(gh="api_key")
    assert go(fake, "gh", "auth", "status").code == 64


def test_version_overrides_and_the_default_versions_the_connectors_were_tested_with(fake):
    assert go(fake, "claude", "--version").out == "2.1.308 (Claude Code)\n" and go(fake, "claude", "-v").out == "2.1.308 (Claude Code)\n"
    assert go(fake, "codex", "--version").out == "codex-cli 0.146.0\n" and go(fake, "codex", "-V").out == "codex-cli 0.146.0\n"
    assert go(fake, "claude", "--version", FAKE_CLAUDE_VERSION="2.2.0").out == "2.2.0 (Claude Code)\n"
    assert go(fake, "codex", "--version", FAKE_CODEX_VERSION="0.150.1").out == "codex-cli 0.150.1\n"


def test_help_texts_are_the_captured_ones(fake):
    assert go(fake, "claude", "--help").out == (FIXTURES / "claude" / "help.txt").read_text()
    assert go(fake, "claude", "-h").out == (FIXTURES / "claude" / "help.txt").read_text()
    assert go(fake, "codex", "exec", "--help").out == (FIXTURES / "codex" / "exec_help.txt").read_text()
    assert go(fake, "codex", "exec", "resume", "--help").out == (FIXTURES / "codex" / "exec_resume_help.txt").read_text()
    top = go(fake, "codex", "--help").out
    assert top == (FIXTURES / "handwritten" / "codex_help.txt").read_text() and "exec" in top and "login" in top
    assert go(fake, "codex", "help").out == top


def test_help_missing_removes_an_option_block_and_nothing_else(fake):
    text = (FIXTURES / "claude" / "help.txt").read_text()
    out = go(fake, "claude", "--help", FAKE_HELP_MISSING="--json-schema,--include-partial-messages").out
    assert "--json-schema" not in out and "--include-partial-messages" not in out and "JSON Schema for structured output" not in out
    assert "--input-format" in out and "--max-budget-usd" in out and "--mcp-config" in out
    removed, kept = text.splitlines(), out.splitlines()
    assert len(removed) - len(kept) == 4 + 3 and set(kept) <= set(removed)                                 # the two option blocks, nothing else
    codex = go(fake, "codex", "exec", "--help", FAKE_HELP_MISSING="--output-schema").out
    assert "--output-schema" not in codex and "Path to a JSON Schema file" not in codex and "--json" in codex and "--ephemeral" in codex
    whole = (FIXTURES / "codex" / "exec_help.txt").read_text().splitlines()
    assert len(whole) - len(codex.splitlines()) == 3                                                   # the flag line, its text and the blank line after it
    codex = go(fake, "codex", "exec", "--help", FAKE_HELP_MISSING="--json").out
    assert "Print events to stdout as JSONL" not in codex and "--output-schema" in codex and "--skip-git-repo-check" in codex
    assert go(fake, "claude", "--help", FAKE_HELP_MISSING="--json").out == text                           # claude has --json-schema but no --json
    out = go(fake, "claude", "--help", FAKE_HELP_MISSING="--allowed-tools").out
    assert "--allowedTools" not in out
    assert "--allowedTools" in go(fake, "claude", "--help", FAKE_HELP_MISSING="--allowed").out


def test_models_come_from_the_captured_catalog(fake):
    doc = json.loads(go(fake, "codex", "debug", "models").out)
    listed = [m["slug"] for m in doc["models"] if m["visibility"] == "list"]
    assert listed == ["gpt-5.6-terra", "gpt-5.6-luna"] and {m["slug"] for m in doc["models"]} >= {"gpt-reserve", "codex-auto-review"}


def test_mcp_list_variants(fake):
    full = go(fake, "claude", "mcp", "list").out
    assert "claude.ai Gmail" in full and "Needs authentication" in full and "tools fetch failed" in full
    assert go(fake, "claude", "mcp", "list", FAKE_CLAUDE_MCP="local").out.count("claude.ai") == 0
    empty = go(fake, "claude", "mcp", "list", FAKE_CLAUDE_MCP="empty")
    assert empty.out == "No MCP servers configured.\n" and empty.code == 0
    assert go(fake, "claude", "mcp", "list", FAKE_CLAUDE_MCP="weird").code == 64
    assert go(fake, "codex", "mcp", "list", "--json").out == "[]\n"
    assert "No MCP servers" in go(fake, "codex", "mcp", "list").out


def test_forget_commands_are_accepted_silently_and_logged(fake):
    seen = go(fake, "claude", "purge", "-y", "/tmp/some-work-dir")
    assert (seen.code, seen.out, seen.err) == (0, "", "")
    seen = go(fake, "codex", "delete", TID)
    assert (seen.code, seen.out, seen.err) == (0, "", "")
    assert [(c["cli"], c["op"], c["argv"]) for c in fake.calls()] == [("claude", "purge", ["purge", "-y", "/tmp/some-work-dir"]), ("codex", "delete", ["delete", TID])]


# ------------------------------------------------------------------------------------------------ codex device sign-in
def test_device_auth_prints_the_captured_text_waits_and_finishes_on_approval(fake):
    fake.auth(codex="signed_out")
    proc = fake.popen("codex", "login", "--device-auth")
    first = proc.stdout.readline() + proc.stdout.readline()
    assert "Welcome to Codex" in first
    fake.wait_for(1, kind="probe")
    time.sleep(0.2)
    assert proc.poll() is None                                                   # still waiting for the code to be entered
    assert fake.run("codex", "login", "status").returncode == 1
    fake.approve_device_auth()
    rest, err = fake.finish(proc)
    out = first + rest
    assert proc.returncode == 0 and "https://auth.openai.com/codex/device" in out and "ABCD-EFGHJ" in out and out.rstrip().endswith("Successfully logged in")
    assert out.startswith((FIXTURES / "codex" / "login_device_auth.txt").read_text())
    status = fake.run("codex", "login", "status")
    assert status.returncode == 0 and "ChatGPT" in status.stderr
    assert json.loads((fake.state_dir / "auth.json").read_text()) == {"codex": "signed_in"}


def test_device_auth_can_complete_by_itself_or_give_up(fake):
    fake.auth(codex="signed_out")
    res = fake.run("codex", "login", "--device-auth", env=fake.process_env(FAKE_DEVICE_AUTH_SECONDS="0.2"), timeout=20)
    assert res.returncode == 0 and "ABCD-EFGHJ" in res.stdout and res.stdout.rstrip().endswith("Successfully logged in")
    assert fake.run("codex", "login", "status").returncode == 0
    fake2_state = fake.state_dir / "other"
    res = fake.run("codex", "login", "--device-auth", env=fake.process_env(FAKE_MAX_SECONDS="0.3", FAKE_CLI_STATE=str(fake2_state)), timeout=20)
    assert res.returncode == 124 and "Successfully" not in res.stdout


def test_device_auth_ends_on_sigterm_like_a_killed_codex(fake):
    proc = fake.popen("codex", "login", "--device-auth")
    proc.stdout.readline()
    proc.send_signal(signal.SIGTERM)
    fake.finish(proc)
    assert proc.returncode == -signal.SIGTERM


# ------------------------------------------------------------------------------------------------ the call log
def test_every_invocation_is_logged_with_what_the_connector_tests_assert_on(fake, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "marker.txt").write_text("")
    res = fake.run("claude", "-p", "--output-format", "stream-json", "--verbose", "--tools", "", input="the prompt é中", cwd=work)
    assert res.returncode == 0
    call = fake.calls()[0]
    assert call["n"] == 1 and call["cli"] == "claude" and call["kind"] == "call" and call["op"] == "print" and call["scenario"] == "ok"
    assert call["argv"] == ["-p", "--output-format", "stream-json", "--verbose", "--tools", ""]
    assert call["stdin"] == "the prompt é中" and call["stdin_complete"] is True
    assert os.path.realpath(call["cwd"]) == os.path.realpath(str(work)) and call["cwd_entries"] == ["marker.txt"]
    assert call["exit"] == 0 and call["t_end"] >= call["t_start"] and call["signal"] is None and call["pid"] > 0
    assert call["session_id"] == "00000000-0000-4000-8000-000000000001"


def test_the_log_records_the_environment_names_without_the_artefacts_of_the_shell_and_python(fake):
    env = fake.process_env(ANTHROPIC_API_KEY="sk-test", CLAUDE_CODE_FOO="1", SUTRA_TOKEN="t", FAKE_LOG_ENV="HOME,NOT_SET,SUTRA_TOKEN")
    fake.run("claude", "-p", "--output-format", "stream-json", "--verbose", input="x", env=env)
    call = fake.calls()[0]
    assert {"PATH", "HOME", "ANTHROPIC_API_KEY", "CLAUDE_CODE_FOO", "SUTRA_TOKEN", "FAKE_CLI_STATE"} <= set(call["env_keys"])
    assert not {"PWD", "SHLVL", "_", "OLDPWD", "__CF_USER_TEXT_ENCODING"} & set(call["env_keys"])
    assert "LC_CTYPE" not in call["env_keys"]                                    # LANG is set in process_env, so LC_CTYPE would be a real variable
    assert call["env_values"] == {"HOME": env["HOME"], "SUTRA_TOKEN": "t"}
    assert call["env_keys"] == sorted(call["env_keys"])
    inproc = go(fake, "claude", "--version", env={"PWD": "/x", "SHLVL": "2", "_": "/y", "OLDPWD": "/z", "LANG": None}, LC_CTYPE="UTF-8")
    assert inproc.code == 0
    keys = fake.calls()[-1]["env_keys"]
    assert not {"PWD", "SHLVL", "_", "OLDPWD", "LC_CTYPE"} & set(keys)
    go(fake, "claude", "--version", LC_CTYPE="UTF-8")
    assert "LC_CTYPE" in fake.calls()[-1]["env_keys"]
    go(fake, "claude", "--version", env={"LANG": None, "LC_ALL": "C"}, LC_CTYPE="UTF-8")
    assert "LC_CTYPE" in fake.calls()[-1]["env_keys"]


def test_the_log_lists_the_working_directory_sorted_and_capped_at_fifty(fake, tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    for name in ("b.txt", "a.txt", "c.txt"):
        (work / name).write_text("")
    ask_claude(fake, cwd=work)
    assert fake.calls()[0]["cwd_entries"] == ["a.txt", "b.txt", "c.txt"]
    for n in range(60):
        (work / ("f%02d" % n)).write_text("")
    ask_claude(fake, cwd=work)
    entries = fake.calls()[1]["cwd_entries"]
    assert len(entries) == 50 and entries == sorted(entries) and entries[0] == "a.txt"
    ask_claude(fake, cwd=tmp_path / "gone")
    assert fake.calls()[2]["cwd_entries"] is None


def test_the_log_captures_files_the_connector_deletes_after_the_call(fake, tmp_path):
    schema, prompt, mcp, image = tmp_path / "s.json", tmp_path / "p.txt", tmp_path / "m.json", tmp_path / "i.png"
    schema.write_text('{"type":"object"}')
    prompt.write_text("system text")
    prompt.chmod(0o600)
    mcp.write_text('{"mcpServers":{}}')
    image.write_bytes(b"not really a png")
    ask_claude(fake, "--system-prompt-file", str(prompt), "--mcp-config", str(mcp), "--mcp-config", '{"mcpServers":{"a":{}}}')
    ask_codex(fake, "--output-schema", str(schema), "-i", str(image), "-i", str(tmp_path / "gone.png"))
    claude_call, codex_call = fake.model_calls()
    files = claude_call["files"]
    assert files["--system-prompt-file"] == [{"path": str(prompt), "exists": True, "mode": "0600", "size": 11, "content": "system text"}]
    assert files["--mcp-config"][0]["content"] == '{"mcpServers":{}}' and files["--mcp-config"][1] == {"inline": True, "content": '{"mcpServers":{"a":{}}}'}
    assert codex_call["files"]["--output-schema"][0]["content"] == '{"type":"object"}'
    assert codex_call["files"]["--image"][0] == {"path": str(image), "exists": True, "mode": "%04o" % (image.stat().st_mode & 0o7777), "size": 16}
    assert codex_call["files"]["--image"][1] == {"path": str(tmp_path / "gone.png"), "exists": False}


def test_stdin_is_captured_whole_even_when_it_is_a_megabyte(fake):
    prompt = "x" * 1_000_000
    proc = fake.popen("claude", "-p", "--output-format", "stream-json", "--verbose")
    out, err = proc.communicate(prompt, timeout=60)
    assert proc.returncode == 0
    call = fake.calls()[0]
    assert call["stdin"] == prompt and call["stdin_complete"] is True


def test_a_caller_that_never_closes_stdin_is_noticed_without_hanging(fake):
    proc = fake.popen("claude", "-p", "--output-format", "stream-json", "--verbose", env=fake.process_env(FAKE_STDIN_TIMEOUT="0.4"))
    proc.stdin.write("partial prompt")
    proc.stdin.flush()
    call = fake.wait_for(1, timeout=10)[0]
    assert call["stdin"] == "partial prompt" and call["stdin_complete"] is False
    out, err = fake.finish(proc)                                                 # the fake went on with what it had
    assert proc.returncode == 0 and '"type":"result"' in out


def test_visible_env_keys_leaves_out_the_names_that_drive_the_fake(fake):
    env = fake.process_env(ANTHROPIC_API_KEY="k")
    fake.run("claude", "--version", env=env)
    keys = fake.visible_env_keys(fake.calls()[0])
    assert keys == {"PATH", "HOME", "LANG", "ANTHROPIC_API_KEY"} and "FAKE_CLI_STATE" in fake.calls()[0]["env_keys"]


def test_calls_merges_the_exit_records_and_filters(fake):
    go(fake, "claude", "auth", "status")
    ask_claude(fake)
    ask_codex(fake)
    go(fake, "codex", "login", "status")
    assert [c["n"] for c in fake.calls()] == [1, 2, 3, 4]
    assert [c["n"] for c in fake.calls("claude")] == [1, 2] and [c["n"] for c in fake.calls(kind="call")] == [2, 3]
    assert [c["n"] for c in fake.calls(op="login_status")] == [4] and [c["n"] for c in fake.model_calls("codex")] == [3]
    assert fake.last_call("claude")["n"] == 2 and fake.last_call(kind="call")["n"] == 3 and fake.last_call("gh") is None
    assert [c["exit"] for c in fake.calls()] == [0, 0, 0, 0]
    ask_claude(fake, FAKE_EXIT_CODE="9")
    assert fake.calls()[-1]["exit"] == 9


def test_wait_for_times_out_with_the_log_in_the_message(fake):
    ask_claude(fake)
    with pytest.raises(AssertionError, match="expected 2 logged invocations, saw 1"):
        fake.wait_for(2, timeout=0.2)
    assert len(fake.wait_for(1, timeout=0.2)) == 1


def test_the_state_lock_excludes_a_second_holder_and_stateless_runs_need_none(tmp_path):
    events = []

    def holder():
        with fake_cli.State(tmp_path / "s").locked():
            events.append("a-in")
            time.sleep(0.3)
            events.append("a-out")

    thread = threading.Thread(target=holder)
    thread.start()
    time.sleep(0.1)
    with fake_cli.State(tmp_path / "s").locked():
        events.append("b-in")
    thread.join()
    assert events == ["a-in", "a-out", "b-in"]
    with fake_cli.State(None).locked():
        assert fake_cli.State(None).bump("n") == 0 and fake_cli.State(None).read("x", 5) == 5


def test_parallel_invocations_are_all_logged_and_each_takes_its_own_sequence_slot(fake):
    names = ["quota", "overloaded", "ok_plain", "server_error", "billing_error", "login_expired"]
    fake.sequence(*names)
    procs = [fake.popen("claude", "-p", "--output-format", "stream-json", "--verbose") for _ in names]
    for proc in procs:
        proc.communicate("x", timeout=60)
    calls = fake.model_calls()
    assert sorted(c["n"] for c in calls) == [1, 2, 3, 4, 5, 6]
    assert sorted(c["scenario"] for c in calls) == sorted(names)                    # no slot used twice, none skipped
    assert len({c["session_id"] for c in calls}) == 6 and all(c["exit"] is not None for c in calls)
    assert json.loads((fake.state_dir / "counters.json").read_text())["seq:shared"] == 6


def test_parallel_resumes_of_one_session_add_up_exactly(fake):
    procs = [fake.popen("codex", "exec", "resume", "--json", TID, "-") for _ in range(16)]
    for proc in procs:
        proc.communicate("x", timeout=60)
    assert fake.sessions()["codex:" + TID]["turns"] == 16
    assert fake.sessions()["codex:" + TID]["usage"]["input_tokens"] == 12174 * 16
    assert sorted(c["n"] for c in fake.model_calls()) == list(range(1, 17))              # no number handed out twice
    assert len(fake.calls()) == 16 and all(c["exit"] == 0 for c in fake.calls())


# ------------------------------------------------------------------------------------------------ behaviours that need a process
def read_events(proc, count, timeout=10):
    """The first `count` stdout lines of a running fake with the time each arrived."""
    out, deadline = [], time.time() + timeout
    while len(out) < count and time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        out.append((time.time(), line.rstrip("\n")))
    return out


def start_hung(fake, cli, scenario="hang", **env):
    """A claude or codex call in the background with its prompt delivered."""
    fake.sequence(scenario)
    args = ("-p", "--output-format", "stream-json", "--verbose") if cli == "claude" else ("exec", "--json", "-")
    proc = fake.popen(cli, *args, env=fake.process_env(**env))
    fake.feed(proc, "x")
    return proc


@pytest.mark.parametrize(("cli", "opening"), [("claude", 1), ("codex", 2)])
def test_hang_prints_the_opening_lines_then_stays_silent_until_signalled(fake, cli, opening):
    proc = start_hung(fake, cli)
    lines = read_events(proc, opening)
    assert len(lines) == opening and json.loads(lines[0][1])["type"] in ("system", "thread.started")
    time.sleep(0.4)
    assert proc.poll() is None
    proc.send_signal(signal.SIGINT)
    rest, err = fake.finish(proc)
    assert rest == "" and proc.returncode == (0 if cli == "claude" else 130)
    assert fake.model_calls(cli)[0]["exit"] == proc.returncode and fake.model_calls(cli)[0]["signal"] == "SIGINT"


@pytest.mark.parametrize(("cli", "code"), [("claude", 143), ("codex", -signal.SIGTERM)])
def test_hang_ends_on_sigterm_with_the_exit_status_each_cli_showed(fake, cli, code):
    proc = start_hung(fake, cli)
    assert read_events(proc, 1)
    proc.send_signal(signal.SIGTERM)
    fake.finish(proc)
    assert proc.returncode == code
    assert fake.model_calls(cli)[0]["exit"] == code and fake.model_calls(cli)[0]["signal"] == "SIGTERM"


def test_a_fake_can_ignore_sigint_or_both_signals_so_the_cancel_ladder_has_work_to_do(fake):
    proc = start_hung(fake, "claude", FAKE_IGNORE_SIGINT="1")
    assert read_events(proc, 1)
    proc.send_signal(signal.SIGINT)
    time.sleep(0.2)
    assert proc.poll() is None                                                   # SIGINT is ignored ...
    proc.send_signal(signal.SIGTERM)
    fake.finish(proc)
    assert proc.returncode == 143                                                # ... SIGTERM is not
    proc = start_hung(fake, "claude", FAKE_IGNORE_SIGINT="1", FAKE_IGNORE_SIGTERM="1")
    assert read_events(proc, 1)
    proc.send_signal(signal.SIGINT)
    proc.send_signal(signal.SIGTERM)
    time.sleep(0.2)
    assert proc.poll() is None
    proc.kill()
    fake.finish(proc)
    assert proc.returncode == -signal.SIGKILL


def test_hang_gives_up_after_max_seconds_and_hang_silent_prints_nothing(fake):
    fake.sequence("hang_silent")
    res = fake.run("claude", "-p", "--output-format", "stream-json", "--verbose", input="x", env=fake.process_env(FAKE_MAX_SECONDS="0.2"), timeout=20)
    assert res.returncode == 124 and res.stdout == ""
    fake.sequence("hang")
    res = fake.run("codex", "exec", "--json", "-", input="x", env=fake.process_env(FAKE_MAX_SECONDS="0.2"), timeout=20)
    assert res.returncode == 124 and len(res.stdout.splitlines()) == 2


def test_slow_prints_a_line_every_third_of_a_second_and_then_finishes(fake):
    started = time.time()
    proc = start_hung(fake, "claude", "slow")
    lines = read_events(proc, 4)
    assert [json.loads(l)["type"] for _, l in lines] == ["system", "assistant", "rate_limit_event", "result"]
    # the first line is immediate and three more follow 0.3 s apart: the last cannot arrive earlier than 0.9 s after the start
    # (a reader that is late for one line makes a single gap meaningless, so only the total is checked)
    assert lines[3][0] - started >= 0.85 and lines[3][0] - lines[0][0] >= 0.5 and lines[3][0] - started < 20
    fake.finish(proc)
    assert proc.returncode == 0
    res = fake.run("codex", "exec", "--json", "-", input="x", env=fake.process_env(FAKE_CLI_SEQUENCE="slow", FAKE_LINE_DELAY="0.05"))
    assert len(res.stdout.splitlines()) == 4 and res.returncode == 0


def test_slow_can_be_stopped_midway_like_a_cancelled_call(fake):
    proc = start_hung(fake, "claude", "slow")
    assert read_events(proc, 1)
    proc.send_signal(signal.SIGINT)
    out, err = fake.finish(proc)
    assert proc.returncode == 0 and '"type":"result"' not in out


def test_slow401_shows_two_401_errors_half_a_second_apart_and_keeps_going(fake):
    started = time.time()
    proc = start_hung(fake, "codex", "slow401")
    lines = read_events(proc, 4)
    assert [json.loads(l)["type"] for _, l in lines] == ["thread.started", "turn.started", "error", "error"]
    assert all("401" in json.loads(l)["message"] for _, l in lines[2:])
    assert lines[3][0] - started >= 0.5                                          # the second 401 comes half a second after the first, which is immediate
    time.sleep(0.2)
    assert proc.poll() is None                                                   # it would go on for about six more seconds
    proc.kill()
    fake.finish(proc)


def test_crash_and_truncated_streams_end_without_a_terminal_event(fake):
    fake.sequence("crash")
    assert (ask_claude(fake).code, ask_codex(fake).code) == (137, 137)
    fake.sequence("truncated_exit0")
    assert (ask_claude(fake).code, ask_codex(fake).code) == (0, 0)
    res = fake.run("claude", "-p", "--output-format", "stream-json", "--verbose", input="x", env=fake.process_env(FAKE_CLI_SEQUENCE="crash"))
    assert res.returncode == 137 and res.stdout.count("\n") == 2


def test_noise_injects_a_non_json_line_and_a_blank_line_after_the_first_event(fake):
    fake.sequence("noise")
    seen = ask_claude(fake)
    assert seen.lines[1:3] == ["Warning: something printed to stdout that is not an event", ""] and seen.result["result"] == "ok"
    want = fixture_lines("derived/claude_noise_lines.jsonl")
    assert seen.lines[1:3] == want[1:3] and len(seen.lines) == len(want)
    seen = ask_codex(fake)
    assert seen.lines[1:3] == list(fake_cli.NOISE_LINES) and seen.lines[0]["type"] == "thread.started" and seen.lines[3]["type"] == "turn.started" and seen.code == 0


def test_control_interrupt_answers_with_the_request_id_it_was_sent(fake):
    fake.sequence("control_interrupt")
    request = json.dumps({"type": "control_request", "request_id": "req_42", "request": {"subtype": "interrupt"}}) + "\n"
    seen = go(fake, "claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", stdin=request)
    assert seen.code == 0 and seen.events == [{"type": "control_response", "response": {"subtype": "success", "request_id": "req_42", "response": {"still_queued": []}}}]
    fake.sequence("control_interrupt")
    seen = ask_claude(fake, stdin="not a control request")
    assert seen.events[0]["response"]["request_id"] == "req_1"


def test_a_closed_pipe_ends_the_fake_quietly(fake):
    fake.sequence("slow")
    proc = fake.popen("claude", "-p", "--output-format", "stream-json", "--verbose", env=fake.process_env(FAKE_LINE_DELAY="0.5"))
    fake.feed(proc, "x")
    assert read_events(proc, 1)
    proc.stdout.close()
    err = proc.stderr.read()
    proc.wait(timeout=10)
    assert proc.returncode == 141 and err == ""
    assert fake.model_calls()[0]["exit"] == 141


# ------------------------------------------------------------------------------------------------ gh
def api(fake, endpoint, *flags, **kw):
    return go(fake, "gh", "api", "-X", "GET", endpoint, *flags, **kw)


def test_gh_api_serves_the_five_read_endpoints_with_the_names_filled_in(fake):
    repo = json.loads(api(fake, "repos/octo-org/hello-world").out)
    assert repo["full_name"] == "octo-org/hello-world" and repo["name"] == "hello-world" and repo["owner"]["login"] == "octo-org" and repo["default_branch"] == "main"
    pulls = json.loads(api(fake, "repos/octo-org/hello-world/pulls").out)
    assert [p["number"] for p in pulls] == [2] and pulls[0]["state"] == "open" and pulls[0]["html_url"].startswith("https://github.com/octo-org/hello-world/")
    assert [p["number"] for p in json.loads(api(fake, "repos/octo-org/hello-world/pulls?state=all").out)] == [2, 1]
    assert [p["number"] for p in json.loads(api(fake, "repos/octo-org/hello-world/pulls?state=closed&per_page=1").out)] == [1]
    assert json.loads(api(fake, "repos/octo-org/hello-world/pulls?state=all&per_page=1&page=2").out)[0]["number"] == 1
    assert json.loads(api(fake, "repos/octo-org/hello-world/pulls/1").out)["merged_at"]
    issue = json.loads(api(fake, "repos/octo-org/hello-world/issues/3").out)
    assert issue["number"] == 3 and "IGNORE ALL PREVIOUS INSTRUCTIONS" in issue["body"] and "__OWNER__" not in json.dumps(issue)
    assert [i["number"] for i in json.loads(api(fake, "repos/octo-org/hello-world/issues?state=all").out)] == [3, 4]
    assert api(fake, "repos/octo-org/hello-world/pulls/99").code == 1


def test_gh_api_file_contents_as_json_and_raw_directories_and_the_big_file(fake):
    doc = json.loads(api(fake, "repos/octo-org/hello-world/contents/README.md?ref=dev").out)
    text = base64.b64decode(doc["content"]).decode()
    assert text.startswith("# hello-world\n") and doc["encoding"] == "base64" and doc["size"] == len(text.encode()) and doc["path"] == "README.md"
    assert all(len(l) <= 60 for l in doc["content"].splitlines()) and doc["content"].endswith("\n")
    assert doc["sha"] == hashlib.sha1(b"blob %d\0" % len(text.encode()) + text.encode()).hexdigest()
    assert doc["url"].endswith("?ref=dev") and "/blob/dev/README.md" in doc["html_url"]
    raw = api(fake, "repos/octo-org/hello-world/contents/src/app.py", "-H", "Accept: application/vnd.github.raw+json")
    assert raw.out.startswith("def main():") and raw.code == 0
    root = json.loads(api(fake, "repos/octo-org/hello-world/contents").out)
    assert {(e["name"], e["type"]) for e in root} == {("README.md", "file"), ("big.txt", "file"), ("docs", "dir"), ("src", "dir")}
    assert [e["path"] for e in json.loads(api(fake, "repos/octo-org/hello-world/contents/docs").out)] == ["docs/guide.md"]
    big = api(fake, "repos/octo-org/hello-world/contents/big.txt", "-H", "Accept: application/vnd.github.raw")
    assert len(big.out) == 60000
    assert len(api(fake, "repos/octo-org/hello-world/contents/big.txt", "-H", "Accept: application/vnd.github.raw", FAKE_GH_BIG_BYTES="30000").out) == 30000
    assert api(fake, "repos/octo-org/hello-world/contents/nope.txt").code == 1
    assert api(fake, "repos/octo-org/hello-world/contents/docs/../README.md").code == 1


def test_gh_api_accepts_a_leading_slash_a_query_in_the_endpoint_and_get_fields(fake):
    assert json.loads(api(fake, "/repos/octo-org/hello-world").out)["name"] == "hello-world"
    assert json.loads(api(fake, "repos/octo-org/hello-world/pulls", "-f", "state=closed").out)[0]["number"] == 1
    assert json.loads(api(fake, "repos/OCTO-ORG/Hello-World").out)["full_name"] == "OCTO-ORG/Hello-World"


def test_gh_api_failures_print_the_body_to_stdout_and_gh_s_line_to_stderr(fake):
    seen = api(fake, "repos/someone/else")
    assert seen.code == 1 and json.loads(seen.out)["message"] == "Not Found" and seen.err == "gh: Not Found (HTTP 404)\n"
    for kind, line in (("rate_limit", "gh: API rate limit exceeded for user ID 1. (HTTP 403)\n"), ("not_found", "gh: Not Found (HTTP 404)\n"),
                       ("server_error", "gh: Server Error (HTTP 502)\n"), ("unauthorized", "gh: Bad credentials (HTTP 401)\ntry authenticating with:  gh auth login\n")):
        seen = api(fake, "repos/octo-org/hello-world", FAKE_GH_FAIL=kind)
        assert seen.code == 1 and seen.err == line and json.loads(seen.out)["message"]
    seen = api(fake, "repos/octo-org/hello-world", FAKE_GH_FAIL="network")
    assert seen.code == 1 and seen.out == "" and "error connecting to api.github.com" in seen.err
    assert api(fake, "repos/octo-org/hello-world", FAKE_GH_FAIL="meteor").code == 64
    assert api(fake, "repos/acme/widgets", FAKE_GH_REPOS="acme/widgets,octo-org/hello-world").code == 0
    assert api(fake, "repos/octo-org/hello-world", FAKE_GH_REPOS="acme/widgets").code == 1


def test_gh_api_is_read_only_and_refuses_what_it_cannot_serve(fake):
    seen = go(fake, "gh", "api", "-X", "POST", "repos/octo-org/hello-world/issues", "-f", "title=x")
    assert seen.code == 1 and seen.out == "" and "only GET is served (read-only); got POST" in seen.err
    seen = go(fake, "gh", "api", "repos/octo-org/hello-world", "-f", "a=b")                   # gh itself turns fields into a POST without -X GET
    assert seen.code == 1 and "got POST" in seen.err
    seen = go(fake, "gh", "api", "--method", "DELETE", "repos/octo-org/hello-world")
    assert "got DELETE" in seen.err
    for flag in (("--jq", ".name"), ("-q", ".name"), ("--template", "{{.name}}"), ("--input", "-")):
        seen = api(fake, "repos/octo-org/hello-world", *flag)
        assert seen.code == 2 and "is not supported by the fake" in seen.err
    fake.auth(gh="signed_out")
    seen = api(fake, "repos/octo-org/hello-world")
    assert seen.code == 4 and "gh auth login" in seen.err and seen.out == ""
    calls = [c for c in fake.calls("gh") if c["op"] == "api"]
    assert [(c["method"], c["endpoint"]) for c in calls][:3] == [("POST", "repos/octo-org/hello-world/issues"), ("POST", "repos/octo-org/hello-world"), ("DELETE", "repos/octo-org/hello-world")]


def test_gh_log_records_the_environment_so_a_leaked_token_is_visible(fake):
    fake.run("gh", "api", "-X", "GET", "repos/octo-org/hello-world", env=fake.process_env(GITHUB_TOKEN="ghp_x", GH_TOKEN="ghp_y"))
    call = fake.calls("gh")[0]
    assert {"GITHUB_TOKEN", "GH_TOKEN"} <= set(call["env_keys"]) and call["kind"] == "probe" and call["op"] == "api"
    fake.run("gh", "api", "-X", "GET", "repos/octo-org/hello-world")
    assert "GITHUB_TOKEN" not in fake.calls("gh")[1]["env_keys"]


# ------------------------------------------------------------------------------------------------ rollout files
def test_rollout_goes_to_codex_home_or_the_state_directory_and_never_for_an_ephemeral_call(fake, tmp_path):
    home = tmp_path / "home"
    seen = ask_codex(fake, "--ephemeral", env={"CODEX_HOME": str(home)})
    assert seen.code == 0 and not home.exists() and fake.model_calls()[0]["session_id"] and "rollout" not in fake.model_calls()[0]
    seen = ask_codex(fake)                                                      # no CODEX_HOME: the state directory
    thread = seen.events[0]["thread_id"]
    files = list((fake.state_dir / "codex_home").glob("sessions/*/*/*/rollout-*-%s.jsonl" % thread))
    assert len(files) == 1 and re.match(r"rollout-\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-" + thread, files[0].name)
    assert fake.model_calls()[1]["rollout"] == str(files[0])
    written = [json.loads(l) for l in files[0].read_text().splitlines()]
    assert [l.get("type") for l in written] == ["session_meta", "event_msg", None] and written[2]["payload"]["type"] == "token_count"


def test_rollout_can_be_switched_off_or_corrupted_and_a_failed_turn_has_none(fake, tmp_path):
    home = tmp_path / "home"
    ask_codex(fake, env={"CODEX_HOME": str(home), "FAKE_CODEX_ROLLOUT": "off"})
    assert not home.exists() and fake.model_calls()[0]["rollout"] == "off"
    seen = ask_codex(fake, env={"CODEX_HOME": str(home), "FAKE_CODEX_ROLLOUT": "bad"})
    (path,) = home.glob("sessions/*/*/*/rollout-*.jsonl")
    assert path.read_text() == "this is not json\n"
    fake.sequence("usage_limit")
    ask_codex(fake, env={"CODEX_HOME": str(tmp_path / "other")})
    assert not (tmp_path / "other").exists()


def test_rollout_never_goes_into_the_real_codex_home(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()
    seen = ask_codex(fake, env={"CODEX_HOME": str(tmp_path / ".codex")})
    assert seen.code == 0 and list((tmp_path / ".codex").iterdir()) == []
    assert fake.model_calls()[0]["rollout"] == "skipped: CODEX_HOME is the real ~/.codex"
    environ = {k: v for k, v in fake.process_env().items() if k != "FAKE_CLI_STATE"}
    out = io.StringIO()
    fake_cli.Run("codex", ["exec", "--json", "-"], env=environ, stdin=b"x", stdout=out, stderr=io.StringIO()).run()
    assert "turn.completed" in out.getvalue()                                      # stateless and no CODEX_HOME: nowhere to write, and no failure


# ------------------------------------------------------------------------------------------------ the pytest harness (conftest.py)
def test_the_handle_builds_the_fake_environment_and_the_connector_configuration(fake, tmp_path):
    env = fake.sequence("quota", "ok_plain").auth(claude="signed_out").reply(json={"a": 1}).cost(0.25).usage(input_tokens=3).set(FAKE_LINE_DELAY=0.1).env()
    assert env["FAKE_CLI_SEQUENCE"] == "quota,ok_plain" and env["FAKE_CLAUDE_AUTH"] == "signed_out" and env["FAKE_REPLY_JSON"] == '{"a": 1}'
    assert env["FAKE_COST_USD"] == "0.25" and json.loads(env["FAKE_USAGE"]) == {"input_tokens": 3} and env["FAKE_LINE_DELAY"] == "0.1"
    assert env["FAKE_CLI_STATE"] == str(fake.state_dir) and env["FAKE_PYTHON"] == sys.executable == env["SUTRA_FAKE_PYTHON"]
    assert "FAKE_CODEX_AUTH" not in env and env["FAKE_MAX_SECONDS"] == "20"
    fake.set(FAKE_LINE_DELAY=None)
    assert "FAKE_LINE_DELAY" not in fake.env() and fake.env(FAKE_X=5)["FAKE_X"] == "5"
    fake.sequence("hang", cli="codex")
    assert fake.env()["FAKE_CODEX_SEQUENCE"] == "hang"
    kw = fake.config_kwargs(tmp_path)
    assert kw["claude_exe"] == str(FAKES / "claude") and kw["codex_exe"] == str(FAKES / "codex") and kw["gh_exe"] == str(FAKES / "gh")
    assert kw["data_dir"] == tmp_path / "data" and kw["work_root"] == tmp_path / "work" and kw["python"] == sys.executable
    assert kw["extra_env"] == {k: v for k, v in fake.env().items() if k != "SUTRA_FAKE_PYTHON"} and "FAKE_PYTHON" in kw["extra_env"]
    assert fake.config_kwargs()["data_dir"] == fake.root / "data"
    with pytest.raises(KeyError):
        fake.exe("rm")


def test_no_fake_variable_name_looks_like_a_secret():
    source = (FAKES / "fake_cli.py").read_text() + (ROOT / "tests" / "connectors" / "conftest.py").read_text()
    names = set(re.findall(r"\b(?:FAKE|SUTRA_FAKE)_[A-Z0-9_]+\b", source))
    assert {"FAKE_CLI_STATE", "FAKE_CLI_SEQUENCE", "FAKE_REPLY_JSON", "FAKE_USAGE", "FAKE_COST_USD", "FAKE_GH_FAIL"} <= names
    assert not [n for n in names if re.search(r"KEY|TOKEN|SECRET|PASSWORD", n)]


def test_bin_dir_puts_the_three_fakes_on_path_and_they_run(fake):
    bin_dir = fake.bin_dir
    assert fake.bin_dir == bin_dir
    for name in ("claude", "codex", "gh"):
        assert shutil.which(name, path=bin_dir) == str(Path(bin_dir) / name)
    env = fake.process_env()
    env["PATH"] = bin_dir + os.pathsep + env["PATH"]
    out = subprocess.run("claude --version && codex --version && gh --version", shell=True, env=env, capture_output=True, text=True)
    assert out.returncode == 0 and "2.1.308" in out.stdout and "codex-cli" in out.stdout and "gh version" in out.stdout


def test_run_gives_the_child_an_empty_stdin_and_popen_children_are_killed_at_teardown(fake, monkeypatch):
    seen = []
    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: seen.append(kw) or real_run(*a, **kw))
    res = fake.run("claude", "-p", "--output-format", "stream-json", "--verbose")
    assert res.returncode == 0 and fake.model_calls()[0]["stdin"] == ""
    assert seen[0]["input"] == "" and seen[0]["timeout"] == 60                  # never our own stdin
    proc = start_hung(fake, "claude")
    assert read_events(proc, 1) and proc.poll() is None
    fake.close()
    assert proc.poll() == -signal.SIGKILL


def test_finish_kills_a_process_that_does_not_end_in_time(fake):
    proc = start_hung(fake, "claude")
    assert read_events(proc, 1)
    started = time.time()
    out, err = fake.finish(proc, timeout=0.3)
    assert proc.returncode == -signal.SIGKILL and time.time() - started < 10 and out == ""


def test_fixtures_lines_keeps_anything_that_is_not_a_json_object_as_text(fixtures, monkeypatch):
    monkeypatch.setattr(type(fixtures), "text", lambda self, rel: '{"a":1}\n123\n"x"\n[1]\nnoise\n\n')
    assert fixtures.lines("whatever") == [{"a": 1}, "123", '"x"', "[1]", "noise", ""]


def test_fixtures_helper_reads_text_json_lines_and_the_manifest(fixtures):
    assert fixtures.root == FIXTURES and fixtures.path("claude/help.txt") == FIXTURES / "claude" / "help.txt"
    assert fixtures.json("claude/auth_status_signed_in.json")["loggedIn"] is True and fixtures.text("handwritten/claude_version.txt") == "2.1.308 (Claude Code)\n"
    lines = fixtures.lines("derived/claude_noise_lines.jsonl")
    assert isinstance(lines[0], dict) and lines[1].startswith("Warning") and lines[2] == "" and isinstance(lines[3], dict)
    assert fixtures.manifest()["files"] == manifest()


def test_fakes_dir_fixture_points_at_the_wrappers(fakes_dir):
    assert fakes_dir == FAKES and (fakes_dir / "fake_cli.py").is_file()


# ------------------------------------------------------------------------------------------------ the capture script
def test_capture_script_refuses_without_the_live_switch_and_prints_its_plan_without_it(monkeypatch, capsys):
    monkeypatch.delenv("SUTRA_LIVE", raising=False)
    assert capture.main([]) == 2
    err = capsys.readouterr().err
    assert "SUTRA_LIVE=1" in err and "at most 2 model calls" in err
    monkeypatch.setenv("SUTRA_LIVE", "0")
    assert capture.main(["--only", "claude"]) == 2
    capsys.readouterr()
    assert capture.main(["--plan"]) == 0
    plan = capsys.readouterr().out
    for step in capture.STEPS["claude"] + capture.STEPS["codex"]:
        assert step in plan
    assert plan.count("[1 model call]") == 4 and "at most 2 calls per CLI reach a model" in plan


def test_every_step_is_planned_and_exactly_four_steps_reach_a_model():
    steps = capture.STEPS["claude"] + capture.STEPS["codex"]
    assert sorted(capture.PLAN) == sorted(steps) and all(callable(getattr(capture.Capture, s)) for s in steps)
    assert [s for s in steps if capture.PLAN[s][2]] == ["claude_fresh", "claude_resume", "codex_fresh", "codex_resume"]
    assert capture.MAX_MODEL_CALLS == 2 and capture.FIXTURES == FIXTURES


def test_the_capture_never_starts_a_third_model_call_for_one_cli(tmp_path):
    cap = capture.Capture(tmp_path / "out", say=lambda *_: None, environ={"PATH": os.environ["PATH"]})
    try:
        for _ in range(2):
            assert cap.call("claude", ["true"], reaches_model=True, env={"PATH": os.environ["PATH"]}).code == 0
        with pytest.raises(capture.CaptureError, match="refusing call 3 that reaches a claude model \\(the limit is 2\\)"):
            cap.call("claude", ["true"], reaches_model=True, env={"PATH": os.environ["PATH"]})
        assert cap.call("codex", ["true"], reaches_model=True, env={"PATH": os.environ["PATH"]}).code == 0       # its own budget
        assert cap.call("claude", ["true"], reaches_model=False, env={"PATH": os.environ["PATH"]}).code == 0     # not counted
        assert cap.model_calls == {"claude": 2, "codex": 1}
    finally:
        cap.close()


def test_scrubber_replaces_identity_and_paths_longest_first():
    s = capture.Scrubber(home="/Users/zed")
    s.learn_identity({"email": "zed@corp.example", "orgId": "11111111-2222-3333-4444-555555555555", "orgName": "Zed Corp"})
    s.add("/tmp/sutra-capture-abc", "/scratch/probe")
    s.add("/Users/zed/tmp/sutra-capture-abc", "/scratch/inner")
    text = "zed@corp.example /Users/zed/.claude /tmp/sutra-capture-abc/x /Users/zed/tmp/sutra-capture-abc/y Zed Corp 11111111-2222-3333-4444-555555555555"
    assert s.text(text) == "user@example.com /Users/me/.claude /scratch/probe/x /scratch/inner/y user@example.com's Organization 00000000-0000-0000-0000-000000000000"
    assert s.obj({"a": ["zed@corp.example", {"b": "/Users/zed"}], "n": 3, "t": True}) == {"a": ["user@example.com", {"b": "/Users/me"}], "n": 3, "t": True}
    s.add("", "x")
    s.add("a", "b")
    assert len(s.pairs) == 6                                                       # empty and one-character secrets are not replaced


def test_trim_keeps_only_the_init_keys_a_connector_reads_and_scrub_stream_applies_it():
    raw = {"type": "system", "subtype": "init", "cwd": "/Users/zed/proj", "session_id": "s", "tools": [], "mcp_servers": [], "model": "m", "permissionMode": "default",
           "apiKeySource": "none", "claude_code_version": "2.1.308", "output_style": "default", "capabilities": ["a"], "uuid": "u",
           "slash_commands": ["/x"], "skills": ["s"], "plugins": [], "memory_paths": {"auto": "/Users/zed/.claude"}, "agents": ["a"]}
    assert capture.trim_claude_init(raw) == {k: raw[k] for k in capture.CLAUDE_INIT_KEYS}
    assert list(capture.trim_claude_init(raw)) == list(capture.CLAUDE_INIT_KEYS)
    s = capture.Scrubber(home="/Users/zed")
    text = json.dumps(raw) + "\nnot json /Users/zed/x\n\n" + json.dumps({"type": "result", "result": "see /Users/zed/f"}) + "\n"
    out = capture.scrub_stream(text, s, fixed_cwd=True)
    lines = out.split("\n")
    assert out.endswith("\n") and len(lines) == 4
    assert json.loads(lines[0]) == dict(capture.trim_claude_init(raw), cwd="/work") and "slash_commands" not in lines[0] and "/Users/zed" not in out
    assert lines[1] == "not json /Users/me/x" and json.loads(lines[2])["result"] == "see /Users/me/f"
    assert json.loads(capture.scrub_stream(json.dumps(raw), s).split("\n")[0])["cwd"] == "/Users/me/proj"
    assert lines[2] == '{"type":"result","result":"see /Users/me/f"}'                      # compact separators


def test_device_code_models_and_result_helpers():
    assert capture.scrub_device_code("code \x1b[94mWXYZ-12345\x1b[0m and ABCD-EFGHJ and ab-cde") == "code \x1b[94mABCD-EFGHJ\x1b[0m and ABCD-EFGHJ and ab-cde"
    doc = {"models": [{"slug": "a", "visibility": "list", "base_instructions": "SECRET LONG TEXT", "priority": 1, "extra": 1}]}
    assert capture.strip_models(doc) == {"models": [{"slug": "a", "visibility": "list", "priority": 1}]}
    assert capture.parse_jsonl('{"a":1}\nnope\n\n[1]\n{"b":2}') == [{"a": 1}, {"b": 2}]
    assert capture.stream_result('{"type":"system"}\n{"type":"result","x":1}\n') == {"type": "result", "x": 1} and capture.stream_result("") == {}
    res = capture.Result(1, "o", "e", 0.5)
    assert capture.probe_doc(res, argv=["x"]) == {"exit": 1, "stdout": "o", "stderr": "e", "seconds": 0.5, "argv": ["x"]}


def test_run_cmd_and_run_until(tmp_path):
    res = capture.run_cmd([sys.executable, "-c", "import sys; print(sys.stdin.read().upper()); sys.exit(3)"], dict(os.environ), "abc")
    assert (res.code, res.stdout.strip(), res.timed_out) == (3, "ABC", False)
    res = capture.run_cmd([sys.executable, "-c", "import time; time.sleep(30)"], dict(os.environ), None, timeout=0.3)
    assert res.timed_out and res.code != 0 and res.seconds < 10
    out, seconds = capture.run_until([sys.executable, "-u", "-c", "import time; print('code AB12-CD345'); time.sleep(30)"], dict(os.environ), r"[A-Z0-9]{4}-[A-Z0-9]{5}", timeout=20)
    assert "AB12-CD345" in out and seconds < 10
    out, seconds = capture.run_until([sys.executable, "-c", "print('nothing to see')"], dict(os.environ), r"NEVER", timeout=20)
    assert out == "nothing to see\n" and seconds < 10


def test_the_probe_mcp_server_logs_what_it_receives_and_answers_like_a_server(tmp_path):
    script, log = tmp_path / "probe.py", tmp_path / "log.jsonl"
    script.write_text(capture.PROBE_SERVER)
    requests = [{"jsonrpc": "2.0", "id": "d", "method": "server/discover", "params": {}}, {"method": "initialize", "params": {"protocolVersion": "2025-11-25"}, "jsonrpc": "2.0", "id": 0},
                {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "method": "tools/list", "id": 1}]
    proc = subprocess.run([sys.executable, str(script), str(log)], input="\n".join(json.dumps(r) for r in requests) + "\n\nnot json\n", capture_output=True, text=True, timeout=20)
    replies = [json.loads(l) for l in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == ["d", 0, 1] and replies[0]["error"]["code"] == -32601
    assert replies[1]["result"]["protocolVersion"] == "2025-11-25" and replies[2]["result"]["tools"][0]["name"] == "ping"
    assert [json.loads(l).get("method") for l in log.read_text().splitlines()[:4]] == ["server/discover", "initialize", "notifications/initialized", "tools/list"]
    assert log.read_text().splitlines()[-1] == "not json"


CLAUDE_CAPTURE_SEQUENCE = "ok_structured,ok_plain,not_logged_in,session_lost,mcp_connected,tool_profile,control_interrupt,bad_flag"
CODEX_CAPTURE_SEQUENCE = "ok_structured,ok_plain,not_signed_in,not_signed_in,bad_flag,session_lost"


class Ran:
    """One run of the capture script against the fakes."""

    def __init__(self, fake, proc, out, claude_cfg, codex_home, pass_env):
        self.fake, self.proc, self.out, self.claude_cfg, self.codex_home, self.pass_env = fake, proc, out, claude_cfg, codex_home, pass_env

    @property
    def stdout(self):
        return self.proc.stdout


def run_capture(fake, root, *extra, versions=True, env=None):
    """Run the capture script as a human would, with the fakes standing in for claude and codex. The scenarios are listed in the
    order of the script's steps, so a reordered step breaks these tests on purpose."""
    root = Path(root)
    out = root / "out"
    shutil.copytree(str(FIXTURES), str(out))
    for stale in ("claude", "codex", "mcp", "derived", "handwritten"):
        shutil.rmtree(str(out / stale))
    old_errors = json.loads((out / "cli_errors.json").read_text())
    old_errors["date"] = "2001-01-01"
    (out / "cli_errors.json").write_text(json.dumps(old_errors))
    claude_cfg, codex_home, home = root / "claude-config", root / "codex-home", root / "home"
    for d in (claude_cfg, codex_home, home):
        d.mkdir()
    (claude_cfg / "fake-login").write_text("")
    (codex_home / "fake-login").write_text("")
    fake_env = fake.env(FAKE_AUTH_FROM_CONFIG="1", FAKE_LOG_ENV="CLAUDE_CONFIG_DIR,CODEX_HOME", FAKE_MAX_SECONDS="10",
                        FAKE_CLAUDE_SEQUENCE=CLAUDE_CAPTURE_SEQUENCE, FAKE_CODEX_SEQUENCE=CODEX_CAPTURE_SEQUENCE)
    if versions:
        fake_env.update(FAKE_CLAUDE_VERSION="9.9.9", FAKE_CODEX_VERSION="8.8.8")
    fake_env.update(env or {})
    (root / "tmp").mkdir()                                        # the script's scratch directory goes here, not into /tmp for good
    script_env = {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(root / "tmp"), "SUTRA_LIVE": "1", "CLAUDE_CONFIG_DIR": str(claude_cfg),
                  "CODEX_HOME": str(codex_home), "ANTHROPIC_API_KEY": "sk-leak-test", "GITHUB_TOKEN": "ghp_leak_test", "CLAUDE_CODE_X": "1", "SUTRA_TOKEN": "t"}
    script_env.update(fake_env)
    pass_env = sorted(fake_env)
    cmd = [sys.executable, str(ROOT / "scripts" / "capture_connector_fixtures.py"), "--out", str(out), "--claude", fake.claude, "--codex", fake.codex,
           "--pass-env", ",".join(pass_env)] + list(extra)
    proc = subprocess.run(cmd, env=script_env, capture_output=True, text=True, timeout=300)
    return Ran(fake, proc, out, claude_cfg, codex_home, pass_env)


@pytest.fixture(scope="module")
def captured(make_fake, tmp_path_factory):
    """One complete capture run against the fakes, shared by the tests that only read its result."""
    return run_capture(make_fake("capture"), tmp_path_factory.mktemp("capture-run"))


def test_the_capture_runs_every_step_against_the_fakes_and_writes_the_files_of_the_fixture_set(captured):
    assert captured.proc.returncode == 0, captured.stdout + captured.proc.stderr
    assert "FAILED" not in captured.stdout and "model calls: claude 2, codex 2" in captured.stdout
    written = sorted(str(p.relative_to(captured.out)) for p in captured.out.rglob("*") if p.is_file())
    assert written == sorted(["MANIFEST.json", "README.md", "cli_errors.json", "claude/auth_status_signed_in.json", "claude/auth_status_signed_out.json",
                              "claude/control_interrupt_response.jsonl", "claude/help.txt", "claude/stream_mcp_server_connected.jsonl", "claude/stream_not_logged_in.jsonl",
                              "claude/stream_resume_plain_ok.jsonl", "claude/stream_resume_unknown_session.jsonl", "claude/stream_structured_ok.jsonl",
                              "claude/stream_tool_profile_init.jsonl", "codex/exec_help.txt", "codex/exec_not_signed_in.jsonl", "codex/exec_resume_help.txt",
                              "codex/exec_resume_plain_ok.jsonl", "codex/exec_structured_ok.jsonl", "codex/login_device_auth.txt", "codex/models_excerpt.json",
                              "codex/rollout_token_count.jsonl"])
    assert "scratch directory kept" not in captured.stdout           # every step succeeded, so the scratch directory was removed


def jl(ran, rel):
    return [json.loads(l) for l in (ran.out / rel).read_text().splitlines()]


def test_the_captured_claude_files_are_what_the_fakes_printed_trimmed_and_scrubbed(captured):
    structured, resumed = jl(captured, "claude/stream_structured_ok.jsonl"), jl(captured, "claude/stream_resume_plain_ok.jsonl")
    assert structured[0]["cwd"] == "/work" and set(structured[0]) <= set(capture.CLAUDE_INIT_KEYS) and structured[-1]["structured_output"] == {"answer": "ok"}
    assert structured[-1]["total_cost_usd"] == pytest.approx(0.0097459) and len(structured) == 14
    assert resumed[-1]["session_id"] == structured[0]["session_id"] != "092c7b68-7118-42da-ba0a-57fa2e5ef699"
    assert resumed[-1]["total_cost_usd"] == pytest.approx(0.0190348)
    assert jl(captured, "claude/stream_not_logged_in.jsonl")[1]["error"] == "authentication_failed"
    assert jl(captured, "claude/stream_resume_unknown_session.jsonl")[0]["num_turns"] == 0
    assert jl(captured, "claude/stream_mcp_server_connected.jsonl")[0]["mcp_servers"][0]["status"] == "connected"
    assert jl(captured, "claude/stream_tool_profile_init.jsonl")[0]["permissionMode"] == "dontAsk"
    assert json.loads((captured.out / "claude/auth_status_signed_in.json").read_text())["email"] == "user@example.com"
    assert json.loads((captured.out / "claude/auth_status_signed_out.json").read_text())["loggedIn"] is False
    assert jl(captured, "claude/control_interrupt_response.jsonl") == [{"type": "control_response", "response": {"subtype": "success", "request_id": "req_1",
                                                                                                                 "response": {"still_queued": []}}}]
    assert (captured.out / "claude/help.txt").read_text() == (FIXTURES / "claude/help.txt").read_text()


def test_the_captured_codex_files_are_what_the_fakes_printed(captured):
    first, second = jl(captured, "codex/exec_structured_ok.jsonl"), jl(captured, "codex/exec_resume_plain_ok.jsonl")
    assert first[0]["type"] == "thread.started" and second[0]["thread_id"] == first[0]["thread_id"]
    assert first[-1]["usage"]["input_tokens"] == 12168 and second[-1]["usage"]["input_tokens"] == 24342
    rollout = jl(captured, "codex/rollout_token_count.jsonl")
    assert [r["payload"]["info"]["last_token_usage"]["input_tokens"] for r in rollout] == [12168, 12174] and set(rollout[0]) == {"timestamp", "payload"}
    assert "turn.failed" in (captured.out / "codex/exec_not_signed_in.jsonl").read_text()
    assert (captured.out / "codex/login_device_auth.txt").read_text() == (FIXTURES / "codex/login_device_auth.txt").read_text()
    assert [m["slug"] for m in json.loads((captured.out / "codex/models_excerpt.json").read_text())["models"]] == ["gpt-reserve", "gpt-5.6-terra", "gpt-5.6-luna", "codex-auto-review"]
    assert (captured.out / "codex/exec_help.txt").read_text() == (FIXTURES / "codex/exec_help.txt").read_text()
    assert (captured.out / "codex/exec_resume_help.txt").read_text() == (FIXTURES / "codex/exec_resume_help.txt").read_text()


def test_the_capture_merges_its_probes_into_cli_errors_by_id_and_keeps_the_rest(captured):
    errors = json.loads((captured.out / "cli_errors.json").read_text())
    original = json.loads((FIXTURES / "cli_errors.json").read_text())
    assert [p["id"] for p in original["probes"]] == [p["id"] for p in errors["probes"]]
    assert errors["signals"] == original["signals"] and errors["verified_flags"] == original["verified_flags"]
    assert errors["captured_with"] == ["claude 9.9.9", "codex-cli 8.8.8"] and errors["date"] == time.strftime("%Y-%m-%d")
    by_id = {p["id"]: p for p in errors["probes"]}
    assert by_id["claude_unknown_effort_value"] == next(p for p in original["probes"] if p["id"] == "claude_unknown_effort_value")      # not reproduced: untouched
    assert by_id["claude_unknown_option"]["stderr"] == "error: unknown option '--no-such-flag'\n" and by_id["claude_unknown_option"]["exit"] == 1
    assert by_id["claude_unknown_option"]["argv"] == ["claude", "-p", "hi", "--no-such-flag"]
    prompt = by_id["claude_system_prompt_file_missing"]
    assert prompt["argv"][-1] == "<missing file>" and prompt["stderr"] == "Error: System prompt file not found: <path>\n"
    invalid = by_id["codex_output_schema_file_invalid"]
    assert invalid["argv"] == ["codex", "exec", "--output-schema", "<file with {not json>", "hi"] and "Output schema file <file> is not valid JSON" in invalid["stderr"]
    assert by_id["codex_output_schema_file_missing"]["argv"][3] == "<missing file>" and "Failed to read output schema file <file>:" in by_id["codex_output_schema_file_missing"]["stderr"]
    assert by_id["codex_missing_working_directory"]["argv"][3] == "<missing dir>"
    assert by_id["codex_resume_unknown_thread"]["argv"][-2] == "<unknown uuid>" and "thread id <id> (code -32600)" in by_id["codex_resume_unknown_thread"]["stderr"]
    assert by_id["codex_login_status_signed_in"]["stderr"] == "Logged in using ChatGPT" and by_id["codex_login_status_signed_out"]["exit"] == 1
    assert by_id["codex_login_status_signed_out"]["env"] == "empty CODEX_HOME" and by_id["codex_login_status_signed_in"]["stream"] == "stderr"
    unknown = by_id["claude_resume_unknown_session"]
    assert unknown["stdout_fixture"] == "claude/stream_resume_unknown_session.jsonl" and "stdout" not in unknown
    assert unknown["stderr"] == "No conversation found with session ID: <id>\n"
    assert by_id["claude_auth_status_signed_in"]["body"] == "claude/auth_status_signed_in.json" and by_id["claude_auth_status_signed_out"]["exit"] == 1
    assert "sutra-capture" not in json.dumps(errors) and str(captured.out) not in json.dumps(errors)


def test_the_capture_updates_the_cli_versions_of_the_captured_manifest_entries_only(captured):
    entries = {e["path"]: e for e in json.loads((captured.out / "MANIFEST.json").read_text())["files"]}
    assert entries["claude/stream_structured_ok.jsonl"]["cli"] == "claude 9.9.9" and entries["codex/exec_structured_ok.jsonl"]["cli"] == "codex-cli 8.8.8"
    assert entries["cli_errors.json"]["cli"] == "claude 9.9.9; codex-cli 8.8.8"
    assert entries["derived/claude_overloaded.jsonl"] == next(e for e in manifest() if e["path"] == "derived/claude_overloaded.jsonl")
    assert entries["handwritten/gh/repo.json"] == next(e for e in manifest() if e["path"] == "handwritten/gh/repo.json")
    assert "updated the CLI versions in MANIFEST.json" in captured.stdout


def test_the_capture_reaches_a_model_at_most_twice_per_cli_and_only_with_the_real_login(captured):
    calls = captured.fake.calls()
    kinds_of = ("print", "exec", "exec_resume")
    claude_calls = [c for c in calls if c["cli"] == "claude" and c["op"] in kinds_of]
    codex_calls = [c for c in calls if c["cli"] == "codex" and c["op"] in kinds_of]
    real_claude = [c for c in claude_calls if c["env_values"]["CLAUDE_CONFIG_DIR"] == str(captured.claude_cfg)]
    real_codex = [c for c in codex_calls if c["env_values"]["CODEX_HOME"] == str(captured.codex_home)]
    assert [c["scenario"] for c in real_claude] == ["ok_structured", "ok_plain"] and [c["scenario"] for c in real_codex] == ["ok_structured", "ok_plain"]
    other_claude = [c for c in claude_calls if c not in real_claude]
    other_codex = [c for c in codex_calls if c not in real_codex]
    assert len(other_claude) == 8 and len(other_codex) == 7                        # signed-out, flag-error and unknown-session calls: they reach no model
    assert all("claude-empty-config" in c["env_values"]["CLAUDE_CONFIG_DIR"] for c in other_claude)
    assert all("codex-empty-config" in c["env_values"]["CODEX_HOME"] for c in other_codex)
    fresh, resumed = real_claude
    assert fresh["argv"][fresh["argv"].index("--session-id") + 1] == resumed["argv"][resumed["argv"].index("--resume") + 1]
    assert "--include-partial-messages" in fresh["argv"] and "--json-schema" in fresh["argv"] and "--json-schema" not in resumed["argv"]
    assert real_codex[1]["op"] == "exec_resume" and "-s" not in real_codex[1]["argv"] and "-C" not in real_codex[1]["argv"]
    assert real_codex[0]["files"]["--output-schema"][0]["content"] == json.dumps(capture.SCHEMA)


def test_the_capture_runs_the_commands_the_manifest_describes(captured):
    calls = captured.fake.model_calls()
    claude_fresh, claude_resume = [c for c in calls if c["cli"] == "claude"][:2]
    uuid = claude_fresh["argv"][-1]
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", uuid)
    assert claude_fresh["argv"] == ["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--json-schema", json.dumps(capture.SCHEMA, separators=(",", ":")),
                                    "--tools", "", "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "", "--model", "sonnet", "--effort", "low",
                                    "--session-id", uuid]
    assert claude_resume["argv"] == ["-p", "--output-format", "stream-json", "--verbose", "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
                                     "--setting-sources", "", "--model", "sonnet", "--effort", "low", "--resume", uuid]
    assert (claude_fresh["stdin"], claude_resume["stdin"]) == (capture.PROMPT_FRESH, capture.PROMPT_RESUME)
    codex_fresh, codex_resume = [c for c in calls if c["cli"] == "codex"][:2]
    schema_path = codex_fresh["files"]["--output-schema"][0]["path"]
    work = codex_fresh["argv"][codex_fresh["argv"].index("-C") + 1]
    assert codex_fresh["argv"] == ["exec", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules", "-s", "read-only", "-C", work,
                                   "-m", "gpt-5.6-luna", "-c", 'model_reasoning_effort="low"', "--output-schema", schema_path, "-"]
    thread = codex_fresh["session_id"]
    assert codex_resume["argv"] == ["exec", "resume", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules", "-m", "gpt-5.6-luna",
                                    "-c", 'model_reasoning_effort="low"', "-c", 'sandbox_mode="read-only"', thread, "-"]
    assert (codex_fresh["stdin"], codex_resume["stdin"]) == (capture.PROMPT_FRESH, capture.PROMPT_RESUME)
    interrupt = next(c for c in captured.fake.model_calls("claude") if "--input-format" in c["argv"])
    assert interrupt["argv"][:6] == ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    assert json.loads(interrupt["stdin"]) == {"type": "control_request", "request_id": "req_1", "request": {"subtype": "interrupt"}}
    tool_profile = next(c for c in captured.fake.model_calls("claude") if "--restricted" in c["argv"])
    config = tool_profile["files"]["--mcp-config"][0]
    assert tool_profile["argv"][-9:] == ["--mcp-config", config["path"], "--restricted", "--allowedTools", "mcp__sutra__*", "--permission-mode", "dontAsk",
                                         "--permission-prompts", "none"]
    assert config["mode"] == "0600"
    assert json.loads(config["content"])["mcpServers"]["sutra"]["command"] == sys.executable


def test_the_capture_removes_the_sessions_it_started(captured):
    calls = captured.fake.calls()
    purge = [c for c in calls if c["op"] == "purge"]
    delete = [c for c in calls if c["op"] == "delete"]
    fresh_claude = next(c for c in calls if c["op"] == "print" and "--session-id" in c["argv"])
    thread = captured.fake.model_calls("codex")[0]["session_id"]
    assert len(purge) == 1 and purge[0]["argv"][:2] == ["purge", "-y"] and os.path.realpath(purge[0]["argv"][2]) == os.path.realpath(fresh_claude["cwd"])
    assert len(delete) == 1 and delete[0]["argv"] == ["delete", thread]


def test_the_capture_gives_the_clis_the_allowlisted_environment_and_scratch_directories(captured):
    allowed = set(capture.ENV_ALLOW) | set(captured.pass_env)
    ops = {c["op"] for c in captured.fake.calls()}
    assert {"version", "help", "auth_status", "login_status", "print", "exec", "exec_resume", "device_auth", "models", "purge", "delete"} <= ops
    for call in captured.fake.calls():
        assert set(call["env_keys"]) <= allowed, set(call["env_keys"]) - allowed
        assert not {"ANTHROPIC_API_KEY", "GITHUB_TOKEN", "CLAUDE_CODE_X", "SUTRA_TOKEN"} & set(call["env_keys"])
        if call["op"] in ("print", "exec", "exec_resume"):
            assert not os.path.realpath(call["cwd"]).startswith(os.path.realpath(str(ROOT))) and "sutra-capture-" in call["cwd"]


def test_the_capture_warns_when_a_cli_never_contacts_the_probe_mcp_server(captured):
    assert not (captured.out / "mcp").exists()
    assert "warning: mcp/claude_client_requests.jsonl: the CLI never contacted the probe MCP server" in captured.stdout
    assert "warning: mcp/codex_client_requests.jsonl: the CLI never contacted the probe MCP server" in captured.stdout
    assert "not regenerated (derived and handwritten fixtures)" in captured.stdout


def test_skipped_steps_run_nothing(fake, tmp_path):
    ran = run_capture(fake, tmp_path, "--only", "claude", "--skip", "claude_mcp,tool_profile,interrupt,errors,fresh,resume,signed_out,resume_unknown")
    assert ran.proc.returncode == 0, ran.stdout
    assert [c["op"] for c in fake.calls()] == ["version", "help", "auth_status", "auth_status"]
    assert "- claude_mcp: skipped" in ran.stdout and "- claude_fresh: skipped" in ran.stdout and "- claude_help:" in ran.stdout
    assert fake.model_calls() == []
    assert not (ran.out / "claude/stream_structured_ok.jsonl").exists() and (ran.out / "claude/help.txt").exists()


ONLY_SIGNED_OUT = ("--only", "claude", "--skip", "help,auth_status,fresh,resume,resume_unknown,mcp,tool_profile,interrupt,errors")


def test_the_capture_stops_a_signed_out_step_that_looks_like_it_reached_a_model(fake, tmp_path):
    # the "signed-out" call answers and costs money: the script must not take that for a signed-out capture
    ran = run_capture(fake, tmp_path, *ONLY_SIGNED_OUT, env={"FAKE_CLAUDE_SEQUENCE": "ok_plain"})
    assert ran.proc.returncode == 1
    assert "FAILED claude_signed_out: the signed-out call cost money: it reached a model, stopping" in ran.stdout
    assert not (ran.out / "claude/stream_not_logged_in.jsonl").exists()
    ran = run_capture(fake, tmp_path / "free", *ONLY_SIGNED_OUT, env={"FAKE_CLAUDE_SEQUENCE": "ok_plain", "FAKE_COST_USD": "0", "FAKE_CLI_STATE": str(tmp_path / "state2")})
    assert "FAILED claude_signed_out: the signed-out call did not fail: stopping, it may have reached a model" in ran.stdout
    ran = run_capture(fake, tmp_path / "ok", *ONLY_SIGNED_OUT, env={"FAKE_CLAUDE_SEQUENCE": "not_logged_in", "FAKE_CLI_STATE": str(tmp_path / "state3")})
    assert ran.proc.returncode == 0 and (ran.out / "claude/stream_not_logged_in.jsonl").is_file()


def test_the_capture_reports_a_failed_fresh_call_and_does_not_resume_it(fake, tmp_path):
    ran = run_capture(fake, tmp_path, "--only", "claude", "--skip", "help,auth_status,signed_out,resume_unknown,mcp,tool_profile,interrupt,errors",
                      env={"FAKE_CLAUDE_SEQUENCE": "overloaded"})
    assert ran.proc.returncode == 1
    assert "FAILED claude_fresh: the fresh call did not succeed (exit 1, API Error: Overloaded)" in ran.stdout
    assert "FAILED claude_resume: there is no fresh session to resume" in ran.stdout
    assert not (ran.out / "claude/stream_structured_ok.jsonl").exists() and not (ran.out / "claude/stream_resume_plain_ok.jsonl").exists()
    assert "model calls: claude 1, codex 0" in ran.stdout and "scratch directory kept at" in ran.stdout
    assert [c["op"] for c in fake.calls()] == ["print"]                               # nothing was started, so there is nothing to purge


def test_a_failed_step_is_reported_and_the_others_still_run(fake, tmp_path):
    ran = run_capture(fake, tmp_path, "--only", "codex", "--skip", "help,login_status,fresh,resume,rollout,device_auth,errors",
                      env={"FAKE_MAX_SECONDS": "0.3", "FAKE_CODEX_SEQUENCE": "hang"})
    assert ran.proc.returncode == 1
    assert "FAILED codex_signed_out: the signed-out call did not fail with turn.failed: stopping, it may have reached a model" in ran.stdout
    assert "FAILED codex_mcp: the mcp call did not fail with turn.failed" in ran.stdout
    assert not (ran.out / "codex/exec_not_signed_in.jsonl").exists()
    assert (ran.out / "codex/models_excerpt.json").is_file()                          # the step after the failures still ran


def test_a_signed_in_check_that_fails_names_the_remedy(fake, tmp_path):
    cap = capture.Capture(tmp_path / "o2", claude=fake.claude, codex=fake.codex, say=lambda *_: None, pass_env=tuple(fake.env()) + ("FAKE_AUTH_FROM_CONFIG",),
                          environ={"PATH": os.environ["PATH"], "HOME": str(tmp_path), "FAKE_AUTH_FROM_CONFIG": "1", **fake.env(),
                                   "CLAUDE_CONFIG_DIR": str(tmp_path / "no-login"), "CODEX_HOME": str(tmp_path / "no-login")})
    try:
        with pytest.raises(capture.CaptureError, match="claude is not signed in here: sign in with `claude auth login`"):
            cap.claude_auth_status()
        with pytest.raises(capture.CaptureError, match="codex is not signed in here: use `codex login`"):
            cap.codex_login_status()
    finally:
        cap.close()


def test_a_login_that_survives_the_empty_config_directory_stops_the_signed_out_captures(fake, tmp_path):
    # without FAKE_AUTH_FROM_CONFIG the fakes stay signed in whatever the config directory holds: the empty-directory trick would fail
    cap = capture.Capture(tmp_path / "o3", claude=fake.claude, codex=fake.codex, say=lambda *_: None, pass_env=tuple(fake.env()),
                          environ={"PATH": os.environ["PATH"], "HOME": str(tmp_path), **fake.env()})
    try:
        with pytest.raises(capture.CaptureError, match="an empty CLAUDE_CONFIG_DIR still shows a login"):
            cap.claude_auth_status()
        with pytest.raises(capture.CaptureError, match="an empty CODEX_HOME still shows a login"):
            cap.codex_login_status()
    finally:
        cap.close()


def stub_exe(tmp_path, name, body):
    """A tiny executable that stands in for a CLI in the error branches of the capture steps."""
    path = tmp_path / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return str(path)


def stubbed_capture(tmp_path, claude="claude", codex="codex"):
    return capture.Capture(tmp_path / "out", claude=claude, codex=codex, say=lambda *_: None, environ={"PATH": os.environ["PATH"], "HOME": str(tmp_path)})


def test_status_steps_refuse_output_they_cannot_use(tmp_path):
    nothing = stub_exe(tmp_path, "nothing", "echo nope")
    failing = stub_exe(tmp_path, "failing", "echo 'Usage: x'; exit 3")
    cap = stubbed_capture(tmp_path, claude=nothing, codex=nothing)
    try:
        with pytest.raises(capture.CaptureError, match="claude --help gave exit 0 and no usage text"):
            cap.claude_help()
        with pytest.raises(capture.CaptureError, match="claude auth status printed no JSON"):
            cap.claude_auth_status()
        with pytest.raises(capture.CaptureError, match="exec --help gave exit 0 and no usage text"):
            cap.codex_help()
        with pytest.raises(capture.CaptureError, match="codex debug models printed no JSON"):
            cap.codex_models()
        with pytest.raises(capture.CaptureError, match="the device sign-in printed no link"):
            cap.codex_device_auth()
        assert cap.versions == {"claude": None, "codex": None}                       # no version in the output: recorded as unknown
    finally:
        cap.close()
    cap = stubbed_capture(tmp_path / "second", claude=failing, codex=failing)
    try:
        with pytest.raises(capture.CaptureError, match="claude --help gave exit 3"):
            cap.claude_help()
        with pytest.raises(capture.CaptureError, match="exec --help gave exit 3"):
            cap.codex_help()
    finally:
        cap.close()


def test_error_probes_must_fail_or_the_step_stops(tmp_path):
    cap = stubbed_capture(tmp_path)
    try:
        with pytest.raises(capture.CaptureError, match="claude_unknown_option: the command succeeded, so it may have reached a model"):
            cap.error_probes("claude", {"claude_unknown_option": (["true"], {}, {})})
        cap.error_probes("claude", {"x": ([sys.executable, "-c", "import sys; sys.stderr.write('bad /A/b'); sys.exit(2)", "/A/b"], {"/A/b": "<arg>"}, {"/A/b": "<err>"})})
        assert cap.probes["x"]["argv"][-1] == "<arg>" and cap.probes["x"]["stderr"] == "bad <err>" and cap.probes["x"]["exit"] == 2
    finally:
        cap.close()


def one_step(fake, tmp_path, step, sequence, **env):
    """Run a single capture step against the fake with the given scenarios."""
    skip = ",".join(n.split("_", 1)[1] for cli in capture.STEPS for n in capture.STEPS[cli] if n != step and n.startswith(step.split("_")[0]))
    return run_capture(fake, tmp_path, "--only", step.split("_")[0], "--skip", skip, env=dict({"FAKE_%s_SEQUENCE" % step.split("_")[0].upper(): sequence}, **env))


def test_a_step_names_what_went_wrong_when_a_fake_answers_differently(fake, tmp_path):
    ran = one_step(fake, tmp_path / "a", "claude_resume_unknown", "error_during_execution", FAKE_COST_USD="0")
    assert "FAILED claude_resume_unknown: the unknown-session call did not fail while loading the session (num_turns 1)" in ran.stdout and ran.proc.returncode == 1
    ran = one_step(fake, tmp_path / "b", "claude_resume_unknown", "ok_plain")
    assert "FAILED claude_resume_unknown: the unknown-session call cost money: it reached a model, stopping" in ran.stdout
    ran = one_step(fake, tmp_path / "c", "claude_interrupt", "ok_plain")
    assert "FAILED claude_interrupt: claude answered no control_request (exit 0)" in ran.stdout
    ran = one_step(fake, tmp_path / "d", "claude_errors", "ok_plain,ok_plain,ok_plain")
    assert "FAILED claude_errors: claude_unknown_option: the command succeeded, so it may have reached a model" in ran.stdout
    ran = one_step(fake, tmp_path / "e", "codex_fresh", "usage_limit")
    assert "FAILED codex_fresh: the fresh call did not complete (exit 1)" in ran.stdout and "model calls: claude 0, codex 1" in ran.stdout
    ran = one_step(fake, tmp_path / "f", "codex_errors", "ok_plain,ok_plain")
    assert "FAILED codex_errors: codex_unknown_argument: the command succeeded, so it may have reached a model" in ran.stdout


def test_the_rollout_step_needs_a_rollout_file_with_a_token_count(fake, tmp_path):
    steps = "help,login_status,resume,signed_out,device_auth,models,mcp,errors"
    ran = run_capture(fake, tmp_path / "a", "--only", "codex", "--skip", steps, env={"FAKE_CODEX_SEQUENCE": "ok_structured", "FAKE_CODEX_ROLLOUT": "off"})
    assert "FAILED codex_rollout: no rollout file for thread" in ran.stdout
    ran = run_capture(fake, tmp_path / "b", "--only", "codex", "--skip", steps, env={"FAKE_CODEX_SEQUENCE": "ok_structured", "FAKE_CODEX_ROLLOUT": "bad", "FAKE_CLI_STATE": str(tmp_path / "s2")})
    assert "FAILED codex_rollout: the rollout file holds no token_count line" in ran.stdout
    ran = run_capture(fake, tmp_path / "c", "--only", "codex", "--skip", "help,login_status,signed_out,device_auth,models,mcp,errors,resume,fresh",
                      env={"FAKE_CLI_STATE": str(tmp_path / "s3")})
    assert "FAILED codex_rollout: there is no thread whose rollout file could be read" in ran.stdout
    ran = run_capture(fake, tmp_path / "d", "--only", "codex", "--skip", "help,login_status,signed_out,device_auth,models,mcp,errors,fresh,rollout",
                      env={"FAKE_CLI_STATE": str(tmp_path / "s4")})
    assert "FAILED codex_resume: there is no fresh thread to resume" in ran.stdout


def test_the_capture_saves_what_a_probe_mcp_server_received(tmp_path):
    cap = capture.Capture(tmp_path / "out", say=lambda *_: None, environ={"PATH": os.environ["PATH"]})
    try:
        script, log = cap.probe_server("x")
        assert script.read_text() == capture.PROBE_SERVER and log.read_text() == "" and script.parent == cap.scratch
        log.write_text('{"jsonrpc":"2.0","id":"s","method":"server/discover","params":{"a":1}}\n{"jsonrpc":"2.0","method":"tools/list","id":1}\n')
        cap.save_mcp_requests("mcp/x.jsonl", log)
        lines = [json.loads(l) for l in (tmp_path / "out/mcp/x.jsonl").read_text().splitlines()]
        assert lines[0]["params"] == "(trimmed)" and lines[1] == {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        assert "mcp/x.jsonl" in cap.written
        log.write_text("")
        cap.save_mcp_requests("mcp/y.jsonl", log)
        assert not (tmp_path / "out/mcp/y.jsonl").exists() and "mcp/y.jsonl: the CLI never contacted" in cap.warnings[-1]
    finally:
        cap.close()


def test_a_capture_scrubs_its_own_scratch_directory_and_the_home_it_was_given(tmp_path):
    cap = capture.Capture(tmp_path / "out", say=lambda *_: None, environ={"PATH": os.environ["PATH"], "HOME": "/Users/zed"})
    try:
        for form in (str(cap.scratch), str(cap.scratch.resolve())):
            assert cap.scrub.text(form + "/claude-work/x") == "/scratch/probe/claude-work/x"
        assert cap.scrub.text("/Users/zed/.claude/projects") == "/Users/me/.claude/projects"
        assert cap.scratch.parent.exists() and cap.scratch.name.startswith("sutra-capture-")
        env = cap.env("codex", empty_config=True)
        assert env["CODEX_HOME"] == str(cap.scratch / "codex-empty-config") and (cap.scratch / "codex-empty-config").is_dir()
        assert cap.env("claude", empty_config=True)["CLAUDE_CONFIG_DIR"] == str(cap.scratch / "claude-empty-config")
        assert "CLAUDE_CONFIG_DIR" not in cap.env("claude")
    finally:
        cap.close()
    assert not cap.scratch.exists()


def test_the_capture_help_names_every_option(capsys):
    with pytest.raises(SystemExit):
        capture.main(["--help"])
    text = capsys.readouterr().out
    for option in ("--only", "--skip", "--out", "--claude", "--codex", "--pass-env", "--keep-scratch", "--plan"):
        assert option in text
