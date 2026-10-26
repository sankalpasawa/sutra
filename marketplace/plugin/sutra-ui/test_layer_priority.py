"""Priority behind its interface (PRD A1, W1-PRIORITY: M5.8 and M5.3): layers/priority/v1 registers every name its recipe
uses, prices a proposal from what the engines have observably spent, answers it with the price, writes one price row per
answer, shows them in its view, and says by='priority' where it writes the record.

One test per done-check of P1 to P5. The contract's cases are layers/contract.py's; the fixtures are test_j2's: a
department born the way a person makes one, a model that is a function of the step id, the same board.
"""
import importlib

import pytest

import layer_schema as S
import layers
import layers.contract as C
import layers.priority.v1 as V1


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return {"ref": C.fixture_department(tmp_path / "departments")}


# ---- P1: priority/v1 by reference --------------------------------------------------------------------------------------
def test_p1_every_name_the_recipe_uses_is_registered_and_the_contract_passes(ctx):
    """A name the recipe uses that priority/v1 does not provide, or a case of the contract that fails, must fail."""
    recipe = C.recipe_of(V1)
    names = {k: sorted({s[k] for s in C._steps(recipe) if s.get(k)}) for k in ("code", "prompt", "draft", "check")}
    for kind, dict_ in (("code", V1.CODE), ("prompt", V1.PROMPT), ("draft", V1.DRAFT), ("check", V1.CHECK)):
        assert set(names[kind]) <= set(dict_), "%s: %s" % (kind, sorted(set(names[kind]) - set(dict_)))
    for number, what, case in C.cases():
        if number in (1, 2, 3, 4, 7):
            assert case(V1, ctx) == [], "case %d: %s" % (number, what)


def test_p1_a_name_still_by_reference_is_a_late_bound_delegate_to_engine_runtimes_own_body(ctx):
    """P1 moves nothing: until a body moves (P3), each name is a late-bound delegate to engine_runtime's own, so a
    reloaded runtime is the one that runs, and the registries are as they were. The count is reported, never gated."""
    import engine_runtime as R
    counts = C.by_reference(V1)
    everything = [(kind, name, fn) for kind, d in (("code", V1.CODE), ("prompt", V1.PROMPT), ("draft", V1.DRAFT), ("check", V1.CHECK))
                  for name, fn in d.items()]
    assert counts["by_reference"] + counts["own"] == len(everything)
    legacy = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    for kind, name, fn in everything:
        if hasattr(fn, "legacy"):
            module, attr = fn.legacy
            assert module == "engine_runtime" and getattr(R, attr) is legacy[kind][name], "%s %s" % (kind, name)
    assert counts["by_reference"] >= 1
    importlib.reload(R)
    assert V1.CODE["priority_envelope"].legacy == ("engine_runtime", "priority_envelope")
    assert layers.recipes()["Priority"] == C.recipe_of(V1)


# ---- the interface rows Priority adds (A1 interface: priority:) and its covering ---------------------------------------
def _read(names, per, room, limit=6):
    """What priority.read hands the bargain, as far as the covering reads it."""
    return {"bag": {"priority.read": {"names": names, "limit": limit, "room": room, "estimate": {"calls": 0, "usd": 0, "per_engine": per}}}}


PER = {"Plan": {"calls": 2, "usd": 0.08}, "Write": {"calls": 4, "usd": 0.16}, "Check": {"calls": 1, "usd": 0.04}}


def test_the_interface_names_the_estimate_and_what_remains_the_covering_and_the_prices_view():
    """The bargain line part gains estimate and remaining, the covering is listed with samples, and the view's prices are
    typed but not required, so a view written before them still validates."""
    line = S.PROMPTS["priority"]["bargain"]["line"]
    assert line["inputs"] == ("source", "engines", "calls", "usd", "room", "limit", "estimate", "remaining")
    assert "price_is_observed" in S.CHECKS["priority"] and "answer_has_its_price" in S.CHECKS["priority"]
    for out in S.CONTRACT_SAMPLES["price_is_observed"]["good"]:
        assert V1.CHECK["price_is_observed"](None, None, None, out)["ok"] is True, out
    for out in S.CONTRACT_SAMPLES["price_is_observed"]["bad"]:
        assert V1.CHECK["price_is_observed"](None, None, None, out)["ok"] is False, out
    view = S.DEFS["view.priority"]
    assert "prices" in view["properties"] and "prices" not in view["required"]
    assert S.validate("view.priority", {"bargains": [], "envelopes": []}) == []


def test_the_covering_keeps_the_notes_of_the_covering_it_replaces_when_there_are_no_facts_to_hold_it_to():
    """With no facts the answer is held to its price alone, as engine_runtime's answer_has_its_price holds it (the notes are
    the same words), so the step keeps its name and the checks that pin it stay as they were."""
    import engine_runtime as R
    for out in ({"answer": "counter", "why": "room for two today", "keep": []}, {"answer": "maybe", "why": "unsure"},
                {"answer": "accept", "why": " "}, {"answer": "accept", "why": "fits today"},
                {"answer": "counter", "why": "room for two today", "keep": ["Plan", "Write"]}):
        assert V1.CHECK["answer_has_its_price"](None, None, None, out) == R.CHECK["answer_has_its_price"](None, None, None, out), out
    assert V1.CHECK["answer_has_its_price"] is V1.CHECK["price_is_observed"]


def test_a_yes_or_an_ask_for_less_is_held_to_the_room_and_a_no_always_stands():
    """A yes that spends what is not there, an ask for less that keeps more than fits, and one that keeps what the
    proposal does not name must fail; a no, or a smaller yes, stands (approvals only tighten)."""
    check = V1.CHECK["price_is_observed"]
    names = ["Plan", "Write", "Check"]
    roomy, tight, none = ({"calls": 100, "usd": 5.0}, {"calls": 6, "usd": 0.24}, {"calls": 0, "usd": 0.0})
    assert check(_read(names, PER, roomy), None, None, {"answer": "accept", "why": "fits today"})["ok"]
    over = check(_read(names, PER, tight), None, None, {"answer": "accept", "why": "fits today"})
    assert not over["ok"] and over["notes"] == ["said yes to what costs more than the room holds: 7 calls and 0.28 USD go past the "
                                               "6 calls and 0.24 USD left today"]
    assert check(_read(names, PER, tight), None, None, {"answer": "counter", "why": "room for two", "keep": ["Plan", "Write"]})["ok"]
    too_many = check(_read(names, PER, tight), None, None, {"answer": "counter", "why": "x", "keep": ["Write", "Plan", "Check"]})
    assert not too_many["ok"] and "asked to keep what costs more than the room holds" in too_many["notes"][0]
    strange = check(_read(names, PER, roomy), None, None, {"answer": "counter", "why": "x", "keep": ["Plan", "Publish"]})
    assert strange["notes"] == ["an ask for less keeps Publish, which the proposal does not name"]
    assert check(_read(names, PER, none), None, None, {"answer": "reject", "why": "no room today"})["ok"]
    assert check(_read(names, PER, roomy), None, None, {"answer": "reject", "why": "no room"})["ok"], "a no stands over ample room"
    assert not check(_read(names, PER, roomy, limit=2), None, None, {"answer": "accept", "why": "fits"})["ok"], "past the limit of workflows"
    assert check(_read(names, PER, roomy), None, None, {"answer": "accept", "why": "fits today"})["notes"] == ["said yes, with its price: fits today"]
