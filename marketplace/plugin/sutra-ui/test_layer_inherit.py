"""A version that extends a version (PRD amendment A2, A2-INHERIT): layers/versions.py, the registry's five wrappers, contract cases
9 to 13, the fixture child end to end, the workflow family and the one entry for the standards.

  I1  inherit, chain, recipe and recipes(): the child's tables hold the parent's very callables, a lineage is walked and refused when
      it repeats or is too deep, a recipe is a whole file, a patch over the parent's, or the parent's, and recipes() resolves a
      default pin that is a patch child
  I2  definition_faults (engine_runtime.validate with the child's recipe in its layer's place) and unchanged_steps
  I3  the contract: recipe_of through the patch and cases 9 to 13, each shown to catch what it is for on a purpose-built stub child
  I4  the fixture child of coordination/v1 (test_fixtures/layers_lineage/coordination), end to end
  I5  S.WORKFLOW_FAMILY, _line_notes through S.validate_workflow, and no other caller of workflow_schema.run

The fixture child lives under test_fixtures/, never under layers/ (test_every_layer_has_its_version_1_on_disk); a test loads it under
the name layers.coordination.v2 and puts it in layers._LOADED, and the monkeypatch takes it out again.
"""
import ast
import copy
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

import layers
import layers.contract as C
import layer_schema as S
import website_dept
from layers import R
from layers import lineage as L
from layers import versions as V

HERE = Path(__file__).resolve().parent
LAYERS = HERE / "layers"
FIXTURE = HERE / "test_fixtures" / "layers_lineage"
BORN = {"msg_type": "inform", "word": "born"}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return tmp_path


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
    return load_fixture(monkeypatch)


def stub(tmp_path, recipe=None, patch=None, layer="coordination", **more):
    """A child of layers/<layer>/v1 as a SimpleNamespace: the tables copied from the parent, its folder in tmp_path, and the recipe
    (a whole file) or the patch it is given written beside it. `more` overrides any attribute."""
    parent = layers.load("%s/v1" % layer)
    folder = tmp_path / layer
    folder.mkdir(parents=True, exist_ok=True)
    base = dict(__file__=str(folder / "v2.py"), LAYER=layer, VERSION=2, IMPLEMENTS=1, PARENT="%s/v1" % layer,
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
    return dict({"parent": "coordination/v1", "on": [{"when": BORN, "steps": list(steps)}]}, **top)


def born_steps(recipe):
    return next(h for h in recipe["on"] if h["when"] == BORN)["steps"]


# ---- I1 . inherit -------------------------------------------------------------------------------------------------------
def test_i1_a_childs_tables_hold_every_entry_of_its_parent_as_the_very_callable():
    v1 = layers.load("coordination/v1")
    got = layers.inherit("coordination/v1")
    for attr in ("CODE", "PROMPT", "DRAFT", "CHECK"):
        assert getattr(v1, attr), attr
        assert set(got[attr]) == set(getattr(v1, attr))
        assert all(got[attr][name] is fn for name, fn in getattr(v1, attr).items()), attr
    assert got["CODE"]["coord_busy"].legacy == ("engine_runtime", "coord_busy"), "a ref_to stays a ref_to, with its .legacy"
    assert set(got) == {"CODE", "PROMPT", "DRAFT", "CHECK", "WORDS", "LAYOUT", "view", "engine_card"}


def test_i1_an_own_entry_replaces_the_parents_and_adds_what_is_new():
    v1 = layers.load("coordination/v1")
    busy, probe, said = (lambda ctx, step, item: 1), (lambda ctx, step, item: 2), (lambda ctx, step, item, out: {"ok": True})
    got = layers.inherit("coordination/v1", code={"coord_busy": busy, "coord_probe": probe}, check={"said_what_it_did": said})
    assert got["CODE"]["coord_busy"] is busy and got["CODE"]["coord_probe"] is probe and got["CHECK"]["said_what_it_did"] is said
    assert v1.CODE["coord_busy"].legacy == ("engine_runtime", "coord_busy"), "the parent's own table is as it was"
    assert "coord_probe" not in v1.CODE
    assert all(got["CODE"][n] is fn for n, fn in v1.CODE.items() if n != "coord_busy")
    assert all(got["CHECK"][n] is fn for n, fn in v1.CHECK.items() if n != "said_what_it_did")


def test_i1_the_tables_are_fresh_dicts_so_a_child_grows_its_own_and_never_its_parents():
    v1 = layers.load("coordination/v1")
    got = layers.inherit("coordination/v1")
    for attr in ("CODE", "PROMPT", "DRAFT", "CHECK", "WORDS", "LAYOUT"):
        assert got[attr] is not getattr(v1, attr), attr
    before = set(v1.CODE)
    got["CODE"]["coord_later"] = lambda ctx, step, item: None
    assert set(v1.CODE) == before and "coord_later" in got["CODE"]
    got["WORDS"]["goal"]["does"]["text"] = "changed in the child"
    got["LAYOUT"]["tie"]["tie"] = "changed in the child"
    assert v1.WORDS["goal"]["does"]["text"] != "changed in the child" and v1.LAYOUT["tie"]["tie"] != "changed in the child"


def test_i1_words_merge_by_field_and_layout_by_part():
    v1 = layers.load("coordination/v1")
    got = layers.inherit("coordination/v1", words={"goal": {"does": {"text": "a new sentence", "note": "an added field"}}},
                         layout={"tie": {"tie": "NEW {task}\n{returns}"}})
    assert got["WORDS"]["goal"]["does"] == {"text": "a new sentence", "note": "an added field"}
    assert got["WORDS"]["goal"]["skills"] == v1.WORDS["goal"]["skills"] and got["WORDS"]["tie"] == v1.WORDS["tie"], "other parts as they were"
    assert got["LAYOUT"]["tie"]["tie"] == "NEW {task}\n{returns}"
    assert got["LAYOUT"]["goal"] == v1.LAYOUT["goal"], "a part the child does not mention keeps the parent's layout"
    own = layers.inherit("coordination/v1", words={"tie": {"tie": {"task": "only the one field"}}})
    assert own["WORDS"]["tie"]["tie"] == {"task": "only the one field"} and own["LAYOUT"] == v1.LAYOUT


def test_i1_the_surface_functions_are_the_parents_and_only_those_the_parent_has():
    coordination, root = layers.load("coordination/v1"), layers.load("root/v1")
    got = layers.inherit("coordination/v1")
    assert got["view"] is coordination.view and got["engine_card"] is coordination.engine_card
    assert "apply_option" not in got and "standards" not in got, "coordination publishes neither"
    top = layers.inherit("root/v1")
    assert top["standards"] is root.standards and top["apply_option"] is root.apply_option
    assert set(V.SURFACE) == {"view", "engine_card", "apply_option", "standards"}


def test_i1_a_non_callable_own_entry_and_a_parent_that_does_not_load_are_model_faults():
    with pytest.raises(L.ModelFault, match="code coord_x is not callable"):
        layers.inherit("coordination/v1", code={"coord_x": "not a function"})
    with pytest.raises(L.ModelFault, match="prompt coord_tie is not callable"):
        layers.inherit("coordination/v1", prompt={"coord_tie": None})
    with pytest.raises(L.ModelFault, match="the code of a version are a dict"):
        layers.inherit("coordination/v1", code=["coord_busy"])
    for parent in ("coordination/v9", "coordination", None, ["coordination/v1"]):
        with pytest.raises(L.ModelFault, match="does not load"):
            layers.inherit(parent)
    assert issubclass(L.ModelFault, Exception) and not issubclass(L.ModelFault, ValueError)


# ---- I1 . chain ---------------------------------------------------------------------------------------------------------
def lineage_of(monkeypatch, parents):
    """Stubs in the registry, {impl id: its PARENT}."""
    for impl_id, parent in parents.items():
        monkeypatch.setitem(layers._LOADED, impl_id, types.SimpleNamespace(PARENT=parent))


def test_i1_chain_runs_nearest_first_up_to_the_version_with_no_parent(child):
    assert layers.chain("coordination/v2") == ["coordination/v2", "coordination/v1"]
    assert layers.chain("coordination/v1") == ["coordination/v1"]
    assert layers.chain("root/v1") == ["root/v1"]


def test_i1_chain_through_three_versions(monkeypatch):
    lineage_of(monkeypatch, {"identity/v2": "identity/v1", "identity/v3": "identity/v2"})
    assert layers.chain("identity/v3") == ["identity/v3", "identity/v2", "identity/v1"]


def test_i1_a_lineage_that_repeats_is_a_model_fault_naming_the_version(monkeypatch):
    lineage_of(monkeypatch, {"identity/v2": "identity/v3", "identity/v3": "identity/v2"})
    with pytest.raises(L.ModelFault, match="identity/v2 repeats in its own lineage"):
        layers.chain("identity/v2")
    lineage_of(monkeypatch, {"audit/v2": "audit/v2"})
    with pytest.raises(L.ModelFault, match="audit/v2 repeats in its own lineage"):
        layers.chain("audit/v2")


def test_i1_a_lineage_deeper_than_depth_is_a_model_fault_and_one_of_depth_is_not(monkeypatch):
    assert V.DEPTH == 8
    lineage_of(monkeypatch, {"coordination/v%d" % n: ("coordination/v%d" % (n - 1) if n > 1 else None) for n in range(1, 10)})
    assert layers.chain("coordination/v8") == ["coordination/v%d" % n for n in range(8, 0, -1)]
    with pytest.raises(L.ModelFault, match="coordination/v9: the lineage is deeper than 8 versions"):
        layers.chain("coordination/v9")


def test_i1_a_parent_that_does_not_load_is_a_model_fault_naming_it(monkeypatch):
    lineage_of(monkeypatch, {"identity/v2": "identity/v7"})
    with pytest.raises(L.ModelFault, match="identity/v7 does not load"):
        layers.chain("identity/v2")
    with pytest.raises(L.ModelFault, match="identity/v8 does not load"):
        layers.chain("identity/v8")


# ---- I1 . recipe --------------------------------------------------------------------------------------------------------
def test_i1_a_whole_file_child_brings_exactly_its_file(tmp_path):
    whole = copy.deepcopy(layers.recipe("coordination/v1"))
    whole["description"] = "a whole file, version 2"
    born_steps(whole)[0]["name"] = "Write the table, whole"
    child = stub(tmp_path, recipe=whole)
    assert V.recipe_of_module(child) == whole
    assert V.recipe_of_module(child, folder=tmp_path / "coordination") == whole


def test_i1_the_folder_a_recipe_is_read_from_can_be_given(tmp_path):
    whole = copy.deepcopy(layers.recipe("coordination/v1"))
    whole["description"] = "read from elsewhere"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "v2.json").write_text(json.dumps(whole), encoding="utf-8")
    child = stub(tmp_path / "here", RECIPE="v2.json")
    with pytest.raises(L.ModelFault, match="the recipe is missing: v2.json"):
        V.recipe_of_module(child)
    assert V.recipe_of_module(child, folder=elsewhere) == whole


def test_i1_a_patch_child_has_the_step_it_adds_and_the_rest_is_its_parents(child):
    parent, mine = layers.recipe("coordination/v1"), layers.recipe("coordination/v2")
    assert [s["id"] for s in born_steps(mine)] == ["coord.table", "coord.probe"]
    assert mine["description"] != parent["description"]
    mine["description"] = parent["description"]
    born_steps(mine).pop()
    born_steps(mine)[0]["name"] = born_steps(parent)[0]["name"]
    assert mine == parent, "everything else is the parent's"


def test_i1_a_child_with_neither_a_file_nor_a_patch_has_its_parents_recipe(tmp_path):
    child = stub(tmp_path)
    assert V.recipe_of_module(child) == layers.recipe("coordination/v1")
    assert V.recipe_of_module(child) is not V.recipe_of_module(child), "a fresh object each time"


def test_i1_a_patch_child_may_extend_a_child(tmp_path, monkeypatch, child):
    grand = stub(tmp_path, patch=dict(patch_of({"id": "coord.probe", "name": "Probe, again"}), parent="coordination/v2"),
                 VERSION=3, PARENT="coordination/v2")
    monkeypatch.setitem(layers._LOADED, "coordination/v3", grand)
    got = layers.recipe("coordination/v3")
    assert [s["id"] for s in born_steps(got)] == ["coord.table", "coord.probe"]
    assert born_steps(got)[1]["name"] == "Probe, again" and born_steps(got)[0]["name"] == born_steps(layers.recipe("coordination/v2"))[0]["name"]
    assert layers.chain("coordination/v3") == ["coordination/v3", "coordination/v2", "coordination/v1"]


def test_i1_a_patch_whose_step_breaks_the_law_is_a_model_fault_naming_the_step(tmp_path):
    fixed = patch_of({"id": "coord.table", "check": "facts_are_closed"})
    with pytest.raises(L.ModelFault, match="coord.table: check is the parent's"):
        V.recipe_of_module(stub(tmp_path, patch=fixed))
    dangling = patch_of({"id": "coord.pre", "name": "Pre", "nature": "transform", "born": "C2", "code": "coord_ready",
                         "check": "said_what_it_did", "only_if": "coord.nothing.answer", "before": "coord.table"})
    with pytest.raises(L.ModelFault, match="coord.pre: only_if points at coord.nothing, which is no step of this recipe"):
        V.recipe_of_module(stub(tmp_path, patch=dangling))
    with pytest.raises(L.ModelFault, match="coord.new: a new step needs nature, born, check"):
        V.recipe_of_module(stub(tmp_path, patch=patch_of({"id": "coord.new", "name": "No more than a name"})))


def test_i1_a_patch_for_another_parent_a_patch_with_no_parent_and_a_file_that_is_not_there_are_model_faults(tmp_path):
    other = dict(patch_of({"id": "coord.table", "name": "Again"}), parent="coordination/v7")
    with pytest.raises(L.ModelFault, match="the patch is for coordination/v7, not for coordination/v1"):
        V.recipe_of_module(stub(tmp_path, patch=other))
    with pytest.raises(L.ModelFault, match="names no PARENT"):
        V.recipe_of_module(stub(tmp_path, patch=patch_of(), PARENT=None))
    with pytest.raises(L.ModelFault, match="the recipe patch is missing: v2.patch.json"):
        V.recipe_of_module(stub(tmp_path / "none", RECIPE_PATCH="v2.patch.json"))
    (tmp_path / "bad" / "coordination").mkdir(parents=True)
    (tmp_path / "bad" / "coordination" / "v2.patch.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(L.ModelFault, match="the recipe patch is not JSON: v2.patch.json"):
        V.recipe_of_module(stub(tmp_path / "bad", RECIPE_PATCH="v2.patch.json"))
    (tmp_path / "list" / "coordination").mkdir(parents=True)
    (tmp_path / "list" / "coordination" / "v2.patch.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(L.ModelFault, match="the recipe patch is an object: v2.patch.json"):
        V.recipe_of_module(stub(tmp_path / "list", RECIPE_PATCH="v2.patch.json"))


def test_i1_a_patch_for_a_parent_that_does_not_load_is_a_model_fault(tmp_path):
    with pytest.raises(L.ModelFault, match="coordination/v7 does not load"):
        V.recipe_of_module(stub(tmp_path, patch=dict(patch_of(), parent="coordination/v7"), PARENT="coordination/v7"))


def test_i1_a_module_with_no_recipe_is_a_model_fault(tmp_path):
    with pytest.raises(L.ModelFault, match="coordination/v1 names no recipe"):
        V.recipe_of_module(stub(tmp_path, PARENT=None, VERSION=1))
    with pytest.raises(L.ModelFault, match="coordination/v2 does not load"):
        layers.recipe("coordination/v2")
    with pytest.raises(L.ModelFault, match="there is no folder to read the recipe from"):
        V.recipe_of_module(types.SimpleNamespace(LAYER="coordination", VERSION=2, RECIPE="v2.json"))


def test_i1_roots_recipe_is_the_librarys_template_as_a_copy():
    got = layers.recipe("root/v1")
    assert got == R.engine_templates()["Setup"] and got is not R.engine_templates()["Setup"]
    got["description"] = "changed"
    assert R.engine_templates()["Setup"].get("description") != "changed"


def test_i1_a_v1_recipe_resolves_to_its_file_for_all_six():
    for layer in layers.RECIPE_ORDER:
        assert layers.recipe("%s/v1" % layer) == json.loads((LAYERS / layer / "v1.json").read_text(encoding="utf-8")), layer


# ---- I1 . recipes() -----------------------------------------------------------------------------------------------------
def test_i1_recipes_is_what_it_was_for_the_six_v1():
    got = layers.recipes()
    assert list(got) == ["Identity", "Priority", "Coordination", "Adaptation", "Audit"]
    for layer in layers.RECIPE_ORDER:
        assert got[S.TITLE[layer]] == json.loads((LAYERS / layer / "v1.json").read_text(encoding="utf-8")), layer


def a_tree_with_a_child(tmp_path, monkeypatch, module):
    """layers.HERE pointed at a tree that holds each v1.json and an empty coordination/v2.py, the default pin of Coordination at
    the child, the child in the registry, and coordination/v1 loaded first (the tree has no v1.py to load it from)."""
    layers.load("coordination/v1")
    tree = tmp_path / "tree"
    for layer in layers.RECIPE_ORDER:
        (tree / layer).mkdir(parents=True)
        (tree / layer / "v1.json").write_text((LAYERS / layer / "v1.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tree / "coordination" / "v2.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(layers, "HERE", tree)
    monkeypatch.setitem(S.DEFAULT_PINS, "coordination", "coordination/v2")
    monkeypatch.setitem(layers._LOADED, "coordination/v2", module)


def test_i1_recipes_asks_recipe_for_a_default_pin_that_is_a_patch_child(tmp_path, monkeypatch, child):
    a_tree_with_a_child(tmp_path, monkeypatch, child)
    got = layers.recipes()
    assert list(got) == ["Identity", "Priority", "Coordination", "Adaptation", "Audit"]
    assert [s["id"] for s in born_steps(got["Coordination"])] == ["coord.table", "coord.probe"]
    assert got["Coordination"] == layers.recipe("coordination/v2")
    for layer in ("identity", "priority", "adaptation", "audit"):
        assert got[S.TITLE[layer]] == json.loads((LAYERS / layer / "v1.json").read_text(encoding="utf-8")), layer


def test_i1_recipes_names_a_patch_that_does_not_merge(tmp_path, monkeypatch):
    bad = stub(tmp_path, patch=patch_of({"id": "coord.probe", "name": "Probe", "nature": "transform", "born": "C2",
                                         "code": "coord_ready", "check": "said_what_it_did", "after": "coord.nothing"}))
    a_tree_with_a_child(tmp_path, monkeypatch, bad)
    with pytest.raises(ValueError) as got:
        layers.recipes()
    assert str(got.value) == ("the engine definitions are refused: Coordination's recipe (coordination/v2) does not merge "
                              "(coord.probe: the step it goes after, coord.nothing, is not in the steps of the handler for inform/born)")
    assert not isinstance(got.value, L.ModelFault)


def test_i1_recipes_leaves_the_missing_and_the_not_json_refusals_as_they_were(tmp_path, monkeypatch):
    a_tree_with_a_child(tmp_path, monkeypatch, stub(tmp_path))
    (tmp_path / "tree" / "coordination" / "v2.py").unlink()
    with pytest.raises(ValueError, match="Coordination's recipe .coordination/v2. is missing"):
        layers.recipes()
    (tmp_path / "tree" / "coordination" / "v2.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Coordination's recipe .coordination/v2. is not JSON"):
        layers.recipes()


# ---- I2 . definition_faults and unchanged_steps ------------------------------------------------------------------------
def soft_step(sid, **where):
    """A new step by an agent (born at C0, a prompt and its draft): the kind a unit may hold between its first and its last."""
    return dict({"id": sid, "name": "A soft step", "nature": "decide", "born": "C0", "ceiling": "C2", "prompt": "coord_tie",
                 "draft": "coord_tie_draft", "out": {"answer": "str", "why": "str"}, "answer": "answer",
                 "check": "names_who_goes_first"}, **where)


def code_step(sid, **where):
    return dict({"id": sid, "name": "A step by code", "nature": "transform", "born": "C2", "code": "coord_ready",
                 "check": "said_what_it_did"}, **where)


def passes_the_first_law(child):
    """The resolved recipe of a patch child, after asserting that lineage.recipe_faults has nothing to say of it."""
    merged = V.recipe_of_module(child)
    assert L.recipe_faults(layers.recipe("coordination/v1"), merged, "coordination") == []
    return merged


def test_i2_the_fixture_child_and_each_v1_have_definitions_that_validate(child):
    assert layers.definition_faults("coordination/v2") == []
    assert layers.definition_faults(child) == []
    for layer in S.LAYER_NAMES:
        assert layers.definition_faults("%s/v1" % layer) == [], layer
    assert layers.definition_faults(layers.load("root/v1")) == [], "Root's recipe is the Library's: nothing to swap"


def test_i2_a_soft_step_first_in_a_unit_passes_the_first_law_and_fails_the_definitions(tmp_path):
    child = stub(tmp_path, patch=patch_of(soft_step("coord.pre", before="coord.table")))
    assert [s["id"] for s in born_steps(passes_the_first_law(child))] == ["coord.pre", "coord.table"]
    got = layers.definition_faults(child)
    assert len(got) == 1 and "a unit starts with a step by code; agents come between" in got[0], got
    assert got[0].startswith("Coordination, An engine is born:")


def test_i2_a_soft_step_last_in_a_unit_passes_the_first_law_and_fails_the_definitions(tmp_path):
    child = stub(tmp_path, patch=patch_of(soft_step("coord.post", after="coord.table")))
    assert [s["id"] for s in born_steps(passes_the_first_law(child))] == ["coord.table", "coord.post"]
    got = layers.definition_faults(child)
    assert len(got) == 1 and "a unit ends with a step by code; agents come between" in got[0], got


def test_i2_an_id_another_layer_uses_passes_the_first_law_and_fails_the_definitions(tmp_path):
    taken = L.step_ids(layers.recipe("identity/v1"))[0]
    child = stub(tmp_path, patch=patch_of(code_step(taken, after="coord.table")))
    assert taken in L.step_ids(passes_the_first_law(child))
    assert layers.definition_faults(child) == ["Coordination, %s: the id is used by Identity too" % taken]


def test_i2_a_recipe_that_cannot_be_read_is_the_one_fault(tmp_path):
    assert layers.definition_faults(stub(tmp_path, RECIPE="v2.json")) == ["the recipe is missing: v2.json"]
    assert layers.definition_faults(stub(tmp_path / "x", patch=patch_of({"id": "coord.table", "check": "facts_are_closed"}))) == [
        "coord.table: check is the parent's and a version leaves it as it is; changing what a step is for, how it is judged or "
        "when it runs makes a new step"]
    assert layers.definition_faults("coordination/v9") == ["coordination/v9 does not load"]
    assert layers.definition_faults(stub(tmp_path / "y", LAYER="no-such-layer", RECIPE="v2.json", PARENT=None)) != []


def test_i2_the_names_a_module_brings_are_provided_and_those_it_does_not_are_not(tmp_path):
    v1 = layers.load("coordination/v1")
    own = {"coord_probe": lambda ctx, step, item: {"said": "probe"}}
    child = stub(tmp_path, patch=patch_of(code_step("coord.probe", code="coord_probe", after="coord.table")),
                 CODE=dict(v1.CODE, **own))
    assert layers.definition_faults(child) == [], "its own CODE is provided by default"
    again = layers.definition_faults(child, {"code": set()})
    assert again == ["Coordination, coord.probe: no function named coord_probe ships with the app"], "what is given is what counts"
    assert layers.definition_faults(child, {"code": {"coord_probe"}}) == []
    d = copy.deepcopy(R.defs())
    d["engines"]["Coordination"] = V.recipe_of_module(child)
    assert R.validate(d) == again, "validate(d) with nothing provided is as it always was"
    assert R.validate(d, {"code": {"coord_probe"}}) == []


def test_i2_validate_without_provided_is_unchanged_for_the_definitions_as_they_stand():
    assert R.validate(R.defs()) == [] and R.validate(R.defs(), None) == [] and R.validate(R.defs(), {}) == []
    assert R.validate(R.defs(), {"code": None, "prompt": ()}) == []


def test_i2_unchanged_steps_of_the_fixture_child_is_every_step_of_its_parent_but_the_one_renamed(child):
    parent = set(L.step_ids(layers.recipe("coordination/v1")))
    got = layers.unchanged_steps("coordination/v2")
    assert got == parent - {"coord.table"}
    assert "coord.probe" not in got and "coord.table" not in got and len(parent) > 5


def test_i2_unchanged_steps_of_a_version_with_no_parent_is_nothing():
    for layer in S.LAYER_NAMES:
        assert layers.unchanged_steps("%s/v1" % layer) == set(), layer


def test_i2_unchanged_steps_of_a_lineage_that_cannot_be_read_is_nothing(monkeypatch):
    lineage_of(monkeypatch, {"identity/v2": "identity/v7"})
    assert layers.unchanged_steps("identity/v2") == set()
    assert layers.unchanged_steps("identity/v9") == set()


def test_i2_a_ref_to_made_again_is_unchanged_and_a_body_replaced_is_not(tmp_path, monkeypatch):
    v1 = layers.load("coordination/v1")
    ready_steps = {s["id"] for s in L.all_steps(layers.recipe("coordination/v1")) if s.get("code") == "coord_ready"}
    assert ready_steps == {"coord.ready"}
    everything = set(L.step_ids(layers.recipe("coordination/v1")))

    again = stub(tmp_path, CODE=dict(v1.CODE, coord_ready=layers.ref_to("coord_ready")))
    assert again.CODE["coord_ready"] is not v1.CODE["coord_ready"] and again.CODE["coord_ready"].legacy == v1.CODE["coord_ready"].legacy
    monkeypatch.setitem(layers._LOADED, "coordination/v2", again)
    assert layers.unchanged_steps("coordination/v2") == everything, "a new delegate to the same target is the parent's body"

    replaced = stub(tmp_path / "r", CODE=dict(v1.CODE, coord_ready=lambda ctx, step, item: {"said": "another body"}))
    monkeypatch.setitem(layers._LOADED, "coordination/v2", replaced)
    assert layers.unchanged_steps("coordination/v2") == everything - {"coord.ready"}

    other_target = stub(tmp_path / "t", CODE=dict(v1.CODE, coord_ready=layers.ref_to("coord_record")))
    monkeypatch.setitem(layers._LOADED, "coordination/v2", other_target)
    assert layers.unchanged_steps("coordination/v2") == everything - {"coord.ready"}


def test_i2_a_replaced_prompt_draft_or_check_makes_the_step_that_names_it_changed(tmp_path, monkeypatch):
    v1 = layers.load("coordination/v1")
    everything = set(L.step_ids(layers.recipe("coordination/v1")))
    new_check = lambda ctx, step, item, out: {"ok": True, "notes": []}  # noqa: E731
    cases = (("PROMPT", "coord_tie", {"coord.tie"}), ("DRAFT", "coord_tie_draft", {"coord.tie"}),
             ("CHECK", "names_who_goes_first", {"coord.pick", "coord.tie"}))
    for i, (table, name, steps) in enumerate(cases):
        mine = dict(getattr(v1, table), **{name: new_check})
        monkeypatch.setitem(layers._LOADED, "coordination/v2", stub(tmp_path / str(i), **{table: mine}))
        assert layers.unchanged_steps("coordination/v2") == everything - steps, (table, name)


# ---- I3 . the contract: recipe_of through the patch, cases 9 to 13 ----------------------------------------------------------
NEW_CASES = (C.case_9, C.case_10, C.case_11, C.case_12, C.case_13)


def test_i3_the_contract_lists_thirteen_cases_in_order_and_the_docstring_names_the_new_five():
    numbers = [n for n, _, _ in C.cases()]
    assert numbers[:13] == list(range(1, 14)) and numbers == list(range(1, len(numbers) + 1)), "numbered in order, thirteen at least"
    assert [fn for _, _, fn in C.cases()][8:13] == list(NEW_CASES)
    what = [w for _, w, _ in C.cases()][8:13]
    assert what == ["The lineage is sound.", "The version publishes every surface function its PARENT does.",
                    "The resolved recipe keeps what the parent fixes.", "Every gate or rule the version replaces is declared in TIGHTENS.",
                    "The assembled definitions validate with this version's resolved recipe in its layer's place."]
    for n in range(9, 14):
        assert "\n    %d " % n in C.__doc__, "the module docstring lists case %d" % n


def test_i3_the_new_cases_pass_for_all_six_v1_modules():
    modules = C.discover()
    assert len(modules) == 6
    for module in modules:
        for fn in NEW_CASES:
            assert fn(module, {}) == [], (C.impl_id(module), fn.__name__)


def test_i3_recipe_of_resolves_a_patch_or_an_inherited_recipe_and_leaves_the_rest_as_it_was(tmp_path, child):
    assert C.recipe_of(child) == layers.recipe("coordination/v2") != layers.recipe("coordination/v1")
    assert C.recipe_of(stub(tmp_path / "p", patch=patch_of(code_step("coord.probe", after="coord.table")))) is not None
    assert C.recipe_of(stub(tmp_path / "n")) == layers.recipe("coordination/v1"), "a PARENT and no file: the parent's"
    whole = copy.deepcopy(layers.recipe("coordination/v1"))
    whole["description"] = "a whole file"
    assert C.recipe_of(stub(tmp_path / "w", recipe=whole)) == whole
    assert C.recipe_of(stub(tmp_path / "b", patch=patch_of({"id": "coord.table", "check": "facts_are_closed"}))) is None, "a patch that does not merge"
    for module in C.discover():
        assert C.recipe_of(module) is not None
    assert C.recipe_of(types.SimpleNamespace(LAYER="coordination", VERSION=1)) is None, "no folder, no file"


def test_i3_the_new_cases_tolerate_a_module_with_none_of_the_new_attributes(tmp_path):
    (tmp_path / "coordination").mkdir()
    (tmp_path / "coordination" / "v1.json").write_text(json.dumps(layers.recipe("coordination/v1")), encoding="utf-8")
    plain = types.SimpleNamespace(__file__=str(tmp_path / "coordination" / "v1.py"), LAYER="coordination", VERSION=1, IMPLEMENTS=1,
                                  RECIPE="v1.json", CODE={}, PROMPT={}, DRAFT={}, CHECK={}, WORDS={}, LAYOUT={})
    bare = types.SimpleNamespace(LAYER="coordination", VERSION=1)
    for module in (plain, bare, types.SimpleNamespace()):
        for fn in NEW_CASES:
            assert isinstance(fn(module, {}), list), (fn.__name__, module)
    for fn in NEW_CASES[:4]:
        assert fn(plain, {}) == []


def test_i3_case_9_a_version_above_1_names_the_version_it_extends(tmp_path):
    assert C.case_9(stub(tmp_path, PARENT=None)) == ["coordination/v2: a version above 1 names the version it extends (PARENT)"]
    assert C.case_9(stub(tmp_path / "v1", PARENT=None, VERSION=1)) == []
    assert C.case_9(stub(tmp_path / "x", PARENT="nonsense")) == ["coordination/v2: PARENT 'nonsense' is no implementation id"]
    assert C.case_9(stub(tmp_path / "y", PARENT=["coordination/v1"])) == ["coordination/v2: PARENT ['coordination/v1'] is no implementation id"]
    assert C.case_9(stub(tmp_path / "z")) == []


def test_i3_case_9_a_parent_of_another_layer_one_that_is_not_lower_and_one_that_does_not_load(tmp_path):
    assert C.case_9(stub(tmp_path / "a", PARENT="identity/v1")) == ["coordination/v2: its PARENT identity/v1 is another layer's"]
    assert C.case_9(stub(tmp_path / "b", VERSION=1)) == ["coordination/v1: its PARENT coordination/v1 is not a lower version"]
    assert C.case_9(stub(tmp_path / "c", VERSION=2, PARENT="coordination/v2")) == ["coordination/v2: its PARENT coordination/v2 is not a lower version"]
    assert C.case_9(stub(tmp_path / "d", VERSION=8, PARENT="coordination/v7")) == ["coordination/v8: its PARENT coordination/v7 does not load"]
    both = C.case_9(stub(tmp_path / "e", VERSION=1, PARENT="identity/v1"))
    assert both == ["coordination/v1: its PARENT identity/v1 is another layer's", "coordination/v1: its PARENT identity/v1 is not a lower version"]


def test_i3_case_9_a_lineage_that_repeats_or_runs_too_deep_is_reported_alone(tmp_path, monkeypatch):
    lineage_of(monkeypatch, {"coordination/v2": "coordination/v3", "coordination/v3": "coordination/v2"})
    got = C.case_9(stub(tmp_path / "a", VERSION=4, PARENT="coordination/v3"))
    assert got == ["coordination/v4: the lineage of its PARENT is not sound: coordination/v3 repeats in its own lineage"]
    # the module under test is itself in its parent's lineage (the registry holds another module under its id)
    lineage_of(monkeypatch, {"coordination/v5": "coordination/v6", "coordination/v6": None})
    got = C.case_9(stub(tmp_path / "b", VERSION=6, PARENT="coordination/v5"))
    assert got == ["coordination/v6: it repeats in its own lineage: coordination/v5, coordination/v6"]
    deep = stub(tmp_path / "c", layer="audit", VERSION=10, PARENT="audit/v9")
    lineage_of(monkeypatch, {"audit/v%d" % n: ("audit/v%d" % (n - 1) if n > 1 else None) for n in range(1, 10)})
    got = C.case_9(deep)
    assert got == ["audit/v10: the lineage of its PARENT is not sound: audit/v9: the lineage is deeper than 8 versions"]


@pytest.mark.parametrize("table,key,name", (("CODE", "code", "coord_busy"), ("PROMPT", "prompt", "coord_tie"),
                                            ("DRAFT", "draft", "coord_tie_draft"), ("CHECK", "check", "one_run_at_a_time")))
def test_i3_case_9_a_table_that_drops_a_name_of_its_parent(tmp_path, table, key, name):
    mine = {n: fn for n, fn in getattr(layers.load("coordination/v1"), table).items() if n != name}
    assert C.case_9(stub(tmp_path, **{table: mine})) == ["coordination/v2: it drops the %s %s of its parent" % (key, name)]


def test_i3_case_9_a_words_part_or_a_layout_part_dropped(tmp_path):
    v1 = layers.load("coordination/v1")
    words = {g: dict(parts) for g, parts in v1.WORDS.items()}
    del words["tie"]["tie"]
    assert C.case_9(stub(tmp_path / "w", WORDS=words)) == ["coordination/v2: it drops the words tie.tie of its parent"]
    layout = {g: dict(parts) for g, parts in v1.LAYOUT.items()}
    del layout["goal"]["skills"]
    assert C.case_9(stub(tmp_path / "l", LAYOUT=layout)) == ["coordination/v2: it drops the layout goal.skills of its parent"]
    assert C.case_9(stub(tmp_path / "g", WORDS={})) == ["coordination/v2: it drops the words goal.does of its parent",
                                                        "coordination/v2: it drops the words goal.skills of its parent",
                                                        "coordination/v2: it drops the words tie.tie of its parent"]
    extra = dict(copy.deepcopy(v1.WORDS), more={"part": {"x": "an added part"}})
    assert C.case_9(stub(tmp_path / "e", WORDS=extra)) == [], "a child may add what its parent has not"


def test_i3_case_10_a_version_publishes_every_surface_function_its_parent_does(tmp_path):
    assert C.case_10(stub(tmp_path / "ok")) == []
    assert C.case_10(stub(tmp_path / "a", view=None)) == ["coordination/v2: it does not publish view, which its parent does"]
    assert C.case_10(stub(tmp_path / "b", view="a pane", engine_card=None)) == [
        "coordination/v2: it does not publish view, which its parent does",
        "coordination/v2: it does not publish engine_card, which its parent does"]
    top = stub(tmp_path / "r", layer="root", apply_option=None, standards=None)
    assert C.case_10(top) == ["root/v2: it does not publish apply_option, which its parent does",
                              "root/v2: it does not publish standards, which its parent does"]
    assert C.case_10(stub(tmp_path / "n", PARENT=None, VERSION=1, view=None)) == [], "no parent: nothing to publish"
    assert C.case_10(stub(tmp_path / "m", PARENT="coordination/v9", view=None)) == [], "a parent that does not load is case 9's"


def whole(tmp_path, sub, edit, layer="coordination"):
    """A whole-file child of layers/<layer>/v1 whose recipe is the parent's after `edit(recipe)`."""
    rec = copy.deepcopy(layers.recipe("%s/v1" % layer))
    edit(rec)
    return stub(tmp_path / sub, recipe=rec, layer=layer)


def test_i3_case_11_a_whole_file_child_that_keeps_what_the_parent_fixes_passes(tmp_path, child):
    assert C.case_11(child) == []
    assert C.case_11(whole(tmp_path, "same", lambda rec: None)) == []
    assert C.case_11(whole(tmp_path, "free", lambda rec: born_steps(rec)[0].update(name="Another name", born="C2"))) == []
    assert C.case_11(whole(tmp_path, "added", lambda rec: born_steps(rec).append(code_step("coord.added")))) == []


def test_i3_case_11_a_dropped_handler(tmp_path):
    got = C.case_11(whole(tmp_path, "h", lambda rec: rec.update(on=rec["on"][:-1])))
    assert got == ["coordination/v2: the handler for inform/born is gone: a version hears what its parent hears",
                   "coordination/v2: coord.table: a version keeps every step of its parent, and this one is gone"]


def test_i3_case_11_a_changed_check_on_a_rule_a_dropped_gate_and_a_dropped_rule(tmp_path):
    got = C.case_11(whole(tmp_path, "c", lambda rec: rec["rules"][0].update(check="said_what_it_did")))
    assert got == ["coordination/v2: coord.busy: check is the parent's and a version leaves it as it is"]
    got = C.case_11(whole(tmp_path, "g", lambda rec: rec.update(gates=[])))
    assert got == ["coordination/v2: coord.chain: a version keeps every gate and rule of its parent, and this one is gone"]
    got = C.case_11(whole(tmp_path, "r", lambda rec: rec.update(rules=rec["rules"][1:])))
    assert got == ["coordination/v2: coord.busy: a version keeps every gate and rule of its parent, and this one is gone"]
    got = C.case_11(whole(tmp_path, "m", lambda rec: rec["steps"][0].update(nature="decide")))
    assert got == ["coordination/v2: coord.ready: nature is the parent's and a version leaves it as it is"]


def test_i3_case_11_a_changed_enum(tmp_path):
    def drop_a_member(rec):
        next(s for s in L.all_steps(rec) if s["id"] == "priority.bargain")["out"]["answer"] = ["accept", "reject"]

    steps = L.step_ids(layers.recipe("priority/v1"))
    assert "priority.bargain" in steps
    got = C.case_11(whole(tmp_path, "e", drop_a_member, layer="priority"))
    assert got == ["priority/v2: priority.bargain: out.answer has other values than the parent's: an enum keeps the same members"]


def test_i3_case_11_a_dangling_only_if_and_an_id_used_twice(tmp_path):
    got = C.case_11(whole(tmp_path, "o", lambda rec: rec["steps"].append(code_step("coord.late", only_if="coord.nothing.answer=yes"))))
    assert got == ["coordination/v2: coord.late: only_if points at coord.nothing, which is no step of this recipe"]
    got = C.case_11(whole(tmp_path, "d", lambda rec: rec["steps"].append(code_step("coord.ready"))))
    assert got == ["coordination/v2: coord.ready: this id is used by more than one step"]


def test_i3_case_11_a_version_with_no_parent_is_judged_alone_and_a_recipe_that_cannot_be_read_is_case_1s(tmp_path):
    alone = stub(tmp_path / "a", recipe=dict(layers.recipe("coordination/v1"), steps=[code_step("coord.x"), code_step("coord.x")]),
                 PARENT=None, VERSION=1)
    assert C.case_11(alone) == ["coordination/v1: coord.x: this id is used by more than one step"]
    unreadable = stub(tmp_path / "b", RECIPE="nothing.json")
    assert C.case_11(unreadable) == [] and C.case_1(unreadable)[-1] == "coordination/v2: its recipe nothing.json is not there"


def test_i3_case_12_a_replaced_gate_or_rule_is_declared_in_tightens(tmp_path):
    v1 = layers.load("coordination/v1")
    stricter = dict(v1.CODE, coord_chain=coord_chain_one_sooner)
    assert C.case_12(stub(tmp_path / "a", CODE=stricter)) == ["coordination/v2: it replaces the code of coord.chain and does not list it in TIGHTENS"]
    other_check = dict(v1.CHECK, one_run_at_a_time=lambda ctx, step, item, out: {"ok": True, "notes": []})
    assert C.case_12(stub(tmp_path / "b", CHECK=other_check)) == [
        "coordination/v2: it replaces the check of coord.busy and does not list it in TIGHTENS"]
    elsewhere = dict(v1.CODE, coord_ready=lambda ctx, step, item: {})
    assert C.case_12(stub(tmp_path / "c", CODE=elsewhere)) == [], "a step that is no gate or rule is not tightened"
    again = dict(v1.CODE, coord_chain=layers.ref_to("coord_chain"))
    assert C.case_12(stub(tmp_path / "d", CODE=again)) == [], "a ref_to to the same target is the parent's body"
    assert C.case_12(stub(tmp_path / "e")) == []


def test_i3_case_12_a_replacement_declared_with_a_test_that_exists_passes(tmp_path):
    where = "test_layer_inherit.py::test_a_child_that_stops_a_chain_one_run_sooner_lets_through_nothing_its_parent_held_back"
    v1 = layers.load("coordination/v1")
    child = stub(tmp_path, CODE=dict(v1.CODE, coord_chain=coord_chain_one_sooner), TIGHTENS={"coord.chain": where})
    assert C.case_12(child) == []
    assert C.case_12(stub(tmp_path / "also", CODE=dict(v1.CODE, coord_chain=coord_chain_one_sooner),
                          TIGHTENS={"coord.chain": where, "coord.busy": where})) == [], "a declared step need not be replaced"


def test_i3_case_12_a_tightens_that_names_a_test_that_is_not_there(tmp_path):
    v1 = layers.load("coordination/v1")
    mine = dict(v1.CODE, coord_chain=coord_chain_one_sooner)
    outside = tmp_path / "outside.py"
    outside.write_text("def test_outside():\n    pass\n", encoding="utf-8")
    for where in ("test_nothing.py::test_nope", "test_layer_inherit.py::test_nope", "test_layer_inherit.py", "no colons at all",
                  "test_layer_inherit.py::", "::test_nope", "test_layer_inherit.py::test_i3_case_12_a_tightens", None,
                  "%s::test_outside" % outside, "../outside.py::test_outside"):
        got = C.case_12(stub(tmp_path, CODE=mine, TIGHTENS={"coord.chain": where}))
        assert got == ["coordination/v2: TIGHTENS coord.chain names a test that is not there: %s" % where], where


def test_i3_case_12_a_tightens_that_names_a_step_that_is_no_gate_or_rule(tmp_path):
    where = "test_layer_inherit.py::test_i3_case_12_a_replaced_gate_or_rule_is_declared_in_tightens"
    got = C.case_12(stub(tmp_path / "a", TIGHTENS={"coord.ready": where}))
    assert got == ["coordination/v2: TIGHTENS names coord.ready, which is no gate or rule of its recipe"]
    got = C.case_12(stub(tmp_path / "b", TIGHTENS={"coord.nothing": "test_nothing.py::test_nope"}))
    assert got == ["coordination/v2: TIGHTENS names coord.nothing, which is no gate or rule of its recipe",
                   "coordination/v2: TIGHTENS coord.nothing names a test that is not there: test_nothing.py::test_nope"]


def test_i3_case_12_a_tightens_on_a_version_with_no_parent_or_not_a_dict(tmp_path):
    where = "test_layer_inherit.py::test_i3_case_12_a_replaced_gate_or_rule_is_declared_in_tightens"
    one = stub(tmp_path / "a", PARENT=None, VERSION=1, TIGHTENS={"coord.chain": where, "coord.busy": where})
    assert C.case_12(one) == ["coordination/v1: TIGHTENS names coord.busy, coord.chain, and there is no parent to tighten"]
    assert C.case_12(stub(tmp_path / "b", PARENT=None, VERSION=1, TIGHTENS={})) == []
    assert C.case_12(stub(tmp_path / "c", TIGHTENS=[where])) == ["coordination/v2: TIGHTENS is a dict of a step id and the test that proves it"]


def test_i3_case_13_the_definitions_must_validate_with_the_versions_recipe(tmp_path, child):
    assert C.case_13(child) == []
    first = stub(tmp_path / "f", patch=patch_of(soft_step("coord.pre", before="coord.table")))
    got = C.case_13(first)
    assert len(got) == 1 and got[0].startswith("coordination/v2: Coordination, An engine is born: a unit starts with a step by code"), got
    unreadable = stub(tmp_path / "u", RECIPE="nothing.json")
    assert C.case_13(unreadable) == ["coordination/v2: the recipe is missing: nothing.json"]


def coord_chain_one_sooner(ctx, step, item):
    """A replacement of Coordination's gate for the tests of case 12: it stops a chain one run before the limit, where version 1
    stops it at the limit. It reads what version 1's body reads, through the same two functions of the department."""
    chain = website_dept._chain_of(ctx["ref"], ctx["def"]["reads"], ctx["inp"]["v"])
    if chain and sum(1 for r in website_dept.runs(ctx["ref"]) if r.get("chain") == chain) >= website_dept.CHAIN_LIMIT - 1:
        return "wait", "the chain from %s is one run from its limit" % chain
    return "admit", None


def test_a_child_that_stops_a_chain_one_run_sooner_lets_through_nothing_its_parent_held_back(monkeypatch):
    """The proof case 12 asks of a replaced gate (A2-R6): on every count of runs in a chain, from none to past the limit, the child
    answers at least as strictly as version 1; and the check is not vacuous, for the parent against the child fails where the child
    holds back the one run the parent lets through."""
    counts = {}
    monkeypatch.setattr(website_dept, "_chain_of", lambda ref, reads, v: "chain-a")
    monkeypatch.setattr(website_dept, "runs", lambda ref: [{"chain": "chain-a"}] * counts[ref])
    contexts = []
    for n in range(website_dept.CHAIN_LIMIT + 3):
        counts["ref-%d" % n] = n
        contexts.append(({"ref": "ref-%d" % n, "def": {"reads": "x"}, "inp": {"v": 1}}, None, None))
    parent = layers.load("coordination/v1").CODE["coord_chain"]
    assert {parent(*c)[0] for c in contexts} == {"admit", "wait"}, "the contexts reach both answers"
    assert L.tightens(parent, coord_chain_one_sooner, contexts) == []
    assert L.tightens(coord_chain_one_sooner, parent, contexts) == [
        "context %d: the child answers admit where its parent answers wait" % (website_dept.CHAIN_LIMIT - 1)]


# ---- I4 . the fixture child, end to end ---------------------------------------------------------------------------------------
@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """The contract fixture department, as test_layer_contracts.py makes it."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return {"ref": C.fixture_department(tmp_path / "departments")}


PROBE = {"id": "coord.probe", "name": "Probe", "nature": "transform", "born": "C2", "code": "coord_probe", "check": "said_what_it_did"}
TIE_TASK = "Several functions are ready, and one runs at a time. Say who goes first (version 2)."


def test_i4_the_fixture_child_is_a_version_of_coordination_that_lives_outside_layers(child):
    assert (child.LAYER, child.VERSION, child.IMPLEMENTS, child.PARENT) == ("coordination", 2, S.SCHEMA_VERSION, "coordination/v1")
    assert child.RECIPE_PATCH == "v2.patch.json" and not hasattr(child, "RECIPE")
    assert layers.load("coordination/v2") is child and C.impl_id(child) == "coordination/v2"
    assert Path(child.__file__) == FIXTURE / "coordination" / "v2.py" and not (LAYERS / "coordination" / "v2.py").exists()
    assert child.coord_probe({}, {}, None) == {"said": "probe"}


def test_i4_the_fixture_child_passes_the_contract_cases_1_to_13(child, ctx):
    assert len(C.cases()) >= 13
    for number, what, fn in C.cases():
        assert fn(child, ctx) == [], "case %d: %s" % (number, what)


def test_i4_a_pinned_child_serves_its_own_body_and_its_parents_for_the_rest(child, monkeypatch):
    v1 = layers.load("coordination/v1")
    monkeypatch.setitem(S.DEFAULT_PINS, "coordination", "coordination/v2")
    assert layers.impl(None, "coordination") is child and layers.pins(None)["coordination"] == "coordination/v2"
    probe = layers.resolve(None, "Coordination", "code", "coord_probe", R.CODE)
    assert probe is child.CODE["coord_probe"] and probe is child.coord_probe
    busy = layers.resolve(None, "Coordination", "code", "coord_busy", R.CODE)
    assert busy is v1.CODE["coord_busy"] and busy is child.CODE["coord_busy"], "the very callable coordination/v1 holds"
    assert layers.resolve(None, "Coordination", "check", "said_what_it_did", R.CHECK) is v1.CHECK["said_what_it_did"]
    assert layers.impl(None, "identity") is layers.load("identity/v1"), "the other layers run their own"


def test_i4_the_childs_published_tables_are_what_the_registry_reads(child, monkeypatch):
    monkeypatch.setitem(S.DEFAULT_PINS, "coordination", "coordination/v2")
    other = lambda ctx, step, item: {"said": "another probe"}  # noqa: E731
    monkeypatch.setitem(child.CODE, "coord_probe", other)
    assert layers.resolve(None, "Coordination", "code", "coord_probe", R.CODE) is other
    monkeypatch.setitem(child.CODE, "coord_busy", other)
    assert layers.resolve(None, "Coordination", "code", "coord_busy", R.CODE) is other
    assert layers.load("coordination/v1").CODE["coord_busy"] is not other, "the parent's table is the parent's"


def test_i4_a_pinned_child_is_viewed_through_its_parents_view(child, ctx, monkeypatch):
    v1 = layers.load("coordination/v1")
    ref = ctx["ref"]
    d, asks = layers.W.dept(ref), layers.W.asks(ref)
    monkeypatch.setitem(S.DEFAULT_PINS, "coordination", "coordination/v2")
    assert child.view is v1.view and child.engine_card is v1.engine_card
    assert layers.view(ref, "coordination", d, [], asks) == v1.view(ref, d, [], asks)


def test_i4_the_childs_recipe_is_its_parents_with_the_probe_added_and_the_table_step_renamed(child):
    expected = copy.deepcopy(layers.recipe("coordination/v1"))
    expected["description"] = "Coordination, version 2 (a fixture): version 1 and one probe step."
    born_steps(expected)[0]["name"] = "Write the table, version 2"
    born_steps(expected).append(copy.deepcopy(PROBE))
    got = layers.recipe("coordination/v2")
    assert got == expected
    parent_ids = L.step_ids(layers.recipe("coordination/v1"))
    assert L.step_ids(got) == parent_ids + ["coord.probe"], "every step of version 1, and the probe after coord.table"
    assert [s["id"] for s in born_steps(got)] == ["coord.table", "coord.probe"]
    assert layers.chain("coordination/v2") == ["coordination/v2", "coordination/v1"]
    assert L.recipe_faults(layers.recipe("coordination/v1"), got, "coordination") == []


def test_i4_the_words_overlay_reaches_one_field_and_every_other_part_is_the_parents(child, monkeypatch):
    v1 = layers.load("coordination/v1")
    assert v1.WORDS["tie"]["tie"]["task"] != TIE_TASK
    monkeypatch.setitem(S.DEFAULT_PINS, "coordination", "coordination/v2")
    assert layers.words(None, "coordination", "tie", "tie")["task"] == TIE_TASK
    for group, parts in v1.WORDS.items():
        for part, fields in parts.items():
            got = layers.words(None, "coordination", group, part)
            if (group, part) == ("tie", "tie"):
                assert {k: v for k, v in got.items() if k != "task"} == {k: v for k, v in fields.items() if k != "task"}
            else:
                assert got == fields, (group, part)
    assert child.LAYOUT == v1.LAYOUT, "no layout was given, so the parent's arranges the new words"
    text = layers.prompt(None, "coordination", "tie", "tie", **layers.prompts.sample_inputs("coordination", "tie", "tie"))
    assert TIE_TASK in text and v1.WORDS["tie"]["tie"]["task"] not in text


def test_i4_the_definitions_assembled_with_the_child_in_coordinations_place_validate(child):
    assert layers.definition_faults(child) == [] and layers.definition_faults("coordination/v2") == []
    d = copy.deepcopy(R.defs())
    d["engines"]["Coordination"] = layers.recipe("coordination/v2")
    assert R.validate(d) == ["Coordination, coord.probe: no function named coord_probe ships with the app"], \
        "the child is not on disk under layers/, so its names are not the registry's until a caller says it brings them"
    assert R.validate(d, {"code": set(child.CODE)}) == []
    assert R.validate(R.defs()) == [], "and the definitions the department runs are untouched"


def test_i4_the_fixture_changes_nothing_the_registry_lists(monkeypatch):
    before = (layers.available(), {k: layers.names(k) for k in layers.KINDS})
    load_fixture(monkeypatch)
    after = (layers.available(), {k: layers.names(k) for k in layers.KINDS})
    assert before == after and "coord_probe" not in after[1]["code"]
    assert [C.impl_id(m) for m in C.discover()] == [S.DEFAULT_PINS[layer] for layer in S.LAYER_NAMES]


FORBIDDEN_AT_IMPORT = ("engine_runtime", "website_dept", "j2_runtime", "functions_view", "layer_schema")


def imports_at_import_time(tree):
    """The imports that run when a module is imported: its own, and those under an if, a try or a class; not those in a function."""
    found = []

    def walk(node):
        for child_node in ast.iter_child_nodes(node):
            if isinstance(child_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child_node, (ast.Import, ast.ImportFrom)):
                found.append(child_node)
            else:
                walk(child_node)

    walk(tree)
    return found


def runtime_names(node):
    if isinstance(node, ast.Import):
        return [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_AT_IMPORT]
    named = [node.module] if node.module and node.module.split(".")[0] in FORBIDDEN_AT_IMPORT else []
    return named + [a.name for a in node.names if a.name in FORBIDDEN_AT_IMPORT]


def test_i4_versions_and_the_contract_import_nothing_from_the_runtime_at_import_time():
    for name in ("versions.py", "contract.py"):
        top = imports_at_import_time(ast.parse((LAYERS / name).read_text(encoding="utf-8")))
        assert top, "the scan found no import in layers/%s" % name
        assert not [n for n in top if runtime_names(n)], "layers/%s imports the runtime when it is imported" % name
    versions = imports_at_import_time(ast.parse((LAYERS / "versions.py").read_text(encoding="utf-8")))
    assert {a.name for n in versions if isinstance(n, ast.ImportFrom) and n.module == "layers" for a in n.names} == {"R", "S", "lineage"}
    # the five wrappers import layers.versions when called, so the package itself holds none of it at import time
    package = imports_at_import_time(ast.parse((LAYERS / "__init__.py").read_text(encoding="utf-8")))
    assert not [n for n in package if runtime_names(n) or "versions" in [a.name for a in n.names] or getattr(n, "module", "") == "layers.versions"]


def test_i4_versions_and_the_contract_import_without_the_runtime_present():
    code = ("import sys; sys.path.insert(0, %r)\n"
            "for m in %r: sys.modules[m] = None\n"
            "import layers.versions, layers.contract\n"
            "assert layers.versions.DEPTH == 8 and layers.contract.cases()[12][0] == 13\n"
            "print('ok')\n" % (str(HERE), list(FORBIDDEN_AT_IMPORT)))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(HERE), timeout=60)
    assert done.returncode == 0 and done.stdout.strip() == "ok", done.stderr[-2000:]
