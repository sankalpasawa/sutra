"""j2ui_page.py -- the J2 prototype's page, served at /j2ui/{ref}/ (UI-port package j2ui-shell, E3).

The department screen shows the J2 prototype's own page (j2ui_assets/j2_ui.html, copied by scripts/sync_j2_ui.py and
changed by three documented substitutions only), in a same-origin iframe. This module serves it and the two files it
loads: j2host.js (the fetch wrapper that gives a write the panel token) and, once vendored, fonts/. The adapter that
answers the page's api/, site/, file/ and shot/ calls under the same base is j2ui_api's, not this file's.

The page sits at a directory-style URL, so the relative URLs substitution S1 left (api/state, site/latest) resolve to
/j2ui/{ref}/api/state and so on; a request for /j2ui/{ref} is redirected to the slash by the framework. Only a department
of the engine runtime whose kind is website has the page; a Root, a department of another kind, a department of the first
build or an unknown ref is 404 {"error": "no such department"} on every route here.

Only this module reads j2ui_assets/. Nothing here writes."""
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

import website_dept as W

try:                                    # the adapter's package decides the scope once it is in the tree
    import j2ui_common as _common
except ModuleNotFoundError as _e:
    if _e.name != "j2ui_common":
        raise
    _common = None

router = APIRouter(prefix="/j2ui", tags=["j2ui"])

ASSETS = Path(__file__).resolve().parent / "j2ui_assets"
_CACHE = {}                             # path -> (mtime_ns, size, bytes): a file is read again only when it changed
FONT_TYPES = {".woff2": "font/woff2", ".css": "text/css; charset=utf-8", ".txt": "text/plain; charset=utf-8"}


def _scoped(ref):
    """True for a department of the engine runtime whose kind is website. j2ui_common.need is the one place that
    decides when the adapter is in the tree; until then the same rule is read here from the record."""
    if _common is not None:
        try:
            _common.need(ref)
            return True
        except _common.NotJ2:
            return False
    if not ref or ref.startswith("."):
        return False
    try:
        d = W.dept(ref)
    except ValueError:
        return False
    return bool(d) and d.get("runtime") == 2 and d.get("kind") == "website"


def _none():
    return JSONResponse({"error": "no such department"}, status_code=404, headers={"Cache-Control": "no-store"})


def _gone():
    """The page's own file is not in the tree (a build that left j2ui_assets out): plain 404, never a stack trace."""
    return Response(content="not found", status_code=404, media_type="text/plain", headers={"Cache-Control": "no-store"})


def _read(path):
    st = path.stat()
    hit = _CACHE.get(path)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    data = path.read_bytes()
    _CACHE[path] = (st.st_mtime_ns, st.st_size, data)
    return data


def pin():
    """PINNED.json as the sync script wrote it ({} when there is none): what the page's security policy and the font
    route depend on."""
    try:
        return json.loads(_read(ASSETS / "PINNED.json"))
    except (OSError, ValueError):
        return {}


def csp(local_fonts):
    """The page's content security policy. It runs script and style of its own (inline), calls only its own origin and may
    be framed only by the panel. The prototype's Google Fonts hosts are allowed only while the fonts are not vendored."""
    return "; ".join([
        "default-src 'self'", "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'" + ("" if local_fonts else " https://fonts.googleapis.com"),
        "font-src " + ("'self'" if local_fonts else "https://fonts.gstatic.com"),
        "img-src 'self' data:", "frame-src 'self'", "connect-src 'self'", "object-src 'none'", "base-uri 'none'",
        "form-action 'none'", "frame-ancestors 'self'"])


@router.get("/{ref}/")
@router.get("/{ref}/index.html")
def page(ref: str):
    if not _scoped(ref):
        return _none()
    headers = {"Content-Security-Policy": csp(bool(pin().get("local_fonts"))), "X-Content-Type-Options": "nosniff",
               "Cache-Control": "no-store"}
    try:
        body = _read(ASSETS / "j2_ui.html")
    except OSError:
        return _gone()
    return Response(content=body, media_type="text/html; charset=utf-8", headers=headers)


@router.get("/{ref}/j2host.js")
def host(ref: str):
    if not _scoped(ref):
        return _none()
    try:
        body = _read(ASSETS / "j2host.js")
    except OSError:
        return _gone()
    return Response(content=body, media_type="application/javascript",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.get("/{ref}/fonts/{name}")
def font(ref: str, name: str):
    """Only a file the pin lists under fonts/ (the vendored families, their stylesheet and licence); anything else is 404."""
    listed = {k.split("/", 2)[2] for k in (pin().get("app") or {}).get("files", {}) if k.startswith("j2ui_assets/fonts/")}
    if not _scoped(ref):
        return _none()
    kind = FONT_TYPES.get(Path(name).suffix)
    if name not in listed or kind is None or not (ASSETS / "fonts" / name).is_file():
        return _gone()
    return Response(content=_read(ASSETS / "fonts" / name), media_type=kind,
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=3600"})
