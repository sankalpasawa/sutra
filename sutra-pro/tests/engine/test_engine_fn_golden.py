"""Function nodes in a whole run (work package E7, engine design 9, function-nodes.md 9 "Golden").

The Brew Lab brief goes through the real engine host in mock mode (J2's `ScriptedPort`, Chrome faked, a fake clock for the layer)
as a vague first line that the Requester answers with the full brief, so Identity asks, the turn pauses and the manual atom
appears. It runs twice, with the function-node layer on and with `SUTRA_NODES=off`; both runs are made once per module
(`scripts/record_fn_golden.py` is the single implementation and the recorder of the two golden files).

What is asserted: the prompts of the two runs are identical; each function has an atom of each kind it handles; one atom per
function turn and never two open at once for a node; none open at `run.ended`; every atom has a check; the ledger rows equal the
terminal atoms; no `usage` line without an atom; the measured story of the layer-on run equals `golden/fn_atoms_brewlab.json` and
its events equal `golden/run_events.jsonl`.
"""
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from sutra_app.library.types import FUNCTIONS, overhead_atom_id

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "tests" / "engine" / "golden"


def _load_recorder():
    spec = importlib.util.spec_from_file_location("record_fn_golden", REPO / "scripts" / "record_fn_golden.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rec = _load_recorder()
ATOMS = json.loads((GOLD / rec.ATOMS_FILE).read_text(encoding="utf-8"))
OVERHEAD = overhead_atom_id(rec.RUN_ID)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    return {mode: rec.run_scenario(tmp_path_factory.mktemp(f"fn-golden-{mode}"), mode) for mode in ("on", "off")}


@pytest.fixture(scope="module")
def on(runs):
    return runs["on"]


@pytest.fixture(scope="module")
def off(runs):
    return runs["off"]


def atom_events(run):
    return rec.function_atom_events(run["events"])


def terminal(run):
    """The last event of every function atom, by id."""
    last = {}
    for e in atom_events(run):
        last[e["atom"]["id"]] = e
    return last


# ---- prompts unchanged ---------------------------------------------------------------------------------------------------
def test_the_prompts_are_identical_with_the_layer_on_and_off(on, off):
    digest_on, digest_off = rec.prompt_digest(on["calls"]), rec.prompt_digest(off["calls"])
    assert len(digest_on) == len(on["calls"]) > 25
    assert digest_on == digest_off, "[function, sha(system), sha(prompt)] per call, in order"


def test_the_prompts_equal_the_recorded_golden(on):
    assert ATOMS["prompts"] == {"calls": len(on["calls"]), "digest": rec.prompt_digest(on["calls"])}


def test_the_run_ends_the_same_way_with_the_layer_on_and_off(on, off):
    assert on["code"] == off["code"] == 0
    ended_on, ended_off = on["events"][-1], off["events"][-1]
    assert ended_on["t"] == ended_off["t"] == "run.ended"
    assert (ended_on["status"], ended_on["outcome"], ended_on["code"]) == (ended_off["status"], ended_off["outcome"], ended_off["code"])
    assert ended_on["status"] == "done"
    said = lambda run: [(e["who"], e["text"]) for e in run["events"] if e["t"] == "say"]       # noqa: E731
    assert said(on) == said(off), "the layer adds no say line and changes none"


def test_the_layer_off_run_has_no_function_atoms_and_every_usage_line_is_a_builder_or_the_overhead(off):
    assert atom_events(off) == []
    atoms = {u["atom"] for u in off["events"] if u["t"] == "usage"}
    assert OVERHEAD in atoms and all(a == OVERHEAD or a.startswith("W-") for a in atoms)


# ---- atoms per function --------------------------------------------------------------------------------------------------
def opened_kinds(run):
    """(function, J2 step letter, work kind) of every opened function atom."""
    out = set()
    for e in atom_events(run):
        if e["outcome"] == "opened":
            fn = e["node"].rpartition(".")[2]
            out.add((fn, e["atom"]["body"]["work"]["steps"].split(" ")[0], e["atom"]["work_kind"]))
    return out


@pytest.mark.parametrize("fn, step, kind", [
    ("identity", "J2.a", "llm"),             # intake
    ("identity", "J2.h", "llm"),             # audit of the finished site
    ("identity", "J2.a", "manual"),          # the owner's answer to the question
    ("adaptation", "J2.b", "llm"),           # propose
    ("priority", "J2.c", "llm"),             # price
    ("priority", "J2.f", "bash"),            # envelope
    ("coordination", "J2.f", "llm"),         # schedule
    ("audit", "J2.g", "llm"),                # audit
])
def test_each_function_has_an_atom_of_each_kind_it_handles(on, fn, step, kind):
    assert (fn, step, kind) in opened_kinds(on)


def test_only_the_five_functions_open_atoms_and_the_five_all_do(on):
    nodes = {e["node"] for e in atom_events(on)}
    assert nodes == {f"{rec.DEPT}.{fn}" for fn in FUNCTIONS}


def test_the_manual_atom_follows_the_paused_turn_and_closes_on_the_answer(on):
    manual = [a for a in ATOMS["atoms"] if a["work_kind"] == "manual"]
    assert [a["checks"] for a in manual] == [["answer-recorded"]]
    final = terminal(on)[manual[0]["id"]]
    assert final["outcome"] == "closed" and final["atom"]["closed_by"] == "verify"
    asked = [e for e in on["events"] if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"]
    assert len(asked) == 1 and asked[0]["who"] == "identity"
    # the order: the question is said, the manual atom opens, the owner's answer closes it
    ids = [(i, e) for i, e in enumerate(on["events"])]
    said_at = next(i for i, e in ids if e["t"] == "say" and e.get("act") == "ASK_REQUESTER")
    opened_at = next(i for i, e in ids if e["t"] == "atom" and e["atom"]["id"] == manual[0]["id"] and e["outcome"] == "opened")
    closed_at = next(i for i, e in ids if e["t"] == "atom" and e["atom"]["id"] == manual[0]["id"] and e["outcome"] == "closed")
    assert said_at < opened_at < closed_at


def test_one_atom_per_function_turn_and_never_two_open_for_a_node(on):
    turns = Counter(t["data"]["function"] for t in on["trace"] if t["type"] == "turn.started" and t["data"]["function"] in FUNCTIONS)
    work_atoms = Counter(e["node"].rpartition(".")[2] for e in atom_events(on) if e["outcome"] == "opened" and e["atom"]["work_kind"] != "manual")
    assert turns == work_atoms and sum(turns.values()) > 25, "every function turn opened exactly one atom"
    pauses = sum(1 for t in on["trace"] if t["type"] == "turn.finished" and t["data"].get("result") == "paused")
    assert sum(1 for e in atom_events(on) if e["outcome"] == "opened" and e["atom"]["work_kind"] == "manual") == pauses == 1
    open_by_node: dict[str, str] = {}
    for e in atom_events(on):
        node, a = e["node"], e["atom"]
        if e["outcome"] == "opened":
            assert node not in open_by_node, f"{a['id']} opened while {open_by_node.get(node)} was still open"
            open_by_node[node] = a["id"]
        elif e["outcome"] in ("closed", "abandoned", "refused"):
            assert open_by_node.pop(node) == a["id"]
    assert not open_by_node


def test_no_atom_is_open_when_the_run_ends(on):
    last = on["events"][-1]
    assert last["t"] == "run.ended"
    assert [e for e in terminal(on).values() if e["atom"]["status"] == "open"] == []
    assert all(e["atom"]["id"] in terminal(on) for e in atom_events(on))
    assert all(e["outcome"] in ("closed", "abandoned") for e in terminal(on).values())


def test_a_failed_close_keeps_the_atom_open_until_the_third_run_or_the_end_of_the_turn(on):
    abandoned = [e for e in terminal(on).values() if e["outcome"] == "abandoned"]
    # GAP-TUNE: the reply classes read every reply of J2's mock, so none is abandoned any more (test_engine_fn_tuning.py lists the
    # allowed ones); the retry path itself is pinned by test_engine_fn_layer.py. Whatever is abandoned still follows the rule.
    for e in abandoned:
        assert e["atom"]["body"]["abandon_code"] == "verify_failed" and e["atom"]["reason"].startswith("verify failed: ")
        tries = [x["outcome"] for x in atom_events(on) if x["atom"]["id"] == e["atom"]["id"]]
        assert tries[0] == "opened" and tries[-1] == "abandoned" and set(tries[1:-1]) == {"verify_failed"} and 1 <= len(tries[1:-1]) <= 2
    assert not [t for t in on["trace"] if t["type"] in ("layer.error", "atom.refused")], "no hook failed and no template was refused"
    assert not [e for e in atom_events(on) if e["outcome"] == "refused"]


def test_every_atom_has_a_check_and_the_event_names_the_first(on):
    for e in atom_events(on):
        checks = e["atom"]["body"]["verify"]["checks"]
        assert checks, e["atom"]["id"]
        assert e["atom"]["verify_template"] == checks[0]["template"]
        assert all(c["relevance"] and c["text"] for c in checks)


def test_the_ledger_rows_equal_the_terminal_atoms(on):
    ledgers = [(e["atom"]["id"], e["ledger"]) for e in atom_events(on) if e.get("ledger")]
    final = terminal(on)
    assert sorted(i for i, _ in ledgers) == sorted(final), "one row per atom, none twice, none missing"
    for atom_id, row in ledgers:
        assert row["atom_id"] == atom_id and row["node_id"] == final[atom_id]["node"]
        failed = final[atom_id]["atom"]["body"]["abandon_code"] == "verify_failed"
        assert row["status"] == ("verify_failed" if failed else "closed")
    assert not [e for e in atom_events(on) if e.get("ledger") and e["outcome"] in ("opened", "verify_failed")], "an open atom has no row"


# ---- cost: no usage line without an atom ---------------------------------------------------------------------------------
def test_no_usage_line_without_an_atom_and_every_atom_is_known(on):
    usage = [e for e in on["events"] if e["t"] == "usage"]
    function_ids = {e["atom"]["id"] for e in atom_events(on)}
    assert len(usage) > 25
    for u in usage:
        assert u["atom"], u
        assert u["atom"] in function_ids or u["atom"] == OVERHEAD or u["atom"].startswith(f"W-"), u["atom"]


def test_a_function_atoms_cost_arrives_while_that_atom_is_open(on):
    open_now: set[str] = set()
    charged = 0
    for e in on["events"]:
        if e["t"] == "atom" and e["atom"]["schema"] == "work-atom/0.3":
            (open_now.add if e["atom"]["status"] == "open" else open_now.discard)(e["atom"]["id"])
        elif e["t"] == "usage" and e["atom"].startswith("a-"):
            if e["atom"] != OVERHEAD:
                assert e["atom"] in open_now, f"{e['call_ref']} was charged to {e['atom']} after it ended"
                charged += 1
    assert charged == ATOMS["usage"]["on_function_atoms"] > 20


def test_calls_outside_a_turn_carry_the_run_overhead_key(on):
    other = [u for u in on["events"] if u["t"] == "usage" and not u["atom"].startswith("W-") and not u["atom"].startswith("a-")]
    other += [u for u in on["events"] if u["t"] == "usage" and u["atom"] == OVERHEAD]
    assert other and {u["atom"] for u in other} == {OVERHEAD}
    assert ATOMS["usage"]["on_other"] == len(other)


# ---- the golden files ----------------------------------------------------------------------------------------------------
def test_the_atoms_of_the_run_equal_the_golden_file(on):
    measured = rec.atoms_golden(on["events"], on["trace"])
    recorded = {k: v for k, v in ATOMS.items() if k != "prompts"}
    assert measured == recorded


def test_the_events_of_the_run_equal_the_golden_event_file(on):
    expected = (GOLD / rec.EVENTS_FILE).read_text(encoding="utf-8")
    assert rec.encode_events(rec.normalized_events(on["events"])) == expected


def test_the_golden_atoms_file_tells_the_story_per_function():
    per = ATOMS["per_function"]
    assert set(per) == set(FUNCTIONS)
    assert sum(v["atoms"] for v in per.values()) == len(ATOMS["atoms"])
    assert {a["failing_check"] for a in ATOMS["atoms"]} == {None}, "no check fails on the mock's replies (GAP-TUNE)"
    assert all(a["ledger"] == {"closed": "closed", "verify_failed": "verify_failed"}[a["final"]["display"]] for a in ATOMS["atoms"])
    assert ATOMS["usage"]["rows"] == sum(v for k, v in ATOMS["usage"].items() if k != "rows")
    assert ATOMS["touches_miss"] == {}, "every record the run saves is named in a function's writes (GAP-TUNE)"


def test_the_recorder_writes_exactly_the_golden_files_and_check_notices_a_stale_one(tmp_path, runs, monkeypatch):
    monkeypatch.setattr(rec, "run_scenario", lambda base, mode, **kw: runs[mode])       # the runs of the fixture: no third and fourth run
    assert rec.main(["--out-dir", str(tmp_path)]) == 0
    for name in (rec.ATOMS_FILE, rec.EVENTS_FILE):
        assert (tmp_path / name).read_text(encoding="utf-8") == (GOLD / name).read_text(encoding="utf-8")
    assert rec.main(["--out-dir", str(tmp_path), "--check"]) == 0
    (tmp_path / rec.ATOMS_FILE).write_text("{}\n")
    assert rec.main(["--out-dir", str(tmp_path), "--check"]) == 1
    (tmp_path / rec.ATOMS_FILE).unlink()
    assert rec.main(["--out-dir", str(tmp_path), "--check"]) == 1, "a missing file is stale too"


def test_the_recorder_refuses_a_layer_that_changes_a_prompt(runs, monkeypatch):
    skewed = {**runs["off"], "calls": [{**runs["off"]["calls"][0], "prompt": "changed"}, *runs["off"]["calls"][1:]]}
    monkeypatch.setattr(rec, "run_scenario", lambda base, mode, **kw: runs["on"] if mode == "on" else skewed)
    with pytest.raises(RuntimeError, match="changed a prompt"):
        rec.record()


# ---- the default wiring --------------------------------------------------------------------------------------------------
def test_the_default_wiring_gives_function_atoms(tmp_path):
    run = rec.run_scenario(tmp_path, "default")
    assert atom_events(run), [t for t in run["trace"] if t["type"] == "publish.error"][:1]


def test_a_stopped_run_leaves_no_atom_open(tmp_path):
    run = rec.run_scenario(tmp_path, "on", stop_on_question=True)
    assert run["code"] == 0 and run["events"][-1]["status"] == "stopped"
    assert any(e["atom"]["work_kind"] == "manual" for e in atom_events(run)), "the question did open its manual atom"
    assert [e["atom"]["id"] for e in terminal(run).values() if e["atom"]["status"] == "open"] == []
