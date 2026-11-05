"""The engine's run events against the orchestrator's `RunEvent` union, unconditionally (work package E7, engine design 4.5 and 9).

`test_engine_events.py` keeps a conditional check for the case that ORCH-1 has not merged; this file imports
`sutra_app.orchestrator.models` at the top and fails loudly if it cannot. Four sources are validated STRICTLY (`extra="forbid"`,
the way the engine's tests parse; the server's Projector ignores unknown fields):

    the eight builders of `sutra_app.engine.events`, with representative arguments
    a live mock run (every line of `events.jsonl`: node, step, heartbeat and the builders' `atom/1` views included)
    the function-node events of that run, down to the library's own checks of the atom body, the card and the ledger row
    the golden file `golden/run_events.jsonl`
"""
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from sutra_app.engine import events as ev
from sutra_app.library.atom import Card
from sutra_app.library.gate import GATE
from sutra_app.orchestrator.models import RUN_EVENT_TYPES, EventParseError, RunEvent, parse_event

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "tests" / "engine" / "golden"


def _load_recorder():
    spec = importlib.util.spec_from_file_location("record_fn_golden", REPO / "scripts" / "record_fn_golden.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rec = _load_recorder()
ADAPTER = TypeAdapter(RunEvent)
RUN = rec.RUN_ID
ATOM_V1 = {"id": "W-1.a2", "schema": "atom/1", "goal": "Write the menu section", "work_kind": "llm", "verify_template": "contains",
           "status": "closed", "attempt": 1, "closed_by": "verify", "reason": None, "body": {"id": "W-1.a2"}, "ts_open": 1793748000,
           "ts_closed": 1793748060}
ATOM_V03 = {"id": "a-3f9a1c2b7d-01", "schema": "work-atom/0.3", "goal": "The charter is stamped", "work_kind": "llm",
            "verify_template": "charter-stamp", "status": "open", "attempt": 0, "closed_by": None, "reason": None,
            "body": {"state": "open"}, "ts_open": 1793748000, "ts_closed": None}
TASK = {"id": "t-1", "kind": "intake", "summary": "J2.a Enough information to work?: intake", "state": "running", "set_by": "system"}
USAGE = dict(fn="identity", step="J2.a", atom="a-3f9a1c2b7d-01", provider="claude", model="sonnet", purpose="agent_turn", usd=0.012,
             tokens_in=3100, tokens_out=240, seconds=6.2, ok=True, how="native", call_ref=RUN + ":1", detail={"retries": 0})
CARD = {"label": "WORK ATOM OPEN", "goal": "The charter is stamped", "rows": [{"label": "Ref", "text": "a-3f9a1c2b7d-01"}]}


def samples() -> dict[str, dict]:
    return {
        "run.started": ev.run_started_event(pid=48211, mock=False, seed="rehydrated"),
        "say": ev.say_event(id=3, who="identity", text="@Requester What are your opening hours?", to_user=True, act="ASK_REQUESTER",
                            pause="info", questions=[{"question": "What are your opening hours?", "options": []}], next="user"),
        "node fn": ev.node_event(fn="identity", status="waiting_on_you", detail="Waiting for your answer", calls=1, seconds=6.2,
                                 task=TASK, context=[("charter", "none yet")], wait_on="you", tokens={"input": 3100, "output": 240}),
        "node step": ev.node_event(step="team:cook", status="left_open"),
        "step": ev.step_event(step="W-2", name="Menu", status="running", parent="box-1", handoff=["W-3"], reads=["W-1"], rework="W-1"),
        "atom/1": ev.atom_event(node="W-1", atom=ATOM_V1),
        "work-atom open": ev.atom_event(node="web.identity", atom=ATOM_V03, outcome="opened", card=CARD),
        "work-atom closed": ev.atom_event(node="web.identity", atom={**ATOM_V03, "status": "closed", "closed_by": "verify", "ts_closed": 1793748001},
                                          outcome="closed", card=CARD, ledger={"atom_id": ATOM_V03["id"], "status": "closed"}),
        "work-atom abandoned": ev.atom_event(node="web.identity", atom={**ATOM_V03, "status": "abandoned", "attempt": 2,
                                                                       "reason": "verify failed: charter-stamp: x"},
                                             outcome="abandoned", card=CARD, ledger={"atom_id": ATOM_V03["id"], "status": "verify_failed"}),
        "usage": ev.usage_event(**USAGE),
        "usage stub": ev.usage_event(**{**USAGE, "provider": "stub", "usd": None, "tokens_in": None, "tokens_out": None, "detail": None}),
        "heartbeat": ev.heartbeat_event(),
        "run.ended done": ev.run_ended_event(status="done", outcome="Done: the site is workable."),
        "run.ended crashed": ev.run_ended_event(status="crashed", outcome="could not start: x", code="start_failed"),
    }


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    return rec.run_scenario(tmp_path_factory.mktemp("events-contract"), "on")


def golden_lines() -> list[dict]:
    return [json.loads(line) for line in (GOLD / rec.EVENTS_FILE).read_text(encoding="utf-8").splitlines()]


# ---- the closed list -----------------------------------------------------------------------------------------------------
def test_the_engine_and_the_orchestrator_name_the_same_eight_types_in_the_same_order():
    assert tuple(RUN_EVENT_TYPES) == ev.EVENT_TYPES == ("run.started", "say", "node", "step", "atom", "usage", "heartbeat", "run.ended")


@pytest.mark.parametrize("name", list(samples()))
def test_every_builder_output_is_a_run_event_strictly(name):
    line = samples()[name]
    parsed = parse_event(line, strict=True)
    assert parsed.t == line["t"] and ADAPTER.validate_python(line).t == line["t"]
    assert line["at"].endswith("Z") and len(line["at"]) == 20


def test_the_builders_cover_each_of_the_eight_types():
    assert {s["t"] for s in samples().values()} == set(ev.EVENT_TYPES)


# ---- the strictness is real (a contract test that cannot fail proves nothing) ------------------------------------------------
def test_an_unknown_field_is_an_error_in_strict_mode_and_dropped_and_listed_otherwise():
    line = {**ev.heartbeat_event(), "beat": 7}
    with pytest.raises(EventParseError) as err:
        parse_event(line, strict=True)
    assert err.value.code == "invalid"
    dropped: list[str] = []
    assert parse_event(line, strict=False, dropped=dropped).t == "heartbeat" and dropped == ["beat"]


def test_an_unknown_type_and_a_line_that_is_not_an_object_are_refused():
    with pytest.raises(EventParseError) as err:
        parse_event({"t": "session", "at": "2026-11-04T10:00:00Z"}, strict=True)
    assert err.value.code == "unknown_type"
    with pytest.raises(EventParseError) as err:
        parse_event("[1]", strict=True)
    assert err.value.code == "not_object"
    with pytest.raises(EventParseError) as err:
        parse_event("{", strict=True)
    assert err.value.code == "not_json"


@pytest.mark.parametrize("bad", [
    {**samples()["atom/1"], "outcome": "closed"},                                        # outcome belongs to work-atom/0.3
    {**samples()["work-atom open"], "atom": {**samples()["work-atom open"]["atom"], "status": "verify_failed"}},      # not a stored state
    {**samples()["node fn"], "status": "filed"},                                          # a function node has five statuses
    {**samples()["node fn"], "goal": "x"},                                                # a node event carries no goal
    {**samples()["node fn"], "step": "W-1"},                                              # fn and step are exclusive
    {**samples()["run.ended done"], "code": "internal"},                                   # only a crash has a code
    {**samples()["usage"], "ok": "yes"},
])
def test_what_the_orchestrator_refuses_the_engine_builders_never_produce(bad):
    with pytest.raises(EventParseError):
        parse_event(bad, strict=True)


def test_the_builders_refuse_the_same_shapes_themselves():
    with pytest.raises(ev.EventError):
        ev.node_event(fn="identity", status="filed")
    with pytest.raises(ev.EventError):
        ev.node_event(fn="identity", step="W-1", status="idle")
    with pytest.raises(ev.EventError):
        ev.run_ended_event(status="done", outcome="x", code="internal")
    with pytest.raises(ev.EventError):
        ev.atom_event(node="W-1", atom=ATOM_V1, outcome="closed")


# ---- a live run ----------------------------------------------------------------------------------------------------------
def test_every_line_of_a_live_run_is_a_run_event_strictly_and_all_eight_types_occur(live):
    lines = [(line, parse_event(line, strict=True)) for line in live["events"]]
    assert {line["t"] for line, _ in lines} == set(ev.EVENT_TYPES)
    assert lines[0][0]["t"] == "run.started" and lines[-1][0]["t"] == "run.ended"
    assert [line["t"] for line, _ in lines].count("run.ended") == 1
    # the file itself, line by line, as the watcher reads it
    raw = (live["run_dir"] / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw) == len(live["events"]) and all(parse_event(r, strict=True) for r in raw)


def test_the_function_node_events_of_a_run_carry_no_goal_and_one_turn_state(live):
    nodes = [e for e in live["events"] if e["t"] == "node" and "fn" in e]
    assert nodes and all("goal" not in e and e["status"] in ev.FUNCTION_STATUSES for e in nodes)
    tasked = [e for e in nodes if "task" in e]
    assert tasked and {e["task"]["state"] for e in tasked} == {"running", "done"}
    assert all(e["task"]["id"].startswith("t-") and len(e["task"]["summary"]) <= 300 for e in tasked)
    assert {e["fn"] for e in nodes} == set(rec.FUNCTIONS)


def test_the_function_atom_events_carry_what_the_library_checks(live):
    atoms = rec.function_atom_events(live["events"])
    assert len(atoms) > 60
    for e in atoms:
        body = GATE.check("atom", e["atom"]["body"])                     # strict model, cross rules, canonical JSON
        assert body.model.id == e["atom"]["id"] and body.model.state == e["atom"]["status"]
        assert body.model.ts_open == e["atom"]["ts_open"]
        Card.model_validate(e["card"])
        if e["ledger"] is not None:
            assert GATE.check("atom_ledger_row", e["ledger"]).model.atom_id == e["atom"]["id"]
            assert e["outcome"] in ("closed", "abandoned", "refused")
        else:
            assert e["outcome"] in ("opened", "verify_failed")


def test_builder_atoms_are_atom_1_views_without_the_function_fields(live):
    views = [e for e in live["events"] if e["t"] == "atom" and e["atom"]["schema"] == "atom/1"]
    assert views and all(e["atom"]["id"].startswith("W-") and "outcome" not in e and "card" not in e and "ledger" not in e for e in views)


def test_usage_lines_of_a_live_run_all_name_an_atom(live):
    usage = [parse_event(e, strict=True) for e in live["events"] if e["t"] == "usage"]
    assert len(usage) > 25 and all(u.atom for u in usage)
    assert {u.provider for u in usage} == {"stub"} and len({u.call_ref for u in usage}) == len(usage)


# ---- the golden file -----------------------------------------------------------------------------------------------------
def test_the_golden_event_file_validates_line_by_line_strictly():
    lines = golden_lines()
    for line in lines:
        parse_event(line, strict=True)
    types = [line["t"] for line in lines]
    assert types[0] == "run.started" and types[-1] == "run.ended"
    assert set(types) == set(rec.GOLDEN_EVENT_TYPES) and {line["at"] for line in lines} == {rec.FIXED_AT}


def test_the_golden_event_file_holds_function_atoms_only_with_outcome_card_and_ledger_at_the_end():
    atoms = [line for line in golden_lines() if line["t"] == "atom"]
    assert atoms and all(a["atom"]["schema"] == "work-atom/0.3" and a["outcome"] and a["card"] for a in atoms)
    ends = [a for a in atoms if a["outcome"] in ("closed", "abandoned")]
    assert all(a["ledger"] for a in ends) and not [a for a in atoms if a not in ends and a["ledger"]]


def test_the_golden_event_file_agrees_with_the_atoms_golden():
    lines = golden_lines()
    atoms_file = json.loads((GOLD / rec.ATOMS_FILE).read_text(encoding="utf-8"))
    measured = rec.atoms_golden(lines, [])
    assert [a for a in measured["atoms"]] == atoms_file["atoms"]
    assert measured["usage"] == atoms_file["usage"]
    assert [c["outcome"] for c in lines if c["t"] == "atom" and c["atom"]["id"] == atoms_file["atoms"][0]["id"]] == ["opened", "closed"]
