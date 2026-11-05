"""`Services`: the one object the routes, the engine plug-in and the UI plug-in are given (orchestrator 3.4, 3.5).

It carries what the plug-ins read by name (`engine.md` 4.9, `ui.md` 4.1): `settings`, `version`, `data_dir`, `require_token`,
`redact`, `resolve_run`, `department`, `deliver_to_department` and `stop_live`. There is ONE department lookup,
`department(dept_id) -> DeptRow | None`; there is no `lookup_dept`. The stores are slots (`bus`, `chats`, `atoms`, ...) that
`wiring.build_services` (ORCH-8) fills as the packages that own them land; `missing()` says which are still empty, and
`need()` fetches one or fails with its name.
"""
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from sutra_app.config import Settings
from sutra_app.orchestrator.api.deps import require_token
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.ids import Clock, IdFactory, SystemClock
from sutra_app.orchestrator.models import DeptRow

__all__ = ["Services", "STORE_SLOTS", "CALLABLE_SLOTS"]

STORE_SLOTS = (
    "bus", "chats", "atoms", "usage", "graph", "chart", "departments", "tasks", "projector", "watcher", "runner", "connector",
    "launcher",
)
CALLABLE_SLOTS = ("resolve_run", "department", "deliver_to_department", "stop_live")


@dataclass
class Services:
    settings: Settings
    version: str
    db: Database
    redact: Callable[[str], str]
    clock: Clock = field(default_factory=SystemClock)
    ids: IdFactory | None = None
    require_token: Callable[..., Any] = require_token
    # the stores and workers, filled by wiring.build_services
    bus: Any = None
    chats: Any = None
    atoms: Any = None
    usage: Any = None
    graph: Any = None
    chart: Any = None
    departments: Any = None
    tasks: Any = None
    projector: Any = None
    watcher: Any = None
    runner: Any = None
    connector: Any = None
    launcher: Any = None
    # what the engine plug-in calls (resolve_run(run_id, dept_id), deliver_to_department(dept_id, text, ...), stop_live(dept_id))
    resolve_run: Callable[..., Any] | None = None
    department: Callable[[str], DeptRow | None] | None = None
    deliver_to_department: Callable[..., Any] | None = None
    stop_live: Callable[[str], bool] | None = None

    def __post_init__(self) -> None:
        if self.ids is None:
            self.ids = IdFactory(self.clock)

    @property
    def data_dir(self) -> Path:
        return self.settings.data_dir

    def missing(self) -> list[str]:
        """The slots nobody has filled yet, in declaration order."""
        names = {f.name for f in fields(self)}
        return [name for name in (*STORE_SLOTS, *CALLABLE_SLOTS) if name in names and getattr(self, name) is None]

    def need(self, name: str) -> Any:
        """A slot's value, or a RuntimeError that names the slot when it was never wired."""
        if name not in {f.name for f in fields(self)}:
            raise KeyError(name)
        value = getattr(self, name)
        if value is None:
            raise RuntimeError(f"Services.{name} is not wired")
        return value
