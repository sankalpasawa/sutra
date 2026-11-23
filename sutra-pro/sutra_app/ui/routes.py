"""The page routes, the static mount and the headers the pages carry.

`sutra_app.ui` is the only server of HTML and static files (D72); the engine and the orchestrator answer no page.
Three pages share one look (a fourth, the project page of the multi-agent nodes at `/p/{id}`, MAN-13, exists only while SUTRA_NODES_V1 is on): Home at `/`, the owner console at `/console` (usage and cost, the Atom log, health; GAP-CONSOLE) and the
copied J2 page for one department at `/d/{dept}/`. The shared template library is a page of the team too, `/d/{dept}/library`: the same
page file, the same boot block and the same policy (D141); the library behind it is one global store, and the team in the path only gives
the page its shell (rail, token, node panel). A page is a file under `pages/` with one boot marker; `render_page` fills it per
request, and the Content-Security-Policy is built from the page file once per version of that file (D82).

GAP-CONSOLE also puts the HTML error page here (`install_error_pages`, called by `mount_static`, the one call of this package that
receives the app): a request whose `Accept` starts with `text/html` that would be answered 404 or 500 gets a small page (the app name,
the request id, a link Home, the log path) instead of the JSON envelope; every other request keeps the envelope.
"""
from __future__ import annotations

import html as html_lib
import inspect
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote_plus

from fastapi import APIRouter, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from .boot import (
    BootContext,
    BootMarkerError,
    DeptLike,
    csp_header,
    dept_boot,
    inline_script_hashes,
    is_url_id,
    render_page,
)

log = logging.getLogger("sutra_app.ui")

UI_DIR = Path(__file__).resolve().parent
PAGES_DIR = UI_DIR / "pages"  # outside STATIC_DIR on purpose: a raw page file is never served
STATIC_DIR = UI_DIR / "static"  # css/, js/, vendor/
HOME_PAGE = "home.html"
DEPT_PAGE = "j2_ui.html"
CONSOLE_PAGE = "console.html"
PROJECT_PAGE = "project.html"           # MAN-13: the page of one multi-agent project; served only while SUTRA_NODES_V1 is on
PROJECT_ID = re.compile(r"prj_[0-9a-f]{12}")
WORK_PAGE = "work.html"                 # Devin parity DV-2: the Work page; served only while SUTRA_WORK_V1 is on
RECIPES_PAGE = "recipes.html"           # Devin parity DV-3: Recipes; served only while SUTRA_RECIPES_V1 is on
APP_NAME = "Sutra Pro"
STATIC_URL = "/ui"

# Every page response. The token sits in the page, so nothing may be cached (D81).
PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
# A redirect carries no page, so it carries only the cache rule.
REDIRECT_HEADERS = {"Cache-Control": "no-store"}
VENDOR_CACHE = "max-age=3600"  # d3 does not change between releases of the app, as in J2
ASSET_CACHE = "no-cache"  # js and css: always revalidate by ETag, so an edit shows at once

_NOT_FOUND_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>No such team</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
main{max-width:32rem;padding:2rem 1.5rem}
h1{margin:0 0 .75rem;font-size:1.25rem}
a{color:inherit}
</style>
</head>
<body>
<main>
<h1>No team called <code>{dept}</code></h1>
<p><a href="/">Back to all teams</a></p>
</main>
</body>
</html>
"""


_ERROR_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title} - {app}</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
main{max-width:36rem;padding:2rem 1.5rem}
h1{margin:0 0 .25rem;font-size:1.25rem}
.app{margin:0 0 1rem;opacity:.7;font-size:.875rem}
dl{margin:1rem 0;font-size:.875rem}
dt{margin-top:.5rem;opacity:.7}
dd{margin:0;overflow-wrap:anywhere}
a{color:inherit}
</style>
</head>
<body>
<main>
<p class="app">{app}</p>
<h1>{title}</h1>
<p>{message}</p>
<dl>
<dt>Request id</dt><dd><code>{request_id}</code></dd>
<dt>Log file</dt><dd><code>{log_path}</code></dd>
</dl>
<p><a href="/">Home</a></p>
</main>
</body>
</html>
"""
_ERROR_TEXT = {
    404: ("Not found", "There is nothing at {path}."),
    500: ("Something went wrong", "The app hit an unexpected error. The log file below holds the details."),
}


def wants_html(request: Request) -> bool:
    """A browser navigation: the `Accept` header starts with `text/html`."""
    return request.headers.get("accept", "").lstrip().lower().startswith("text/html")


def _shown(text: str, limit: int = 80) -> str:
    return "".join(ch if ch.isprintable() else "\ufffd" for ch in text[:limit]) + ("..." if len(text) > limit else "")


def error_page(request: Request, status_code: int) -> HTMLResponse:
    """The HTML page of a 404 or 500: the app name, the request id of this request, a link Home and the log file's path. Everything that
    came from the request is cut, made printable and escaped; the page has no script."""
    title, message = _ERROR_TEXT[status_code]
    services = getattr(request.app.state, "services", None)
    log_path = getattr(getattr(services, "settings", None), "log_path", None)
    fields = {
        "app": APP_NAME,
        "title": title,
        "message": message.replace("{path}", "<code>" + html_lib.escape(_shown(request.url.path)) + "</code>"),
        "request_id": html_lib.escape(str((request.scope.get("state") or {}).get("request_id") or "-")),
        "log_path": html_lib.escape(str(log_path) if log_path is not None else "not available"),
    }
    page = _ERROR_HTML
    for name, value in fields.items():
        page = page.replace("{" + name + "}", value)
    return _html(page, csp_header([]), status_code=status_code)


async def _answer(handler, request: Request, exc: Exception):
    result = handler(request, exc)
    return await result if inspect.isawaitable(result) else result


def install_error_pages(app: FastAPI) -> bool:
    """Wrap every exception handler of `app` (and add the two a plain app lacks: the framework's HTTP errors and the catch-all) so that a
    browser navigation (`Accept: text/html`) that the handler answered 404 or 500 gets `error_page`; the handler still runs first, so
    it logs and redacts as before, and every other request keeps the answer it had. A second call changes nothing."""
    if getattr(app.state, "sutra_error_pages", False):
        return False
    app.state.sutra_error_pages = True
    handlers = app.exception_handlers
    handlers.setdefault(StarletteHTTPException, http_exception_handler)

    async def unexpected(request: Request, exc: Exception):
        log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return PlainTextResponse("Internal Server Error", status_code=500)

    handlers.setdefault(Exception, unexpected)

    def wrap(handler):
        async def wrapped(request: Request, exc: Exception):
            response = await _answer(handler, request, exc)
            if wants_html(request) and getattr(response, "status_code", None) in _ERROR_TEXT:
                return error_page(request, response.status_code)
            return response
        return wrapped

    for key in list(handlers):
        handlers[key] = wrap(handlers[key])
    return True


@dataclass(frozen=True)
class _Page:
    stamp: tuple[int, int]  # (mtime in ns, size) of the file this was read from
    html: str
    csp: str


class _PageCache:
    """Page files, read and hashed once per version of the file. A version is its mtime and size: an edit shows on the
    next request, and nothing is re-read or re-hashed between edits."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pages: dict[Path, _Page] = {}

    def get(self, path: Path) -> _Page:
        status = path.stat()
        with self._lock:
            page = self._pages.get(path)
        if page is not None and page.stamp == (status.st_mtime_ns, status.st_size):
            return page
        with path.open("rb") as handle:
            status = os.fstat(handle.fileno())  # the stamp of the bytes actually read
            html = handle.read().decode("utf-8")
        page = _Page((status.st_mtime_ns, status.st_size), html, csp_header(inline_script_hashes(html)))
        with self._lock:
            self._pages[path] = page
        return page


def _html(html: str, csp: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(html, status_code=status_code, headers={**PAGE_HEADERS, "Content-Security-Policy": csp})


def _redirect(path: str, query: str) -> RedirectResponse:
    """308 (the method and the query are kept) to `path`, with the raw query string as the client sent it."""
    return RedirectResponse(f"{path}?{query}" if query else path, status_code=308, headers=REDIRECT_HEADERS)


def _without_dept(raw_query: str) -> str:
    """The raw query string without its `dept` parameters; every other parameter stays byte for byte."""
    kept = [part for part in raw_query.split("&") if part and unquote_plus(part.partition("=")[0]) != "dept"]
    return "&".join(kept)


def _not_found(dept: str) -> HTMLResponse:
    """The small 404 page of a team that does not exist. The id comes from the URL, so it is cut, made printable and
    escaped; the page has no script."""
    shown = "".join(ch if ch.isprintable() else "\ufffd" for ch in dept[:80]) + ("..." if len(dept) > 80 else "")
    return _html(_NOT_FOUND_HTML.replace("{dept}", html_lib.escape(shown)), csp_header([]), status_code=404)


def _unavailable(name: str) -> Response:
    """A page file that is missing or unreadable is a broken installation, not a missing team."""
    return Response(
        f"The page {name} cannot be served by this installation.\n",
        status_code=500,
        media_type="text/plain",
        headers=dict(PAGE_HEADERS),
    )


def _serve(cache: "_PageCache", pages: Path, name: str, boot: BootContext, patch: Callable[[str], str] | None = None) -> Response:
    """One page file, filled with its boot block, under the policy built from that file. `patch` may change the filled page (only the links of Home, below); it never adds a script."""
    try:
        page = cache.get(pages / name)
        html = render_page(page.html, boot)
        if patch is not None:
            html = patch(html)
    except (OSError, UnicodeDecodeError, BootMarkerError) as exc:
        log.error("page %s cannot be served: %s", name, exc)
        return _unavailable(name)
    return _html(html, page.csp)


def build_project_router(*, token: str, version: str, project: Callable[[str], bool], pages_dir: Path = PAGES_DIR) -> APIRouter:
    """The one route of the project page, `/p/{project_id}` (MAN-13, D326). It is a router of its own, mounted by `ui.mount_project_page` only while SUTRA_NODES_V1 is on, so with the flag off
    the route does not exist and no other page changes. `project` says whether a project with that id exists; anything else answers 404."""
    BootContext(page="project", token=token, version=version)
    pages = Path(pages_dir)
    cache = _PageCache()

    def project_page(project_id: str) -> Response:
        if PROJECT_ID.fullmatch(project_id) is None or not project(project_id):
            raise StarletteHTTPException(status_code=404)
        return _serve(cache, pages, PROJECT_PAGE, BootContext(page="project", token=token, version=version))

    router = APIRouter()
    router.add_api_route("/p/{project_id}", project_page, methods=["GET", "HEAD"], response_model=None, include_in_schema=False, name="ui_project")
    return router


_CONSOLE_LINK_END = '<span class="rtstat">cost, Atom log, health</span></a>'


def add_home_links(html: str, links: list[tuple[str, str, str, str]]) -> str:
    """Home's "Logs & debug" group with one more row for each of `links` `(id, href, name, note)`, put in at serve time (the desktop window has no address bar, so a page that exists must be reachable). Only
    called with links: with both switches off Home is served exactly as the file says. Nothing is added when the anchor of the console row is not found."""
    if html.count(_CONSOLE_LINK_END) != 1:
        return html
    rows = "".join(f'\n    <a class="railteam" href="{html_lib.escape(href)}" id="{html_lib.escape(ident)}"><span class="rtname">{html_lib.escape(name)}</span><span class="rtstat">{html_lib.escape(note)}</span></a>'
                   for ident, href, name, note in links)
    return html.replace(_CONSOLE_LINK_END, _CONSOLE_LINK_END + rows, 1)


def build_simple_page_router(*, token: str, version: str, page: str, path: str, name: str, pages_dir: Path = PAGES_DIR) -> APIRouter:
    """A router with ONE page, `path`, of its own (the Work page, the Recipes page): mounted by `ui` only while its switch is on, so with the switch off the route does not exist and no other page
    changes. `page` is the file under `pages/` and also the boot context's page name (the file name without `.html`)."""
    kind = page[:-5]
    BootContext(page=kind, token=token, version=version)
    pages = Path(pages_dir)
    cache = _PageCache()

    def serve_it() -> Response:
        return _serve(cache, pages, page, BootContext(page=kind, token=token, version=version))

    router = APIRouter()
    router.add_api_route(path, serve_it, methods=["GET", "HEAD"], response_model=None, include_in_schema=False, name=name)
    return router


def build_router(
    *,
    token: str,
    department: Callable[[str], DeptLike | None],
    version: str,
    pages_dir: Path = PAGES_DIR,
) -> APIRouter:
    """The router of the pages: `/`, `/d/{dept}`, `/d/{dept}/library`, `/d/{dept}/raw` (the Raw AI chat), `/console` and `/favicon.ico`. `department` is `Services.department`; the pages
    are read from `pages_dir` (a parameter so tests run on a temp tree)."""
    BootContext(page="home", token=token, version=version)  # a bad token fails at mount time, not at the first view
    pages = Path(pages_dir)
    cache = _PageCache()

    def serve(name: str, boot: BootContext, patch: Callable[[str], str] | None = None) -> Response:
        return _serve(cache, pages, name, boot, patch)

    def known_dept(raw: str) -> str | None:
        """`raw` when it passes the id rule and `Services.department` knows it, else None."""
        if is_url_id(raw) and department(raw) is not None:
            return raw
        return None

    def home(request: Request) -> Response:
        # Compatibility shim only: nothing generates `/?dept=<id>` any more. One unambiguous, known team is sent to its
        # page with the other parameters; anything else serves Home and ignores `dept`.
        asked = request.query_params.getlist("dept")
        dept = known_dept(asked[0]) if len(asked) == 1 else None
        if dept is not None:
            return _redirect(f"/d/{dept}/", _without_dept(request.url.query))
        links = getattr(request.app.state, "home_links", None)                          # the Work and Recipes entries: present only while their switches are on (DV-2b, DV-3b)
        return serve(HOME_PAGE, BootContext(page="home", token=token, version=version), patch=(lambda html: add_home_links(html, links)) if links else None)

    def dept_slash(dept: str, request: Request) -> Response:
        return _redirect(f"/d/{quote(dept, safe=':')}/", request.url.query)

    def dept_page(dept: str) -> Response:
        row = department(dept) if is_url_id(dept) else None
        if row is None:
            return _not_found(dept)
        return serve(DEPT_PAGE, dept_boot(row, token=token, version=version))

    def dept_library(dept: str) -> Response:
        # D141: the page that J2 serves at /library, under the team. The file is the team page's and J2's own script tells the two apart by
        # the path (SutraCtx.onLibrary), so the answer is the team page's answer, an unknown team's 404 included.
        return dept_page(dept)

    def dept_library_slash(dept: str, request: Request) -> Response:
        return _redirect(f"/d/{quote(dept, safe=':')}/library", request.url.query)

    def dept_raw(dept: str) -> Response:
        # The Raw AI chat debugger (raw_chat.js): the team page again, whose script opens the viewer full screen on this path; `?run=` picks the run.
        return dept_page(dept)

    def console() -> Response:
        return serve(CONSOLE_PAGE, BootContext(page="console", token=token, version=version))

    def favicon() -> Response:
        return Response(status_code=204)

    router = APIRouter()
    for path, endpoint, name in (
        ("/", home, "ui_home"),
        ("/d/{dept}", dept_slash, "ui_dept_redirect"),
        ("/d/{dept}/", dept_page, "ui_dept"),
        ("/d/{dept}/library", dept_library, "ui_dept_library"),
        ("/d/{dept}/library/", dept_library_slash, "ui_dept_library_redirect"),
        ("/d/{dept}/raw", dept_raw, "ui_dept_raw"),
        ("/console", console, "ui_console"),
        ("/favicon.ico", favicon, "ui_favicon"),
    ):
        # HEAD is explicit: FastAPI does not add it to a GET route
        router.add_api_route(path, endpoint, methods=["GET", "HEAD"], response_model=None, include_in_schema=False, name=name)
    return router


class _UiStatic(StaticFiles):
    """`StaticFiles` with the cache rule of the UI and no start-up failure for a missing directory."""

    async def check_config(self) -> None:
        # Starlette raises RuntimeError at the first request when the directory is missing. A broken install should
        # show as 404s (and the warning at mount time), not take the API down with a 500 on every asset.
        return None

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        vendor = path.split(os.sep, 1)[0] == "vendor"
        response.headers["Cache-Control"] = VENDOR_CACHE if vendor else ASSET_CACHE  # 200 and 304 alike
        return response


def mount_static(app: FastAPI, static_dir: Path = STATIC_DIR) -> None:
    """Serve `css/`, `js/` and `vendor/` of `static_dir` at `/ui`. `StaticFiles` answers only GET and HEAD, refuses a
    path that leaves the directory and follows no symlink out of it. Also installs the HTML error pages (`install_error_pages`)."""
    install_error_pages(app)
    static_dir = Path(static_dir)
    if not static_dir.is_dir():
        log.warning("the UI static directory %s does not exist: every /ui request will answer 404", static_dir)
    app.mount(STATIC_URL, _UiStatic(directory=static_dir, check_dir=False), name="ui")
