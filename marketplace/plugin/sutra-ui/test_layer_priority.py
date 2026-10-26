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


def test_p1_the_by_reference_count_is_reported_and_changes_no_behaviour(ctx):
    """P1 moves nothing: until a body moves (P3), each name is a late-bound delegate to engine_runtime's own, so a
    reloaded runtime is the one that runs, and nothing in the registries changed."""
    import engine_runtime as R
    counts = C.by_reference(V1)
    assert counts["by_reference"] + counts["own"] == 10, "four codes, one prompt, one draft and four checks"
    for kind, dict_, legacy in (("code", V1.CODE, R.CODE), ("prompt", V1.PROMPT, R.PROMPT), ("draft", V1.DRAFT, R.DRAFT),
                                ("check", V1.CHECK, R.CHECK)):
        for name, fn in dict_.items():
            if hasattr(fn, "legacy"):
                module, attr = fn.legacy
                assert module == "engine_runtime" and getattr(R, attr) is legacy[name], "%s %s" % (kind, name)
    importlib.reload(R)
    assert V1.CODE["priority_envelope"].legacy == ("engine_runtime", "priority_envelope")
    assert layers.recipes()["Priority"] == C.recipe_of(V1)
