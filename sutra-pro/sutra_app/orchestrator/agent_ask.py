"""A function's model-backed answer is a turn of ITS OWN agent session (J2 sync 4, D147 to D149; owner rule R2).

The owner asks one of J2's functions a question about a run (`POST /api/ask {who, q, run}`). The engine's route is J2's `j2_agent.answer`, unchanged; what it
needs from the server is a turn of that function's chat session, and this module is that port. The engine reaches it only through `services.agent_chat`
(optional: `engine/api/ports.AgentChatTurn`); a `Services` without it, and a function that has no session of its own in the run, answer from the records.

    asking = AgentAsk(db=..., tasks=..., chats=..., router=..., chat_port=..., limits=..., redact=...)        # `services.agent_chat` is `asking.turn`
    turn = asking.turn(dept_id, run_id, "audit")       # None: the function has no session of its own for that run (it never worked in it), or it is the validator
    turn.begin(question)                                # the owner's line in the function's session, scrubbed; one question at a time per session (409 busy)
    text = turn.ask(system, user, records_only)         # J2's `ask` callable: one call of the server's Router, as a call of THAT session
    turn.end(answer, "model")                           # the function's line; {session_id, question_id, answer_id}; always called, in a `finally`

What makes the call a turn of the session and not a side path:

  * its own pick: the function's session resolves own, then run, then team (`agent_sessions.effective`); that pick travels in `RouteContext.pick`, so the router
    sends the call to that provider with that model and effort (a session id no longer costs the call its pick). When nobody chose (`default`) no pick is
    passed: the policy decides, and no "your choice could not run" note is made;
  * scrubbed: the records of a run can hold a secret the owner pasted, and this prompt is Sutra's turn, not J2's: the system and user text go through the app's
    secret values and the credential shapes before the call, with the egress audit row in replace mode (J2's own prompts are only observed);
  * limited: at most 2 calls (one retry), $0.25 and 120 seconds in all; the owner's monthly limit and plan window (`Limits.gate`) hold it back, and so does a
    router with no model (offline, `SUTRA_CONNECTOR=stub`, no router in a test app): `can_ask` is False and `reason` says why, and the answer is from the records;
  * booked: the usage row carries the session, the node, the function, the purpose `agent_chat` and the run's overhead atom (an answer is overhead: D59), so it
    shows under the function's usage and keeps the session's model chip current, exactly like the function's own calls.

The question is a `user` line of the session with `src_ref` `ask:<id>` and the answer an `agent` line (`who` = the function) with `ask:<id>:records` or
`ask:<id>:model`; `ChatMessageOut.ask` reads the part from it (chats.py). They are stored in the session of the run asked about, an archived one included (a past
run's chat is its record). The session stays read-only for everyone else: only this port writes these lines, and the engine is never given them (a note steers an
agent, a question does not).
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Any, Callable

from sutra_app.connectors.egress import scrubbed
from sutra_app.connectors.errors import ConnectorError
from sutra_app.connectors.models import Allowance, AskRequest, CallTag, Pick, RouteContext
from sutra_app.library.gate import GATE
from sutra_app.library.types import FUNCTIONS, clip, overhead_atom_id
from sutra_app.orchestrator.agent_sessions import effective
from sutra_app.orchestrator.chats import ASK_REF
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.ids import SystemClock
from sutra_app.orchestrator.records import ChatMessage

__all__ = ["AgentAsk", "AskTurn", "ASK_REF", "ASK_MAX_CALLS", "ASK_MAX_USD", "ASK_TIMEOUT_S", "NO_MODEL", "BUSY_TEXT"]

log = logging.getLogger(__name__)

ASK_MAX_CALLS, ASK_MAX_USD, ASK_TIMEOUT_S = 2, 0.25, 120.0       # one retry at most; a ceiling, not a budget; a whole answer is one short call
NO_MODEL = "No model is connected."
BUSY_TEXT = "This agent is still answering your last question. Ask again when it has answered."
LINE_CHARS = 100_000                                              # a stored line is cut here (the record allows 200,000): a long answer is stored, never refused
REASON_CHARS = 300
SOURCES = ("records", "model")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PICK_SOURCES = ("own", "run", "team")                             # where a pick of the owner can come from; `default` is the policy's own answer, not a choice

_SESSION = ("SELECT s.id, s.node_id, s.status FROM chat_sessions s JOIN graph_nodes g ON g.id = s.node_id "
            "WHERE s.kind = 'function' AND s.run_id = ? AND g.department_id = ? AND g.kind = ? "
            "ORDER BY s.created_at DESC, s.rowid DESC LIMIT 1")


def _failed(reason: str) -> Exception:
    """The refusal the route catches: `engine/api/ports.AskFailed`. It is imported where it is raised because the engine's API package pulls in J2 and the
    orchestrator must not (the engine never imports the orchestrator, and this module is imported by `wiring`)."""
    from sutra_app.engine.api.ports import AskFailed
    return AskFailed(reason)


def _reason(exc: BaseException, redact: Callable[[str], str] | None) -> str:
    """A short sentence for the owner from whatever the model side raised: the connector's own plain words; for anything else the error's name and text (a
    bug, not a refusal, so it is named). No secret, no line breaks, at most REASON_CHARS."""
    if isinstance(exc, ConnectorError):
        said = exc.user_message()
    else:
        said = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    return clip(" ".join(scrubbed(said, redact).split()), REASON_CHARS) or "the model side failed"


class AgentAsk:
    """The port: `turn(dept_id, run_id, agent)` is what `services.agent_chat` is. Holds the one-question-per-session mark, so it is made once and shared."""

    def __init__(self, *, db: Any, tasks: Any, chats: Any, router: Any, chat_port: Any, limits: Any, redact: Callable[[str], str] | None,
                 ids: Any = None, clock: Any = None) -> None:
        self.db = db
        self.tasks = tasks                    # resolve_run(run_id, dept_id): the run must be one of the team's
        self.chats = chats
        self.router = router                  # the server's connector Router; None in a test app that has none
        self.chat_port = chat_port            # the policy default of an agent (`default_pick`), the last step of the pick's cascade
        self.limits = limits                  # the owner's monthly limit and plan window (`gate`)
        self.redact = redact
        self.ids = ids                        # when given, a question's token comes from its session ids: deterministic under FakeIds; else random
        self._clock = clock if clock is not None else SystemClock()
        self._lock = threading.Lock()
        self._running: set[str] = set()       # the sessions with a question in flight: one at a time

    # ---- the turn ------------------------------------------------------------------------------------------------------------------

    def turn(self, dept_id: str, run_id: str | None, agent: str) -> "AskTurn | None":
        """The function's turn for that run, or None: the agent is not one of the five functions (the validator is code, a builder is not offered), the run is not
        one of the team's, or the function has no session stamped with that run (it never worked in it). An archived session counts."""
        if agent not in FUNCTIONS or not run_id or not dept_id or self.tasks is None:
            return None
        ref = self.tasks.resolve_run(run_id, dept_id)
        if ref is None:
            return None
        conn = self.db.conn()
        found = conn.execute(_SESSION, (ref.run_id, dept_id, agent)).fetchone()
        if found is None:
            return None
        can_ask, reason = self._can_ask(conn, dept_id)
        return AskTurn(self, session_id=found["id"], node_id=found["node_id"], task_id=ref.task_id, run_id=ref.run_id, dept_id=dept_id, agent=agent,
                       can_ask=can_ask, reason=reason)

    def _can_ask(self, conn: Any, dept_id: str) -> tuple[bool, str]:
        """Whether a model may answer now, and when not, the sentence the owner reads: no model (offline, the stub, no router or no chat port), or the owner's
        limit or plan window is reached (the gate's own words). Never raises."""
        router = self.router
        if router is None or self.chat_port is None or getattr(router, "mode", "offline") == "offline":
            return False, NO_MODEL
        held = self.limits.gate(conn, self._clock.now(), dept_id) if self.limits is not None else ""
        return (False, held) if held else (True, "")

    # ---- one question at a time per session ---------------------------------------------------------------------------------------------

    def _hold(self, turn: "AskTurn") -> None:
        with self._lock:
            if turn._held or turn.session_id in self._running:
                raise AppError("busy", BUSY_TEXT)
            self._running.add(turn.session_id)
            turn._held = True

    def _release(self, turn: "AskTurn") -> None:
        with self._lock:
            if turn._held:
                self._running.discard(turn.session_id)
                turn._held = False

    def asking(self, session_id: str) -> bool:
        """Whether a question is being answered in this session now."""
        with self._lock:
            return session_id in self._running

    def _token(self) -> str:
        """The part of `src_ref` that pairs a question with its answer: 12 hex digits no other question of the session has."""
        if self.ids is not None:
            return str(self.ids.session_id()).removeprefix("cs_")
        return secrets.token_hex(6)

    # ---- the two lines -----------------------------------------------------------------------------------------------------------------------

    def _post(self, turn: "AskTurn", *, role: str, who: str, text: str, src_ref: str) -> Any:
        """One line of the function's session, through the gate, in its own transaction (`chat.message` goes out when it commits)."""
        with self.db.tx() as tx:
            checked = GATE.check("chat_message", ChatMessage(
                kind="text", session_id=turn.session_id, role=role, who=who, text=clip(text, LINE_CHARS), src_ref=src_ref, task_id=turn.task_id, at=tx.now()),
                ctx=tx.ctx)
            return self.chats.post(tx, turn.session_id, checked)

    # ---- the model call ----------------------------------------------------------------------------------------------------------------------

    def _pick(self, turn: "AskTurn") -> Pick | None:
        """The owner's pick for this function in this run: its own session's, else the run's, else the team's. None when nobody chose (the policy decides)."""
        default = getattr(self.chat_port, "default_pick", None)
        try:
            found = effective(self.db.conn(), turn.session_id, default if callable(default) else None)
            if found.get("source") in PICK_SOURCES and found.get("provider"):
                return Pick(provider=found["provider"], model=found.get("model"), effort=found.get("effort"))
        except Exception:                                    # noqa: BLE001  (an unreadable pick is no reason to refuse a question: the policy answers)
            log.warning("could not read the pick of %s (session %s)", turn.agent, turn.session_id, exc_info=True)
        return None

    def _scrub_user(self, text: str, turn: "AskTurn", pick: Pick | None, system: str) -> str:
        """The records and the question as the model gets them: the egress scrub in replace mode (its audit row says what was replaced, never what it was), then
        the app's secret values and the credential shapes once more, so a router without an egress is no gap."""
        egress = getattr(self.router, "egress", None)
        if egress is not None:
            try:
                text = egress.check(text, session=turn.session_id, provider=pick.provider if pick is not None else "-", replace=True, system=system)
            except Exception:                                # noqa: BLE001  (an audit row that cannot be written must not let the text go unscrubbed)
                log.warning("the egress check failed for %s; the text is scrubbed without it", turn.session_id, exc_info=True)
        return scrubbed(text, self.redact)

    def _router_now(self) -> float:
        return float(getattr(self.router, "_clock", time.time)())          # the deadline is in the router's own time

    def _ask(self, turn: "AskTurn", system: str, user: str, records_only: Callable[[], str] | None, effort: str) -> str:
        """One call of the server's Router as a call of the function's session (the module docstring says how). Raises only `AskFailed`."""
        try:
            pick = self._pick(turn)
            system = scrubbed(system, self.redact)
            user = self._scrub_user(user, turn, pick, system)
            request = AskRequest(
                system=system, user=user, kind="text", effort=effort if effort in EFFORTS else "low", timeout_s=ASK_TIMEOUT_S,
                scripted=records_only if callable(records_only) else None,
                ctx=RouteContext(
                    tag=CallTag(function=turn.agent, purpose="agent_chat", run_id=turn.run_id, dept_id=turn.dept_id, task_id=turn.task_id,
                                atom=overhead_atom_id(turn.run_id), workspace="none"),
                    session_id=turn.session_id, node_id=turn.node_id,
                    allowance=Allowance(max_calls=ASK_MAX_CALLS, max_usd=ASK_MAX_USD, deadline=self._router_now() + ASK_TIMEOUT_S), pick=pick))
            text = (self.router.ask(request).text or "").strip()
        except Exception as exc:                             # noqa: BLE001  (a connector error, no provider, a refused allowance: every one is the route's fallback)
            reason = _reason(exc, self.redact)
            log.info("the model could not answer %s (session %s): %s", turn.agent, turn.session_id, reason)
            raise _failed(reason) from exc
        if not text:
            raise _failed("the model returned no text")
        return text


class AskTurn:
    """One question to one function: its session of the run, and the three steps the route takes (`begin`, `ask`, `end`). Made by `AgentAsk.turn`."""

    def __init__(self, owner: AgentAsk, *, session_id: str, node_id: str, task_id: str, run_id: str, dept_id: str, agent: str,
                 can_ask: bool, reason: str) -> None:
        self._owner = owner
        self.session_id, self.node_id, self.task_id, self.run_id, self.dept_id, self.agent = session_id, node_id, task_id, run_id, dept_id, agent
        self.can_ask, self.reason = can_ask, reason
        self._held = False                                   # this turn holds its session's one-question mark
        self._token: str | None = None
        self._question_id: int | None = None
        self._stored: dict[str, Any] | None = None

    def begin(self, question: str) -> int:
        """Store the owner's line (scrubbed) in the function's session and return its id. A second question while this session is answering one raises
        `AppError("busy")`, which the route answers with 409; nothing is stored then."""
        owner = self._owner
        text = scrubbed(str(question or ""), owner.redact).strip()
        if not text:
            raise AppError("validation", "The question is empty.")
        owner._hold(self)
        try:
            token = owner._token()
            posted = owner._post(self, role="user", who="user", text=text, src_ref=f"{ASK_REF}{token}")
            if posted is None:                               # the same src_ref twice in a session: a token that was used before
                raise AppError("internal", "The question could not be stored.")
        except BaseException:
            owner._release(self)
            raise
        self._token, self._question_id = token, posted.id
        return posted.id

    def ask(self, system: str, user: str, records_only: Callable[[], str] | None = None, max_tokens: int = 700, effort: str = "low") -> str:
        """J2's `ask` callable. One short model call as a call of this session; `max_tokens` is J2's and has no field here (the CLIs take none: the shortness
        is in J2's prompt). Raises only `AskFailed`, and never when `can_ask` is False: it refuses then, so no path can call a model offline."""
        if not self.can_ask:
            raise _failed(self.reason or NO_MODEL)
        return self._owner._ask(self, str(system or ""), str(user or ""), records_only, effort)

    def end(self, answer: str | None, source: str) -> dict[str, Any]:
        """Store the function's line (`source` is `records` or `model`) and return `{session_id, question_id, answer_id}`. With no answer (None, or nothing
        to say) nothing is stored and `{}` comes back. Either way the session's mark is released, so this is the one call in the route's `finally`. Called
        again after an answer it stored, it returns the same ids and stores nothing."""
        owner = self._owner
        try:
            if self._token is None or answer is None:
                return {}
            if self._stored is not None:
                return dict(self._stored)
            if source not in SOURCES:
                raise ValueError(f"an answer is from the records or from a model, not {source!r}")
            text = scrubbed(str(answer), owner.redact).strip()
            if not text:
                return {}
            posted = owner._post(self, role="agent", who=self.agent, text=text, src_ref=f"{ASK_REF}{self._token}:{source}")
            if posted is None:
                raise AppError("internal", "The answer could not be stored.")
            self._stored = {"session_id": self.session_id, "question_id": self._question_id, "answer_id": posted.id}
            return dict(self._stored)
        finally:
            owner._release(self)
