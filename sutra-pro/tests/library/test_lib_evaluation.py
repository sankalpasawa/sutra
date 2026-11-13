"""Evaluation (library design section 5): Finding, RubricResult, ConditionResult and the four kinds of the family
"evaluation": result, recheck, plan, run.

The rows are J2's own, from audits.json, conditions.json and report.json that J2 33aeeda wrote in mock mode (and, for
WITHDRAWN and the assumptions of a condition, from its saved runs), trimmed to what a test needs."""
import pytest
from pydantic import ValidationError

from sutra_app.library import evaluation as evaluation_module
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.evaluation import (
    PLAN_GATE, AgentReview, ConditionResult, Evaluation, Finding, JudgeAnswer, LldComparison, PlanEvaluation,
    RecheckEvaluation, RecheckResult, ResultEvaluation, RubricResult, RunReview,
)
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY

PASSING = {"PASS", "PASS_WITH_WARNING", "WITHDRAWN"}
ALL_VERDICTS = ["PASS", "PASS_WITH_WARNING", "NEEDS_REVISION", "BLOCKED_BY_EVIDENCE", "POLICY_CONCERN", "TO_BE_CONFIRMED", "UNPAID", "WITHDRAWN"]


def row(n: int = 1, verdict: str = "PASS", **change) -> dict:
    """A result row as J2 `_audit_findings` writes it (J2:8909)."""
    return {"id": f"F-{n}", "criterion": f"Item {n} is shown", "verdict": verdict, "note": "Section present in the page",
            "severity": "low", "confidence": "high", "needs_requester_fact": None, "item": n, "pass": verdict in PASSING, **change}


RUBRIC_ROW = {"id": "R-1", "item": "R-1", "criterion": "Consistent styling: the whole page follows the style guide", "verdict": "PASS",
              "note": "Mock: looks fine in the measurements", "rubric": True, "severity": "medium", "pass": True}
COND_N1 = {"id": "N1", "text": "The page opens (it parses, tags balanced)", "check": "page-parses", "met": True, "evidence": "page parses, tags balanced"}
COND_P8 = {"id": "P8", "text": "Each numeric success metric states its measurement window", "check": "metric-window", "met": False,
           "evidence": "no measurement window: G1 | average in-room wait under 10 minutes", "severity": "warn"}
MECHANICAL = {"available": True, "bytes": 3842, "broken_in_page_links": [], "forms": 1, "phone": {"width": 360, "overflow_px": 0},
              "desktop": {"width": 1280, "overflow_px": 0}, "js_errors": [], "design": {}, "form_results": [{"index": 1, "ok": True}]}


def entry(**change) -> dict:
    """A website audit entry as J2 writes it, with the `kind` that whoever checks audits.json adds."""
    return {"kind": "result", "cycle": 2, "version": 5, "results": [row(1), row(2, "PASS_WITH_WARNING")], "extra_issues": [],
            "rubric": [RUBRIC_ROW], "mechanical": MECHANICAL, "screenshot": None, "all_pass": True, "conditions": [COND_N1], **change}


def problems(cls, data) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        cls.model_validate(data)
    return [(".".join(str(p) for p in e["loc"]), e["type"]) for e in error.value.errors()]


def refused(data, family="evaluation") -> list[tuple[str, str]]:
    with pytest.raises(GateError) as error:
        GATE.check(family, data)
    return [(v.path, v.code) for v in error.value.violations]


# ---- Finding ------------------------------------------------------------------------------------------------------

def test_a_result_row_of_j2_is_a_finding_and_dumps_with_its_wire_key_pass():
    finding = Finding.model_validate(row(1))
    assert (finding.id, finding.item, finding.verdict, finding.passed) == ("F-1", 1, "PASS", True)
    dumped = finding.model_dump(mode="json", by_alias=True)
    assert dumped["pass"] is True and "passed" not in dumped
    assert Finding.model_validate(dumped) == finding


@pytest.mark.parametrize("verdict", ALL_VERDICTS)
def test_every_verdict_j2_writes_is_a_finding_verdict_and_pass_follows_it(verdict):
    assert Finding.model_validate(row(3, verdict)).passed is (verdict in PASSING)


def test_the_flag_can_be_given_by_name_too():
    assert Finding.model_validate({**{k: v for k, v in row(1).items() if k != "pass"}, "passed": True}).passed is True


def test_a_pass_needs_evidence_but_a_failure_does_not():
    assert problems(Finding, row(1, note="")) == [("note", "value_error")]
    assert problems(Finding, row(1, "PASS_WITH_WARNING", note="")) == [("note", "value_error")]
    for verdict in ("NEEDS_REVISION", "BLOCKED_BY_EVIDENCE", "POLICY_CONCERN", "TO_BE_CONFIRMED", "UNPAID", "WITHDRAWN"):
        assert Finding.model_validate(row(1, verdict, note=""))


def test_the_stored_flag_may_not_contradict_the_verdict():
    assert problems(Finding, row(1, "PASS", **{"pass": False})) == [("pass", "value_error")]
    assert problems(Finding, row(1, "NEEDS_REVISION", **{"pass": True})) == [("pass", "value_error")]
    assert problems(Finding, row(1, "UNPAID", **{"pass": True})) == [("pass", "value_error")]       # J2:9180 sets it false
    assert problems(Finding, row(1, "WITHDRAWN", **{"pass": False})) == [("pass", "value_error")]    # J2:5079 sets it true


def test_both_rules_are_reported_together():
    assert sorted(problems(Finding, row(1, "PASS", note="", **{"pass": False}))) == [("note", "value_error"), ("pass", "value_error")]


def test_an_extra_issue_has_no_pass_flag_whatever_its_verdict():
    extra = {k: v for k, v in row(9, "PASS_WITH_WARNING").items() if k not in ("pass", "item")}
    finding = Finding.model_validate(extra)
    assert finding.passed is None and finding.item is None


def test_a_forced_test_row_and_a_renamed_audit_id_are_known_keys():
    forced = row(2, "NEEDS_REVISION", forced_test=True, real_verdict="PASS: Section present in the page", audit_id="F-extra")
    assert Finding.model_validate(forced).real_verdict.startswith("PASS")


@pytest.mark.parametrize("change, where, code", [
    ({"id": "X-1"}, "id", "string_pattern_mismatch"),
    ({"id": "F-"}, "id", "string_pattern_mismatch"),
    ({"verdict": "OK", "pass": None}, "verdict", "literal_error"),
    ({"verdict": "pass", "pass": None}, "verdict", "literal_error"),
    ({"severity": "urgent"}, "severity", "literal_error"),
    ({"confidence": "certain"}, "confidence", "literal_error"),
    ({"item": -1}, "item", "greater_than_equal"),
    ({"note": "n" * 2001}, "note", "string_too_long"),
    ({"criterion": "c" * 601}, "criterion", "string_too_long"),
    ({"colour": "red"}, "colour", "extra_forbidden"),
    ({"pass": "true"}, "pass", "bool_type"),
])
def test_a_finding_refuses(change, where, code):
    assert (where, code) in problems(Finding, {**row(1), **change})


def test_the_ids_j2_gives_a_missing_item_and_a_skipped_one_are_findings_ids():
    assert Finding.model_validate(row(3, "BLOCKED_BY_EVIDENCE", id="F-missing-3")).id == "F-missing-3"
    assert ("id", "missing") in problems(Finding, {k: v for k, v in row(1).items() if k != "id"})


# ---- RubricResult, ConditionResult, LldComparison ------------------------------------------------------------------

def test_a_rubric_row_as_j2_stores_it():
    rubric = RubricResult.model_validate(RUBRIC_ROW)
    assert (rubric.id, rubric.passed, rubric.rubric, rubric.severity, rubric.item) == ("R-1", True, True, "medium", "R-1")
    assert RubricResult.model_validate({"id": "D-5", "verdict": "PASS", "note": "read from the text", "pass": True})      # the design's minimum


@pytest.mark.parametrize("verdict, passed", [("BLOCKED_BY_EVIDENCE", False), ("NEEDS_REVISION", False), ("WITHDRAWN", True), ("PASS_WITH_WARNING", True)])
def test_a_rubric_row_can_be_blocked_by_evidence_or_withdrawn(verdict, passed):
    """J2:9195 writes BLOCKED_BY_EVIDENCE for a missing or unproven rubric item; a settled dispute writes WITHDRAWN."""
    assert RubricResult.model_validate({**RUBRIC_ROW, "verdict": verdict, "pass": passed}).passed is passed


@pytest.mark.parametrize("change, where, code", [
    ({"id": "X1"}, "id", "string_pattern_mismatch"), ({"id": "R-"}, "id", "string_pattern_mismatch"),
    ({"verdict": "POLICY_CONCERN", "pass": False}, "verdict", "literal_error"),
    ({"verdict": "PASS", "pass": False}, "pass", "value_error"), ({"note": ""}, "note", "value_error"),
    ({"severity": "huge"}, "severity", "literal_error"), ({"colour": 1}, "colour", "extra_forbidden"),
])
def test_a_rubric_row_refuses(change, where, code):
    assert (where, code) in problems(RubricResult, {**RUBRIC_ROW, **change})


def test_a_rubric_row_must_say_whether_it_passed():
    assert ("pass", "missing") in problems(RubricResult, {k: v for k, v in RUBRIC_ROW.items() if k != "pass"})


def test_a_condition_as_code_checks_it():
    assert ConditionResult.model_validate(COND_N1).check == "page-parses"
    warn = ConditionResult.model_validate(COND_P8)
    assert (warn.met, warn.severity) == (False, "warn")
    several = {"id": "H3", "text": "Components have unique ids", "check": ["ids-sequential", "components-have-responsibility"],
               "met": True, "evidence": "ok"}
    assert ConditionResult.model_validate(several).check == ["ids-sequential", "components-have-responsibility"]
    P4 = {"id": "P4", "text": "No invented facts", "check": "no-invented-facts", "met": False, "evidence": "not in the charter: 9198450123457",
          "assumptions": ["Pre-orders are counted from the order emails received at hello@brewlab.example."]}
    assert ConditionResult.model_validate(P4).assumptions == [P4["assumptions"][0]]
    assert ConditionResult.model_validate({"id": "N2", "met": True, "evidence": "ok"}).text == ""         # the design's minimum


@pytest.mark.parametrize("change, expected", [
    ({"id": "n1"}, [("id", "string_pattern_mismatch")]), ({"id": "NNNNN1"}, [("id", "string_pattern_mismatch")]),
    ({"id": "N"}, [("id", "string_pattern_mismatch")]), ({"severity": "error"}, [("severity", "literal_error")]),
    ({"met": "yes"}, [("met", "bool_type")]), ({"verdict": "PASS"}, [("verdict", "extra_forbidden")]),
    ({"assumptions": ["a"] * 101}, [("assumptions", "too_long")]),
    ({"check": 5}, [("check.constrained-str", "string_type"), ("check.list[constrained-str]", "list_type")]),
    ({"check": ["a"] * 9}, [("check.constrained-str", "string_type"), ("check.list[constrained-str]", "too_long")]),
])
def test_a_condition_refuses(change, expected):
    assert problems(ConditionResult, {**COND_N1, **change}) == expected


def test_an_lld_comparison_lists_ids_and_the_sections_that_do_not_match():
    lld = LldComparison.model_validate({"matches": ["S1", "S2"], "mismatches": [{"section": "S3", "evidence": "no #hero on the page"}], "dropped": []})
    assert lld.mismatches[0].section == "S3"
    assert ("mismatches.0.evidence", "missing") in problems(LldComparison, {"mismatches": [{"section": "S3"}]})


# ---- the result: one audit entry ----------------------------------------------------------------------------------

def test_a_website_audit_entry_passes_the_gate_as_a_result():
    checked = GATE.check("evaluation", entry())
    assert isinstance(checked.model, ResultEvaluation) and (checked.kind, checked.family) == ("result", "evaluation")
    assert checked.model.results[1].verdict == "PASS_WITH_WARNING" and checked.model.mechanical["available"] is True


def test_a_document_audit_entry_names_its_output_and_what_audit_read():
    doc = entry(mechanical={}, rubric=[{**RUBRIC_ROW, "id": "D-1", "item": "D-1"}], conditions=[COND_N1, COND_P8], output="prd",
                read="Read prd.md v6: Problem (15 words); Users (31 words)")
    model = GATE.check("evaluation", doc).model
    assert (model.output, model.mechanical, model.conditions[1].severity) == ("prd", {}, "warn")
    assert ("output", "string_pattern_mismatch") in problems(ResultEvaluation, {**doc, "output": "PDF"})      # a name by shape
    assert GATE.check("evaluation", {**doc, "output": "business_report"}).model.output == "business_report"


def test_an_entry_can_carry_the_lld_comparison_and_what_the_requester_accepted():
    model = GATE.check("evaluation", entry(lld={"matches": ["S1"], "mismatches": [], "dropped": []}, accepted=["R-6", "Opening hours are listed"])).model
    assert model.lld.matches == ["S1"] and model.accepted == ["R-6", "Opening hours are listed"]


def test_all_pass_may_not_lie_about_a_failing_row():
    assert refused(entry(results=[row(1), row(2, "NEEDS_REVISION")])) == [("result.all_pass", "value_error")]
    assert refused(entry(rubric=[{**RUBRIC_ROW, "verdict": "NEEDS_REVISION", "pass": False}])) == [("result.all_pass", "value_error")]
    with pytest.raises(GateError, match="these rows do not pass: F-2"):
        GATE.check("evaluation", entry(results=[row(1), row(2, "UNPAID")]))
    assert GATE.check("evaluation", entry(results=[row(1), row(2, "NEEDS_REVISION")], all_pass=False)).model.all_pass is False


def test_all_pass_may_not_lie_about_a_blocking_condition_but_a_warning_never_blocks():
    unmet = {**COND_N1, "met": False, "evidence": "tags are not balanced"}
    with pytest.raises(GateError, match="these conditions are not met: N1"):
        GATE.check("evaluation", entry(conditions=[unmet]))
    assert GATE.check("evaluation", entry(conditions=[unmet], all_pass=False)).model.all_pass is False
    assert GATE.check("evaluation", entry(conditions=[COND_N1, COND_P8])).model.all_pass is True        # P8 is a warning


def test_all_pass_may_not_be_false_when_everything_passes():
    with pytest.raises(GateError, match="all_pass is false, but every result and rubric row passes"):
        GATE.check("evaluation", entry(all_pass=False))


def test_an_extra_issue_does_not_count_for_all_pass_and_has_its_own_id():
    extra = {k: v for k, v in row(9, "NEEDS_REVISION").items() if k not in ("pass", "item")}
    assert GATE.check("evaluation", entry(extra_issues=[extra])).model.extra_issues[0].passed is None


def test_a_result_with_no_rows_never_passes():
    assert GATE.check("evaluation", entry(results=[], rubric=[], all_pass=False)).model.results == []
    assert refused(entry(results=[], rubric=[], all_pass=True)) == [("result.all_pass", "value_error")]


def test_a_withdrawn_finding_makes_all_pass_a_function_of_the_rows_alone():
    """J2:5080 recomputes all_pass from results and rubric after a dispute, so a blocking condition no longer counts."""
    unmet = {**COND_N1, "met": False, "evidence": "tags are not balanced"}
    withdrawn = [row(1), row(2, "WITHDRAWN", note="Sunday is missing (withdrawn in C-1)")]
    assert GATE.check("evaluation", entry(results=withdrawn, conditions=[unmet], all_pass=True)).model.all_pass is True
    assert refused(entry(results=[*withdrawn, row(3, "NEEDS_REVISION")], conditions=[unmet], all_pass=True)) == [("result.all_pass", "value_error")]
    assert GATE.check("evaluation", entry(results=[row(2, "WITHDRAWN")], rubric=[], conditions=[], all_pass=True))
    extra = {k: v for k, v in row(9, "WITHDRAWN").items() if k not in ("pass", "item")}                 # a withdrawn extra counts too
    assert GATE.check("evaluation", entry(extra_issues=[extra], conditions=[unmet], all_pass=True))


def test_a_finding_id_is_used_once_across_results_and_extra_issues():
    twin = {k: v for k, v in row(1, "NEEDS_REVISION").items() if k not in ("pass", "item")}
    assert refused(entry(extra_issues=[twin])) == [("result.extra_issues.0.id", "value_error")]
    assert refused(entry(results=[row(1), row(1)])) == [("result.results.1.id", "value_error")]


def test_the_entry_is_closed_and_bounded():
    assert ("cycle", "greater_than_equal") in problems(ResultEvaluation, {**entry(), "cycle": 0})
    assert ("version", "greater_than_equal") in problems(ResultEvaluation, {**entry(), "version": 0})
    assert ("verdict", "extra_forbidden") in problems(ResultEvaluation, {**entry(), "verdict": "PASS"})
    assert ("results", "missing") in problems(ResultEvaluation, {k: v for k, v in entry().items() if k != "results"})
    assert ("results", "too_long") in problems(ResultEvaluation, {**entry(), "results": [row(n) for n in range(201)]})
    assert ("mechanical", "value_error") in problems(ResultEvaluation, {**entry(), "mechanical": {f"k{n}": n for n in range(501)}})


def test_an_audit_entry_has_no_kind_so_the_caller_must_add_it():
    bare = {k: v for k, v in entry().items() if k != "kind"}
    assert refused(bare) == [("", "union_tag_not_found")]
    assert refused({**bare, "kind": "audit"}) == [("", "union_tag_invalid")]


# ---- recheck ------------------------------------------------------------------------------------------------------

RECHECK = {"kind": "recheck", "trigger": "Q-1", "doc": "hld", "version": 7, "t": "2026-11-04T12:49:16",
           "results": [{"atom": "W-9.a1", "check": "The document has the heading Components.", "pass": True,
                        "evidence": "heading 'Components' found in the document"},
                       {"atom": "W-13.a1", "check": "Ids C1, C2, ... are unique.", "pass": None, "evidence": "could not run: no browser"}]}


def test_a_recheck_entry_as_j2_writes_it():
    checked = GATE.check("evaluation", RECHECK)
    assert isinstance(checked.model, RecheckEvaluation) and checked.kind == "recheck"
    assert [r.passed for r in checked.model.results] == [True, None]
    assert RecheckResult.model_validate({"atom": "W-1.a1", "check": None, "pass": False, "evidence": "x"}).check is None


@pytest.mark.parametrize("change, where, code", [
    ({"t": "2026-11-04 12:49:16"}, "t", "string_pattern_mismatch"), ({"t": "12:49:16"}, "t", "string_pattern_mismatch"),
    ({"trigger": ""}, "trigger", "string_too_short"), ({"doc": "d" * 41}, "doc", "string_too_long"), ({"version": -1}, "version", "greater_than_equal"),
    ({"results": [{"atom": "atom-1", "check": "c", "pass": True, "evidence": "e"}]}, "results.0.atom", "string_pattern_mismatch"),
    ({"results": [{"atom": "W-1.a1", "check": "c", "pass": "ok", "evidence": "e"}]}, "results.0.pass", "bool_type"),
    ({"colour": 1}, "colour", "extra_forbidden"),
])
def test_a_recheck_refuses(change, where, code):
    assert (where, code) in problems(RecheckEvaluation, {**RECHECK, **change})


# ---- plan: the confidence judge ------------------------------------------------------------------------------------

PLAN = {"kind": "plan", "workflow": "Play screen and game loop", "round": 1, "score": 0.83, "passed": True, "weakest": "done_test",
        "answers": {"I1": {"answer": "yes", "note": ""}, "D3": {"answer": "no", "note": "nothing checks a round ends at 30 s"},
                    "M2": {"answer": "n/a"}, "K4": {"answer": "yes"}, "F2": {"answer": "yes"}, "G0": {"answer": "yes"}}}


def test_a_plan_evaluation_is_a_workflow_a_score_and_the_judges_answers():
    checked = GATE.check("evaluation", PLAN)
    assert isinstance(checked.model, PlanEvaluation) and checked.model.answers["M2"] == JudgeAnswer(answer="n/a", note="")
    assert (PLAN_GATE, checked.model.weakest) == (0.80, "done_test")


@pytest.mark.parametrize("score, passed, ok", [(0.80, True, True), (0.79, False, True), (0.79, True, False), (0.80, False, False),
                                               (1, True, True), (0, False, True), (0.95, False, False)])
def test_passed_is_exactly_the_gate(score, passed, ok):
    data = {**PLAN, "score": score, "passed": passed}
    assert (not problems_or_none(PlanEvaluation, data)) is ok


def problems_or_none(cls, data):
    try:
        cls.model_validate(data)
    except ValidationError as error:
        return error.errors()
    return None


def test_a_plan_with_a_perfect_score_and_nothing_lost_has_no_weakest_check():
    perfect = PlanEvaluation.model_validate({**PLAN, "score": 0.95, "weakest": None})
    assert perfect.weakest is None
    assert PlanEvaluation.model_validate({k: v for k, v in PLAN.items() if k != "weakest"}).weakest is None


@pytest.mark.parametrize("change, where, code", [
    ({"round": 4}, "round", "less_than_equal"), ({"round": -1}, "round", "greater_than_equal"),
    ({"score": 1.01, "passed": True}, "score", "less_than_equal"), ({"score": -0.1, "passed": False}, "score", "greater_than_equal"),
    ({"score": "0.9"}, "score", "float_type"), ({"weakest": "speed"}, "weakest", "literal_error"),
    ({"answers": {"i1": {"answer": "yes"}}}, "answers.i1.[key]", "string_pattern_mismatch"),
    ({"answers": {"I1": {"answer": "maybe"}}}, "answers.I1.answer", "literal_error"),
    ({"answers": {"I1": {"answer": "yes", "colour": 1}}}, "answers.I1.colour", "extra_forbidden"),
    ({"workflow": ""}, "workflow", "string_too_short"), ({"colour": 1}, "colour", "extra_forbidden"),
])
def test_a_plan_refuses(change, where, code):
    assert (where, code) in problems(PlanEvaluation, {**PLAN, **change})


# ---- run: the reviewer ---------------------------------------------------------------------------------------------

REVIEW = {"kind": "run", "verdict": "Mock run: Done: the site is workable.",
          "agents": {"identity": {"score": 4, "note": "4 turns, 0 redirects, 0 invalid moves"}, "W-1": {"score": 5, "note": ""}, "ceo": {"score": 3}},
          "went_well": ["2 conflict(s): 1 settled by the agents."], "problems": ["1 illegal route pick(s) were redirected."],
          "learnings": ["Mock replies are scripted."]}


def test_a_run_review_as_the_reviewer_writes_it():
    checked = GATE.check("evaluation", REVIEW)
    assert isinstance(checked.model, RunReview) and checked.model.agents["W-1"] == AgentReview(score=5, note="")
    assert checked.model.agents["ceo"].note == ""


def test_a_review_written_while_the_run_is_paused_holds_the_verdict_alone():
    paused = RunReview.model_validate({"kind": "run", "verdict": "Paused for the Requester; the reviewer runs when the run ends."})
    assert (paused.agents, paused.went_well, paused.raw) == ({}, [], None)
    bad_reply = RunReview.model_validate({"kind": "run", "verdict": "The reviewer's reply wasn't valid JSON.", "raw": "I think {"})
    assert bad_reply.raw == "I think {"


@pytest.mark.parametrize("change, where, code", [
    ({"verdict": ""}, "verdict", "string_too_short"), ({"agents": {"identity": {"score": 0}}}, "agents.identity.score", "greater_than_equal"),
    ({"agents": {"identity": {"score": 6}}}, "agents.identity.score", "less_than_equal"), ({"agents": {"identity": {"score": 4.5}}}, "agents.identity.score", "int_type"),
    ({"agents": {"not a key!": {"score": 4}}}, "agents.not a key!.[key]", "string_pattern_mismatch"),
    ({"went_well": ["w"] * 31}, "went_well", "too_long"), ({"learnings": [""]}, "learnings.0", "string_too_short"),
    ({"verdict": "v" * 1001}, "verdict", "string_too_long"), ({"score": 4}, "score", "extra_forbidden"),
])
def test_a_run_review_refuses(change, where, code):
    assert (where, code) in problems(RunReview, {**REVIEW, **change})


# ---- the family ---------------------------------------------------------------------------------------------------

def test_the_family_has_four_kinds_and_the_base_is_not_one_of_them():
    assert {k: c.__name__ for k, c in REGISTRY.kinds("evaluation").items()} == {
        "result": "ResultEvaluation", "recheck": "RecheckEvaluation", "plan": "PlanEvaluation", "run": "RunReview"}
    assert Evaluation.FAMILY == "evaluation" and Evaluation.ABSTRACT is True and Evaluation not in REGISTRY.kinds("evaluation").values()
    assert all(issubclass(c, Evaluation) for c in REGISTRY.kinds("evaluation").values())


def test_an_evaluation_is_versioned_and_its_canonical_form_ignores_key_order():
    assert problems(PlanEvaluation, {**PLAN, "schema_version": 2}) == [("", "value_error")]
    data = entry()
    assert GATE.check("evaluation", data).sha256 == GATE.check("evaluation", dict(reversed(list(data.items())))).sha256


def test_every_class_is_bounded_and_aliases_nothing_but_pass():
    for cls in (Finding, RubricResult, ConditionResult, LldComparison, ResultEvaluation, RecheckResult, RecheckEvaluation, JudgeAnswer,
                PlanEvaluation, AgentReview, RunReview):
        assert unbounded_fields(cls) == [], cls.__name__
        assert aliased_fields(cls) == [], cls.__name__


def test_the_module_lists_what_it_exports():
    assert all(hasattr(evaluation_module, name) for name in evaluation_module.__all__)
