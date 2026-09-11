"""modules_api.py -- Org > Modules: the registry of finished products a user
builds inside Sutra Desktop. Design of record:
holding/departments/experience/desktop-app/2026-09-08-modules-design.md.

THE FOLDER IS THE MODULE (D-M1). A module exists iff
~/.sutra-ui/modules/<id>/module.json parses. The in-app form, the Shadow
fence and any Claude Code session that writes the folder all land in the same
list because this module only ever READS that directory; there is no second
store. System modules are SEEDS in this file (D-M3), served through the same
GET so the screen never carries a registry of its own.

SAFETY
  - id is the folder name: ^[a-z0-9][a-z0-9-]{1,40}$, validated BEFORE any
    join; the joined path is realpath'd and must stay under the home
    (shadow_ledger._path posture). A symlinked module dir is refused on write.
  - `sys-` ids are reserved: refused at write, listed read-only with a
    warning at read.
  - GET /{id}/page serves user-authored HTML under a CSP with no connect-src
    and frame-ancestors 'self'; the panel mounts it with sandbox="allow-scripts"
    (no same-origin), so the page has an opaque origin and can reach neither
    the panel token nor /api/* (D-M5).
  - flags.modules: opt-out, default ON, read per request (workspace
    precedent). Off answers 404 with the hint sentence.
  - archive never deletes. System rows answer 404 to every mutation.
"""
import datetime
import json
import os
import re
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

import providers
from json_store import read_json, write_json

router = APIRouter(prefix="/api/modules", tags=["modules"])

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
SCREEN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
KINDS = ("chat", "page", "link")
STATUSES = ("draft", "ready", "archived")
CREATED_BY = ("app", "shadow", "chat", "disk", "system")
ACTIONS = ("archive", "restore", "rename", "mark_ready", "set_instructions")
SYS_PREFIX = "sys-"
NAME_MAX, TAGLINE_MAX, INSTR_MAX, HTML_MAX = 80, 140, 4000, 512 * 1024
LINK_FORBIDDEN = ("terminal", "usage")   # terminal is a pane toggle; usage renders inside settings
FLAG = "modules"
FLAG_OFF_MESSAGE = "modules flag is off — set flags.modules in ~/.sutra-ui/settings.json"

# System seeds (D-M3). `sys-settings` carries NO section list: the screen derives
# the sections from DEST_PLANES.settings at render (D-M9), so the two cannot drift.
# Shadow is deliberately NOT here (D-M4): Asawa's instance holds it as an on-disk
# link module; one more row here makes it fleet-wide.
SYSTEM_SEEDS = (
    {"id": "sys-balance", "name": "Balance", "tagline": "how the week is spending you",
     "kind": "link", "surface": {"screen": "balance"}},
    {"id": "sys-help", "name": "Help", "tagline": "Team Sutra tasks and help",
     "kind": "link", "surface": {"screen": "teamsutra"}},
    {"id": "sys-settings", "name": "Settings", "tagline": "provider, tools, automation, system",
     "kind": "link", "surface": {"screen": "settings", "sections": "client"}},
)

# The app's own tokens (panel.css:1-33), injected into every served page so a
# module written against var(--ink) / var(--acc) looks like the app in both
# themes. Kept as a literal so the page endpoint never reads panel.css at
# request time.
TOKEN_CSS = """:root{--serif:ui-serif,"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--r:10px}
:root,html[data-theme="dark"]{--bg:#0C0B09;--surface:#161412;--card:#1C1A17;--line:#2A2622;--line-soft:#221F1C;
--ink:#F5F0E8;--muted:#8C857D;--faint:#6E6860;--acc:#C4956A;--acc-bg:rgba(196,149,106,.12);--on-acc:#0C0B09;
--ok:#5A9E6F;--warn:#C9A227;--block:#B8574B;--ok-bg:rgba(90,158,111,.13);--warn-bg:rgba(201,162,39,.13);--block-bg:rgba(184,87,75,.14);
--ok-line:rgba(90,158,111,.32);--warn-line:rgba(201,162,39,.3);--block-line:rgba(184,87,75,.38);--inset:#161412;--sepia:rgba(196,149,106,.06)}
@media (prefers-color-scheme:light){html:not([data-theme]){--bg:#fafaf9;--surface:#ffffff;--card:#ffffff;--line:#e2e0dd;--line-soft:#eeecea;
--ink:#1c1917;--muted:#78716c;--faint:#a8a29e;--acc:#8A5D2E;--acc-bg:#f6efe7;--on-acc:#ffffff;--ok:#3f7d54;--warn:#8a6d12;--block:#9c3f34;
--ok-bg:#eef4ef;--warn-bg:#f8f3e4;--block-bg:#faeeec;--ok-line:#cfe0d4;--warn-line:#e8dcbb;--block-line:#eccfc9;--inset:#fafaf9;--sepia:#faf6ef}}
html[data-theme="light"]{--bg:#fafaf9;--surface:#ffffff;--card:#ffffff;--line:#e2e0dd;--line-soft:#eeecea;
--ink:#1c1917;--muted:#78716c;--faint:#a8a29e;--acc:#8A5D2E;--acc-bg:#f6efe7;--on-acc:#ffffff;--ok:#3f7d54;--warn:#8a6d12;--block:#9c3f34;
--ok-bg:#eef4ef;--warn-bg:#f8f3e4;--block-bg:#faeeec;--ok-line:#cfe0d4;--warn-line:#e8dcbb;--block-line:#eccfc9;--inset:#fafaf9;--sepia:#faf6ef}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.55;margin:0;padding:16px;-webkit-font-smoothing:antialiased}
"""

PAGE_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src data: blob:; font-src data:; frame-ancestors 'self'")


class ModuleError(ValueError):
    """A refusal with an HTTP status. Routes map it 1:1; the Shadow fence path
    catches it so an invalid fence leaves the reply text standing."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------ plumbing ----

def _home():
    """Resolved PER CALL (shadow_ledger pattern) so tests can point
    SUTRA_MODULES_HOME anywhere before the first write."""
    return os.path.realpath(os.path.expanduser(
        os.environ.get("SUTRA_MODULES_HOME", "~/.sutra-ui/modules")))


def _flag_on():
    """flags.modules from ~/.sutra-ui/settings.json, per request. Absent means
    ON; only an explicit false turns the surface off (workspace precedent)."""
    flags = providers._raw_settings().get("flags")
    return not (isinstance(flags, dict) and flags.get(FLAG) is False)


def _require_flag():
    if not _flag_on():
        raise HTTPException(404, FLAG_OFF_MESSAGE)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir(mid):
    """id -> absolute module dir, or ModuleError(404). Validate BEFORE join;
    realpath AFTER join; containment against the realpath'd home."""
    if not isinstance(mid, str) or not ID_RE.match(mid):
        raise ModuleError(404, "no module named %r" % (mid,))
    home = _home()
    path = os.path.realpath(os.path.join(home, mid))
    if not path.startswith(home + os.sep):
        raise ModuleError(404, "no module named %r" % (mid,))
    return path


def _write_text(path, text):
    """tmp + os.replace, unique tmp per writer -- the json_store convention,
    for the one non-JSON file this store keeps (index.html)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = "%s.sutra-tmp.%d.%d" % (path, os.getpid(), threading.get_ident())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _mtime_iso(path):
    try:
        ts = os.stat(path).st_mtime
    except OSError:
        return None
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------- rows -----

def _seed_rows():
    rows = []
    for s in SYSTEM_SEEDS:
        rows.append({"schema": 1, "id": s["id"], "name": s["name"], "tagline": s["tagline"],
                     "kind": s["kind"], "status": "ready", "version": 1,
                     "origin": {"created_by": "system", "session_id": None, "at": None},
                     "surface": dict(s["surface"]), "guard": {},
                     "created_at": None, "updated_at": None,
                     "has_page": False, "reserved": False, "warning": None})
    return rows


def _normalize(raw, mid, path):
    """One on-disk record -> one row the screen can render. Never raises; a
    strange file becomes a row with a warning, never a missing row (the folder
    is the truth and the screen reports the folder's state)."""
    raw = raw if isinstance(raw, dict) else {}
    surface = raw.get("surface") if isinstance(raw.get("surface"), dict) else {}
    origin = raw.get("origin") if isinstance(raw.get("origin"), dict) else {}
    kind = raw.get("kind") if raw.get("kind") in KINDS else "chat"
    status = raw.get("status") if raw.get("status") in STATUSES else "draft"
    guard = raw.get("guard") if isinstance(raw.get("guard"), dict) else {}
    json_path = os.path.join(path, "module.json")
    has_page = os.path.isfile(os.path.join(path, "index.html"))
    warning = None
    if raw.get("id") and raw.get("id") != mid:
        warning = "module.json id does not match its folder; the folder wins"
    if kind == "page" and not has_page and status != "archived":
        status = "draft"
        warning = "index.html is missing"
    if kind == "link":
        scr = surface.get("screen")
        if not isinstance(scr, str) or not SCREEN_RE.match(scr) or scr in LINK_FORBIDDEN:
            warning = "link target is not a screen this app can open"
    if guard:
        warning = warning or "guard rules not enforced yet"
    reserved = mid.startswith(SYS_PREFIX)
    if reserved:
        warning = "reserved id, not loaded"
    created_by = origin.get("created_by") if origin.get("created_by") in CREATED_BY else "disk"
    version = raw.get("version")
    version = int(version) if isinstance(version, int) and version > 0 else 1
    return {"schema": 1, "id": mid,
            "name": str(raw.get("name") or mid)[:NAME_MAX],
            "tagline": str(raw.get("tagline") or "")[:TAGLINE_MAX],
            "kind": kind, "status": status, "version": version,
            "origin": {"created_by": created_by,
                       "session_id": origin.get("session_id") or None,
                       "at": origin.get("at") or None},
            "surface": surface, "guard": guard,
            "created_at": raw.get("created_at") or _mtime_iso(json_path),
            "updated_at": raw.get("updated_at") or _mtime_iso(json_path),
            "has_page": has_page, "reserved": reserved, "warning": warning}


def _read(mid):
    path = _dir(mid)
    raw = read_json(os.path.join(path, "module.json"), {})
    if not raw:
        raise ModuleError(404, "no module named %r" % (mid,))
    return _normalize(raw, mid, path)


def list_modules(include_archived=False):
    """Seeds first (fixed order), then the folder, newest first."""
    home = _home()
    try:
        names = sorted(os.listdir(home))
    except OSError:
        names = []
    rows = []
    for name in names:
        if not ID_RE.match(name):
            continue
        path = os.path.join(home, name)
        if not os.path.isdir(path):
            continue
        raw = read_json(os.path.join(path, "module.json"), {})
        if not raw:
            continue
        rows.append(_normalize(raw, name, path))
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    archived = sum(1 for r in rows if r["status"] == "archived")
    user = [r for r in rows if include_archived or r["status"] != "archived"]
    return _seed_rows() + user, len(rows), archived


# ------------------------------------------------------------- writes -----

def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    if len(s) < 2:
        s = ("m-" + s).strip("-")[:40] or "m-1"
    if not ID_RE.match(s):
        s = "m-" + re.sub(r"[^a-z0-9-]", "", s)[:38]
    return s


def _str(spec, key, cap, required=False):
    v = spec.get(key)
    if v is None or v == "":
        if required:
            raise ModuleError(400, "%s is required" % key)
        return ""
    if not isinstance(v, str):
        raise ModuleError(400, "%s must be a string" % key)
    if len(v) > cap:
        raise ModuleError(400, "%s is longer than %d characters" % (key, cap))
    return v


def create_module(spec, created_by, session_id=None):
    """The ONE creation path (D-M1). The POST route and the Shadow fence both
    come through here so validation never forks."""
    if not isinstance(spec, dict):
        raise ModuleError(400, "module spec must be an object")
    if created_by not in CREATED_BY:
        raise ModuleError(400, "unknown creator")
    name = _str(spec, "name", NAME_MAX, required=True).strip()
    if not name:
        raise ModuleError(400, "name is required")
    kind = spec.get("kind") or "chat"
    if kind not in KINDS:
        raise ModuleError(400, "kind must be chat, page or link")
    tagline = _str(spec, "tagline", TAGLINE_MAX).strip()
    mid = spec.get("id") or _slug(name)
    if not isinstance(mid, str) or not ID_RE.match(mid):
        raise ModuleError(400, "id must match ^[a-z0-9][a-z0-9-]{1,40}$")
    if mid.startswith(SYS_PREFIX):
        raise ModuleError(400, "ids starting with sys- are reserved for system modules")
    if kind == "chat":
        surface = {"instructions": _str(spec, "instructions", INSTR_MAX)}
        cwd = _str(spec, "cwd", 1024)
        if cwd:
            surface["cwd"] = cwd
    elif kind == "page":
        surface = {"entry": "index.html"}
    else:
        screen = _str(spec, "screen", 40, required=True)
        if not SCREEN_RE.match(screen) or screen in LINK_FORBIDDEN:
            raise ModuleError(400, "screen must name a screen this app can open")
        surface = {"screen": screen}
    html = _str(spec, "html", HTML_MAX) if kind == "page" else ""
    path = _dir(mid)
    if os.path.islink(path):
        raise ModuleError(400, "module folder may not be a symlink")
    if os.path.exists(os.path.join(path, "module.json")):
        raise ModuleError(409, "a module with id %s already exists" % mid)
    now = _now()
    row = {"schema": 1, "id": mid, "name": name, "tagline": tagline, "kind": kind,
           # a link has nothing left to finish; chat and page start as drafts
           "status": "ready" if kind == "link" else "draft",
           "version": 1,
           "origin": {"created_by": created_by, "session_id": session_id, "at": now},
           "surface": surface, "guard": {}, "created_at": now, "updated_at": now}
    write_json(os.path.join(path, "module.json"), row)
    if html:
        _write_text(os.path.join(path, "index.html"), html)
    return _read(mid)


def apply_action(mid, action, body):
    if not isinstance(mid, str) or mid.startswith(SYS_PREFIX):
        raise ModuleError(404, "no module named %r" % (mid,))   # system rows: read-only
    if action not in ACTIONS:
        raise ModuleError(400, "action must be one of " + ", ".join(ACTIONS))
    path = _dir(mid)
    fpath = os.path.join(path, "module.json")
    raw = read_json(fpath, {})
    if not raw:
        raise ModuleError(404, "no module named %r" % (mid,))
    kind = raw.get("kind") if raw.get("kind") in KINDS else "chat"
    body = body if isinstance(body, dict) else {}
    if action == "archive":
        raw["status"] = "archived"
    elif action == "restore":
        raw["status"] = "ready" if kind == "link" else "draft"
    elif action == "rename":
        raw["name"] = _str(body, "name", NAME_MAX, required=True).strip() or raw.get("name")
    elif action == "mark_ready":
        if kind == "page" and not os.path.isfile(os.path.join(path, "index.html")):
            raise ModuleError(409, "index.html is missing — write it at %s" % os.path.join(path, "index.html"))
        raw["status"] = "ready"
    elif action == "set_instructions":
        if kind != "chat":
            raise ModuleError(400, "only chat modules carry instructions")
        surface = raw.get("surface") if isinstance(raw.get("surface"), dict) else {}
        surface["instructions"] = _str(body, "instructions", INSTR_MAX)
        raw["surface"] = surface
    v = raw.get("version")
    raw["version"] = (v if isinstance(v, int) and v > 0 else 0) + 1
    raw["updated_at"] = _now()
    write_json(fpath, raw)
    return _read(mid)


def page_html(mid, theme=None):
    path = _dir(mid)
    fpath = os.path.join(path, "index.html")
    if not os.path.isfile(fpath):
        raise ModuleError(404, "index.html is missing — write it at %s" % fpath)
    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    theme = theme if theme in ("dark", "light") else ""
    head = ('<meta charset="utf-8"><meta name="color-scheme" content="dark light">'
            '<style id="sutra-tokens">%s</style>' % TOKEN_CSS)
    if theme:
        head += '<script>document.documentElement.setAttribute("data-theme",%s)</script>' % json.dumps(theme)
    return head + body


# ------------------------------------------------------------- routes -----

def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ModuleError as e:
        raise HTTPException(e.status, str(e))


@router.get("")
async def api_modules_list(request: Request):
    _require_flag()
    include = (request.query_params.get("include") or "") == "archived"
    rows, count_user, archived = list_modules(include_archived=include)
    return {"modules": rows, "count_user": count_user, "archived": archived, "home": _home()}


@router.post("")
async def api_modules_create(request: Request):
    _require_flag()
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    row = _guard(create_module, body, "app", None)
    return JSONResponse(row, status_code=201)


@router.get("/{mid}")
async def api_modules_get(mid: str):
    _require_flag()
    for s in _seed_rows():
        if s["id"] == mid:
            return s
    return _guard(_read, mid)


@router.post("/{mid}")
async def api_modules_action(mid: str, request: Request):
    _require_flag()
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    body = body if isinstance(body, dict) else {}
    return _guard(apply_action, mid, body.get("action"), body)


@router.get("/{mid}/page")
async def api_modules_page(mid: str, request: Request):
    _require_flag()
    html = _guard(page_html, mid, request.query_params.get("theme"))
    return HTMLResponse(html, headers={
        "Content-Security-Policy": PAGE_CSP,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store, max-age=0",
    })
