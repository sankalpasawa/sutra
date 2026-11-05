"""ClaudeConnector and the ModelConnector base against the fake `claude` (work package CN-3, connectors design 3.3, 3.4).

Every test runs the real connector, runner and process code; only the CLI is the fake that replays captured streams.
Fake settings (sequence, reply, auth) must be set BEFORE `make()` because the connector copies them into its extra_env.
"""
from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path

import pytest
from pydantic import BaseModel

from sutra_app.connectors.base import CallInfo, CallRecord, Hooks, MAX_PROMPT_CHARS, prompted_prompt, tool_names
from sutra_app.connectors.claude import ClaudeConnector, SYSTEM_FILE_THRESHOLD
from sutra_app.connectors.env import PASS_NAMES
from sutra_app.connectors.errors import (
    CallCancelledError, EnvelopeExceededError, InvalidJsonError, InvalidRequestError, NotSignedInError,
    SessionLostError, StructuredError,
)
from sutra_app.connectors.models import ConnectorConfig, Message, RouteContext, SessionSpec, Usage
from sutra_app.engine.port import Allowance

ONE_SHOT_HEAD = ["-p", "--output-format", "stream-json", "--verbose", "--model", "sonnet", "--effort"]
TAIL = ["--tools", "", "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", ""]


class Answer(BaseModel):
    answer: str


class Recorder(Hooks):
    def __init__(self, veto=None):
        self.infos, self.records, self.quotas, self.veto = [], [], [], veto

    def before_call(self, info):
        if self.veto:
            raise self.veto
        self.infos.append(info)

    def after_call(self, record):
        self.records.append(record)

    def on_quota(self, provider, quota):
        self.quotas.append((provider, quota))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("SUTRA_CLAUDE_MODEL", "CLAUDE_CLI_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def make(fake, tmp_path):
    def build(*scenarios, clock=None, **settings):
        if scenarios:
            fake.sequence(*scenarios)
        fake.set(**settings)
        cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
        return ClaudeConnector(cfg, clock=clock) if clock else ClaudeConnector(cfg)
    return build


def argv_of(fake, index=-1):
    return fake.model_calls("claude")[index]["argv"]


def value_after(argv, flag):
    return argv[argv.index(flag) + 1]


# ---- the command line: six shapes ---------------------------------------------------------------------------------------------

def test_one_shot_text_command_line_stdin_cwd_and_env(fake, make, tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "CLAUDE_CODE_ENTRYPOINT", "SUTRA_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "leak")
    conn = make("ok_plain")
    turn = conn.call_text("What is 2+2?", system="Be terse.")
    call = fake.model_calls("claude")[0]
    assert call["argv"] == ONE_SHOT_HEAD + ["high", "--system-prompt", "Be terse."] + TAIL + ["--no-session-persistence"]
    assert call["stdin"] == "What is 2+2?"                            # the prompt is on stdin, never argv
    assert "What is 2+2?" not in " ".join(call["argv"])
    assert fake.visible_env_keys(call) <= set(PASS_NAMES)
    assert call["cwd_entries"] == []                                  # a fresh EMPTY directory
    work = Path(call["cwd"])
    assert work.parent.parent == Path(os.path.realpath(tmp_path / "work")) and not work.exists()    # removed afterwards
    assert turn.text == "ok" and turn.provider == "claude"


def test_one_shot_native_schema_command_line(fake, make):
    conn = make("ok_structured")
    value, usd, how = conn.call_json("Say ok.", schema=Answer, system="S")
    argv = argv_of(fake)
    assert argv[:7] == ONE_SHOT_HEAD[:7] and value_after(argv, "--effort") == "low"
    schema = json.loads(value_after(argv, "--json-schema"))
    assert schema["properties"]["answer"]["type"] == "string" and schema["additionalProperties"] is False
    assert value_after(argv, "--json-schema") == json.dumps(schema, separators=(",", ":"), ensure_ascii=False)   # one line
    assert (value, how) == (Answer(answer="ok"), "native") and usd == pytest.approx(0.0097459)
    assert fake.model_calls("claude")[0]["stdin"] == "Say ok."


def test_chat_turns_create_then_resume_the_same_session(fake, make, tmp_path):
    conn = make("ok_structured", "ok_plain")
    state = conn.start(SessionSpec(session_id="cs_one", system="You are a chat."))
    conn.send(state, Message(role="user", text="hello"))
    conn.send(state, Message(role="user", text="again"))
    first, second = (c["argv"] for c in fake.model_calls("claude"))
    assert "--no-session-persistence" not in first and "--resume" not in first
    uuid_given = value_after(first, "--session-id")
    assert state.provider_session_id == uuid_given and value_after(second, "--resume") == uuid_given
    assert "--session-id" not in second
    assert value_after(first, "--system-prompt") == value_after(second, "--system-prompt") == "You are a chat."
    cwds = {c["cwd"] for c in fake.model_calls("claude")}
    assert cwds == {state.workdir} and "--include-partial-messages" not in first


def test_tool_profile_command_line_and_mcp_file(fake, make):
    conn = make("ok_plain", "ok_plain")
    conn.call_text("look", tools=("sutra", "github"))
    call = fake.model_calls("claude")[0]
    argv = call["argv"]
    start = argv.index("--mcp-config")
    assert argv[start + 2:start + 9] == ["--restricted", "--allowedTools", "mcp__sutra__*", "--permission-mode", "dontAsk",
                                         "--permission-prompts", "none"]
    mcp = call["files"]["--mcp-config"][0]
    assert mcp["mode"] == "0600" and not os.path.exists(mcp["path"])           # 0600 while it lived, deleted afterwards
    server = json.loads(mcp["content"])["mcpServers"]["sutra"]
    assert server["args"] == ["-m", "sutra_app.connectors.tools.mcp_server", "--profile", "sutra,github"]
    assert set(server["env"]) == {"PYTHONPATH", "SUTRA_DB_RO"}                 # a path each, no secret
    conn.call_text("plain")
    assert "--mcp-config" not in argv_of(fake) and "--restricted" not in argv_of(fake)


def test_images_go_in_as_one_stream_json_line(fake, make, tmp_path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake image body")
    conn = make("ok_plain")
    conn.call_text("What is on it?", images=[str(png)])
    call = fake.model_calls("claude")[0]
    assert value_after(call["argv"], "--input-format") == "stream-json"
    line = call["stdin"]
    assert line.endswith("\n") and line.count("\n") == 1
    content = json.loads(line)["message"]["content"]
    assert [b["type"] for b in content] == ["image", "text"] and content[1]["text"] == "What is on it?"
    assert content[0]["source"]["media_type"] == "image/png" and content[0]["source"]["type"] == "base64"


def test_a_missing_or_foreign_image_is_refused_before_any_spawn(fake, make, tmp_path):
    conn = make("ok_plain")
    with pytest.raises(InvalidRequestError, match="image not found"):
        conn.call_text("x", images=[str(tmp_path / "none.png")])
    text = tmp_path / "notes.png"
    text.write_text("not an image")
    with pytest.raises(InvalidRequestError, match="not a PNG or JPEG"):
        conn.call_text("x", images=[str(text)])
    assert fake.model_calls("claude") == []


def test_a_long_system_prompt_goes_in_a_private_file_that_is_deleted(fake, make):
    conn = make("ok_plain", "ok_plain")
    long = "s" * (SYSTEM_FILE_THRESHOLD + 1)
    conn.call_text("x", system=long)
    call = fake.model_calls("claude")[0]
    assert "--system-prompt" not in call["argv"]
    record = call["files"]["--system-prompt-file"][0]
    assert record["mode"] == "0600" and record["content"] == long and not os.path.exists(record["path"])
    conn.call_text("x", system="s" * SYSTEM_FILE_THRESHOLD)                    # exactly at the limit stays on argv
    assert "--system-prompt-file" not in argv_of(fake) and len(value_after(argv_of(fake), "--system-prompt")) == SYSTEM_FILE_THRESHOLD


def test_max_budget_flag_only_with_an_allowance(fake, make):
    conn = make("ok_plain", "ok_plain")
    conn.call_text("x")
    assert "--max-budget-usd" not in argv_of(fake)
    conn.call_text("x", ctx=RouteContext(allowance=Allowance(max_usd=0.25)))
    assert value_after(argv_of(fake), "--max-budget-usd") == "0.25"


def test_json_repairs_get_the_money_that_is_left(fake, make):
    fake.cost(0.2).reply(text='{"answer":"ok"}')
    conn = make("plain_not_json", "ok_plain")
    result = conn.call_json_result("x", schema=Answer, ctx=RouteContext(allowance=Allowance(max_usd=1.0)), force_prompted=True)
    first, second = (float(value_after(c["argv"], "--max-budget-usd")) for c in fake.model_calls("claude"))
    assert first == 1.0 and second == pytest.approx(0.8) and result.how == "repaired"


def test_no_money_left_stops_before_a_spawn(fake, make):
    conn = make("ok_plain")
    with pytest.raises(EnvelopeExceededError):
        conn.call_text("x", ctx=RouteContext(allowance=Allowance(max_usd=0)))
    assert fake.model_calls("claude") == []


@pytest.mark.parametrize("kwargs,message", [
    ({"effort": "turbo"}, "effort must be one of"),
    ({"timeout": 0}, "timeout"),
    ({"timeout": float("inf")}, "timeout"),
    ({"tools": ("mystery",)}, "unknown tool profile"),
])
def test_bad_arguments_are_refused_before_a_spawn(fake, make, kwargs, message):
    conn = make("ok_plain")
    with pytest.raises(InvalidRequestError, match=message):
        conn.call_text("x", **kwargs)
    assert fake.model_calls("claude") == []


def test_prompt_rules(fake, make):
    conn = make("ok_plain")
    for bad in ("", "   \n"):
        with pytest.raises(InvalidRequestError, match="prompt is empty"):
            conn.call_text(bad)
    with pytest.raises(InvalidRequestError, match="too long"):
        conn.call_text("x" * (MAX_PROMPT_CHARS + 1))
    assert fake.model_calls("claude") == []


def test_tool_names_normalise():
    assert tool_names(()) == () and tool_names(("none",)) == () and tool_names(("sutra+github",)) == ("sutra", "github")
    assert tool_names(("github", "sutra", "sutra")) == ("sutra", "github") and tool_names(("sutra,github",)) == ("sutra", "github")


def test_the_model_comes_from_the_request_the_default_or_an_override(fake, make, monkeypatch):
    conn = make("ok_plain", "ok_plain", "ok_plain", "ok_plain")
    conn.call_text("x")
    assert value_after(argv_of(fake), "--model") == "sonnet"
    conn.call_text("x", model="opus")
    assert value_after(argv_of(fake), "--model") == "opus"
    monkeypatch.setenv("CLAUDE_CLI_MODEL", "claude-haiku-4-5")
    conn.call_text("x", model="opus")
    assert value_after(argv_of(fake), "--model") == "claude-haiku-4-5"
    monkeypatch.setenv("SUTRA_CLAUDE_MODEL", "fable")
    conn.call_text("x")
    assert value_after(argv_of(fake), "--model") == "fable"
    monkeypatch.setenv("SUTRA_CLAUDE_MODEL", "--evil flag")                 # an override is checked like any other name
    with pytest.raises(InvalidRequestError, match="not a usable model name"):
        conn.call_text("x")
    monkeypatch.delenv("SUTRA_CLAUDE_MODEL")
    monkeypatch.delenv("CLAUDE_CLI_MODEL")
    with pytest.raises(InvalidRequestError, match="not a usable model name"):
        conn.call_text("x", model="--evil flag")


def test_partials_flag_and_streamed_deltas(fake, make):
    conn = make("ok_structured")
    state = conn.start(SessionSpec(session_id="cs_part"))
    events = list(conn.stream(state, Message(role="user", text="go"), partials=True))
    assert "--include-partial-messages" in argv_of(fake)
    kinds = [e.kind for e in events]
    assert kinds[0] == "started" and kinds[-1] == "turn_done" and "text_delta" in kinds
    assert events[-1].data["result"]["provider"] == "claude" and events[-1].data["result"]["usd"] == pytest.approx(0.0097459)


# ---- sessions ----------------------------------------------------------------------------------------------------------------------

def test_start_creates_the_work_dir_and_a_private_session_file(fake, make, tmp_path):
    conn = make()
    state = conn.start(SessionSpec(session_id="cs_a", model="opus", effort="high", system="sys"))
    root = Path(os.path.realpath(tmp_path / "work"))
    assert Path(state.workdir) == root / "cs_a" and Path(state.workdir).is_dir()
    assert (state.provider, state.model, state.effort, state.turns, state.provider_session_id) == ("claude", "opus", "high", 0, None)
    saved = Path(state.workdir) / "session.json"
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert json.loads(saved.read_text())["session_id"] == "cs_a"
    assert stat.S_IMODE((Path(state.workdir) / "system.txt").stat().st_mode) == 0o600
    assert fake.calls() == []                                            # no process yet
    again = conn.start(SessionSpec(session_id="cs_a"))                   # a new provider session replaces the file
    assert again.created_at >= state.created_at and not (Path(state.workdir) / "system.txt").exists()
    with pytest.raises(InvalidRequestError, match="not codex"):
        conn.start(SessionSpec(session_id="cs_b", provider="codex"))
    with pytest.raises(InvalidRequestError, match="unknown tool profile"):
        conn.start(SessionSpec(session_id="cs_c", tool_profile="mystery"))


def test_two_turns_add_up_the_counters_and_persist_them(fake, make):
    conn = make("ok_structured", "ok_plain")
    state = conn.start(SessionSpec(session_id="cs_sum"))
    one = conn.send(state, Message(role="user", text="one"))
    assert (state.turns, state.cum_usd) == (1, pytest.approx(0.0097459)) and one.usd == pytest.approx(0.0097459)
    two = conn.send(state, Message(role="user", text="two"))
    assert two.usd == pytest.approx(0.0092889, abs=1e-9)                     # the delta, not the cumulative 0.0190348
    assert state.cum_usd == pytest.approx(0.0190348, abs=1e-7) and state.turns == 2
    assert state.cum_usage == Usage(input_tokens=6, cached_input_tokens=1728, cache_write_tokens=4570, output_tokens=57)
    assert conn.usage(state) == state.cum_usage and conn.usage().total == one.usage.total + two.usage.total
    on_disk = json.loads((Path(state.workdir) / "session.json").read_text())
    assert on_disk["turns"] == 2 and on_disk["provider_session_id"] == state.provider_session_id
    assert on_disk["cum_usage"]["cache_write_tokens"] == 4570


def test_a_failed_turn_leaves_the_session_as_it_was(fake, make):
    conn = make("quota")
    state = conn.start(SessionSpec(session_id="cs_fail"))
    with pytest.raises(Exception) as caught:
        conn.send(state, Message(role="user", text="hi"))
    assert caught.value.code == "quota"
    assert (state.turns, state.provider_session_id, state.cum_usd) == (0, None, 0.0)


def test_a_lost_provider_session_is_reported_and_kept_for_the_router(fake, make):
    conn = make("ok_plain", "session_lost")
    state = conn.start(SessionSpec(session_id="cs_lost"))
    conn.send(state, Message(role="user", text="one"))
    known = state.provider_session_id
    with pytest.raises(SessionLostError):
        conn.send(state, Message(role="user", text="two"))
    assert state.provider_session_id == known and state.turns == 1


def test_resume_checks_only_local_things(fake, make, tmp_path):
    conn = make("ok_plain")
    state = conn.start(SessionSpec(session_id="cs_res"))
    conn.send(state, Message(role="user", text="hi"))
    kept = conn.resume(state.model_copy())
    assert kept.provider_session_id == state.provider_session_id and kept.turns == 1       # session.json wins
    (Path(state.workdir) / "session.json").unlink()
    lost = conn.resume(state.model_copy())
    assert lost.provider_session_id is None and (Path(state.workdir) / "session.json").is_file()    # a new provider session
    bad = lost.model_copy(update={"provider_session_id": "not-a-uuid"})
    assert conn.resume(bad).provider_session_id is None
    with pytest.raises(InvalidRequestError, match="belongs to codex"):
        conn.resume(state.model_copy(update={"provider": "codex"}))
    elsewhere = state.model_copy(update={"workdir": str(tmp_path / "elsewhere")})
    with pytest.raises(InvalidRequestError, match="not under the work root"):
        conn.resume(elsewhere)
    with pytest.raises(InvalidRequestError, match="not under the work root"):
        conn.send(elsewhere, Message(role="user", text="x"))


def test_resume_refuses_a_session_file_of_another_session(fake, make):
    conn = make()
    state = conn.start(SessionSpec(session_id="cs_x"))
    other = conn.start(SessionSpec(session_id="cs_y"))
    (Path(state.workdir) / "session.json").write_text((Path(other.workdir) / "session.json").read_text())
    with pytest.raises(InvalidRequestError, match="does not belong"):
        conn.resume(state)
    (Path(state.workdir) / "session.json").write_text("{broken")
    with pytest.raises(InvalidRequestError, match="not valid"):
        conn.resume(state)


def test_a_lost_session_file_starts_a_new_provider_session(fake, make):
    conn = make("ok_plain", "ok_plain")
    state = conn.start(SessionSpec(session_id="cs_gone"))
    conn.send(state, Message(role="user", text="one"))
    (Path(state.workdir) / "session.json").unlink()
    conn.send(state, Message(role="user", text="two"))
    first, second = (c["argv"] for c in fake.model_calls("claude"))
    assert "--session-id" in second and "--resume" not in second and value_after(second, "--session-id") != value_after(first, "--session-id")


def test_session_rules(fake, make):
    conn = make("ok_plain")
    state = conn.start(SessionSpec(session_id="cs_rules"))
    with pytest.raises(InvalidRequestError, match="user message"):
        conn.send(state, Message(role="assistant", text="x"))
    with pytest.raises(InvalidRequestError, match="belongs to codex"):
        conn.send(state.model_copy(update={"provider": "codex"}), Message(role="user", text="x"))
    assert fake.model_calls("claude") == []


def test_one_turn_at_a_time_and_stop_ends_it(fake, make):
    conn = make("slow", FAKE_LINE_DELAY="0.2")
    state = conn.start(SessionSpec(session_id="cs_busy"))
    box = {}

    def turn():
        try:
            conn.send(state, Message(role="user", text="long"))
        except Exception as e:                                   # noqa: BLE001 - the test reads it
            box["error"] = e

    worker = threading.Thread(target=turn)
    worker.start()
    fake.wait_for(1)
    with pytest.raises(InvalidRequestError, match="already running a turn"):
        conn.send(state, Message(role="user", text="second"))
    began = time.time()
    stopped = False
    for _ in range(100):
        if conn.stop(state):
            stopped = True
            break
        time.sleep(0.05)
    worker.join(12)
    assert stopped and not worker.is_alive() and time.time() - began < 12
    assert isinstance(box["error"], CallCancelledError) and state.turns == 0
    assert conn.runner.live() == [] and conn.stop(state) is False          # nothing left, and an idle session says False
    assert fake.calls("claude")[0]["exit"] is not None
    conn.send(state, Message(role="user", text="free again"))             # the busy mark is gone (a sequence of one repeats slow)


def test_forget_runs_purge_on_the_work_dir_and_never_raises(fake, make, tmp_path):
    conn = make()
    state = conn.start(SessionSpec(session_id="cs_forget"))
    conn.forget(state)
    purge = fake.calls("claude", op="purge")[0]
    assert purge["argv"] == ["purge", "-y", state.workdir] and Path(state.workdir).is_dir()   # the dir stays for a switch
    broken = ClaudeConnector(ConnectorConfig(**dict(fake.config_kwargs(tmp_path), claude_exe=str(tmp_path / "no-such-claude"))))
    broken.forget(state)


def test_abandoning_a_stream_cancels_the_child(fake, make):
    conn = make("slow", FAKE_LINE_DELAY="0.2")
    hooks = Recorder()
    state = conn.start(SessionSpec(session_id="cs_drop"))
    stream = conn.stream(state, Message(role="user", text="go"), hooks=hooks)
    assert next(stream).kind == "started"
    stream.close()
    assert conn.runner.live() == [] and hooks.records[0].code == "cancelled" and state.turns == 0


# ---- health -------------------------------------------------------------------------------------------------------------------------

def test_auth_status_reads_the_status_command_and_caches_for_30_seconds(fake, make):
    now = [1000.0]
    conn = make(clock=lambda: now[0])
    status = conn.auth_status()
    assert (status.installed, status.signed_in, status.method, status.billing) == (True, True, "claude.ai", "subscription")
    assert (status.plan, status.account, status.version, status.checked_at) == ("max", "user@example.com", "2.1.308", 1000.0)
    assert "user@example.com" not in repr(status)
    assert len(fake.calls("claude", op="auth_status")) == 1
    now[0] += 29
    assert conn.auth_status() is status and len(fake.calls("claude", op="auth_status")) == 1
    now[0] += 2
    assert conn.auth_status() is not status and len(fake.calls("claude", op="auth_status")) == 2
    conn.auth_status(refresh=True)
    assert len(fake.calls("claude", op="auth_status")) == 3
    assert len(fake.calls("claude", op="version")) == 1                  # the version is read once


@pytest.mark.parametrize("mode,signed_in,billing", [("signed_out", False, "subscription"), ("api_key", True, "api_key"),
                                                    ("console", True, "api_key"), ("error", None, "unknown")])
def test_auth_status_modes(fake, make, mode, signed_in, billing):
    fake.auth(claude=mode)
    status = make().auth_status()
    assert (status.signed_in, status.billing) == (signed_in, billing) and status.installed


def test_auth_status_for_a_missing_cli(fake, make, tmp_path):
    conn = ClaudeConnector(ConnectorConfig(**dict(fake.config_kwargs(tmp_path), claude_exe=str(tmp_path / "nope"))))
    status = conn.auth_status()
    assert (status.installed, status.signed_in) == (False, None) and "not found" in status.detail


def test_a_not_signed_in_error_drops_the_cached_status(fake, make):
    conn = make("not_logged_in")
    conn.auth_status()
    with pytest.raises(NotSignedInError):
        conn.call_text("x")
    conn.auth_status()
    assert len(fake.calls("claude", op="auth_status")) == 2


def test_probe_flags_reads_the_help_once(fake, make):
    conn = make()
    flags = conn.flags()
    assert flags["--json-schema"] and flags["--allowedTools"] and all(flags.values()) and "--system-prompt-file" not in flags
    conn.flags()
    assert len(fake.calls("claude", op="help")) == 1
    old = make(FAKE_HELP_MISSING="--json-schema,--restricted")
    missing = old.probe_flags()
    assert not missing["--json-schema"] and not missing["--restricted"] and missing["--model"]


def test_models_version_and_capabilities(fake, make):
    conn = make(FAKE_CLAUDE_VERSION="2.2.0")
    assert [m.slug for m in conn.models()] == ["sonnet", "opus", "fable"] and all(m.listed and m.images for m in conn.models())
    assert conn.version() == "2.2.0"
    assert conn.capabilities.native_schema and conn.capabilities.resume and conn.capabilities.partials
    assert ClaudeConnector(ConnectorConfig(data_dir=Path("/nonexistent"), claude_exe="/nonexistent/claude")).version() is None


# ---- the JSON strategy -------------------------------------------------------------------------------------------------------

def test_native_json_returns_the_class_instance(fake, make):
    result = make("ok_structured").call_json_result("Say ok.", schema=Answer)
    assert isinstance(result.value, Answer) and result.how == "native" and result.calls_made == 1
    assert result.usd == pytest.approx(0.0097459) and result.usd_spent == result.usd and result.turn.structured == {"answer": "ok"}
    assert result.as_tuple() == (result.value, result.usd, "native")


def test_a_dict_schema_returns_a_dict(fake, make):
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    value, _, how = make("ok_structured").call_json("Say ok.", schema=schema)
    assert value == {"answer": "ok"} and how == "native"


def test_json_without_a_schema_returns_the_text(fake, make):
    fake.reply(text="plain words")
    value, _, how = make("ok_plain").call_json("hi")
    assert value == "plain words" and how == "prompted"
    assert "--json-schema" not in argv_of(fake)


def test_a_structured_error_switches_to_the_prompted_path_once(fake, make):
    fake.reply(text='{"answer": "ok"}')
    hooks = Recorder()
    result = make("structured_failed", "ok_plain").call_json_result("Say ok.", schema=Answer, hooks=hooks)
    first, second = fake.model_calls("claude")
    assert "--json-schema" in first["argv"] and "--json-schema" not in second["argv"]
    assert "ONE JSON object" in second["stdin"] and '"answer"' in second["stdin"]
    assert (result.how, result.calls_made, result.value) == ("prompted", 2, Answer(answer="ok"))
    assert [r.code for r in hooks.records] == ["structured", None]
    assert hooks.records[0].native_schema_sha is not None and hooks.records[1].native_schema_sha is None


def test_a_second_structured_error_stands(fake, make):
    with pytest.raises(StructuredError):
        make("structured_failed").call_json("x", schema=Answer)
    assert len(fake.model_calls("claude")) == 2                    # the native try, then one prompted try; no more switching


def test_force_prompted_never_sends_the_native_schema(fake, make):
    fake.reply(text='{"answer": "ok"}')
    result = make("ok_plain").call_json_result("Say ok.", schema=Answer, force_prompted=True)
    call = fake.model_calls("claude")[0]
    assert "--json-schema" not in call["argv"] and call["stdin"].startswith("Say ok.") and result.how == "prompted"


def test_a_huge_schema_goes_prompted_by_itself(fake, make):
    fake.reply(text='{"answer": "ok"}')
    schema = {"type": "object", "properties": {"answer": {"type": "string", "description": "d" * 100_001}}, "required": ["answer"]}
    result = make("ok_plain").call_json_result("x", schema=schema)
    assert len(fake.model_calls("claude")) == 1 and result.calls_made == 1        # no failed native try first
    assert "--json-schema" not in argv_of(fake) and result.how == "prompted" and result.value == {"answer": "ok"}


def test_a_reply_in_a_fence_is_read(fake, make):
    value, _, how = make("plain_json_in_fence").call_json("x", schema=Answer, effort="high")
    assert how == "prompted" and isinstance(value, Answer)
    assert value_after(argv_of(fake), "--effort") == "high"


def test_a_reply_that_is_not_json_is_repaired_once(fake, make):
    hooks = Recorder()
    conn = make("plain_not_json", "ok_plain")
    fake.reply(text='{"answer": "fixed"}')
    conn = make("plain_not_json", "ok_plain")
    result = conn.call_json_result("Say ok.", schema=Answer, hooks=hooks, force_prompted=True)
    first, second = fake.model_calls("claude")
    assert result.how == "repaired" and result.calls_made == 2 and result.value == Answer(answer="fixed")
    assert "YOUR LAST REPLY WAS REJECTED" in second["stdin"] and "Say ok." in second["stdin"]
    assert "YOUR LAST REPLY WAS" not in first["stdin"] and [i.kind for i in hooks.infos] == ["json", "repair"]


def test_a_reply_of_the_wrong_shape_is_repaired_with_pydantics_words(fake, make):
    conn = make("plain_json_wrong_shape", "ok_plain")
    fake.reply(text='{"answer": "fixed"}')
    conn = make("plain_json_wrong_shape", "ok_plain")
    result = conn.call_json_result("x", schema=Answer, force_prompted=True)
    assert result.how == "repaired" and "answer" in fake.model_calls("claude")[1]["stdin"]


def test_a_reply_that_never_validates_ends_in_invalid_json(fake, make):
    conn = make("plain_not_json")
    with pytest.raises(InvalidJsonError) as caught:
        conn.call_json("x", schema=Answer, force_prompted=True)
    assert len(fake.model_calls("claude")) == 3                       # the first try and two repair rounds
    assert caught.value.detail == {"rounds": 2, "calls": 3} and caught.value.provider == "claude"
    assert not caught.value.fallback_ok


def test_repair_rounds_can_be_zero(fake, make):
    with pytest.raises(InvalidJsonError):
        make("plain_not_json").call_json("x", schema=Answer, force_prompted=True, repair_rounds=0)
    assert len(fake.model_calls("claude")) == 1
    with pytest.raises(InvalidRequestError, match="repair_rounds"):
        make("plain_not_json").call_json("x", schema=Answer, repair_rounds=-1)


def test_a_native_reply_of_the_wrong_shape_is_repaired_natively(fake, make):
    conn = make("ok_structured")
    fake.reply(json={"answer": 5})
    conn = make("ok_structured")
    with pytest.raises(InvalidJsonError):
        conn.call_json("x", schema=Answer)
    assert all("--json-schema" in c["argv"] for c in fake.model_calls("claude")) and len(fake.model_calls("claude")) == 3


def test_money_adds_up_over_the_spawns(fake, make):
    fake.cost(0.5).reply(text='{"answer":"ok"}')
    result = make("plain_not_json", "ok_plain").call_json_result("x", schema=Answer, force_prompted=True)
    assert result.calls_made == 2 and result.usd == pytest.approx(1.0) and result.usd_spent == result.usd


def test_prompted_prompt_names_the_schema():
    text = prompted_prompt("Do it.", {"type": "object"})
    assert text.startswith("Do it.") and 'JSON Schema:\n{"type":"object"}' in text


# ---- hooks and records --------------------------------------------------------------------------------------------------------

def test_hooks_see_every_spawn(fake, make):
    hooks = Recorder()
    conn = make("ok_structured")
    conn.call_json_result("x", schema=Answer, hooks=hooks, ctx=RouteContext(session_id="s9"))
    info, record = hooks.infos[0], hooks.records[0]
    assert isinstance(info, CallInfo) and (info.provider, info.kind, info.model, info.effort, info.native, info.attempt) == (
        "claude", "json", "sonnet", "low", True, 1) and info.ctx.session_id == "s9"
    assert isinstance(record, CallRecord) and record.ok and record.code is None and record.error is None
    assert record.usage.input_total == 3357 and record.usd == pytest.approx(0.0097459) and record.exit_code == 0
    assert record.turn.structured == {"answer": "ok"} and record.cli_version is None and record.seconds >= 0
    assert record.native_schema_sha and len(record.native_schema_sha) == 64
    assert [q.status for _, q in hooks.quotas] == ["ok"] and hooks.quotas[0][0] == "claude"


def test_a_failed_spawn_is_recorded_with_its_code(fake, make):
    hooks = Recorder()
    with pytest.raises(Exception):
        make("overloaded").call_text("x", hooks=hooks)
    record = hooks.records[0]
    assert (record.ok, record.code, record.turn, record.usd) == (False, "overloaded", None, None)
    assert record.error.provider == "claude" and record.exit_code == 1


def test_before_call_can_veto_a_spawn(fake, make):
    hooks = Recorder(veto=EnvelopeExceededError("no more calls"))
    with pytest.raises(EnvelopeExceededError):
        make("ok_plain").call_text("x", hooks=hooks)
    assert fake.model_calls("claude") == [] and hooks.records == []


def test_the_connector_level_hooks_are_the_default(fake, make):
    conn = make("ok_plain")
    conn.hooks = Recorder()
    conn.call_text("x")
    assert len(conn.hooks.records) == 1


def test_a_missing_system_prompt_file_is_retried_once_inline(fake, make):
    hooks = Recorder()
    conn = make("C3b", "ok_plain")
    long = "L" * (SYSTEM_FILE_THRESHOLD + 5)
    turn = conn.call_text("x", system=long, hooks=hooks)
    first, second = fake.model_calls("claude")
    assert "--system-prompt-file" in first["argv"] and value_after(second["argv"], "--system-prompt") == long
    assert [r.code for r in hooks.records] == ["cli_flag_unsupported", None] and [i.attempt for i in hooks.infos] == [1, 2]
    assert turn.text == "ok"


def test_the_retry_happens_once_only(fake, make):
    conn = make("C3b")
    with pytest.raises(Exception) as caught:
        conn.call_text("x", system="L" * (SYSTEM_FILE_THRESHOLD + 5))
    assert caught.value.code == "cli_flag_unsupported" and len(fake.model_calls("claude")) == 2
    conn = make("C3b")
    with pytest.raises(Exception):
        conn.call_text("x", system="short")                           # nothing to inline: no retry
    assert len(fake.model_calls("claude")) == 3


def test_a_consumer_exception_cancels_the_child(fake, make):
    conn = make("slow", FAKE_LINE_DELAY="0.2")

    def boom(event):
        raise RuntimeError("consumer failed")

    with pytest.raises(RuntimeError, match="consumer failed"):
        conn.call_text("x", on_event=boom)
    assert conn.runner.live() == []


def test_on_event_sees_the_events_of_a_one_shot(fake, make):
    seen = []
    make("ok_structured").call_json("x", schema=Answer, on_event=None)
    make("ok_structured").call_text("x", on_event=seen.append)
    assert [e.kind for e in seen] == ["started", "tool_call", "tool_result", "quota"]


def test_send_reports_events_to_on_event_without_the_final_marker(fake, make):
    seen = []
    conn = make("ok_structured")
    state = conn.start(SessionSpec(session_id="cs_events"))
    turn = conn.send(state, Message(role="user", text="go"), on_event=seen.append)
    assert [e.kind for e in seen] == ["started", "tool_call", "tool_result", "quota"] and turn.provider == "claude"
