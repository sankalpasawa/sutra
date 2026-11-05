"""The chat agent's reply classes (orchestrator 3.2, S2-models-13, S4-fnodes-12).

    AssignmentDraft   one task for one department (the top-level Step); refs a1 to a5
    ChatDecision      family `chat_turn`, kind `decide` (stage A): what the request is and whether the chart changes
    AssignmentPlan    family `chat_turn`, kind `assignments` (stage C): 1 to 5 drafts; `to_task_workflow(request_id)`

All three are flat and transport-safe (no union, no recursion). There is NO prose field anywhere: the model's output is structure
only and none of its sentences is shown to the owner. The model never writes an id of a new node (stage B's `$ref` does that).
Importing this module registers the family `chat_turn` in the library `REGISTRY`; import it before the registry is frozen.
"""
from collections.abc import Sequence
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator
from pydantic import ValidationError
from pydantic_core import InitErrorDetails

from sutra_app.library.base import Record, Value
from sutra_app.library.registry import record
from sutra_app.library.types import NodeId
from sutra_app.library.workflow import AssignmentStep, TaskWorkflow

__all__ = ["AssignmentRef", "AssignmentDraft", "ChatDecision", "AssignmentPlan", "plan_of", "dependency_order", "REF_ORDER"]

AssignmentRef = Annotated[str, StringConstraints(pattern=r"^a[1-5]$")]
REF_ORDER = ("a1", "a2", "a3", "a4", "a5")
Problem = tuple[tuple[str | int, ...], str]


def _raise(title: str, problems: Sequence[Problem]) -> None:
    """One validation error per problem, each at its own place."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)})
        for loc, text in problems])


def _draft_problems(drafts: Sequence["AssignmentDraft"]) -> list[Problem]:
    """Refs unique, `depends_on` names known refs, no cycle (a depth-first walk)."""
    problems: list[Problem] = []
    first: dict[str, int] = {}
    for index, draft in enumerate(drafts):
        if draft.ref in first:
            problems.append((("assignments", index, "ref"), f"ref {draft.ref} is used twice (first at assignments.{first[draft.ref]})"))
        first.setdefault(draft.ref, index)
    for index, draft in enumerate(drafts):
        for pos, dep in enumerate(draft.depends_on):
            if dep not in first:
                problems.append((("assignments", index, "depends_on", pos), f"{draft.ref} depends on {dep}, which is not one of the assignments"))
            elif dep == draft.ref:
                problems.append((("assignments", index, "depends_on", pos), f"{draft.ref} cannot depend on itself"))
        if len(set(draft.depends_on)) != len(draft.depends_on):
            problems.append((("assignments", index, "depends_on"), f"{draft.ref} lists the same dependency twice"))
    if not problems:
        graph = {d.ref: list(d.depends_on) for d in drafts}
        state: dict[str, int] = {}           # 1 = on the walk, 2 = done

        def visit(ref: str, trail: list[str]) -> list[str] | None:
            if state.get(ref) == 2:
                return None
            if state.get(ref) == 1:
                return trail[trail.index(ref):] + [ref]
            state[ref] = 1
            for dep in graph[ref]:
                found = visit(dep, trail + [ref])
                if found:
                    return found
            state[ref] = 2
            return None

        for ref in graph:
            cycle = visit(ref, [])
            if cycle:
                problems.append((("assignments",), "the assignments depend on each other in a circle: " + " -> ".join(cycle)))
                break
    return problems


def dependency_order(drafts: Sequence["AssignmentDraft"]) -> list["AssignmentDraft"]:
    """The drafts with every dependency before the draft that needs it; the given order is kept where the dependencies allow."""
    by_ref = {d.ref: d for d in drafts}
    done: list[AssignmentDraft] = []
    seen: set[str] = set()

    def place(draft: AssignmentDraft) -> None:
        if draft.ref in seen:
            return
        seen.add(draft.ref)
        for dep in draft.depends_on:
            if dep in by_ref:
                place(by_ref[dep])
        done.append(draft)

    for draft in drafts:
        place(draft)
    return done


class AssignmentDraft(Value):
    """One task for one department: `brief` states the need in one paragraph (the team also reads the owner's own words); `scope`
    is a division under that department; `follows` is a task id listed for that team in the chart digest."""

    ref: AssignmentRef
    dept: NodeId
    scope: NodeId | None = None
    title: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    brief: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    depends_on: Annotated[list[AssignmentRef], Field(max_length=4)] = []
    follows: Annotated[str, StringConstraints(pattern=r"^tsk_[0-9a-f]{12}$")] | None = None


Intent = Literal["new_task", "chart_request", "status", "smalltalk", "clarify"]
Change = Literal["none", "reuse", "add", "rearrange"]


@record
class ChatDecision(Record):
    """Stage A. What the request is (`intent`) and how the chart must change (`change`). `assignments` are filled only when the
    change is none or reuse; when the chart changes, stage C writes them after stage B. `why` is for the change log, never shown.

    Rules: new_task with change none or reuse needs assignments; reuse needs reuse_nodes; chart_request means add or rearrange;
    status and smalltalk change nothing and carry no assignments; clarify changes nothing, carries no assignments and may name up
    to 3 candidate teams in reuse_nodes; assignments only when the change is none or reuse."""

    FAMILY = "chat_turn"
    TRANSPORT_OPTIONAL = frozenset({"schema_version"})
    kind: Literal["decide"] = "decide"
    intent: Intent
    change: Change
    reuse_nodes: Annotated[list[NodeId], Field(max_length=10)] = []
    why: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    assignments: Annotated[list[AssignmentDraft], Field(max_length=5)] = []

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        problems: list[Problem] = []
        if self.assignments and self.change in ("add", "rearrange"):
            problems.append((("assignments",), f"assignments are left empty when the change is {self.change}: they are asked after the chart change"))
        if self.intent == "new_task" and self.change in ("none", "reuse") and not self.assignments:
            problems.append((("assignments",), f"intent new_task with change {self.change} needs at least one assignment"))
        if self.change == "reuse" and not self.reuse_nodes:
            problems.append((("reuse_nodes",), "change reuse needs reuse_nodes: the ids of the teams to reuse"))
        if self.intent == "chart_request" and self.change not in ("add", "rearrange"):
            problems.append((("change",), "intent chart_request means the change is add or rearrange"))
        if self.intent in ("status", "smalltalk", "clarify") and self.change != "none":
            problems.append((("change",), f"intent {self.intent} changes nothing: change is none"))
        if self.intent in ("status", "smalltalk", "clarify") and self.assignments:
            problems.append((("assignments",), f"intent {self.intent} carries no assignments"))
        if self.intent == "clarify" and len(self.reuse_nodes) > 3:
            problems.append((("reuse_nodes",), "clarify names at most 3 candidate teams"))
        problems.extend(_draft_problems(self.assignments))
        if problems:
            _raise("ChatDecision", problems)
        return self


@record
class AssignmentPlan(Record):
    """Stage C: 1 to 5 assignments, given the chart as it will be after stage B."""

    FAMILY = "chat_turn"
    TRANSPORT_OPTIONAL = frozenset({"schema_version"})
    kind: Literal["assignments"] = "assignments"
    assignments: Annotated[list[AssignmentDraft], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def _plan(self) -> Self:
        problems = _draft_problems(self.assignments)
        if problems:
            _raise("AssignmentPlan", problems)
        return self

    def to_task_workflow(self, request_id: str) -> TaskWorkflow:
        """The library `TaskWorkflow` of this plan: id = the request id ('req-<message id>'), name = the first title, one
        `AssignmentStep` per draft with every dependency before its dependant. The caller gates it; it is not stored."""
        ordered = dependency_order(self.assignments)
        steps = [AssignmentStep(id=d.ref, name=d.title, dept=d.dept, scope=d.scope, brief=d.brief, depends_on=list(d.depends_on),
                                follows=d.follows) for d in ordered]
        return TaskWorkflow(id=request_id, name=self.assignments[0].title, steps=steps)


def plan_of(assignments: Sequence[AssignmentDraft]) -> AssignmentPlan:
    """An `AssignmentPlan` over drafts a decision already carries."""
    return AssignmentPlan(assignments=list(assignments))
