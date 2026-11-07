"""The app shell: `create_app`, the lifespan and the command line (orchestrator 5.1, 6.4; work packages ORCH-8 and GAP-OPS-1).

    app = create_app(settings=None, *, connector=None, launcher=None, clock=None, ids=None)       # a FastAPI app
    python -m sutra_app [serve] [--port N] [--data-dir D] [--offline] [--no-browser] [--browser B] [--verbose]    # the server (`run`)
    python -m sutra_app doctor | status | stop | config | open ...                               # the operator commands (`ops.cli`)

`create_app` builds the services (`wiring.build_services`), puts the app-wide Host guard in front (400 `bad_host`), installs the error
envelope and the redacting responses, includes the orchestrator's routers and then, in this fixed order, the plug-ins: the engine's
routes (`sutra_app.engine.api.mount`), the connector routes, the library's `/api/schemas` and the UI pages (`sutra_app.ui.mount`).
A plug-in that cannot be imported is logged and skipped. `docs_url` and `redoc_url` are off (their scripts come from a CDN, so
they are broken offline); `/openapi.json` stays. The lifespan runs `wiring.start_services` and `wiring.stop_services`.

GAP-OPS-1: the whole app is wrapped in the request-id middleware (`X-Request-Id` on every response, even a 400 or a 500), and the
router of `sutra_app.ops.api` is mounted when that module exists. The instance lock, the log file and the first-run doctor belong to
`run` (the server process), not to `create_app`: a library call must not lock a folder or change the process's logging.

The server binds 127.0.0.1 only. Port: `--port N` or `SUTRA_PORT` means exactly that port; otherwise 8780, then the next free port up
to 8799. The socket is bound before the app is built, so the port in `/api/config` is the real one.
"""
import argparse
import asyncio
import contextlib
import importlib
import importlib.util
import logging
import os
import socket
import sys
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

import sutra_app
from sutra_app import oslayer
from sutra_app.config import LOOPBACK_HOSTS, Settings, SettingsError
from sutra_app.orchestrator.api import agent, atoms, chat_v2, chart, chat, departments, graph, recurring, system, tasks, usage
from sutra_app.orchestrator.api import events as events_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.errors import error_body
from sutra_app.orchestrator.ids import Clock, IdFactory
from sutra_app.ops import browser as ops_browser
from sutra_app.ops import logsetup
from sutra_app.orchestrator.wiring import AppServices, build_services, start_services, stop_services

__all__ = [
    "create_app", "lifespan", "LoopbackHostMiddleware", "build_parser", "run", "bind_socket", "AppServer", "FIRST_PORT", "LAST_PORT",
    "GRACEFUL_SHUTDOWN_S", "PLUGINS", "OPS_API",
]

log = logging.getLogger(__name__)
FIRST_PORT = 8780
LAST_PORT = 8799
STOP_POLL_S = 0.5                # how often the server looks for a stop request (the app.stop file)
GRACEFUL_SHUTDOWN_S = 5                 # open connections are cancelled after this; the stop ladders then run in the lifespan
# the orchestrator's own routers, in include order: the agent router first (it owns POST /api/chats/{sid}/messages and the decision route)
ROUTERS = (events_api, chat_v2, agent, chat, atoms, usage, graph, chart, departments, tasks, recurring, system)
# plug-ins: (module, how to mount it), in the order orchestrator 6.4 fixes; the library's schema router sits before the UI
PLUGINS = ("sutra_app.engine.api", "sutra_app.connectors.api", "sutra_app.library.api", "sutra_app.ui")
OPS_API = "sutra_app.ops.api"           # GAP-CONSOLE's router (`router`); mounted after the orchestrator's routers when the module exists


class LoopbackHostMiddleware:
    """The Host allow-list for the whole app: `127.0.0.1` or `localhost`, any port, else 400 `bad_host` in the error envelope. A
    missing or malformed Host header is refused too. (Starlette's TrustedHostMiddleware does the same check but answers plain text.)"""

    def __init__(self, app: ASGIApp, allowed_hosts: Sequence[str] = LOOPBACK_HOSTS) -> None:
        self.app = app
        self.allowed = tuple(h.lower() for h in allowed_hosts)

    def _ok(self, scope: Scope) -> bool:
        raw = b""
        for name, value in scope.get("headers", ()):
            if name == b"host":
                raw = value
                break
        try:
            text = raw.decode("ascii").strip().lower()
        except UnicodeDecodeError:
            return False
        name, sep, port = text.partition(":")
        if sep and not (port.isdigit() and len(port) <= 5):
            return False
        return name in self.allowed

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or self._ok(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = JSONResponse(error_body("bad_host", "This server answers only on 127.0.0.1 or localhost"), status_code=400)
        await response(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    services: AppServices = app.state.services
    await start_services(services)
    try:
        yield
    finally:
        await stop_services(services)


def _mount_plugin(app: FastAPI, services: AppServices, name: str) -> bool:
    """Mount one plug-in; an ImportError is logged and skipped (orchestrator 3.5)."""
    try:
        module = importlib.import_module(name)
    except ImportError as exc:
        log.error("plug-in %s is not available and was skipped: %s", name, exc)
        return False
    if name == "sutra_app.connectors.api":
        app.include_router(module.build_api_router(router=services.connector_router, write_guard=services.require_token))
    elif name == "sutra_app.library.api":
        app.include_router(module.build_api_router(write_guard=services.require_token))
    else:
        module.mount(app, services)
    return True


def _mount_ops_api(app: FastAPI) -> bool:
    """Include `sutra_app.ops.api.router` when GAP-CONSOLE's module exists (found without importing it, so a broken module is an error,
    not a silent skip)."""
    if importlib.util.find_spec(OPS_API) is None:
        return False
    app.include_router(importlib.import_module(OPS_API).router)
    return True


def create_app(settings: Settings | None = None, *, connector: Any = None, launcher: Any = None, clock: Clock | None = None,
               ids: IdFactory | None = None) -> FastAPI:
    """The whole app. `connector` replaces the chat agent's model connector (tests pass a `ScriptedConnector`), `launcher` the run
    launcher (`FakeLauncher`), `clock` and `ids` the time and id sources. Nothing runs until the lifespan starts."""
    settings = settings if settings is not None else Settings.load()
    services = build_services(settings, connector=connector, launcher=launcher, clock=clock, ids=ids)
    app = FastAPI(title="Sutra Pro", version=services.version, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.services = services
    app.add_middleware(LoopbackHostMiddleware)
    install_error_handlers(app, redacted_response_class(services.redact))
    for module in ROUTERS:
        app.include_router(module.build_router())
    app.state.ops_api = _mount_ops_api(app)
    app.state.plugins = {name: _mount_plugin(app, services, name) for name in PLUGINS}
    inner = app.build_middleware_stack
    app.build_middleware_stack = lambda: logsetup.RequestIdMiddleware(inner())       # outermost: the Host guard's 400 and a 500 carry the id too
    return app


# ---- the command line -----------------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sutra-pro", description="Sutra Pro: a chat on top of one global org chart, run by five function nodes per department. "
        "Serves on 127.0.0.1 only. `sutra-pro [serve] [flags]` starts the server; the commands doctor, status, stop, config and open "
        "(each with --help) look after it.", epilog="Environment: SUTRA_DATA_DIR, SUTRA_PORT, SUTRA_CONNECTOR (auto|claude|codex|stub), SUTRA_OFFLINE, "
        "SUTRA_ENGINE (process|fake), SUTRA_MAX_RUNS, SUTRA_MAX_LIVE, SUTRA_TOKEN, SUTRA_BROWSER_APP. See docs/design/orchestrator.md 6.4.")
    parser.add_argument("--port", type=int, metavar="N", help=f"port to serve on (default {FIRST_PORT}, or the next free one up to {LAST_PORT})")
    parser.add_argument("--data-dir", type=Path, metavar="D", help="where the database, run folders and logs live")
    parser.add_argument("--offline", action="store_true", help="no model calls: the stub connector and the engine's mock mode")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--browser", choices=ops_browser.PREFER, default="auto",
                        help="auto/chrome: open Chrome when it is installed (the measured browser); default: the system default browser")
    parser.add_argument("--verbose", action="store_true", help="log at DEBUG level")
    return parser


def bind_socket(host: str, port: int, *, scan: bool, last: int = LAST_PORT) -> socket.socket:
    """A listening-ready socket on `host`. With `scan` the ports `port`..`last` are tried in turn (a port that accepts a
    connection is taken); otherwise exactly `port` (0 lets the system choose). Raises OSError when none is free."""
    candidates = range(port, max(port, last) + 1) if scan else (port,)
    error: OSError | None = None
    for candidate in candidates:
        if scan:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.3)
                if probe.connect_ex((host, candidate)) == 0:
                    error = OSError(f"port {candidate} is in use")
                    continue
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if oslayer.IS_WINDOWS:
            # SO_REUSEADDR on Windows lets a second program bind a port that is already in use (and take its connections)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, candidate))
        except OSError as exc:
            sock.close()
            error = exc
            continue
        return sock
    if scan:
        raise OSError(f"no free port between {port} and {max(port, last)}")
    raise error if error is not None else OSError("could not bind")


class AppServer(uvicorn.Server):
    """uvicorn's server with two additions: the event bus is closed first thing at shutdown (an open event stream would hold the
    graceful stop), and the browser opens once the app is up."""

    def __init__(self, config: uvicorn.Config, *, services: AppServices, url: str, open_browser: bool,
                 opener: Callable[[str], Any] | None = None, stop_path: Path | None = None) -> None:
        super().__init__(config)
        self.services, self.url, self.open_browser = services, url, open_browser
        self.stop_path = stop_path                                       # `app.stop`: its appearance is a request to shut down
        self._stop_watch: asyncio.Task | None = None
        self.opener: Callable[[str], Any] = opener if opener is not None else ops_browser.open_url
        self.after_shutdown: Callable[[], Any] | None = None             # `run` sets it to the instance lock's release (see `shutdown`)

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if not self.started:
            return
        print(f"Sutra Pro is running at {self.url}  (Ctrl+C to stop)", flush=True)
        if self.stop_path is not None:
            self._stop_watch = asyncio.create_task(self._watch_stop_file(self.stop_path))
        if self.open_browser:
            try:
                await asyncio.to_thread(self.opener, self.url)
            except Exception:                                             # noqa: BLE001  (no browser is not a failure)
                log.warning("could not open the browser; open %s yourself", self.url)

    async def _watch_stop_file(self, path: Path) -> None:
        """A stop request is a file: the answer is the same as to a SIGTERM (uvicorn's `should_exit`), and the file is removed."""
        while not self.should_exit:
            if path.exists():
                with contextlib.suppress(OSError):
                    path.unlink()
                log.info("stop requested through %s", path.name)
                self.should_exit = True
                return
            await asyncio.sleep(STOP_POLL_S)

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        if self._stop_watch is not None:
            self._stop_watch.cancel()
        self.services.bus.close()
        await super().shutdown(sockets=sockets)
        if self.after_shutdown is not None:
            # uvicorn re-raises SIGTERM once it is done, so `run` never gets control back after a signal: whatever must happen
            # after the lifespan (the teams are stopped, the database is closed) happens here
            try:
                self.after_shutdown()
            except Exception:                                             # noqa: BLE001
                log.warning("the after-shutdown step failed", exc_info=True)


def run(argv: Sequence[str] | None = None) -> int:
    """The server. Returns the exit status: 0 after a normal stop (or when another instance already serves this data folder), 1 when the
    start was refused (inconsistent library, pre-upgrade backup failed), 2 for a setting or a port that cannot be used. `--help` exits 0.

    Order: settings; the instance lock (a held lock means: print where the running server is, open it, exit 0); logging; the
    pre-upgrade hook; on an empty data folder the doctor's failures; the socket; the library check; `create_app`; serve; release."""
    from sutra_app.ops import cli, lock
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.load(port=args.port, data_dir=args.data_dir, offline=True if args.offline else None)
    except SettingsError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 2
    instance = lock.InstanceLock(settings.data_dir, version=sutra_app.__version__)
    try:
        acquired = instance.acquire()
    except OSError as exc:
        print(f"sutra-pro: cannot use the data folder {settings.data_dir}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    if not acquired:
        return _already_running(instance, args)
    try:
        return _serve(args, settings, instance, cli)
    finally:
        instance.release()


def _already_running(instance: Any, args: argparse.Namespace) -> int:
    holder = instance.holder()
    where = holder.url if holder is not None and holder.url else "this data folder (the port is not known yet)"
    pid = f" (pid {holder.pid})" if holder is not None else ""
    print(f"Sutra Pro is already running on {where}{pid}", flush=True)
    if holder is not None and holder.url and not args.no_browser:
        result = ops_browser.open_url(holder.url, args.browser)
        if not result.opened:
            print(f"Could not open a browser; open {holder.url} yourself.", flush=True)
    return 0


def _serve(args: argparse.Namespace, settings: Settings, instance: Any, cli: Any) -> int:
    first_run = not settings.db_path.exists()
    logsetup.configure(settings, verbose=args.verbose)
    try:
        cli.before_start(settings)
    except Exception as exc:                                                # noqa: BLE001
        print(f"sutra-pro: cannot start: {exc}", file=sys.stderr)
        return 1
    if first_run:
        problems = cli.first_run_problems(settings)
        if problems:
            print("Sutra Pro found problems with this machine (`sutra-pro doctor` lists every check):", flush=True)
            for line in problems:
                print("  " + line, flush=True)
    explicit = args.port is not None or bool(os.environ.get("SUTRA_PORT", "").strip())
    try:
        sock = bind_socket(settings.host, settings.port, scan=not explicit)
    except OSError as exc:
        print(f"sutra-pro: {exc}. Use --port to pick another port.", file=sys.stderr)
        return 2
    settings = settings.model_copy(update={"port": sock.getsockname()[1]})
    instance.update(settings.port)
    from sutra_app.library import all as library      # the registry holds every family only after this import
    problems = library.verify()
    if problems:
        sock.close()
        print("sutra-pro: the model library is inconsistent: " + "; ".join(f"{v.path}: {v.message}" for v in problems[:5]), file=sys.stderr)
        return 1
    library.freeze()
    app = create_app(settings)
    url = f"http://127.0.0.1:{settings.port}/"
    config = uvicorn.Config(app, log_config=None, access_log=True, timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
    from sutra_app.ops import lock as instance_lock
    instance_lock.clear_stop(settings.data_dir)               # a request left by an earlier run must not stop this one
    server = AppServer(config, services=app.state.services, url=url, open_browser=not args.no_browser)
    server.opener = lambda target: ops_browser.open_url(target, args.browser)       # after construction: a test double needs no new argument
    server.stop_path = settings.data_dir / instance_lock.STOP_NAME                   # likewise
    server.after_shutdown = instance.release
    server.run(sockets=[sock])
    return 0
