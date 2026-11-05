"""Function nodes across sections (function-nodes.md sections 8, 9; S2-models-05..10, S4-fnodes-07, -10, -11): ids minted by the library
are the ones the engine's events carry and the server stores, no cost row and no log row lacks an atom id, the node `meta` keys are exactly
the ones the chip and the drawer are specified to show, and the engine's host calls the hook factory with arguments the factory takes."""
import ast
import inspect
import json
import re
from pathlib import Path

import pytest

from sutra_app.engine.fnodes import layer
from sutra_app.engine.host import loop
from sutra_app.engine.events import usage_event
from sutra_app.library.types import ATOM_ID_PATTERN, FUNCTIONS, atom_sid, function_node_id, overhead_atom_id

from .test_contract_world import REPO, World, clock, db, events, ids, jsonl, settings, tenv, world  # noqa: F401  (fixtures used by name)

GOLDEN = REPO / "tests" / "engine" / "golden" / "run_events.jsonl"
GOLDEN_RUN = "j2-20261104-100004-7f3a"
CHIP_META = {"stats", "wait_on"}
DRAWER_META = {"goal", "task", "context", "constraints", "wait_on", "hands_to", "stats"}
STATS = {"calls", "seconds", "tokens_in", "tokens_out", "atoms_open", "atoms_closed", "atoms_failed", "atoms_total"}


def replay(w: World, *extra: dict) -> str:
    """The recorded engine run, written into a real task's run folder and drained like a watcher would. `extra` lines go in before
    `run.ended`, the last line of the file."""
    task = w.t.new("web", "Brew Lab: a site for a craft coffee roaster")
    w.t.run(w.t.service.start_ready())
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["t"] == "run.ended"
    body = "\n".join([*lines[:-1], *(json.dumps({"at": "2026-11-04T10:00:00Z", **line}) for line in extra), lines[-1]]) + "\n"
    (w.t.run_dir(task.id) / "events.jsonl").write_text(body, encoding="utf-8")
    while w.t.drain(task.id).more:
        pass
    return task.id


@pytest.fixture
def replayed(world):
    return world, replay(world)


# ---- ids ---------------------------------------------------------------------------------------------------------------------------

def test_every_function_atom_id_the_engine_wrote_is_the_librarys_id_for_its_node():
    lines = [e for e in jsonl(GOLDEN) if e["t"] == "atom" and e["atom"]["schema"] == "work-atom/0.3"]
    assert lines
    for line in lines:
        atom_id = line["atom"]["id"]
        assert re.fullmatch(ATOM_ID_PATTERN, atom_id)
        node = line["node"]
        assert node in {function_node_id("web", fn) for fn in FUNCTIONS}
        assert atom_id.split("-")[1] == atom_sid(GOLDEN_RUN, node), atom_id                # the sid binds the id to its run and node
        assert line["atom"]["body"]["id"] == atom_id and line["atom"]["body"]["node_id"] == node


def test_every_usage_line_the_engine_wrote_names_an_atom_that_exists_or_the_runs_overhead_key():
    lines = jsonl(GOLDEN)
    usage = [e for e in lines if e["t"] == "usage"]
    atoms = {e["atom"]["id"] for e in lines if e["t"] == "atom"}
    assert usage and all(e.get("atom") for e in usage)
    named = {e["atom"] for e in usage}
    builders = {atom for atom in named if re.fullmatch(r"W-[0-9]+\.a[0-9]+", atom)}          # J2's own ids: the golden file keeps no atom/1 views
    assert builders and named - atoms - builders == {overhead_atom_id(GOLDEN_RUN)}          # the only other name without an atoms row


def test_no_row_of_the_ledger_or_the_atom_log_or_the_atoms_lacks_an_atom_id(replayed):
    world, _ = replayed
    one = world.t.one
    assert one("SELECT count(*) FROM usage_ledger") == 30
    assert one("SELECT count(*) FROM usage_ledger WHERE atom_id IS NULL OR atom_id = ''") == 0
    assert one("SELECT count(*) FROM atom_ledger WHERE atom_id IS NULL OR atom_id = ''") == 0
    assert one("SELECT count(*) FROM atoms WHERE id IS NULL OR id = ''") == 0
    cited = {m for row in world.t.sql("SELECT src_ref FROM chat_messages WHERE src_ref LIKE '%#atom:%'")
             for m in re.findall(r"#atom:([^:]+):", row["src_ref"])}
    assert cited and all(world.t.one("SELECT count(*) FROM atoms WHERE id = ?", atom) == 1 for atom in cited)   # a card names a stored atom
    log = world.client.get("/api/atoms/log", params={"limit": 200}).json()
    assert len(log) == 31 and all(row["atom_id"] for row in log)


def test_the_cost_of_an_atom_over_the_api_is_the_sum_of_its_provider_rows_and_never_counts_stub_rows(world):
    ids_ = list(dict.fromkeys(e["atom"]["id"] for e in jsonl(GOLDEN) if e["t"] == "atom" and e["atom"]["schema"] == "work-atom/0.3"))
    first_id, second_id = ids_[0], ids_[1]
    extra = [(first_id, 0.01, 100, 10), (first_id, 0.02, 200, 20), (second_id, None, 50, 5)]
    task = replay(world, *[usage_event(fn="audit", step=None, atom=atom, provider="claude" if usd is not None else "codex", model="m",
                                       purpose="agent_turn", usd=usd, tokens_in=tin, tokens_out=tout, seconds=1.0, ok=True, how="native",
                                       call_ref=f"{GOLDEN_RUN}:{100 + n}", detail=None) for n, (atom, usd, tin, tout) in enumerate(extra)])
    assert world.t.one("SELECT count(*) FROM usage_ledger WHERE task_id = ?", task) == 33
    first = world.client.get(f"/api/atoms/{first_id}").json()["usage"]
    second = world.client.get(f"/api/atoms/{second_id}").json()["usage"]
    assert (first["calls"], first["usd"], first["tokens_in"], first["tokens_out"]) == (2, 0.03, 300, 30)
    assert (second["calls"], second["usd"], second["tokens_in"]) == (1, None, 50)         # the stub rows of both atoms are not in it
    assert world.t.one("SELECT count(*) FROM usage_ledger WHERE atom_id = ? AND provider = 'stub'", first_id) >= 1


# ---- node meta -----------------------------------------------------------------------------------------------------------------------

def test_the_chip_of_every_function_node_has_exactly_the_agreed_meta_and_stats_keys(replayed):
    world, _ = replayed
    nodes = {n["id"]: n for n in world.client.get("/api/graph", params={"level": "full"}).json()["nodes"]}
    for fn in FUNCTIONS:
        chip = nodes[function_node_id("web", fn)]
        assert set(chip["meta"]) == CHIP_META, fn
        assert set(chip["meta"]["stats"]) == STATS, fn
        stats = chip["meta"]["stats"]
        assert stats["atoms_open"] == 0 and stats["atoms_total"] >= stats["atoms_closed"] + stats["atoms_failed"]
    assert sum(nodes[function_node_id("web", fn)]["meta"]["stats"]["atoms_total"] for fn in FUNCTIONS) == 31


def test_the_drawer_of_a_function_node_has_exactly_the_agreed_meta_keys_and_the_open_atom_counts_agree(replayed):
    world, _ = replayed
    for fn in FUNCTIONS:
        detail = world.client.get(f"/api/graph/nodes/{function_node_id('web', fn)}").json()
        assert set(detail["node"]["meta"]) == DRAWER_META, fn
        assert set(detail["node"]["meta"]["stats"]) == STATS, fn
        assert detail["node"]["meta"]["stats"]["atoms_total"] == len(world.client.get(
            "/api/atoms", params={"node_id": function_node_id("web", fn), "limit": 100}).json()), fn
        assert detail["node"]["meta"]["stats"]["atoms_open"] == 0                         # none open at run.ended


# ---- the host calls the factory with what it takes ------------------------------------------------------------------------------------

def host_call_keywords() -> list[str]:
    """The keyword names `Host._make_hooks` passes to the hook factory, read from the host's own source."""
    tree = ast.parse(Path(inspect.getsourcefile(loop)).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_make_hooks":
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "factory":
                    return [kw.arg for kw in call.keywords]
    raise AssertionError("the host no longer calls `factory(...)` in _make_hooks: update this contract")


def test_the_host_names_the_arguments_it_gives_the_factory():
    assert {"writer", "notify", "validator", "node_context_file"} <= set(host_call_keywords())


def test_the_layer_factory_accepts_every_argument_the_host_passes():
    arguments = {name: object() for name in host_call_keywords()}
    inspect.signature(layer.factory).bind(**arguments)
