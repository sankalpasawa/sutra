"""`TurnRunner`: one owner request at a time through the chat agent (orchestrator 5.2, T0 to T9; S4-fnodes-07, S4-fnodes-12).

    runner = TurnRunner(db=..., chart=..., chats=..., tasks=..., agent=..., connector=..., publish=bus.publish_one)
    await runner.post_user_message("cs_org", text, choice=None)   # T0: stores the line, answers at once (Accepted), the turn runs behind
    await runner.decide(change_id, approve)                       # the owner's yes or no on a pending chart change (resumes the request)
    await runner.retry("cs_org")                                  # the last request that ended in state `error`, again
    await runner.wait_idle() / runner.close()                     # tests and shutdown

The chart is global, so ONE turn runs at a time; up to `PENDING_TURNS` more wait (the next gets 429 `too_many_pending`). T1: a bare yes
or no with exactly one change waiting for approval answers it with no model call; so does a click on a card button (`choice`). T2 to T5
are the agent's; T6: a rearrange that merges or splits stores `pending_approval` and posts an `approval` card; T7: `ChartStore.apply`,
then one transaction per assignment in dependency order (`TaskService.create`, the owner's words as the first line of the team's chat),
then `start_ready()`; T8: the code template line and the cards. Every Sutra line is a template (`planner.LINES`): no sentence of the
model is ever shown. The usage rows of the model calls are written by the connector router (`AsyncConnector.records_usage`), not here.

Events: `chat.turn` `{session_id, turn, message_id, phase, detail}` with phases reading_chart, consulting_library, planning, applying,
handing_off, done, or error. The org chat's `phase` (reading, planning, building) is kept in `ChatStore.set_turn_phase`.
"""
import asyncio
import inspect
import json
import logging
import re
import sqlite3
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sutra_app.library.gate import GATE, Checked
from sutra_app.library.org_chart import AddOp, MergeOp, MoveOp, OrgChart, RenameOp, SplitOp
from sutra_app.orchestrator.agent import planner
from sutra_app.orchestrator.agent.agent import ChartBusy, ChatAgent, Plan, PlanRequest, StaleChart
from sutra_app.orchestrator.agent.planner import TaskLine, line, names_phrase
from sutra_app.orchestrator.agent.ports import PENDING_TURNS, ConnectorFailure, ConnectorPort, hint, missing_cli, usable
from sutra_app.orchestrator.agent.replies import AssignmentDraft, ChatDecision, dependency_order
from sutra_app.orchestrator.chart import ChangeFailed, ChartStore
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.db import Database, Tx, run_blocking
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound
from sutra_app.orchestrator.ids import ORG_SESSION_ID, IdFactory
from sutra_app.orchestrator.models import Accepted, ChangeContext, ChangeResult, ChatChoice
from sutra_app.orchestrator.tasks import TaskService
from sutra_app.orchestrator.textutil import one_line_title, parse_yes_no

__all__ = ["TurnRunner", "TurnHooks", "PHASE_DETAIL", "TITLE_CHARS", "YES", "NO", "NONE_OPTION"]

log = logging.getLogger(__name__)
ORG = ORG_SESSION_ID
TITLE_CHARS = 60
YES, NO, NONE_OPTION = "yes", "no", "none"
PHASE_DETAIL = {
    "reading_chart": "Reading the org chart", "consulting_library": "Checking the model library", "planning": "Planning",
    "applying": "Setting up the team", "handing_off": "Setting up the team", "done": "Done", "error": "",
}
_BUILDING = ("applying", "handing_off")
_CHOICE_REF = re.compile(r"req:([0-9]+):choice")


@dataclass
class TurnHooks:
    """Optional callbacks (sync or async) for whoever wires the runner: each phase, the end of a turn, an error line."""

    on_phase: Callable[[int, str], Any] | None = None
    on_done: Callable[[int], Any] | None = None
    on_error: Callable[[int, str], Any] | None = None


@dataclass
class _Pick:
    kind: str                       # approval | team | none
    change_id: str | None = None
    approve: bool = False
    node_id: str | None = None
    origin: int = 0                 # the request message a `choice` card belongs to


@dataclass
class _Item:
    message_id: int | None
    pick: _Pick | None = None
    decide: tuple[str, bool] | None = None
    future: asyncio.Future | None = None


@dataclass
class _Applied:
    result: ChangeResult
    before: OrgChart
    after: OrgChart


class TurnRunner:
    def __init__(self, *, db: Database, chart: ChartStore, chats: ChatStore, tasks: TaskService, agent: ChatAgent, connector: ConnectorPort,
                 publish: Callable[[str, dict], Any] | None = None, redact: Callable[[str], str] | None = None,
                 hooks: TurnHooks | None = None, pending_turns: int = PENDING_TURNS) -> None:
        self.db, self.chart, self.chats, self.tasks, self.agent, self.connector = db, chart, chats, tasks, agent, connector
        self._publish = publish or (lambda _type, _data: None)
        self._redact = redact or (lambda text: text)
        self.hooks = hooks or TurnHooks()
        self.pending_turns = pending_turns
        self._waiting: deque[_Item] = deque()
        self._active: _Item | None = None
        self._wake: asyncio.Event | None = None
        self._worker: asyncio.Task | None = None

    # =================================================================================================================
    # T0: accept
    # =================================================================================================================

    async def post_user_message(self, session_id: str, text: str, choice: ChatChoice | None = None) -> Accepted:
        """Store the owner's line (state `pending`), queue the turn and return at once. A click on a card button (`choice`) is stored
        as the owner's line with the option's label. Raises 503 `provider_unavailable` / `cli_missing` before anything is stored when
        a model is needed and none is usable, 429 `too_many_pending`, 409 `already_decided` for a card answered before, 422 `validation`."""
        if session_id != ORG:
            raise AppError("validation", f"only the org chat {ORG} is answered by the chat agent")
        body = text.strip()
        if not body:
            raise AppError("validation", "write something first")
        resolved = await run_blocking(self._resolve_choice, choice) if choice is not None else None
        if resolved is None and not await run_blocking(self._is_answer, body):
            self._preflight()                                   # only a request that may call a model needs one
        self._room()
        message_id = await run_blocking(self._store_user_line, resolved.label if resolved is not None else body, choice)
        turn = "queued" if (self._active is not None or self._waiting) else "started"
        self._enqueue(_Item(message_id, resolved.pick if resolved is not None else None))
        return Accepted(message_id=message_id, turn=turn)

    async def retry(self, session_id: str) -> Accepted:
        """Run the newest owner line again when it ended in state `error` (the chart was not changed by it)."""
        if session_id != ORG:
            raise AppError("validation", f"only the org chat {ORG} has requests to retry")
        found = await run_blocking(self._last_user_line)
        if found is None or found["state"] != "error":
            raise NotFound("a request to retry")
        self._preflight()
        self._room()
        await run_blocking(self._set_state_tx, found["id"], "pending")
        turn = "queued" if (self._active is not None or self._waiting) else "started"
        self._enqueue(_Item(found["id"]))
        return Accepted(message_id=found["id"], turn=turn)

    async def decide(self, change_id: str, approve: bool) -> ChangeResult:
        """The owner's yes or no on a change waiting for approval, from a route. It waits its turn behind the running request, then
        applies (or refuses) the change and, for a change the chat agent planned, finishes the request: assignments, tasks, lines and
        cards. `AlreadyDecided` is raised for a change decided before."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._enqueue(_Item(None, decide=(change_id, approve), future=future))
        return await future

    async def wait_idle(self) -> None:
        """Return when no turn is running or waiting (tests, shutdown)."""
        while self._active is not None or self._waiting:
            await asyncio.sleep(0.002)

    async def close(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None and not worker.done():
            worker.cancel()
            try:
                await worker
            except (asyncio.CancelledError, Exception):       # noqa: BLE001
                pass
        for item in [*self._waiting, *([self._active] if self._active else [])]:
            if item.future is not None and not item.future.done():
                item.future.cancel()
        self._waiting.clear()
        self._active = None
        self.chats.set_turn_phase(None)

    @property
    def busy(self) -> bool:
        return self._active is not None or bool(self._waiting)

    # ---- accept helpers ---------------------------------------------------------------------------------------------------

    def _preflight(self) -> None:
        status = self.connector.status()
        if usable(status):
            return
        why = hint(status)
        raise AppError("cli_missing" if missing_cli(status) else "provider_unavailable", line("no_connector", hint=why))

    def _room(self) -> None:
        waiting = len(self._waiting) + (1 if self._active is not None else 0)
        if waiting >= 1 + self.pending_turns:
            raise AppError("too_many_pending", "Too many requests are waiting. Try again when one is done.")

    def _is_answer(self, text: str) -> bool:
        """A bare yes or no while exactly one change waits for approval: it needs no model."""
        return parse_yes_no(text) is not None and len(self.chart.pending()) == 1

    def _resolve_choice(self, choice: ChatChoice) -> "_Resolved":
        conn = self.db.conn()
        row = conn.execute("SELECT id, session_id, kind, card_json, src_ref FROM chat_messages WHERE id = ?", (choice.message_id,)).fetchone()
        card = json.loads(row["card_json"]) if row is not None and row["card_json"] else None
        if row is None or row["session_id"] != ORG or row["kind"] != "card" or card is None or card.get("type") not in ("approval", "choice"):
            raise AppError("validation", "that message has no buttons to press")
        wanted = choice.option.strip().casefold()
        option = next((o for o in card["options"] if o["id"].casefold() == wanted or o["label"].casefold() == wanted), None)
        if option is None:
            raise AppError("validation", f"{choice.option!r} is not one of the buttons: {', '.join(o['label'] for o in card['options'])}")
        if card["type"] == "approval":
            change = self.chart.record(card["change_id"])
            if change.out.status != "pending_approval":
                raise AlreadyDecided(_result_of_out(change.out))
            return _Resolved(_Pick("approval", change_id=card["change_id"], approve=option["id"] == YES), option["label"])
        if conn.execute("SELECT 1 FROM chat_messages WHERE session_id = ? AND src_ref = ?", (ORG, f"choice:{choice.message_id}")).fetchone():
            raise AlreadyDecided(None)
        origin = _CHOICE_REF.fullmatch(row["src_ref"] or "")
        if origin is None:
            raise AppError("validation", "that question is not waiting for an answer")
        kind = "none" if option["id"] == NONE_OPTION else "team"
        return _Resolved(_Pick(kind, node_id=None if kind == "none" else option["id"], origin=int(origin.group(1))), option["label"])

    def _store_user_line(self, text: str, choice: ChatChoice | None) -> int:
        with self.db.tx() as tx:
            src = f"choice:{choice.message_id}" if choice is not None else None
            posted = self._post(tx, kind="text", text=text, role="user", who="user", state="pending", src_ref=src)
            if posted is None:
                raise AlreadyDecided(None)
            return posted.id

    def _last_user_line(self) -> sqlite3.Row | None:
        return self.db.conn().execute(
            "SELECT id, state FROM chat_messages WHERE session_id = ? AND role = 'user' ORDER BY id DESC LIMIT 1", (ORG,)).fetchone()

    # =================================================================================================================
    # the queue
    # =================================================================================================================

    def _enqueue(self, item: _Item) -> None:
        self._waiting.append(item)
        loop = asyncio.get_running_loop()
        if self._worker is None or self._worker.done() or self._worker.get_loop() is not loop:
            self._wake = asyncio.Event()
            self._worker = loop.create_task(self._work(), name="chat-agent-turns")
        assert self._wake is not None
        self._wake.set()

    async def _work(self) -> None:
        assert self._wake is not None
        wake = self._wake
        while True:
            while not self._waiting:
                wake.clear()
                await wake.wait()
            item = self._waiting.popleft()
            self._active = item
            try:
                await self._run(item)
            except asyncio.CancelledError:
                raise
            except Exception:                                      # noqa: BLE001  (_run reports its own; this keeps the worker alive)
                log.exception("a chat turn ended with an unexpected error")
            finally:
                self._active = None

    async def _run(self, item: _Item) -> None:
        mid = item.message_id
        try:
            if item.decide is not None:
                result = await self._decide_flow(item.decide[0], item.decide[1], None, raise_already=True)
                if item.future is not None and not item.future.done():
                    item.future.set_result(result)
                return
            assert mid is not None
            await self._turn(item, mid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:                                   # noqa: BLE001
            if item.future is not None:
                if not item.future.done():
                    item.future.set_exception(exc)
                return
            log.exception("chat turn for message %s failed", mid)
            await self._finish_error(mid, line("failed"))
        finally:
            self.chats.set_turn_phase(None)

    # =================================================================================================================
    # one turn
    # =================================================================================================================

    async def _turn(self, item: _Item, mid: int) -> None:
        msg = await run_blocking(self.chats.message, mid)
        if msg is None:
            return
        if item.pick is not None:
            await self._picked(item.pick, mid)
            return
        pending = await run_blocking(self.chart.pending)
        answer = parse_yes_no(msg.text)
        if answer is not None and len(pending) == 1:                               # T1
            await self._decide_flow(pending[0].id, answer, mid, raise_already=False)
            return
        request = await run_blocking(self._request_of, mid, msg.text)
        stale = 0
        while True:
            try:
                plan = await self.agent.plan(request, phase=lambda name: self._phase(mid, name))
                done = await self._carry_out(mid, request, plan)
            except ConnectorFailure as exc:
                await self._connector_down(mid, exc)
                return
            except ChartBusy as exc:
                await self._reply(mid, [line("busy", reason=exc.violations[0].message)])
                return
            except StaleChart:
                done = False
            if done:
                return
            stale += 1
            if stale >= 2:
                await self._finish_error(mid, line("stale"))
                return

    async def _picked(self, pick: _Pick, mid: int) -> None:
        if pick.kind == "approval":
            assert pick.change_id is not None
            await self._decide_flow(pick.change_id, pick.approve, mid, raise_already=False)
        elif pick.kind == "none":
            await self._reply(mid, [line("smalltalk")])
        else:
            assert pick.node_id is not None
            origin = await run_blocking(self.chats.message, pick.origin)
            if origin is None:
                await self._finish_error(mid, line("failed"))
                return
            request = PlanRequest(text=origin.text, message_id=pick.origin)
            try:
                plan = await self.agent.choice_plan(request, pick.node_id)
                if not await self._carry_out(mid, request, plan):
                    await self._finish_error(mid, line("stale"))
            except ConnectorFailure as exc:
                await self._connector_down(mid, exc)

    def _request_of(self, mid: int, text: str) -> PlanRequest:
        rows = self.chats.last_messages(ORG, self.agent.history + 2, kinds=("text", "error"))
        history = [(m.who, m.text) for m in rows if m.id != mid][-self.agent.history:]
        pending = [f"{c.id}: {c.summary} (waiting for the owner's yes or no)" for c in self.chart.pending()]
        return PlanRequest(text=text, message_id=mid, history=history, pending=pending)

    # ---- carrying a plan out (T6 to T8) -------------------------------------------------------------------------------

    async def _carry_out(self, mid: int, request: PlanRequest, plan: Plan) -> bool:
        """True when the turn is finished; False when the chart moved under it (stale: plan again)."""
        if plan.outcome == "status":
            await self._reply(mid, [await run_blocking(self._status_text)])
            return True
        if plan.outcome == "smalltalk":
            await self._reply(mid, [line("smalltalk")])
            return True
        if plan.outcome in ("clarify", "none"):
            await self._offer(mid, request, plan)
            return True
        self.chats.set_turn_phase("building")
        applied: _Applied | None = None
        if plan.change is not None:
            self._phase(mid, "applying")
            title = plan.drafts[0].title if plan.drafts else one_line_title(request.text, TITLE_CHARS)
            ctx = ChangeContext(session_id=ORG, message_id=request.message_id, request_id=request.request_id, request_title=title)
            resume = self._resume_note(request, plan)
            try:
                applied = await run_blocking(self._apply_sync, plan.change, ctx, resume)
            except ChangeFailed:
                await self._finish_error(mid, line("save_failed"))
                return True
            except AppError as exc:
                if exc.code == "rules":                                 # the chart moved between the check and the apply
                    return False
                raise
            if applied.result.status == "stale":
                return False
            if applied.result.status == "pending_approval":
                await self._ask_approval(mid, plan, applied)
                return True
        await self._hand_off(mid, request, plan, applied)
        return True

    async def _hand_off(self, mid: int, request: PlanRequest, plan: Plan, applied: _Applied | None) -> None:
        drafts = dependency_order(plan.drafts)
        task_ids: list[str] = []
        failure: str | None = None
        if drafts:
            self._phase(mid, "handing_off")
            change_id = applied.result.id if applied is not None else None
            try:
                task_ids = await run_blocking(self._create_tasks, request, drafts, change_id)
            except AppError as exc:
                failure = exc.message
            if task_ids:
                try:
                    await self.tasks.start_ready()
                except Exception:                                           # noqa: BLE001  (a task that cannot start is that task's problem)
                    log.exception("start_ready failed after request %s", request.request_id)
        await run_blocking(self._write_outcome, mid, plan, applied, drafts, task_ids, failure)
        self._phase(mid, "done")
        await self._call_hook(self.hooks.on_done, mid)

    # ---- approvals -----------------------------------------------------------------------------------------------------

    async def _ask_approval(self, mid: int, plan: Plan, applied: _Applied) -> None:
        question = self._approval_question(plan.change.model if plan.change else None, applied.before)  # type: ignore[union-attr]
        card = {"type": "approval", "change_id": applied.result.id, "question": question,
                "options": [{"id": YES, "label": "Yes"}, {"id": NO, "label": "No"}]}
        await run_blocking(self._write_cards, mid, [], [card])
        self._phase(mid, "done")
        await self._call_hook(self.hooks.on_done, mid)

    async def _decide_flow(self, change_id: str, approve: bool, mid: int | None, *, raise_already: bool) -> ChangeResult:
        """Answer a pending change. For a change the chat agent planned, finish its request (stage C if it is still missing, tasks,
        lines and cards). `mid` is the owner's yes/no line to mark done, or None when the answer came from a route."""
        self.chats.set_turn_phase("building")
        stored = await run_blocking(self.chart.record, change_id)
        try:
            result = await run_blocking(self.chart.decide, change_id, approve)
        except AlreadyDecided as exc:
            if raise_already:
                raise
            await self._reply(mid, [line("already")])
            return exc.result if exc.result is not None else _result_of_out(stored.out)
        except ChangeFailed:
            await self._finish_error(mid, line("save_failed"))
            raise
        note = stored.plan if stored.out.actor == "chat_agent" else None
        if mid is not None:
            self._phase(mid, "applying")
        if result.status != "applied":
            after = await run_blocking(self.chart.record, change_id)
            reason = (after.violations[0]["message"] if after.violations else "the change was not applied")
            sentence = line("declined") if not approve else line("rejected", reason=reason)
            await self._reply(mid, [sentence] if note is not None or mid is not None else [])
            return result
        if note is None or stored.change is None:
            await self._reply(mid, [])
            return result
        request = PlanRequest(text=note["text"], message_id=int(note["message_id"]))
        decision = ChatDecision.model_validate(note["decision"]) if note.get("decision") else None
        try:
            plan = await self.agent.resume(request, decision)
        except ConnectorFailure as exc:
            await self._connector_down(mid, exc)
            return result
        plan = _with_change(plan, stored.change)
        applied = await run_blocking(self._applied_of, stored.change, result)
        shown = mid if mid is not None else request.message_id
        await self._hand_off(shown, request, plan, applied)
        if plan.outcome in ("none", "clarify"):                       # the keywords found no team for the work: ask the owner
            await self._offer(shown, request, plan)
        return result

    # =================================================================================================================
    # the database work (each runs in one worker thread)
    # =================================================================================================================

    def _apply_sync(self, change: Checked, ctx: ChangeContext, resume: dict) -> _Applied:
        before = self.chart.head().model
        result = self.chart.apply(change, actor="chat_agent", ctx=ctx, plan=resume)
        after = self.chart.head().model if result.status == "applied" else before
        return _Applied(result, before, after)

    def _applied_of(self, change: Checked, result: ChangeResult) -> _Applied:
        """The chart before and after an approved change (the revision it was based on, and the head)."""
        conn = self.db.conn()
        row = conn.execute("SELECT body FROM org_charts WHERE revision = ?", (change.model.base_revision,)).fetchone()
        before = GATE.check("org_chart", row["body"]).model if row is not None else self.chart.head().model
        return _Applied(result, before, self.chart.head().model)

    @staticmethod
    def _resume_note(request: PlanRequest, plan: Plan) -> dict:
        return {"v": 1, "message_id": request.message_id, "text": request.text, "keywords": plan.keywords,
                "decision": json.loads(plan.decision.model_dump_json()) if plan.decision is not None else None}

    def _create_tasks(self, request: PlanRequest, drafts: Sequence[AssignmentDraft], change_id: str | None) -> list[str]:
        """One transaction per assignment, dependencies first. The owner's words become the first line of the team's chat (the
        engine never echoes them)."""
        made: dict[str, str] = {}
        for draft in drafts:
            follows = draft.follows
            while True:
                try:
                    with self.db.tx() as tx:
                        task = self.tasks.create(
                            tx, dept_id=draft.dept, text=request.text, title=draft.title, scope_id=draft.scope, framing=draft.brief,
                            depends_on=[made[ref] for ref in draft.depends_on if ref in made], follows=follows,
                            request=request.request_id, change_id=change_id)
                        sid = tx.conn.execute("SELECT chat_session_id FROM graph_nodes WHERE id = ?", (draft.dept,)).fetchone()["chat_session_id"]
                        self._post(tx, session_id=sid, kind="text", text=request.text, role="user", who="user",
                                   src_ref=f"req:{request.message_id}:{task.id}", task_id=task.id)
                    break
                except AppError as exc:
                    if follows is not None and exc.code == "validation":   # the task it should continue has no run: start fresh instead
                        follows = None
                        continue
                    raise
            made[draft.ref] = task.id
        return list(made.values())

    def _write_outcome(self, mid: int, plan: Plan, applied: _Applied | None, drafts: Sequence[AssignmentDraft], task_ids: Sequence[str],
                       failure: str | None) -> None:
        """T8: the template line, the chart card and a task card per task; the request is `ok`."""
        sentences = self._sentences(plan, applied, drafts)
        if failure is not None:
            sentences = [line("task_failed", reason=failure)]
        cards: list[dict] = []
        if applied is not None and applied.result.status == "applied" and plan.change is not None and plan.change.model.kind != "reuse":
            cards.append(self._chart_card(plan.change, applied))
        conn = self.db.conn()
        for task_id in task_ids:
            task = self.tasks.store.out_in(conn, task_id)
            cards.append({"type": "task", "task_id": task.id, "dept_id": task.dept_id, "dept_name": task.dept_name, "title": task.title,
                          "status": task.status})
        self._write_cards(mid, sentences, cards, error=failure is not None)

    def _write_cards(self, mid: int | None, sentences: Sequence[str], cards: Sequence[dict], *, error: bool = False,
                     src_ref: str | None = None) -> None:
        with self.db.tx() as tx:
            if sentences:
                self._post(tx, kind="error" if error else "text", text=" ".join(sentences))
            for index, card in enumerate(cards):
                self._post(tx, kind="card", card=card, src_ref=src_ref if index == 0 else None)
            if mid is not None:
                self._set_state(tx, mid, "error" if error else "ok")

    def _post(self, tx: Tx, *, kind: str, session_id: str = ORG, text: str = "", card: dict | None = None, role: str = "agent",
              who: str = "sutra", src_ref: str | None = None, state: str = "ok", task_id: str | None = None):
        payload: dict[str, Any] = dict(kind=kind, session_id=session_id, role=role, who=who, text=self._redact(text) if text else "",
                                       card=card, src_ref=src_ref, state=state, task_id=task_id, at=tx.now())
        return self.chats.post(tx, session_id, GATE.check("chat_message", payload, ctx=tx.ctx))

    def _set_state(self, tx: Tx, mid: int, state: str) -> None:
        tx.conn.execute("UPDATE chat_messages SET state = ? WHERE id = ? AND session_id = ?", (state, mid, ORG))
        out = ChatStore.message_in(tx.conn, mid)
        tx.emit("chat.message", {"session_id": ORG, "message": out.model_dump(mode="json")})

    def _set_state_tx(self, mid: int, state: str) -> None:
        with self.db.tx() as tx:
            self._set_state(tx, mid, state)

    def _status_text(self) -> str:
        chart = self.chart.head().model
        # How long a team has waited for the owner (gap attention) is timed from its open question, not from `last_event_at`: a waiting
        # team's engine lives on and its heartbeat moves `last_event_at` every few seconds.
        rows = self.db.conn().execute(
            "SELECT t.dept_id, t.title, t.status, CASE WHEN t.status = 'waiting_user' THEN (SELECT min(m.at) FROM chat_messages m"
            " WHERE m.task_id = t.id AND m.kind = 'question' AND m.answered_by IS NULL) END AS asked_at FROM tasks t"
            " ORDER BY t.created_at, t.rowid").fetchall()
        clock = getattr(self.tasks, "clock", None)
        return planner.status_report(chart, [TaskLine(r["dept_id"], r["title"], r["status"], r["asked_at"]) for r in rows],
                                     now=clock.now() if clock is not None else None)

    # ---- the words of the org chat -------------------------------------------------------------------------------------

    async def _reply(self, mid: int | None, sentences: Sequence[str]) -> None:
        """A turn that ends with a plain line: post it, mark the request `ok`, say `done`."""
        if mid is None and not sentences:
            return
        await run_blocking(self._write_cards, mid, list(sentences), [])
        if mid is not None:
            self._phase(mid, "done")
            await self._call_hook(self.hooks.on_done, mid)

    async def _offer(self, mid: int, request: PlanRequest, plan: Plan) -> None:
        options = [{"id": c.id, "label": c.name} for c in plan.candidates] + [{"id": NONE_OPTION, "label": planner.NONE_OF_THESE}]
        card = {"type": "choice", "question": line("choice"), "options": options}
        sentences = [line("none")] if plan.outcome == "none" else []
        await run_blocking(lambda: self._write_cards(mid, sentences, [card], src_ref=f"req:{request.message_id}:choice"))
        self._phase(mid, "done")
        await self._call_hook(self.hooks.on_done, mid)

    def _sentences(self, plan: Plan, applied: _Applied | None, drafts: Sequence[AssignmentDraft]) -> list[str]:
        chart = applied.after if applied is not None else self.chart.head().model
        before = applied.before if applied is not None else chart
        ids = dict(applied.result.ids_by_ref) if applied is not None else {}

        def name(target: str) -> str:
            node = chart.node(ids.get(target, target)) or before.node(ids.get(target, target))
            return node.name if node is not None else target

        receiving = {d.dept for d in drafts} | {d.scope for d in drafts if d.scope}
        said: set[str] = set()
        out: list[str] = []
        for op in (plan.change.model.ops if plan.change is not None else []):
            if isinstance(op, AddOp):
                new_id = ids.get(op.node.ref, op.node.ref)
                said.add(new_id)
                out.append(line("add", name=op.node.name) if new_id in receiving else line("add_only", name=op.node.name))
            elif isinstance(op, MoveOp):
                out.append(line("move", x=name(op.node), y=name(op.to_parent)))
            elif isinstance(op, RenameOp):
                out.append(line("rename", a=before.node(op.node).name if before.node(op.node) else op.node, b=op.name) if op.name
                           else line("purpose", a=name(op.node)))
            elif isinstance(op, MergeOp):
                out.append(line("merge", a=names_phrase([name(s) for s in op.sources]), b=name(op.into)))
            elif isinstance(op, SplitOp):
                out.append(line("split", a=name(op.node), b=names_phrase([p.name for p in op.parts])))
        elsewhere = [d.dept for d in drafts if d.dept not in said]
        if elsewhere:
            out.append(line("reuse", name=names_phrase([name(d) for d in dict.fromkeys(elsewhere)])))
        return out

    @staticmethod
    def _chart_card(change: Checked, applied: _Applied) -> dict:
        model, result, before, after = change.model, applied.result, applied.before, applied.after
        ids = result.ids_by_ref

        def name(node_id: str) -> str:
            node = after.node(node_id) or before.node(node_id)
            return node.name if node is not None else node_id

        added = [{"id": i, "name": name(i), "kind": after.node(i).kind} for i in result.added if after.node(i) is not None]
        moved = []
        for i in result.moved:
            if before.node(i) is None or after.node(i) is None:
                continue
            old, new = before.parent_of(i), after.parent_of(i)
            moved.append({"id": i, "name": name(i), "from_name": name(old) if old else "", "to_name": name(new) if new else ""})
        archived = []
        for op in model.ops:
            if isinstance(op, MergeOp):
                for source in op.sources:
                    real = ids.get(source, source)
                    if real in result.archived:
                        archived.append({"id": real, "name": name(real), "into_name": name(ids.get(op.into, op.into))})
        return {"type": "chart_change", "change_id": result.id, "decision": result.decision, "summary": result.summary,
                "added": added, "moved": moved, "archived": archived, "pending": False}

    @staticmethod
    def _approval_question(change: Any, before: OrgChart) -> str:
        parts = []
        refs = {}
        for op in change.ops if change is not None else []:
            if isinstance(op, AddOp):
                refs[op.node.ref] = op.node.name
            elif isinstance(op, SplitOp):
                refs.update({p.ref: p.name for p in op.parts})

        def name(target: str) -> str:
            node = before.node(target)
            return node.name if node is not None else refs.get(target, target)

        for op in change.ops if change is not None else []:
            if isinstance(op, MergeOp):
                parts.append(line("approve_merge", a=names_phrase([name(s) for s in op.sources]), b=name(op.into)))
            elif isinstance(op, SplitOp):
                parts.append(line("approve_split", a=name(op.node), b=names_phrase([p.name for p in op.parts])))
        return " ".join(parts)

    # ---- errors and events ----------------------------------------------------------------------------------------------

    async def _connector_down(self, mid: int | None, exc: ConnectorFailure) -> None:
        status = self.connector.status()
        why = hint(status) or str(exc)[:120]
        await self._finish_error(mid, line("no_connector", hint=why))

    async def _finish_error(self, mid: int | None, sentence: str) -> None:
        await run_blocking(lambda: self._write_cards(mid, [sentence], [], error=True))
        if mid is not None:
            self._phase(mid, "error")
            await self._call_hook(self.hooks.on_error, mid, sentence)

    def _phase(self, mid: int, name: str) -> None:
        if name in ("reading_chart",):
            self.chats.set_turn_phase("reading")
        elif name in ("consulting_library", "planning"):
            self.chats.set_turn_phase("planning")
        elif name in _BUILDING:
            self.chats.set_turn_phase("building")
        self._publish("chat.turn", {"session_id": ORG, "turn": mid, "message_id": mid, "phase": name, "detail": PHASE_DETAIL.get(name, "")})
        callback = self.hooks.on_phase
        if callback is not None:
            try:
                found = callback(mid, name)
                if inspect.isawaitable(found):
                    asyncio.ensure_future(found)
            except Exception:                                             # noqa: BLE001
                log.exception("on_phase hook failed")

    async def _call_hook(self, hook: Callable[..., Any] | None, *args: Any) -> None:
        if hook is None:
            return
        try:
            found = hook(*args)
            if inspect.isawaitable(found):
                await found
        except Exception:                                                 # noqa: BLE001
            log.exception("a turn hook failed")


@dataclass
class _Resolved:
    pick: _Pick
    label: str


def _with_change(plan: Plan, change: Checked) -> Plan:
    """A resumed plan keeps the applied change for the template line and the card (it is not applied again)."""
    plan.change = change
    return plan


def _result_of_out(out: Any) -> ChangeResult:
    status = out.status if out.status in ("applied", "pending_approval", "rejected", "stale") else "rejected"
    return ChangeResult(id=out.id, status=status, decision=out.decision, summary=out.summary, revision=out.revision, added=list(out.added),
                        moved=list(out.moved), archived=list(out.archived))
