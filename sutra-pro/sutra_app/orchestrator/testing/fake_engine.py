"""A fake engine for the orchestrator tests (orchestrator 7, "Test doubles"): `FakeLauncher` runs a script in-process, and
`python -m sutra_app.orchestrator.testing.fake_engine --run-dir D` plays the same script as a real process.

A script is a list of steps, played in order:

    {"emit": {...a run event...}}      append one line to events.jsonl (`at` is filled in when missing; run.started gets this pid);
                                       a `run.ended` line ends the run
    {"wait_inbox": n}                  wait until inbox.jsonl holds n lines (a `stop` line ends the run: run.ended stopped)
    {"sleep": seconds}                 wait
    {"hold": true}                     stay alive until a stop line arrives (or the process is killed)
    {"die": code}                      the process vanishes WITHOUT writing run.ended (a crash); the exit code is `code`
    {"ignore_stop": true}              from now on a stop line is not honoured (the ladder has to use signals)

`FakeLauncher(scripts)`: `scripts` is a mapping from run id, task id, department id or `"*"` (looked up in that order) to a script,
or a callable `RunSpec -> script`. With none, the run starts, ends done and writes `run.ended`. The fake gives each run a distinct
fake pid (from 2,000,000,000: far above any real one), so the crash rules can tell the runs apart; `alive(pid)` is true while
the script is still playing. Nothing here touches the network or a model.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import RunSpec
from sutra_app.orchestrator.runs import append_inbox, inbox_line_count

__all__ = ["FakeLauncher", "play", "standard_script", "ev", "FIRST_FAKE_PID", "SCRIPT_FILE", "main"]

FIRST_FAKE_PID = 2_000_000_000
SCRIPT_FILE = "fake_script.json"
_POLL_S = 0.01


def ev(t: str, **fields: Any) -> dict[str, Any]:
    """A run event dict (`at` is added when it is played)."""
    return {"t": t, **fields}


def standard_script(*, outcome: str = "Done.", status: str = "done") -> list[dict[str, Any]]:
    """run.started, then run.ended."""
    return [{"emit": ev("run.started", schema="events/1", mock=True, seed="none")}, {"emit": ev("run.ended", status=status, outcome=outcome)}]


def _append(path: Path, event: Mapping[str, Any]) -> None:
    data = (json.dumps(dict(event), ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)                                     # one write per line: the watcher never sees half of one
    finally:
        os.close(fd)


def _has_stop(run_dir: Path) -> bool:
    try:
        lines = (run_dir / "inbox.jsonl").read_bytes().split(b"\n")
    except OSError:
        return False
    for raw in lines:
        try:
            if raw.strip() and json.loads(raw).get("kind") == "stop":
                return True
        except ValueError:
            continue
    return False


async def play(run_dir: Path, steps: list[dict[str, Any]], *, pid: int | None = None) -> int:
    """Play a script against a run folder; returns the exit code (0 normal, the `die` code, or 0 after a stop)."""
    run_dir = Path(run_dir)
    events = run_dir / "events.jsonl"
    pid = pid or os.getpid()
    honour_stop = True

    def stopped() -> bool:
        return honour_stop and _has_stop(run_dir)

    async def end_stopped() -> None:
        _append(events, {"t": "run.ended", "at": iso_z(time.time()), "status": "stopped", "outcome": "stopped by you"})

    for step in steps:
        if stopped():
            await end_stopped()
            return 0
        if "emit" in step:
            line = dict(step["emit"])
            line.setdefault("at", iso_z(time.time()))
            if line.get("t") == "run.started":
                line.setdefault("pid", pid)
            _append(events, line)
            if line.get("t") == "run.ended":
                break
        elif "wait_inbox" in step:
            while inbox_line_count(run_dir) < int(step["wait_inbox"]):
                if stopped():
                    await end_stopped()
                    return 0
                await asyncio.sleep(_POLL_S)
        elif "sleep" in step:
            await asyncio.sleep(float(step["sleep"]))
        elif step.get("hold"):
            while not stopped():
                await asyncio.sleep(_POLL_S)
            await end_stopped()
            return 0
        elif "die" in step:
            return int(step["die"])
        elif "ignore_stop" in step:
            honour_stop = not step["ignore_stop"]
    return 0


class FakeLauncher:
    """Implements `RunLauncher` in-process. `started` lists every (spec, run_dir) it was given; `fail_with` makes `start` raise."""

    def __init__(self, scripts: Mapping[str, list[dict[str, Any]]] | Callable[[RunSpec], list[dict[str, Any]]] | None = None, *,
                 stop_grace: float = 0.5, command: Callable[[int, Path], str] | None = None) -> None:
        self._scripts = scripts
        self.stop_grace = stop_grace
        self.started: list[tuple[RunSpec, Path]] = []
        self.sent: list[tuple[Path, dict]] = []
        self.stopped: list[int] = []
        self.fail_with: BaseException | None = None
        self.commands: dict[int, str] = {}
        self._next_pid = FIRST_FAKE_PID
        self._jobs: dict[int, asyncio.Task] = {}
        self._alive: set[int] = set()
        self._dirs: dict[int, Path] = {}
        self._codes: dict[int, int] = {}
        self._killed: set[int] = set()
        self._command = command

    # ---- scripts -----------------------------------------------------------------------------------------------------

    def script_for(self, spec: RunSpec) -> list[dict[str, Any]]:
        if callable(self._scripts):
            return list(self._scripts(spec))
        if self._scripts:
            for key in (spec.run_id, spec.task_id, spec.dept_id, "*"):
                if key in self._scripts:
                    return list(self._scripts[key])
        return standard_script()

    # ---- the RunLauncher protocol -----------------------------------------------------------------------------------------

    async def start(self, spec: RunSpec, run_dir: Path) -> int:
        if self.fail_with is not None:
            raise self.fail_with
        pid = self._next_pid
        self._next_pid += 1
        self.started.append((spec, Path(run_dir)))
        self._dirs[pid] = Path(run_dir)
        self.commands[pid] = self._command(pid, Path(run_dir)) if self._command else f"python -m sutra_app.engine --run-dir {run_dir}"
        self._alive.add(pid)
        self._jobs[pid] = asyncio.get_running_loop().create_task(self._run(pid, Path(run_dir), self.script_for(spec)))
        return pid

    async def _run(self, pid: int, run_dir: Path, script: list[dict[str, Any]]) -> None:
        """Play the script. The process counts as alive until the script ends or it is killed. A loop that is torn down (a test
        with several `asyncio.run` calls) cancels the player but leaves the 'process' alive: it just stops writing."""
        try:
            self._codes[pid] = await play(run_dir, script, pid=pid)
            self._alive.discard(pid)
        except asyncio.CancelledError:
            if pid in self._killed:
                self._alive.discard(pid)
            raise

    def send(self, run_dir: Path, line: dict) -> int:
        n = append_inbox(run_dir, line)
        self.sent.append((Path(run_dir), {"n": n, **line}))
        return n

    def alive(self, pid: int | None) -> bool:
        return (pid or 0) in self._alive

    def exit_code(self, pid: int | None) -> int | None:
        return self._codes.get(pid or 0)

    def command_of(self, pid: int | None) -> str:
        return self.commands.get(pid or 0, "") if self.alive(pid) else ""

    async def stop(self, run_dir: Path, pid: int | None, *, stop_grace: float | None = None, term_grace: float | None = None) -> None:
        """The stop line, a wait for the script to end by itself, then the process is killed (what SIGKILL would do)."""
        pid = pid or 0
        if pid not in self._alive:
            return
        self.stopped.append(pid)
        self.send(run_dir, {"kind": "stop", "at": iso_z(time.time())})
        job = self._jobs.get(pid)
        if job is not None and not job.done():
            try:
                await asyncio.wait_for(asyncio.shield(job), stop_grace if stop_grace is not None else self.stop_grace)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        if pid in self._alive:
            self.kill(pid)
            if job is not None and not job.done():
                try:
                    await job
                except asyncio.CancelledError:
                    pass

    # ---- helpers for tests --------------------------------------------------------------------------------------------------

    async def wait(self, pid: int, timeout: float = 5.0) -> None:
        """Wait until the script of `pid` has finished."""
        job = self._jobs[pid]
        await asyncio.wait_for(asyncio.shield(job), timeout)

    async def wait_all(self, timeout: float = 5.0) -> None:
        for pid, job in list(self._jobs.items()):
            if not job.done():
                await self.wait(pid, timeout)

    def kill(self, pid: int) -> None:
        """Make the process vanish without a trace (no run.ended)."""
        self._killed.add(pid)
        self._codes[pid] = -9
        self._alive.discard(pid)
        job = self._jobs.get(pid)
        if job is not None and not job.done():
            job.cancel()


# ---- the process form ------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sutra_app.orchestrator.testing.fake_engine", description="A fake engine process for tests.")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    path = os.environ.get("SUTRA_FAKE_SCRIPT") or str(run_dir / SCRIPT_FILE)
    try:
        steps = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        steps = standard_script()
    return asyncio.run(play(run_dir, steps, pid=os.getpid()))


if __name__ == "__main__":
    sys.exit(main())
