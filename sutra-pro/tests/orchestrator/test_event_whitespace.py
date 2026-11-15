"""A streamed piece of text keeps its white space on the way through the event bus (streaming design D232).

`Event` is a `Value`, and a `Value` strips the white space around every string it validates, nested ones included. A live chat piece is "the " or " price": all of its edge is
white space. Stripped, the page read "aprice in rupees", its offset check saw a missing character on every piece boundary and read the snapshot again and again."""
from __future__ import annotations

from sutra_app.orchestrator.events import CONTROL_TYPES, LIVE, EventBus
from sutra_app.orchestrator.models import Event


def test_the_data_of_an_event_keeps_the_white_space_of_its_strings():
    event = Event(seq=0, at="2026-11-14T10:00:00Z", type=LIVE, data={"payload": {"delta": " price in ", "offset": 3}, "note": "  kept\n"})
    assert event.data == {"payload": {"delta": " price in ", "offset": 3}, "note": "  kept\n"}


def test_a_live_piece_published_on_the_bus_reaches_a_subscriber_exactly():
    bus = EventBus()
    seen = []
    original = bus._deliver

    def record(event):
        seen.append(event)
        return original(event)

    bus._deliver = record
    bus.publish_one(LIVE, {"type": "block.delta", "payload": {"delta": "for the ", "offset": 0}})
    bus.publish_one(LIVE, {"type": "block.delta", "payload": {"delta": " site", "offset": 8}})
    assert [e.data["payload"]["delta"] for e in seen] == ["for the ", " site"]
    assert LIVE in CONTROL_TYPES


def test_the_fields_that_are_not_data_are_still_checked():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Event(seq=0, at="not a time", type=LIVE, data={})
    with pytest.raises(ValidationError):
        Event(seq=0, at="2026-11-14T10:00:00Z", type="", data={})
