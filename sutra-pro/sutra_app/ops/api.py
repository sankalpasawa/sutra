"""The owner console's routes (work package GAP-CONSOLE, gaps G11 and G12): health, usage by period, diagnostics.

    GET /api/ops/info                              version, schema, data folder, sizes, uptime, live tasks, engine settings source
    GET /api/ops/doctor[?refresh=1]                the doctor's checks (no model call), cached 30 s
    GET /api/ops/usage?period=today|7d|30d|all&include_stub=0|1     totals, providers, days, teams, functions, purposes, top ten atoms by cost
    GET /api/ops/diagnostics                       a zip for a bug report; needs the X-Sutra-Token header although it is a GET

All four are reads and answer in the usual error envelope. `router` is mounted by `create_app` when this module exists
(`main._mount_ops_api`). The usage route exists because the period picker of the console needs one report for a period in one request (totals, the basis of
each dollar figure, the team names, the dearest atoms); the by-purpose rows are the store's own (`UsageStore.summary("purpose", since=...)`, the same rows
as `GET /api/usage/summary?by=purpose&since=`, D159). Every other panel of the console reads the orchestrator's existing routes.

The diagnostics zip holds `info.json`, `doctor.json`, `server-log-tail.txt` (the last 2 000 lines of `server.log`), `settings.json`
(`Settings.public()`), `schema-versions.json`, `departments.json` (folder names and sizes) and `README.txt`. It never holds a chat, a
prompt, a site or document file, the `.env` file or a secret: every text goes through the app's redactor, and the log tail also through
a pattern pass (`sk-` keys, bearer tokens, `key=value` pairs) for secrets the redactor cannot know.
"""
import hmac
import io
import json
import logging
import os
import platform
import re
import shutil
import sys
import threading
import time
import zipfile
from collections import deque
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from sutra_app.library.registry import REGISTRY
from sutra_app.ops import doctor, lock
from sutra_app.orchestrator.api.deps import TOKEN_HEADER, RedactedJSONResponse, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import LIVE_STATUSES

__all__ = ["router", "build_router", "collect_info", "usage_report", "build_diagnostics", "tail_lines", "scrub_text", "period_start",
           "PERIODS", "DOCTOR_TTL_S", "LOG_TAIL_LINES", "TOP_ATOMS"]

log = logging.getLogger(__name__)
PERIODS: dict[str, int | None] = {"today": 1, "7d": 7, "30d": 30, "all": None}      # days, counted in UTC dates, today included
DOCTOR_TTL_S = 30.0
LOG_TAIL_LINES = 2000
TOP_ATOMS = 10
DAY_S = 86400
MAX_DEPARTMENTS = 500
FN_TABS = {"identity": "charter", "adaptation": "workflows", "priority": "conflicts", "coordination": "timeline", "audit": "audit"}
_PROCESS_STARTED = time.time()                     # fallback for the uptime when the instance lock does not name this process
_now = time.monotonic                              # the doctor cache's clock (a test replaces it)

# secrets the redactor cannot know by value: sk- style keys, bearer tokens, and name=value pairs whose name says secret
_PATTERNS = (
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "[redacted]"),
    (re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=\-]{8,}", re.IGNORECASE), r"\1 [redacted]"),
    (re.compile(r"""(?ix)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd|authorization)\b(["']?\s*[:=]\s*["']?)[^\s"',;&]+"""),
     r"\1\2[redacted]"),
)


def scrub_text(text: str, redact: Any = None) -> str:
    """`text` through the app's redactor (when given) and then the pattern pass."""
    if callable(redact):
        text = redact(text)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---- the guard and the answers -------------------------------------------------------------------------------------------------

async def require_header_token(request: Request) -> None:
    """The write guard's check for a GET that must not be fetched by a page that does not hold the token: the header `X-Sutra-Token` equals
    the launch token (401 `bad_token`), and a present `Origin` is this app (403 `bad_origin`)."""
    expected = services_of(request).settings.token
    supplied = request.headers.getlist(TOKEN_HEADER)
    if len(supplied) != 1 or not hmac.compare_digest(supplied[0].encode("utf-8"), expected.encode("utf-8")):
        raise AppError("bad_token", "A valid X-Sutra-Token header is required for this request")
    origins = request.headers.getlist("origin")
    if origins:
        host = request.headers.get("host", "")
        if len(origins) != 1 or origins[0].lower() != f"http://{host}".lower() or not host:
            raise AppError("bad_origin", "The Origin of this request is not this app")


def _json(request: Request, content: Any) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(scrub(content) if callable(scrub) else content)


# ---- info ----------------------------------------------------------------------------------------------------------------------

def _tree_bytes(path: Path) -> tuple[int, int]:
    """(bytes, files) under `path`, symlinks not followed, unreadable entries skipped."""
    size = files = 0
    for folder, _, names in os.walk(path, followlinks=False):
        for name in names:
            try:
                status = os.lstat(os.path.join(folder, name))
            except OSError:
                continue
            size += status.st_size
            files += 1
    return size, files


def _nearest_existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path("/")


def _engine_settings_source(data_dir: Path) -> dict[str, Any]:
    """Where the engine's settings come from for a new run: defaults, `<data>/engine.json` (field names only) and the `J2_*` variables."""
    from sutra_app.engine.api.settings import settings_file
    from sutra_app.engine.spec import ENV_NAMES, EngineSettings, read_settings_file
    path = settings_file(data_dir, None)
    fields: list[str] = []
    problem = ""
    if path.exists():
        try:
            fields = sorted((read_settings_file(path) or {}).keys())
        except Exception as exc:                                                   # noqa: BLE001  (a bad file is reported, not raised)
            problem = str(exc)[:200]
    names = {env_name for field, env_name in ENV_NAMES.items() if field in EngineSettings.model_fields}
    from_env = sorted(name for name in names if (os.environ.get(name) or "").strip())
    layers = (["data/engine.json"] if fields else []) + (["the process environment"] if from_env else [])
    return {"source": " + ".join(layers) if layers else "defaults", "file": str(path), "file_exists": path.exists(), "fields": fields,
            "env": from_env, "problem": problem}


def _uptime_s(data_dir: Path) -> float:
    holder = lock.read_holder(data_dir)
    started = holder.started if holder is not None and holder.pid == os.getpid() and holder.started else _PROCESS_STARTED
    return round(max(0.0, time.time() - float(started)), 1)


def collect_info(services: Any) -> dict[str, Any]:
    """The facts the Health panel and the diagnostics show. Runs on a worker thread (database reads, folder sizes)."""
    settings = services.settings
    conn = services.db.conn()
    db_path = settings.db_path
    db_bytes = sum(p.stat().st_size for p in (db_path, db_path.with_name(db_path.name + "-wal")) if p.exists())
    live = conn.execute(f"SELECT count(*) FROM tasks WHERE status IN ({','.join('?' * len(LIVE_STATUSES))})", LIVE_STATUSES).fetchone()[0]
    atoms = conn.execute("SELECT count(*), coalesce(max(seq), 0) FROM atom_ledger").fetchone()
    usage_rows = conn.execute("SELECT count(*) FROM usage_ledger").fetchone()[0]
    try:
        free = shutil.disk_usage(_nearest_existing(settings.data_dir)).free
    except OSError:
        free = None
    from sutra_app.orchestrator.schema import SCHEMA_VERSION
    return {
        "app": "Sutra Pro", "version": services.version, "schema": services.db.version(), "schema_expected": SCHEMA_VERSION,
        "data_dir": str(settings.data_dir), "db_path": str(db_path), "db_bytes": db_bytes, "free_bytes": free,
        "log_path": str(settings.log_path), "uptime_s": _uptime_s(settings.data_dir), "live_tasks": live,
        "engine_settings": _engine_settings_source(settings.data_dir),
        "connector": settings.connector, "engine": settings.engine, "offline": settings.offline, "port": settings.port,
        "atom_log": {"rows": atoms[0], "last_seq": atoms[1]}, "usage_rows": usage_rows,
        "python": sys.version.split()[0], "platform": platform.platform(terse=True),
    }


# ---- doctor (cached) -----------------------------------------------------------------------------------------------------------

def _doctor_dict(services: Any) -> dict[str, Any]:
    settings = services.settings
    report = doctor.run(settings, offline=settings.offline)
    checks = []
    for check in report.checks:
        if check.id == "port":
            # the doctor asks "is a port free for a new server"; this process is the server and is listening
            check = doctor.Check("port", "Port", "ok", f"this server listens on {settings.host}:{settings.port}")
        checks.append(check)
    report.checks = checks
    return report.to_dict()


def doctor_answer(app: Any, services: Any, refresh: bool = False) -> dict[str, Any]:
    """The doctor's report with `cached`, `age_s` and `ttl_s`. A report younger than 30 s is reused unless `refresh`."""
    state = app.state
    guard = getattr(state, "ops_doctor_lock", None)
    if guard is None:
        guard = state.ops_doctor_lock = threading.Lock()
    with guard:
        held = getattr(state, "ops_doctor", None)
        age = None if held is None else _now() - held[0]
        if held is not None and not refresh and 0 <= age < DOCTOR_TTL_S:
            return {**held[1], "cached": True, "age_s": round(age, 1), "ttl_s": DOCTOR_TTL_S}
        report = _doctor_dict(services)
        report["checked_at"] = iso_z(time.time())
        state.ops_doctor = (_now(), report)
        return {**report, "cached": False, "age_s": 0.0, "ttl_s": DOCTOR_TTL_S}


# ---- usage by period -----------------------------------------------------------------------------------------------------------

def period_start(period: str, now: int) -> int | None:
    """Epoch seconds of the first moment of the period (UTC midnight, `today` included), None for `all`."""
    days = PERIODS[period]
    if days is None:
        return None
    return (now - now % DAY_S) - (days - 1) * DAY_S


def _sums(row: Any) -> dict[str, Any]:
    usd = row["usd"]
    return {"calls": row["calls"], "usd": None if usd is None else round(float(usd), 6), "tokens_in": row["tin"], "tokens_out": row["tout"]}


def _add(a: int | float | None, b: int | float | None) -> int | float | None:
    return b if a is None else (a if b is None else a + b)


def _dearest_first(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups with a dollar figure first, the dearest on top; then the ones with tokens only, the most tokens first; then by key (the order of the top atoms)."""
    return sorted(groups, key=lambda g: (g["usd"] is None, -(g["usd"] or 0.0), -((g["tokens_in"] or 0) + (g["tokens_out"] or 0)), g["key"]))


def usage_report(services: Any, period: str, include_stub: bool, now: int) -> dict[str, Any]:
    """Usage over `period`: totals, per provider (with the basis of the dollar figure), per day, per team and function, per purpose (what the calls were for,
    the dearest first, D159) and the ten atoms that cost most. Stub rows are left out unless `include_stub`. A sum is null when every row's part is null."""
    since = period_start(period, now)
    where, args = [], []
    if since is not None:
        where.append("u.at >= ?")
        args.append(since)
    if not include_stub:
        where.append("u.provider != 'stub'")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    conn = services.db.conn()
    cols = "count(*) AS calls, sum(u.usd) AS usd, sum(u.tokens_in) AS tin, sum(u.tokens_out) AS tout"
    totals = _sums(conn.execute(f"SELECT {cols} FROM usage_ledger u{clause}", args).fetchone())

    providers: dict[str, dict[str, Any]] = {}
    for r in conn.execute(
            f"SELECT u.provider AS k, json_extract(u.detail_json, '$.usd_basis') AS basis, json_extract(u.detail_json, '$.billing') AS billing, {cols}"
            f" FROM usage_ledger u{clause} GROUP BY u.provider, basis, billing ORDER BY u.provider", args):
        entry = providers.setdefault(r["k"], {"key": r["k"], "calls": 0, "usd": None, "tokens_in": None, "tokens_out": None,
                                              "usd_basis": [], "billing": []})
        part = _sums(r)
        entry["calls"] += part["calls"]
        for name in ("usd", "tokens_in", "tokens_out"):
            entry[name] = _add(entry[name], part[name])
        for name, value in (("usd_basis", r["basis"]), ("billing", r["billing"])):
            if value and value not in entry[name]:
                entry[name].append(value)
    for entry in providers.values():
        if entry["usd"] is not None:
            entry["usd"] = round(entry["usd"], 6)
        # a dollar figure the subscription does not bill is notional: the console labels it so
        entry["notional"] = "subscription" in entry["billing"]

    days = [{"key": r["k"], **_sums(r)} for r in conn.execute(
        f"SELECT strftime('%Y-%m-%d', u.at, 'unixepoch') AS k, {cols} FROM usage_ledger u{clause} GROUP BY k ORDER BY k", args)]

    teams: dict[str, dict[str, Any]] = {}
    functions = []
    for r in conn.execute(
            f"SELECT u.dept_id AS dept, o.name AS name, u.fn AS fn, {cols} FROM usage_ledger u LEFT JOIN org_nodes o ON o.id = u.dept_id{clause}"
            f" GROUP BY u.dept_id, u.fn ORDER BY u.dept_id, u.fn", args):
        part = _sums(r)
        key = r["dept"] or "(none)"
        team = teams.setdefault(key, {"key": key, "name": r["name"] or key, "calls": 0, "usd": None, "tokens_in": None, "tokens_out": None})
        team["calls"] += part["calls"]
        for name in ("usd", "tokens_in", "tokens_out"):
            team[name] = _add(team[name], part[name])
        functions.append({"dept": key, "name": r["name"] or key, "fn": r["fn"] or "(none)", **part})
    for team in teams.values():
        if team["usd"] is not None:
            team["usd"] = round(team["usd"], 6)

    purposes = _dearest_first(services.usage.summary("purpose", include_stub=include_stub, since=since))

    top = []
    atom_clause = (clause + " AND " if clause else " WHERE ") + "u.atom_id IS NOT NULL"
    for r in conn.execute(
            f"SELECT u.atom_id AS atom, max(u.dept_id) AS dept, max(u.fn) AS fn, max(u.node_id) AS node, {cols} FROM usage_ledger u{atom_clause}"
            f" GROUP BY u.atom_id ORDER BY (sum(u.usd) IS NULL), sum(u.usd) DESC, coalesce(sum(u.tokens_in), 0) + coalesce(sum(u.tokens_out), 0) DESC,"
            f" u.atom_id LIMIT ?", (*args, TOP_ATOMS)):
        dept, fn = r["dept"], r["fn"]
        top.append({"atom_id": r["atom"], "dept": dept, "fn": fn, "node_id": r["node"], **_sums(r),
                    "team_href": f"/d/{dept}/?tab={FN_TABS[fn]}" if dept and fn in FN_TABS else None,
                    "node_href": f"/?pane=graph&node={r['node']}" if r["node"] else None})
    return {"period": period, "since": iso_z(since) if since is not None else None, "include_stub": include_stub, "totals": totals,
            "providers": list(providers.values()), "days": days, "teams": list(teams.values()), "functions": functions, "purposes": purposes, "atoms": top}


# ---- diagnostics ---------------------------------------------------------------------------------------------------------------

def tail_lines(path: Path, count: int = LOG_TAIL_LINES) -> list[str]:
    """The last `count` lines of a text file (all of them when it is shorter); a missing file is no lines."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\n") for line in deque(handle, maxlen=count)]
    except OSError:
        return []


def _departments(settings: Any) -> list[dict[str, Any]]:
    root = settings.departments_dir
    out = []
    try:
        names = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.is_symlink())[:MAX_DEPARTMENTS]
    except OSError:
        return []
    for name in names:
        size, files = _tree_bytes(root / name)
        out.append({"id": name, "bytes": size, "files": files})
    return out


def _schema_versions(services: Any, info: dict[str, Any]) -> dict[str, Any]:
    from sutra_app.engine.spec import SETTINGS_SCHEMA
    return {"database_user_version": info["schema"], "database_expected": info["schema_expected"], "engine_settings": SETTINGS_SCHEMA,
            "library": {family: REGISTRY.versions(family) for family in REGISTRY.families()}}


README = (
    "Sutra Pro diagnostics\n"
    "\n"
    "info.json            version, schema, data folder, sizes, uptime, live tasks\n"
    "doctor.json          the doctor's checks (no model call was made)\n"
    "server-log-tail.txt  the last {lines} lines of server.log, with secrets removed\n"
    "settings.json        the non-secret settings\n"
    "schema-versions.json database and library schema versions\n"
    "departments.json     the team folders and their sizes\n"
    "\n"
    "Not included: chats, prompts, site and document files, the .env file, the launch token and any key.\n"
)


def build_diagnostics(services: Any, info: dict[str, Any], doctor_report: dict[str, Any], now: int) -> bytes:
    """The zip. Every text is redacted (the app's redactor, then the patterns); JSON members are redacted as data first."""
    redact = services.redact
    scrub = getattr(redact, "scrub", None)

    def dump(obj: Any) -> str:
        data = scrub(obj) if callable(scrub) else obj
        return scrub_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", redact)

    log_text = "\n".join(scrub_text(line, redact) for line in tail_lines(services.settings.log_path))
    when = time.gmtime(now)[:6]
    members = {
        "info.json": dump(info),
        "doctor.json": dump(doctor_report),
        "server-log-tail.txt": (log_text + "\n") if log_text else "(no server.log lines yet)\n",
        "settings.json": dump(services.settings.public()),
        "schema-versions.json": dump(_schema_versions(services, info)),
        "departments.json": dump(_departments(services.settings)),
        "README.txt": README.format(lines=LOG_TAIL_LINES),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in members.items():
            entry = zipfile.ZipInfo(name, date_time=when)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, text)
    return buffer.getvalue()


# ---- the router ----------------------------------------------------------------------------------------------------------------

def build_router() -> APIRouter:
    api = APIRouter(prefix="/api/ops", tags=["ops"])

    @api.get("/info", summary="Version, schema, data folder, sizes, uptime, live tasks, engine settings source")
    async def get_info(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        return _json(request, await run_blocking(lambda: collect_info(services)))

    @api.get("/doctor", summary="The doctor's checks without a model call, cached for 30 seconds")
    async def get_doctor(request: Request, refresh: bool = Query(False)) -> RedactedJSONResponse:
        services = services_of(request)
        return _json(request, await run_blocking(lambda: doctor_answer(request.app, services, refresh)))

    @api.get("/usage", summary="Usage over a period: totals, providers, days, teams, functions, top atoms")
    async def get_usage(request: Request, period: Literal["today", "7d", "30d", "all"] = Query("all"),
                        include_stub: bool = Query(False)) -> RedactedJSONResponse:
        services = services_of(request)
        now = services.clock.now()
        return _json(request, await run_blocking(lambda: usage_report(services, period, include_stub, now)))

    @api.get("/diagnostics", summary="A zip for a bug report (needs the token header)", dependencies=[Depends(require_header_token)],
             response_class=Response, responses={200: {"content": {"application/zip": {}}}})
    async def get_diagnostics(request: Request) -> Response:
        services = services_of(request)
        now = services.clock.now()

        def build() -> bytes:
            return build_diagnostics(services, collect_info(services), doctor_answer(request.app, services), now)

        body = await run_blocking(build)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
        return Response(body, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="sutra-pro-diagnostics-{stamp}.zip"', "Cache-Control": "no-store"})

    return api


router = build_router()
