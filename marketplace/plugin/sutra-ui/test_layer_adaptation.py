"""Adaptation behind its interface (PRD amendment A1: W1-ADAPT, M5.7, M5.1, M6.3 to M6.5), one section per step.

  A1  adaptation/v1 provides every name its recipe uses, by reference, and passes the contract
  A6  Adaptation starts on the department's deliverable
  A7  the practices in place ride on the line request (J2_ADAPT_MAKE)
  A8  a shape with a confidence: J2B-4 in the covering, J2B-7 in the offer
  A9  organic and default kinds end to end, with stubbed models

The departments here are born the way a person makes them (found, say the words, Root sets up), on a records home of
their own, with no model but the ones a test installs; a test that meets a fault of the interface fails through
conftest.py, so a deliberate one is wrapped in S.expect_refused().
"""
import importlib
import json

import pytest

import layer_schema as S
import layers
import layers.contract as C

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LINE = ["Plan", "Write", "Check", "Publish"]


@pytest.fixture
def j2(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    monkeypatch.delenv("J2_ADAPT_MAKE", raising=False)

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


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return {"ref": C.fixture_department(tmp_path / "departments")}


def v1():
    return importlib.import_module("layers.adaptation.v1")


# ---- A1 · adaptation/v1 by reference ----------------------------------------------------------------------------------
def test_a1_the_module_provides_every_name_its_recipe_uses():
    module = v1()
    used = {"code": set(), "prompt": set(), "draft": set(), "check": set()}
    for s in C._steps(C.recipe_of(module)):
        for kind in used:
            if s.get(kind):
                used[kind].add(s[kind])
    assert {k: len(v) for k, v in used.items()} == {"code": 15, "prompt": 2, "draft": 2, "check": 6}
    for kind, names in used.items():
        assert names <= set(getattr(module, kind.upper())), "%s names the recipe uses that the module leaves to the legacy registry" % kind


@pytest.mark.parametrize("case", [c for c in C.cases() if c[0] in (1, 2, 3, 4, 7)], ids=lambda c: "case %d" % c[0])
def test_a1_the_contract_cases_pass_for_adaptation_v1(case, home):
    _, what, fn = case
    assert fn(v1(), home) == [], what


def test_a1_what_it_holds_by_reference_is_counted_for_the_hand_in(capsys):
    counts = C.by_reference(v1())
    print("adaptation/v1: %(by_reference)d by reference, %(own)d own" % counts)
    assert counts["by_reference"] + counts["own"] == 25
