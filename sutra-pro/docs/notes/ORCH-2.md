# ORCH-2 as built: event bus and the SSE route

Built: `orchestrator/events.py` (`EventBus`, `Subscription`, `Replay`, helpers) and `orchestrator/api/events.py` (`GET /api/events`, `build_router()`).
Tests: `test_events_bus.py` (15) and `test_events_sse.py` (16), about 2 s together, no browser, three live-server cases on a uvicorn thread.

## What it does
- `EventBus.publish(list[Event])` is the `Database(publish=...)` hook; `publish_one(type, data)` is the connector router's `events=` callback. Both are
  thread-safe: one lock numbers the events (seq from 1) and appends to the ring (1000) in one step; each open stream gets its events through
  `loop.call_soon_threadsafe`, so a stream sees them in seq order and a publisher's own order is kept.
- `subscribe(after, topics)` returns the stream's queue and what it missed in ONE locked step: nothing lost or doubled between replay and live tail.
  `after` None: no replay; past the head: `restart`; older than the oldest retained id minus one: `gap`; else the retained events after it.
- The route sends `server.hello` {version, chart_version, graph_version} first, then a resync (if any), the replay, the live tail. `once=1` stops after
  the replay (no id given: replays from 0). `Last-Event-ID` wins over `?after=`; a header that is not a whole number is ignored.

## Decisions (deviations from the text are marked D)
- Control events (`server.hello`, `server.resync`) never get a seq and never enter the ring; they are broadcast to open streams only and the route
  writes no `id:` line for them. This is how the reconciler's `server.resync {reason:'restart'}` goes out (`bus.publish_one('server.resync', ...)`), and
  it matches the UI's fake backend. A replayed ring therefore never contains a resync.
- D: `publish` and `publish_one` never raise: an invalid type (not `[a-z][a-z0-9_]*(.[a-z][a-z0-9_]*)*`, at most 60 characters, it becomes the one-line
  `event:` field) or non-JSON data is logged and dropped (`publish_one` returns None). A health event must not break a model call, and the database has
  committed already when it publishes.
- D: a slow stream (more than 2000 queued events) has its queue replaced by one `server.resync {reason:'gap'}` and goes on live; the spec only named
  gap for ids older than the ring. Bounded memory per stream, same client behaviour (refetch).
- D: the subscription is created in a `yield` dependency (`_tail`), not in the generator. Measured: when a client left while the generator was suspended
  at a `yield`, FastAPI cancelled the producer but the generator's `finally` waited for garbage collection, so the subscription leaked (a test with a burst
  after the disconnect found it). The dependency's teardown runs with the request.
- Topics: comma list of `[a-z][a-z_]{0,39}`, at most 20, blanks ignored, bad value is 422 `validation` (raised in a dependency, before the stream starts);
  an unknown topic is allowed and matches nothing. `topics=chat` does not match `chatter.x` (whole word before the dot).
- Wire: FastAPI writes the lines as `event`, `data`, `id` (the spec listed `id` before `data`; the order is free in SSE and the UI client does not care).
  `data` is the event's `data` object only, compact ASCII JSON, passed through `Services.redact.scrub` when it has one. `at` is not on the wire.
- `hello_data` reads `MAX(org_charts.revision)` and `meta.graph_version` straight from the database (0 when absent), so the route needs no store slot.

## Known limits
- seq restarts at 1 each launch (spec). The 15 s ping is FastAPI's; tested by shortening `fastapi.routing._PING_INTERVAL`.

## Follow-ups for other packages
- ORCH-8: build ONE `EventBus(clock=...)`, pass `bus.publish` to `Database`, put it in `Services.bus`, include `api.events.router`, pass
  `events=lambda t, d: bus.publish_one(t, d)` to the connector factory, call `bus.close()` at the start of shutdown (open streams would hold uvicorn's
  graceful stop), and have `reconcile` end with `bus.publish_one('server.resync', {'reason': 'restart'})`.

## Mutation check
20 hand-made mutants (ring boundary, restart boundary, seq step, control events in the ring, `server` always passes, id on control frames, header vs
`after`, `once` default, `close`, hello graph_version, redaction, topic pattern, topic cap, invalid-type guard, subscription release, data copy, overflow
threshold and reset, `topics=None`, topic filter on replay). All killed; one test run hung on the topic-pattern mutant because a 422 probe lacked `once=1`
(fixed: every probe now carries it). No second round.
