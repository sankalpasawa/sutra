"""The Ask mode's read cap in the router (DV-1, D340): a chat turn whose tag asks for `workspace: read` never gets more of the owner's folder than the file tools that look, even
when the owner let the team change files; a turn that does not ask is exactly what it was. Real Claude and Codex connectors against the fake CLIs, no network, no model.

Also: the limits a turn carries in `ChatTurnIn.allowance` reach the router's own gate, and a turn without them is unchanged."""
from __future__ import annotations

import os

import pytest

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import EnvelopeExceededError
from sutra_app.connectors.models import Allowance, ConnectorConfig, Message, RouteContext
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.workdir import WorkFolder
from sutra_app.engine.port import CallTag

SID = "cs_ask1"
READ = "Read,Glob,Grep,LS"
WRITING = {"Edit", "MultiEdit", "Write", "Bash", "NotebookEdit"}
ASK = RouteContext(tag=CallTag(workspace="read"))


def policy(sandbox="read-only"):
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": sandbox}},
                         "defaults": {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
                                      "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
                                      "tool_profile": "none", "idle_timeout_s": 120}, "rules": [], "rates": {}})


class History:
    def messages(self, session_id, limit=20):
        return []


def value(argv, flag):
    return argv[argv.index(flag) + 1]


@pytest.fixture
def rig(fake, tmp_path):
    made = []

    def build(name, access="edit", sandbox="read-only"):
        cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
        maker = {"claude": lambda: ClaudeConnector(cfg), "codex": lambda: CodexConnector(cfg, sandbox=sandbox)}[name]
        router = Router({name: maker()}, policy(sandbox), transcripts=History(), sleep=lambda s: None)
        router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
        folder = tmp_path / "proj"
        folder.mkdir(exist_ok=True)
        router.folders.set(str(folder), access=access)
        made.append(router)
        router.chat_pin(SID, name)
        return router, folder

    yield build
    for router in made:
        router.close()


def turn(router, ctx=None, text="hello"):
    return router.chat_send(SID, Message(role="user", text=text), ctx or RouteContext())


def test_claude_a_plain_turn_with_edit_access_can_change_files_and_an_ask_turn_cannot(rig, fake):
    fake.sequence("ok_plain").reply(text="r")
    router, folder = rig("claude", access="edit")
    turn(router)
    turn(router, ASK)
    plain, ask = (c["argv"] for c in fake.model_calls("claude"))
    assert WRITING & set(value(plain, "--tools").split(",")) == {"Edit", "MultiEdit", "Write", "Bash"}          # the owner's "edit" is real for the chat as it was
    assert value(ask, "--tools") == READ and value(ask, "--allowedTools") == READ
    denied = set(value(ask, "--disallowedTools").split(","))
    assert WRITING | {"WebFetch", "WebSearch", "Task", "Agent", "PowerShell"} <= denied and not denied & set(READ.split(","))
    assert "--restricted" in ask and value(ask, "--permission-mode") == "dontAsk" and value(ask, "--permission-prompts") == "none"
    assert not any("git" in rule for rule in value(ask, "--allowedTools").split(","))                           # not even the four git reads


def test_claude_both_turns_run_in_the_same_folder_and_the_same_provider_session(rig, fake):
    """Switching between Ask and Do must not start a new provider session (the folder is the same string): the chat keeps its thread."""
    fake.sequence("ok_plain").reply(text="r")
    router, folder = rig("claude", access="edit")
    turn(router, ASK)
    turn(router)
    turn(router, ASK)
    first, second, third = fake.model_calls("claude")
    assert first["cwd"] == second["cwd"] == third["cwd"] == os.path.realpath(folder)
    assert "--session-id" in first["argv"] and "--resume" in second["argv"] and "--resume" in third["argv"]
    assert value(second["argv"], "--resume") == value(third["argv"], "--resume") == value(first["argv"], "--session-id")


def test_claude_with_read_access_an_ask_turn_and_a_plain_turn_are_the_same_command(rig, fake):
    fake.sequence("ok_plain").reply(text="r")
    router, _ = rig("claude", access="read")
    turn(router)
    turn(router, ASK)
    plain, ask = (c["argv"] for c in fake.model_calls("claude"))
    for flag in ("--tools", "--allowedTools", "--disallowedTools", "--permission-mode"):
        assert value(plain, flag) == value(ask, flag)


def test_claude_an_ask_turn_with_no_folder_has_no_tools_at_all(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="r")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    router = Router({"claude": ClaudeConnector(cfg)}, policy(), transcripts=History(), sleep=lambda s: None)
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())            # none chosen
    try:
        turn(router, ASK)
    finally:
        router.close()
    call = fake.model_calls("claude")[0]
    assert value(call["argv"], "--tools") == "" and not {"--allowedTools", "--disallowedTools"} & set(call["argv"])


def test_codex_an_ask_turn_runs_in_a_read_only_sandbox_even_when_the_owner_allowed_changes_and_on_every_resumed_turn(rig, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router, folder = rig("codex", access="edit", sandbox="workspace-write")
    turn(router)
    turn(router, ASK)
    turn(router, ASK)
    turn(router)
    plain, ask1, ask2, plain2 = (c["argv"] for c in fake.model_calls("codex"))
    assert value(plain, "-s") == "workspace-write"
    assert "resume" in ask1 and 'sandbox_mode="read-only"' in ask1 and 'sandbox_mode="read-only"' in ask2      # a resumed thread takes its sandbox from -c, every turn
    assert 'sandbox_mode="workspace-write"' in plain2                                                         # and a plain turn after it is the chat as it was


def test_the_limits_of_a_turn_reach_the_routers_gate_and_a_turn_without_them_is_unchanged(rig, fake):
    fake.sequence("ok_plain").reply(text="r")
    router, _ = rig("claude", access="read")
    port = RouterChatPort(router)
    out = port.send(SID, ChatTurnIn(text="hello"))                                      # no allowance: as it always was
    assert out.text == "r"
    with pytest.raises(EnvelopeExceededError):                                          # zero calls allowed: refused before any process starts
        port.send(SID, ChatTurnIn(text="again", allowance=Allowance(max_calls=0)))
    assert len(fake.model_calls("claude")) == 1
    port.send(SID, ChatTurnIn(text="limited", allowance=Allowance(max_calls=2, max_usd=0.25)))
    assert len(fake.model_calls("claude")) == 2
