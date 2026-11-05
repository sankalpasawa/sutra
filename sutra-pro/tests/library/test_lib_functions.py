"""The five function models (library design section 6, WP L5): a valid sample per kind built from J2's reply formats and
mocks, the invalid table, the transport schemas, Certainty, Conflict and Lesson.

The samples are J2's own mock replies where J2 has one (identity intake and done, priority price, coordination schedule,
audit report); the saved conflicts are two real entries of runs/j2-20261006-115833 (trimmed)."""
import copy
import itertools
import json

import pytest
from pydantic import ValidationError

from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.functions import (
    REPLY_CLASSES, SIGNALS, ZONES, Certainty, Conflict, Dispute, Factor, Lesson, Propose, certainty_zone, signal_answer,
)
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY, is_transport_safe, transport_schema
from sutra_app.library.replies import ReplyInvalid, ReplyParser

PARSER = ReplyParser()
STEP = {"kind": "ai", "id": "a1", "name": "Build the hero",
        "atom": {"goal": "Visitors see a hero banner", "work": {"dispatch_kind": "llm", "how_kind": "AI"}}}


def wf(**over):
    return {"kind": "proposed", "id": "P-1", "name": "Scaffold", "goal_gap": "no page", "outputs": ["#hero"],
            "completion_check": "hero exists", "steps": [STEP], **over}


def granted(**over):
    return {**wf(), "envelope": {"money_limit": 10}, **over}


CHARTER = {"kind": "site", "statement": "A one-page website for Brew Lab", "site_name": "Brew Lab",
           "done_when": ["The menu is shown", "Opening hours are listed", "Layout works on a phone"]}
SIGNALS_ALL_KNOWN = {k: {"answer": a, "evidence": "e"} for k, a in
                     (("broken", "no"), ("reaction", "no"), ("facts_given", "yes"), ("known_pattern", "yes"), ("open_choices", "no"))}

SAMPLES = {   # (family, kind) -> a valid reply, as J2 words it
    ("identity", "intake"): {"kind": "intake", "say": "", "to_requester": "Thanks, I have everything I need.", "to_agents":
                             "@Adaptation Charter recorded from the brief.", "enough": True, "next": "Adaptation", "goal": CHARTER},
    ("identity", "ruling"): {"kind": "ruling", "say": "Priority's position stands.", "clause": "done_when", "facts": ["budget 60"],
                             "resolved": True, "ruling": "priority", "instruction": "Register it."},
    ("identity", "heard"): {"kind": "heard", "say": "Noted.", "clause": "done_when", "decision": "continue", "add": 20,
                            "drop_items": [3], "confirmed": [{"item": 2, "fact": "07:00"}], "still_to_be_confirmed": [],
                            "instruction_to_adaptation": "Put the answer in.", "next": "Adaptation"},
    ("identity", "done"): {"kind": "done", "to_requester": "@Requester Your website is ready.", "clause": "done_when",
                           "done": True, "next": "Requester"},
    ("identity", "approval"): {"kind": "approval", "say": "The Requester approved it.", "approved": True, "budget_increase": 12},
    ("identity", "approval_ask"): {"kind": "approval_ask", "say": "Adding budget is the Requester's call.", "clause": "authority",
                                   "decision": "ASK"},
    ("adaptation", "propose"): {"kind": "propose", "say": "@Priority Proposal.", "act": "PROPOSE", "workflows": [wf()],
                                "left_out": [{"item": 3, "reason": "budget"}], "next": "Priority"},
    ("adaptation", "respond"): {"kind": "respond", "say": "@Priority Accepted.", "act": "ACCEPT", "workflows": [], "next": "Priority"},
    ("adaptation", "atom_verdict"): {"kind": "atom_verdict", "say": "@Coordination The build is wrong.", "verdict": "BUILD_WRONG",
                                     "atom": "W-1.a1", "affordable": True, "build_wrong_reason": "the form has no submit button"},
    ("adaptation", "lesson"): {"kind": "lesson", "say": "Lesson saved.", "lessons": [
        {"problem": "no viewport tag", "cause": "the first build left it out", "fix": "add the viewport meta tag"}]},
    ("priority", "price"): {"kind": "price", "say": "@Adaptation Granted.", "decision": "GRANT", "workflows": [granted()],
                            "next": "Adaptation"},
    ("priority", "envelope_check"): {"kind": "envelope_check", "say": "@Identity W-1 is over.", "reason": "calls 3/2",
                                     "decision": "REQUEST_APPROVAL", "next": "Identity"},
    ("coordination", "schedule"): {"kind": "schedule", "say": "@Priority Schedule: W-1.", "rule": "dependencies first, one writer",
                                   "order": ["W-1", "W-2"], "holds": [{"id": "W-2", "missing": "waits for W-1 to finish"}],
                                   "next": "Priority"},
    ("audit", "report"): {"kind": "report", "say": "@Identity All criteria pass.", "findings": [
        {"id": "F-1", "item": 1, "criterion": "The menu is shown", "verdict": "PASS", "severity": "low", "confidence": "high",
         "evidence": "section #menu lists 6 drinks", "needs_requester_fact": None}],
        "rubric": [{"id": "R-1", "verdict": "PASS", "evidence": "buttons are 48px"}], "next": "Identity"},
}


def make(family, kind, **over):
    return {**copy.deepcopy(SAMPLES[(family, kind)]), **over}


def parse(family, kind, **over):
    return PARSER.parse(family, json.dumps(make(family, kind, **over)), kind=kind).model


def refused(family, kind, **over):
    """The (path, message) pairs the reply is refused with."""
    with pytest.raises(ReplyInvalid) as exc:
        PARSER.parse(family, json.dumps(make(family, kind, **over)), kind=kind)
    return [(v.path, v.message) for v in exc.value.violations]


def says(found, *needles):
    text = " | ".join(f"{p}: {m}" for p, m in found)
    for needle in needles:
        assert needle in text, (needle, text)


# ---- registry and samples -------------------------------------------------------------------------------------------

def test_the_families_and_kinds_of_the_design_are_registered():
    want = {"identity": {"intake", "ruling", "heard", "done", "approval", "approval_ask"},
            "adaptation": {"propose", "respond", "atom_verdict", "lesson"}, "priority": {"price", "envelope_check"},
            "coordination": {"schedule"}, "audit": {"report"}, "conflict": {"conflict"}, "lesson": {"lesson"}}
    for family, kinds in want.items():
        assert set(REGISTRY.kinds(family)) == kinds
    assert set(SAMPLES) == set(REPLY_CLASSES) and len(REPLY_CLASSES) == 14
    for (family, kind), cls in REPLY_CLASSES.items():
        assert REGISTRY.kinds(family)[kind] is cls and cls.FAMILY == family


@pytest.mark.parametrize("family,kind", sorted(SAMPLES))
def test_a_valid_sample_per_kind_parses_and_passes_the_gate(family, kind):
    model = parse(family, kind)
    assert model.kind == kind and model.schema_version == 1
    checked = GATE.check(family, model)
    assert GATE.check(family, checked.json).sha256 == checked.sha256
    assert REGISTRY.adapter(family).validate_json(checked.json) == model


def test_say_and_reason_default_to_empty_and_reason_is_a_field_of_every_reply():
    model = PARSER.parse("priority", json.dumps({"kind": "price", "decision": "REFUSE", "next": "Identity"})).model
    assert (model.say, model.reason) == ("", "")
    assert all("reason" in cls.model_fields and "say" in cls.model_fields for cls in REPLY_CLASSES.values())
    assert list(REPLY_CLASSES[("priority", "price")].model_fields)[2] == "reason"          # reason first, after kind and schema_version


def test_the_parser_reads_j2_replies_tolerantly():
    parsed = PARSER.parse("priority", json.dumps({**make("priority", "price", decision="counter", next="adaptation"),
                                                  "colour": "red"}), kind="price")
    assert parsed.model.decision == "COUNTER" and parsed.model.next == "Adaptation"
    assert parsed.dropped_keys == ["colour"] and "decision" in parsed.normalised


def test_a_reply_that_names_no_kind_in_a_family_with_several_is_refused():
    with pytest.raises(ReplyInvalid) as exc:
        PARSER.parse("identity", json.dumps({"enough": True}))
    assert exc.value.violations[0].code == "union_tag_not_found"


# ---- the invalid table ----------------------------------------------------------------------------------------------

def test_price_rules():
    says(refused("priority", "price", decision="REFUSE"), "REFUSE funds nothing: workflows must be empty")
    says(refused("priority", "price", decision="COUNTER", workflows=[]), "COUNTER funds something")
    says(refused("priority", "price", decision="GRANT", workflows=[]), "GRANT funds something")
    says(refused("priority", "price", workflows=[granted(envelope={"money_limit": 0})]), "money_limit of at least 1")
    says(refused("priority", "price", workflows=[wf()]), "workflows.0.envelope", "money_limit")
    assert parse("priority", "price", decision="REFUSE", workflows=[], next="Identity").workflows == []
    assert parse("priority", "price", decision="COUNTER").decision == "COUNTER"
    found = refused("priority", "price", workflows=[wf(), wf(id="P-2", envelope={"money_limit": 0})])
    assert len(found) == 2                                                                # every violation, not the first
    says(refused("priority", "price", next="Audit"), "next")
    says(refused("priority", "price", decision="MAYBE"), "decision")


def test_envelope_check_rules():
    says(refused("priority", "envelope_check", decision="HOLD", next="Identity"), "HOLD goes to Coordination")
    says(refused("priority", "envelope_check", decision="REQUEST_APPROVAL", next="Coordination"), "REQUEST_APPROVAL")
    assert parse("priority", "envelope_check", decision="HOLD", next="Coordination").next == "Coordination"
    says(refused("priority", "envelope_check", next="Adaptation"), "next")


def test_schedule_rules():
    says(refused("coordination", "schedule", order=["W-1", "W-1"]), "order repeats W-1")
    says(refused("coordination", "schedule", holds=[{"id": "W-2", "missing": "a"}, {"id": "W-2", "missing": "b"}]), "holds repeats W-2")
    says(refused("coordination", "schedule", rule=""), "rule")
    says(refused("coordination", "schedule", order=["W-1 Scaffold"]), "order.0")
    says(refused("coordination", "schedule", next="Adaptation"), "every ordered workflow is held", "W-1")
    all_held = {"order": ["W-1"], "holds": [{"id": "W-1", "missing": "x"}], "next": "Adaptation"}
    assert parse("coordination", "schedule", **all_held).next == "Adaptation"
    assert parse("coordination", "schedule", order=[], holds=[], next="Adaptation").order == []
    says(refused("coordination", "schedule", holds=[{"id": "W-2", "missing": ""}]), "holds.0.missing")


def test_intake_rules():
    says(refused("identity", "intake", next="Requester"), "enough is true", "next must be Adaptation")
    says(refused("identity", "intake", goal=None), "the charter (goal) is required")
    says(refused("identity", "intake", questions=[{"question": "q?"}]), "ask no questions")
    ask = {"enough": False, "goal": None, "next": "Requester", "questions": [{"question": "What is the business called?"}]}
    assert parse("identity", "intake", **ask).questions[0].options == []
    says(refused("identity", "intake", **{**ask, "questions": []}), "ask 1 to 4 questions")
    says(refused("identity", "intake", **{**ask, "questions": [{"question": f"q{i}?"} for i in range(5)]}), "questions")
    says(refused("identity", "intake", **{**ask, "goal": CHARTER}), "enough is false", "goal must be left out")
    says(refused("identity", "intake", **{**ask, "next": "Adaptation"}), "next must be Requester")
    both = refused("identity", "intake", enough=False, goal=CHARTER, questions=[], next="Adaptation")
    assert len(both) == 3                                                                 # questions, goal, next
    assert parse("identity", "intake", goal={**CHARTER, "kind": "doc", "product_name": "QuickQueue", "site_name": "x"}).goal.kind == "doc"
    says(refused("identity", "intake", goal={"kind": "site", "statement": "s", "done_when": ["a"]}), "site_name")


def test_ruling_rules():
    says(refused("identity", "ruling", ruling=None), "ruling must name whose position stands")
    open_ = {"resolved": False, "ruling": None, "user_question": {"question": "Fund it?", "options": ["Yes", "No"]}}
    assert parse("identity", "ruling", **open_).user_question.options == ["Yes", "No"]
    says(refused("identity", "ruling", **{**open_, "user_question": None}), "ask the Requester one question")
    says(refused("identity", "ruling", **{**open_, "user_question": {"question": "Fund it?", "options": ["Yes"]}}), "at least 2 options")
    says(refused("identity", "ruling", **{**open_, "ruling": "priority"}), "give no ruling yet")
    says(refused("identity", "ruling", ruling="split"), "a split names the workflows")
    says(refused("identity", "ruling", ruling=" Split "), "a split names the workflows")
    assert parse("identity", "ruling", ruling="Split", workflows=["Scaffold"]).workflows == ["Scaffold"]
    says(refused("identity", "ruling", clause=""), "clause")


def test_heard_rules():
    says(refused("identity", "heard", decision="pause"), "decision")
    says(refused("identity", "heard", add=-1), "add")
    says(refused("identity", "heard", drop_items=[0]), "drop_items.0")
    says(refused("identity", "heard", next="Priority"), "next")
    assert parse("identity", "heard", decision=None, add=None, next="Audit").decision is None


def test_done_rules():
    says(refused("identity", "done", next="Adaptation"), "exactly when done or needs_requester")
    says(refused("identity", "done", done=False, needs_requester=False, next="Requester"), "exactly when")
    rework = {"done": False, "needs_requester": False, "next": "Adaptation"}
    assert parse("identity", "done", **rework).next == "Adaptation"
    assert parse("identity", "done", done=False, needs_requester=True, requester_questions=["The phone number?"],
                 next="Requester").needs_requester
    assert parse("identity", "done", **rework, needs_decision=True, budget_needed=40).budget_needed == 40
    says(refused("identity", "done", **rework, budget_needed=-5), "budget_needed")


def test_approval_rules():
    assert parse("identity", "approval", approved=False, budget_increase=None).budget_increase is None
    says(refused("identity", "approval", budget_increase=-1), "budget_increase")
    says(refused("identity", "approval", approved="yes"), "approved")
    ask = parse("identity", "approval_ask", user_question={"question": "Add 12 work credits?", "options": ["Yes", "No"]})
    assert ask.user_question.question.startswith("Add")
    says(refused("identity", "approval_ask", decision="MAYBE"), "decision")


def test_propose_acts():
    says(refused("adaptation", "propose", workflows=[]), "PROPOSE needs at least one workflow")
    says(refused("adaptation", "propose", act="POLICY_QUESTION", workflows=[]), "POLICY_QUESTION needs the question")
    says(refused("adaptation", "propose", act="DISPUTE", workflows=[]), "DISPUTE needs the dispute")
    ok = parse("adaptation", "propose", act="POLICY_QUESTION", workflows=[], question="May I add a gallery?", next="Identity")
    assert ok.question.startswith("May")
    dispute = parse("adaptation", "propose", act="DISPUTE", workflows=[], next="Audit",
                    dispute={"with": "Audit", "about": "F-4", "reason": "fluid widths, no overflow at 360px"}).dispute
    assert dispute.with_ == "Audit" and dispute.model_dump(by_alias=True)["with"] == "Audit"
    assert Dispute(with_="Coordination", about="W-2", reason="r").with_ == "Coordination"
    with pytest.raises(ValidationError):
        Dispute.model_validate({"with": "Priority", "about": "F-4", "reason": "r"})
    says(refused("adaptation", "propose", next="Requester"), "next")
    says(refused("adaptation", "propose", workflows=[wf(steps=[])]), "workflows.0.steps")
    assert parse("adaptation", "propose", deferred=[{"item": "gallery", "until": "after launch"}]).deferred[0].until == "after launch"


def certainty(zone, **signals):
    return {"zone": zone, "rationale": "r", "signals": {**SIGNALS_ALL_KNOWN, **signals}}


def test_propose_certainty_zones():
    operate = parse("adaptation", "propose", certainty_assessment=certainty("operate"))
    assert operate.certainty_assessment.zone == "operate"
    says(refused("adaptation", "propose", certainty_assessment=certainty("analyze")),
         "your signals give operate by the Certainty rule, but zone says analyze")
    analyze = certainty("analyze", open_choices={"answer": "yes", "evidence": "two layouts"})
    says(refused("adaptation", "propose", certainty_assessment=analyze), "zone analyze needs analysis with options and chosen")
    assert parse("adaptation", "propose", certainty_assessment=analyze,
                 analysis={"options": ["one page", "three pages"], "chosen": "one page", "why": "small", "assumptions": []}).analysis.chosen
    says(refused("adaptation", "propose", certainty_assessment=analyze, analysis={"options": [], "chosen": "one page"}), "analysis")


def test_propose_experiment_zone_needs_one_to_three_probes_with_their_parts():
    experiment = certainty("experiment", reaction={"answer": "yes", "evidence": "the market reacts"})
    probe = wf(certainty="experiment", experiment={"hypothesis": "h", "signal": "s", "fails_if": "f", "limit": "l"})
    says(refused("adaptation", "propose", certainty_assessment=experiment), "needs 1 to 3 experiment workflows (has 0)")
    ok = parse("adaptation", "propose", certainty_assessment=experiment, workflows=[probe])
    assert ok.workflows[0].experiment.limit == "l"
    says(refused("adaptation", "propose", certainty_assessment=experiment, workflows=[probe] * 4), "has 4")
    bare = wf(certainty="experiment")
    says(refused("adaptation", "propose", certainty_assessment=experiment, workflows=[bare]), "an experiment workflow needs")


def test_certainty_reading_needs_all_five_signals():
    with pytest.raises(ValidationError):
        Certainty.model_validate({"zone": "analyze", "signals": {k: v for k, v in SIGNALS_ALL_KNOWN.items() if k != "reaction"}})
    with pytest.raises(ValidationError):
        Certainty.model_validate(certainty("analyze", broken={"answer": "maybe"}))
    with pytest.raises(ValidationError):
        Certainty.model_validate({**certainty("operate"), "zone": "chaos"})


def test_respond_rules():
    says(refused("adaptation", "respond", act="REVISE", workflows=[]), "REVISE needs the revised workflows")
    says(refused("adaptation", "respond", act="ACCEPT", workflows=[wf()]), "ACCEPT carries no workflows")
    says(refused("adaptation", "respond", act="PARK", workflows=[wf()]), "PARK carries no workflows")
    assert parse("adaptation", "respond", act="REVISE", workflows=[wf()], next="Priority").workflows[0].id == "P-1"
    assert parse("adaptation", "respond", act="PARK", next="Identity").act == "PARK"


def test_atom_verdict_rules():
    check = {"template": "element-count", "args": ["#contact"], "text": "one contact section", "expect": 1,
             "relevance": None, "relevance_source": "declared", "target_sha256": None, "results": []}
    says(refused("adaptation", "atom_verdict", verdict="CHECK_WRONG", verification=[]), "CHECK_WRONG needs the corrected checks")
    assert parse("adaptation", "atom_verdict", verdict="CHECK_WRONG", verification=[check], affordable=None,
                 build_wrong_reason=None).verification[0].template == "element-count"
    says(refused("adaptation", "atom_verdict", affordable=None), "BUILD_WRONG needs affordable")
    says(refused("adaptation", "atom_verdict", build_wrong_reason="  ", say=""), "BUILD_WRONG needs build_wrong_reason")
    both = refused("adaptation", "atom_verdict", affordable=None, build_wrong_reason=None, say="")
    assert len(both) == 2
    says(refused("adaptation", "atom_verdict", atom="atom-1"), "atom")
    says(refused("adaptation", "atom_verdict", verdict="CHECK_WRONG", verification=[{**check, "template": "lint"}]), "verification.0.template")


def test_lesson_reply_bounds():
    says(refused("adaptation", "lesson", lessons=[{"problem": "", "fix": "f"}]), "lessons.0.problem")
    says(refused("adaptation", "lesson", lessons=[{"problem": "p", "fix": ""}]), "lessons.0.fix")
    says(refused("adaptation", "lesson", lessons=[{"problem": "p", "fix": "f"}] * 11), "lessons")
    assert parse("adaptation", "lesson", lessons=[{"problem": "p", "fix": "f"}]).lessons[0].cause == ""
    assert parse("adaptation", "lesson", lessons=[]).lessons == []


def test_report_rules():
    row = SAMPLES[("audit", "report")]["findings"][0]
    says(refused("audit", "report", findings=[row, row]), "repeats the id F-1")
    says(refused("audit", "report", findings=[{**row, "evidence": ""}]), "a PASS needs evidence")
    says(refused("audit", "report", findings=[{**row, "verdict": "PASS_WITH_WARNING", "evidence": " "}]), "PASS_WITH_WARNING needs evidence")
    assert parse("audit", "report", findings=[{**row, "verdict": "NEEDS_REVISION", "evidence": "", "item": None}]).findings[0].item is None
    says(refused("audit", "report", findings=[{**row, "verdict": "OK"}]), "findings.0.verdict")
    says(refused("audit", "report", findings=[{**row, "id": "X-1"}]), "findings.0.id")
    says(refused("audit", "report", findings=[{**row, "severity": "huge"}]), "severity")
    says(refused("audit", "report", rubric=[{"id": "R-1", "verdict": "PASS", "evidence": ""}]), "R-1: a PASS needs evidence")
    says(refused("audit", "report", rubric=[{"id": "R-1", "verdict": "PASS", "evidence": "a"}] * 2), "repeats the id R-1")
    says(refused("audit", "report", rubric=[{"id": "X-1", "verdict": "PASS", "evidence": "a"}]), "rubric.0.id")
    says(refused("audit", "report", rubric=[{"id": "D-5", "verdict": "BLOCKED_BY_EVIDENCE", "evidence": "a"}]), "rubric.0.verdict")
    says(refused("audit", "report", next="Adaptation"), "next")
    assert parse("audit", "report", read="the Problem section, about 120 words").read.startswith("the Problem")
    assert parse("audit", "report", findings=[], rubric=[]).findings == []


def test_realization_fields_on_a_proposal():
    factor = {"name": "opening hours", "source": "brief", "quote": "open 7 to 7", "citation": None, "why": "visitors ask", "stages": ["build"]}
    stage = {"id": "build", "thinking": "make it", "tiers": ["implementation"], "goal": "a page", "done_test": "it loads",
             "method": None, "owns_factors": ["opening hours"], "inputs_from": []}
    ok = parse("adaptation", "propose", factors=[factor], unplaced=[{"name": "x", "why": "y"}], stages=[stage],
               open_facts=[{"fact": "phone", "workflow": "Scaffold", "blocking": True, "handling": "ask"}],
               not_ready=[{"workflow": "Scaffold", "score": 0.5, "weakest": "inputs", "stop_reason": "no inputs", "route": "identity"}])
    assert ok.factors[0].stages == ["build"] and ok.not_ready[0].score == 0.5
    says(refused("adaptation", "propose", factors=[{**factor, "quote": None}]), "quote must not be empty")
    says(refused("adaptation", "propose", factors=[{**factor, "source": "research", "citation": "R-1"}]), "research.md#R-1")
    assert Factor(**{**factor, "source": "research", "citation": "research.md#R-12", "quote": None}).citation == "research.md#R-12"
    says(refused("adaptation", "propose", factors=[{**factor, "source": "budget", "quote": None}]), "stages must be empty")
    says(refused("adaptation", "propose", stages=[{**stage, "tiers": []}]), "stages.0.tiers")
    says(refused("adaptation", "propose", stages=[{**stage, "tiers": ["wish"]}]), "stages.0.tiers.0")
    says(refused("adaptation", "propose", not_ready=[{"workflow": "w", "score": 1.5, "weakest": "inputs", "stop_reason": "s", "route": "identity"}]), "score")
    says(refused("adaptation", "propose", not_ready=[{"workflow": "w", "score": 0.5, "weakest": "fits", "stop_reason": "s", "route": "identity"}]), "weakest")


# ---- transport ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("family,kind", sorted(SAMPLES))
def test_every_reply_class_is_transport_safe_and_names_its_kind(family, kind):
    schema = REGISTRY.transport_schema(family, kind=kind)
    assert is_transport_safe(schema) == []
    assert schema["properties"]["kind"]["enum"] == [kind]
    assert "kind" in schema["required"] and "schema_version" not in schema["required"] and "reason" not in schema["required"]
    assert "oneOf" not in json.dumps(schema) and "discriminator" not in json.dumps(schema)


def test_no_optional_class_or_union_field_is_required():
    """L1 review: `Optional[Model]` and `Optional[Union]` lose their null (a one-member anyOf, kept for J2 sha parity), so the
    model must omit such a field: it is in TRANSPORT_OPTIONAL and never in `required`."""
    singles = 0
    for (family, kind), cls in REPLY_CLASSES.items():
        schema = REGISTRY.transport_schema(family, kind=kind)
        for name, node in {"": schema, **schema.get("definitions", {})}.items():
            for prop, sub in node.get("properties", {}).items():
                members = sub.get("anyOf", ())
                if len(members) == 1 or (len(members) > 1 and all("$ref" in m for m in members)):    # an optional class or union
                    singles += 1
                    assert prop not in node.get("required", []), (family, kind, name, prop)
    assert singles >= 6


ASKING = {"enough": False, "next": "Requester", "questions": [{"question": "What is the business called?"}]}


@pytest.mark.parametrize("family,kind,field,sample", [
    ("identity", "intake", "goal", ASKING), ("identity", "ruling", "user_question", {}),
    ("identity", "approval_ask", "user_question", {}), ("adaptation", "propose", "dispute", {}),
    ("adaptation", "propose", "certainty_assessment", {}), ("adaptation", "propose", "analysis", {}),
])
def test_the_listed_optional_model_fields_are_omitted_not_nulled(family, kind, field, sample):
    cls = REPLY_CLASSES[(family, kind)]
    assert field in cls.TRANSPORT_OPTIONAL
    schema = REGISTRY.transport_schema(family, kind=kind)
    assert field in schema["properties"] and field not in schema["required"]
    reply = {k: v for k, v in make(family, kind, **sample).items() if k != field}
    assert cls.model_validate(reply)                                                     # the model leaves it out: valid


def test_the_intake_goal_is_an_anyof_of_the_two_charters():
    node = REGISTRY.transport_schema("identity", kind="intake")["properties"]["goal"]
    refs = [m["$ref"].rsplit("/", 1)[-1] for m in node["anyOf"]]
    assert sorted(refs) == ["DocGoalDraft", "SiteGoalDraft"] and len(node["anyOf"]) == 2


def test_propose_transport_asks_what_j2_asks():
    schema = REGISTRY.transport_schema("adaptation", kind="propose")
    required = set(schema["required"])
    assert {"say", "act", "workflows", "left_out", "question", "playbook_used", "playbook_changes", "lesson_used", "next"} <= required
    assert not required & {"factors", "stages", "not_ready", "deferred", "analysis", "dispute", "certainty_assessment"}
    assert schema["properties"]["dispute"]["anyOf"][0]["$ref"].endswith("Dispute")
    assert "with" in schema["definitions"]["Dispute"]["properties"]          # the J2 key, not with_


@pytest.mark.parametrize("cls", sorted(set(REPLY_CLASSES.values()) | {Conflict, Lesson}, key=lambda c: c.__name__))
def test_design_rules_every_str_and_list_bounded(cls):
    assert unbounded_fields(cls) == []
    allowed = {("Dispute", "with")}
    assert set(aliased_fields(cls)) <= allowed


# ---- certainty ------------------------------------------------------------------------------------------------------

def sig(**answers):
    base = {"broken": "no", "reaction": "no", "facts_given": "yes", "known_pattern": "yes", "open_choices": "no"}
    return {k: {"answer": a, "evidence": ""} for k, a in {**base, **answers}.items()}


def test_certainty_zone_rule():
    assert certainty_zone(sig()) == "operate"
    assert certainty_zone(sig(broken="yes")) == "stabilize"
    assert certainty_zone(sig(broken="yes", reaction="yes")) == "stabilize"             # broken beats reaction
    assert certainty_zone(sig(reaction="yes")) == "experiment"
    assert certainty_zone(sig(reaction="yes", facts_given="unknown", known_pattern="unknown")) == "experiment"   # unknowns never move it
    assert certainty_zone(sig(open_choices="yes")) == "analyze"
    assert certainty_zone(sig(facts_given="no")) == "analyze"
    assert certainty_zone(sig(known_pattern="no")) == "analyze"
    assert certainty_zone(sig(open_choices="unknown")) == "analyze"                    # one unknown: no shift
    assert certainty_zone(sig(broken="unknown", reaction="unknown")) == "analyze"          # two unknowns: operate moves to analyze
    assert certainty_zone(sig(facts_given="unknown", known_pattern="unknown")) == "experiment"    # analyze moves to experiment
    assert certainty_zone(sig(broken="unknown", reaction="unknown", facts_given="no")) == "experiment"


def test_certainty_zone_reads_bare_strings_a_models_instance_and_bad_answers():
    assert certainty_zone({"broken": "YES"}) == "stabilize"
    assert certainty_zone({}) == "experiment"                                           # five unknowns: analyze, shifted once
    assert signal_answer({"broken": {"answer": " Yes "}}, "broken") == "yes"
    assert signal_answer({"broken": {"answer": "perhaps"}}, "broken") == "unknown"
    assert signal_answer(None, "broken") == "unknown"
    assert certainty_zone(Certainty.model_validate(certainty("operate")).signals) == "operate"
    assert set(ZONES) == {"operate", "analyze", "experiment", "stabilize"} and len(SIGNALS) == 5


def test_certainty_zone_matches_a_reference_on_every_signal_combination():
    """243 combinations, against the J2 rule written out again in the plainest way."""
    def reference(a):
        if a["broken"] == "yes":
            return "stabilize"
        zone = ("experiment" if a["reaction"] == "yes" else
                "operate" if (a["facts_given"], a["known_pattern"], a["open_choices"]) == ("yes", "yes", "no") else "analyze")
        if list(a.values()).count("unknown") >= 2 and zone in ("operate", "analyze"):
            zone = {"operate": "analyze", "analyze": "experiment"}[zone]
        return zone
    for combo in itertools.product(("yes", "no", "unknown"), repeat=5):
        answers = dict(zip(SIGNALS, combo))
        assert certainty_zone(sig(**answers)) == reference(answers), answers


# ---- Conflict -------------------------------------------------------------------------------------------------------

FINDING_CONFLICT = {   # runs/j2-20261006-115833 C-2
    "id": "C-2", "cycle": 2, "topic": "finding", "between": ["adaptation", "audit"], "about": "F-4", "subject": "finding F-4",
    "detail": "{\"id\": \"F-4\", \"item\": 4, \"verdict\": \"NEEDS_REVISION\"}",
    "attempts": [{"n": 1, "who": "adaptation", "msg": 31, "text": "@Audit I disagree with F-4.", "position": "Fluid layout", "agree": False},
                 {"n": 3, "who": "adaptation", "msg": 33, "text": "@Audit Fair point.", "position": "Accepts Audit's position.", "agree": True}],
    "status": "settled", "escalated": False, "attempts_before_escalation": None, "resolved_by": "agents", "identity": [],
    "escalated_to_user": False, "user_question": None, "user_answer": None, "winner": "audit",
    "outcome": "Finding F-4 stands: Adaptation proposes the rework.", "attempts_used": 3}
PROPOSAL_CONFLICT = {   # runs/j2-20261006-115833 C-1, trimmed
    "id": "C-1", "cycle": 1, "topic": "proposal", "between": ["adaptation", "priority"], "about": None,
    "subject": "what to fund in cycle 1", "detail": None,
    "attempts": [{"n": 0, "who": "adaptation", "msg": 7, "text": "@Priority Proposal for cycle 1.", "position": "opening proposal", "agree": None},
                 {"n": 1, "who": "priority", "msg": 8, "text": "@Adaptation Granted.", "position": "COUNTER: Scaffold (15)", "agree": False}],
    "status": "settled", "escalated": True, "attempts_before_escalation": 4, "resolved_by": "identity_after_user",
    "identity": [{"say": "I am asking the Requester.", "clause": "done_when; standards", "resolved": False, "ruling": None, "after_user": False},
                 {"say": "Priority's position stands.", "clause": "Requester's decision", "resolved": True, "ruling": "priority", "after_user": True}],
    "escalated_to_user": True, "user_question": {"question": "Fund a stories section?", "options": ["Yes (20)", "No"]},
    "user_answer": "Option 2.", "winner": "priority", "outcome": "Priority's position stands.", "escalated_because": "no deal in 4 attempts",
    "priority_final": [{"name": "Scaffold", "cost": 15, "envelope": {"money_limit": 15}}], "adaptation_final": [], "attempts_used": 4}


@pytest.mark.parametrize("saved", [FINDING_CONFLICT, PROPOSAL_CONFLICT], ids=["finding", "proposal"])
def test_saved_conflicts_validate_through_the_gate(saved):
    checked = GATE.check("conflict", {**saved, "kind": "conflict"})
    assert checked.model.id == saved["id"] and checked.family == "conflict"
    assert REGISTRY.adapter("conflict").validate_json(checked.json) == checked.model


def test_conflict_rules():
    base = {**FINDING_CONFLICT, "kind": "conflict"}
    for changes, where in (({"id": "c1"}, "id"), ({"topic": "hold-up"}, "topic"), ({"between": ["audit", "audit"]}, "between"),
                           ({"between": ["audit"]}, "between"), ({"between": ["audit", "boss"]}, "between.1"),
                           ({"status": "done"}, "status"), ({"resolved_by": "coin"}, "resolved_by"),
                           ({"outcome": None}, "outcome"), ({"status": "escalated", "escalated": False}, "escalated"),
                           ({"resolved_by": "identity_after_user"}, "resolved_by"), ({"colour": 1}, "colour"),
                           ({"attempts": [{"n": -1, "who": "audit", "text": "", "position": "", "agree": True}]}, "attempts.0.n")):
        with pytest.raises(ValidationError) as exc:
            Conflict.model_validate({**base, **changes})
        assert any(e["loc"] and ".".join(map(str, e["loc"])) == where or ".".join(map(str, e["loc"])).startswith(where) for e in exc.value.errors()), changes
    assert Conflict.model_validate({**base, "status": "open", "outcome": None, "winner": None, "resolved_by": None}).status == "open"


def test_a_conflict_in_repricing_keeps_its_working_keys():
    c = Conflict.model_validate({**PROPOSAL_CONFLICT, "kind": "conflict", "status": "repricing", "outcome": None, "winner": None,
                                 "repriced": True, "pending_winner": "adaptation", "ruled_wfs": [{"name": "Scaffold"}],
                                 "repricing": {"decision": "GRANT", "say": "ok"}, "cut": ["Stories"], "resend": [], "resend_asks": 1})
    assert c.repriced and c.pending_winner == "adaptation" and c.resend_asks == 1


# ---- Lesson ---------------------------------------------------------------------------------------------------------

LESSON = {"kind": "lesson", "id": "L-j2-20261006-115833-1", "problem": "No viewport meta tag", "cause": "The first build left it out",
          "fix": "Add the viewport meta tag", "run": "j2-20261006-115833", "cycle": 2, "versions": [1, 2], "workflows": ["W-3"],
          "t": "2026-10-06 12:01:44"}


def test_lesson_is_a_record_of_its_own_family():
    checked = GATE.check("lesson", LESSON)
    assert checked.model.versions == [1, 2] and REGISTRY.kinds("lesson") == {"lesson": Lesson}
    full = Lesson.model_validate({**LESSON, "output": "prd", "test": True, "mock": False})
    assert (full.output, full.test, full.mock) == ("prd", True, False)


@pytest.mark.parametrize("changes", [{"id": "L-1"}, {"id": "lesson-1-1"}, {"versions": [1]}, {"versions": [0, 1]}, {"problem": ""},
                                     {"fix": ""}, {"workflows": ["W-x"]}, {"cycle": -1}, {"colour": 1}, {"t": ""}, {"run": ""}])
def test_lesson_rejects(changes):
    with pytest.raises(ValidationError):
        Lesson.model_validate({**LESSON, **changes})


def test_a_function_reply_is_not_a_stored_record_of_another_family():
    with pytest.raises(GateError) as exc:
        GATE.check("priority", make("priority", "price", decision="REFUSE"))
    assert exc.value.stage == "shape"
    assert Propose.FAMILY == "adaptation"
