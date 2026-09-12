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

v1.1 -- ONE DEPARTMENT PER MODULE (D-M13/D-M14/D-M15, founder 2026-09-08;
codex folds 2026-09-11). `module.json` carries `department: {"ref": …}` and
ONLY the ref is persisted (P6): path and name are re-resolved on every read
from the placement registry, the way org_api.org_tree() does, and a retired
ref follows its successor chain at read time (placement_engine.live_destination,
public). An unknown ref is Unassigned, never the root (P2). Modules never
mints a domain (D-M14): an empty registry has no root, so everything is
Unassigned and the screen says so. Filtering is server-side (D-M15):
GET ?department=<ref>&subtree=1 answers groups here / below / system /
unassigned plus per-department subtree counts; the flat `modules` list keeps
its v1 shape and is never filtered (P10).
"""
import datetime
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

import providers
from json_store import read_json, write_json
import modules_events
import modules_pkg

# The department registry. The same explicit path insert org_api.py makes:
# importing placement_engine must not depend on import order (codex P1).
_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import placement_engine as E  # noqa: E402

router = APIRouter(prefix="/api/modules", tags=["modules"])

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
SCREEN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
KINDS = ("chat", "page", "link")
STATUSES = ("draft", "ready", "archived")
CREATED_BY = ("app", "shadow", "chat", "disk", "system", "marketplace")   # marketplace: ADR-039 install path (no UI yet)
ACTIONS = ("archive", "restore", "rename", "mark_ready", "set_instructions", "assign", "migrate_kit")
SYS_PREFIX = "sys-"
NAME_MAX, TAGLINE_MAX, INSTR_MAX, HTML_MAX = 80, 140, 4000, 512 * 1024
LINK_FORBIDDEN = ("terminal", "usage")   # terminal is a pane toggle; usage renders inside settings
# The screens a link may open: every SCREENS.<id> registration in static/js
# minus LINK_FORBIDDEN. One tuple, parity-tested against the registrations
# (test_modules.js) and copied into apps-frameworks/screens.json by
# build_kit.py so check.py can read it offline (Apps frameworks, step 4).
SCREEN_IDS = ("agents", "automation", "balance", "charters", "connectors", "departments", "editor",
              "evals", "git", "goal", "goals", "health", "history", "modules", "now", "optimus",
              "placements", "reorg", "routines", "settings", "shadow", "shadowsettings",
              "shadowwatching", "skills", "teamsutra", "workspace")
RECORD_FILE = "APP.md"                    # the per-app record (Apps frameworks); never an edit of the app
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

# Apps frameworks kit (design v1, D75): resolved beside this file, the way
# _LIB_DIR is, so the dev checkout and the bundled payload agree and check.py
# next to it reads the same kit.json. No environment variable, no search path.
_KIT_DIR = Path(__file__).resolve().parent / "apps-frameworks"
RECORD_TEMPLATE_KEYS = ("STAMP", "NAME", "TAGLINE", "KIT_VERSION", "DEPARTMENT", "SCREEN", "DATE")


def _kit_json():
    try:
        return json.loads((_KIT_DIR / "kit.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def frameworks_payload():
    """What the panel and the seeded chats read about the installed kit. None
    when the kit is absent (an older bundle): every caller degrades to the
    pre-kit behaviour, nothing errors."""
    kit = _kit_json()
    if not kit:
        return None
    try:
        screens = json.loads((_KIT_DIR / "screens.json").read_text(encoding="utf-8")).get("screens") or list(SCREEN_IDS)
    except (OSError, ValueError):
        screens = list(SCREEN_IDS)
    return {"dir": str(_KIT_DIR), "version": kit.get("version"), "digest": kit.get("digest_short"),
            "kinds": {k: str(_KIT_DIR / "profiles" / (k + ".md")) for k in KINDS},
            "check": str(_KIT_DIR / "check.py"),
            "screens": [s for s in screens if s not in LINK_FORBIDDEN],
            "tokens": sorted(set(re.findall(r"--([a-z][a-z0-9-]*)\s*:", TOKEN_CSS))),
            "must_fix": kit.get("v1_must_fix") or []}


def _kit_stamp(kind, now):
    kit = _kit_json()
    if not kit:
        return None
    return {"kit": "apps-frameworks", "version": kit.get("version"), "digest": kit.get("digest_short"),
            "created_at": now, "kind": kind}


def _render_record(kind, stamp, name, tagline, department_name, screen, now):
    """templates/<kind>/APP.md with the placeholders filled; None when the kit
    has no template for the kind (nothing is written, nothing fails)."""
    try:
        text = (_KIT_DIR / "templates" / kind / "APP.md").read_text(encoding="utf-8")
    except OSError:
        return None
    values = {"STAMP": json.dumps(stamp, separators=(",", ":")), "NAME": name, "TAGLINE": tagline or "",
              "KIT_VERSION": str(stamp.get("version") or ""), "DEPARTMENT": department_name or "Unassigned",
              "SCREEN": screen or "", "DATE": now[:10]}
    for k in RECORD_TEMPLATE_KEYS:
        text = text.replace("{{%s}}" % k, values[k])
    return text


def _kit_check_module():
    """check.py from the kit dir, imported once. None when absent."""
    p = _KIT_DIR / "check.py"
    if not p.is_file():
        return None
    if str(_KIT_DIR) not in sys.path:
        sys.path.insert(0, str(_KIT_DIR))
    try:
        import check as kit_check  # noqa: E402
        return kit_check
    except Exception:
        return None


def run_checks(mid, raw):
    """Live checks for one app, in-process, no render and NO writes (the GET
    lane and the mark_ready gate). None when the kit is absent or the app
    predates it (no stamp): legacy apps are never gated."""
    kit_check = _kit_check_module()
    if kit_check is None or not isinstance(raw.get("frameworkKit"), dict):
        return None
    kind = raw.get("kind") if raw.get("kind") in KINDS else "chat"
    prev = os.environ.get("KIT_NO_RENDER")
    os.environ["KIT_NO_RENDER"] = "1"
    try:
        results, summary, code = kit_check.run(_dir(mid), kind, home=_home(), kitdir=str(_KIT_DIR), allow_skip_render=True)
    finally:
        if prev is None:
            os.environ.pop("KIT_NO_RENDER", None)
        else:
            os.environ["KIT_NO_RENDER"] = prev
    if code == 2:
        return {"error": summary.get("error"), "blocked": False, "fails": [], "warns": [], "waived": [], "summary": summary}
    return {"blocked": bool(summary.get("blocked")),
            "fails": [r["id"] for r in results if r["status"] == "fail" and r["level"] == "must-fix"],
            "warns": [r["id"] for r in results if r["status"] in ("warn", "fail") and r["level"] == "suggest"],
            "waived": [r["id"] for r in results if r["status"] == "waived"],
            "summary": summary, "checks": results}


def _record_skeleton(mid, raw, stamp):
    """templates/<kind>/APP.md for an app whose answers were never recorded:
    every unanswered id row reads `not recorded`, which the checks report as
    WARN, never FAIL. Shared by import (reconstruct_record) and adoption
    (migrate_kit on an app without a stamp). None when the kit has no
    template for the kind."""
    kind = raw.get("kind") if raw.get("kind") in KINDS else "chat"
    reg = _Registry()
    dept = raw.get("department") if isinstance(raw.get("department"), dict) else {}
    dept_row = reg.row(dept.get("ref")) if dept.get("ref") else None
    surface = raw.get("surface") if isinstance(raw.get("surface"), dict) else {}
    text = _render_record(kind, stamp, str(raw.get("name") or mid), str(raw.get("tagline") or ""),
                          (dept_row or {}).get("name"), surface.get("screen"), _now())
    if text is None:
        return None
    out = []
    for line in text.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and re.match(r"^(P|S|DS|E|B|F)[0-9]{1,2}$", cells[0]) and not cells[2]:
                line = "| %s | %s | not recorded |" % (cells[0], cells[1])
        out.append(line)
    return "\n".join(out) + "\n"


def reconstruct_record(mid):
    """After an import (ADR-039 install path): APP.md does not travel with a
    package, so the installer rebuilds the skeleton from module.json plus the
    mirrored stamp; every answer it cannot recover reads `not recorded`, which
    the checks report as WARN, never FAIL. Sets origin.imported = true. No
    version bump, no updated_ms, no event. Returns True when it wrote."""
    path = _dir(mid)
    fpath = os.path.join(path, "module.json")
    raw = read_json(fpath, {})
    stamp = raw.get("frameworkKit") if isinstance(raw.get("frameworkKit"), dict) else None
    if not raw or not stamp or os.path.isfile(os.path.join(path, RECORD_FILE)):
        return False
    text = _record_skeleton(mid, raw, stamp)
    if text is None:
        return False
    _write_text(os.path.join(path, RECORD_FILE), text)
    origin = raw.get("origin") if isinstance(raw.get("origin"), dict) else {}
    origin["imported"] = True
    raw["origin"] = origin
    write_json(fpath, raw)
    return True


def recorded_checks(mid):
    """The ## Checks block of APP.md as last written by a check run (or None)."""
    rp = os.path.join(_dir(mid), RECORD_FILE)
    if not os.path.isfile(rp):
        return None
    text = open(rp, encoding="utf-8", errors="replace").read()
    m = re.search(r"(?ms)^## Checks\n(.*?)(?=^## |\Z)", text)
    if not m:
        return None
    lines = [l for l in m.group(1).splitlines() if l.strip()]
    if not lines or lines[0].startswith("(written by"):
        return {"ran": False}
    return {"ran": True, "header": lines[0], "summary": lines[1] if len(lines) > 1 else "",
            "waived": [l[len("waived: "):] for l in lines if l.startswith("waived: ")],
            "must_fix": [l[len("must-fix: "):] for l in lines if l.startswith("must-fix: ")]}


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


PUBLISH_FLAG = "apps_publish"
PUBLISH_OFF_MESSAGE = "apps export/import is off — set flags.apps_publish to true in ~/.sutra-ui/settings.json (ADR-039; off by default)"


def _publish_flag_on():
    """Opt-IN, unlike flags.modules: export/import are the marketplace trust
    boundary (APPS-THREATS.md X-10) and stay unreachable until switched on."""
    flags = providers._raw_settings().get("flags")
    return isinstance(flags, dict) and flags.get(PUBLISH_FLAG) is True


def _require_publish_flag():
    if not _publish_flag_on():
        raise HTTPException(404, PUBLISH_OFF_MESSAGE)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir(mid):
    """id -> absolute module dir, or ModuleError(404). Validate BEFORE join;
    realpath AFTER join; containment against the realpath'd home."""
    if not isinstance(mid, str) or not ID_RE.match(mid):
        raise ModuleError(404, "no app named %r" % (mid,))
    home = _home()
    path = os.path.realpath(os.path.join(home, mid))
    if not path.startswith(home + os.sep):
        raise ModuleError(404, "no app named %r" % (mid,))
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


# --------------------------------------------------------- departments -----

UNASSIGNED = "unassigned"          # a pseudo-ref the screen may SELECT, never ASSIGN
UNASSIGNED_ROW = {"ref": UNASSIGNED, "path": "", "name": "Unassigned", "description": ""}


class _Registry(object):
    """One read of the domain registry per request; list + normalize share it
    so a 40-module folder does not read the registry 40 times."""

    def __init__(self):
        self.domains = E.load_domains()
        self.root = E.live_root(self.domains)
        self.live = set(E.live_refs(self.domains).keys()) if self.domains else set()

    def row(self, ref, moved=False):
        """The display row for a LIVE ref. `path` is computed over the FULL
        set: a retired sibling keeps its ordinal (codex P3)."""
        d = self.domains.get(ref) or {}
        return {"ref": ref, "path": E.domain_path(ref, self.domains),
                "name": d.get("name") or ref, "moved": bool(moved)}

    def echo(self, ref):
        d = self.domains.get(ref) or {}
        return {"ref": ref, "path": E.domain_path(ref, self.domains),
                "name": d.get("name") or ref, "description": d.get("description") or ""}

    def resolve(self, ref):
        """Stored ref -> display row, or None (Unassigned). A retired ref
        follows its successor chain; an unknown ref is NOT the root (codex P2)."""
        if not isinstance(ref, str) or not ref:
            return None
        dest, how = E.live_destination(ref, self.domains, self.root)
        if not dest:
            return None
        return self.row(dest, moved=(how != "home"))

    def ancestors(self, ref):
        """ref, its parent, grandparent … (live members only, full-set walk)."""
        out, cur, seen = [], ref, set()
        while cur and cur in self.domains and cur not in seen:
            seen.add(cur)
            if cur in self.live:
                out.append(cur)
            cur = self.domains[cur].get("parent_ref")
        return out

    def order(self):
        """Live refs in tree order: root first, siblings by their D-path ordinal."""
        kids = {}
        for ref in self.live:
            kids.setdefault(self.domains[ref].get("parent_ref"), []).append(ref)

        def ordinal(ref):
            return [int(p[1:]) if p[1:].isdigit() else 0
                    for p in E.domain_path(ref, self.domains).split(".")]
        for v in kids.values():
            v.sort(key=ordinal)
        out = []

        def walk(ref):
            out.append(ref)
            for c in kids.get(ref, []):
                walk(c)
        if self.root:
            walk(self.root)
        return out


def _require_department(ref, reg):
    """A write-side department value: a LIVE ref, or 400. Names, the
    `unassigned` pseudo-ref and retired refs are refused -- assignment is a
    department, always (codex P5 / P12 / P18)."""
    if not isinstance(ref, str) or not ref:
        raise ModuleError(400, "department must be a department ref")
    if ref not in reg.live:
        raise ModuleError(400, "department %r is not a live department" % (ref,))
    return ref


# --------------------------------------------------------------- rows -----

def _seed_rows(reg):
    """System seeds sit at the registry root (D-M13); on an empty registry
    they carry no department, like everything else."""
    root = reg.row(reg.root) if reg.root else None
    rows = []
    for s in SYSTEM_SEEDS:
        rows.append({"schema": 1, "id": s["id"], "name": s["name"], "tagline": s["tagline"],
                     "kind": s["kind"], "status": "ready", "version": 1,
                     "origin": {"created_by": "system", "session_id": None, "at": None},
                     "surface": dict(s["surface"]), "guard": {},
                     "created_at": None, "updated_at": None,
                     "has_page": False, "reserved": False, "warning": None,
                     "department": dict(root) if root else None})
    return rows


def _normalize(raw, mid, path, reg):
    """One on-disk record -> one row the screen can render. Never raises; a
    strange file becomes a row with a warning, never a missing row (the folder
    is the truth and the screen reports the folder's state)."""
    raw = raw if isinstance(raw, dict) else {}
    dept = raw.get("department")
    dept_ref = dept.get("ref") if isinstance(dept, dict) else dept
    department = reg.resolve(dept_ref)       # None = Unassigned: a state, not a fault
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
    return {"schema": raw.get("schema") if raw.get("schema") in (1, 2) else 1, "id": mid,
            "name": str(raw.get("name") or mid)[:NAME_MAX],
            "tagline": str(raw.get("tagline") or "")[:TAGLINE_MAX],
            "kind": kind, "status": status, "version": version,
            "origin": {"created_by": created_by,
                       "session_id": origin.get("session_id") or None,
                       "at": origin.get("at") or None},
            "surface": surface, "guard": guard,
            "created_at": raw.get("created_at") or _mtime_iso(json_path),
            "updated_at": raw.get("updated_at") or _mtime_iso(json_path),
            "has_page": has_page, "reserved": reserved, "warning": warning,
            "department": department,
            # ADR-039: the optional publish block (semver, author, license, state …)
            # is carried through untouched so Publish never needs a storage migration
            "publish": raw.get("publish") if isinstance(raw.get("publish"), dict) else None,
            # Apps frameworks: the stamp mirror (None for apps that predate the kit)
            "frameworkKit": raw.get("frameworkKit") if isinstance(raw.get("frameworkKit"), dict) else None}


BUILDING_WARNING = "building… — this app's manifest is not readable yet"


def _building_row(mid, path, json_path):
    """A folder whose module.json exists but does not parse (a chat is still
    writing it): a row with a warning, never a missing app (D-M21, MIGRATIONS M-6)."""
    return {"schema": None, "id": mid, "name": mid, "tagline": "", "kind": "chat", "status": "draft",
            "version": 0, "origin": {"created_by": "disk", "session_id": None, "at": None},
            "surface": {}, "guard": {}, "created_at": _mtime_iso(json_path), "updated_at": _mtime_iso(json_path),
            "has_page": os.path.isfile(os.path.join(path, "index.html")),
            "reserved": mid.startswith(SYS_PREFIX), "warning": BUILDING_WARNING,
            "department": None, "publish": None, "frameworkKit": None, "building": True}


def _read(mid, reg=None):
    path = _dir(mid)
    jpath = os.path.join(path, "module.json")
    raw = read_json(jpath, {})
    if not raw:
        if os.path.isfile(jpath):
            return _building_row(mid, path, jpath)
        raise ModuleError(404, "no app named %r" % (mid,))
    return _normalize(raw, mid, path, reg or _Registry())


def list_modules(include_archived=False, reg=None):
    """Seeds first (fixed order), then the folder, newest first."""
    reg = reg or _Registry()
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
        jpath = os.path.join(path, "module.json")
        if not os.path.isfile(jpath):
            continue                                   # a folder without a manifest is not an app
        raw = read_json(jpath, {})
        if not raw:
            rows.append(_building_row(name, path, jpath))   # exists but does not parse: "building…"
            continue
        rows.append(_normalize(raw, name, path, reg))
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    archived = sum(1 for r in rows if r["status"] == "archived")
    user = [r for r in rows if include_archived or r["status"] != "archived"]
    return _seed_rows(reg) + user, len(rows), archived


def list_grouped(department=None, subtree=True, include_archived=False):
    """D-M15: one department's view, computed server-side. The flat `modules`
    list is the v1 answer, unfiltered (codex P10); `groups` is the selection:
      here        user modules assigned to the selected department
      below       user modules in its sub-departments, grouped, tree order
                  (empty when subtree is off)
      system      the seeds -- at the root only
      unassigned  user modules with no live department -- at the root only
    `counts_by_ref` counts USER modules into their department and every live
    ancestor (codex P7/P8); `unassigned_count` sits beside it, never inside.
    `department=unassigned` is terminal: no subtree, no system (codex P9)."""
    reg = _Registry()
    rows, count_user, archived = list_modules(include_archived, reg)
    seeds = [r for r in rows if r["origin"]["created_by"] == "system"]
    users = [r for r in rows if r["origin"]["created_by"] != "system"]
    unassigned = [r for r in users if not r["department"]]
    counts = {}
    for r in users:
        if r["department"]:
            for a in reg.ancestors(r["department"]["ref"]):
                counts[a] = counts.get(a, 0) + 1
    base = {"modules": rows, "count_user": count_user, "archived": archived, "home": _home(),
            "counts_by_ref": counts, "unassigned_count": len(unassigned),
            "root": reg.echo(reg.root) if reg.root else None}
    if department == UNASSIGNED:
        base.update({"groups": {"here": [], "below": [], "system": [], "unassigned": unassigned},
                     "department": dict(UNASSIGNED_ROW)})
        return base
    if department:
        dest, _how = E.live_destination(department, reg.domains, reg.root)
        if not dest:
            raise ModuleError(404, "no department %r" % (department,))
        sel = dest
    else:
        sel = reg.root                         # None on an empty registry (D-M14)
    here = [r for r in users if r["department"] and r["department"]["ref"] == sel] if sel else []
    below = []
    if sel and subtree:
        by = {}
        for r in users:
            d = r["department"]
            if d and d["ref"] != sel and sel in reg.ancestors(d["ref"]):
                by.setdefault(d["ref"], []).append(r)
        below = [{"department": reg.row(ref), "modules": by[ref]} for ref in reg.order() if ref in by]
    at_root = (sel == reg.root)                # also true when both are None
    base.update({"groups": {"here": here, "below": below,
                            "system": seeds if at_root else [],
                            "unassigned": unassigned if at_root else []},
                 "department": reg.echo(sel) if sel else None})
    return base


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
    # D-M13 creation defaults: a named department must be a live ref (the
    # Shadow fence and the seeded chats pass refs, never names -- codex P12);
    # absent means the registry root; no root (empty registry) means Unassigned.
    reg = _Registry()
    if spec.get("department") not in (None, ""):
        dept_ref = _require_department(spec.get("department"), reg)
    else:
        dept_ref = reg.root
    path = _dir(mid)
    if os.path.islink(path):
        raise ModuleError(400, "module folder may not be a symlink")
    if os.path.exists(os.path.join(path, "module.json")):
        raise ModuleError(409, "an app with id %s already exists" % mid)
    now = _now()
    # schema 2 from the start (MIGRATIONS M-7): a registry entry requires
    # manifest_schema 2, so a fresh app must never need a write-back to export
    row = {"schema": 2, "id": mid, "name": name, "tagline": tagline, "kind": kind,
           # a link has nothing left to finish; chat and page start as drafts
           "status": "ready" if kind == "link" else "draft",
           "version": 1,
           "origin": {"created_by": created_by, "session_id": session_id, "at": now},
           "surface": surface, "guard": {}, "created_at": now, "updated_at": now,
           "updated_ms": int(time.time() * 1000),
           # ONLY the ref (codex P6): path/name are read-time caches
           "department": {"ref": dept_ref} if dept_ref else None,
           "publish": None}
    # Apps frameworks (design v1 R1-P1): the SERVER materializes the folder --
    # the kind's starter files, then APP.md with the stamp, then module.json
    # LAST so a half-written folder is never a listed app. The chat that opens
    # afterwards fills answers and the surface; it never writes the stamp.
    stamp = _kit_stamp(kind, now)
    if stamp:
        row["frameworkKit"] = stamp
        if kind == "page" and not html:
            try:
                html = (_KIT_DIR / "templates" / "page" / "index.html").read_text(encoding="utf-8")
            except OSError:
                html = ""
        dept_row = reg.row(dept_ref) if dept_ref else None
        record = _render_record(kind, stamp, name, tagline, (dept_row or {}).get("name"), surface.get("screen"), now)
        if record is not None:
            _write_text(os.path.join(path, RECORD_FILE), record)
    if html:
        _write_text(os.path.join(path, "index.html"), html)
    write_json(os.path.join(path, "module.json"), row)
    modules_events.append(_home(), "app.created", mid, kind=kind, version=1, department_ref=dept_ref,
                          actor=(created_by + ":" + session_id) if session_id else created_by)
    return _read(mid, reg)


def _adopt_kit(mid, path, fpath, raw, kind, actor):
    """ADOPTION (D75, amended 2026-09-12: "whenever a task is given, a framework
    should be there ... if not, then a framework should be created"). An app
    built before the kit takes the stamp now and gets the record it never had:
    every unanswered row reads `not recorded` (WARN, never FAIL). Status is
    untouched, so a ready app stays ready; the checks gate only a LATER
    mark_ready, and a legacy page whose index.html predates the token rules is
    refused there until it is brought in line. Audited as its own event because
    it writes more than a migration (codex, 2026-09-12), with the actor that
    brought the task (panel, chat:<session>, marketplace). No version bump, no
    updated_ms. Callers: apply_action("migrate_kit") and touch_app(mode="edit");
    create_module stamps at birth and needs neither. Returns the stamp, or None
    when the kit is absent."""
    now = _now()
    stamp = _kit_stamp(kind, now)
    if not stamp:
        return None
    stamp["adopted"] = now[:10]
    raw["frameworkKit"] = stamp
    write_json(fpath, raw)
    rp = os.path.join(path, RECORD_FILE)
    if not os.path.isfile(rp):
        text = _record_skeleton(mid, raw, stamp)
        if text is not None:
            _write_text(rp, text)
    dept = raw.get("department") if isinstance(raw.get("department"), dict) else {}
    modules_events.append(_home(), "app.kit_adopted", mid, kind=kind, version=raw.get("version"),
                          department_ref=dept.get("ref"), actor=actor)
    return stamp


def apply_action(mid, action, body):
    if not isinstance(mid, str) or mid.startswith(SYS_PREFIX):
        raise ModuleError(404, "no app named %r" % (mid,))   # system rows: read-only
    if action not in ACTIONS:
        raise ModuleError(400, "action must be one of " + ", ".join(ACTIONS))
    path = _dir(mid)
    fpath = os.path.join(path, "module.json")
    raw = read_json(fpath, {})
    if not raw:
        raise ModuleError(404, "no app named %r" % (mid,))
    kind = raw.get("kind") if raw.get("kind") in KINDS else "chat"
    body = body if isinstance(body, dict) else {}
    if action == "migrate_kit":
        kit = _kit_json()
        if not kit:
            raise ModuleError(409, "the frameworks kit is not installed; nothing to migrate")
        stamp = raw.get("frameworkKit") if isinstance(raw.get("frameworkKit"), dict) else None
        rp = os.path.join(path, RECORD_FILE)
        if not stamp:
            _adopt_kit(mid, path, fpath, raw, kind, actor="panel")
            return _read(mid)
        # MIGRATION (design v1 §The APP.md record): the builder said yes in
        # Edit in chat. Rewrite the two stamp copies (version, digest,
        # migrated) and NOTHING else: no version bump, no updated_ms, no event.
        stamp.update({"version": kit.get("version"), "digest": kit.get("digest_short"), "migrated": _now()[:10]})
        raw["frameworkKit"] = stamp
        write_json(fpath, raw)
        rp = os.path.join(path, RECORD_FILE)
        if os.path.isfile(rp):
            lines = open(rp, encoding="utf-8", errors="replace").read().split("\n")
            for i, l in enumerate(lines):
                if l.strip():
                    if l.strip().startswith("frameworkKit:"):
                        lines[i] = "frameworkKit: " + json.dumps(stamp, separators=(",", ":"))
                    break
            _write_text(rp, "\n".join(lines))
        return _read(mid)
    if action == "archive":
        raw["status"] = "archived"
    elif action == "restore":
        raw["status"] = "ready" if kind == "link" else "draft"
    elif action == "rename":
        raw["name"] = _str(body, "name", NAME_MAX, required=True).strip() or raw.get("name")
    elif action == "mark_ready":
        if kind == "page" and not os.path.isfile(os.path.join(path, "index.html")):
            raise ModuleError(409, "index.html is missing — write it at %s" % os.path.join(path, "index.html"))
        # Apps frameworks (design v1): only must-fix failures refuse; waivers,
        # suggestions and imported "not recorded" rows never do. Apps without a
        # stamp predate the kit and are never gated.
        chk = run_checks(mid, raw)
        if chk and chk.get("blocked"):
            raise ModuleError(409, "checks must pass before ready: %s — run the check and fix or waive them" % ", ".join(chk["fails"]))
        raw["status"] = "ready"
    elif action == "set_instructions":
        if kind != "chat":
            raise ModuleError(400, "only chat modules carry instructions")
        surface = raw.get("surface") if isinstance(raw.get("surface"), dict) else {}
        surface["instructions"] = _str(body, "instructions", INSTR_MAX)
        raw["surface"] = surface
    elif action == "assign":
        # Move (D-M15 / D-M17): one department, a live ref, nothing else
        prev_ref = (raw.get("department") or {}).get("ref") if isinstance(raw.get("department"), dict) else None
        raw["department"] = {"ref": _require_department(body.get("department_ref"), _Registry())}
    v = raw.get("version")
    raw["version"] = (v if isinstance(v, int) and v > 0 else 0) + 1
    raw["updated_at"] = _now()
    raw["updated_ms"] = int(time.time() * 1000)   # the precise stamp touch_app compares file mtimes against
    raw["schema"] = 2                      # MIGRATIONS M-2: the write-back bumps 1 -> 2, everything else preserved
    write_json(fpath, raw)
    dept_ref = (raw.get("department") or {}).get("ref") if isinstance(raw.get("department"), dict) else None
    event = {"archive": "app.archived", "assign": "app.assigned"}.get(action, "app.edited")
    extra = {"changed": [action]}
    if action == "assign":
        extra = {"from_ref": prev_ref, "to_ref": dept_ref}
    modules_events.append(_home(), event, mid, kind=kind, version=raw["version"], department_ref=dept_ref,
                          actor="app", **extra)
    return _read(mid)


def _iso_to_epoch(s):
    try:
        return datetime.datetime.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return 0.0


def touch_app(mid, mode="edit", session_id=None):
    """The seeded chat's completion hook (APPS-EVENTS.md §done; program step 57):
    re-read the folder; if any file is newer than updated_at, bump version and
    updated_at (schema 2) and append app.edited (mode edit) or app.created
    (mode new). An unchanged folder appends nothing. Never emitted by a GET."""
    if not isinstance(mid, str) or mid.startswith(SYS_PREFIX):
        raise ModuleError(404, "no app named %r" % (mid,))
    path = _dir(mid)
    fpath = os.path.join(path, "module.json")
    if not os.path.isfile(fpath):
        raise ModuleError(404, "no app named %r" % (mid,))
    raw = read_json(fpath, {})
    if not raw:
        raise ModuleError(409, BUILDING_WARNING)
    # D75 amendment (2026-09-12): a task on an app runs through its framework.
    # An edit that reached the server without the panel's own adoption (another
    # client, an older panel) adopts here, before anything is measured; create
    # already stamps, so mode "new" needs nothing.
    if mode == "edit" and _kit_json() and not isinstance(raw.get("frameworkKit"), dict):
        _adopt_kit(mid, path, fpath, raw, raw.get("kind") if raw.get("kind") in KINDS else "chat",
                   actor=("chat:" + session_id) if session_id else "chat")
        raw = read_json(fpath, {}) or raw
    # Compare every file EXCEPT the manifest itself against the manifest's own
    # millisecond write stamp (updated_ms, set on every write; falls back to
    # updated_at for schema-1 files). No tolerance window (codex R3 P2b).
    newest = 0.0
    for root, dirs, files in os.walk(path):
        if root == path:
            # Apps frameworks (design v1 R1-P2): the record, dot-prefixed
            # names and a top-level holding/ are never an edit of the app.
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "holding"]
        for f in files:
            if root == path and f in ("module.json", RECORD_FILE):
                continue
            if f.startswith("."):
                continue
            try:
                newest = max(newest, os.stat(os.path.join(root, f)).st_mtime)
            except OSError:
                pass
    stamp = raw.get("updated_ms")
    since = (stamp / 1000.0) if isinstance(stamp, (int, float)) else _iso_to_epoch(raw.get("updated_at"))
    changed = newest > since
    if changed:
        v = raw.get("version")
        raw["version"] = (v if isinstance(v, int) and v > 0 else 0) + 1
        raw["updated_at"] = _now()
        raw["updated_ms"] = int(time.time() * 1000)
        raw["schema"] = 2
        write_json(fpath, raw)
        dept_ref = (raw.get("department") or {}).get("ref") if isinstance(raw.get("department"), dict) else None
        modules_events.append(_home(), "app.created" if mode == "new" else "app.edited", mid,
                              kind=raw.get("kind"), version=raw["version"], department_ref=dept_ref,
                              actor=("chat:" + session_id) if session_id else "chat", changed=["files"])
    out = {"app": _read(mid), "changed": changed}
    chk = run_checks(mid, raw)                 # live, no render, no writes (design v1 §Injection points)
    if chk:
        out["check"] = {"blocked": chk["blocked"], "fails": chk["fails"], "warns": chk["warns"], "waived": chk["waived"]}
    return out


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
    """v1 fields (modules / count_user / archived / home) unchanged; v1.1 adds
    groups / counts_by_ref / unassigned_count / root / department (codex P19).
    ?department=<ref|unassigned>  the selection (default: the root)
    ?subtree=0                    this department only (default: on)
    ?include=archived             as in v1"""
    _require_flag()
    qp = request.query_params
    include = (qp.get("include") or "") == "archived"
    subtree = (qp.get("subtree") or "1") != "0"
    return _guard(list_grouped, qp.get("department") or None, subtree, include)


@router.post("")
async def api_modules_create(request: Request):
    _require_flag()
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    row = _guard(create_module, body, "app", None)
    return JSONResponse(row, status_code=201)


@router.get("/frameworks")
async def api_modules_frameworks():
    """The installed Apps frameworks kit (design v1): version, digest, per-kind
    profile paths, the check runner, the screens a link may open and the token
    names a page may use. Declared BEFORE /{mid} so "frameworks" is never read
    as an app id. null when the kit is absent (older bundle)."""
    _require_flag()
    return JSONResponse(frameworks_payload())


@router.post("/import")
async def api_modules_import(request: Request):
    """ADR-039 install path (APPS-THREATS.md X-1..X-10). Declared BEFORE the
    /{mid} action route so "import" is never read as an app id. Body = the
    tarball bytes; ?id= ?sha256= ?replace=1 (no multipart dependency)."""
    _require_flag()
    _require_publish_flag()
    qp = request.query_params
    blob = await request.body()
    try:
        res = modules_pkg.import_app(_home(), qp.get("id") or "", blob, qp.get("sha256") or "",
                                     replace=(qp.get("replace") in ("1", "true", "yes")),
                                     downgrade=(qp.get("downgrade") in ("1", "true", "yes")))
    except modules_pkg.PkgError as e:
        raise HTTPException(e.status, str(e))
    try:
        res["record_reconstructed"] = reconstruct_record(res.get("id") or "")
    except (ModuleError, OSError, ValueError):
        res["record_reconstructed"] = False    # the install stands; the first edit can still write the record
    return JSONResponse(res, status_code=201)


@router.post("/install")
async def api_modules_install(request: Request):
    """Publish program P2 (ADR-041): fetch one app from a registry and import it
    VERIFIED -- index validated, publishers pinned (shipped pins for the default
    registry, first-contact pins for another), entry signature checked against
    the bytes before the archive opens, downgrades refused. Body: {registry, id,
    version?, replace?, downgrade?}. Declared BEFORE /{mid}."""
    _require_flag()
    _require_publish_flag()
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    body = body if isinstance(body, dict) else {}
    try:
        res = modules_pkg.install_app(_home(), str(body.get("registry") or ""), str(body.get("id") or ""),
                                      version=(str(body["version"]) if body.get("version") else None),
                                      replace=bool(body.get("replace")), downgrade=bool(body.get("downgrade")))
    except modules_pkg.PkgError as e:
        raise HTTPException(e.status, str(e))
    try:
        res["record_reconstructed"] = reconstruct_record(res.get("id") or "")
    except (ModuleError, OSError, ValueError):
        res["record_reconstructed"] = False
    return JSONResponse(res, status_code=201)


@router.post("/{mid}/export")
async def api_modules_export(mid: str):
    _require_flag()
    _require_publish_flag()
    try:
        return modules_pkg.export_app(_home(), mid)
    except modules_pkg.PkgError as e:
        raise HTTPException(e.status, str(e))


@router.post("/{mid}/touch")
async def api_modules_touch(mid: str, request: Request):
    _require_flag()
    try:
        body = await request.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    return _guard(touch_app, mid, body.get("mode") or "edit", body.get("session_id"))


@router.get("/{mid}/checks")
async def api_modules_checks(mid: str):
    """Read-only: the live check results (no render, no writes) beside what
    the record last recorded, so the header chip can say "record out of date"
    instead of the chip and the file silently disagreeing (design v1)."""
    _require_flag()
    if not isinstance(mid, str) or mid.startswith(SYS_PREFIX):
        raise HTTPException(404, "no app named %r" % (mid,))
    path = _guard(_dir, mid)
    raw = read_json(os.path.join(path, "module.json"), {})
    if not raw:
        raise HTTPException(404, "no app named %r" % (mid,))
    live = run_checks(mid, raw)
    kit = _kit_json() or {}
    return {"id": mid, "kit": kit.get("version"), "kind": raw.get("kind"),
            "stamped": (raw.get("frameworkKit") or {}).get("version") if isinstance(raw.get("frameworkKit"), dict) else None,
            "live": live, "recorded": recorded_checks(mid)}


@router.get("/{mid}")
async def api_modules_get(mid: str):
    _require_flag()
    reg = _Registry()
    for s in _seed_rows(reg):
        if s["id"] == mid:
            return s
    return _guard(_read, mid, reg)


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
