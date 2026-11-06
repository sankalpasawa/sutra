"""How long the owner has kept a team waiting, and why a queued task is not starting (gap package attention).

The words are fixed by the package (docs/notes/GAP-attention.md): a question waits "3 days", a question unanswered for 24 h is stale,
and a task queued behind a team that waits for the OWNER says so instead of blaming the team."""
import pytest
from orchestrator.test_chat_store import QUESTION, post
from orchestrator.test_tasks import tenv_with

from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.testing.fake_engine import ev
from sutra_app.orchestrator.waiting import ASK_STALE_S, OWNER_BUSY, TEAM_BUSY, age_words, ask_state, why_waiting

DAY = 86400


@pytest.mark.parametrize("seconds, words", [
    (0, "just now"), (59, "just now"), (60, "1 minute"), (59 * 60, "59 minutes"), (3600, "1 hour"), (5 * 3600 + 59, "5 hours"),
    (DAY, "1 day"), (3 * DAY + 7200, "3 days"), (-30, "just now"), (None, "just now"), ("x", "just now"), (float("inf"), "just now"),
])
def test_age_words_round_down_to_the_largest_unit(seconds, words):
    assert age_words(seconds) == words


def test_a_question_becomes_stale_after_24_hours_and_a_future_one_has_waited_nothing():
    assert ASK_STALE_S == 24 * 3600
    assert ask_state(1000, 1000 + 59 * 60) == (59 * 60, False)
    assert ask_state(1000, 1000 + 25 * 3600) == (25 * 3600, True)
    assert ask_state(1000, 1000 + ASK_STALE_S) == (ASK_STALE_S, True)
    assert ask_state(5000, 1000) == (0, False)                     # a clock that moved back
    assert ask_state(1000, 1000 + 120, stale_s=60) == (120, True)


def test_why_waiting_names_the_owner_when_the_teams_task_waits_for_an_answer():
    common = dict(working=0, live=1, max_runs=3, max_live=12)
    assert why_waiting(busy_status="waiting_user", **common) == OWNER_BUSY
    assert "your answer" in OWNER_BUSY
    assert why_waiting(busy_status="running", **common) == TEAM_BUSY
    assert why_waiting(busy_status="starting", **common) == TEAM_BUSY
    assert why_waiting(busy_status=None, **common) == ""


def test_why_waiting_says_when_every_slot_is_held_by_teams_that_wait_for_the_owner():
    assert why_waiting(busy_status=None, working=3, live=3, max_runs=3, max_live=12) == "waiting for a free slot (3 teams working)"
    assert why_waiting(busy_status=None, working=0, live=12, max_runs=3, max_live=12) == \
        "waiting for a free slot: 12 teams are waiting for your answers"
    assert why_waiting(busy_status=None, working=1, live=2, max_runs=2, max_live=2) == \
        "waiting for a free slot: 1 teams working, 1 team is waiting for your answers"


# ---- the store and the queue ------------------------------------------------------------------------------------------------

def test_needs_you_says_how_long_each_item_waited_and_marks_the_stale_one(db, clock):
    from orchestrator.test_graph_store import World
    world = World(db, clock)
    chats = ChatStore(db)
    old = post(db, chats, world.session_of["web"], QUESTION, kind="question", at=1000)
    new = post(db, chats, world.session_of["sales"], QUESTION, kind="question", at=1000 + 26 * 3600)
    now = 1000 + 26 * 3600 + 120
    first, second = chats.needs_you(now=now)
    assert (first.message_id, first.waiting_s, first.stale) == (old.id, 26 * 3600 + 120, True)
    assert (second.message_id, second.waiting_s, second.stale) == (new.id, 120, False)
    plain = chats.needs_you()                                       # without a time: the shape it always had, nothing computed
    assert [(n.waiting_s, n.stale) for n in plain] == [(None, False), (None, False)]


def test_a_task_queued_behind_a_team_that_waits_for_the_owner_says_the_owner_is_awaited(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events)
    a = t.new(dept="web", text="one")
    b = t.new(dept="web", text="two")
    t.run(t.service.start_ready())
    t.write_events(a.id, ev("run.started", pid=1, schema="events/1", mock=True, seed="none"),
                   ev("say", id=1, who="identity", text="What is it called?", to_user=True, act="ASK_REQUESTER", next="user"))
    t.drain(a.id)
    assert t.status(a.id) == "waiting_user"
    t.run(t.service.start_ready())
    assert t.status(b.id) == "queued"
    assert t.graph.get(t.one("SELECT id FROM graph_nodes WHERE task_id = ?", b.id)).detail == OWNER_BUSY


def test_a_full_house_of_waiting_teams_is_named_as_such(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, max_runs=1, max_live=1)
    a, b = t.new(dept="web", text="one"), t.new(dept="sales", text="two")
    t.run(t.service.start_ready())
    t.write_events(a.id, ev("run.started", pid=1, schema="events/1", mock=True, seed="none"),
                   ev("say", id=1, who="identity", text="Q?", to_user=True, act="ASK_REQUESTER", next="user"))
    t.drain(a.id)
    t.run(t.service.start_ready())
    assert t.status(b.id) == "queued"
    assert t.graph.get(t.one("SELECT id FROM graph_nodes WHERE task_id = ?", b.id)).detail == \
        "waiting for a free slot: 1 team is waiting for your answers"
