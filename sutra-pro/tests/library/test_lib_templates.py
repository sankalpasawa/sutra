"""The Template bases and their pure checks (library design 9.2; WP L7), ported from J2's j2_template_lib (baseline 33aeeda).

Parity data: tests/library/fixtures/artifacts/ holds J2's five committed templates/<artifact>/generic.json files (a frozen
copy, the test data of the generic layer: the library holds no generic of its own, D171) and four templates stored in J2's
library/ (spec.json, schema.json, meta.json), copied by build_artifact_cases.py. The library must accept a generic file's
entries, give a stored spec the sha J2 gave it and its transport schema J2's schema.json.
One declared difference: a one-value enum (`facts_used` narrowed to one fact) stays a constraint in the transport schema
(L1 keeps `const` as an enum; J2 dropped it); the thread-filter test shows it is the only difference."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.library import templates as T
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY, is_transport_safe, schema_sha

FIX = Path(__file__).parent / "fixtures" / "artifacts"
ENGINE_TEMPLATES = Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "templates"      # the vendored generics
# the names a reply may leave out in the five frozen generic files (J2's `reply_optional`, which the generic.json of that pin
# did not carry): test data, since the library holds no such list
REPLY_OPTIONAL = frozenset({
    "assumptions", "google_fonts_url", "notes", "window", "target", "validation", "page", "head", "anchor", "html",
    "selectors_used", "facts_used", "implements", "covers", "goals", "actions", "needs", "responsive_rules",
    "accessibility_rules", "out_of_scope", "risks", "data_flows", "files"})
GENERIC_FILES = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted((FIX / "generic").glob("*/generic.json"))}
SECTIONS = [(a, e["section"]) for a, f in GENERIC_FILES.items() for e in f["templates"]]
STORED = ["prd/requirements/still-point-yoga-requirements", "hld/components/still-point-yoga-components",
          "lld/form-fields/still-point-yoga-form-fields", "website/section/thread-filter"]


def generic(artifact, section):
    """The GenericTemplate of one entry of the frozen generic.json of `artifact` (test data)."""
    entry = next(e for e in GENERIC_FILES[artifact]["templates"] if e["section"] == section)
    return T.GenericTemplate.model_validate({k: v for k, v in entry.items() if k != "schema_sha"})


def keeps(data):
    """What `keeps_problems` says of a prd Requirements spec against its generic (the generic is the caller's, D171)."""
    return T.keeps_problems(generic("prd", "Requirements"), T.SpecialisedTemplate.model_validate(data))


def stored(rel):
    d = FIX / "library" / rel / "v1"
    return tuple(json.loads((d / n).read_text(encoding="utf-8")) for n in ("spec.json", "schema.json", "meta.json"))


REQ = stored(STORED[0])[0]


def spec(**changes):
    """The stored prd Requirements template with the changes applied (deep copy)."""
    out = copy.deepcopy(REQ)
    out.update(changes)
    return out


def field(name, type_="string", required=False, **rest):
    return {"name": name, "type": type_, "required": required, "description": "", "enum": None, "nullable": False, **rest}


def with_fields(*extra, **changes):
    out = spec(**changes)
    out["fields"] = out["fields"] + list(extra)
    return out


def refused(data) -> list[str]:
    return T.refusal(data)


def one_error(data) -> str:
    got = refused(data)
    assert len(got) == 1, got
    return got[0]


# ---------------------------------------------------------------- the generic layer is J2's data, not the library's
@pytest.mark.parametrize("artifact,section", SECTIONS, ids=[f"{a}/{s}" for a, s in SECTIONS])
def test_every_entry_of_a_frozen_generic_file_is_a_generic_template(artifact, section):
    g = generic(artifact, section)
    assert (g.kind, g.artifact, g.section, g.version) == ("generic", artifact, section, 1)
    assert g.sha == g.compute_sha() and len(g.sha) == 64
    assert g.model_dump()["kind"] == "generic" and GATE.check("template", g).kind == "generic"


def test_the_library_holds_no_generic_layer_of_its_own():
    for gone in ("generic", "generic_file", "write_generic", "generic_drift", "from_model", "templates_dir", "ARTIFACTS"):
        assert not hasattr(T, gone), gone


def test_a_generic_spec_of_j2_is_accepted_and_written_back_as_j2s_file():
    committed = json.loads((FIX / "generic" / "prd" / "generic.json").read_text(encoding="utf-8"))["templates"][2]
    plain = {k: v for k, v in committed.items() if k != "schema_sha"}
    g = T.GenericTemplate.model_validate(plain)
    assert T.spec_json(g) == plain and g.schema_version == 1


# ---------------------------------------------------------------- the Document generics (the whole PRD, HLD or LLD)
# keys of a generic.json ENTRY that are J2's own: how J2 builds its models, checks and rendering. The library's closed
# GenericTemplate is the template itself (fields, objects, rules), which is what J2's own runtime GenericTemplate is.
J2_ENTRY_ONLY = ("sha", "schema_sha", "render", "model", "conditions", "fact_fields", "reply_optional", "requires_one_of")


@pytest.mark.parametrize("artifact", ["prd", "hld", "lld"])
def test_the_document_generic_of_a_prd_hld_or_lld_loads_through_the_library_models(artifact):
    """agent-views/1: the whole document as one object, the last entry of the vendored templates/<artifact>/generic.json."""
    data = json.loads((ENGINE_TEMPLATES / artifact / "generic.json").read_text(encoding="utf-8"))
    document = data["templates"][-1]
    assert [x["section"] for x in data["templates"]].count("Document") == 1 and document["section"] == "Document"
    plain = {k: v for k, v in document.items() if k not in J2_ENTRY_ONLY}
    g = T.GenericTemplate.model_validate(plain)
    g = g.evolve(sha=g.compute_sha())
    assert (g.kind, g.artifact, g.section, g.version) == ("generic", artifact, "Document", 1)
    assert T.spec_json(g) == {**plain, "sha": g.sha} and len(g.sha) == 64
    assert GATE.check("template", {**plain, "sha": g.sha}).kind == "generic"


@pytest.mark.parametrize("artifact", sorted(p.name for p in ENGINE_TEMPLATES.iterdir() if (p / "generic.json").is_file()))
def test_every_generic_entry_of_the_vendored_tree_is_a_generic_template(artifact):
    """Every type's generic.json (a type J2 adds later too: the glob names none) holds entries the library can read."""
    data = json.loads((ENGINE_TEMPLATES / artifact / "generic.json").read_text(encoding="utf-8"))
    assert data["artifact"] == artifact
    for entry in data["templates"]:
        plain = {k: v for k, v in entry.items() if k not in J2_ENTRY_ONLY}
        g = T.GenericTemplate.model_validate(plain)
        assert (g.artifact, g.section) == (artifact, entry["section"])


# ---------------------------------------------------------------- the registry
def test_template_is_one_family_of_two_kinds():
    assert REGISTRY.kinds("template") == {"generic": T.GenericTemplate, "specialised": T.SpecialisedTemplate}
    assert not REGISTRY.is_payload("template")
    assert REGISTRY.json_schema("template")["discriminator"]["propertyName"] == "kind"


def test_the_gate_takes_a_specialised_template_and_refuses_a_broken_one():
    checked = GATE.check("template", spec())
    assert (checked.kind, checked.model.name) == ("specialised", "Still Point Yoga Requirements")
    with pytest.raises(GateError):
        GATE.check("template", spec(extends="prd/goals@generic/1"))


def test_the_meta_decision_and_file_models_are_payloads():
    for name, cls in (("template.meta", T.TemplateMeta), ("template.decision", T.TemplateDecision),
                      ("template.run", T.RunTemplate), ("template.file", T.TemplatesFile)):
        assert REGISTRY.kinds(name) == {name: cls}


@pytest.mark.parametrize("cls", [T.GenericTemplate, T.SpecialisedTemplate, T.TemplateMeta, T.TemplateDecision, T.RunTemplate, T.TemplatesFile])
def test_every_string_and_list_is_bounded(cls):
    assert unbounded_fields(cls) == []
    assert aliased_fields(cls) == []


# ---------------------------------------------------------------- stored J2 templates keep their shas and schemas
@pytest.mark.parametrize("rel", STORED)
def test_a_stored_j2_template_is_accepted_and_keeps_its_sha(rel):
    data, schema, meta = stored(rel)
    t = T.SpecialisedTemplate.model_validate(data)
    assert t.compute_sha() == data["sha"] == meta["sha"]
    assert T.spec_json(t) == data
    assert T.sha_of(T.spec_json(t)) == T.sha_of(data)
    m = T.TemplateMeta.model_validate(meta)
    assert m.to_json() == meta and (m.class_, m.sha) == (meta["class"], t.sha)
    assert m.model_dump(by_alias=True)["class"] == meta["class"]


@pytest.mark.parametrize("rel", STORED[:3])
def test_the_transport_schema_of_a_stored_template_is_j2s(rel):
    data, schema, meta = stored(rel)
    t = T.SpecialisedTemplate.model_validate(data)
    gen = generic(data["artifact"], data["section"])                  # the caller holds the generic: its fields are not "added"
    assert T.transport(t, REPLY_OPTIONAL, gen) == schema and T.transport(data, REPLY_OPTIONAL, gen) == schema
    assert schema_sha(T.transport(t, REPLY_OPTIONAL, gen)) == meta["schema_sha"]
    assert is_transport_safe(T.transport(t, REPLY_OPTIONAL, gen)) == []


def test_a_one_value_enum_stays_a_constraint_where_j2_lost_it():
    data, schema, meta = stored(STORED[3])
    mine = T.transport(data, REPLY_OPTIONAL, generic(data["artifact"], data["section"]))
    items = mine["properties"]["facts_used"]["items"]
    assert items == {"type": "string", "enum": ["Visitors can filter products by size and price"]}
    del items["enum"]
    assert mine == schema


def test_a_template_accepts_its_own_json_round_trip():
    t = T.SpecialisedTemplate.model_validate(spec())
    assert T.SpecialisedTemplate.model_validate_json(t.model_dump_json()) == t
    assert T.SpecialisedTemplate.model_validate(t.model_dump()) == t


# ---------------------------------------------------------------- sha, content, ref
def test_the_sha_covers_the_template_and_not_its_version_or_provenance():
    t = T.SpecialisedTemplate.model_validate(spec())
    changed = t.evolve(version=7, made_by={"run": "r", "workflow": "w", "atom": "a", "agent": "x"},
                       used_by=[{"run": "r", "workflow": "W-1", "atom": "a", "action": "reused"}])
    assert changed.compute_sha() == t.compute_sha() and changed.ref() == "Still Point Yoga Requirements@7"
    assert t.evolve(description="other").compute_sha() != t.compute_sha()
    assert t.evolve(name="Other").compute_sha() != t.compute_sha()
    assert "sha" not in t.content() and "schema_version" not in t.content() and "made_by" not in t.content()
    assert t.content()["rules"][0]["from"] == "facts"
    assert T.sha_of({"b": 1, "a": 2}) == T.sha_of({"a": 2, "b": 1})


def test_a_template_is_frozen_and_changes_by_evolve_only():
    t = T.SpecialisedTemplate.model_validate(spec())
    with pytest.raises(ValidationError):
        t.version = 2
    assert t.evolve(version=2).version == 2
    with pytest.raises(ValidationError, match="appears twice"):
        t.evolve(fields=[*t.fields, t.fields[0]])


# ---------------------------------------------------------------- shape_problems: one reason each
@pytest.mark.parametrize("name,why", [
    ("1x", "fields: field name '1x' is not an identifier (letters, digits and _ only, no dunder)"),
    ("a b", "fields: field name 'a b' is not an identifier (letters, digits and _ only, no dunder)"),
    ("a__b", "fields: field name 'a__b' is not an identifier (letters, digits and _ only, no dunder)"),
    ("", "fields: field name '' is not an identifier (letters, digits and _ only, no dunder)"),
    ("requirements", "fields: field 'requirements' appears twice")])
def test_a_field_name_is_an_identifier_used_once(name, why):
    assert one_error(with_fields(field(name))).endswith(why)


def test_a_field_type_is_one_of_the_allowed():
    assert one_error(with_fields(field("x", "float"))).endswith(
        "fields.x: type 'float' is not allowed (string, integer, boolean, list[string], list[<Object>] or <Object>)")
    assert one_error(with_fields(field("x", "list[list[string]]"))).endswith("is not allowed (string, integer, boolean, list[string], list[<Object>] or <Object>)")
    assert one_error(with_fields(field("x", "Nothing"))).endswith("fields.x: object type 'Nothing' is not defined in the spec")
    assert one_error(with_fields(field("x", "list[Nothing]"))).endswith("fields.x: object type 'Nothing' is not defined in the spec")
    for good in ("integer", "boolean", "list[string]", "list[ClassesItem]", "ClassesItem"):
        assert refused(with_fields(field("x", good))) == []


@pytest.mark.parametrize("extra,why", [
    (field("x", "integer", enum=["a"]), "fields.x: an enum is allowed on string and list[string] only"),
    (field("x", enum=[]), "fields.x: the enum must list non-empty strings"),
    (field("x", enum=["a", " "]), "fields.x: the enum must list non-empty strings"),
    (field("x", enum=["a", "a"]), "fields.x: the enum repeats a value"),
    (field("x", "integer", nullable=True), "fields.x: only a string or an object may be nullable")])
def test_enum_and_nullable_rules(extra, why):
    assert one_error(with_fields(extra)).endswith(why)
    assert refused(with_fields(field("x", enum=["a", "b"]), field("y", "list[string]", enum=["a"]), field("z", nullable=True),
                               field("w", "ClassesItem", nullable=True))) == []


def test_at_most_25_fields():
    def generic_with(n, objects=()):
        return {"name": "n", "artifact": "prd", "section": "Goals", "fields": [field(f"f{i}") for i in range(n)], "objects": list(objects)}
    assert T.GenericTemplate.model_validate(generic_with(25))
    with pytest.raises(ValidationError, match="fields has 26 fields; at most 25 are allowed"):
        T.GenericTemplate.model_validate(generic_with(26))
    part = {"name": "Part", "fields": [field(f"g{i}") for i in range(26)]}
    with pytest.raises(ValidationError, match="Part has 26 fields; at most 25 are allowed"):
        T.GenericTemplate.model_validate(generic_with(1, [part]))


def test_fields_over_the_hard_bound_are_refused_before_the_checks():
    out = {"name": "n", "artifact": "prd", "section": "Goals", "fields": [field(f"f{i}") for i in range(61)]}
    with pytest.raises(ValidationError, match="List should have at most 60 items"):
        T.GenericTemplate.model_validate(out)


def test_object_names_are_capwords_defined_once_and_never_recursive():
    out = spec()
    out["objects"][1]["name"] = "classes_item"
    assert any("object name 'classes_item' must be a CapWord identifier" in x for x in refused(out))
    out = spec()
    out["objects"].append(copy.deepcopy(out["objects"][0]))
    assert one_error(out).endswith("an object is defined twice")
    out = spec()
    out["objects"][0]["fields"].append(field("again", "list[Requirement]"))
    assert one_error(out).endswith("object 'Requirement' contains itself; recursion is not allowed")
    out = spec()
    out["objects"][0]["fields"].append(field("other", "ClassesItem"))
    out["objects"][1]["fields"].append(field("back", "Requirement"))
    assert "contains itself" in one_error(out)


def test_a_template_needs_a_name():
    assert refused(spec(name="  ")) and "name" in refused(spec(name=""))[0]
    assert T.shape_problems(T.GenericTemplate.model_construct(
        name=" ", fields=[], objects=[], rules=[], artifact="prd", section="Goals")) == ["the template needs a name"]


# ---------------------------------------------------------------- rule paths resolve to fields of the template
def test_resolve_follows_fields_objects_and_lists():
    t = T.SpecialisedTemplate.model_validate(spec())
    for path in ("requirements", "requirements[]", "requirements[].priority", "facts_used[]", "classes[].day", "assumptions[]"):
        assert T.resolve(t, path) is None, path
    g = generic("design", "Style guide")
    for path in ("palette.primary", "palette.*", "fonts.google_fonts_url", "buttons.primary", "card", "notes"):
        assert T.resolve(g, path) is None, path


@pytest.mark.parametrize("path,why", [
    ("", "rule path '' is empty or malformed"),
    ("a..b", "rule path 'a..b' is empty or malformed"),
    ("nothing", "rule path 'nothing': 'nothing' is not a field of the template"),
    ("requirements[].nothing", "rule path 'requirements[].nothing': 'nothing' is not a field of the template"),
    ("assumptions.x", "rule path 'assumptions.x': 'assumptions' has no fields under it"),
    ("requirements.id", "rule path 'requirements.id': 'requirements' has no fields under it"),
    ("*", "rule path '*': * must come last, after an object"),
    ("requirements.*.x", "rule path 'requirements.*.x': 'requirements' is not an object")])
def test_resolve_says_why_a_path_does_not(path, why):
    assert T.resolve(T.SpecialisedTemplate.model_validate(spec()), path) == why


def test_resolve_refuses_a_list_marker_on_something_that_is_not_a_list_and_a_non_object_prefix():
    t = T.GenericTemplate.model_validate({"name": "n", "artifact": "prd", "section": "Goals", "fields": [
        field("s"), field("n", "integer"), field("o", "Item"), field("l", "list[Item]")],
        "objects": [{"name": "Item", "fields": [field("a")]}]})
    assert T.resolve(t, "s[]") == "rule path 's[]': 's' is not a list"
    assert T.resolve(t, "n.x") == "rule path 'n.x': 'n' has no fields under it"
    assert T.resolve(t, "o.a") is None and T.resolve(t, "o.*") is None
    assert T.resolve(t, "l[].a") is None and T.resolve(t, "l.a") == "rule path 'l.a': 'l' has no fields under it"


def test_a_rule_path_outside_the_template_is_a_template_error_with_the_rule_position():
    bad = spec()
    bad["rules"].append({"rule": "not_empty", "path": ["requirements", "nothing"], "name": "n", "from": "x"})
    assert one_error(bad).endswith("rule 2 (not_empty): rule path 'nothing': 'nothing' is not a field of the template")
    bad = spec()
    bad["rules"] = [{"rule": "anchor_in_html", "anchor_path": "anchor", "html_path": "html", "name": "n", "from": "x"}]
    assert one_error(bad).endswith("rule path 'anchor': 'anchor' is not a field of the template; "
                                   "rule 1 (anchor_in_html): rule path 'html': 'html' is not a field of the template")


def test_rule_problems_takes_specs_and_j2_dicts_and_adds_the_path_check():
    t = T.SpecialisedTemplate.model_validate(spec())
    shipped = list(generic("prd", "Requirements").rules)
    assert T.rule_problems(t, shipped) == []
    assert T.rule_problems(t, [r.as_j2() for r in shipped]) == []
    out = T.rule_problems(t, [{"rule": "enum", "path": "x", "name": "n"}, "junk", {"rule": "nope"},
                              {"rule": "hex", "path": 5, "name": "n"}, {"rule": "not_empty", "path": ["facts_used", 7], "name": "n"}])
    assert out == [
        "rule 1 (enum): values is missing",
        "rule 1 (enum): values must be a list of strings",
        "rule 1 (enum): rule path 'x': 'x' is not a field of the template",
        "rule 2 is not an object",
        "rule 3: unknown rule type 'nope' (known: " + ", ".join(sorted(T.RULE_TYPES)) + ")",
        "rule 4 (hex): path must be one path",
        "rule 4 (hex): rule path 5 is not a string",
        "rule 5 (not_empty): rule path 7 is not a string"]


# ---------------------------------------------------------------- a specialised template keeps its generic
def test_extends_names_the_generic_of_its_section():
    assert one_error(spec(extends="prd/goals@generic/1")).endswith("extends must be 'prd/requirements@generic/1', not 'prd/goals@generic/1'")
    assert T.generic_ref("hld", "Hosting and deployment") == "hld/hosting-and-deployment@generic/1"


def test_the_artifact_is_a_name_by_shape_and_no_list():
    assert any("String should match pattern" in x for x in refused(spec(artifact="Doc")))
    assert any("String should match pattern" in x for x in refused(spec(artifact="a")))
    assert refused(spec(artifact="business_report", extends="business_report/requirements@generic/1")) == []     # any name by shape


def test_keeps_a_required_field_of_the_generic():
    out = spec()
    out["fields"] = [f for f in out["fields"] if f["name"] != "requirements"]
    assert keeps(out) == ["requirements: the generic's required field 'requirements' is dropped"]
    out = spec()
    out["fields"][0]["required"] = False
    assert keeps(out) == ["requirements: required in the generic, so it stays required"]
    out = spec()
    out["fields"][0]["type"] = "list[string]"
    assert keeps(out) == ["requirements: type 'list[string]' doesn't keep the generic's 'list[Requirement]'"]


def test_an_optional_field_of_the_generic_may_be_dropped():
    out = spec()
    out["fields"] = [f for f in out["fields"] if f["name"] != "assumptions"]
    assert keeps(out) == [] and refused(out) == []


def test_an_enum_may_only_narrow_the_generics():
    out = spec()
    out["objects"][0]["fields"][2]["enum"] = ["must", "should"]
    assert keeps(out) == []
    out["objects"][0]["fields"][2]["enum"] = ["must", "never"]
    assert keeps(out) == ["requirements.priority: the enum may only narrow the generic's (must, should, could)"]
    out["objects"][0]["fields"][2]["enum"] = None
    assert keeps(out) == ["requirements.priority: the enum may only narrow the generic's (must, should, could)"]


def test_the_parts_of_an_object_are_kept_too():
    out = spec()
    out["objects"][0]["fields"] = [f for f in out["objects"][0]["fields"] if f["name"] != "statement"]
    assert keeps(out) == ["requirements.statement: the generic's required field 'statement' is dropped"]
    out = spec()
    out["objects"][0]["name"] = "Req"
    out["fields"][0]["type"] = "list[Req]"
    out["objects"][0]["fields"][0]["required"] = False
    assert keeps(out) == ["requirements.id: required in the generic, so it stays required"]


def test_keeps_problems_on_models_directly():
    gen = generic("prd", "Requirements")
    sp = T.SpecialisedTemplate.model_validate(spec())
    assert T.keeps_problems(gen, sp) == []
    raw = sp.model_copy(update={"fields": [f for f in sp.fields if f.name != "requirements"]})       # not re-checked: model_copy
    assert T.keeps_problems(gen, raw) == ["requirements: the generic's required field 'requirements' is dropped"]


# ---------------------------------------------------------------- refusal
def test_refusal_is_empty_for_a_good_spec_and_plain_words_for_a_bad_one():
    assert refused(spec()) == []
    assert refused(spec(extends="x")) == ["extends must be 'prd/requirements@generic/1', not 'x'"]
    assert refused({"name": "n"})[0].startswith("artifact: Field required")
    assert refused("junk") and refused(None)
    assert refused(spec(unknown_key=1)) == ["unknown_key: Extra inputs are not permitted"]


# ---------------------------------------------------------------- the runtime class
def test_class_name_is_a_camel_case_name_and_the_version():
    t = T.SpecialisedTemplate.model_validate(spec())
    assert T.class_name(t) == "StillPointYogaRequirementsV1"
    assert T.class_name(t.evolve(name="2 fast", version=3)) == "T2FastV3"
    assert T.class_name(t.evolve(name="--")) == "TemplateV1"


def test_build_model_makes_a_strict_class_from_the_spec_and_caches_it():
    t = T.SpecialisedTemplate.model_validate(spec())
    cls = T.build_model(t)
    assert cls is T.build_model(t) is T.build_model(spec())
    assert cls.__name__ == "StillPointYogaRequirementsV1" and cls.template() == "Still Point Yoga Requirements v1"
    assert cls.SECTION == "Requirements"
    assert set(cls.model_fields) == {"requirements", "assumptions", "facts_used", "booking_form_fields", "classes"}
    other = T.build_model(t.evolve(version=2))
    assert other is not cls


def test_build_model_fills_defaults_by_type():
    t = T.SpecialisedTemplate.model_validate(with_fields(
        field("n", "integer"), field("b", "boolean"), field("e", enum=["x", "y"]), field("o", "ClassesItem"),
        field("s", nullable=True), field("l", "list[ClassesItem]"), field("ls", "list[string]", enum=["p", "q"])))
    cls = T.build_model(t)
    got = cls.model_validate({"requirements": []})
    assert (got.n, got.b, got.e, got.o, got.s, got.l, got.ls) == (0, False, "x", None, None, [], [])
    assert (got.assumptions, got.facts_used) == ([], [])


def test_a_field_named_like_a_python_keyword_is_read_by_its_name():
    t = T.SpecialisedTemplate.model_validate(with_fields(field("from"), field("pass", "boolean")))
    cls = T.build_model(t)
    got = cls.model_validate({"requirements": [], "from": "a", "pass": True})
    assert got.from_ == "a" and got.pass_ is True
    assert got.model_dump()["from"] == "a" and "pass" in got.model_dump()
    assert T.transport(t)["properties"]["from"] == {"description": "", "type": "string"}


def test_the_runtime_class_is_strict_and_closed():
    cls = T.build_model(T.SpecialisedTemplate.model_validate(spec()))
    good = {"requirements": [{"id": "R1", "statement": "s", "priority": "must", "goals": []}]}
    assert cls.model_validate(good)
    with pytest.raises(ValidationError):
        cls.model_validate({**good, "extra": 1})
    with pytest.raises(ValidationError):
        cls.model_validate({"requirements": [{"id": 1, "statement": "s", "priority": "must"}]})


def test_the_build_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(T, "_BUILT_MAX", 2)
    monkeypatch.setattr(T, "_BUILT", {})
    base = T.SpecialisedTemplate.model_validate(spec())
    first = T.build_model(base)
    T.build_model(base.evolve(version=2))
    T.build_model(base.evolve(version=3))
    assert len(T._BUILT) == 2
    assert T.build_model(base) is not first            # the oldest was dropped, a new class is built


# ---------------------------------------------------------------- the transport schema of a template
def test_a_field_the_template_added_as_optional_is_optional_in_the_transport_schema():
    t = T.SpecialisedTemplate.model_validate(with_fields(field("extra_note"), field("must_have", required=True)))
    schema = T.transport(t)
    assert "extra_note" not in schema["required"] and "must_have" in schema["required"]
    assert "requirements" in schema["required"] and "assumptions" not in schema["required"]     # not required in the template
    assert "facts_used" not in schema["required"]
    assert "requirements" not in T.transport(t, {"requirements"})["required"]               # a name the generic's reply_optional gives


def test_an_added_optional_part_field_is_optional_in_the_parts_schema_too():
    out = spec()
    out["objects"][0]["fields"].append(field("remark"))
    schema = T.transport(out)
    assert schema["definitions"]["Requirement"]["required"] == ["id", "statement", "priority"]


def test_the_transport_schema_of_a_generic_template_is_safe_and_the_same_from_a_dict():
    for artifact, section in SECTIONS:
        g = generic(artifact, section)
        assert is_transport_safe(T.transport(g, REPLY_OPTIONAL, g)) == []
        assert T.transport(g.model_dump(), REPLY_OPTIONAL, g) == T.transport(g, REPLY_OPTIONAL, g)
        assert list(T.transport(g, REPLY_OPTIONAL, g)["properties"]) == [f.name for f in g.fields]


# ---------------------------------------------------------------- validate: the template, then the generic model
def test_validate_gives_the_data_back_as_a_dict_or_the_errors():
    good = {"requirements": [{"id": "R1", "statement": "s", "priority": "MUST", "goals": ["G1"]}], "facts_used": ["Still Point Yoga"]}
    got, errors = T.validate(spec(), good)
    assert errors == [] and got["requirements"][0]["priority"] == "must" and got["assumptions"] == [] and got["classes"] == []
    got, errors = T.validate(spec(), {**good, "facts_used": ["not a fact"]})
    assert got is None and errors and errors[0].startswith("facts_used.0:")


def test_validate_holds_the_templates_shape_and_leaves_requires_one_of_to_j2():
    """The template makes `html` optional. J2's generic entry says "html or head" (`requires_one_of`): J2 runs that check
    on its own file, the library has no copy of it, so a section without either passes here."""
    data, _, _ = stored(STORED[3])
    got, errors = T.validate(data, {"id": "S1", "html": "<p>x</p>"})
    assert errors == [] and got["html"] == "<p>x</p>"
    assert T.validate(data, {"id": "S1"})[1] == []
    got, errors = T.validate(data, {"id": 5})
    assert got is None and errors and errors[0].startswith("id:")


def test_enum_casing_is_normalised_from_the_templates_own_enums():
    model = T.build_model(spec())
    assert model.ENUMS["priority"] == ["must", "should", "could"]
    assert T.normalise(model, {"requirements": [{"priority": " MUST "}]}) == {"requirements": [{"priority": "must"}]}
    assert T.normalise(model, "junk") == "junk"
    assert T.errors_of(ValueError("one\ntwo")) == ["one"]


def test_validate_takes_a_generic_template_and_a_model():
    g = generic("prd", "Goals")
    assert T.validate(g, {"goals": [{"id": "G1", "statement": "x"}]})[1] == []
    assert T.validate(g.model_dump(), {"goals": "G1"})[1] == ["goals: Input should be a valid list"]


# ---------------------------------------------------------------- a run's own copy (J2 33aeeda)
DECISION = {"run": "j2-20261103-161111-3", "t": "2026-11-03T16:11:11", "workflow": "W-4", "atom": "W-4.a1", "artifact": "prd",
            "section": "Requirements", "fingerprint": "33a8d2a50129cb4a96469aea615825c8399e15ba8972d0d899dfb38a580dc67e",
            "facts": 7, "fields": 3, "needed_fields": ["booking_form_fields", "classes"],
            "needed_enums": {"booking_form_fields": ["name", "email"]},
            "candidates": [{"name": "Still Point Yoga Requirements", "version": 1, "score": 0.5, "fingerprint_match": False, "has_fields": True}],
            "action": "created", "template": "Still Point Yoga Requirements", "version": 1, "kind": "specialised", "score": 0.0,
            "reason": "no candidate", "rule": "d", "attempts": 1, "refused": [], "covers": "covers 7 of 7 facts",
            "schema_sha": "2142c6dc4f14b39d3b95559a7d57466fa7a8a018e38fc336bc1a351653fc93f4",
            "saved": "templates/prd/requirements/still-point-yoga-requirements@v1"}
GENERIC_DECISION = {"run": "r", "t": "2026-11-03T16:11:11", "workflow": "W-9", "atom": "W-9.a1", "artifact": "design",
                    "section": "Style guide", "action": "generic", "template": "Design/1 · Style guide", "version": 1,
                    "kind": "generic", "score": None, "rule": "-", "reason": "the style guide is written inside the first page builder's reply",
                    "saved": None}


def test_run_tpl_rel_is_where_a_run_keeps_its_copy():
    assert T.run_tpl_rel(DECISION) == DECISION["saved"]
    assert T.run_tpl_rel(GENERIC_DECISION) == "templates/design/style-guide/design-1-style-guide@v1"
    assert T.run_tpl_rel(T.TemplateDecision.model_validate(DECISION)) == DECISION["saved"]
    assert T.RUN_TEMPLATE_FILES == ("spec.json", "model.py", "schema.json", "meta.json")


def test_a_routing_decision_of_j2_is_accepted_with_and_without_saved():
    d = T.TemplateDecision.model_validate(DECISION)
    assert (d.action, d.saved, d.candidates[0].score, d.needed_enums) == ("created", DECISION["saved"], 0.5, {"booking_form_fields": ["name", "email"]})
    assert T.TemplateDecision.model_validate(GENERIC_DECISION).saved is None
    older = {k: v for k, v in DECISION.items() if k != "saved"}
    assert T.TemplateDecision.model_validate(older).saved is None
    assert T.TemplateDecision.model_validate(d.model_dump()) == d


def test_the_decisions_of_the_fallback_paths_are_accepted():
    router_failed = {"workflow": "W-1", "atom": "W-1.a1", "artifact": "prd", "section": "Goals", "action": "generic", "template": "PRD/1 · Goals",
                     "version": 1, "kind": "generic", "score": None, "rule": "e", "reason": "the router could not run (KeyError: 'x')"}
    no_generic = {"workflow": None, "atom": None, "artifact": "prd", "section": "Goals", "action": "generic", "template": "not recorded",
                  "version": None, "kind": "generic", "score": None, "reason": "no generic template for prd 'Goals'", "fingerprint": "f",
                  "facts": 0, "fields": 0, "needed_fields": [], "needed_enums": {}, "candidates": []}
    twice = {**DECISION, "action": "generic", "kind": "generic", "attempts": 2, "refused": ["a", None], "rule": "e", "score": 0.0}
    for data in (router_failed, no_generic, twice):
        assert T.TemplateDecision.model_validate(data)


@pytest.mark.parametrize("saved", ["/etc/passwd", "../x", "templates/../x", "templates/prd/requirements/x", "templates/prd/requirements/x@v",
                                   "templates/prd/Requirements/x@v1", "templates/prd/requirements/a/b@v1", "run/templates/prd/requirements/x@v1"])
def test_saved_is_the_relative_path_of_a_copy_inside_the_run(saved):
    with pytest.raises(ValidationError):
        T.TemplateDecision.model_validate({**DECISION, "saved": saved})


def test_a_decision_is_closed_and_typed():
    for bad in ({"action": "reuse"}, {"kind": "special"}, {"artifact": "Doc"}, {"extra": 1}, {"version": 0}, {"attempts": 0}, {"score": "high"}):
        with pytest.raises(ValidationError):
            T.TemplateDecision.model_validate({**DECISION, **bad})


def test_a_run_template_row_adds_where_the_copy_can_be_read_from():
    row = T.RunTemplate.model_validate({**DECISION, "source": "from this run"})
    assert row.source == "from this run" and isinstance(row, T.TemplateDecision)
    for source in ("from library", "not recorded"):
        assert T.RunTemplate.model_validate({**GENERIC_DECISION, "source": source}).source == source
    with pytest.raises(ValidationError):
        T.RunTemplate.model_validate({**DECISION, "source": "elsewhere"})
    with pytest.raises(ValidationError):
        T.RunTemplate.model_validate(DECISION)


def test_templates_json_is_a_checked_file_that_writes_its_schema_key_back():
    raw = {"schema": "template-library/1", "library": "/tmp/library", "decisions": [DECISION, GENERIC_DECISION]}
    f = T.TemplatesFile.model_validate(raw)
    assert len(f.decisions) == 2 and "schema" not in f.model_dump()
    assert list(f.to_json())[0] == "schema" and f.to_json()["decisions"][0]["saved"] == DECISION["saved"]
    assert T.TemplatesFile.model_validate({"library": "/tmp/library"}).decisions == []
    with pytest.raises(ValidationError, match="schema must be 'template-library/1', not 'template-library/2'"):
        T.TemplatesFile.model_validate({**raw, "schema": "template-library/2"})


def test_meta_of_a_generic_copy_says_kind_generic_and_has_no_uses():
    g = generic("prd", "Goals")
    meta = {"schema": "template-library/1", "name": g.name, "version": 1, "kind": "generic", "sha": g.sha, "schema_sha": "a" * 64,
            "model_sha": "b" * 64, "used_by": []}
    m = T.TemplateMeta.model_validate(meta)
    assert (m.kind, m.used_by, m.class_) == ("generic", [], None)
    assert m.to_json() == meta
    used = T.TemplateMeta.model_validate({**meta, "kind": "specialised", "used_by": [{"run": "r", "workflow": "W-1", "atom": "W-1.a1", "action": "reused"}]})
    assert used.used_by[0].action == "reused"


def test_meta_is_closed_and_its_shas_are_hex():
    meta = {"name": "n", "version": 1, "sha": "a" * 64, "schema_sha": "b" * 64, "model_sha": "c" * 64}
    assert T.TemplateMeta.model_validate(meta).kind is None
    for bad in ({"sha": "xyz"}, {"kind": "other"}, {"extra": 1}, {"version": 0}, {"used_by": [{"who": "x"}]}):
        with pytest.raises(ValidationError):
            T.TemplateMeta.model_validate({**meta, **bad})
