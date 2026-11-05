"""Workflow and Step (library design section 9.1, WP L5): the two levels, the steps, J2's dicts and the gate.

`EXAMPLE_WORKFLOW` is J2's own (j2.py:292, shown to Adaptation as the example that passes); `ROW` is one row of a saved J2
run's workflows.json (runs/j2-20261012-155549, `last_check` and `covers_text` shortened)."""
import copy

import pytest
from pydantic import ValidationError

from factories_atom import check, draft, work
from sutra_app.library import workflow as workflow_module
from sutra_app.library.atom import AtomDraft, Check, Verify
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY, is_transport_safe, transport_schema
from sutra_app.library.workflow import (
    AIStep, AssignmentStep, CodeStep, DeptWorkflow, Envelope, ProposedWorkflow, RegisteredWorkflow, Resources, Step,
    TaskWorkflow, WorkflowError, from_j2, registered_from_j2, to_j2,
)

EXAMPLE_WORKFLOW = {
    "name": "Contact section", "goal_gap": "Visitors have no way to message the business", "outputs": ["#contact"],
    "completion_check": "A contact form with a send button is on the page", "parts": ["form"], "covers": [1],
    "atoms": [{"id": "a1", "goal": "Visitors can send the business a message from a contact form.",
               "constraints": ["Other sections stay unchanged", "Create only #contact and #contact-send"],
               "context": ["charter item 1"],
               "how": {"kind": "AI", "agent": "Builder", "steps": "Create section #contact holding a name field, an "
                       "email field and a send button #contact-send"},
               "expected_output": [{"text": "The contact section", "kind": "section", "target": "#contact"},
                                   {"text": "The send button", "kind": "element", "target": "#contact-send"}],
               "verification": [{"text": "One #contact section is on the page", "type": "element-count",
                                 "target": "#contact", "expect": 1},
                                {"text": "The form has a submit button", "type": "named-test",
                                 "target": "form-has-submit", "expect": True}]}]}
ROW = {
    "id": "W-2", "proposal_id": "schedule", "name": "Day by day schedule", "covers": [2], "fixes": [],
    "covers_text": ["A schedule section has Day 1, Day 2 and Day 3, each listing that day's events with start and end time."],
    "purpose": "Students cannot see what happens on each day.", "cost": 10, "estimate": 10,
    "envelope": {"money_limit": 10, "model_call_limit": 3, "time_limit_minutes": 12, "retry_limit": 2,
                 "stop_loss": "Stop if the same verification fails twice in a row"},
    "charged": True, "calls_used": 1, "retries_used": 0, "outputs": ["section #schedule"],
    "completion_check": "Section #schedule has 3 day blocks and 8 event rows with the exact times from the Requester's list.",
    "dependencies": [], "status": "done", "cycle": 1,
    "atoms": [{"id": "W-2.a1", "goal": "Day 1, Day 2 and Day 3 each list their events with exact start and end times.",
               "constraints": ["Times match the Requester's list exactly", "No extra events"], "context": ["charter item 2"],
               "how": {"kind": "AI", "agent": "W-schedule builder"},
               "verification": [{"text": "Three day headings exist", "type": "grep-count", "target": "Day [123]", "expect": 3},
                                {"text": "Schedule section exists", "type": "grep-count", "target": "id=\"schedule\"", "expect": 1}]}],
    "section": "W-2", "revises": None, "agent": "W-2 Builder", "last_check": "usable section", "version": 2}


def ai_step(id="a1", **over):
    return AIStep(id=id, name=over.pop("name", "Build the form"), atom=draft(check(), kind="llm"), **over)


def code_step(id="a2", **over):
    return CodeStep(id=id, name=over.pop("name", "Send the mail"), atom=draft(check(), kind="manual"), **over)


def assignment(id="a1", **over):
    return AssignmentStep(id=id, name=over.pop("name", "Open sales"), dept=over.pop("dept", "sales"),
                          brief=over.pop("brief", "Plan the launch offer"), **over)


def dept_fields(**over):
    base = {"name": "Contact section", "goal_gap": "no contact form", "outputs": ["#contact"], "completion_check": "form exists",
            "steps": [ai_step()]}
    return {**base, **over}


def proposed(**over):
    return ProposedWorkflow(id=over.pop("id", "P-1"), **dept_fields(**over))


def codes(exc: ValidationError) -> list[tuple[str, str]]:
    return [(".".join(str(p) for p in e["loc"]), e["type"]) for e in exc.errors()]


def messages(exc: ValidationError) -> list[str]:
    return [e["msg"] for e in exc.errors()]


# ---- resources and envelope ----------------------------------------------------------------------------------------

def test_resources_and_envelope_defaults():
    assert Resources().model_dump() == {"money": 0, "calls": 0, "time_minutes": 0}
    env = Envelope(money_limit=5)
    assert (env.model_call_limit, env.time_limit_minutes, env.retry_limit, env.stop_loss) == (2, 10, 1, "")


@pytest.mark.parametrize("bad", [{"money_limit": -1}, {"money_limit": "5"}, {"money_limit": 5, "colour": 1}, {}])
def test_envelope_rejects(bad):
    with pytest.raises(ValidationError):
        Envelope(**bad)


def test_envelope_reads_a_null_as_the_default_for_the_two_fields_j2_left_null():
    env = Envelope.model_validate({"money_limit": 4, "time_limit_minutes": None, "stop_loss": None})
    assert (env.time_limit_minutes, env.stop_loss) == (10, "")
    with pytest.raises(ValidationError):                      # no other field reads null
        Envelope.model_validate({"money_limit": 4, "retry_limit": None})


# ---- steps ----------------------------------------------------------------------------------------------------------

def test_step_base_is_abstract():
    with pytest.raises(ValidationError) as exc:
        Step(id="a1", name="x")
    assert "Step is abstract" in messages(exc.value)[0]


def test_ai_step_needs_ai_work_dispatched_as_llm_or_skill():
    ai_step()
    AIStep(id="a1", name="x", atom=draft(check(), work=work("skill", how_kind="AI")))
    with pytest.raises(ValidationError) as exc:
        AIStep(id="a1", name="x", atom=draft(check(), work=work("bash", how_kind="AI")))
    assert codes(exc.value) == [("atom.work.dispatch_kind", "value_error")]
    with pytest.raises(ValidationError) as exc:
        AIStep(id="a1", name="x", atom=draft(check(), work=work("llm", how_kind="code")))
    assert codes(exc.value) == [("atom.work.how_kind", "value_error")]


def test_code_step_needs_code_work_dispatched_as_bash_or_manual():
    code_step()
    CodeStep(id="a2", name="x", atom=draft(check(), work=work("bash")))
    with pytest.raises(ValidationError) as exc:
        CodeStep(id="a2", name="x", atom=draft(check(), work=work("bash", how_kind="AI")))
    assert codes(exc.value) == [("atom.work.how_kind", "value_error")]
    with pytest.raises(ValidationError) as exc:
        CodeStep(id="a2", name="x", atom=draft(check(), work=work("llm", how_kind="code")))
    assert codes(exc.value) == [("atom.work.dispatch_kind", "value_error")]


def test_step_reports_both_work_problems_at_once():
    with pytest.raises(ValidationError) as exc:
        AIStep(id="a1", name="x", atom=draft(check(), work=work("manual", how_kind="code")))
    assert {c[0] for c in codes(exc.value)} == {"atom.work.how_kind", "atom.work.dispatch_kind"}


@pytest.mark.parametrize("changes", [{"id": ""}, {"id": "x" * 21}, {"name": ""}, {"name": "x" * 121}, {"on_failure": "retry"},
                                     {"depends_on": ["a"] * 21}, {"colour": "red"}])
def test_step_rejects(changes):
    with pytest.raises(ValidationError):
        AssignmentStep.model_validate({"id": "a1", "name": "n", "dept": "sales", "brief": "b", **changes})


@pytest.mark.parametrize("action", ["rollback", "escalate", "pause", "abort", "continue"])
def test_on_failure_takes_the_closed_five(action):
    assert ai_step(on_failure=action).on_failure == action


def test_assignment_step_rules():
    assert assignment(scope="leads", follows="tsk_0123456789ab").scope == "leads"
    for bad in ({"follows": "T-9"}, {"follows": "tsk_0123456789AB"}, {"depends_on": ["a1", "a2", "a3", "a4", "a5"]},
                {"brief": ""}, {"brief": "x" * 2001}, {"dept": "Sales"}, {"scope": "no way"}):
        with pytest.raises(ValidationError):
            assignment(**bad)
    assert len(assignment(depends_on=["a1", "a2", "a3", "a4"]).depends_on) == 4


# ---- workflows ------------------------------------------------------------------------------------------------------

def test_task_workflow_is_assignment_steps_only():
    w = TaskWorkflow(id="req-17", name="Launch", steps=[assignment("a1"), assignment("a2", dept="support", depends_on=["a1"])])
    assert (w.kind, w.failure_policy, w.schema_version) == ("task", "escalate", 1)
    with pytest.raises(ValidationError) as exc:
        TaskWorkflow(id="req-17", name="Launch", steps=[ai_step()])
    assert codes(exc.value)[0][1] == "model_type" or "steps.0" in codes(exc.value)[0][0]
    with pytest.raises(ValidationError):
        TaskWorkflow.model_validate({"id": "req-1", "name": "n", "steps": [{"kind": "human", "id": "a1", "name": "x"}]})
    with pytest.raises(ValidationError):
        TaskWorkflow(id="", name="Launch", steps=[assignment()])
    with pytest.raises(ValidationError):
        TaskWorkflow(id="x" * 65, name="Launch", steps=[assignment()])


def test_dept_workflow_takes_atom_steps_only():
    proposed(steps=[ai_step("a1"), code_step("a2")])
    with pytest.raises(ValidationError) as exc:
        proposed(steps=[assignment()])
    assert "steps" in codes(exc.value)[0][0]
    with pytest.raises(ValidationError) as exc:
        ProposedWorkflow.model_validate({**proposed().model_dump(), "steps": [{"kind": "human", "id": "a1", "name": "x"}]})
    assert codes(exc.value)[0][1] == "union_tag_invalid"


def test_step_ids_are_unique_and_depend_only_on_earlier_steps():
    with pytest.raises(ValidationError) as exc:
        proposed(steps=[ai_step("a1"), ai_step("a1")])
    assert codes(exc.value) == [("steps.1.id", "value_error")]
    with pytest.raises(ValidationError) as exc:
        proposed(steps=[ai_step("a1", depends_on=["a2"]), ai_step("a2")])
    assert codes(exc.value) == [("steps.0.depends_on.0", "value_error")]
    with pytest.raises(ValidationError):
        proposed(steps=[ai_step("a1", depends_on=["a1"])])                    # not earlier than itself
    with pytest.raises(ValidationError):
        proposed(steps=[ai_step("a1", depends_on=["ghost"])])
    proposed(steps=[ai_step("a1"), ai_step("a2", depends_on=["a1"]), ai_step("a3", depends_on=["a1", "a2"])])


def test_step_graph_reports_every_problem():
    with pytest.raises(ValidationError) as exc:
        proposed(steps=[ai_step("a1", depends_on=["a9"]), ai_step("a1")])
    assert len(codes(exc.value)) == 2


def test_workflow_bounds_and_policy():
    with pytest.raises(ValidationError) as exc:
        proposed(steps=[])
    assert codes(exc.value) == [("steps", "too_short")]
    with pytest.raises(ValidationError):
        proposed(steps=[ai_step(f"a{i}") for i in range(13)])
    assert len(proposed(steps=[ai_step(f"a{i}") for i in range(12)]).steps) == 12
    assert proposed(failure_policy="rollback").failure_policy == "rollback"
    with pytest.raises(ValidationError) as exc:
        proposed(failure_policy="retry")
    assert codes(exc.value) == [("failure_policy", "literal_error")]


@pytest.mark.parametrize("changes,where,code", [
    ({"outputs": []}, "outputs", "too_short"),
    ({"outputs": ["x"] * 21}, "outputs", "too_long"),
    ({"covers": [0]}, "covers.0", "greater_than_equal"),
    ({"completion_check": ""}, "completion_check", "string_too_short"),
    ({"goal_gap": ""}, "goal_gap", "string_too_short"),
    ({"name": ""}, "name", "string_too_short"),
    ({"output": "pdf"}, "output", "literal_error"),
    ({"authority_touched": "world"}, "authority_touched", "literal_error"),
    ({"estimated_resources": {"money": -1}}, "estimated_resources.money", "greater_than_equal"),
    ({"colour": "red"}, "colour", "extra_forbidden"),
])
def test_dept_workflow_invalid(changes, where, code):
    with pytest.raises(ValidationError) as exc:
        proposed(**changes)
    assert (where, code) in codes(exc.value)


def test_proposed_workflow_carries_the_optional_fields():
    w = proposed(envelope=Envelope(money_limit=7), stage="build", certainty="operate", approach="standard form",
                 done_test="the form shows", delivers=[1], informs=[2], inputs_from=["Scaffold"], hold="waiting_on_dependency",
                 certainty_signals=["facts given"], trigger="request", authority_touched="local",
                 inputs=["charter"], capabilities=["html"], risks=["spam"], revises="W-1", parts=["form"], covers=[1],
                 fixes=["F-3"], dependencies=["Scaffold"], estimated_resources=Resources(money=3, calls=2, time_minutes=4))
    assert w.envelope.money_limit == 7 and w.kind == "proposed"


def test_research_workflow_rules():
    research = {"question": "Which competitors?", "feeds": "positioning", "min_sources": 3, "output": "research.md#R-1"}
    assert proposed(research=research, stage="product").research.min_sources == 3
    with pytest.raises(ValidationError) as exc:
        proposed(research=research, stage="build", delivers=[1])
    assert {c[0] for c in codes(exc.value)} == {"delivers", "stage"}
    for bad in ({**research, "min_sources": 2}, {**research, "output": "notes.md"}, {**research, "question": ""}):
        with pytest.raises(ValidationError):
            proposed(research=bad)


def test_experiment_needs_all_four_parts():
    ok = {"hypothesis": "h", "signal": "s", "fails_if": "f", "limit": "l"}
    assert proposed(experiment=ok, certainty="experiment").experiment.limit == "l"
    for missing in ok:
        with pytest.raises(ValidationError):
            proposed(experiment={k: v for k, v in ok.items() if k != missing})


def test_registered_workflow_valid_and_closed():
    w = registered_from_j2(ROW)
    assert (w.kind, w.id, w.status, w.cost, w.atoms) == ("registered", "W-2", "done", 10, ["W-2.a1"])
    base = w.model_dump()
    for changes, where in (({"id": "W-x"}, "id"), ({"status": "finished"}, "status"), ({"cycle": 0}, "cycle"),
                           ({"cost": -1}, "cost"), ({"envelope": None}, "envelope"), ({"colour": 1}, "colour")):
        with pytest.raises(ValidationError) as exc:
            RegisteredWorkflow.model_validate({**base, **changes})
        assert any(c[0].startswith(where) for c in codes(exc.value)), changes


def test_registered_atoms_must_be_the_workflow_id_and_step_ids():
    w = registered_from_j2(ROW)
    with pytest.raises(ValidationError) as exc:
        w.evolve(atoms=["W-2.a9"])
    assert codes(exc.value) == [("atoms", "value_error")]
    assert w.evolve(atoms=[]).atoms == []


def test_dept_workflow_base_is_abstract():
    assert workflow_module.DeptWorkflow.ABSTRACT and workflow_module.Workflow.ABSTRACT
    assert not ProposedWorkflow.__dict__.get("ABSTRACT", False)
    assert REGISTRY.kinds("workflow") == {"task": TaskWorkflow, "proposed": ProposedWorkflow, "registered": RegisteredWorkflow}
    assert issubclass(ProposedWorkflow, DeptWorkflow)


# ---- the gate -------------------------------------------------------------------------------------------------------

def test_gate_checks_each_kind_and_round_trips():
    task = TaskWorkflow(id="req-3", name="Launch", steps=[assignment()])
    for model in (task, from_j2(EXAMPLE_WORKFLOW), registered_from_j2(ROW)):
        checked = GATE.check("workflow", model)
        assert checked.kind == model.kind and len(checked.sha256) == 64
        assert GATE.check("workflow", checked.json).sha256 == checked.sha256
        assert REGISTRY.adapter("workflow").validate_json(checked.json) == model


def test_gate_refuses_a_bad_workflow_with_every_violation():
    bad = {**from_j2(EXAMPLE_WORKFLOW).model_dump(), "outputs": [], "completion_check": ""}
    with pytest.raises(GateError) as exc:
        GATE.check("workflow", bad)
    assert exc.value.stage == "shape" and {v.path for v in exc.value.violations} >= {"proposed.outputs", "proposed.completion_check"}


def test_evolve_revalidates_a_workflow():
    w = proposed()
    assert w.evolve(name="Other").name == "Other"
    with pytest.raises(ValidationError):
        w.evolve(steps=[])


# ---- J2's dicts -----------------------------------------------------------------------------------------------------

def test_example_workflow_round_trips():
    w = from_j2(EXAMPLE_WORKFLOW)
    assert (w.id, w.name, w.covers, w.parts) == ("P-1", "Contact section", [1], ["form"])
    step = w.steps[0]
    assert (step.kind, step.id, step.atom.work.how_kind, step.atom.work.dispatch_kind) == ("ai", "a1", "AI", "llm")
    assert [c.template for c in step.atom.verify.checks] == ["element-count", "named-test"]
    assert step.atom.verify.checks[1].expect is True and step.atom.verify.checks[0].expect == 1
    assert to_j2(w) == {**EXAMPLE_WORKFLOW, "id": "P-1"}
    assert to_j2(from_j2(to_j2(w))) == to_j2(w)


def test_from_j2_does_not_touch_its_input():
    before = copy.deepcopy(EXAMPLE_WORKFLOW)
    from_j2(EXAMPLE_WORKFLOW)
    assert EXAMPLE_WORKFLOW == before


def test_from_j2_takes_the_id_of_the_dict_then_the_keyword():
    assert from_j2({**EXAMPLE_WORKFLOW, "id": "P-7"}).id == "P-7"
    assert from_j2(EXAMPLE_WORKFLOW, id="P-9").id == "P-9"


def test_j2_grep_count_keeps_its_count_in_expect_and_the_file_in_the_third_argument():
    d = copy.deepcopy(EXAMPLE_WORKFLOW)
    d["atoms"][0]["verification"] = [{"text": "t", "type": "grep-count", "target": "contact", "expect": 2},
                                     {"text": "u", "type": "grep-count", "target": "hero", "expect": 1, "file": "site/a.html"}]
    w = from_j2(d)
    first, second = w.steps[0].atom.verify.checks
    assert first.args == ["contact", "index.html", "2"] and first.expect == 2
    assert second.args == ["hero", "site/a.html", "1"]
    assert to_j2(w)["atoms"][0]["verification"] == d["atoms"][0]["verification"]


def test_a_grep_count_of_zero_is_asked_for_at_least_one_but_keeps_its_zero():
    d = copy.deepcopy(EXAMPLE_WORKFLOW)
    d["atoms"][0]["verification"] = [{"text": "t", "type": "grep-count", "target": "banner", "expect": 0}]
    check_ = from_j2(d).steps[0].atom.verify.checks[0]
    assert check_.args == ["banner", "index.html", "1"] and check_.expect == 0
    assert to_j2(from_j2(d))["atoms"][0]["verification"] == d["atoms"][0]["verification"]


def test_j2_targets_may_be_a_list_a_missing_expect_stays_missing():
    d = copy.deepcopy(EXAMPLE_WORKFLOW)
    d["atoms"][0]["verification"] = [{"text": "facts", "type": "facts-present", "target": ["07:00", "a@b.co"], "expect": True},
                                     {"text": "exists", "type": "file-exists", "target": "index.html"}]
    out = to_j2(from_j2(d))["atoms"][0]["verification"]
    assert out == d["atoms"][0]["verification"]


def test_j2_code_atom_is_a_code_step_and_behavior_steps_round_trip():
    d = copy.deepcopy(EXAMPLE_WORKFLOW)
    d["atoms"][0]["how"] = {"kind": "code", "agent": "Sender", "steps": "send the mail"}
    d["atoms"][0]["expected_output"] = [{"text": "total shows", "kind": "behavior", "target": "#total",
                                         "steps": ["set #qty 2", "click #calc", "expect-text #total 4"]},
                                        {"text": "three tiles", "kind": "element", "target": ".tile", "count": 3}]
    w = from_j2(d)
    assert (w.steps[0].kind, w.steps[0].atom.work.dispatch_kind) == ("code", "bash")
    assert to_j2(w)["atoms"][0]["expected_output"] == d["atoms"][0]["expected_output"]
    assert to_j2(w)["atoms"][0]["how"] == d["atoms"][0]["how"]


def test_from_j2_gives_the_atom_a_name_from_its_goal_and_defaults_how_to_ai():
    d = copy.deepcopy(EXAMPLE_WORKFLOW)
    d["atoms"][0].pop("how")
    d["atoms"][0]["goal"] = "g" * 200
    step = from_j2(d).steps[0]
    assert step.kind == "ai" and step.atom.work.agent is None and len(step.name) == 120
    d["atoms"][0]["goal"] = ""
    assert from_j2(d).steps[0].name == "a1"


def test_from_j2_reads_the_envelope_and_plan_fields_of_a_grant():
    d = {**EXAMPLE_WORKFLOW, "id": "P-2", "envelope": {"money_limit": 12, "model_call_limit": 3, "time_limit_minutes": None,
                                                         "retry_limit": 1, "stop_loss": None},
         "estimated_resources": {"money": 9, "calls": 2, "time_minutes": None}, "stage": "build", "certainty": "operate",
         "delivers": [1], "hold": "waiting_on_identity", "cost": 12, "estimate": 9, "unknown_key": 1}
    w = from_j2(d)
    assert w.envelope == Envelope(money_limit=12, model_call_limit=3) and w.estimated_resources.money == 9
    out = to_j2(w)
    assert out["envelope"]["money_limit"] == 12 and out["stage"] == "build" and out["delivers"] == [1] and "unknown_key" not in out
    assert out["estimated_resources"] == {"money": 9, "calls": 2, "time_minutes": 0}


def test_from_j2_refuses_what_is_not_a_workflow():
    with pytest.raises(WorkflowError) as exc:
        from_j2([EXAMPLE_WORKFLOW])
    assert exc.value.code == "not_a_mapping"
    with pytest.raises(WorkflowError):
        from_j2({**EXAMPLE_WORKFLOW, "atoms": ["a1"]})
    with pytest.raises(ValidationError):
        from_j2({k: v for k, v in EXAMPLE_WORKFLOW.items() if k != "atoms"})       # a workflow needs at least one atom
    with pytest.raises(ValidationError):
        from_j2({**EXAMPLE_WORKFLOW, "outputs": []})


def test_to_j2_takes_department_workflows_only():
    with pytest.raises(WorkflowError) as exc:
        to_j2(TaskWorkflow(id="req-1", name="n", steps=[assignment()]))
    assert exc.value.code == "not_a_department_workflow"


def test_registered_row_round_trips_through_to_j2():
    w = registered_from_j2(ROW)
    assert w.steps[0].id == "a1" and w.steps[0].atom.verify.checks[0].args == ["Day [123]", "index.html", "3"]
    out = to_j2(w)
    assert out["atoms"][0]["id"] == "W-2.a1" and out["atoms"][0]["how"] == {"kind": "AI", "agent": "W-schedule builder", "steps": ""}
    for key in ("id", "proposal_id", "name", "covers", "purpose", "cost", "estimate", "envelope", "charged", "calls_used",
                "status", "cycle", "section", "agent", "last_check", "version", "outputs", "completion_check"):
        assert out[key] == ROW[key], key
    assert out["atoms"][0]["verification"] == ROW["atoms"][0]["verification"]
    assert registered_from_j2(out) == w


def test_a_legacy_row_without_atoms_is_refused_and_purpose_fills_goal_gap():
    legacy = {k: v for k, v in ROW.items() if k != "atoms"}
    with pytest.raises(ValidationError) as exc:
        registered_from_j2(legacy)
    assert ("steps", "too_short") in codes(exc.value)
    assert registered_from_j2(ROW).goal_gap == ROW["purpose"]
    with pytest.raises(WorkflowError):
        registered_from_j2("W-2")


# ---- transport ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [TaskWorkflow, ProposedWorkflow, RegisteredWorkflow])
def test_workflow_classes_are_transport_safe(cls):
    assert is_transport_safe(transport_schema(cls)) == []


def test_proposed_workflow_transport_asks_what_j2_asks_and_no_more():
    schema = transport_schema(ProposedWorkflow)
    required = set(schema["required"])
    assert {"kind", "id", "name", "goal_gap", "expected_outcome", "outputs", "completion_check", "dependencies", "parts", "covers",
            "fixes", "revises", "estimated_resources", "steps"} <= required
    assert not required & {"envelope", "research", "experiment", "stage", "certainty", "schema_version", "failure_policy", "output"}
    assert schema["properties"]["kind"]["enum"] == ["proposed"]
    steps = schema["properties"]["steps"]["items"]
    assert "oneOf" not in str(schema) and len(steps["anyOf"]) == 2                  # ai and code, no assignment


def test_every_optional_class_field_is_left_out_of_required():
    """A field that is an optional class loses its null in the transport schema: it must be optional, not required."""
    for cls in (ProposedWorkflow, RegisteredWorkflow, TaskWorkflow):
        schema = transport_schema(cls)
        for name, node in {**{"": schema}, **schema.get("definitions", {})}.items():
            for prop, sub in node.get("properties", {}).items():
                if len(sub.get("anyOf", ())) == 1:
                    assert prop not in node.get("required", []), (cls.__name__, name, prop)


@pytest.mark.parametrize("cls", [TaskWorkflow, ProposedWorkflow, RegisteredWorkflow, AIStep, CodeStep, AssignmentStep, Envelope, Resources])
def test_design_rules_every_str_and_list_bounded_no_stray_alias(cls):
    assert unbounded_fields(cls) == []
    assert aliased_fields(cls) == []
