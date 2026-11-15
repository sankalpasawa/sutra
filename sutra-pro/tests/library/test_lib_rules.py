"""The rules as data (library design 9.3; WP L7): J2's 12 rule functions, with a `RuleSpec` model in front.

The rules of a section are DATA in J2 (`templates/<type>/generic.json`, D171); the library holds none. Parity data:
tests/library/fixtures/artifacts/cases.json holds, for every (kind, section) of J2's rules, J2's own `run_rules` answer on
the good payload and on bad variants, with and without the documents the run recorded (100 cases, made once by
build_artifact_cases.py), and the folder fixtures/artifacts/generic/ holds the generic.json files those rules were read from
(a frozen copy, read-only). The library, given those rules as specs, must give the same list, evidence text included."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.library.rules import RULE_TYPES, RuleSpec, failures, run_specs, spec_problems, walk

FIXTURES = Path(__file__).parent / "fixtures" / "artifacts"
CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
RULE_CASES = CASES["rules"]


def _specs() -> dict[tuple[str, str], list[RuleSpec]]:
    """(kind, section) -> the rules of that section, from the frozen generic.json files."""
    out = {}
    for path in sorted((FIXTURES / "generic").glob("*/generic.json")):
        file = json.loads(path.read_text(encoding="utf-8"))
        for entry in file["templates"]:
            out[(file["artifact"], entry["section"])] = [RuleSpec.model_validate(r) for r in entry.get("rules") or []]
    return out


RULES = {key: value for key, value in _specs().items() if value}


def run_rules(kind, section, data, docs=None):
    return run_specs(RULES.get((kind, section), []), data, docs)


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


def test_the_rules_of_the_frozen_generic_files_are_specs_with_j2s_names():
    assert sum(len(v) for v in RULES.values()) == 38
    assert all(isinstance(r, RuleSpec) for v in RULES.values() for r in v)
    assert {f"{k}/{s}": [r.name for r in specs] for (k, s), specs in RULES.items()} == {
        key: names for key, names in CASES["rule_names"].items() if names}


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
    assert message({"rule": "ref_exists", "path": "a", "name": "n", "from": "f"}) == "rule (ref_exists): target is missing; rule (ref_exists): target must start with this. or an artifact's name"
    assert message({"rule": "enum", "path": "a", "name": "n", "from": "f"}) == "rule (enum): values is missing; rule (enum): values must be a list of strings"
    assert message({"rule": "anchor_in_html", "anchor_path": "a", "name": "n", "from": "f"}) == "rule (anchor_in_html): html_path is missing"
    assert message({"rule": "not_empty", "name": "n", "from": "f"}) == "rule (not_empty): path is missing"


def test_a_rule_that_takes_one_path_refuses_a_list():
    assert message({**SPEC, "path": ["a", "b"]}) == "rule (ids_sequential): path must be one path"
    RuleSpec.model_validate({"rule": "not_empty", "path": ["a", "b"], "name": "n", "from": "f"})        # a list is fine here
    assert message({"rule": "hex", "path": ["a"], "name": "n", "from": "f"}) == "rule (hex): path must be one path"


def test_a_ref_exists_target_starts_with_this_or_an_artifact_name_by_shape():
    base = {"rule": "ref_exists", "path": "a", "name": "n", "from": "f"}
    want = "rule (ref_exists): target must start with this. or an artifact's name"
    for bad in ("Foo.x", "this", "1abc.x", "a-b.x", ".x"):
        assert message({**base, "target": bad}) == want, bad
    for good in ("this.a", "prd.a", "hld.a", "business_report.a", "x1.a"):        # a name is a shape: the data names the types
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


def test_a_typo_in_a_rule_is_refused_when_the_spec_is_built():
    broken = dict(RULES[("prd", "Goals")][0].as_j2())
    broken["rule"] = "ids_sequental"
    with pytest.raises(ValidationError, match="unknown rule type 'ids_sequental'"):
        RuleSpec.model_validate(broken)
