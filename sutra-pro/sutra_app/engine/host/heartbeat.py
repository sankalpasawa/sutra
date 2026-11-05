"""The heartbeat thread (engine design 4.5, S1-contracts-16).

A daemon thread writes `{"t":"heartbeat"}` every `SUTRA_HEARTBEAT_S` seconds (default 5), the first one right after
`run.started`, also while the run thread is blocked in a model call. It proves the process lives, not that the run
progresses. It stops by itself when `run.ended` was written or the writer is closed.
"""
import os
import threading
from collections.abc import Mapping
from typing import Optional

from ..events import EventError, EventWriter, heartbeat_event

__all__ = ["Heartbeat", "heartbeat_interval", "DEFAULT_INTERVAL_S"]

DEFAULT_INTERVAL_S = 5.0


def heartbeat_interval(environ: Optional[Mapping[str, str]] = None) -> float:
    """`SUTRA_HEARTBEAT_S` as seconds; a missing, bad or non-positive value is the default of 5."""
    env = os.environ if environ is None else environ
    try:
        seconds = float(env.get("SUTRA_HEARTBEAT_S", ""))
    except ValueError:
        return DEFAULT_INTERVAL_S
    return seconds if 0 < seconds < float("inf") else DEFAULT_INTERVAL_S


class Heartbeat:
    NAME = "sutra-heartbeat"

    def __init__(self, writer: EventWriter, interval: float = DEFAULT_INTERVAL_S):
        if not interval > 0:
            raise ValueError("the heartbeat interval must be greater than 0")
        self.writer = writer
        self.interval = float(interval)
        self.beats = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("the heartbeat was started already")
        self._thread = threading.Thread(target=self._run, name=self.NAME, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.writer.emit(heartbeat_event())
            except (EventError, OSError):         # run.ended was written, or the writer was closed: nothing more to prove
                return
            self.beats += 1
            if self._stop.wait(self.interval):
                return
