"""What the engine's routes need from the server (engine design 4.9). Defined here and nowhere else (S1-contracts-01).

The orchestrator's `Services` satisfies `EngineServices`; the tests use a fake. The engine never imports the orchestrator, so
the four small shapes it reads (`DeptLike`, `RunRefLike`, `DeliveryLike` and the busy refusal) are Protocols and a name rule.
"""
from collections.abc import Callable
from pathlib import Path
from typing import Optional, Protocol

__all__ = ["DeptLike", "RunRefLike", "DeliveryLike", "EngineServices", "LIVE_STATUSES", "BUSY_NAMES", "is_busy"]

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


def is_busy(exc: BaseException) -> bool:
    """The orchestrator's `Busy` (error code 'busy') or a class named like it. `StoreBusy` (a locked database) is not this."""
    if getattr(exc, "code", None) == "busy":
        return True
    return any(cls.__name__ in BUSY_NAMES for cls in type(exc).__mro__)
