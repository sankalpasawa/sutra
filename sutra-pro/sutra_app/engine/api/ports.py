"""What the engine's routes need from the server (engine design 4.9). Defined here and nowhere else (S1-contracts-01).

The orchestrator's `Services` satisfies `EngineServices`; the tests use a fake. The engine never imports the orchestrator, so
the small shapes it reads (`DeptLike`, `RunRefLike`, `DeliveryLike`, `AgentChatTurn` and the busy refusal) are Protocols and a name rule.

One more member of `Services` is OPTIONAL and so is not part of `EngineServices`: `agent_chat(dept_id, run_id, agent) ->
AgentChatTurn | None` (J2 sync 4, D147: the orchestrator's `orchestrator/agent_ask.py`). `POST /api/ask` looks it up with `getattr`: a
`Services` without it (a fake in the engine tests) answers every question from the run's records, and so does a function that has no
chat session of its own for the run (it returns None).
"""
from collections.abc import Callable
from pathlib import Path
from typing import Optional, Protocol

__all__ = ["DeptLike", "RunRefLike", "DeliveryLike", "EngineServices", "AgentChatTurn", "AskFailed", "LIVE_STATUSES", "BUSY_NAMES",
           "is_busy"]

LIVE_STATUSES = ("starting", "running", "waiting_user")      # a task whose process may exist (orchestrator task states)
BUSY_NAMES = ("Busy", "FakeBusy")


class DeptLike(Protocol):
    """Nothing else is read from a department row (S3-web-02, S2-models-14)."""

    id: str
    name: str
    archived: bool          # read as getattr(d, "archived", False): the orchestrator's row may not carry it


class RunRefLike(Protocol):
    run_id: str
    dept_id: str
    dir: str                # relative to the data dir
    status: str


class DeliveryLike(Protocol):
    delivered: str          # "answer" (an inbox line for the waiting task) | "follow_up" (a new task)


class EngineServices(Protocol):
    data_dir: Path
    require_token: Callable         # a FastAPI dependency: header X-Sutra-Token only, plus the Origin check
    redact: Callable[[str], str]    # the orchestrator's port of J2's redact()

    def resolve_run(self, run_id: Optional[str], dept_id: str) -> Optional[RunRefLike]: ...     # run_id wins, else live, else latest
    def deliver_to_department(self, dept_id: str, text: str, *, scope_id: Optional[str] = None,
                              settings: Optional[dict] = None) -> DeliveryLike: ...             # raises Busy
    def stop_live(self, dept_id: str) -> bool: ...          # True: nothing of the team is starting or running afterwards
    def department(self, dept_id: str) -> Optional[DeptLike]: ...


class AskFailed(Exception):
    """What `AgentChatTurn.ask` raises, and only this, when the model side cannot answer: a connector error, no provider, a refused
    allowance, anything the port wraps. `reason` is a short sentence for the owner; the route then answers from the records."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AgentChatTurn(Protocol):
    """One question to one function as a turn of that function's own chat session (D147 to D149). The orchestrator implements it
    (`orchestrator/agent_ask.py`, `AskTurn`); the engine only calls it, in this order and nothing else: `begin`, then, when `can_ask`,
    `ask` (J2's `answer` calls it with the system and user text), then `end` (always, in a `finally`)."""

    session_id: str
    node_id: str
    task_id: str
    run_id: str
    dept_id: str
    agent: str
    can_ask: bool          # False: no model answer is possible now (offline, the owner's limit, no router): `reason` says why, in a sentence
    reason: str

    def begin(self, question: str) -> int:
        """Store the owner's line in the session (scrubbed) and return its id. A question already being answered in this session raises
        the orchestrator's busy error (code `busy`), which `DeptCommands.ask` turns into `views.AskBusy` (409)."""

    def ask(self, system: str, user: str, records_only: Callable[[], str], max_tokens: int = 700, effort: str = "low") -> str:
        """J2's `ask` callable: one short model call made as a call of this session (its own model and effort, booked to it). Raises
        only `AskFailed`."""

    def end(self, answer: Optional[str], source: str) -> dict:
        """`source` is `records` or `model`. With an answer: store the agent's line and return `{session_id, question_id,
        answer_id}`. With None (an unexpected error): store nothing and return `{}`. Either way release the busy mark."""


def is_busy(exc: BaseException) -> bool:
    """The orchestrator's `Busy` (error code 'busy') or a class named like it. `StoreBusy` (a locked database) is not this."""
    if getattr(exc, "code", None) == "busy":
        return True
    return any(cls.__name__ in BUSY_NAMES for cls in type(exc).__mro__)
