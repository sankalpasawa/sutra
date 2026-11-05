"""The end-to-end harness (work package GAP-E2E, G05): the REAL app on a temp data folder, served by a real uvicorn thread.

    with LiveApp(tmp_path, connector=ScriptedConnector()) as live:
        live.say("I need a landing page", decide(...), change_reply(...), assignments(...))    # the owner writes, the model answers
        live.until("the run", lambda: live.task_status(task) == "done")
        live.sse.types()                                                                         # what the event stream carried, in order

What is real: `create_app(settings)`, the lifespan, the SQLite database, the HTTP server and its token header, the event stream
(a client thread records it frame by frame), `ProcessLauncher` and the engine process (`python -m sutra_app.engine`, J2 mock mode,
`ScriptedPort`, the DEFAULT hooks with the function-node layer: nothing is replaced through `SUTRA_HOOKS`), the watcher, the
projector, the ledgers. What is scripted: the chat agent's model (`ScriptedConnector`, or the real connector router over the fake
`claude`/`codex` of tests/fakes). The engine's Chrome is a small stand-in executable named by `J2_CHROME` (`FAKE_CHROME`): J2's own check code runs, only the browser is
fake, so a machine with or without Chrome gives the same run.

Everything an e2e test needs is here, so GAP-E2E-UI can reuse it: `LiveApp`, `SseRecorder`, the reply builders (`decide`,
`change_reply`, `assignments`, `add_dept`, ...), `FakeCliBin` (the queue-fed fake `claude`/`codex`), `ControlledClock`.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sqlite3
import stat
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from sutra_app.config import Settings
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.library.org_chart import AddOp, ChartChange, NewNode
from sutra_app.orchestrator.agent.agent import DIGEST_CHARS
from sutra_app.main import GRACEFUL_SHUTDOWN_S, AppServer, bind_socket, create_app
from sutra_app.orchestrator import wiring
from sutra_app.orchestrator.runs import ProcessLauncher

TOKEN = "e2e-token-0123456789abcdef"
HEADERS = {"X-Sutra-Token": TOKEN}
ORG = "cs_org"
REPO = Path(__file__).resolve().parents[2]
FAKES = REPO / "tests" / "fakes"
FIRST_MESSAGE = "I need a landing page for my coffee shop"

# a brief that Identity accepts as it is (the run never asks), and the owner's answer to the vague first message
BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the "
            "farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).")
ANSWER = ("It's called Little Fig, in Koramangala, Bengaluru. Visitors should see our menu with prices, opening hours and "
          "where to find us. Cozy and simple, and it must work on phones.")
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
LIVE = ("starting", "running", "waiting_user")
TERMINAL = ("done", "done_with_open_items", "stopped", "crashed", "cancelled")


# ---- the scripted chat agent's replies (the shapes of tests/orchestrator/test_chat_agent.py) ------------------------------------

def draft(ref: str = "a1", dept: str = "web", title: str = "Cafe page", brief: str = "Build the cafe landing page.", scope=None,
          depends_on=(), follows=None) -> dict:
    return {"ref": ref, "dept": dept, "scope": scope, "title": title, "brief": brief, "depends_on": list(depends_on), "follows": follows}


def decide(intent: str = "new_task", change: str = "reuse", reuse=("web",), why: str = "web fits", assignments=None) -> dict:
    if assignments is None:
        assignments = [draft()] if intent == "new_task" and change in ("none", "reuse") else []
    return {"kind": "decide", "intent": intent, "change": change, "reuse_nodes": list(reuse), "why": why, "assignments": assignments}


def add_dept(ref: str, name: str, purpose: str = "", parent: str = "root") -> dict:
    return {"op": "add", "node": {"ref": ref, "kind": "department", "name": name, "purpose": purpose, "parent": parent}}


def change_reply(*ops: dict, reason: str = "a new team", reuses=()) -> dict:
    return {"reason": reason, "reuses": list(reuses), "ops": list(ops)}


def assignments(*drafts: dict) -> dict:
    return {"kind": "assignments", "assignments": list(drafts)}


def new_team_script(dept: str = "web", name: str = "Web", purpose: str = "Websites and landing pages", title: str = "Cafe page") -> list[dict]:
    """The three model replies of 'a new team for this request': decide add, the chart change, the assignment."""
    return [decide(change="add", reuse=(), why="no team builds pages"), change_reply(add_dept(f"${dept}", name, purpose)),
            assignments(draft("a1", dept, title=title, brief="Build the cafe landing page."))]


def dept_change_payload(revision: int, change_id: str, dept: str, name: str, purpose: str = "") -> dict:
    """The body of `POST /api/chart/changes` that adds a department (the owner's hand, no model)."""
    node = NewNode(ref=f"${dept}", kind="department", name=name, purpose=purpose, parent="root")
    change = ChartChange(kind="add", reason=f"add {name}", reuses=[], ops=[AddOp(node=node)], id=change_id, task_id="req-1",
                         base_revision=revision, ts=1)
    return change.model_dump(mode="json")


# ---- the event stream --------------------------------------------------------------------------------------------------------

class SseRecorder:
    """A thread that holds `GET /api/events` open and keeps every frame as `{"type", "id", "data"}`, in arrival order. It does not
    reconnect: a server that stops ends the stream (`closed` becomes true)."""

    def __init__(self, base_url: str, after: int | None = None) -> None:
        self.frames: list[dict] = []
        self.closed = False
        self.error: str | None = None
        self._lock = threading.Lock()
        self._url = base_url + "/api/events" + (f"?after={after}" if after is not None else "")
        self._response: httpx.Response | None = None
        self._thread = threading.Thread(target=self._run, name="sse-recorder", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, read=None)) as client, client.stream("GET", self._url) as response:
                self._response = response
                frame: dict[str, Any] = {}
                for line in response.iter_lines():
                    if line == "":
                        if "type" in frame:
                            with self._lock:
                                self.frames.append(frame)
                        frame = {}
                    elif line.startswith("event: "):
                        frame["type"] = line[7:]
                    elif line.startswith("id: "):
                        frame["id"] = int(line[4:])
                    elif line.startswith("data: "):
                        frame["data"] = json.loads(line[6:])
        except Exception as exc:                          # noqa: BLE001  (the server stopped, or the test closed the stream)
            self.error = repr(exc)
        finally:
            self.closed = True

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self.frames)

    def types(self) -> list[str]:
        return [f["type"] for f in self.snapshot()]

    def of(self, *types: str) -> list[dict]:
        return [f for f in self.snapshot() if f["type"] in types]

    def data(self, type_: str) -> list[dict]:
        return [f["data"] for f in self.snapshot() if f["type"] == type_]

    def index(self, type_: str, after: int = 0, where: Callable[[dict], bool] | None = None) -> int | None:
        """The position of the first frame of `type_` at or after `after` that `where` accepts, else None."""
        for at, frame in enumerate(self.snapshot()):
            if at >= after and frame["type"] == type_ and (where is None or where(frame["data"])):
                return at
        return None

    def close(self) -> None:
        response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:                              # noqa: BLE001
                pass
        self._thread.join(5)


# ---- the browser the engine's checks run in ------------------------------------------------------------------------------

FAKE_CHROME = r'''#!__PYTHON__
"""A stand-in for headless Chrome for J2's render checks (j2_check.find_chrome reads J2_CHROME). It answers the two wrappers J2
writes (`--dump-dom file://.../wrap.html`) the way a clean page would: both widths without overflow or script errors, every form
submittable, no small tap target. A behaviour wrapper or a screenshot gets no answer, which J2 reads as 'Chrome ran but never
reported', exactly what the recorded engine runs of E7 saw."""
import json, re, sys, html
args = sys.argv[1:]
url = next((a for a in args if a.startswith("file://")), "")
wrap = open(url[len("file://"):], encoding="utf-8").read() if url else ""
if "--dump-dom" not in args or "data-name=" not in wrap and "const f = document.querySelector('iframe')" not in wrap:
    sys.exit(0)
site = ""
try:
    site = open(url[len("file://"):].rsplit("/", 1)[0] + "/site.html", encoding="utf-8").read()
except OSError:
    pass
if "data-name=" in wrap:
    forms = [{"index": i + 1, "has_submit": True, "submitted": True, "invalid": [], "errors_during": []}
             for i in range(len(re.findall(r"<form\b", site, re.I)))]
    def design(phone):
        d = {"contrast": {"checked": 12, "low_count": 0, "low": []}, "headings": {"h1": 1, "skipped_levels": 0},
             "images_without_alt": [], "images": 0, "fonts": ["Inter"], "nav": {"nav_elements": 1, "in_page_links": 3},
             "first_screen_actions": ["Order"]}
        if phone:
            d["small_tap_targets"] = {"min_px": 44, "count": 0, "examples": []}
        return d
    out = {"phone": {"width": 360, "scroll_width": 360, "errors": [], "design": design(True), "forms": forms},
           "desktop": {"width": 1280, "scroll_width": 1280, "errors": [], "design": design(False)}}
else:
    out = {"roots": 1, "checked": 0, "revealed": False, "small_count": 0, "small": []}
print('<html><body data-j2="%s"></body></html>' % html.escape(json.dumps(out), quote=True))
'''


def write_fake_chrome(path: Path) -> str:
    path.write_text(FAKE_CHROME.replace("__PYTHON__", sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


# ---- time ----------------------------------------------------------------------------------------------------------------------

class ControlledClock:
    """The wall clock plus an offset the test can move: `jump(40)` makes the app believe 40 seconds went by (the watcher's and
    the reconcile pass's silence checks read it), without waiting."""

    def __init__(self) -> None:
        self.offset = 0.0

    def jump(self, seconds: float) -> None:
        self.offset += seconds

    def time(self) -> float:
        return time.time() + self.offset

    def now(self) -> int:
        return int(self.time())


# ---- the fake claude and codex -----------------------------------------------------------------------------------------------

class FakeCliBin:
    """The fake `claude` and `codex` of tests/fakes, fed from a queue: every model call (`-p` for claude, `exec` for codex) takes
    the next JSON reply from `<root>/queue-<cli>/` (the fake's own FAKE_REPLY_JSON is one value per process, but a chat turn needs
    three different replies). Probes (`--help`, `--version`, auth status) take nothing. Per-CLI scenario sequences, e.g. `quota`,
    go in `claude_sequence` / `codex_sequence`. `calls()` reads the fake's call log."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state = self.root / "fake-state"
        self.bin = self.root / "fake-bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        self.counts = {"claude": 0, "codex": 0}
        self.sequence: dict[str, str] = {}
        self._made = False

    def _write(self, cli: str) -> str:
        queue = self.root / f"queue-{cli}"
        queue.mkdir(parents=True, exist_ok=True)
        flag = '-p' if cli == "claude" else 'exec'
        script = self.bin / cli
        script.write_text(
            "#!/bin/sh\n"
            f'queue="{queue}"\n'
            "call=0\n"
            f'for a in "$@"; do [ "$a" = "{flag}" ] && call=1; done\n'
            'for a in "$@"; do [ "$a" = "--help" ] && call=0; done\n'
            'if [ "$call" = 1 ]; then\n'
            '  next=$(ls "$queue" 2>/dev/null | sort | head -n 1)\n'
            '  if [ -n "$next" ]; then FAKE_REPLY_JSON=$(cat "$queue/$next"); export FAKE_REPLY_JSON; rm -f "$queue/$next"; fi\n'
            "fi\n"
            f'exec "{FAKES / cli}" "$@"\n')
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return str(script)

    def push(self, cli: str, *replies: dict) -> None:
        queue = self.root / f"queue-{cli}"
        queue.mkdir(parents=True, exist_ok=True)
        for reply in replies:
            self.counts[cli] += 1
            (queue / f"{self.counts[cli]:06d}.json").write_text(json.dumps(reply))

    def config_kwargs(self) -> dict[str, Any]:
        env = {"FAKE_CLI_STATE": str(self.state), "FAKE_PYTHON": sys.executable, "FAKE_MAX_SECONDS": "20",
               "FAKE_COST_USD": "0.01", "FAKE_USAGE": json.dumps({"input_tokens": 120, "output_tokens": 30})}
        for cli, value in self.sequence.items():
            env[f"FAKE_{cli.upper()}_SEQUENCE"] = value
        return {"data_dir": self.root / "data", "work_root": self.root / "work", "claude_exe": self._write("claude"),
                "codex_exe": self._write("codex"), "gh_exe": str(FAKES / "gh"), "python": sys.executable, "extra_env": env}

    def calls(self, cli: str | None = None) -> list[dict]:
        out = []
        try:
            lines = (self.state / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            return out
        for raw in lines:
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if rec.get("kind") == "call" and (cli is None or rec.get("cli") == cli):
                out.append(rec)
        return sorted(out, key=lambda r: r["n"])


# ---- the app --------------------------------------------------------------------------------------------------------------------

def engine_environment(root: Path) -> dict[str, str]:
    """The environment the engine processes are launched from: this process's, minus every name the engine reads for itself."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_", "SUTRA_", "FAKE_"))}
    env["SUTRA_ENV_FILE"] = str(Path(root) / "none.env")
    return env


class LiveApp:
    """One app on `root/data`, listening on a free port of 127.0.0.1. `start()` returns after the lifespan finished (reconcile
    included); `stop()` is the owner closing the app; `crash()` is the server dying without its stop ladders (the engine
    processes live on). Use it as a context manager, or call `kill_engines()` yourself: a test must not leave a process behind."""

    def __init__(self, root: Path, *, connector: Any = None, launcher: Any = None, clock: Any = None, watch_ms: int = 50, max_runs: int = 3,
                 max_live: int = 12, mock_delay: float | None = None, heartbeat: float = 0.5, connector_name: str = "stub", offline: bool = True,
                 stop_grace: float = 3.0, term_grace: float = 2.0, extra_env: dict[str, str] | None = None, cli: "FakeCliBin | None" = None,
                 record: bool = True) -> None:
        self.root = Path(root)
        self.settings = Settings.load({}, data_dir=self.root / "data", token=TOKEN, env_file=self.root / "none.env", engine="process",
                                      watch_ms=watch_ms, max_runs=max_runs, max_live=max_live, connector=connector_name, offline=offline)
        env = {"J2_CHROME": write_fake_chrome(self.root / "fake-chrome"), "SUTRA_HEARTBEAT_S": str(heartbeat), **(extra_env or {})}
        if mock_delay is not None:
            env["STUDIO_MOCK_DELAY"] = str(mock_delay)
        if not offline:
            env["SUTRA_MOCK"] = "1"                         # the chat agent talks to the fake CLIs; the engine still plays J2's mock
        self.launcher = launcher or ProcessLauncher(environ=engine_environment(self.root), extra_env=env, stop_grace=stop_grace,
                                                    term_grace=term_grace)
        self.connector, self.clock, self.record = connector, clock, record
        self.cli = cli
        self.app = None
        self.server: AppServer | None = None
        self.thread: threading.Thread | None = None
        self.port = 0
        self.sse: SseRecorder | None = None
        self.http: httpx.Client | None = None
        self.started = False
        self._access_state = None

    # ---- life --------------------------------------------------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def services(self):
        return self.app.state.services

    def start(self) -> "LiveApp":
        access = logging.getLogger("uvicorn.access")           # uvicorn empties its handlers when access_log is off: put them back at the end
        self._access_state = (access, list(access.handlers), access.propagate, access.disabled, access.level)
        sock = bind_socket("127.0.0.1", 0, scan=False)
        self.port = sock.getsockname()[1]
        settings = self.settings.model_copy(update={"port": self.port})
        self.settings = settings
        self.app = self._create_app(settings)
        config = uvicorn.Config(self.app, log_config=None, access_log=False, timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
        self.server = AppServer(config, services=self.services, url=self.base_url + "/", open_browser=False)
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, name="uvicorn-e2e", daemon=True)
        self.thread.start()
        deadline = time.time() + 60
        while not self.server.started:
            if not self.thread.is_alive():
                raise RuntimeError("the server thread ended before it started")
            if time.time() > deadline:
                raise RuntimeError("the server did not start within 60 s")
            time.sleep(0.02)
        self.http = httpx.Client(base_url=self.base_url, headers=HEADERS, timeout=30.0)
        if self.record:
            self.sse = SseRecorder(self.base_url)
            self.until("the event stream", lambda: self.sse.snapshot())
        self.started = True
        return self

    def _create_app(self, settings: Settings):
        """`create_app`; with `cli` the connector router the app builds is aimed at the fake claude and codex (the one argument
        `create_app` has no way to pass: the executables of `ConnectorConfig`)."""
        if self.cli is None:
            return create_app(settings, connector=self.connector, launcher=self.launcher, clock=self.clock)
        config = ConnectorConfig(**self.cli.config_kwargs())
        real = wiring.build_connector_router
        wiring.build_connector_router = lambda s, **kw: real(s, config=config, **kw)
        try:
            return create_app(settings, connector=self.connector, launcher=self.launcher, clock=self.clock)
        finally:
            wiring.build_connector_router = real

    def stop(self) -> None:
        """The owner closes the app: the lifespan runs the stop ladders of every live run."""
        self._shutdown(crash=False)

    def crash(self) -> None:
        """The server dies without its ladders: the lifespan finds the services already stopped and does nothing, so no engine
        is signalled and no task is settled. The engine processes (their own session) keep running."""
        self.services.stopped = True
        self._shutdown(crash=True)

    def _shutdown(self, *, crash: bool) -> None:
        if self.server is None or self.thread is None:
            return
        if self.http is not None:
            self.http.close()
            self.http = None
        self.server.should_exit = True
        self.thread.join(GRACEFUL_SHUTDOWN_S + 60)
        if self.thread.is_alive():
            raise RuntimeError("the server thread did not stop")
        if self.sse is not None:
            self.sse.close()
        if crash:
            self.services.db.close()
        self.started = False
        logger, handlers, propagate, disabled, level = self._access_state
        logger.handlers[:], logger.propagate, logger.disabled = handlers, propagate, disabled
        logger.setLevel(level)

    def kill_engines(self) -> None:
        """Teardown: SIGKILL every engine process this app's data folder knows that is still alive."""
        for pid in self.pids():
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    def pids(self) -> list[int]:
        found = []
        for (pid,) in self.rows("SELECT pid FROM tasks WHERE pid IS NOT NULL"):
            try:
                os.kill(pid, 0)
            except OSError:
                continue
            found.append(pid)
        return found

    def __enter__(self) -> "LiveApp":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        try:
            if self.started:
                self.stop()
        finally:
            self.kill_engines()

    # ---- driving ----------------------------------------------------------------------------------------------------------

    def until(self, what: str, check: Callable[[], Any], timeout: float = 60.0, every: float = 0.02) -> Any:
        end = time.time() + timeout
        while time.time() < end:
            found = check()
            if found:
                return found
            time.sleep(every)
        raise AssertionError(f"timed out after {timeout:.0f} s waiting for {what}")

    def get(self, path: str, **params: Any) -> Any:
        response = self.http.get(path, params=params or None)
        assert response.status_code == 200, f"GET {path}: {response.status_code} {response.text[:300]}"
        return response.json()

    def post(self, path: str, body: dict | None = None) -> httpx.Response:
        return self.http.post(path, json=body if body is not None else {})

    def write(self, session: str, text: str, **extra: Any) -> httpx.Response:
        return self.post(f"/api/chats/{session}/messages", {"text": text, **extra})

    def say(self, text: str, *script: Any, wait: bool = True) -> int:
        """The owner writes in the org chat; the scripted model answers with `script`; returns the message id once the turn is over."""
        if script:
            self.connector.push(*script)
        response = self.write(ORG, text)
        assert response.status_code == 202, response.text
        if wait:
            self.until("the chat turn to end", lambda: not self.services.runner.busy)
        return response.json()["message_id"]

    def add_department(self, dept: str, name: str, purpose: str = "") -> None:
        """The owner adds a team by hand (`POST /api/chart/changes`), without a model."""
        revision = self.get("/api/chart")["version"]
        change_id = f"chg-{int(self.one('SELECT max(seq) FROM chart_changes')) + 1:04d}"
        response = self.post("/api/chart/changes", dept_change_payload(revision, change_id, dept, name, purpose))
        assert response.status_code == 200, response.text

    def give_task(self, dept: str, text: str, title: str | None = None) -> str:
        response = self.post("/api/tasks", {"dept_id": dept, "text": text, **({"title": title} if title else {})})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    # ---- reading ----------------------------------------------------------------------------------------------------------

    def db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.settings.db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def rows(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        conn = self.db()
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def one(self, sql: str, *args: Any) -> Any:
        found = self.rows(sql, *args)
        return found[0][0] if found else None

    def task_status(self, task_id: str) -> str | None:
        return self.one("SELECT status FROM tasks WHERE id = ?", task_id)

    def task_row(self, task_id: str) -> sqlite3.Row:
        [row] = self.rows("SELECT * FROM tasks WHERE id = ?", task_id)
        return row

    def run_dir(self, task_id: str) -> Path:
        row = self.task_row(task_id)
        return self.settings.data_dir / "departments" / row["dept_id"] / "runs" / row["run_id"]

    def events_of(self, task_id: str) -> list[dict]:
        if self.task_row(task_id)["run_id"] is None:
            return []                                               # queued: no run folder yet
        path = self.run_dir(task_id) / "events.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def session_of(self, node_id: str) -> str:
        return self.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", node_id)

    def messages(self, session: str = ORG) -> list[dict]:
        return self.get(f"/api/chats/{session}/messages")["messages"]

    def cards(self, kind: str, session: str = ORG) -> list[dict]:
        return [m["card"] for m in self.messages(session) if m["kind"] == "card" and m["card"]["type"] == kind]

    def task_of_message(self, message_id: int) -> str:
        return self.one("SELECT id FROM tasks WHERE request_id = ?", f"req-{message_id}")

    def settled(self, task_id: str, timeout: float = 90.0) -> str:
        """Wait until the task is over (any terminal status) and return it."""
        return self.until(f"task {task_id} to end", lambda: (self.task_status(task_id) in TERMINAL) and self.task_status(task_id), timeout)

    def ended(self, task_id: str, status: str = "done", timeout: float = 90.0) -> None:
        got = self.settled(task_id, timeout)
        assert got == status, f"task {task_id} ended {got}, not {status}: {self.task_row(task_id)['outcome']}"


@dataclass
class Journey:
    """One owner message to a new team, through to Done: what the tests of the scenario look at afterwards."""

    live: LiveApp
    message_id: int
    task: str
    digest0: str                    # the chart digest the first prompt must carry (taken before the message)
    needs: list[dict]               # GET /api/needs-you while Identity waited
    question: str
    sse_before_answer: int          # how many frames the stream held when the owner answered
    answer_response: dict

    @property
    def run_id(self) -> str:
        return self.live.task_row(self.task)["run_id"]


def run_new_team(live: LiveApp, message: str = FIRST_MESSAGE, answer: str = ANSWER, script: list[dict] | None = None,
                 timeout: float = 90.0) -> Journey:
    """The owner's first message makes the Web team and its task; the real engine starts, Identity asks, the owner answers in
    the department chat, the run ends. Returns once the task is over (the caller asserts how)."""
    digest0 = live.services.chart.digest(message, max_chars=DIGEST_CHARS)
    mid = live.say(message, *(script if script is not None else new_team_script()))
    task = live.task_of_message(mid)
    live.until("Identity's question", lambda: live.task_status(task) in ("waiting_user", *TERMINAL), timeout)
    needs = live.get("/api/needs-you")
    asked = [m["text"] for m in live.messages(live.session_of("web")) if m["kind"] == "question"]
    mark = len(live.sse.snapshot())
    response = live.write(live.session_of("web"), answer)
    assert response.status_code == 200, response.text
    live.settled(task, timeout)
    return Journey(live, mid, task, digest0, needs, asked[0] if asked else "", mark, response.json())


def pid_alive(pid: int) -> bool:
    """True while the process runs. A child of this test process that has died is reaped here (a server that was 'killed' in a
    test leaves its engine as a zombie of the test process, which `kill(pid, 0)` would still call alive)."""
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done == pid:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def atoms_left_open(events: list[dict]) -> list[str]:
    """The atoms of an engine's own event file whose LAST line says `open`: what the engine left open when it ended (the server
    abandons them in the database anyway, so only the file shows whether the engine closed its books)."""
    last: dict[str, str] = {}
    for event in events:
        if event["t"] == "atom":
            last[event["atom"]["id"]] = event["atom"]["status"]
    return sorted(atom for atom, status in last.items() if status == "open")


def terminate_all(pids: Iterable[int]) -> None:
    for pid in pids:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            pass
