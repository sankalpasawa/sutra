"""CodexConnector against the fake `codex` (work package CN-4, connectors design 3.5, 5.6).

Every test runs the real connector, runner and process code; only the CLI is the fake that replays captured streams.
Fake settings (sequence, reply, auth) must be set BEFORE `make()` because the connector copies them into its extra_env.
CODEX_HOME always points into tmp_path, so no test reads or writes the real ~/.codex.
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

from sutra_app.connectors.base import CallRecord, Hooks, prompted_prompt
from sutra_app.connectors.codex import API_KEY_REFUSED, CodexConnector, PROBED_FLAGS
from sutra_app.connectors.env import PASS_NAMES
from sutra_app.connectors.errors import (
    CallCancelledError, CliMissingError, InvalidRequestError, NotSignedInError, ProviderError,
)
from sutra_app.connectors.models import ConnectorConfig, Message, SessionSpec, Usage
from sutra_app.connectors.policy import Rate
from sutra_app.connectors.process import ProcessRunner
from sutra_app.connectors.schema import strict_schema, to_json_schema

THREAD_HEAD = ["exec", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules"]
SLUG = "gpt-5.6-luna"


class Answer(BaseModel):
    answer: str


class Maybe(BaseModel):
    answer: str
    note: str = "kept"


class Recorder(Hooks):
    def __init__(self):
        self.infos, self.records, self.quotas = [], [], []

    def before_call(self, info):
        self.infos.append(info)

    def after_call(self, record):
        self.records.append(record)

    def on_quota(self, provider, quota):
        self.quotas.append((provider, quota))


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def make(fake, tmp_path):
    def build(*scenarios, clock=None, runner=None, env=None, **settings):
        if scenarios:
            fake.sequence(*scenarios)
        fake.set(**settings)
        kwargs = fake.config_kwargs(tmp_path)
        kwargs["extra_env"] = {**kwargs["extra_env"], "CODEX_HOME": str(tmp_path / "codex-home"), **(env or {})}
        kw = {"clock": clock} if clock else {}
        if runner is not None:
            kw["runner"] = runner
        return CodexConnector(ConnectorConfig(**kwargs), **kw)
    return build


def argv_of(fake, index=-1):
    return fake.model_calls("codex")[index]["argv"]


def value_after(argv, flag):
    return argv[argv.index(flag) + 1]


def probes(fake, op):
    return fake.calls("codex", kind="probe", op=op)


# ---- the command line -------------------------------------------------------------------------------------------------------------

def test_one_shot_text_command_line_stdin_cwd_and_env(fake, make, tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "GITHUB_TOKEN", "ANTHROPIC_API_KEY", "SUTRA_TOKEN"):
        monkeypatch.setenv(name, "leak")
    conn = make("ok_plain")
    turn = conn.call_text("What is 2+2?", system="Be terse.")
    call = fake.model_calls("codex")[0]
    work = Path(call["cwd"])
    assert call["argv"] == THREAD_HEAD + ["--ephemeral", "-s", "read-only", "-C", str(work), "-m", SLUG, "-c",
                                          'model_reasoning_effort="high"', "-"]
    assert call["stdin"] == "<system>\nBe terse.\n</system>\n\nWhat is 2+2?"       # system text inline, prompt on stdin
    assert "2+2" not in " ".join(call["argv"])
    assert fake.visible_env_keys(call) <= set(PASS_NAMES) and call["cwd_entries"] == []
    assert work.parent.parent == Path(os.path.realpath(tmp_path / "work")) and not work.exists()    # removed afterwards
    assert (turn.text, turn.provider, turn.model) == ("ok", "codex", SLUG)


def test_no_system_text_means_the_bare_prompt(fake, make):
    make("ok_plain").call_text("Just this.")
    assert fake.model_calls("codex")[0]["stdin"] == "Just this."


def test_one_shot_native_schema_goes_through_the_strict_adapter_in_a_private_file(fake, make):
    conn = make("ok_structured")
    schema = {"type": "object", "required": ["answer"], "title": "T",
              "properties": {"answer": {"type": "string"}, "note": {"type": "string", "default": "x"}}}
    value, usd, how = conn.call_json("Say ok.", schema=schema)
    argv = argv_of(fake)
    assert value_after(argv, "-c") == 'model_reasoning_effort="low"'
    record = fake.model_calls("codex")[0]["files"]["--output-schema"][0]
    sent = json.loads(record["content"])
    assert sent == strict_schema(schema) and sent["required"] == ["answer", "note"] and sent["additionalProperties"] is False
    assert sent["properties"]["note"]["type"] == ["string", "null"] and "default" not in json.dumps(sent) and "title" not in sent
    assert record["path"] == value_after(argv, "--output-schema") and record["mode"] == "0600" and not Path(record["path"]).exists()
    assert (value, how, usd) == ({"answer": "ok"}, "native", None)


def test_a_pydantic_class_is_sent_as_its_transport_schema(fake, make):
    make("ok_structured").call_json("Say ok.", schema=Maybe)
    sent = json.loads(fake.model_calls("codex")[0]["files"]["--output-schema"][0]["content"])
    assert sent == strict_schema(to_json_schema(Maybe)) and sent["required"] == ["answer", "note"]


def test_nulls_forced_in_by_the_strict_schema_do_not_defeat_a_default(fake, make):
    fake.reply(text=json.dumps({"answer": "ok", "note": None}))
    value, _, how = make("ok_structured").call_json("x", schema=Maybe)
    assert value == Maybe(answer="ok", note="kept") and how == "native"


def test_chat_turns_create_then_resume_the_same_thread(fake, make):
    conn = make("ok_structured", "ok_plain")
    state = conn.start(SessionSpec(session_id="cs_one", system="You are a chat."))
    first = conn.send(state, Message(role="user", text="hello"))
    thread = first.provider_session_id
    second = conn.send(state, Message(role="user", text="again"))
    a, b = (c["argv"] for c in fake.model_calls("codex"))
    assert a == THREAD_HEAD + ["-s", "read-only", "-C", state.workdir, "-m", SLUG, "-c", 'model_reasoning_effort="low"', "-"]
    assert b == ["exec", "resume", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules", "-m", SLUG, "-c",
                 'model_reasoning_effort="low"', "-c", 'sandbox_mode="read-only"', thread, "-"]
    assert "-s" not in b and "-C" not in b and "--ephemeral" not in a
    assert fake.model_calls("codex")[1]["cwd"] == state.workdir                # resume has no -C: the process cwd is the work dir
    assert state.provider_session_id == thread == second.provider_session_id and state.turns == 2
    assert fake.model_calls("codex")[0]["stdin"].startswith("<system>\nYou are a chat.\n</system>")
    assert fake.model_calls("codex")[1]["stdin"] == "again"                    # the thread keeps the system text from turn 1


def test_chat_usage_is_a_delta_per_turn_and_the_session_keeps_the_cumulative_counter(fake, make):
    conn = make("ok_structured", "ok_plain")
    state = conn.start(SessionSpec(session_id="cs_usage"))
    one = conn.send(state, Message(role="user", text="a"))
    two = conn.send(state, Message(role="user", text="b"))
    assert one.usage.input_total == 12168 and one.usage.output_tokens == 15
    assert (two.usage.input_total, two.usage.cached_input_tokens, two.usage.output_tokens) == (12174, 10368, 5)
    assert state.cum_usage == Usage(input_tokens=13974, cached_input_tokens=10368, output_tokens=20)
    assert conn.usage(state) == state.cum_usage and conn.usage().output_tokens == 20
    saved = json.loads((Path(state.workdir) / "session.json").read_text())
    assert saved["cum_usage"]["output_tokens"] == 20 and saved["provider_session_id"] == state.provider_session_id


def test_mcp_tools_are_defined_per_call_with_dash_c(fake, make, tmp_path):
    conn = make("ok_plain")
    conn.call_text("x", tools=("sutra",))
    argv = argv_of(fake)
    root = str(Path(__import__("sutra_app").__file__).resolve().parent.parent)
    assert value_after(argv, "-c") == 'model_reasoning_effort="high"'
    flags = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
    assert flags[1:] == [
        f'mcp_servers.sutra.command={json.dumps(conn.cfg.python)}',
        'mcp_servers.sutra.args=["-m","sutra_app.connectors.tools.mcp_server","--profile","sutra"]',
        f'mcp_servers.sutra.env={{PYTHONPATH={json.dumps(root)},SUTRA_DB_RO={json.dumps(str(tmp_path / "data" / "db.sqlite3"))}}}']
    conn.call_text("x", tools=("sutra", "github"))
    assert '"--profile","sutra,github"' in " ".join(argv_of(fake))


def test_images_are_given_one_dash_i_each_before_the_model_flag(fake, make, tmp_path):
    one, two = tmp_path / "a.png", tmp_path / "b.png"
    one.write_bytes(b"\x89PNG\r\n\x1a\n")
    two.write_bytes(b"\x89PNG\r\n\x1a\n")
    make("ok_plain").call_text("look", images=[str(one), str(two)])
    argv = argv_of(fake)
    assert argv[argv.index("-i"):argv.index("-m")] == ["-i", str(one), "-i", str(two)] and argv[-1] == "-"
    with pytest.raises(InvalidRequestError, match="image not found"):
        make("ok_plain").call_text("look", images=[str(tmp_path / "none.png")])


def test_sandbox_is_read_only_by_default_workspace_write_on_request_never_full_access(fake, make, tmp_path):
    make("ok_plain").call_text("x")
    assert "danger-full-access" not in " ".join(argv_of(fake)) and not any(a.startswith("--dangerously") for a in argv_of(fake))
    cfg = ConnectorConfig(**{**fake.config_kwargs(tmp_path), "extra_env": {**fake.config_kwargs(tmp_path)["extra_env"], "CODEX_HOME": str(tmp_path / "h")}})
    CodexConnector(cfg, sandbox="workspace-write").call_text("x")
    assert value_after(argv_of(fake), "-s") == "workspace-write"
    with pytest.raises(InvalidRequestError, match="sandbox must be one of"):
        CodexConnector(cfg, sandbox="danger-full-access")


def test_a_resume_with_an_unusable_thread_id_is_refused_before_spawning(fake, make):
    conn = make("ok_plain")
    state = conn.start(SessionSpec(session_id="cs_bad"))
    state.provider_session_id = "../../etc/passwd"
    # `send` would drop the id through resume(); build_command itself must still refuse it
    from sutra_app.connectors.base import TurnPlan
    from sutra_app.connectors.models import RouteContext
    plan = TurnPlan(prompt="x", ctx=RouteContext(), model=SLUG, effort="low", session=state, resume=True,
                    provider_session_id="../../etc/passwd", workdir=state.workdir, oneshot=False)
    with pytest.raises(InvalidRequestError, match="thread id is not usable"):
        conn.build_command(plan)
    assert fake.model_calls("codex") == []


# ---- partials -----------------------------------------------------------------------------------------------------------------------

class SpyRunner(ProcessRunner):
    def __init__(self):
        super().__init__()
        self.idle = []

    def start(self, cmd, *, timeout_s=None, idle_timeout_s=None):
        if list(cmd.argv[1:2]) == ["exec"]:
            self.idle.append(idle_timeout_s)
        return super().start(cmd, timeout_s=timeout_s, idle_timeout_s=idle_timeout_s)


def test_codex_has_no_deltas_so_no_idle_deadline_is_ever_armed(fake, make):
    spy = SpyRunner()
    conn = make("ok_plain", "ok_plain", runner=spy)
    assert conn.capabilities.partials is False
    conn.call_text("x", partials=True)
    state = conn.start(SessionSpec(session_id="cs_nopartials"))
    events = list(conn.stream(state, Message(role="user", text="hi"), partials=True))
    assert spy.idle == [None, None] and events[-1].kind == "turn_done" and not any(e.kind == "text_delta" for e in events)


# ---- the login check before a call (X4) and the billing guard ----------------------------------------------------------------------

def test_signed_out_stops_before_any_exec_and_says_what_to_do(fake, make):
    fake.auth(codex="signed_out")
    conn = make("ok_plain")
    rec = Recorder()
    conn.hooks = rec
    with pytest.raises(NotSignedInError) as caught:
        conn.call_text("x")
    assert fake.model_calls("codex") == [] and len(probes(fake, "login_status")) == 1
    assert "Codex is not signed in" in caught.value.user_message() and caught.value.detail["reason"] == "login_status"
    assert [r.code for r in rec.records] == ["not_signed_in"]                   # the Router still gets its record


def test_an_api_key_login_is_refused_with_the_d7_reason_and_no_override(fake, make):
    fake.auth(codex="api_key")
    conn = make("ok_plain")
    status = conn.auth_status()
    assert (status.signed_in, status.billing, status.method, status.detail) == (True, "api_key", "API key", API_KEY_REFUSED)
    assert API_KEY_REFUSED == "API-key login is refused: sign in with your subscription"
    with pytest.raises(NotSignedInError, match="API-key login is refused"):
        conn.call_text("x")
    assert fake.model_calls("codex") == []


def test_the_login_status_is_cached_30_seconds_on_the_injected_clock(fake, make):
    clock = Clock()
    conn = make("ok_plain", clock=clock)
    conn.call_text("a")
    conn.call_text("b")
    assert len(probes(fake, "login_status")) == 1
    clock.now += 31
    conn.call_text("c")
    assert len(probes(fake, "login_status")) == 2 and len(fake.model_calls("codex")) == 3


def test_an_unusable_status_does_not_stop_the_call(fake, make):
    fake.auth(codex="error")
    conn = make("ok_plain")
    assert conn.auth_status().signed_in is None
    assert conn.call_text("x").text == "ok"


def test_probe_auth_reads_the_chatgpt_login_and_the_version(fake, make):
    status = make().auth_status()
    assert (status.provider, status.installed, status.signed_in, status.billing, status.method) == ("codex", True, True, "subscription", "ChatGPT")
    assert status.version == "0.146.0" and status.detail == "signed in with ChatGPT" and status.account is None


def test_probe_auth_for_signed_out_unknown_wording_and_a_missing_cli(fake, make, tmp_path):
    fake.auth(codex="signed_out")
    out = make().auth_status()
    assert (out.signed_in, out.billing, out.installed) == (False, "unknown", True) and "codex login" in out.detail
    missing = CodexConnector(ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", codex_exe=str(tmp_path / "no-such-codex")))
    gone = missing.auth_status()
    assert (gone.installed, gone.signed_in) == (False, None) and "not found" in gone.detail
    with pytest.raises(CliMissingError):
        missing.call_text("x")


def test_an_unknown_login_wording_is_allowed(tmp_path):
    script = tmp_path / "codex"
    script.write_text('#!/bin/sh\ncase "$1" in --version) echo codex-cli 9.9.9;; login) echo "Logged in via the moon" >&2;; esac\n')
    script.chmod(0o755)
    conn = CodexConnector(ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", codex_exe=str(script)))
    status = conn.auth_status()
    assert (status.signed_in, status.billing, status.method, status.version) == (True, "unknown", None, "9.9.9")


# ---- models and effort -----------------------------------------------------------------------------------------------------------------

def test_models_lists_only_what_the_cli_lists(fake, make):
    models = make().models()
    assert [m.slug for m in models] == ["gpt-5.6-terra", "gpt-5.6-luna"]
    luna = models[1]
    assert (luna.label, luna.efforts, luna.context_window, luna.images, luna.listed) == (
        "GPT-5.6-Luna", ["low", "medium", "high", "xhigh", "max"], 272000, True, True)
    assert "ultra" not in models[0].efforts                                    # an effort this app does not know is left out


def test_models_is_empty_when_the_cli_cannot_be_asked(tmp_path):
    conn = CodexConnector(ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", codex_exe=str(tmp_path / "nope")))
    assert conn.models() == []


def test_the_catalog_is_cached_an_hour_and_a_failure_a_minute(fake, make, tmp_path):
    clock = Clock()
    conn = make("ok_plain", clock=clock)
    conn.models()
    conn.call_text("x")
    assert len(probes(fake, "models")) == 1
    clock.now += 3599
    conn.models()
    assert len(probes(fake, "models")) == 1
    clock.now += 2
    conn.models()
    assert len(probes(fake, "models")) == 2
    broken = CodexConnector(ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", codex_exe=str(tmp_path / "nope")), clock=clock)
    calls = []
    original = broken._read_catalog
    broken._read_catalog = lambda: calls.append(1) or original()
    broken.models(), broken.models()
    clock.now += 61
    broken.models()
    assert len(calls) == 2


def test_an_unknown_slug_becomes_the_first_listed_model_with_a_notice(fake, make):
    conn = make("ok_plain")
    events = []
    turn = conn.call_text("x", model="gpt-nope", on_event=events.append)
    assert value_after(argv_of(fake), "-m") == "gpt-5.6-terra" and turn.model == "gpt-5.6-terra"
    notice = [e for e in events if e.kind == "notice"]
    assert len(notice) == 1 and notice[0].data["model"] == "gpt-nope" and notice[0].data["used"] == "gpt-5.6-terra"
    conn.call_text("y", model="gpt-reserve")                                   # a hidden model is not a listed one
    assert value_after(argv_of(fake), "-m") == "gpt-5.6-terra"
    events.clear()
    conn.call_text("z", model="gpt-5.6-luna", on_event=events.append)
    assert value_after(argv_of(fake), "-m") == SLUG and not [e for e in events if e.kind == "notice"]


def test_a_catalog_that_cannot_be_read_leaves_the_slug_alone(fake, make):
    conn = make("ok_plain")
    conn._catalog = (conn._clock(), None)
    conn.call_text("x", model="whatever-1")
    assert value_after(argv_of(fake), "-m") == "whatever-1"


def test_effort_is_clamped_to_what_the_model_supports(fake, make):
    conn = make("ok_plain")
    entry = {"slug": SLUG, "visibility": "list", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}]}
    conn._catalog = (conn._clock(), [entry])
    assert conn.effective_effort(SLUG, "low") == "low"
    assert conn.effective_effort(SLUG, "max") == "high" and conn.effective_effort(SLUG, "xhigh") == "high"
    entry["supported_reasoning_levels"] = [{"effort": "medium"}, {"effort": "high"}]
    assert conn.effective_effort(SLUG, "low") == "medium"                       # nothing below: the lowest supported
    assert conn.effective_effort("unknown-model", "max") == "max"
    events = []
    conn.call_text("x", effort="max", on_event=events.append)
    assert 'model_reasoning_effort="high"' in argv_of(fake)
    assert [e.data["used"] for e in events if e.kind == "notice"] == ["high"]


# ---- the JSON strategy -----------------------------------------------------------------------------------------------------------------

def test_a_reply_that_is_not_json_is_repaired_with_a_second_spawn(fake, make):
    fake.reply(text='{"answer":"fixed"}')
    conn = make("reply_not_json", "ok_structured")
    result = conn.call_json_result("Say ok.", schema=Answer)
    assert (result.value, result.how, result.calls_made) == (Answer(answer="fixed"), "repaired", 2)
    stdin = fake.model_calls("codex")[1]["stdin"]
    assert "YOUR LAST REPLY WAS REJECTED" in stdin and "Say ok." in stdin


def test_a_schema_the_api_rejects_switches_to_the_prompted_path_once(fake, make):
    fake.reply(text='{"answer":"ok"}')
    conn = make("schema_rejected_400", "ok_structured")
    rec = Recorder()
    value, usd, how = conn.call_json("Say ok.", schema=Answer, hooks=rec)
    first, second = fake.model_calls("codex")
    assert "--output-schema" in first["argv"] and "--output-schema" not in second["argv"]
    assert second["stdin"] == prompted_prompt("Say ok.", to_json_schema(Answer))
    assert (value, how) == (Answer(answer="ok"), "prompted")
    assert [r.code for r in rec.records] == ["structured", None] and rec.records[0].native_schema_sha and rec.records[1].native_schema_sha is None


def test_a_dict_schema_is_validated_by_the_minimal_rules(fake, make):
    value, _, how = make("ok_structured").call_json("x", schema={"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}})
    assert (value, how) == ({"answer": "ok"}, "native")


# ---- hooks, cost, quota ------------------------------------------------------------------------------------------------------------------

def test_hooks_see_every_spawn_and_the_usage_of_each(fake, make):
    conn = make("ok_structured")
    rec = Recorder()
    conn.call_text("x", hooks=rec)
    info, record = rec.infos[0], rec.records[0]
    assert (info.provider, info.model, info.kind, info.native) == ("codex", SLUG, "text", False)
    assert isinstance(record, CallRecord) and record.ok and record.usage.input_total == 12168 and record.exit_code == 0
    assert record.cli_version == "0.146.0" and record.usd is None


def test_rates_turn_the_delta_into_a_cost(fake, make):
    conn = make("ok_structured")
    conn.rates = {SLUG: Rate(in_per_mtok=1.0, cached_in_per_mtok=0.1, out_per_mtok=4.0)}
    turn = conn.call_text("x")
    assert turn.usd == pytest.approx((12168 * 1.0 + 15 * 4.0) / 1e6) and turn.usd_basis == "rate_card"
    assert CodexConnector(conn.cfg, rates={SLUG: Rate()}).rates == {SLUG: Rate()}


def test_a_chat_turn_reads_the_quota_from_the_threads_rollout(fake, make):
    conn = make("ok_structured")
    rec = Recorder()
    conn.hooks = rec
    state = conn.start(SessionSpec(session_id="cs_quota"))
    events = list(conn.stream(state, Message(role="user", text="hi")))
    turn = events[-1].data["result"]
    quota = turn["quota"]
    assert (quota["status"], quota["window"], quota["plan"], quota["source"]) == ("ok", "thirty_day", "go", "rollout")
    assert [e.kind for e in events if e.kind == "quota"] == ["quota"] and events[-2].kind == "quota" and events[-1].kind == "turn_done"
    assert rec.quotas[0][0] == "codex" and rec.quotas[0][1].window == "thirty_day"
    assert conn.auth_status(refresh=True).plan == "go"                          # the plan the rollout named


@pytest.mark.parametrize("mode", ["off", "bad"])
def test_a_missing_or_corrupt_rollout_is_ignored(fake, make, mode):
    conn = make("ok_structured", FAKE_CODEX_ROLLOUT=mode)
    state = conn.start(SessionSpec(session_id="cs_norollout"))
    turn = conn.send(state, Message(role="user", text="hi"))
    assert turn.quota is None and turn.text


def test_one_shot_calls_are_ephemeral_and_leave_no_rollout_to_read(fake, make):
    turn = make("ok_structured").call_text("x")
    assert turn.quota is None and "--ephemeral" in argv_of(fake)


def test_read_rollout_quota_refuses_odd_thread_ids_and_survives_garbage(fake, make, tmp_path):
    conn = make()
    for odd in ("", "../../x", "a/b", "a*b", "-x"):
        assert conn.read_rollout_quota(odd) is None
    sessions = tmp_path / "codex-home" / "sessions" / "2026" / "11" / "04"
    sessions.mkdir(parents=True)
    (sessions / "rollout-2026-11-04T00-00-00-t1.jsonl").write_bytes(b"\xff\xfe not json\n{\"payload\": 5}\n[]\n")
    assert conn.read_rollout_quota("t1") is None
    line = {"payload": {"type": "token_count", "rate_limits": {"primary": {"used_percent": 95, "window_minutes": 300, "resets_at": 7}}}}
    with open(sessions / "rollout-2026-11-04T00-00-00-t1.jsonl", "a") as fh:
        fh.write(json.dumps(line) + "\n" + "{\"payload\": {\"type\": \"agent_message\"}}\n")
    quota = conn.read_rollout_quota("t1")
    assert (quota.status, quota.window, quota.resets_at) == ("warning", "five_hour", 7.0)
    newer = {"payload": {"type": "token_count", "rate_limits": {"primary": {"used_percent": 10, "window_minutes": 300, "resets_at": 8}}}}
    with open(sessions / "rollout-2026-11-04T00-00-00-t1.jsonl", "a") as fh:
        fh.write(json.dumps(newer) + "\n")
    assert conn.read_rollout_quota("t1").resets_at == 8.0                       # the LAST token_count line is the current one


# ---- stop, forget, flags ---------------------------------------------------------------------------------------------------------------------

def test_stop_ends_a_running_turn_and_leaves_no_process(fake, make):
    conn = make("slow", FAKE_LINE_DELAY="0.2")
    state = conn.start(SessionSpec(session_id="cs_stop"))
    box = {}

    def turn():
        try:
            conn.send(state, Message(role="user", text="long"))
        except Exception as e:                                   # noqa: BLE001 - the test reads it
            box["error"] = e

    worker = threading.Thread(target=turn)
    worker.start()
    fake.wait_for(1)
    began, stopped = time.time(), False
    for _ in range(100):
        if conn.stop(state):
            stopped = True
            break
        time.sleep(0.05)
    worker.join(12)
    assert stopped and not worker.is_alive() and time.time() - began < 12
    assert isinstance(box["error"], CallCancelledError) and state.turns == 0 and conn.runner.live() == []
    assert conn.stop(state) is False


def test_forget_deletes_the_thread_and_does_nothing_without_one(fake, make):
    conn = make("ok_structured")
    state = conn.start(SessionSpec(session_id="cs_forget"))
    conn.forget(state)
    assert fake.calls("codex", op="delete") == []                              # no thread yet
    conn.send(state, Message(role="user", text="hi"))
    conn.forget(state)
    assert fake.calls("codex", op="delete")[0]["argv"] == ["delete", state.provider_session_id]
    state.provider_session_id = "not a thread"
    assert conn.forget_command(state) is None


def test_probe_flags_reads_exec_help_once(fake, make):
    conn = make(FAKE_HELP_MISSING="--ephemeral")
    flags = conn.flags()
    assert set(flags) == set(PROBED_FLAGS) and flags["--output-schema"] is True and flags["--ephemeral"] is False
    conn.flags()
    assert len(probes(fake, "help")) == 1 and probes(fake, "help")[0]["argv"] == ["exec", "--help"]


# ---- sign-in (5.6) ---------------------------------------------------------------------------------------------------------------------------

def idle(conn, seconds=5.0):
    """True once the runner has no live child (a ladder that just ended may need a moment to be forgotten)."""
    end = time.time() + seconds
    while conn.runner.live() and time.time() < end:
        time.sleep(0.02)
    return conn.runner.live() == []


def wait_for_state(conn, sid, clock, want, seconds=10.0):
    end = time.time() + seconds
    state = None
    while time.time() < end:
        clock.now += 3                                               # past the 2 s poll throttle
        state = conn.sign_in_poll(sid)["state"]
        if state == want:
            return state
        time.sleep(0.05)
    return state


def test_begin_sign_in_returns_the_link_and_code_and_polls_until_signed_in(fake, make):
    fake.auth(codex="signed_out")
    clock = Clock()
    conn = make(clock=clock)
    entry = conn.begin_sign_in()
    assert entry.as_dict() == {"id": entry.id, "url": "https://auth.openai.com/codex/device", "code": "ABCD-EFGHJ", "expires_in": 900}
    assert conn.sign_in_poll(entry.id) == {"state": "pending", "reason": None}
    assert conn.auth_status(refresh=True).signed_in is False
    fake.approve_device_auth()
    assert wait_for_state(conn, entry.id, clock, "signed_in") == "signed_in"
    assert conn.auth_status().signed_in is True                                 # the cache was dropped
    assert idle(conn)


def test_a_pending_sign_in_is_looked_at_most_every_two_seconds(fake, make):
    fake.auth(codex="signed_out")
    clock = Clock()
    conn = make(clock=clock)
    entry = conn.begin_sign_in()
    conn.sign_in_poll(entry.id)
    conn.sign_in_poll(entry.id)
    clock.now += 1
    conn.sign_in_poll(entry.id)
    assert len(probes(fake, "login_status")) == 1 and clock.now > 0
    clock.now += 2
    conn.sign_in_poll(entry.id)
    assert len(probes(fake, "login_status")) == 2
    conn.cancel_sign_in(entry.id)


def test_a_sign_in_expires_after_15_minutes_and_stops_its_child(fake, make):
    fake.auth(codex="signed_out")
    clock = Clock()
    conn = make(clock=clock)
    entry = conn.begin_sign_in()
    clock.now += 901
    assert conn.sign_in_poll(entry.id)["state"] == "expired"
    assert idle(conn) and conn.cancel_sign_in(entry.id) is False


def test_cancel_stops_the_child_and_reports_failed(fake, make):
    fake.auth(codex="signed_out")
    conn = make()
    entry = conn.begin_sign_in()
    assert conn.cancel_sign_in(entry.id) is True
    assert conn.sign_in_poll(entry.id) == {"state": "failed", "reason": "cancelled"} and idle(conn)
    assert conn.cancel_sign_in(entry.id) is False
    with pytest.raises(InvalidRequestError, match="no sign-in"):
        conn.sign_in_poll("nope")


def test_a_second_sign_in_replaces_a_pending_one(fake, make):
    fake.auth(codex="signed_out")
    conn = make()
    first = conn.begin_sign_in()
    second = conn.begin_sign_in()
    assert conn.sign_in_poll(first.id)["reason"] == "replaced by a new sign-in" and second.state == "pending"
    assert len(conn.runner.live()) == 1
    conn.cancel_sign_in(second.id)


def test_a_login_child_that_shows_no_code_is_an_error(tmp_path):
    script = tmp_path / "codex"
    script.write_text('#!/bin/sh\necho "nothing useful" >&2\nexit 1\n')
    script.chmod(0o755)
    conn = CodexConnector(ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", codex_exe=str(script)))
    with pytest.raises(ProviderError, match="showed no link and code"):
        conn.begin_sign_in(ready_timeout_s=5)


def test_a_login_child_that_ends_without_a_login_is_failed(fake, make, tmp_path):
    clock = Clock()
    script = tmp_path / "codex"
    script.write_text('#!/bin/sh\ncase "$1" in\n login) case "$2" in status) echo "Not logged in" >&2; exit 1;; *) echo "https://x.example/device"; echo "WXYZ-12345";; esac;; esac\nexit 0\n')
    script.chmod(0o755)
    conn = CodexConnector(ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", codex_exe=str(script)), clock=clock)
    entry = conn.begin_sign_in()
    assert (entry.url, entry.code) == ("https://x.example/device", "WXYZ-12345")
    assert wait_for_state(conn, entry.id, clock, "failed") == "failed"
    assert "without a login" in conn.sign_in_poll(entry.id)["reason"]


def test_connector_file_modes(fake, make):
    """The work root and the private files are not readable by others."""
    conn = make("ok_structured")
    conn.call_json("x", schema=Answer)
    assert stat.S_IMODE(os.stat(conn.work_root()).st_mode) == 0o700
