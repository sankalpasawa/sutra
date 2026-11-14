"""The live direct chat over HTTP (streaming design D201 to D222; work package STR-7): idempotent sends, the numbered `chat.live` events, a Stop that answers at once and ends the
turn in every window, the snapshot and retry routes, the ordered store with its earlier-try note, recovery from a checkpoint, and that with `SUTRA_LIVE_V1` off every payload is
what it always was. The ports here are scripted; the real router, connectors and fake CLIs are covered by the connector tests."""
from __future__ import annotations

import json
import threading
import time

import pytest
from orchestrator.test_api_chat_v2 import H, error_code, rig, say, wait_for, world  # noqa: F401  (the fixtures of the chat v2 routes)

from sutra_app.connectors.cancel import CancelToken
from sutra_app.connectors.chat_blocks import BlockAccumulator
from sutra_app.connectors.chat_models import ChatEvent
from sutra_app.connectors.errors import CallCancelledError, CrashedError
from sutra_app.connectors.models import ConnectorEvent
from sutra_app.orchestrator import direct_running, live_checkpoint
from sutra_app.orchestrator.api import chat_v2
from sutra_app.orchestrator.api.events import _frame
from sutra_app.orchestrator.chat_v2 import recover_interrupted
from sutra_app.orchestrator.events import LIVE
from sutra_app.orchestrator.redact import Redactor


# ---- a scripted live port ------------------------------------------------------------------------------------------------------------------

class Gate:
    """Waits for the test, or for the turn's stop token (what a real process does when it is cancelled)."""

    def __init__(self):
        self.event = threading.Event()
        self.reached = threading.Event()

    def wait(self, cancel, seconds=15):
        self.reached.set()
        end = time.time() + seconds
        while time.time() < end:
            if cancel is not None and cancel.requested:
                raise CallCancelledError("stopped")
            if self.event.wait(0.01):
                return


class LivePort:
    """`ChatPort.stream(cancel=, acc=)` as a script. Items: a ChatEvent is yielded; ("feed", [(kind, data)...]) feeds the accumulator like the real port and yields the block events;
    a Gate waits; an exception is raised; a callable is called with (cancel, acc)."""

    def __init__(self, *script, stop_delay=0.0):
        self.script, self.stop_delay, self.stops, self.streams = script, stop_delay, [], []

    def stream(self, sid, turn, *, cancel=None, acc=None):
        self.streams.append((sid, turn, cancel, acc))
        for item in self.script:
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, Gate):
                item.wait(cancel)
            elif isinstance(item, tuple) and item[0] == "feed":
                for kind, data in item[1]:
                    for out in acc.feed(ConnectorEvent(kind=kind, data=data)):
                        yield ChatEvent(kind="block_" + out.kind, data={"block_id": out.block_id, **out.data})
            elif callable(item):
                item(cancel, acc)
            else:
                yield item
        for out in acc.finalize("ok"):
            yield ChatEvent(kind="block_" + out.kind, data={"block_id": out.block_id, **out.data})
        yield ChatEvent(kind="turn_done", data={"text": acc.text() or "ok", "provider": "claude", "model": "m", "usd": None, "usage": None, "blocks": acc.stored_blocks(),
                                                "blocks_ordered": acc.stored_blocks(ordered=True), "stored_order": acc.stored_order(), "earlier": acc.earlier_attempts(),
                                                "switched": None})

    def set_system(self, *a):
        return None

    def stop(self, sid):
        self.stops.append(sid)
        time.sleep(self.stop_delay)
        token = direct_running.token_of(sid)
        if token is not None:
            token.request()
        return True


def route(event, **data):
    return ChatEvent(kind="route", data={"event": event, **data})


def attempt(n=1, provider="claude"):
    return route("attempt", provider=provider, model="m", n=n, idle_limit_s=120.0, stream_mode="tokens")


def started():
    return ChatEvent(kind="started", data={"provider": "claude", "model": "m", "session_id": "p1"})


def text(*pieces):
    return ("feed", [("message_boundary", {}), ("block_start", {"index": 0, "type": "text"})] + [("text_delta", {"text": p, "kind": "text"}) for p in pieces] + [("block_stop", {"index": 0})])


def tool(tid="t1", name="Read", path="/x/a.py", result=True):
    events = [("block_start", {"index": 1, "type": "tool_use", "tool_id": tid, "name": name}), ("tool_call", {"id": tid, "name": name, "input": {"file_path": path}}), ("block_stop", {"index": 1})]
    if result:
        events.append(("tool_result", {"tool_use_id": tid, "content": "out", "truncated": False, "is_error": False}))
    return ("feed", events)


@pytest.fixture
def live(rig):
    client, world, chats, bus, services = rig
    services.settings = services.settings.model_copy(update={"live_v1": True, "live_coalesce_ms": 5, "live_checkpoint_s": 0.05})
    seen, original = [], bus.publish_one

    def record(type, data=None):
        if type == LIVE:
            seen.append(json.loads(json.dumps(data)))
        return original(type, data)
    bus.publish_one = record
    services.seen = seen
    yield client, world, chats, bus, services
    for sid in list(direct_running.RUNNING):
        token = direct_running.token_of(sid)
        if token is not None:
            token.request()
    assert wait_for(lambda: not direct_running.RUNNING, 10)


def post(client, sid, text="hello there", **extra):
    return client.post(f"/api/chats/{sid}/direct", json={"text": text, **extra}, headers=H)


def types(services):
    return [e["type"] for e in services.seen]


def done(chats, sid, count):
    return wait_for(lambda: len(chats.messages(sid)) >= count and not direct_running.answering(sid), 15)


CID = "client-aaaa1111"


# ---- the flag off: nothing changes ---------------------------------------------------------------------------------------------------

def test_with_the_flag_off_the_payloads_are_what_they_always_were(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    services.chat_port = LivePortLegacy()
    r = client.post(f"/api/chats/{sid}/direct", json={"text": "hi", "client_id": CID}, headers=H)
    assert r.status_code == 202 and set(r.json()) == {"message_id", "turn"} and r.json()["turn"] == "started"
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and not direct_running.answering(sid))
    assert client.post(f"/api/chats/{sid}/direct/stop", headers=H).json() == {"session_id": sid, "stopped": False}
    assert client.get(f"/api/chats/{sid}/turn").json() == {"live": False} or client.get(f"/api/chats/{sid}/turn").json()["live"] is False
    assert "live" not in client.get(f"/api/chats/{sid}").json()
    assert error_code(client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": r.json()["message_id"]}, headers=H), 404) == "not_found"
    owner = chats.messages(sid)[0]
    assert owner.client_id is not None and owner.client_id != CID                  # the flag off ignores the page's client id: a random one, as before


class LivePortLegacy:
    def stream(self, sid, turn):
        yield ChatEvent(kind="turn_done", data={"text": "legacy", "provider": "claude", "model": None, "usd": None, "blocks": [], "switched": None})

    def set_system(self, *a):
        return None

    def stop(self, sid):
        return False


# ---- a send, the events, the store ---------------------------------------------------------------------------------------------------------

def test_a_live_send_answers_202_with_the_generation_and_streams_numbered_events_then_stores_one_reply(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(route("plan", order=["claude"], model="m"), attempt(), started(), text("Hel", "lo ", "world"), tool(), text("Done."))
    r = post(client, sid, client_id=CID)
    assert r.status_code == 202
    body = r.json()
    assert set(body) == {"message_id", "turn", "generation_id", "attempt_no", "client_id"} and body["attempt_no"] == 1 and body["client_id"] == CID and len(body["generation_id"]) == 32
    assert done(chats, sid, 2)
    e = services.seen
    assert [x["seq"] for x in e] == list(range(1, len(e) + 1)) and types(services)[0] == "turn.accepted" and types(services)[-1] == "turn.done"
    assert e[0]["payload"] == {"client_id": CID, "attempt_no": 1} and all(x["generation_id"] == body["generation_id"] and x["conversation_id"] == sid for x in e)
    assert types(services)[1:4] == ["turn.connecting", "turn.started", "block.start"]
    reply = chats.messages(sid)[1]
    assert reply.attempt == 1 and reply.ordered is True and reply.superseded is False and reply.turn == body["message_id"]
    assert [b.type for b in reply.blocks] == ["text", "tool_use", "tool_result", "text"] and reply.blocks[0].text == "Hello world"
    final = e[-1]["payload"]
    assert final["message_id_reply"] == reply.id and final["stored_order"] == ["b1", "b2", "b2", "b3"] and final["attempt_no"] == 1 and final["text_len"] == len(reply.text)
    assert live_checkpoint.all_rows(services.db) == []                              # the checkpoint went with the reply
    assert not direct_running.answering(sid) and direct_running.live_of(sid) is None and direct_running.token_of(sid) is None
    owner = chats.messages(sid)[0]
    assert owner.client_id == CID and owner.attempt is None


def test_the_port_is_given_the_stop_token_and_the_turns_own_accumulator(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    port = services.chat_port = LivePort(started())
    post(client, sid, client_id=CID)
    assert done(chats, sid, 2)
    _, turn, token, acc = port.streams[0]
    assert isinstance(token, CancelToken) and isinstance(acc, BlockAccumulator) and turn.text == "hello there"


def test_the_events_carry_no_secret_and_the_frame_scrubs_what_slipped_through(live):
    client, world, chats, bus, services = live
    services.redact = Redactor(None, environ={}, extra=("hunter2-password",))
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), text("the pass", "word hunter2-", "password!"))
    post(client, sid, client_id=CID)
    assert done(chats, sid, 2)
    assert "hunter2-password" not in json.dumps(services.seen) and "hunter2-password" not in chats.messages(sid)[1].text
    frame = _frame(LIVE, 0, {"payload": {"delta": "x hunter2-password y"}}, services.redact.scrub)
    assert frame.id is None and "hunter2-password" not in frame.raw_data and "[redacted]" in frame.raw_data


def test_a_failed_turn_keeps_what_was_written_and_the_tools_and_says_why(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), text("half an answ"), tool(result=False), CrashedError("died", provider="claude", detail={"exit": 137}))
    r = post(client, sid, client_id=CID)
    assert done(chats, sid, 3)
    out = chats.messages(sid)[1:]
    assert [m.kind for m in out] == ["text", "error"] and out[0].text == "half an answ" and "stopped unexpectedly" in out[1].text
    assert out[0].ordered and [b.type for b in out[0].blocks] == ["text", "tool_use"]
    last = services.seen[-1]
    assert last["type"] == "turn.failed" and last["payload"]["code"] == "crashed" and last["payload"]["message_id_reply"] == out[0].id and "stopped unexpectedly" in last["payload"]["message"]
    ends = [x for x in services.seen if x["type"] == "block.end"]
    assert {x["payload"]["status"] for x in ends if x["block_id"] == "b2"} == {"interrupted"}
    assert live_checkpoint.all_rows(services.db) == []


def test_earlier_tries_become_a_note_and_the_stored_reply_is_the_final_attempt(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), text("first try"), tool("t9", "Edit", "/x/b.py", result=True),
                                  route("failed", provider="claude", code="crashed", reason="Claude stopped unexpectedly (exit 137)", retryable=True, action="retry", delay_s=0.0, next_provider="claude"),
                                  attempt(2), ChatEvent(kind="restart", data={"provider": "claude", "reason": "Claude stopped unexpectedly (exit 137)", "after_side_effects": True}), started(),
                                  lambda cancel, acc: acc.restart("Claude stopped unexpectedly (exit 137)", "claude") and None, text("second try"))
    post(client, sid, client_id=CID)
    assert done(chats, sid, 3)
    rows = chats.messages(sid)[1:]
    assert [m.kind for m in rows] == ["note", "text"]
    assert "Earlier try (Claude" in rows[0].text or "Earlier try (claude" in rows[0].text
    assert "Editing b.py" in rows[0].text and "may have changed files" in rows[0].text
    assert rows[1].text == "second try" and [b.type for b in rows[1].blocks] == ["text"]
    assert types(services).count("attempt.failed") == 1 and "attempt.restart" in types(services)


# ---- idempotency ---------------------------------------------------------------------------------------------------------------------------

def test_a_second_post_with_the_same_client_id_during_the_turn_is_a_duplicate_not_a_409_nor_a_second_turn(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), gate, text("answer"))
    first = post(client, sid, client_id=CID)
    assert first.status_code == 202 and gate.reached.wait(10)
    dup = post(client, sid, client_id=CID)
    assert dup.status_code == 200 and dup.json() == {"duplicate": True, "turn": "started", "message_id": first.json()["message_id"], "client_id": CID,
                                                     "generation_id": first.json()["generation_id"]}
    assert error_code(post(client, sid, client_id="client-bbbb2222"), 409) == "busy"
    assert error_code(post(client, sid), 409) == "busy"                                 # a send without an id is a different send
    gate.event.set()
    assert done(chats, sid, 2)
    assert len([m for m in chats.messages(sid) if m.role == "user"]) == 1 and len(services.chat_port.streams) == 1
    after = post(client, sid, client_id=CID)
    assert after.status_code == 200 and after.json()["duplicate"] is True and after.json()["turn"] == "done" and after.json()["generation_id"] is None


def test_two_concurrent_posts_with_the_same_client_id_start_one_turn(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), gate, text("x"))
    results = []

    def send():
        results.append(post(client, sid, client_id=CID))
    threads = [threading.Thread(target=send) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    gate.event.set()
    codes = sorted(r.status_code for r in results)
    assert codes == [200] * 5 + [202] and all(r.json().get("duplicate") for r in results if r.status_code == 200)
    assert done(chats, sid, 2)
    assert len([m for m in chats.messages(sid) if m.role == "user"]) == 1 and len(services.chat_port.streams) == 1


def test_a_bad_client_id_is_refused(live):
    client, world, *_ = live
    sid = world.session_of["web"]
    for bad in ("short", "has space in it", "x" * 65, "a.b.c.d.e.f.g"):
        assert error_code(post(client, sid, client_id=bad), 422) == "validation"


# ---- stop ----------------------------------------------------------------------------------------------------------------------------------

def test_stop_answers_at_once_while_the_process_is_still_being_stopped_and_the_turn_ends_stopped(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = port = LivePort(attempt(), started(), text("some words "), gate, text("never shown"), stop_delay=1.5)
    post(client, sid, client_id=CID)
    assert gate.reached.wait(10)
    assert wait_for(lambda: "block.delta" in types(services))
    began = time.time()
    r = client.post(f"/api/chats/{sid}/direct/stop", headers=H)
    assert time.time() - began < 1.0 and r.status_code == 200
    assert r.json() == {"session_id": sid, "stopped": True, "state": "stopping"}
    assert types(services)[-1] == "turn.stopping" or "turn.stopping" in types(services)
    assert wait_for(lambda: port.stops == [sid], 5)
    assert done(chats, sid, 3)
    rows = chats.messages(sid)[1:]
    assert [m.kind for m in rows] == ["text", "note"] and rows[0].text == "some words" and rows[1].text.startswith("Stopped")
    last = services.seen[-1]
    assert last["type"] == "turn.stopped" and last["payload"]["message_id_reply"] == rows[0].id
    received = "".join(x["payload"]["delta"] for x in services.seen if x["type"] == "block.delta")
    assert received.rstrip() == rows[0].text                                                 # what every tab saw is what was stored (the store trims the ends of a message)
    assert types(services).index("turn.stopping") < types(services).index("turn.stopped")


def test_stop_before_the_stream_starts_ends_the_turn_and_a_second_stop_is_fine(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = LivePort(gate, attempt(), started(), text("x"))                     # the port is still in session setup
    post(client, sid, client_id=CID)
    assert gate.reached.wait(10)
    first = client.post(f"/api/chats/{sid}/direct/stop", headers=H).json()
    second = client.post(f"/api/chats/{sid}/direct/stop", headers=H).json()
    assert first["stopped"] is True and second["stopped"] is True
    assert done(chats, sid, 2)
    assert [m.kind for m in chats.messages(sid)[1:]] == ["note"] and chats.messages(sid)[1].text.startswith("Stopped before the model wrote anything")


def test_stop_during_the_back_off_wait_ends_it_at_once(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), route("failed", provider="claude", code="server_error", reason="Claude had a server error", retryable=True, action="retry",
                                                              delay_s=30.0, next_provider="claude"), gate)
    post(client, sid, client_id=CID)
    assert gate.reached.wait(10)
    began = time.time()
    assert client.post(f"/api/chats/{sid}/direct/stop", headers=H).json()["stopped"] is True
    assert done(chats, sid, 2) and time.time() - began < 5
    assert "attempt.failed" in types(services) and services.seen[-1]["type"] == "turn.stopped"


def test_stop_with_nothing_running_says_false_and_changes_nothing(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = port = LivePort()
    r = client.post(f"/api/chats/{sid}/direct/stop", headers=H)
    assert r.json() == {"session_id": sid, "stopped": False, "state": "none"} and port.stops == [] and services.seen == []
    assert error_code(client.post(f"/api/chats/{sid}/direct/stop"), 401) == "bad_token"
    assert error_code(client.post("/api/chats/cs_000000000fff/direct/stop", headers=H), 404) == "not_found"


def test_stop_that_races_a_finishing_turn_ends_done_not_stopped(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), text("all of it"), gate)
    post(client, sid, client_id=CID)
    assert gate.reached.wait(10)
    gate.event.set()
    assert done(chats, sid, 2)
    r = client.post(f"/api/chats/{sid}/direct/stop", headers=H)
    assert r.json()["stopped"] is False and chats.messages(sid)[1].text == "all of it"


# ---- the snapshot --------------------------------------------------------------------------------------------------------------------------

def test_the_snapshot_route_says_where_the_turn_is_and_then_where_the_stored_reply_is(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    assert client.get(f"/api/chats/{sid}/turn").json() == {"live": False}
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), text("Hello "), tool(result=False), gate, text("end"))
    r = post(client, sid, client_id=CID)
    assert gate.reached.wait(10)
    snap = client.get(f"/api/chats/{sid}/turn").json()
    assert snap["generation_id"] == r.json()["generation_id"] and snap["state"] == "running" and snap["attempt_no"] == 1 and snap["message_id"] == r.json()["message_id"]
    assert snap["stream_mode"] == "tokens" and snap["idle_limit_s"] == 120.0 and snap["seq"] == services.seen[-1]["seq"] and snap["client_id"] == CID
    assert [(b["type"], b.get("text"), b["status"]) for b in snap["blocks"] if b["type"] == "text"] == [("text", "Hello ", "ok")]
    assert [(b["type"], b["title"], b["status"]) for b in snap["blocks"] if b["type"] == "tool_use"] == [("tool_use", "Reading a.py", "open")]
    assert client.get(f"/api/chats/{sid}").json()["live"] == {"generation_id": snap["generation_id"], "seq": snap["seq"], "state": "running", "attempt_no": 1}
    gate.event.set()
    assert done(chats, sid, 2)
    after = client.get(f"/api/chats/{sid}/turn").json()
    assert after == {"live": False, "last_reply_id": chats.messages(sid)[1].id, "last_attempt_no": 1}
    assert "live" not in client.get(f"/api/chats/{sid}").json()
    assert error_code(client.get("/api/chats/cs_000000000fff/turn"), 404) == "not_found"


# ---- retry ---------------------------------------------------------------------------------------------------------------------------------

def test_retry_of_a_failed_line_starts_a_new_generation_and_lands_its_reply_under_attempt_two(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), text("part"), CrashedError("died", provider="claude", detail={"exit": 1}))
    first = post(client, sid, client_id=CID).json()
    assert done(chats, sid, 3)
    services.seen.clear()
    services.chat_port = LivePort(attempt(), started(), text("the whole answer"))
    r = client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": first["message_id"], "client_id": "retry-client-01"}, headers=H)
    assert r.status_code == 202 and r.json()["attempt_no"] == 2 and r.json()["message_id"] == first["message_id"] and r.json()["generation_id"] != first["generation_id"]
    assert done(chats, sid, 4)
    agents = [m for m in chats.messages(sid) if m.role == "agent"]
    assert [(m.kind, m.attempt, m.superseded) for m in agents] == [("text", 1, True), ("error", 1, True), ("text", 2, False)]
    assert agents[2].text == "the whole answer" and agents[2].turn == first["message_id"]
    assert len([m for m in chats.messages(sid) if m.role == "user"]) == 1                    # the owner's line is not stored again
    assert services.seen[0]["type"] == "turn.accepted" and services.seen[0]["payload"]["attempt_no"] == 2 and services.seen[-1]["payload"]["attempt_no"] == 2


def test_retry_of_a_stopped_line_works_and_the_model_does_not_hear_the_replaced_reply(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), text("first partial "), gate)
    first = post(client, sid, client_id=CID).json()
    assert gate.reached.wait(10)
    client.post(f"/api/chats/{sid}/direct/stop", headers=H)
    assert done(chats, sid, 3)
    services.chat_port = LivePort(attempt(), started(), text("second"))
    assert client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": first["message_id"]}, headers=H).status_code == 202
    assert done(chats, sid, 4)
    from sutra_app.orchestrator.chats import ChatTranscripts
    carried = [m.text for m in ChatTranscripts(chats).messages(sid, 20)]
    assert "second" in carried and "first partial " not in carried


def test_retry_refusals(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), text("fine"))
    first = post(client, sid, client_id=CID).json()
    assert done(chats, sid, 2)
    retry = lambda body: client.post(f"/api/chats/{sid}/direct/retry", json=body, headers=H)       # noqa: E731
    assert error_code(retry({"message_id": first["message_id"]}), 409) == "not_retryable"            # it was answered
    assert error_code(retry({"message_id": 99999}), 404) == "not_found"
    assert error_code(retry({"message_id": chats.messages(sid)[1].id}), 404) == "not_found"          # an agent line is no owner line
    services.chat_port = LivePort(attempt(), started(), CrashedError("died", provider="claude", detail={"exit": 1}))
    second = post(client, sid, "another", client_id="client-cccc3333").json()
    assert done(chats, sid, 4)                                                                       # the owner's line and one error line
    assert error_code(retry({"message_id": first["message_id"]}), 409) == "not_retryable"            # not the newest line
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), gate, text("x"))
    assert retry({"message_id": second["message_id"]}).status_code == 202 and gate.reached.wait(10)
    assert error_code(retry({"message_id": second["message_id"]}), 409) == "busy"                    # a turn is running
    assert error_code(retry({"message_id": 0}), 422) == "validation" and error_code(retry({"message_id": second["message_id"], "client_id": "bad"}), 422) == "validation"
    assert error_code(client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": 1}), 401) == "bad_token"
    gate.event.set()
    assert done(chats, sid, 5)


def test_retry_refuses_a_chat_that_cannot_be_asked_directly(live):
    client, world, chats, bus, services = live
    assert client.post("/api/chats/cs_000000000fff/direct/retry", json={"message_id": 1}, headers=H).status_code == 404


# ---- recovery ------------------------------------------------------------------------------------------------------------------------------

def test_a_checkpoint_left_by_a_crash_becomes_the_partial_reply_with_the_interrupted_line(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    line = chat_v2._store_user_line(services, sid, "write the menu", "", CID)
    rows = [{"block_id": "b1", "type": "text", "kind": "other", "name": "", "status": "ok", "text": "Starters: soup, "},
            {"block_id": "b2", "type": "tool_use", "kind": "read", "name": "Read", "status": "open", "title": "Reading menu.md", "target": "menu.md"},
            {"block_id": "b3", "type": "text", "kind": "other", "name": "", "status": "open", "text": "mains"}]
    live_checkpoint.save(services.db, generation_id="g" * 32, session_id=sid, message_id=line, attempt=1, attempt_no=1, state="running", seq=17, blocks=rows)
    assert recover_interrupted(services.db, chats) >= 1
    out = chats.messages(sid)[1:]
    assert [m.kind for m in out] == ["text", "error"] and out[0].text == "Starters: soup, mains" and out[1].text.startswith("Interrupted")
    assert out[0].ordered and [b.type for b in out[0].blocks] == ["text", "tool_use", "text"] and out[0].blocks[1].text == "Reading menu.md" and out[0].turn == line
    assert live_checkpoint.all_rows(services.db) == [] and recover_interrupted(services.db, chats) == 0


def test_a_checkpoint_of_a_retry_is_recovered_under_its_own_attempt_even_when_the_first_try_has_a_reply(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), CrashedError("died", provider="claude", detail={"exit": 1}))
    first = post(client, sid, client_id=CID).json()
    assert done(chats, sid, 2)
    live_checkpoint.save(services.db, generation_id="h" * 32, session_id=sid, message_id=first["message_id"], attempt=1, attempt_no=2, state="running", seq=4,
                         blocks=[{"block_id": "b1", "type": "text", "text": "retry words", "status": "open"}])
    recover_interrupted(services.db, chats)
    agents = [m for m in chats.messages(sid) if m.role == "agent"]
    assert [(m.kind, m.attempt) for m in agents] == [("error", 1), ("text", 2), ("error", 2)] and agents[1].text == "retry words"


def test_a_stale_checkpoint_of_a_turn_that_has_its_reply_is_only_dropped(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), text("fine"))
    first = post(client, sid, client_id=CID).json()
    assert done(chats, sid, 2)
    live_checkpoint.save(services.db, generation_id="s" * 32, session_id=sid, message_id=first["message_id"], attempt=1, attempt_no=1, state="running", seq=2, blocks=[])
    before = len(chats.messages(sid))
    recover_interrupted(services.db, chats)
    assert len(chats.messages(sid)) == before and live_checkpoint.all_rows(services.db) == []


# ---- the session and the registry ------------------------------------------------------------------------------------------------------------

def test_the_checkpoint_is_written_while_the_turn_streams_and_gone_when_it_ends(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    services.chat_port = LivePort(attempt(), started(), text("x" * 400), gate)
    post(client, sid, client_id=CID)
    assert gate.reached.wait(10)
    assert wait_for(lambda: live_checkpoint.load(services.db, sid) is not None, 5)
    ck = live_checkpoint.load(services.db, sid)
    assert ck["state"] == "running" and ck["attempt_no"] == 1 and any(b["type"] == "text" for b in ck["blocks"])
    gate.event.set()
    assert done(chats, sid, 2)
    assert live_checkpoint.load(services.db, sid) is None


def test_the_worker_always_frees_the_chat_even_when_the_ticker_or_the_store_fail(live, monkeypatch):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    monkeypatch.setattr(chat_v2, "_post_all", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the store is down")))
    services.chat_port = LivePort(attempt(), started(), text("x"))
    post(client, sid, client_id=CID)
    assert wait_for(lambda: not direct_running.answering(sid), 10)
    assert direct_running.live_of(sid) is None and direct_running.token_of(sid) is None
    monkeypatch.undo()
    services.chat_port = LivePort(attempt(), started(), text("again"))
    assert post(client, sid, "again please", client_id="client-dddd4444").status_code == 202
    assert done(chats, sid, 3)


def test_a_stop_that_loses_the_race_with_the_provider_result_still_ends_stopped_with_the_text_every_tab_saw(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    gate = Gate()
    stop_now = lambda cancel, acc: direct_running.live_of(sid).request_stop()
    # the provider returns a full result although Stop was asked: the process had already exited when the cancel ladder ran
    services.chat_port = LivePort(attempt(), started(), text("seen part "), gate, stop_now, text("never shown"))
    post(client, sid, client_id=CID)
    assert gate.reached.wait(10)
    assert wait_for(lambda: "block.delta" in types(services))
    gate.event.set()
    assert done(chats, sid, 3)
    rows = chats.messages(sid)[1:]
    assert [m.kind for m in rows] == ["text", "note"] and rows[0].text == "seen part"
    assert "never shown" not in " ".join(m.text for m in rows)
    assert types(services).index("turn.stopping") < types(services).index("turn.stopped")
    assert "turn.done" not in types(services)
    received = "".join(x["payload"]["delta"] for x in services.seen if x["type"] == "block.delta")
    assert received.rstrip() == rows[0].text


def test_the_chat_is_free_before_a_slow_ticker_close_returns(live, monkeypatch):
    from sutra_app.orchestrator import live_turn
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = LivePort(attempt(), started(), text("hi"))
    original, freed = live_turn.LiveTurn.close, []

    def slow_close(self):
        freed.append(not direct_running.answering(sid))                       # the chat must already be free when close starts
        return original(self)
    monkeypatch.setattr(live_turn.LiveTurn, "close", slow_close)
    post(client, sid, client_id=CID)
    assert done(chats, sid, 2)
    assert wait_for(lambda: bool(freed), 5) and freed == [True]


class GluedPort(LivePort):
    """A provider whose result text is its text blocks run together (what a CLI's final result can look like)."""

    def stream(self, sid, turn, *, cancel=None, acc=None):
        for event in super().stream(sid, turn, cancel=cancel, acc=acc):
            if event.kind == "turn_done":
                event.data["text"] = "".join(b["text"] for b in event.data["blocks_ordered"] if b["type"] == "text")
            yield event


@pytest.mark.parametrize("glued", [False, True])
def test_the_stored_text_of_a_reply_with_a_tool_in_the_middle_keeps_its_paragraphs_apart(live, glued):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = (GluedPort if glued else LivePort)(attempt(), started(), text("Let me check the file."), tool(), text("Found it: the value is alpha."))
    post(client, sid, client_id=CID)
    assert done(chats, sid, 2)
    reply = chats.messages(sid)[1]
    assert reply.text == "Let me check the file.\n\nFound it: the value is alpha."
    assert services.seen[-1]["payload"]["text_len"] == len(reply.text)
