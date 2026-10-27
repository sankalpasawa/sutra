"""Per-department versions, by the rule that keeps old pins working (PRD amendment A1.18, M2.11; W3-PINS, steps N1 to N4).

  N1  recipes per pin set: the definitions are assembled for the versions the department in hand pins, once for each tuple of
      implementation ids; a context variable, set at the motor's slot, a delivery, the sweep and an API route, chooses the set
  N2  Root's version is the organisation's Root's; a pin that cannot run (it does not load, its recipe does not resolve, the
      assembled definitions refuse it, its words break the function template) runs the layer's default, with one row
  N3  ladder entries are kept per (step, implementation): a rung learned under one version is not applied to another, and a
      step a child leaves as its parent has it carries the parent's rung over
  N4  the pin option: pin {layer, impl} writes the department's record through save_dept(by='root'), or is UNKNOWN_OPTION

The stub child is A2-INHERIT's fixture (test_fixtures/layers_lineage/coordination/v2.py), never a second one: it adds the step
coord.probe after coord.table when an engine is born. Nothing is added under layers/. A test loads the fixture under the name
layers.coordination.v2 and puts it in layers._LOADED, as test_layer_inherit.py does, and the monkeypatch takes it out again.

A test that meets a fault of the interface fails (conftest.py); a deliberate one is wrapped in S.expect_refused().
"""
import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

import layers
import layers.contract as C
import layer_schema as S
from layers import R, W

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "test_fixtures" / "layers_lineage"
CHILD = "coordination/v2"
ORDER = layers.RECIPE_ORDER


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "0")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    monkeypatch.setattr(layers, "_TOLD", set())
    monkeypatch.setattr(layers, "_RUNNABLE", {}, raising=False)
    monkeypatch.setattr(S, "PER_DEPARTMENT", True)
    R._DEFS.clear()
    yield tmp_path / "departments"
    R._DEFS.clear()


def RT():
    """The runtime module itself: R and W are lazy proxies that read it afresh, and a monkeypatch must patch the module, not the proxy."""
    return importlib.import_module("engine_runtime")


def load_fixture(monkeypatch, layer="coordination"):
    """The fixture child of layers/<layer>/v1, executed under its module name and registered as the registry would hold it."""
    path = FIXTURE / layer / "v2.py"
    name = "layers.%s.v2" % layer
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    monkeypatch.setitem(layers._LOADED, "%s/v2" % layer, module)
    return module


@pytest.fixture
def child(monkeypatch):
    """The fixture child, loaded; and, for the interface's check of a record that names it, found as if it were on disk (the interface
    asks layers.available(), which lists layers/ only: the fixture is never put there)."""
    module = load_fixture(monkeypatch)
    real = S._available
    monkeypatch.setattr(S, "_available", lambda: {layer: (ids + [CHILD] if layer == "coordination" else ids) for layer, ids in real().items()})
    return module


def department(home, ref, **pins):
    """A department made with W.create, and, for each layer=impl given, the pin its record holds (written the way Root writes it)."""
    C.fixture_department(home, ref)
    if pins:
        d = W.dept(ref)
        d["layers"] = dict(d["layers"], **pins)
        W.save_dept(ref, d, by="root")
    return ref


def born_post(ref):
    """An engine is born: the post Coordination's handler 'An engine is born' hears."""
    return R.post(ref, "Identity", "Coordination", "inform", {"word": "born", "engines": ["Plan"], "version": 1})


def coordination_rows(ref):
    return [(r["step"], r["impl"]) for r in R.step_rows(ref) if r["engine"] == "Coordination" and r.get("mode") != "gate"]


def child_ids():
    return tuple(CHILD if layer == "coordination" else S.DEFAULT_PINS[layer] for layer in ORDER)


# ---- N1 . recipes per pin set ----------------------------------------------------------------------------------------------
def test_n1_recipes_for_no_pins_are_the_defaults_and_a_pin_puts_its_recipe_in_its_layers_place(child):
    default = layers.recipes()
    assert layers.recipes({}) == default == layers.recipes(dict(S.DEFAULT_PINS))
    got = layers.recipes({"coordination": CHILD})
    assert got["Coordination"] == layers.recipe(CHILD) and got["Coordination"] != default["Coordination"]
    assert {t: e for t, e in got.items() if t != "Coordination"} == {t: e for t, e in default.items() if t != "Coordination"}
    assert list(got) == list(default), "the order the definitions keep"


def test_n1_a_pin_is_assembled_by_recipe_never_by_reading_its_file_here(child, monkeypatch):
    seen = []
    from layers import versions
    real = versions.recipe
    monkeypatch.setattr(versions, "recipe", lambda impl, folder=None: seen.append(impl) or real(impl, folder))
    layers.recipes({"coordination": CHILD, "audit": "audit/v1"})
    assert seen[0] == CHILD and set(seen) == {CHILD, "coordination/v1"}, \
        "the fixture lives outside layers/: only recipe() finds its file (and its parent's); a default pin is read as before"


def test_n1_a_recipe_that_does_not_merge_refuses_the_assembly_with_a_named_fault(child, monkeypatch):
    from layers import lineage, versions

    def boom(impl, folder=None):
        raise lineage.ModelFault("the patch is torn")
    monkeypatch.setattr(versions, "recipe", boom)
    with pytest.raises(ValueError, match="Coordination's recipe .coordination/v2. does not merge .the patch is torn."):
        layers.recipes({"coordination": CHILD})


def test_n1_pins_lay_the_records_version_over_the_defaults_when_the_registry_can_load_it(home, child):
    ref = department(home, "dref-v2", coordination=CHILD)
    want = dict(S.DEFAULT_PINS, coordination=CHILD)
    assert layers.pins(ref) == want and layers.pins(ref, W.dept(ref)) == want
    assert layers.pins() == S.DEFAULT_PINS and layers.pins("dref-nobody") == S.DEFAULT_PINS
    assert layers.impl(ref, "coordination") is child and layers.impl(ref, "identity") is layers.load("identity/v1")
    assert layers.pins(ref, dict(W.dept(ref), layers={"coordination": None, "audit": "audit/v1"})) == S.DEFAULT_PINS, "a pin not named is no pin"
    assert not [r for r in W.runs(ref) if "per-department" in str(r.get("what"))], "a pin that runs is no news"


def test_n1_a_pin_the_registry_cannot_load_runs_the_layers_default_with_one_row(home, child):
    ref = department(home, "dref-x")
    for named in ({"identity": "identity/v9"}, {"audit": "coordination/v1"}, {"priority": "priority"}, {"coordination": 2}):
        d = dict(W.dept(ref), layers=dict(S.DEFAULT_PINS, **named))
        for _ in range(3):
            assert layers.pins(ref, d) == S.DEFAULT_PINS, named
    rows = [(r["engine"], r["what"]) for r in W.runs(ref) if "per-department" in str(r.get("what"))]
    assert rows == [(S.TITLE[layer], "runs the default: its per-department version cannot run here") for layer in ("identity", "audit", "priority", "coordination")]


def test_n1_with_per_department_off_every_department_runs_the_defaults(home, child, monkeypatch):
    ref = department(home, "dref-v2", coordination=CHILD)
    monkeypatch.setattr(S, "PER_DEPARTMENT", False)
    assert layers.pins(ref) == S.DEFAULT_PINS
    with R.pinned(ref):
        assert R.current_ids() == R.default_ids()
        assert R.step_def("coord.probe") == (None, None)


def test_n1_the_default_set_is_served_with_no_department_in_hand(child):
    base = R.defs()
    assert R.current_ids() == R.default_ids() == tuple(S.DEFAULT_PINS[layer] for layer in ORDER)
    assert R.step_def("coord.probe") == (None, None), "version 2's step is nobody's in the default definitions"
    with R.pinned():
        assert R.defs() is base
    with R.pinned("dref-nobody"):
        assert R.defs() is base, "no department at that ref: the default set"


def test_n1_a_department_in_hand_reads_its_own_definitions_and_the_default_comes_back(home, child):
    ref = department(home, "dref-v2", coordination=CHILD)
    base = R.defs()
    with R.pinned(ref):
        assert R.current_ids() == child_ids()
        mine = R.defs()
        assert mine is not base and mine is R.defs(), "assembled once, then served"
        assert R.step_def("coord.probe")[0] == "Coordination"
        ids = [s["id"] for s in R.all_steps("Coordination")]
        assert ids.index("coord.probe") == ids.index("coord.table") + 1
        born = R._handler(R.engine_def("Coordination"), {"msg_type": "inform", "payload": {"word": "born"}})
        assert [s["id"] for s in born["steps"]] == ["coord.table", "coord.probe"], "the probe runs after the table step"
        assert R.engine_def("Coordination")["description"] == "Coordination, version 2 (a fixture): version 1 and one probe step."
        assert {n: e for n, e in mine["engines"].items() if n != "Coordination"} == \
               {n: e for n, e in base["engines"].items() if n != "Coordination"}, "every other engine is the default's"
    assert R.defs() is base and R.step_def("coord.probe") == (None, None)
    assert [s["id"] for s in R._handler(R.engine_def("Coordination"), {"msg_type": "inform", "payload": {"word": "born"}})["steps"]] == ["coord.table"]


def test_n1_the_assembly_is_cached_per_tuple_and_a_child_and_its_parent_are_different_keys(home, child, monkeypatch):
    ref = department(home, "dref-v2", coordination=CHILD)
    made = []
    real = layers.recipes
    monkeypatch.setattr(layers, "recipes", lambda pins=None: made.append(pins) or real(pins))
    with R.pinned(ref):
        first = R.defs()
    with R.pinned(ref):
        assert R.defs() is first
    assert child_ids() in R._DEFS and R.default_ids() not in R._DEFS, "the default set is the file's, held under its own key"
    assert [m["coordination"] for m in made if m] == [CHILD], "one assembly for the tuple"
    R._DEFS.clear()
    with R.pinned(ref):
        assert R.defs() is not first, "a cleared cache assembles again"


def test_n1_a_set_the_definitions_refuse_raises_as_the_default_set_does(home, child, monkeypatch):
    ref = department(home, "dref-v2", coordination=CHILD)
    real = RT().validate
    monkeypatch.setattr(RT(), "validate", lambda d, provided=None: ["a fault of the set"] if provided else real(d, provided))
    with R.pinned(ref):
        with pytest.raises(ValueError, match="the engine definitions are refused: a fault of the set"):
            R.defs()


def test_n1_the_name_a_version_outside_layers_brings_is_served_to_the_definitions_it_is_in(home, child):
    ref = department(home, "dref-v2", coordination=CHILD)
    assert "coord_probe" not in layers.names("code"), "the fixture is not on disk under layers/"
    with R.pinned(ref):
        assert R.validate(R.defs(), {"code": {"coord_probe"}}) == [], "the set is whole once the version brings its name"
    assert R.validate(R.defs()) == []


def test_n1_a_department_pinned_to_the_child_runs_the_step_and_one_on_the_parent_does_not(home, child):
    on_child, on_parent = department(home, "dref-v2", coordination=CHILD), department(home, "dref-v1")
    for ref in (on_child, on_parent):
        born_post(ref)
        W.run_until_idle(ref, limit=20)
    assert coordination_rows(on_child) == [("coord.table", CHILD), ("coord.probe", CHILD)]
    assert coordination_rows(on_parent) == [("coord.table", "coordination/v1")]
    probe = next(r for r in R.step_rows(on_child) if r["step"] == "coord.probe")
    assert probe["status"] == "ok" and probe["check"]["ok"] and probe["by"] == "code"


def test_n1_both_pass_the_contract_for_the_version_each_pins(home, child):
    ctx = {"ref": department(home, "dref-c")}
    for impl in ("coordination/v1", CHILD):
        module = layers.load(impl)
        assert len(C.cases()) >= 13
        for number, what, fn in C.cases():
            assert fn(module, ctx) == [], "%s, case %d: %s" % (impl, number, what)


def test_n1_the_steps_of_a_side_by_side_step_run_in_the_department_that_started_them(home, child, monkeypatch):
    """A fan-out step runs in worker threads, which have no context of their own: they read the department's definitions."""
    ref = department(home, "dref-v2", coordination=CHILD)
    code = {"nature": "transform", "born": "C2", "code": "x", "check": "y"}
    fake = {"kind": "function", "start": {"on": [{"kind": "post"}]}, "on": [],
            "steps": [dict(code, id="t.a", name="List"), dict(code, id="t.b", name="Each", each="t.a.pages", side_by_side=2)]}
    seen = []

    def run_step(ctx, step, item):
        probe = any(x["id"] == "coord.probe" for h in R.defs()["engines"]["Coordination"]["on"] for x in h["steps"])
        seen.append((step["id"], item, R.current_ids(), probe))
        return {"status": "ok"}, ({"pages": [1, 2, 3, 4]} if step["id"] == "t.a" else {"page": item})
    monkeypatch.setattr(RT(), "engine_def", lambda name: fake)
    monkeypatch.setattr(RT(), "run_step", run_step)
    R.run_engine(ref, "Coordination", {"art": "Brief", "v": 1}, "slot-pool")
    fanned = [row for row in seen if row[0] == "t.b"]
    assert sorted(item for _, item, _, _ in fanned) == [1, 2, 3, 4]
    assert all(ids == child_ids() and probe for _, _, ids, probe in fanned), fanned
    assert R._PINS.get() is None


def test_n1_the_entry_points_of_the_runtime_put_the_departments_versions_in_hand(home, child, monkeypatch):
    ref = department(home, "dref-v2", coordination=CHILD)
    for name in ("post", "next_due", "sweep", "run_engine"):
        assert getattr(getattr(RT(), name), "__wrapped__", None) is not None, "%s is wrapped by in_dept" % name
    held = {}

    def spy(name):
        real = getattr(RT(), name)

        def look(*args, **kwargs):
            held.setdefault(name, []).append(RT().current_ids())
            return real(*args, **kwargs)
        monkeypatch.setattr(RT(), name, look)
    for name in ("_run_rule", "_handler", "_ask_rule"):          # what the delivery, the run and the sweep each call first
        spy(name)
    born_post(ref)
    W.run_until_idle(ref, limit=20)
    assert held["_run_rule"] and held["_handler"], held.keys()
    assert all(ids == child_ids() for name in ("_run_rule", "_handler") for ids in held[name]), "the delivery and the run read the department's own versions"
    assert RT()._PINS.get() is None, "and nothing stays in hand after them"
    R.sweep(ref)
    assert held["_ask_rule"] and all(ids == child_ids() for ids in held["_ask_rule"]), "and so does the sweep"
    assert RT()._PINS.get() is None


def test_n1_a_route_with_a_ref_reads_the_departments_own_definitions(home, child):
    import website_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    on_child, on_parent = department(home, "dref-v2", coordination=CHILD), department(home, "dref-v1")
    app = FastAPI()
    app.include_router(website_api.router)
    api = TestClient(app)
    ids = {ref: [s["id"] for s in api.get("/api/native/%s/steps/Coordination" % ref).json()["steps"]] for ref in (on_child, on_parent)}
    assert "coord.probe" in ids[on_child] and "coord.probe" not in ids[on_parent]
    assert ids[on_child].index("coord.probe") == ids[on_child].index("coord.table") + 1
    assert R._PINS.get() is None, "the request's context did not leak into this one"


def test_n1_a_route_whose_pins_cannot_be_read_reads_the_default_definitions(monkeypatch):
    import interface_http
    monkeypatch.setattr(RT(), "pinned", lambda ref=None, d=None: (_ for _ in ()).throw(RuntimeError("no runtime")))
    with interface_http.department_pins("dref-x"):
        assert R.current_ids() == R.default_ids()
    with interface_http.department_pins(None):
        assert R.current_ids() == R.default_ids()
