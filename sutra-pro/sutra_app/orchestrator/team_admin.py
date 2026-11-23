"""Named projects (D426): the owner makes, renames and hides projects. A project is a team (a department of the one org chart); these are
the owner's own changes, made by code through `ChartStore.apply` with `actor="user"`: no model call, no credits.

    admin = TeamAdmin(db, chart, departments, data_dir, clock, folders=WorkFolder(data_dir, work_root))
    admin.create("Pulse")                         # TeamCreated(team, folder, access): the team, its five agents, its folder
    admin.rename("pulse", "Pulse pilot")          # DepartmentOut, the id kept
    admin.hide("pulse")                           # renamed "Pulse (deleted 23 Nov)", hidden; its runs and files stay (DL5)

Every project has a folder (Q11): the one the owner chose, checked like the app-wide working folder, else `Documents/Sutra Pro/<name>`, made
here with a name every system accepts and never one that already holds files.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sutra_app import oslayer
from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.connectors.workdir import ACCESS, WorkFolder, check_folder
from sutra_app.library.gate import GATE
from sutra_app.library.org_chart import AddOp, ChartChange, ChartChangeRequest, NewNode, RenameOp
from sutra_app.orchestrator.chart_rules import OPEN_STATUSES
from sutra_app.orchestrator.errors import AppError, Busy, NotFound
from sutra_app.orchestrator.models import ChangeContext, DepartmentOut

__all__ = ["TeamAdmin", "TeamCreated", "clean_name", "folder_name", "deleted_name", "team_admin_of", "NAME_CHARS", "HOME_FOLDER"]

log = logging.getLogger(__name__)
NAME_CHARS = 80                                  # the chart's own limit on a node name (library/org_chart.py Name)
HOME_FOLDER = "Sutra Pro"                        # under Documents: where a project with no chosen folder keeps its work
OWNER_TASK = "owner-teams"                       # the request id of the owner's own team changes (chart_changes.task_id)
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_DEVICE = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", re.IGNORECASE)


@dataclass(frozen=True)
class TeamCreated:
    team: DepartmentOut
    folder: str
    access: str


def clean_name(raw: Any) -> str:
    """The name as the owner typed it, whitespace collapsed; a blank or too long one is the 422 the box shows under the name field."""
    name = " ".join(raw.split()) if isinstance(raw, str) else ""
    if not name:
        raise AppError("validation", "Give the project a name", {"field": "name"})
    if len(name) > NAME_CHARS:
        raise AppError("validation", f"Keep the project name to {NAME_CHARS} characters", {"field": "name"})
    return name


def name_key(name: str) -> str:
    """What two project names are compared by: case and spaces do not count (the library's sibling rule, library/org_chart.py)."""
    return "".join(unicodedata.normalize("NFKC", name).split()).casefold()


def folder_name(name: str, taken: Callable[[str], bool]) -> str:
    """A folder name for `name` that every system accepts: the characters Windows refuses become `-`, trailing dots and spaces go, a device
    name (CON, LPT1, ...) or nothing at all becomes "Project"; then " 2", " 3", ... while `taken` says the name is in use."""
    base = _UNSAFE.sub("-", name).rstrip(". ").strip()
    if not base or _DEVICE.fullmatch(base):
        base = "Project"
    found, n = base, 1
    while taken(found):
        n += 1
        found = f"{base} {n}"
    return found


def deleted_name(name: str, today: date) -> str:
    """The name a hidden team gets so its own name is free again: "Pulse (deleted 23 Nov)", cut to the chart's 80 characters."""
    tail = f" (deleted {today.day} {today:%b})"
    return name[:NAME_CHARS - len(tail)].rstrip() + tail


class TeamAdmin:
    """The owner's team changes. `documents` is where `Sutra Pro/<name>` folders are made (default: the system's Documents folder)."""

    def __init__(self, db: Any, chart: Any, departments: Any, data_dir: str | Path, clock: Any, *, folders: WorkFolder,
                 documents: Path | None = None) -> None:
        self.db, self.chart, self.departments, self.clock, self.folders = db, chart, departments, clock, folders
        self.data_dir = Path(data_dir)
        self.documents = Path(documents) if documents is not None else oslayer.documents_dir()

    @classmethod
    def of(cls, services: Any) -> "TeamAdmin":
        """The admin of a running app, from its stores; the folder store is the connectors' own when there is one (its work root)."""
        router = getattr(services, "connector", None)
        folders = getattr(router, "folders", None)
        if not isinstance(folders, WorkFolder):
            from sutra_app.connectors.models import ConnectorConfig
            folders = WorkFolder(services.data_dir, ConnectorConfig(data_dir=services.data_dir).resolved_work_root())
        return cls(services.db, services.chart, services.departments, services.data_dir, services.clock, folders=folders)

    # ---- names ------------------------------------------------------------------------------------------------------------------

    def name_problem(self, name: str, *, except_id: str | None = None) -> str | None:
        """The sentence when a visible project already has this name (case and spaces ignored), else None."""
        key = name_key(name)
        for team in self.departments.listing():
            if team.id != except_id and name_key(team.name) == key:
                return f"A project called {team.name} already exists"
        return None

    def _need_free(self, name: str, *, except_id: str | None = None) -> None:
        problem = self.name_problem(name, except_id=except_id)
        if problem:
            raise AppError("name_taken", problem, {"field": "name"})

    # ---- create -----------------------------------------------------------------------------------------------------------------

    def create(self, name: Any, folder: str | None = None, access: str = "edit") -> TeamCreated:
        """Make the team (its five function agents, its home folder and page, through the chart) and its project folder."""
        clean = clean_name(name)
        self._need_free(clean)
        access = self._access(access)
        chosen = self._check(folder) if folder else None
        made = None if chosen else self._make_default(clean)
        try:
            dept_id = self._add(clean)
        except BaseException:
            if made is not None:
                _remove_if_empty(made)
            raise
        stored = self.ensure_folder(dept_id, clean, chosen or str(made), access)
        return TeamCreated(team=self.departments.get(dept_id), folder=stored, access=access)

    def ensure_folder(self, dept_id: str, name: str, folder: str | None, access: str = "edit") -> str:
        """Store the team's folder: the chosen one (checked), else a new `Documents/Sutra Pro/<name>`. Returns the stored path."""
        access = self._access(access)
        target = self._check(folder) if folder else str(self._make_default(name))
        try:
            return self.folders.for_team(dept_id).set(target, access=access)
        except InvalidRequestError as exc:
            raise AppError("validation", exc.user_message(), {"field": "folder"}) from None

    def _add(self, name: str) -> str:
        """Apply one AddOp of a department under the root as the owner; the new id. A chart that moved on is read again once."""
        for attempt in (1, 2):
            head = self.chart.head().model
            request = ChartChangeRequest(reason=f"The owner made the project {name}",
                                         ops=[AddOp(node=NewNode(ref="$p", kind="department", name=name, parent="root"))])
            change = GATE.check("chart_change", ChartChange.from_request(request, id=self.chart.next_change_id(), task_id=OWNER_TASK,
                                                                         base_revision=head.revision))
            result = self.chart.apply(change, actor="user", ctx=self._ctx(f"New project {name}"))
            if result.status == "applied":
                return result.ids_by_ref["$p"]
            if result.status != "stale" or attempt == 2:
                raise AppError("stale_chart", "The projects changed while this was made. Try again.")
        raise AssertionError("unreachable")

    # ---- rename and hide --------------------------------------------------------------------------------------------------------

    def rename(self, dept_id: str, name: Any) -> DepartmentOut:
        clean = clean_name(name)
        self._visible(dept_id)
        self._need_free(clean, except_id=dept_id)
        self._rename(dept_id, clean)
        return self.departments.get(dept_id)

    def hide(self, dept_id: str) -> None:
        """Delete a project for the owner: refused while it works; else renamed "<name> (deleted <d Mon>)" and hidden. Nothing on disk goes."""
        team = self._visible(dept_id)
        marks = ",".join("?" * len(OPEN_STATUSES))
        working = self.db.conn().execute(f"SELECT 1 FROM tasks WHERE dept_id = ? AND status IN ({marks}) LIMIT 1", (dept_id, *OPEN_STATUSES)).fetchone()
        if working is not None:
            raise Busy(f"{team.name} is working. Stop it first.")
        base = deleted_name(team.name, datetime.fromtimestamp(self.clock.now()).date())
        taken = {name_key(r[0]) for r in self.db.conn().execute("SELECT name FROM org_nodes WHERE kind = 'department' AND id != ?", (dept_id,))}
        hidden, n = base, 1
        while name_key(hidden) in taken:
            n += 1
            hidden = f"{base[:NAME_CHARS - len(str(n)) - 1]} {n}"
        self._rename(dept_id, hidden)
        with self.db.tx() as tx:
            tx.conn.execute("UPDATE departments SET hidden_at = ? WHERE id = ?", (tx.now(), dept_id))

    def _rename(self, dept_id: str, name: str) -> None:
        for attempt in (1, 2):
            head = self.chart.head().model
            request = ChartChangeRequest(reason=f"The owner renamed a project to {name}", ops=[RenameOp(node=dept_id, name=name)])
            change = GATE.check("chart_change", ChartChange.from_request(request, id=self.chart.next_change_id(), task_id=OWNER_TASK,
                                                                         base_revision=head.revision))
            result = self.chart.apply(change, actor="user", ctx=self._ctx(f"Rename to {name}"))
            if result.status == "applied":
                return
            if result.status != "stale" or attempt == 2:
                raise AppError("stale_chart", "The projects changed while this was saved. Try again.")

    # ---- the last project picked on Attention (R1.9) ---------------------------------------------------------------------------
    # Kept on the server next to the sidebar sections (`ui/`): a browser's storage belongs to one port, and the app's port can change.

    @property
    def _last_path(self) -> Path:
        return self.data_dir / "ui" / "last_project.json"

    def last_pick(self) -> str:
        """The project last picked on Attention, "" for "Let Sutra choose" (also when it was deleted since, or the file does not read)."""
        try:
            dept = json.loads(self._last_path.read_text(encoding="utf-8")).get("dept", "")
        except (OSError, ValueError, AttributeError):
            return ""
        row = self.departments.row(dept) if isinstance(dept, str) and dept else None
        return dept if row is not None and not row.archived else ""

    def set_last_pick(self, dept: str) -> str:
        """Keep the pick ("" = Let Sutra choose); a project that is not there is the 404."""
        if dept:
            self._visible(dept)
        folder = self._last_path.parent
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{self._last_path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"version": 1, "dept": dept}) + "\n")
            oslayer.replace(tmp, self._last_path)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        return dept

    # ---- helpers ----------------------------------------------------------------------------------------------------------------

    def _visible(self, dept_id: str) -> DepartmentOut:
        row = self.departments.row(dept_id)
        if row is None or row.archived:
            raise NotFound("that project")
        return self.departments.get(dept_id)

    def _ctx(self, title: str) -> ChangeContext:
        return ChangeContext(session_id="cs_org", request_id=OWNER_TASK, request_title=title[:NAME_CHARS])

    @staticmethod
    def _access(access: Any) -> str:
        if access not in ACCESS:
            raise AppError("validation", "Choose read and edit, or read only", {"field": "access"})
        return access

    def _claimed_folders(self) -> set[str]:
        """Every folder a team (a deleted one too) stores as its own: a new project never shares one, even an empty one."""
        found: set[str] = set()
        for stored in (self.data_dir / "departments").glob("*/workdir.json"):
            try:
                path = json.loads(stored.read_text(encoding="utf-8")).get("path")
            except (OSError, ValueError, AttributeError):
                continue
            if isinstance(path, str) and path:
                found.add(os.path.realpath(path))
        return found

    def check_folder(self, folder: str) -> str:
        """The chosen folder, checked like the app-wide working folder; the 422 `folder` when it cannot be used."""
        return self._check(folder)

    def _check(self, folder: str) -> str:
        try:
            return check_folder(folder, data_dir=self.folders.data_dir, work_root=self.folders.work_root)
        except InvalidRequestError as exc:
            raise AppError("validation", exc.user_message(), {"field": "folder"}) from None

    def _make_default(self, name: str) -> Path:
        home = self.documents / HOME_FOLDER
        home.mkdir(parents=True, exist_ok=True)
        claimed = self._claimed_folders()
        target = home / folder_name(name, lambda candidate: _in_use(home / candidate) or os.path.realpath(home / candidate) in claimed)
        target.mkdir(parents=False, exist_ok=True)
        return target


def team_admin_of(services: Any) -> TeamAdmin:
    """The app's one TeamAdmin, made from its stores on first use (a test sets `services.team_admin` itself)."""
    if getattr(services, "team_admin", None) is None:
        services.team_admin = TeamAdmin.of(services)
    return services.team_admin


def _in_use(path: Path) -> bool:
    """A folder name is in use when something is there that is not an empty folder (an old project's work is never written over)."""
    if not path.exists():
        return False
    try:
        return not path.is_dir() or any(path.iterdir())
    except OSError:
        return True


def _remove_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        log.info("left the project folder %s in place", path)

