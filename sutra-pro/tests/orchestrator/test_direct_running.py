"""The registry of direct turns: the claim, the turn's stop token and its `LiveTurn` (streaming design D215, work package STR-2)."""
from __future__ import annotations

from sutra_app.orchestrator import direct_running as dr


def teardown_function(_):
    for sid in list(dr.RUNNING):
        dr.end(sid)


def test_begin_turn_hands_out_a_token_and_a_second_claim_is_busy_with_the_holders_client_id():
    first = dr.begin_turn("cs_a", "client-one")
    assert isinstance(first, dr.Started) and dr.token_of("cs_a") is first.token and dr.client_of("cs_a") == "client-one"
    second = dr.begin_turn("cs_a", "client-two")
    assert isinstance(second, dr.Busy) and second.client_id == "client-one"
    assert dr.token_of("cs_a") is first.token                 # a refused claim never replaces the holder's token


def test_begin_stays_a_thin_wrapper_and_claims_one_chat_at_a_time():
    assert dr.begin("cs_b") is True and dr.begin("cs_b") is False and dr.begin("cs_c") is True
    assert dr.answering("cs_b") and dr.token_of("cs_b") is not None


def test_end_drops_claim_token_client_turn_and_live_together():
    started = dr.begin_turn("cs_d", "c1")
    dr.attach("cs_d", 7)
    dr.bind("cs_d", object())
    assert dr.turn_of("cs_d") == 7 and dr.live_of("cs_d") is not None
    dr.end("cs_d")
    assert (dr.answering("cs_d"), dr.token_of("cs_d"), dr.client_of("cs_d"), dr.turn_of("cs_d"), dr.live_of("cs_d")) == (False, None, None, None, None)
    assert isinstance(dr.begin_turn("cs_d"), dr.Started) and dr.token_of("cs_d") is not started.token       # the next claim gets its own token


def test_bind_is_ignored_for_a_chat_that_is_not_answering():
    dr.bind("cs_e", object())
    assert dr.live_of("cs_e") is None
