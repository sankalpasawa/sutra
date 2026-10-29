"""A5 P1.3: the Shadow graph models (A5.2.1, A5.4.1): every validator, each with a value that passes and one that fails."""
import copy

import pytest

import layer_models.a5_graph as G
from test_layer_models_a5_depts import MID1, MID2, NOW, bad, choice, decision, ok, row


def opn(kind="none", ref=None):
    return {"kind": kind, "ref": ref}


def node(id, kind, **k):
    return dict({"id": id, "kind": kind, "label": "x", "sub": None, "status": "idle", "col": 0, "row": 0, "open": opn(), "since": None,
                 "cost_usd": None, "tip": "t"}, **k)


def edge(kind, source, target, **k):
    return dict({"id": "%s:%s>%s" % (kind, source, target), "kind": kind, "source": source, "target": target, "reason": None,
                 "confidence": None, "live": False, "held": False}, **k)


def graph(**k):
    nodes = [node("shadow:now", "shadow"), node("task:" + MID1, "task", col=2, open=opn("task", MID1)),
             node("dept:dref-billing1", "department", col=3, open=opn("dept_page", "dref-billing1"))]
    edges = [edge("has", "shadow:now", "task:" + MID1),
             edge("uses", "task:" + MID1, "dept:dref-billing1", reason="Billing already handles it", confidence="high")]
    return dict({"nodes": nodes, "edges": edges, "as_of": NOW, "focus": MID1, "truncated": False, "shadow_on": True}, **k)


def head(**k):
    return dict({"id": MID1, "objective": "Fix the login bug", "state": "running", "template": "general", "executor": "worker", "goal_id": None,
                 "created": NOW, "updated": NOW, "turns_used": 3}, **k)


def detail(**k):
    return dict({"task": head(), "graph": graph(), "decision": decision(), "departments": [row()], "chats": [], "costs": [], "total_usd": 0.1,
                 "timeline": [], "as_of": NOW}, **k)


def test_the_task_states_are_the_missions_states():
    import mission_engine
    assert set(G.TASK_STATES) == set(mission_engine.STATES)


def test_open_has_a_ref_exactly_when_it_opens_something():
    ok(G.NodeOpen, opn()), ok(G.NodeOpen, opn("task", MID1))
    bad(G.NodeOpen, opn("task"), "exactly when kind is none")
    bad(G.NodeOpen, opn("none", "x"), "exactly when kind is none")
    bad(G.NodeOpen, opn("task", "a b"), "does not match")
    bad(G.NodeOpen, dict(opn(), extra=1), "not a field here")


@pytest.mark.parametrize("id,kind", [("shadow:now", "shadow"), ("conv:shc-a1b2c3", "conversation"), ("goal:g-000000000001", "goal"),
                                     ("task:" + MID1, "task"), ("tchat:" + MID1, "task_chat"), ("worker:" + MID1, "worker"),
                                     ("dept:dref-acme0001", "department")])
def test_a_node_id_matches_its_kind(id, kind):
    ok(G.ShadowGraphNode, node(id, kind))
    other = "task" if kind != "task" else "goal"
    bad(G.ShadowGraphNode, node(id, other), "is not the id of a %s node" % other)


def test_a_node_is_bounded():
    bad(G.ShadowGraphNode, node("task:m-xyz", "task"), "does not match")
    bad(G.ShadowGraphNode, node("shadow:now", "shadow", col=9), "above 8")
    bad(G.ShadowGraphNode, node("shadow:now", "shadow", row=400), "above 399")
    bad(G.ShadowGraphNode, node("shadow:now", "shadow", label=""), "shorter than 1")
    bad(G.ShadowGraphNode, node("shadow:now", "shadow", status="red"), "is not one of")
    bad(G.ShadowGraphNode, node("shadow:now", "shadow", cost_usd=-1), "below 0")
    ok(G.ShadowGraphNode, node("shadow:now", "shadow", cost_usd=0.5, since=NOW, sub="s"))


def test_an_edge_id_is_derived_and_a_reason_is_required_where_the_edge_claims_something():
    a, b = "task:" + MID1, "dept:dref-x"
    ok(G.ShadowGraphEdge, edge("has", "shadow:now", a))
    bad(G.ShadowGraphEdge, edge("has", "shadow:now", a, id="whatever"), "id is not kind:source>target")
    bad(G.ShadowGraphEdge, edge("has", a, a), "joins two nodes")
    bad(G.ShadowGraphEdge, edge("uses", a, b), "uses edge says why")
    bad(G.ShadowGraphEdge, edge("spawned", a, b, reason=""), "spawned edge says why")
    bad(G.ShadowGraphEdge, edge("has", "shadow:now", a, held=True), "held edge says why")
    ok(G.ShadowGraphEdge, edge("uses", a, b, reason="Held: X is Off", held=True, confidence="low"))
    bad(G.ShadowGraphEdge, edge("uses", a, b, reason="r" * 301), "longer than 300")


def test_the_graph_holds_together():
    ok(G.ShadowGraph, graph())
    g = graph(); g["nodes"].append(copy.deepcopy(g["nodes"][1]))
    bad(G.ShadowGraph, g, "a node id is used twice")
    g = graph(); g["edges"].append(copy.deepcopy(g["edges"][0]))
    bad(G.ShadowGraph, g, "an edge id is used twice")
    g = graph(); g["edges"].append(edge("has", "shadow:now", "task:m-00000000ffff"))
    bad(G.ShadowGraph, g, "joins a node that is not drawn")
    g = graph(); g["nodes"].append(node("conv:shc-a1b2c3", "conversation"))
    ok(G.ShadowGraph, g)
    g["nodes"].append(node("shadow:now", "shadow")); g["nodes"].pop(0)
    bad(G.ShadowGraph, graph(nodes=[n for n in graph()["nodes"] if n["kind"] != "shadow"], edges=[]), "exactly one shadow node")
    bad(G.ShadowGraph, graph(focus="m-00000000ffff"), "focus task is not drawn")
    ok(G.ShadowGraph, graph(focus=None))
    bad(G.ShadowGraph, graph(nodes=[node("shadow:now", "shadow")] * 401, edges=[]), "more than 400")


def test_small_records():
    ok(G.TimelineRow, {"at": NOW, "kind": "said", "by": "founder", "text": "hi", "ref": None})
    bad(G.TimelineRow, {"at": NOW, "kind": "said", "by": "robot", "text": "hi"}, "is not one of")
    bad(G.TimelineRow, {"at": NOW, "kind": "said", "by": "founder", "text": ""}, "shorter than 1")
    ok(G.ChatLink, {"role": "now", "label": "Now", "live": True, "open": opn("session", "s1"), "alt_open": None})
    ok(G.ChatLink, {"role": "now", "label": "Now", "live": True, "open": opn("session", "s1"), "alt_open": opn()})
    bad(G.ChatLink, {"role": "now", "label": "Now", "live": 1, "open": opn()}, "is not")
    ok(G.CostLine, {"role": "worker", "usd": 0.2, "turns": 3})
    bad(G.CostLine, {"role": "worker", "usd": -0.2, "turns": 3}, "below 0")
    bad(G.CostLine, {"role": "worker", "usd": 0.2, "turns": 100001}, "above 100000")


def test_task_head():
    ok(G.TaskHead, head()), ok(G.TaskHead, head(goal_id="g-000000000001"))
    bad(G.TaskHead, head(state="sleeping"), "is not one of")
    bad(G.TaskHead, head(id="x"), "does not match")
    bad(G.TaskHead, head(goal_id="m-000000000001"), "does not match")
    bad(G.TaskHead, head(executor="robot"), "is not one of")
    bad(G.TaskHead, head(objective="o" * 401), "longer than 400")


def test_task_detail_rules():
    ok(G.ShadowTaskDetail, detail())
    ok(G.ShadowTaskDetail, detail(decision=None, departments=[]))
    bad(G.ShadowTaskDetail, detail(task=head(id=MID2)), "graph is not focused on the task")
    bad(G.ShadowTaskDetail, detail(decision=decision(mission_id=MID2)), "belongs to another task")
    ok(G.ShadowTaskDetail, detail(decision=decision(mission_id=None)))
    bad(G.ShadowTaskDetail, detail(departments=[row("dref-nowhere")]), "not drawn in the graph")
    bad(G.ShadowTaskDetail, detail(departments=[row()] * 9), "more than 8")
    bad(G.ShadowTaskDetail, detail(total_usd=-1), "below 0")
