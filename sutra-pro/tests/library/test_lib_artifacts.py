"""The artifact models (library design 9.3; WP L7): the 19 section models and the PRD, HLD and LLD documents, ported from J2's
j2_artifact_models (baseline 33aeeda) as strict, frozen, bounded `Value`s.

The parity data is tests/library/fixtures/artifacts/cases.json, made ONCE by build_artifact_cases.py from J2's own code: the
good payloads, J2's schema shas for the 19 sections and 3 documents (transport and whole reply), and J2's render output.
Declared differences from J2, each tested below: strict types (`required: "true"` is refused), a closed frozen object, bounds
on every string and list."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.library import artifacts as A
from sutra_app.library.artifacts import models as M
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.registry import REGISTRY, is_transport_safe, reply_schema, schema_sha, transport_schema

CASES = json.loads((Path(__file__).parent / "fixtures" / "artifacts" / "cases.json").read_text(encoding="utf-8"))
GOOD = CASES["good"]
SECTIONS = [(kind, section) for kind, by in A.SECTION_MODELS.items() for section in by]
IDS = [f"{k}/{s}" for k, s in SECTIONS]


def problems(model, data) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        model.model_validate(data)
    return [(".".join(str(p) for p in e["loc"]), e["type"]) for e in error.value.errors()]


def with_(data, *path_and_value):
    """A deep copy of `data` with the value at the path replaced (the last argument is the value)."""
    *path, value = path_and_value
    out = json.loads(json.dumps(data))
    node = out
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    return out


# ---------------------------------------------------------------- the sections and documents accept J2's payloads
def test_there_are_19_sections_and_5_document_models():
    assert len(SECTIONS) == 19
    assert {k: len(v) for k, v in A.SECTION_MODELS.items()} == {"prd": 6, "hld": 6, "lld": 5, "design": 1, "website": 1}
    assert set(A.DOC_MODELS) == {"prd", "hld", "lld", "design", "website"}
    assert A.DOC_MODELS["design"] is A.SECTION_MODELS["design"]["Style guide"]
    assert A.DOC_MODELS["website"] is A.SECTION_MODELS["website"]["Section"]


@pytest.mark.parametrize("kind,section", SECTIONS, ids=IDS)
def test_a_section_accepts_the_j2_payload(kind, section):
    model = A.SECTION_MODELS[kind][section]
    obj = model.model_validate(GOOD[f"{kind}/{section}"])
    assert isinstance(obj, M.Artifact)
    assert A.render.validate(model, A.normalise(model, GOOD[f"{kind}/{section}"])) == (obj, [])


@pytest.mark.parametrize("kind", ["prd", "hld", "lld"])
def test_a_document_accepts_the_j2_document(kind):
    doc = A.DOC_MODELS[kind].model_validate(CASES["docs"][kind])
    assert doc.model_dump(by_alias=True, exclude_defaults=False)["assumptions"] == CASES["docs"][kind]["assumptions"]


def test_a_document_may_hold_only_what_it_has():
    assert M.PRD.model_validate({"problem": {"statement": "x"}}).users == []
    assert M.HLD.model_validate({}).hosting is None
    assert M.LLD.model_validate({}).files == []


# ---------------------------------------------------------------- what is refused (the table of library design section 14)
def test_a_string_where_a_flag_is_needed_is_refused():
    """J2 coerced "true" to True; the library is strict."""
    bad = with_(GOOD["lld/Form fields"], "form_fields", 0, "required", "true")
    assert problems(A.SECTION_MODELS["lld"]["Form fields"], bad) == [("form_fields.0.required", "bool_type")]


def test_a_key_the_model_does_not_declare_is_refused_at_any_depth():
    model = A.SECTION_MODELS["prd"]["Goals"]
    assert problems(model, {**GOOD["prd/Goals"], "extra": 1}) == [("extra", "extra_forbidden")]
    assert problems(model, with_(GOOD["prd/Goals"], "goals", 0, "colour", "red")) == [("goals.0.colour", "extra_forbidden")]


def test_a_website_section_needs_html_or_head():
    model = A.SECTION_MODELS["website"]["Section"]
    bad = {"id": "S1", "html": "  ", "head": ""}
    with pytest.raises(ValidationError, match="a section must have html, or head tags when it writes only those"):
        model.model_validate(bad)
    assert problems(model, bad) == [("", "value_error")]
    assert model.model_validate({"id": "S1", "head": "<meta name=\"a\">"}).html == ""


def test_a_string_where_a_list_is_needed_is_refused():
    model = A.SECTION_MODELS["prd"]["Requirements"]
    assert problems(model, with_(GOOD["prd/Requirements"], "requirements", 0, "goals", "G1")) == [
        ("requirements.0.goals", "list_type")]


def test_the_enums_are_shape_and_the_rules_are_not():
    """An unknown priority or field type is refused by the model; an id out of order is not (that is a rule)."""
    assert problems(A.SECTION_MODELS["prd"]["Requirements"],
                    with_(GOOD["prd/Requirements"], "requirements", 0, "priority", "urgent")) == [
        ("requirements.0.priority", "literal_error")]
    assert problems(A.SECTION_MODELS["lld"]["Form fields"],
                    with_(GOOD["lld/Form fields"], "form_fields", 0, "type", "color")) == [("form_fields.0.type", "literal_error")]
    A.SECTION_MODELS["prd"]["Goals"].model_validate(with_(GOOD["prd/Goals"], "goals", 0, "id", "G7"))


def test_a_required_field_that_is_missing_is_named():
    assert problems(A.SECTION_MODELS["prd"]["Problem"], {}) == [("statement", "missing")]
    assert problems(A.SECTION_MODELS["design"]["Style guide"], {k: v for k, v in GOOD["design/Style guide"].items() if k != "card"}) == [
        ("card", "missing")]


def test_the_wire_key_from_is_read_by_alias_and_written_back():
    flow = A.SECTION_MODELS["hld"]["Data flow"].model_validate(GOOD["hld/Data flow"])
    assert flow.data_flows[0].from_ == "visitor"
    assert flow.model_dump()["data_flows"][0]["from"] == "visitor"
    by_name = M.DataFlow.model_validate({"from_": "a", "to": "b", "data": "c", "trigger": "d"})
    assert by_name.from_ == "a"


def test_an_artifact_is_frozen_and_text_is_stripped():
    goal = M.Goal.model_validate({"id": " G1 ", "statement": "x"})
    assert goal.id == "G1"
    with pytest.raises(ValidationError):
        goal.id = "G2"
    assert goal.evolve(statement="y").statement == "y"
    with pytest.raises(ValidationError):
        goal.evolve(id=5)


def test_a_list_or_text_over_its_bound_is_refused():
    assert problems(M.Goal, {"id": "G" * 41, "statement": "x"}) == [("id", "string_too_long")]
    assert problems(A.SECTION_MODELS["prd"]["Out of scope"], {"out_of_scope": ["x"] * 201}) == [("out_of_scope", "too_long")]
    assert problems(A.SECTION_MODELS["website"]["Section"], {"id": "S1", "html": "x" * 200_001}) == [("html", "string_too_long")]


# ---------------------------------------------------------------- schemas: J2's shas, byte for byte
@pytest.mark.parametrize("kind,section", SECTIONS, ids=IDS)
def test_the_transport_schema_of_a_section_is_j2s(kind, section):
    model = A.SECTION_MODELS[kind][section]
    schema = transport_schema(model)
    assert schema_sha(schema) == CASES["transport_sha"][f"{kind}/{section}"]
    assert schema_sha(reply_schema(model, {})) == CASES["reply_sha"][f"{kind}/{section}"]
    assert is_transport_safe(schema) == []


@pytest.mark.parametrize("kind", ["prd", "hld", "lld"])
def test_the_transport_schema_of_a_document_is_j2s(kind):
    schema = transport_schema(A.DOC_MODELS[kind])
    assert schema_sha(schema) == CASES["transport_sha"][f"doc/{kind}"]
    assert schema_sha(reply_schema(A.DOC_MODELS[kind], {})) == CASES["reply_sha"][f"doc/{kind}"]


def test_the_optional_set_is_set_once_on_the_base_class_and_every_class_inherits_it():
    assert M.Artifact.TRANSPORT_OPTIONAL == frozenset(M.OPTIONAL_FIELDS)
    assert "assumptions" in M.OPTIONAL_FIELDS and len(M.OPTIONAL_FIELDS) == 23
    classes = [c for c in vars(M).values() if isinstance(c, type) and issubclass(c, M.Artifact)]
    assert len(classes) == 40            # the base, 22 section and document classes, and the parts nested in them
    assert all(c.TRANSPORT_OPTIONAL is M.Artifact.TRANSPORT_OPTIONAL for c in classes)


def test_a_nested_part_keeps_its_own_required_fields_in_the_transport_schema():
    schema = transport_schema(A.SECTION_MODELS["prd"]["Requirements"])
    item = schema["definitions"]["Requirement"]
    assert item["required"] == ["id", "statement", "priority"]       # `goals` is optional, the rest is required
    assert schema["required"] == ["requirements"]                    # `assumptions` is optional


def test_the_one_value_literals_stay_constraints_in_the_transport_schema():
    """The L1 change to J2: `const` is kept as a one-value enum. No artifact model has one, so the shas still match."""
    for kind, section in SECTIONS:
        assert "const" not in json.dumps(transport_schema(A.SECTION_MODELS[kind][section]))


# ---------------------------------------------------------------- the registry
def test_the_registry_of_sections_and_conditions_agree():
    assert {k: list(v) for k, v in A.SECTION_CONDITIONS.items()} == {k: list(v) for k, v in A.SECTION_MODELS.items()}
    assert A.SECTION_CONDITIONS["hld"]["Components"] == ["H1", "H3", "H4"]
    assert A.SECTION_CONDITIONS["website"]["Section"] == ["N1", "N4", "N8"]


def test_model_for_finds_a_model_by_name_loosely():
    assert A.model_for("prd", "Problem") is M.PRDProblem
    assert A.model_for("prd", "success  METRICS") is M.PRDSuccessMetrics
    assert A.model_for("lld", "responsive-and-accessibility rules") is M.LLDRules
    assert A.model_for("hld", "Nothing like it") is None
    assert A.model_for("nothing", "Problem") is None
    assert A.model_for(None, None) is None
    # design and website have one model each: any section name finds it
    assert A.model_for("design", "whatever") is M.Design
    assert A.model_for("website", "") is M.WebsiteSection


def test_the_model_names_are_the_templates_the_records_show():
    assert M.PRDProblem.template() == "PRD/1 · Problem"
    assert M.Design.template() == "Design/1 · Style guide"
    assert M.WebsiteSection.template() == "WebsiteSection/1 · Section"
    assert M.Goal.template() == "artifact/1"


def test_slug_and_payload_name():
    assert A.slug("Hosting and deployment") == "hosting-and-deployment"
    assert A.slug("  --  ") == "template" and A.slug(None) == "template"
    assert A.payload_name("prd", "Success metrics") == "artifact.prd.success-metrics"
    assert A.payload_name("hld") == "artifact.hld"


def test_all_22_payloads_are_registered_with_their_rules():
    names = {f for f in REGISTRY.families() if f.startswith("artifact.")}
    assert len(names) == 22
    for kind, section in SECTIONS:
        name = A.payload_name(kind, section)
        assert REGISTRY.is_payload(name) and REGISTRY.versions(name) == [1]
        assert REGISTRY.kinds(name) == {name: A.SECTION_MODELS[kind][section]}
        assert list(REGISTRY.rules(name)) == A.RULES[(kind, section)]
    for kind in ("prd", "hld", "lld"):
        assert REGISTRY.kinds(A.payload_name(kind)) == {A.payload_name(kind): A.DOC_MODELS[kind]}
        assert REGISTRY.rules(A.payload_name(kind)) == ()
    assert "artifact.design" not in names and "artifact.website" not in names     # their documents are their sections


def test_the_registered_json_schemas_and_transport_schemas_build():
    for kind, section in SECTIONS:
        name = A.payload_name(kind, section)
        assert REGISTRY.json_schema(name)["type"] == "object"
        assert REGISTRY.transport_schema(name) == transport_schema(A.SECTION_MODELS[kind][section])


@pytest.mark.parametrize("kind,section", SECTIONS, ids=IDS)
def test_every_string_and_list_is_bounded_and_no_alias_is_odd(kind, section):
    model = A.SECTION_MODELS[kind][section]
    assert unbounded_fields(model) == []
    assert aliased_fields(model) == []


@pytest.mark.parametrize("kind", ["prd", "hld", "lld"])
def test_the_documents_are_bounded_too(kind):
    assert unbounded_fields(A.DOC_MODELS[kind]) == []


# ---------------------------------------------------------------- rendering: code writes the document
@pytest.mark.parametrize("key", sorted(CASES["render"]))
def test_render_section_equals_j2s(key):
    kind, section = key.split("/", 1)
    model = A.SECTION_MODELS[kind][section]
    data = model.model_validate(GOOD[key]).model_dump(by_alias=True)
    assert A.render_section(kind, section, data) == CASES["render"][key]
    assert A.render_section(kind, section, GOOD[key]) == CASES["render"][key]


def test_render_section_says_none_for_what_it_does_not_render():
    assert A.render_section("design", "Style guide", GOOD["design/Style guide"]) is None
    assert A.render_section("prd", "Nothing", {}) is None
    assert A.render_section("prd", "Problem", None) == "## Problem\n\n\n"


def test_the_users_section_names_a_group_without_actions():
    text = A.render_section("prd", "Users", GOOD["prd/Users"])
    assert "Regulars have no actions in this version." in text
    assert "- newcomers: a gentle first class; they book a trial class." in text


def test_a_data_flow_renders_from_either_spelling_of_from():
    flow = {"to": "b", "data": "c", "trigger": "d"}
    assert A.render_section("hld", "Data flow", {"data_flows": [{**flow, "from": "a"}]}) == \
        A.render_section("hld", "Data flow", {"data_flows": [{**flow, "from_": "a"}]})


def test_style_from_design_keeps_the_keys_the_style_guide_has():
    assert A.style_from_design(GOOD["design/Style guide"]) == CASES["style"]
    assert A.style_from_design(None)["fonts"] == {"heading": None, "body": None, "google_fonts_url": None}


def test_normalise_writes_enum_words_in_the_models_casing_and_leaves_the_input_alone():
    source = json.loads(json.dumps(CASES["normalise"]["in"]))
    assert A.normalise(None, source) == CASES["normalise"]["out"]
    assert source == CASES["normalise"]["in"]
    assert A.normalise(None, "text") == "text" and A.normalise(None, [1]) == [1]


def test_validate_and_errors_of_word_the_errors_for_a_retry():
    model = A.SECTION_MODELS["prd"]["Requirements"]
    bad = with_(GOOD["prd/Requirements"], "requirements", 0, "priority", "urgent")
    obj, errors = A.validate(model, bad)
    assert obj is None and errors == ["requirements.0.priority: Input should be 'must', 'should' or 'could'"]
    assert A.validate(model, A.normalise(model, with_(bad, "requirements", 0, "priority", "MUST")))[1] == []
    assert A.errors_of(ValueError("a\nb")) == ["a"]
    assert A.validate(model, "text")[1] == ["section: Input should be a valid dictionary or instance of PRDRequirements"]
