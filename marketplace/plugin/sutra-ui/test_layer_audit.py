"""Audit behind its interface (PRD amendment A1: W1-AUDIT; M8.1 to M8.3, M8.9, M0.3), one section a step.

  U1  audit/v1 provides every name its recipe uses, by reference, and passes the contract
  U3  the deliverable: every place on Audit's path asks the interface (S.deliverable), one test per kind
  U4  Audit starts on and reads any kind's deliverable; one that is not HTML is read as text
  U5  a reading per done-when item in the S-30 shape; a version not read is a row with read false
  U6  Audit's view: latest and readings

The departments here are born the way test_j2's are (founded, asked for, set up by Root), so what is tested is what a
real department does on its real board; a model is a function (a step id maps to what it says).
"""
import importlib
import json

import pytest

import layer_schema as S
import layers
import layers.contract as C

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return tmp_path


@pytest.fixture
def j2(home):
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
    """A model that is a function: a step id maps to what the model says (a dict, or a callable taking the prompt).
    Every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)


def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _default(j2, ref="dref-answers"):
    """A department of the default kind, as test_j2 makes one: one Do engine, its Result the deliverable."""
    W, R, J, _, _ = j2
    d, _ = W.create(ref, "Answers", None, kind="default")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start(d["ref"])
    W.give_goal(d["ref"], "Answer what the science team asks about the lab rota")
    W.run_until_idle(d["ref"], limit=300)
    return d["ref"]


def _stamp_all(W, ref, kind=None):
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and (kind is None or a["kind"] == kind)]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


# ---- U1 · audit/v1 by reference ------------------------------------------------------------------------------------
def _audit_module():
    return next(m for m in C.discover() if m.LAYER == "audit")


@pytest.fixture
def contract_ctx(home):
    return {"ref": C.fixture_department(home / "departments")}


def test_u1_audit_v1_passes_the_contract_cases_1_to_4_and_7(contract_ctx):
    m = _audit_module()
    assert C.impl_id(m) == "audit/v1"
    for number, case in ((1, C.case_1), (2, C.case_2), (3, C.case_3), (4, C.case_4), (7, C.case_7)):
        assert case(m, contract_ctx) == [], "contract case %d" % number


def test_u1_every_name_the_recipe_uses_is_provided_by_reference_not_by_the_legacy_registries():
    m = _audit_module()
    recipe = C.recipe_of(m)
    used = {kind: {s[kind] for s in C._steps(recipe) if s.get(kind)} for kind in ("code", "prompt", "draft", "check")}
    mine = C._dicts(m)
    for kind, names in used.items():
        assert names <= set(mine[kind]), "%s: %s are not provided by audit/v1" % (kind, sorted(names - set(mine[kind])))
    counts = C.by_reference(m)
    assert counts["by_reference"] == sum(len(v) for v in used.values()) and counts["own"] == 0
