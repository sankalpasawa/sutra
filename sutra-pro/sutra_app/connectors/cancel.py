"""`CancelToken`: the single stop flag of one chat turn (streaming design D215).

A direct turn used to be stopped through three unrelated flags (`Router._chat_stop_early`, `Router._chat_active`, the connector's tracked process), and a Stop
that arrived between two of them was lost. One token now travels with the turn: `ChatPort.stream(cancel=)` -> `Router` -> `TurnPlan.cancel` ->
`ModelConnector._spawn`. Whoever asks for Stop calls `request()`; the process binds to the token the moment it is tracked, and a token that was
already requested cancels it at once, so no window between "turn registered" and "process tracked" can swallow a Stop.

The token knows nothing about HTTP, sessions or the bus. It is safe to use from any thread.
"""
from __future__ import annotations

import threading
from typing import Any

__all__ = ["CancelToken"]


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._bound: list[Any] = []

    # ---- asking for a stop ------------------------------------------------------------------------------------------------------
    def request(self) -> bool:
        """Mark the turn as stopped. True the first time, False when it was already requested. It never blocks: it does not run the cancel ladder
        (up to 12 s); `cancel_bound` does, and `bind` does for a process that arrives after the request."""
        with self._lock:
            first = not self._event.is_set()
            self._event.set()
        return first

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Sleep up to `timeout` seconds; True as soon as the token is requested (the back-off between two attempts uses this, so Stop ends it at once)."""
        return self._event.wait(timeout)

    # ---- the process ------------------------------------------------------------------------------------------------------------
    def bind(self, proc: Any) -> bool:
        """Called right after the process is tracked. When the token was requested before (or while) the process started, it is cancelled now.
        -> True when the process was cancelled by this call."""
        with self._lock:
            self._bound.append(proc)
            late = self._event.is_set()
        if late:
            return bool(self._cancel(proc))
        return False

    def unbind(self, proc: Any) -> None:
        with self._lock:
            self._bound = [p for p in self._bound if p is not proc]

    def cancel_bound(self) -> bool:
        """Run the cancel ladder on every bound process. Blocks until they are gone. True when one was still running."""
        with self._lock:
            procs = list(self._bound)
        found = False
        for proc in procs:
            found = bool(self._cancel(proc)) or found
        return found

    @staticmethod
    def _cancel(proc: Any) -> bool:
        try:
            return bool(proc.cancel())
        except Exception:                      # noqa: BLE001  a process that cannot be cancelled twice must not break the turn
            return False
