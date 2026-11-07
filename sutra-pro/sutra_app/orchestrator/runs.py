"""The run launcher, the watcher and the start-up reconcile (orchestrator 5.1, 5.6; D14, D16, D23, D24; S1-contracts-11, -15, -16).

    launcher = ProcessLauncher()                 # the default RunLauncher; testing.fake_engine.FakeLauncher is the double
    pid = await launcher.start(spec, run_dir)    # python -m sutra_app.engine --run-dir <dir>, new session, own stdout/stderr files
    n = launcher.send(run_dir, {"kind": "user", "text": "..."})      # appends to inbox.jsonl, returns the line number
    await launcher.stop(run_dir, pid)            # THE stop ladder: stop line, STOP_GRACE_S, SIGTERM to the group, TERM_GRACE_S, SIGKILL
    launcher.alive(pid)                          # the Process handle when this server spawned the pid, else os.kill(pid, 0)

    RunWatcher(projector, tasks, launcher, ...)  # one asyncio task per live run: drain events.jsonl every watch_ms, detect a crash
    await reconcile(...)                         # at server start: settle, re-attach or crash every unfinished task

The child environment is `connectors.env.PASS_NAMES` plus SHELL, TERM, PYTHONPATH, every `SUTRA_*` except `SUTRA_TOKEN`, and the
seven task-settings keys of the run spec; a name that looks like a secret (KEY, TOKEN, SECRET, PASSWORD) is never passed. The
owner's own logins reach the child through the allowlist (CLAUDE_CONFIG_DIR, CODEX_HOME, XDG_*, proxy and certificate names).
"""
import asyncio
import json
import logging
import os
from sutra_app import oslayer
import signal
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sutra_app.connectors.env import PASS_NAMES, is_secret_name
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.ids import Clock, SystemClock, iso_z
from sutra_app.orchestrator.models import RunSpec
from sutra_app.orchestrator.pathwords import machine_roots, shorten

__all__ = [
    "STOP_GRACE_S", "TERM_GRACE_S", "SILENT_AFTER_S", "STDERR_TAIL_BYTES", "EXTRA_PASS_NAMES", "child_environment", "RunLauncher",
    "ProcessLauncher", "RunWatcher", "ReconcileReport", "reconcile", "run_has_ended", "stderr_tail", "inbox_line_count", "append_inbox",
]

log = logging.getLogger(__name__)
STOP_GRACE_S = 8.0               # after the stop line: wait this long for run.ended
TERM_GRACE_S = 4.0               # after SIGTERM to the process group: wait this long, then SIGKILL (12 s in all)
SILENT_AFTER_S = 30.0            # no event for this long: "no signal" (and, at app start, a crash)
STDERR_TAIL_BYTES = 2048
EXTRA_PASS_NAMES = ("SHELL", "TERM", "PYTHONPATH")
ENGINE_MODULE = "sutra_app.engine"
_POLL_S = 0.05


# ---- the child environment ---------------------------------------------------------------------------------------------

def child_environment(settings: Mapping[str, str] | None = None, environ: Mapping[str, str] | None = None,
                      extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment of one engine process: PASS_NAMES + SHELL, TERM, PYTHONPATH + every SUTRA_* except SUTRA_TOKEN + the
    task-settings keys (J2_*) given in `settings`. A name that looks like a secret is dropped wherever it comes from;
    `extra` (tests) is added last and held to the same rule."""
    source = os.environ if environ is None else environ
    env: dict[str, str] = {}
    for name in (*PASS_NAMES, *EXTRA_PASS_NAMES):
        if name in source and not is_secret_name(name):
            env[name] = source[name]
    for name, value in source.items():
        if name.startswith("SUTRA_") and name != "SUTRA_TOKEN" and not is_secret_name(name):
            env[name] = value
    for name, value in {**(settings or {}), **(extra or {})}.items():
        if is_secret_name(name) or "=" in name or "\0" in name or "\0" in str(value):
            continue
        env[name] = str(value)
    return env


# ---- small file helpers --------------------------------------------------------------------------------------------------

def inbox_line_count(run_dir: Path) -> int:
    try:
        return sum(1 for raw in (Path(run_dir) / "inbox.jsonl").read_bytes().split(b"\n") if raw.strip())
    except OSError:
        return 0


def append_inbox(run_dir: Path, line: dict) -> int:
    """Append `{"n": <next line number>, ...line}` to the run's `inbox.jsonl` with one write (the engine's tailer never sees half a
    line) and return the number."""
    n = inbox_line_count(run_dir) + 1
    body = {key: value for key, value in line.items() if key != "n"}
    data = (json.dumps({"n": n, **body}, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(Path(run_dir) / "inbox.jsonl", os.O_WRONLY | oslayer.O_BINARY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return n


def run_has_ended(run_dir: Path) -> bool:
    """True when the last lines of `events.jsonl` hold a `run.ended` event."""
    try:
        with open(Path(run_dir) / "events.jsonl", "rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - 65536))
            tail = handle.read()
    except OSError:
        return False
    for raw in reversed([line for line in tail.split(b"\n") if line.strip()][-20:]):
        try:
            if json.loads(raw).get("t") == "run.ended":
                return True
        except ValueError:
            continue
    return False


def stderr_tail(run_dir: Path, limit: int = STDERR_TAIL_BYTES) -> str:
    """The last `limit` bytes of `run.stderr.log` as text (the caller redacts it before it is shown or stored)."""
    try:
        with open(Path(run_dir) / "run.stderr.log", "rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", "replace").strip()
    except OSError:
        return ""


# ---- the launcher ------------------------------------------------------------------------------------------------------------

class RunLauncher(Protocol):
    """What the TaskService needs of a launcher. `ProcessLauncher` is the default, `FakeLauncher` the test double."""

    async def start(self, spec: RunSpec, run_dir: Path) -> int: ...

    def send(self, run_dir: Path, line: dict) -> int: ...

    async def stop(self, run_dir: Path, pid: int | None) -> None: ...

    def alive(self, pid: int | None) -> bool: ...


class ProcessLauncher:
    """Starts `python -m sutra_app.engine --run-dir <dir>` in a new session (so one signal reaches the whole process group,
    Chrome children included), with stdout and stderr in the run folder. `module` and `extra_env` exist for tests that run the
    fake engine process instead of the real one."""

    def __init__(self, *, module: str = ENGINE_MODULE, environ: Mapping[str, str] | None = None, extra_env: Mapping[str, str] | None = None,
                 stop_grace: float | None = None, term_grace: float | None = None, python: str | None = None) -> None:
        self.module = module
        self._environ = environ
        self._extra_env = dict(extra_env or {})
        self._stop_grace = stop_grace
        self._term_grace = term_grace
        self._python = python or oslayer.console_python()
        self._handles: dict[int, asyncio.subprocess.Process] = {}

    # ---- starting ----------------------------------------------------------------------------------------------------

    def environment(self, spec: RunSpec) -> dict[str, str]:
        settings = {k: v for k, v in spec.settings.model_dump().items() if isinstance(v, str)}
        return child_environment(settings, self._environ, self._extra_env)

    async def start(self, spec: RunSpec, run_dir: Path) -> int:
        run_dir = Path(run_dir)
        out_fd = os.open(run_dir / "run.stdout.log", os.O_WRONLY | oslayer.O_BINARY | os.O_APPEND | os.O_CREAT, 0o600)
        err_fd = os.open(run_dir / "run.stderr.log", os.O_WRONLY | oslayer.O_BINARY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._python, *self._interpreter_flags(), "-m", self.module, "--run-dir", str(run_dir), env=self.environment(spec),
                stdin=asyncio.subprocess.DEVNULL, stdout=out_fd, stderr=err_fd, cwd=str(run_dir), **oslayer.popen_group_kwargs())
        finally:
            os.close(out_fd)
            os.close(err_fd)
        self._handles[proc.pid] = proc
        return proc.pid

    @staticmethod
    def _interpreter_flags() -> list[str]:
        """Windows: UTF-8 mode, so every file the engine opens without an encoding is UTF-8, not the legacy code page."""
        return ["-X", "utf8"] if oslayer.IS_WINDOWS else []

    # ---- the inbox -----------------------------------------------------------------------------------------------------

    def send(self, run_dir: Path, line: dict) -> int:
        """Append one object to `inbox.jsonl` as `{"n": <line number>, ...line}`; returns the line number (counted from 1)."""
        return append_inbox(run_dir, line)

    # ---- life and death ------------------------------------------------------------------------------------------------

    def alive(self, pid: int | None) -> bool:
        """The Process handle when this server spawned the pid (a return code means it is gone), else `os.kill(pid, 0)`."""
        if not pid or pid < 1:
            return False
        handle = self._handles.get(pid)
        if handle is not None:
            return handle.returncode is None
        return oslayer.pid_alive(pid)

    def exit_code(self, pid: int | None) -> int | None:
        handle = self._handles.get(pid or 0)
        return handle.returncode if handle is not None else None

    @staticmethod
    def command_of(pid: int | None) -> str:
        """`ps -p <pid> -o command=` (empty when there is no such process): the identity check of the reconcile pass."""
        if not pid or pid < 1:
            return ""
        if oslayer.IS_WINDOWS:
            return oslayer.process_command(pid)
        try:
            done = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return ""
        return done.stdout.strip() if done.returncode == 0 else ""

    def _signal_group(self, pid: int, sig: int) -> None:
        if oslayer.IS_WINDOWS:
            # no signals to send to a process with no console: SIGTERM and SIGKILL both end the process and what it started
            oslayer.kill_tree(pid)
            return
        try:
            os.killpg(os.getpgid(pid), sig)
        except ProcessLookupError:
            return
        except PermissionError:
            log.warning("no permission to signal process group of %s", pid)
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                pass

    async def _wait(self, pid: int, seconds: float, stop_when: Callable[[], bool] | None = None) -> bool:
        """True when the process is gone (or `stop_when()` holds) within `seconds`."""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            if not self.alive(pid):
                return True
            if stop_when is not None and stop_when():
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(_POLL_S)

    async def stop(self, run_dir: Path, pid: int | None, *, stop_grace: float | None = None, term_grace: float | None = None) -> None:
        """THE stop ladder (D23): append `{"kind":"stop"}` to the inbox, wait up to STOP_GRACE_S for `run.ended` (or the exit),
        send SIGTERM to the process group, wait TERM_GRACE_S, then SIGKILL (12 s at most with the defaults)."""
        run_dir = Path(run_dir)
        if not self.alive(pid):
            return
        stop_s = stop_grace if stop_grace is not None else (self._stop_grace if self._stop_grace is not None else STOP_GRACE_S)
        term_s = term_grace if term_grace is not None else (self._term_grace if self._term_grace is not None else TERM_GRACE_S)
        try:
            self.send(run_dir, {"kind": "stop", "at": iso_z(time.time())})
        except OSError:
            log.warning("could not append the stop line to %s", run_dir)
        ended = False

        def has_ended() -> bool:
            nonlocal ended
            ended = ended or run_has_ended(run_dir)
            return ended

        if await self._wait(pid, stop_s, has_ended):
            if not self.alive(pid):
                return
        if not ended:
            self._signal_group(pid, signal.SIGTERM)
        if await self._wait(pid, term_s):
            return
        self._signal_group(pid, oslayer.SIGKILL)
        await self._wait(pid, 2.0)


# ---- the watcher -------------------------------------------------------------------------------------------------------------

class RunWatcher:
    """One asyncio task per live run. Every `interval` seconds it drains `events.jsonl` into the Projector (one transaction per
    batch, together with the new offset); a task whose process is gone with no terminal event is `crashed` after one final
    drain; a silent but alive process is never touched, only flagged ('no signal for N s') after SILENT_AFTER_S.

    `after_drain` is awaited when a drain freed a run slot (a team began waiting for the owner, or a task ended): the
    TaskService passes `start_ready`."""

    def __init__(self, projector: Any, tasks: Any, launcher: Any, *, interval: float = 0.4, clock: Clock | None = None,
                 redact: Callable[[str], str] | None = None, after_drain: Callable[[], Awaitable[Any]] | None = None,
                 silent_after: float = SILENT_AFTER_S) -> None:
        self.projector = projector
        self.tasks = tasks
        self.launcher = launcher
        self.interval = interval
        self.clock = clock or SystemClock()
        self.redact = redact or (lambda text: text)
        self.after_drain = after_drain
        self.silent_after = silent_after
        self._jobs: dict[str, asyncio.Task] = {}
        self._wakes: dict[str, asyncio.Event] = {}
        self._retired: set[str] = set()
        self._closing = False
        self._flagged: dict[str, int] = {}

    def watching(self) -> list[str]:
        return [task_id for task_id, job in self._jobs.items() if not job.done()]

    def watch(self, task_id: str) -> None:
        """Start (or keep) the watcher of one task. Needs a running event loop."""
        job = self._jobs.get(task_id)
        if job is not None and not job.done():
            return
        self._retired.discard(task_id)
        self._wakes[task_id] = asyncio.Event()
        self._jobs[task_id] = asyncio.get_running_loop().create_task(self._loop(task_id), name=f"watch-{task_id}")

    def unwatch(self, task_id: str) -> None:
        """Ask the watcher of a task to finish after the look it is making (a database call is never cut off halfway)."""
        if task_id in self._jobs:
            self._retired.add(task_id)
            wake = self._wakes.get(task_id)
            if wake is not None:
                wake.set()
        self._flagged.pop(task_id, None)

    async def close(self, timeout: float = 15.0) -> None:
        """Stop every watcher gracefully (app shutdown, after the final drains): each finishes the look it is in, then returns."""
        jobs = [job for job in self._jobs.values() if not job.done()]
        self._closing = True
        for wake in list(self._wakes.values()):
            wake.set()
        if jobs:
            done, pending = await asyncio.wait(jobs, timeout=timeout)
            for job in pending:
                job.cancel()
        self._closing = False
        self._jobs.clear()
        self._wakes.clear()
        self._retired.clear()

    async def _loop(self, task_id: str) -> None:
        wake = self._wakes[task_id]
        try:
            while not self._closing and task_id not in self._retired:
                if await self.tick(task_id):
                    return
                try:
                    await asyncio.wait_for(wake.wait(), self.interval)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:                                      # noqa: BLE001  (a watcher must not die silently)
            log.exception("the watcher of %s stopped on an error", task_id)
        finally:
            if self._jobs.get(task_id) is asyncio.current_task():
                self._jobs.pop(task_id, None)
                self._wakes.pop(task_id, None)
            self._retired.discard(task_id)

    async def drain(self, task_id: str, *, notify: bool = True) -> Any:
        """Drain until the file is read to its end; returns the last result (and calls `after_drain` once if a slot was freed)."""
        freed, result = False, None
        while True:
            result = await run_blocking(self.projector.drain, task_id)
            freed = freed or result.freed_slot
            if not result.more:
                break
        if freed and notify and self.after_drain is not None:
            await self.after_drain()
        return result

    async def tick(self, task_id: str) -> bool:
        """One look at one task. True when the task is over (stop watching)."""
        result = await self.drain(task_id)
        if result.ended:
            return True
        row = await run_blocking(self.tasks.find_row, task_id)
        if row is None or row.status not in ("starting", "running", "waiting_user"):
            return True
        if not self.launcher.alive(row.pid):
            final = await self.drain(task_id)                  # the process may have written its last lines as it died
            if final.ended:
                return True
            outcome = self.crash_outcome(row)
            await run_blocking(self.projector.mark_ended, task_id, "crashed", outcome, "process_gone")
            if self.after_drain is not None:
                await self.after_drain()
            return True
        age = self.clock.now() - (row.last_event_at or row.started_at or row.created_at)
        if age > self.silent_after:
            bucket = int(age // 5 * 5)
            if self._flagged.get(task_id) != bucket:
                self._flagged[task_id] = bucket
                await run_blocking(self.projector.flag_silent, task_id, int(age))
        else:
            self._flagged.pop(task_id, None)
        return False

    def crash_outcome(self, row: Any) -> str:
        """'the team process stopped unexpectedly', the exit code when known and the redacted stderr tail (up to 2 KB), with this machine's
        folders shortened to file names (pathwords: the owner reads 'tools.py', not the install folder; run.stderr.log keeps the whole tail)."""
        text = "the team process stopped unexpectedly"
        code = getattr(self.launcher, "exit_code", lambda pid: None)(row.pid)
        if code is not None:
            text += f" (exit code {code})"
        tail = ""
        try:
            tail = self.tasks.stderr_tail(row)
        except Exception:                                      # noqa: BLE001
            tail = ""
        if tail:
            text += ": " + shorten(self.redact(tail)[-STDERR_TAIL_BYTES:], machine_roots([getattr(self.tasks, "data_dir", None) or ""]))
        return text[:2000]


# ---- reconcile at server start ----------------------------------------------------------------------------------------------

@dataclass
class ReconcileReport:
    settled: list[str] = field(default_factory=list)        # a terminal event was found while draining
    reattached: list[str] = field(default_factory=list)     # the process lives and talks: watched again
    crashed: list[str] = field(default_factory=list)        # no process, or a silent one: crashed
    signalled: list[str] = field(default_factory=list)      # silent processes the stop ladder was run on (identity proven)
    untouched: list[str] = field(default_factory=list)      # silent pids whose command was not ours: nothing signalled

    def all(self) -> list[str]:
        return [*self.settled, *self.reattached, *self.crashed]


async def reconcile(*, tasks: Any, projector: Any, watcher: Any, launcher: Any, publish: Callable[[str, dict], Any] | None = None,
                    clock: Clock | None = None, silent_after: float = SILENT_AFTER_S) -> ReconcileReport:
    """Run once after migrate and bootstrap, before `start_ready()` (5.1 step 6). For each task in starting, running or
    waiting_user: (1) drain `events.jsonl` from `events_offset`; (2) a terminal event settles the task; (3) a live pid with a
    recent line is watched again; (4) a live but silent pid is signalled only when `ps` shows our engine for that very run
    folder, and the task is crashed; (5) a missing pid is crashed ('the app was closed while it ran'); (6) `starting` without a
    pid is crashed ('could not start'). Ends with `server.resync {reason: 'restart'}`."""
    clock = clock or SystemClock()
    report = ReconcileReport()
    for task_id in await run_blocking(tasks.unfinished_ids):
        result = await watcher.drain(task_id, notify=False)
        row = await run_blocking(tasks.find_row, task_id)
        if row is None:
            continue
        if result.ended or row.status not in ("starting", "running", "waiting_user"):
            report.settled.append(task_id)
            continue
        last = row.last_event_at or row.started_at or row.created_at
        recent = clock.now() - last <= silent_after
        if row.status == "starting" and not row.pid:
            await run_blocking(projector.mark_ended, task_id, "crashed", "could not start", "start_failed")
            report.crashed.append(task_id)
        elif not row.pid or not launcher.alive(row.pid):
            await run_blocking(projector.mark_ended, task_id, "crashed", "the app was closed while it ran", "app_closed")
            report.crashed.append(task_id)
        elif recent:
            watcher.watch(task_id)
            report.reattached.append(task_id)
        else:
            run_dir = await run_blocking(tasks.run_dir_of, row)
            command = getattr(launcher, "command_of", lambda pid: "")(row.pid)
            if f"{ENGINE_MODULE} --run-dir {run_dir}" in command:
                await launcher.stop(run_dir, row.pid)
                report.signalled.append(task_id)
            else:
                report.untouched.append(task_id)
            await watcher.drain(task_id, notify=False)
            final = await run_blocking(tasks.find_row, task_id)
            if final is not None and final.status in ("starting", "running", "waiting_user"):
                await run_blocking(projector.mark_ended, task_id, "crashed",
                                   "the app was closed while it ran and the team stopped answering", "app_closed")
            report.crashed.append(task_id)
    if publish is not None:
        publish("server.resync", {"reason": "restart"})
    return report
