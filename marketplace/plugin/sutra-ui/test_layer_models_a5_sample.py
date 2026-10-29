"""A5 P1.7: fixtures/shadow_graph_sample.json (A5.2.6): the sample validates, and each invalid variant fails with the rule it is for."""
import copy
import json

import pytest
from pydantic import TypeAdapter

import layer_models.a5_depts as D
import layer_models.a5_graph as G
from layer_models.faults import sentences

SAMPLE = json.loads((__import__("pathlib").Path(__file__).parent / "fixtures" / "shadow_graph_sample.json").read_text(encoding="utf-8"))
CLASS = {"graph": G.ShadowGraph, "detail": G.ShadowTaskDetail, "listing": D.DeptListing, "choice": D.DeptChoice, "decision": D.DeptDecision,
         "open": G.NodeOpen}


def edited(base, edits):
    v = copy.deepcopy(base)
    for e in edits:
        cur = v
        for k in e["at"][:-1]:
            cur = cur[k]
        if e["op"] == "set":
            cur[e["at"][-1]] = e["value"]
        elif e["op"] == "del":
            del cur[e["at"][-1]]
        else:
            cur[e["at"][-1]].append(e["value"])
    return v


@pytest.mark.parametrize("name", sorted(CLASS))
def test_the_sample_validates(name):
    assert sentences(TypeAdapter(CLASS[name]), SAMPLE[name]) == []


def test_the_sample_shows_what_the_spec_lists():
    g = SAMPLE["graph"]
    kinds = {n["kind"] for n in g["nodes"]}
    assert kinds == {"shadow", "conversation", "goal", "task", "task_chat", "worker", "department"}
    by = {(e["kind"], e["held"]) for e in g["edges"]}
    assert {("uses", False), ("spawned", False), ("uses", True), ("has", False), ("attempt", False), ("steered_by", False), ("driven_by", False)} <= by
    tasks = {n["id"]: n for n in g["nodes"] if n["kind"] == "task"}
    assert tasks["task:m-00000000a001"]["label"] == "Fix the login bug" and tasks["task:m-00000000a001"]["status"] == "working"
    assert tasks["task:m-00000000a002"]["label"] == "Weekly sales report" and tasks["task:m-00000000a002"]["status"] == "waiting"
    assert tasks["task:m-00000000a003"]["status"] == "done"
    assert not [e for e in g["edges"] if e["target"].startswith("dept:") and e["source"] == "task:m-00000000a003"]
    uses = next(e for e in g["edges"] if e["kind"] == "uses" and not e["held"])
    assert uses["reason"] == "Billing already handles invoice and login-token questions"
    assert next(e for e in g["edges"] if e["kind"] == "spawned")["reason"] == "No department covers recurring reports"
    assert SAMPLE["detail"]["graph"] == g


@pytest.mark.parametrize("row", SAMPLE["invalid"], ids=[r["says"] for r in SAMPLE["invalid"]])
def test_each_invalid_variant_fails_with_its_rule(row):
    got = sentences(TypeAdapter(CLASS[row["from"]]), edited(SAMPLE[row["from"]], row["edits"]))
    assert got and any(row["says"] in g for g in got), (row["says"], got)


def test_every_validator_has_a_variant():
    """The rule sentences registered by the models are all shown by some variant (the open rule, node id, edge, graph, detail, listing,
    choice and decision rules)."""
    import layer_models.a5_types as A
    said = " | ".join(r["says"] for r in SAMPLE["invalid"])
    for fragment in ("exactly when kind is none", "is not the id of", "id is not kind:source>target", "joins two nodes", "says why", "used twice",
                     "not drawn", "exactly one shadow node", "focus task", "not focused", "another task", "listed twice", "needs a", "does not take",
                     "fewer than", "made nothing"):
        assert fragment in said, fragment
    assert len(A.RULE_RES) >= 24
