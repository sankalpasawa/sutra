"""A step's builder tools are never wider than its grant (D380).

J2's builder asks for the whole Claude tool list. For an ordinary run that stays. For a call whose tag names a node of a project the router takes it down to what the node's frozen
grant allows, before the program is started: the real command line (made by the Claude connector, started as the fake CLI) carries the narrowed list, and an ordinary call carries
the full one. Codex runs no builder tools at all; what it can and cannot do is pinned at the end.
"""
from __future__ import annotations

import json
import os

import pytest

from sutra_app.connectors import node_tools
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import NoProviderError
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.node_tools import NARROWEST, NodeRights
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.engine.port import CallTag, CompletionRequest, ToolGrant

FULL_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebSearch", "WebFetch")
FULL_ALLOW = ("Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebSearch", "WebFetch", "WebFetch(domain:*)")
NODE_TAG = CallTag(function="W-1", role="builder", node_id="nd_0123456789ab", node_role="worker")


def policy():
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": "read-only"}},
                         "defaults": {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
                                      "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
                                      "tool_profile": "none", "idle_timeout_s": 120}, "rules": [], "rates": {}})


def value(argv, flag):
    return argv[argv.index(flag) + 1]


@pytest.fixture
def folders(tmp_path):
    root = tmp_path / "run"
    (root / "out").mkdir(parents=True)
    return os.path.realpath(root / "out"), os.path.realpath(root)


def builder_grant(folders) -> ToolGrant:
    return ToolGrant(tools=FULL_TOOLS, allow=FULL_ALLOW, cwd=folders[0], root=folders[1], usd=0.5, log_chars=10)


def rig(fake, tmp_path, rights, *names):
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    makers = {"claude": lambda: ClaudeConnector(cfg), "codex": lambda: CodexConnector(cfg, sandbox="read-only")}
    router = Router({n: makers[n]() for n in (names or ("claude",))}, policy(), sleep=lambda s: None)
    router.node_rights = rights
    return router


def run(router, grant, tag):
    return router.complete(CompletionRequest(system="s", user="build it", tag=tag, run_tools=grant))


def command_of(fake):
    call, = fake.model_calls("claude")
    return call["argv"]


# ---- the command line the program is started with ------------------------------------------------------------------------------------

def test_a_step_with_the_default_grant_is_started_with_reads_and_writes_in_its_own_folder_only(fake, tmp_path, folders):
    fake.sequence("ok_plain").reply(text="built")
    router = rig(fake, tmp_path, NodeRights((0, 1), "none"))
    try:
        run(router, builder_grant(folders), NODE_TAG)
        argv = command_of(fake)
    finally:
        router.close()
    assert value(argv, "--tools") == "Read,Write,Edit,Glob,Grep"
    allowed = value(argv, "--allowedTools").split(" ")
    assert allowed == ["Read", "Glob", "Grep", f"Edit(/{folders[0]}/**)", "Edit(./**)"]
    for tool in ("Bash", "WebSearch", "WebFetch", "WebFetch(domain:*)"):
        assert tool not in value(argv, "--tools").split(",") and tool not in allowed
    settings = json.loads(value(argv, "--settings"))
    assert settings["permissions"]["allow"] == allowed and settings["permissions"]["blockReadsOutsideWorkingDirectories"] is True


def test_an_ordinary_call_keeps_the_whole_list(fake, tmp_path, folders):
    """No node in the tag: byte for byte what J2 asked for, with a router that has rights set and one that has none."""
    for rights in (NodeRights((0, 1), "none"), None):
        fake.sequence("ok_plain").reply(text="built")
        router = rig(fake, tmp_path, rights)
        try:
            run(router, builder_grant(folders), CallTag(function="W-1", role="builder"))
        finally:
            router.close()
        argv = fake.model_calls("claude")[-1]["argv"]
        assert value(argv, "--tools") == ",".join(FULL_TOOLS)
        assert value(argv, "--allowedTools") == " ".join(FULL_ALLOW)
        assert json.loads(value(argv, "--settings"))["permissions"]["allow"] == list(FULL_ALLOW)


def test_a_step_whose_rights_are_not_known_gets_the_narrowest_list(fake, tmp_path, folders):
    fake.sequence("ok_plain").reply(text="built")
    router = rig(fake, tmp_path, None)
    try:
        run(router, builder_grant(folders), NODE_TAG)
        argv = command_of(fake)
    finally:
        router.close()
    assert value(argv, "--tools") == "Read,Write,Edit,Glob,Grep" and "Bash" not in value(argv, "--allowedTools")


@pytest.mark.parametrize("rights, shell, web", [
    (NodeRights((0, 1, 2, 3), "git_reads"), False, False),         # tier 3 is the four git reads of the owner's folder, not a shell
    (NodeRights((0, 1, 2, 3, 4), "git_reads"), False, True),       # tier 4 opens the web tools
    (NodeRights((0, 1, 3), "sandboxed_builder"), True, False),     # a shell level that no grant holds today
])
def test_the_shell_needs_a_shell_level_and_the_web_needs_tier_four(fake, tmp_path, folders, rights, shell, web):
    fake.sequence("ok_plain").reply(text="built")
    router = rig(fake, tmp_path, rights)
    try:
        run(router, builder_grant(folders), NODE_TAG)
        argv = command_of(fake)
    finally:
        router.close()
    offered = value(argv, "--tools").split(",")
    assert ("Bash" in offered) is shell and ("WebSearch" in offered and "WebFetch" in offered) is web
    assert ("Bash" in value(argv, "--allowedTools").split(" ")) is shell
    assert ("WebFetch(domain:*)" in value(argv, "--allowedTools").split(" ")) is web
    assert {"Read", "Glob", "Grep"} <= set(offered)


# ---- the pure rule -------------------------------------------------------------------------------------------------------------

def test_a_tool_the_rule_does_not_name_is_never_offered(folders):
    odd = ToolGrant(tools=("Read", "Task", "TodoWrite", "mcp__x"), allow=("Read", "Task"), cwd=folders[0], root=folders[1], usd=0.5, log_chars=10)
    narrowed = node_tools.narrow(odd, NodeRights((0, 1, 2, 3, 4), "sandboxed_builder"))
    assert narrowed.tools == ("Read",) and narrowed.allow == ("Read",)


def test_the_narrowed_grant_is_a_copy_and_the_engines_own_is_untouched(folders):
    grant = builder_grant(folders)
    narrowed = node_tools.narrow(grant, NARROWEST)
    assert grant.tools == FULL_TOOLS and grant.allow == FULL_ALLOW
    assert (narrowed.cwd, narrowed.root, narrowed.usd, narrowed.log_chars, narrowed.sandbox) == (grant.cwd, grant.root, grant.usd, grant.log_chars, grant.sandbox)


def test_the_words_of_the_grant_line_are_true_for_each_case():
    assert node_tools.words(NARROWEST) == "reads; writes only in its own folder; no commands; no web"
    assert node_tools.words(NodeRights((0, 1, 4), "none")) == "reads; writes only in its own folder; no commands; web"
    assert node_tools.owner_words(NARROWEST) == "This step can look at the files it is given and write its own working files in a scratch space of its own. It cannot run commands or use the web."
    assert "search and read the web" in node_tools.owner_words(NodeRights((0, 1, 4), "none"))


# ---- Codex ---------------------------------------------------------------------------------------------------------------------

def test_a_builder_tools_call_of_a_step_never_reaches_codex(fake, tmp_path, folders):
    """Codex cannot filter per tool, so it is never given the builder tools call: with Claude unusable the call fails and no Codex program is started."""
    fake.auth(claude="signed_out")
    router = rig(fake, tmp_path, NodeRights((0, 1), "none"), "claude", "codex")
    try:
        with pytest.raises(NoProviderError):
            run(router, builder_grant(folders), NODE_TAG)
        assert not fake.model_calls("codex") and not fake.model_calls("claude")
    finally:
        router.close()


def test_a_codex_step_with_a_read_folder_runs_in_the_read_only_sandbox(fake, tmp_path):
    """What Codex CAN do for a step whose grant only reads: its sandbox is read-only (no file is written, no network). What it cannot do: narrow a write to a path (D342)."""
    from sutra_app.connectors.workdir import Folder
    fake.sequence("ok_plain").reply(text="ok")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    work = tmp_path / "owner"
    work.mkdir()
    CodexConnector(cfg, sandbox="read-only").call_text("look", folder=Folder(str(work), edit=False))
    argv = fake.model_calls("codex")[-1]["argv"]
    assert value(argv, "-s") == "read-only" and "workspace-write" not in argv and "danger-full-access" not in " ".join(argv)
