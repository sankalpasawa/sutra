"""Stand-ins for Chrome's DevTools endpoint and for the Chrome program, for the tests of tests/ui/cdp.py (UI-0).

`FakeDevTools` is a websocket server that answers the DevTools commands `cdp.py` sends, records them, and lets a test push
events (console messages, network events, dialogs) the way Chrome would. `chrome_main(argv)` is a Chrome that is not one:
given Chrome's flags it opens a debugging port the way Chrome does (a `DevToolsActivePort` file in the profile folder,
`/json/list` and `/json/new` over HTTP, one page target on a websocket) and serves a FakeDevTools; `FAKE_CHROME_MODE` makes
it fail in the ways a real Chrome can. Nothing in the app imports this file; no Chrome is needed to run it.
"""
from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"a picture that is not one"
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode()
MODES = ("ok", "exit", "noport", "nopage", "newpage", "stubborn", "helper", "consoleerror", "blank")


class ScriptError(Exception):
    """Raise (or return) this from a `values` entry or the `hook` to make Runtime.evaluate answer with an exception."""

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


class FakeDevTools:
    """A DevTools websocket on a free loopback port.

    commands   every command received, in order: {"method", "params"}
    values     Runtime.evaluate: expression -> value (an Exception is an exception in the page)
    hook       Runtime.evaluate: callable(expression) -> value, used when `values` has no entry (default: undefined)
    fail       method -> message: the command is answered with a protocol error
    silent     methods that are never answered
    after      method -> [(event, params)]: events sent right after that command's answer
    """

    def __init__(self, host: str = "127.0.0.1") -> None:
        self.commands: list[dict] = []
        self.values: dict[str, Any] = {}
        self.hook: Callable[[str], Any] | None = None
        self.fail: dict[str, str] = {}
        self.silent: set[str] = set()
        self.screenshot: str = PNG_BASE64
        self.navigate_result: dict = {"frameId": "frame-1", "loaderId": "loader-1"}
        self.after: dict[str, list[tuple[str, dict]]] = {
            "Page.navigate": [("Page.loadEventFired", {"timestamp": 1.0})],
            "Page.reload": [("Page.loadEventFired", {"timestamp": 2.0})],
        }
        self._lock = threading.Lock()
        self._connections: list[Any] = []
        self._scripts = 0
        self._server = serve(self._handle, host, 0, compression=None, ping_interval=None)
        self.port = self._server.socket.getsockname()[1]
        self.url = f"ws://{host}:{self.port}/devtools/page/fake"
        self._thread = threading.Thread(target=self._server.serve_forever, name="fake-devtools", daemon=True)
        self._thread.start()

    # -- the connection --------------------------------------------------------------------------------------------------
    def _handle(self, ws: Any) -> None:
        with self._lock:
            self._connections.append(ws)
        try:
            for raw in ws:
                self._answer(ws, json.loads(raw))
        except ConnectionClosed:
            pass
        finally:
            with self._lock:
                if ws in self._connections:
                    self._connections.remove(ws)

    def _answer(self, ws: Any, message: dict) -> None:
        method, params = message["method"], message.get("params") or {}
        with self._lock:
            self.commands.append({"method": method, "params": params})
        if method in self.silent:
            return
        if method in self.fail:
            ws.send(json.dumps({"id": message["id"], "error": {"code": -32000, "message": self.fail[method]}}))
            return
        ws.send(json.dumps({"id": message["id"], "result": self._result(method, params)}))
        for event, event_params in self.after.get(method, []):
            ws.send(json.dumps({"method": event, "params": event_params}))

    def _result(self, method: str, params: dict) -> dict:
        if method == "Page.navigate":
            return dict(self.navigate_result)
        if method == "Runtime.evaluate":
            return self._evaluate(params.get("expression", ""))
        if method == "Page.captureScreenshot":
            return {"data": self.screenshot}
        if method == "Page.addScriptToEvaluateOnNewDocument":
            with self._lock:
                self._scripts += 1
                return {"identifier": f"script-{self._scripts}"}
        return {}

    def _evaluate(self, expression: str) -> dict:
        value = self.values[expression] if expression in self.values else (self.hook(expression) if self.hook else None)
        if isinstance(value, ScriptError):
            return {"exceptionDetails": {"text": "Uncaught", "exception": {"type": "object", "description": value.description}}}
        if value is None:
            return {"result": {"type": "undefined"}}
        return {"result": {"type": "object" if isinstance(value, (dict, list)) else type(value).__name__, "value": value}}

    # -- for the test ----------------------------------------------------------------------------------------------------
    def calls(self, method: str) -> list[dict]:
        """The params of every command with this name, in order."""
        with self._lock:
            return [c["params"] for c in self.commands if c["method"] == method]

    def methods(self) -> list[str]:
        with self._lock:
            return [c["method"] for c in self.commands]

    def wait_for_command(self, method: str, count: int = 1, timeout: float = 15.0) -> list[dict]:
        deadline = time.monotonic() + timeout
        while len(self.calls(method)) < count:
            if time.monotonic() > deadline:
                raise AssertionError(f"{method} was not sent {count} time(s) within {timeout} s; saw {self.methods()}")
            time.sleep(0.01)
        return self.calls(method)

    def wait_for_client(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while not self._connections:
            if time.monotonic() > deadline:
                raise AssertionError("no client connected")
            time.sleep(0.01)

    def push(self, method: str, params: dict | None = None) -> None:
        """Send an event to every connected client."""
        with self._lock:
            connections = list(self._connections)
        for ws in connections:
            try:
                ws.send(json.dumps({"method": method, "params": params or {}}))
            except ConnectionClosed:
                pass

    def drop_clients(self) -> None:
        """Close every connection from this side, as a Chrome that quit would."""
        with self._lock:
            connections = list(self._connections)
        for ws in connections:
            try:
                ws.close()
            except ConnectionClosed:
                pass

    def stop(self) -> None:
        self.drop_clients()
        self._server.shutdown()
        self._thread.join(timeout=5)

    def __enter__(self) -> "FakeDevTools":
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


# ---------------------------------------------------------------------------------------------------------------------
# A Chrome that is not one
# ---------------------------------------------------------------------------------------------------------------------
def _flags(argv: list[str]) -> dict[str, str]:
    flags = {}
    for arg in argv:
        if arg.startswith("--"):
            name, _, value = arg.partition("=")
            flags[name] = value
    return flags


def chrome_main(argv: list[str]) -> int:
    """Run as Chrome would be run: `chrome --headless=new --remote-debugging-port=0 --user-data-dir=<dir> ... about:blank`.

    FAKE_CHROME_LOG   a file that receives {"argv", "pid", "pgid", "mode"} when the program starts
    FAKE_CHROME_MODE  ok (default) | exit (quit with code 7 before a port) | noport (never open one) | nopage (the target
                      list is empty and cannot make one) | newpage (the list is empty, PUT /json/new makes the page) |
                      stubborn (ignores SIGTERM) | helper (starts a helper process in the same group, as Chrome does) |
                      consoleerror (the page logs a console error after it loads) | blank (the page does not render: the
                      script that reads it answers undefined)
    The page it serves is the one `cdp.py --self-test` opens: `document.getElementById('x').textContent` is "ok" and `1 + 1` is 2.
    """
    flags = _flags(argv)
    mode = os.environ.get("FAKE_CHROME_MODE", "ok")
    if mode not in MODES:
        print(f"unknown FAKE_CHROME_MODE {mode!r}", file=sys.stderr)
        return 2
    log = os.environ.get("FAKE_CHROME_LOG")
    if log:
        Path(log).write_text(json.dumps({"argv": argv, "pid": os.getpid(), "pgid": os.getpgrp(), "mode": mode}), encoding="utf-8")
    if mode == "exit":
        return 7
    stop = threading.Event()
    if mode != "stubborn":
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    else:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if mode == "noport":
        stop.wait()
        return 0
    profile = Path(flags["--user-data-dir"])
    (profile / "Default").mkdir(parents=True, exist_ok=True)
    (profile / "Default" / "Cookies").write_bytes(b"not a database")  # something to remove with the profile
    if mode == "helper":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    devtools = FakeDevTools()
    if mode != "blank":
        devtools.values.update({"document.getElementById('x').textContent": "ok", "1 + 1": 2})
    if mode == "consoleerror":
        devtools.after["Page.navigate"].append(("Runtime.consoleAPICalled", {"type": "error", "args": [{"type": "string", "value": "boom"}]}))
    page = {"id": "page-1", "type": "page", "title": "", "url": "about:blank", "webSocketDebuggerUrl": devtools.url}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, payload: Any) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server's name
            if self.path == "/json/list":
                self._send([page] if mode not in ("nopage", "newpage") else [])
            else:
                self.send_error(404)

        def do_PUT(self) -> None:  # noqa: N802
            if self.path.startswith("/json/new"):
                self._send(page if mode != "nopage" else {})
            else:
                self.send_error(404)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    (profile / "DevToolsActivePort").write_text(f"{http.server_address[1]}\n/devtools/browser/fake\n", encoding="utf-8")
    stop.wait()
    http.shutdown()
    devtools.stop()
    return 0


if __name__ == "__main__":
    sys.exit(chrome_main(sys.argv[1:]))
