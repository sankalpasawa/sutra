"""The kill switch and pause for multi-agent nodes (guardrails 7; D279). It is built before anything can spawn on purpose: the owner can stop and pause first.

    switch = KillSwitch(settings.nodes_dir)          # two files in <data>/nodes: KILL and PAUSE
    switch.level()                                   # "none", "pause" or "kill"
    switch.held()                                    # "" when nodes may start, else a plain sentence for a waiting task
    control = NodeControl(switch, tasks=..., db=..., store=..., clock=...)
    await control.kill_all(by="owner", reason="...") # writes KILL, runs the stop ladder on every live node, audits it

The two levels, and the two levels of stop that need no file:

    node stop    `NodeControl.stop_node(id)`: that node's task goes through the stop ladder (a queued one is cancelled); its dependants follow the usual rule for a task that ended badly.
    pause all    a file `<data>/nodes/PAUSE`: no new node starts anywhere; the nodes that run finish.
    kill all     a file `<data>/nodes/KILL`: the stop ladder for every live node, and no new node starts until the file is removed.
    (project stop arrives with the projects, MAN-5.)

The files exist because the page can be the thing that is stuck: the owner can create `KILL` by hand (an empty file is enough) or with `sutra-pro nodes kill`. Their presence is the
whole signal; a file the switch writes also holds a few words (who, why, when) as JSON, read only to show them. The check fails closed: a file that cannot be looked at counts as
present. `KILL` beats `PAUSE`. Whoever starts a node asks `KillSwitch.held()` inside its own start transaction (the Conductor's task gate, MAN-5), so a tick that was missed cannot spawn past
it; `NodeControl.enforce()` is the watcher's part for a file made by hand: it runs the ladder for every live node while `KILL` is there.

Nothing here kills a process itself: the one stop ladder is `ProcessLauncher.stop`, reached through `TaskService` (stop line, SIGTERM to the process group, SIGKILL only after the grace times,
as for every other stop). Nothing runs while SUTRA_NODES_V1 is off: the services are not built and the files are not looked at.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sutra_app import oslayer
from sutra_app.connectors.egress import scrubbed
from sutra_app.orchestrator.db import Database, run_blocking
from sutra_app.orchestrator.ids import Clock, SystemClock, iso_z
from sutra_app.orchestrator.nodes_store import NodeBlockError, node_block_of

__all__ = ["KillSwitch", "NodeControl", "KILL_FILE", "PAUSE_FILE", "LEVELS", "WATCH_S", "REASON_MAX", "LIVE_TASK_STATUSES", "OPEN_TASK_STATUSES", "NO_GRANT_HELD", "KillResult", "NOTE_MAX_BYTES"]

log = logging.getLogger(__name__)
KILL_FILE = "KILL"
PAUSE_FILE = "PAUSE"
LEVELS = ("none", "pause", "kill")
WATCH_S = 2.0                                  # how often the server looks for a file made by hand
REASON_MAX = 200
NOTE_MAX_BYTES = 4096                          # how much of a switch file is read to show its words
LIVE_TASK_STATUSES = ("starting", "running", "waiting_user")
OPEN_TASK_STATUSES = ("blocked", "queued", "starting", "running", "waiting_user")
KILL_OUTCOME = "stopped by the kill switch"
NO_GRANT_HELD = "Held: this agent has no valid grant"


class KillSwitch:
    """The two files. Reads only look at the file system; a write is a small file made by temp file and rename (mode 0600 in a 0700 folder)."""

    def __init__(self, directory: str | os.PathLike[str], *, clock: Clock | None = None) -> None:
        self.directory = Path(directory)
        self._clock = clock or SystemClock()
        self._latched = ""                         # "kill" or "pause" when the file could not be written: the switch is on in memory until it is cleared (Minor 3: a full or read-only disk must not open the gate)

    # ---- reading ---------------------------------------------------------------------------------------------------------------

    def _present(self, name: str) -> bool:
        """True when something is at `<folder>/<name>`. A link, a folder or a file nobody can read counts: the owner put it there, or the answer is not known, and the safe reading
        of "not known" is "stop"."""
        try:
            os.lstat(self.directory / name)
        except FileNotFoundError:
            return False
        except OSError:                            # includes NotADirectoryError (`<data>/nodes` is a file, or a part of the path was swapped for one): not known, so stop (Minor 3)
            return True
        return True

    @property
    def killed(self) -> bool:
        return self._latched == "kill" or self._present(KILL_FILE)

    @property
    def paused(self) -> bool:
        return self._latched in ("kill", "pause") or self._present(PAUSE_FILE)

    def latch(self, level: str) -> None:
        """Hold the switch in memory at `level` ("pause" or "kill") because its file could not be written; `clear` lets it go. The strongest level wins."""
        if level == "kill" or (level == "pause" and self._latched != "kill"):
            self._latched = level

    def level(self) -> str:
        """`kill` while the KILL file is there, else `pause` while the PAUSE file is, else `none`."""
        if self.killed:
            return "kill"
        return "pause" if self.paused else "none"

    def allows_spawn(self) -> bool:
        return self.level() == "none"

    def held(self) -> str:
        """The sentence a node that waits for this shows, or "" when nothing holds it (the waiting detail of a held task)."""
        level = self.level()
        if level == "kill":
            return "Stopped: the kill switch is on, so no agent starts (remove the KILL file or run `sutra-pro nodes resume`)"
        if level == "pause":
            return "Paused: no new agent starts until you resume (remove the PAUSE file or run `sutra-pro nodes resume`)"
        return ""

    def _note(self, name: str) -> dict[str, Any] | None:
        """What the file says (who, why, when), or None when it is not there. A file made by hand, empty or not JSON, says nothing: `{}`."""
        if not self._present(name):
            if self._latched == ("kill" if name == KILL_FILE else "pause"):
                return {"by": "system", "reason": "the file could not be written, so the switch is held in memory"}
            return None
        path = self.directory / name
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):         # a folder, a link or a pipe says nothing (and a pipe must never be opened: the read would wait for ever)
                return {}
            with open(path, "rb") as handle:
                found = json.loads(handle.read(NOTE_MAX_BYTES).decode("utf-8", "replace"))      # at most 4 KB: a file made by hand can be any size
        except (OSError, ValueError):
            return {}
        if not isinstance(found, dict):
            return {}
        return {key: " ".join(found[key].split())[:REASON_MAX] for key in ("by", "reason", "at") if isinstance(found.get(key), str)}

    def status(self) -> dict[str, Any]:
        """`{level, kill, pause}`: each of the two is None or what its file says."""
        return {"level": self.level(), "kill": self._note(KILL_FILE), "pause": self._note(PAUSE_FILE)}

    def stamp(self) -> tuple[int, int] | None:
        """`(mtime_ns, size)` of the KILL file, None when there is none or it cannot be looked at: a new file (or a changed one) is a new stamp, so the watcher audits each kill once."""
        try:
            st = os.lstat(self.directory / KILL_FILE)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    # ---- writing ---------------------------------------------------------------------------------------------------------------

    def set(self, level: str, *, by: str = "owner", reason: str = "") -> None:
        """Put the PAUSE or the KILL file there (`level` is `pause` or `kill`). An existing file is replaced by the new words."""
        if level not in ("pause", "kill"):
            raise ValueError("the switch is set to pause or kill")
        try:
            self._write(level, by, reason)
        except OSError:
            self.latch(level)                      # the file is not there, so the switch is held in memory: the gate still holds (Minor 3)
            raise

    def _write(self, level: str, by: str, reason: str) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.directory / (KILL_FILE if level == "kill" else PAUSE_FILE)
        body = json.dumps({"v": 1, "by": str(by)[:40], "reason": scrubbed(" ".join(str(reason).split()))[:REASON_MAX], "at": iso_z(self._clock.now())}, ensure_ascii=False) + "\n"
        temp = self.directory / f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"      # a name nobody else has: O_EXCL never meets a file left by a crash or by another writer
        fd = os.open(temp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())                                                       # on disk before it counts, as `task.json` is written
            oslayer.replace(temp, target)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise

    def clear(self, *, kill: bool = True, pause: bool = True) -> list[str]:
        """Remove the files asked for; returns the names that were there. A folder or link at the name is removed as the owner would (a link itself, not what it points at)."""
        removed = []
        if (self._latched == "kill" and kill) or (self._latched == "pause" and pause):
            removed.append(KILL_FILE if self._latched == "kill" else PAUSE_FILE)
            self._latched = ""
        for wanted, name in ((kill, KILL_FILE), (pause, PAUSE_FILE)):
            if not wanted or not self._present(name):
                continue
            path = self.directory / name
            try:
                if path.is_dir() and not path.is_symlink():
                    path.rmdir()                      # an empty folder only: what is inside a folder the owner made is never deleted by this
                else:
                    path.unlink()
                if name not in removed:
                    removed.append(name)
            except FileNotFoundError:
                continue
            except OSError as exc:                    # a folder that is not empty, a file nobody may remove: it stays, and `held()` still says so
                log.warning("the %s file of the node switch could not be removed (%s)", name, type(exc).__name__)
        return removed


class KillResult(int):
    """What `kill_all` returns: the number of nodes it stopped (so it compares and adds as a number), and whether the KILL file was written."""

    file_written: bool

    def __new__(cls, stopped: int, file_written: bool = True) -> "KillResult":
        found = super().__new__(cls, stopped)
        found.file_written = file_written
        return found


class NodeControl:
    """What the routes, the command line and the watcher call: stop one node, pause, kill, resume. It writes an audit row for each and uses the one stop ladder through `TaskService`.

    `tasks` is the `TaskService`, `store` a `NodeStore`; `kick` is called after a resume so that what waited starts (the scheduler's `start_ready`)."""

    def __init__(self, switch: KillSwitch, *, tasks: Any, db: Database, store: Any, clock: Clock | None = None, kick: Callable[[], Any] | None = None) -> None:
        self.switch = switch
        self.tasks = tasks
        self.db = db
        self.store = store
        self._clock = clock or SystemClock()
        self._kick = kick
        self._enforced: tuple[int, int] | None = None          # the KILL file the watcher has dealt with already
        self.projects: Any = None                              # the `ProjectService` (MAN-5): a kill ends its projects and stops its planners; None while there are none
        self._watcher: asyncio.Task[None] | None = None

    # ---- the nodes the switch reaches --------------------------------------------------------------------------------------------

    def _nodes(self, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
        """The nodes whose task is in one of `statuses`: id, project, role, task id, task status."""
        marks = ",".join("?" * len(statuses))
        rows = self.db.conn().execute(
            f"SELECT n.id AS id, n.project_id AS project_id, n.role AS role, n.task_id AS task_id, t.status AS status FROM agent_nodes n JOIN tasks t ON t.id = n.task_id "
            f"WHERE t.status IN ({marks}) ORDER BY t.created_at, t.rowid", statuses).fetchall()
        return [dict(row) for row in rows]

    def _audit(self, action: str, *, reason: str, node: dict[str, Any] | None = None, actor: str = "owner", count: int | None = None) -> None:
        with self.db.tx() as tx:
            self.store.audit(tx, actor=actor, action=action, project_id=node["project_id"] if node else None, node_id=node["id"] if node else None,
                             role=node["role"] if node else "", decision="n/a", reason=reason + (f" ({count} node(s))" if count is not None else ""), target="nodes")

    def _mark(self, node_id: str, state: str, why: str) -> None:
        with self.db.tx() as tx:
            self.store.mark_ended(tx, node_id, state, why)

    def gate(self, conn: Any, now: int, row: Any) -> str:
        """`TaskService.task_gate`: the sentence a NODE task waits with, "" for everything else (an ordinary task is never held). Two reasons hold a node: a file of the switch is there
        (the files are looked at first: one `lstat`), or its grant is missing, unreadable, wider than its role or not its own (D302): an ordinary task has the reach of a team run, wider than
        a reviewer's, so a node with a broken grant is held and never started as one. The Conductor's task gate (MAN-5) asks this first and adds its checks, never replaces it (D303)."""
        held = self.switch.held()
        found = conn.execute("SELECT 1 FROM agent_nodes WHERE task_id = ?", (row.id,)).fetchone()
        if found is None:
            return ""
        if held:
            return held
        try:
            node_block_of(conn, row.id)
        except NodeBlockError:
            return NO_GRANT_HELD
        return ""

    # ---- stop one node -----------------------------------------------------------------------------------------------------------

    async def stop_node(self, node_id: str, *, by: str = "owner") -> bool:
        """Stop one node: its task through the stop ladder (a queued or blocked one is cancelled). False when there is no such node, or its task is over already.
        The owner's own stop: the words are the ones a stopped task has, and the audit says `node.stopped`."""
        found = await run_blocking(self._node_of, node_id)
        if found is None and self.projects is not None:            # a planner node has no task: its running call is what the owner's stop ends (D301)
            return await self.projects.stop_planner_node(node_id)
        if found is None or found["status"] not in OPEN_TASK_STATUSES:
            return False
        stopped = await self.tasks.stop_node(found["task_id"], "stopped by you", by="owner" if by == "owner" else "system")
        if stopped:
            await run_blocking(self._mark, node_id, "cancelled", "stopped by you")
            await run_blocking(lambda: self._audit("node.stopped", reason="stopped by you", node=found, actor="owner" if by == "owner" else "system"))
        return stopped

    def _node_of(self, node_id: str) -> dict[str, Any] | None:
        row = self.db.conn().execute(
            "SELECT n.id AS id, n.project_id AS project_id, n.role AS role, n.task_id AS task_id, t.status AS status FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.id = ?",
            (node_id,)).fetchone()
        return dict(row) if row is not None else None

    # ---- pause, kill, resume -----------------------------------------------------------------------------------------------------

    async def pause_all(self, *, by: str = "owner", reason: str = "") -> int:
        """Put the PAUSE file there: no new node starts, the ones that run finish. Returns how many nodes now wait (queued or blocked) to start."""
        await run_blocking(lambda: self.switch.set("pause", by=by, reason=reason))
        waiting = await run_blocking(self._nodes, ("blocked", "queued"))
        await run_blocking(lambda: self._audit("pause", reason=reason or "paused", count=len(waiting), actor="owner" if by == "owner" else "system"))
        return len(waiting)

    async def kill_all(self, *, by: str = "owner", reason: str = "") -> "KillResult":
        """Put the KILL file there and run the stop ladder for every live node (all together). Returns how many nodes it stopped, as a number that also says `file_written`. No new node
        starts until the file is removed. It never fails open: if the file cannot be written (a read-only or full disk, a folder in the way) the ladders still run, the audit row says so
        and the caller is told (`file_written` is False), so the owner knows nothing holds the next start back."""
        written = True
        try:
            await run_blocking(lambda: self.switch.set("kill", by=by, reason=reason))
        except OSError as exc:
            written = False
            self.switch.latch("kill")                                  # the gate holds in memory although the file is not there (Minor 3)
            log.error("the KILL file could not be written (%s): the agents are stopped anyway", type(exc).__name__)
        if written:
            self._enforced = await run_blocking(self._marker)
        stopped = await self._sweep(KILL_OUTCOME)
        note = (reason or "kill all") + ("" if written else "; the KILL file could not be written")
        await run_blocking(lambda: self._audit("kill", reason=note, count=stopped, actor="owner" if by == "owner" else "system"))
        return KillResult(stopped, written)

    async def resume(self, *, by: str = "owner") -> bool:
        """Remove both files. True when there was something to remove; what waited then starts."""
        removed = await run_blocking(self.switch.clear)
        self._enforced = None
        if removed:
            await run_blocking(lambda: self._audit("resume", reason="resumed: " + ", ".join(removed), actor="owner" if by == "owner" else "system"))
            if self._kick is not None:
                found = self._kick()
                if asyncio.iscoroutine(found):
                    await found
        return bool(removed)

    async def _sweep(self, outcome: str) -> int:
        """What a kill does, in this order (D303): the projects with open nodes become `stopped` first, the planner calls and every live node are stopped together, then the nodes that had not
        started are cancelled. Without projects it is `_stop_live` alone."""
        if self.projects is None:
            return await self._stop_live(outcome)
        ids = await run_blocking(self.projects.begin_kill, outcome)
        planners = asyncio.ensure_future(run_blocking(self.projects.stop_planners, None))
        try:
            stopped = await self._stop_live(outcome)
        finally:
            await planners
        if ids:
            await self.projects.finish_kill(ids, outcome)
        return stopped

    async def _stop_live(self, outcome: str) -> int:
        """The ladder for every node whose task is starting, running or waiting for the owner, all together (as app shutdown does, D303): the whole kill takes about one ladder's time
        (12 s at most), not one per node. Each node is marked and audited as its ladder ends; a failure of one is logged and the others go on."""
        live = await run_blocking(self._nodes, LIVE_TASK_STATUSES)

        async def one(node: dict[str, Any]) -> int:
            try:
                if not await self.tasks.stop_node(node["task_id"], outcome, by="system"):
                    return 0
                await run_blocking(self._mark, node["id"], "cancelled", outcome)
                await run_blocking(lambda: self._audit("node.stopped", reason=outcome, node=node, actor="system"))
                return 1
            except Exception:                         # noqa: BLE001  (one node that will not stop must not keep the others running)
                log.exception("could not stop node %s", node["id"])
                return 0

        return sum(await asyncio.gather(*(one(node) for node in live)))

    # ---- the watcher ---------------------------------------------------------------------------------------------------------------

    def _marker(self) -> Any:
        """Which KILL file this is, for the audit's once-only rule: its stamp, or a fixed word for a file that cannot be looked at."""
        return self.switch.stamp() or ("unreadable",)

    async def enforce(self) -> int:
        """While a KILL file is there, run the stop ladder for every live node, on EVERY call: a node that started after the file appeared (a start that was under way, a retry) is
        stopped at the next tick, so nothing keeps running behind a kill (M1). Only the audit row `kill` is once per file (by its stamp). Returns how many it stopped. Costs one `lstat`
        when there is no file, and one query while there is."""
        if not await run_blocking(lambda: self.switch.killed):
            self._enforced = None
            return 0
        marker = await run_blocking(self._marker)
        first = marker != self._enforced
        self._enforced = marker
        stopped = await self._sweep(KILL_OUTCOME)
        if first:
            await run_blocking(lambda: self._audit("kill", reason="the KILL file was found", count=stopped, actor="system"))
        return stopped

    def spawn_guard(self, conn: Any, row: Any) -> str:
        """`TaskService.spawn_guard`, asked just before a process is started and just after: the outcome sentence when this task is a node and the KILL file is there, else "". A start
        that was decided before the kill (the task is `starting` already) is abandoned here, or stopped right after it began (M1)."""
        if not self.switch.killed:
            return ""
        return KILL_OUTCOME if conn.execute("SELECT 1 FROM agent_nodes WHERE task_id = ?", (row.id,)).fetchone() is not None else ""

    def start_watching(self, interval: float = WATCH_S) -> None:
        """Look for a KILL file made by hand every `interval` seconds, on the running loop. Idempotent."""
        if self._watcher is not None and not self._watcher.done():
            return
        self._watcher = asyncio.get_running_loop().create_task(self._watch(interval))

    async def _watch(self, interval: float) -> None:
        while True:
            try:
                await self.enforce()
            except asyncio.CancelledError:
                raise
            except Exception:                         # noqa: BLE001  (a bad look must not end the watch)
                log.exception("the kill switch watcher could not look")
            await asyncio.sleep(interval)

    async def stop_watching(self) -> None:
        task, self._watcher = self._watcher, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):         # noqa: BLE001
                pass

