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
import copy
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

import layers
import layer_schema as S
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


def stub(tmp_path, recipe=None, patch=None, **more):
    """A child of coordination/v1 as a SimpleNamespace: the tables copied from the parent, its folder in tmp_path, and the recipe
    (a whole file) or the patch it is given written beside it. `more` overrides any attribute."""
    v1 = layers.load("coordination/v1")
    folder = tmp_path / "coordination"
    folder.mkdir(parents=True, exist_ok=True)
    base = dict(__file__=str(folder / "v2.py"), LAYER="coordination", VERSION=2, IMPLEMENTS=1, PARENT="coordination/v1",
                CODE=dict(v1.CODE), PROMPT=dict(v1.PROMPT), DRAFT=dict(v1.DRAFT), CHECK=dict(v1.CHECK),
                WORDS=copy.deepcopy(v1.WORDS), LAYOUT=copy.deepcopy(v1.LAYOUT), view=v1.view, engine_card=v1.engine_card)
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
