"""Departments (orchestrator 3.4, 4.1, 4.2, 6.2; D48, S3-web-02, S2-models-14, S1-contracts-03).

    departments = DepartmentStore(db, data_dir)
    departments.row("web")            # DeptRow | None: what `Services.department` returns (None for an unknown or malformed id)
    departments.listing() / .get("web")  # DepartmentOut: name and purpose from the chart, live task, node state, session, five function chips
    departments.runs("web")           # RunRef[], newest first (the tasks that have a run folder)
    departments.sweep()               # remove empty departments/<id> folders that have no row; returns how many
    departments.problems()            # invariant I4: every live department has its row, five function nodes and its home folder
    departments.write_mirror("web")   # departments/<id>/department.json, a mirror for humans (best effort, never authoritative)

A department is made by `ChartStore.apply` (the `departments` row and the `Department` record in the same transaction as the
chart revision that adds it) and by nothing else. It is never archived, moved or merged (DL5), so `DeptRow.archived` is False and
`merged_into_name` is empty. The charter is the run folder's `goal.json` (D65): no table copies it.
"""
import json
import logging
import os
from sutra_app import oslayer
import re
import shutil
import sqlite3
from pathlib import Path

from sutra_app.engine.spec import DEPT_ID_RE
from sutra_app.library.types import FUNCTIONS, function_node_id
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import LIVE_STATUSES, DepartmentOut, DeptRow, FunctionChip, RunRef

__all__ = ["DepartmentStore", "ENGINE_OWNED", "MIRROR_NAME"]

log = logging.getLogger(__name__)
ENGINE_OWNED = ("engine.json", "page.json", "memory")      # a folder that holds one of these is the engine's: sweep never touches it
MIRROR_NAME = "department.json"
_DEPT_ID = re.compile(DEPT_ID_RE)


class DepartmentStore:
    """Reads departments as the wire shows them, sweeps orphaned folders and keeps the human-readable mirror."""

    def __init__(self, db: Database, data_dir: str | os.PathLike[str]) -> None:
        self._db = db
        self._data_dir = Path(data_dir)

    @property
    def departments_dir(self) -> Path:
        return self._data_dir / "departments"

    # ---- reads ------------------------------------------------------------------------------------------------------

    def row(self, dept_id: str) -> DeptRow | None:
        """`Services.department`: the department with its chart name, or None. A department is never archived or merged."""
        if not isinstance(dept_id, str) or not _DEPT_ID.fullmatch(dept_id):
            return None
        found = self._db.conn().execute(
            "SELECT d.id, o.name FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone()
        return DeptRow(id=found["id"], name=found["name"]) if found is not None else None

    def listing(self) -> list[DepartmentOut]:
        """Every department in chart order (by position under the root)."""
        with self._db.read() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT d.id FROM departments d JOIN org_edges e ON e.child_id = d.id AND e.parent_id = 'root'"
                " JOIN org_nodes o ON o.id = d.id WHERE o.state = 'active' ORDER BY e.position, d.id")]
            return [self._out(conn, dept_id) for dept_id in ids]

    def get(self, dept_id: str) -> DepartmentOut:
        with self._db.read() as conn:
            if self.row(dept_id) is None:
                raise NotFound("that team")
            return self._out(conn, dept_id)

    def runs(self, dept_id: str) -> list[RunRef]:
        """The department's runs, newest first: every task that has a run id, with its folder relative to the data dir."""
        with self._db.read() as conn:
            home = conn.execute("SELECT home_dir FROM departments WHERE id = ?", (dept_id,)).fetchone()
            if home is None:
                raise NotFound("that team")
            rows = conn.execute(
                "SELECT id, run_id, status, pid, started_at, ended_at FROM tasks WHERE dept_id = ? AND run_id IS NOT NULL"
                " ORDER BY created_at DESC, rowid DESC", (dept_id,)).fetchall()
            return [RunRef(
                run_id=r["run_id"], task_id=r["id"], dept_id=dept_id, dir=f"{home['home_dir']}/runs/{r['run_id']}", status=r["status"],
                pid=r["pid"], started_at=iso_z(r["started_at"]) if r["started_at"] is not None else None,
                ended_at=iso_z(r["ended_at"]) if r["ended_at"] is not None else None) for r in rows]

    def _out(self, conn: sqlite3.Connection, dept_id: str) -> DepartmentOut:
        node = conn.execute("SELECT name, purpose FROM org_nodes WHERE id = ?", (dept_id,)).fetchone()
        graph = conn.execute("SELECT state, chat_session_id FROM graph_nodes WHERE id = ?", (dept_id,)).fetchone()
        marks = ",".join("?" * len(LIVE_STATUSES))
        live = conn.execute(
            f"SELECT id FROM tasks WHERE dept_id = ? AND status IN ({marks}) ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (dept_id, *LIVE_STATUSES)).fetchone()
        chips: list[FunctionChip] = []
        for fn in FUNCTIONS:
            found = conn.execute("SELECT state, chat_session_id FROM graph_nodes WHERE id = ?", (function_node_id(dept_id, fn),)).fetchone()
            if found is not None:
                chips.append(FunctionChip(id=function_node_id(dept_id, fn), fn=fn, status=found["state"], chat_session_id=found["chat_session_id"]))
        return DepartmentOut(
            id=dept_id, name=node["name"], purpose=node["purpose"], node_status=graph["state"] if graph is not None else "idle",
            live_task_id=live["id"] if live is not None else None, session_id=graph["chat_session_id"] if graph is not None else None,
            functions=chips)

    # ---- invariant I4 ------------------------------------------------------------------------------------------------

    def problems(self) -> list[str]:
        """What breaks invariant I4: a live department without its `departments` row, its five function nodes (in the graph) or its
        home folder. Empty when all is well."""
        conn = self._db.conn()
        out: list[str] = []
        for node in conn.execute("SELECT id FROM org_nodes WHERE kind = 'department' AND state = 'active' ORDER BY id"):
            dept_id = node["id"]
            row = conn.execute("SELECT home_dir FROM departments WHERE id = ?", (dept_id,)).fetchone()
            if row is None:
                out.append(f"{dept_id}: no departments row")
                continue
            if not (self._data_dir / row["home_dir"]).is_dir():
                out.append(f"{dept_id}: the home folder {row['home_dir']} does not exist")
            for fn in FUNCTIONS:
                if conn.execute("SELECT 1 FROM graph_nodes WHERE id = ?", (function_node_id(dept_id, fn),)).fetchone() is None:
                    out.append(f"{dept_id}: no function node {fn}")
        return out

    # ---- files ---------------------------------------------------------------------------------------------------------

    def write_mirror(self, dept_id: str) -> bool:
        """Write `departments/<id>/department.json` ({id, name, purpose, home_dir, created}); True when written. Best effort: a
        failure is logged and the database stays the authority."""
        try:
            conn = self._db.conn()
            found = conn.execute(
                "SELECT d.home_dir, d.ts, o.name, o.purpose FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ?", (dept_id,)).fetchone()
            if found is None:
                return False
            folder = self._data_dir / found["home_dir"]
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            body = {"id": dept_id, "name": found["name"], "purpose": found["purpose"], "home_dir": found["home_dir"], "created": iso_z(found["ts"]),
                    "note": "A mirror for humans; the app's database is the authority."}
            target = folder / MIRROR_NAME
            temp = folder / (MIRROR_NAME + ".tmp")
            temp.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            oslayer.replace(temp, target)
            return True
        except (OSError, sqlite3.Error):
            log.warning("could not write the mirror of department %s", dept_id, exc_info=True)
            return False

    def sweep(self) -> int:
        """Remove `departments/<id>` folders that no `departments` row owns and that hold nothing (empty folders only, such as the
        `runs/` a failed apply left behind). A folder with a file in it, or with `engine.json`, `page.json` or `memory/`, is left
        alone: those are the engine's. Returns the number of folders removed."""
        base = self.departments_dir
        if not base.is_dir():
            return 0
        known = {r["id"] for r in self._db.conn().execute("SELECT id FROM departments")}
        removed = 0
        for entry in sorted(base.iterdir()):
            if entry.name in known or entry.is_symlink() or not entry.is_dir() or not _DEPT_ID.fullmatch(entry.name):
                continue
            if any((entry / name).exists() for name in ENGINE_OWNED) or _has_file(entry):
                continue
            try:
                shutil.rmtree(entry)
                removed += 1
            except OSError:
                log.warning("could not remove the empty folder %s", entry, exc_info=True)
        return removed


def _has_file(folder: Path) -> bool:
    """True when anything but a directory lives under `folder` (a symlink counts as a file)."""
    for _root, dirs, files in os.walk(folder):
        if files or any(Path(_root, d).is_symlink() for d in dirs):
            return True
    return False
