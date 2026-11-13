"""llm.py: J2's `llm` API over a ModelPort (engine.md 4.2; S1-contracts-10; S2-models-12; S4-fnodes-07).

`ask` keeps J2's call syntax, builds a tagged CompletionRequest and hands it to the configured port; `ScriptedPort` is J2's
mock mode as a port. The library's `extract_json` and `close_json` are tested once, in tests/library/test_lib_replies.py:
here we only check that this module re-exports those objects.
"""
import ast
import inspect
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.engine import llm
from sutra_app.engine.llm import ScriptedPort
from sutra_app.engine.port import (
    CallTag, CompletionRequest, CompletionResult, ModelError, ModelTimeout, NoModelAvailable, PortInfo, PreflightResult,
)
from sutra_app.library import replies

pytestmark = pytest.mark.usefixtures("clean_env", "llm_reset")


class Recorder:
    """A real-looking port (not mock): keeps each request and answers with `reply`."""

    def __init__(self, reply=None, *, mock=False, provider="claude", model="sonnet"):
        self.requests, self.progress, self.reply = [], [], reply
        self._info = PortInfo(provider=provider, model=model, mock=mock)

    def describe(self):
        return self._info

    def preflight(self):
        return PreflightResult(ok=True, message="ok", providers=[])

    def complete(self, req, on_progress=None):
        self.requests.append(req)
        self.progress.append(on_progress)
        reply = self.reply
        if isinstance(reply, Exception):
            raise reply
        return reply if reply is not None else CompletionResult(text="reply")

    def close(self):
        pass


# ---- the call syntax ------------------------------------------------------------------------------------------------

def test_ask_signature_is_j2s_plus_a_keyword_only_tag():
    """J2's own signature, `timeout` (sync 5, D170) included."""
    sig = inspect.signature(llm.ask)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["system", "user", "mock", "max_tokens", "effort", "on_progress", "json_mode", "images",
                                        "schema", "timeout", "tag"]
    assert {p.name: p.default for p in params if p.default is not p.empty} == {
        "max_tokens": 1500, "effort": "high", "on_progress": None, "json_mode": False, "images": None, "schema": None,
        "timeout": None, "tag": None}
    assert all(p.kind is p.POSITIONAL_OR_KEYWORD for p in params[:-1])
    assert params[-1].kind is params[-1].KEYWORD_ONLY


def test_ask_builds_the_request_from_j2s_arguments():
    port = Recorder()
    llm.configure(port)
    progress = lambda event: None
    mock = lambda: "scripted"
    llm.ask("the system", "the user", mock, 900, "low", progress, True, None, {"type": "object"})
    (req,) = port.requests
    assert isinstance(req, CompletionRequest)
    assert (req.system, req.user, req.max_tokens, req.effort, req.json_mode) == ("the system", "the user", 900, "low", True)
    assert (req.json_schema, req.images, req.timeout_s, req.allowance) == ({"type": "object"}, [], None, None)
    assert req.scripted is mock
    assert port.progress == [progress]


def test_ask_defaults_are_j2s():
    port = Recorder()
    llm.configure(port)
    llm.ask("s", "u", None)
    (req,) = port.requests
    assert (req.max_tokens, req.effort, req.json_mode, req.json_schema, req.images, req.scripted) == (1500, "high", False, None, [], None)
    assert port.progress == [None]


def test_a_real_reply_is_stripped():
    llm.configure(Recorder(CompletionResult(text="  the text \n")))
    assert llm.ask("s", "u", lambda: "mock") == "the text"


def test_the_mock_reply_comes_back_unstripped_as_in_j2():
    llm.configure(mock=True)
    assert llm.ask("s", "u", lambda: "  hello \n") == "  hello \n"
    llm.configure(ScriptedPort(), mock=True)
    assert llm.ask("s", "u", lambda: "\n{\"a\": 1}\n") == "\n{\"a\": 1}\n"


def test_an_empty_mock_reply_is_returned_as_it_is():
    llm.configure(mock=True)
    assert llm.ask("s", "u", lambda: "") == ""


def test_a_real_empty_reply_is_an_error_like_j2s_providers():
    llm.configure(Recorder(CompletionResult(text=" \n", provider="claude", model="sonnet", input_tokens=5)))
    with pytest.raises(llm.EmptyReply) as caught:
        llm.ask("s", "u", lambda: "mock")
    assert isinstance(caught.value, ModelError) and caught.value.code == "empty_reply" and "claude" in str(caught.value)
    assert llm.LAST_META == {"model": "sonnet", "provider": "claude", "input_tokens": 5}      # saved with the failed reply


def test_a_port_error_passes_through_unchanged():
    err = ModelError("the model is broken")
    llm.configure(Recorder(err))
    llm.LAST_META["stale"] = 1
    with pytest.raises(ModelError) as caught:
        llm.ask("s", "u", lambda: "mock")
    assert caught.value is err
    assert llm.LAST_META == {}


# ---- timeout, CallTimeout and can_read_files (D170) -----------------------------------------------------------------------

def test_timeout_becomes_the_requests_timeout_s_and_none_or_zero_is_no_limit():
    port = Recorder()
    llm.configure(port)
    llm.ask("s", "u", None, timeout=45)
    llm.ask("s", "u", None)
    llm.ask("s", "u", None, timeout=0)
    assert [r.timeout_s for r in port.requests] == [45.0, None, None]


def test_a_timeout_error_of_the_port_is_raised_as_call_timeout_with_the_cause_kept():
    err = ModelTimeout("took too long")
    llm.configure(Recorder(err))
    llm.LAST_META["stale"] = 1
    with pytest.raises(llm.CallTimeout, match="took too long") as caught:
        llm.ask("s", "u", lambda: "mock")
    assert caught.value.__cause__ is err and isinstance(caught.value, RuntimeError) and not isinstance(caught.value, ModelError)
    assert llm.LAST_META == {}
    assert "CallTimeout" in llm.__all__ and "can_read_files" in llm.__all__


def test_every_other_error_code_is_unchanged_next_to_a_timeout_limit():
    err = NoModelAvailable("none")
    llm.configure(Recorder(err))
    with pytest.raises(NoModelAvailable) as caught:
        llm.ask("s", "u", None, timeout=5)
    assert caught.value is err


def test_can_read_files_is_false_in_every_mode_and_reads_files_is_not_defined():
    assert llm.can_read_files() is False
    llm.configure(Recorder(provider="claude"))
    assert llm.can_read_files() is False
    llm.configure(mock=True)
    assert llm.can_read_files() is False
    assert not hasattr(llm, "READS_FILES")


def test_bad_arguments_fail_before_the_port_is_called():
    port = Recorder()
    llm.configure(port)
    with pytest.raises(ValidationError):
        llm.ask("s", "u", None, effort="medium")
    with pytest.raises(ValidationError):
        llm.ask("s", "u", None, max_tokens=0)
    assert port.requests == []


# ---- LAST_META --------------------------------------------------------------------------------------------------------

def test_last_meta_is_cleared_and_then_filled_from_the_result():
    llm.configure(Recorder(CompletionResult(
        text="x", model="sonnet", provider="claude", input_tokens=120, output_tokens=7, usd=0.012, duration_ms=800,
        session_id="s1", structured={"provider": "claude", "subtype": "success", "present": True}, note="n", detail={"a": 1})))
    llm.LAST_META["stale"] = True
    llm.ask("s", "u", lambda: "mock")
    assert llm.LAST_META == {"model": "sonnet", "provider": "claude", "input_tokens": 120, "output_tokens": 7, "usd": 0.012,
                             "duration_ms": 800, "structured": {"provider": "claude", "subtype": "success", "present": True}}
    assert llm.LAST_META is llm.LAST_META and isinstance(llm.LAST_META, dict)


def test_last_meta_keeps_only_what_the_result_reports():
    llm.configure(Recorder(CompletionResult(text="x", model="codex-model")))
    llm.ask("s", "u", lambda: "mock")
    assert llm.LAST_META == {"model": "codex-model"}


def test_last_meta_is_cleared_by_every_call():
    port = Recorder(CompletionResult(text="x", model="m"))
    llm.configure(port)
    llm.ask("s", "u", None)
    port.reply = CompletionResult(text="y")
    llm.ask("s", "u", None)
    assert llm.LAST_META == {}


def test_a_mock_call_leaves_last_meta_empty_whatever_the_port_reports():
    """J2 reported nothing for a mock reply; the stub connector reports tokens, ScriptedPort too, and neither shows."""
    llm.configure(Recorder(CompletionResult(text="x", model="scripted", provider="stub", input_tokens=3, output_tokens=1),
                           mock=True))
    llm.LAST_META["stale"] = 1
    llm.ask("s", "u", lambda: "x")
    assert llm.LAST_META == {}
    llm.configure(ScriptedPort(), mock=True)
    llm.ask("s", "u", lambda: "x")
    assert llm.LAST_META == {}


# ---- configure, MOCK, PROVIDER, MODEL ---------------------------------------------------------------------------------

@pytest.mark.parametrize("env, expected", [
    ({}, False), ({"SUTRA_MOCK": "1"}, True), ({"SUTRA_OFFLINE": "1"}, True), ({"STUDIO_MOCK": "1"}, True),
    ({"SUTRA_MOCK": "0"}, False), ({"SUTRA_MOCK": "true"}, False), ({"SUTRA_OFFLINE": ""}, False), ({"STUDIO_MOCK": "yes"}, False),
    ({"SUTRA_MOCK": "0", "STUDIO_MOCK": "1"}, True)])
def test_env_mock_reads_the_three_switches(env, expected):
    assert llm.env_mock(env) is expected


def test_env_mock_defaults_to_the_process_environment(clean_env):
    assert llm.env_mock() is False
    clean_env.setenv("SUTRA_OFFLINE", "1")
    assert llm.env_mock() is True
    assert llm.MOCK_ENV == ("SUTRA_MOCK", "SUTRA_OFFLINE", "STUDIO_MOCK")


@pytest.mark.parametrize("switch", ["SUTRA_MOCK", "SUTRA_OFFLINE", "STUDIO_MOCK"])
def test_mock_is_decided_at_import_from_the_environment(switch):
    probe = "from sutra_app.engine import llm; print(llm.MOCK, llm.PROVIDER, llm.MODEL)"
    env = {k: v for k, v in os.environ.items() if k not in llm.MOCK_ENV}
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env, check=True).stdout.split()
    assert out == ["False", "None", "None"]
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env={**env, switch: "1"}, check=True).stdout.split()
    assert out == ["True", "None", "None"]


def test_configure_with_a_real_port_takes_provider_and_model_from_describe():
    llm.configure(Recorder(provider="codex", model="gpt-x"))
    assert (llm.MOCK, llm.PROVIDER, llm.MODEL) == (False, "codex", "gpt-x")


def test_configure_with_a_mock_port_is_mock_and_keeps_provider_and_model_none():
    """J2 wrote a null provider and model into its run files in mock mode, whatever the port calls itself."""
    llm.configure(Recorder(mock=True, provider="stub", model="scripted"))
    assert (llm.MOCK, llm.PROVIDER, llm.MODEL) == (True, None, None)
    llm.configure(ScriptedPort())
    assert (llm.MOCK, llm.PROVIDER, llm.MODEL) == (True, None, None)


def test_configure_mock_argument_wins_over_the_port():
    llm.configure(Recorder(mock=True), mock=False)
    assert llm.MOCK is False and llm.PROVIDER == "claude"
    llm.configure(Recorder(), mock=True)
    assert (llm.MOCK, llm.PROVIDER, llm.MODEL) == (True, None, None)


def test_configure_without_arguments_is_the_environments_default(clean_env):
    llm.configure(Recorder(), mock=True, base_tag=CallTag(run_id="j2-1"))
    llm.configure()
    assert (llm.MOCK, llm.PROVIDER, llm.MODEL) == (False, None, None)
    assert llm.current_tag() == CallTag()
    with pytest.raises(NoModelAvailable):
        llm.ask("s", "u", lambda: "x")
    clean_env.setenv("SUTRA_MOCK", "1")
    llm.configure()
    assert llm.MOCK is True


def test_no_port_and_no_mock_raises_no_model_available():
    llm.LAST_META["stale"] = 1
    with pytest.raises(NoModelAvailable) as caught:
        llm.ask("s", "u", lambda: "never called")
    assert caught.value.code == "no_model" and isinstance(caught.value, ModelError)
    assert llm.LAST_META == {}


def test_mock_without_a_port_answers_through_a_scripted_port_made_once():
    llm.configure(mock=True)
    assert llm.ask("s", "u", lambda: "one") == "one"
    first = llm._DEFAULT_PORT
    assert isinstance(first, ScriptedPort)
    assert llm.ask("s", "u", lambda: "two") == "two"
    assert llm._DEFAULT_PORT is first


def test_the_base_tag_may_be_a_tag_a_mapping_or_nothing():
    llm.configure(mock=True, base_tag=CallTag(run_id="j2-1", dept_id="web"))
    assert llm.current_tag() == CallTag(run_id="j2-1", dept_id="web")
    llm.configure(mock=True, base_tag={"run_id": "j2-2", "task_id": "tsk_1"})
    assert llm.current_tag() == CallTag(run_id="j2-2", task_id="tsk_1")
    llm.configure(mock=True, base_tag=None)
    assert llm.current_tag() == CallTag()
    with pytest.raises(TypeError):
        llm.configure(mock=True, base_tag="web")
    with pytest.raises(ValidationError):
        llm.configure(mock=True, base_tag={"flavour": "x"})


# ---- tags -----------------------------------------------------------------------------------------------------------

def test_ask_sends_the_current_tag():
    port = Recorder()
    llm.configure(port, base_tag=CallTag(run_id="j2-1", dept_id="web", task_id="tsk_1"))
    llm.ask("s", "u", None)
    with llm.tagged(function="audit", step=7, cycle=2, call_no=5, stage="website", purpose="judge", role="judge", atom="W-1.a2"):
        llm.ask("s", "u", None)
    plain, tagged = [r.tag for r in port.requests]
    assert plain == CallTag(run_id="j2-1", dept_id="web", task_id="tsk_1")
    assert tagged == CallTag(run_id="j2-1", dept_id="web", task_id="tsk_1", function="audit", step=7, cycle=2, call_no=5,
                             stage="website", purpose="judge", role="judge", atom="W-1.a2")


def test_nested_tagged_blocks_merge_and_restore():
    llm.configure(mock=True, base_tag=CallTag(run_id="j2-1", dept_id="web", task_id="tsk_1"))
    base = llm.current_tag()
    with llm.tagged(function="adaptation", step=2, cycle=1) as outer:
        assert outer == llm.current_tag() == CallTag(run_id="j2-1", dept_id="web", task_id="tsk_1", function="adaptation", step=2, cycle=1)
        with llm.tagged(purpose="judge", role="judge", step=3) as inner:
            assert inner == CallTag(run_id="j2-1", dept_id="web", task_id="tsk_1", function="adaptation", step=3, cycle=1,
                                    purpose="judge", role="judge")
            assert llm.current_tag() is inner
        assert llm.current_tag() is outer
    assert llm.current_tag() == base


def test_tagged_restores_the_tag_when_the_block_raises():
    llm.configure(mock=True)
    with pytest.raises(RuntimeError):
        with llm.tagged(function="audit"):
            with llm.tagged(function="identity"):
                raise RuntimeError("boom")
    assert llm.current_tag() == CallTag()


def test_tagged_refuses_unknown_and_invalid_fields_at_once():
    llm.configure(mock=True)
    with pytest.raises(ValidationError):
        with llm.tagged(goal="x"):
            pass
    with pytest.raises(ValidationError):
        with llm.tagged(purpose="Not Valid"):
            pass
    assert llm.current_tag() == CallTag()


def test_the_base_tag_reaches_other_threads_but_a_block_stays_in_its_own():
    llm.configure(mock=True, base_tag=CallTag(run_id="j2-1"))
    seen = {}

    def other():
        seen["tag"] = llm.current_tag()

    with llm.tagged(function="audit"):
        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
    assert seen["tag"] == CallTag(run_id="j2-1")


def test_an_explicit_tag_is_used_as_it_is_not_merged_with_the_block():
    port = Recorder()
    llm.configure(port, base_tag=CallTag(run_id="j2-1"))
    with llm.tagged(function="audit", step=7):
        llm.ask("s", "u", None, tag=CallTag(function="reviewer", purpose="review"))
        llm.ask("s", "u", None, tag={"function": "template", "purpose": "template"})
    assert [r.tag for r in port.requests] == [CallTag(function="reviewer", purpose="review"),
                                              CallTag(function="template", purpose="template")]
    with pytest.raises(TypeError):
        llm.ask("s", "u", None, tag="audit")


# ---- images -----------------------------------------------------------------------------------------------------------

def test_images_that_do_not_exist_are_dropped(tmp_path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"\x89PNG")
    port = Recorder()
    llm.configure(port)
    llm.ask("s", "u", None, images=[str(shot), str(tmp_path / "gone.png"), "", None])
    llm.ask("s", "u", None, images=[str(tmp_path / "gone.png")])
    llm.ask("s", "u", None, images=None)
    assert [r.images for r in port.requests] == [[str(shot)], [], []]


# ---- bind_atom --------------------------------------------------------------------------------------------------------

def test_bind_atom_fills_the_atom_of_a_tag_that_has_none():
    port = Recorder()
    llm.configure(port, base_tag=CallTag(run_id="j2-1"))
    llm.bind_atom("a-3f9a1c2b7d-01")
    llm.ask("s", "u", None)
    with llm.tagged(function="identity", step=1):
        llm.ask("s", "u", None)
    llm.ask("s", "u", None, tag=CallTag(function="reviewer", purpose="review"))
    assert [r.tag.atom for r in port.requests] == ["a-3f9a1c2b7d-01"] * 3
    assert port.requests[1].tag.function == "identity"        # the rest of the tag is untouched


def test_an_explicit_atom_wins_over_the_binding():
    port = Recorder()
    llm.configure(port)
    llm.bind_atom("a-3f9a1c2b7d-01")
    with llm.tagged(function="W-3", atom="W-3.a1"):
        llm.ask("s", "u", None)
    llm.ask("s", "u", None, tag=CallTag(function="W-3", atom="W-3.a2"))
    assert [r.tag.atom for r in port.requests] == ["W-3.a1", "W-3.a2"]


def test_the_binding_stays_until_it_is_replaced_or_cleared():
    port = Recorder()
    llm.configure(port)
    assert llm.bound_atom() is None
    llm.bind_atom("a-aaaaaaaaaa-01")
    llm.ask("s", "u", None)
    llm.ask("s", "u", None)
    llm.bind_atom("a-bbbbbbbbbb-01")                          # the layer rebinds the run overhead key after a turn
    llm.ask("s", "u", None)
    llm.bind_atom(None)                                       # tests only
    assert llm.bound_atom() is None
    llm.ask("s", "u", None)
    assert [r.tag.atom for r in port.requests] == ["a-aaaaaaaaaa-01", "a-aaaaaaaaaa-01", "a-bbbbbbbbbb-01", None]


def test_the_binding_does_not_change_the_tag_object_it_was_given():
    llm.configure(Recorder())
    llm.bind_atom("a-aaaaaaaaaa-01")
    given = CallTag(function="reviewer")
    llm.ask("s", "u", None, tag=given)
    assert given.atom is None


@pytest.mark.parametrize("bad", ["", 5, ["a-1"], b"a-1"])
def test_bind_atom_refuses_something_that_is_not_an_atom_id(bad):
    with pytest.raises(ValueError):
        llm.bind_atom(bad)


def test_the_atom_reaches_the_usage_row_of_a_mock_call(scripted_port):
    llm.configure(scripted_port)
    llm.bind_atom("a-3f9a1c2b7d-01")
    llm.ask("s", "u", lambda: "ok")
    assert [row["atom_id"] for row in scripted_port.usage_sink.rows] == ["a-3f9a1c2b7d-01"]


# ---- the helpers that stay -----------------------------------------------------------------------------------------

def test_extract_json_and_close_json_are_the_librarys_objects():
    assert llm.extract_json is replies.extract_json
    assert llm.close_json is replies.close_json
    assert llm.extract_json('{"a": 1}') == {"a": 1}


@pytest.mark.parametrize("text, expected", [
    ("```html\n<p>hi</p>\n```", "<p>hi</p>"),
    ("Here you go:\n```HTML\n  <!doctype html><p>x</p>  \n```\nbye", "<!doctype html><p>x</p>"),
    ("Sure!\n<!DOCTYPE html>\n<html><body>b</body></html>\n", "<!DOCTYPE html>\n<html><body>b</body></html>"),
    ("intro <html lang=en><body>b</body></html>  ", "<html lang=en><body>b</body></html>"),
    ("a <html> b <!doctype html> c", "<!doctype html> c"),            # the doctype wins over an earlier <html>
])
def test_extract_html_gives_j2s_results(text, expected):
    assert llm.extract_html(text) == expected


@pytest.mark.parametrize("text", ["no markup here", "", "```python\nprint(1)\n```"])
def test_extract_html_raises_when_there_is_no_html(text):
    with pytest.raises(ValueError, match="no HTML in reply"):
        llm.extract_html(text)


@pytest.mark.parametrize("text, expected", [
    ("thinking... <!doctype html><html><body><h1>Hi", "<!doctype html><html><body><h1>Hi"),
    ("<html><body>x</body></html>\n```\nthat was it", "<html><body>x</body></html>\n"),
    ("only prose so far", ""),
    ("", ""),
    ("x <HTML>y", "<HTML>y"),
])
def test_partial_html_gives_j2s_results(text, expected):
    assert llm.partial_html(text) == expected


J2_CHECKOUT = os.environ.get("SUTRA_J2_CHECKOUT")


@pytest.mark.skipif(not J2_CHECKOUT, reason="set SUTRA_J2_CHECKOUT to a J2 checkout to compare the html helpers with J2's llm.py")
def test_the_html_helpers_are_verbatim_from_j2():
    j2 = {n.name: n for n in ast.parse((Path(J2_CHECKOUT) / "llm.py").read_text(encoding="utf-8")).body
          if isinstance(n, ast.FunctionDef)}
    for name in ("extract_html", "partial_html"):
        mine = ast.parse(inspect.getsource(getattr(llm, name))).body[0]
        assert ast.dump(mine) == ast.dump(j2[name]), name


# ---- ScriptedPort -----------------------------------------------------------------------------------------------------

USAGE_KEYS = ["provider", "model", "purpose", "session_id", "node_id", "task_id", "dept_id", "fn", "step", "atom_id", "tokens_in",
              "tokens_out", "usd", "seconds", "ok", "how", "call_ref", "detail"]


def req(scripted=lambda: "reply", system="the system prompt", user="the user prompt", **kwargs):
    return CompletionRequest(system=system, user=user, scripted=scripted, **kwargs)


class Sink:
    def __init__(self):
        self.rows = []

    def record(self, row):
        self.rows.append(row)
        return len(self.rows)


def test_scripted_port_describes_itself_as_mock_with_no_provider_or_model():
    port = ScriptedPort()
    assert port.describe() == PortInfo(provider=None, model=None, mock=True)
    result = port.preflight()
    assert result.ok is True and result.providers == [] and "mock" in result.message


def test_scripted_port_returns_scripted_and_a_stub_result():
    port = ScriptedPort(delay=0)
    res = port.complete(req(lambda: "  twelve chars \n"))
    assert res.text == "  twelve chars \n"
    assert (res.provider, res.model, res.usd) == ("stub", "scripted", 0.0)
    assert (res.input_tokens, res.output_tokens) == (len("the system promptthe user prompt") // 4, len("  twelve chars \n") // 4)
    assert isinstance(res.duration_ms, int) and res.duration_ms >= 0


def test_scripted_port_streams_one_chunk_without_a_delay():
    events = []
    ScriptedPort(delay=0).complete(req(lambda: "hello"), events.append)
    assert events == [{"chars": 5, "text": "hello"}]


def test_scripted_port_streams_thirty_chunks_with_a_delay():
    events = []
    text = "x" * 90
    started = time.monotonic()
    ScriptedPort(delay=0.06).complete(req(lambda: text), events.append)
    assert time.monotonic() - started >= 0.05
    assert len(events) == 30
    assert [e["chars"] for e in events] == [90 * i // 30 for i in range(1, 31)]
    assert all(e["text"] == text[:e["chars"]] for e in events) and events[-1]["text"] == text


def test_scripted_port_needs_no_progress_callback():
    assert ScriptedPort(delay=0).complete(req(lambda: "x"), None).text == "x"


@pytest.mark.parametrize("value, expected", [("0.5", 0.5), ("0", 0.0), ("", 0.0), ("abc", 0.0), ("-3", 0.0), ("nan", 0.0),
                                             ("inf", 0.0), (None, 0.0)])
def test_the_mock_delay_comes_from_studio_mock_delay(clean_env, value, expected):
    if value is not None:
        clean_env.setenv("STUDIO_MOCK_DELAY", value)
    assert ScriptedPort().delay == expected


def test_an_explicit_delay_beats_the_environment_and_must_be_sane(clean_env):
    clean_env.setenv("STUDIO_MOCK_DELAY", "9")
    assert ScriptedPort(delay=0.25).delay == 0.25
    assert ScriptedPort(delay=0).delay == 0
    assert ScriptedPort(delay=-1).delay == 0
    assert ScriptedPort(delay=math.inf).delay == 0
    assert ScriptedPort(delay="soon").delay == 0


def test_scripted_port_has_a_canned_reply_when_nothing_is_scripted():
    port = ScriptedPort(delay=0)
    assert port.complete(req(None, user="Write a haiku about " + "coffee " * 20)).text == "[stub] " + ("Write a haiku about " + "coffee " * 20)[:60]
    assert port.complete(req(None, json_mode=True)).text == "{}"
    assert port.complete(req(None, json_schema={"type": "object"})).text == "{}"


def test_a_scripted_reply_must_be_text():
    sink = Sink()
    with pytest.raises(TypeError):
        ScriptedPort(sink, delay=0).complete(req(lambda: {"say": "x"}))
    assert [row["ok"] for row in sink.rows] == [False]


def test_scripted_port_hands_one_usage_row_with_the_connectors_keys():
    sink = Sink()
    port = ScriptedPort(sink, delay=0)
    tag = CallTag(run_id="j2-20261104-100004-7f3a", dept_id="web", task_id="tsk_a1", function="identity", step=1, call_no=4,
                  atom="a-3f9a1c2b7d-01", purpose="agent_turn")
    port.complete(req(lambda: "y" * 41, tag=tag))
    (row,) = sink.rows
    assert list(row) == USAGE_KEYS
    assert row == {"provider": "stub", "model": "scripted", "purpose": "agent_turn", "session_id": None, "node_id": None,
                   "task_id": "tsk_a1", "dept_id": "web", "fn": "identity", "step": "J2.a", "atom_id": "a-3f9a1c2b7d-01",
                   "tokens_in": len("the system promptthe user prompt") // 4, "tokens_out": 41 // 4, "usd": 0.0,
                   "seconds": row["seconds"], "ok": True, "how": "stub", "call_ref": "j2-20261104-100004-7f3a:4", "detail": None}
    assert 0 <= row["seconds"] < 5


def test_the_usage_row_of_an_untagged_call():
    sink = Sink()
    ScriptedPort(sink, delay=0).complete(req(lambda: "ok"))
    (row,) = sink.rows
    assert (row["task_id"], row["dept_id"], row["fn"], row["step"], row["atom_id"], row["purpose"]) == (None, None, "", None, None, "agent_turn")
    assert row["call_ref"] == "r:1"


def test_request_keys_count_up_for_unnumbered_calls_and_a_number_wins():
    sink = Sink()
    port = ScriptedPort(sink, delay=0)
    port.complete(req())
    port.complete(req(tag=CallTag(run_id="j2-9", call_no=7)))
    port.complete(req())
    assert [row["call_ref"] for row in sink.rows] == ["r:1", "j2-9:7", "r:3"]


@pytest.mark.parametrize("tag, label", [
    (CallTag(function="W-3", step=6), "W-3"), (CallTag(function="W-12"), "W-12"), (CallTag(step=1), "J2.a"),
    (CallTag(step=2), "J2.b"), (CallTag(step=3), "J2.c"), (CallTag(step=4), "J2.d"), (CallTag(step=5), "J2.e"),
    (CallTag(step=6), "J2.f"), (CallTag(step=7), "J2.g"), (CallTag(step=8), "J2.h"), (CallTag(step=0), None),
    (CallTag(step=9), None), (CallTag(function="W-x", step=0), None), (CallTag(function="xW-3", step=0), None)])
def test_step_label_is_the_builder_id_or_the_j2_step_letter(tag, label):
    assert llm.step_label(tag) == label


def test_scripted_port_without_a_sink_just_answers():
    assert ScriptedPort(delay=0).complete(req(lambda: "fine")).text == "fine"


def test_a_failing_scripted_call_leaves_one_failure_row_and_raises_again():
    sink = Sink()
    port = ScriptedPort(sink, delay=0)

    def boom():
        raise ModelTimeout("slow")

    with pytest.raises(ModelTimeout):
        port.complete(req(boom, tag=CallTag(function="audit", step=7, atom="a-aaaaaaaaaa-01")))
    with pytest.raises(KeyError):
        port.complete(req(lambda: {}["missing"]))
    first, second = sink.rows
    assert (first["ok"], first["tokens_out"], first["detail"], first["atom_id"], first["fn"]) == (False, 0, {"note": "timeout"}, "a-aaaaaaaaaa-01", "audit")
    assert (second["ok"], second["detail"]) == (False, {"note": "KeyError"})
    assert first["tokens_in"] == len("the system promptthe user prompt") // 4


def test_a_sink_that_fails_is_not_hidden():
    class Broken:
        def record(self, row):
            raise OSError("disk full")
    with pytest.raises(OSError):
        ScriptedPort(Broken(), delay=0).complete(req())


def test_closing_a_scripted_port_refuses_new_requests_and_says_so_in_the_ledger():
    sink = Sink()
    port = ScriptedPort(sink, delay=0)
    assert port.closed is False
    port.close()
    port.close()
    assert port.closed is True
    with pytest.raises(ModelError, match="closed"):
        port.complete(req())
    assert [row["ok"] for row in sink.rows] == [False]


def test_closing_ends_a_request_that_is_waiting_out_its_delay():
    """Stop and SIGTERM close the port to kill an in-flight call; a mock call must stop waiting too."""
    port = ScriptedPort(Sink(), delay=30)
    started, outcome = threading.Event(), {}

    def run():
        try:
            port.complete(req(lambda: "x" * 90), lambda event: started.set())
        except ModelError as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(5)
    port.close()
    thread.join(5)
    assert not thread.is_alive()
    assert "closed" in str(outcome["error"])
    assert port.usage_sink.rows[0]["ok"] is False


def test_scripted_port_is_the_port_ask_uses_in_mock_mode(scripted_port):
    llm.configure(scripted_port, base_tag=CallTag(run_id="j2-1", dept_id="web", task_id="tsk_1"))
    with llm.tagged(function="priority", step=3, call_no=2):
        assert llm.ask("s", "u", lambda: "priced") == "priced"
    (row,) = scripted_port.usage_sink.rows
    assert (row["fn"], row["step"], row["call_ref"], row["task_id"], row["dept_id"]) == ("priority", "J2.c", "j2-1:2", "tsk_1", "web")
