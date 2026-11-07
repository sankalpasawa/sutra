"""The fake backend of the UI tests (UI-0, docs/design/ui.md sections 8 and 10, D85).

`make_app(fixtures_dir)` returns a FastAPI app that mounts the REAL UI package (pages, boot block, CSP, `/ui` static
files) and answers the paths of the UI-to-server contract (ORCH section 6, as patched by S1 to S4) from the JSON files of
`tests/ui/fixtures/`: the chart, the graph, the chats, the departments, "needs you", the Atom log, the health, the engine
Settings, the connector Test and Sign in paths, the event stream, and J2's own 28 routes at the root with `?dept=`.
Everything uses the library ids (`root`, `web`, `web.identity`, `s-3f9a1c2b7d`, `cs_org`, `chg-0002`, `req-17`), J2's nine
status words, the edge kinds of S3-web-13 and the five atom words. Errors of the new routes are `{error:{code,message,details}}`;
J2's routes keep J2's bodies. Writes need the header `X-Sutra-Token` (`TOKEN`) and a matching Origin, as the real server does.

The state is a STAGE of the story the fixtures tell:

    stage  chart  graph  what the owner sees
    "1"    1      1      a new app: only the root, the greeting
    "2"    2      2      "A website for my cafe": the Web team exists and Identity asks about the menu
    "3"    2      3      the owner answered: Identity is idle, Adaptation proposes
    "full" 3      full   two teams (Web, Content), two divisions, a pending merge, every J2 status word on some node

`chart` (with `changes`) and `graph` have their own version; departments, "needs you" and what each chat shows follow the
graph. A chat fixture holds the whole conversation; `visible_at` says how much of it each graph version shows.

Test-only controls (not under /api, no token):
    POST /__fake/emit {event, data?}          publish one of the 14 events (data defaults to the sample of events.script.json;
                                               a chat.message also stores its message); server.hello/resync go to live streams only
    POST /__fake/fixture {name, version}      name chart (the chart and its change log) | graph | stage | sign_in (see STAGES)
    POST /__fake/fail {path, status, ...}     answer `path` with `status` (method, code, message, details, count are optional;
                                               status null or 200 clears); failing /api/events also ends the open streams
    GET  /__fake/log[?prefix=]                the requests seen: [{n, method, path, query, status, token, body}]
    GET  /__fake/state                        stages, failures, open streams, last event id
    POST /__fake/reset                        back to stage 1, empty log and ring (open streams get server.resync)
    POST /__fake/page {name, html}            register /__fake/mount/<name>.html for a test of one view
    GET  /__fake/mount/<name>.html            a page that loads ONE module: fixtures/mount_<name>.html (graph, panel) or a registered one

`run_in_thread(app)` serves the app on a free loopback port. `FakeClient` talks to it over HTTP. Run it by hand to look at a
page: `scripts/py tests/ui/fake_backend.py --port 8790`.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import hashlib
import hmac
import json
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NamedTuple
from urllib.parse import urlencode

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from sutra_app.library.types import atom_sid, function_atom_id
from sutra_app.ui import BootContext, build_router, mount, mount_static, render_page

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
TOKEN = "fake-token-0123456789abcdef0123"  # 32 characters, like secrets.token_urlsafe(24)
VERSION = "0.1.0"
RING_SIZE = 1000
PING_SECONDS = 15.0  # an SSE comment when a stream is idle (ORCH 6.3)
FLOW_STEP_SECONDS = 0.02  # the pause between the steps of a scripted flow; tests may set it to 0
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
# stage -> (chart version, graph version). `changes` follows the chart; departments, needs-you and chats follow the graph.
STAGES = {"1": ("1", "1"), "2": ("2", "2"), "3": ("2", "3"), "full": ("3", "full")}
EVENT_NAMES = (
    "server.hello", "server.resync", "chat.turn", "chat.message", "chart.changed", "chart.approval", "graph.updated",
    "task.updated", "atom.updated", "usage.recorded", "needs_you.changed", "connector.health", "connector.switch",
    "connector.mode",
)
CONTROL_EVENTS = ("server.hello", "server.resync")  # no `id:` line, never in the ring
DEPT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
HOSTS = ("127.0.0.1", "localhost")
TASK_STATUS = {"running": "running", "waiting_on_you": "waiting_user", "filed": "done", "left_open": "done_with_open_items",
               "fault": "crashed", "idle": "queued", "not_made": "queued", "waiting": "running", "done_unchecked": "done"}
SANDBOX = "sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'"  # generated HTML (S3-web-14)
ENGINE_ENUMS = {"output": ("website", "prd", "hld", "lld"), "fixes": (0, 1), "send_mode": ("dry-run", "mock", "live")}
ENGINE_MIN = {"budget": 1, "max_cycles": 1, "max_turns": 1, "chat_full_chars": 1000, "budget_cap": 1}
DEFAULT_MESSAGES = {
    400: ("bad_request", "The request is not valid."),
    401: ("bad_token", "This page was opened without its access token. Reload it from the app."),
    403: ("read_only", "This chat is read-only."),
    404: ("not_found", "Not found."),
    409: ("busy", "The team is working. You can write again when it asks you something or is done"),
    422: ("validation", "The request did not pass validation."),
    429: ("too_many_pending", "Too many messages are waiting. I answer them one at a time."),
    500: ("internal", "Something went wrong on the server."),
    503: ("provider_unavailable", "No model is available right now: Claude and Codex are both unavailable."),
}


class FixtureError(RuntimeError):
    """A fixture file is missing or does not have the shape the fake needs."""


class ApiError(Exception):
    """An error of a new route: answered as `{error:{code,message,details}}`."""

    def __init__(self, status: int, code: str | None = None, message: str | None = None, details: dict | None = None) -> None:
        default_code, default_message = DEFAULT_MESSAGES.get(status, ("internal", "Error."))
        self.status, self.code = status, code or default_code
        self.message, self.details = message or default_message, details or {}
        super().__init__(f"{status} {self.code}: {self.message}")


class J2Reject(Exception):
    """An error of a J2 route: J2's own body (`{"error": "..."}` or `{"ok": false}`)."""

    def __init__(self, status: int, body: dict) -> None:
        self.status, self.body = status, body
        super().__init__(f"{status} {body}")


def envelope(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details or {}}}, status_code=status)


def violation(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def short_hash(text: str, size: int) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:size]


def iso_at(seconds: int) -> str:
    """The wire time of a message made by the fake: 2026-11-04T10:05:00Z plus `seconds`."""
    total = 10 * 3600 + 5 * 60 + seconds
    return f"2026-11-04T{total // 3600 % 24:02d}:{total // 60 % 60:02d}:{total % 60:02d}Z"


# ---------------------------------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------------------------------
class Fixtures:
    """Every JSON file of the fixtures folder, read once. Nothing here changes; `FakeState` copies what it hands out."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.charts = self._versions("chart.v*.json", r"chart\.v(\d+)\.json")
        self.changes = self._versions("changes.v*.json", r"changes\.v(\d+)\.json")
        self.graphs = self._versions("graph.v*.json", r"graph\.v(\d+)\.json")
        self.graphs["full"] = self.json("graph-full.json")
        self.departments = self.json("departments.json")
        self.needs_you = self.json("needs-you.json")
        self.functions = self.json("functions.json")
        self.node_identity = self.json("node-identity.json")
        self.atom_log = self.json("atom-log.json")
        self.health = self.json("health.json")
        self.engine_settings = self.json("engine-settings.json")
        self.connectors = self.json("connectors.json")
        self.script = self.json("events.script.json")
        self.chats: list[dict] = []
        for name in ("chat-org.json", "chat-dept.json", "chat-identity.json", "chat-division.json"):
            self.chats.append(self.json(name))
        self.chats += self.json("chat-others.json")["sessions"]
        self.j2 = J2Fixtures(self.root / "j2")

    def path(self, name: str) -> Path:
        return self.root / name

    def json(self, name: str) -> Any:
        try:
            return json.loads(self.path(name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FixtureError(f"fixture {name} is missing in {self.root}") from None
        except ValueError as exc:
            raise FixtureError(f"fixture {name} is not valid JSON: {exc}") from None

    def _versions(self, pattern: str, regex: str) -> dict[str, Any]:
        found = {}
        for path in sorted(self.root.glob(pattern)):
            match = re.fullmatch(regex, path.name)
            if match:
                found[match.group(1)] = self.json(path.name)
        if not found:
            raise FixtureError(f"no {pattern} in {self.root}")
        return found


class J2Fixtures:
    """What `scripts/capture_j2_fixtures.py` saved: J2's own answers, byte for byte, served by the J2 routes."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._cache: dict[str, bytes] = {}

    def raw(self, name: str) -> bytes | None:
        if name not in self._cache:
            path = self.folder / name
            if not path.is_file():
                return None
            self._cache[name] = path.read_bytes()
        return self._cache[name]

    def json(self, name: str) -> Any:
        data = self.raw(name)
        return None if data is None else json.loads(data)


# ---------------------------------------------------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------------------------------------------------
class Chat:
    """One session: its fixture conversation (shown up to `visible`) and the messages added since (always shown)."""

    def __init__(self, fixture: dict) -> None:
        self.info: dict = fixture["session"]
        self.fixture: list[dict] = fixture["messages"]
        self.initial = int(fixture.get("initial_visible", 0))
        self.visible_at: dict[str, int] = fixture.get("visible_at", {})
        self.reset()

    def reset(self) -> None:
        self.visible = self.initial
        self.extra: list[dict] = []
        self.text_override: dict[int, str] = {}

    @property
    def sid(self) -> str:
        return self.info["id"]

    def next_id(self) -> int:
        ids = [m["id"] for m in self.fixture] + [m["id"] for m in self.extra]
        return max(ids, default=0) + 1

    def messages(self) -> list[dict]:
        """What the session shows now, with each question's `answered_by` read live from the owner's next line."""
        shown = [copy.deepcopy(m) for m in self.fixture[: self.visible]] + copy.deepcopy(self.extra)
        for m in shown:
            if m["id"] in self.text_override:
                m["text"] = self.text_override[m["id"]]
        for index, m in enumerate(shown):
            if m["kind"] == "question":
                m["answered_by"] = next((later["id"] for later in shown[index + 1:] if later["role"] == "user"), None)
        return shown

    def session_out(self) -> dict:
        out = copy.deepcopy(self.info)
        shown = self.messages()
        out["last_message_id"] = shown[-1]["id"] if shown else 0
        return out


# ---------------------------------------------------------------------------------------------------------------------
# The event bus
# ---------------------------------------------------------------------------------------------------------------------
class Subscriber:
    """One open event stream. `notify` is safe to call from any thread."""

    def __init__(self, loop: asyncio.AbstractEventLoop, topics: set[str] | None) -> None:
        self.loop, self.topics = loop, topics
        self.queue: asyncio.Queue = asyncio.Queue()

    def wants(self, event: str) -> bool:
        return self.topics is None or event.split(".")[0] in self.topics or event.startswith("server.")

    def notify(self, item: Any) -> None:
        with contextlib.suppress(RuntimeError):  # the loop is gone: the stream is over
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)


# ---------------------------------------------------------------------------------------------------------------------
# The state
# ---------------------------------------------------------------------------------------------------------------------
class FakeState:
    """All the mutable state of one fake app. Every public method is safe to call from any thread."""

    def __init__(self, fixtures: Fixtures, *, token: str = TOKEN, version: str = VERSION) -> None:
        self.fx = fixtures
        self.token, self.version = token, version
        self.lock = threading.RLock()
        self.chats = {chat["session"]["id"]: Chat(chat) for chat in fixtures.chats}
        self.subscribers: list[Subscriber] = []
        self.closing = False
        self.generation = 0  # raised by every reset: a scripted flow that started before it stops at its next step
        self.flows_running = 0
        self.reset(announce=False)

    # -- life cycle ------------------------------------------------------------------------------------------------
    def reset(self, *, announce: bool = True) -> None:
        with self.lock:
            self.generation += 1
        deadline = time.monotonic() + 3  # a flow of the old story ends at its next step (FLOW_STEP_SECONDS), not after the reset
        while self.flows_running > 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        with self.lock:
            self.chart_stage, self.graph_stage = "1", "1"
            self.ring: list[dict] = []
            self.seq = 0
            self.log: list[dict] = []
            self.failures: list[dict] = []
            self.pages: dict[str, str] = {}
            self.answered: set[str] = set()
            self.flows_played: set[str] = set()
            self.clock = 0
            self.phase: str | None = None
            es = self.fx.engine_settings
            self.layers = {"global": copy.deepcopy(es["global"]), "dept": {"web": copy.deepcopy(es.get("department", {}))}}
            self.codex_signed_in = bool(self.fx.health["connectors"]["codex"]["signed_in"])
            self.cli_paths: dict[str, str] = {}                 # PUT /api/connectors/{provider}/path (GAP-providers)
            self.signins: dict[str, dict] = {}
            self.signin_sequence = "success"
            self.heads_up: list[dict] = []          # gap attention: GET /api/heads-up (set by /__fake/heads-up), emptied of a task on its retry
            self.retried: list[str] = []
            for chat in self.chats.values():
                chat.reset()
            self._apply_visibility()
        if announce:
            self.publish_control("server.resync", {"reason": "restart"})

    def close(self) -> None:
        """Called before the server stops: ends every open stream so the server can shut down."""
        self.closing = True
        self.wake_all()

    def wake_all(self) -> None:
        with self.lock:
            subscribers = list(self.subscribers)
        for sub in subscribers:
            sub.notify(None)

    # -- the story ---------------------------------------------------------------------------------------------------
    def set_stage(self, label: str) -> None:
        if label not in STAGES:
            raise ApiError(422, "validation", f"stage must be one of {', '.join(STAGES)}, not {label!r}")
        with self.lock:
            self.chart_stage, self.graph_stage = (STAGES[label][0], STAGES[label][1])
            self._apply_visibility()

    def set_fixture(self, name: str, version: Any, *, keep: frozenset[str] = frozenset()) -> dict:
        """Switch what the routes serve. A new graph version also sets how much each chat shows, except for the sessions in
        `keep` (a scripted flow reveals those itself, one message and one event at a time)."""
        version = str(version)
        with self.lock:
            if name == "stage":
                self.set_stage(version)
            elif name == "chart":  # the chart and its change log are one thing
                if version not in self.fx.charts or version not in self.fx.changes:
                    raise ApiError(422, "validation", f"no chart version {version!r}; have {', '.join(sorted(self.fx.charts))}")
                self.chart_stage = version
            elif name == "graph":
                if version not in self.fx.graphs:
                    raise ApiError(422, "validation", f"no graph version {version!r}; have {', '.join(self.fx.graphs)}")
                self.graph_stage = version
                self._apply_visibility(keep)
            elif name == "sign_in":
                if version not in self.fx.connectors["sign_in"]["sequences"]:
                    raise ApiError(422, "validation", f"no sign-in sequence {version!r}")
                self.signin_sequence = version
            else:
                raise ApiError(422, "validation", f"unknown fixture name {name!r}: chart, graph, stage or sign_in")
            return self.stages()

    def stages(self) -> dict:
        return {"chart": self.chart_stage, "graph": self.graph_stage, "sign_in": self.signin_sequence}

    def _apply_visibility(self, keep: frozenset[str] = frozenset()) -> None:
        for chat in self.chats.values():
            if chat.sid not in keep and self.graph_stage in chat.visible_at:
                chat.visible = chat.visible_at[self.graph_stage]

    # -- the data the routes hand out ----------------------------------------------------------------------------------
    def chart(self) -> dict:
        return copy.deepcopy(self.fx.charts[self.chart_stage])

    def changes(self, after: int = 0, limit: int = 50) -> list[dict]:
        rows = [c for c in self.fx.changes[self.chart_stage] if c["seq"] > after]
        return copy.deepcopy(rows[:limit])

    def full_graph(self) -> dict:
        return copy.deepcopy(self.fx.graphs[self.graph_stage])

    def graph(self, level: str, dept: str | None, task: str | None) -> dict:
        graph = self.full_graph()
        if dept is not None and not any(n.get("dept_id") == dept for n in graph["nodes"]):
            raise ApiError(404, "not_found", f"No team {dept!r} in the graph.")

        def keep(node: dict) -> bool:
            if level == "chart" and node["kind"] not in ("root", "department", "division") and not (
                    node["kind"] == "step" and node["step_ref"] == "task"):
                return False
            if dept is not None and node["id"] != "root" and node.get("dept_id") != dept:
                return False
            if task is not None and node["kind"] == "step" and node["task_id"] != task:
                return False
            return True

        graph["nodes"] = [n for n in graph["nodes"] if keep(n)]
        ids = {n["id"] for n in graph["nodes"]}
        graph["edges"] = [e for e in graph["edges"] if e["src"] in ids and e["dst"] in ids]
        return graph

    def node(self, node_id: str) -> dict | None:
        return next((n for n in self.fx.graphs[self.graph_stage]["nodes"] if n["id"] == node_id), None)

    def departments(self) -> list[dict]:
        return copy.deepcopy(self.fx.departments.get(self.graph_stage, []))

    def department(self, dept_id: str) -> dict | None:
        return next((d for d in self.departments() if d["id"] == dept_id), None)

    def needs_you(self) -> list[dict]:
        items = copy.deepcopy(self.fx.needs_you.get(self.graph_stage, []))
        return [item for item in items if item["session_id"] not in self.answered]

    def known_runs(self, dept: str) -> set[str]:
        """The runs of one team that a `?run=` may name (D73: another team's run is `not_found`): the run J2 itself recorded
        (the Web team's) and every run a graph node of this team points to in any graph version (`meta.run_id`), so the link
        of a finished step node opens the same saved view."""
        runs = {r["id"] for r in (self.fx.j2.json("runs.json") or {}).get("runs", [])} if dept == "web" else set()
        for graph in self.fx.graphs.values():
            runs |= {n["meta"]["run_id"] for n in graph["nodes"] if n.get("dept_id") == dept and n["meta"].get("run_id")}
        return runs

    def session_ids(self) -> dict[str, dict]:
        """Session id -> graph node, for the nodes of the current graph: the sessions that exist now."""
        return {n["chat_session_id"]: n for n in self.fx.graphs[self.graph_stage]["nodes"] if n.get("chat_session_id")}

    def chat(self, sid: str) -> Chat:
        node = self.session_ids().get(sid)
        if node is None:
            raise ApiError(404, "not_found", "This chat is gone.")
        chat = self.chats.get(sid)
        if chat is None:  # a node with no conversation of its own: a read-only (or writable) empty session
            kind = {"root": "org"}.get(node["kind"], node["kind"])
            writable = kind in ("org", "department", "division")
            chat = Chat({"session": {
                "id": sid, "node_id": node["id"], "kind": kind, "title": node["label"], "writable": writable, "status": "active",
                "filed_under": None, "connector": "claude" if kind in ("function", "step", "department") else None,
                "model": None, "provider_session_id": None, "last_message_id": 0, "note": ""}, "messages": []})
            self.chats[sid] = chat
        return chat

    def task_of(self, node: dict) -> dict | None:
        """The task a node works for: the task step of its department."""
        if node["kind"] not in ("department", "function", "step"):
            return None
        step = next((n for n in self.fx.graphs[self.graph_stage]["nodes"]
                     if n["kind"] == "step" and n["step_ref"] == "task" and n["dept_id"] == node.get("dept_id")), None)
        if step is None:
            return None
        return {"id": step["task_id"], "title": step["label"], "status": TASK_STATUS.get(step["status"], "running")}

    # -- atoms -------------------------------------------------------------------------------------------------------
    def _atom_ts(self, index: int) -> str:
        return f"2026-11-04T10:{index // 60 % 60:02d}:{index % 60:02d}Z"

    def function_atoms(self, node: dict) -> list[dict]:
        """The atoms of one function node, open first, then newest first. Identity's come from `node-identity.json`; the
        others are made from the node's own counts, so the list always agrees with the chip."""
        if node["id"] == "web.identity":
            return self.identity_atoms(node["meta"]["stats"])
        stats = node["meta"]["stats"]
        fn, dept = node["fn"], node["dept_id"]
        template = self.fx.functions["atom_templates"][fn]
        meta = self.fx.functions["meta"][fn]
        texts = self.fx.functions["check_text"]
        run_id = "j2-20261104-100004-7f3a" if dept == "web" else "j2-20261104-103300-2c9e"
        sid = atom_sid(run_id, node["id"])
        task_id = (self.task_of(node) or {}).get("id")
        n_open, n_closed, n_failed = min(stats["atoms_open"], 1), stats["atoms_closed"], stats["atoms_failed"]
        n_other = max(0, stats["atoms_total"] - n_open - n_closed - n_failed)
        plan = ["closed"] * n_closed + ["verify_failed"] * n_failed + ["abandoned"] * n_other + ["open"] * n_open
        atoms = []
        for index, state in enumerate(plan, start=1):
            attempt = {"closed": 1, "verify_failed": 2, "abandoned": 1, "open": 0}[state]
            checks = []
            for check in template["checks"]:
                results = [{"attempt": a, "exit_code": 0, "evidence": "ok"} for a in range(1, attempt + 1)]
                if state == "verify_failed" and check is template["checks"][-1]:
                    results[-1] = {"attempt": attempt, "exit_code": 1, "evidence": texts[check["template"]] + ": not met"}
                checks.append({"template": check["template"], "args": check["args"], "text": texts[check["template"]],
                               "relevance": f"declared: {check['template']}", "relevance_source": "declared", "results": results})
            body: dict = {"constraints": [{"text": t, "check": None} for t in meta["constraints"][:2]], "context": meta["context"][:2],
                          "work": {"dispatch_kind": "llm", "agent": fn, "steps": template["steps"], "how_kind": "AI"},
                          "model": template["model"], "verify": {"checks": checks}, "outputs": template["outputs"], "touches": []}
            if state == "closed":
                body["closed_by"] = "verify"
            elif state == "verify_failed":
                body.update(closed_by="manual-override", abandon_code="verify_failed", reason="verify failed: " + checks[-1]["text"])
            elif state == "abandoned":
                body.update(closed_by="manual-override", abandon_code="run_ended", reason="run ended: stopped")
            terminal = state != "open"
            calls = 0 if state == "abandoned" else 2 + index
            atoms.append({
                "id": function_atom_id(sid, index), "schema": "work-atom/0.3", "node_id": node["id"], "task_id": task_id,
                "state": state, "goal": template["goal"], "attempt": attempt, "ts_open": self._atom_ts(index * 10),
                "ts_closed": self._atom_ts(index * 10 + 7) if terminal else None, "body": body,
                "usage": {"calls": calls, "usd": round(calls * 0.03, 2) if calls else None,
                          "tokens_in": calls * 600 if calls else None, "tokens_out": calls * 180 if calls else None}})
        open_first = [a for a in atoms if a["state"] == "open"]
        rest = sorted((a for a in atoms if a["state"] != "open"), key=lambda a: a["ts_open"], reverse=True)
        return open_first + rest

    def identity_atoms(self, stats: dict) -> list[dict]:
        """Identity's five hand-made atoms (`node-identity.json`, all five display words). When the graph says the node
        has no open atom any more (stage 3: the owner answered), the open one is closed by a third passing try, so the
        drawer, the chip and `/api/atoms` always agree."""
        atoms = copy.deepcopy(self.fx.node_identity["atoms"])
        if stats["atoms_open"] == 0:
            for atom in atoms:
                if atom["state"] != "open":
                    continue
                atom["state"], atom["attempt"] = "closed", atom["attempt"] + 1
                atom["ts_closed"] = self._atom_ts(2 * 60 + 15)
                atom["body"]["closed_by"] = "verify"
                for check in atom["body"]["verify"]["checks"]:
                    check["results"].append({"attempt": atom["attempt"], "exit_code": 0, "evidence": "ok"})
                atom["usage"] = {"calls": 9, "usd": 0.32, "tokens_in": 5400, "tokens_out": 1620}
        return atoms

    def all_atoms(self) -> list[dict]:
        atoms: list[dict] = []
        for node in self.fx.graphs[self.graph_stage]["nodes"]:
            if node["kind"] == "function":
                atoms += self.function_atoms(node)
        return atoms

    def atom_log(self) -> list[dict]:
        if self.node("web.identity") is None:
            return []
        return copy.deepcopy(self.fx.atom_log)

    def node_detail(self, node_id: str) -> dict:
        node = self.node(node_id)
        if node is None:
            raise ApiError(404, "not_found", f"No node {node_id!r}.")
        node = copy.deepcopy(node)
        atoms: list[dict] = []
        usage = {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None}
        if node["kind"] == "function":
            meta = self.fx.functions["meta"][node["fn"]]
            stats = node["meta"]["stats"]
            node["meta"] = {"goal": meta["goal"], "task": meta["task"], "context": meta["context"], "constraints": meta["constraints"],
                            "wait_on": node["meta"].get("wait_on"), "hands_to": meta["hands_to"], "stats": stats}
            atoms = self.function_atoms(node)
            if stats["calls"]:
                usage = {"calls": stats["calls"], "usd": round(stats["calls"] * 0.035, 2), "tokens_in": stats["tokens_in"],
                         "tokens_out": stats["tokens_out"]}
        return {"node": node, "session": self.chat(node["chat_session_id"]).session_out(), "atoms": atoms, "usage_total": usage,
                "task": self.task_of(node), "archived_chats": []}

    # -- engine settings -----------------------------------------------------------------------------------------------
    def settings_view(self, dept: str | None) -> dict:
        es = self.fx.engine_settings
        layer = self.layers["dept"].setdefault(dept, {}) if dept else {}
        view = {"schema": es["schema"], "defaults": copy.deepcopy(es["defaults"]), "global": copy.deepcopy(self.layers["global"])}
        if dept:
            view["department"] = copy.deepcopy(layer)
        view["effective"] = {**es["defaults"], **self.layers["global"], **layer}
        view["editable"], view["locked"] = list(es["editable"]), list(es["locked"])
        return view

    def settings_put(self, dept: str | None, body: Any) -> dict:
        es = self.fx.engine_settings
        problems: list[dict] = []
        if not isinstance(body, dict) or set(body) - {"set", "unset"}:
            raise ApiError(422, "validation", "The body is {set: {field: value}, unset: [field]}.",
                           {"violations": [violation("", "bad_body", "the body is {set, unset}")]})
        sets, unsets = body.get("set", {}), body.get("unset", [])
        if not isinstance(sets, dict):
            problems.append(violation("set", "bad_type", "set must be an object"))
            sets = {}
        if not isinstance(unsets, list) or not all(isinstance(f, str) for f in unsets):
            problems.append(violation("unset", "bad_type", "unset must be a list of field names"))
            unsets = []
        for field, value in sets.items():
            problem = self._check_setting(field, value, es)
            if problem:
                problems.append(violation(f"set.{field}", *problem))
        for field in unsets:
            if field not in es["defaults"]:
                problems.append(violation(f"unset.{field}", "unknown_field", f"{field} is not a setting"))
            elif field in es["locked"]:
                problems.append(violation(f"unset.{field}", "locked_field", f"{field} can only be changed by hand in engine.json"))
        if problems:
            raise ApiError(422, "validation", f"Not saved: {problems[0]['message']}", {"violations": problems})
        with self.lock:
            layer = self.layers["dept"].setdefault(dept, {}) if dept else self.layers["global"]
            layer.update(copy.deepcopy(sets))
            for field in unsets:
                layer.pop(field, None)
        return self.settings_view(dept)

    @staticmethod
    def _check_setting(field: str, value: Any, es: dict) -> tuple[str, str] | None:
        if field not in es["defaults"]:
            return ("unknown_field", f"{field} is not a setting")
        if field in es["locked"]:
            return ("locked_field", f"{field} can only be changed by hand in engine.json")
        default = es["defaults"][field]
        if field in ENGINE_ENUMS:
            return None if value in ENGINE_ENUMS[field] and not isinstance(value, bool) else (
                "invalid_value", f"{field} must be one of {', '.join(map(str, ENGINE_ENUMS[field]))}")
        if field == "budget_cap" and value is None:
            return None
        if isinstance(default, bool):
            return None if isinstance(value, bool) else ("invalid_value", f"{field} must be true or false")
        if isinstance(default, int) or field == "budget_cap":
            if isinstance(value, bool) or not isinstance(value, int) or value < ENGINE_MIN.get(field, 0):
                return ("invalid_value", f"{field} must be a whole number of at least {ENGINE_MIN.get(field, 0)}")
            return None
        if isinstance(default, float):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                return ("invalid_value", f"{field} must be a number of at least 0")
            return None
        return None if isinstance(value, str) and len(value) <= 500 else ("invalid_value", f"{field} must be text of at most 500 characters")

    # -- connectors --------------------------------------------------------------------------------------------------
    def health(self) -> dict:
        health = copy.deepcopy(self.fx.health)
        if self.codex_signed_in:
            health["connectors"]["codex"].update(signed_in=True, detail="Signed in with ChatGPT", method="ChatGPT", billing="subscription",
                                                 health={"state": "ok", "until": None, "reason": None})
        for provider in self.cli_paths:
            if provider in health["connectors"]:
                health["connectors"][provider]["installed"] = True
        return health

    def set_cli_path(self, provider: str, body: Any) -> dict:
        """The real route's rules in small: claude or codex, a full path named as the command (the fake has no file system to look at)."""
        if provider not in ("claude", "codex"):
            raise ApiError(404, "not_found", f"{provider} has no command-line file to choose")
        if not isinstance(body, dict) or set(body) != {"path"} or not (body["path"] is None or isinstance(body["path"], str)):
            raise ApiError(422, "validation", "The body must be {\"path\": text or null}.")
        path = (body["path"] or "").strip()
        with self.lock:
            if not path:
                self.cli_paths.pop(provider, None)
            elif not path.startswith("/"):
                raise ApiError(422, "invalid_request", f"Write the full path, starting with / (or ~ for your home folder), as `which {provider}` prints it")
            elif path.rsplit("/", 1)[-1] != provider:
                raise ApiError(422, "invalid_request", f"Choose the file named {provider}: {path.rsplit('/', 1)[-1]} is not the {provider.capitalize()} command")
            else:
                self.cli_paths[provider] = path
            installed = provider in self.cli_paths or bool(self.fx.health["connectors"].get(provider, {}).get("installed"))
        self.publish("connector.health", {"provider": provider, "state": "ok", "until": None, "reason": None})
        return {"provider": provider, "path": self.cli_paths.get(provider), "installed": installed, "signed_in": True, "detail": "signed in"}

    def connector_test(self, provider: str) -> dict:
        tests = self.fx.connectors["test"]
        if provider not in tests:
            raise ApiError(404, "not_found", f"No connector {provider!r}.")
        if provider == "codex" and not self.codex_signed_in:
            error = self.fx.connectors["test_error"]["error"]
            raise ApiError(503, error["code"], error["message"], error["details"])
        return copy.deepcopy(tests[provider])

    def sign_in_start(self) -> dict:
        start = copy.deepcopy(self.fx.connectors["sign_in"]["start"])
        with self.lock:
            self.signins[start["id"]] = {"states": list(self.fx.connectors["sign_in"]["sequences"][self.signin_sequence]), "i": 0}
        return start

    def sign_in_poll(self, sign_in_id: str) -> dict:
        with self.lock:
            flow = self.signins.get(sign_in_id)
            if flow is None:
                raise ApiError(404, "not_found", "No such sign-in.")
            state = flow["states"][min(flow["i"], len(flow["states"]) - 1)]
            flow["i"] += 1
            became_signed_in = state == "signed_in" and not self.codex_signed_in
            if became_signed_in:
                self.codex_signed_in = True
        if became_signed_in:
            self.publish("connector.health", {"provider": "codex", "state": "ok", "until": None, "reason": None})
        return {"state": state}

    def sign_in_cancel(self, sign_in_id: str) -> None:
        with self.lock:
            if self.signins.pop(sign_in_id, None) is None:
                raise ApiError(404, "not_found", "No such sign-in.")

    # -- the event stream --------------------------------------------------------------------------------------------
    def publish(self, event: str, data: Any) -> dict:
        """One event with the next id, kept in the ring and sent to every open stream that wants it."""
        if event in CONTROL_EVENTS:
            return self.publish_control(event, data)
        with self.lock:
            self.seq += 1
            item = {"id": self.seq, "event": event, "data": copy.deepcopy(data)}
            self.ring.append(item)
            del self.ring[: max(0, len(self.ring) - RING_SIZE)]
            if event == "chat.turn":
                self.phase = None if data.get("phase") in ("done", "error") else data.get("phase")
            subscribers = [s for s in self.subscribers if s.wants(event)]
        for sub in subscribers:
            sub.notify(item)
        return item

    def publish_control(self, event: str, data: Any) -> dict:
        item = {"id": None, "event": event, "data": copy.deepcopy(data)}
        with self.lock:
            subscribers = [s for s in self.subscribers if s.wants(event)]
        for sub in subscribers:
            sub.notify(item)
        return item

    def sample(self, event: str) -> Any:
        return copy.deepcopy(self.fx.script["samples"][event])

    def emit(self, event: str, data: Any = None) -> dict:
        if event not in EVENT_NAMES:
            raise ApiError(422, "validation", f"{event!r} is not an event; the events are {', '.join(EVENT_NAMES)}")
        if data is None:
            data = self.sample(event)
        if event == "chat.message":
            self._store_event_message(data)
        return self.publish(event, data)

    def _store_event_message(self, data: Any) -> None:
        """An emitted chat.message is also stored, because the page refetches the session after it."""
        try:
            message = data["message"]
            chat = self.chat(message["session_id"])
        except (KeyError, TypeError):
            raise ApiError(422, "validation", "chat.message needs {session_id, message} with the message's own session_id") from None
        with self.lock:
            known = {m["id"] for m in chat.fixture[: chat.visible]} | {m["id"] for m in chat.extra}
            if message["id"] not in known:
                chat.extra.append(copy.deepcopy(message))

    def subscribe(self, loop: asyncio.AbstractEventLoop, topics: set[str] | None) -> Subscriber:
        sub = Subscriber(loop, topics)
        with self.lock:
            self.subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self.lock:
            if sub in self.subscribers:
                self.subscribers.remove(sub)

    def replay(self, after: int | None) -> tuple[list[dict], str | None]:
        """(events to replay, the reason for a resync or None) for a client that last saw event id `after`."""
        with self.lock:
            if after is None:
                return [], None
            if after > self.seq:
                return [], "restart"
            oldest = self.ring[0]["id"] if self.ring else self.seq + 1
            if after < oldest - 1 and self.seq > 0:
                return [], "gap"
            return [copy.deepcopy(e) for e in self.ring if e["id"] > after], None

    def hello(self) -> dict:
        return {"version": self.version, "chart_version": self.fx.charts[self.chart_stage]["version"],
                "graph_version": self.fx.graphs[self.graph_stage]["version"]}

    # -- failures ----------------------------------------------------------------------------------------------------
    def set_failure(self, spec: dict) -> list[dict]:
        path, status = spec.get("path"), spec.get("status")
        method = (spec.get("method") or "").upper() or None
        if not isinstance(path, str) or not path.startswith("/"):
            raise ApiError(422, "validation", "fail needs a path that starts with /")
        if status is not None and (isinstance(status, bool) or not isinstance(status, int) or not 200 <= status <= 599):
            raise ApiError(422, "validation", "status must be a whole number from 200 to 599, or null to clear")
        count = spec.get("count")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 1):
            raise ApiError(422, "validation", "count must be a whole number of at least 1")
        with self.lock:
            self.failures = [f for f in self.failures if not (f["path"] == path and f["method"] == method)]
            if status is not None and status != 200:
                code, message = DEFAULT_MESSAGES.get(status, ("internal", "Forced failure."))
                self.failures.append({"path": path, "method": method, "status": status, "code": spec.get("code") or code,
                                      "message": spec.get("message") or message, "details": spec.get("details") or {}, "count": count})
            failures = copy.deepcopy(self.failures)
        if path == "/api/events":
            self.wake_all()
        return failures

    def match_failure(self, method: str, path: str, *, consume: bool = True) -> dict | None:
        with self.lock:
            for rule in self.failures:
                if rule["path"] == path and rule["method"] in (None, method):
                    found = dict(rule)
                    if consume and rule["count"] is not None:
                        rule["count"] -= 1
                        if rule["count"] <= 0:
                            self.failures.remove(rule)
                    return found
        return None

    def is_failing(self, path: str) -> bool:
        return self.match_failure("GET", path, consume=False) is not None

    # -- the log -----------------------------------------------------------------------------------------------------
    def record(self, entry: dict) -> None:
        with self.lock:
            entry["n"] = len(self.log) + 1
            self.log.append(entry)

    def requests(self, prefix: str | None = None) -> list[dict]:
        with self.lock:
            return [copy.deepcopy(e) for e in self.log if prefix is None or e["path"].startswith(prefix)]

    # -- delivering the owner's words ------------------------------------------------------------------------------------
    def next_clock(self) -> str:
        with self.lock:
            self.clock += 1
            return iso_at(self.clock)

    def add_message(self, chat: Chat, role: str, who: str, kind: str, text: str, *, task_id: str | None = None) -> dict:
        with self.lock:
            message = {"id": chat.next_id(), "session_id": chat.sid, "role": role, "who": who, "kind": kind, "text": text, "card": None,
                       "pause": None, "answered_by": None, "task_id": task_id, "state": "ok", "at": self.next_clock()}
            chat.extra.append(message)
        self.publish("chat.message", {"session_id": chat.sid, "message": copy.deepcopy(message)})
        return message

    def reveal(self, chat: Chat, upto: int, text: str | None = None) -> list[dict]:
        """Show the fixture messages up to `upto` and announce each one. `text` replaces the text of the first."""
        with self.lock:
            if upto <= chat.visible:
                return []
            first = chat.visible
            chat.visible = min(upto, len(chat.fixture))
            new = [copy.deepcopy(m) for m in chat.fixture[first: chat.visible]]
            if text is not None and new:
                chat.text_override[new[0]["id"]] = text
                new[0]["text"] = text
        for message in new:
            self.publish("chat.message", {"session_id": chat.sid, "message": message})
        return new

    def flow_for(self, name: str, chat: Chat) -> dict | None:
        """The scripted flow `name` when it has not played and its first step still has a message to show."""
        flow = self.fx.script["flows"].get(name)
        with self.lock:
            if flow is None or name in self.flows_played or flow["session"] != chat.sid:
                return None
            first = flow["steps"][0].get("reveal")
            if first is None or chat.visible >= first["upto"]:
                return None
        return flow

    def play_flow(self, name: str, flow: dict, text: str) -> list[dict]:
        """Run the first step now (it is the owner's own line, whose id the POST answers) and the rest on a thread."""
        with self.lock:
            self.flows_played.add(name)
            self.flows_running += 1
        steps = flow["steps"]
        keep = frozenset(step["reveal"]["session"] for step in steps if "reveal" in step)
        try:
            first = self._run_step(steps[0], text, keep)
        except BaseException:
            with self.lock:
                self.flows_running -= 1
            raise
        args = (steps[1:], text, keep, self.generation)
        threading.Thread(target=self._run_steps, args=args, name=f"fake-flow-{name}", daemon=True).start()
        return first

    def _run_steps(self, steps: list[dict], text: str, keep: frozenset[str], generation: int) -> None:
        try:
            for step in steps:
                time.sleep(FLOW_STEP_SECONDS)
                if self.closing or generation != self.generation:
                    return
                self._run_step(step, text, keep)
        finally:
            with self.lock:
                self.flows_running -= 1

    def _run_step(self, step: dict, text: str, keep: frozenset[str] = frozenset()) -> list[dict]:
        only = step.get("only_stage")
        if only is not None and self.graph_stage not in only:
            return []
        if "reveal" in step:
            reveal = step["reveal"]
            return self.reveal(self.chats[reveal["session"]], reveal["upto"], text if step.get("text_from_post") else None)
        if "emit" in step:
            self.publish(step["emit"], step["data"])
        elif "fixture" in step:
            self.set_fixture(step["fixture"]["name"], step["fixture"]["version"], keep=keep)
        return []

    def deliver(self, chat: Chat, text: str) -> dict:
        """The owner writes in a department or division chat (ORCH 5.5): an answer, a follow-up, or busy."""
        node = self.session_ids()[chat.sid]
        dept_id = node["id"] if node["kind"] == "department" else node["dept_id"]
        dept_node = self.node(dept_id)
        dept_chat = self.chat(dept_node["chat_session_id"])
        open_question = any(n["session_id"] == dept_chat.sid for n in self.needs_you())
        task = self.task_of(dept_node)
        if open_question:
            with self.lock:
                self.answered.add(dept_chat.sid)
            flow = self.flow_for("answer", dept_chat)
            if flow is not None:
                message = self.play_flow("answer", flow, text)[0]
            else:
                message = self.add_message(dept_chat, "user", "user", "text", text, task_id=(task or {}).get("id"))
            self.publish("needs_you.changed", {"count": len(self.needs_you())})
            return {"message_id": message["id"], "delivered": "answer", "task_id": (task or {}).get("id")}
        if dept_node["status"] == "running":
            raise ApiError(409, "busy")
        task_id = "tsk_" + short_hash("follow-up:" + dept_id + text, 12)
        message = self.add_message(dept_chat, "user", "user", "text", text, task_id=task_id)
        return {"message_id": message["id"], "delivered": "follow_up", "task_id": task_id}


# ---------------------------------------------------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _DeptRow:
    id: str
    name: str


class _Settings:
    def __init__(self, token: str) -> None:
        self.token = token


class _Services:
    """The three members `sutra_app.ui.mount` reads from the orchestrator's Services."""

    def __init__(self, state: FakeState) -> None:
        self.settings = _Settings(state.token)
        self.version = state.version
        self._state = state

    def department(self, dept_id: str):
        found = self._state.department(dept_id)
        return _DeptRow(found["id"], found["name"]) if found else None


class FakeMiddleware:
    """Pure ASGI: the Host check, forced failures and the request log, in front of every route. The body of a write is
    read here once and handed to the route again, so the log has it whether the route reads it or not."""

    def __init__(self, app, state: FakeState) -> None:
        self.app, self.state = app, state

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method, path = scope["method"], scope["path"]
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        control = path.startswith("/__fake/")
        raw = b""
        if method not in ("GET", "HEAD", "OPTIONS"):
            parts = []
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    break
                parts.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            raw = b"".join(parts)
        entry = {"method": method, "path": path, "query": scope.get("query_string", b"").decode("latin-1"), "status": None,
                 "token": "x-sutra-token" in headers, "body": _parse_body(raw)}
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": raw, "more_body": False}
            return await receive()

        async def logging_send(message):
            if message["type"] == "http.response.start":
                entry["status"] = message["status"]
                if not control:
                    self.state.record(entry)
            await send(message)

        host = headers.get("host", "").split(":")[0]
        if host not in HOSTS:
            response: Response | None = envelope(400, "bad_host", "This server answers on 127.0.0.1 and localhost only.")
        elif not control and (rule := self.state.match_failure(method, path)) is not None:
            if path in J2_PATH_SET:
                response = JSONResponse({"error": rule["code"]}, status_code=rule["status"])
            else:
                response = envelope(rule["status"], rule["code"], rule["message"], rule["details"])
        else:
            response = None
        if response is not None:
            await response(scope, replay, logging_send)
            return
        await self.app(scope, replay, logging_send)


def _parse_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw[:20000])
    except ValueError:
        return raw[:200].decode("utf-8", "replace")


J2_GET_PATHS = (
    "/api/state", "/api/runs", "/api/call", "/api/preview", "/api/docs", "/api/map", "/api/plan", "/api/library",
    "/api/run-templates", "/api/artifacts", "/api/agent", "/api/code", "/api/artifacts/tree", "/api/artifact", "/api/story",
    "/api/board", "/api/audits", "/api/refs",
)
J2_POST_PATHS = ("/api/say", "/api/playbooks/clear", "/api/lessons/clear", "/api/output", "/api/reset")
J2_PATH_SET = frozenset(J2_GET_PATHS + J2_POST_PATHS)


def make_app(fixtures_dir: str | Path = FIXTURES_DIR, *, pages_dir: str | Path | None = None,
             static_dir: str | Path | None = None, token: str = TOKEN, version: str = VERSION) -> FastAPI:
    """The fake backend. `pages_dir` and `static_dir` replace the real UI folders (the tests of the fake itself use temp
    trees, since the real pages belong to other packages)."""
    fixtures = Fixtures(Path(fixtures_dir))
    state = FakeState(fixtures, token=token, version=version)
    app = FastAPI(docs_url=None, redoc_url=None)
    app.state.fake = state
    app.add_middleware(FakeMiddleware, state=state)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return envelope(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(J2Reject)
    async def _j2_reject(_: Request, exc: J2Reject):
        return JSONResponse(exc.body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        problems = [violation(".".join(str(p) for p in e["loc"]), e["type"], e["msg"]) for e in exc.errors()]
        return envelope(422, "validation", "The request did not pass validation.", {"violations": problems})

    register_api(app, state)
    register_j2(app, state)
    register_controls(app, state, fixtures)
    register_welcome_settings(app, state)
    services = _Services(state)
    if pages_dir is None and static_dir is None:
        mount(app, services)
    else:
        from sutra_app.ui import PAGES_DIR, STATIC_DIR

        app.include_router(build_router(token=token, department=services.department, version=version,
                                        pages_dir=Path(pages_dir) if pages_dir else PAGES_DIR))
        mount_static(app, Path(static_dir) if static_dir else STATIC_DIR)
    return app


def require_token(request: Request, state: FakeState) -> None:
    """The write guard (D81): a present Origin must be `http://<Host>`, and the header token must match."""
    origin = request.headers.get("origin")
    if origin is not None and origin != "http://" + request.headers.get("host", ""):
        raise ApiError(403, "bad_origin", "This request came from another origin.")
    if not hmac.compare_digest(request.headers.get("x-sutra-token", "").encode(), state.token.encode()):
        raise ApiError(401, "bad_token")


async def json_body(request: Request) -> Any:
    try:
        return await request.json()
    except ValueError:
        raise ApiError(422, "validation", "The body is not valid JSON.",
                       {"violations": [violation("", "json_invalid", "the body is not valid JSON")]}) from None


def int_arg(value: int | None, default: int, low: int, high: int) -> int:
    return default if value is None else max(low, min(high, value))


# ---------------------------------------------------------------------------------------------------------------------
# The ORCH routes
# ---------------------------------------------------------------------------------------------------------------------
def register_api(app: FastAPI, state: FakeState) -> None:
    @app.get("/api/chart")
    def chart():
        return JSONResponse(state.chart())

    @app.get("/api/chart/changes")
    def chart_changes(after: int = 0, limit: int | None = None):
        return JSONResponse(state.changes(max(after, 0), int_arg(limit, 50, 1, 500)))

    @app.get("/api/graph")
    def graph(level: str = "chart", dept: str | None = None, task: str | None = None):
        if level not in ("chart", "full"):
            raise ApiError(422, "validation", "level must be chart or full.", {"violations": [violation("level", "enum", "chart or full")]})
        return JSONResponse(state.graph(level, dept, task))

    @app.get("/api/graph/nodes/{node_id}")
    def graph_node(node_id: str):
        return JSONResponse(state.node_detail(node_id))

    @app.get("/api/chats")
    def chats(node_id: str | None = None, include: str | None = None):
        sessions = [state.chat(sid).session_out() for sid in state.session_ids()]
        if node_id is not None:
            sessions = [s for s in sessions if s["node_id"] == node_id]
        if include != "archived":
            sessions = [s for s in sessions if s["status"] == "active"]
        return JSONResponse(sessions)

    @app.get("/api/chats/{sid}")
    def chat(sid: str):
        out = state.chat(sid).session_out()
        if sid == "cs_org":
            out["phase"] = state.phase
        return JSONResponse(out)

    @app.get("/api/chats/{sid}/messages")
    def chat_messages(sid: str, after: int = 0, limit: int | None = None):
        shown = [m for m in state.chat(sid).messages() if m["id"] > max(after, 0)][: int_arg(limit, 200, 1, 200)]
        return JSONResponse({"messages": shown, "next_after": shown[-1]["id"] if shown else max(after, 0)})

    @app.post("/api/chats/cs_org/retry")
    def retry(request: Request):
        require_token(request, state)
        return JSONResponse({"message_id": state.chat("cs_org").messages()[-1]["id"], "turn": "started"}, status_code=202)

    @app.post("/api/chats/{sid}/messages")
    async def post_message(sid: str, request: Request):
        require_token(request, state)
        body = await json_body(request)
        problems = _check_post(body)
        if problems:
            raise ApiError(422, "validation", problems[0]["message"], {"violations": problems})
        chat = state.chat(sid)
        text = body["text"].strip()
        if chat.info["status"] != "active" or not chat.info["writable"]:
            raise ApiError(403, "read_only", f"This is the working log of {chat.info['title']}. It is read-only.")
        if chat.info["kind"] == "org":
            flow = state.flow_for("first_task", chat)
            if flow is not None:
                message = state.play_flow("first_task", flow, text)[0]
            else:
                message = state.add_message(chat, "user", "user", "text", text)
            return JSONResponse({"message_id": message["id"], "turn": "started"}, status_code=202)
        return JSONResponse(state.deliver(chat, text))

    @app.get("/api/needs-you")
    def needs_you():
        return JSONResponse(state.needs_you())

    @app.get("/api/heads-up")
    def heads_up():
        with state.lock:
            return JSONResponse(copy.deepcopy(state.heads_up))

    @app.post("/api/tasks/{task_id}/retry")
    def retry_task(task_id: str, request: Request):
        """Try again (gap attention): a row that offers it leaves the lane (the real server lists a retried task no more) and
        task.updated says so; anything else is 409 busy, as the real route answers a task that may not be retried."""
        require_token(request, state)
        with state.lock:
            row = next((h for h in state.heads_up if h.get("task_id") == task_id and h.get("retry") is True), None)
            if row is None:
                raise ApiError(409, "busy", "Only a task that stopped, crashed or was cancelled can be tried again")
            state.heads_up = [h for h in state.heads_up if h is not row]
            state.retried.append(task_id)
            new_id = "tsk_" + format(len(state.retried), "012x")
        task = {"id": new_id, "dept_id": row.get("dept_id", "web"), "dept_name": row.get("dept_name", ""), "title": row.get("title", ""),
                "status": "queued", "parent_task_id": task_id, "created_at": "2026-11-04T10:00:00Z"}
        state.publish("task.updated", {"task": task})
        return JSONResponse(task, status_code=201)

    @app.get("/api/departments")
    def departments():
        return JSONResponse(state.departments())

    @app.get("/api/departments/{dept_id}")
    def department(dept_id: str):
        found = state.department(dept_id)
        if found is None:
            raise ApiError(404, "not_found", f"No team {dept_id!r}.")
        return JSONResponse(found)

    @app.get("/api/atoms")
    def atoms(node_id: str | None = None, task_id: str | None = None, status: str | None = None, limit: int | None = None,
              offset: int = 0):
        rows = state.all_atoms()
        rows = [a for a in rows if (node_id is None or a["node_id"] == node_id) and (task_id is None or a["task_id"] == task_id)
                and (status is None or a["state"] == status)]
        rows.sort(key=lambda a: a["ts_open"], reverse=True)
        start = max(offset, 0)
        return JSONResponse(rows[start: start + int_arg(limit, 50, 1, 500)])

    @app.get("/api/atoms/log")
    def atoms_log(node_id: str | None = None, after: int = 0, limit: int | None = None):
        rows = [r for r in state.atom_log() if r["seq"] > max(after, 0) and (node_id is None or r["node_id"] == node_id)]
        return JSONResponse(rows[: int_arg(limit, 50, 1, 500)])

    @app.get("/api/atoms/{atom_id}")
    def atom(atom_id: str):
        found = next((a for a in state.all_atoms() if a["id"] == atom_id), None)
        if found is None:
            raise ApiError(404, "not_found", f"No atom {atom_id!r}.")
        return JSONResponse(found)

    @app.get("/api/health")
    def health():
        return JSONResponse(state.health())

    @app.get("/api/engine/settings")
    def settings_get(dept: str | None = None):
        return JSONResponse(state.settings_view(_settings_scope(dept)))

    @app.put("/api/engine/settings")
    async def settings_put(request: Request, dept: str | None = None):
        require_token(request, state)
        scope = _settings_scope(dept)
        return JSONResponse(state.settings_put(scope, await json_body(request)))

    def _settings_scope(dept: str | None) -> str | None:
        if dept is None:
            return None
        if not DEPT_ID_RE.fullmatch(dept) or state.department(dept) is None:
            raise ApiError(404, "not_found", f"No team {dept!r}.")
        return dept

    @app.post("/api/connectors/{provider}/test")
    def connector_test(provider: str, request: Request):
        require_token(request, state)
        return JSONResponse(state.connector_test(provider))

    @app.put("/api/connectors/{provider}/path")
    async def connector_path(provider: str, request: Request):
        require_token(request, state)
        return JSONResponse(state.set_cli_path(provider, await json_body(request)))

    @app.post("/api/connectors/codex/sign-in")
    def sign_in_start(request: Request):
        require_token(request, state)
        return JSONResponse(state.sign_in_start())

    @app.get("/api/connectors/codex/sign-in/{sign_in_id}")
    def sign_in_poll(sign_in_id: str):
        return JSONResponse(state.sign_in_poll(sign_in_id))

    @app.delete("/api/connectors/codex/sign-in/{sign_in_id}")
    def sign_in_cancel(sign_in_id: str, request: Request):
        require_token(request, state)
        state.sign_in_cancel(sign_in_id)
        return Response(status_code=204)

    @app.get("/api/events")
    async def events(request: Request, after: int | None = None, topics: str | None = None, once: int | None = None):
        last_id = request.headers.get("last-event-id")
        if after is None and last_id is not None and last_id.isdigit():
            after = int(last_id)
        wanted = {t.strip() for t in topics.split(",") if t.strip()} if topics else None
        sub = state.subscribe(asyncio.get_running_loop(), wanted)

        async def stream():
            try:
                yield frame("server.hello", state.hello(), None)
                replay, reason = state.replay(after if after is not None else (0 if once else None))
                if reason:
                    yield frame("server.resync", {"reason": reason}, None)
                sent = 0
                for item in replay:
                    if sub.wants(item["event"]):
                        yield frame(item["event"], item["data"], item["id"])
                    sent = item["id"]
                if once:
                    return
                while not state.closing and not state.is_failing("/api/events"):
                    try:
                        item = await asyncio.wait_for(sub.queue.get(), PING_SECONDS)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    if item is None:
                        continue
                    if item["id"] is None:
                        if item["event"] == "server.resync":
                            sent = 0  # a restart: the ids begin again at 1, none of them has been replayed
                    elif item["id"] <= sent:
                        continue  # already replayed
                    yield frame(item["event"], item["data"], item["id"])
            finally:
                state.unsubscribe(sub)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def frame(event: str, data: Any, event_id: int | None) -> str:
    """One server-sent event: `event`, then `id` (control events have none), then `data`."""
    lines = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append("data: " + json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n\n"


def _check_post(body: Any) -> list[dict]:
    if not isinstance(body, dict) or set(body) - {"text", "choice"}:
        return [violation("", "bad_body", "the body is {text, choice?}")]
    text = body.get("text")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 8000:
        return [violation("text", "bad_text", "text must be 1 to 8000 characters")]
    choice = body.get("choice")
    if choice is not None and not (isinstance(choice, dict) and set(choice) == {"message_id", "option"}
                                   and isinstance(choice["message_id"], int) and isinstance(choice["option"], str)):
        return [violation("choice", "bad_choice", "choice is {message_id, option}")]
    return []


# ---------------------------------------------------------------------------------------------------------------------
# J2's routes (engine.md 7.1): J2 paths at the root, the team in ?dept=, J2's own bodies
# ---------------------------------------------------------------------------------------------------------------------
def register_j2(app: FastAPI, state: FakeState) -> None:
    j2 = state.fx.j2
    secure = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}

    def scope(dept: str | None, run: str | None, no_run: dict | None = None) -> None:
        """The checks every J2 route makes first: a well-formed department that exists, and a run of it (D73)."""
        if not dept or not DEPT_ID_RE.fullmatch(dept):
            raise J2Reject(400, {"error": "dept_required"})
        if state.department(dept) is None:
            raise J2Reject(404, {"error": "not_found"})
        if run is not None and run not in state.known_runs(dept):
            raise J2Reject(404, no_run or {"error": "not_found"})

    def need(name: str) -> bytes:
        data = j2.raw(name)
        if data is None:
            raise J2Reject(404, {"error": f"no J2 fixture {name}: run scripts/capture_j2_fixtures.py"})
        return data

    def raw_json(name: str) -> Response:
        return Response(need(name), media_type="application/json", headers=secure)

    def html(data: bytes) -> Response:
        return Response(data, media_type="text/html", headers={**secure, "Content-Security-Policy": SANDBOX})

    def not_found_text() -> Response:
        return PlainTextResponse("not found", status_code=404, headers=secure)

    @app.get("/api/state")
    def j2_state(dept: str | None = None, run: str | None = None, since: str = "0"):
        scope(dept, run, {"error": "no such run"})
        snapshot = json.loads(need("state.json"))
        start = int(since) if since.isdigit() else 0
        snapshot["chat"] = snapshot["chat"][start:]
        snapshot["saved"] = run
        return JSONResponse(snapshot, headers=secure)

    for path, name in (("/api/runs", "runs.json"), ("/api/docs", "docs.json"), ("/api/map", "map.json"), ("/api/plan", "plan.json"),
                       ("/api/run-templates", "run-templates.json"), ("/api/artifacts", "artifacts.json"),
                       ("/api/artifacts/tree", "artifacts-tree.json"), ("/api/story", "story.json"), ("/api/board", "board.json"),
                       ("/api/audits", "audits.json")):
        def make(file_name: str):
            def view(dept: str | None = None, run: str | None = None):
                scope(dept, run)
                return raw_json(file_name)
            return view

        app.add_api_route(path, make(name), methods=["GET"])

    @app.get("/api/runlist")
    def j2_runlist(dept: str | None = None, run: str | None = None):
        """Patch P13's run list, derived from the captured /api/runs: the runs of the web team only, as the engine's rows."""
        scope(dept, run)
        listed = json.loads(need("runs.json")) if dept == "web" else {"live": "", "runs": []}
        rows = []
        for item in listed["runs"]:
            m = re.search(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", item["id"])
            rows.append({"id": item["id"], "title": item["id"], "status": "done" if str(item["status"]).startswith("done") else "stopped",
                         "output": "website", "when": f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}" if m else "", "brief": item["brief"][:160]})
        return JSONResponse({"live": listed["live"], "runs": rows}, headers=secure)

    @app.get("/api/changes")
    def j2_changes(dept: str | None = None, run: str | None = None):
        """Patch P13's build journey: the captured run has no change.json, so no stops."""
        scope(dept, run)
        return JSONResponse({"changes": []}, headers=secure)

    @app.get("/api/library")
    def j2_library(dept: str | None = None):
        scope(dept, None)
        return raw_json("library.json")

    @app.get("/api/refs")
    def j2_refs(dept: str | None = None):
        scope(dept, None)
        return raw_json("refs.json")

    @app.get("/api/library/{artifact}/{section}/{slug}/{ver}")
    def j2_library_item(artifact: str, section: str, slug: str, ver: str, dept: str | None = None, run: str | None = None):
        scope(dept, run)
        raise J2Reject(404, {"error": "no such template"})

    @app.get("/api/call")
    def j2_call(id: int = 0, dept: str | None = None, run: str | None = None):
        scope(dept, run)
        raise J2Reject(404, {"error": "no such call"})

    @app.get("/api/preview")
    def j2_preview(atom: str = "", dept: str | None = None, run: str | None = None):
        scope(dept, run)
        replies = j2.json("preview-replies.json") or {}
        return JSONResponse(replies.get(atom, {"anchor": None, "html": None}), headers=secure)

    @app.get("/api/agent")
    def j2_agent(who: str = "", dept: str | None = None, run: str | None = None):
        scope(dept, run)
        if who in (*FUNCTIONS, "W-1") and j2.raw(f"agent-{who}.json") is not None:
            return raw_json(f"agent-{who}.json")
        unknown = json.loads(need("agent-unknown.json"))
        unknown["who"] = who
        return JSONResponse(unknown, headers=secure)

    @app.get("/api/code")
    def j2_code(dept: str | None = None, run: str | None = None, deck: str = "", section: str = ""):
        scope(dept, run)
        return not_found_text()

    @app.get("/api/artifact")
    def j2_artifact(name: str = "", dept: str | None = None, run: str | None = None):
        scope(dept, run)
        return html(need("site-latest.html")) if name == "site/index.html" else not_found_text()

    @app.get("/shot/{n}")
    def j2_shot(n: str, dept: str | None = None, run: str | None = None):
        scope(dept, run)
        return not_found_text()

    @app.get("/file/{name}")
    def j2_file(name: str, dept: str | None = None, run: str | None = None):
        scope(dept, run)
        return not_found_text()

    @app.get("/site/{key}")
    def j2_site(key: str, dept: str | None = None, run: str | None = None):
        scope(dept, run)
        versions = int((j2.json("state.json") or {}).get("versions", 0))
        match = re.fullmatch(r"v(\d+)", key)
        if key == "latest" or (match and 1 <= int(match.group(1)) <= versions):
            return html(need("site-latest.html"))
        return not_found_text()

    @app.post("/api/say")
    async def j2_say(request: Request, dept: str | None = None):
        require_token(request, state)
        scope(dept, None)
        body = await json_body(request)
        text = body.get("text") if isinstance(body, dict) else None
        text = text.strip() if isinstance(text, str) else ""  # anything but text is nothing to say
        if not text:
            raise J2Reject(400, {"error": "empty"})
        dept_node = state.node(dept or "")
        try:
            state.deliver(state.chat(dept_node["chat_session_id"]), text)
        except ApiError as exc:
            if exc.status == 409:
                raise J2Reject(409, {"ok": False}) from None
            raise
        return JSONResponse({"ok": True}, headers=secure)

    @app.post("/api/playbooks/clear")
    def j2_playbooks_clear(request: Request, dept: str | None = None):
        require_token(request, state)
        scope(dept, None)
        return JSONResponse({"ok": True, "cleared": 0}, headers=secure)

    @app.post("/api/lessons/clear")
    def j2_lessons_clear(request: Request, dept: str | None = None):
        require_token(request, state)
        scope(dept, None)
        return JSONResponse({"ok": True, "cleared": 0}, headers=secure)

    @app.post("/api/output")
    async def j2_output(request: Request, dept: str | None = None):
        require_token(request, state)
        scope(dept, None)
        body = await json_body(request)
        kind = body.get("type") if isinstance(body, dict) else None
        if kind not in ENGINE_ENUMS["output"]:
            raise J2Reject(409, {"ok": False, "output": "website"})
        return JSONResponse({"ok": True, "output": kind}, headers=secure)

    @app.post("/api/reset")
    def j2_reset(request: Request, dept: str | None = None):
        require_token(request, state)
        scope(dept, None)
        node = state.node(dept or "")
        if node is not None and node["status"] == "running":
            raise J2Reject(409, {"ok": False})
        return JSONResponse({"ok": True}, headers=secure)


# ---------------------------------------------------------------------------------------------------------------------
# The test-only controls
# ---------------------------------------------------------------------------------------------------------------------
def register_controls(app: FastAPI, state: FakeState, fixtures: Fixtures) -> None:
    @app.post("/__fake/emit")
    async def emit(request: Request):
        body = await json_body(request)
        if not isinstance(body, dict) or not isinstance(body.get("event"), str):
            raise ApiError(422, "validation", "emit needs {event, data?}")
        item = state.emit(body["event"], body.get("data"))
        return JSONResponse({"id": item["id"], "event": item["event"]})

    @app.post("/__fake/fixture")
    async def fixture(request: Request):
        body = await json_body(request)
        if not isinstance(body, dict) or not isinstance(body.get("name"), str) or "version" not in body:
            raise ApiError(422, "validation", "fixture needs {name, version}")
        return JSONResponse(state.set_fixture(body["name"], body["version"]))

    @app.post("/__fake/heads-up")
    async def set_heads_up(request: Request):
        body = await json_body(request)
        if not isinstance(body, dict) or not isinstance(body.get("items"), list) or not all(isinstance(i, dict) for i in body["items"]):
            raise ApiError(422, "validation", "heads-up needs {items: [...]}")
        with state.lock:
            state.heads_up = copy.deepcopy(body["items"])
        state.publish("task.updated", {"task": None})
        return JSONResponse({"items": len(body["items"])})

    @app.post("/__fake/fail")
    async def fail(request: Request):
        body = await json_body(request)
        if not isinstance(body, dict):
            raise ApiError(422, "validation", "fail needs {path, status}")
        return JSONResponse({"failures": state.set_failure(body)})

    @app.get("/__fake/log")
    def log(prefix: str | None = None):
        return JSONResponse(state.requests(prefix))

    @app.get("/__fake/state")
    def get_state():
        with state.lock:
            return JSONResponse({**state.stages(), "failures": copy.deepcopy(state.failures), "subscribers": len(state.subscribers),
                                 "last_event_id": state.seq, "flows_running": state.flows_running,
                                 "codex_signed_in": state.codex_signed_in})

    @app.post("/__fake/reset")
    def reset():
        state.reset()
        return JSONResponse(state.stages())

    @app.post("/__fake/page")
    async def page(request: Request):
        body = await json_body(request)
        if not (isinstance(body, dict) and isinstance(body.get("name"), str) and re.fullmatch(r"[a-z0-9_]{1,40}", body["name"])
                and isinstance(body.get("html"), str)):
            raise ApiError(422, "validation", "page needs {name: [a-z0-9_]+, html}")
        with state.lock:
            state.pages[body["name"]] = body["html"]
        return JSONResponse({"url": f"/__fake/mount/{body['name']}.html"})

    @app.get("/__fake/mount/{name}")
    def mount_page(name: str, dept: str | None = None):
        stem = name[:-5] if name.endswith(".html") else None
        if stem is None or not re.fullmatch(r"[a-z0-9_]{1,40}", stem):
            raise ApiError(404, "not_found", "A mount page is /__fake/mount/<name>.html")
        with state.lock:
            source = state.pages.get(stem)
        if source is None:
            path = fixtures.path(f"{stem}.html" if stem.startswith("mount_") else f"mount_{stem}.html")
            if path.is_file():
                source = path.read_text(encoding="utf-8")
        if source is None:
            raise ApiError(404, "not_found", f"No mount page {stem!r}.")
        row = state.department(dept) if dept else None
        boot = (BootContext(page="dept", token=state.token, dept=row["id"], dept_label=row["name"], version=state.version)
                if row else BootContext(page="home", token=state.token, version=state.version))
        return Response(render_page(source, boot), media_type="text/html", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------------------------------------------------
# welcome-settings: the first-run card, the default-model controls and the owner-click update check
# ---------------------------------------------------------------------------------------------------------------------
WELCOME_FACTS = {
    "models": [{"name": "claude", "state": "ready", "why": "", "fix": ""},
               {"name": "codex", "state": "not_ready", "why": "0.5.2: not signed in", "fix": "run `codex login`"}],
    "data": {"dir": "/data/sutra-pro", "db_bytes": 1_310_720, "free_bytes": 42_949_672_960, "backup": "sutra-pro backup"},
    "egress": {"scrub": True, "api_key_refused": True, "only_your_cli": True},
    "autonomy": {"budget": 30, "send_mode": "dry-run", "asks": True},
}
UPDATE_UP_TO_DATE = {"current": VERSION, "latest": VERSION, "newer": False, "url": "https://github.com/sankalpasawa/sutra/releases?q=sutra-pro",
                     "notes_url": "https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v" + VERSION, "how": "Run `git pull`.", "kind": "checkout",
                     "error": None, "said": f"You have {VERSION}: up to date."}


def register_welcome_settings(app: FastAPI, state: FakeState) -> None:
    """The welcome card (seen by default, so no other test is covered by it; `/__fake/welcome` shows it), GET and PUT /api/connectors/policy with the real
    validation, GET /api/connectors/models, GET /api/ops/info and POST /api/ops/update-check (`/__fake/update` sets the answer). Reset with the story."""
    from sutra_app.connectors.errors import PolicyInvalidError
    from sutra_app.connectors.model_catalog import claude_options
    from sutra_app.connectors.policy import load_default_policy, parse_policy

    def fresh() -> dict:
        return {"seen": True, "facts": copy.deepcopy(WELCOME_FACTS), "policy": load_default_policy().model_dump(mode="json"), "update": copy.deepcopy(UPDATE_UP_TO_DATE),
                "pill": False, "choice": {"provider": None, "model": None, "effort": None}}

    state.ws = fresh()
    original_reset = state.reset

    def reset(*args: Any, **kw: Any) -> None:
        original_reset(*args, **kw)
        state.ws = fresh()
    state.reset = reset                                    # type: ignore[method-assign]

    @app.get("/api/ops/welcome")
    def welcome_get():
        return JSONResponse({"seen": state.ws["seen"], "facts": None if state.ws["seen"] else state.ws["facts"]})

    @app.post("/api/ops/welcome/seen")
    def welcome_seen(request: Request):
        require_token(request, state)
        state.ws["seen"] = True
        return JSONResponse({"seen": True})

    @app.get("/api/ops/info")
    def ops_info():
        return JSONResponse({"app": "Sutra Pro", "version": state.version, "data_dir": "/data/sutra-pro", "db_bytes": 1_310_720, "free_bytes": 42_949_672_960})

    @app.get("/api/connectors/policy")
    def policy_get():
        return JSONResponse(state.ws["policy"])

    @app.put("/api/connectors/policy")
    async def policy_put(request: Request):
        require_token(request, state)
        try:
            policy = parse_policy(await request.body())
        except PolicyInvalidError as exc:
            return envelope(422, "policy_invalid", exc.user_message(), {"kind": "unavailable", "errors": list(exc.detail.get("errors", []))})
        state.ws["policy"] = policy.model_dump(mode="json")
        return JSONResponse(state.ws["policy"])

    @app.get("/api/connectors/models")
    def models_get():
        codex = [{"slug": "gpt-5.6-luna", "label": "GPT-5.6 Luna", "efforts": ["low", "medium", "high"], "context_window": 258400, "images": True, "listed": True,
                  "note": "", "group": "main", "provider": "codex"}]
        return JSONResponse({"models": [{**o.model_dump(mode="json"), "images": True, "listed": True, "provider": "claude"} for o in claude_options()] + codex})

    @app.post("/api/ops/update-check")
    def update_check(request: Request):
        require_token(request, state)
        return JSONResponse(state.ws["update"])

    # the pill of a chat (item 4): the fake serves none until a test asks (`/__fake/pill`), as it never did, so no other test sees a pill
    def pill_of(sid: str) -> dict:
        choice = state.ws["choice"]
        claude = choice["provider"] == "claude"
        return {"providers": [
            {"name": "claude", "ready": True, "why_not": "", "model": "sonnet", "models": [], "plan": None, "billing": "subscription", "chosen": claude,
             "quota": None, "model_options": [o.model_dump(mode="json") for o in claude_options()], "chat_model": choice["model"] if claude else None,
             "chat_effort": choice["effort"] if claude else None, "can_pick": True},
            {"name": "codex", "ready": False, "why_not": "not signed in", "model": "gpt-5.6-luna", "models": [], "plan": None, "billing": "unknown",
             "chosen": False, "quota": None, "model_options": [], "chat_model": None, "chat_effort": None, "can_pick": True}], "chosen": choice["provider"]}

    @app.get("/api/chats/{sid}/providers")
    def pill_get(sid: str):
        if not state.ws["pill"]:
            raise ApiError(404, "not_found", "This chat is gone.")
        return JSONResponse(pill_of(sid))

    @app.put("/api/chats/{sid}/choice")
    async def pill_choice(sid: str, request: Request):
        require_token(request, state)
        body = await json_body(request)
        provider, model, effort = body.get("provider"), body.get("model"), body.get("effort")
        slugs = [o.slug for o in claude_options()]
        if provider is not None and provider != "claude":
            raise ApiError(422, "validation", f"{provider} cannot run: not signed in")
        if model is not None and model not in slugs:
            raise ApiError(422, "validation", f"{model} is not a model claude offers. Choose one of: {', '.join(slugs[:4])}")
        state.ws["choice"] = {"provider": provider, "model": model or (state.ws["choice"]["model"] if provider else None),
                              "effort": effort or (state.ws["choice"]["effort"] if provider else None)}
        return JSONResponse({"session_id": sid, **state.ws["choice"]})

    @app.post("/__fake/pill")
    async def pill_control(request: Request):
        body = await json_body(request)
        state.ws["pill"] = bool(isinstance(body, dict) and body.get("on", True))
        if isinstance(body, dict) and isinstance(body.get("choice"), dict):
            state.ws["choice"] = {"provider": None, "model": None, "effort": None, **body["choice"]}
        return JSONResponse({"pill": state.ws["pill"], "choice": state.ws["choice"]})

    @app.post("/__fake/welcome")
    async def welcome_control(request: Request):
        body = await json_body(request)
        state.ws["seen"] = bool(isinstance(body, dict) and body.get("seen", False))
        if isinstance(body, dict) and isinstance(body.get("facts"), dict):
            state.ws["facts"] = body["facts"]
        return JSONResponse({"seen": state.ws["seen"]})

    @app.post("/__fake/update")
    async def update_control(request: Request):
        body = await json_body(request)
        if isinstance(body, dict):
            state.ws["update"] = {**copy.deepcopy(UPDATE_UP_TO_DATE), **body}
        return JSONResponse(state.ws["update"])


# ---------------------------------------------------------------------------------------------------------------------
# Serving it
# ---------------------------------------------------------------------------------------------------------------------
class RunningApp(NamedTuple):
    url: str
    stop: Callable[[], None]


def run_in_thread(app: FastAPI, host: str = "127.0.0.1") -> RunningApp:
    """Serve `app` with uvicorn on a free port in a daemon thread. Returns the URL and a function that stops it."""
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=0, log_level="warning", lifespan="off", timeout_graceful_shutdown=2))
    def serve() -> None:
        with contextlib.suppress(SystemExit):  # uvicorn exits the thread this way when it cannot bind; `started` stays False
            server.run()

    thread = threading.Thread(target=serve, name="fake-backend", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the fake backend did not start")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]

    def stop() -> None:
        fake = getattr(app.state, "fake", None)
        if fake is not None:
            fake.close()
        server.should_exit = True
        thread.join(15)

    return RunningApp(f"http://{host}:{port}", stop)


class FakeClient:
    """The controls and a few reads over HTTP, for tests that run next to a `run_in_thread` server."""

    def __init__(self, url: str, token: str = TOKEN) -> None:
        self.url, self.token = url.rstrip("/"), token

    def request(self, method: str, path: str, body: Any = None, *, token: bool = False, headers: dict | None = None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
        if token:
            request.add_header("X-Sutra-Token", self.token)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=20) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, raw.decode("utf-8", "replace")

    def get(self, path: str, **query: Any) -> tuple[int, Any]:
        return self.request("GET", path + ("?" + urlencode(query) if query else ""))

    def post(self, path: str, body: Any = None, *, token: bool = True) -> tuple[int, Any]:
        return self.request("POST", path, body if body is not None else {}, token=token)

    def emit(self, event: str, data: Any = None) -> dict:
        status, answer = self.request("POST", "/__fake/emit", {"event": event, **({} if data is None else {"data": data})})
        assert status == 200, answer
        return answer

    def fixture(self, name: str, version: Any) -> dict:
        status, answer = self.request("POST", "/__fake/fixture", {"name": name, "version": version})
        assert status == 200, answer
        return answer

    def stage(self, label: str) -> dict:
        return self.fixture("stage", label)

    def fail(self, path: str, status: int | None = 500, **options: Any) -> dict:
        code, answer = self.request("POST", "/__fake/fail", {"path": path, "status": status, **options})
        assert code == 200, answer
        return answer

    def log(self, prefix: str | None = None) -> list[dict]:
        return self.request("GET", "/__fake/log" + (f"?prefix={prefix}" if prefix else ""))[1]

    def state(self) -> dict:
        return self.request("GET", "/__fake/state")[1]

    def reset(self) -> dict:
        return self.request("POST", "/__fake/reset", {})[1]

    def page(self, name: str, html: str) -> str:
        status, answer = self.request("POST", "/__fake/page", {"name": name, "html": html})
        assert status == 200, answer
        return self.url + answer["url"]

    def mount_url(self, name: str, **query: Any) -> str:
        return f"{self.url}/__fake/mount/{name}.html" + ("?" + urlencode(query) if query else "")

    def wait_subscribers(self, count: int = 1, timeout: float = 5.0) -> None:
        """Wait until `count` event streams are open, so an event emitted next is not missed by the page."""
        deadline = time.monotonic() + timeout
        while self.state()["subscribers"] < count:
            if time.monotonic() > deadline:
                raise TimeoutError(f"no event stream opened within {timeout} s")
            time.sleep(0.02)

    def wait_flows(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while self.state()["flows_running"] > 0:
            if time.monotonic() > deadline:
                raise TimeoutError("a scripted flow did not finish")
            time.sleep(0.02)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the fake backend of the UI tests (for looking at a page by hand).")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--stage", default="1", choices=list(STAGES))
    args = parser.parse_args(argv)
    app = make_app()
    app.state.fake.set_stage(args.stage)
    print(f"fake backend on http://127.0.0.1:{args.port}/  (stage {args.stage}; token {TOKEN}; Ctrl-C stops)")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", lifespan="off")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
