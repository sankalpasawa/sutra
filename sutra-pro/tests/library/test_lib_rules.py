"""The rules as data (library design 9.3; WP L7): J2's 12 rule functions and `RULES`, with a `RuleSpec` model in front.

Parity data: tests/library/fixtures/artifacts/cases.json holds, for every (kind, section) of J2's RULES, J2's own `run_rules`
answer on the good payload and on bad variants, with and without the documents the run recorded (100 cases, made once by
build_artifact_cases.py). The library must give the same list, evidence text included."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.library.artifacts import rules as R
from sutra_app.library.artifacts import SECTION_MODELS
from sutra_app.library.artifacts.rules import (
    RULE_NAMES, RULE_TYPES, RULES, RuleSpec, failures, rule_names, rules_count, rules_for, run_rules, run_specs, spec_problems, walk,
)

CASES = json.loads((Path(__file__).parent / "fixtures" / "artifacts" / "cases.json").read_text(encoding="utf-8"))
RULE_CASES = CASES["rules"]


def problems(data) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        RuleSpec.model_validate(data)
    return [(".".join(str(p) for p in e["loc"]), e["type"]) for e in error.value.errors()]


def message(data) -> str:
    with pytest.raises(ValidationError) as error:
        RuleSpec.model_validate(data)
    return error.value.errors()[0]["msg"].removeprefix("Value error, ")


SPEC = {"rule": "ids_sequential", "path": "goals", "prefix": "G", "name": "ids G1, G2, ...", "from": "P6"}


# ---------------------------------------------------------------- parity with J2
@pytest.mark.parametrize("case", RULE_CASES, ids=[f"{c['kind']}/{c['section']}/{c['label']}/{'docs' if c['with_docs'] else 'alone'}" for c in RULE_CASES])
def test_run_rules_gives_j2s_answer(case):
    assert run_rules(case["kind"], case["section"], case["data"], case["docs"]) == case["results"]


def test_the_cases_cover_every_rule_and_both_outcomes():
    seen = {(c["kind"], c["section"]) for c in RULE_CASES}
    assert seen == set(RULES)
    outcomes = {r["pass"] for c in RULE_CASES for r in c["results"]}
    assert outcomes == {True, False, None}
    assert {r["rule"] for c in RULE_CASES for r in c["results"]} == set(RULE_TYPES) - {"ids_unique"}      # no shipped rule uses it


def test_ids_unique_is_a_rule_type_a_template_may_use():
    spec = {"rule": "ids_unique", "path": "goals", "name": "n", "from": "f"}
    assert run_specs([spec], {"goals": [{"id": "a"}, {"id": "b"}]})[0]["evidence"] == "2 id(s), each once"
    assert run_specs([spec], {"goals": [{"id": "b"}, {"id": "a"}, {"id": "b"}]})[0]["pass"] is False
    assert run_specs([spec], {"goals": ["x", "x"]})[0]["evidence"] == "duplicate id(s): x"
    assert run_specs([spec], {})[0]["pass"] is None


def test_rules_is_one_list_of_specs_per_section_model_and_the_names_are_j2s():
    assert set(RULES) == {(k, s) for k, by in SECTION_MODELS.items() for s in by}
    assert sum(len(v) for v in RULES.values()) == 38
    assert all(isinstance(r, RuleSpec) for v in RULES.values() for r in v)
    assert {f"{k}/{s}": names for (k, s), names in RULE_NAMES.items()} == CASES["rule_names"]


def test_a_rule_path_never_names_a_field_the_model_lacks():
    """Every rule of RULES is checked against its section model by the generic template (templates.resolve), so a typo in a
    path fails there; here the first segment of each path is looked up directly."""
    for (kind, section), specs in RULES.items():
        fields = set(SECTION_MODELS[kind][section].model_fields)
        for spec in specs:
            for key in ("path", "anchor_path", "html_path"):
                value = getattr(spec, key)
                for path in value if isinstance(value, list) else [value] if value else []:
                    assert path.split(".")[0].removesuffix("[]") in fields, (kind, section, path)


# ---------------------------------------------------------------- the lookups
def test_rules_for_gives_the_specs_of_one_section_as_a_new_list():
    first = rules_for("prd", "Goals")
    assert [r.rule for r in first] == ["ids_sequential"]
    first.append("junk")
    assert len(rules_for("prd", "Goals")) == 1
    assert rules_for("prd", "Nothing") == [] and rules_for(None, None) == []


def test_rule_names_and_rules_count():
    assert rule_names("hld", "Components") == [
        "ids C1, C2, ... unique and in order", "every component states its responsibility",
        "page points at a page id of this document", "covers points at a requirement id of the PRD"]
    assert rules_count("hld", "Components") == 4 and rules_count("website", "Section", {"x": 1}) == 4
    assert rules_count("prd", "Nothing") == 0


def test_failures_are_the_evidence_of_the_failed_rules_in_order():
    results = run_rules("prd", "Goals", {"goals": [{"id": "G2", "statement": "x"}]})
    assert failures(results) == ["ids are not in order from G1: G2"]
    assert failures(run_rules("prd", "Goals", {"goals": []})) == []                  # not recorded is not a failure
    assert failures([{"pass": False, "evidence": "a"}, {"pass": True, "evidence": "b"}, {"pass": False, "evidence": "c"}]) == ["a", "c"]


# ---------------------------------------------------------------- run_specs never raises
def test_run_specs_takes_specs_or_j2_dicts_and_gives_the_same_answer():
    data = {"goals": [{"id": "G1"}, {"id": "G1"}]}
    spec = RuleSpec.model_validate(SPEC)
    assert run_specs([spec], data) == run_specs([SPEC], data)
    assert run_specs([SPEC], data)[0] == {"rule": "ids_sequential", "name": "ids G1, G2, ...", "from": "P6", "pass": False,
                                          "evidence": "duplicate id(s): G1"}


def test_an_unknown_rule_type_is_reported_not_raised():
    out = run_specs([{"rule": "frobnicate", "name": "n", "from": "f"}], {})
    assert out == [{"rule": "frobnicate", "name": "n", "from": "f", "pass": None, "evidence": "unknown rule type 'frobnicate'"}]


def test_something_that_is_not_a_rule_is_reported_where_j2_raised():
    out = run_specs(["junk", None, 5, {"rule": ["x"]}], {})
    assert [r["pass"] for r in out] == [None] * 4
    assert out[0]["evidence"] == "unknown rule type None"
    assert out[3]["evidence"] == "unknown rule type ['x']"


def test_a_rule_whose_check_breaks_is_reported_with_the_reason():
    """`enum` without its values breaks inside the check: the answer is "not recorded" and says why."""
    out = run_specs([{"rule": "enum", "path": "a", "name": "n", "from": "f"}], {"a": "x"})
    assert out[0]["pass"] is None
    assert out[0]["evidence"] == "the rule could not run: KeyError: 'values'"


def test_no_specs_and_no_data_are_fine():
    assert run_specs(None, None) == [] and run_specs([], {}) == []
    assert run_rules("prd", "Problem", None)[0]["pass"] is False
    assert run_rules("nothing", "nothing", {}) == []


def test_a_target_the_run_has_not_recorded_is_not_recorded_unless_it_is_required():
    soft = run_rules("prd", "Success metrics", {"success_metrics": [{"goal": "G1"}]}, {})
    assert (soft[0]["pass"], soft[0]["evidence"]) == (None, "this.goals[].id is not recorded, so success_metrics[].goal can't be checked")
    hard = run_rules("hld", "Components", {"components": [{"id": "C1", "responsibility": "r", "covers": ["R1"]}]}, {})
    covers = [r for r in hard if r["from"] == "H4"][0]
    assert (covers["pass"], covers["evidence"]) == (False, "C1: the PRD's requirement ids are not recorded, so Covers can't be checked")


# ---------------------------------------------------------------- walk
def test_walk_follows_fields_lists_and_object_values():
    data = {"a": {"b": [{"id": "x", "c": 1}, {"c": 2}]}, "palette": {"p": "#fff", "q": "#000"}, "empty": None}
    assert walk(data, "a.b[].c") == [(1, {"id": "x", "c": 1}), (2, {"c": 2})]
    assert walk(data, "palette.*") == [("#fff", {"id": "p"}), ("#000", {"id": "q"})]
    assert walk(data, "a.b") == [([{"id": "x", "c": 1}, {"c": 2}], data)]
    assert walk(data, "empty") == [] and walk(data, "nothing.here") == [] and walk(data, "") == [] and walk(data, None) == []
    assert walk({"a": 1}, "a.*") == []                      # `*` over something that is not an object
    assert walk({"a": ["s", "t"]}, "a[]") == [("s", {"a": ["s", "t"]}), ("t", {"a": ["s", "t"]})]


# ---------------------------------------------------------------- RuleSpec
def test_a_rule_spec_is_the_j2_dict_with_from_as_from_():
    spec = RuleSpec.model_validate(SPEC)
    assert (spec.rule, spec.from_, spec.path, spec.prefix, spec.required_target) == ("ids_sequential", "P6", "goals", "G", False)
    assert spec.as_j2() == SPEC
    assert RuleSpec.model_validate({k: v for k, v in SPEC.items() if k != "from"} | {"from_": "P6"}) == spec
    with pytest.raises(ValidationError):
        spec.name = "other"


def test_as_j2_keeps_what_is_set_and_drops_the_rest():
    spec = RuleSpec.model_validate({"rule": "ref_exists", "path": "a", "target": "this.b", "name": "n", "from": "f", "required_target": True})
    assert spec.as_j2() == {"rule": "ref_exists", "path": "a", "target": "this.b", "name": "n", "from": "f", "required_target": True}
    shipped = RULES[("hld", "Components")][3]
    assert sorted(shipped.as_j2()) == sorted(["rule", "path", "target", "required_target", "fail_text", "missing_text", "name", "from"])
    assert "required_target" not in RULES[("hld", "Components")][0].as_j2()


def test_every_shipped_spec_survives_a_round_trip():
    for specs in RULES.values():
        for spec in specs:
            assert RuleSpec.model_validate(spec.as_j2()) == spec


def test_an_unknown_rule_type_is_a_value_error_in_j2s_words():
    bad = {**SPEC, "rule": "frobnicate"}
    assert problems(bad) == [("", "value_error")]
    assert message(bad) == "rule: unknown rule type 'frobnicate' (known: " + ", ".join(sorted(RULE_TYPES)) + ")"
    assert problems({**SPEC, "rule": 5}) == [("", "value_error")]


def test_a_rule_missing_what_its_type_needs_is_refused():
    assert message({k: v for k, v in SPEC.items() if k != "prefix"}) == "rule (ids_sequential): prefix is missing"
    assert message({"rule": "ref_exists", "path": "a", "name": "n", "from": "f"}) == "rule (ref_exists): target is missing; rule (ref_exists): target must start with this., prd., hld. or lld."
    assert message({"rule": "enum", "path": "a", "name": "n", "from": "f"}) == "rule (enum): values is missing; rule (enum): values must be a list of strings"
    assert message({"rule": "anchor_in_html", "anchor_path": "a", "name": "n", "from": "f"}) == "rule (anchor_in_html): html_path is missing"
    assert message({"rule": "not_empty", "name": "n", "from": "f"}) == "rule (not_empty): path is missing"


def test_a_rule_that_takes_one_path_refuses_a_list():
    assert message({**SPEC, "path": ["a", "b"]}) == "rule (ids_sequential): path must be one path"
    RuleSpec.model_validate({"rule": "not_empty", "path": ["a", "b"], "name": "n", "from": "f"})        # a list is fine here
    assert message({"rule": "hex", "path": ["a"], "name": "n", "from": "f"}) == "rule (hex): path must be one path"


def test_a_ref_exists_target_starts_with_a_document_name():
    base = {"rule": "ref_exists", "path": "a", "name": "n", "from": "f"}
    assert message({**base, "target": "foo.x"}) == "rule (ref_exists): target must start with this., prd., hld. or lld."
    assert message({**base, "target": "this"}) == "rule (ref_exists): target must start with this., prd., hld. or lld."
    for good in ("this.a", "prd.a", "hld.a", "lld.a"):
        assert RuleSpec.model_validate({**base, "target": good}).target == good


def test_several_problems_are_reported_together():
    text = message({"rule": "enum", "path": ["a"], "name": "n", "from": "f"})
    assert text == ("rule (enum): values is missing; rule (enum): path must be one path; "
                    "rule (enum): values must be a list of strings")


def test_a_rule_needs_a_readable_name_and_a_source():
    assert problems({**SPEC, "name": "  "}) == [("name", "string_too_short")]
    assert problems({k: v for k, v in SPEC.items() if k != "from"}) == [("from", "missing")]
    assert problems({**SPEC, "extra": 1}) == [("extra", "extra_forbidden")]
    assert {e[0].split(".")[0] for e in problems({**SPEC, "path": ""})} == {"path"}


def test_values_must_be_strings_and_not_empty():
    base = {"rule": "enum", "path": "a", "name": "n", "from": "f"}
    assert [e[1] for e in problems({**base, "values": [1, 2]})] == ["string_type", "string_type"]
    assert problems({**base, "values": []}) == [("values", "too_short")]
    assert RuleSpec.model_validate({**base, "values": ["a", "b"]}).values == ["a", "b"]


def test_strict_types_and_bounds():
    assert problems({**SPEC, "required_target": "yes"}) == [("required_target", "bool_type")]
    assert problems({**SPEC, "name": "n" * 201}) == [("name", "string_too_long")]
    assert problems({**SPEC, "prefix": "G" * 301}) == [("prefix", "string_too_long")]
    assert len(problems({**SPEC, "path": ["a"] * 41})) >= 1


def test_spec_problems_wording_with_and_without_a_position():
    assert spec_problems("junk") == ["rule is not an object"] and spec_problems(None, 3) == ["rule 3 is not an object"]
    assert spec_problems({"rule": "nope"}, 2) == ["rule 2: unknown rule type 'nope' (known: " + ", ".join(sorted(RULE_TYPES)) + ")"]
    assert spec_problems({"rule": "hex", "path": "a", "name": "n", "colour": 1}, 1) == ["rule 1 (hex): unknown key(s) colour"]
    assert spec_problems({"rule": "hex", "path": "a"}, 1) == ["rule 1 (hex): it needs a name a reader can read"]
    assert spec_problems({"rule": "hex", "path": "a", "name": "n"}) == []
    assert spec_problems({"rule": ["x"]}) == ["rule: unknown rule type ['x'] (known: " + ", ".join(sorted(RULE_TYPES)) + ")"]


def test_rules_are_built_and_checked_at_import():
    """A typo in the data fails the import: building the same data again from a broken copy raises."""
    broken = [dict(r.as_j2()) for r in RULES[("prd", "Goals")]]
    broken[0]["rule"] = "ids_sequental"
    with pytest.raises(ValidationError, match="unknown rule type 'ids_sequental'"):
        RuleSpec.model_validate(broken[0])
    assert isinstance(RULES, dict) and all(isinstance(k, tuple) and len(k) == 2 for k in RULES)
