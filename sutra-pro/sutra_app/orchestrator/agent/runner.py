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
import dataclasses
import inspect
import json
import logging
import re
import sqlite3
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sutra_app.connectors.egress import scrubbed
from sutra_app.connectors.errors import CallCancelledError
from sutra_app.library.gate import GATE, Checked
from sutra_app.library.org_chart import AddOp, MergeOp, MoveOp, OrgChart, RenameOp, SplitOp
from sutra_app.library.practice import load_packs, pack_by_id
from sutra_app.orchestrator.agent import planner, suggest
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
from sutra_app.orchestrator.reorg_preview import ReorgPreview, card_lines
from sutra_app.orchestrator.standing_rules import StandingRules
from sutra_app.orchestrator.tasks import TaskService
from sutra_app.orchestrator.textutil import one_line_title, parse_yes_no, project_title

__all__ = ["TurnRunner", "TurnHooks", "PHASE_DETAIL", "TITLE_CHARS", "YES", "NO", "NONE_OPTION"]

log = logging.getLogger(__name__)
ORG = ORG_SESSION_ID
def step_framing(brief: str, number: int, total: int, title: str, others: list[str]) -> str:
    """The step's own framing for a project: what the planner wrote for it, then the rule that it does ONLY its own job (D414). Run 4: step 1 named the one improvement that was step 2's job, so the money
    was spent twice. The others are named by their titles so the step knows what is not its to do."""
    rule = (f"THIS IS STEP {number} OF {total} OF A PROJECT. Do ONLY this step's own job: {title}. The other steps do their own work"
            + (f" ({'; '.join(t for t in others if t)[:600]})" if any(others) else "")
            + ". Do not do, start or answer the job of another step, not even in part; leave it to that step.")
    return (brief.rstrip() + "\n\n" if brief and brief.strip() else "") + rule


_NO_PROJECT_ADDRESS = re.compile(r"/p/(?=prj_)")        # the shape the chat page turns into a link: only the app writes it
PROJECT_SRC = "project:"        # the `src_ref` prefix of a line the owner sent with `POST /api/projects` (MAN-13): a repeated `client_id` finds the same line
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
    pack: str | None = None         # kind `pack`: the practice a suggestion card offered (node_id is the team)


@dataclass
class _Item:
    message_id: int | None
    pick: _Pick | None = None
    decide: tuple[str, bool, dict] | None = None             # (change id, yes, {names, folder, access}): D427's naming travels with the yes
    future: asyncio.Future | None = None


@dataclass
class _Applied:
    result: ChangeResult
    before: OrgChart
    after: OrgChart


class TurnRunner:
    def __init__(self, *, db: Database, chart: ChartStore, chats: ChatStore, tasks: TaskService, agent: ChatAgent, connector: ConnectorPort,
                 publish: Callable[[str, dict], Any] | None = None, redact: Callable[[str], str] | None = None,
                 hooks: TurnHooks | None = None, pending_turns: int = PENDING_TURNS, projects: Any = None) -> None:
        self.db, self.chart, self.chats, self.tasks, self.agent, self.connector = db, chart, chats, tasks, agent, connector
        self._publish = publish or (lambda _type, _data: None)
        self._redact = redact or (lambda text: text)
        self.hooks = hooks or TurnHooks()
        self.pending_turns = pending_turns
        self.projects = projects                    # the `ProjectService` while SUTRA_NODES_V1 is on (MAN-5), else None: with None this runner is what it was
        # named projects (D427): `team_folder(dept_id, name, folder, access)` gives a project the org chat started (after the owner's yes) its
        # folder; None (a bare test runner) makes none
        self.team_folder: Callable[[str, str, str | None, str], Any] | None = None
        self._waiting: deque[_Item] = deque()
        self._active: _Item | None = None
        self._wake: asyncio.Event | None = None
        self._worker: asyncio.Task | None = None

    # =================================================================================================================
    # T0: accept
    # =================================================================================================================

    async def post_user_message(self, session_id: str, text: str, choice: ChatChoice | None = None, *, budget: int | None = None, decide_for_me: bool = False,
                                 failure_policy: str | None = None, client_id: str | None = None, usd_budget: float | None = None, files: Sequence[dict] = ()) -> Accepted:
        """Store the owner's line (state `pending`), queue the turn and return at once. A click on a card button (`choice`) is stored
        as the owner's line with the option's label. Raises 503 `provider_unavailable` / `cli_missing` before anything is stored when
        a model is needed and none is usable, 429 `too_many_pending`, 409 `already_decided` for a card answered before, 422 `validation`.
        `budget` (D252): the home screen's Budget field, kept with the owner's line; every task this request makes runs with it as J2_BUDGET.
        `failure_policy` and `client_id` come only from `POST /api/projects` (MAN-13, D310 c, D326): the first is kept with the line for the project it may become, the second makes a repeated send find the
        same line (`AlreadyDecided`). `usd_budget` (D423): the same as `budget` for the dollar budget (API price), as J2_USD_BUDGET.
        `files` (D451): [{id, name}] of files in the attachment store that came with a NEW request: the planner is shown their digest and every task the request makes is given them
        (`inputs/attached/`); a file that is gone is a 404 before anything is stored, and a card's answer takes none."""
        if session_id != ORG:
            raise AppError("validation", f"only the org chat {ORG} is answered by the chat agent")
        body = scrubbed(text.strip(), self._redact)                # a secret never lands in the chat store, the team's first line or a prompt
        if not body:
            raise AppError("validation", "write something first")
        resolved = await run_blocking(self._resolve_choice, choice) if choice is not None else None
        if files and choice is not None:
            raise AppError("validation", "Files go with a new request, not with the answer to a card.")
        snapshot = await run_blocking(self.tasks._snapshot, files)          # a file that is gone is a 404 here, before the line is stored (D451)
        if resolved is None and not await run_blocking(self._is_answer, body):
            self._preflight()                                   # only a request that may call a model needs one
        self._room()
        message_id = await run_blocking(self._store_user_line, resolved.label if resolved is not None else body, choice, budget, decide_for_me, failure_policy, client_id,
                                        usd_budget, snapshot)
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

    async def decide(self, change_id: str, approve: bool, *, names: dict[str, str] | None = None, folder: str | None = None,
                     access: str = "edit") -> ChangeResult:
        """The owner's yes or no on a change waiting for approval, from a route. It waits its turn behind the running request, then
        applies (or refuses) the change and, for a change the chat agent planned, finishes the request: assignments, tasks, lines and
        cards. `AlreadyDecided` is raised for a change decided before. `names`, `folder` and `access` are the Create project box's (D427): the
        name the owner gave each team the change adds, and the folder (with what the team may do there) of the one it starts."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._enqueue(_Item(None, decide=(change_id, approve, {"names": names or None, "folder": folder, "access": access}), future=future))
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

    def recover(self) -> int:
        """At start, before any turn runs: every owner line of the org chat still `pending` was accepted by an app that then stopped (closed in the
        middle of a turn, killed, or lost power), and nothing will ever answer it. Each becomes `error`, with one template line saying so, and the
        newest is what `retry` runs again. Returns how many lines it closed. (A turn that had already changed the chart is not undone: Retry plans
        again from the chart as it is.)"""
        with self.db.tx() as tx:
            open_lines = [r["id"] for r in tx.conn.execute(
                "SELECT id FROM chat_messages WHERE session_id = ? AND role = 'user' AND state = 'pending' ORDER BY id", (ORG,)).fetchall()]
            for mid in open_lines:
                self._set_state(tx, mid, "error")
            if open_lines:
                self._post(tx, kind="error", text=line("interrupted"))
        return len(open_lines)

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
        offered = suggest.parse_ref(row["src_ref"])
        if offered is not None:                                    # a practice suggestion after an add (GAP2 rules-notes): Yes or No
            return _Resolved(_Pick("pack", node_id=offered[0], pack=offered[1], approve=option["id"] == suggest.YES), option["label"])
        origin = _CHOICE_REF.fullmatch(row["src_ref"] or "")
        if origin is None:
            raise AppError("validation", "that question is not waiting for an answer")
        kind = "none" if option["id"] == NONE_OPTION else "team"
        return _Resolved(_Pick(kind, node_id=None if kind == "none" else option["id"], origin=int(origin.group(1))), option["label"])

    def _store_user_line(self, text: str, choice: ChatChoice | None, budget: int | None = None, decide_for_me: bool = False,
                         failure_policy: str | None = None, client_id: str | None = None, usd_budget: float | None = None, input_files: Sequence[dict] = ()) -> int:
        with self.db.tx() as tx:
            src = f"choice:{choice.message_id}" if choice is not None else f"{PROJECT_SRC}{client_id}" if client_id else None
            posted = self._post(tx, kind="text", text=text, role="user", who="user", state="pending", src_ref=src)
            if posted is None:
                raise AlreadyDecided(None)
            if budget is not None:      # D252: a sibling key of meta_json, as `via` and `blocks` are; read back by _budget_of
                tx.conn.execute("UPDATE chat_messages SET meta_json = json_set(meta_json, '$.budget', ?) WHERE id = ?", (int(budget), posted.id))
            if usd_budget is not None:      # D423: the dollar budget, the same way
                tx.conn.execute("UPDATE chat_messages SET meta_json = json_set(meta_json, '$.usd_budget', ?) WHERE id = ?", (float(usd_budget), posted.id))
            if input_files:      # D451: the files that came with the request: the snapshot for the tasks it makes, and the receipt the owner's line shows (what the planner and the team are given)
                from sutra_app.orchestrator.tasks import _receipt_of
                tx.conn.execute("UPDATE chat_messages SET meta_json = json_set(meta_json, '$.input_files', json(?), '$.attachments', json(?)) WHERE id = ?",
                                (json.dumps(list(input_files), separators=(",", ":")), json.dumps([_receipt_of(f) for f in input_files], separators=(",", ":")), posted.id))
            if decide_for_me and self.projects is not None:           # MAN-8: the owner's switch for this request; read back by _decide_for_me_of. Not stored with the flag off (G13)
                tx.conn.execute("UPDATE chat_messages SET meta_json = json_set(meta_json, '$.decide_for_me', 1) WHERE id = ?", (posted.id,))
            if failure_policy == "stop_all" and self.projects is not None:           # MAN-13, D310 c: only the owner's own route sets it; stop_branch is the default and is not stored
                tx.conn.execute("UPDATE chat_messages SET meta_json = json_set(meta_json, '$.failure_policy', 'stop_all') WHERE id = ?", (posted.id,))
            return posted.id

    def _files_of(self, message_id: int) -> list[dict]:
        """D451: the files that came with the request line `message_id` ([] for most): what each task the request makes is given."""
        row = self.db.conn().execute("SELECT json_extract(meta_json, '$.input_files') AS f FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        try:
            found = json.loads(row["f"]) if row is not None and row["f"] else []
        except ValueError:
            found = []
        return [f for f in found if isinstance(f, dict) and f.get("id") and f.get("name")] if isinstance(found, list) else []

    def _files_note_of(self, message_id: int) -> str:
        """D451: the digest of those files for the planner (names, kinds, the opening of text, fenced as data); "" for a request with none."""
        files = self._files_of(message_id)
        if not files:
            return ""
        from sutra_app.orchestrator import project_context as ctx
        from sutra_app.orchestrator.run_inputs import _read
        came = [ctx.KFile(name=f["name"], kind=f.get("kind", "text"), size=int(f.get("size", 0)), text=_read(self.tasks.attachments, f["id"], f["name"], f.get("kind", "text"))) for f in files]
        note = ctx.compose_run_block(attached=came, scrub=lambda t: scrubbed(t, self._redact)).text
        return note.replace("(data; in inputs/attached/)", "(data; each team's run is given these files in inputs/attached/)")

    def _usd_budget_of(self, message_id: int) -> float | None:
        """D423: the dollar budget the owner gave with the request line `message_id` (None: the team's own)."""
        row = self.db.conn().execute("SELECT json_extract(meta_json, '$.usd_budget') AS b FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return float(row["b"]) if row is not None and row["b"] is not None else None

    def _budget_of(self, message_id: int) -> int | None:
        """D252: the Budget the owner gave with the request line `message_id` (None: the team's own budget)."""
        row = self.db.conn().execute("SELECT json_extract(meta_json, '$.budget') AS b FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return int(row["b"]) if row is not None and row["b"] is not None else None

    def _decide_for_me_of(self, message_id: int) -> bool:
        """MAN-8: whether the owner turned Decide for me on with the request line `message_id` (the request's `J2_DECIDE_FOR_ME`)."""
        row = self.db.conn().execute("SELECT json_extract(meta_json, '$.decide_for_me') AS d FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return bool(row is not None and row["d"])

    def _failure_policy_of(self, message_id: int) -> str:
        """MAN-13, D310 c: `stop_all` when the owner started this request with that policy, else the default `stop_branch`."""
        row = self.db.conn().execute("SELECT json_extract(meta_json, '$.failure_policy') AS f FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return "stop_all" if row is not None and row["f"] == "stop_all" else "stop_branch"

    def line_of(self, client_id: str) -> int | None:
        """The org-chat line a `POST /api/projects` send with this `client_id` stored, or None (a repeated send finds the first one)."""
        row = self.db.conn().execute("SELECT id FROM chat_messages WHERE session_id = ? AND src_ref = ?", (ORG, f"{PROJECT_SRC}{client_id}")).fetchone()
        return int(row["id"]) if row is not None else None

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
                result = await self._decide_flow(item.decide[0], item.decide[1], None, raise_already=True, **item.decide[2])
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
        request = self._as_planner(request)
        try:
            stale = 0
            while True:
                try:
                    plan = await self.agent.plan(request, phase=lambda name: self._phase(mid, name))
                    done = await self._carry_out(mid, request, plan)
                except CallCancelledError:                                  # the owner's Stop (node stop, project stop, kill all) ended the planner's running call: no plan is adopted (D301)
                    self._release_planner(request)
                    await self._finish_error(mid, line("stopped"))              # a stop, not "something went wrong" (G7, D308)
                    return
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
        finally:
            self._release_planner(request)                              # the planner's token lives only while the request is planned (D301)

    def _as_planner(self, request: PlanRequest) -> PlanRequest:
        """With nodes on, the planner's calls carry its node identity and a stop token that the project service keeps while the request is planned (D291, D301). Without: the request as it is."""
        if self.projects is None:
            return request
        node_id, token = self.projects.planner_for(request.request_id)
        return dataclasses.replace(request, node_id=node_id, cancel=token)

    def _release_planner(self, request: PlanRequest) -> None:
        if self.projects is not None:
            self.projects.release_planner(request.request_id)

    async def _picked(self, pick: _Pick, mid: int) -> None:
        if pick.kind == "approval":
            assert pick.change_id is not None
            await self._decide_flow(pick.change_id, pick.approve, mid, raise_already=False)
        elif pick.kind == "none":
            await self._reply(mid, [line("smalltalk")])
        elif pick.kind == "pack":
            await self._answer_pack(pick, mid)
        else:
            assert pick.node_id is not None
            origin = await run_blocking(self.chats.message, pick.origin)
            if origin is None:
                await self._finish_error(mid, line("failed"))
                return
            request = PlanRequest(text=origin.text, message_id=pick.origin, files_note=self._files_note_of(pick.origin))
            try:
                plan = await self.agent.choice_plan(request, pick.node_id)
                if not await self._carry_out(mid, request, plan):
                    await self._finish_error(mid, line("stale"))
            except ConnectorFailure as exc:
                await self._connector_down(mid, exc)

    async def _answer_pack(self, pick: _Pick, mid: int) -> None:
        """The owner's Yes or No on a suggested practice: Yes puts the pick on the team, No keeps the defaults and is remembered."""
        pack = pack_by_id(pick.pack)
        node = (await run_blocking(self.chart.head)).model.node(pick.node_id or "")
        if pack is None or node is None or pick.node_id is None:
            await self._finish_error(mid, line("failed"))
            return
        rules = StandingRules(self.db, self._redact)
        try:
            await run_blocking(rules.accept if pick.approve else rules.decline, pick.node_id, pack.id)
        except AppError:
            await self._finish_error(mid, line("failed"))
            return
        await self._reply(mid, [line("pack_yes", name=node.name, pack=pack.name) if pick.approve else line("pack_no", name=node.name)])

    def _request_of(self, mid: int, text: str) -> PlanRequest:
        rows = self.chats.last_messages(ORG, self.agent.history + 2, kinds=("text", "error"))
        history = [(m.who, m.text) for m in rows if m.id != mid][-self.agent.history:]
        pending = [f"{c.id}: {c.summary} (waiting for the owner's yes or no)" for c in self.chart.pending()]
        return PlanRequest(text=text, message_id=mid, history=history, pending=pending, files_note=self._files_note_of(mid))

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
        waits = ""
        project_id = ""
        asked_system = False
        if drafts:
            self._phase(mid, "handing_off")
            change_id = applied.result.id if applied is not None else None
            reservation = None
            try:
                if self.projects is not None and len(drafts) >= 2:      # nodes on and two or more steps: a project (D255); one step keeps today's path
                    asked, defaulted = await self.agent.node_plan(request, drafts)       # stage D (D306): the scope and the needs the steps ask for; flag on and two or more steps only
                    reservation = await run_blocking(self._reserve_project, request, drafts, asked, defaulted)
                    if reservation is not None and not reservation.ok:  # the Gatekeeper refused the plan: no node, no task, and the owner is told why
                        raise AppError("validation", reservation.why or "the plan was refused")
                    if reservation is not None:
                        try:
                            if await self.projects.probe_system(reservation.project_id):   # what the computer has allowed, before any task exists (MAN-15): the steps it affects wait, the rest run
                                asked_system = True
                        except Exception:                                           # noqa: BLE001  (a probe that fails for any reason must not leave a reserved project with no tasks; a refusal found late is still caught)
                            log.exception("the permission probe of request %s failed", request.request_id)
                task_ids = await run_blocking(self._create_tasks, request, drafts, change_id, reservation)
                if reservation is not None and reservation.ok and task_ids:
                    project_id = reservation.project_id                                       # D382: the reply ends with the project's address, whichever way the line came in
                if reservation is not None:                                             # every question the owner has to answer is said in plain words, not only the estimate (D308, D317)
                    said = []
                    if reservation.waits is not None:
                        said.append(line("project_waits", title=reservation.title, credits=str(reservation.waits[0]), limit=str(reservation.waits[1])))
                    if reservation.asks:
                        what = " and ".join({"tier": "Reading GitHub", "scope": "Changing files in several places", "sutra_tools": "Reading this app\u2019s own data"}[k] for k in reservation.asks)
                        said.append(line("project_asks", title=reservation.title, what=what))
                    if asked_system:
                        said.append(line("project_system", title=reservation.title))
                    waits = " ".join(said)
            except AppError as exc:
                failure = exc.message
            if task_ids:
                try:
                    await self.tasks.start_ready()
                except Exception:                                           # noqa: BLE001  (a task that cannot start is that task's problem)
                    log.exception("start_ready failed after request %s", request.request_id)
        await run_blocking(self._write_outcome, mid, plan, applied, drafts, task_ids, failure, waits, project_id)
        self._phase(mid, "done")
        await self._call_hook(self.hooks.on_done, mid)

    # ---- approvals -----------------------------------------------------------------------------------------------------

    async def _ask_approval(self, mid: int, plan: Plan, applied: _Applied) -> None:
        question = self._approval_question(plan.change.model if plan.change else None, applied.before)  # type: ignore[union-attr]
        card = {"type": "approval", "change_id": applied.result.id, "question": question,
                "options": [{"id": YES, "label": "Yes"}, {"id": NO, "label": "No"}]}
        adds = _team_adds(plan.change.model if plan.change else None)
        if adds:
            card["adds"] = adds                                                # the owner names each project before it is made (D427)
        impact = await run_blocking(self._impact_of, plan.change.model if plan.change else None, applied.before)
        if impact:
            card["impact"] = impact                                            # what a yes would do, in words; `question` is unchanged
        await run_blocking(self._write_cards, mid, [], [card])
        self._phase(mid, "done")
        await self._call_hook(self.hooks.on_done, mid)

    def _start_folders(self, change: Any, result: ChangeResult, names: dict[str, str], folder: str | None, access: str) -> None:
        """Give every project an applied change started its folder (D427): the chosen one for the first, else `Documents/Sutra Pro/<name>`.
        A folder that cannot be made is logged: the team exists and works in the app-wide folder until the owner picks one."""
        if self.team_folder is None:
            return
        for index, add in enumerate(_team_adds(getattr(change, "model", change))):
            dept_id = result.ids_by_ref.get(add["ref"])
            if not dept_id:
                continue
            try:
                self.team_folder(dept_id, names.get(add["ref"]) or add["name"], folder if index == 0 else None, access)
            except Exception:                                                  # noqa: BLE001 - the team is made; only its folder is missing
                log.exception("could not give the new project %s its folder", dept_id)

    def _impact_of(self, change: Any, before: OrgChart) -> list[str]:
        """The lines of the approval card (reorg_preview.py). A courtesy: a failure here leaves the card as it was, never without it."""
        if change is None:
            return []
        try:
            return card_lines(ReorgPreview(self.db).describe(change, before))
        except Exception:                                                      # noqa: BLE001
            log.exception("could not describe what the change would do")
            return []

    async def _decide_flow(self, change_id: str, approve: bool, mid: int | None, *, raise_already: bool, names: dict[str, str] | None = None,
                           folder: str | None = None, access: str = "edit") -> ChangeResult:
        """Answer a pending change. For a change the chat agent planned, finish its request (stage C if it is still missing, tasks,
        lines and cards). `mid` is the owner's yes/no line to mark done, or None when the answer came from a route."""
        self.chats.set_turn_phase("building")
        stored = await run_blocking(self.chart.record, change_id)
        try:
            result = await run_blocking(lambda: self.chart.decide(change_id, approve, names=names))
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
        await run_blocking(self._start_folders, stored.change, result, names or {}, folder, access)
        if note is None or stored.change is None:
            await self._reply(mid, [])
            return result
        request = self._as_planner(PlanRequest(text=note["text"], message_id=int(note["message_id"]), files_note=self._files_note_of(int(note["message_id"]))))     # a resumed request has its planner node and stop token too (G5, D301)
        decision = ChatDecision.model_validate(note["decision"]) if note.get("decision") else None
        try:
            try:
                plan = await self.agent.resume(request, decision)
            except CallCancelledError:                                    # the owner's Stop ended the planner's running call: no plan is adopted (D301)
                await self._finish_error(mid, line("stopped"))
                return result
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
        finally:
            self._release_planner(request)

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

    def _reserve_project(self, request: PlanRequest, drafts: Sequence[AssignmentDraft], asked: Any = None, defaulted: bool = False) -> Any:
        """The project of a request with two or more steps, made before its tasks (MAN-5): the plan goes through the Gatekeeper's rules, each step gets a node and a frozen grant."""
        from sutra_app.orchestrator.projects import ProjectStep
        asked = asked or {}
        steps = [ProjectStep(ref=d.ref, dept_id=d.dept, depends_on=tuple(r for r in d.depends_on if r != d.ref), scope=asked.get(d.ref, ((), ()))[0], needs=asked.get(d.ref, ((), ()))[1]) for d in drafts]
        title = project_title(request.text)                       # the request's own short title, a whole phrase and not 80 characters cut mid-sentence (D394, D404)
        return self.projects.reserve(request.request_id, title, steps, budget=self._budget_of(request.message_id), planner_node_id=self.projects.planner_id_of(request.request_id),
                                      plan_defaults=defaulted, decide_for_me=self._decide_for_me_of(request.message_id),
                                      failure_policy=self._failure_policy_of(request.message_id), usd=self._usd_budget_of(request.message_id))

    def _create_tasks(self, request: PlanRequest, drafts: Sequence[AssignmentDraft], change_id: str | None, reservation: Any = None) -> list[str]:
        """One transaction per assignment, dependencies first. The owner's words become the first line of the team's chat (the
        engine never echoes them)."""
        made: dict[str, str] = {}
        budget = self._budget_of(request.message_id)
        usd = self._usd_budget_of(request.message_id)
        files = self._files_of(request.message_id)            # D451: every task the request makes is given the files that came with it
        settings = {**({"J2_BUDGET": str(budget)} if budget is not None else {}),      # D252: every task of the request runs with the owner's Budget
                    **({"J2_USD_BUDGET": f"{usd:g}"} if usd is not None else {})} or None      # D423: and with its dollar budget
        if self.projects is not None and self._decide_for_me_of(request.message_id):
            settings = {**(settings or {}), "J2_DECIDE_FOR_ME": "1"}               # Decide for me reaches the workers as their own switch (D294)
        for index, draft in enumerate(drafts, start=1):
            follows = draft.follows
            framing = draft.brief
            if reservation is not None and reservation.ok:                           # a step of a project is told to do its own job only (D414); an ordinary request keeps its framing as it was
                framing = step_framing(draft.brief, index, len(drafts), draft.title, [d.title for d in drafts if d is not draft])
            while True:
                try:
                    with self.db.tx() as tx:
                        task = self.tasks.create(
                            tx, dept_id=draft.dept, text=request.text, title=draft.title, scope_id=draft.scope, framing=framing,
                            depends_on=[made[ref] for ref in draft.depends_on if ref in made], follows=follows,
                            request=request.request_id, change_id=change_id, settings=settings, input_files=files)
                        if reservation is not None and reservation.ok:           # the node and its task become one thing in the transaction that makes the task (MAN-5)
                            self.projects.link_task(tx, reservation, draft.ref, task.id)
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

    def _project_exists(self, project_id: str) -> bool:
        return self.db.conn().execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is not None

    def _write_outcome(self, mid: int, plan: Plan, applied: _Applied | None, drafts: Sequence[AssignmentDraft], task_ids: Sequence[str],
                       failure: str | None, waits: str = "", project_id: str = "") -> None:
        """T8: the template line, the chart card and a task card per task; the request is `ok`. `waits`: the sentence of a project that waits for the owner's OK (D308)."""
        sentences = self._sentences(plan, applied, drafts)
        if waits:
            sentences = sentences + [waits]
        sentences = [_NO_PROJECT_ADDRESS.sub("/p/ ", text) for text in sentences]     # a word of the model's (a title) that looks like a project address is not one (D389, m11)
        if project_id and not self._project_exists(project_id):
            project_id = ""                                                          # only a project that exists is linked, in the reply and on the cards (D389, D408)
        if project_id and failure is None:
            sentences = sentences + [f"You can follow it here: /p/{project_id}"]           # D382: the page shows the address as a link ("Open the project"); only that exact shape
        if failure is not None:
            sentences = [line("task_failed", reason=failure)]
        cards: list[dict] = []
        if applied is not None and applied.result.status == "applied" and plan.change is not None and plan.change.model.kind != "reuse":
            cards.append(self._chart_card(plan.change, applied))
        conn = self.db.conn()
        cards.extend(self._started_cards(conn, applied))
        for task_id in task_ids:
            task = self.tasks.store.out_in(conn, task_id)
            card = {"type": "task", "task_id": task.id, "dept_id": task.dept_id, "dept_name": task.dept_name, "title": task.title, "status": task.status}
            if project_id and failure is None:
                card["project_id"] = project_id                                        # D382: a step's card links to the project's page
            cards.append(card)
        self._write_cards(mid, sentences, cards, error=failure is not None)
        if failure is None:
            self._suggest_packs(applied)

    @staticmethod
    def _started_cards(conn: sqlite3.Connection, applied: _Applied | None) -> list[dict]:
        """One short pointer per department or division this turn made: "Started <name>: open its chat" (GAP3 dept-chats). The team has its own
        chat session since its node was made; the org chat only says so and links to it, it never holds the team's lines."""
        if applied is None or applied.result.status != "applied":
            return []
        out: list[dict] = []
        for node_id in applied.result.added:
            node = applied.after.node(node_id)
            if node is None or node.kind not in ("department", "division"):
                continue
            found = conn.execute("SELECT chat_session_id FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
            if found is None or not found["chat_session_id"]:
                continue
            out.append({"type": "team_chat", "node_id": node_id, "name": node.name, "kind": node.kind, "session_id": found["chat_session_id"],
                        "about": "started"})
        return out

    def _suggest_packs(self, applied: _Applied | None) -> None:
        """After a team was added: one choice card (code only, no model prose) for each added team whose name and purpose fit a practice pick,
        at most two, unless the team already wears one or the owner said no to it. A suggestion never fails the turn."""
        if applied is None or applied.result.status != "applied":
            return
        try:
            packs, rules, made = load_packs(), StandingRules(self.db), 0
            for dept_id in applied.result.added:
                node = applied.after.node(dept_id)
                pack = suggest.suggest_pack(node.name, node.purpose, packs) if node is not None and node.kind == "department" else None
                if node is None or pack is None:
                    continue
                state = rules.get(dept_id)
                if state.pack is not None or pack.id in state.declined:
                    continue
                with self.db.tx() as tx:
                    self._post(tx, kind="card", card=suggest.card_for(node.name, pack), src_ref=suggest.pack_ref(dept_id, pack.id))
                made += 1
                if made == 2:
                    break
        except Exception:                                          # noqa: BLE001
            log.exception("a practice suggestion could not be made")

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
                what = planner.added(op.node.name, op.node.kind)
                out.append(line("add", what=what) if new_id in receiving else line("add_only", what=what))
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

        added = [a["name"] for a in _team_adds(change)]
        if added:
            parts.append(line("approve_add", name=names_phrase(added)))
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


def _team_adds(change: Any) -> list[dict[str, str]]:
    """The projects (departments) a change would start, as `{ref, name}` in op order (D427)."""
    return [{"ref": op.node.ref, "name": op.node.name} for op in (change.ops if change is not None else [])
            if isinstance(op, AddOp) and op.node.kind == "department"]
