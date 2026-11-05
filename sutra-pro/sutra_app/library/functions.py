"""The five function models: what Identity, Adaptation, Priority, Coordination and Audit say back (library design section 6).

Each function has a FAMILY named after it. Each turn J2 asks of it is a KIND, one class, because a transport schema is
per class (design 3.5):

    identity      intake  ruling  heard  done  approval  approval_ask
    adaptation    propose  respond  atom_verdict  lesson
    priority      price  envelope_check
    coordination  schedule
    audit         report

Every reply class carries `say` and `reason` (J2's builders put `reason` first) and, where J2 asks for one, a `next` limited
to the functions that turn may hand to (J2 `next_field`). Fields and rules come from the J2 reply formats named on each
class. The classes are model-facing: the connector asks for `transport_schema(family, kind=...)`, `ReplyParser` reads the
reply. A validator reports every violation it finds, not only the first.

Transport. A field that is an optional class or an optional union loses its `null` in the transport schema (it becomes a
one-member `anyOf`, kept so that J2's schema shas stay comparable), so each such field is in the class's
`TRANSPORT_OPTIONAL` and the model OMITS it instead of sending null. `schema_version` and `reason` are optional too.

Also here: `Envelope`'s sibling `Certainty` with `certainty_zone`, `Conflict` (J2's conflicts.json) and `Lesson` (J2's
memory/lessons.jsonl).
"""
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal, NoReturn, Self, Union

from pydantic import Field, StringConstraints, ValidationError, model_validator
from pydantic_core import InitErrorDetails, core_schema

from .atom import Check
from .base import Record, Value
from .goal import DocGoalDraft, Question, SiteGoalDraft, TbcAnswer, goal_kind
from .registry import record
from .replies import tolerate
from .types import AtomId, FindingId, FunctionName, JsonObject, WorkflowId
from .workflow import ProposedWorkflow, StageId, WorkflowError, ZoneName, from_j2

__all__ = [
    "ZONES", "SIGNALS", "Signal", "Signals", "Certainty", "certainty_zone", "signal_answer", "Analysis", "Dispute", "LeftOut",
    "Deferred", "Factor", "Unplaced", "PlanStage", "OpenFact", "NotReady", "RealizationFields", "LessonDraft", "HoldRow",
    "FindingRow", "RubricRow", "FunctionReply", "IdentityReply", "AdaptationReply", "PriorityReply", "CoordinationReply",
    "AuditReply", "Intake", "Ruling", "Heard", "Done", "Approval", "ApprovalAsk", "Propose", "Respond", "AtomVerdict",
    "LessonReply", "Price", "EnvelopeCheck", "Schedule", "Report", "Lesson", "Conflict", "Attempt", "IdentityTurn",
    "REPLY_CLASSES",
]

Problem = tuple[tuple[str | int, ...], str]       # (place inside the model, what is wrong)

ZONES: Final = ("operate", "analyze", "experiment", "stabilize")       # Cynefin: clear, complicated, complex, chaotic
SIGNALS: Final = ("broken", "reaction", "facts_given", "known_pattern", "open_choices")

Line40 = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Line300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Line600 = Annotated[str, StringConstraints(min_length=1, max_length=600)]
Text300 = Annotated[str, StringConstraints(max_length=300)]
Text600 = Annotated[str, StringConstraints(max_length=600)]
Text1000 = Annotated[str, StringConstraints(max_length=1000)]
Say = Annotated[str, StringConstraints(max_length=4000)]
Count = Annotated[int, Field(ge=1)]
Whole = Annotated[int, Field(ge=0)]
Verdict = Literal["PASS", "PASS_WITH_WARNING", "NEEDS_REVISION", "BLOCKED_BY_EVIDENCE", "POLICY_CONCERN"]
PASSING: Final = ("PASS", "PASS_WITH_WARNING")


def _raise(title: str, problems: Sequence[Problem]) -> NoReturn:
    """Fail validation with one error per problem, each at its own place (one ValueError could report only one)."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)}) for loc, text in problems])


# ---- the workflows of a reply, read the way J2 words them (GAP-TUNE, G14) -----------------------------------------------

def _read_workflows(value: Any) -> Any:
    """A reply's `workflows`, each as a ProposedWorkflow. J2 words a workflow with `atoms` (its WF_FMT) and gives it no `id`
    (the validator numbers it when it registers it); the class says `steps` and wants an `id`. A workflow with `atoms` and no
    `steps` is read through `from_j2`; one with `steps` and no `id` gets `P-<position>`; the reply parser's tolerant pass
    (which would drop `atoms` as an undeclared key before any validator runs) is applied here to the second kind. What is
    still wrong is reported at its place, one violation each, as the strict class would."""
    if not isinstance(value, list):
        return value
    out: list[Any] = []
    problems: list[Problem] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            out.append(item)
            continue
        try:
            if "steps" not in item and "atoms" in item:
                out.append(from_j2(item, id=f"P-{index + 1}"))
            else:
                data, _, _ = tolerate(ProposedWorkflow, dict(item))
                out.append({**data, "id": data.get("id") or f"P-{index + 1}"})
        except ValidationError as exc:
            for error in exc.errors():
                text = str(error["msg"]).removeprefix("Value error, ")
                problems.append(((index, *error["loc"]), text))
        except WorkflowError as exc:
            problems.append(((index,), str(exc)))
    if problems:
        _raise("workflows", problems)
    return out


class _ReplyWorkflows:
    """`list[ProposedWorkflow]` (at most 20) whose items are read by `_read_workflows` first. A class of its own, not an
    `Annotated` alias, so that the reply parser's pre-pass (which walks the declared types) does not drop J2's `atoms`.
    Its JSON schema is the list's, so the exported schemas do not change."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
        inner = handler.generate_schema(Annotated[list[ProposedWorkflow], Field(max_length=20)])
        return core_schema.no_info_before_validator_function(_read_workflows, inner)


if TYPE_CHECKING:
    _Workflows = list[ProposedWorkflow]
else:
    _Workflows = _ReplyWorkflows


# ---- certainty (adaptation.md, Certainty section; JZ:77-135) --------------------------------------------------------

def signal_answer(signals: Mapping[str, Any] | None, key: str) -> str:
    """yes, no or unknown, from {"answer": ..., "evidence": ...} or a bare string (JZ:signal_answer)."""
    value = (signals or {}).get(key)
    answer = str((value.get("answer") if isinstance(value, dict) else value) or "unknown").strip().lower()
    return answer if answer in ("yes", "no") else "unknown"


def certainty_zone(signals: Any) -> str:
    """The Certainty rule (JZ:certainty_zone, ported): broken -> stabilize; reaction -> experiment; facts, a known pattern
    and no open choices -> operate; else analyze. Two or more unknowns move operate or analyze one zone toward less
    certainty. `signals` is a mapping of the five signals (each a dict with an `answer`, or a bare string) or a `Signals`."""
    if isinstance(signals, Value):
        signals = signals.model_dump()
    a = lambda key: signal_answer(signals, key)
    if a("broken") == "yes":
        return "stabilize"
    if a("reaction") == "yes":
        zone = "experiment"
    elif a("facts_given") == "yes" and a("known_pattern") == "yes" and a("open_choices") == "no":
        zone = "operate"
    else:
        zone = "analyze"
    if sum(a(k) == "unknown" for k in SIGNALS) >= 2 and zone in ("operate", "analyze"):
        zone = ZONES[ZONES.index(zone) + 1]
    return zone


class Signal(Value):
    answer: Literal["yes", "no", "unknown"]
    evidence: Text600 = ""


class Signals(Value):
    """All five signals the Certainty rule reads."""

    broken: Signal
    reaction: Signal
    facts_given: Signal
    known_pattern: Signal
    open_choices: Signal


class Certainty(Value):
    """Adaptation's reading of how certain the goal is. The zone may not contradict its own signals."""

    zone: ZoneName
    rationale: Text600 = ""
    signals: Signals

    @model_validator(mode="after")
    def _zone_follows_the_signals(self) -> Self:
        said = certainty_zone(self.signals)
        if said != self.zone:
            _raise("Certainty", [(("zone",), f"your signals give {said} by the Certainty rule, but zone says {self.zone}: "
                                              "fix the signals or the zone, and shape the workflows to match")])
        return self


# ---- small parts ----------------------------------------------------------------------------------------------------

class Analysis(Value):
    """The analyze zone's working: the options weighed and the one chosen."""

    options: Annotated[list[Line300], Field(max_length=10)] = []
    chosen: Line300
    why: Text600 = ""
    assumptions: Annotated[list[Line300], Field(max_length=10)] = []


class Dispute(Value):
    """Adaptation disagrees with an open Audit finding or a Coordination HOLD. `with` is a Python keyword, hence the alias."""

    with_: Literal["Audit", "Coordination"] = Field(alias="with")
    about: Line40            # a finding id or a workflow id
    reason: Line600


class LeftOut(Value):
    item: Count
    reason: Line300


class Deferred(Value):
    item: Line300
    until: Line300


class Factor(Value):
    """A factor of the realization plan (RS:13-100): where it comes from decides what it must carry."""

    name: Line300
    source: Literal["brief", "general", "research", "budget"]
    quote: Annotated[str, StringConstraints(max_length=1000)] | None = None
    citation: Annotated[str, StringConstraints(max_length=100)] | None = None
    why: Line600
    stages: Annotated[list[StageId], Field(max_length=35)] = []

    @model_validator(mode="after")
    def _source_rules(self) -> Self:
        problems: list[Problem] = []
        if self.source == "brief" and not (self.quote or "").strip():
            problems.append((("quote",), "a factor from the brief quotes the brief: quote must not be empty"))
        if self.source == "research" and not (self.citation and _CITATION.fullmatch(self.citation)):
            problems.append((("citation",), "a research factor cites a research entry such as research.md#R-1"))
        if self.source == "budget" and self.stages:
            problems.append((("stages",), "a budget factor belongs to no stage: stages must be empty"))
        if problems:
            _raise("Factor", problems)
        return self


class Unplaced(Value):
    name: Line300
    why: Line600


class PlanStage(Value):
    id: StageId
    thinking: Line300
    tiers: Annotated[list[Literal["strategy", "capability", "architecture", "feature", "contract", "implementation"]],
                     Field(min_length=1, max_length=6)]
    goal: Line600
    done_test: Line600
    method: Text600 | None = None
    owns_factors: Annotated[list[Line300], Field(max_length=60)] = []
    inputs_from: Annotated[list[StageId], Field(max_length=35)] = []


class OpenFact(Value):
    fact: Line300
    workflow: Line300
    blocking: bool
    handling: Text600 = ""


class NotReady(Value):
    workflow: Line300
    score: Annotated[float, Field(ge=0, le=1)]
    weakest: Literal["inputs", "method", "done_test", "factors", "zone_fit", "size"]
    stop_reason: Line600
    route: Literal["identity", "priority", "left_out"]


_CITATION: Final = re.compile(r"research\.md#R-[0-9]+")


class RealizationFields(Value):
    """The realization plan that sits on Adaptation's PROPOSE when J2_REALIZATION is on (design 9.4). `plan_faults`
    (R1 to R6, cycles) stays in the engine."""

    factors: Annotated[list[Factor], Field(max_length=60)] = []
    unplaced: Annotated[list[Unplaced], Field(max_length=60)] = []
    stages: Annotated[list[PlanStage], Field(max_length=35)] = []
    open_facts: Annotated[list[OpenFact], Field(max_length=60)] = []
    not_ready: Annotated[list[NotReady], Field(max_length=60)] = []


class LessonDraft(Value):
    """One lesson as Adaptation writes it (J2:9294)."""

    problem: Line600
    cause: Text600 = ""
    fix: Line600


class HoldRow(Value):
    id: WorkflowId
    missing: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class FindingRow(Value):
    """One finding of Audit's reply (J2:9062): exactly one per done-when item, plus one per extra issue."""

    id: FindingId
    item: Whole | None = None
    criterion: Text1000 = ""
    verdict: Verdict
    severity: Literal["low", "medium", "high", "critical"] | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    evidence: Text1000 = ""
    needs_requester_fact: Text300 | None = None


class RubricRow(Value):
    id: Annotated[str, StringConstraints(pattern=r"^[RD]-[0-9]{1,3}$")]
    verdict: Literal["PASS", "PASS_WITH_WARNING", "NEEDS_REVISION"]
    evidence: Text1000 = ""


# ---- the reply classes ----------------------------------------------------------------------------------------------

class FunctionReply(Record):
    """What every function reply carries (abstract). `reason` comes first, as in J2's builder replies."""

    ABSTRACT = True
    # schema_version is bookkeeping and reason is not asked by J2's function formats: the model may leave them out.
    TRANSPORT_OPTIONAL = frozenset({"schema_version", "reason"})

    reason: Text600 = ""
    say: Say = ""


class IdentityReply(FunctionReply):
    ABSTRACT = True
    FAMILY = "identity"


class AdaptationReply(FunctionReply):
    ABSTRACT = True
    FAMILY = "adaptation"


class PriorityReply(FunctionReply):
    ABSTRACT = True
    FAMILY = "priority"


class CoordinationReply(FunctionReply):
    ABSTRACT = True
    FAMILY = "coordination"


class AuditReply(FunctionReply):
    ABSTRACT = True
    FAMILY = "audit"


_Goal = Annotated[Union[SiteGoalDraft, DocGoalDraft], Field(discriminator="kind")]


@record
class Intake(IdentityReply):
    """J2.a (J2:4027-4032; ROLE:identity): is there enough to write the charter? Enough: the charter and no questions,
    handed to Adaptation. Not enough: 1 to 4 questions and no charter, handed to the Requester."""

    TRANSPORT_OPTIONAL = frozenset({"schema_version", "reason", "goal"})

    kind: Literal["intake"] = "intake"
    enough: bool
    questions: Annotated[list[Question], Field(max_length=4)] = []
    goal: _Goal | None = None
    to_requester: Text600 = ""
    to_agents: Text600 = ""
    next: Literal["Requester", "Adaptation"]

    @model_validator(mode="before")
    @classmethod
    def _goal_kind_from_its_shape(cls, data: Any) -> Any:
        """J2's charter has no `kind` key (goal.py): a goal without one is a document's when it names a product, else a site's."""
        goal = data.get("goal") if isinstance(data, Mapping) else None
        if isinstance(goal, Mapping) and "kind" not in goal:
            return {**data, "goal": {**goal, "kind": goal_kind(goal)}}
        return data

    @model_validator(mode="after")
    def _enough_or_ask(self) -> Self:
        problems: list[Problem] = []
        if self.enough:
            if self.goal is None:
                problems.append((("goal",), "enough is true: the charter (goal) is required"))
            if self.questions:
                problems.append((("questions",), "enough is true: ask no questions"))
            if self.next != "Adaptation":
                problems.append((("next",), "enough is true: the charter goes to Adaptation, next must be Adaptation"))
        else:
            if not 1 <= len(self.questions) <= 4:
                problems.append((("questions",), f"enough is false: ask 1 to 4 questions, this reply has {len(self.questions)}"))
            if self.goal is not None:
                problems.append((("goal",), "enough is false: record no charter yet (goal must be left out)"))
            if self.next != "Requester":
                problems.append((("next",), "enough is false: the questions go to the Requester, next must be Requester"))
        if problems:
            _raise("Intake", problems)
        return self


@record
class Ruling(IdentityReply):
    """J2.d (J2:4206-4213): Identity rules on a conflict two agents could not settle, or asks the Requester."""

    TRANSPORT_OPTIONAL = frozenset({"schema_version", "reason", "user_question"})

    kind: Literal["ruling"] = "ruling"
    clause: Line300
    facts: Annotated[list[Line300], Field(max_length=20)] = []
    resolved: bool
    ruling: Line40 | None = None            # one of the two parties (a function name), or "split" for a proposal
    workflows: Annotated[list[Line300], Field(max_length=20)] = []
    instruction: Text600 = ""
    user_question: Question | None = None

    @model_validator(mode="after")
    def _resolved_or_ask(self) -> Self:
        problems: list[Problem] = []
        if self.resolved:
            if not self.ruling:
                problems.append((("ruling",), "resolved is true: ruling must name whose position stands (or split)"))
        else:
            if self.ruling:
                problems.append((("ruling",), "resolved is false: give no ruling yet"))
            if self.user_question is None or len(self.user_question.options) < 2:
                problems.append((("user_question",), "resolved is false: ask the Requester one question with at least 2 options"))
        if self.ruling and self.ruling.strip().lower() == "split" and not self.workflows:
            problems.append((("workflows",), "a split names the workflows to register: workflows must not be empty"))
        if problems:
            _raise("Ruling", problems)
        return self


@record
class Heard(IdentityReply):
    """J2:4396-4402, DECISION_FMT (J2:1508): what the Requester's answer settles. J2 applies `add` unless the decision is
    ship (J2:4484), so these are ranges only."""

    kind: Literal["heard"] = "heard"
    clause: Text300 = ""
    decision: Literal["continue", "drop", "ship", "stop"] | None = None
    add: Whole | None = None
    drop_items: Annotated[list[Count], Field(max_length=40)] = []
    confirmed: Annotated[list[TbcAnswer], Field(max_length=40)] = []
    still_to_be_confirmed: Annotated[list[TbcAnswer], Field(max_length=40)] = []
    instruction_to_adaptation: Text600 | None = None
    next: Literal["Audit", "Adaptation"]


@record
class Done(IdentityReply):
    """J2.h (J2:4892-4896, 1504-1506): is the goal reached? The Requester hears it when it is done or when only they can help."""

    kind: Literal["done"] = "done"
    clause: Text300 = ""
    done: bool
    needs_requester: bool = False
    requester_questions: Annotated[list[Line300], Field(max_length=10)] = []
    instruction_to_adaptation: Text600 | None = None
    needs_decision: bool = False
    budget_needed: Whole | None = None
    next: Literal["Requester", "Adaptation"]

    @model_validator(mode="after")
    def _requester_hears_it_when_done(self) -> Self:
        goes_to_requester = self.done or self.needs_requester
        if (self.next == "Requester") != goes_to_requester:
            _raise("Done", [(("next",), "next is Requester exactly when done or needs_requester is true "
                                        f"(done={str(self.done).lower()}, needs_requester={str(self.needs_requester).lower()})")])
        return self


@record
class Approval(IdentityReply):
    """J2:4317: the Requester's answer to 'run this over its envelope?'. J2 uses `budget_increase` only when approved."""

    kind: Literal["approval"] = "approval"
    approved: bool
    budget_increase: Whole | None = None


@record
class ApprovalAsk(IdentityReply):
    """J2:4329: Priority asks for approval; Identity may not raise an envelope, so it denies or asks. J2's own mock sends
    ASK with no question (J2:4334-4335), so the question is not required."""

    TRANSPORT_OPTIONAL = frozenset({"schema_version", "reason", "user_question"})

    kind: Literal["approval_ask"] = "approval_ask"
    clause: Text300 = ""
    decision: Literal["DENY", "ASK"]
    user_question: Question | None = None


@record
class Propose(AdaptationReply, RealizationFields):
    """J2.b (J2:5396-5402; ROLE:adaptation): propose workflows, ask Identity a policy question, or dispute a finding."""

    TRANSPORT_OPTIONAL = frozenset({
        "schema_version", "reason", "dispute", "certainty_assessment", "analysis", "deferred",
        "factors", "unplaced", "stages", "open_facts", "not_ready"})

    kind: Literal["propose"] = "propose"
    act: Literal["PROPOSE", "POLICY_QUESTION", "DISPUTE"]
    workflows: _Workflows = []
    left_out: Annotated[list[LeftOut], Field(max_length=60)] = []
    question: Text600 | None = None
    dispute: Dispute | None = None
    playbook_used: Text300 | None = None
    playbook_changes: Text600 | None = None
    lesson_used: Text300 | None = None
    certainty_assessment: Certainty | None = None
    analysis: Analysis | None = None
    deferred: Annotated[list[Deferred], Field(max_length=20)] = []
    next: Literal["Priority", "Identity", "Audit", "Coordination"]

    @model_validator(mode="after")
    def _act_rules(self) -> Self:
        problems: list[Problem] = []
        if self.act == "PROPOSE" and not self.workflows:
            problems.append((("workflows",), "PROPOSE needs at least one workflow"))
        if self.act == "POLICY_QUESTION" and not (self.question or "").strip():
            problems.append((("question",), "POLICY_QUESTION needs the question for Identity"))
        if self.act == "DISPUTE" and self.dispute is None:
            problems.append((("dispute",), "DISPUTE needs the dispute (with, about, reason)"))
        zone = self.certainty_assessment.zone if self.certainty_assessment is not None else None
        if zone == "analyze" and not (self.analysis is not None and self.analysis.options):
            problems.append((("analysis",), "zone analyze needs analysis with options and chosen"))
        if zone == "experiment":
            probes = [w for w in self.workflows if w.certainty == "experiment"]
            if not 1 <= len(probes) <= 3:
                problems.append((("workflows",), f"zone experiment needs 1 to 3 experiment workflows (has {len(probes)})"))
            for index, w in enumerate(self.workflows):
                if w.certainty == "experiment" and w.experiment is None:
                    problems.append((("workflows", index, "experiment"),
                                     f"workflow {w.name}: an experiment workflow needs hypothesis, signal, fails_if and limit"))
        if problems:
            _raise("Propose", problems)
        return self


@record
class Respond(AdaptationReply):
    """J2 (J2:6285-6288): Adaptation answers Priority's decision on its proposal."""

    kind: Literal["respond"] = "respond"
    act: Literal["ACCEPT", "REVISE", "PARK"]
    workflows: _Workflows = []
    next: Literal["Priority", "Identity"]

    @model_validator(mode="after")
    def _revise_carries_the_revision(self) -> Self:
        if self.act == "REVISE" and not self.workflows:
            _raise("Respond", [(("workflows",), "REVISE needs the revised workflows")])
        if self.act != "REVISE" and self.workflows:
            _raise("Respond", [(("workflows",), f"{self.act} carries no workflows: workflows must be empty")])
        return self


@record
class AtomVerdict(AdaptationReply):
    """J2 (J2:8802-8806): a work atom failed its checks. Is the check wrong (send the corrected checks) or the build?"""

    kind: Literal["atom_verdict"] = "atom_verdict"
    verdict: Literal["CHECK_WRONG", "BUILD_WRONG"]
    atom: AtomId
    verification: Annotated[list[Check], Field(max_length=12)] = []
    affordable: bool | None = None
    build_wrong_reason: Text600 | None = None

    @model_validator(mode="after")
    def _verdict_rules(self) -> Self:
        problems: list[Problem] = []
        if self.verdict == "CHECK_WRONG" and not self.verification:
            problems.append((("verification",), "CHECK_WRONG needs the corrected checks (verification)"))
        if self.verdict == "BUILD_WRONG":
            if self.affordable is None:
                problems.append((("affordable",), "BUILD_WRONG needs affordable: can the budget left pay for a fix workflow?"))
            # J2 reads a missing reason as "no specific reason" and applies its own default (J2:9021), and its own mock says
            # what the build lacks in `say`: the reason may be left out when the message says it.
            if not (self.build_wrong_reason or self.say or "").strip():
                problems.append((("build_wrong_reason",), "BUILD_WRONG needs build_wrong_reason: exactly what the build lacks"))
        if problems:
            _raise("AtomVerdict", problems)
        return self


@record
class LessonReply(AdaptationReply):
    """J2 (J2:9287-9300): one lesson per problem Audit confirmed fixed."""

    kind: Literal["lesson"] = "lesson"
    lessons: Annotated[list[LessonDraft], Field(max_length=10)] = []


@record
class Price(PriorityReply):
    """J2.c (J2:6470-6471, 5190-5191, 6476-6481): Priority funds, counters or refuses. A funded workflow carries its
    envelope with a money limit of at least 1 (J2:6397)."""

    kind: Literal["price"] = "price"
    decision: Literal["GRANT", "COUNTER", "REFUSE"]
    workflows: _Workflows = []
    next: Literal["Adaptation", "Identity"]

    @model_validator(mode="after")
    def _funding_rules(self) -> Self:
        problems: list[Problem] = []
        if self.decision == "REFUSE":
            if self.workflows:
                problems.append((("workflows",), "REFUSE funds nothing: workflows must be empty"))
        else:
            if not self.workflows:
                problems.append((("workflows",), f"{self.decision} funds something: workflows must not be empty"))
            for index, w in enumerate(self.workflows):
                if w.envelope is None or w.envelope.money_limit < 1:
                    problems.append((("workflows", index, "envelope"),
                                     f"workflow {w.name}: a funded workflow needs envelope.money_limit of at least 1"))
        if problems:
            _raise("Price", problems)
        return self


@record
class EnvelopeCheck(PriorityReply):
    """J2.c (J2:6920-6921): a run is over its envelope. HOLD it (Coordination carries on) or REQUEST_APPROVAL from Identity."""

    kind: Literal["envelope_check"] = "envelope_check"
    decision: Literal["HOLD", "REQUEST_APPROVAL"]
    next: Literal["Coordination", "Identity"]

    @model_validator(mode="after")
    def _hold_goes_to_coordination(self) -> Self:
        if (self.decision == "HOLD") != (self.next == "Coordination"):
            _raise("EnvelopeCheck", [(("next",), "HOLD goes to Coordination and REQUEST_APPROVAL to Identity "
                                                  f"(decision {self.decision}, next {self.next})")])
        return self


@record
class Schedule(CoordinationReply):
    """J2.f (J2:6838-6841, 6854-6855; ROLE:coordination): order the registered workflows and name the holds."""

    kind: Literal["schedule"] = "schedule"
    rule: Line300
    order: Annotated[list[WorkflowId], Field(max_length=40)] = []
    holds: Annotated[list[HoldRow], Field(max_length=40)] = []
    next: Literal["Priority", "Adaptation"]

    @model_validator(mode="after")
    def _schedule_rules(self) -> Self:
        problems: list[Problem] = []
        for index, wid in enumerate(self.order):
            if wid in self.order[:index]:
                problems.append((("order", index), f"order repeats {wid}: each workflow once"))
        for index, row in enumerate(self.holds):
            if row.id in [h.id for h in self.holds[:index]]:
                problems.append((("holds", index, "id"), f"holds repeats {row.id}: each workflow once"))
        if self.next == "Adaptation":
            running = [wid for wid in self.order if wid not in {h.id for h in self.holds}]
            if running:
                problems.append((("next",), f"next is Adaptation only when every ordered workflow is held ({', '.join(running)} is not)"))
        if problems:
            _raise("Schedule", problems)
        return self


@record
class Report(AuditReply):
    """J2.g (J2:9062-9072, 9128-9136; ROLE:audit): one finding per done-when item plus one per extra issue, and one rubric
    row per rubric item. Every finding goes to Identity."""

    kind: Literal["report"] = "report"
    read: Text1000 | None = None                # a document check says what was read
    findings: Annotated[list[FindingRow], Field(max_length=120)] = []
    rubric: Annotated[list[RubricRow], Field(max_length=40)] = []
    next: Literal["Identity"]

    @model_validator(mode="after")
    def _findings_rules(self) -> Self:
        problems: list[Problem] = []
        first: dict[str, int] = {}
        for index, row in enumerate(self.findings):
            if row.id in first:
                problems.append((("findings", index, "id"), f"finding {index + 1} repeats the id {row.id} of finding {first[row.id] + 1}"))
            first.setdefault(row.id, index)
            if row.verdict in PASSING and not row.evidence.strip():
                problems.append((("findings", index, "evidence"), f"{row.id}: a {row.verdict} needs evidence (what you observed)"))
        seen: dict[str, int] = {}
        for index, row in enumerate(self.rubric):
            if row.id in seen:
                problems.append((("rubric", index, "id"), f"rubric row {index + 1} repeats the id {row.id}"))
            seen.setdefault(row.id, index)
            if row.verdict in PASSING and not row.evidence.strip():
                problems.append((("rubric", index, "evidence"), f"{row.id}: a {row.verdict} needs evidence"))
        if problems:
            _raise("Report", problems)
        return self


# the reply class of each (family, kind), in the order of the design's table 6
REPLY_CLASSES: Final = {
    ("identity", "intake"): Intake, ("identity", "ruling"): Ruling, ("identity", "heard"): Heard, ("identity", "done"): Done,
    ("identity", "approval"): Approval, ("identity", "approval_ask"): ApprovalAsk,
    ("adaptation", "propose"): Propose, ("adaptation", "respond"): Respond, ("adaptation", "atom_verdict"): AtomVerdict,
    ("adaptation", "lesson"): LessonReply, ("priority", "price"): Price, ("priority", "envelope_check"): EnvelopeCheck,
    ("coordination", "schedule"): Schedule, ("audit", "report"): Report,
}


# ---- what code stores ------------------------------------------------------------------------------------------------

@record
class Lesson(Record):
    """A lesson saved for future runs (J2:9300; memory/lessons.jsonl): the problem, its cause and the fix that worked, with
    where it was learnt. J2's lines have no `kind`: the catalogue supplies it."""

    FAMILY = "lesson"

    kind: Literal["lesson"] = "lesson"
    id: Annotated[str, StringConstraints(pattern=r"^L-[A-Za-z0-9_.-]{1,60}-[0-9]{1,6}$")]
    problem: Line600
    cause: Text600 = ""
    fix: Line600
    run: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    cycle: Whole
    versions: Annotated[list[Count], Field(min_length=2, max_length=2)]
    workflows: Annotated[list[WorkflowId], Field(max_length=40)] = []
    t: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    output: Annotated[str, StringConstraints(max_length=20)] | None = None
    test: bool | None = None
    mock: bool | None = None


class Attempt(Value):
    """One attempt of a function to settle a conflict (J2:4948). `n` is 0 for the opening message."""

    n: Whole
    who: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    msg: Whole | None = None
    text: Annotated[str, StringConstraints(max_length=20_000)] = ""
    position: Annotated[str, StringConstraints(max_length=20_000)] = ""
    agree: bool | None = None            # J2 writes null on the opening attempt (n 0) of a proposal conflict


class IdentityTurn(Value):
    """One time Identity ruled on a conflict (J2:4256)."""

    say: Annotated[str, StringConstraints(max_length=4000)] | None = None
    clause: Text300 | None = None
    resolved: bool
    ruling: Text300 | None = None
    after_user: bool = False


@record
class Conflict(Record):
    """A disagreement between two functions and how it ended (J2:4936-4941, 4256; conflicts.json). Besides the keys the
    design lists it carries the ones J2's code sets as the conflict is settled (`attempts_used`, the final positions, the
    repricing and the document-mode rounds); a key J2 adds later fails the golden-run test, which is how the list stays complete."""

    FAMILY = "conflict"

    kind: Literal["conflict"] = "conflict"
    id: Annotated[str, StringConstraints(pattern=r"^C-[0-9]{1,6}$")]
    cycle: Whole
    topic: Literal["proposal", "finding", "hold"]
    between: Annotated[list[FunctionName], Field(min_length=2, max_length=2)]
    about: Annotated[str, StringConstraints(max_length=200)] | None = None
    subject: Annotated[str, StringConstraints(max_length=600)] = ""
    detail: Annotated[str, StringConstraints(max_length=4000)] | None = None
    attempts: Annotated[list[Attempt], Field(max_length=20)] = []
    status: Literal["open", "escalated", "repricing", "settled"]
    escalated: bool = False
    resolved_by: Literal["agents", "identity", "identity_after_user", "default"] | None = None
    identity: Annotated[list[IdentityTurn], Field(max_length=10)] = []
    escalated_to_user: bool = False
    user_question: Question | None = None
    user_answer: Annotated[str, StringConstraints(max_length=20_000)] | None = None
    winner: Annotated[str, StringConstraints(max_length=40)] | None = None
    outcome: Annotated[str, StringConstraints(max_length=4000)] | None = None
    escalated_because: Annotated[str, StringConstraints(max_length=1000)] | None = None
    # set by code as the conflict goes on (J2:4955-4970, 5058, 6319-6423, 6483, 6726, 6814)
    attempts_before_escalation: Whole | None = None
    attempts_used: Whole | None = None
    adaptation_final: Annotated[list[JsonObject], Field(max_length=20)] = []
    priority_final: Annotated[list[JsonObject], Field(max_length=20)] = []
    registered: Annotated[list[Annotated[str, StringConstraints(max_length=200)]], Field(max_length=20)] = []
    repriced: bool | None = None
    pending_winner: Annotated[str, StringConstraints(max_length=40)] | None = None
    ruled_wfs: Annotated[list[JsonObject], Field(max_length=20)] = []
    repricing: JsonObject | None = None
    cut: Annotated[list[Annotated[str, StringConstraints(max_length=200)]], Field(max_length=40)] = []
    resend: Annotated[list[Annotated[str, StringConstraints(max_length=200)]], Field(max_length=40)] = []
    resend_asks: Whole | None = None
    rounds: JsonObject | None = None
    objections: Annotated[list[JsonObject], Field(max_length=100)] = []
    rulings: Annotated[list[JsonObject], Field(max_length=100)] = []

    @model_validator(mode="after")
    def _conflict_rules(self) -> Self:
        problems: list[Problem] = []
        if len(set(self.between)) != 2:
            problems.append((("between",), "a conflict is between two different functions"))
        if self.status == "settled" and self.outcome is None:
            problems.append((("outcome",), "a settled conflict records its outcome"))
        if self.status == "escalated" and not self.escalated:
            problems.append((("escalated",), "status escalated: escalated must be true"))
        if self.resolved_by == "identity_after_user" and not self.escalated_to_user:
            problems.append((("resolved_by",), "identity_after_user means the Requester was asked: escalated_to_user must be true"))
        if problems:
            _raise("Conflict", problems)
        return self
