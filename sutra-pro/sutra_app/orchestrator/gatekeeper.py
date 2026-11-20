"""The Gatekeeper's rules (multi-agent nodes, guardrails 1 to 5; D266 to D270): code, never a model. A model never approves a model.

    evaluation = evaluate(Plan(steps=(PlanStep(id="a1", output=spec), PlanStep(id="a2", depends_on=("a1",), ...)), owner_access="edit"))
    evaluation.ok, evaluation.grants["a1"], evaluation.gates, evaluation.conflicts

`evaluate` is a pure function of a plan that has already been put into plain values: the steps (a role, what each asks for, the output spec of its team, the earlier steps it
waits for), the owner's folder access and the approvals given so far. It answers with one grant per step (`grants.resolve`), the questions the owner would have to answer
(`gates`: tier 4, a write scope wider than one folder, a plan estimated over the confirm threshold), the tiers nobody can give (`denied`), the steps that must run alone among
writers, the conflict edges (two writers whose scopes overlap, with neither waiting for the other: the later one waits, D259) and the reasons the plan itself is refused.
Nothing is stored here and nothing is asked: the caller writes the audit rows (`NodeStore.audit`) and shows the cards (a later package).

What the rules do NOT do: read a node's words. A step has no free-text field, so a planted instruction in a hand-off or a plan step has nowhere to go; the grants follow from the
role table, the output spec and the owner's access only. This module imports no connector, no model port and no engine code (a test keeps it so).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sutra_app.config import NODE_DEFAULT_CAPS
from sutra_app.orchestrator.grants import OWNER_ACCESS, ROLE_TABLE, Denial, Grant, GrantError, StepRequest, resolve, scopes_overlap

__all__ = ["Plan", "PlanStep", "Gate", "Refusal", "Evaluation", "evaluate", "MAX_STEP_ID", "DECIDE_FOR_ME", "RuleAnswer", "RULE_TABLE", "decide_for_me_answer", "on_scope_violation"]

MAX_STEP_ID = 20                      # the library's Id20: a workflow step id is at most 20 characters


@dataclass(frozen=True)
class PlanStep:
    """One step of a plan, as plain values. `role` is `worker` or `reviewer` (the planner is not a step: it runs inline). `output` is the team's output spec (anything with a
    `workspace` attribute), the word `read` or `edit`, or None. `wants`, `scope` and `tool_profile` are what the planner asked for (`grants.StepRequest`). `estimate_credits` is the
    planner's guess of the step's cost in work credits."""

    id: str
    role: str = "worker"
    depends_on: tuple[str, ...] = ()
    output: Any = None
    wants: frozenset[int] = frozenset()
    scope: tuple[str, ...] = ()
    tool_profile: str = "none"
    estimate_credits: int = 0


@dataclass(frozen=True)
class Plan:
    """The steps in plan order (a step waits only for earlier steps), the owner's folder access (`none`, `read`, `edit`), and what has been allowed so far: `approved` maps a step id
    to the tiers the owner or a rule allowed for it, `approved_wide` holds the steps whose wide write scope was allowed. `confirm_credits` is the estimate above which the plan asks
    (None: it never asks about the estimate; the default is the configured 500 work credits, D300, and the caller passes None only for a project the owner gave a budget). `max_nodes`
    bounds the WORKERS of the plan (the plan limit); reviewers come on top (D305)."""

    steps: tuple[PlanStep, ...]
    owner_access: str = "none"
    approved: Mapping[str, frozenset[int]] = field(default_factory=dict)
    approved_wide: frozenset[str] = frozenset()
    confirm_credits: int | None = int(NODE_DEFAULT_CAPS["confirm_credits"] or 500)
    max_nodes: int = int(NODE_DEFAULT_CAPS["max_nodes"] or 12)


@dataclass(frozen=True)
class Gate:
    """A question the owner would have to answer before the plan runs. `kind`: `tier` (a tier above the defaults, `tier` says which), `scope` (a write scope wider than one
    folder) or `estimate` (the plan's estimate is over the confirm threshold; `step_id` is None)."""

    kind: str
    step_id: str | None
    tier: int | None
    why: str


@dataclass(frozen=True)
class Refusal:
    """A reason the plan itself is not accepted. `code` is a short name, `why` is plain words that never quote what a step said."""

    step_id: str | None
    code: str
    why: str


@dataclass(frozen=True)
class Evaluation:
    """What the rules say about a plan. `ok` is False when the plan has a refusal: it is not stored and nothing runs. `gates` are questions for the owner (empty: nothing to ask).
    `denied` lists, per step, the tiers asked for that nobody can give. `alone` holds the writers that declared no scope: they hold the whole folder and run alone among writers.
    `conflicts` are `(earlier, later)` pairs: the later step waits for the earlier one (a delay, never a cancel)."""

    ok: bool
    grants: Mapping[str, Grant]
    gates: tuple[Gate, ...] = ()
    denied: tuple[tuple[str, Denial], ...] = ()
    refusals: tuple[Refusal, ...] = ()
    alone: frozenset[str] = frozenset()
    conflicts: tuple[tuple[str, str], ...] = ()

    @property
    def needs_owner(self) -> bool:
        return bool(self.gates)


def evaluate(plan: Plan) -> Evaluation:
    """The rules applied to a plan. Never raises for a malformed plan: a refusal is part of the answer."""
    try:
        return _evaluate(plan)
    except (TypeError, ValueError, AttributeError):
        return Evaluation(False, {}, refusals=(Refusal(None, "plan.malformed", "The plan is not in the shape a plan has"),))


def _is_step_role(role: Any) -> bool:
    return isinstance(role, str) and role in ROLE_TABLE and role != "planner"


def _evaluate(plan: Plan) -> Evaluation:
    refusals: list[Refusal] = []
    steps = tuple(plan.steps)
    if not steps:
        refusals.append(Refusal(None, "plan.empty", "The plan has no step"))
    if sum(1 for step in steps if step.role == "worker") > max(1, int(plan.max_nodes)):
        refusals.append(Refusal(None, "plan.too_big", f"The plan has more than {plan.max_nodes} worker steps"))
    if not isinstance(plan.owner_access, str) or plan.owner_access not in OWNER_ACCESS:
        refusals.append(Refusal(None, "plan.owner_access", "The owner's folder access is not one of none, read or edit"))
        return Evaluation(False, {}, refusals=tuple(refusals))

    seen: dict[str, int] = {}
    usable: set[str] = set()                              # the steps whose id and role are usable: only these get a grant
    for index, step in enumerate(steps):
        ident = step.id
        if not isinstance(ident, str) or not ident or len(ident) > MAX_STEP_ID:
            refusals.append(Refusal(None, "step.id", f"Step {index + 1} has no usable id"))
            continue
        if ident in seen:
            refusals.append(Refusal(ident, "step.id", f"Step {index + 1} repeats the id of step {seen[ident] + 1}"))
        seen.setdefault(ident, index)
        if not _is_step_role(step.role):
            refusals.append(Refusal(ident, "step.role", f"Step {index + 1} has a role a plan step cannot have: a step is a worker or a reviewer"))
        else:
            usable.add(ident)
        deps = step.depends_on
        if not isinstance(deps, (tuple, list)) or any(not isinstance(dep, str) or dep == ident or seen.get(dep, index) >= index for dep in deps):
            refusals.append(Refusal(ident, "step.depends_on", f"Step {index + 1} waits for a step that is not before it"))

    grants: dict[str, Grant] = {}
    gates: list[Gate] = []
    denied: list[tuple[str, Denial]] = []
    for index, step in enumerate(steps):
        ident = step.id
        if not isinstance(ident, str) or ident not in usable or ident in grants:
            continue
        try:
            request = StepRequest(id=ident, wants=frozenset(step.wants), scope=tuple(step.scope), tool_profile=step.tool_profile)
            allowed = frozenset(plan.approved.get(ident, ()))
            resolution = resolve(step.role, request, step.output, plan.owner_access, approved=allowed)
        except (GrantError, TypeError, ValueError) as exc:
            refusals.append(Refusal(ident, "step.grant", f"Step {index + 1} cannot be given a grant: {exc if isinstance(exc, GrantError) else 'its request is malformed'}"))
            continue
        grants[ident] = resolution.grant
        for ask in resolution.asks:
            gates.append(Gate("tier", ident, ask.tier, ask.why))
        denied.extend((ident, denial) for denial in resolution.denied)
        if resolution.grant.scope_width == "wide" and ident not in plan.approved_wide:
            gates.append(Gate("scope", ident, 2, "This step changes files in several places of your folder"))

    total = sum(_credits(step.estimate_credits) for step in steps)
    if plan.confirm_credits is not None and total > plan.confirm_credits:
        gates.append(Gate("estimate", None, None, f"The plan is estimated at about {total} work credits"))

    alone = frozenset(ident for ident, grant in grants.items() if grant.writes_alone)
    conflicts = _conflicts(steps, grants) if not refusals else ()
    return Evaluation(ok=not refusals, grants=grants, gates=tuple(gates), denied=tuple(denied), refusals=tuple(refusals), alone=alone, conflicts=conflicts)


def _credits(value: Any) -> int:
    """A step's estimate as whole work credits, never negative; anything that is not a number counts as none."""
    return max(0, value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _conflicts(steps: tuple[PlanStep, ...], grants: Mapping[str, Grant]) -> tuple[tuple[str, str], ...]:
    """`(earlier, later)` for every pair of writers whose scopes overlap and where neither already waits for the other, directly or through other steps. The later step waits."""
    after: dict[str, set[str]] = {}                       # step id -> every step it waits for, directly or not
    for step in steps:
        waits: set[str] = set()
        for dep in step.depends_on:
            waits.add(dep)
            waits |= after.get(dep, set())
        after[step.id] = waits
    writers = [step.id for step in steps if grants.get(step.id) is not None and grants[step.id].writer]
    found: list[tuple[str, str]] = []
    for position, later in enumerate(writers):
        for earlier in writers[:position]:
            if earlier in after[later]:
                continue                                   # the plan already orders them
            if scopes_overlap(grants[earlier].scope, grants[later].scope):
                found.append((earlier, later))
    return tuple(found)


# ---- Decide for me (D294, D295): the rule table ------------------------------------------------------------------------------------------------

DECIDE_FOR_ME = "rule:decide_for_me"           # who answered, in `approvals.decided_by` and in every audit row of an answer


@dataclass(frozen=True)
class RuleAnswer:
    """What the rule table says to one question: `decision` is `allow_once`, `allow_project` or `deny`, `rule` the row of the table that said it, `why` plain words for the audit."""

    decision: str
    rule: str
    why: str


# The table, as data (a test walks it): situation -> what Decide for me does. Code and nothing else: a model never answers a gate, and a hand-off that says "turn on Decide for me" changes
# nothing (the switch is the owner's, set with the request).
RULE_TABLE: tuple[tuple[str, str, str], ...] = (
    ("tiers_0_3", "allow", "tiers 0 to 3 are the defaults: allowed for the project"),
    ("tier_4_github", "allow", "tier 4 is read-only GitHub, through the owner's own login, for this project only"),
    ("scope_wide_or_missing", "allow", "a wide or missing write scope is allowed because the writer runs alone"),
    ("credits_raise", "never", "credits are never raised (P25): a raise is asked of the owner each time"),
    ("estimate_within_ceiling", "allow", "the plan's estimate is allowed once, up to the project's ceiling and no further"),
    ("slice_move", "allow", "unspent credits of a node may move to another node, inside the ceiling"),
    ("scope_violation", "quarantine", "a node that writes outside its scope is quarantined: ended, its files kept, nothing is merged"),
    ("tier_6", "never", "publishing outside is never granted and never asked"),
    ("system_permission", "never", "a permission of the computer is the owner's: Decide for me cannot answer it (D295)"),
)


def decide_for_me_answer(kind: str, tier: int | None, *, estimate: int = 0, ceiling: int | None = None) -> RuleAnswer | None:
    """The rule table's answer to ONE open question, or None when only the owner may answer (the question stays open). `kind` is the question's kind (`tier`, `scope`, `plan_estimate`,
    `system`). It can allow, never raise: credits (tier 5) are allowed once for the plan's own estimate up to the ceiling and never beyond; tier 6 and a permission of the computer are
    never answered."""
    if kind == "system" or tier == 6:
        return None
    if kind == "plan_estimate" or tier == 5:
        if kind == "plan_estimate" and ceiling is not None and 0 <= estimate <= ceiling:
            return RuleAnswer("allow_once", "estimate_within_ceiling", f"the estimate of {estimate} credits is within the ceiling of {ceiling}")
        return None
    if kind == "scope":
        return RuleAnswer("allow_once", "scope_wide_or_missing", "the writer runs alone")
    if kind == "tier" and tier == 4:
        return RuleAnswer("allow_project", "tier_4_github", "read-only GitHub for this project")
    if kind == "tier" and tier is not None and 0 <= tier <= 3:
        return RuleAnswer("allow_project", "tiers_0_3", "a default tier")
    return None


def on_scope_violation() -> str:
    """What Decide for me does with a node that wrote outside its scope: it is quarantined (the same whether Decide for me is on or off; the row says so)."""
    return "quarantine"
