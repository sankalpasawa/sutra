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
import shutil
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


def test_n1_a_department_pinned_to_an_older_version_keeps_it_after_the_release_moves_its_default(home, tmp_path, monkeypatch):
    """The headline rule in its own direction (M2.11): a department born while coordination/v1 was the default holds that pin, so
    when a release ships v2 and makes it the default, the old department still runs v1's recipe and bodies and one born after runs v2.
    The release is laid out as it would be on disk: an overlay of layers/ with the fixture beside v1, standing in for layers.HERE
    (a default pin's recipe is found under layers/ only), and nothing is added to layers/ itself."""
    old = department(home, "dref-old")
    assert W.dept(old)["layers"]["coordination"] == "coordination/v1", "born under the release whose default was v1"
    overlay = tmp_path / "release" / "layers"
    shutil.copytree(layers.HERE, overlay, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("v2.py", "v2.patch.json"):
        shutil.copy(FIXTURE / "coordination" / name, overlay / "coordination" / name)
    v1_recipe = json.loads((overlay / "coordination" / "v1.json").read_text(encoding="utf-8"))
    v2 = load_fixture(monkeypatch)
    monkeypatch.setattr(layers, "HERE", overlay)
    monkeypatch.setitem(S.DEFAULT_PINS, "coordination", CHILD)         # the release moves on
    R._DEFS.clear()
    new = department(home, "dref-new")
    assert W.dept(new)["layers"]["coordination"] == CHILD
    assert layers.pins(old)["coordination"] == "coordination/v1" and layers.pins(new)["coordination"] == CHILD
    assert layers.impl(old, "coordination") is layers.load("coordination/v1") and layers.impl(new, "coordination") is v2, "each one's bodies"
    assert layers.recipes()["Coordination"] == layers.recipe(CHILD), "the default is now the child's"
    assert layers.recipes({"coordination": "coordination/v1"})["Coordination"] == v1_recipe, "a v1 pin is the whole file, though no longer the default"
    old_ids = tuple("coordination/v1" if layer == "coordination" else S.DEFAULT_PINS[layer] for layer in ORDER)
    with R.pinned(old):
        assert R.current_ids() == old_ids != R.default_ids()
        assert R.step_def("coord.probe") == (None, None) and R.step_def("coord.table")[0] == "Coordination"
        assert R.engine_def("Coordination") == v1_recipe
    with R.pinned(new):
        assert R.current_ids() == R.default_ids() == child_ids()
        assert R.step_def("coord.probe")[0] == "Coordination"
    for ref in (old, new):
        born_post(ref)
        W.run_until_idle(ref, limit=20)
    assert coordination_rows(old) == [("coord.table", "coordination/v1")]
    assert coordination_rows(new) == [("coord.table", CHILD), ("coord.probe", CHILD)]
    assert told(old) == [] and told(new) == [], "a pin that runs is no news, the old one least of all"
    assert R._PINS.get() is None


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
def stub(tmp_path, recipe=None, patch=None, layer="coordination", parent_id=None, **more):
    """A child of layers/<layer>/v1 (or of `parent_id`) as a SimpleNamespace (A2-INHERIT's way): the tables copied from the parent,
    its folder in tmp_path, and the recipe (a whole file) or the patch it is given written beside it. `more` overrides any attribute."""
    from layers import versions as V
    parent = layers.load(parent_id or "%s/v1" % layer)
    folder = tmp_path / layer
    folder.mkdir(parents=True, exist_ok=True)
    base = dict(__file__=str(folder / "v2.py"), LAYER=layer, VERSION=2, IMPLEMENTS=S.SCHEMA_VERSION, PARENT=parent_id or "%s/v1" % layer,
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


def test_n2_a_department_pinned_to_a_child_gets_the_childs_role_words_and_one_on_the_parent_does_not(home, monkeypatch, tmp_path):
    """The role words are part of a version (A3): the card of the function's agent reads them through the version the department pins."""
    words = copy.deepcopy(layers.load("coordination/v1").WORDS)
    words["goal"]["role_is"]["text"] = "keeps the table, version two, and says who goes first"
    hold(monkeypatch, CHILD, stub(tmp_path, patch={"parent": "coordination/v1"}, WORDS=words))
    assert layers.cannot_run(CHILD) is None and C.case_14_function_template(CHILD) == []
    on_child, on_parent = department(home, "dref-v2", coordination=CHILD), department(home, "dref-v1")
    blocks = {ref: R._role_block(ref, "Coordination", R.engine_def("Coordination")) for ref in (on_child, on_parent)}
    assert "keeps the table, version two, and says who goes first" in blocks[on_child]
    assert blocks[on_parent] and "version two" not in blocks[on_parent]
    assert layers.words(on_child, "coordination", "goal", "role_is")["text"] != layers.words(on_parent, "coordination", "goal", "role_is")["text"]


# ---- N3 . ladders per version -----------------------------------------------------------------------------------------------
def ladder_file(ref):
    return json.loads((W.ddir(ref) / "ladder.json").read_text(encoding="utf-8"))


def learn(ref, step_id, rung, by="a test"):
    """The step moves to `rung` for the department, as a keeper's move does it."""
    with R.pinned(ref):
        _, step = R.step_def(step_id)
        return R.move(ref, step, rung, by)


def repin(ref, **pins):
    d = W.dept(ref)
    d["layers"] = dict(d["layers"], **pins)
    W.save_dept(ref, d, by="root")


def test_n3_an_entry_is_kept_for_the_step_and_the_version_that_made_it(home):
    ref = department(home, "dref-v1")
    learn(ref, "coord.pick", "C1")
    assert set(ladder_file(ref)) == {"coord.pick@coordination/v1"}
    with R.pinned(ref):
        assert R.ladder(ref)["coord.pick"]["rung"] == "C1" and set(R.ladder(ref)) == {"coord.pick"}, "read by the step, as every reader asks"
        assert R.ladder_key(ref, "coord.pick", "Coordination") == "coord.pick@coordination/v1"
        assert R.ladder_key(ref, "identity.take", "Identity") == "identity.take@identity/v1"
        assert R.ladder_key(ref, "write.page", "Write") == "write.page", "a work engine has no versions: its key is the step"
        assert R.ladder_key(ref, "setup.read", "Setup") == "setup.read@root/v1"


def test_n3_an_old_key_is_the_version_1_entry(home, child):
    ref = department(home, "dref-v1")
    learn(ref, "coord.pick", "C1")
    old = ladder_file(ref)
    (W.ddir(ref) / "ladder.json").write_text(json.dumps({"coord.pick": old["coord.pick@coordination/v1"]}), encoding="utf-8")   # as an older app kept it
    with R.pinned(ref):
        assert R.ladder(ref)["coord.pick"]["rung"] == "C1"
        _, step = R.step_def("coord.pick")
        assert R.rung_of(ref, step) == "C1" and R.entry(ref, step)["rung"] == "C1"
    repin(ref, coordination=CHILD)
    with R.pinned(ref):
        assert R.ladder(ref)["coord.pick"]["rung"] == "C1", "a step the child leaves as it is reads the version 1 rung through the old key"
    learn(ref, "coord.pick", "C0")
    assert set(ladder_file(ref)) == {"coord.pick", "coord.pick@coordination/v2"}, "and the old key is left as it is"
    assert ladder_file(ref)["coord.pick"]["rung"] == "C1"
    repin(ref, coordination="coordination/v1")
    with R.pinned(ref):
        assert R.ladder(ref)["coord.pick"]["rung"] == "C1"
    learn(ref, "coord.pick", "C0")
    with R.pinned(ref):
        assert R.ladder(ref)["coord.pick"]["rung"] == "C0", "a key for the version beats the old key"


def test_n3_a_work_engines_step_is_kept_under_its_own_name(home):
    ref = department(home, "dref-v1")
    learn(ref, "write.page", "C1")
    assert set(ladder_file(ref)) == {"write.page"}
    with R.pinned(ref):
        assert R.ladder(ref)["write.page"]["rung"] == "C1"


def test_n3_a_pin_change_returns_a_step_the_child_changes_to_its_born_rung_and_carries_over_one_it_leaves(home, child):
    from layers import versions as V
    changes = {"coord.table", "coord.probe"}
    unchanged = V.unchanged_steps(CHILD)
    assert changes.isdisjoint(unchanged) and "coord.pick" in unchanged and "coord.busy" in unchanged
    ref = department(home, "dref-x")
    learn(ref, "coord.pick", "C1", "learned under version 1")
    learn(ref, "coord.table", "C1", "learned under version 1")
    v1_file = ladder_file(ref)
    repin(ref, coordination=CHILD)
    with R.pinned(ref):
        seen = R.ladder(ref)
        assert seen["coord.pick"]["rung"] == "C1", "carried over"
        assert "coord.table" not in seen, "a rung learned under version 1 is not applied to a step version 2 changed"
        _, table = R.step_def("coord.table")
        assert R.rung_of(ref, table) == table["born"] == "C2" and R.entry(ref, table)["history"][0]["by"] == "born"
        assert R.entry(ref, table)["rung"] == "C2"
    assert ladder_file(ref) == v1_file, "reading writes nothing"


def test_n3_a_run_under_the_child_never_writes_the_parents_key(home, child):
    ref = department(home, "dref-x")
    learn(ref, "coord.pick", "C1", "learned under version 1")
    learn(ref, "coord.table", "C1", "learned under version 1")
    v1_file = ladder_file(ref)
    repin(ref, coordination=CHILD)
    learn(ref, "coord.pick", "C0", "learned under version 2")
    learn(ref, "coord.table", "C0", "learned under version 2")
    now = ladder_file(ref)
    assert {k: now[k] for k in v1_file} == v1_file, "version 1's entries are as they were"
    assert set(now) == set(v1_file) | {"coord.pick@coordination/v2", "coord.table@coordination/v2"}
    pick = now["coord.pick@coordination/v2"]
    assert pick["rung"] == "C0" and [h["by"] for h in pick["history"]] == ["born", "learned under version 1", "learned under version 2"], \
        "the child's entry begins from the rung it read, and says where it came from"
    assert [h["by"] for h in now["coord.table@coordination/v2"]["history"]] == ["born", "learned under version 2"]
    repin(ref, coordination="coordination/v1")
    with R.pinned(ref):
        assert (R.ladder(ref)["coord.pick"]["rung"], R.ladder(ref)["coord.table"]["rung"]) == ("C1", "C1"), "back on version 1, its own rungs"


def test_n3_a_hold_carries_over_with_the_rung_and_is_the_childs_own_after_it(home, child):
    ref = department(home, "dref-x")
    with R.pinned(ref):
        R.hold(ref, "coord.pick", True)
    repin(ref, coordination=CHILD)
    with R.pinned(ref):
        assert R.ladder(ref)["coord.pick"]["held"] is True
        R.hold(ref, "coord.pick", False)
        assert R.ladder(ref)["coord.pick"]["held"] is False
    assert ladder_file(ref)["coord.pick@coordination/v1"]["held"] is True


def test_n3_a_step_reads_the_rung_of_the_version_that_made_it_what_it_is_up_the_lineage(home, child, monkeypatch, tmp_path):
    """v3 extends v2 extends v1. v2 changed coord.table and coord.probe; v3 changes coord.pick and leaves the rest as v2 has them."""
    v3 = stub(tmp_path, parent_id=CHILD, VERSION=3,
              patch={"parent": CHILD, "rules": [{"id": "coord.pick", "name": "Say who goes first, version 3"}]})
    hold(monkeypatch, "coordination/v3", v3)
    from layers import versions as V
    assert V.chain("coordination/v3") == ["coordination/v3", CHILD, "coordination/v1"]
    assert "coord.pick" not in V.unchanged_steps("coordination/v3") and {"coord.table", "coord.probe", "coord.busy"} <= V.unchanged_steps("coordination/v3")
    ref = department(home, "dref-x")
    learn(ref, "coord.busy", "C1", "version 1")
    learn(ref, "coord.pick", "C1", "version 1")
    learn(ref, "coord.table", "C1", "version 1")
    repin(ref, coordination=CHILD)
    learn(ref, "coord.table", "C0", "version 2")
    learn(ref, "coord.probe", "C0", "version 2")
    repin(ref, coordination="coordination/v3")
    with R.pinned(ref):
        seen = {k: v["rung"] for k, v in R.ladder(ref).items()}
    assert seen == {"coord.busy": "C1", "coord.table": "C0", "coord.probe": "C0"}, \
        "busy: v2 left it as v1, so v1's rung; table and probe: v2 made them what they are, so v2's; pick: v3 changed it, so it is born"
    learn(ref, "coord.busy", "C0", "version 3")
    now = ladder_file(ref)
    assert now["coord.busy@coordination/v1"]["rung"] == "C1" and now["coord.busy@coordination/v3"]["rung"] == "C0"
    assert "coord.busy@coordination/v2" not in now, "the middle version never wrote it"


def test_n3_what_a_version_inherits_is_worked_out_once_and_again_for_another_module(home, child, monkeypatch):
    ref = department(home, "dref-x", coordination=CHILD)
    from layers import versions as V
    seen = []
    real = V.unchanged_steps
    monkeypatch.setattr(V, "unchanged_steps", lambda impl: seen.append(impl) or real(impl))
    monkeypatch.setattr(RT(), "_INHERITS", {})
    learn(ref, "coord.pick", "C1")
    for _ in range(10):
        with R.pinned(ref):
            R.ladder(ref)
    assert seen.count(CHILD) == 1 and len(seen) == len(set(seen)), seen


# ---- N4 . the pin option ----------------------------------------------------------------------------------------------------
def on_disk(monkeypatch, *impls):
    """The registry lists `impls` as versions the app has, as it would a file under layers/ (it lists layers/ only, and nothing is
    put there): the pin option asks layers.available(), and so does the interface's check of a record."""
    real = layers.available

    def available():
        out = {layer: list(ids) for layer, ids in real().items()}
        for impl in impls:
            if impl not in out.setdefault(impl.split("/")[0], []):
                out[impl.split("/")[0]].append(impl)
        return out
    monkeypatch.setattr(layers, "available", available)


def pin_option(layer, impl):
    """The option as a card offers it: the id is the kind and the version's name (an id has no '/', the ask's schema says), the
    layer and the version are its params."""
    return W.option("pin:%s" % impl.replace("/", "."), "Run another version of %s" % S.TITLE[layer], "nothing", {"layer": layer, "impl": impl})


def apply_pin(ref, option, ask=None):
    return layers.impl(ref, "root").apply_option(ref, ask or {"id": "a-pin", "kind": "line", "options": [option]}, option)


def pins_in_record(ref):
    return W.dept(ref)["layers"]


def test_n4_the_pin_option_is_the_interfaces_and_root_applies_it():
    assert S.PER_DEPARTMENT is True and S.describe()["per_department"] is True
    spec = S.OPTION_KINDS["pin"]
    assert (spec["layer"], spec["params"]) == ("root", "option.pin") and S.validate("option.pin", {"layer": "audit", "impl": "audit/v2"}) == []
    assert pin_option("coordination", CHILD)["kind"] == "pin" and pin_option("coordination", CHILD)["params"] == {"layer": "coordination", "impl": CHILD}
    assert callable(layers.load("root/v1").apply_option)


def test_n4_a_pin_for_a_version_the_app_has_writes_the_record_through_root_and_the_department_runs_it(home, child, monkeypatch):
    on_disk(monkeypatch, CHILD)
    ref = department(home, "dref-x")
    before = dict(pins_in_record(ref))
    got = apply_pin(ref, pin_option("coordination", CHILD))
    assert got == {"layer": "coordination", "impl": CHILD, "was": "coordination/v1"}
    assert pins_in_record(ref) == dict(before, coordination=CHILD), "the record names it, and only that layer's pin changed"
    assert ("Coordination", "runs version 2 from now on") in [(r["engine"], r["what"]) for r in W.runs(ref)]
    assert layers.pins(ref)["coordination"] == CHILD
    born_post(ref)
    W.run_until_idle(ref, limit=20)
    assert coordination_rows(ref) == [("coord.table", CHILD), ("coord.probe", CHILD)], "and from its next step the department runs it"
    assert apply_pin(ref, pin_option("coordination", "coordination/v1"))["was"] == CHILD, "and the pin goes back the same way"
    assert pins_in_record(ref) == before


def test_n4_the_write_is_roots_the_interface_asks_who_wrote_a_key(home, child, monkeypatch):
    on_disk(monkeypatch, CHILD)
    ref = department(home, "dref-x")
    seen = []
    real = W.save_dept
    monkeypatch.setattr(importlib.import_module("website_dept"), "save_dept", lambda r, d, by=None: seen.append(by) or real(r, d, by=by))
    apply_pin(ref, pin_option("coordination", CHILD))
    assert seen == ["root"]


def _refused(ref, option, says, monkeypatch=None):
    before = copy.deepcopy(W.dept(ref))
    with pytest.raises(W.AskError) as caught:
        apply_pin(ref, option)
    assert caught.value.code == "UNKNOWN_OPTION" and str(caught.value) == says, str(caught.value)
    assert isinstance(caught.value, ValueError), "Identity's apply_way catches a ValueError, and the card waits as it was"
    assert W.dept(ref) == before, "nothing changed"


def test_n4_a_version_the_app_does_not_have_is_unknown_option(home):
    ref = department(home, "dref-x")
    _refused(ref, pin_option("identity", "identity/v9"), "this app has no version 9 of Identity")


def test_n4_a_version_of_another_function_is_unknown_option(home):
    ref = department(home, "dref-x")
    _refused(ref, pin_option("audit", "identity/v1"), "version 1 is not a version of Audit")


def test_n4_a_pin_with_no_layer_or_version_is_unknown_option(home):
    ref = department(home, "dref-x")
    _refused(ref, W.option("pin", "Run another version", "nothing", {"layer": "audit"}), "say which version of which function to run")
    _refused(ref, W.option("pin", "Run another version", "nothing"), "say which version of which function to run")
    _refused(ref, W.option("pin:audit.v1", "Run another version", "nothing", {"layer": "audit", "impl": "audit/1"}), "say which version of which function to run")


def test_n4_a_version_that_loads_but_cannot_run_is_unknown_option(home, monkeypatch, tmp_path):
    on_disk(monkeypatch, CHILD)
    monkeypatch.setitem(layers._LOADED, CHILD, stub(tmp_path, patch=patch_of(soft_step("coord.pre", before="coord.table"))))
    ref = department(home, "dref-x")
    _refused(ref, pin_option("coordination", CHILD), "version 2 of Coordination cannot run: its steps break the rules every function keeps")
    monkeypatch.setitem(layers._LOADED, CHILD, stub(tmp_path / "w", IMPLEMENTS=0, patch=patch_of()))
    layers._RUNNABLE.clear()
    _refused(ref, pin_option("coordination", CHILD), "version 2 of Coordination cannot run: it was written for another version of the interface")


def test_n4_a_version_on_disk_that_does_not_load_is_unknown_option(home, monkeypatch):
    on_disk(monkeypatch, "priority/v2")                                  # listed, and nothing can be imported under that name
    ref = department(home, "dref-x")
    _refused(ref, pin_option("priority", "priority/v2"), "version 2 of Priority cannot run: it does not load")


def test_n4_a_pin_for_root_applies_only_on_the_root_department(org, monkeypatch):
    on_disk(monkeypatch, "root/v2")
    kid, root = org["kid"], org["root"]
    _refused(kid, pin_option("root", "root/v2"), "Root's version is chosen on Root, for the whole organisation")
    assert apply_pin(root, pin_option("root", "root/v2")) == {"layer": "root", "impl": "root/v2", "was": "root/v1"}
    assert pins_in_record(root)["root"] == "root/v2" and pins_in_record(kid)["root"] == "root/v1"
    assert layers.pins(kid)["root"] == "root/v2", "and the organisation's other departments follow it"


def test_n4_an_option_that_is_not_a_pin_is_still_root_setup(home):
    ref = department(home, "dref-x")
    with pytest.raises(ValueError, match="say what the department is for"):
        layers.impl(ref, "root").apply_option(ref, {}, W.option("root_setup", "Set it up again", "nothing"))
    with pytest.raises(ValueError, match="say what the department is for"):
        layers.impl(ref, "root").apply_option(ref, {}, {"id": "root_setup"})


def test_n4_the_layers_route_shows_the_pin_the_record_holds(home, child, monkeypatch):
    on_disk(monkeypatch, CHILD)
    import website_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    ref = department(home, "dref-x")
    app = FastAPI()
    app.include_router(website_api.router)
    api = TestClient(app)
    assert api.get("/api/native/%s/layers" % ref).json()["pins"] == S.DEFAULT_PINS
    apply_pin(ref, pin_option("coordination", CHILD))
    got = api.get("/api/native/%s/layers" % ref).json()
    assert got["pins"] == dict(S.DEFAULT_PINS, coordination=CHILD) and got["describe"]["per_department"] is True


def card(ref, *options, said="Another version of one function can run."):
    """A card the owner answers (a blocked plan's, the one place a way out is chosen and applied by code), with these ways out."""
    return RT()._blocked(ref, W.dept(ref), {"src": RT().OWNER}, said, "Another version", "Identity", "a test", options=list(options))


def test_n4_the_owner_chooses_a_pin_on_a_card_and_identity_applies_it_through_root(home, child, monkeypatch):
    on_disk(monkeypatch, CHILD)
    ref = department(home, "dref-x")
    ask = card(ref, pin_option("coordination", CHILD), W.option("stop", "Stop here", "the department stops"))
    W.choose_option(ref, ask["id"], "pin:coordination.v2")
    W.run_until_idle(ref, limit=30)
    assert pins_in_record(ref)["coordination"] == CHILD
    assert next(a for a in W.asks(ref) if a["id"] == ask["id"])["status"] == "chosen"
    said = [r["what"] for r in W.runs(ref)]
    assert "applied the owner's choice (pin:coordination.v2) through Root" in said and "runs version 2 from now on" in said


def test_n4_a_pin_that_is_refused_leaves_the_card_waiting_and_says_why_in_plain_words(home, monkeypatch):
    ref = department(home, "dref-x")
    ask = card(ref, pin_option("identity", "identity/v9"), W.option("stop", "Stop here", "the department stops"))
    W.choose_option(ref, ask["id"], "pin:identity.v9")
    W.run_until_idle(ref, limit=30)
    assert pins_in_record(ref) == S.DEFAULT_PINS, "nothing changed"
    told = [p["payload"].get("done") for p in RT().board(ref) if p["src"] == "Identity" and p["dst"] == ["Owner"] and p["msg_type"] == "inform"]
    assert "this app has no version 9 of Identity. Nothing changed; choose again on the card." in told
    assert not [t for t in told if "UNKNOWN_OPTION" in str(t)], "the code is the API's, never the owner's"
    assert any("could not apply the owner's choice (pin:identity.v9)" in r["what"] for r in W.runs(ref))


# ---- the whole way: a department made as a person makes one, pinned, runs ----------------------------------------------------
@pytest.fixture
def j2(home, monkeypatch):
    """test_j2's fixture: the records home and the registry in this test's own folder, the modules reloaded, a domain minted."""
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    import website_dept
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime
    import j2_runtime
    import functions_view
    for module in (E, website_dept, org2_apply, founding, engine_runtime, j2_runtime, functions_view):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return founding


def test_a_department_made_the_way_a_person_makes_one_runs_to_its_work_on_the_version_its_record_pins(j2, child, monkeypatch):
    on_disk(monkeypatch, CHILD)
    root = j2.found_structure("Acme Learning", owner="Sankalp")["root"]
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=300)
    kid = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    assert W.dept(kid)["root"] == root and layers.pins(kid) == S.DEFAULT_PINS
    apply_pin(kid, pin_option("coordination", CHILD))                  # the owner's stamp on the card, as Root applies it
    assert layers.pins(kid)["coordination"] == CHILD and layers.pins(root) == S.DEFAULT_PINS, "a pin is one department's"
    W.run_until_idle(kid, limit=300)
    runs = W.runs(kid)
    assert {r["engine"] for r in runs} >= {"Plan", "Write", "Check"} and not [r for r in runs if r["status"] in ("failed", "interrupted")]
    rows = [r for r in R.step_rows(kid) if r.get("impl")]
    assert {r["impl"] for r in rows if r["engine"] == "Coordination"} == {"coordination/v1", CHILD}, "before the pin and after it"
    assert [r for r in rows if r["engine"] == "Coordination" and r["impl"] == CHILD], "and the department ran its Coordination on the child"
    assert {r["impl"] for r in rows if r["engine"] != "Coordination" and r["impl"]} <= {"identity/v1", "adaptation/v1", "priority/v1", "audit/v1"}, \
        "every other function ran its own"
    assert RT()._PINS.get() is None
