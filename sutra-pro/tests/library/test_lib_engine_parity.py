"""The library's artifact models, rules and Certainty rule against the engine's vendored copies (library design 14, decision D46,
S2-models-12; work package L8). The engine keeps its lax J2 code as the runtime copy; this file is the permanent drift test that
binds the two, and the condition under which the engine may switch to the library's.

It is skipped when `sutra_app.engine` cannot be imported. The corpus is `fixtures/artifacts/cases.json` (J2's good payloads and
its three known bad ones, made once from J2's own code) plus three mechanical mutations of every good payload. The one known
disagreement is in `parity_allowlist.json`; the test fails on any other, and on an allowlist line that no longer disagrees."""
import copy
import itertools
import json
from pathlib import Path

import pytest

pytest.importorskip("sutra_app.engine")

from sutra_app.connectors import jsonio  # noqa: E402
from sutra_app.engine import j2_artifact_models as engine_models  # noqa: E402
from sutra_app.engine import j2_realization, j2_rules, llm  # noqa: E402
from sutra_app.library import artifacts as lib  # noqa: E402
from sutra_app.library import replies  # noqa: E402
from sutra_app.library.artifacts import models as lib_models  # noqa: E402
from sutra_app.library.functions import SIGNALS, certainty_zone  # noqa: E402
from sutra_app.library.registry import is_transport_safe, schema_sha, transport_schema  # noqa: E402

HERE = Path(__file__).parent
CASES = json.loads((HERE / "fixtures" / "artifacts" / "cases.json").read_text(encoding="utf-8"))
ALLOWED = json.loads((HERE / "parity_allowlist.json").read_text(encoding="utf-8"))["verdict"]
SECTIONS = [(kind, section) for kind, by in lib.SECTION_MODELS.items() for section in by]
IDS = [f"{k}/{s}" for k, s in SECTIONS]


# ============================================ transport schemas =============================================================
@pytest.mark.parametrize("kind,section", SECTIONS, ids=IDS)
def test_a_section_model_sends_the_same_transport_schema_as_the_engines(kind, section):
    ours = transport_schema(lib.SECTION_MODELS[kind][section])
    theirs = engine_models.transport_schema(engine_models.SECTION_MODELS[kind][section])
    assert schema_sha(ours) == engine_models.schema_sha(theirs)
    assert is_transport_safe(ours) == []


@pytest.mark.parametrize("kind", ["prd", "hld", "lld"])
def test_a_document_model_sends_the_same_transport_schema_as_the_engines(kind):
    assert schema_sha(transport_schema(lib.DOC_MODELS[kind])) == engine_models.schema_sha(
        engine_models.transport_schema(engine_models.DOC_MODELS[kind]))


def test_the_two_registries_of_sections_name_the_same_sections():
    assert {k: list(v) for k, v in lib.SECTION_MODELS.items()} == {k: list(v) for k, v in engine_models.SECTION_MODELS.items()}
    assert set(lib.DOC_MODELS) == set(engine_models.DOC_MODELS)
    assert (lib.VERSION, lib_models.OPTIONAL_FIELDS) == (engine_models.VERSION, engine_models.OPTIONAL_FIELDS)


# ============================================ verdicts ======================================================================
def accepts(model, data) -> bool:
    try:
        model.model_validate(data)
        return True
    except Exception:
        return False


def mutate_extra(data):
    return {**data, "zzz_extra": 1}


def mutate_type(data):
    out = copy.deepcopy(data)
    for key, value in out.items():
        if isinstance(value, str):
            out[key] = 7
            return out
        if isinstance(value, list) and value:
            out[key] = "oops"
            return out
    return None


def mutate_drop(data):
    out = copy.deepcopy(data)
    if not out:
        return None
    out.pop(next(iter(out)))
    return out


def corpus():
    for key, good in CASES["good"].items():
        for name, mutation in (("good", lambda d: d), ("extra", mutate_extra), ("type", mutate_type), ("drop", mutate_drop)):
            data = mutation(good)
            if data is not None:
                yield f"{key}:{name}", key, data
    for index, case in enumerate(CASES["errors"]):
        yield f"{case['key']}:error:{index}", case["key"], case["data"]


def verdicts():
    out = {}
    for case_id, key, data in corpus():
        kind, section = key.split("/")
        out[case_id] = (accepts(lib.SECTION_MODELS[kind][section], data), accepts(engine_models.SECTION_MODELS[kind][section], data))
    return out


def test_the_corpus_is_large_enough_to_mean_something():
    found = verdicts()
    assert len(found) >= 70 and {a for a, _ in found.values()} == {True, False}


def test_the_models_agree_on_every_case_except_the_ones_the_allowlist_explains():
    disagree = {case_id: pair for case_id, pair in verdicts().items() if pair[0] != pair[1]}
    assert set(disagree) == set(ALLOWED), (
        f"disagreements not in parity_allowlist.json: {sorted(set(disagree) - set(ALLOWED))}; "
        f"lines that no longer disagree: {sorted(set(ALLOWED) - set(disagree))}")
    for case_id, (ours, theirs) in disagree.items():
        assert (("accept" if ours else "reject"), ("accept" if theirs else "reject")) == (ALLOWED[case_id]["library"], ALLOWED[case_id]["engine"])
        assert ALLOWED[case_id]["why"]


def test_every_good_payload_is_accepted_by_both():
    for key, good in CASES["good"].items():
        kind, section = key.split("/")
        assert accepts(lib.SECTION_MODELS[kind][section], good) and accepts(engine_models.SECTION_MODELS[kind][section], good), key


# ============================================ rules =========================================================================
def test_every_rule_spec_is_the_engines_rule_dict():
    assert set(lib.RULES) == set(j2_rules.RULES)
    for key, specs in lib.RULES.items():
        assert [s.as_j2() for s in specs] == j2_rules.RULES[key], key
        assert lib.rule_names(*key) == j2_rules.rule_names(*key) and lib.rules_count(*key) == j2_rules.rules_count(*key)


def test_run_rules_gives_the_same_answer_on_every_case_and_every_section_is_covered():
    covered = set()
    for case in CASES["rules"]:
        docs = case["docs"] if case["with_docs"] else None
        ours = lib.run_rules(case["kind"], case["section"], copy.deepcopy(case["data"]), copy.deepcopy(docs))
        theirs = j2_rules.run_rules(case["kind"], case["section"], copy.deepcopy(case["data"]), copy.deepcopy(docs))
        assert ours == theirs, f"{case['kind']}/{case['section']} ({case['label']})"
        covered.add((case["kind"], case["section"]))
    assert covered >= {key for key, specs in j2_rules.RULES.items() if specs}


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
