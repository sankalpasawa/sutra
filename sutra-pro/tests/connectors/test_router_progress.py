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


def events_of(*events):
    got = []
    on_event = _progress(got.append)
    for event in events:
        on_event(event)
    return got


def tool(**data):
    return ConnectorEvent(kind="tool_call", data=data)


def test_a_tool_call_is_forwarded_with_its_name_and_what_it_is_about():
    got = events_of(tool(name="Read", input={"file_path": "src/app.py"}), tool(name="Grep", input={"pattern": "def main", "path": "."}),
                    tool(name="LS", input={}), tool(type="command_execution", id="x"))
    assert got == [{"tool": "Read src/app.py"}, {"tool": "Grep def main"}, {"tool": "LS"}, {"tool": "command_execution"}]


def test_a_long_or_multiline_tool_line_is_one_short_line():
    title = tool_title({"name": "Bash", "input": {"command": "git log\n  --oneline " + "x" * 400}})
    assert "\n" not in title and len(title) <= 120 and title.startswith("Bash git log --oneline x")


def test_claudes_structured_output_call_is_not_shown_as_work():
    assert events_of(tool(name="StructuredOutput", input={"answer": "ok"})) == []


def test_the_text_events_are_as_before_and_tool_calls_do_not_disturb_them():
    got = events_of(ConnectorEvent(kind="started", data={}), ConnectorEvent(kind="text_delta", data={"text": "ab"}), tool(name="Read", input={"path": "a"}),
                    ConnectorEvent(kind="text_delta", data={"text": "cd"}), ConnectorEvent(kind="text", data={"text": "abcd"}))
    assert got == [{"chars": 2, "text": "ab"}, {"tool": "Read a"}, {"chars": 4, "text": "abcd"}]


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
