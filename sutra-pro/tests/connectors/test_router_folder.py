"""The folder policy of the router (D127, WP2): a call's tag says the most it may do in the owner's working folder, the owner's access setting caps it.

What is proved: the matrix tag x access x folder set x offline (`Router.folder_for`); the engine's two text paths (plain text and text with a schema, the
way `complete()` sends them) and the org chat agent's JSON path run in the folder with the right tools, on the claude and the codex argv; the grounding is
added AFTER the egress check and J2's own system text stays byte for byte; with no folder, or a tag that asks for none, the call is identical to the one
a router that never heard of folders makes; a folder chosen mid-run applies from the next call; `port_from_config` gives a live port the folder store."""
from __future__ import annotations

import json
import os

import pytest
from pydantic import ValidationError

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.egress import Egress
from sutra_app.connectors.engine_port import port_from_config
from sutra_app.connectors.models import AskRequest, ConnectorConfig, JsonRequest, RouteContext
from sutra_app.connectors.orchestrator_port import build_tag
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.workdir import Folder, WorkFolder
from sutra_app.engine.port import CallTag, CompletionRequest, PortSpec

READ = "Read,Glob,Grep,LS"
EDIT = "Read,Glob,Grep,LS,Edit,MultiEdit,Write,Bash"
J2_SYSTEM = "You are J2.a, the intake agent."
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


def policy(sandbox="read-only"):
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": sandbox}},
                         "defaults": {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
                                      "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
                                      "tool_profile": "none", "idle_timeout_s": 120}, "rules": [], "rates": {}})


def value(argv, flag):
    return argv[argv.index(flag) + 1]


def real(path):
    return os.path.realpath(path)


def tag(workspace="", function="identity", purpose="agent_turn"):
    return CallTag(function=function, stage="website", workspace=workspace, purpose=purpose)


def text_req(workspace="", system=J2_SYSTEM, schema=None, function="identity", purpose="agent_turn"):
    return AskRequest(user="the brief", system=system, kind="text" if schema is None else "json", schema=schema,
                      ctx=RouteContext(tag=tag(workspace, function, purpose)))


class Rig:
    def __init__(self, fake, tmp_path, *names, folders=True, egress=False, sandbox="read-only"):
        self.fake = fake
        self.cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
        makers = {"claude": lambda: ClaudeConnector(self.cfg), "codex": lambda: CodexConnector(self.cfg, sandbox=sandbox)}
        self.router = Router({n: makers[n]() for n in names}, policy(sandbox), sleep=lambda s: None)
        if folders:
            self.router.folders = WorkFolder(self.cfg.data_dir, self.cfg.resolved_work_root())
        if egress:
            self.router.egress = Egress(self.cfg.data_dir / "connectors" / "egress.jsonl")
        self.folder = tmp_path / "project"
        self.folder.mkdir()

    def choose(self, access="read"):
        self.router.folders.set(str(self.folder), access=access)

    def calls(self, cli="claude"):
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


# ---- the tag ------------------------------------------------------------------------------------------------------------------

def test_a_tag_asks_for_nothing_by_default_and_refuses_a_word_it_does_not_know():
    assert CallTag().workspace == "" and CallTag(function="audit").workspace == ""
    assert CallTag(workspace="read").workspace == "read" and CallTag(workspace="edit").workspace == "edit"
    with pytest.raises(ValidationError):
        CallTag(workspace="write")


# ---- the matrix: tag x access x folder x offline -----------------------------------------------------------------------------------

@pytest.mark.parametrize("workspace,access,expected", [
    ("", "read", None), ("", "edit", None),
    ("read", "read", "ro"), ("read", "edit", "ro"),              # a read call never edits, whatever the owner allowed
    ("edit", "read", "ro"),                                      # the owner's access caps what the tag asks for
    ("edit", "edit", "rw"),
])
def test_folder_for_the_tag_asked_and_the_owners_access_caps_it(tmp_path, workspace, access, expected):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy())
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
    (tmp_path / "p").mkdir()
    router.folders.set(str(tmp_path / "p"), access=access)
    got = router.folder_for(tag(workspace))
    if expected is None:
        assert got == ""
    else:
        assert str(got) == real(tmp_path / "p") and isinstance(got, Folder) and got.edit is (expected == "rw")


@pytest.mark.parametrize("workspace", ["", "read", "edit"])
def test_no_folder_set_means_none_for_every_tag(tmp_path, workspace):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy())
    assert router.folder_for(tag(workspace)) == ""                       # no store at all
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
    assert router.folder_for(tag(workspace)) == ""                       # a store with nothing chosen


@pytest.mark.parametrize("workspace", ["read", "edit"])
def test_an_offline_router_never_gives_a_folder(tmp_path, workspace):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy(), connector="stub", offline=True)
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
    (tmp_path / "p").mkdir()
    router.folders.set(str(tmp_path / "p"), access="edit")
    assert router.folder_for(tag(workspace)) == "" and router.chat_folder() == ""


def test_a_folder_that_has_gone_is_none(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy())
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
    gone = tmp_path / "gone"
    gone.mkdir()
    router.folders.set(str(gone))
    gone.rmdir()
    assert router.folder_for(tag("read")) == ""


# ---- the engine's plain text path -------------------------------------------------------------------------------------------------

def test_a_read_call_runs_in_the_folder_with_the_four_read_tools_and_the_grounding_after_j2s_text(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.choose("edit")
    rig.router.ask(text_req("read"))
    call, = rig.calls()
    argv = call["argv"]
    assert call["cwd"] == real(rig.folder)
    assert value(argv, "--tools") == READ and value(argv, "--allowedTools") == READ and "--restricted" in argv
    assert "--no-session-persistence" in argv                                                    # still a one-shot call
    system = value(argv, "--system-prompt")
    assert system.startswith(J2_SYSTEM + "\n\nWorking folder: " + real(rig.folder)) and "read-only" in system   # J2's text first, ours after it


def test_an_edit_call_may_change_files_only_when_the_owner_allowed_it(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.choose("edit")
    rig.router.ask(text_req("edit"))
    rig.choose("read")                                           # the owner narrows it: the very next call is capped
    rig.router.ask(text_req("edit"))
    allowed, capped = rig.calls()
    assert value(allowed["argv"], "--tools") == EDIT and "can create and change files" in value(allowed["argv"], "--system-prompt")
    assert value(capped["argv"], "--tools") == READ and "read-only" in value(capped["argv"], "--system-prompt")
    assert value(capped["argv"], "--allowedTools") == READ
    assert {"Edit", "MultiEdit", "Write", "Bash"} <= set(value(capped["argv"], "--disallowedTools").split(","))


def test_a_folder_chosen_in_the_middle_of_a_run_applies_from_the_next_call(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.router.ask(text_req("read"))                             # nothing chosen yet
    rig.choose("read")
    rig.router.ask(text_req("read"))
    rig.router.folders.clear()
    rig.router.ask(text_req("read"))
    first, second, third = rig.calls()
    assert first["cwd"] != real(rig.folder) and value(first["argv"], "--tools") == ""
    assert second["cwd"] == real(rig.folder) and value(second["argv"], "--tools") == READ
    assert third["cwd"] != real(rig.folder) and value(third["argv"], "--tools") == ""


def test_helper_calls_and_a_tag_with_no_workspace_get_no_folder(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    rig.choose("edit")
    rig.router.ask(text_req(""))
    rig.router.ask(text_req("", function="summariser", purpose="summary"))
    for call in rig.calls():
        assert call["cwd"] != real(rig.folder) and value(call["argv"], "--tools") == "" and "Working folder" not in value(call["argv"], "--system-prompt")
        assert not {"--allowedTools", "--disallowedTools", "--restricted"} & set(call["argv"])


def test_the_projects_own_instructions_go_with_the_folder(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude")
    (rig.folder / "CLAUDE.md").write_text("Always run the linter before you say you are done.", encoding="utf-8")
    rig.choose("read")
    rig.router.ask(text_req("read"))
    assert "Always run the linter" in value(rig.calls()[0]["argv"], "--system-prompt")


# ---- the engine's text path that carries a schema (what `complete()` sends with a json_schema) ---------------------------------------------

def test_a_text_call_with_a_schema_gets_the_folder_too(make, fake):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    rig = make("claude")
    rig.choose("read")
    rig.router.ask(text_req("read", schema=SCHEMA))
    call, = rig.calls()
    argv = call["argv"]
    assert "--json-schema" in argv and call["cwd"] == real(rig.folder) and value(argv, "--tools") == READ
    system = value(argv, "--system-prompt")
    assert system.startswith(J2_SYSTEM + "\n\nWorking folder: ") and "--no-session-persistence" in argv


def test_a_text_call_with_a_schema_and_no_folder_is_as_before(make, fake):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    rig = make("claude")
    rig.router.ask(text_req("read", schema=SCHEMA))              # asks for the folder, none is set
    call, = rig.calls()
    assert value(call["argv"], "--system-prompt") == J2_SYSTEM and value(call["argv"], "--tools") == "" and "--restricted" not in call["argv"]


def test_complete_carries_the_workspace_from_the_engines_request_to_the_cli(fake, tmp_path):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    spec = PortSpec(mock=False, connector="claude", run_id="j2-20261109-000000-ab12", dept_id="web", data_dir=str(tmp_path / "data"))
    port = port_from_config(spec, ConnectorConfig(**fake.config_kwargs(tmp_path)), sleep=lambda s: None)
    try:
        folder = tmp_path / "proj"
        folder.mkdir()
        port.router.folders.set(str(folder), access="edit")
        port.complete(CompletionRequest(system=J2_SYSTEM, user="u", json_schema=SCHEMA, tag=CallTag(function="W-3", workspace="edit")))
        call, = fake.model_calls("claude")
        assert call["cwd"] == real(folder) and value(call["argv"], "--tools") == EDIT
    finally:
        port.close()


# ---- the grounding is added after the egress check -----------------------------------------------------------------------------------------

def test_the_egress_row_and_the_text_it_checks_are_j2s_alone_and_the_grounding_comes_after(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude", egress=True)
    rig.choose("read")
    key = "sk-abcdefgh12345678"
    system = f"{J2_SYSTEM} The owner's key is {key}."                # a shape in J2's own text: observed, never replaced (byte for byte)
    rig.router.ask(text_req("read", system=system))
    sent = value(rig.calls()[0]["argv"], "--system-prompt")
    assert sent.startswith(system + "\n\n") and key in sent                                       # J2's text untouched
    row, = rig.router.egress.rows()
    assert row["mode"] == "observe" and row["bytes"] == len((system + "the brief").encode("utf-8"))  # the audit counted J2's text, not the folder's


def test_a_credential_in_the_projects_instructions_does_not_leave_with_the_grounding(make, fake):
    fake.sequence("ok_plain").reply(text="r")
    rig = make("claude", egress=True)
    (rig.folder / "CLAUDE.md").write_text("Use the deploy account. password = abcdefghijkl1234 and token sk-abcdefgh12345678.", encoding="utf-8")
    rig.choose("read")
    rig.router.ask(text_req("read"))
    system = value(rig.calls()[0]["argv"], "--system-prompt")
    assert "abcdefghijkl1234" not in system and "sk-abcdefgh12345678" not in system and "[redacted:" in system and "Use the deploy account" in system


# ---- with no folder the call is what it was ------------------------------------------------------------------------------------------------

def _argv_of_one_call(fake, tmp_path, name, *, folders, set_folder, workspace, schema=None):
    sub = tmp_path / name
    sub.mkdir()
    fake.sequence("ok_structured" if schema else "ok_plain").reply(text="r", json={"answer": "ok"} if schema else None)
    rig = Rig(fake, sub, "claude", folders=folders)
    try:
        if set_folder:
            rig.choose("edit")
        rig.router.ask(text_req(workspace, schema=schema))
        call = rig.calls()[-1]
        return call["argv"], call["stdin"], os.path.relpath(call["cwd"], real(sub)) if call["cwd"].startswith(real(sub)) else call["cwd"]
    finally:
        rig.close()


@pytest.mark.parametrize("schema", [None, SCHEMA])
def test_the_engines_calls_are_byte_identical_with_no_folder(fake, tmp_path, schema):
    """A router that never heard of folders, one with a store and nothing chosen, one with a folder chosen whose tag asks for none, and one whose tag
    asks while no folder is set all send the same argv and the same stdin."""
    base = _argv_of_one_call(fake, tmp_path, "a", folders=False, set_folder=False, workspace="", schema=schema)
    for name, kw in (("b", dict(folders=True, set_folder=False, workspace="")), ("c", dict(folders=True, set_folder=True, workspace="")),
                     ("d", dict(folders=True, set_folder=False, workspace="read")), ("e", dict(folders=True, set_folder=False, workspace="edit"))):
        argv, stdin, cwd = _argv_of_one_call(fake, tmp_path, name, schema=schema, **kw)
        assert (argv, stdin) == (base[0], base[1]), name
        assert "Working folder" not in value(argv, "--system-prompt") and value(argv, "--system-prompt") == J2_SYSTEM


def test_a_connector_that_takes_no_folder_is_not_handed_one_when_there_is_none(tmp_path):
    seen = []

    class Strict(StubConnector):
        def call_text(self, prompt, *, system="", ctx=None, scripted=None, **kw):       # the signature of a connector written before `folder`
            seen.append(kw)
            return super().call_text(prompt, system=system, ctx=ctx, scripted=scripted, **kw)

    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": Strict(cfg)}, policy(), connector="stub")
    router.ask(text_req("edit"))
    assert "folder" not in seen[0]


# ---- codex -------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("workspace,access,sandbox", [("read", "edit", "read-only"), ("edit", "read", "read-only"), ("edit", "edit", "workspace-write")])
def test_codex_text_path_runs_in_the_folder_with_the_sandbox_the_tag_and_the_owner_allow(make, fake, workspace, access, sandbox):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    rig = make("codex", sandbox="read-only")
    rig.choose(access)
    rig.router.ask(text_req(workspace))
    call, = rig.calls("codex")
    argv = call["argv"]
    assert value(argv, "-s") == sandbox and value(argv, "-C") == real(rig.folder)
    assert f"<system>\n{J2_SYSTEM}\n\nWorking folder: {real(rig.folder)}" in call["stdin"]


def test_codex_with_no_folder_keeps_the_policys_sandbox_and_its_own_folder(make, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    rig = make("codex", sandbox="workspace-write")
    rig.router.ask(text_req("edit"))
    call, = rig.calls("codex")
    assert value(call["argv"], "-s") == "workspace-write" and value(call["argv"], "-C") != real(rig.folder)
    assert "Working folder" not in call["stdin"]


# ---- the org chat agent (JSON path), now by its own tag ---------------------------------------------------------------------------------------

def test_the_org_chat_agent_tags_itself_edit_and_nobody_else_does():
    assert build_tag("chat_agent", "decide", {"purpose": "chat_plan"}).workspace == "edit"
    assert build_tag("planner", "decide", {"purpose": "chat_plan"}).workspace == ""


@pytest.mark.parametrize("access,tools", [("read", READ), ("edit", EDIT)])
def test_the_org_chat_agents_json_call_follows_the_owners_access(make, fake, access, tools):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    rig = make("claude")
    rig.choose(access)
    rig.router.call_json(JsonRequest(user="plan this", schema=SCHEMA, ctx=RouteContext(tag=build_tag("chat_agent", "plan", {}))))
    call, = rig.calls()
    assert call["cwd"] == real(rig.folder) and value(call["argv"], "--tools") == tools
    assert f"Working folder: {real(rig.folder)}" in value(call["argv"], "--system-prompt")


def test_a_json_call_by_any_other_function_is_not_given_the_folder_by_its_name(make, fake):
    fake.sequence("ok_structured").reply(json={"answer": "ok"})
    rig = make("claude")
    rig.choose("edit")
    rig.router.call_json(JsonRequest(user="p", schema=SCHEMA, ctx=RouteContext(tag=CallTag(function="chat_agent", stage="plan"))))   # the name alone is nothing
    call, = rig.calls()
    assert call["cwd"] != real(rig.folder) and value(call["argv"], "--tools") == ""


# ---- port_from_config ---------------------------------------------------------------------------------------------------------------------

def test_a_live_port_reads_the_folder_store_and_a_stub_only_port_has_none(fake, tmp_path):
    spec = PortSpec(mock=False, connector="claude", run_id="j2-20261109-000000-ab12", dept_id="web", data_dir=str(tmp_path / "data"))
    live = port_from_config(spec, ConnectorConfig(**fake.config_kwargs(tmp_path)))
    stub = port_from_config(spec.model_copy(update={"mock": True}), ConnectorConfig(data_dir=tmp_path / "data2"))
    try:
        assert isinstance(live.router.folders, WorkFolder)
        assert live.router.folders.path == tmp_path / "data" / "connectors" / "workdir.json"      # the file the server's Settings writes
        assert stub.router.folders is None and stub.router.folder_for(tag("edit")) == ""
    finally:
        live.close()
        stub.close()


def test_the_engine_process_sees_a_folder_the_server_wrote_after_it_started(fake, tmp_path):
    """The server's WorkFolder and the engine's are two objects on one file: a choice made while the run is going applies from its next call."""
    fake.sequence("ok_plain").reply(text="r")
    spec = PortSpec(mock=False, connector="claude", run_id="j2-20261109-000000-ab12", dept_id="web", data_dir=str(tmp_path / "data"))
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    port = port_from_config(spec, cfg, sleep=lambda s: None)
    try:
        folder = tmp_path / "later"
        folder.mkdir()
        request = CompletionRequest(system=J2_SYSTEM, user="u", tag=CallTag(function="identity", workspace="read"))
        port.complete(request)
        WorkFolder(tmp_path / "data", cfg.resolved_work_root()).set(str(folder), access="read")      # the server, in another process
        port.complete(request)
        before, after = fake.model_calls("claude")
        assert value(before["argv"], "--tools") == "" and value(after["argv"], "--tools") == READ and after["cwd"] == real(folder)
    finally:
        port.close()
