"""The Ask mode's read cap in the router (DV-1, D350): a chat turn whose tag asks for `workspace: read` never gets more of the owner's folder than the file tools that look, even
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
    assert value(plain, "-s") == "workspace-write" and "resume" not in plain
    assert value(ask1, "-s") == "read-only" and "resume" not in ask1                                       # the first Ask turn: a new thread (the mode changed), read only
    assert "resume" in ask2 and 'sandbox_mode="read-only"' in ask2                                         # the next Ask turn resumes it, read only again
    assert value(plain2, "-s") == "workspace-write" and "resume" not in plain2                             # a Do after it: a new thread, as it was


def system_of(call):
    """The text a Codex thread was given in its first prompt, or "" (a resumed turn is given none)."""
    stdin = call["stdin"]
    return stdin.split("</system>")[0] if stdin.startswith("<system>") else ""


def test_codex_the_ask_words_reach_an_ask_turn_and_never_a_do_turn_in_either_order(rig, fake):
    """Review M3. Codex reads the system text of a thread's first turn and never again, so a thread is one mode: Do first then Ask, and Ask first then Do, both start a new thread."""
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router, _ = rig("codex", access="edit", sandbox="workspace-write")
    port = RouterChatPort(router)
    def go(mode, text):
        port.set_system(SID, f"SYSTEM-{mode.upper()}: " + ("you cannot change anything" if mode == "ask" else "you may change the files"))
        return turn(router, ASK if mode == "ask" else None, text)
    for mode in ("do", "ask", "do", "ask", "ask", "do", "do"):
        go(mode, "hello " + mode)
    calls = fake.model_calls("codex")
    expected = ["do", "ask", "do", "ask", "ask", "do", "do"]
    for call, mode in zip(calls, expected):
        system = system_of(call)
        if "resume" in call["argv"]:
            assert system == "", (mode, call["stdin"][:80])                                                # a resumed thread is told nothing new, and was started in this very mode
        else:
            assert f"SYSTEM-{mode.upper()}" in system and f"SYSTEM-{'DO' if mode == 'ask' else 'ASK'}" not in system, (mode, system)
    resumed = [("resume" in c["argv"]) for c in calls]
    assert resumed == [False, False, False, False, True, False, True]                                      # a change of mode is a new thread; the same mode resumes
    assert all("SYSTEM-ASK" not in c["stdin"] for c, m in zip(calls, expected) if m == "do")               # no Do prompt ever carries the Ask words, in its system part or in the carry-over of one


def test_codex_a_new_thread_after_a_mode_change_carries_the_conversation_over(rig, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router, _ = rig("codex", access="edit", sandbox="workspace-write")
    router.transcripts.messages = lambda sid, limit=20: [Message(role="user", text="an earlier question"), Message(role="assistant", text="an earlier answer")]
    turn(router, text="first")
    turn(router, ASK, text="second")
    first, second = fake.model_calls("codex")
    assert "an earlier question" in second["stdin"] and "resume" not in second["argv"]


def test_claude_keeps_its_thread_across_modes_and_the_system_text_is_given_every_turn(rig, fake):
    fake.sequence("ok_plain").reply(text="r")
    router, _ = rig("claude", access="edit")
    port = RouterChatPort(router)
    for mode in ("do", "ask", "do"):
        port.set_system(SID, f"SYSTEM-{mode.upper()}")
        turn(router, ASK if mode == "ask" else None)
    a, b, c = (x["argv"] for x in fake.model_calls("claude"))
    assert [value(x, "--system-prompt") for x in (a, b, c)] == ["SYSTEM-DO", "SYSTEM-ASK", "SYSTEM-DO"] and "--resume" in b and "--resume" in c


def test_a_chat_that_never_asked_has_the_same_session_file_as_before(rig, fake):
    import json
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router, _ = rig("codex", access="read")
    turn(router)
    turn(router)
    saved = json.loads((router._workdir(SID) / "session.json").read_text(encoding="utf-8"))
    assert "thread_mode" not in saved
    turn(router, ASK)
    assert json.loads((router._workdir(SID) / "session.json").read_text(encoding="utf-8"))["thread_mode"] == "ask"


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


def test_claude_an_ask_turn_carries_the_remaining_money_as_a_budget_the_cli_enforces(rig, fake):
    """Review M4: the dollars of the allowance reach the process as `--max-budget-usd`, so one spawn cannot read for ever at the owner's cost; a plain turn has no such flag."""
    fake.sequence("ok_plain").reply(text="r")
    router, _ = rig("claude", access="edit")
    port = RouterChatPort(router)
    port.send(SID, ChatTurnIn(text="plain"))
    port.send(SID, ChatTurnIn(text="asked", allowance=Allowance(max_calls=2, max_usd=0.25)))
    port.send(SID, ChatTurnIn(text="small", allowance=Allowance(max_calls=2, max_usd=0.0625)))
    plain, ask, small = (c["argv"] for c in fake.model_calls("claude"))
    assert "--max-budget-usd" not in plain
    assert value(ask, "--max-budget-usd") == "0.25" and value(small, "--max-budget-usd") == "0.0625"


def test_claude_a_second_process_of_one_turn_gets_only_what_the_first_left(rig, fake):
    """The remaining budget is the limit less what earlier processes of the same turn cost (checked on the router's own bookkeeping)."""
    from sutra_app.connectors.router import _Request
    router, _ = rig("claude", access="read")
    state = _Request(router, RouteContext(allowance=Allowance(max_usd=0.25)), router.policy.resolve(__import__("sutra_app.connectors.models", fromlist=["AskRequest"]).AskRequest(user="x")), kind="chat", purpose="chat")
    assert state.money_left() == 0.25
    state.usd_spent = 0.1
    assert abs(state.money_left() - 0.15) < 1e-9
    state.usd_spent = 0.4
    assert state.money_left() == 0.0
    assert _Request(router, RouteContext(), router.policy.resolve(__import__("sutra_app.connectors.models", fromlist=["AskRequest"]).AskRequest(user="x")), kind="chat", purpose="chat").money_left() is None


def test_codex_cannot_cap_a_process_and_says_nothing_of_a_budget(rig, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router, _ = rig("codex", access="read", sandbox="read-only")
    RouterChatPort(router).send(SID, ChatTurnIn(text="asked", allowance=Allowance(max_calls=2, max_usd=0.25)))
    argv = fake.model_calls("codex")[0]["argv"]
    assert not any("budget" in str(a) for a in argv)
