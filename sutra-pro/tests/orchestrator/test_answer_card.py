"""The card of a cited answer (DV-1): its closed shape, how it is stored beside the answer, and that the ordinary endings of a turn did not change."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sutra_app.library.gate import GATE
from sutra_app.orchestrator import chats
from sutra_app.orchestrator.direct_turns import CardEnding, Ending, failed, finished, ref_of, stopped
from sutra_app.orchestrator.models import AnswerCard, AnswerSource, ChatMessageOut
from sutra_app.orchestrator.records import ChatMessage

OK = {"path": "src/app.py", "start": 3, "end": 4, "label": "checked", "how": "lines"}
NO = {"path": "src/gone.py", "start": 1, "end": 2, "label": "could not find", "reason": "there is no such file"}


def card(**over):
    return AnswerCard(type="answer_sources", **{"question": "what does it print?", "sources": [AnswerSource(**OK), AnswerSource(**NO)], "checked": 1, "missing": 1, **over})


def test_the_wire_shape_has_only_what_there_is():
    wire = card().model_dump(mode="json")
    assert wire == {"type": "answer_sources", "question": "what does it print?", "checked": 1, "missing": 1, "more": 0,
                    "sources": [{"path": "src/app.py", "start": 3, "end": 4, "label": "checked", "how": "lines"},
                                {"path": "src/gone.py", "start": 1, "end": 2, "label": "could not find", "reason": "there is no such file"}]}
    quoted = AnswerSource(**OK, quote="print('hi')").model_dump(mode="json")
    assert quoted["quote"] == "print('hi')"
    assert AnswerCard(type="answer_sources").model_dump(mode="json") == {"type": "answer_sources", "question": "", "sources": [], "checked": 0, "missing": 0, "more": 0}


@pytest.mark.parametrize("bad", [
    {"label": "verified"}, {"label": "Checked"}, {"how": "guess"}, {"path": ""}, {"path": "x" * 301}, {"start": -1}, {"end": 1_000_000_000}, {"reason": "x" * 201},
    {"extra": 1}, {"start": "3"}, {"label": None},
])
def test_a_source_is_closed_and_its_label_is_one_of_two_words(bad):
    with pytest.raises(ValidationError):
        AnswerSource(**{**OK, **bad})


def test_a_card_is_closed_too():
    for bad in ({"checked": -1}, {"sources": [{"nope": 1}]}, {"extra": 1}, {"question": "q" * 501}):
        with pytest.raises(ValidationError):
            AnswerCard(type="answer_sources", **bad)
    with pytest.raises(ValidationError):
        AnswerCard(type="answer", sources=[])
    with pytest.raises(ValidationError):
        AnswerCard(type="answer_sources", sources=[AnswerSource(**OK)] * 51)


def test_the_store_takes_the_card_as_a_message_of_kind_card_and_reads_it_back_as_a_card():
    record = GATE.check("chat_message", ChatMessage(kind="card", session_id="cs_00000000000a", role="agent", who="sutra", card=card().model_dump(mode="json"),
                                                    src_ref="direct-sources:5", at=1))
    assert record.model.card["type"] == "answer_sources"
    with pytest.raises(Exception):                                          # a card carries no text, as every card
        GATE.check("chat_message", ChatMessage(kind="card", session_id="cs_00000000000a", role="agent", who="sutra", text="x", card=card().model_dump(mode="json"), at=1))
    with pytest.raises(Exception):                                          # a card of a label nobody may write is not a card
        GATE.check("chat_message", ChatMessage(kind="card", session_id="cs_00000000000a", role="agent", who="sutra",
                                               card={"type": "answer_sources", "sources": [{**OK, "label": "verified by the model"}]}, at=1))
    out = ChatMessageOut(id=7, session_id="cs_00000000000a", role="agent", who="sutra", kind="card", text="", card=card().model_dump(mode="json"), at="2026-11-20T10:00:00Z")
    assert isinstance(out.card, AnswerCard) and out.card.sources[1].label == "could not find"


def test_the_card_ending_is_a_card_with_no_text_and_a_ref_that_names_the_owners_line_and_the_try():
    ending = CardEnding(src_ref=ref_of(41, "sources", 1), card=card().model_dump(mode="json"))
    assert (ending.kind, ending.text, ending.src_ref, ending.blocks, ending.ordered, ending.via) == ("card", "", "direct-sources:41", [], False, None)
    assert CardEnding(src_ref=ref_of(41, "sources", 3), card={}).src_ref == "direct-sources:41.3"
    for ref in ("direct:41", "direct-note:41", "direct-sources:", "direct-sources:041", "direct-sources:41.1", "direct-sources:41.100", "ask:41"):
        with pytest.raises(ValidationError):
            CardEnding(src_ref=ref, card={})
    with pytest.raises(ValidationError):
        CardEnding(src_ref="direct-sources:41", card={}, text="a word")
    with pytest.raises(ValidationError):
        CardEnding(src_ref="direct-sources:41")                              # a card ending has a card


def test_the_ordinary_ending_did_not_change_it_still_needs_text_and_has_no_card_kind():
    with pytest.raises(ValidationError):
        Ending(kind="text", text="", src_ref="direct:5")
    with pytest.raises(ValidationError):
        Ending(kind="card", text="x", src_ref="direct:5")
    with pytest.raises(ValidationError):
        Ending(kind="text", text="x", src_ref="direct-sources:5")
    assert "card" not in Ending.model_fields and "card" in CardEnding.model_fields


def test_the_endings_of_a_turn_are_what_they_were_a_card_is_added_only_by_the_ask_mode():
    done = {"text": "answer", "blocks": [], "switched": None}
    assert [e.kind for e in finished(5, done)] == ["text"] and [e.src_ref for e in finished(5, done)] == ["direct:5"]
    assert [e.kind for e in stopped(5, "some")] == ["text", "note"] and [e.kind for e in failed(5, "", "no")] == ["error"]
    assert all(not isinstance(e, CardEnding) for e in finished(5, done) + stopped(5, "x") + failed(5, "x", "no"))


@pytest.mark.parametrize("ref, owner, attempt", [("direct-sources:5", 5, 1), ("direct-sources:5.2", 5, 2), ("direct:5", 5, 1), ("direct-note:5.3", 5, 3)])
def test_the_page_reads_which_line_and_which_try_a_card_belongs_to(ref, owner, attempt):
    assert chats._turn_of(ref) == owner and chats._attempt_of(ref) == attempt


def test_a_ref_that_is_not_a_direct_ref_is_still_not_one():
    for ref in ("direct-sources:", "direct-sourcesx:5", "direct-source:5", "ask:5", None, ""):
        assert chats._turn_of(ref) is None
