"""Evaluation: a judgement of a subject against a Goal (library design section 5, the owner's "Evaluation").

One family, "evaluation", four kinds; the vocabulary is J2's:

    result    Audit's check of a build against the charter: the J2 audit entry of audits.json (J2:8966)
    recheck   a re-run of an atom's own checks after a board answer changed a document (J2:7928)
    plan      the confidence judge's score for one planned workflow (j2_realization.py `settle`)
    run       the reviewer's verdict on a finished run (REVIEW_FMT, J2:9317)

and the parts of a result: `Finding` (a done-when item's row, or an extra issue), `RubricResult` (a design or document
rubric row), `ConditionResult` (a necessary condition checked by code).

The stored rows carry more than the design's first list of keys, because J2's code writes more: a finding can be UNPAID
(`_flag_unpaid`, J2:9170) or WITHDRAWN (a settled dispute, J2:5079), an extra issue has no `pass`, a rubric row can be
BLOCKED_BY_EVIDENCE and carries `item`, `criterion`, `rubric` and `severity`, a condition carries its `text` and `check`
and for the document checks its `assumptions`, a forced test row carries `forced_test` and `real_verdict`, and an entry
for a document or an LLD comparison carries `output`, `read` and `lld`. Each was read in J2's code and seen in its saved
runs. J2's audit entry has no `kind`: whoever checks audits.json adds `"kind": "result"` (a recheck entry has its own).
"""
from collections.abc import Sequence
from typing import Annotated, Final, Literal, NoReturn, Self

from pydantic import Field, StringConstraints, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from .base import Record, Value
from .registry import record
from .types import AtomId, FindingId, JsonObject

__all__ = [
    "PLAN_GATE", "PASSING_VERDICTS", "Evaluation", "Finding", "RubricResult", "ConditionResult", "LldMismatch",
    "LldComparison", "ResultEvaluation", "RecheckResult", "RecheckEvaluation", "JudgeAnswer", "PlanEvaluation",
    "AgentReview", "RunReview",
]

PLAN_GATE: Final = 0.80       # a workflow scoring below this is not ready (j2_realization.THRESHOLD)
# These verdicts mean the item passes; every other verdict is a failure. WITHDRAWN is a finding the agents settled in
# Adaptation's favour (J2:5079 sets pass true); UNPAID is a pass that no workflow paid for (J2:9180 sets pass false).
PASSING_VERDICTS: Final = frozenset({"PASS", "PASS_WITH_WARNING", "WITHDRAWN"})
_NEEDS_EVIDENCE: Final = frozenset({"PASS", "PASS_WITH_WARNING"})                  # audit.md: a pass without evidence is not one

Problem = tuple[tuple[str | int, ...], str]       # (place inside the model, what is wrong)

Verdict = Literal["PASS", "PASS_WITH_WARNING", "NEEDS_REVISION", "BLOCKED_BY_EVIDENCE", "POLICY_CONCERN", "TO_BE_CONFIRMED",
                  "UNPAID", "WITHDRAWN"]
RubricVerdict = Literal["PASS", "PASS_WITH_WARNING", "NEEDS_REVISION", "BLOCKED_BY_EVIDENCE", "WITHDRAWN"]
Severity = Literal["low", "medium", "high", "critical"]
Confidence = Literal["low", "medium", "high"]

Criterion = Annotated[str, StringConstraints(max_length=600)]
Evidence = Annotated[str, StringConstraints(max_length=2000)]
Short = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Count = Annotated[int, Field(ge=0)]
Sentence = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
StampedAt = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$")]    # J2's strftime


def _raise(title: str, problems: Sequence[Problem]) -> NoReturn:
    """Fail validation with one error for every problem, each at its own place."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)})
        for loc, text in problems])


def _row_problems(verdict: str, note: str, passed: bool | None) -> list[Problem]:
    """The two rules a finding and a rubric row share: a pass needs evidence, and the stored flag may not lie."""
    found: list[Problem] = []
    if verdict in _NEEDS_EVIDENCE and not note:
        found.append((("note",), f"a {verdict} verdict needs evidence in its note"))
    if passed is not None and passed != (verdict in PASSING_VERDICTS):
        found.append((("pass",), f"pass is {str(passed).lower()}, but the verdict {verdict} means pass is {str(verdict in PASSING_VERDICTS).lower()}"))
    return found


class Evaluation(Record):
    """The base of the family: it holds the family name and registers nothing itself."""

    FAMILY = "evaluation"
    ABSTRACT = True


# ---- the parts of a result ----------------------------------------------------------------------------------------

class Finding(Value):
    """One row of Audit's result: a done-when item (`item` set, `pass` set) or an extra issue (no `pass`: J2 treats an
    extra issue as failing whatever its verdict says). Ids are F-<item number>, F-missing-<n> for an item Audit skipped,
    and `audit_id` keeps Audit's own id when code renamed it (J2:8908)."""

    id: FindingId
    item: Count | None = None
    criterion: Criterion
    verdict: Verdict
    severity: Severity | None = None
    confidence: Confidence | None = None
    note: Evidence
    needs_requester_fact: Annotated[str, StringConstraints(max_length=600)] | None = None
    passed: bool | None = Field(default=None, alias="pass")
    audit_id: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    forced_test: bool | None = None                                          # J2_FORCE_AUDIT_FAIL: humans only (J2:9222)
    real_verdict: Annotated[str, StringConstraints(max_length=2100)] | None = None

    @model_validator(mode="after")
    def _finding_rules(self) -> Self:
        problems = _row_problems(self.verdict, self.note, self.passed)
        if problems:
            _raise("Finding", problems)
        return self


class RubricResult(Value):
    """One row of the design rubric (R-1 to R-7, a website) or the document rubric (D-1 to D-5), as code stores it
    (J2:9186). `item` repeats the id, `criterion` is the rubric text, `rubric` is true, `severity` is "medium"."""

    id: Annotated[str, StringConstraints(pattern=r"^[RD]-[0-9]+$", max_length=12)]
    verdict: RubricVerdict
    note: Evidence
    passed: bool = Field(alias="pass")
    item: Annotated[str, StringConstraints(min_length=1, max_length=12)] | None = None
    criterion: Criterion | None = None
    rubric: bool | None = None
    severity: Severity | None = None

    @model_validator(mode="after")
    def _rubric_rules(self) -> Self:
        problems = _row_problems(self.verdict, self.note, self.passed)
        if problems:
            _raise("RubricResult", problems)
        return self


class ConditionResult(Value):
    """A necessary condition checked by code (conditions/*.json, J2:1296 `check_conditions`). A "warn" condition is shown
    and never blocks. `check` names the code check, or several of them."""

    id: Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]+$", max_length=8)]
    text: Criterion = ""
    check: Annotated[str, StringConstraints(min_length=1, max_length=80)] | Annotated[
        list[Annotated[str, StringConstraints(min_length=1, max_length=80)]], Field(max_length=8)] | None = None
    met: bool
    evidence: Evidence
    severity: Literal["warn"] | None = None
    assumptions: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=600)]], Field(max_length=100)] | None = None


class LldMismatch(Value):
    """An LLD section that the page does not match, or that no workflow built (J2:8992 `_lld_compare`)."""

    section: Short
    evidence: Evidence


class LldComparison(Value):
    """The finished page against the whole LLD, by code: section ids that match, and those that do not."""

    matches: Annotated[list[Short], Field(max_length=100)] = []
    mismatches: Annotated[list[LldMismatch], Field(max_length=100)] = []
    dropped: Annotated[list[LldMismatch], Field(max_length=100)] = []


# ---- the four kinds -----------------------------------------------------------------------------------------------

@record
class ResultEvaluation(Evaluation):
    """Audit's check of one build: the entry J2 appends to audits.json (J2:8966). `all_pass` may not lie."""

    kind: Literal["result"] = "result"
    cycle: Annotated[int, Field(ge=1)]
    version: Annotated[int, Field(ge=1)]
    results: Annotated[list[Finding], Field(max_length=200)]
    extra_issues: Annotated[list[Finding], Field(max_length=100)] = []
    rubric: Annotated[list[RubricResult], Field(max_length=20)] = []
    conditions: Annotated[list[ConditionResult], Field(max_length=40)] = []
    mechanical: JsonObject = Field(default_factory=dict)                       # j2_check's render check: its own shape
    screenshot: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None
    all_pass: bool
    accepted: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=600)]], Field(max_length=200)] = []
    output: Literal["website", "prd", "hld", "lld"] | None = None              # set for a document's audit
    read: Evidence | None = None                                               # what Audit says it read (a document)
    lld: LldComparison | None = None

    @model_validator(mode="after")
    def _audit_rules(self) -> Self:
        problems: list[Problem] = []
        where_seen: dict[str, str] = {}
        for group, rows in (("results", self.results), ("extra_issues", self.extra_issues)):
            for index, row in enumerate(rows):
                if row.id in where_seen:
                    problems.append(((group, index, "id"), f"finding id {row.id} is used twice (also at {where_seen[row.id]})"))
                else:
                    where_seen[row.id] = f"{group}.{index}"
        # J2 sets all_pass when it builds the entry: a result, every rubric row and every blocking condition decide, and
        # an empty result never passes (J2:8968). A settled dispute that withdraws a finding recomputes it from the rows
        # alone (J2:5080), so with a WITHDRAWN row the conditions and the empty case no longer count.
        scored = [*self.results, *self.rubric]
        failing = [row.id for row in scored if not row.passed]
        blocking = [c.id for c in self.conditions if not c.met and c.severity != "warn"]
        withdrawn = any(row.verdict == "WITHDRAWN" for row in [*scored, *self.extra_issues])
        expected = not failing and (withdrawn or (bool(self.results) and not blocking))
        if self.all_pass != expected:
            if self.all_pass:
                why = (f"these rows do not pass: {', '.join(failing[:5])}" if failing else
                       f"these conditions are not met: {', '.join(blocking[:5])}" if blocking and not withdrawn else
                       "there is no result at all")
                problems.append((("all_pass",), f"all_pass is true, but {why}"))
            else:
                problems.append((("all_pass",), "all_pass is false, but every result and rubric row passes and no condition blocks"))
        if problems:
            _raise("ResultEvaluation", problems)
        return self


class RecheckResult(Value):
    """One check of an atom, run again (a receipt, J2:8712). `pass` is None when the check could not run."""

    atom: AtomId
    check: Criterion | None = None
    passed: bool | None = Field(default=None, alias="pass")
    evidence: Evidence


@record
class RecheckEvaluation(Evaluation):
    """The entry J2 adds to audits.json when a board answer changed a document and the atoms built from it were checked
    again (J2:7928). `trigger` is the board question, `doc` the document kind, `t` J2's local time stamp."""

    kind: Literal["recheck"] = "recheck"
    trigger: Short
    doc: Short
    version: Count
    t: StampedAt
    results: Annotated[list[RecheckResult], Field(max_length=500)]


class JudgeAnswer(Value):
    """The judge's answer to one yes/no question, with its note (required by the judge's prompt for a "no")."""

    answer: Literal["yes", "no", "n/a"]
    note: Annotated[str, StringConstraints(max_length=600)] = ""


@record
class PlanEvaluation(Evaluation):
    """The confidence judge's result for one planned workflow: code turned the answers into `score` (settle(), 0.95 less
    the weight of each "no"), and the gate is PLAN_GATE. `weakest` is the check that lost most; None when nothing was lost.
    `round` counts the revision rounds after the first judgement (0 to 3)."""

    kind: Literal["plan"] = "plan"
    workflow: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    round: Annotated[int, Field(ge=0, le=3)]
    score: Annotated[float, Field(ge=0, le=1)]
    passed: bool
    answers: Annotated[dict[Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{1,3}$")], JudgeAnswer], Field(max_length=200)]
    weakest: Literal["inputs", "method", "done_test", "factors", "zone_fit", "size", "fits"] | None = None

    @model_validator(mode="after")
    def _gate_decides(self) -> Self:
        if self.passed != (self.score >= PLAN_GATE):
            _raise("PlanEvaluation", [(("passed",), f"passed is {str(self.passed).lower()}, but a score of {self.score} "
                                                    f"{'reaches' if self.score >= PLAN_GATE else 'is below'} the gate of {PLAN_GATE}")])
        return self


class AgentReview(Value):
    """The reviewer's score (1 to 5) for one agent, with its note."""

    score: Annotated[int, Field(ge=1, le=5)]
    note: Annotated[str, StringConstraints(max_length=2000)] = ""


@record
class RunReview(Evaluation):
    """The reviewer's verdict on a finished run (REVIEW_FMT). A review written while the run is paused holds the verdict
    alone; a reply that was not JSON holds the verdict and the start of the reply in `raw` (J2:9534)."""

    kind: Literal["run"] = "run"
    verdict: Sentence
    agents: Annotated[dict[Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,40}$")], AgentReview], Field(max_length=40)] = {}
    went_well: Annotated[list[Sentence], Field(max_length=30)] = []
    problems: Annotated[list[Sentence], Field(max_length=30)] = []
    learnings: Annotated[list[Sentence], Field(max_length=30)] = []
    raw: Annotated[str, StringConstraints(max_length=2000)] | None = None
