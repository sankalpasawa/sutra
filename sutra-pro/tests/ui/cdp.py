"""Headless Chrome over the DevTools protocol, for the UI browser tests (UI-0, docs/design/ui.md section 10, D85).

Nothing to install: it speaks the protocol with `websockets` (already here through `uvicorn[standard]`) and starts the
Chrome that is on the machine.

    with Browser() as b:
        b.goto("http://127.0.0.1:8780/")
        b.wait_for("document.readyState === 'complete'")
        b.hover("#to-home")
        b.click("#to-home")
        b.shot("tests/ui/screens/home.png")
        assert not b.console_errors and not b.failed_requests

`find_chrome()` tries `SUTRA_CHROME`, the macOS app, `google-chrome`, `chromium`, then the Playwright cache.
`scripts/py tests/ui/cdp.py --self-test` prints `chrome ok`, or `chrome missing` (exit 0); a Chrome that is found but
cannot be driven prints `chrome failed: <why>` and exits 1.

Diagnostics (collected by listeners, read as properties):
  console_errors   console.error calls, uncaught exceptions and error log entries (a CSP violation is one of them)
  failed_requests  any 4xx or 5xx answer and any request that failed, except the favicon and requests the page itself
                   cancelled (a navigation cancels the streams of the old page); the `browser` fixture of conftest.py
                   fails the test when this list is not empty at its end. A test that provokes a failure on purpose
                   says so with `expect_failed("/api/graph")`, or empties the lists with `clear_diagnostics()`.

`Browser(ws_url=...)` attaches to a page that is already open (the unit tests use it with a fake DevTools endpoint).
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import glob
import inspect
import itertools
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
THEMES = ("light", "dark", "system")
SCHEMES = ("light", "dark")
THEME_KEY = "j2theme"  # the localStorage key of both pages (ui.md section 3.2, browser storage)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
STOP_GRACE_S = 5.0  # how long Chrome gets to leave after SIGTERM, after SIGKILL, and for its helper processes to be gone
STARTUP_S = 20.0  # how long Chrome gets to open its debugging port (a cold start on a busy machine is slow)

# Chrome flags: headless, quiet, nothing that talks to the network on its own, and a profile of its own.
CHROME_FLAGS = (
    "--headless=new",
    "--remote-debugging-port=0",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-features=Translate,OptimizationHints,MediaRouter",
    "--mute-audio",
    "--hide-scrollbars",
)

KEYS = {  # name -> (key, code, windowsVirtualKeyCode, text sent with keyDown)
    "Enter": ("Enter", "Enter", 13, "\r"),
    "Escape": ("Escape", "Escape", 27, ""),
    "Tab": ("Tab", "Tab", 9, ""),
    "Backspace": ("Backspace", "Backspace", 8, ""),
    "Delete": ("Delete", "Delete", 46, ""),
    "ArrowUp": ("ArrowUp", "ArrowUp", 38, ""),
    "ArrowDown": ("ArrowDown", "ArrowDown", 40, ""),
    "ArrowLeft": ("ArrowLeft", "ArrowLeft", 37, ""),
    "ArrowRight": ("ArrowRight", "ArrowRight", 39, ""),
    "Space": (" ", "Space", 32, " "),
}


class BrowserError(RuntimeError):
    """Chrome could not be started or driven."""


class JSError(BrowserError):
    """A script evaluated in the page threw."""


# ---------------------------------------------------------------------------------------------------------------------
# Finding Chrome
# ---------------------------------------------------------------------------------------------------------------------
def _playwright_roots(env: Mapping[str, str], home: Path) -> list[Path]:
    roots = []
    if env.get("PLAYWRIGHT_BROWSERS_PATH"):
        roots.append(Path(env["PLAYWRIGHT_BROWSERS_PATH"]))
    roots += [home / "Library" / "Caches" / "ms-playwright", home / ".cache" / "ms-playwright"]
    return roots


_PLAYWRIGHT_PATTERNS = (  # relative to a Playwright browsers folder, newest build first
    "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
    "chromium-*/chrome-linux*/chrome",
    "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
    "chromium_headless_shell-*/chrome-mac*/headless_shell",
    "chromium_headless_shell-*/chrome-linux*/headless_shell",
)


def chrome_candidates(
    env: Mapping[str, str] | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    home: Path | None = None,
) -> list[str]:
    """Every place a Chrome may be, in the order `find_chrome` tries them (the paths are not checked here)."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    out: list[str] = []
    if env.get("SUTRA_CHROME"):
        out.append(env["SUTRA_CHROME"])
    out.append(MAC_CHROME)
    for name in ("google-chrome", "chromium"):
        found = which(name)
        if found:
            out.append(found)
    for root in _playwright_roots(env, home):
        for pattern in _PLAYWRIGHT_PATTERNS:
            out += sorted(glob.glob(str(root / pattern)), reverse=True)
    return out


def find_chrome(
    env: Mapping[str, str] | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    home: Path | None = None,
) -> str | None:
    """The first Chrome that exists and can be run, or None. A `SUTRA_CHROME` that does not exist is skipped."""
    for candidate in chrome_candidates(env, which=which, home=home):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


# ---------------------------------------------------------------------------------------------------------------------
# The protocol connection
# ---------------------------------------------------------------------------------------------------------------------
class Connection:
    """One DevTools websocket. A reader thread routes answers to the caller that waits for them and events to
    `on_event(method, params)`."""

    def __init__(self, ws_url: str, on_event: Callable[[str, dict], None], timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._on_event = on_event
        self._ids = itertools.count(1)
        self._pending: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._stack = contextlib.ExitStack()
        try:
            # websockets 17 wants connect() used as a context manager (it warns otherwise): the stack holds it open.
            # No proxy (this is loopback; the argument exists from websockets 15), no keep-alive pings (Chrome does not
            # need them), any message size (screenshots).
            options: dict[str, Any] = {"ping_interval": None, "compression": None, "max_size": None, "open_timeout": timeout}
            if "proxy" in inspect.signature(connect).parameters:
                options["proxy"] = None
            self._ws = self._stack.enter_context(connect(ws_url, **options))
        except Exception as exc:  # noqa: BLE001 - one error type for every way a connection can fail
            self._stack.close()
            raise BrowserError(f"cannot connect to {ws_url}: {exc}") from exc
        self._reader = threading.Thread(target=self._read, name="cdp-reader", daemon=True)
        self._reader.start()

    def _read(self) -> None:
        try:
            while True:
                message = json.loads(self._ws.recv())
                if "id" in message:
                    with self._lock:
                        waiter = self._pending.pop(message["id"], None)
                    if waiter is not None:
                        waiter.put(message)
                elif "method" in message:
                    try:
                        self._on_event(message["method"], message.get("params") or {})
                    except Exception:  # noqa: BLE001 - a bad listener must not kill the reader
                        pass
        except (ConnectionClosed, OSError, ValueError):
            pass
        finally:
            self._closed.set()
            with self._lock:
                waiting, self._pending = list(self._pending.values()), {}
            for waiter in waiting:
                waiter.put({"error": {"message": "the connection to Chrome closed"}})

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def send(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        """Run one command and return its `result`. A protocol error raises `BrowserError`."""
        if self._closed.is_set():
            raise BrowserError(f"{method}: the connection to Chrome is closed")
        call_id = next(self._ids)
        waiter: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._pending[call_id] = waiter
        try:
            self._ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
        except (ConnectionClosed, OSError) as exc:
            with self._lock:
                self._pending.pop(call_id, None)
            raise BrowserError(f"{method}: the connection to Chrome is closed") from exc
        try:
            answer = waiter.get(timeout=self.timeout if timeout is None else timeout)
        except queue.Empty:
            with self._lock:
                self._pending.pop(call_id, None)
            raise BrowserError(f"{method}: no answer from Chrome within {self.timeout if timeout is None else timeout} s") from None
        if "error" in answer:
            raise BrowserError(f"{method}: {answer['error'].get('message', answer['error'])}")
        return answer.get("result") or {}

    def post(self, method: str, params: dict | None = None) -> None:
        """Send a command and do not wait for its answer. The reader thread uses this one (it must never wait for
        itself); the answer comes back with an id nobody waits for and is dropped."""
        if self._closed.is_set():
            return
        with contextlib.suppress(ConnectionClosed, OSError):
            self._ws.send(json.dumps({"id": next(self._ids), "method": method, "params": params or {}}))

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._stack.close()  # leaves the `with connect(...)` block: closes the websocket
        self._reader.join(timeout=2)


# ---------------------------------------------------------------------------------------------------------------------
# Starting Chrome
# ---------------------------------------------------------------------------------------------------------------------
def _http_json(url: str, method: str = "GET", timeout: float = 5.0) -> Any:
    request = urllib.request.Request(url, method=method)
    # Chrome's debugging port is on loopback; the environment's proxy settings must not apply to it
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read())


class ChromeProcess:
    """A Chrome child process with its own profile folder and debugging port."""

    def __init__(self, chrome: str, *, headless: bool = True, extra_args: Sequence[str] = (), timeout: float = STARTUP_S,
                 profile_dir: str | os.PathLike | None = None) -> None:
        self.profile = Path(profile_dir) if profile_dir else Path(tempfile.mkdtemp(prefix="sutra-chrome-"))
        self._own_profile = profile_dir is None
        flags = [f for f in CHROME_FLAGS if headless or not f.startswith("--headless")]
        self.process = subprocess.Popen(
            [chrome, *flags, f"--user-data-dir={self.profile}", *extra_args, "about:blank"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        try:
            self.port = self._wait_for_port(timeout)
        except BaseException:
            self.close()
            raise

    def _wait_for_port(self, timeout: float) -> int:
        port_file = self.profile / "DevToolsActivePort"  # Chrome writes the port it chose on its first line
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            code = self.process.poll()
            if code is not None:
                raise BrowserError(f"Chrome exited with code {code} before it opened its debugging port")
            try:
                first = port_file.read_text().splitlines()[0].strip()
                if first.isdigit():
                    return int(first)
            except (OSError, IndexError):
                pass
            time.sleep(0.05)
        raise BrowserError(f"Chrome did not open its debugging port within {timeout} s")

    def page_ws_url(self, timeout: float) -> str:
        """The websocket of the first page target (the `about:blank` tab Chrome opened)."""
        base = f"http://127.0.0.1:{self.port}"
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                for target in _http_json(f"{base}/json/list"):
                    if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                        return target["webSocketDebuggerUrl"]
                created = _http_json(f"{base}/json/new?about:blank", method="PUT")
                if created.get("webSocketDebuggerUrl"):
                    return created["webSocketDebuggerUrl"]
            except (OSError, ValueError, urllib.error.URLError) as exc:
                last = exc
            time.sleep(0.05)
        raise BrowserError(f"Chrome has no page to drive within {timeout} s ({last})")

    def _group_alive(self) -> bool:
        try:
            os.killpg(self.process.pid, 0)
        except ProcessLookupError:
            return False
        except OSError:  # no permission: the group exists
            return True
        return True

    def close(self) -> None:
        process = self.process
        if process.poll() is None:
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGTERM)  # Chrome starts helper processes; the group takes them with it
            try:
                process.wait(timeout=STOP_GRACE_S)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(OSError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=STOP_GRACE_S)
        # The helpers outlive the main process by a moment and may still write into the profile: wait for the group to
        # be gone (then kill what is left), so the folder can be removed for good.
        deadline = time.monotonic() + STOP_GRACE_S
        while self._group_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if self._group_alive():
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)
        if self._own_profile:
            for _ in range(10):
                shutil.rmtree(self.profile, ignore_errors=True)
                if not self.profile.exists():
                    break
                time.sleep(0.1)


# ---------------------------------------------------------------------------------------------------------------------
# The browser
# ---------------------------------------------------------------------------------------------------------------------
def _is_favicon(url: str) -> bool:
    return urlsplit(url).path.endswith("/favicon.ico")


def _remote_text(arg: Mapping[str, Any]) -> str:
    """A console argument as text: its value when it has one, else Chrome's description of it."""
    if "value" in arg:
        return str(arg["value"])
    return str(arg.get("description") or arg.get("unserializableValue") or arg.get("type") or "")


class Browser:
    """A headless Chrome with one page. Use it as a context manager."""

    def __init__(
        self,
        chrome: str | None = None,
        *,
        ws_url: str | None = None,
        size: tuple[int, int] = (1280, 900),
        timeout: float = 15.0,
        headless: bool = True,
        extra_args: Sequence[str] = (),
        profile_dir: str | os.PathLike | None = None,
        startup_timeout: float | None = None,
    ) -> None:
        self.timeout = timeout
        self.startup_timeout = max(timeout, STARTUP_S) if startup_timeout is None else startup_timeout
        self.size = size
        self._chrome = chrome
        self._ws_url = ws_url
        self._headless = headless
        self._extra_args = tuple(extra_args)
        self._profile_dir = profile_dir
        self._process: ChromeProcess | None = None
        self._conn: Connection | None = None
        self._lock = threading.Lock()
        self._console: list[str] = []
        self._failed: list[dict] = []
        self._expected: list[dict] = []
        self._expect_rules: list[tuple[str, int | None]] = []
        self._requests: dict[str, tuple[str, str]] = {}
        self._load = threading.Event()
        self._theme_script: str | None = None
        self.dialogs: list[dict] = []  # alert, confirm and prompt boxes the page opened (all are accepted)

    # -- life cycle ---------------------------------------------------------------------------------------------------
    def __enter__(self) -> "Browser":
        try:
            self.start()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self) -> None:
        if self._conn is not None:
            return
        ws_url = self._ws_url
        if ws_url is None:
            chrome = self._chrome or find_chrome()
            if chrome is None:
                raise BrowserError("Chrome is not installed (set SUTRA_CHROME to its path)")
            self._process = ChromeProcess(chrome, headless=self._headless, extra_args=self._extra_args,
                                          timeout=self.startup_timeout, profile_dir=self._profile_dir)
            ws_url = self._process.page_ws_url(self.timeout)
        self._conn = Connection(ws_url, self._on_event, self.timeout)
        for domain in ("Page", "Runtime", "Network", "Log"):
            self._send(f"{domain}.enable")
        self.set_size(*self.size)

    def close(self) -> None:
        conn, self._conn = self._conn, None
        process, self._process = self._process, None
        if conn is not None:
            conn.close()
        if process is not None:
            process.close()

    @property
    def pid(self) -> int | None:
        return self._process.process.pid if self._process else None

    def _send(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        if self._conn is None:
            raise BrowserError(f"{method}: the browser is not started")
        return self._conn.send(method, params, timeout)

    # -- listeners ----------------------------------------------------------------------------------------------------
    def _on_event(self, method: str, params: dict) -> None:
        if method == "Page.loadEventFired":
            self._load.set()
        elif method == "Page.javascriptDialogOpening":
            self.dialogs.append({"type": params.get("type"), "message": params.get("message", "")})
            if self._conn is not None:  # this runs on the reader thread: answer without waiting for the answer
                self._conn.post("Page.handleJavaScriptDialog", {"accept": True})
        elif method == "Runtime.consoleAPICalled":
            if params.get("type") in ("error", "assert"):
                self._note_console(" ".join(_remote_text(a) for a in params.get("args", [])))
        elif method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails", {})
            exception = details.get("exception") or {}
            self._note_console(exception.get("description") or details.get("text") or "uncaught exception")
        elif method == "Log.entryAdded":
            entry = params.get("entry", {})
            if entry.get("level") == "error" and not _is_favicon(entry.get("url", "")):
                self._note_console(f"[{entry.get('source', 'log')}] {entry.get('text', '')}")
        elif method == "Network.requestWillBeSent":
            request = params.get("request", {})
            self._requests[params.get("requestId", "")] = (request.get("url", ""), request.get("method", "GET"))
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            if response.get("status", 0) >= 400:
                method_ = self._requests.get(params.get("requestId", ""), ("", "GET"))[1]
                self._note_failed({"url": response.get("url", ""), "status": response["status"], "error": None, "method": method_})
        elif method == "Network.loadingFailed":
            url, method_ = self._requests.get(params.get("requestId", ""), ("", "GET"))
            if not params.get("canceled") and url and not url.startswith(("data:", "blob:")):
                self._note_failed({"url": url, "status": 0, "error": params.get("errorText", "failed"), "method": method_})

    def _note_console(self, text: str) -> None:
        with self._lock:
            self._console.append(text)

    def _note_failed(self, item: dict) -> None:
        if _is_favicon(item["url"]):
            return
        with self._lock:
            expected = any(part in item["url"] and (status is None or status == item["status"])
                           for part, status in self._expect_rules)
            (self._expected if expected else self._failed).append(item)

    @property
    def console_errors(self) -> list[str]:
        with self._lock:
            return list(self._console)

    @property
    def failed_requests(self) -> list[dict]:
        """Requests that failed and were not announced with `expect_failed`: `{url, status, error, method}`."""
        with self._lock:
            return list(self._failed)

    @property
    def expected_failures(self) -> list[dict]:
        with self._lock:
            return list(self._expected)

    def expect_failed(self, url_part: str, status: int | None = None) -> None:
        """A failure of a URL that contains `url_part` (and has this status, when given) is on purpose from now on."""
        with self._lock:
            self._expect_rules.append((url_part, status))

    def clear_diagnostics(self) -> None:
        with self._lock:
            self._console.clear()
            self._failed.clear()
            self._expected.clear()

    # -- the page -----------------------------------------------------------------------------------------------------
    def goto(self, url: str, timeout: float | None = None) -> None:
        """Open `url` and wait for its load event."""
        wait = self.timeout if timeout is None else timeout
        self._load.clear()
        result = self._send("Page.navigate", {"url": url}, wait)
        if result.get("errorText"):
            raise BrowserError(f"cannot open {url}: {result['errorText']}")
        if result.get("loaderId") and not self._load.wait(wait):  # a change of the #hash has no loader and no load event
            raise TimeoutError(f"{url} did not finish loading within {wait} s")

    def reload(self, timeout: float | None = None) -> None:
        wait = self.timeout if timeout is None else timeout
        self._load.clear()
        self._send("Page.reload", {}, wait)
        if not self._load.wait(wait):
            raise TimeoutError(f"the page did not finish loading within {wait} s")

    def js(self, expression: str) -> Any:
        """Evaluate `expression` in the page (a promise is awaited) and return its value as JSON data."""
        result = self._send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True,
        })
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            text = (details.get("exception") or {}).get("description") or details.get("text") or "script error"
            raise JSError(text)
        return (result.get("result") or {}).get("value")

    def wait_for(self, expression: str, timeout: float = 10.0, interval: float = 0.05) -> Any:
        """Poll `expression` until it is truthy and return that value; TimeoutError (with the console errors) otherwise."""
        deadline = time.monotonic() + timeout
        last_error = ""
        while True:
            try:
                value = self.js(expression)
                if value:
                    return value
            except JSError as exc:
                last_error = str(exc)
            if time.monotonic() >= deadline:
                break
            time.sleep(interval)
        message = f"wait_for({expression!r}) was still false after {timeout} s"
        if last_error:
            message += f"; last script error: {last_error}"
        if self.console_errors:
            message += f"; console errors: {self.console_errors[:3]}"
        raise TimeoutError(message)

    def exists(self, selector: str) -> bool:
        return bool(self.js(f"!!document.querySelector({json.dumps(selector)})"))

    def count(self, selector: str) -> int:
        return int(self.js(f"document.querySelectorAll({json.dumps(selector)}).length"))

    def text(self, selector: str) -> str | None:
        """The text of the first element that matches, or None."""
        return self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); return e ? e.textContent : null; }})()")

    def _center(self, selector: str) -> tuple[float, float]:
        point = self.js(
            "(() => { const e = document.querySelector(" + json.dumps(selector) + "); if (!e) return null;"
            " e.scrollIntoView({block: 'center', inline: 'center'}); const r = e.getBoundingClientRect();"
            " return [r.left + r.width / 2, r.top + r.height / 2]; })()"
        )
        if not point:
            raise BrowserError(f"no element matches {selector!r}")
        return float(point[0]), float(point[1])

    def click(self, selector: str) -> None:
        """Click the middle of the first element that matches `selector` (a real mouse press and release)."""
        x, y = self._center(selector)
        base = {"x": x, "y": y, "button": "left", "clickCount": 1}
        self._send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        self._send("Input.dispatchMouseEvent", {"type": "mousePressed", **base})
        self._send("Input.dispatchMouseEvent", {"type": "mouseReleased", **base})

    def hover(self, selector: str) -> None:
        """Move the mouse over the middle of the first element that matches `selector`, without pressing (a node lights up)."""
        x, y = self._center(selector)
        self._send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})

    def type(self, selector: str, text: str) -> None:
        """Focus the first element that matches and insert `text` (it fires the input events a typist would)."""
        if not self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; e.focus(); return true; }})()"):
            raise BrowserError(f"no element matches {selector!r}")
        self._send("Input.insertText", {"text": text})

    def press(self, key: str) -> None:
        """Press and release one key of `KEYS` (Enter, Escape, Tab, Backspace, the arrows, Space)."""
        if key not in KEYS:
            raise BrowserError(f"unknown key {key!r}; known: {', '.join(KEYS)}")
        name, code, vk, text = KEYS[key]
        down = {"type": "keyDown", "key": name, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        if text:
            down["text"] = text
        self._send("Input.dispatchKeyEvent", down)
        self._send("Input.dispatchKeyEvent", {"type": "keyUp", "key": name, "code": code, "windowsVirtualKeyCode": vk,
                                              "nativeVirtualKeyCode": vk})

    def shot(self, path: str | os.PathLike) -> Path:
        """Save a PNG of the page to `path` (its folder is made when needed) and return the path."""
        data = base64.b64decode(self._send("Page.captureScreenshot", {"format": "png"})["data"])
        if not data.startswith(PNG_MAGIC):
            raise BrowserError("Chrome did not return a PNG")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    # -- the look -----------------------------------------------------------------------------------------------------
    def set_theme(self, theme: str, scheme: str | None = None) -> None:
        """`light`, `dark` or `system` for the next page that opens: the pages read `localStorage j2theme`, and for
        `system` they follow the emulated `prefers-color-scheme` (`scheme`, default light). Takes effect on the next
        `goto` or `reload`."""
        if theme not in THEMES:
            raise ValueError(f"theme must be one of {', '.join(THEMES)}, not {theme!r}")
        if scheme is None:
            scheme = theme if theme in SCHEMES else "light"
        if scheme not in SCHEMES:
            raise ValueError(f"scheme must be one of {', '.join(SCHEMES)}, not {scheme!r}")
        if self._theme_script is not None:
            self._send("Page.removeScriptToEvaluateOnNewDocument", {"identifier": self._theme_script})
        source = f"try {{ localStorage.setItem({json.dumps(THEME_KEY)}, {json.dumps(theme)}); }} catch (e) {{}}"
        self._theme_script = self._send("Page.addScriptToEvaluateOnNewDocument", {"source": source})["identifier"]
        self._send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": scheme}]})

    def set_size(self, width: int, height: int) -> None:
        if not (isinstance(width, int) and isinstance(height, int) and 100 <= width <= 5000 and 100 <= height <= 5000):
            raise ValueError(f"the size must be two whole numbers from 100 to 5000, not {width!r} x {height!r}")
        self._send("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
        })
        self.size = (width, height)


# ---------------------------------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------------------------------
def self_test(out=None) -> int:
    """Start Chrome, open a page, run a script, take a picture. 0 with `chrome ok` or `chrome missing`, 1 on a failure."""
    out = out or sys.stdout
    chrome = find_chrome()
    if chrome is None:
        print("chrome missing", file=out)
        return 0
    try:
        with Browser(chrome) as browser:
            browser.goto("data:text/html,<title>cdp</title><p id=x>ok</p><script>console.log('hi')</script>")
            if browser.js("document.getElementById('x').textContent") != "ok":
                raise BrowserError("the test page did not render")
            if browser.js("1 + 1") != 2:
                raise BrowserError("scripts do not run")
            with tempfile.TemporaryDirectory(prefix="sutra-cdp-") as folder:
                browser.shot(Path(folder) / "self-test.png")
            if browser.console_errors:
                raise BrowserError(f"console errors on a clean page: {browser.console_errors}")
    except (BrowserError, TimeoutError, OSError) as exc:
        print(f"chrome failed: {exc}", file=out)
        return 1
    print("chrome ok", file=out)
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Headless Chrome driver for the UI tests.")
    parser.add_argument("--self-test", action="store_true", help="start Chrome, open a page, take a picture")
    parser.add_argument("--where", action="store_true", help="print the Chrome that would be used, or 'none'")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.where:
        print(find_chrome() or "none")
        return 0
    if args.self_test:
        return self_test()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
