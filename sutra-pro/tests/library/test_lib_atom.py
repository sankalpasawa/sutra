"""The Atom record and its parts (library design section 7; WP L4): the 26 check names and their argument rules, the closed
classes, the plugin's open-time rules V1 to V4 (`open_rules`), the per-state rules V5, the result count rule V6, the
registry entries and the invalid-input rows of section 14."""
import json
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import ValidationError

from factories_atom import ATOM_ID, abandon, check, close_with, closed, draft, fields, opened, refused, tried, verify_failed_atom, work
from sutra_app.library import atom as atom_module
from sutra_app.library.atom import (
    BEHAVIOR_VERBS, CHECK_NAMES, J2_CHECKS, PLUGIN_CHECKS, REGISTRY_CHECKS, Atom, AtomDraft, AtomEdge, Check, CheckResult,
    CheckTemplate, Constraint, ExpectedItem, OutputItem, Refusal, Verify, Work, check_arity, check_sentence, default_relevance,
    open_rules,
)
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY
from sutra_app.library.types import violations_from_validation_error


def violations(build):
    with pytest.raises(ValidationError) as caught:
        build()
    return violations_from_validation_error(caught.value)


def said(vs, code, *words):
    """Is there a violation with this pydantic code whose message holds every word?"""
    return any(v.code == code and all(w in v.message for w in words) for v in vs)


# ---- the 26 names --------------------------------------------------------------------------------------------------------

def test_there_are_26_check_names_twelve_old_and_fourteen_from_the_registry():
    assert len(CHECK_NAMES) == 26 and len(set(CHECK_NAMES)) == 26
    assert CHECK_NAMES[:12] == (*PLUGIN_CHECKS, *J2_CHECKS) and CHECK_NAMES[12:] == REGISTRY_CHECKS
    assert len(PLUGIN_CHECKS) == 3 and len(J2_CHECKS) == 9 and len(REGISTRY_CHECKS) == 14
    assert get_args(CheckTemplate) == CHECK_NAMES


@pytest.mark.parametrize("name,limits", [
    ("grep-count", (3, 3)), ("file-exists", (1, 8)), ("named-test", (1, 8)), ("element-count", (0, 8)), ("facts-present", (0, 8)),
    ("reply-valid", (2, 2)), ("answer-recorded", (1, 1)), ("turn-posted", (0, 0)), ("charter-stamp", (0, 0)), ("workable", (0, 0)),
    ("audience-split", (0, 0)), ("atom-rules", (0, 0)), ("judge-gate", (0, 0)), ("price-kept", (0, 0)), ("within-budget", (0, 0)),
    ("order-registered", (0, 0)), ("finding-per-item", (0, 0)), ("pass-needs-proof", (0, 0)), ("code-measure-wins", (0, 0)),
])
def test_argument_counts_of_the_names(name, limits):
    assert check_arity(name) == limits


def test_every_name_has_an_arity_and_a_stranger_has_none():
    assert all(check_arity(name) is not None for name in CHECK_NAMES)
    assert check_arity("lint") is None


def test_the_arity_is_bound_to_the_registry_so_verify_refs_checks_function_specs():
    def spec(*refs):
        template = SimpleNamespace(name="t", checks=[SimpleNamespace(name=n, args=a) for n, a in refs])
        return SimpleNamespace(specs={"identity": SimpleNamespace(function="identity", task_kinds=[], atom_templates=[template])})
    assert REGISTRY.verify_refs(spec(("reply-valid", ["priority", "price"]), ("turn-posted", []), ("answer-recorded", ["m-1"]))) == []
    found = REGISTRY.verify_refs(spec(("reply-valid", ["priority"]), ("lint", []), ("turn-posted", ["x"])))
    assert sorted(v.code for v in found) == ["bad_check_args", "bad_check_args", "unknown_check"]


# ---- the parts -----------------------------------------------------------------------------------------------------------

def test_constraint_and_work_defaults_and_bounds():
    assert Constraint(text="Other sections stay unchanged").check is None
    assert violations(lambda: Constraint(text=""))
    w = Work(dispatch_kind="llm")
    assert (w.how_kind, w.steps, w.agent, w.ref) == ("AI", "", None, None)
    assert Work(dispatch_kind="skill", ref="sutra:plan").ref == "sutra:plan"
    assert said(violations(lambda: Work(dispatch_kind="shell")), "literal_error")
    assert said(violations(lambda: Work(dispatch_kind="llm", how_kind="human")), "literal_error")


def test_expected_item_kinds_target_forms_and_met():
    item = ExpectedItem(text="The contact section", kind="section", target="#contact")
    assert (item.count, item.steps, item.met) == (1, [], None)
    assert ExpectedItem(text="Facts", kind="facts", target=["a", "b"], met=True).met is True
    for kind in ("heading", "ids", "send"):       # the kinds J2's document and deed atoms use
        assert ExpectedItem(text="x", kind=kind, target="t").kind == kind
    assert said(violations(lambda: ExpectedItem(text="x", kind="page", target="t")), "literal_error")
    assert said(violations(lambda: ExpectedItem(text="x", kind="element", target="#a", count=0)), "greater_than_equal")
    assert said(violations(lambda: ExpectedItem(text="x", kind="facts", target=[str(n) for n in range(21)])), "too_long")


def test_a_behavior_step_starts_with_a_known_verb_and_at_most_three_waits():
    ok = ["set #size L", "click #go", "scroll-to #menu", "wait 1", "wait 1", "wait 2", "expect-visible #a", "expect-hidden #b",
          "expect-text #t hi", "expect-number #n 1+2"]
    assert all(step.split()[0] in BEHAVIOR_VERBS for step in ok)
    item = ExpectedItem(text="works", kind="behavior", target="#go", steps=ok[:8])
    assert len(item.steps) == 8
    assert said(violations(lambda: ExpectedItem(text="x", kind="behavior", target="#a", steps=["tap #go"])), "value_error", "tap")
    four = ["wait 1", "wait 1", "wait 1", "wait 1"]
    assert said(violations(lambda: ExpectedItem(text="x", kind="behavior", target="#a", steps=four)), "value_error", "at most 3 wait")
    assert ExpectedItem(text="x", kind="behavior", target="#a", steps=four[:3]).steps == four[:3]
    assert said(violations(lambda: ExpectedItem(text="x", kind="behavior", target="#a", steps=["click #a"] * 9)), "too_long")


def test_check_result_attempt_is_1_to_3():
    assert CheckResult(attempt=3, exit_code=127, ts=1).evidence == ""
    for attempt in (0, 4):
        assert violations(lambda a=attempt: CheckResult(attempt=a, exit_code=0, ts=1))
    assert said(violations(lambda: CheckResult(attempt=1, exit_code="0", ts=1)), "int_type")
    assert violations(lambda: CheckResult(attempt=1, exit_code=0, ts=-1))


def test_check_fields_and_bounds():
    c = Check(template="file-exists", args=["a.html"])
    assert (c.text, c.expect, c.relevance, c.relevance_source, c.target_sha256, c.results) == ("", None, None, "declared", None, [])
    assert Check(template="element-count", args=["#a"], expect=True).expect is True and Check(template="element-count", expect=2).expect == 2
    assert said(violations(lambda: Check(template="element-count", expect="1")), "int_type")
    assert said(violations(lambda: Check(template="named-test", args=["t.sh"], target_sha256="XYZ")), "string_pattern_mismatch")
    assert said(violations(lambda: Check(template="file-exists", args=["a"] * 9)), "too_long")
    assert said(violations(lambda: Check(template="lint")), "literal_error")
    assert said(violations(lambda: Check(template="file-exists", args=[""])), "string_too_short")
    assert said(violations(lambda: Check(template="file-exists", args=["a"], results=[CheckResult(attempt=1, exit_code=0, ts=1)] * 4)), "too_long")


@pytest.mark.parametrize("template,args", [("reply-valid", ["priority"]), ("reply-valid", ["a", "b", "c"]), ("answer-recorded", []),
                                           ("turn-posted", ["x"]), ("charter-stamp", ["x"]), ("workable", ["x", "y"])])
def test_the_registry_checks_take_exactly_their_arguments(template, args):
    assert said(violations(lambda: Check(template=template, args=args)), "value_error", template)


def test_registry_checks_with_their_arguments_are_fine():
    assert Check(template="reply-valid", args=["priority", "price|counter"]).args == ["priority", "price|counter"]
    assert Check(template="answer-recorded", args=["m-14"]).args == ["m-14"]
    assert all(Check(template=n).args == [] for n in REGISTRY_CHECKS if n not in ("reply-valid", "answer-recorded"))


def test_verify_holds_at_most_12_checks_and_edges_and_refusals_are_closed():
    assert said(violations(lambda: Verify(checks=[check()] * 13)), "too_long")
    assert violations(lambda: AtomEdge(atom="atom-1", why="x")) and violations(lambda: AtomEdge(atom=ATOM_ID, why=""))
    assert AtomEdge(atom="W-2.a1", why="its section was listed").atom == "W-2.a1"
    assert violations(lambda: Refusal(code="", message="x")) and violations(lambda: Refusal(code="x", message="y" * 601))
    assert said(violations(lambda: OutputItem(verb="build", name="n", form="page", ref="r")), "literal_error")
    assert violations(lambda: Verify(checks=[], extra=1))


def test_sentences_and_default_relevance():
    assert check_sentence(check("file-exists")) == "the file site/index.html exists and is not empty"
    assert check_sentence(check("file-exists", ["a", "b"])) == "the files a, b exist and are not empty"
    assert check_sentence(check("grep-count")) == 'the text "Contact" appears in site/index.html'
    assert check_sentence(check("named-test")) == "the test tests/form.sh passes"
    assert check_sentence(check("element-count", ["#a"])) == "element-count"
    assert check_sentence(check("turn-posted", text="The turn posted a message")) == "The turn posted a message"
    assert default_relevance(check("file-exists")) == "declared: file-exists on site/index.html"
    assert default_relevance(check("element-count", [])) == "declared: element-count on ?"
    assert default_relevance(check("turn-posted", text="The turn posted a message")) == "The turn posted a message"
    assert default_relevance(check("turn-posted")) == "declared: turn-posted"


# ---- the Atom ------------------------------------------------------------------------------------------------------------

SPEC_CLOSED = {
    "kind": "atom", "schema_version": 1, "id": ATOM_ID, "node_id": "sales.adaptation", "goal": "Visitors can open the contact form",
    "state": "closed", "attempt": 2, "closed_by": "verify",
    "work": {"dispatch_kind": "llm", "agent": "Builder", "steps": "Create #contact", "how_kind": "AI"}, "touches": ["site/"],
    "ts_open": 100, "ts_closed": 120,
    "verify": {"checks": [{"template": "file-exists", "args": ["site/index.html"], "relevance": "declared: file-exists on site/index.html",
                           "relevance_source": "default",
                           "results": [{"attempt": 1, "exit_code": 1, "evidence": "missing", "ts": 110},
                                       {"attempt": 2, "exit_code": 0, "evidence": "present", "ts": 120}]}]},
}


def test_the_closed_atom_of_the_design_validates_and_goes_through_the_gate():
    atom = Atom.model_validate(SPEC_CLOSED)
    checked = GATE.check("atom", SPEC_CLOSED)
    assert checked.model == atom and checked.family == "atom" and checked.kind == "atom"
    assert json.loads(checked.json)["state"] == "closed"
    assert GATE.check("atom", json.loads(checked.json)).sha256 == checked.sha256


def test_an_open_atom_is_an_atom_draft_and_a_record():
    atom = opened()
    assert isinstance(atom, AtomDraft) and (atom.kind, atom.schema_version, Atom.FAMILY) == ("atom", 1, "atom")
    assert (atom.state, atom.attempt, atom.ts_closed, atom.abandon_code, atom.produced, atom.details) == ("open", 0, None, None, [], {})
    assert GATE.check("atom", atom).model == atom


def test_registered_under_the_design_names():
    assert REGISTRY.kinds("atom") == {"atom": Atom}
    assert REGISTRY.kinds("atom_ledger_row")["atom_ledger_row"].__name__ == "LedgerRow"
    assert REGISTRY.is_payload("atom_view") and REGISTRY.versions("atom_view") == [1]
    for family in ("atom", "atom_ledger_row", "atom_view"):
        assert REGISTRY.json_schema(family)


def test_rules_three_and_seven_hold_for_the_atom_classes():
    """Every str and list is bounded; the one alias is AtomView.schema (a Python-reserved name in pydantic)."""
    for family in ("atom", "atom_ledger_row", "atom_view"):
        for cls in set(REGISTRY.kinds(family).values()):
            assert unbounded_fields(cls) == [], cls
            assert aliased_fields(cls) in ([], [("AtomView", "schema")]), cls


def test_evolve_checks_the_atom_again():
    atom = opened()
    assert atom.evolve(notes="hello").notes == "hello"
    assert violations(lambda: atom.evolve(attempt=4))
    assert violations(lambda: atom.evolve(attempt=1))          # one attempt but no result: V6


def test_ids_pattern_and_extra_keys():
    atom = opened()
    assert said(violations(lambda: Atom.model_validate(fields(atom, id="atom-1"))), "string_pattern_mismatch")
    assert said(violations(lambda: Atom.model_validate(fields(atom, state="done"))), "literal_error")
    assert said(violations(lambda: Atom.model_validate({**fields(atom), "colour": "red"})), "extra_forbidden")
    assert said(violations(lambda: Atom.model_validate(fields(atom, workflow_id="W-x"))), "string_pattern_mismatch")
    assert Atom.model_validate(fields(atom, workflow_id="W-12", department_id="sales", task_id="tsk_1", session_id="3f9a1c2b7d")).task_id == "tsk_1"
    assert said(violations(lambda: Atom.model_validate(fields(atom, closed_by="human"))), "literal_error")


def test_task_and_session_ids_are_bounded_strings():
    atom = opened()
    for field in ("task_id", "session_id"):
        assert Atom.model_validate(fields(atom, **{field: "x" * 64})).model_dump()[field] == "x" * 64
        for bad in ("", "x" * 65):
            assert violations(lambda f=field, b=bad: Atom.model_validate(fields(atom, **{f: b})))


class Ctx:
    """What a store hands the gate: the stored models by (family, id)."""

    def __init__(self, found):
        self.found = found

    def get(self, family, id):
        return self.found.get((family, id))


def test_the_gates_cross_rule_lets_an_atom_supersede_only_an_abandoned_one():
    gone = abandon(opened(), "stopped").atom
    nxt = opened(id="a-3f9a1c2b7d-02", supersedes=gone.id, abandoned_ids={gone.id})
    assert GATE.check("atom", nxt, ctx=Ctx({("atom", gone.id): gone})).model == nxt
    for found in ({("atom", gone.id): opened()}, {}):
        with pytest.raises(GateError) as caught:
            GATE.check("atom", nxt, ctx=Ctx(found))
        assert caught.value.stage == "cross"


# ---- V1 to V4: the plugin's open-time rules, as model rules --------------------------------------------------------------

@pytest.mark.parametrize("goal,code", [("", "goal_missing"), ("done", "goal_banal"), ("DONE", "goal_banal"), ("It Runs", "goal_banal"),
                                       ("no errors", "goal_banal"), ("works", "goal_banal"), ("fixed", "goal_banal")])
def test_goal_rules(goal, code):
    rule = open_rules(draft(goal=goal))
    assert rule is not None and rule.code == code
    assert said(violations(lambda: Atom.model_validate(fields(opened(), goal=goal))), "value_error", code)


@pytest.mark.parametrize("goal", ["done.", "all done", "Visitors can open the contact form", "ok then"])
def test_a_goal_is_banal_only_when_it_is_exactly_a_banal_phrase(goal):
    assert open_rules(draft(goal=goal)) is None


def test_an_atom_needs_a_check():
    no_checks = AtomDraft(goal="Visitors can open the contact form", work=work())
    assert open_rules(no_checks).code == "verify_missing"
    assert said(violations(lambda: Atom.model_validate(fields(opened(), verify={"checks": []}))), "value_error", "verify_missing")


@pytest.mark.parametrize("make,code", [
    (lambda: check("grep-count", ["x", "a.html"]), "bad_args"),
    (lambda: check("grep-count", ["x", "a.html", "1", "2"]), "bad_args"),
    (lambda: check("grep-count", ["x", "a.html", "many"]), "bad_args"),
    (lambda: check("grep-count", ["x", "a.html", "-1"]), "bad_args"),
    (lambda: check("file-exists", []), "bad_args"),
    (lambda: check("named-test", []), "bad_args"),
    (lambda: check("grep-count", ["x", "a.html", "0"]), "vacuous_check"),
    (lambda: check("grep-count", ["x", "a.html", "00"]), "vacuous_check"),
    (lambda: check("file-exists", relevance=""), "relevance_empty"),
    (lambda: check("named-test", target_sha256=None).evolve(target_sha256=None), "pin_missing"),
    (lambda: check("file-exists", ["../secret"]), "dotdot"),
    (lambda: check("file-exists", ["site/a..b.html"]), "dotdot"),
    (lambda: check("grep-count", ["x", "../a.html", "1"]), "dotdot"),
])
def test_check_rules_of_the_plugin(make, code):
    rule = open_rules(draft(make()))
    assert rule is not None and rule.code == code
    atom = opened()
    assert said(violations(lambda: Atom.model_validate(fields(atom, verify={"checks": [make().model_dump()]}))), "value_error", code)


def test_grep_count_with_a_positive_min_and_the_other_templates_are_fine():
    for ok in (check("grep-count", ["x", "a.html", "1"]), check("grep-count", ["x", "a.html", "25"]), check("file-exists", ["a", "b"]),
               check("named-test"), check("element-count", ["#a"], expect=1), check("facts-present", ["Brew Lab"]), check("behavior-steps")):
        assert open_rules(draft(ok)) is None


def test_the_pattern_of_a_grep_count_may_hold_dots():
    assert open_rules(draft(check("grep-count", ["a..b", "site/a.html", "1"]))) is None      # only the file is a path


@pytest.mark.parametrize("path,touches,outputs,outside", [
    ("site/index.html", ["site/"], [], False), ("site", ["site/"], [], True), ("site/", ["site/"], [], True),
    ("site/a/b.html", ["site/"], [], False), ("other.html", ["site/"], [], True), ("site/index.html", [], ["site/index.html"], False),
    ("site/index.html", ["site/index.html"], [], False), ("site/index.html", ["site/index.htm"], [], True),
    ("site/x.html", ["docs/"], ["site/"], False), ("site/index.html", [], [], False), ("site/index.html", ["../"], [], True),
])
def test_the_envelope_a_directory_covers_only_what_is_strictly_under_it(path, touches, outputs, outside):
    rule = open_rules(draft(check("file-exists", [path]), touches=touches, outputs=outputs))
    assert (rule.code if rule else None) == ("outside_envelope" if outside else None)


def test_the_envelope_covers_every_file_exists_path_and_the_grep_count_file_but_not_other_templates():
    assert open_rules(draft(check("file-exists", ["site/a.html", "other.html"]), touches=["site/"])).code == "outside_envelope"
    assert open_rules(draft(check("grep-count", ["x", "other.html", "1"]), touches=["site/"])).code == "outside_envelope"
    assert open_rules(draft(check("grep-count", ["x", "site/a.html", "1"]), touches=["site/"])) is None
    assert open_rules(draft(check("element-count", ["#a"]), check("turn-posted"), touches=["site/"])) is None


def test_relevance_defaults_are_a_stored_rule_not_a_draft_rule():
    assert open_rules(draft(check("file-exists"))) is None                # a draft may leave relevance out (None)
    atom = opened()
    assert all(c.relevance for c in atom.verify.checks)
    blank = {"checks": [check("file-exists", relevance=None).model_dump()]}
    assert said(violations(lambda: Atom.model_validate(fields(atom, verify=blank))), "value_error", "relevance_empty")


def test_open_rules_reports_the_first_rule_in_the_plugins_order():
    banal_and_vacuous = draft(check("grep-count", ["x", "a.html", "0"]), goal="done")
    assert open_rules(banal_and_vacuous).code == "goal_banal"
    assert open_rules(banal_and_vacuous, other_open=ATOM_ID).code == "atom_still_open"
    bad_then_vacuous = draft(check("grep-count", ["x", "a.html", "0"]), check("file-exists", []))
    assert open_rules(bad_then_vacuous).code == "bad_args"
    assert open_rules(draft(check("named-test", ["../t.sh"], target_sha256=None), check("file-exists", ["../a"]))).code == "pin_missing"
    assert open_rules(draft(check("file-exists", ["../a"]), touches=["site/"])).code == "dotdot"
    assert open_rules(draft(check("file-exists", ["a"]), touches=["site/"], supersedes=ATOM_ID), abandoned_ids=()).code == "outside_envelope"


def test_the_two_context_rules_run_only_when_the_caller_gives_the_context():
    d = draft(supersedes="a-3f9a1c2b7d-07")
    assert open_rules(d) is None and open_rules(d, None, None) is None            # the model passes neither
    assert open_rules(d, None, ()).code == "bad_supersedes"
    assert open_rules(d, None, {"a-3f9a1c2b7d-07"}) is None
    assert open_rules(draft(), ATOM_ID).code == "atom_still_open"
    assert open_rules(draft(), SimpleNamespace(id=ATOM_ID)).code == "atom_still_open"


# ---- V5: what each state requires -----------------------------------------------------------------------------------------

def test_open_atom_rules_of_v5():
    atom = opened()
    for name, value in (("ts_closed", 5), ("closed_by", "verify"), ("reason", "why")):
        assert said(violations(lambda n=name, v=value: Atom.model_validate(fields(atom, **{n: v}))), "value_error", "open atom must not")
    refusal = Refusal(code="x", message="y").model_dump()
    assert said(violations(lambda: Atom.model_validate(fields(atom, refusal=refusal))), "value_error", "open atom must not have a refusal")


def test_closed_atom_rules_of_v5():
    ok = closed()
    assert said(violations(lambda: Atom.model_validate(fields(ok, closed_by=None))), "value_error", "must be closed_by verify")
    assert said(violations(lambda: Atom.model_validate(fields(ok, ts_closed=None))), "value_error", "ts_closed")
    failing = tried(opened(), 1)
    assert said(violations(lambda: Atom.model_validate(fields(failing, state="closed", closed_by="verify", ts_closed=130))),
                "value_error", "must have a passing last result")
    assert said(violations(lambda: Atom.model_validate(fields(opened(), state="closed", closed_by="verify", ts_closed=130))), "value_error", "attempt")
    one_fails = close_with(opened(check("file-exists"), check("grep-count")), 1, 0).atom          # every check must pass, not just one
    assert said(violations(lambda: Atom.model_validate(fields(one_fails, state="closed", closed_by="verify", ts_closed=130))),
                "value_error", "must have a passing last result")
    assert said(violations(lambda: Atom.model_validate(fields(ok, abandon_code="manual"))), "value_error", "only an abandoned atom may")


def test_abandoned_atom_rules_of_v5():
    base = fields(opened(), state="abandoned", closed_by="manual-override", ts_closed=130)
    assert said(violations(lambda: Atom.model_validate({**base, "reason": ""})), "string_too_short")
    assert said(violations(lambda: Atom.model_validate({**base, "reason": None})), "value_error", "abandoned atom must have a reason")
    assert said(violations(lambda: Atom.model_validate({**base, "reason": "why", "closed_by": "verify"})), "value_error", "must be closed_by manual-override")
    assert said(violations(lambda: Atom.model_validate({**base, "reason": "why", "ts_closed": None})), "value_error", "must have ts_closed")
    assert said(violations(lambda: Atom.model_validate({**base, "reason": "why", "abandon_code": "crash"})), "literal_error")
    assert Atom.model_validate({**base, "reason": "why"}).abandon_code == "manual"        # the default code


def test_an_abandon_code_is_only_for_an_abandoned_atom():
    atom = opened()
    assert said(violations(lambda: Atom.model_validate(fields(atom, abandon_code="manual"))), "value_error", "only an abandoned atom may")
    assert said(violations(lambda: Atom.model_validate(fields(atom, abandon_code="crash"))), "literal_error")
    for code in ("verify_failed", "run_ended", "replaced", "manual"):
        assert verify_failed_atom().abandon_code == "verify_failed"
        assert Atom.model_validate({**fields(opened(), state="abandoned", closed_by="manual-override", ts_closed=130, reason="r"),
                                    "abandon_code": code}).abandon_code == code


def test_refused_atom_rules_of_v5_and_a_refused_atom_records_what_was_refused():
    r = refused()
    assert (r.state, r.attempt, r.ts_closed, r.closed_by) == ("refused", 0, 100, None) and r.goal == "done"
    empty = AtomDraft(work=work())            # no goal, no check: allowed, because it records what was refused
    again = Atom.model_validate({**fields(r), "goal": "", "verify": {"checks": []}})
    assert again.goal == "" and empty.verify.checks == []
    for change, word in (({"attempt": 1}, "attempt must be 0"), ({"refusal": None}, "must record its refusal"), ({"ts_closed": None}, "must have ts_closed"),
                         ({"closed_by": "verify"}, "must not have closed_by"), ({"supersedes": ATOM_ID}, "supersedes nothing")):
        assert said(violations(lambda c=change: Atom.model_validate({**fields(r), **c})), "value_error", word)


def test_a_refused_atom_is_not_held_to_the_open_time_rules():
    r = refused(goal="")
    assert r.refusal.code == "goal_missing" and r.verify.checks[0].relevance is None          # the draft as it was refused
    assert GATE.check("atom", r).model == r


# ---- V6 and the remaining field rules ------------------------------------------------------------------------------------

def test_every_check_has_one_result_per_attempt_in_order():
    one = tried(opened(), 1)
    assert one.attempt == 1 and all(len(c.results) == 1 for c in one.verify.checks)
    assert said(violations(lambda: Atom.model_validate(fields(one, attempt=2))), "value_error", "one result per attempt")
    assert said(violations(lambda: Atom.model_validate(fields(opened(), attempt=1))), "value_error", "one result per attempt")
    swapped = tried(opened(), 2).model_dump()
    swapped["verify"]["checks"][0]["results"].reverse()
    assert said(violations(lambda: Atom.model_validate(swapped)), "value_error", "numbered")
    assert said(violations(lambda: Atom.model_validate(fields(one, attempt=4))), "less_than_equal")


def test_details_keys_come_from_a_short_list():
    atom = opened()
    keys = {"selectors": ["#a"], "ids": ["a"], "section": "W-1", "anchor": "hero", "elements": ["#a"], "scope": "self", "channel": "email",
            "mode": "mock", "sent": True}
    assert Atom.model_validate(fields(atom, details=keys)).details == keys
    assert said(violations(lambda: Atom.model_validate(fields(atom, details={"colour": "red"}))), "value_error", "colour")


def test_every_violation_of_one_atom_is_reported_together():
    vs = violations(lambda: Atom.model_validate(fields(opened(), state="closed", goal="done", verify={"checks": []})))
    codes = {v.message.split(":")[0] for v in vs}
    assert {"goal_banal", "verify_missing"} <= codes and any("closed_by" in v.message for v in vs)


def test_the_plugin_fields_are_kept_as_given():
    atom = opened(constraints=[Constraint(text="Create only #contact", check="grep")], context=["charter item 1"], touches=["site/"],
                  outputs=["site/index.html"], model="sonnet", effort="high",
                  expected=[ExpectedItem(text="The contact section", kind="section", target="#contact")],
                  depends_on=[AtomEdge(atom="W-2.a1", why="it builds the page")])
    assert (atom.constraints[0].check, atom.context, atom.touches, atom.outputs, atom.model, atom.effort) == \
        ("grep", ["charter item 1"], ["site/"], ["site/index.html"], "sonnet", "high")
    assert atom.expected[0].target == "#contact" and atom.depends_on[0].atom == "W-2.a1"
    assert GATE.check("atom", atom).model == atom


def test_a_registry_check_opens_with_its_own_sentence_as_relevance():
    atom = opened(check("reply-valid", ["priority", "price"], text="The reply is a valid price"), check("turn-posted"))
    first, second = atom.verify.checks
    assert (first.relevance, first.relevance_source) == ("The reply is a valid price", "default")
    assert (second.relevance, second.relevance_source) == ("declared: turn-posted", "default")


def test_module_public_names_exist():
    for name in atom_module.__all__:
        assert hasattr(atom_module, name), name
