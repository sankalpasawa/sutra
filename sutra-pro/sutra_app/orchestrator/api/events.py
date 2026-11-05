"""`GET /api/events?after=&topics=&once=` : the server-sent event stream (orchestrator 6.3, D80).

Wire, one SSE frame per event: `event: <type>`, `data: <json>` (the event's `data` object only, compact ASCII JSON) and
`id: <seq>` (FastAPI writes the lines in that order; the order is free in SSE). The frames:

  1. `server.hello` {version, chart_version, graph_version}, always first, NO `id:` line.
  2. `server.resync` {reason: "restart"|"gap"} when the client's last id cannot be replayed (an id past the head comes from a
     previous launch; an id older than the 1000-event ring was forgotten), NO `id:` line. The client refetches what it shows.
  3. the retained events after the client's last id, in order (`id:` = seq), when it can be replayed.
  4. the live tail, until the client leaves or the bus is closed. FastAPI adds a `: ping` comment after 15 s of silence.

The client's last id is the `Last-Event-ID` header (the browser's own, sent on a reconnect) or `?after=`; the header wins when
both are present. A header that is not a whole number is ignored. `topics=chat,graph` keeps the events whose type starts with
one of those names before the dot; `server` always passes and `connector` is a topic. `once=1` replays and closes (with no last
id it replays the whole ring, as `after=0`): the form tests and polling scripts use. Reads are open on loopback, so no token.
Payloads go through the redactor like every other body.
"""
import json
import re
import sqlite3
from collections.abc import AsyncIterator
from typing import Any, NamedTuple

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from sutra_app.library.types import violation
from sutra_app.orchestrator.api.deps import services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError, validation_error
from sutra_app.orchestrator.events import CONTROL_TYPES, HELLO, RESYNC, EventBus, Replay, Subscription

__all__ = ["router", "build_router", "parse_topics", "parse_last_event_id", "hello_data", "MAX_TOPICS"]

MAX_TOPICS = 20
_TOPIC_RE = re.compile(r"[a-z][a-z_]{0,39}")
_ID_RE = re.compile(r"[0-9]{1,15}")


def parse_topics(raw: str | None) -> frozenset[str] | None:
    """`chat,graph` -> {chat, graph}; None or only blanks -> None (every topic). A name that is not lower-case letters and
    underscores, or more than 20 names, is 422 `validation`."""
    if raw is None:
        return None
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        return None
    bad = [n for n in names if not _TOPIC_RE.fullmatch(n)]
    if bad or len(set(names)) > MAX_TOPICS:
        what = "bad_topic" if bad else "too_many_topics"
        text = f"topics are lower-case names: {bad[0]!r}" if bad else f"at most {MAX_TOPICS} topics"
        raise validation_error([violation("topics", what, text)])
    return frozenset(names)


def parse_last_event_id(raw: str | None) -> int | None:
    """The `Last-Event-ID` header as a number; absent or not a whole number -> None (treated as a first connection)."""
    text = (raw or "").strip()
    return int(text) if _ID_RE.fullmatch(text) else None


def hello_data(services: Any) -> dict[str, Any]:
    """`{version, chart_version, graph_version}` read from the database (0 when the tables are not there yet)."""
    conn = services.db.conn()
    try:
        chart = int(conn.execute("SELECT COALESCE(MAX(revision), 0) FROM org_charts").fetchone()[0])
        row = conn.execute("SELECT value FROM meta WHERE key = 'graph_version'").fetchone()
        graph = int(row[0]) if row is not None else 0
    except (sqlite3.Error, ValueError):
        chart, graph = 0, 0
    return {"version": services.version, "chart_version": chart, "graph_version": graph}


def _frame(event_type: str, seq: int, data: dict[str, Any], scrub: Any) -> ServerSentEvent:
    body = scrub(data) if callable(scrub) else data
    return ServerSentEvent(event=event_type, id=None if event_type in CONTROL_TYPES else str(seq),
                           raw_data=json.dumps(body, separators=(",", ":")))


def _bus(request: Request) -> EventBus:
    bus = getattr(services_of(request), "bus", None)
    if bus is None:
        raise AppError("internal", "the event bus is not wired")
    return bus


def _topics(topics: str | None = Query(None, max_length=1000, description="comma-separated topics (the part of the event name before the dot); server always passes")) -> frozenset[str] | None:
    return parse_topics(topics)          # a dependency: a bad value is a 422 before the stream starts


class Tail(NamedTuple):
    """What a stream starts from: its registered subscription, what it missed, and whether to stop after the replay."""

    sub: Subscription
    replay: Replay
    once: bool


async def _tail(
    bus: EventBus = Depends(_bus),
    wanted: frozenset[str] | None = Depends(_topics),
    after: int | None = Query(None, ge=0, le=2**53 - 1, description="the last event id the client saw (the Last-Event-ID header wins)"),
    once: bool = Query(False, description="replay what is retained, then close"),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> AsyncIterator[Tail]:
    """Subscribe, atomically with the replay. A dependency with `yield` so the subscription is released when the request ends
    (the exit stack runs on a client disconnect too), not when the generator happens to be finalised: a stream suspended at a
    `yield` when the client leaves would otherwise keep its subscription until garbage collection."""
    seen = parse_last_event_id(last_event_id)
    if seen is None:
        seen = after
    if once and seen is None:
        seen = 0
    sub, replay = bus.subscribe(after=seen, topics=wanted)
    try:
        yield Tail(sub, replay, once)
    finally:
        sub.close()


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/events", tags=["events"])

    @router.get("", response_class=EventSourceResponse, summary="Server-sent events: invalidations to refetch")
    async def stream(request: Request, tail: Tail = Depends(_tail)):
        services = services_of(request)
        scrub = getattr(services.redact, "scrub", None)
        hello = await run_blocking(hello_data, services)
        yield _frame(HELLO, 0, hello, scrub)
        if tail.replay.resync is not None:
            yield _frame(RESYNC, 0, {"reason": tail.replay.resync}, scrub)
        for event in tail.replay.events:
            yield _frame(event.type, event.seq, event.data, scrub)
        if tail.once:
            return
        while True:
            event = await tail.sub.next()
            if event is None:
                return
            yield _frame(event.type, event.seq, event.data, scrub)

    return router


router = build_router()
