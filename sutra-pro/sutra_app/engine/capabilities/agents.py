"""The capabilities of the agent sessions (engine design 3.3 and 3.5, D131, D133): each agent's own model and effort, and the live view of its work.

    AgentLiveCapability    keeps, per agent that is working, the text of its reply so far and its last tool call, and a daemon thread rewrites
                           `<run>/agent_live.json` from that at most four times a second; the server's watcher turns the file into `chat.partial`
                           events for the agent's chat (D133: a published file, not a ninth run event). An entry goes when its call ends.
    AgentPicksCapability   `install` gives the process's model router a reader of `<run>/choices.json`, the file the server writes from the owner's
                           choices (`connectors/agent_picks.py` owns its shape for both sides). The router then asks it, per request, which provider,
                           model and effort the agent a call is tagged for should get; a change applies from that agent's next call.

This file depends on the registry (`capabilities/base.py`) only for the `Capability` base class and on the connector layer only inside `install`,
so the engine still imports without the connectors. Neither capability changes what a call says: they route it and watch it.
"""
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from ..hooks import AGENT_PURPOSES

try:
    from .base import Capability
except ModuleNotFoundError as _missing:                    # pragma: no cover  (the registry is merged by another branch: stand alone until then)
    if _missing.name != f"{__package__}.base":
        raise

    class Capability:                                      # the same defaults as base.Capability: a capability overrides only what it adds
        name: str = ""

        def outputs(self) -> dict:
            return {}

        def install(self, ctx: Any) -> None:
            return None

        def tag(self, tag: Any, ctx: Any) -> dict:
            return {}

        def progress(self, tag: Any, event: dict) -> None:
            return None

        def addendum(self, fn: str, ctx: Any) -> str:
            return ""

        def select(self, brief: str, ctx: Any) -> Optional[Any]:
            return None

        def settings(self) -> list:
            return []

__all__ = ["AgentPicksCapability", "AgentLiveCapability", "router_of", "CHOICES_FILE", "LIVE_FILE", "LIVE_SCHEMA"]

log = logging.getLogger("sutra_app.engine.capabilities.agents")

CHOICES_FILE = "choices.json"          # = connectors.agent_picks.CHOICES_FILE (not imported: the engine must start without the connectors)
LIVE_FILE = "agent_live.json"
LIVE_SCHEMA = "agent-live/1"
LIVE_TAIL = 4000                       # characters of an agent's reply kept (the end of it: what it is writing now)
LIVE_INTERVAL = 0.25                   # seconds: the file is rewritten at most four times a second
LIVE_PURPOSES = AGENT_PURPOSES                       # an agent's own work; a helper call (summary, template, review) is not shown as the agent's
TOOL_CHARS = 200


def router_of(ctx: Any) -> Optional[Any]:
    """The model router of this process, or None (mock mode and the stdlib adapter have none). The host configures `llm` with its port before the
    capabilities are installed, so the port is where a capability finds the router; a context that carries its own `router` or `port` wins."""
    router = getattr(ctx, "router", None)
    if router is None:
        router = getattr(getattr(ctx, "port", None), "router", None)
    if router is None:
        from .. import llm
        router = getattr(getattr(llm, "_PORT", None), "router", None)
    return router


def run_dir_of(ctx: Any) -> Any:
    paths = getattr(ctx, "paths", None)
    return getattr(paths, "run_dir", None)


class AgentPicksCapability(Capability):
    """Each agent of a run has its own provider, model and effort when the owner chose one (D131). The capability adds nothing to a call's text or
    tag: `install` sets `router.agent_pick`, and the router does the rest (`Router._plan`, `Plan.effort_for`)."""

    name = "agent-picks"

    def install(self, ctx: Any) -> None:
        router, run_dir = router_of(ctx), run_dir_of(ctx)
        if router is None or run_dir is None or not hasattr(router, "agent_pick"):
            return                                         # mock mode: no router, nothing to route
        from sutra_app.connectors.agent_picks import AgentPicks
        router.agent_pick = AgentPicks(run_dir / CHOICES_FILE).for_tag


class AgentLiveCapability(Capability):
    """The live view of an agent's work (D133). `progress` sees every progress event of every engine call: `{"chars", "text"}` (the reply so far)
    and `{"tool": title}` (a tool call); the router's `finish_hooks` say when a call ends. The capability adds nothing to a call; it only watches it.

    The file: `{"schema": "agent-live/1", "at": <epoch>, "agents": {"W-3": {"call", "since", "text", "tool", "tools"}}}`, replaced atomically (0600).
    An agent is listed from its first event of a call until the call ends. `write_now()` writes at once (the thread calls it, throttled; tests call
    it directly); `threaded=False` leaves the thread out."""

    name = "agent-live"

    def __init__(self, *, interval: float = LIVE_INTERVAL, clock: Callable[[], float] = time.time, threaded: bool = True) -> None:
        self.interval = interval
        self._clock = clock
        self._threaded = threaded
        self._lock = threading.Lock()
        self._agents: dict[str, dict] = {}
        self._path: Optional[Path] = None
        self._last: Optional[dict] = None            # the body last written, without `at`
        self._dirty = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.writes = 0

    # ---- wiring ------------------------------------------------------------------------------------------------------------------
    def install(self, ctx: Any) -> None:
        router, run_dir = router_of(ctx), run_dir_of(ctx)
        if router is None or run_dir is None or not hasattr(router, "finish_hooks"):
            return                                         # mock mode: nothing runs a tool, nothing to show
        self.attach(Path(run_dir) / LIVE_FILE)
        if self.finished not in router.finish_hooks:
            router.finish_hooks.append(self.finished)

    def attach(self, path: "str | Path") -> None:
        """Publish to `path` from now on (and start the writer thread unless this capability was made `threaded=False`)."""
        self._path = Path(path)
        self._stop.clear()
        if self._threaded and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._loop, name="agent-live", daemon=True)
            self._thread.start()

    def close(self) -> None:
        """Stop the thread and write what is left (a run that ends cleanly has no entry left, so the file ends empty)."""
        self._stop.set()
        self._dirty.set()
        thread = self._thread
        if thread is not None:
            thread.join(2.0)
        self._thread = None
        self.write_now()

    # ---- what the engine's calls tell us -------------------------------------------------------------------------------------------
    def progress(self, tag: Any, event: dict) -> None:
        if self._path is None or tag.purpose not in LIVE_PURPOSES or not isinstance(event, dict):
            return
        text, tool = event.get("text"), event.get("tool")
        if not isinstance(text, str) and not isinstance(tool, str):
            return                                         # a note ("claude out of quota, answered by codex") is not live work
        key = tag.function or "agent"
        with self._lock:
            entry = self._agents.get(key)
            if entry is None:
                entry = self._agents[key] = {"call": tag.call_no, "since": round(self._clock(), 3), "text": "", "tool": "", "tools": 0}
            if isinstance(text, str):
                entry["text"] = text[-LIVE_TAIL:]
            if isinstance(tool, str):
                entry["tool"] = tool[:TOOL_CHARS]
                entry["tools"] += 1
        self._dirty.set()

    def finished(self, tag: Any) -> None:
        """The call this tag belongs to is over: its entry goes."""
        with self._lock:
            gone = self._agents.pop(tag.function or "agent", None)
        if gone is not None:
            self._dirty.set()

    # ---- the file ----------------------------------------------------------------------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return {"schema": LIVE_SCHEMA, "agents": {name: dict(entry) for name, entry in sorted(self._agents.items())}}

    def write_now(self) -> bool:
        """Replace the file with the agents' state now. False, touching nothing, when it is what the file already holds."""
        path = self._path
        if path is None:
            return False
        body = self.snapshot()
        if body == self._last:
            return False
        tmp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
        data = json.dumps({**body, "at": round(self._clock(), 3)}, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
            try:
                os.write(fd, data.encode("utf-8"))
            finally:
                os.close(fd)
            from sutra_app import oslayer
            oslayer.replace(tmp, path)
        except OSError as exc:                             # a view that cannot be written is lost, the run is not
            log.warning("could not write %s (%s)", path, type(exc).__name__)
            return False
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        self._last = body
        self.writes += 1
        return True

    def _loop(self) -> None:
        """Write when something changed, then rest for `interval`: events that come in the meantime are written together afterwards."""
        while not self._stop.is_set():
            self._dirty.wait()
            if self._stop.is_set():
                return
            self._dirty.clear()
            self.write_now()
            self._stop.wait(self.interval)
