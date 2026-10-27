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
import copy
import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

import layers
import layers.contract as C
import layer_schema as S
from layers import R, W
from layers import lineage as L

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
    cannot = "runs the default: its per-department version cannot run here (%s)"
    assert rows == [("Identity", cannot % "it does not load")] + [(S.TITLE[layer], cannot % "it is not a version of %s" % S.TITLE[layer])
                                                                for layer in ("audit", "priority", "coordination")]


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
    real = RT().validate
    monkeypatch.setattr(RT(), "validate", lambda d, provided=None: ["a fault of the set"] if provided else real(d, provided))
    with pytest.raises(ValueError, match="the engine definitions are refused: a fault of the set"):
        R.defs_of(child_ids())
    assert child_ids() not in R._DEFS, "a refused set is not kept"


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


# ---- N2 . Root's version from the organisation's Root; a pin that cannot run -------------------------------------------------
def stub(tmp_path, recipe=None, patch=None, layer="coordination", **more):
    """A child of layers/<layer>/v1 as a SimpleNamespace (A2-INHERIT's way): the tables copied from the parent, its folder in
    tmp_path, and the recipe (a whole file) or the patch it is given written beside it. `more` overrides any attribute."""
    from layers import versions as V
    parent = layers.load("%s/v1" % layer)
    folder = tmp_path / layer
    folder.mkdir(parents=True, exist_ok=True)
    base = dict(__file__=str(folder / "v2.py"), LAYER=layer, VERSION=2, IMPLEMENTS=S.SCHEMA_VERSION, PARENT="%s/v1" % layer,
                CODE=dict(parent.CODE), PROMPT=dict(parent.PROMPT), DRAFT=dict(parent.DRAFT), CHECK=dict(parent.CHECK),
                WORDS=copy.deepcopy(parent.WORDS), LAYOUT=copy.deepcopy(parent.LAYOUT))
    base.update({name: getattr(parent, name) for name in V.SURFACE if callable(getattr(parent, name, None))})
    if recipe is not None:
        (folder / "v2.json").write_text(json.dumps(recipe), encoding="utf-8")
        base["RECIPE"] = "v2.json"
    if patch is not None:
        (folder / "v2.patch.json").write_text(json.dumps(patch), encoding="utf-8")
        base["RECIPE_PATCH"] = "v2.patch.json"
    base.update(more)
    return types.SimpleNamespace(**base)


def patch_of(*steps, **top):
    """A patch for coordination/v1 that carries `steps` for the handler of an engine being born, and `top` keys beside it."""
    return dict({"parent": "coordination/v1", "on": [{"when": {"msg_type": "inform", "word": "born"}, "steps": list(steps)}]}, **top)


def soft_step(sid, **where):
    """A new step by an agent (born at C0, a prompt and its draft): the kind a unit may hold between its first and its last."""
    return dict({"id": sid, "name": "A soft step", "nature": "decide", "born": "C0", "ceiling": "C2", "prompt": "coord_tie",
                 "draft": "coord_tie_draft", "out": {"answer": "str", "why": "str"}, "answer": "answer",
                 "check": "names_who_goes_first"}, **where)


def hold(monkeypatch, impl, module):
    """The registry holds `module` as the version `impl`, and the interface finds it as it would a file on disk."""
    monkeypatch.setitem(layers._LOADED, impl, module)
    real = S._available
    monkeypatch.setattr(S, "_available", lambda: {layer: (ids + [impl] if impl.startswith(layer + "/") and impl not in ids else ids)
                                                  for layer, ids in real().items()})


def told(ref):
    return [(r["engine"], r["what"]) for r in W.runs(ref) if str(r.get("what")).startswith("runs the default") or "version of Root" in str(r.get("what"))]


@pytest.fixture
def org(home, monkeypatch):
    """An organisation's Root and one department under it; a stub child of Root's version 1 that the registry can load."""
    W.create("dref-root", "Org Root", None, kind="root")
    kid = department(home, "dref-kid")
    d = W.dept(kid)
    d["root"] = "dref-root"
    W.save_dept(kid, d, by="root")
    v1 = layers.load("root/v1")
    root_v2 = types.SimpleNamespace(LAYER="root", VERSION=2, IMPLEMENTS=S.SCHEMA_VERSION, PARENT="root/v1", RECIPE_TEMPLATE="Setup",
                                    CODE=dict(v1.CODE), PROMPT=dict(v1.PROMPT), DRAFT=dict(v1.DRAFT), CHECK=dict(v1.CHECK),
                                    WORDS=copy.deepcopy(v1.WORDS), LAYOUT=copy.deepcopy(v1.LAYOUT), standards=v1.standards,
                                    apply_option=v1.apply_option)
    hold(monkeypatch, "root/v2", root_v2)
    return {"root": "dref-root", "kid": kid, "v2": root_v2}


def pin_root(ref, impl):
    d = W.dept(ref)
    d["layers"] = dict(d["layers"], root=impl)
    W.save_dept(ref, d, by="root")


def test_n2_a_child_runs_the_organisations_root_version_and_the_roots_own_is_its_own(org):
    root, kid = org["root"], org["kid"]
    assert layers.pins(root)["root"] == layers.pins(kid)["root"] == "root/v1"
    pin_root(root, "root/v2")
    assert layers.pins(root)["root"] == "root/v2"
    assert layers.pins(kid)["root"] == "root/v2", "Root's version is the organisation's Root's"
    assert layers.impl(kid, "root") is org["v2"] and layers.impl(root, "root") is org["v2"]
    assert told(kid) == [] and told(root) == [], "the child's record names the default: nothing it asked for is set aside"
    assert layers.pins(kid, dict(W.dept(kid), root=None))["root"] == "root/v1", "a department with no Root keeps the default"
    assert layers.pins(kid, dict(W.dept(kid), root="dref-nobody"))["root"] == "root/v1", "and so does one whose Root has no record here"


def test_n2_a_childs_own_pin_of_root_is_never_followed_and_is_told_once(org):
    root, kid = org["root"], org["kid"]
    pin_root(kid, "root/v2")                                  # the child names a Root version the organisation's Root does not run
    for _ in range(3):
        assert layers.pins(kid)["root"] == "root/v1"
    assert told(kid) == [("Root", "runs the organisation's version of Root: Root's version is not pinned for one department")]
    pin_root(root, "root/v2")
    assert layers.pins(kid)["root"] == "root/v2"
    assert told(root) == []


def test_n2_a_child_pinned_to_a_root_version_that_is_not_there_runs_the_organisations_with_one_row(org):
    root, kid = org["root"], org["kid"]
    d = dict(W.dept(kid), layers=dict(S.DEFAULT_PINS, root="root/v9"))      # as an older record holds it: save_dept refuses this
    for _ in range(3):
        assert layers.pins(kid, d)["root"] == "root/v1"
    pin_root(root, "root/v2")
    assert layers.pins(kid, d)["root"] == "root/v2", "the organisation's Root version, whatever the child names"
    assert told(kid) == [("Root", "runs the organisation's version of Root: Root's version is not pinned for one department")]


def test_n2_a_root_pinned_to_a_version_that_cannot_run_runs_the_default_with_one_row(org):
    root = org["root"]
    d = dict(W.dept(root), layers=dict(S.DEFAULT_PINS, root="root/v9"))
    for _ in range(3):
        assert layers.pins(root, d)["root"] == "root/v1" and layers.pins(org["kid"], dict(W.dept(org["kid"])))["root"] == "root/v1"
    assert told(root) == [("Root", "runs the default: its per-department version cannot run here (it does not load)")]
    assert told(org["kid"]) == []


@pytest.mark.parametrize("why, make", [
    ("it does not load", lambda tmp, mp: None),
    ("it was written for another version of the interface", lambda tmp, mp: stub(tmp, IMPLEMENTS=0, patch=patch_of())),
    ("it was written for another version of the interface", lambda tmp, mp: stub(tmp, IMPLEMENTS=S.SCHEMA_VERSION + 1, patch=patch_of())),
    ("a version it extends does not load", lambda tmp, mp: stub(tmp, PARENT="coordination/v9", patch=patch_of())),
])
def test_n2_a_version_that_does_not_load_or_was_written_for_another_interface_runs_the_default_with_one_row(home, monkeypatch, tmp_path, why, make):
    module = make(tmp_path, monkeypatch)
    if module is not None:
        hold(monkeypatch, CHILD, module)
    ref = department(home, "dref-x")
    d = dict(W.dept(ref), layers=dict(S.DEFAULT_PINS, coordination=CHILD))
    for _ in range(3):
        assert layers.pins(ref, d) == S.DEFAULT_PINS
    assert told(ref) == [("Coordination", "runs the default: its per-department version cannot run here (%s)" % why)]
    with R.pinned(ref, d):
        assert R.current_ids() == R.default_ids() and R.defs() is R.defs()


def test_n2_a_pin_whose_parent_is_a_version_of_the_wrong_interface_runs_the_default(home, monkeypatch, tmp_path):
    grand = stub(tmp_path / "g", IMPLEMENTS=0, patch=patch_of())
    hold(monkeypatch, "coordination/v2", grand)
    child = stub(tmp_path / "c", VERSION=3, PARENT="coordination/v2", patch=patch_of())
    child.__dict__["RECIPE_PATCH"] = "v2.patch.json"
    hold(monkeypatch, "coordination/v3", child)
    ref = department(home, "dref-x")
    d = dict(W.dept(ref), layers=dict(S.DEFAULT_PINS, coordination="coordination/v3"))
    assert layers.pins(ref, d) == S.DEFAULT_PINS
    assert told(ref) == [("Coordination", "runs the default: its per-department version cannot run here (it was written for another version of the interface)")]


def test_n2_a_recipe_that_does_not_resolve_runs_the_default_with_one_row(home, monkeypatch, tmp_path):
    hold(monkeypatch, CHILD, stub(tmp_path, RECIPE="v2.json"))             # a whole file that is not there
    ref = department(home, "dref-x")
    d = dict(W.dept(ref), layers=dict(S.DEFAULT_PINS, coordination=CHILD))
    assert layers.pins(ref, d) == S.DEFAULT_PINS
    assert told(ref) == [("Coordination", "runs the default: its per-department version cannot run here (its recipe does not resolve)")]


def test_n2_a_soft_step_before_the_first_step_of_a_unit_runs_the_default_and_does_not_take_the_definitions_down(home, monkeypatch, tmp_path):
    child = stub(tmp_path, patch=patch_of(soft_step("coord.pre", before="coord.table")))
    hold(monkeypatch, CHILD, child)
    merged = __import__("layers.versions", fromlist=["recipe_of_module"]).recipe_of_module(child)
    assert L.recipe_faults(layers.recipe("coordination/v1"), merged, "coordination") == [], "it passes the first law"
    assert layers.definition_faults(child), "and fails the definitions"
    ref = department(home, "dref-x", coordination=CHILD)
    for _ in range(3):
        assert layers.pins(ref) == S.DEFAULT_PINS
    assert told(ref) == [("Coordination", "runs the default: its per-department version cannot run here (its steps break the rules every function keeps)")]
    with R.pinned(ref):
        assert R.current_ids() == R.default_ids()
        assert R.defs()["engines"]["Coordination"] == layers.recipes()["Coordination"], "R.defs() does not raise 'the engine definitions are refused'"
    born_post(ref)
    W.run_until_idle(ref, limit=20)
    assert coordination_rows(ref) == [("coord.table", "coordination/v1")], "the department runs on, on the default"


def test_n2_words_that_break_the_function_template_run_the_default_with_one_row(home, monkeypatch, tmp_path):
    words = copy.deepcopy(layers.load("coordination/v1").WORDS)
    words["goal"]["done"]["text"] = "The charter is met."
    child = stub(tmp_path, WORDS=words)
    hold(monkeypatch, CHILD, child)
    assert C.case_14_function_template(CHILD), "the contract's case names it"
    ref = department(home, "dref-x", coordination=CHILD)
    assert layers.pins(ref) == S.DEFAULT_PINS
    assert told(ref) == [("Coordination", "runs the default: its per-department version cannot run here (its words break what every function keeps)")]


def test_n2_the_check_is_made_once_for_a_version_never_on_a_lookup(home, child, monkeypatch):
    ref = department(home, "dref-v2", coordination=CHILD)
    from layers import versions as V
    seen = []
    real = V.definition_faults
    monkeypatch.setattr(V, "definition_faults", lambda impl, provided=None: seen.append(impl) or real(impl, provided))
    for _ in range(25):
        assert layers.pins(ref)["coordination"] == CHILD
        layers.resolve(ref, "Coordination", "code", "coord_probe", R.CODE)
    assert seen == [CHILD]
    assert layers.cannot_run(CHILD) is None and layers.cannot_run("coordination/v9") == "it does not load"
    hold(monkeypatch, CHILD, stub(tmp_path_factory_dir(), IMPLEMENTS=0))
    assert layers.cannot_run(CHILD) == "it was written for another version of the interface", "another module under the id is checked again"


def tmp_path_factory_dir():
    import tempfile
    return Path(tempfile.mkdtemp())


def test_n2_two_versions_that_run_alone_and_do_not_fit_together_run_the_defaults(home, monkeypatch, tmp_path):
    """Each passes alone against the default definitions; both add the same step id, so the definitions assembled with both are refused."""
    probe = {"id": "twin.step", "name": "A step by code", "nature": "transform", "born": "C2", "code": "coord_ready", "check": "said_what_it_did"}
    a = stub(tmp_path / "a", patch=patch_of(dict(probe, after="coord.table")))
    hold(monkeypatch, CHILD, a)
    identity_v2 = stub(tmp_path / "i", layer="identity", patch={"parent": "identity/v1", "on": [{"when": {"msg_type": "request", "word": "front"},
                                                                                                    "steps": [dict(probe, after=layers.recipe("identity/v1")["on"][0]["steps"][0]["id"])]}]})
    hold(monkeypatch, "identity/v2", identity_v2)
    assert layers.cannot_run(CHILD) is None and layers.cannot_run("identity/v2") is None
    ref = department(home, "dref-x", coordination=CHILD, identity="identity/v2")
    assert layers.pins(ref) == S.DEFAULT_PINS
    assert sorted(told(ref)) == [("Coordination", "runs the default: the versions pinned for it do not fit together"),
                                 ("Identity", "runs the default: the versions pinned for it do not fit together")]
    only = department(home, "dref-y", coordination=CHILD)
    assert layers.pins(only)["coordination"] == CHILD, "alone, either one runs"


def test_n2_a_read_of_the_department_tells_no_pin_and_the_tick_tells_it_once(home, monkeypatch, tmp_path):
    ref = department(home, "dref-x")
    d = dict(W.dept(ref), layers=dict(S.DEFAULT_PINS, identity="identity/v9"))
    with layers.reading():
        assert layers.pins(ref, d) == S.DEFAULT_PINS
        with R.pinned(ref, d):
            assert R.current_ids() == R.default_ids()
    assert told(ref) == [] and layers._TOLD == set(), "a read writes nothing and marks nothing told"
    for _ in range(2):
        layers.pins(ref, d)
    assert told(ref) == [("Identity", "runs the default: its per-department version cannot run here (it does not load)")]
