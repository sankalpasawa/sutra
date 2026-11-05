"""Mutation tests of the verify registry (WP E8, function-nodes.md section 9): a check nobody can fail is decoration.

1. Every check is replaced, in a copy of the registry, by an always-ok and by an always-fail check; the fixture cases of that
   check must notice both ways. Under always-ok exactly the cases that expect something other than a plain pass must flip;
   under always-fail exactly the cases that expect ok must flip.
2. Outcome mutants: a passing situation is changed in the one way that should break it (a GRANT over the budget posted as
   GRANT, a schedule with an unregistered id, a PASS row with an empty note, a rubric item measured but passed, a charter that
   fails the stamp) and the named check must flip from ok to not ok.
"""
import copy
import dataclasses
import json

import pytest
from test_engine_fn_registry import CASE_FILES, FIXTURES, build_evidence, load_case, mismatches

from sutra_app.engine.fnodes.registry import REGISTRY, CheckRegistry, Outcome


def mutated(check: str, fn) -> CheckRegistry:
    """A copy of the registry whose `check` runs `fn`."""
    return CheckRegistry(tuple(dataclasses.replace(REGISTRY[name], fn=fn) if name == check else REGISTRY[name] for name in REGISTRY))


def flag_mismatches(outcome: Outcome, expect: dict) -> list[str]:
    """Only the verdict is compared (the evidence text is not): the question is whether the check can tell cases apart."""
    verdict = {k: v for k, v in expect.items() if k in ("ok", "na", "waived", "changed")}
    return mismatches(outcome, verdict)


def cases_of(check: str):
    return sorted(p for p in CASE_FILES if p.parent.name == check)


def flipped(check: str, fn) -> set[str]:
    registry = mutated(check, fn)
    out = set()
    for path in cases_of(check):
        _, args, raw, expect = load_case(path)
        if flag_mismatches(registry.run(check, build_evidence(check, raw), args), expect):
            out.add(path.stem)
    return out


@pytest.mark.parametrize("check", REGISTRY.names())
def test_a_check_that_always_says_ok_is_caught(check):
    names = {p.stem for p in cases_of(check)}
    plain_pass = {p.stem for p in cases_of(check) if load_case(p)[3]["ok"] and not any(load_case(p)[3].get(k) for k in ("na", "waived", "changed"))}
    caught = flipped(check, lambda ev, args: Outcome(ok=True, evidence="always ok"))
    assert caught and caught == names - plain_pass
    assert any(n.startswith("fail") for n in caught)


@pytest.mark.parametrize("check", REGISTRY.names())
def test_a_check_that_always_fails_is_caught(check):
    caught = flipped(check, lambda ev, args: Outcome(ok=False, evidence="always fail"))
    assert caught == {p.stem for p in cases_of(check) if load_case(p)[3]["ok"]}
    assert any(n.startswith("pass") for n in caught)


# ---- outcome mutants ------------------------------------------------------------------------------------------------------

def base_and_mutant(check: str, case: str, change):
    """(the outcome of a passing fixture, the outcome after `change(evidence dict)`)."""
    name, args, raw, expect = load_case(FIXTURES / check / f"{case}.json")
    assert expect["ok"] and not expect.get("na")
    before = REGISTRY.run(name, build_evidence(name, raw), args)
    broken = copy.deepcopy(raw)
    change(broken)
    return before, REGISTRY.run(name, build_evidence(name, broken), args)


def test_a_grant_over_the_budget_posted_as_grant_fails_within_budget():
    def post_grant(raw):
        assert raw["posted"][0]["decision"] == "refuse"
        raw["posted"][0]["decision"] = "grant"
    ok, broken = base_and_mutant("within-budget", "recovered_code_turned_the_grant_into_refuse", post_grant)
    assert ok.ok and ok.changed and not broken.ok and broken.evidence == "GRANT 120 > 80 left, posted GRANT"


def test_a_schedule_with_an_unregistered_id_fails_order_registered():
    def add_unregistered(raw):
        raw["posted"][0]["schedule"].append("W-9")
    ok, broken = base_and_mutant("order-registered", "pass", add_unregistered)
    assert ok.ok and not broken.ok and broken.evidence == "W-9 is not registered"


def test_a_pass_row_with_an_empty_note_fails_pass_needs_proof():
    def empty_the_note(raw):
        raw["records"]["audits.json"][0]["results"][0]["note"] = ""
    ok, broken = base_and_mutant("pass-needs-proof", "pass", empty_the_note)
    assert ok.ok and not broken.ok and broken.evidence == "F-1 PASS without evidence"


def test_a_rubric_item_measured_but_passed_fails_code_measure_wins():
    def pass_the_measured_item(raw):
        row = next(r for r in raw["records"]["audits.json"][0]["rubric"] if r["id"] == "R-2")
        row.update(verdict="PASS", note="looks fine")
        row["pass"] = True
    ok, broken = base_and_mutant("code-measure-wins", "pass", pass_the_measured_item)
    assert ok.ok and not broken.ok and broken.evidence == "R-2 measured but recorded PASS"


def test_a_charter_that_fails_the_stamp_fails_charter_stamp():
    def drop_items(raw):
        raw["records"]["goal.json"]["done_when"] = raw["records"]["goal.json"]["done_when"][:2]
    ok, broken = base_and_mutant("charter-stamp", "pass", drop_items)
    assert ok.ok and not broken.ok and broken.evidence == "fewer than 3 'done when' criteria"


def test_removing_the_evidence_a_check_needs_turns_a_pass_into_a_failure():
    """The other half of 'missing evidence is a fail': take away what the passing case relied on."""
    for check, case, drop in (("charter-stamp", "pass", "records"), ("finding-per-item", "pass", "records"), ("workable", "pass_ended_workable", "records"),
                              ("order-registered", "pass", "before"), ("reply-valid", "pass_schedule", "reply"), ("price-kept", "pass_priced", "reply")):
        ok, broken = base_and_mutant(check, case, lambda raw, drop=drop: raw.pop(drop))
        assert ok.ok and not broken.ok and broken.evidence.startswith("missing:"), (check, broken)
    assert json.loads((FIXTURES / "reply-valid" / "pass_schedule.json").read_text())["expect"]["ok"]
