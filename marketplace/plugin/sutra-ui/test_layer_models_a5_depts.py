"""A5 P1.4: the department listing and the create-or-reuse models (A5.3, A5.4.1): each validator with a pass and a fail."""
from pydantic import TypeAdapter

import layer_models.a5_depts as D
from layer_models.faults import sentences

NOW = "2026-10-29T10:00:00+05:30"
MID1, MID2 = "m-00000000a001", "m-00000000a002"


def row(ref="dref-billing1"):
    return {"ref": ref, "name": "Billing", "kind": "default", "parent": None, "root": None, "runtime": 2, "stopped": False,
            "state": "idle", "waiting_on_you": False, "pending_asks": 0, "working": [], "last_activity": None, "created": None,
            "goal": "g", "done": "d", "done_met": None, "engines": [], "artifacts": [], "j2_url": None}



def choice(**k):
    return dict({"action": "use", "ref": "dref-billing1", "reason": "it covers it", "confidence": "high"}, **k)



def decision(**k):
    return dict({"choice": choice(), "final_action": "use", "final_ref": "dref-billing1", "overrides": [], "held": False, "held_reason": None,
                 "decided_by": "agent", "mode": "link", "considered": ["dref-billing1"], "candidates_seen": 1, "root_ref": "dref-root0001",
                 "result_ref": None, "operation_id": None, "mission_id": MID1, "at": NOW, "prompt_version": "1"}, **k)



def bad(cls, value, *words):
    got = sentences(TypeAdapter(cls), value)
    assert got and all(any(w in g for g in got) for w in words), (words, got)



def ok(cls, value):
    assert sentences(TypeAdapter(cls), value) == []




def cand(**k):
    return dict({"ref": "dref-billing1", "name": "Billing", "kind": "default", "goal": "g", "done": "d", "state": "idle", "stopped": False,
                 "blocked": False, "last_activity": None, "score": 0.5}, **k)


def test_row_and_listing():
    ok(D.DeptRow, row())
    ok(D.DeptRow, dict(row(), parent="dref-root0001", root="dref-root0001", last_activity=NOW, done_met=False, j2_url="/j2ui/x/"))
    bad(D.DeptRow, dict(row(), runtime=3), "is not one of")
    bad(D.DeptRow, dict(row(), kind="Site"), "does not match")
    bad(D.DeptRow, dict(row(), state="asleep"), "is not one of")
    bad(D.DeptRow, dict(row(), ref="a/b"), "does not match")
    bad(D.DeptRow, dict(row(), pending_asks=100), "above 99")
    bad(D.DeptRow, dict(row(), working=["w"] * 13), "more than 12")
    bad(D.DeptRow, dict(row(), engines=["e"] * 33), "more than 32")
    bad(D.DeptRow, {k: v for k, v in row().items() if k != "name"}, "name: is missing")
    bad(D.DeptRow, dict(row(), colour="red"), "not a field here")
    ok(D.DeptListing, {"departments": [row(), row("dref-two")], "root_ref": None, "as_of": NOW})
    bad(D.DeptListing, {"departments": [row(), row()], "root_ref": None, "as_of": NOW}, "listed twice")
    bad(D.DeptListing, {"departments": [row()] * 501, "root_ref": None, "as_of": NOW}, "more than 500")


def test_candidate():
    ok(D.DeptCandidate, cand())
    bad(D.DeptCandidate, cand(score=1.5), "above 1")
    bad(D.DeptCandidate, cand(name=""), "shorter than 1")
    bad(D.DeptCandidate, cand(name="n" * 81), "longer than 80")
    bad(D.DeptCandidate, cand(state="x"), "is not one of")


def test_choice_takes_what_its_action_needs():
    ok(D.DeptChoice, choice())
    bad(D.DeptChoice, choice(ref=None), "use needs a ref")
    bad(D.DeptChoice, choice(kind="default"), "use does not take a kind")
    bad(D.DeptChoice, choice(name="n", goal="g"), "use does not take a name", "use does not take a goal")
    create = dict(choice(action="create", ref=None), kind="organic", name="Reports", goal="Weekly sales reports", done_items=["a"])
    ok(D.DeptChoice, create)
    bad(D.DeptChoice, dict(create, kind=None), "create needs a kind")
    bad(D.DeptChoice, dict(create, name=None, goal=None), "create needs a name", "create needs a goal")
    bad(D.DeptChoice, dict(create, ref="dref-x"), "create does not take a ref")
    ok(D.DeptChoice, choice(action="none", ref=None))
    bad(D.DeptChoice, choice(action="none"), "none does not take a ref")
    bad(D.DeptChoice, choice(action="none", ref=None, kind="x"), "none does not take a kind")
    bad(D.DeptChoice, choice(reason=""), "shorter than 1")
    bad(D.DeptChoice, choice(reason="r" * 401), "longer than 400")
    bad(D.DeptChoice, choice(confidence="sure"), "is not one of")
    bad(D.DeptChoice, dict(create, goal="g" * 2001), "longer than 2000")
    bad(D.DeptChoice, dict(create, done_items=["d"] * 13), "more than 12")


def test_choice_round_trips_for_each_action():
    full = {"kind": "default", "name": "Billing", "goal": "g"}
    for k in ({"action": "use", "ref": "dref-billing1"}, dict(full, action="create", ref=None), {"action": "none", "ref": None}):
        c = D.DeptChoice(reason="x", confidence="low", **k)
        assert c.done_items == []
        TypeAdapter(D.DeptChoice).validate_python(c.model_dump())


def test_override():
    ok(D.DeptOverride, {"rule": "founder_rule", "note": "held"})
    bad(D.DeptOverride, {"rule": "mystery", "note": "x"}, "is not one of")
    bad(D.DeptOverride, {"rule": "rate", "note": ""}, "shorter than 1")
    assert len(D.RULES) == 10


def test_decision_rules():
    ok(D.DeptDecision, decision())
    bad(D.DeptDecision, decision(final_ref=None), "use needs a final_ref")
    none = decision(final_action="none", final_ref=None, choice=choice(action="none", ref=None))
    ok(D.DeptDecision, none)
    bad(D.DeptDecision, dict(none, final_ref="dref-x"), "none does not take a final_ref")
    bad(D.DeptDecision, decision(held=True), "held decision says why")
    ok(D.DeptDecision, decision(held=True, held_reason="stopped"))
    bad(D.DeptDecision, decision(held=True, held_reason="mood"), "is not one of")
    bad(D.DeptDecision, decision(considered=["a", "b"], candidates_seen=1), "fewer than the departments considered")
    ok(D.DeptDecision, decision(considered=["a", "b"], candidates_seen=2))
    create = decision(final_action="create", final_ref=None, result_ref="dref-new", choice=dict(choice(action="create", ref=None),
                      kind="organic", name="Reports", goal="g"))
    ok(D.DeptDecision, create)
    bad(D.DeptDecision, dict(create, held=True, held_reason="founder_rule"), "held create has made nothing")
    ok(D.DeptDecision, dict(create, result_ref=None, held=True, held_reason="founder_rule"))
    ok(D.DeptDecision, decision(mode="execute", decided_by="stub", overrides=[{"rule": "offline", "note": "n"}]))
    bad(D.DeptDecision, decision(mode="chat"), "is not one of")
    bad(D.DeptDecision, decision(overrides=[{"rule": "rate", "note": "n"}] * 7), "more than 6")
    bad(D.DeptDecision, decision(mission_id="x"), "does not match")
    bad(D.DeptDecision, decision(prompt_version="v" * 21), "longer than 20")


def test_request_defaults():
    m = TypeAdapter(D.DeptRequest).validate_python({"words": "Weekly sales reports"})
    assert (m.apply, m.confirmed, m.mission_id) == (True, False, None)
    ok(D.DeptRequest, {"words": "x", "mission_id": "m-00000000a001", "apply": False, "confirmed": True})
    bad(D.DeptRequest, {"words": ""}, "shorter than 1")
    bad(D.DeptRequest, {"words": "x" * 4001}, "longer than 4000")
    bad(D.DeptRequest, {"words": "x", "force": True}, "not a field here")
    bad(D.DeptRequest, {"words": "x", "apply": "yes"}, "is not")
