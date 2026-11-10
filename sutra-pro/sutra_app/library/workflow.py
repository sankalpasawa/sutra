"""Workflow and Step: the plan across departments and the plan inside one department (library design section 9.1, DL8).

Two levels, because the owner's graph has both:

    TaskWorkflow       what the chat agent builds across departments: a list of AssignmentStep (one department each);
                       its steps are the `step` nodes of the workflow graph. Transient: the validated plan is not stored.
    DeptWorkflow       what Adaptation proposes and the validator registers inside one department: J2's workflow dicts,
                       whose steps are work atoms (AIStep / CodeStep, each holding an AtomDraft)
      ProposedWorkflow   Adaptation's proposal (J2 `WF_FMT`), with Priority's envelope once granted
      RegisteredWorkflow the workflow as the validator registered it (J2:6672 and the keys code adds later)

`to_j2(w)` / `from_j2(d)` convert a department workflow to and from J2's dict (J2's `atoms` are the `steps`) and round-trip
J2's own EXAMPLE_WORKFLOW; `registered_from_j2(row)` does the same for one row of J2's workflows.json.

Every class is closed, strict and frozen (`Value` / `Record`). A validator reports every violation it finds. Fields the
model leaves out of a reply are listed in the class's `TRANSPORT_OPTIONAL` (a field that is an optional class, or an
optional union, loses its `null` in the transport schema, so the model omits it instead of sending null).
"""
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal, NoReturn, Self, Union

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator
from pydantic_core import InitErrorDetails

from .atom import AtomDraft, Check, Constraint, ExpectedItem, Verify, Work
from .base import Record, Value
from .registry import record
from .types import NodeId, WorkflowId, clip

__all__ = [
    "FailureAction", "Resources", "Envelope", "Step", "AIStep", "CodeStep", "AssignmentStep", "Workflow", "TaskWorkflow",
    "DeptWorkflow", "ProposedWorkflow", "RegisteredWorkflow", "Research", "Experiment", "StageId", "ZoneName",
    "ENVELOPE_KEYS", "WorkflowError", "to_j2", "from_j2", "registered_from_j2",
]

FailureAction = Literal["rollback", "escalate", "pause", "abort", "continue"]      # ADR-011's closed five
ZoneName = Literal["operate", "analyze", "experiment", "stabilize"]
Problem = tuple[tuple[str | int, ...], str]       # (place inside the model, what is wrong)

Id20 = Annotated[str, StringConstraints(min_length=1, max_length=20)]
Name120 = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Line40 = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Line80 = Annotated[str, StringConstraints(min_length=1, max_length=80)]
Line200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Line300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Text400 = Annotated[str, StringConstraints(max_length=400)]
Count = Annotated[int, Field(ge=1)]
# A stage id is one of agents/j2/stages.json (35 ids). The library does not read that file (it imports nothing from the
# engine and does no I/O): the shape is checked here, the membership by the engine's `plan_faults`.
StageId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]
ResearchRef = Annotated[str, StringConstraints(pattern=r"^research\.md#R-[0-9]{1,6}$")]

ENVELOPE_KEYS: Final = ("money_limit", "model_call_limit", "time_limit_minutes", "retry_limit", "stop_loss")


class WorkflowError(Exception):
    """A programming error: something `to_j2` / `from_j2` cannot be given (a value that is not a mapping). Data that is
    merely wrong is a pydantic ValidationError, as everywhere in the library."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _raise(title: str, problems: Sequence[Problem]) -> NoReturn:
    """Fail validation with one error per problem, each at its own place (one ValueError could report only one)."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)}) for loc, text in problems])


# ---- what a workflow may spend --------------------------------------------------------------------------------------

class Resources(Value):
    """Adaptation's estimate of what a workflow needs (J2 `estimated_resources`)."""

    money: Annotated[int, Field(ge=0)] = 0
    calls: Annotated[int, Field(ge=0)] = 0
    time_minutes: Annotated[int, Field(ge=0)] = 0


class Envelope(Value):
    """What Priority grants a workflow to spend (J2:5190, 166). ROLE:priority also lists proposal_id and valid_until; J2's
    code has neither, so they are omitted."""

    money_limit: Annotated[int, Field(ge=0)]
    model_call_limit: Annotated[int, Field(ge=0)] = 2
    time_limit_minutes: Annotated[int, Field(ge=0)] = 10
    retry_limit: Annotated[int, Field(ge=0)] = 1
    stop_loss: Annotated[str, StringConstraints(max_length=300)] = ""

    @field_validator("time_limit_minutes", "stop_loss", mode="before")
    @classmethod
    def _null_is_the_default(cls, value: Any, info: Any) -> Any:
        """J2 stored `null` for these two when Priority left them out (2 of 500 saved envelopes), so a saved row must read."""
        if value is None:
            return cls.model_fields[info.field_name].default
        return value


# ---- steps ----------------------------------------------------------------------------------------------------------

class Step(Value):
    """One step of a workflow (abstract: use AIStep, CodeStep or AssignmentStep). `depends_on` names earlier steps."""

    id: Id20
    name: Name120
    depends_on: Annotated[list[Id20], Field(max_length=20)] = []
    on_failure: FailureAction | None = None

    @model_validator(mode="after")
    def _not_the_base(self) -> Self:
        if type(self) is Step:
            raise ValueError("Step is abstract: use AIStep, CodeStep or AssignmentStep")
        return self


class AIStep(Step):
    """A work atom done by a model (J2 `how.kind` AI): dispatched as llm or skill."""

    kind: Literal["ai"] = "ai"
    atom: AtomDraft

    @model_validator(mode="after")
    def _is_ai_work(self) -> Self:
        problems: list[Problem] = []
        if self.atom.work.how_kind != "AI":
            problems.append((("atom", "work", "how_kind"), f"an AI step needs how_kind 'AI', this one has {self.atom.work.how_kind!r}"))
        if self.atom.work.dispatch_kind not in ("llm", "skill"):
            problems.append((("atom", "work", "dispatch_kind"),
                             f"an AI step is dispatched as llm or skill, this one as {self.atom.work.dispatch_kind!r}"))
        if problems:
            _raise("AIStep", problems)
        return self


class CodeStep(Step):
    """A work atom done by code or by the owner (J2 `how.kind` code; a send deed is a code step, AS:69-75)."""

    kind: Literal["code"] = "code"
    atom: AtomDraft

    @model_validator(mode="after")
    def _is_code_work(self) -> Self:
        problems: list[Problem] = []
        if self.atom.work.how_kind != "code":
            problems.append((("atom", "work", "how_kind"), f"a code step needs how_kind 'code', this one has {self.atom.work.how_kind!r}"))
        if self.atom.work.dispatch_kind not in ("bash", "manual"):
            problems.append((("atom", "work", "dispatch_kind"),
                             f"a code step is dispatched as bash or manual, this one as {self.atom.work.dispatch_kind!r}"))
        if problems:
            _raise("CodeStep", problems)
        return self


class AssignmentStep(Step):
    """A piece of a request given to one department (the chat agent's refs a1 to a5): its brief, an optional division
    scope, and an earlier task it continues."""

    kind: Literal["assignment"] = "assignment"
    dept: NodeId
    scope: NodeId | None = None
    brief: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    follows: Annotated[str, StringConstraints(pattern=r"^tsk_[0-9a-f]{12}$")] | None = None
    depends_on: Annotated[list[Id20], Field(max_length=4)] = []


# ---- workflows ------------------------------------------------------------------------------------------------------

@record
class Workflow(Record):
    """A named plan of steps (abstract). Step ids are unique and a step depends only on an EARLIER step."""

    ABSTRACT = True
    FAMILY = "workflow"

    name: Name120
    steps: Annotated[list[Annotated[Union[AIStep, CodeStep, AssignmentStep], Field(discriminator="kind")]],
                     Field(min_length=1, max_length=12)]
    failure_policy: FailureAction = "escalate"     # ADR-011 names the set, not the default: escalate is the library's choice (DL8)

    @model_validator(mode="after")
    def _steps_form_a_plan(self) -> Self:
        problems: list[Problem] = []
        first: dict[str, int] = {}
        for index, step in enumerate(self.steps):
            if step.id in first:
                problems.append((("steps", index, "id"), f"step {index + 1} repeats the id {step.id!r} of step {first[step.id] + 1}: ids must differ"))
            for pos, dep in enumerate(step.depends_on):
                if dep not in first:                 # `first` holds only the steps before this one
                    problems.append((("steps", index, "depends_on", pos),
                                     f"step {step.id!r} depends on {dep!r}, which is not an earlier step"))
            first.setdefault(step.id, index)
        if problems:
            _raise(type(self).__name__, problems)
        return self


@record
class TaskWorkflow(Workflow):
    """What the chat agent plans across departments: assignment steps only. `id` is the request id "req-<message id>"."""

    kind: Literal["task"] = "task"
    id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    steps: Annotated[list[AssignmentStep], Field(min_length=1, max_length=12)]


_DEPT_HOUSEKEEPING = frozenset({"schema_version", "failure_policy", "output", "inputs", "capabilities", "risks", "trigger",
                                "authority_touched"})


class DeptWorkflow(Workflow):
    """A workflow inside one department (abstract): J2's workflow dict, whose `atoms` are the `steps`. `name`, `goal_gap`,
    `outputs` and `completion_check` are required and non-empty (J2 `REQUIRED`, J2:6611)."""

    ABSTRACT = True
    # The model sends what J2's WF_FMT asks for. Code-set and role-file fields are left out of its reply.
    TRANSPORT_OPTIONAL = _DEPT_HOUSEKEEPING

    steps: Annotated[list[Annotated[Union[AIStep, CodeStep], Field(discriminator="kind")]], Field(min_length=1, max_length=12)]
    goal_gap: Annotated[str, StringConstraints(min_length=1, max_length=400)]
    expected_outcome: Text400 = ""
    outputs: Annotated[list[Line200], Field(min_length=1, max_length=20)]
    completion_check: Annotated[str, StringConstraints(min_length=1, max_length=400)]
    dependencies: Annotated[list[Line40], Field(max_length=20)] = []
    parts: Annotated[list[Line80], Field(max_length=60)] = []                      # rate-card items, repeated for quantity
    covers: Annotated[list[Count], Field(max_length=60)] = []                       # done-when item numbers
    fixes: Annotated[list[Line40], Field(max_length=20)] = []                       # Audit finding ids
    revises: Line40 | None = None
    estimated_resources: Resources = Field(default_factory=Resources)
    output: Literal["website", "prd", "hld", "lld", "project"] = "website"
    # role-file fields (ROLE:adaptation:20-37), absent from J2's reply format
    inputs: Annotated[list[Line200], Field(max_length=10)] = []
    capabilities: Annotated[list[Line200], Field(max_length=10)] = []
    risks: Annotated[list[Line200], Field(max_length=10)] = []
    trigger: Line200 | None = None
    authority_touched: Literal["local", "cross_department", "external"] | None = None


class Research(Value):
    """A research workflow (realization.md): it finds sources and delivers no done-when item (RS:27-30, 71-83)."""

    question: Line300
    feeds: Line300
    min_sources: Annotated[int, Field(ge=3)]
    output: ResearchRef


class Experiment(Value):
    """A probe in the experiment zone (JZ:94-135): what is tried, what is watched, when it is dropped, how far it goes."""

    hypothesis: Line300
    signal: Line300
    fails_if: Line300
    limit: Line300


_PLAN_FIELDS = frozenset({"envelope", "stage", "certainty", "done_test", "delivers", "informs", "inputs_from", "hold",
                          "research", "approach", "certainty_signals", "experiment"})


@record
class ProposedWorkflow(DeptWorkflow):
    """Adaptation's proposal, or Priority's grant of it (then `envelope` is set). The realization plan fields (RS:56-84)
    appear only when J2_REALIZATION is on."""

    TRANSPORT_OPTIONAL = _DEPT_HOUSEKEEPING | _PLAN_FIELDS

    kind: Literal["proposed"] = "proposed"
    id: Line40
    envelope: Envelope | None = None
    stage: StageId | None = None
    certainty: ZoneName | None = None
    certainty_signals: Annotated[list[Line300], Field(max_length=10)] = []
    approach: Annotated[str, StringConstraints(max_length=600)] | None = None
    done_test: Annotated[str, StringConstraints(max_length=600)] | None = None
    delivers: Annotated[list[Count], Field(max_length=60)] = []
    informs: Annotated[list[Count], Field(max_length=60)] = []
    inputs_from: Annotated[list[Line200], Field(max_length=20)] = []          # names of workflows it reads
    hold: Literal["waiting_on_identity", "waiting_on_dependency"] | None = None
    research: Research | None = None
    experiment: Experiment | None = None

    @model_validator(mode="after")
    def _research_rules(self) -> Self:
        problems: list[Problem] = []
        if self.research is not None:
            if self.delivers:
                problems.append((("delivers",), "a research workflow delivers no done-when item: delivers must be empty"))
            if self.stage == "build":
                problems.append((("stage",), "a research workflow is not in the build stage"))
        if problems:
            _raise("ProposedWorkflow", problems)
        return self


Status = Literal["registered", "held", "running", "done", "failed", "unfunded"]


@record
class RegisteredWorkflow(DeptWorkflow):
    """The workflow as the validator registered it (J2:6672-6678 and the keys code adds as the workflow runs). `atoms`
    lists the J2 atom ids ("W-n.a1"); the atoms themselves are the `steps`, and each id is `<id>.<step id>`."""

    kind: Literal["registered"] = "registered"
    id: WorkflowId
    proposal_id: Line40 | None = None
    covers_text: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=600)]], Field(max_length=60)] = []
    purpose: Annotated[str, StringConstraints(max_length=600)] = ""
    cost: Annotated[int, Field(ge=0)]
    estimate: Annotated[int, Field(ge=0)] = 0
    envelope: Envelope
    charged: bool = False
    calls_used: Annotated[int, Field(ge=0)] = 0
    retries_used: Annotated[int, Field(ge=0)] = 0
    status: Status
    cycle: Count = 1
    atoms: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=40)]], Field(max_length=12)] = []
    lld_sections: Annotated[list[Line80], Field(max_length=20)] = []
    section: Annotated[str, StringConstraints(max_length=40)] = ""
    agent: Annotated[str, StringConstraints(max_length=80)] = ""
    stage: Line40 | None = None
    change: Line40 | None = None
    kept: Annotated[str, StringConstraints(max_length=200)] | None = None
    last_check: Annotated[str, StringConstraints(max_length=2000)] | None = None
    send_error: Annotated[str, StringConstraints(max_length=2000)] | None = None
    hold_override: bool = False
    approval_asked: bool = False
    style_guide: bool = False
    version: Annotated[int, Field(ge=0)] | None = None      # the site version the work ended at: 0 for work that makes none (the Plan workflow)
    artifact: Annotated[str, StringConstraints(max_length=300)] | None = None

    @model_validator(mode="after")
    def _atoms_are_the_steps(self) -> Self:
        want = [f"{self.id}.{step.id}" for step in self.steps]
        if self.atoms and self.atoms != want:
            _raise("RegisteredWorkflow", [(("atoms",), f"atoms must be {', '.join(want)} (the workflow id, a dot and each step id)")])
        return self


# ---- J2's dicts -----------------------------------------------------------------------------------------------------

_DEFAULT_FILE: Final = "index.html"
_EXPECTED_KEYS: Final = ("text", "kind", "target", "count", "steps", "met")


def _as_mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkflowError("not_a_mapping", f"{what} must be a dict, not {type(value).__name__}")
    return value


def _count(expect: Any) -> int:
    """A grep-count's minimum: J2 keeps it in `expect`; the plugin's third argument is a count of at least 1."""
    return max(expect, 1) if isinstance(expect, int) and not isinstance(expect, bool) else 1


def _check_from_j2(c: Mapping[str, Any]) -> Check:
    template, target, expect = c.get("type"), c.get("target"), c.get("expect")
    expect = expect if isinstance(expect, (bool, int)) else None
    items = [str(x) for x in (target if isinstance(target, list) else [] if target is None else [target]) if str(x)]
    if template == "grep-count":       # the plugin's (pattern, file, min); J2's target is the pattern, the count is `expect`
        args = [*items[:1], str(c.get("file") or _DEFAULT_FILE), str(_count(expect))] if items else []
    else:
        args = items
    return Check(template=template, args=args, text=str(c.get("text") or ""), expect=expect)


def _check_to_j2(check: Check) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if check.text:
        out["text"] = check.text
    out["type"] = check.template
    if check.template == "grep-count":
        out["target"] = check.args[0] if check.args else ""
        if len(check.args) > 1 and check.args[1] != _DEFAULT_FILE:
            out["file"] = check.args[1]
        expect = check.expect if check.expect is not None else (int(check.args[2]) if len(check.args) > 2 and check.args[2].isdigit() else None)
    else:
        out["target"] = check.args[0] if len(check.args) == 1 else list(check.args)
        expect = check.expect
    if expect is not None:
        out["expect"] = expect
    return out


def _expected_from_j2(x: Mapping[str, Any]) -> ExpectedItem:
    return ExpectedItem.model_validate({k: v for k, v in x.items() if k in _EXPECTED_KEYS})


def _expected_to_j2(item: ExpectedItem) -> dict[str, Any]:
    out: dict[str, Any] = {"text": item.text, "kind": item.kind, "target": item.target}
    if item.count != 1:
        out["count"] = item.count
    if item.steps:
        out["steps"] = list(item.steps)
    if item.met is not None:
        out["met"] = item.met
    return out


def _step_from_j2(atom: Mapping[str, Any], step_id: str) -> AIStep | CodeStep:
    how = atom.get("how") if isinstance(atom.get("how"), Mapping) else {}
    how_kind = how.get("kind") or "AI"
    draft = AtomDraft(
        goal=str(atom.get("goal") or ""),
        constraints=[Constraint(text=str(t)) for t in atom.get("constraints") or []],
        context=[str(t) for t in atom.get("context") or []],
        work=Work(dispatch_kind="llm" if how_kind == "AI" else "bash", agent=how.get("agent") or None,
                  steps=str(how.get("steps") or ""), how_kind=how_kind),
        expected=[_expected_from_j2(_as_mapping(x, "an expected_output item")) for x in atom.get("expected_output") or []],
        verify=Verify(checks=[_check_from_j2(_as_mapping(x, "a verification item")) for x in atom.get("verification") or []]))
    name = clip(draft.goal, 120) or step_id
    return (AIStep if how_kind == "AI" else CodeStep)(id=step_id, name=name, atom=draft)


def _atom_to_j2(step: AIStep | CodeStep, atom_id: str) -> dict[str, Any]:
    atom = step.atom
    how: dict[str, Any] = {"kind": atom.work.how_kind}
    if atom.work.agent is not None:
        how["agent"] = atom.work.agent
    how["steps"] = atom.work.steps
    return {"id": atom_id, "goal": atom.goal, "constraints": [c.text for c in atom.constraints], "context": list(atom.context),
            "how": how, "expected_output": [_expected_to_j2(x) for x in atom.expected],
            "verification": [_check_to_j2(c) for c in atom.verify.checks]}


def _dept_fields_from_j2(d: Mapping[str, Any]) -> dict[str, Any]:
    """The keys every J2 workflow dict shares, as DeptWorkflow fields. Keys the model does not have are dropped."""
    atoms = [_as_mapping(a, "an atom") for a in d.get("atoms") or []]
    steps = [_step_from_j2(a, str(a.get("id") or f"a{n}").rsplit(".", 1)[-1]) for n, a in enumerate(atoms, 1)]
    out: dict[str, Any] = {"name": d.get("name"), "goal_gap": d.get("goal_gap"), "outputs": d.get("outputs"),
                           "completion_check": d.get("completion_check"), "steps": steps}
    for key in ("expected_outcome", "dependencies", "parts", "covers", "fixes", "revises", "output", "inputs", "capabilities",
                "risks", "trigger", "authority_touched"):
        if d.get(key) is not None:
            out[key] = d[key]
    resources = d.get("estimated_resources")
    if isinstance(resources, Mapping):
        out["estimated_resources"] = {k: v for k, v in resources.items() if k in ("money", "calls", "time_minutes") and v is not None}
    return out


def from_j2(d: Mapping[str, Any], *, id: str = "P-1") -> ProposedWorkflow:
    """J2's workflow dict (WF_FMT / GRANT_FMT, `atoms` as steps) as a ProposedWorkflow. `id` is used when the dict has none
    (EXAMPLE_WORKFLOW has none). Plan fields and the envelope are read when present; keys the model lacks are dropped."""
    d = _as_mapping(d, "a workflow")
    fields = _dept_fields_from_j2(d)
    fields["id"] = str(d.get("id") or id)
    for key in _PLAN_FIELDS - {"envelope"}:
        if d.get(key) is not None:
            fields[key] = d[key]
    env = d.get("envelope")
    if isinstance(env, Mapping):
        fields["envelope"] = {k: v for k, v in env.items() if k in ENVELOPE_KEYS and v is not None}
    return ProposedWorkflow.model_validate(fields)


def registered_from_j2(row: Mapping[str, Any]) -> RegisteredWorkflow:
    """One row of J2's workflows.json as a RegisteredWorkflow (its `atoms` are atom dicts with ids "W-n.a1"; a legacy row
    without atoms is refused, since a workflow has at least one step). `purpose` fills `goal_gap` when the row has none."""
    row = _as_mapping(row, "a workflow row")
    fields = _dept_fields_from_j2({**row, "goal_gap": row.get("goal_gap") or row.get("purpose")})
    fields["id"] = row.get("id")
    fields["atoms"] = [str(a.get("id")) for a in row.get("atoms") or [] if isinstance(a, Mapping)]
    for key in ("proposal_id", "covers_text", "purpose", "cost", "estimate", "charged", "calls_used", "retries_used", "status",
                "cycle", "lld_sections", "section", "agent", "stage", "change", "kept", "last_check", "send_error",
                "hold_override", "approval_asked", "style_guide", "version", "artifact"):
        if row.get(key) is not None:
            fields[key] = row[key]
    env = row.get("envelope")
    fields["envelope"] = {k: v for k, v in env.items() if k in ENVELOPE_KEYS and v is not None} if isinstance(env, Mapping) else env
    return RegisteredWorkflow.model_validate(fields)


def to_j2(w: ProposedWorkflow | RegisteredWorkflow) -> dict[str, Any]:
    """A department workflow as J2's dict. Keys that hold their default are left out, as in J2's own examples; a registered
    workflow's atoms carry the ids "<workflow id>.<step id>". What an AtomDraft holds beyond J2's six atom fields
    (touches, outputs, depends_on, supersedes, model, effort) has no place in J2's dict and is not written."""
    if not isinstance(w, (ProposedWorkflow, RegisteredWorkflow)):
        raise WorkflowError("not_a_department_workflow", f"to_j2 takes a ProposedWorkflow or RegisteredWorkflow, not {type(w).__name__}")
    out: dict[str, Any] = {"id": w.id, "name": w.name, "goal_gap": w.goal_gap}
    if w.expected_outcome:
        out["expected_outcome"] = w.expected_outcome
    out["outputs"] = list(w.outputs)
    out["completion_check"] = w.completion_check
    for key in ("dependencies", "parts", "covers", "fixes", "inputs", "capabilities", "risks"):
        if getattr(w, key):
            out[key] = list(getattr(w, key))
    for key in ("revises", "trigger", "authority_touched"):
        if getattr(w, key) is not None:
            out[key] = getattr(w, key)
    if w.output != "website":
        out["output"] = w.output
    if w.estimated_resources != Resources():
        out["estimated_resources"] = w.estimated_resources.model_dump()
    if w.envelope is not None:
        out["envelope"] = w.envelope.model_dump()
    registered = isinstance(w, RegisteredWorkflow)
    out["atoms"] = [_atom_to_j2(s, f"{w.id}.{s.id}" if registered else s.id) for s in w.steps]
    if isinstance(w, ProposedWorkflow):
        for key in sorted(_PLAN_FIELDS - {"envelope"}):
            value = getattr(w, key)
            if value not in (None, [], ""):
                out[key] = value.model_dump(exclude_none=True) if isinstance(value, Value) else value
    else:
        for key in ("proposal_id", "covers_text", "purpose", "cost", "estimate", "charged", "calls_used", "retries_used", "status",
                    "cycle", "lld_sections", "section", "agent", "stage", "change", "kept", "last_check", "send_error",
                    "hold_override", "approval_asked", "style_guide", "version", "artifact"):
            out[key] = getattr(w, key)
    return out
