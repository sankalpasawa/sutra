"""StubConnector and ReplyBook (work package CN-5, connectors design 3.7, CD11, CD18).

No process, no fake CLI: the stub answers from a script. Delays are tiny so the file runs in a few seconds.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Literal

import pytest
from pydantic import BaseModel

from sutra_app.connectors.base import Hooks
from sutra_app.connectors.errors import (
    ERROR_CLASSES, CallCancelledError, ConnectorError, EnvelopeExceededError, InvalidJsonError, InvalidRequestError,
    ProviderError, QuotaError,
)
from sutra_app.connectors.models import ConnectorConfig, Message, RouteContext, SessionSpec
from sutra_app.connectors.stub import CHUNKS, STUB_MODEL, ReplyBook, StubConnector
from sutra_app.engine.llm import ScriptedPort
from sutra_app.engine.port import CallTag, CompletionRequest


class Mood(BaseModel):
    label: Literal["calm", "angry"]
    score: int
    tags: list[str]
    note: str = "optional"


class Recorder(Hooks):
    def __init__(self, veto=None):
        self.infos, self.records, self.veto = [], [], veto

    def before_call(self, info):
        if self.veto:
            raise self.veto
        self.infos.append(info)

    def after_call(self, record):
        self.records.append(record)


def ctx(function="", stage=None, **tag):
    return RouteContext(tag=CallTag(function=function, stage=stage, **tag))


@pytest.fixture(autouse=True)
def _no_env_delay(monkeypatch):
    monkeypatch.delenv("STUDIO_MOCK_DELAY", raising=False)


@pytest.fixture
def make(tmp_path):
    def build(**kw):
        return StubConnector(ConnectorConfig(data_dir=tmp_path, work_root=tmp_path / "work"), **kw)
    return build


@pytest.fixture
def stub(make):
    return make()


# ---- determinism, built-in replies, numbers -----------------------------------------------------------------------------------

def test_same_input_twice_gives_the_same_output(stub):
    a = stub.call_text("Write a haiku", system="Be brief.")
    b = stub.call_text("Write a haiku", system="Be brief.")
    assert a.model_dump(exclude={"duration_ms"}) == b.model_dump(exclude={"duration_ms"})


def test_builtin_text_is_stub_marker_plus_first_60_characters(stub):
    long = "x" * 100
    assert stub.call_text(long).text == "[stub] " + "x" * 60
    assert stub.call_text("short one").text == "[stub] short one"


def test_result_fields_and_token_estimate(stub):
    turn = stub.call_text("a" * 41, system="s" * 7)           # (7 + 41) // 4 = 12 in; reply "[stub] " + 41 chars = 48 // 4 = 12 out
    assert (turn.provider, turn.model, turn.usd, turn.usd_basis) == ("stub", STUB_MODEL, 0.0, "none")
    assert turn.usage.input_tokens == 12 and turn.usage.output_tokens == 12
    assert turn.provider_session_id is None and turn.quota is None
    tiny = stub.call_text("abc")                                # 3 // 4 = 0 in; "[stub] abc" = 10 // 4 = 2 out
    assert (tiny.usage.input_tokens, tiny.usage.output_tokens) == (0, 2)


def test_tokens_and_text_match_the_scripted_port_twin(stub):
    system, user = "Be terse.", "What is the capital of France? " * 3
    turn = stub.call_text(user, system=system)
    twin = ScriptedPort().complete(CompletionRequest(system=system, user=user))
    assert (turn.text, turn.usage.input_tokens, turn.usage.output_tokens) == (twin.text, twin.input_tokens, twin.output_tokens)
    assert (turn.provider, turn.model, turn.usd) == (twin.provider, twin.model, twin.usd)


def test_the_connector_total_adds_every_call(stub):
    stub.call_text("a" * 40)
    stub.call_text("b" * 40)
    assert stub.usage().input_tokens == 20 and stub.usage().output_tokens == 2 * ((7 + 40) // 4)


def test_a_requested_model_name_does_not_matter(stub):
    assert stub.call_text("hi", model="sonnet").model == STUB_MODEL
    assert stub.resolve_model("anything at all") == STUB_MODEL


def test_scripted_text_is_returned_unstripped(stub):
    assert stub.call_text("hi", scripted=lambda: "  padded reply \n").text == "  padded reply \n"


# ---- reply resolution ---------------------------------------------------------------------------------------------------------

def test_resolution_order_scripted_exact_function_wildcard_global_wildcard_builtin(make):
    book = ReplyBook({("audit", "prd"): "exact", ("audit", "*"): "fn-any", ("*", "*"): "all"})
    stub = make(book=book)
    ask = lambda fn, stage, **kw: stub.call_text("prompt", ctx=ctx(fn, stage), **kw).text    # noqa: E731
    assert ask("audit", "prd", scripted=lambda: "mock") == "mock"        # 1 scripted beats the book
    assert ask("audit", "prd") == "exact"                                # 2 exact pair
    assert ask("audit", "hld") == "fn-any"                               # 3 (function, "*")
    assert ask("identity", "prd") == "all"                               # 4 ("*", "*")
    assert [c.rule for c in stub.calls] == ["scripted", "book", "book", "book"]
    plain = make()
    assert plain.call_text("prompt", ctx=ctx("audit", "prd")).text == "[stub] prompt"          # 5 built-in
    assert plain.calls[0].rule == "builtin"


def test_exact_pair_beats_wildcards_whatever_the_insertion_order(make):
    stub = make(book=ReplyBook().set("*", "*", "all").set("audit", "*", "fn").set("audit", "prd", "exact"))
    assert stub.call_text("p", ctx=ctx("audit", "prd")).text == "exact"


def test_an_untagged_call_has_empty_function_and_stage(make):
    stub = make(book=ReplyBook({("audit", "*"): "no", ("", ""): "untagged"}))
    assert stub.call_text("p").text == "untagged"
    only_global = make(book=ReplyBook({("audit", "*"): "no", ("*", "*"): "global"}))
    assert only_global.call_text("p").text == "global"


def test_the_book_can_be_filled_after_the_connector_is_built(stub):
    assert stub.call_text("p", ctx=ctx("audit")).text == "[stub] p"
    stub.book.set("audit", "*", "late")
    assert stub.call_text("p", ctx=ctx("audit")).text == "late"


def test_scripted_must_return_text(stub):
    with pytest.raises(TypeError, match="scripted reply is text"):
        stub.call_text("p", scripted=lambda: 42)


def test_scripted_is_not_called_when_the_call_fails_first(stub):
    stub.fail_next("overloaded")
    called = []
    with pytest.raises(ConnectorError):
        stub.call_text("p", scripted=lambda: called.append(1) or "x")
    assert called == []


# ---- ReplyBook ----------------------------------------------------------------------------------------------------------------

def test_replybook_json_value_becomes_json_text(make):
    stub = make(book=ReplyBook({("audit", "*"): {"ok": True, "n": [1, 2]}, ("*", "*"): ["a", "é"]}))
    assert json.loads(stub.call_text("p", ctx=ctx("audit")).text) == {"ok": True, "n": [1, 2]}
    assert stub.call_text("p").text == '["a", "é"]'


def test_replybook_callable_runs_at_every_lookup(make):
    replies = iter(["first", "second"])
    stub = make(book=ReplyBook({("*", "*"): lambda: next(replies)}))
    assert [stub.call_text("p").text, stub.call_text("p").text] == ["first", "second"]


def test_replybook_set_chains_and_counts():
    book = ReplyBook().set("a", "b", "1").set("a", "*", "2")
    assert len(book) == 2 and ("a", "b") in book and ("x", "y") not in book
    assert book.lookup("a", "b") == (True, "1") and book.lookup("zzz", "b") == (False, None)
    book.set("a", "b", "replaced")
    assert len(book) == 2 and book.lookup("a", "b") == (True, "replaced")


def test_replybook_refuses_what_it_cannot_serve():
    with pytest.raises(TypeError, match="JSON-serialisable"):
        ReplyBook().set("a", "b", {1, 2})
    with pytest.raises(TypeError, match="function must be a string"):
        ReplyBook().set(None, "b", "x")
    with pytest.raises(TypeError, match="stage must be a string"):
        ReplyBook({("a", 3): "x"})


def test_a_callable_book_reply_that_returns_junk_fails_when_asked(make):
    stub = make(book=ReplyBook({("*", "*"): lambda: {1, 2}}))
    with pytest.raises(TypeError):
        stub.call_text("p")


# ---- JSON requests ------------------------------------------------------------------------------------------------------------

def test_schema_example_validates_for_a_pydantic_class(stub):
    value, usd, how = stub.call_json("Rate it", schema=Mood)
    assert isinstance(value, Mood) and value.label == "calm" and value.score == 0 and value.tags == []
    assert (usd, how) == (0.0, "stub")


def test_schema_example_for_a_dict_schema(stub):
    schema = {"type": "object", "required": ["kind", "ok", "items", "child"], "properties": {
        "kind": {"enum": ["x", "y"]}, "ok": {"type": "boolean"}, "items": {"type": "array", "items": {"type": "string"}},
        "child": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}, "extra": {"type": "string"}}}
    value, _, how = stub.call_json("p", schema=schema)
    assert value == {"kind": "x", "ok": False, "items": [], "child": {"name": "stub"}} and how == "stub"


def test_json_without_a_schema_answers_an_empty_object_as_text(stub):
    assert stub.call_json("p")[0] == "{}"      # the base returns the text when no schema asks for validation


def test_json_result_reports_one_call_and_zero_spend(stub):
    result = stub.call_json_result("p", schema=Mood)
    assert (result.how, result.calls_made, result.usd, result.usd_spent) == ("stub", 1, 0.0, 0.0)
    assert result.turn.provider == "stub" and json.loads(result.turn.text)["label"] == "calm"


def test_schema_over_the_native_size_limit_still_gets_its_example(stub):
    schema = {"type": "object", "description": "d" * 120_000, "required": ["a"], "properties": {"a": {"type": "integer"}}}
    assert stub.call_json("p", schema=schema)[0] == {"a": 0}
    assert stub.calls[-1].kind == "json"


def test_forced_prompted_path_still_gets_the_example(stub):
    result = stub.call_json_result("p", schema=Mood, force_prompted=True)
    assert result.how == "stub" and result.value.label == "calm"
    assert "JSON Schema" in stub.calls[-1].prompt         # the prompted prompt was built, the answer is the same


def test_book_and_scripted_replies_beat_the_schema_example(make):
    stub = make(book=ReplyBook({("audit", "*"): {"label": "angry", "score": 7, "tags": ["a"]}}))
    assert stub.call_json("p", schema=Mood, ctx=ctx("audit"))[0].score == 7
    value, _, how = stub.call_json("p", schema=Mood, scripted=lambda: '```json\n{"label": "calm", "score": 1, "tags": []}\n```')
    assert value.score == 1 and how == "stub"


def test_a_bad_reply_gets_repair_rounds_then_invalid_json(make):
    stub = make(book=ReplyBook({("*", "*"): "not json at all"}))
    with pytest.raises(InvalidJsonError) as e:
        stub.call_json("p", schema=Mood)
    assert e.value.detail["rounds"] == 2 and e.value.detail["calls"] == 3
    assert [c.kind for c in stub.calls] == ["json", "repair", "repair"]


def test_repair_round_can_fix_the_reply_and_how_stays_stub(stub):
    replies = iter(["oops", '{"label": "calm", "score": 2, "tags": []}'])
    result = stub.call_json_result("p", schema=Mood, scripted=lambda: next(replies))
    assert result.how == "stub" and result.calls_made == 2 and result.value.score == 2
    assert "REJECTED" in stub.calls[1].prompt


def test_requests_in_two_threads_keep_their_own_schema_and_scripted(make):
    stub = make()
    gate = threading.Barrier(2, timeout=5)
    out = {}

    def worker(name, schema, reply):
        def scripted():
            gate.wait()                                     # both requests are inside the stub at the same time
            return reply
        out[name] = stub.call_json("p", schema=schema, scripted=scripted)[0] if reply else stub.call_json("p", schema=schema)[0]

    a = threading.Thread(target=worker, args=("a", Mood, '{"label": "angry", "score": 1, "tags": []}'))
    b = threading.Thread(target=worker, args=("b", {"type": "object", "required": ["z"], "properties": {"z": {"type": "string"}}},
                                               '{"z": "mine"}'))
    a.start(); b.start(); a.join(10); b.join(10)
    assert out["a"].label == "angry" and out["b"] == {"z": "mine"}


# ---- fail_next ----------------------------------------------------------------------------------------------------------------

def test_fail_next_raises_the_error_of_the_code_once(stub):
    stub.fail_next("quota", message="used up", resets_at=123.0)
    with pytest.raises(QuotaError) as e:
        stub.call_text("p")
    assert (e.value.code, e.value.provider, e.value.message, e.value.resets_at) == ("quota", "stub", "used up", 123.0)
    assert stub.call_text("p").text == "[stub] p"             # the next call works again


def test_fail_next_times_and_order(stub):
    stub.fail_next("rate_limited", times=2)
    stub.fail_next("overloaded")
    seen = []
    for _ in range(4):
        try:
            stub.call_text("p")
            seen.append("ok")
        except ConnectorError as e:
            seen.append(e.code)
    assert seen == ["rate_limited", "rate_limited", "overloaded", "ok"]


def test_every_error_code_can_be_scripted(stub):
    for code in ERROR_CLASSES:
        stub.fail_next(code)
        with pytest.raises(ERROR_CLASSES[code]) as e:
            stub.call_text("p")
        assert e.value.code == code and e.value.provider == "stub"


def test_fail_next_validates_its_arguments(stub):
    with pytest.raises(ValueError, match="unknown error code"):
        stub.fail_next("quotta")
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="positive integer"):
            stub.fail_next("quota", times=bad)
    assert stub.call_text("p").text == "[stub] p"              # nothing was queued


def test_a_failed_call_reaches_the_hooks_as_one_failed_record(make):
    rec = Recorder()
    stub = make(hooks=rec)
    stub.fail_next("timeout")
    with pytest.raises(ConnectorError):
        stub.call_text("p", ctx=ctx("audit", atom="W-3"))
    assert len(rec.infos) == 1 and len(rec.records) == 1
    r = rec.records[0]
    assert (r.ok, r.code, r.turn, r.usd) == (False, "timeout", None, None) and r.error.provider == "stub"
    assert stub.usage().input_tokens == 0                      # a failed call adds nothing to the total
    assert (stub.calls[0].rule, stub.calls[0].code, stub.calls[0].reply) == ("failed", "timeout", None)


def test_fail_next_hits_a_repair_round_too(make):
    stub = make(book=ReplyBook({("*", "*"): "bad"}))
    stub.fail_next("overloaded")                               # eats the first spawn of the json request
    with pytest.raises(ConnectorError) as e:
        stub.call_json("p", schema=Mood)
    assert e.value.code == "overloaded" and len(stub.calls) == 1


# ---- hooks --------------------------------------------------------------------------------------------------------------------

def test_hooks_see_each_call_with_stub_facts(make):
    rec = Recorder()
    stub = make(hooks=rec)
    stub.call_text("a" * 40, system="sys", ctx=ctx("audit", "prd", atom="W-1", purpose="review"), effort="max")
    info, record = rec.infos[0], rec.records[0]
    assert (info.provider, info.model, info.kind, info.effort, info.attempt, info.native) == ("stub", STUB_MODEL, "text", "max", 1, False)
    assert info.ctx.tag.atom == "W-1"
    assert record.ok and record.code is None and record.usd == 0.0 and record.usage.output_tokens == (7 + 40) // 4
    assert record.exit_code is None and record.native_schema_sha is None and record.turn.text.startswith("[stub]")


def test_per_call_hooks_override_the_connector_hooks(make):
    own, other = Recorder(), Recorder()
    stub = make(hooks=own)
    stub.call_text("p", hooks=other)
    assert len(other.records) == 1 and own.records == []


def test_a_veto_in_before_call_stops_the_call(make):
    rec = Recorder(veto=EnvelopeExceededError("no more"))
    stub = make(hooks=rec)
    with pytest.raises(EnvelopeExceededError):
        stub.call_text("p")
    assert rec.records == [] and stub.calls == []


def test_a_zero_money_allowance_is_refused_before_any_call(make):
    from sutra_app.engine.port import Allowance
    rec = Recorder()
    stub = make(hooks=rec)
    with pytest.raises(EnvelopeExceededError):
        stub.call_text("p", ctx=RouteContext(allowance=Allowance(max_usd=0)))
    assert rec.infos == [] and stub.calls == []


# ---- streaming and delay ------------------------------------------------------------------------------------------------------

def collect(stub, text_len=90, **call):
    events = []
    turn = stub.call_text("p", scripted=lambda: "".join(chr(97 + i % 26) for i in range(text_len)), on_event=events.append, **call)
    return turn, events


def test_without_a_delay_the_reply_is_one_chunk(stub):
    turn, events = collect(stub)
    assert [e.kind for e in events] == ["started", "text_delta", "text"]
    assert events[1].data["text"] == turn.text == events[2].data["text"]
    assert events[0].data["model"] == STUB_MODEL


def test_with_a_delay_the_text_streams_in_30_chunks_that_add_up(make):
    stub = make(delay=0.06)
    began = time.monotonic()
    turn, events = collect(stub, text_len=90)
    elapsed = time.monotonic() - began
    deltas = [e.data["text"] for e in events if e.kind == "text_delta"]
    assert CHUNKS == 30 and len(deltas) == 30 and all(len(d) == 3 for d in deltas)
    assert "".join(deltas) == turn.text
    assert 0.05 <= elapsed < 3                                   # the delay was really spent (one thirtieth per chunk)


def test_a_text_shorter_than_30_characters_skips_empty_chunks(make):
    _, events = collect(make(delay=0.03), text_len=10)
    assert "".join(e.data["text"] for e in events if e.kind == "text_delta") == "abcdefghij"
    assert len([e for e in events if e.kind == "text_delta"]) == 10


def test_delay_comes_from_studio_mock_delay_when_not_given(make, monkeypatch):
    monkeypatch.setenv("STUDIO_MOCK_DELAY", "0.9")
    assert make().delay == 0.9
    assert make(delay=0.2).delay == 0.2                       # an argument beats the environment
    for junk in ("soon", "-3", "nan", "inf", ""):
        monkeypatch.setenv("STUDIO_MOCK_DELAY", junk)
        assert make().delay == 0.0
    assert make(delay=-1).delay == 0.0


def test_stop_ends_a_delayed_turn_and_reports_it(make):
    stub = make(delay=30.0)
    state = stub.start(SessionSpec(session_id="s1"))
    outcome = {}

    def run():
        try:
            stub.send(state, Message(role="user", text="hello there"))
        except ConnectorError as e:
            outcome["error"] = e

    t = threading.Thread(target=run)
    t.start()
    deadline = time.monotonic() + 5
    while not stub.stop(state):                               # False until the turn is waiting out its delay
        assert time.monotonic() < deadline
        time.sleep(0.01)
    t.join(5)
    assert not t.is_alive() and isinstance(outcome["error"], CallCancelledError)
    assert stub.stop(state) is False                          # idle again
    assert state.turns == 0 and stub.transcript("s1") == []   # a stopped turn changes nothing


# ---- sessions -----------------------------------------------------------------------------------------------------------------

def test_a_session_keeps_an_in_memory_transcript(stub):
    state = stub.start(SessionSpec(session_id="chat-1", system="You are kind."))
    first = stub.send(state, Message(role="user", text="hello"))
    second = stub.send(state, Message(role="user", text="and again"))
    history = stub.transcript("chat-1")
    assert [(m.role, m.text) for m in history] == [("user", "hello"), ("assistant", first.text), ("user", "and again"),
                                                    ("assistant", second.text)]
    history.clear()
    assert len(stub.transcript("chat-1")) == 4                  # a copy
    assert stub.transcript("unknown") == []


def test_session_state_counters_and_provider_session_id(stub):
    state = stub.start(SessionSpec(session_id="chat-2", system="s" * 8))
    assert (state.provider, state.model, state.provider_session_id, state.turns) == ("stub", STUB_MODEL, None, 0)
    t1 = stub.send(state, Message(role="user", text="a" * 24))   # (8 + 24) // 4 = 8 in
    t2 = stub.send(state, Message(role="user", text="b" * 24))
    assert t1.usage.input_tokens == 8 and t1.provider_session_id == t2.provider_session_id == state.provider_session_id
    assert state.turns == 2 and state.cum_usage.input_tokens == 16 and state.cum_usd == 0.0
    assert stub.usage(state).input_tokens == 16
    again = stub.resume(state)
    assert again.provider_session_id == state.provider_session_id and again.turns == 2


def test_provider_session_id_is_deterministic_per_session(make):
    ids = []
    for _ in range(2):
        stub = make()
        state = stub.start(SessionSpec(session_id="same"))
        ids.append(stub.send(state, Message(role="user", text="hi")).provider_session_id)
    other = make().start(SessionSpec(session_id="other"))
    assert ids[0] == ids[1] and ids[0] != make().send(other, Message(role="user", text="hi")).provider_session_id


def test_stream_ends_with_turn_done_and_start_resets_the_transcript(stub):
    state = stub.start(SessionSpec(session_id="chat-3"))
    events = list(stub.stream(state, Message(role="user", text="hello"), partials=True))
    assert [e.kind for e in events] == ["started", "text_delta", "text", "turn_done"]
    assert events[-1].data["result"]["text"] == "[stub] hello"
    assert len(stub.transcript("chat-3")) == 2
    stub.start(SessionSpec(session_id="chat-3"))
    assert stub.transcript("chat-3") == []


def test_forget_drops_the_transcript(stub):
    state = stub.start(SessionSpec(session_id="chat-4"))
    stub.send(state, Message(role="user", text="hello"))
    stub.forget(state)
    assert stub.transcript("chat-4") == []


def test_session_turns_resolve_through_the_book_and_hooks(make):
    rec = Recorder()
    stub = make(hooks=rec, book=ReplyBook({("*", "*"): "from the book"}))
    state = stub.start(SessionSpec(session_id="chat-5"))
    assert stub.send(state, Message(role="user", text="hello")).text == "from the book"
    assert rec.infos[0].kind == "chat" and rec.infos[0].session_id == "chat-5" and stub.calls[0].session_id == "chat-5"


def test_a_failed_turn_leaves_the_session_untouched(stub):
    state = stub.start(SessionSpec(session_id="chat-6"))
    stub.fail_next("server_error")
    with pytest.raises(ConnectorError):
        stub.send(state, Message(role="user", text="hello"))
    assert state.turns == 0 and state.provider_session_id is None and stub.transcript("chat-6") == []


# ---- the rest of the connector surface ----------------------------------------------------------------------------------------

def test_identity_health_and_models(stub):
    status = stub.auth_status()
    assert (status.provider, status.installed, status.signed_in, status.billing) == ("stub", True, True, "unknown")
    assert stub.flags() == {}
    assert [m.slug for m in stub.models()] == [STUB_MODEL] and stub.models()[0].listed
    caps = StubConnector.capabilities
    assert (StubConnector.name, caps.resume, caps.images, caps.partials, caps.mcp) == ("stub", True, True, True, False)


def test_no_process_is_ever_started(make):
    class NoProcess:
        def __getattr__(self, name):
            raise AssertionError(f"the stub touched the process runner: {name}")

    stub = make(runner=NoProcess())
    stub.call_text("p")
    stub.call_json("p", schema=Mood)
    state = stub.start(SessionSpec(session_id="np"))
    stub.send(state, Message(role="user", text="hello"))
    stub.forget(state)
    stub.auth_status()


def test_the_process_hooks_refuse_to_run(stub):
    from sutra_app.connectors.base import TurnPlan
    plan = TurnPlan(prompt="p", ctx=RouteContext())
    with pytest.raises(ProviderError, match="no process"):
        stub.build_command(plan)
    with pytest.raises(ProviderError, match="no process"):
        stub.new_parser(plan)


def test_base_request_checks_still_apply(stub, tmp_path):
    with pytest.raises(InvalidRequestError, match="prompt is empty"):
        stub.call_text("   ")
    with pytest.raises(InvalidRequestError, match="effort must be"):
        stub.call_text("p", effort="turbo")
    with pytest.raises(InvalidRequestError, match="image not found"):
        stub.call_text("p", images=[str(tmp_path / "missing.png")])
    png = tmp_path / "a.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert stub.call_text("p", images=[str(png)]).text == "[stub] p"
    with pytest.raises(InvalidRequestError, match="not claude"):
        stub.start(SessionSpec(session_id="x", provider="claude"))


def test_calls_log_names_the_rule_function_and_stage(make):
    stub = make(book=ReplyBook({("audit", "prd"): "x"}))
    stub.call_text("first", ctx=ctx("audit", "prd"))
    stub.call_text("second", system="sys")
    first, second = stub.calls
    assert (first.rule, first.function, first.stage, first.prompt, first.reply) == ("book", "audit", "prd", "first", "x")
    assert (second.rule, second.function, second.stage, second.system, second.kind) == ("builtin", "", "", "sys", "text")
    assert isinstance(stub.calls, list) and stub.calls is not stub.calls


def test_a_turn_on_an_existing_provider_session_keeps_its_id(stub):
    state = stub.start(SessionSpec(session_id="chat-7"))
    state.provider_session_id = "11111111-2222-4333-8444-555555555555"
    turn = stub.send(state, Message(role="user", text="hello"))
    assert turn.provider_session_id == state.provider_session_id == "11111111-2222-4333-8444-555555555555"
