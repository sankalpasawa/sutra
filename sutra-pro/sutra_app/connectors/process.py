"""Run one CLI child: its own process group, a stdin writer, a line reader, deadlines and the cancel ladder (CD2, D27).

    runner = ProcessRunner()
    with runner.start(Command(argv=[...], cwd=dir, env=child_env("claude"), stdin_text=prompt), timeout_s=900,
                      idle_timeout_s=120) as proc:
        for line in proc.lines():            # stdout, one str per line, decoded as UTF-8 with replacement; noise passes
            parser.feed(line)
        info = proc.wait()                   # ExitInfo: returncode, reason, stderr_tail, ladder, seconds
    # or: info = runner.run(cmd, on_line=parser.feed, timeout_s=...)

The runner never raises for a bad exit; `ExitInfo.reason` says why the child ended (`exit`, `total_timeout`,
`idle_timeout` or `cancelled`) and the connector's parser turns that into an error. It raises only when the child cannot
be started (`CliMissingError`, `InvalidRequestError` for a missing working directory, `ProviderError` for any other
OSError).

Facts that bite (probed 2026-11-04, connectors design row 9):
- The child is a session leader (`start_new_session`), so one `killpg` reaches the CLI and its MCP children. After the
  child has ended, whatever is left in its group is killed with SIGKILL: no orphans.
- The cancel ladder is SIGINT (5 s), SIGTERM (5 s), SIGKILL (2 s): Claude exited in 1.3 s on SIGINT and 2.9 s on SIGTERM.
  The ladder stops at the first signal the child obeys; `ExitInfo.ladder` lists the signals that were sent.
- stdin is written by its own thread and stderr is drained by another, so a 1 MB prompt cannot deadlock against a child
  that writes before it has read everything; only the last 8 KB of stderr are kept.
- The environment is EXACTLY `Command.env`: nothing is inherited. POSIX only (Windows needs CREATE_NEW_PROCESS_GROUP).
"""
from __future__ import annotations

import os
import queue
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Literal, Mapping, Optional, Sequence

from .errors import CliMissingError, InvalidRequestError, ProviderError

__all__ = ["Command", "ExitInfo", "ProcessRunner", "RunningProcess", "LADDER", "STDERR_TAIL_BYTES", "MAX_LINE_BYTES"]

LADDER: tuple[tuple[int, float], ...] = ((signal.SIGINT, 5.0), (signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0))
STDERR_TAIL_BYTES = 8192
MAX_LINE_BYTES = 8 * 1024 * 1024       # a longer stdout line is cut here (the rest of it is dropped)
READER_GRACE_S = 2.0                   # after the child ended, wait this long for stdout to close (a stray grandchild)
_POLL_S = 0.02
_CHUNK = 65536

Reason = Literal["exit", "total_timeout", "idle_timeout", "cancelled"]
_EOF = object()


@dataclass(frozen=True)
class Command:
    """What to run. `env` is the whole environment of the child; `stdin_text` is written and closed (None: no stdin);
    `cleanup` are files or folders removed when the child is done, whatever happened (prompt, schema and MCP files)."""

    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str] = field(default_factory=dict)
    stdin_text: Optional[str] = None
    cleanup: tuple[str, ...] = ()
    provider: Optional[str] = None         # names the CLI in a start error

    def __post_init__(self) -> None:
        argv = tuple(self.argv)
        if not argv or not all(isinstance(a, str) and "\0" not in a for a in argv) or not argv[0]:
            raise InvalidRequestError("a command needs a non-empty argv of strings", provider=self.provider)
        env = dict(self.env)
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise InvalidRequestError("a command's environment must map strings to strings", provider=self.provider)
        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "cwd", str(self.cwd))
        object.__setattr__(self, "env", env)
        object.__setattr__(self, "cleanup", tuple(str(p) for p in self.cleanup))


@dataclass(frozen=True)
class ExitInfo:
    """How a child ended. `returncode` is negative when a signal ended it (Popen's convention)."""

    returncode: Optional[int]
    reason: Reason
    stderr_tail: str
    seconds: float
    pid: int
    ladder: tuple[str, ...] = ()           # the signals sent by the cancel ladder, in order
    stderr_bytes: int = 0                  # everything the child wrote to stderr, not only the tail

    @property
    def signal_name(self) -> Optional[str]:
        if self.returncode is not None and self.returncode < 0:
            try:
                return signal.Signals(-self.returncode).name
            except ValueError:
                return f"SIG{-self.returncode}"
        return None

    @property
    def ok(self) -> bool:
        return self.reason == "exit" and self.returncode == 0


class RunningProcess:
    """One started child. Created by `ProcessRunner.start`; `cancel()` may be called from any thread."""

    def __init__(self, runner: "ProcessRunner", cmd: Command, popen: subprocess.Popen, timeout_s: Optional[float],
                 idle_timeout_s: Optional[float]) -> None:
        self._runner = runner
        self._cmd = cmd
        self._popen = popen
        self._clock = runner._clock
        self.pid = popen.pid
        self._started = self._clock()
        self._total_deadline = None if timeout_s is None else self._started + timeout_s
        self._idle_s = idle_timeout_s
        self._last_activity = self._started
        self._q: "queue.Queue[object]" = queue.Queue()
        self._stderr = bytearray()
        self._stderr_bytes = 0
        self._reason: Optional[Reason] = None
        self._sent: list[str] = []
        self._ladder_lock = threading.Lock()
        self._finished = threading.Event()
        self._out_done = threading.Event()
        self._abandoned = False
        self._info: Optional[ExitInfo] = None
        self._threads = {
            "in": threading.Thread(target=self._pump_in, name=f"proc-{self.pid}-in", daemon=True),
            "err": threading.Thread(target=self._pump_err, name=f"proc-{self.pid}-err", daemon=True),
            "out": threading.Thread(target=self._pump_out, name=f"proc-{self.pid}-out", daemon=True),
            "watch": threading.Thread(target=self._watch, name=f"proc-{self.pid}-watch", daemon=True),
        }
        for t in self._threads.values():
            t.start()

    # ---- the three pipes -------------------------------------------------------------------------------------------
    def _pump_in(self) -> None:
        pipe = self._popen.stdin
        if pipe is None:
            return
        try:
            view = memoryview((self._cmd.stdin_text or "").encode("utf-8"))
            while len(view):
                written = pipe.write(view[:_CHUNK])
                view = view[written or 0:]
        except (BrokenPipeError, OSError, ValueError):
            pass                                  # the child closed its stdin early: that is its right
        finally:
            try:
                pipe.close()
            except (BrokenPipeError, OSError):
                pass

    def _pump_err(self) -> None:
        pipe = self._popen.stderr
        try:
            while True:
                chunk = pipe.read(_CHUNK)
                if not chunk:
                    break
                self._stderr_bytes += len(chunk)
                self._stderr += chunk
                if len(self._stderr) > STDERR_TAIL_BYTES:
                    del self._stderr[:len(self._stderr) - STDERR_TAIL_BYTES]
        except (OSError, ValueError):
            pass
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    def _emit(self, raw: bytes) -> None:
        if self._abandoned:
            return
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        self._last_activity = self._clock()
        self._q.put(raw.decode("utf-8", errors="replace"))

    def _pump_out(self) -> None:
        pipe = self._popen.stdout
        buf = bytearray()
        skipping = False                          # inside a line that was cut at MAX_LINE_BYTES
        try:
            while True:
                chunk = pipe.read(_CHUNK)
                if not chunk:
                    break
                start = 0
                while True:
                    nl = chunk.find(b"\n", start)
                    if not skipping:
                        buf += chunk[start:] if nl < 0 else chunk[start:nl]
                        if len(buf) > MAX_LINE_BYTES:
                            self._emit(bytes(buf[:MAX_LINE_BYTES]))
                            buf.clear()
                            skipping = True
                    if nl < 0:
                        break
                    if skipping:
                        skipping = False          # the cut line ends here; its first part went out already
                    else:
                        self._emit(bytes(buf))
                        buf.clear()
                    start = nl + 1
            if buf and not skipping:
                self._emit(bytes(buf))
        except (OSError, ValueError):
            pass
        finally:
            try:
                pipe.close()
            except OSError:
                pass
            self._out_done.set()
            self._q.put(_EOF)

    # ---- end of life -----------------------------------------------------------------------------------------------
    def _signal_group(self, sig: int) -> None:
        try:
            os.killpg(self.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _terminate(self, reason: Reason) -> bool:
        """The cancel ladder. True when this call found the child still running."""
        with self._ladder_lock:
            if self._popen.poll() is not None:
                return False
            if self._reason is None:
                self._reason = reason
            for sig, wait_s in self._runner._ladder:
                self._signal_group(sig)
                self._sent.append(signal.Signals(sig).name)
                try:
                    self._popen.wait(timeout=wait_s)
                    break
                except subprocess.TimeoutExpired:
                    continue
            return True

    def _watch(self) -> None:
        try:
            while True:
                try:
                    self._popen.wait(timeout=_POLL_S)
                    break
                except subprocess.TimeoutExpired:
                    pass
                now = self._clock()
                if self._total_deadline is not None and now >= self._total_deadline:
                    self._terminate("total_timeout")
                elif self._idle_s is not None and now - self._last_activity >= self._idle_s:
                    self._terminate("idle_timeout")
            self._signal_group(signal.SIGKILL)            # whatever the child left in its group dies with it
            if not self._out_done.wait(READER_GRACE_S):   # a grandchild outside the group still holds stdout
                self._abandoned = True
                self._q.put(_EOF)
            for key in ("in", "err"):
                self._threads[key].join(1.0)
        finally:
            self._finish()

    def _finish(self) -> None:
        returncode = self._popen.poll()
        self._info = ExitInfo(
            returncode=returncode, reason=self._reason or "exit",
            stderr_tail=bytes(self._stderr).decode("utf-8", errors="replace"),
            seconds=max(0.0, self._clock() - self._started), pid=self.pid, ladder=tuple(self._sent),
            stderr_bytes=self._stderr_bytes)
        for path in self._cmd.cleanup:
            _remove(path)
        self._runner._forget(self)
        self._finished.set()

    # ---- the caller's side -----------------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return not self._finished.is_set()

    def lines(self) -> Iterator[str]:
        """Stdout, one line at a time, until the child has ended and its output is drained."""
        while True:
            item = self._q.get()
            if item is _EOF:
                return
            yield item  # type: ignore[misc]

    def wait(self) -> ExitInfo:
        self._finished.wait()
        assert self._info is not None
        return self._info

    def cancel(self, reason: Reason = "cancelled") -> bool:
        """Run the ladder (up to 12 s) and return True when the child was still running; False when it had ended."""
        was_running = self._popen.poll() is None
        self._terminate(reason)
        return was_running

    def __enter__(self) -> "RunningProcess":
        return self

    def __exit__(self, *exc: object) -> None:
        if self.running:
            self.cancel()
        self.wait()


def _remove(path: str) -> None:
    try:
        p = Path(path)
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    except OSError:
        pass


class ProcessRunner:
    """Starts children and remembers the live ones, so `stop_all()` (Router.close) can end every one of them."""

    def __init__(self, *, ladder: Sequence[tuple[int, float]] = LADDER, clock: Callable[[], float] = time.monotonic) -> None:
        if not ladder:
            raise ValueError("the cancel ladder needs at least one signal")
        self._ladder = tuple(ladder)
        self._clock = clock
        self._live: set[RunningProcess] = set()
        self._lock = threading.Lock()

    def start(self, cmd: Command, *, timeout_s: Optional[float] = None, idle_timeout_s: Optional[float] = None) -> RunningProcess:
        for name, value in (("timeout_s", timeout_s), ("idle_timeout_s", idle_timeout_s)):
            if value is not None and not value > 0:
                raise InvalidRequestError(f"{name} must be positive", provider=cmd.provider)
        if not Path(cmd.cwd).is_dir():
            _cleanup(cmd)
            raise InvalidRequestError(f"the working directory does not exist: {cmd.cwd}", provider=cmd.provider)
        try:
            popen = subprocess.Popen(
                list(cmd.argv), cwd=cmd.cwd, env=dict(cmd.env), bufsize=0, close_fds=True, start_new_session=True,
                stdin=subprocess.PIPE if cmd.stdin_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as e:
            _cleanup(cmd)
            raise CliMissingError(f"{cmd.argv[0]} was not found", provider=cmd.provider, detail={"cli": cmd.argv[0]}) from e
        except OSError as e:
            _cleanup(cmd)
            raise ProviderError(f"{cmd.argv[0]} could not be started: {e.strerror or e}", provider=cmd.provider,
                                detail={"cli": cmd.argv[0]}) from e
        proc = RunningProcess(self, cmd, popen, timeout_s, idle_timeout_s)
        with self._lock:
            self._live.add(proc)
        return proc

    def run(self, cmd: Command, *, on_line: Optional[Callable[[str], None]] = None, timeout_s: Optional[float] = None,
            idle_timeout_s: Optional[float] = None) -> ExitInfo:
        """Start, feed every stdout line to `on_line`, wait. An exception from `on_line` cancels the child first."""
        with self.start(cmd, timeout_s=timeout_s, idle_timeout_s=idle_timeout_s) as proc:
            for line in proc.lines():
                if on_line is not None:
                    on_line(line)
            return proc.wait()

    def live(self) -> list[RunningProcess]:
        with self._lock:
            return list(self._live)

    def stop_all(self) -> int:
        """Cancel every live child (ladders run side by side); returns how many were still running."""
        procs = self.live()
        results: list[bool] = []
        threads = [threading.Thread(target=lambda p=p: results.append(p.cancel()), daemon=True) for p in procs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for p in procs:
            p.wait()
        return sum(1 for r in results if r)

    def _forget(self, proc: RunningProcess) -> None:
        with self._lock:
            self._live.discard(proc)


def _cleanup(cmd: Command) -> None:
    for path in cmd.cleanup:
        _remove(path)
