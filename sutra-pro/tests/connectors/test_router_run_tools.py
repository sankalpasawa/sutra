"""J2's builder tools through the connector layer (D245, superseding D240).

What is proved: a `ToolGrant` goes to the Claude CLI only, with J2's own command line (the grant's tools and rules, `--restricted`, `--safe-mode`,
`dontAsk`, `--settings` with the CLI sandbox when the grant asks for it, the grant's cost limit), in the grant's folder; the parser reads every tool
call back in J2's `_tool_meta` shape; the router never plans a tools call on Codex (no fallback: with the Claude CLI unusable the call fails and
Codex runs nothing); the Codex connector refuses one itself; the engine port reports which provider would take one and returns the record; and the
startup line says whether builders get tools and whether the sandbox is on.
"""
from __future__ import annotations

import json
import os

import pytest

from sutra_app.connectors import engine_port
from sutra_app.connectors.base import TurnPlan
from sutra_app.connectors.claude import ClaudeConnector, ClaudeParser, run_tools_settings
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import InvalidRequestError, NoProviderError
from sutra_app.connectors.models import AskRequest, ConnectorConfig, RouteContext
from sutra_app.connectors.process import ExitInfo
from sutra_app.connectors.router import RUN_TOOLS_REFUSED, Router
from sutra_app.engine import llm
from sutra_app.engine.port import CallTag, ToolGrant

from sutra_app.connectors.policy import parse_policy


def policy():
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": "read-only"}},
                         "defaults": {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
                                      "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
                                      "tool_profile": "none", "idle_timeout_s": 120}, "rules": [], "rates": {}})


def value(argv, flag):
    return argv[argv.index(flag) + 1]


def real(path):
    return os.path.realpath(path)


def grant(folder, root, **kw) -> ToolGrant:
    return ToolGrant(**{"tools": ("ToolA", "ToolB"), "allow": ("ToolA", "ToolB(run *)"), "cwd": str(folder), "root": str(root), "usd": 0.5,
                        "log_chars": 10, **kw})


@pytest.fixture
def folders(tmp_path):
    root = tmp_path / "run"
    (root / "out").mkdir(parents=True)
    return root / "out", root


# ---- the parser: J2's tool record -----------------------------------------------------------------------------------------------

J2_LINES = [  # J2's own agent_tools_cli stream (prototypes/j2 j2_flow_test.py), with the fields a result line has
    {"type": "system", "subtype": "init", "session_id": "s1", "model": "sonnet"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "ToolA", "input": {"path": "a.py", "content": "x" * 50}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": False}]}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "ToolB", "input": {"command": "run t.py"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "is_error": True}]}},
    {"type": "result", "subtype": "success", "is_error": False, "result": "done", "total_cost_usd": 0.02, "session_id": "s1",
     "permission_denials": [{}], "usage": {"input_tokens": 1, "output_tokens": 1}},
]


def parse(plan_kw):
    parser = ClaudeParser(TurnPlan(prompt="u", ctx=RouteContext(), model="sonnet", effort="high", **plan_kw))
    for line in J2_LINES:
        parser.feed(json.dumps(line))
    return parser.finish(ExitInfo(returncode=0, reason="exit", stderr_tail="", seconds=0.1, pid=1))


def test_the_parser_reads_every_tool_call_back_in_j2s_shape(folders):
    turn = parse({"run_tools": grant(*folders)})
    record = turn.tool_record
    assert [(c["n"], c["name"], c["ok"]) for c in record["tool_calls"]] == [(1, "ToolA", True), (2, "ToolB", False)]
    first = record["tool_calls"][0]["input"]
    assert first["path"] == "a.py" and first["content"]["chars"] == 50 and len(first["content"]["sha256"]) == 64, "a long string: length and sha256"
    assert (record["denied"], record["stop"], turn.text) == (1, "done", "done")


def test_a_call_without_a_grant_has_no_tool_record():
    assert parse({}).tool_record is None


# ---- the command line -----------------------------------------------------------------------------------------------------------

def command(tmp_path, g):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    plan = TurnPlan(prompt="u", ctx=RouteContext(), system="s", model="sonnet", effort="high", run_tools=g)
    return ClaudeConnector(cfg).build_command(plan)


def test_a_grant_is_j2s_command_line_in_its_own_folder(tmp_path, folders):
    cmd = command(tmp_path, grant(*folders))
    argv = list(cmd.argv)
    assert cmd.cwd == str(folders[0])
    assert value(argv, "--tools") == "ToolA,ToolB" and value(argv, "--allowedTools") == "ToolA ToolB(run *)"
    assert {"--restricted", "--safe-mode", "--no-session-persistence"} <= set(argv) and "--disallowedTools" not in argv
    assert value(argv, "--permission-mode") == "dontAsk" and value(argv, "--permission-prompts") == "none"
    assert value(argv, "--max-budget-usd") == "0.5" and argv.count("--max-budget-usd") == 1
    settings = json.loads(value(argv, "--settings"))
    assert "sandbox" not in settings, "the grant did not ask for the sandbox"
    assert settings["permissions"] == {"allow": ["ToolA", "ToolB(run *)"], "additionalDirectories": [], "blockReadsOutsideWorkingDirectories": True}


def test_with_the_sandbox_the_cli_fences_reads_and_writes_to_the_folder(tmp_path, folders):
    settings = json.loads(value(list(command(tmp_path, grant(*folders, sandbox=True)).argv), "--settings"))
    fs = settings["sandbox"]["filesystem"]
    assert settings["sandbox"]["enabled"] and settings["sandbox"]["allowUnsandboxedCommands"] is False
    assert fs["denyRead"] == ["~/"] and fs["allowRead"] == fs["allowWrite"] == [real(folders[0])]
    assert run_tools_settings(grant(*folders, sandbox=True)) == settings


# ---- the router: Claude only, no fallback -----------------------------------------------------------------------------------------

def rig(fake, tmp_path, *names):
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    makers = {"claude": lambda: ClaudeConnector(cfg), "codex": lambda: CodexConnector(cfg, sandbox="read-only")}
    return Router({n: makers[n]() for n in names}, policy(), sleep=lambda s: None)


def tools_req(g):
    return AskRequest(user="build it", system="s", ctx=RouteContext(tag=CallTag(function="W-1", role="builder")), run_tools=g)


def test_a_tools_call_runs_on_the_claude_cli_in_the_builders_folder(fake, tmp_path, folders):
    fake.sequence("ok_plain").reply(text="built")
    router = rig(fake, tmp_path, "claude", "codex")
    try:
        assert engine_port.tools_provider_of(router) == "claude"
        router.ask(tools_req(grant(*folders)))
        call, = fake.model_calls("claude")
        assert call["cwd"] == real(folders[0]) and value(call["argv"], "--tools") == "ToolA,ToolB"
        assert not fake.model_calls("codex")
    finally:
        router.close()


def test_with_the_claude_cli_signed_out_a_tools_call_never_falls_back_to_codex(fake, tmp_path, folders):
    fake.auth(claude="signed_out")
    router = rig(fake, tmp_path, "claude", "codex")
    try:
        assert engine_port.tools_provider_of(router) is None
        with pytest.raises(NoProviderError) as caught:
            router.ask(tools_req(grant(*folders)))
        assert {"provider": "codex", "reason": RUN_TOOLS_REFUSED} in caught.value.detail["skipped"]
        assert not fake.model_calls("codex") and not fake.model_calls("claude")
    finally:
        router.close()


def test_a_codex_only_router_has_no_tools_provider_and_codex_refuses_a_grant_itself(fake, tmp_path, folders):
    router = rig(fake, tmp_path, "codex")
    try:
        assert engine_port.tools_provider_of(router) is None
        with pytest.raises(InvalidRequestError, match="can't run J2's builder tools call"):
            router.connectors["codex"].call_text("u", run_tools=grant(*folders))
    finally:
        router.close()


# ---- the startup line and the sandbox ---------------------------------------------------------------------------------------------

@pytest.fixture
def clean_env(monkeypatch):
    for name in ("J2_SANDBOX", "J2_SANDBOX_CMD", "J2_AGENT_TOOLS"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("platform, found, on", [("darwin", True, True), ("linux", True, True), ("darwin", False, True), ("win32", True, False)])
def test_the_sandbox_is_on_for_macos_and_linux_whatever_is_on_path(clean_env, platform, found, on):
    """D462: the bundled srt decides, not `which`; a missing node or bundle keeps it on (each launch then fails closed)."""
    clean_env.setattr(llm.sys, "platform", platform)
    clean_env.setattr(llm.shutil, "which", lambda name: "/opt/srt" if found else None)
    got, why = llm.sandbox_status(mock=False)
    assert got is on
    assert "npm i -g" not in why


@pytest.mark.parametrize("value_, on", [("1", True), ("0", False)])
def test_j2_sandbox_overrides_the_platform_either_way(clean_env, value_, on):
    clean_env.setenv("J2_SANDBOX", value_)
    for platform in ("darwin", "win32"):
        clean_env.setattr(llm.sys, "platform", platform)
        assert llm.sandbox_status(mock=False) == (on, f"J2_SANDBOX={value_}")


def test_offline_the_sandbox_is_j2s_default(clean_env):
    assert llm.sandbox_status(mock=True)[0] is False


def test_the_startup_line_says_whether_builders_get_tools_and_whether_the_sandbox_is_on(fake, tmp_path, clean_env):
    clean_env.setattr(llm.sys, "platform", "darwin")
    clean_env.setattr(llm, "bundled_srt", lambda environ=None: (["node", "srt.mjs"], None, "bundled srt 0.0.83 at /opt/srt, node 24.22.1"))
    router = rig(fake, tmp_path, "claude", "codex")
    try:
        assert engine_port.builder_tools_line(router, offline=False) == ("Builder tools: on (the Claude CLI). "
                                                                         "Sandbox: on (bundled srt 0.0.83 at /opt/srt, node 24.22.1).")
        # the engine settings a new run reads (engine.json, J2_* environment): J2_AGENT_TOOLS=0 and J2_SANDBOX=0 decide
        line = engine_port.builder_tools_line(router, offline=False, agent_tools=False, sandbox=False)
        assert line == "Builder tools: off (J2_AGENT_TOOLS=0): J2 builds through its section path. Sandbox: off (J2_SANDBOX=0)."
    finally:
        router.close()
    codex = rig(fake, tmp_path, "codex")
    try:
        line = engine_port.builder_tools_line(codex, offline=False)
        assert line.startswith("Builder tools: off (no connector can run them") and "Codex has no J2 tools path" in line
    finally:
        codex.close()
    assert engine_port.builder_tools_line(None, offline=True).startswith("Builder tools: off (offline")
    assert os.environ.get("J2_AGENT_TOOLS") is None


def test_a_tools_call_is_tried_once(fake, tmp_path, folders):
    """J2 runs a tools call once: a retry would start over on the files the first try wrote (the engine decides what comes next). A plain call's
    retry is tests/connectors/test_router_attempts.py's."""
    fake.sequence("overloaded", "ok_plain").reply(text="built")
    router = rig(fake, tmp_path, "claude")
    try:
        with pytest.raises(Exception) as caught:
            router.ask(tools_req(grant(*folders)))
        assert getattr(caught.value, "code", None) == "overloaded" and len(fake.model_calls("claude")) == 1, "one try, no retry"
    finally:
        router.close()
