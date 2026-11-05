"""Rows 31 and 32: the engine settings the owner edits in Settings (engine design 7.1, S1-contracts-03, D18).

    GET /api/engine/settings[?dept=]   {schema, defaults, global, department (only with dept), effective, editable, locked}
    PUT /api/engine/settings[?dept=]   {"set": {field: value}, "unset": [field]}   (token required)

Without `dept` the file is `data/engine.json`, with it `data/departments/<dept>/engine.json`. A file holds field names (partial,
J2's defaults fill the rest). PUT checks every new value strictly against `EngineSettings` (closed, no secret is a field),
refuses unknown and `LOCKED_FIELDS` (live email, recipients, the Chrome path, the test switches: hand edits only) with 422
`validation`, proves the whole file still validates, and writes it by temp file and rename with mode 0600. A change applies to
the NEXT run of that scope: the host reads the files once at start and writes `<run>/settings.json`. These are new routes, so
errors are the envelope `{error: {code, message, details}}`; an unreadable settings file is 422 `validation` naming the file.
"""
import json
import os
from sutra_app import oslayer
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import ValidationError

from ..paths import DataPaths
from ..spec import EDITABLE_FIELDS, LOCKED_FIELDS, SETTINGS_SCHEMA, EngineSettings, SettingsError, read_settings_file
from .commands import read_json_body
from .ctx import dept_dependency
from .reply import json_reply, to_response, validation

__all__ = ["add_routes", "settings_view", "apply_change", "settings_file"]

_WRITE_LOCK = threading.Lock()
_FIELDS = tuple(EngineSettings.model_fields)


def _violation(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def settings_file(data_dir, dept_id: Optional[str]) -> Path:
    paths = DataPaths.for_dept(data_dir, dept_id or "global")
    return paths.dept_engine_json if dept_id else paths.engine_json


def _read(path: Path) -> dict:
    try:
        return read_settings_file(path) or {}
    except SettingsError as exc:
        raise validation([_violation("file", "unreadable_settings", str(exc))], "A settings file cannot be read") from None


def settings_view(data_dir, dept_id: Optional[str]) -> dict:
    """The body of GET (and of PUT): what the files hold and what the next run of this scope would use."""
    global_file = _read(settings_file(data_dir, None))
    dept_file = _read(settings_file(data_dir, dept_id)) if dept_id else None
    try:
        effective = EngineSettings.layered({}, global_file, dept_file, {})
    except SettingsError as exc:
        raise validation([_violation("file", "invalid_settings", str(exc))], "The settings files do not validate") from None
    body: dict[str, Any] = {"schema": SETTINGS_SCHEMA, "defaults": EngineSettings().model_dump(), "global": global_file}
    if dept_id:
        body["department"] = dept_file
    body.update(effective=effective.model_dump(), editable=list(EDITABLE_FIELDS), locked=list(LOCKED_FIELDS))
    return body


def _errors(prefix: str, exc: ValidationError) -> list[dict]:
    return [_violation(".".join([prefix, *map(str, err["loc"])]), err["type"], err["msg"]) for err in exc.errors(include_url=False)]


def apply_change(data_dir, dept_id: Optional[str], body: Any) -> None:
    """Validate a `{set, unset}` body and write the file. Raises `EngineError` (422 `validation`) and writes nothing on a problem."""
    if not isinstance(body, dict):
        raise validation([_violation("body", "not_object", "send a JSON object with set and/or unset")])
    bad = [_violation(key, "unknown_key", "only set and unset are allowed") for key in body if key not in ("set", "unset")]
    to_set, to_unset = body.get("set", {}), body.get("unset", [])
    if not isinstance(to_set, dict):
        bad.append(_violation("set", "not_object", "set must be an object of field: value"))
        to_set = {}
    if not isinstance(to_unset, list) or not all(isinstance(name, str) for name in to_unset):
        bad.append(_violation("unset", "not_list", "unset must be a list of field names"))
        to_unset = []
    for where, names in (("set", list(to_set)), ("unset", to_unset)):
        for name in names:
            if name in LOCKED_FIELDS:
                bad.append(_violation(f"{where}.{name}", "locked_field", f"{name} is locked: edit the settings file by hand"))
            elif name not in _FIELDS:
                bad.append(_violation(f"{where}.{name}", "unknown_field", f"{name} is not an engine setting"))
    bad += [_violation(f"unset.{name}", "also_set", f"{name} is in set and unset") for name in to_unset if name in to_set]
    # strict mode lets true through for 0/1 (True == 1): a yes/no belongs to the flags only
    bad += [_violation(f"set.{name}", "not_a_flag", f"{name} is not a yes/no setting") for name, value in to_set.items()
            if isinstance(value, bool) and name in _FIELDS and EngineSettings.model_fields[name].annotation is not bool]
    if bad:
        raise validation(bad)
    try:
        checked = EngineSettings.model_validate(to_set, strict=True)
    except ValidationError as exc:
        raise validation(_errors("set", exc)) from None
    path = settings_file(data_dir, dept_id)
    with _WRITE_LOCK:
        current = _read(path)
        merged = {**current, **{name: getattr(checked, name) for name in to_set}}
        for name in to_unset:
            merged.pop(name, None)
        try:
            EngineSettings(**merged)
        except ValidationError as exc:
            raise validation(_errors("file", exc), "The settings file would not validate") from None
        if merged != current:
            _write_atomic(path, merged)


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)       # 0600 from the start
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        oslayer.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def add_routes(router: APIRouter, services, _j2_dept_dep=None) -> None:
    dept_dep = dept_dependency(services, optional=True, envelope_errors=True)

    @router.get("/api/engine/settings", response_class=Response)
    def settings_get(dept: Optional[str] = Depends(dept_dep)) -> Response:
        return to_response(json_reply(settings_view(services.data_dir, dept)), services.redact)

    @router.put("/api/engine/settings", dependencies=[Depends(services.require_token)], response_class=Response)
    async def settings_put(request: Request, dept: Optional[str] = Depends(dept_dep)) -> Response:
        body = await read_json_body(request)

        def work() -> Response:
            apply_change(services.data_dir, dept, body if body is not None else "not an object")
            return to_response(json_reply(settings_view(services.data_dir, dept)), services.redact)
        return await run_in_threadpool(work)
