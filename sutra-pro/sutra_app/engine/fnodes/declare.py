"""Declare: a function turn becomes an `AtomDraft` BEFORE the work (function-nodes.md sections 2.3 and 3, library 6).

    declare(turn, spec, workflows=None, work=None)      the draft of a turn: template by (function, kind), else `generic`
    declare_question(turn, spec, question_id, ...)       the draft of the manual atom that follows a turn that ends paused
    pick_template(spec, kind), spec_kind(function, kind), predicted_work(...)   the pieces, exposed for tests and the layer

What the draft holds (function-nodes.md 2.3):

    goal         the template sentence with {function} {kind} {step_label} {task} filled in; never empty and never one of the
                 plugin's banal words (a goal that would be falls back to a sentence of our own)
    constraints  the first 20 `FunctionSpec.may_not`, `check` null
    context      the `TurnInfo.context` pairs as `<kind>: <summary>`, each cut to 200 characters, at most 40
    work         dispatch_kind llm, bash or manual; agent = the function (the owner for a manual atom); steps = the step
                 label; how_kind AI for llm else code
    outputs      [FunctionSpec.yields]       touches  the template's paths (none in the seeds)       model, effort  null
    verify       FLOOR checks first (`reply-valid` when the TaskKind names a reply family and kind and the work is llm,
                 `turn-posted` for llm and bash, none for manual), then the template's named checks; each with the check's own
                 sentence as `text` and `relevance`

The work kind is PREDICTED from the file or the template, never from a reply: the template's `work_hint`, except that a
Coordination `schedule` turn is bash exactly when `workflows.json` at turn start holds no registered or held workflow. The
layer corrects a wrong guess afterwards with `Seen.work`. J2's handoff kind for the price turn is `proposal`: it picks the
`price` template (`KIND_ALIASES`).
"""
from collections.abc import Mapping, Sequence
from typing import Final, Literal, Optional

from sutra_app.engine.events import CONTEXT_ITEMS_MAX, context_strings
from sutra_app.engine.hooks import TurnInfo
from sutra_app.library.atom import BANAL_GOAL_RE, AtomDraft, Check, Constraint, Verify, Work
from sutra_app.library.node import AtomTemplate, FunctionSpec, TaskKind
from sutra_app.library.types import clip

from .registry import REGISTRY

__all__ = [
    "DeclareError", "KIND_ALIASES", "QUESTION_PLACEHOLDER", "MAX_CONSTRAINTS", "spec_kind", "task_kind_of", "pick_template",
    "has_work_to_schedule", "predicted_work", "build_goal", "declare", "declare_question",
]

WorkKind = Literal["llm", "bash", "manual"]
KIND_ALIASES: Final = {("priority", "proposal"): "price"}      # J2 hands the price turn over as kind "proposal" (j2.py:5725)
QUESTION_PLACEHOLDER: Final = "{question_message_id}"            # the argument of `answer-recorded` in the seed template
MAX_CONSTRAINTS: Final = 20
GOAL_MAX: Final = 600
CHECK_TEXT_MAX: Final = 300
UNKNOWN_KIND: Final = "turn"                                      # the word used for a turn whose handoff has no kind


class DeclareError(ValueError):
    """A turn cannot be declared (a placeholder with nothing to fill it). A programming or spec error, never J2's."""


def spec_kind(function: str, kind: Optional[str]) -> Optional[str]:
    """The task kind a J2 handoff kind stands for in the spec (None when the handoff has none)."""
    if kind is None:
        return None
    return KIND_ALIASES.get((function, kind), kind)


def task_kind_of(spec: FunctionSpec, kind: Optional[str]) -> Optional[TaskKind]:
    """The spec's `TaskKind` of this handoff kind, or None."""
    wanted = spec_kind(spec.function, kind)
    return next((task_kind for task_kind in spec.task_kinds if task_kind.kind == wanted), None)


def pick_template(spec: FunctionSpec, kind: Optional[str]) -> AtomTemplate:
    """The atom template named like the kind, else the one named `generic` (every spec has it)."""
    wanted = spec_kind(spec.function, kind)
    by_name = {template.name: template for template in spec.atom_templates}
    return by_name.get(wanted) or by_name["generic"]


def has_work_to_schedule(workflows: Optional[Sequence]) -> bool:
    """Does `workflows.json` (as read at turn start) hold a registered or held workflow? None (no file) holds none."""
    return any(isinstance(w, Mapping) and w.get("status") in ("registered", "held") for w in workflows or [])


def predicted_work(spec: FunctionSpec, template: AtomTemplate, kind: Optional[str], workflows: Optional[Sequence] = None,
                   asked: Optional[WorkKind] = None) -> WorkKind:
    """The work kind a turn is expected to be. `asked` (a caller that wants the other kind, such as an envelope check done
    by a model) wins; then the schedule rule; then the template's `work_hint`."""
    if asked is not None:
        return asked
    if spec.function == "coordination" and spec_kind(spec.function, kind) == "schedule":
        return "llm" if has_work_to_schedule(workflows) else "bash"
    return template.work_hint


def build_goal(template: AtomTemplate, turn: TurnInfo) -> str:
    """The template goal with the turn's words in it, never empty and never banal."""
    word = turn.kind or UNKNOWN_KIND
    goal = template.goal.format(function=turn.function, kind=word, step_label=turn.step_label, task=turn.task).strip()
    goal = clip(goal, GOAL_MAX)
    if not goal or BANAL_GOAL_RE.fullmatch(goal):
        goal = clip(f"The {turn.function} completes the {word} turn ({turn.step_label or 'no step'}): {goal or turn.task or word}", GOAL_MAX)
    return goal


def _sentence(name: str) -> Optional[str]:
    return clip(REGISTRY[name].text, CHECK_TEXT_MAX) if name in REGISTRY else None


def _check(name: str, args: Sequence[str]) -> Check:
    sentence = _sentence(name)
    return Check(template=name, args=list(args), text=sentence or "", relevance=sentence)


def _checks(floors: Sequence[tuple[str, Sequence[str]]], template: AtomTemplate, question_id: Optional[int]) -> list[Check]:
    out = [_check(name, args) for name, args in floors]
    for ref in template.checks:
        args = []
        for arg in ref.args:
            if QUESTION_PLACEHOLDER in arg:
                if question_id is None:
                    raise DeclareError(f"the check {ref.name} of template {template.name!r} needs a question message id")
                arg = arg.replace(QUESTION_PLACEHOLDER, str(question_id))
            args.append(arg)
        if not any(c.template == ref.name and c.args == args for c in out):
            out.append(_check(ref.name, args))
    return out


def _constraints(spec: FunctionSpec) -> list[Constraint]:
    return [Constraint(text=text, check=None) for text in spec.may_not[:MAX_CONSTRAINTS]]


def _work(template: AtomTemplate, kind: WorkKind, agent: str, steps: str) -> Work:
    return Work(dispatch_kind=kind, ref=template.work.ref, agent=agent, steps=steps, how_kind="AI" if kind == "llm" else "code")


def declare(turn: TurnInfo, spec: FunctionSpec, *, workflows: Optional[Sequence] = None, work: Optional[WorkKind] = None,
            question_id: Optional[int] = None) -> AtomDraft:
    """The draft of one function turn. `workflows` is `workflows.json` as read at turn start (None: no such file), `work`
    overrides the predicted kind, `question_id` fills the placeholder of a template that names one."""
    if turn.function != spec.function:
        raise DeclareError(f"the turn is {turn.function}'s, the spec is {spec.function}'s")
    template = pick_template(spec, turn.kind)
    kind = predicted_work(spec, template, turn.kind, workflows, work)
    floors: list[tuple[str, list[str]]] = []
    task_kind = task_kind_of(spec, turn.kind)
    if kind == "llm" and task_kind is not None and task_kind.reply_family and task_kind.reply_kind:
        floors.append(("reply-valid", [task_kind.reply_family, task_kind.reply_kind]))
    if kind in ("llm", "bash"):
        floors.append(("turn-posted", []))
    return AtomDraft(
        goal=build_goal(template, turn), constraints=_constraints(spec), context=context_strings(turn.context[:CONTEXT_ITEMS_MAX]),
        work=_work(template, kind, "owner" if kind == "manual" else turn.function, turn.step_label), touches=list(template.touches),
        outputs=[spec.yields], verify=Verify(checks=_checks(floors, template, question_id)))


def declare_question(turn: TurnInfo, spec: FunctionSpec, question_id: int, *, question: str = "",
                     pause: Optional[str] = None) -> AtomDraft:
    """The manual atom of a turn that ended paused: the owner's answer to the question `question_id` is recorded. The template
    is the spec's `answer` one (else its first manual one, else a built-in goal); the only check is `answer-recorded`."""
    templates = {template.name: template for template in spec.atom_templates}
    template = templates.get("answer") or next((t for t in spec.atom_templates if t.work_hint == "manual"), None)
    if template is None:
        template = pick_template(spec, None).evolve(
            goal="The owner's answer to the question is recorded", work_hint="manual", checks=[{"name": "answer-recorded", "args": [QUESTION_PLACEHOLDER]}])
    context = [f"question: {question.strip() or 'message ' + str(question_id)}"] + ([f"pause: {pause}"] if pause else [])
    return AtomDraft(
        goal=build_goal(template, turn), constraints=_constraints(spec), context=context_strings(context),
        work=_work(template, "manual", "owner", turn.step_label), touches=list(template.touches), outputs=[spec.yields],
        verify=Verify(checks=_checks([], template, question_id)))
