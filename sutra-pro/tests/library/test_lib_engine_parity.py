"""The library's rule layer and Certainty rule against the engine's vendored copies (library design 14, decision D46; work
package L8). The engine keeps its lax J2 code as the runtime copy; this file is the permanent drift test that binds the two.
The section-model parts are gone with the models (D171): J2's generic.json files are the single source of a type's sections.

It is skipped when `sutra_app.engine` cannot be imported. The rule cases are `fixtures/artifacts/cases.json` (J2's own answers on
good and bad payloads, made once from J2's code)."""
import copy
import itertools
import json
from pathlib import Path

import pytest

pytest.importorskip("sutra_app.engine")

from sutra_app.connectors import jsonio  # noqa: E402
from sutra_app.engine import j2_realization, j2_rules, llm  # noqa: E402
from sutra_app.library import replies  # noqa: E402
from sutra_app.library import rules as lib_rules  # noqa: E402
from sutra_app.library.functions import SIGNALS, certainty_zone  # noqa: E402

HERE = Path(__file__).parent
CASES = json.loads((HERE / "fixtures" / "artifacts" / "cases.json").read_text(encoding="utf-8"))


# ============================================ rules =========================================================================
# The section models are retired (D171: J2 holds them as data in templates/<type>/generic.json). What stays bound to the
# engine is the rule layer, run on J2's own rule data, and the two functions below.
def test_every_rule_of_the_engines_data_is_a_rule_spec_that_writes_back_as_the_same_dict():
    every = j2_rules.all_rules()
    assert every and sum(len(v) for v in every.values()) > 0
    for key, rules in every.items():
        assert [lib_rules.RuleSpec.model_validate(r).as_j2() for r in rules] == rules, key


def test_run_specs_gives_the_engines_answer_on_every_case_and_every_section_is_covered():
    covered = set()
    for case in CASES["rules"]:
        docs = case["docs"] if case["with_docs"] else None
        rules = j2_rules.rules_for(case["kind"], case["section"])
        ours = lib_rules.run_specs([lib_rules.RuleSpec.model_validate(r) for r in rules], copy.deepcopy(case["data"]), copy.deepcopy(docs))
        theirs = j2_rules.run_rules(case["kind"], case["section"], copy.deepcopy(case["data"]), copy.deepcopy(docs))
        assert ours == theirs, f"{case['kind']}/{case['section']} ({case['label']})"
        covered.add((case["kind"], case["section"]))
    assert covered and covered <= set(j2_rules.all_rules())          # every section the cases cover still has its template


def test_the_rule_types_are_the_engines():
    assert set(lib_rules.RULE_TYPES) == set(j2_rules.RULE_TYPES)


# ============================================ Certainty =====================================================================
def test_certainty_zone_agrees_on_all_243_answer_combinations():
    combos = list(itertools.product(("yes", "no", "unknown"), repeat=len(SIGNALS)))
    assert len(combos) == 243
    for combo in combos:
        signals = {k: {"answer": a, "evidence": "e"} for k, a in zip(SIGNALS, combo)}
        assert certainty_zone(signals) == j2_realization.certainty_zone(signals), combo
        bare = dict(zip(SIGNALS, combo))
        assert certainty_zone(bare) == j2_realization.certainty_zone(bare), combo


@pytest.mark.parametrize("signals", [{}, None, {"broken": None}, {"broken": {"answer": "YES "}}, {"reaction": {"answer": "maybe"}},
                                     {"broken": {"evidence": "x"}}, {"facts_given": "yes", "known_pattern": "yes", "open_choices": "no"}])
def test_certainty_zone_agrees_on_odd_signals(signals):
    assert certainty_zone(signals) == j2_realization.certainty_zone(signals)


def test_the_zone_names_and_signal_names_are_the_engines():
    from sutra_app.library.functions import ZONES
    assert (ZONES, SIGNALS) == (j2_realization.ZONES, j2_realization.SIGNALS)


# ============================================ the one copy of the JSON helpers ==============================================
def test_extract_json_and_close_json_are_one_object_in_the_engine_the_connectors_and_the_library():
    assert llm.extract_json is jsonio.extract_json is replies.extract_json
    assert llm.close_json is jsonio.close_json is replies.close_json
