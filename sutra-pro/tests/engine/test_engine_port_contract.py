"""The model seam (engine.md 4.1; S1-contracts-02, -05, -06, -07; S4-fnodes-07).

Two halves. First the shapes of `port.py`: CallTag, Allowance, PortSpec, CompletionRequest/Result, PortInfo, PreflightResult,
the ModelError family and the ModelPort protocol. Then ONE assertion set that runs against every port that claims to be J2's
mock mode: `llm.ScriptedPort` and, when the connector section has merged, the stub-only port of
`connectors.engine_port.make_port` (the twin that `ScriptedPort` lets the engine run without the connectors package).
"""
import importlib.util
import inspect
from typing import Optional

import pytest
from pydantic import ValidationError

from sutra_app.engine import llm, port
from sutra_app.engine.llm import ScriptedPort
from sutra_app.engine.port import (
    Allowance, CallTag, CliMissing, CompletionRequest, CompletionResult, ModelError, ModelPort, ModelTimeout,
    NoModelAvailable, NotSignedIn, PortInfo, PortSpec, PreflightResult, QuotaExhausted, StructuredOutputFailed,
)


# ---- CallTag ------------------------------------------------------------------------------------------------------

def test_call_tag_has_exactly_these_fields_and_defaults():
    assert list(CallTag.model_fields) == ["run_id", "dept_id", "task_id", "function", "role", "stage", "step", "cycle",
                                          "call_no", "atom", "purpose", "workspace"]
    tag = CallTag()
    assert (tag.run_id, tag.dept_id, tag.task_id, tag.function, tag.role, tag.stage) == ("", "", None, "", None, None)
    assert (tag.step, tag.cycle, tag.call_no, tag.atom, tag.purpose) == (0, 0, 0, None, "agent_turn")
    assert tag.workspace == "none"


def test_call_tag_is_frozen_and_closed():
    tag = CallTag(function="audit")
    with pytest.raises(ValidationError):
        tag.function = "identity"
    with pytest.raises(ValidationError):
        CallTag(goal="x")


@pytest.mark.parametrize("purpose", ["agent_turn", "summary", "template", "review", "plan", "judge", "change", "chat_plan",
                                     "chat", "a", "_", "x" * 24])
def test_call_tag_purpose_is_an_open_string_of_lowercase_words(purpose):
    assert CallTag(purpose=purpose).purpose == purpose


@pytest.mark.parametrize("purpose", ["", "Chat", "agent-turn", "agent turn", "agent_turn\n", "x" * 25, "plan2", "é"])
def test_call_tag_purpose_pattern_refuses_the_rest(purpose):
    with pytest.raises(ValidationError):
        CallTag(purpose=purpose)


def test_call_tag_step_is_the_j2_number_never_a_word():
    """ORCH's string step goes to `stage`; a word in `step` must fail loudly (S1-contracts-07)."""
    assert CallTag(step=7).step == 7
    with pytest.raises(ValidationError):
        CallTag(step="decide")
    assert CallTag(stage="decide").stage == "decide"


@pytest.mark.parametrize("field", ["step", "cycle", "call_no"])
def test_call_tag_numbers_are_not_negative(field):
    with pytest.raises(ValidationError):
        CallTag(**{field: -1})


# ---- Allowance, PortSpec ------------------------------------------------------------------------------------------

def test_allowance_is_a_closed_model_with_these_fields():
    assert list(Allowance.model_fields) == ["max_calls", "max_usd", "deadline", "envelope_id"]
    assert Allowance.model_config["extra"] == "forbid"
    assert Allowance().model_dump() == {"max_calls": None, "max_usd": None, "deadline": None, "envelope_id": None}
    with pytest.raises(ValidationError):
        Allowance(max_tokens=5)


@pytest.mark.parametrize("bad", [{"max_calls": -1}, {"max_usd": -0.01}, {"max_usd": float("inf")}, {"deadline": float("nan")},
                                 {"max_calls": "many"}])
def test_allowance_bounds(bad):
    with pytest.raises(ValidationError):
        Allowance(**bad)


def test_allowance_accepts_the_envelope_of_one_request():
    a = Allowance(max_calls=3, max_usd=0.5, deadline=1793748000.0, envelope_id="a-3f9a1c2b7d-01")
    assert (a.max_calls, a.max_usd, a.deadline, a.envelope_id) == (3, 0.5, 1793748000.0, "a-3f9a1c2b7d-01")
    assert Allowance(max_calls=0).max_calls == 0


def test_port_spec_has_exactly_its_fields():
    assert list(PortSpec.model_fields) == ["mock", "connector", "run_id", "dept_id", "task_id", "data_dir"]
    spec = PortSpec(mock=False, run_id="j2-1", dept_id="web", data_dir="/tmp/d")
    assert (spec.connector, spec.task_id) == ("auto", None)
    with pytest.raises(ValidationError):
        spec.mock = True                                  # frozen
    with pytest.raises(ValidationError):
        PortSpec(mock=False, run_id="j2-1", dept_id="web", data_dir="/tmp/d", model="sonnet")     # closed: no `model` (S1-02)


@pytest.mark.parametrize("connector", ["auto", "claude", "codex", "stub"])
def test_port_spec_connector_words(connector):
    assert PortSpec(mock=True, connector=connector, run_id="r", dept_id="web", data_dir="d").connector == connector


def test_port_spec_refuses_an_unknown_connector_and_a_missing_field():
    with pytest.raises(ValidationError):
        PortSpec(mock=True, connector="gemini", run_id="r", dept_id="web", data_dir="d")
    for missing in ("mock", "run_id", "dept_id", "data_dir"):
        kwargs = {"mock": True, "run_id": "r", "dept_id": "web", "data_dir": "d"}
        del kwargs[missing]
        with pytest.raises(ValidationError):
            PortSpec(**kwargs)


# ---- request, result, info ----------------------------------------------------------------------------------------

def test_completion_request_defaults_match_j2_ask():
    req = CompletionRequest(system="s", user="u")
    assert (req.max_tokens, req.effort, req.json_mode, req.images, req.json_schema, req.timeout_s) == (1500, "high", False, [], None, None)
    assert req.tag == CallTag() and req.allowance is None and req.scripted is None


def test_completion_request_field_list_and_closed():
    assert list(CompletionRequest.model_fields) == ["system", "user", "max_tokens", "effort", "json_mode", "images",
                                                    "json_schema", "timeout_s", "tag", "allowance", "scripted"]
    with pytest.raises(ValidationError):
        CompletionRequest(system="s", user="u", model="sonnet")
    for name in ("system", "user"):
        with pytest.raises(ValidationError):
            CompletionRequest(**{"system": "s", "user": "u", name: None})


def test_completion_request_allowance_is_typed_not_a_dict():
    """`CompletionRequest.allowance` is `Allowance | None` (S1-contracts-02)."""
    assert CompletionRequest.model_fields["allowance"].annotation == Optional[Allowance]
    assert CompletionRequest(system="s", user="u", allowance=Allowance(max_calls=2)).allowance.max_calls == 2
    with pytest.raises(ValidationError):
        CompletionRequest(system="s", user="u", allowance={"max_calls": 2, "unknown": 1})


def test_completion_request_scripted_is_called_by_the_stub_only_and_never_dumped():
    req = CompletionRequest(system="s", user="u", scripted=lambda: "x")
    assert req.scripted() == "x"
    assert "scripted" not in req.model_dump()


@pytest.mark.parametrize("bad", [{"effort": "medium"}, {"max_tokens": 0}, {"timeout_s": 0}, {"timeout_s": -1}, {"images": "a.png"}])
def test_completion_request_refuses_bad_values(bad):
    with pytest.raises(ValidationError):
        CompletionRequest(system="s", user="u", **bad)


def test_completion_result_fields():
    assert list(CompletionResult.model_fields) == ["text", "model", "provider", "input_tokens", "output_tokens", "usd",
                                                   "duration_ms", "session_id", "structured", "note", "detail"]
    res = CompletionResult(text="t")
    assert all(getattr(res, name) is None for name in list(CompletionResult.model_fields)[1:])
    with pytest.raises(ValidationError):
        CompletionResult(text="t", cost=1)


def test_port_info_and_preflight_result():
    assert list(PortInfo.model_fields) == ["provider", "model", "mock"]
    assert PortInfo(provider=None, model=None, mock=True).mock is True
    with pytest.raises(ValidationError):
        PortInfo(mock=True)                               # provider and model are required (they may be null)
    assert list(PreflightResult.model_fields) == ["ok", "message", "providers"]
    assert PreflightResult(ok=True, message="m", providers=[{"name": "claude"}]).providers == [{"name": "claude"}]


# ---- errors -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cls, code, retryable", [
    (ModelError, "model_error", False), (NoModelAvailable, "no_model", False), (CliMissing, "cli_missing", False),
    (NotSignedIn, "not_signed_in", False), (QuotaExhausted, "quota", False), (ModelTimeout, "timeout", True),
    (StructuredOutputFailed, "structured", False)])
def test_model_error_family_codes(cls, code, retryable):
    assert (cls.code, cls.retryable) == (code, retryable)
    err = cls("boom")
    assert isinstance(err, ModelError) and isinstance(err, RuntimeError) and str(err) == "boom"


def test_model_error_family_is_exactly_the_six_subclasses():
    subclasses = {obj for obj in vars(port).values() if inspect.isclass(obj) and issubclass(obj, ModelError) and obj is not ModelError}
    assert subclasses == {NoModelAvailable, CliMissing, NotSignedIn, QuotaExhausted, ModelTimeout, StructuredOutputFailed}


def test_a_model_error_keeps_j2s_crash_path_working():
    """J2 catches RuntimeError around structured output (j2.py:7095) and in `_run_safe`."""
    with pytest.raises(RuntimeError):
        raise QuotaExhausted("out of quota")


# ---- the protocol -------------------------------------------------------------------------------------------------

def test_scripted_port_is_a_model_port():
    assert isinstance(ScriptedPort(), ModelPort)


def test_a_class_missing_a_method_is_not_a_model_port():
    class Half:
        def describe(self): ...
        def preflight(self): ...
        def complete(self, req, on_progress=None): ...
    assert not isinstance(Half(), ModelPort)


def test_complete_takes_the_request_and_an_optional_progress_callback():
    params = list(inspect.signature(ScriptedPort.complete).parameters)
    assert params == ["self", "req", "on_progress"]
    assert inspect.signature(ScriptedPort.complete).parameters["on_progress"].default is None


# ---- the engine never sends an allowance (S1-contracts-06) --------------------------------------------------------

class _Recorder:
    """A ModelPort that keeps every request it is given."""

    def __init__(self):
        self.requests = []

    def describe(self):
        return PortInfo(provider="claude", model="sonnet", mock=False)

    def preflight(self):
        return PreflightResult(ok=True, message="ok", providers=[])

    def complete(self, req, on_progress=None):
        self.requests.append(req)
        return CompletionResult(text="{}")

    def close(self):
        pass


def test_ask_has_no_allowance_parameter():
    assert "allowance" not in inspect.signature(llm.ask).parameters


@pytest.mark.parametrize("tag", [
    {}, {"function": "identity", "step": 1}, {"function": "W-3", "atom": "W-3.a1", "call_no": 9}, {"function": "audit", "role": "judge", "purpose": "judge"},
    {"function": "reviewer", "purpose": "review"}, {"function": "summariser", "purpose": "summary"}, {"function": "template", "purpose": "template"},
    {"function": "validator"}, {"function": "chat_agent", "stage": "decide", "purpose": "chat_plan"}])
def test_every_request_the_engine_builds_has_allowance_none(tag, llm_reset):
    recorder = _Recorder()
    llm.configure(recorder)
    with llm.tagged(**tag):
        llm.ask("system", "user", lambda: "x", json_mode=True, schema={"type": "object"})
    llm.ask("system", "user", lambda: "x", tag=CallTag(**tag))
    assert len(recorder.requests) == 2
    assert [r.allowance for r in recorder.requests] == [None, None]


# ---- the twin: one assertion set for every J2-mock port -----------------------------------------------------------

def _router_port_available() -> bool:
    try:
        return importlib.util.find_spec("sutra_app.connectors.engine_port") is not None
    except ModuleNotFoundError:
        return False


class _Sink:
    def __init__(self):
        self.rows = []

    def record(self, row):
        self.rows.append(dict(row) if isinstance(row, dict) else row.model_dump())
        return len(self.rows)


@pytest.fixture(params=[
    "scripted",
    pytest.param("router_stub", marks=pytest.mark.skipif(
        not _router_port_available(),
        reason="sutra_app.connectors.engine_port is not merged yet (CN-7): this set then also runs against its stub-only make_port"))])
def twin(request, tmp_path):
    sink = _Sink()
    if request.param == "scripted":
        made = ScriptedPort(sink, delay=0.0)
    else:
        from sutra_app.connectors.engine_port import make_port
        made = make_port(PortSpec(mock=True, connector="stub", run_id="j2-20261104-100004-7f3a", dept_id="web",
                                  task_id="tsk_a1b2c3d4e5f6", data_dir=str(tmp_path)), usage_sink=sink)
    yield made, sink
    made.close()


TAG = CallTag(run_id="j2-20261104-100004-7f3a", dept_id="web", task_id="tsk_a1b2c3d4e5f6", function="audit", step=7,
              call_no=12, atom="W-1.a2", purpose="review")


def _request(scripted, **kwargs):
    return CompletionRequest(system="You are Audit.", user="Check the site.", scripted=scripted, **kwargs)


def test_twin_describes_itself_and_survives_close_twice(twin):
    made, _ = twin
    info = made.describe()
    assert isinstance(info, PortInfo) and info.mock is True
    assert isinstance(made.preflight(), PreflightResult) and made.preflight().ok is True
    made.close()
    made.close()


def test_twin_honours_scripted_and_returns_it_unstripped(twin):
    made, _ = twin
    res = made.complete(_request(lambda: '  {"a": 1}\n'))
    assert isinstance(res, CompletionResult)
    assert res.text == '  {"a": 1}\n'


def test_twin_hands_one_usage_row_to_the_sink_per_request_and_the_tag_reaches_it(twin):
    made, sink = twin
    made.complete(_request(lambda: "x" * 40, tag=TAG))
    assert len(sink.rows) == 1
    row = sink.rows[0]
    assert (row["provider"], row["model"], row["how"], row["ok"], row["usd"]) == ("stub", "scripted", "stub", True, 0.0)
    assert (row["fn"], row["step"], row["purpose"]) == ("audit", "J2.g", "review")
    assert row["atom_id"] == "W-1.a2"
    assert (row["task_id"], row["dept_id"]) == ("tsk_a1b2c3d4e5f6", "web")
    assert row["call_ref"] == "j2-20261104-100004-7f3a:12"
    assert isinstance(row["seconds"], (int, float)) and row["seconds"] >= 0


def test_twin_counts_tokens_as_characters_over_four(twin):
    made, sink = twin
    made.complete(_request(lambda: "y" * 400))
    row = sink.rows[0]
    assert abs(row["tokens_out"] - 100) <= 1
    assert isinstance(row["tokens_in"], int) and 0 <= row["tokens_in"] <= (len("You are Audit.") + len("Check the site.")) // 4 + 1


def test_twin_gives_an_unnumbered_call_a_request_key_and_every_request_its_own_row(twin):
    made, sink = twin
    for _ in range(3):
        made.complete(_request(lambda: "ok"))
    assert len(sink.rows) == 3
    refs = [row["call_ref"] for row in sink.rows]
    assert all(ref.startswith("r:") for ref in refs) and len(set(refs)) == 3


def test_twin_error_from_scripted_is_a_model_error(twin):
    made, _ = twin

    def boom():
        raise ModelTimeout("slow")
    with pytest.raises(ModelError):
        made.complete(_request(boom))


def test_twin_accepts_the_request_with_no_allowance(twin):
    made, sink = twin
    made.complete(_request(lambda: "ok", allowance=None))
    assert len(sink.rows) == 1
