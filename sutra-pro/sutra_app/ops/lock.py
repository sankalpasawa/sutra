"""One server per data folder (D94, gaps G08).

    lock = InstanceLock(data_dir, version="0.1.0")
    if lock.acquire():           # flock(LOCK_EX | LOCK_NB) on <data>/app.lock; app.pid now names this process
        lock.update(port=8780)   # once the port is bound
        ...                      # serve
        lock.release()
    else:
        holder = lock.holder()   # who has it: Holder(pid, port, started, version) -- or None for an instant while it starts

`<data>/app.pid` is the file the macOS launcher already keeps. Its first line is `"<pid> <port>"`, which the launcher's own check
(`read -r pid port`) understands; a JSON line `{pid, port, started, version}` follows. The launcher rewrites the file with only the first line
once the server is healthy (its own pid then), so a reader accepts both shapes. The LOCK, not the file, says whether a server is
running: a pid file without a held lock is stale and is replaced by the next server. The kernel drops the lock when the process
ends, however it ends. The lock itself is `oslayer.try_lock` (`flock` on POSIX, `msvcrt.locking` on Windows).

A stop can also be asked for with a file: `request_stop(data_dir)` creates `<data>/app.stop`, which the running server polls and answers
by shutting down the way a SIGTERM does. It is how `sutra-pro stop` reaches a server on Windows, where a process with no console
cannot be signalled. `stop_requested` and `clear_stop` are the server's side of it.
"""
import contextlib
import json
import os
from sutra_app import oslayer
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["InstanceLock", "Holder", "LOCK_NAME", "PID_NAME", "STOP_NAME", "read_holder", "is_locked", "pid_alive", "request_stop",
           "stop_requested", "clear_stop"]

LOCK_NAME = "app.lock"
PID_NAME = "app.pid"
STOP_NAME = "app.stop"
HOLDER_WAIT_S = 1.0          # a loser waits this long for the winner to write the pid file (it takes microseconds)


@dataclass(frozen=True)
class Holder:
    """What `app.pid` says about the running server. `port` is None until the server has bound one."""

    pid: int
    port: int | None = None
    started: float | None = None
    version: str | None = None

    @property
    def url(self) -> str | None:
        return f"http://127.0.0.1:{self.port}/" if self.port else None


def pid_alive(pid: int) -> bool:
    return oslayer.pid_alive(pid)


def request_stop(data_dir: str | os.PathLike[str]) -> Path:
    """Ask the server of this data folder to stop: create `<data>/app.stop`. The server removes it when it has seen it."""
    path = Path(data_dir) / STOP_NAME
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    return path


def stop_requested(data_dir: str | os.PathLike[str]) -> bool:
    return (Path(data_dir) / STOP_NAME).exists()


def clear_stop(data_dir: str | os.PathLike[str]) -> None:
    """Remove a stop request (the server does it at start, so a leftover from a crash never stops the next server)."""
    with contextlib.suppress(OSError):
        (Path(data_dir) / STOP_NAME).unlink()


def read_holder(data_dir: str | os.PathLike[str]) -> Holder | None:
    """The pid file as a `Holder`, or None when it is missing or unreadable. A launcher-style file (one line) and ours (two) both work."""
    try:
        text = (Path(data_dir) / PID_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    lines = text.splitlines()
    if not lines:
        return None
    words = lines[0].split()
    try:
        pid = int(words[0])
        port = int(words[1]) if len(words) > 1 else 0
    except (ValueError, IndexError):
        return None
    if pid <= 0:
        return None
    extra: dict[str, Any] = {}
    if len(lines) > 1:
        try:
            parsed = json.loads("\n".join(lines[1:]))
            extra = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            extra = {}
    started = extra.get("started")
    version = extra.get("version")
    return Holder(pid=pid, port=port if 0 < port < 65536 else None,
                  started=float(started) if isinstance(started, (int, float)) and not isinstance(started, bool) else None,
                  version=version if isinstance(version, str) else None)


def is_locked(data_dir: str | os.PathLike[str]) -> bool:
    """True while some process holds the instance lock of this folder. Takes and drops the lock to find out, so call it only to look."""
    path = Path(data_dir) / LOCK_NAME
    try:
        fd = os.open(path, os.O_RDWR | oslayer.O_BINARY)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    try:
        if not oslayer.try_lock(fd):
            return True
        oslayer.unlock(fd)
        return False
    finally:
        os.close(fd)


class InstanceLock:
    """The lock of one data folder. Not re-entrant: a second `InstanceLock` on the same folder (even in this process) does not get it."""

    def __init__(self, data_dir: str | os.PathLike[str], *, version: str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.version = version
        self._fd: int | None = None
        self._started: float | None = None
        self._port: int | None = None

    @property
    def lock_path(self) -> Path:
        return self.data_dir / LOCK_NAME

    @property
    def pid_path(self) -> Path:
        return self.data_dir / PID_NAME

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> bool:
        """Take the lock and write the pid file. False when another process (or another `InstanceLock`) holds it."""
        if self._fd is not None:
            return True
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
        if not oslayer.try_lock(fd):
            os.close(fd)
            return False
        self._fd = fd
        self._started = time.time()
        self._write(port=None)
        return True

    def update(self, port: int) -> None:
        """Record the port the server bound (the pid file is rewritten in one rename)."""
        if self._fd is None:
            raise RuntimeError("the instance lock is not held")
        self._write(port=port)

    def release(self) -> None:
        """Drop the lock. The pid file is removed only when it still names this process (the launcher may have rewritten it)."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        holder = read_holder(self.data_dir)
        if holder is not None and holder.pid == os.getpid():
            with contextlib.suppress(OSError):
                self.pid_path.unlink()
        oslayer.unlock(fd)
        os.close(fd)

    def holder(self, *, wait: float = HOLDER_WAIT_S) -> Holder | None:
        """Who holds the lock, from the pid file. Right after the winner took the lock the file may not be there yet, so this
        waits up to `wait` seconds for it."""
        deadline = time.monotonic() + wait
        while True:
            found = read_holder(self.data_dir)
            if found is not None or time.monotonic() >= deadline:
                return found
            time.sleep(0.02)

    def __enter__(self) -> "InstanceLock":
        if not self.acquire():
            raise RuntimeError("another Sutra Pro holds this data folder")
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def _write(self, *, port: int | None) -> None:
        self._port = port
        body = f"{os.getpid()} {port or 0}\n" + json.dumps(
            {"pid": os.getpid(), "port": port, "started": self._started, "version": self.version}) + "\n"
        tmp = self.pid_path.with_name(f"{PID_NAME}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, body.encode("utf-8"))
        finally:
            os.close(fd)
        oslayer.replace(tmp, self.pid_path)
