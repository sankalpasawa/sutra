"""Test doubles that every orchestrator test shares: `FakeClock`, `FakeIds`, `EventCollector`.

They live in the package so imports are stable (`from sutra_app.orchestrator.testing import FakeClock`). Later packages add
`fake_engine` (FakeLauncher) and `scripted` (ScriptedConnector) next to this file.
"""
import itertools

from sutra_app.orchestrator.ids import IdFactory
from sutra_app.orchestrator.models import Event

__all__ = ["FakeClock", "FakeIds", "EventCollector"]


class FakeClock:
    """Time that only moves when asked: every `now()` / `time()` call returns the next second (`step`, default 1)."""

    def __init__(self, start: int = 1_793_786_400, step: int = 1) -> None:       # 2026-11-04 10:00:00 UTC
        self._value = start
        self._step = step

    def now(self) -> int:
        value = self._value
        self._value += self._step
        return value

    def time(self) -> float:
        return float(self.now())

    def advance(self, seconds: int) -> None:
        self._value += seconds

    @property
    def peek(self) -> int:
        """The next value, without consuming it."""
        return self._value


class FakeIds(IdFactory):
    """Predictable ids: tsk_000000000001, cs_000000000001, ... and run ids from the fake clock with counted suffixes."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self._counter = itertools.count(1)
        super().__init__(clock or FakeClock(), token_hex=self._hex_counter)

    def _hex_counter(self, nbytes: int) -> str:
        return f"{next(self._counter):0{2 * nbytes}x}"[-2 * nbytes:]


class EventCollector:
    """A `publish` callable that keeps what it is given: `events` (flat, in order) and `batches` (one list per commit)."""

    def __init__(self) -> None:
        self.batches: list[list[Event]] = []

    def __call__(self, events: list[Event]) -> None:
        self.batches.append(list(events))

    @property
    def events(self) -> list[Event]:
        return [event for batch in self.batches for event in batch]

    def types(self) -> list[str]:
        return [event.type for event in self.events]
