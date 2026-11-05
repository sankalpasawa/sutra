"""The model seam (S1-contracts-02, -05, -06, -07; S4-fnodes-07): one signature in one place, the engine's stub twin (`ScriptedPort`)
equal to the connectors' stub-only router, and the chat agent's path through `AsyncConnector` writing the same ledger."""
import ast
import asyncio
import inspect
from pathlib import Path

import pytest

from sutra_app.connectors import engine_port, models, orchestrator_port, router
from sutra_app.connectors.engine_port import make_port
from sutra_app.connectors.usage import UsageSink
from sutra_app.engine import llm
from sutra_app.engine import port as engine_port_module
from sutra_app.engine.port import Allowance, CallTag, CompletionRequest, ModelPort, PortSpec
from sutra_app.library.types import overhead_atom_id

from .test_contract_world import World, clock, db, events, ids, settings, tenv, world  # noqa: F401  (fixtures used by name)

CONNECTORS = Path(engine_port.__file__).resolve().parent
RUN = "j2-20261104-100004-7f3a"
TAG = CallTag(run_id=RUN, dept_id="web", task_id="tsk_a1b2c3d4e5f6", function="audit", step=7, call_no=12, atom="W-1.a2", purpose="review")
DETAIL_FREE = ("provider", "model", "purpose", "session_id", "node_id", "task_id", "dept_id", "fn", "step", "atom_id", "usd", "tokens_in",
               "tokens_out", "seconds", "ok", "how", "call_ref")


class Rows:
    def __init__(self):
        self.rows = []

    def record(self, row):
        self.rows.append(dict(row) if isinstance(row, dict) else row.model_dump())
        return len(self.rows)


def spec(tmp_path, **over) -> PortSpec:
    return PortSpec(**{"mock": True, "connector": "stub", "run_id": RUN, "dept_id": "web", "task_id": "tsk_a1b2c3d4e5f6",
                       "data_dir": str(tmp_path), **over})


# ---- one signature, one place -----------------------------------------------------------------------------------------------------

def test_make_port_has_exactly_the_agreed_signature():
    params = inspect.signature(make_port).parameters
    assert list(params) == ["spec", "usage_sink"]
    assert params["spec"].annotation is PortSpec and params["spec"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params["usage_sink"].kind is inspect.Parameter.KEYWORD_ONLY and params["usage_sink"].default is None
    assert inspect.signature(make_port).return_annotation is ModelPort


def test_make_port_is_defined_once_and_the_two_types_come_from_the_engine():
    defined = [str(path.relative_to(CONNECTORS.parent)) for path in sorted(CONNECTORS.parent.rglob("*.py")) if "seed" not in path.parts
               for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.FunctionDef) and node.name == "make_port"]
    assert defined == ["connectors/engine_port.py"]
    assert engine_port.PortSpec is engine_port_module.PortSpec and models.Allowance is engine_port_module.Allowance is router.Allowance
    assert engine_port.CallTag is engine_port_module.CallTag is models.CallTag
    assert list(PortSpec.model_fields) == ["mock", "connector", "run_id", "dept_id", "task_id", "data_dir"]       # no `model`, no RunSpec fields
    assert list(Allowance.model_fields) == ["max_calls", "max_usd", "deadline", "envelope_id"]


def test_the_run_spec_never_appears_in_the_connector_layer():
    for path in sorted(CONNECTORS.rglob("*.py")):
        names = {node.id for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.Name)}
        names |= {alias.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.ImportFrom) for alias in node.names}
        assert "RunSpec" not in names and "TaskSpec" not in names, path.name


# ---- the twin ----------------------------------------------------------------------------------------------------------------------

def run_both(tmp_path, scripted, **req_kwargs):
    seen = {}
    for name in ("scripted", "router"):
        sink = Rows()
        port = llm.ScriptedPort(sink, delay=0.0) if name == "scripted" else make_port(spec(tmp_path), usage_sink=sink)
        seen[name] = (port.complete(CompletionRequest(system="You are Audit.", user="Check the site.", scripted=scripted, **req_kwargs)), sink.rows, port)
    return seen


def test_the_stub_only_router_answers_like_the_engines_scripted_port(tmp_path):
    seen = run_both(tmp_path, lambda: "x" * 40, tag=TAG)
    (res_a, rows_a, _), (res_b, rows_b, _) = seen["scripted"], seen["router"]
    for field in ("text", "model", "provider", "input_tokens", "output_tokens", "usd", "session_id", "structured"):
        assert getattr(res_a, field) == getattr(res_b, field), field
    assert (res_a.provider, res_a.model, res_a.usd) == ("stub", "scripted", 0.0)
    assert len(rows_a) == len(rows_b) == 1
    assert {key: rows_a[0][key] for key in DETAIL_FREE} == {key: rows_b[0][key] for key in DETAIL_FREE}
    seen["router"][2].close()


def test_both_ports_hand_over_one_row_for_a_failed_request_and_one_per_request_otherwise(tmp_path):
    for make in (lambda sink: llm.ScriptedPort(sink, delay=0.0), lambda sink: make_port(spec(tmp_path), usage_sink=sink)):
        sink = Rows()
        port = make(sink)

        def boom():
            raise engine_port_module.ModelTimeout("slow")
        with pytest.raises(engine_port_module.ModelError):
            port.complete(CompletionRequest(system="s", user="u", scripted=boom, tag=TAG))
        port.complete(CompletionRequest(system="s", user="u", scripted=lambda: "ok", tag=TAG))
        assert [row["ok"] for row in sink.rows] == [False, True] and {row["atom_id"] for row in sink.rows} == {"W-1.a2"}
        port.close()


def test_mock_and_the_stub_word_both_mean_a_stub_only_router_and_nothing_is_ever_spawned(tmp_path):
    for over in ({"mock": True, "connector": "claude"}, {"mock": False, "connector": "stub"}, {"mock": True, "connector": "auto"}):
        port = make_port(spec(tmp_path, **over))
        assert port.describe().mock is True and list(port.router.connectors) == ["stub"], over
        assert port.preflight().ok is True
        port.close()


def test_a_make_port_without_a_sink_is_fine_and_the_router_sink_is_the_one_given(tmp_path):
    assert make_port(spec(tmp_path)).router.usage_sink is None
    sink = Rows()
    assert make_port(spec(tmp_path), usage_sink=sink).router.usage_sink is sink


def test_the_engine_sends_no_allowance_and_the_router_reads_none_as_the_empty_one(tmp_path):
    assert "allowance" not in inspect.signature(llm.ask).parameters
    assert CompletionRequest.model_fields["allowance"].default is None
    sink = Rows()
    port = make_port(spec(tmp_path), usage_sink=sink)
    port.complete(CompletionRequest(system="s", user="u", scripted=lambda: "ok", tag=TAG))
    assert sink.rows[0]["detail"]["envelope_id"] is None
    port.complete(CompletionRequest(system="s", user="u", scripted=lambda: "ok", tag=TAG, allowance=Allowance(max_calls=3, envelope_id="a-3f9a1c2b7d-01")))
    assert sink.rows[1]["detail"]["envelope_id"] == "a-3f9a1c2b7d-01"


# ---- the chat agent's path ---------------------------------------------------------------------------------------------------------

def test_the_chat_agent_call_is_tagged_from_the_orchestrators_words_and_the_server_writes_its_row(world):
    from sutra_app.connectors.orchestrator_port import AsyncConnector, build_tag
    tag = build_tag("chat_agent", "decide", {"purpose": "chat_plan", "task_id": "tsk_a1b2c3d4e5f6", "atom_id": overhead_atom_id("req-12")})
    assert (tag.function, tag.stage, tag.step, tag.purpose, tag.task_id) == ("chat_agent", "decide", 0, "chat_plan", "tsk_a1b2c3d4e5f6")
    assert tag.atom == overhead_atom_id("req-12")
    connector = AsyncConnector(world.connector_router)
    assert connector.records_usage is True and isinstance(world.connector_router.usage_sink, UsageSink)
    value, usd, how = asyncio.run(connector.call_json(
        "Plan the work", function="chat_agent", step="plan", context={"purpose": "chat_plan", "atom_id": overhead_atom_id("req-12")}))
    assert isinstance(value, dict) and how == "stub"
    row = world.t.sql("SELECT * FROM usage_ledger ORDER BY id DESC LIMIT 1").fetchone()
    assert (row["fn"], row["purpose"], row["provider"], row["atom_id"]) == ("chat_agent", "chat_plan", "stub", overhead_atom_id("req-12"))
    assert row["call_ref"].startswith("r:") and row["task_id"] is None
    assert world.t.one("SELECT count(*) FROM usage_ledger WHERE atom_id IS NULL") == 0
    assert orchestrator_port.build_tag is build_tag
