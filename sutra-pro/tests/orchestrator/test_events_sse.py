"""GET /api/events (ORCH-2): the wire format, once=1, replay by Last-Event-ID and ?after=, restart and gap resync, control events
without an id, topics (connector.*), error envelopes, redaction, and a live tail through a real uvicorn thread."""
import contextlib
import json
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.orchestrator.api import events as events_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.events import EventBus
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

SECRET = "tok-secret-0123456789"


def parse(text: str) -> list[dict]:
    """The frames of an event stream body: {event, id, data (parsed JSON)}; comments come back as {comment}."""
    frames = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        frame: dict = {}
        for line in block.split("\n"):
            if line.startswith(":"):
                frame["comment"] = line[1:].strip()
            else:
                key, _, value = line.partition(": ")
                frame[key] = json.loads(value) if key == "data" else value
        frames.append(frame)
    return frames


def types(frames) -> list[str]:
    return [f["event"] for f in frames if "event" in f]


def make_app(settings, db, bus, *, redact=None) -> FastAPI:
    app = FastAPI()
    redactor = redact or Redactor(None, environ={}, extra=[SECRET])
    services = Services(settings=settings, version="9.9.9", db=db, redact=redactor)
    services.bus = bus
    app.state.services = services
    install_error_handlers(app, redacted_response_class(redactor))
    app.include_router(events_api.build_router())
    return app


@pytest.fixture
def bus(clock):
    return EventBus(clock=clock)


@pytest.fixture
def app(settings, db, bus):
    return make_app(settings, db, bus)


@pytest.fixture
def client(app):
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


def once(client, query="", headers=None):
    response = client.get("/api/events?once=1" + (f"&{query}" if query else ""), headers=headers or {})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse(response.text)


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return body["error"]


# ---- hello and the wire format ----------------------------------------------------------------------------------------------------------

def test_hello_comes_first_without_an_id_and_reads_the_versions(client, db, bus):
    assert once(client) == [{"event": "server.hello", "data": {"version": "9.9.9", "chart_version": 0, "graph_version": 0}}]
    with db.tx() as tx:
        tx.conn.execute("INSERT INTO meta (key, value) VALUES ('graph_version', '7')")
        tx.conn.execute("INSERT INTO org_charts (revision, body, sha256, ts) VALUES (3, '{}', 'x', 1)")
    frames = once(client)
    assert frames[0]["data"] == {"version": "9.9.9", "chart_version": 3, "graph_version": 7}


def test_each_frame_is_event_data_id_lines_with_compact_ascii_json(client, bus):
    payload = {"session_id": "cs_org", "message": {"id": 4, "text": "h\u00e9llo \u2713"}}
    bus.publish_one("chat.message", payload)
    raw = client.get("/api/events?once=1").text
    first, second = raw.strip().split("\n\n")
    assert first.startswith("event: server.hello\ndata: {") and "\nid:" not in first and "id:" not in first
    assert second.split("\n") == ["event: chat.message", "data: " + json.dumps(payload, separators=(",", ":")), "id: 1"]
    assert raw.isascii() and json.loads(second.split("\n")[1][6:]) == payload


def test_once_replays_the_whole_ring_when_no_id_is_given_then_closes(client, bus):
    for t in ("chat.turn", "chat.message", "graph.updated"):
        bus.publish_one(t, {"t": t})
    frames = once(client)
    assert types(frames) == ["server.hello", "chat.turn", "chat.message", "graph.updated"]
    assert [f.get("id") for f in frames] == [None, "1", "2", "3"]
    assert frames[3]["data"] == {"t": "graph.updated"}


# ---- replay by Last-Event-ID and ?after= ------------------------------------------------------------------------------------------------

def test_replay_after_an_id_sends_only_the_newer_events(client, bus):
    for i in range(5):
        bus.publish_one("task.updated", {"i": i})
    assert [f["id"] for f in once(client, "after=3")[1:]] == ["4", "5"]
    assert once(client, "after=5") == once(client, "after=5")[:1]                 # up to date: hello only
    assert [f["id"] for f in once(client, headers={"Last-Event-ID": "4"})[1:]] == ["5"]


def test_the_header_wins_over_after_and_a_bad_header_is_ignored(client, bus):
    for i in range(5):
        bus.publish_one("task.updated", {"i": i})
    assert [f["id"] for f in once(client, "after=0", {"Last-Event-ID": "3"})[1:]] == ["4", "5"]
    assert [f["id"] for f in once(client, "after=3", {"Last-Event-ID": "soon"})[1:]] == ["4", "5"]
    assert [f["id"] for f in once(client, "after=3", {"Last-Event-ID": "-1"})[1:]] == ["4", "5"]
    assert len(once(client, "", {"Last-Event-ID": "nope"})) == 6                  # once with no usable id replays from 0
    assert events_api.parse_last_event_id(" 12 ") == 12 and events_api.parse_last_event_id("1" * 16) is None
    assert events_api.parse_last_event_id("²") is None and events_api.parse_last_event_id(None) is None


def test_an_id_past_the_head_gets_resync_restart_without_an_id_and_no_replay(client, bus):
    bus.publish_one("chat.message", {})
    frames = once(client, "after=57")
    assert types(frames) == ["server.hello", "server.resync"]
    assert frames[1] == {"event": "server.resync", "data": {"reason": "restart"}}          # no id line
    assert types(once(client, headers={"Last-Event-ID": "2"})) == ["server.hello", "server.resync"]


def test_an_id_older_than_the_ring_gets_resync_gap_without_an_id(settings, db, clock):
    small = EventBus(clock=clock, ring_size=3)
    client = TestClient(make_app(settings, db, small), base_url="http://127.0.0.1:8780")
    for i in range(6):
        small.publish_one("chat.message", {"i": i})                # the ring holds 4..6
    gap = once(client, "after=2")
    assert types(gap) == ["server.hello", "server.resync"] and gap[1] == {"event": "server.resync", "data": {"reason": "gap"}}
    assert [f["id"] for f in once(client, "after=3")[1:]] == ["4", "5", "6"]               # the oldest replayable id
    assert types(once(client, "after=0")) == ["server.hello", "server.resync"]


# ---- topics -----------------------------------------------------------------------------------------------------------------------------

def test_topics_filter_by_the_part_before_the_dot_and_server_always_passes(client, bus):
    for t in ("chat.message", "graph.updated", "connector.health", "needs_you.changed", "chat.turn"):
        bus.publish_one(t, {})
    assert types(once(client, "topics=chat,graph")) == ["server.hello", "chat.message", "graph.updated", "chat.turn"]
    assert types(once(client, "topics=needs_you")) == ["server.hello", "needs_you.changed"]
    assert types(once(client, "topics=%20chat%20,,")) == ["server.hello", "chat.message", "chat.turn"]
    assert types(once(client, "topics=")) == types(once(client))                          # blank = every topic
    assert types(once(client, "topics=nothing_here")) == ["server.hello"]
    resync = once(client, "after=40&topics=chat")
    assert types(resync) == ["server.hello", "server.resync"]


def test_a_connector_mode_event_from_the_router_callback_reaches_a_connector_client(client, bus):
    emit = lambda t, d: bus.publish_one(t, d)                                           # noqa: E731  (the router's events= callback)
    worker = threading.Thread(target=lambda: [emit("connector.mode", {"mode": "stub"}), emit("chat.message", {}),
                                              emit("connector.switch", {"session_id": "cs_1", "from": "claude", "to": "codex", "reason": "quota"}),
                                              emit("connector.health", {"provider": "codex", "state": "ok", "until": None, "reason": ""})])
    worker.start()
    worker.join()
    frames = once(client, "topics=connector")
    assert types(frames) == ["server.hello", "connector.mode", "connector.switch", "connector.health"]
    assert frames[1]["data"] == {"mode": "stub"} and frames[2]["data"]["to"] == "codex" and frames[3]["data"]["until"] is None
    assert [f["id"] for f in frames[1:]] == ["1", "3", "4"]


# ---- refusals and redaction -------------------------------------------------------------------------------------------------------------

def test_bad_query_values_are_422_before_the_stream_starts(client):
    for query in ("topics=Chat", "topics=chat.message", "topics=a b", "after=-1", "after=abc", "after=9007199254740992", "once=maybe"):
        error_of(client.get(f"/api/events?once=1&{query}"), 422, "validation")
    many = ",".join(f"t{chr(97 + i)}" for i in range(21))
    assert error_of(client.get(f"/api/events?once=1&topics={many}"), 422, "validation")["details"]["violations"][0]["code"] == "too_many_topics"
    bad = error_of(client.get("/api/events?once=1&topics=BAD"), 422, "validation")["details"]["violations"][0]
    assert bad["path"] == "topics" and bad["code"] == "bad_topic"
    assert len(parse(client.get("/api/events?once=1&topics=" + ",".join(f"t{chr(97 + i)}" for i in range(20))).text)) == 1   # 20 is allowed


def test_a_bus_that_is_not_wired_is_a_500_internal(settings, db):
    app = make_app(settings, db, None)
    bare = TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)
    assert error_of(bare.get("/api/events?once=1"), 500, "internal")["message"] == "the event bus is not wired"


def test_reading_the_stream_needs_no_token_and_other_methods_are_refused(client):
    assert client.get("/api/events?once=1").status_code == 200
    assert client.post("/api/events").status_code == 405


def test_event_data_is_redacted_like_every_other_body(client, bus):
    bus.publish_one("chat.message", {"message": {"text": f"the key is {SECRET}"}, SECRET: 1})
    raw = client.get("/api/events?once=1").text
    assert SECRET not in raw and "[redacted]" in raw


# ---- a live tail through a real server --------------------------------------------------------------------------------------------------

class Live:
    """A uvicorn thread serving `app`, plus a reader for one stream."""

    def __init__(self, app):
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off", timeout_graceful_shutdown=2))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            assert time.monotonic() < deadline and self.thread.is_alive(), "the test server did not start"
            time.sleep(0.01)
        self.url = f"http://127.0.0.1:{self.server.servers[0].sockets[0].getsockname()[1]}/api/events"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(15)

    @contextlib.contextmanager
    def stream(self, query="", headers=None):
        with httpx.stream("GET", self.url + (f"?{query}" if query else ""), headers=headers or {}, timeout=10) as response:
            assert response.status_code == 200
            yield Reader(response)


class Reader:
    def __init__(self, response):
        self._lines = response.iter_lines()

    def frame(self) -> dict:
        """The next frame (or comment) of the stream."""
        block = []
        for line in self._lines:
            if line == "":
                if block:
                    return parse("\n".join(block) + "\n\n")[0]
                continue
            block.append(line)
        raise AssertionError("the stream ended")

    def frames(self, n) -> list[dict]:
        return [self.frame() for _ in range(n)]

    def ended(self) -> bool:
        return next(self._lines, None) is None


@pytest.fixture
def live(app):
    server = Live(app)
    yield server
    server.stop()


def wait_for(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_live_tail_reconnect_with_last_event_id_then_restart_and_gap(live, bus):
    bus.publish_one("chat.message", {"n": 0})
    with live.stream() as r:                                              # a first connection: hello, no replay
        assert r.frame()["event"] == "server.hello"
        wait_for(lambda: bus.subscriber_count == 1)
        bus.publish_one("graph.updated", {"n": 1})
        bus.publish_one("connector.mode", {"mode": "stub"})
        bus.publish_one("server.resync", {"reason": "restart"})           # the reconciler's: a control event, live only
        bus.publish_one("task.updated", {"n": 2})
        got = r.frames(4)
    assert [(f["event"], f.get("id")) for f in got] == [("graph.updated", "2"), ("connector.mode", "3"), ("server.resync", None), ("task.updated", "4")]
    wait_for(lambda: bus.subscriber_count == 0)                           # leaving the stream frees the subscription
    bus.publish_one("chat.message", {"n": 3})
    bus.publish_one("chat.message", {"n": 4})
    with live.stream(headers={"Last-Event-ID": "4"}) as r:                # the browser's reconnect: the missed two, then live
        assert [r.frame()["event"], *[f["id"] for f in r.frames(2)]] == ["server.hello", "5", "6"]
        bus.publish_one("chat.message", {"n": 5})
        assert r.frame()["id"] == "7"
    with live.stream(headers={"Last-Event-ID": "400"}) as r:              # an id from a previous launch: resync, then live
        assert r.frame()["event"] == "server.hello"
        assert r.frame() == {"event": "server.resync", "data": {"reason": "restart"}}
        wait_for(lambda: bus.subscriber_count == 1)
        bus.publish_one("chat.message", {"n": 6})
        assert r.frame()["id"] == "8"
    for _ in range(1005):                                                 # a burst after the client left: its subscription still goes
        bus.publish_one("chat.message", {})
    wait_for(lambda: bus.subscriber_count == 0)
    with live.stream("after=3") as r:                                     # older than the ring: gap, then the live tail
        assert r.frame()["event"] == "server.hello"
        assert r.frame() == {"event": "server.resync", "data": {"reason": "gap"}}
        wait_for(lambda: bus.subscriber_count == 1)
        bus.publish_one("task.updated", {})
        last = r.frame()
        assert last["event"] == "task.updated" and last["id"] == str(bus.head)


def test_live_topics_and_closing_the_bus_ends_the_stream(live, bus):
    with live.stream("topics=connector") as r:
        assert r.frame()["event"] == "server.hello"
        wait_for(lambda: bus.subscriber_count == 1)
        bus.publish_one("chat.message", {})
        bus.publish_one("connector.health", {"provider": "claude", "state": "ok", "until": None, "reason": ""})
        frame = r.frame()
        assert frame["event"] == "connector.health" and frame["id"] == "2"
        bus.close()
        assert r.ended()


def test_live_an_idle_stream_gets_a_ping_comment(live, bus, monkeypatch):
    import fastapi.routing
    monkeypatch.setattr(fastapi.routing, "_PING_INTERVAL", 0.2)
    with live.stream() as r:
        assert r.frame()["event"] == "server.hello"
        assert r.frame() == {"comment": "ping"}
