"""What the router tells an engine call's progress callback and its finish hooks (D133, WP9).

`{"chars", "text"}` is unchanged (J2's contract); a tool call of the model is forwarded as `{"tool": title}` so a live view can say what an agent is
doing; Claude's own StructuredOutput call is not work to show. `Router.finish_hooks` hear the tag of every engine call (`complete`) when it ends,
answered or failed, and a hook that raises never fails the call."""
from __future__ import annotations

import sys

import pytest

from sutra_app.connectors.models import ConnectorConfig, ConnectorEvent
from sutra_app.connectors.policy import load_default_policy
from sutra_app.connectors.router import Router, _progress, tool_title
from sutra_app.connectors.stub import StubConnector
from sutra_app.engine.port import CallTag, CompletionRequest, ModelError


def events_of(*events, folder=""):
    got = []
    on_event = _progress(got.append, folder)
    for event in events:
        on_event(event)
    return got


def tool(**data):
    return ConnectorEvent(kind="tool_call", data=data)


def test_a_tool_call_is_forwarded_with_its_name_and_what_it_is_about():
    got = events_of(tool(name="Read", input={"file_path": "src/app.py"}), tool(name="Grep", input={"pattern": "def main", "path": "."}),
                    tool(name="LS", input={}), tool(type="command_execution", id="x"))
    assert got == [{"tool": "Reading src/app.py"}, {"tool": "Using Grep"}, {"tool": "Using LS"}, {"tool": "Using command_execution"}]


def test_a_long_or_multiline_tool_line_is_one_short_line():
    title = tool_title({"name": "Bash", "input": {"command": "git log\n  --oneline " + "x" * 400}})
    assert title == "Running git"


RUN = "/home/someone/.sutra-pro-beta/departments/web/runs/j2-1"


@pytest.mark.parametrize("data, line", [
    ({"name": "Bash", "input": {"command": "python3 - <<'E'\np='index.html';s=open(p).read()\nE"}}, "Running python3"),      # never the heredoc
    ({"name": "Bash", "input": {"command": "/usr/bin/python3 build.py --out " + RUN}}, "Running python3"),                       # the program, no path or arguments
    ({"name": "Bash", "input": {"command": "FOO=1 node x.js"}}, "Running node"),
    ({"name": "Write", "input": {"file_path": RUN + "/site/index.html"}}, "Writing site/index.html"),                        # relative to the run folder
    ({"name": "Read", "input": {"file_path": "/home/someone/notes/plan.md"}}, "Reading plan.md"),                           # outside: the basename only
    ({"name": "Edit", "input": {"file_path": RUN + "/src/a.py", "old_string": "x", "new_string": "y"}}, "Editing src/a.py"),
    ({"name": "Mystery", "input": {"command_line": "--token abc"}}, "Using Mystery"),                                       # an unknown tool: its name only
])
def test_a_live_tool_line_is_an_action_and_a_file_never_a_command_body_or_a_home_path(data, line):
    """D453 (the owner's live test): the line names the action and the file; a run's paths are relative to the call's folder."""
    assert tool_title(data, RUN) == line
    assert events_of(tool(**data), folder=RUN) == [{"tool": line}]


def test_claudes_structured_output_call_is_not_shown_as_work():
    assert events_of(tool(name="StructuredOutput", input={"answer": "ok"})) == []


def test_the_text_events_are_as_before_and_tool_calls_do_not_disturb_them():
    got = events_of(ConnectorEvent(kind="started", data={}), ConnectorEvent(kind="text_delta", data={"text": "ab"}), tool(name="Read", input={"path": "a"}),
                    ConnectorEvent(kind="text_delta", data={"text": "cd"}), ConnectorEvent(kind="text", data={"text": "abcd"}))
    assert got == [{"chars": 2, "text": "ab"}, {"tool": "Reading a"}, {"chars": 4, "text": "abcd"}]


def test_no_callback_no_listener():
    assert _progress(None) is None


@pytest.fixture
def router(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    r = Router({"stub": StubConnector(cfg)}, load_default_policy(), connector="stub")
    yield r
    r.close()


def request(function="W-3"):
    return CompletionRequest(system="s", user="u", scripted=lambda: "answer", tag=CallTag(function=function))


def test_finish_hooks_hear_the_tag_of_every_call_that_ends(router):
    heard = []
    router.finish_hooks.append(heard.append)
    router.complete(request("W-3"))
    router.complete(request("identity"))
    assert [t.function for t in heard] == ["W-3", "identity"]


def test_finish_hooks_hear_a_call_that_failed_too(router):
    heard = []
    router.finish_hooks.append(heard.append)
    router._connectors["stub"].fail_next("quota")
    with pytest.raises(ModelError):
        router.complete(request("W-5"))
    assert [t.function for t in heard] == ["W-5"]


def test_a_hook_that_raises_does_not_fail_the_call_or_stop_the_others(router):
    heard = []

    def boom(tag):
        raise RuntimeError("no")

    router.finish_hooks.extend([boom, heard.append])
    assert router.complete(request()).text == "answer" and len(heard) == 1


def test_progress_ends_with_the_text_and_no_extra_event(router):
    seen = []
    router.complete(request(), seen.append)
    assert seen[-1] == {"chars": 6, "text": "answer"}                  # J2's contract: the last progress event is the text
