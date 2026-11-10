"""Usage with atom ids, from the engine's `llm.ask` to the ledger and the API (S1-contracts-05, -10, S2-models-10, S4-fnodes-07).

One builder (the Router builds one `UsageIn` per request, a failed one included), two sinks, one ledger writer. A call inside a function
turn carries that atom's id, a builder call carries J2's own id (stored as `<run id>:<id>`), every other call carries the run's overhead
key: the ledger has no row without an atom, per-atom sums equal the total, and the total without stub rows is the provider bill."""
import ast
import json
import re
import sqlite3
from pathlib import Path

import pytest

from sutra_app.connectors import usage as connector_usage
from sutra_app.connectors.engine_port import make_port
from sutra_app.connectors.usage import MemoryUsageSink, UsageIn, UsageSink
from sutra_app.engine import llm
from sutra_app.engine.events import EventUsageSink, EventWriter, usage_event
from sutra_app.engine.fnodes.ids import AtomIds, run_overhead_id
from sutra_app.engine.port import CallTag, ModelTimeout, PortSpec
from sutra_app.library.types import ATOM_ID_PATTERN, function_node_id
from sutra_app.orchestrator import projector
from sutra_app.orchestrator.usage import UsageStore

from .test_contract_world import World, clock, db, events, ids, jsonl, settings, tenv, world  # noqa: F401  (fixtures used by name)

APP = Path(connector_usage.__file__).resolve().parents[1]
RUN = "j2-20261104-100004-7f3a"


class Chain:
    """The real chain on one run folder: `llm.ask` -> stub-only Router -> `EventUsageSink` -> `events.jsonl` -> Projector -> ledger."""

    def __init__(self, w: World, monkeypatch) -> None:
        self.w = w
        self.task = w.t.started()
        self.run_dir = w.t.run_dir(self.task)
        self.run_id = w.t.row(self.task).run_id
        self.writer = EventWriter(self.run_dir)
        self.overhead = run_overhead_id(self.run_id)
        sink = EventUsageSink(self.writer, default_atom=self.overhead)
        self.port = make_port(PortSpec(mock=True, connector="stub", run_id=self.run_id, dept_id="web", task_id=self.task,
                                       data_dir=str(w.t.settings.data_dir)), usage_sink=sink)
        for name, value in (("_PORT", None), ("_DEFAULT_PORT", None), ("_BASE_TAG", CallTag()), ("_BOUND_ATOM", None), ("MOCK", False),
                            ("PROVIDER", None), ("MODEL", None)):
            monkeypatch.setattr(llm, name, value)
        llm.configure(self.port, mock=True, base_tag=CallTag(run_id=self.run_id, dept_id="web", task_id=self.task))
        llm.bind_atom(self.overhead)

    def ask(self, text: str = "ok", **tag) -> str:
        with llm.tagged(**tag):
            return llm.ask("system", "user", lambda: text)

    def ingest(self) -> None:
        while self.w.t.drain(self.task).more:
            pass

    def usage_lines(self) -> list[dict]:
        return [e for e in jsonl(self.run_dir / "events.jsonl") if e["t"] == "usage"]

    def rows(self) -> list[sqlite3.Row]:
        return list(self.w.t.sql("SELECT * FROM usage_ledger WHERE task_id = ? ORDER BY id", self.task))


@pytest.fixture
def chain(world, monkeypatch):
    made = Chain(world, monkeypatch)
    yield made
    made.port.close()
    made.writer.close()


def first_atom(chain: Chain) -> str:
    return AtomIds().next(chain.run_id, function_node_id("web", "identity"))


# ---- one builder, two sinks, one ledger writer ------------------------------------------------------------------------------------

def test_there_is_one_usage_row_class_and_both_sinks_satisfy_the_sink_protocol(world):
    defined = [f"{path.relative_to(APP)}" for path in sorted(APP.rglob("*.py")) if "seed" not in path.parts
               for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.ClassDef) and node.name == "UsageIn"]
    assert defined == ["connectors/usage.py"]
    assert projector.UsageIn is UsageIn
    assert isinstance(world.t.usage, UsageSink) and isinstance(EventUsageSink(object()), UsageSink) and isinstance(MemoryUsageSink(), UsageSink)
    assert isinstance(world.t.usage, UsageStore) and world.services.usage is world.t.usage


def test_the_ledger_has_step_and_atom_columns_and_the_atom_has_no_foreign_key(world):
    columns = {row["name"] for row in world.t.sql("PRAGMA table_info(usage_ledger)")}
    assert {"step", "atom_id", "detail_json", "call_ref"} <= columns
    assert "atom_id" not in {row["from"] for row in world.t.sql("PRAGMA foreign_key_list(usage_ledger)")}   # an overhead key names no atoms row


# ---- the atom id rides on every call ----------------------------------------------------------------------------------------------

def test_a_call_in_a_function_turn_a_builder_call_and_a_call_outside_any_turn_each_reach_the_ledger_with_their_atom(chain):
    atom = first_atom(chain)
    llm.bind_atom(atom)                                                                  # the layer, after open_atom
    chain.ask("a" * 40, function="identity", step=1, call_no=1)
    chain.ask("b" * 40, function="identity", step=1, call_no=2, purpose="summary")      # a helper call of the same turn
    llm.bind_atom(chain.overhead)                                                        # the layer, at turn_finished
    chain.ask("c" * 40, function="W-1", atom="W-1.a2", call_no=3)                        # a builder: J2's own tag wins
    chain.ask("d" * 40, function="summariser", purpose="summary", call_no=4)             # outside any turn: the overhead key
    lines = chain.usage_lines()
    assert [line["atom"] for line in lines] == [atom, atom, "W-1.a2", chain.overhead]
    chain.ingest()
    rows = chain.rows()
    assert [row["atom_id"] for row in rows] == [atom, atom, f"{chain.run_id}:W-1.a2", chain.overhead]
    assert [row["step"] for row in rows] == ["J2.a", "J2.a", "W-1", None]
    assert [row["call_ref"] for row in rows] == [f"{chain.run_id}:{n}" for n in (1, 2, 3, 4)]
    assert {row["provider"] for row in rows} == {"stub"} and {row["task_id"] for row in rows} == {chain.task}


def test_no_row_the_engine_writes_has_a_null_atom_even_for_an_untagged_call(chain):
    chain.ask("x" * 8)                                                                   # no function, no atom, no call number
    llm.bind_atom(None)                                                                  # and not even the host's binding
    chain.ask("y" * 8, function="audit")
    chain.ingest()
    rows = chain.rows()
    assert len(rows) == 2
    assert [row["atom_id"] for row in rows] == [chain.overhead, chain.overhead]          # the sink's default_atom closes the gap
    assert all(row["call_ref"].startswith("r:") for row in rows)                         # no call number: the request id keys it
    assert chain.w.t.one("SELECT count(*) FROM usage_ledger WHERE atom_id IS NULL") == 0


def test_the_overhead_key_is_an_atom_id_that_names_no_atoms_row(chain):
    assert re.fullmatch(ATOM_ID_PATTERN, chain.overhead)
    chain.ask("z" * 8)
    chain.ingest()
    assert chain.w.t.one("SELECT count(*) FROM atoms WHERE id = ?", chain.overhead) == 0
    assert chain.w.t.one("SELECT count(*) FROM atom_ledger WHERE atom_id = ?", chain.overhead) == 0


def test_a_failed_request_still_leaves_exactly_one_row_with_its_atom(chain):
    atom = first_atom(chain)
    llm.bind_atom(atom)

    def times_out():
        raise ModelTimeout("slow")
    with pytest.raises(Exception), llm.tagged(function="identity", step=1, call_no=7):
        llm.ask("system", "user", times_out)
    lines = chain.usage_lines()
    assert len(lines) == 1 and lines[0]["ok"] is False and lines[0]["atom"] == atom
    chain.ingest()
    row = chain.rows()[0]
    assert (row["ok"], row["atom_id"], row["call_ref"]) == (0, atom, f"{chain.run_id}:7")


def test_a_second_delivery_of_the_same_lines_changes_nothing(chain):
    chain.ask("a" * 40, function="identity", step=1, call_no=1)
    chain.ask("b" * 40, function="audit", step=7, call_no=2)
    chain.ingest()
    before = [tuple(row) for row in chain.rows()]
    path = chain.run_dir / "events.jsonl"
    path.write_bytes(path.read_bytes() * 2)                                              # the same file twice, as a replay does
    chain.ingest()
    assert [tuple(row) for row in chain.rows()] == before


# ---- sums -----------------------------------------------------------------------------------------------------------------------------

def test_per_atom_sums_equal_the_total_and_stub_rows_are_left_out_unless_asked(chain):
    atom = first_atom(chain)
    llm.bind_atom(atom)
    for n in (1, 2, 3):
        chain.ask("a" * 40, function="identity", step=1, call_no=n)
    llm.bind_atom(chain.overhead)
    chain.ask("b" * 400, function="W-1", atom="W-1.a1", call_no=4)
    chain.writer.emit(usage_event(fn="audit", step="J2.g", atom=atom, provider="claude", model="sonnet", purpose="agent_turn", usd=0.0123,
                                  tokens_in=3000, tokens_out=200, seconds=4.0, ok=True, how="native", call_ref=f"{chain.run_id}:5", detail=None))
    chain.ingest()
    client = chain.w.client
    everything = client.get("/api/usage", params={"task_id": chain.task, "include_stub": 1}).json()
    groups = client.get("/api/usage/summary", params={"by": "atom", "include_stub": 1}).json()["groups"]
    assert everything["totals"]["calls"] == sum(g["calls"] for g in groups) == 5
    assert everything["totals"]["tokens_in"] == sum(g["tokens_in"] for g in groups)
    assert everything["totals"]["tokens_out"] == sum(g["tokens_out"] for g in groups)
    by_atom = {g["key"]: g for g in groups}
    assert by_atom[atom]["calls"] == 4 and by_atom[f"{chain.run_id}:W-1.a1"]["calls"] == 1
    assert "(none)" not in by_atom                                                      # no row without an atom
    bill = client.get("/api/usage", params={"task_id": chain.task}).json()["totals"]       # stub rows excluded
    assert (bill["calls"], bill["usd"], bill["tokens_in"]) == (1, 0.0123, 3000)
    assert {g["key"]: g["calls"] for g in client.get("/api/usage/summary", params={"by": "atom"}).json()["groups"]} == {atom: 1}


def test_per_purpose_sums_equal_the_total_and_the_purposes_the_engine_tags_are_the_ledgers(chain):
    """D159: a turn's own call, the late judge's planner and judge calls (D145) and a helper's reach the ledger under the purpose the engine tagged them with, and `by=purpose`
    groups them: the groups add up to the total, with the stub rows and without them (the provider bill, by purpose)."""
    atom = first_atom(chain)
    llm.bind_atom(atom)
    chain.ask("a" * 40, function="adaptation", step=1, call_no=1)                                                  # a turn: the tag's own purpose, agent_turn
    chain.ask("b" * 40, function="adaptation", step=1, call_no=2, role="planner", purpose="plan")                  # the late judge has Adaptation plan ...
    chain.ask("c" * 40, function="adaptation", step=1, call_no=3, role="judge", purpose="judge")                   # ... and a judge score the plan
    chain.ask("d" * 40, function="priority", step=2, call_no=4, role="judge", purpose="judge")
    chain.ask("e" * 40, function="summariser", call_no=5, purpose="summary")                                       # a helper of the turn
    chain.writer.emit(usage_event(fn="priority", step="J2.c", atom=atom, provider="claude", model="sonnet", purpose="judge", usd=0.0123, tokens_in=3000, tokens_out=200,
                                  seconds=4.0, ok=True, how="native", call_ref=f"{chain.run_id}:6", detail=None))   # the one call a provider billed
    chain.ingest()
    client = chain.w.client
    everything = client.get("/api/usage", params={"task_id": chain.task, "include_stub": 1}).json()
    groups = client.get("/api/usage/summary", params={"by": "purpose", "include_stub": 1}).json()["groups"]
    assert {g["key"]: g["calls"] for g in groups} == {"agent_turn": 1, "plan": 1, "judge": 3, "summary": 1}
    assert sum(g["calls"] for g in groups) == everything["totals"]["calls"] == 6
    assert sum(g["tokens_in"] for g in groups) == everything["totals"]["tokens_in"] and sum(g["tokens_out"] for g in groups) == everything["totals"]["tokens_out"]
    assert round(sum(g["usd"] or 0 for g in groups), 6) == everything["totals"]["usd"] == 0.0123
    assert client.get("/api/usage/summary", params={"by": "purpose"}).json()["groups"] == [
        {"key": "judge", "calls": 1, "usd": 0.0123, "tokens_in": 3000, "tokens_out": 200}]                         # stub rows left out: what the provider billed, by purpose
    assert [r["purpose"] for r in client.get("/api/usage", params={"task_id": chain.task, "include_stub": 1}).json()["rows"]] == [
        "agent_turn", "plan", "judge", "judge", "summary", "judge"]                                                 # the rows are the groups' rows: nothing was renamed on the way


def test_a_usage_line_the_ledger_refuses_is_not_stored_and_does_not_stop_the_run(chain):
    atom = first_atom(chain)
    chain.writer.emit(usage_event(fn="audit", step="J2.g", atom=atom, provider="claude", model="sonnet", purpose="agent_turn", usd=0.01,
                                  tokens_in=10, tokens_out=5, seconds=1.0, ok=True, how="native", call_ref=f"{chain.run_id}:1", detail=None))
    with open(chain.run_dir / "events.jsonl", "ab") as handle:                          # a hand-made line with a provider the ledger does not know
        handle.write(json.dumps({"t": "usage", "at": "2026-11-04T10:00:00Z", "fn": "audit", "atom": atom, "provider": "gemini",
                                 "purpose": "agent_turn", "seconds": 1.0, "ok": True, "how": "native", "call_ref": "x:2"}).encode() + b"\n")
    chain.writer.emit(usage_event(fn="audit", step=None, atom=atom, provider="codex", model="gpt", purpose="agent_turn", usd=None, tokens_in=7,
                                  tokens_out=3, seconds=1.0, ok=True, how="native", call_ref=f"{chain.run_id}:3", detail=None))
    chain.ingest()
    assert [row["call_ref"] for row in chain.rows()] == [f"{chain.run_id}:1", f"{chain.run_id}:3"]
