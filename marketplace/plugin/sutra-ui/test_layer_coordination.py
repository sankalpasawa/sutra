"""Coordination behind its interface (PRD amendment A1.11, W1-COORD): layers/coordination/v1.py and the line it keeps.

  K1  every code, prompt, draft and check name Coordination's recipe uses is provided by the module itself, by reference
      (nineteen, none of them left to the legacy registries), and contract cases 1 to 4 and 7 pass for coordination/v1
"""
import importlib
import json

import pytest

import layer_schema as S
import layers
import layers.contract as C
from layers.coordination import v1 as V1

WEBSITE = "Build a website that teaches algebra to Class 8 students"
LINE = ["Plan", "Write", "Check", "Publish"]


@pytest.fixture
def j2(tmp_path, monkeypatch):
    """test_j2's fixture: the records home and the registry in this test's own folder, the modules reloaded."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)

    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as FV

    for module in (E, W, org2_apply, founding, R, J, FV):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding, FV


def _recipe():
    return json.loads((layers.HERE / "coordination" / V1.RECIPE).read_text(encoding="utf-8"))


def _names(kind):
    """The names of one kind (code, prompt, draft, check) the recipe's steps, gates, rules and handlers use."""
    return {s[kind] for s in C._steps(_recipe()) if s.get(kind)}


# ---- K1: coordination/v1 by reference -----------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["code", "prompt", "draft", "check"])
def test_k1_the_module_provides_every_name_its_recipe_uses_and_leaves_none_to_the_legacy_registries(kind):
    """A name the recipe uses that only engine_runtime's own registry holds, or a name the module holds that no step
    uses, must fail: the module names what its recipe needs, no more and no less."""
    mine = getattr(V1, kind.upper())
    assert set(mine) == _names(kind)
    assert _names(kind), "the recipe uses at least one %s" % kind


def test_k1_each_name_is_a_late_bound_delegate_to_the_body_the_runtime_holds_now(j2):
    """The delegate must reach the body the registry holds (a reloaded runtime's included), so no behaviour changes."""
    _, R, _, _, _ = j2
    registry = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    for kind in registry:
        for name, fn in getattr(V1, kind.upper()).items():
            module, attr = fn.legacy
            assert module == "engine_runtime"
            assert getattr(R, attr) is registry[kind][name], (kind, name, attr)


def test_k1_nineteen_by_reference_and_none_of_its_own():
    assert C.by_reference(V1) == {"by_reference": 19, "own": 0}


@pytest.mark.parametrize("case", [c for c in C.cases() if c[0] in (1, 2, 3, 4, 7)], ids=lambda c: "case %d" % c[0])
def test_k1_contract_cases_1_to_4_and_7_pass_for_coordination_v1(case, j2):
    _, what, fn = case
    assert fn(V1, {}) == [], what


def test_k1_the_recipe_is_the_one_the_default_pin_names():
    assert S.DEFAULT_PINS["coordination"] == C.impl_id(V1) == "coordination/v1"
    assert layers.recipes()["Coordination"] == _recipe()
