"""The Heads up lane (gap package attention): crashed or app-stopped work with Try again, a team gone quiet, work finished in 24 h.

Expected values come from the package (docs/notes/GAP-attention.md) and the old app's relevance rule (shadow_feed.py: a failed card
lives 24 h, an FYI 24 h, a stall row only while the task runs, the founder's own intervention is never news)."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_graph_store import World
from orchestrator.test_tasks import ask, tenv  # noqa: F401  (tenv is a fixture used by name)

from sutra_app.orchestrator.api import chat as chat_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.headsup import QUIET_AFTER_S, STOP_KEY, WINDOW_S, HeadsUp, HeadsUpOut
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.testing import FakeClock

NOW = 2_000_000_000
HOUR = 3600


def put(world: World, n: int, dept: str, status: str, *, ended: int | None = None, created: int | None = None, outcome: str = "",
        last_event: int | None = None, started: int | None = None, parent: str | None = None, stopped_by: str | None = None,
        title: str | None = None) -> str:
    task = world.task(n, dept, status, created=created if created is not None else (ended or NOW) - HOUR, with_step=False, title=title)
    settings = json.dumps({STOP_KEY: stopped_by}) if stopped_by else "{}"
    world.sql("UPDATE tasks SET ended_at = ?, outcome = ?, last_event_at = ?, started_at = ?, parent_task_id = ?, settings_json = ? WHERE id = ?",
              ended, outcome, last_event, started, parent, settings, task)
    return task


def kinds(items):
    return [(i.kind, i.task_id) for i in items]


def test_a_crash_of_two_hours_ago_is_a_problem_with_try_again_and_one_of_25_hours_ago_is_gone(db, clock):
    world = World(db, clock)
    recent = put(world, 1, "web", "crashed", ended=NOW - 2 * HOUR, outcome="The team stopped unexpectedly.", title="Landing page")
    put(world, 2, "sales", "crashed", ended=NOW - 25 * HOUR)
    [item] = HeadsUp(db).items(NOW)
    assert (item.kind, item.tone, item.task_id, item.retry, item.since_s) == ("problem", "err", recent, True, 2 * HOUR)
    assert item.text == 'Web ran into a problem on "Landing page"' and item.outcome == "The team stopped unexpectedly."
    assert item.dept_name == "Web" and item.status == "crashed" and item.at.endswith("Z")


def test_a_retried_crash_leaves_the_lane_and_so_does_one_the_owner_wrote_to_the_team_after(db, clock):
    world = World(db, clock)
    first = put(world, 1, "web", "crashed", ended=NOW - 3 * HOUR)
    put(world, 2, "web", "running", created=NOW - 2 * HOUR, parent=first, last_event=NOW - 10)
    other = put(world, 3, "sales", "crashed", ended=NOW - 3 * HOUR)
    put(world, 4, "sales", "done", created=NOW - 2 * HOUR, ended=NOW - HOUR)
    lane = HeadsUp(db).items(NOW)
    assert all(i.task_id not in (first, other) for i in lane)


def test_a_newer_task_made_before_the_crash_does_not_hide_it(db, clock):
    world = World(db, clock)
    crashed = put(world, 1, "web", "crashed", created=NOW - 5 * HOUR, ended=NOW - HOUR)
    put(world, 2, "web", "cancelled", created=NOW - 4 * HOUR, ended=NOW - HOUR)       # made while the first still ran
    assert kinds(HeadsUp(db).items(NOW)) == [("problem", crashed)]


def test_the_owners_own_stop_is_never_listed_and_a_stop_the_owner_did_not_ask_for_is(db, clock):
    world = World(db, clock)
    put(world, 1, "web", "stopped", ended=NOW - HOUR, outcome="Stopped: stopped on request", stopped_by="owner")
    put(world, 2, "sales", "stopped", ended=NOW - HOUR, outcome="stopped by you")
    put(world, 3, "web", "stopped", ended=NOW - HOUR, outcome="reset by you", created=NOW - 2 * HOUR + 1)
    closed = put(world, 4, "sales", "stopped", ended=NOW - HOUR + 5, outcome="Stopped: stopped on request",
                 stopped_by="app", created=NOW - HOUR + 1, title="Quote")
    [item] = HeadsUp(db).items(NOW)
    assert (item.task_id, item.kind, item.tone, item.retry) == (closed, "problem", "stop", True)
    assert item.text == 'Sales was working on "Quote" when the app closed'


def test_a_crash_while_the_app_was_closed_reads_that_way(db, clock):
    world = World(db, clock)
    put(world, 1, "web", "crashed", ended=NOW - 60, outcome="the app was closed while it ran", title="Menu")
    assert HeadsUp(db).items(NOW)[0].text == 'Web was working on "Menu" when the app closed'


def test_finished_work_is_a_quiet_fyi_and_left_open_offers_try_again_until_replaced(db, clock):
    world = World(db, clock)
    done = put(world, 1, "web", "done", ended=NOW - 3 * HOUR, title="Menu")
    left = put(world, 2, "sales", "done_with_open_items", ended=NOW - 2 * HOUR, title="Quote")
    put(world, 3, "web", "done", ended=NOW - WINDOW_S - 1)
    lane = HeadsUp(db).items(NOW)
    assert kinds(lane) == [("finished", left), ("finished", done)]               # newest first
    assert [(i.tone, i.retry, i.text) for i in lane] == [
        ("warn", True, 'Sales finished "Quote" with some things left open'), ("ok", False, 'Web finished "Menu"')]
    put(world, 4, "sales", "queued", created=NOW - HOUR)
    assert [i.retry for i in HeadsUp(db).items(NOW) if i.task_id == left] == [False]


def test_a_running_team_goes_quiet_after_ten_minutes_without_an_event_and_clears_itself(db, clock):
    world = World(db, clock)
    quiet = put(world, 1, "web", "running", last_event=NOW - 11 * 60, started=NOW - HOUR, title="Menu")
    put(world, 2, "sales", "running", last_event=NOW - 9 * 60, started=NOW - HOUR)
    [item] = HeadsUp(db).items(NOW)
    assert (item.kind, item.tone, item.task_id, item.retry, item.since_s) == ("quiet", "warn", quiet, False, 11 * 60)
    assert item.text == 'Web has gone quiet on "Menu": no sign of work for 11 minutes'
    world.sql("UPDATE tasks SET last_event_at = ? WHERE id = ?", NOW - 5, quiet)
    assert HeadsUp(db).items(NOW) == []
    assert QUIET_AFTER_S == 600


def test_a_team_waiting_for_the_owner_is_not_quiet_it_is_in_needs_you(db, clock):
    world = World(db, clock)
    put(world, 1, "web", "waiting_user", last_event=NOW - 5 * HOUR, started=NOW - 6 * HOUR)
    assert HeadsUp(db).items(NOW) == []


def test_order_is_problems_then_quiet_then_finished_and_hostile_names_stay_one_line(db, clock):
    world = World(db, clock)
    fin = put(world, 1, "web", "done", ended=NOW - 60)
    old_crash = put(world, 2, "sales", "crashed", ended=NOW - 5 * HOUR)
    quiet = put(world, 3, "web", "running", last_event=NOW - HOUR, started=NOW - 2 * HOUR, created=NOW - 30)
    new_crash = put(world, 4, "sales", "crashed", ended=NOW - HOUR, created=NOW - 7 * HOUR, title="a\nb\t<c>")
    lane = HeadsUp(db).items(NOW)
    assert kinds(lane) == [("problem", new_crash), ("problem", old_crash), ("quiet", quiet), ("finished", fin)]
    assert lane[0].title == "a b <c>"
    assert all(HeadsUpOut.model_validate(i.model_dump(mode="json")) == i for i in lane)


# ---- the real stop paths --------------------------------------------------------------------------------------------------------------

def test_the_owner_pressing_stop_marks_the_task_and_it_is_never_listed(tenv):  # noqa: F811
    task = tenv.started()
    tenv.run(tenv.service.stop(task))
    assert json.loads(tenv.one("SELECT settings_json FROM tasks WHERE id = ?", task))[STOP_KEY] == "owner"
    assert HeadsUp(tenv.db).items(tenv.row(task).ended_at + 5) == []
    assert tenv.row(task).settings.get(STOP_KEY) is None                     # a reserved key: never part of the task's J2 settings


def test_closing_the_app_marks_the_live_tasks_and_they_come_back_with_try_again(tenv):  # noqa: F811
    a = tenv.started()
    ask(tenv, a)
    tenv.run(tenv.service.shutdown())
    row = tenv.row(a)
    assert row.status == "stopped"
    [item] = HeadsUp(tenv.db).items(row.ended_at + 60)
    assert (item.task_id, item.kind, item.retry) == (a, "problem", True)
    assert item.text.endswith("when the app closed")


def test_a_crash_then_try_again_clears_the_row(tenv):  # noqa: F811
    task = tenv.started()
    tenv.projector.mark_ended(task, "crashed", "boom")
    ended = tenv.row(task).ended_at
    assert kinds(HeadsUp(tenv.db).items(ended + 1)) == [("problem", task)]
    retried = tenv.run(tenv.service.retry(task))
    assert retried.parent_task_id == task
    assert all(i.task_id != task for i in HeadsUp(tenv.db).items(ended + 2))


# ---- the route ---------------------------------------------------------------------------------------------------------------------------

def test_get_heads_up_is_a_read_without_a_token_in_the_response_model(db, clock, settings):
    world = World(db, clock)
    crashed = put(world, 1, "web", "crashed", ended=NOW - HOUR)
    app = FastAPI()
    services = Services(settings=settings, version="test", db=db, redact=Redactor(None, environ={}), clock=FakeClock(start=NOW, step=0))
    services.chats = ChatStore(db)
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(chat_api.build_router())
    client = TestClient(app, base_url="http://127.0.0.1:8780")
    response = client.get("/api/heads-up")
    assert response.status_code == 200
    [body] = response.json()
    assert HeadsUpOut.model_validate(body).task_id == crashed and body["since_s"] == HOUR
    assert set(body) == {"kind", "tone", "task_id", "dept_id", "dept_name", "title", "status", "text", "outcome", "at", "since_s", "retry"}
