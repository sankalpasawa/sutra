"""Machine-wide provider slots (multi-agent nodes, MAN-12; SUTRA_NODES_SLOTS): how many model programs run at once is limited for the whole computer, not for each process.

    pool = SlotPool(<data>/connectors/slots, {"claude": 4, "codex": 2})
    slot = pool.acquire("claude", timeout=120, cancelled=event.is_set)      # waits for a free slot; None when the wait ran out or was cancelled
    ...                                                                      # run the program
    pool.release(slot)

A slot is a small file whose lock (`flock`, or `msvcrt.locking` on Windows, through `oslayer.try_lock`) one process holds while it runs a program. The kernel frees the lock when the process dies, so a
crashed engine never keeps a slot. The router's own per-process semaphore stays as it is (it is taken first); this adds the cross-process limit on top. The files hold nothing and are never read.
"""
from __future__ import annotations

import os
import random
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from sutra_app import oslayer

__all__ = ["SlotPool", "Slot"]

POLL_S = 0.05


@dataclass(frozen=True)
class Slot:
    provider: str
    index: int
    fd: int


class SlotPool:
    def __init__(self, directory: str | os.PathLike[str], limits: Mapping[str, int], *, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self.directory = Path(directory)
        self.limits = {name: max(1, int(n)) for name, n in limits.items()}
        self._clock, self._sleep = clock, sleep
        self._queues: dict[str, deque] = {}                    # the waiters of THIS process, first come first served (PB-14)
        self._guard = threading.Lock()

    def _try(self, provider: str) -> Slot | None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        for index in range(self.limits.get(provider, 1)):
            fd = os.open(self.directory / f"{provider}.{index}.lock", os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
            if oslayer.try_lock(fd):
                return Slot(provider, index, fd)
            os.close(fd)
        return None

    def acquire(self, provider: str, *, timeout: float = 120.0, cancelled: Callable[[], bool] = lambda: False) -> Slot | None:
        """A free slot of `provider`, waiting up to `timeout` seconds (a stop ends the wait). None when none came. Fairness (PB-14): the waiters of one process are served in the order they came; between
        processes there is no queue (a file lock has none), so each waiter looks again after a random short pause, which keeps any one of them from being passed over for long. A call that waits
        past its timeout is not a call: it never started a program."""
        end = self._clock() + timeout
        ticket = object()
        with self._guard:
            self._queues.setdefault(provider, deque()).append(ticket)
        try:
            while True:
                with self._guard:
                    first = self._queues[provider][0] is ticket
                if first:
                    found = self._try(provider)
                    if found is not None:
                        return found
                if cancelled() or self._clock() >= end:
                    return None
                self._sleep(POLL_S * (0.5 + random.random()))
        finally:
            with self._guard:
                self._queues[provider].remove(ticket)

    def release(self, slot: Slot | None) -> None:
        if slot is None:
            return
        oslayer.unlock(slot.fd)
        try:
            os.close(slot.fd)
        except OSError:
            pass

    def in_use(self, provider: str) -> int:
        """How many slots of `provider` are held right now (by any process): a look, for tests and the doctor."""
        held = 0
        for index in range(self.limits.get(provider, 1)):
            path = self.directory / f"{provider}.{index}.lock"
            if not path.exists():
                continue
            fd = os.open(path, os.O_RDWR | oslayer.O_BINARY)
            try:
                if oslayer.try_lock(fd):
                    oslayer.unlock(fd)
                else:
                    held += 1
            finally:
                os.close(fd)
        return held
