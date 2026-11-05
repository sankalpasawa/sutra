"""The read-only Sutra tools (connectors design 3.9, CD14): chart, models, graph and atom.

Every tool reads through a `ReadModel`. The default one opens SQLite as `file:...?mode=ro` (and `query_only`), so a write is
impossible at the database; a section that owns the data can supply its own with `--readmodel pkg.mod:factory` (the factory
is called with the database path, or None). `tool_specs` lists only the tools the ReadModel supports. Nothing here changes
anything: the model proposes, the server's write gate disposes (a chart change is a structured reply, never a tool).
"""
from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional, Protocol

from .profiles import ToolError, ToolSpec

__all__ = ["ReadModel", "SqliteReadModel", "default_readmodel", "load_readmodel", "tool_specs", "TOOL_METHODS",
           "MAX_NODES", "MAX_DEPTH"]

MAX_NODES = 300                   # a graph answer lists at most this many nodes
MAX_DEPTH = 20
_ID = r"[A-Za-z0-9_.:-]{1,120}"


class ReadModel(Protocol):
    """What the Sutra tools read. Implement any subset: a tool whose method is missing is not offered."""

    def chart(self, department_id: Optional[str], depth: Optional[int]) -> dict: ...
    def model_names(self) -> list[str]: ...
    def model_schema(self, name: str) -> dict: ...
    def graph(self, workflow_id: Optional[str]) -> dict: ...
    def atom(self, atom_id: str) -> dict: ...


# tool name -> the ReadModel methods it needs
TOOL_METHODS = {
    "sutra_chart_read": ("chart",),
    "sutra_models_list": ("model_names",),
    "sutra_model_schema": ("model_schema",),
    "sutra_graph_read": ("graph",),
    "sutra_atom_read": ("atom",),
}


class SqliteReadModel:
    """The default ReadModel over the app's SQLite database, opened read-only for every call."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _open(self) -> sqlite3.Connection:
        if not self.path.exists():
            raise ToolError("no_data", "the Sutra database does not exist yet")
        conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self._open()
        try:
            return conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise ToolError("read_failed", f"the Sutra database could not be read: {exc}") from None
        finally:
            conn.close()

    # ---- chart ---------------------------------------------------------------------------------------------------------------
    def chart(self, department_id: Optional[str] = None, depth: Optional[int] = None) -> dict:
        nodes = {r["id"]: dict(r) for r in self._query("SELECT id, kind, name, purpose FROM org_nodes WHERE state = 'active'")}
        children: dict[str, list[str]] = {}
        for r in self._query("SELECT parent_id, child_id FROM org_edges ORDER BY parent_id, position, child_id"):
            if r["parent_id"] in nodes and r["child_id"] in nodes:
                children.setdefault(r["parent_id"], []).append(r["child_id"])
        revision = self._query("SELECT max(revision) AS r FROM org_charts")
        revision = revision[0]["r"] if revision else None
        if department_id is None:
            start = next((i for i, n in nodes.items() if n["kind"] == "root"), None)
        else:
            start = department_id if department_id in nodes else None
            if start is None:
                raise ToolError("not_found", f"no active node {department_id!r} in the chart")
        if start is None:
            return {"revision": revision, "root": None}

        def build(node_id: str, level: int) -> dict:
            out = dict(nodes[node_id])
            kids = children.get(node_id, [])
            if depth is not None and level >= depth:
                if kids:
                    out["children_hidden"] = len(kids)
                return out
            out["children"] = [build(k, level + 1) for k in kids]
            return out

        return {"revision": revision, "root": build(start, 0)}

    # ---- graph ---------------------------------------------------------------------------------------------------------------
    def graph(self, workflow_id: Optional[str] = None) -> dict:
        columns = "id, kind, state, label, department_id, parent_id, task_id, step_ref"
        if workflow_id is None:
            rows = self._query(f"SELECT {columns} FROM graph_nodes ORDER BY ts, id")
        else:
            rows = self._query(f"SELECT {columns} FROM graph_nodes WHERE task_id = ? OR department_id = ? OR id = ? ORDER BY ts, id",
                               (workflow_id, workflow_id, workflow_id))
            if not rows:
                raise ToolError("not_found", f"no graph nodes for {workflow_id!r} (a task id, a department id or a node id)")
        total = len(rows)
        shown = [dict(r) for r in rows[:MAX_NODES]]
        ids = {n["id"] for n in shown}
        edges = [dict(id=r["id"], kind=r["kind"], **{"from": r["from_id"], "to": r["to_id"]}, status=r["status"], label=r["label"])
                 for r in self._query("SELECT id, kind, from_id, to_id, status, label FROM graph_edges ORDER BY id")
                 if r["from_id"] in ids and r["to_id"] in ids]
        counts: dict[str, int] = {}
        for n in shown:
            counts[n["state"]] = counts.get(n["state"], 0) + 1
        version = self._query("SELECT value FROM meta WHERE key = 'graph_version'")
        return {"graph_version": version[0]["value"] if version else None, "node_count": total, "truncated": total > MAX_NODES,
                "states": counts, "nodes": shown, "edges": edges}

    # ---- atom ----------------------------------------------------------------------------------------------------------------
    def atom(self, atom_id: str) -> dict:
        rows = self._query("SELECT id, schema, node_id, department_id, task_id, state, display, attempt, goal, body, ts_open, "
                           "ts_closed FROM atoms WHERE id = ?", (atom_id,))
        if not rows:
            raise ToolError("not_found", f"no atom {atom_id!r}")
        out = dict(rows[0])
        try:
            out["body"] = json.loads(out["body"])
        except ValueError:
            pass                                            # a body that is not JSON is returned as it is
        return out


def _library_registry():
    """The library's registry with every module imported, or None when it cannot be loaded."""
    try:
        try:
            importlib.import_module("sutra_app.library.all")
        except ModuleNotFoundError as exc:
            if exc.name != "sutra_app.library.all":
                raise
            for name in ("types", "base", "atom", "chat", "department", "evaluation", "functions", "goal", "node", "org_chart", "workflow"):
                importlib.import_module(f"sutra_app.library.{name}")
        from sutra_app.library.registry import REGISTRY
        return REGISTRY
    except Exception:
        return None


class _LibraryReadModel(SqliteReadModel):
    """SqliteReadModel plus the Interface-library model names and schemas."""

    def __init__(self, path: str | Path, registry: Any) -> None:
        super().__init__(path)
        self._registry = registry

    def model_names(self) -> list[str]:
        return list(self._registry.families())

    def model_schema(self, name: str) -> dict:
        if name not in self._registry.families():
            raise ToolError("not_found", f"no model {name!r} (call sutra_models_list for the names)")
        try:
            return self._registry.json_schema(name)
        except Exception as exc:
            raise ToolError("schema_failed", f"the schema of {name!r} could not be built: {exc}") from None


def default_readmodel(path: str | Path) -> ReadModel:
    """Chart, graph and atom over SQLite; the model tools too when the library registry loads."""
    registry = _library_registry()
    return _LibraryReadModel(path, registry) if registry is not None else SqliteReadModel(path)


def load_readmodel(spec: Optional[str], db_path: Optional[str]) -> ReadModel:
    """`pkg.mod:factory` -> factory(db_path); no spec -> the default over `db_path` (ValueError when there is no path)."""
    if spec:
        module, sep, attr = spec.partition(":")
        if not sep or not module or not attr:
            raise ValueError(f"--readmodel must look like pkg.mod:factory, got {spec!r}")
        return getattr(importlib.import_module(module), attr)(db_path)
    if not db_path:
        raise ValueError("no database: set SUTRA_DB_RO or pass --readmodel")
    return default_readmodel(db_path)


def supports(readmodel: Any, tool: str) -> bool:
    return all(callable(getattr(readmodel, m, None)) for m in TOOL_METHODS[tool])


def tool_specs(readmodel: Optional[ReadModel]) -> list[ToolSpec]:
    """The Sutra tools `readmodel` supports (all of them when it is None: used for the static catalog)."""
    def chart(a: dict) -> Any:
        return readmodel.chart(a.get("department_id"), a.get("depth"))

    def names(a: dict) -> Any:
        return {"models": list(readmodel.model_names())}

    def schema(a: dict) -> Any:
        return readmodel.model_schema(a["name"])

    def graph(a: dict) -> Any:
        return readmodel.graph(a.get("workflow_id"))

    def atom(a: dict) -> Any:
        return readmodel.atom(a["atom_id"])

    def obj(properties: dict, required: tuple = ()) -> dict:
        return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}

    specs = [
        ToolSpec("sutra_chart_read", "Read the global org chart as a tree. Optional department_id starts at that node; depth limits "
                 "the levels below it (0 = the node only).",
                 obj({"department_id": {"type": "string", "pattern": _ID}, "depth": {"type": "integer", "minimum": 0, "maximum": MAX_DEPTH}}),
                 chart),
        ToolSpec("sutra_models_list", "List the names of the Interface-library models.", obj({}), names),
        ToolSpec("sutra_model_schema", "Read the JSON Schema of one Interface-library model by name.",
                 obj({"name": {"type": "string", "pattern": r"[A-Za-z0-9_.-]{1,80}"}}, ("name",)), schema),
        ToolSpec("sutra_graph_read", "Read the workflow graph (nodes and edges). Optional workflow_id is a task id, a department id "
                 "or a node id; without it the whole graph summary is returned.",
                 obj({"workflow_id": {"type": "string", "pattern": _ID}}), graph),
        ToolSpec("sutra_atom_read", "Read one work atom (its goal, task and context) by id.",
                 obj({"atom_id": {"type": "string", "pattern": _ID}}, ("atom_id",)), atom),
    ]
    return [s for s in specs if readmodel is None or supports(readmodel, s.name)]
