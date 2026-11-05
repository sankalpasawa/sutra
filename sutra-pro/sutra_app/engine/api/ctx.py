"""Which team and which run a request is about (engine design 7.2, S1-contracts-01, S3-web-12).

    dept_dependency(services)    the route dependency: `?dept=` only (400 `dept_required`, 404 `not_found`, 403 `read_only` for a
                                 write to an archived team); no header, no cookie, no default team
    build_ctx(services, dept, run)   the `views.RunCtx` of one request: `?run=<id>` is a saved run (read-only, from disk, also
                                 while it runs), else the team's current run (live), else idle
    serve(...)                   ctx + view + response, the three lines every J2 route is made of
    PageState, read_page, write_page   `data/departments/<dept>/page.json`: the start page's output and the reset marker

The client never sends a path: the run folder is `services.data_dir / ref.dir`, and only when that stays inside the team's
`runs/` folder. The current run is `resolve_run(None, dept)` (the live task's run, else the latest) unless it is at or before
`page.json.since_run` (the team was reset): then the page is idle until the next task.
"""
import json
import os
import re
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, Request
from fastapi.responses import Response

from ..paths import DataPaths
from ..spec import DEPT_ID_RE, EngineSettings, SettingsError, read_settings_file
from ..views import VIEWS, MemoryPaths, RunCtx, idle_snapshot, read_published
from .reply import EngineError, dept_required, not_found, read_only, to_response, validation

__all__ = ["RUN_PARAM_RE", "SAFE_METHODS", "PageState", "read_page", "write_page", "first_values", "dept_dependency",
           "current_ref", "run_dir_of", "effective_settings", "build_ctx", "serve", "add_get", "IDLE_RUN_ID"]

RUN_PARAM_RE = r"j2-[\w-]+"          # J2's SAVED regex; a run id also has to be one the team owns
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
IDLE_RUN_ID = "j2-idle"
_PAGE_LOCK = threading.Lock()


# ---- page.json -----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PageState:
    since_run: Optional[str] = None
    next_settings: Mapping[str, str] = field(default_factory=dict)


def _page_file(data_dir, dept_id: str) -> Path:
    return DataPaths.for_dept(data_dir, dept_id).page_json


def read_page(data_dir, dept_id: str) -> PageState:
    """The page file; a missing, torn or odd file reads as the empty state (the page then simply starts clean)."""
    try:
        data = json.loads(_page_file(data_dir, dept_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PageState()
    if not isinstance(data, dict):
        return PageState()
    since = data.get("since_run")
    nxt = data.get("next_settings")
    nxt = {str(k): str(v) for k, v in nxt.items() if isinstance(v, (str, int))} if isinstance(nxt, dict) else {}
    return PageState(since if isinstance(since, str) else None, nxt)


def write_page(data_dir, dept_id: str, **changes: Any) -> PageState:
    """Change `since_run` and/or `next_settings` and write the file by temp file and rename (mode 0600)."""
    unknown = set(changes) - {"since_run", "next_settings"}
    if unknown:
        raise ValueError(f"page.json has no field {sorted(unknown)[0]}")
    target = _page_file(data_dir, dept_id)
    with _PAGE_LOCK:
        old = read_page(data_dir, dept_id)
        state = PageState(changes.get("since_run", old.since_run), dict(changes.get("next_settings", old.next_settings)))
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".page.json.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"since_run": state.since_run, "next_settings": dict(state.next_settings)}, f)
            os.chmod(temp, 0o600)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return state


# ---- the team ------------------------------------------------------------------------------------------------------
def first_values(request: Request) -> dict:
    """The query as a plain dict, the first value of a repeated key (J2's `parse_qs(...)[k][0]`)."""
    out: dict = {}
    for key, value in request.query_params.multi_items():
        out.setdefault(key, value)
    return out


def dept_dependency(services, *, optional: bool = False, envelope_errors: bool = False):
    """The dependency that reads `?dept=`. It returns the team id, or None when `optional` and the parameter is absent.
    J2 routes answer J2's bodies (`envelope_errors=False`); the two settings routes are new routes and answer the envelope."""

    def dept_dep(request: Request) -> Optional[str]:
        values = request.query_params.getlist("dept")
        if optional and not values:
            return None
        dept = values[0] if len(values) == 1 else None
        if dept is None or re.fullmatch(DEPT_ID_RE, dept) is None:
            if envelope_errors:
                raise validation([{"path": "query.dept", "code": "bad_dept", "message": "dept must be a team id"}])
            raise dept_required()
        row = services.department(dept)
        if row is None:
            if envelope_errors:
                raise EngineError(404, {"error": {"code": "not_found", "message": "That team was not found", "details": {}}})
            raise not_found()
        if getattr(row, "archived", False) and request.method.upper() not in SAFE_METHODS:
            raise read_only()
        return dept

    return dept_dep


# ---- the run -------------------------------------------------------------------------------------------------------
def current_ref(services, dept_id: str, page: Optional[PageState] = None):
    """The run the team's page shows: the live one, else the latest, unless the team was reset after it (then None)."""
    page = page or read_page(services.data_dir, dept_id)
    ref = services.resolve_run(None, dept_id)
    if ref is None or getattr(ref, "dept_id", dept_id) != dept_id:
        return None
    if page.since_run is not None and ref.run_id <= page.since_run:
        return None
    return ref


def run_dir_of(services, dept_id: str, ref) -> Optional[str]:
    """`data_dir / ref.dir` when that folder exists inside the team's `runs/` folder; else None."""
    runs = os.path.realpath(DataPaths.for_dept(services.data_dir, dept_id).runs_dir)
    folder = os.path.realpath(os.path.join(os.fspath(services.data_dir), ref.dir))
    inside = os.path.dirname(folder) == runs and os.path.basename(folder) == ref.run_id
    return folder if inside and os.path.isdir(folder) else None


def effective_settings(data_dir, dept_id: str, page: Optional[PageState] = None) -> EngineSettings:
    """What the team's next run would use: data/engine.json < the team's engine.json < the start page's output choice.
    The server's own `J2_*` environment is not a layer (a spawned engine never receives it). A settings file that cannot be
    read gives J2's defaults here: the page must still draw (the Settings routes report the file)."""
    paths = DataPaths.for_dept(data_dir, dept_id)
    page = page or read_page(data_dir, dept_id)
    try:
        return EngineSettings.layered({}, read_settings_file(paths.engine_json), read_settings_file(paths.dept_engine_json), dict(page.next_settings))
    except SettingsError:
        return EngineSettings()


def build_ctx(services, dept_id: str, run: Optional[str] = None, *, commands=None) -> RunCtx:
    paths = DataPaths.for_dept(services.data_dir, dept_id)
    memory = MemoryPaths(str(paths.lessons_file), str(paths.playbooks_file))
    page = read_page(services.data_dir, dept_id)
    current = current_ref(services, dept_id, page)
    live_id = current.run_id if current is not None else ""
    common = dict(runs_dir=str(paths.runs_dir), live_id=live_id, memory=memory, dept_id=dept_id, commands=commands)
    if run:
        ref = services.resolve_run(run, dept_id) if re.fullmatch(RUN_PARAM_RE, run) else None
        if ref is None or getattr(ref, "dept_id", dept_id) != dept_id or ref.run_id != run:
            raise not_found()
        return RunCtx("saved", run, run_dir_of(services, dept_id, ref), **common)
    published = None
    folder = run_dir_of(services, dept_id, current) if current is not None else None
    if folder is not None:
        published = read_published(folder)
    if published is None:       # no run yet, the team was reset, or the process has not published yet (it is still starting)
        snap = idle_snapshot(effective_settings(services.data_dir, dept_id, page), memory, IDLE_RUN_ID)
        return RunCtx("idle", None, None, snap=snap, **common)
    return RunCtx("live", current.run_id, folder, snap=published.snap, extras=published.live, alive=published.alive, **common)


def serve(services, view: str, request: Request, dept_id: str, extra: Optional[Mapping] = None, *, commands=None,
          body: Optional[dict] = None) -> Response:
    """One J2 route: the view `view` over the request's context, as a response. Path parts (`extra`) become query entries,
    as `views` expects. A write (`body` is not None) is about the team's current state and ignores `?run=`."""
    query = {**first_values(request), **(extra or {})}
    ctx = build_ctx(services, dept_id, None if body is not None else query.get("run"), commands=commands)
    return to_response(VIEWS[view](ctx, query if body is None else body), services.redact)


def add_get(router, services, dept_dep, path: str, name: str) -> None:
    """Register `GET path` as the view `name`. The parts of the path (`{key}`, `{n}`, ...) are passed on as query entries."""

    def endpoint(request: Request, dept: str = Depends(dept_dep)) -> Response:       # a plain def: FastAPI runs it in its thread pool
        return serve(services, name, request, dept, request.path_params)

    endpoint.__name__ = name
    router.get(path, response_class=Response)(endpoint)
