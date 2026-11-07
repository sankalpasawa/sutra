"""`ChatAgent`: the staged structured calls of one owner request (orchestrator 5.2 T2 to T5, 5.3, S2-models-01, S4-fnodes-07/12).

    plan(request, phase=...)       stages A (decide), B (change, only when the chart changes), C (assignments) -> a `Plan`
    resume(request, decision)      stage C only, for a request whose chart change the owner approved
    choice_plan(request, node_id)  the plan for a team the owner picked on a `choice` card (no model call)

Every stage is one `call_json(prompt, schema=transport_schema(...), function="chat_agent", step=<stage>, context=...)`; the reply goes
through `ReplyParser` (tolerant in, closed out), then `GATE.check`, then our checks. A rejected reply is asked again with the reasons
(`retry.md`), up to `ATTEMPTS` per stage and `MAX_CALLS` for the request; `timeout` and `bad_output` count as an attempt, `unavailable`,
`auth` and `quota` do not retry (they raise `ConnectorFailure`, failure F1). A stage that runs out of attempts, or the call cap, gives
the keyword fallback of `planner.fallback_plan` (T5); the change row's reason then ends "(planned by keywords)".

Every call of a request carries the same accounting key, `context.atom_id = overhead_atom_id("req-<message id>")`, with `node_id` root.
The model writes structure only: no sentence of it is shown. Code sets a change's `kind`, `id`, `task_id`, `base_revision` and `ts`,
builds a reuse change itself, and the chart store gives new nodes their ids.
"""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from sutra_app.library.gate import GATE, Checked, GateError
from sutra_app.library.org_chart import (
    AddOp, ChartChange, ChartChangeRequest, ChildMove, MergeOp, MoveOp, NewNode, OrgChart, RenameOp, SplitOp, apply_change, slug_id,
)
from sutra_app.library.registry import REGISTRY
from sutra_app.library.replies import ReplyInvalid, ReplyParser
from sutra_app.library.types import Violation, clip, overhead_atom_id, violation, violations_from_validation_error
from sutra_app.orchestrator.agent import prompts
from sutra_app.orchestrator.agent.planner import Candidate, candidates, fallback_plan
from sutra_app.orchestrator.agent.ports import (
    ATTEMPTS, CALL_TIMEOUT, DIGEST_CHARS, HISTORY, MAX_CALLS, NO_RETRY_KINDS, ConnectorFailure, ConnectorPort, failure_kind,
)
from sutra_app.orchestrator.agent.replies import AssignmentDraft, AssignmentPlan, ChatDecision, plan_of
from sutra_app.orchestrator.chart import ChartStore
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.ids import ORG_SESSION_ID, ROOT_NODE_ID, IdFactory
from sutra_app.orchestrator.textutil import one_line_title

__all__ = [
    "ChatAgent", "PlanRequest", "Plan", "StageFailed", "ChartBusy", "StaleChart", "STAGES", "request_id_of", "call_context",
    "KEYWORDS_NOTE",
]

log = logging.getLogger(__name__)
STAGES = ("decide", "change", "assign")
KEYWORDS_NOTE = "(planned by keywords)"
_CALL_GRACE_S = 10.0              # the connector enforces `timeout`; this outer cut only guards a connector that does not
Phase = Callable[[str], None]


def request_id_of(message_id: int) -> str:
    return IdFactory.request_id(message_id)


def call_context(message_id: int) -> dict[str, str]:
    """The context of every model call of one request: its purpose, the org chat, the root node and the request's overhead key."""
    return {"purpose": "chat_plan", "session_id": ORG_SESSION_ID, "node_id": ROOT_NODE_ID,
            "atom_id": overhead_atom_id(request_id_of(message_id))}


class StageFailed(Exception):
    """A stage used its attempts (`reason` 'attempts') or the request used its call cap ('budget'). The agent answers with the
    keyword fallback; `violations` are the last reasons."""

    def __init__(self, stage: str, reason: str, violations: Sequence[Violation] = ()) -> None:
        super().__init__(f"stage {stage} failed ({reason})")
        self.stage, self.reason, self.violations = stage, reason, list(violations)


class ChartBusy(Exception):
    """The change would move a division that has unfinished work: not retried, the owner is told (`violations` hold the sentence)."""

    def __init__(self, violations: Sequence[Violation]) -> None:
        super().__init__("; ".join(v.message for v in violations))
        self.violations = list(violations)


class StaleChart(Exception):
    """The chart moved on while the request was planned (`stale_base`): the runner reads it again once, then gives up (F4)."""


@dataclass(frozen=True)
class PlanRequest:
    """One owner request as the agent reads it. `history` is (who, text) oldest first (who: user | sutra), `pending` one line per
    chart change waiting for the owner's yes or no."""

    text: str
    message_id: int
    history: Sequence[tuple[str, str]] = ()
    pending: Sequence[str] = ()

    @property
    def request_id(self) -> str:
        return request_id_of(self.message_id)


@dataclass
class Plan:
    """What the agent decided. `outcome`: work (a chart change and/or assignments), status, smalltalk, clarify or none (a `choice` card).
    `change` is the checked chart change to apply or None (a resumed plan, whose change was applied already). `drafts` are the
    assignments, `stage_c_pending` says stage C still has to run after the owner approves the change."""

    outcome: Literal["work", "status", "smalltalk", "clarify", "none"]
    decision: ChatDecision | None = None
    change: Checked | None = None
    drafts: list[AssignmentDraft] = field(default_factory=list)
    stage_c_pending: bool = False
    candidates: list[Candidate] = field(default_factory=list)
    keywords: bool = False
    calls: int = 0
    revision: int = 0
    added: list[str] = field(default_factory=list)       # ids the change will give new nodes (from the dry run)


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit, self.used = limit, 0

    def take(self, stage: str, violations: Sequence[Violation]) -> None:
        if self.used >= self.limit:
            raise StageFailed(stage, "budget", violations)
        self.used += 1


Build = Callable[[Any], Awaitable[tuple[Any, list[Violation]]]]


class ChatAgent:
    def __init__(self, connector: ConnectorPort, chart: ChartStore, *, redact: Callable[[str], str] | None = None, clock: Any = None,
                 attempts: int = ATTEMPTS, max_calls: int = MAX_CALLS, timeout: float = CALL_TIMEOUT, history: int = HISTORY,
                 parser: ReplyParser | None = None, notes: Callable[[], str] | None = None) -> None:
        self.connector = connector
        self.chart = chart
        self._redact = redact or (lambda text: text)
        self._clock = clock
        self.attempts, self.max_calls, self.timeout, self.history = attempts, max_calls, timeout, history
        self._parser = parser or ReplyParser()
        self._notes = notes or (lambda: "")             # the owner's notes block of the decide and assign prompts ("" when there are none)

    # ---- public ------------------------------------------------------------------------------------------------------------

    async def plan(self, request: PlanRequest, *, phase: Phase | None = None) -> Plan:
        """T2 to T5 for one request. Raises `ConnectorFailure` (F1), `ChartBusy`, `StaleChart`; any other trouble with the model
        gives the keyword fallback (a `ConnectorFailure` too when the chart has no department to fall back on)."""
        notify = phase or (lambda _name: None)
        budget = _Budget(self.max_calls)
        notify("reading_chart")
        head = await run_blocking(self.chart.head)
        chart: OrgChart = head.model
        digest = await run_blocking(lambda: self.chart.digest(request.text, max_chars=DIGEST_CHARS))
        notify("consulting_library")
        notify("planning")
        try:
            decision = await self._decide(request, chart, digest, budget)
            return await self._after_decision(request, chart, decision, budget)
        except StageFailed as failed:
            log.info("request %s: stage %s failed (%s): keyword fallback", request.request_id, failed.stage, failed.reason)
            return await self._fallback(request, chart, budget)

    async def resume(self, request: PlanRequest, decision: ChatDecision | None) -> Plan:
        """The assignments for a request whose chart change the owner approved. The change is applied already, so the plan holds no
        change. Only an `intent` new_task has work; a decision that carries its own assignments (never with a rearrange) keeps them."""
        budget = _Budget(self.max_calls)
        head = await run_blocking(self.chart.head)
        chart: OrgChart = head.model
        if decision is None or decision.intent != "new_task":
            return Plan("work", decision=decision, revision=chart.revision)
        if decision.assignments:
            return Plan("work", decision=decision, drafts=list(decision.assignments), revision=chart.revision)
        try:
            digest = await run_blocking(lambda: self.chart.digest(request.text, max_chars=DIGEST_CHARS))
            drafts = await self._assign(request, chart, digest, budget)
            return Plan("work", decision=decision, drafts=drafts, calls=budget.used, revision=chart.revision)
        except StageFailed:
            fallback = await self._fallback(request, chart, budget)
            fallback.change = None                     # the change row exists: only the assignment is new
            return fallback

    async def choice_plan(self, request: PlanRequest, node_id: str, *, reason: str | None = None) -> Plan:
        """The plan for the team the owner picked on a `choice` card: a reuse change and one assignment holding the request's words.
        No model call. A division is reused through its department with the division as the scope."""
        head = await run_blocking(self.chart.head)
        chart: OrgChart = head.model
        node = chart.node(node_id)
        if node is None or node.kind not in ("department", "division"):
            raise AppError("validation", f"{node_id!r} is not a team in the chart")
        candidate = Candidate(node.id, node.name, node.kind)
        change = await self._reuse_change(request, chart, [node.id], reason or f"You picked the {node.name} team.")
        return Plan("work", change=change, drafts=[self._draft_for(request.text, candidate, chart)], revision=chart.revision)

    # ---- after stage A -----------------------------------------------------------------------------------------------------

    async def _after_decision(self, request: PlanRequest, chart: OrgChart, decision: ChatDecision, budget: _Budget) -> Plan:
        base = Plan("work", decision=decision, revision=chart.revision)
        if decision.intent in ("status", "smalltalk"):
            base.outcome = decision.intent
            base.calls = budget.used
            return base
        if decision.intent == "clarify":
            base.outcome = "clarify"
            base.candidates = candidates(chart, request.text, ids=decision.reuse_nodes)
            base.calls = budget.used
            return base
        if decision.change in ("none", "reuse"):
            ids = list(decision.reuse_nodes) if decision.change == "reuse" else _teams_of(decision.assignments)
            base.change = await self._reuse_change(request, chart, ids, decision.why)
            base.drafts = list(decision.assignments)
            base.calls = budget.used
            return base
        change, added = await self._change(request, chart, decision, budget)
        base.change = change
        base.added = added
        if self.chart.classify(change) == "approve":
            base.stage_c_pending = decision.intent == "new_task"
        elif decision.intent == "new_task":
            after = await run_blocking(lambda: self._chart_after(change, chart, added))
            digest = await run_blocking(lambda: self._digest_of(after, request.text))
            base.drafts = await self._assign(request, after, digest, budget)
        base.calls = budget.used
        return base

    # ---- the stages --------------------------------------------------------------------------------------------------------

    async def _decide(self, request: PlanRequest, chart: OrgChart, digest: str, budget: _Budget) -> ChatDecision:
        schema = REGISTRY.transport_schema("chat_turn", kind="decide")
        prompt = prompts.render(
            "decide", revision=chart.revision, digest=digest, conversation=prompts.conversation(request.history, limit=self.history),
            pending=prompts.pending_lines(request.pending), message=request.text, notes=await run_blocking(self._notes),
            field_digest=prompts.field_digest(AssignmentDraft, ChatDecision), schema=_dump(schema))

        async def build(model: ChatDecision) -> tuple[Any, list[Violation]]:
            found: list[Violation] = []
            for index, node_id in enumerate(model.reuse_nodes):
                node = chart.node(node_id)
                if node is None or node.kind == "root":
                    found.append(violation(f"reuse_nodes.{index}", "unknown_node", f"{node_id!r} is not a team in CHART: use only ids that appear in CHART"))
            if model.assignments:
                found.extend(await run_blocking(lambda: self.chart.check_assignments(model.assignments, chart)))
            return model, found

        return await self._stage("decide", "chat_turn", "decide", prompt, schema, request, budget, build)

    async def _change(self, request: PlanRequest, chart: OrgChart, decision: ChatDecision, budget: _Budget) -> tuple[Checked, list[str]]:
        schema = REGISTRY.transport_schema("chart_change_request")
        prompt = prompts.render(
            "change", revision=chart.revision, digest=await run_blocking(lambda: self.chart.digest(request.text, max_chars=DIGEST_CHARS)),
            field_digest=prompts.field_digest(ChartChangeRequest, NewNode, AddOp, MoveOp, RenameOp, MergeOp, SplitOp, ChildMove),
            message=request.text, decision=decision.model_dump_json(exclude={"assignments"}), kind=decision.change, schema=_dump(schema))

        async def build(model: ChartChangeRequest) -> tuple[Any, list[Violation]]:
            try:
                change = ChartChange.from_request(model, id=await run_blocking(self.chart.next_change_id), task_id=request.request_id,
                                                  base_revision=chart.revision, ts=self._now())
            except ValidationError as exc:
                return None, violations_from_validation_error(exc)
            if change.kind != decision.change:
                return None, [violation("ops", "kind_mismatch", f"you decided change {decision.change}, but these ops make a change of kind {change.kind}")]
            try:
                checked = GATE.check("chart_change", change)
            except GateError as exc:
                return None, exc.violations
            found = await run_blocking(lambda: self.chart.check(checked))
            if any(v.code == "stale_base" for v in found):
                raise StaleChart()
            busy = [v for v in found if v.code == "busy"]
            if busy:
                raise ChartBusy(busy)
            if found:
                return None, found
            preview = await run_blocking(lambda: self.chart.preview(checked))
            return (checked, list(preview.added)), []

        return await self._stage("change", "chart_change_request", None, prompt, schema, request, budget, build)

    async def _assign(self, request: PlanRequest, chart: OrgChart, digest: str, budget: _Budget) -> list[AssignmentDraft]:
        schema = REGISTRY.transport_schema("chat_turn", kind="assignments")
        prompt = prompts.render("assign", digest=digest, field_digest=prompts.field_digest(AssignmentDraft, AssignmentPlan),
                                message=request.text, notes=await run_blocking(self._notes), schema=_dump(schema))

        async def build(model: AssignmentPlan) -> tuple[Any, list[Violation]]:
            found = await run_blocking(lambda: self.chart.check_assignments(model.assignments, chart))
            return list(model.assignments), found

        return await self._stage("assign", "chat_turn", "assignments", prompt, schema, request, budget, build)

    async def _stage(self, stage: str, family: str, kind: str | None, prompt: str, schema: dict, request: PlanRequest,
                     budget: _Budget, build: Build) -> Any:
        """One stage: ask, read, gate, check; on rejection ask again with the reasons. Returns what `build` made."""
        context = call_context(request.message_id)
        violations: list[Violation] = []
        replies: list[dict] = []
        for attempt in range(1, self.attempts + 1):
            text = prompt
            if attempt > 1:
                delta = prompts.changed_keys(replies[-2] if len(replies) > 1 else None, replies[-1] if replies else None)
                text = prompt + "\n\n" + prompts.render("retry", n=attempt - 1, max=self.attempts,
                                                       violations=prompts.violation_lines(violations), delta=delta)
            budget.take(stage, violations)
            try:
                obj, _usd, _how = await asyncio.wait_for(
                    self.connector.call_json(self._redact(text), schema=schema, timeout=self.timeout, function="chat_agent", step=stage,
                                             context=context), timeout=self.timeout + _CALL_GRACE_S)
            except Exception as exc:                     # noqa: BLE001  (CancelledError is not an Exception)
                failed = failure_kind(exc)
                if failed is None:
                    raise
                if failed in NO_RETRY_KINDS:
                    if isinstance(exc, ConnectorFailure):
                        raise
                    raise ConnectorFailure(failed, str(exc), provider=getattr(exc, "provider", None)) from exc
                violations = [violation("", failed, f"the call ended with {failed}: answer with one JSON object that matches SCHEMA")]
                continue
            if isinstance(obj, dict):
                replies.append(obj)
            try:
                parsed = self._parser.parse(family, obj, kind=kind)
                GATE.check(family, parsed.model)
            except ReplyInvalid as exc:
                violations = exc.violations
                continue
            except GateError as exc:
                violations = exc.violations
                continue
            result, violations = await build(parsed.model)
            if not violations:
                return result
        raise StageFailed(stage, "attempts", violations)

    # ---- helpers -----------------------------------------------------------------------------------------------------------

    async def _reuse_change(self, request: PlanRequest, chart: OrgChart, ids: Sequence[str], reason: str) -> Checked:
        """A change of kind reuse built by code: it only logs which teams the request went to."""
        unique = list(dict.fromkeys(ids))[:10]
        change = ChartChange(kind="reuse", reason=clip(reason, 400), reuses=unique, ops=[], id=await run_blocking(self.chart.next_change_id),
                             task_id=request.request_id, base_revision=chart.revision, ts=self._now())
        checked = GATE.check("chart_change", change)
        found = await run_blocking(lambda: self.chart.check(checked))
        if any(v.code == "stale_base" for v in found):
            raise StaleChart()
        if found:                                                  # ids come from the chart or from checked replies: a bug, not bad output
            raise ValueError("a reuse change built by code was refused: " + "; ".join(v.message for v in found))
        return checked

    @staticmethod
    def _draft_for(text: str, team: Candidate, chart: OrgChart) -> AssignmentDraft:
        dept = team.id if team.kind == "department" else chart.department_of(team.id)
        return AssignmentDraft(ref="a1", dept=dept, scope=team.id if team.kind == "division" else None,
                               title=one_line_title(text, 60) or "Your request", brief=clip(" ".join(text.split()), 2000) or "Your request")

    async def _fallback(self, request: PlanRequest, chart: OrgChart, budget: _Budget) -> Plan:
        """T5. A department whose words match, else candidates for a `choice` card; no department at all is F1."""
        found = fallback_plan(request.text, chart)
        if found is None:
            raise ConnectorFailure("bad_output", "no usable answer and no team to fall back on")
        if found.reuse is None:
            return Plan("none", candidates=list(found.candidates), keywords=True, calls=budget.used, revision=chart.revision)
        change = await self._reuse_change(request, chart, [found.reuse.id], f"The words of the request fit the {found.reuse.name} team {KEYWORDS_NOTE}")
        return Plan("work", change=change, drafts=[self._draft_for(request.text, found.reuse, chart)], keywords=True, calls=budget.used,
                    revision=chart.revision)

    def _chart_after(self, change: Checked, head: OrgChart, added: Sequence[str]) -> OrgChart:
        """The chart as it will be once `change` is applied, with the ids the chart store will really give (from its dry run)."""
        preview = self.chart.preview(change)
        names: dict[str, list[str]] = {}
        for op in change.model.ops:
            for node in ([op.node] if isinstance(op, AddOp) else list(op.parts) if isinstance(op, SplitOp) else []):
                if node.ref in preview.ids_by_ref:
                    names.setdefault(node.name, []).append(preview.ids_by_ref[node.ref])

        def new_id(kind: str, name: str, taken: Any) -> str:
            queue = names.get(name)
            return queue.pop(0) if queue else slug_id(kind, name, taken)

        return apply_change(head, change.model, new_id=new_id).chart

    def _digest_of(self, chart: OrgChart, text: str) -> str:
        return self.chart.rules.digest(self.chart.db.conn(), chart, text, max_chars=DIGEST_CHARS)

    def _now(self) -> int:
        return int(self._clock.now()) if self._clock is not None else 0


def _teams_of(drafts: Sequence[AssignmentDraft]) -> list[str]:
    ids: list[str] = []
    for draft in drafts:
        ids.append(draft.dept)
        if draft.scope:
            ids.append(draft.scope)
    return ids


def _dump(schema: dict) -> str:
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))
