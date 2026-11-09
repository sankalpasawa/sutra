"""`StatePublisher`: the state the live views need and the events the watcher projects (engine design 4.5, 4.6).

The host cannot be asked questions, so this class writes, from a `J2Run` that other threads keep changing (the same benign
race J2's HTTP threads had):

* `snapshot.json` and `live.json` (`views.live_state`), atomically (temp file and rename), only when the content changed
  (`live.json` is compared without its `at`), at most every 250 ms, and once more by `final()` before `run.ended`;
* the map-derived events, built from `j2_map.build` and the snapshot, on change only and always in the order
  `node`, `step`, `atom` (the `atom/1` views of the builders; the function-node layer writes its own `work-atom/0.3` lines):
    - `node` for each of the five function nodes (`fn`) and for each builder lane `W-n` (`step`): status (a function node uses
      the first five of the nine map words), detail, calls, seconds, `tokens` and, while it waits, `wait_on` (display names of
      the map mapped back through `NAMES`: 'Requester' becomes `you`, 'W-3 Builder' becomes `W-3`). A function node also
      carries `task` (its turn: `t-<turn_no>`, running while the turn runs, done after) and `context` from the `TurnInfo`.
    - `step` for each workflow of the map (`W-n`: parent = its box, reads, the workflows that read it, rework = `revises`)
      and for each team of the map (`team:<persona>`).
    - `atom` (`atom/1`) for each builder atom whose status or attempt changed.

It wakes on `notify()` (post, save, call finished, turn started or finished, status change) and every second while the run is
running (that also catches `thinking`). `turn_started` and `turn_finished` publish at once, from the run thread, so every turn
boundary is seen even when two of them fall inside one 250 ms window.
"""
import json
import os
from sutra_app import oslayer
import re
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Optional

from sutra_app.library.types import FUNCTIONS, clip

from ..events import STEP_RE, EventError, EventWriter, atom_event, node_event, step_event

__all__ = ["StatePublisher", "HostHooks", "builder_status", "wait_on_key", "MIN_INTERVAL_S", "WAKE_INTERVAL_S"]

MIN_INTERVAL_S = 0.25
WAKE_INTERVAL_S = 1.0
MAX_TRACED_ERRORS = 20
SNAPSHOT_FILE, LIVE_FILE = "snapshot.json", "live.json"
FUNCTION_WORDS = ("idle", "running", "waiting", "waiting_on_you", "fault")
# worst first: the status of a team that holds several boxes
TEAM_ORDER = ("fault", "running", "waiting_on_you", "waiting", "left_open", "done_unchecked", "idle", "filed", "not_made")


def _text_file_write(path: str, text: str) -> None:
    """Atomic: a temp file in the same folder, then rename. The page reads these files on every poll."""
    tmp = f"{path}.tmp-{os.getpid()}-{threading.get_ident()}"
    fd = os.open(tmp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        oslayer.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def wait_on_key(display: Any, names: Mapping[str, str]) -> Optional[str]:
    """What a node is waiting on, from the map's display name: `you`, a function key, a builder id (`W-3`) or None."""
    if not isinstance(display, str) or not display.strip():
        return None
    text = display.strip()
    if text in ("you", "user", "Requester") or text == names.get("user"):
        return "you"
    if text in FUNCTIONS or STEP_RE.fullmatch(text):
        return text
    for key, name in names.items():
        if name == text and (key in FUNCTIONS or STEP_RE.fullmatch(key)):
            return key
    found = re.fullmatch(r"(W-[0-9]+) Builder", text)
    return found.group(1) if found else None


def builder_status(lane: Optional[str], workflow: Optional[str], atoms: Optional[str]) -> str:
    """One of the nine map words for a builder: from its lane (working, waiting, blocked, idle), its workflow's status and
    the status of its atoms (the rules of `j2_map._status` and the lanes)."""
    if lane == "working" or workflow == "running":
        return "running"
    if workflow == "unfunded":
        return "not_made"
    if workflow in ("failed", "held") or lane == "blocked":
        return "fault"
    if lane == "waiting":
        return "waiting"
    if workflow == "done":
        if atoms == "abandoned":
            return "not_made"
        return "done_unchecked" if atoms in ("verify_failed", "open") else "filed"
    return "idle"


class StatePublisher:
    NAME = "sutra-publisher"

    def __init__(self, writer: EventWriter, run_dir, *, pid: Optional[int] = None, min_interval: float = MIN_INTERVAL_S,
                 wake_interval: float = WAKE_INTERVAL_S, clock: Callable[[], float] = time.monotonic):
        self.writer = writer
        self.run_dir = Path(run_dir)
        self.pid = os.getpid() if pid is None else pid
        self.min_interval = min_interval
        self.wake_interval = wake_interval
        self._clock = clock
        self.run = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._last_publish = -1e9
        self._snapshot_text: Optional[str] = None
        self._live_cmp: Optional[str] = None
        self._sent: dict[tuple, dict] = {}              # ("node", "fn:identity") -> the arguments last emitted
        self._atoms: dict[str, tuple] = {}              # atom id -> (status, attempt) last emitted
        self._ts_open: dict[str, int] = {}
        self._tasks: dict[str, dict] = {}               # function -> {"task": {...}, "context": [...]}
        self._errors = 0
        self._mods: Optional[tuple] = None
        self.publishes = 0                              # how many times files or events changed (for tests)

    # ---- wiring ------------------------------------------------------------------------------------------------------
    def attach(self, run) -> None:
        self.run = run

    def notify(self) -> None:
        self._wake.set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("the publisher was started already")
        self._thread = threading.Thread(target=self._loop, name=self.NAME, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Stop the thread. A publish in progress finishes first, so nothing is written after this returns."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def final(self) -> None:
        """The last publish, before `run.ended`: the files and every event that is still to come."""
        self.publish(force=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.wake_interval)
            if self._stop.is_set():
                return
            asked = self._wake.is_set()
            self._wake.clear()
            run = self.run
            if run is None or not (asked or run.status == "running"):
                continue
            wait = self._last_publish + self.min_interval - self._clock()
            if wait > 0 and self._stop.wait(wait):       # "at most every 250 ms"
                return
            self.publish()

    # ---- the turn boundary (called by HostHooks in the run thread) ------------------------------------------------------
    def turn_started(self, info) -> None:
        if info.function not in FUNCTIONS:
            return
        handoff = getattr(self.run, "handoff", None) or {}
        frm = handoff.get("frm") if isinstance(handoff, dict) else None
        self._tasks[info.function] = {
            "task": {"id": f"t-{info.turn_no}", "kind": info.kind, "summary": clip(f"{info.step_label}: {info.task}", 300),
                     "state": "running", "set_by": frm if isinstance(frm, str) and frm else "system"},
            "context": list(info.context)}

    def turn_finished(self, info) -> None:
        mine = self._tasks.get(info.function)
        if mine is not None:
            mine["task"] = {**mine["task"], "state": "done"}

    def boundary(self) -> None:
        """Publish now, ignoring the 250 ms window; never raises (a publish error never reaches J2)."""
        try:
            self.publish(force=True)
        except Exception as exc:  # noqa: BLE001
            self._error("boundary", exc)

    # ---- one publish ---------------------------------------------------------------------------------------------------
    def _modules(self):
        if self._mods is None:          # J2 reads the environment when it is imported: the host imports this module late
            from .. import j2, j2_map, views
            self._mods = (j2, j2_map, views)
        return self._mods

    def _error(self, where: str, exc: BaseException) -> None:
        self._errors += 1
        if self._errors <= MAX_TRACED_ERRORS:
            try:
                self.writer.trace("publish.error", {"where": where, "error": clip(f"{type(exc).__name__}: {exc}", 300)})
            except (EventError, OSError):
                pass

    def publish(self, *, force: bool = False) -> bool:
        """Write `snapshot.json` and `live.json` when they changed and emit the events that follow from the new state.
        `force` builds the events even when the files did not change. Returns True when anything was written."""
        run = self.run
        if run is None:
            return False
        j2, j2_map, views = self._modules()
        with self._lock:
            if self._stop.is_set() and not force:
                return False
            snap = live = None
            for attempt in (1, 2):                       # a dict that changes size under json.dumps: look again
                try:
                    snap, live = views.live_state(run)
                    snap_text = json.dumps(snap, ensure_ascii=False)
                    break
                except RuntimeError as exc:
                    if attempt == 2:
                        self._error("live_state", exc)
                        return False
                except Exception as exc:  # noqa: BLE001
                    self._error("live_state", exc)
                    return False
            live_cmp = json.dumps({k: v for k, v in live.items() if k != "at"}, ensure_ascii=False, sort_keys=True)
            changed = False
            try:
                if snap_text != self._snapshot_text:
                    _text_file_write(str(self.run_dir / SNAPSHOT_FILE), snap_text)
                    self._snapshot_text, changed = snap_text, True
                if live_cmp != self._live_cmp:
                    _text_file_write(str(self.run_dir / LIVE_FILE), json.dumps(live, ensure_ascii=False))
                    self._live_cmp, changed = live_cmp, True
            except OSError as exc:
                self._error("files", exc)
            emitted = 0
            if changed or force:
                try:
                    emitted = self._emit(snap, live, j2, j2_map)
                except Exception as exc:  # noqa: BLE001
                    self._error("events", exc)
            self._last_publish = self._clock()
            if changed or emitted:
                self.publishes += 1
            return changed or bool(emitted)

    # ---- the events ------------------------------------------------------------------------------------------------------
    def _emit(self, snap: dict, live: dict, j2, j2_map) -> int:
        running = snap.get("status") == "running" or bool(snap.get("paused"))
        arg = {"snapshot": snap, "stages": list(live.get("stages") or []), "stage_words": j2.J2Run.STAGE_WORDS,
               "board": live.get("board")} if running else None
        built = j2_map.build(self.run.dir, arg)
        pending: list[tuple[tuple, str, dict]] = []
        for key, kind, args in [*self._node_events(built, snap, j2), *self._step_events(built, snap)]:
            if self._sent.get(key) != args:
                pending.append((key, kind, args))
        order = {"node": 0, "step": 1}
        pending.sort(key=lambda item: order[item[1]])    # node, then step; the stable sort keeps the map's order inside
        count = 0
        for key, kind, args in pending:
            try:
                self.writer.emit((node_event if kind == "node" else step_event)(**args))
            except EventError as exc:
                if self.writer.ended:
                    return count
                self._error(kind, exc)
            self._sent[key] = args
            count += 1
        return count + self._atom_events(snap)

    @staticmethod
    def _tokens(calls: list, who: str) -> tuple[int, float, dict]:
        mine = [c for c in calls if c.get("fn") == who]
        return (len(mine), round(sum(c.get("seconds") or 0 for c in mine), 1),
                {"input": sum((c.get("tokens") or {}).get("input") or 0 for c in mine),
                 "output": sum((c.get("tokens") or {}).get("output") or 0 for c in mine)})

    def _node_events(self, built: dict, snap: dict, j2) -> list[tuple[tuple, str, dict]]:
        names = j2.NAMES
        out = []
        for node in built.get("nodes") or []:
            if node.get("kind") != "function" or not str(node.get("id", "")).startswith("fn:"):
                continue
            fn = node["id"][3:]
            if fn not in FUNCTIONS:
                continue
            status = node.get("status") if node.get("status") in FUNCTION_WORDS else "idle"
            args: dict[str, Any] = {"fn": fn, "status": status, "detail": clip(str(node.get("detail") or ""), 1000),
                                    "calls": int(node.get("calls") or 0), "seconds": float(node.get("seconds") or 0.0),
                                    "tokens": {"input": int((node.get("tokens") or {}).get("input") or 0),
                                               "output": int((node.get("tokens") or {}).get("output") or 0)}}
            wait_on = wait_on_key(node.get("wait_on"), names) if status in ("waiting", "waiting_on_you") else None
            if wait_on is not None:
                args["wait_on"] = wait_on
            mine = self._tasks.get(fn)
            if mine is not None:
                args["task"] = dict(mine["task"])
                args["context"] = [list(pair) for pair in mine["context"]]
            out.append((("node", "fn:" + fn), "node", args))
        calls = snap.get("call_log") or []
        flows = {f.get("id"): f for f in built.get("workflows") or []}
        for lane in snap.get("lanes") or []:
            wid = lane.get("id")
            if not isinstance(wid, str) or not re.fullmatch(r"W-[0-9]+", wid):
                continue
            flow = flows.get(wid) or {}
            n, seconds, tokens = self._tokens(calls, wid)
            args = {"step": wid, "status": builder_status(lane.get("status"), flow.get("status"), flow.get("atoms")),
                    "detail": clip(str(lane.get("doing") or ""), 1000), "calls": n, "seconds": seconds, "tokens": tokens}
            wait_on = wait_on_key(lane.get("on"), names) if args["status"] == "waiting" else None
            if wait_on is not None:
                args["wait_on"] = wait_on
            out.append((("node", wid), "node", args))
        return out

    def _step_events(self, built: dict, snap: dict) -> list[tuple[tuple, str, dict]]:
        out = []
        flows = [f for f in built.get("workflows") or [] if isinstance(f.get("id"), str) and re.fullmatch(r"W-[0-9]+", f["id"])]
        lanes = {lane.get("id"): lane for lane in snap.get("lanes") or []}
        revises = {w.get("id"): w.get("revises") for w in snap.get("workflows") or [] if isinstance(w, dict)}
        readers: dict[str, list[str]] = {f["id"]: [] for f in flows}
        for f in flows:
            for read in f.get("reads") or []:
                if read in readers and f["id"] not in readers[read]:
                    readers[read].append(f["id"])
        for f in flows:
            wid = f["id"]
            rework = revises.get(wid)
            out.append((("step", wid), "step", {
                "step": wid, "name": clip(str(f.get("name") or wid), 300), "parent": f.get("box"),
                "status": builder_status((lanes.get(wid) or {}).get("status"), f.get("status"), f.get("atoms")),
                "handoff": readers[wid], "reads": [r for r in f.get("reads") or [] if isinstance(r, str)],
                "rework": rework if isinstance(rework, str) and re.fullmatch(r"W-[0-9]+", rework) else None}))
        teams: dict[str, str] = {}
        for node in built.get("nodes") or []:
            persona = node.get("persona") if node.get("kind") == "engine" else None
            if not isinstance(persona, str) or not persona.strip():
                continue
            label = re.sub(r"[\x00-\x1f\x7f]", " ", persona).strip()[:80]
            status = node.get("status") if node.get("status") in TEAM_ORDER else "idle"
            old = teams.get(label)
            if old is None or TEAM_ORDER.index(status) < TEAM_ORDER.index(old):
                teams[label] = status
        for label, status in teams.items():
            out.append((("step", "team:" + label), "step", {"step": "team:" + label, "name": label, "parent": None,
                                                           "status": status, "handoff": [], "reads": [], "rework": None}))
        return out

    def _atom_events(self, snap: dict) -> int:
        count = 0
        views = snap.get("atoms_v1") or {}
        for aid in sorted(views):
            view = views[aid]
            attempt = min(int(view.get("attempt") or 0), 3)
            key = (view.get("status"), attempt)
            if self._atoms.get(aid) == key:
                continue
            self._atoms[aid] = key
            now = int(time.time())
            ts_open = self._ts_open.setdefault(aid, now)
            status = view.get("status")
            verification = view.get("verification") or []
            method = next((v.get("method") for v in verification if v.get("method")), None)
            failing = next((v.get("method") for v in verification if v.get("met") is False), None)
            body = json.loads(json.dumps(view, default=str))
            try:
                self.writer.emit(atom_event(node=str(view.get("workflow") or aid.split(".")[0]), atom={
                    "id": aid, "schema": "atom/1", "goal": clip(str(view.get("goal") or view.get("name") or aid), 2000),
                    "work_kind": "llm" if (view.get("how") or {}).get("kind") == "AI" else "bash",
                    "verify_template": clip(str(method).split(":")[0], 80) if method else None, "status": status,
                    "attempt": attempt, "closed_by": "verify" if status == "closed" else None,
                    "reason": clip(str(failing), 2000) if status in ("verify_failed", "abandoned") and failing else None,
                    "body": body, "ts_open": ts_open, "ts_closed": None if status == "open" else now}))
                count += 1
            except EventError as exc:
                if self.writer.ended:
                    return count
                self._error("atom", exc)
        return count


class HostHooks:
    """Wraps the hooks object the run uses: every hook goes to it first, then the publisher learns of the turn boundary and
    publishes at once. It remembers the code of the last `run_error` (the `ModelError` code that ends a crashed run). Any
    attribute the wrapped hooks have (`last_error`, `trace`, ...) is read through."""

    def __init__(self, inner, publisher: StatePublisher, context=None):
        self._inner = inner
        self.publisher = publisher
        self.context = context                       # the capabilities' EngineContext (D126); None: no capability adds text
        self.error_code: Optional[str] = None
        self.error_message: Optional[str] = None

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def run_started(self, spec: dict) -> None:
        return self._inner.run_started(spec)

    def run_status(self, snap: dict) -> None:
        result = self._inner.run_status(snap)
        self.publisher.notify()
        return result

    def turn_started(self, t) -> None:
        self._inner.turn_started(t)
        self.publisher.turn_started(t)
        self.publisher.boundary()

    def turn_finished(self, t, o) -> None:
        try:
            self._inner.turn_finished(t, o)
        finally:
            self.publisher.turn_finished(t)
            self.publisher.boundary()

    def call_finished(self, c) -> None:
        result = self._inner.call_finished(c)
        self.publisher.notify()
        return result

    def message_posted(self, m: dict, questions: Optional[list] = None) -> None:
        result = self._inner.message_posted(m, questions=questions)
        self.publisher.notify()
        return result

    def record_saved(self, name: str, data: Any) -> list[str]:
        result = self._inner.record_saved(name, data)
        self.publisher.notify()
        return result

    def run_error(self, code: str, message: str) -> None:
        self.error_code, self.error_message = code, message
        return self._inner.run_error(code, message)

    def system_addendum(self, fn: str) -> str:
        """The inner hooks' node-context text, then every capability's addendum for this agent (D126)."""
        text = self._inner.system_addendum(fn)
        if self.context is None:
            return text
        from .. import capabilities
        return (text if isinstance(text, str) else "") + capabilities.addenda(fn, self.context)
