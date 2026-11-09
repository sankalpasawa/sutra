"""The working folder in a chat turn (GAP3-workdir): the real Claude and Codex connectors against the fake CLIs, no network.

What is proved: with a folder the child runs IN it with read-only file tools only (claude: the four tools, everything that writes or runs
denied by name; codex: a read-only sandbox, whatever the policy says), the session's own state stays in its private folder, a changed folder
starts a new provider session with the carry-over (and a repeated one resumes), the org chat agent's call gets the folder and a team's run does
not, and with no folder nothing changed."""
from __future__ import annotations

import os

import pytest

from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.models import AskRequest, ConnectorConfig, JsonRequest, Message, RouteContext, SessionSpec
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.usage import load_session_state
from sutra_app.connectors.workdir import WorkFolder
from sutra_app.engine.port import CallTag

SID = "cs_wd1"
READ = "Read,Glob,Grep,LS"


def policy(sandbox="read-only"):
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": sandbox}},
                         "defaults": {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
                                      "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
                                      "tool_profile": "none", "idle_timeout_s": 120}, "rules": [], "rates": {}})


class History:
    def __init__(self):
        self.messages_list = []

    def messages(self, session_id, limit=20):
        return list(self.messages_list)


def value(argv, flag):
    return argv[argv.index(flag) + 1]


class Rig:
    def __init__(self, fake, tmp_path, *names, sandbox="read-only"):
        self.fake = fake
        self.cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
        self.history, self.events = History(), []
        makers = {"claude": lambda: ClaudeConnector(self.cfg), "codex": lambda: CodexConnector(self.cfg, sandbox=sandbox)}
        self.router = Router({n: makers[n]() for n in names}, policy(sandbox), transcripts=self.history, sleep=lambda s: None,
                             events=lambda t, d: self.events.append((t, d)))
        self.router.folders = WorkFolder(self.cfg.data_dir, self.cfg.resolved_work_root())
        self.folder_a, self.folder_b = tmp_path / "proj-a", tmp_path / "proj-b"
        self.folder_a.mkdir()
        self.folder_b.mkdir()
        self.session_dir = self.cfg.resolved_work_root() / SID

    def choose(self, folder, access="read"):
        if folder is None:
            self.router.folders.clear()
        else:
            self.router.folders.set(str(folder), access=access)

    def turn(self, text="hello"):
        self.history.messages_list.append(Message(role="user", text=text))
        out = self.router.chat_send(SID, Message(role="user", text=text), RouteContext())
        self.history.messages_list.append(Message(role="assistant", text=out.text))
        return out

    def state(self):
        return load_session_state(self.session_dir)

    def calls(self, cli):
        return self.fake.model_calls(cli)

    def close(self):
        self.router.close()


@pytest.fixture
def make(fake, tmp_path):
    rigs = []

    def build(*names, **kw):
        rigs.append(Rig(fake, tmp_path, *names, **kw))
        return rigs[-1]

    yield build
    for r in rigs:
        r.close()


def real(path):
    return os.path.realpath(path)


# ---- claude --------------------------------------------------------------------------------------------------------------------

def test_claude_with_a_folder_runs_in_it_with_the_four_read_tools_and_denies_the_rest(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.choose(rig.folder_a)
    rig.turn()
    call = rig.calls("claude")[0]
    argv = call["argv"]
    assert call["cwd"] == real(rig.folder_a)
    assert value(argv, "--tools") == READ and value(argv, "--allowedTools") == READ
    assert "--restricted" in argv and value(argv, "--permission-mode") == "dontAsk" and value(argv, "--permission-prompts") == "none"
    denied = value(argv, "--disallowedTools").split(",")
    assert {"Bash", "Edit", "MultiEdit", "Write", "NotebookEdit", "WebFetch", "WebSearch"} <= set(denied)
    assert not set(denied) & set(READ.split(","))                       # nothing is both allowed and denied
    assert value(argv, "--setting-sources") == "" and "--strict-mcp-config" in argv


def test_claude_with_no_folder_is_unchanged_a_private_empty_folder_and_no_tools(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.turn()
    call = rig.calls("claude")[0]
    assert call["cwd"] == real(rig.session_dir)
    assert value(call["argv"], "--tools") == ""
    assert not {"--allowedTools", "--disallowedTools", "--restricted", "--permission-mode"} & set(call["argv"])


def test_the_sessions_own_state_stays_in_its_private_folder(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    RouterChatPort(rig.router).set_system(SID, "grounding text")
    rig.choose(rig.folder_a)
    rig.turn()
    rig.turn("again")
    assert (rig.session_dir / "session.json").is_file() and (rig.session_dir / "system.txt").read_text(encoding="utf-8") == "grounding text"
    assert rig.state().workdir == str(rig.session_dir) and rig.state().work_folder == real(rig.folder_a)
    assert sorted(p.name for p in rig.folder_a.iterdir()) == []                 # the owner's folder got nothing from the app
    first, second = rig.calls("claude")
    assert value(first["argv"], "--system-prompt") == value(second["argv"], "--system-prompt") == "grounding text"
    assert "--resume" in second["argv"] and second["cwd"] == real(rig.folder_a)       # the integrity check kept passing: the turn resumed


def test_a_changed_folder_starts_a_new_provider_session_with_the_carry_over_and_a_repeated_one_resumes(make, fake):
    fake.sequence("ok_plain").reply(text="reply")
    rig = make("claude")
    rig.turn("one")                                                  # no folder yet
    rig.choose(rig.folder_a)
    rig.turn("two")                                                  # the first turn in a folder: a new provider session
    rig.turn("three")                                                # the same folder: resumed
    rig.choose(rig.folder_b)
    rig.turn("four")                                                 # another folder: new again
    rig.choose(None)
    rig.turn("five")                                                 # folder forgotten: new again, back in the private folder
    c1, c2, c3, c4, c5 = rig.calls("claude")
    assert "--session-id" in c1["argv"] and "--session-id" in c2["argv"] and "--resume" in c3["argv"]
    assert "--session-id" in c4["argv"] and "--session-id" in c5["argv"]
    ids = [value(c["argv"], "--session-id" if "--session-id" in c["argv"] else "--resume") for c in (c1, c2, c3, c4, c5)]
    assert len({ids[0], ids[1], ids[3], ids[4]}) == 4 and ids[2] == ids[1]
    assert [c["cwd"] for c in (c1, c2, c3, c4, c5)] == [real(rig.session_dir), real(rig.folder_a), real(rig.folder_a), real(rig.folder_b),
                                                        real(rig.session_dir)]
    for call, said in ((c2, "one"), (c4, "three"), (c5, "four")):    # the carry-over holds what the owner said before; nothing was lost
        assert "carried over" in call["stdin"] and f"User: {said}" in call["stdin"], call["stdin"]
    assert "carried over" not in c3["stdin"]
    assert rig.state().work_folder == "" and rig.state().turns == 5


def test_a_folder_change_is_announced_as_such_and_the_session_hook_hears_the_new_id(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="r")
    hooks = []
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    events = []
    router = Router({"claude": ClaudeConnector(cfg)}, policy(), transcripts=History(), sleep=lambda s: None,
                    events=lambda t, d: events.append((t, d)), session_hook=lambda *a: hooks.append(a))
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
    (tmp_path / "x").mkdir()
    router.chat_send(SID, Message(role="user", text="one"))
    router.folders.set(str(tmp_path / "x"))
    router.chat_send(SID, Message(role="user", text="two"))
    router.close()
    assert [d["reason"] for t, d in events if t == "connector.switch"] == ["working folder changed"]
    assert len(hooks) == 2 and hooks[0][3] != hooks[1][3]


def test_the_connector_itself_never_resumes_a_session_into_another_folder(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="r")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    connector = ClaudeConnector(cfg)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    state = connector.start(SessionSpec(session_id=SID))
    connector.send(state, Message(role="user", text="one"), folder=str(a))
    connector.send(state, Message(role="user", text="two"), folder=str(a))
    connector.send(state, Message(role="user", text="three"), folder=str(b))
    c1, c2, c3 = fake.model_calls("claude")
    assert "--session-id" in c1["argv"] and "--resume" in c2["argv"] and "--session-id" in c3["argv"] and "--resume" not in c3["argv"]
    assert c3["cwd"] == real(b)


def test_the_folder_is_read_on_every_turn_not_once(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.choose(rig.folder_a)
    rig.turn("one")
    rig.choose(rig.folder_b)
    rig.turn("two")
    assert [c["cwd"] for c in rig.calls("claude")] == [real(rig.folder_a), real(rig.folder_b)]


def test_a_folder_that_vanished_between_turns_is_not_used(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.choose(rig.folder_a)
    rig.turn("one")
    rig.folder_a.rmdir()
    rig.turn("two")
    c1, c2 = rig.calls("claude")
    assert c1["cwd"] == real(rig.folder_a)
    assert c2["cwd"] == real(rig.session_dir) and value(c2["argv"], "--tools") == ""


# ---- codex ---------------------------------------------------------------------------------------------------------------------

def test_codex_with_a_folder_is_read_only_whatever_the_policy_says_and_runs_in_it(make, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    rig = make("codex", sandbox="workspace-write")
    rig.router.chat_pin(SID, "codex")
    rig.choose(rig.folder_a)
    rig.turn("one")
    rig.turn("two")
    first, second = rig.calls("codex")
    assert value(first["argv"], "-s") == "read-only" and value(first["argv"], "-C") == real(rig.folder_a) and first["cwd"] == real(rig.folder_a)
    assert "resume" in second["argv"] and "-C" not in second["argv"] and second["cwd"] == real(rig.folder_a)
    assert 'sandbox_mode="read-only"' in second["argv"]
    assert rig.state().workdir == str(rig.session_dir)


def test_codex_without_a_folder_keeps_the_policys_sandbox_and_its_private_folder(make, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    rig = make("codex", sandbox="workspace-write")
    rig.router.chat_pin(SID, "codex")
    rig.turn("one")
    call = rig.calls("codex")[0]
    assert value(call["argv"], "-s") == "workspace-write" and value(call["argv"], "-C") == real(rig.session_dir)


def test_a_codex_thread_does_not_resume_into_another_folder(make, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    rig = make("codex")
    rig.router.chat_pin(SID, "codex")
    rig.choose(rig.folder_a)
    rig.turn("one")
    rig.choose(rig.folder_b)
    rig.turn("two")
    first, second = rig.calls("codex")
    assert "resume" not in second["argv"] and value(second["argv"], "-C") == real(rig.folder_b) and "carried over" in second["stdin"]


# ---- the org chat agent and the engine -------------------------------------------------------------------------------------------

def agent_call(function, workspace="edit"):
    """The org chat agent tags its own calls `workspace="edit"` (D127); the owner's access setting caps it, as it always did."""
    return JsonRequest(user="plan this", schema={"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
                       ctx=RouteContext(tag=CallTag(function=function, stage="plan", workspace=workspace)))


def test_the_org_chat_agents_call_runs_in_the_folder_with_read_only_tools_and_the_grounding(make, fake):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    rig = make("claude")
    rig.choose(rig.folder_a)
    rig.router.call_json(agent_call("chat_agent"))
    call = rig.calls("claude")[0]
    assert call["cwd"] == real(rig.folder_a) and value(call["argv"], "--tools") == READ and "--disallowedTools" in call["argv"]
    system = value(call["argv"], "--system-prompt")
    assert f"Working folder: {real(rig.folder_a)}" in system and "read-only" in system
    assert "--no-session-persistence" in call["argv"]                            # still a one-shot call


def test_a_teams_run_and_the_engines_calls_never_get_the_folder(make, fake):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    rig = make("claude")
    rig.choose(rig.folder_a)
    rig.router.call_json(agent_call("planner", workspace=""))
    rig.router.ask(AskRequest(user="hello", kind="text", ctx=RouteContext(tag=CallTag(function="chat_agent"))))      # a text call: the engine's path
    for call in rig.calls("claude"):
        assert call["cwd"] != real(rig.folder_a) and value(call["argv"], "--tools") == ""
        assert not {"--allowedTools", "--disallowedTools", "--restricted"} & set(call["argv"])
        assert "Working folder" not in value(call["argv"], "--system-prompt")


def test_the_org_chat_agent_with_no_folder_is_unchanged(make, fake):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    rig = make("claude")
    rig.router.call_json(agent_call("chat_agent"))
    call = rig.calls("claude")[0]
    assert value(call["argv"], "--tools") == "" and "--restricted" not in call["argv"] and "Working folder" not in value(call["argv"], "--system-prompt")


def test_offline_nothing_is_given_a_folder(tmp_path):
    from sutra_app.connectors.stub import StubConnector
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy(), connector="stub", offline=True)
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
    (tmp_path / "p").mkdir()
    router.folders.set(str(tmp_path / "p"))
    assert router.chat_folder() == ""
    router.close()


# ---- the owner lets the team change files (D125) --------------------------------------------------------------------------------

EDIT = "Read,Glob,Grep,LS,Edit,MultiEdit,Write,Bash"
GIT = ["Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"]


def test_claude_with_edit_access_may_change_files_and_run_only_the_git_reads(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.choose(rig.folder_a, access="edit")
    rig.turn()
    argv = rig.calls("claude")[0]["argv"]
    assert value(argv, "--tools") == EDIT
    assert value(argv, "--allowedTools").split(",") == ["Read", "Glob", "Grep", "LS", "Edit", "MultiEdit", "Write", *GIT]
    denied = set(value(argv, "--disallowedTools").split(","))
    assert {"PowerShell", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent"} <= denied
    assert not denied & {"Edit", "MultiEdit", "Write", "Bash"}                      # what is offered is not denied
    # the allowed tools may not do more than they say: no write into .git (its config can name a program git status runs), no git option that writes
    # a file or reads outside the repository
    assert {"Edit(.git/**)", "Edit(**/.git/**)", "Bash(git*--output*)", "Bash(git*--no-index*)", "Bash(git*--ext-diff*)", "Bash(git*--textconv*)"} <= denied
    assert value(argv, "--setting-sources") == "" and "--restricted" in argv and value(argv, "--permission-mode") == "dontAsk"


def test_codex_with_edit_access_writes_inside_the_folder_only(make, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    rig = make("codex", sandbox="read-only")
    rig.router.chat_pin(SID, "codex")
    rig.choose(rig.folder_a, access="edit")
    rig.turn()
    argv = rig.calls("codex")[0]["argv"]
    assert value(argv, "-s") == "workspace-write" and value(argv, "-C") == real(rig.folder_a)


def test_a_folder_chosen_before_the_owner_could_say_stays_read_only(make, tmp_path):
    rig = make("claude")
    rig.router.folders.set(str(rig.folder_a))
    stored = rig.router.folders.path
    stored.write_text('{"version": 1, "path": "%s"}' % real(rig.folder_a), encoding="utf-8")
    assert rig.router.folders.stored_access() == "read" and rig.router.folders.grant().edit is False
