"""The question of a project is a card in the org chat (D317, G12): one card for each open question, in the transaction that opens it; it counts in `needs_you`; an answer or an end marks it
answered and clears the count; a repeat makes no second card; the words say what a no does and never promise a writer "runs alone" (G19, G21, D323). Without projects no such row exists."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator import gatekeeper
from sutra_app.orchestrator.ids import ORG_SESSION_ID

BASE = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def cards(rig):
    return [r for r in rig.sql("SELECT id, card_json, answered_by, src_ref FROM chat_messages WHERE session_id = ? AND json_extract(card_json, '$.type') = 'node_approval' ORDER BY id", ORG_SESSION_ID)]


def asking(rig, **kw):
    return rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)}, **kw)


def test_an_open_question_makes_one_card_and_one_needs_you_item_and_an_answer_clears_both(rig):
    reservation, tasks = asking(rig)
    [row] = cards(rig)
    card = json.loads(row["card_json"])
    assert row["src_ref"] == f"approval:{rig.store.approvals(reservation.project_id)[0].id}" and card["type"] == "node_approval" and card["options"] == ["allow_once", "allow_project", "deny"]
    assert "only that step is cancelled" in card["question"] and row["answered_by"] is None
    [item] = rig.t.chats.needs_you()
    assert item.kind == "node_approval" and item.message_id == row["id"] and item.options == ["allow_once", "allow_project", "deny"] and rig.t.chats.needs_you_count() == 1
    rig.t.run(rig.projects.answer(reservation.project_id, rig.store.approvals(reservation.project_id)[0].id, "allow_once"))
    assert cards(rig)[0]["answered_by"] == row["id"] and rig.t.chats.needs_you() == [] and rig.t.chats.needs_you_count() == 0
    assert len(cards(rig)) == 1                                                                       # a second answer makes no second card
    rig.t.run(rig.projects.answer(reservation.project_id, rig.store.approvals(reservation.project_id)[0].id, "allow_once"))
    assert len(cards(rig)) == 1


def test_needs_you_changed_is_sent_when_a_question_opens_and_when_it_ends(rig):
    before = len(rig.t.env.events.events)
    reservation, tasks = asking(rig)
    opened = [e for e in rig.t.env.events.events[before:] if e.type == "needs_you.changed"]
    assert opened and opened[-1].data["count"] == 1
    before = len(rig.t.env.events.events)
    rig.t.run(rig.projects.stop(reservation.project_id))                                               # a stop ends the question too
    ended = [e for e in rig.t.env.events.events[before:] if e.type == "needs_you.changed"]
    assert ended and ended[-1].data["count"] == 0 and cards(rig)[0]["answered_by"] is not None


def test_a_sleep_that_refuses_the_gate_marks_the_card_answered(rig):
    reservation, tasks = asking(rig)
    rig.t.run(rig.projects.tick(now=BASE + 10))
    rig.t.run(rig.projects.tick(now=BASE + 5000))
    assert cards(rig)[0]["answered_by"] is not None and rig.t.chats.needs_you_count() == 0


def test_the_estimate_and_scope_questions_say_what_a_no_does_and_none_of_the_words_say_alone(rig):
    rig.projects._output_of = lambda dept: "edit"
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("a/", "b/", "c/")}, estimates={"a1": 300, "a2": 300})
    questions = {json.loads(r["card_json"])["kind"]: json.loads(r["card_json"]) for r in cards(rig)}
    assert set(questions) == {"scope", "plan_estimate"} and questions["scope"]["options"] == ["allow_once", "deny"]
    assert "about 600 credits, which is over 400" in questions["plan_estimate"]["question"]
    assert "only that step is cancelled" in questions["scope"]["question"] and "whole project stops" in questions["plan_estimate"]["question"]       # what a no does (D315)
    assert "kept apart from other steps" in questions["scope"]["question"]                                     # true from MAN-10: the leases are enforced (D323)
    assert "apart from other writers" in gatekeeper.decide_for_me_answer("scope", 2).why


def test_a_project_without_a_chat_or_with_the_flag_off_writes_no_such_row(db, settings, clock, events):
    from orchestrator.test_tasks import tenv_with
    plain = tenv_with(db, settings, clock, events)
    assert plain.chats.needs_you() == [] and plain.sql("SELECT count(*) FROM chat_messages WHERE json_extract(card_json, '$.type') = 'node_approval'").fetchone()[0] == 0
