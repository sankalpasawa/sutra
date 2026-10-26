"""Identity behind its interface (PRD amendment A1, package W1-IDENTITY: M3.8 and M3.9), one section per step:

    I1  identity/v1 provides every code, prompt, draft and check name its recipe uses, by reference, and passes the
        contract cases that do not read words
    I3  identity/v1.view returns Identity's pane and it validates as view.identity in the four states of a cycle
    I4  Identity's writers say who they are: a save of Identity's keys names Identity, and no row says otherwise
    I5  Hear a doubt: Adaptation's one doubt is put to the owner as one question with no number in it, its answer goes
        back to Adaptation as a line request, and the bounds (one a line request, two a cycle) hold

The departments are born the way a person makes them, on the real board, as test_j2's are (its fixture and helpers are
copied here with the pane's module reloaded too). A test that meets a fault of the interface fails through conftest.py;
a deliberate one is wrapped in S.expect_refused().
"""
import importlib
import json
import re

import pytest

import layer_schema as S
import layers
import layers.contract as C
import layers.identity.v1 as V1

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A records home of the test's own, as test_j2's fixture makes one, with no model."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return tmp_path


@pytest.fixture
def ctx(home):
    """The contract's fixture department, in a home of its own."""
    return {"ref": C.fixture_department(home / "departments")}


@pytest.fixture
def j2(home):
    """test_j2's fixture: the modules reloaded on a home of their own, the organisation's Root minted; the pane's module too."""
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


def _model(monkeypatch, R, answers):
    """test_j2's _model: a step id maps to what the model says (a dict, or a callable taking the prompt); every other
    step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)


def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    """test_j2's _born: a department as a person makes one: found the organisation, say the words, Root sets it up."""
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _recipe_names():
    """Every code, prompt, draft and check name Identity's recipe uses, by kind."""
    out = {kind: set() for kind in ("code", "prompt", "draft", "check")}
    for s in C._steps(layers.recipes()["Identity"]):
        for kind in out:
            if s.get(kind):
                out[kind].add(s[kind])
    return out


# ---- I1: identity/v1 by reference ------------------------------------------------------------------------------------
def test_i1_every_name_the_recipe_uses_is_provided_and_nothing_else_is():
    names = _recipe_names()
    assert {k: set(d) for k, d in C._dicts(V1).items()} == names


def test_i1_each_name_the_recipe_uses_is_a_reference_to_the_body_engine_runtime_holds(home):
    import engine_runtime as R
    legacy = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    for kind, d in C._dicts(V1).items():
        for name, fn in d.items():
            module, attr = fn.legacy
            assert module == "engine_runtime"
            assert getattr(R, attr) is legacy[kind][name], "%s %s points at %s, which is not the body the registry holds" % (kind, name, attr)


def test_i1_the_count_by_reference_is_reported(capsys):
    got = C.by_reference(V1)
    assert got == {"by_reference": sum(len(v) for v in _recipe_names().values()), "own": got["own"]}
    print("identity/v1: %(by_reference)d by reference, %(own)d own" % got)


@pytest.mark.parametrize("number", [1, 2, 3, 4, 7])
def test_i1_the_contract_cases_that_read_no_words_pass(number, ctx):
    fn = dict((n, f) for n, _, f in C.cases())[number]
    assert fn(V1, ctx) == []
