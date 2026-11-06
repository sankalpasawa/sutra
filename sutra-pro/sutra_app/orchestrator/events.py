"""The event bus: a numbered ring of the last events and a live tail for every open SSE stream (orchestrator 6.3, D80).

    bus = EventBus()
    Database(path, bus.publish)                          # each committed transaction's events, seq 0, in order
    connector router events=lambda t, d: bus.publish_one(t, d)
    sub, replay = bus.subscribe(after=41, topics={"chat"})      # inside the event loop that serves the stream
    event = await sub.next()                             # the next live event, None once the bus is closed

* `publish(events)` and `publish_one(type, data)` are thread-safe: the database commits on worker threads and the connector
  router calls from its own. A lock numbers the events and appends them to the ring in one step (so ring order is seq
  order); each subscriber's queue is fed with `loop.call_soon_threadsafe`, so a subscriber sees the events in seq order.
* `seq` is process-local and starts at 1 at each launch. The ring keeps the last `RING_SIZE` (1000) events.
* `server.hello`, `server.resync` and `chat.partial` are CONTROL events [S3-web-06]: they are broadcast to the open streams only, get no
  `seq` (0) and never enter the ring, so a client's last event id always names a real event. The reconciler publishes
  `server.resync {reason:'restart'}` this way; a stream that falls too far behind is given `server.resync {reason:'gap'}`.
* `replay(after, topics)` / `subscribe(after=...)` give the events a client missed: nothing for a first connection (`after`
  None); `restart` when `after` is past the head (the id comes from a previous launch); `gap` when it is older than the ring;
  otherwise the retained events after it. `subscribe` takes the snapshot and registers the stream under one lock, so an event
  is never replayed twice nor lost between the replay and the live tail.
* `topics` narrows by the part of the type before the dot; `server` always passes.
* Best effort by design: events are invalidations, the page refetches. `publish` and `publish_one` never raise into a caller
  that already committed or is in the middle of a model call; an invalid event is logged and dropped.
"""
import asyncio
import collections
import copy
import logging
import re
import threading
from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple

from pydantic import ValidationError

from sutra_app.orchestrator.ids import Clock, SystemClock, iso_z
from sutra_app.orchestrator.models import Event

__all__ = [
    "RING_SIZE", "MAX_PENDING", "CONTROL_TYPES", "HELLO", "RESYNC", "PARTIAL", "EventBus", "Subscription", "Replay", "topic_of",
    "topic_matches", "event_type_ok",
]

log = logging.getLogger(__name__)
RING_SIZE = 1000                   # events kept for replay
MAX_PENDING = 2000                 # events a slow stream may hold before it is told to resync (gap)
HELLO = "server.hello"
RESYNC = "server.resync"
PARTIAL = "chat.partial"           # a streamed piece of a chat reply: shown, never stored, never replayed (ABS-7)
CONTROL_TYPES = (HELLO, RESYNC, PARTIAL)
_TYPE_RE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")
_GAP_EVENT = Event(seq=0, at="1970-01-01T00:00:00Z", type=RESYNC, data={"reason": "gap"})


def event_type_ok(type: object) -> bool:
    """A lower-case dotted name of at most 60 characters (it becomes the SSE `event:` line, which must be one line)."""
    return isinstance(type, str) and len(type) <= 60 and _TYPE_RE.fullmatch(type) is not None


def topic_of(type: str) -> str:
    """`chat.message` -> `chat`; a type without a dot is its own topic."""
    return type.split(".", 1)[0]


def topic_matches(topics: Iterable[str] | None, type: str) -> bool:
    """None means every topic. `server` always passes."""
    if topics is None:
        return True
    topic = topic_of(type)
    return topic == "server" or topic in topics


class Replay(NamedTuple):
    """What a client that last saw id `after` has missed. `resync` is None, `restart` or `gap`; then `events` is empty."""

    events: tuple[Event, ...]
    resync: str | None


class Subscription:
    """One open stream's queue. Create it with `EventBus.subscribe` inside the loop that serves the stream."""

    def __init__(self, bus: "EventBus", loop: asyncio.AbstractEventLoop, topics: frozenset[str] | None, max_pending: int) -> None:
        self._bus = bus
        self.loop = loop
        self.topics = topics
        self._max = max_pending
        self._queue: collections.deque[Event | None] = collections.deque()
        self._ready = asyncio.Event()
        self._overflow = False

    def wants(self, type: str) -> bool:
        return topic_matches(self.topics, type)

    def _push(self, event: Event | None) -> None:            # runs in the stream's loop
        if event is None:
            self._queue.append(None)
        elif self._overflow:
            return                                           # the gap marker is still queued: the client refetches anyway
        elif len(self._queue) >= self._max:
            self._queue.clear()
            self._queue.append(_GAP_EVENT)
            self._overflow = True
        else:
            self._queue.append(event)
        self._ready.set()

    async def next(self) -> Event | None:
        """The next live event; None once the bus is closed (and after that, always None)."""
        while not self._queue:
            self._ready.clear()
            await self._ready.wait()
        item = self._queue[0]
        if item is None:
            return None
        self._queue.popleft()
        if item is _GAP_EVENT:
            self._overflow = False
        return item

    def close(self) -> None:
        """Stop receiving (safe from any thread, safe twice)."""
        self._bus.unsubscribe(self)


class EventBus:
    def __init__(self, *, clock: Clock | None = None, ring_size: int = RING_SIZE, max_pending: int = MAX_PENDING) -> None:
        if ring_size < 1 or max_pending < 1:
            raise ValueError("ring_size and max_pending must be at least 1")
        self._clock = clock or SystemClock()
        self._ring: collections.deque[Event] = collections.deque(maxlen=ring_size)
        self._max_pending = max_pending
        self._subs: list[Subscription] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._closed = False

    # ---- publishing -----------------------------------------------------------------------------------------

    @property
    def head(self) -> int:
        """The newest `seq` (0 before the first event)."""
        return self._seq

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, events: Sequence[Event]) -> list[Event]:
        """Number and deliver `events` (the database's committed batch, `seq` 0), in order, as one step. Returns them as
        numbered (control events keep seq 0). An event with a bad type is logged and left out."""
        good: list[Event] = []
        for event in events:
            if event_type_ok(event.type):
                good.append(event)
            else:
                log.error("event bus: dropped an event with the invalid type %r", event.type)
        out: list[Event] = []
        with self._lock:
            for event in good:
                out.append(self._deliver(event))
        return out

    def publish_one(self, type: str, data: dict[str, Any] | None = None) -> Event | None:
        """Build an event (`at` from the clock) and publish it. The connector router's `events=` callback. An invalid type or
        non-JSON data is logged and returns None: a health event must never break a model call."""
        try:
            event = Event(seq=0, at=iso_z(self._clock.now()), type=type, data=copy.deepcopy(data or {}))
        except (ValidationError, TypeError, ValueError):
            log.exception("event bus: dropped %r (its data is not a JSON object)", type)
            return None
        if not event_type_ok(type):
            log.error("event bus: dropped an event with the invalid type %r", type)
            return None
        with self._lock:
            return self._deliver(event)

    def _deliver(self, event: Event) -> Event:                # the lock is held
        if event.type in CONTROL_TYPES:
            numbered = event if event.seq == 0 else event.model_copy(update={"seq": 0})
        else:
            self._seq += 1
            numbered = event.model_copy(update={"seq": self._seq})
            self._ring.append(numbered)
        for sub in list(self._subs):
            if not sub.wants(numbered.type):
                continue
            try:
                sub.loop.call_soon_threadsafe(sub._push, numbered)
            except RuntimeError:                              # its loop is closed: the stream is gone
                self._subs.remove(sub)
        return numbered

    # ---- reading ----------------------------------------------------------------------------------------------

    def _replay_locked(self, after: int | None, topics: Iterable[str] | None) -> Replay:
        if after is None:
            return Replay((), None)
        if after > self._seq:
            return Replay((), "restart")
        if self._ring and after < self._ring[0].seq - 1:
            return Replay((), "gap")
        return Replay(tuple(e for e in self._ring if e.seq > after and topic_matches(topics, e.type)), None)

    def replay(self, after: int | None, topics: Iterable[str] | None = None) -> Replay:
        """The events after id `after` that are still in the ring (see the module text). No stream is registered."""
        with self._lock:
            return self._replay_locked(after, topics)

    def subscribe(self, *, after: int | None = None, topics: Iterable[str] | None = None,
                  loop: asyncio.AbstractEventLoop | None = None) -> tuple[Subscription, Replay]:
        """Register a live stream and return what it missed, atomically. Call it inside the loop that serves the stream."""
        wanted = None if topics is None else frozenset(topics)
        sub = Subscription(self, loop or asyncio.get_running_loop(), wanted, self._max_pending)
        with self._lock:
            replay = self._replay_locked(after, wanted)
            if self._closed:
                sub.loop.call_soon_threadsafe(sub._push, None)
            else:
                self._subs.append(sub)
        return sub, replay

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def close(self) -> None:
        """End every open stream (app shutdown: uvicorn waits for them). Later subscriptions end at once. Events can still
        be published; nobody receives them."""
        with self._lock:
            self._closed = True
            subs, self._subs = self._subs, []
        for sub in subs:
            try:
                sub.loop.call_soon_threadsafe(sub._push, None)
            except RuntimeError:
                pass

