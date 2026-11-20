"""The words and links of a step's own cards (D394): a done card of a project step links to the project and says how it was stopped in the owner's words; the engine's pseudo-tool is no tool row; the
grant line has no 'tools none' next to the run tools; the project is titled by the request."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.connectors import tool_audit
from sutra_app.orchestrator.grants import StepRequest, intersect
from sutra_app.orchestrator.stopwords import plain_outcome, plain_stop

BASE = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def done_cards(rig):
    cards = [json.loads(r["card_json"]) for r in rig.sql("SELECT card_json FROM chat_messages WHERE kind = 'card'").fetchall()]
    return [c for c in cards if c.get("type") == "done"]


def test_the_engines_pseudo_tool_is_not_a_tool_row():
    assert tool_audit.facts({"name": "PROPOSE", "input": {}}) is None
    assert tool_audit.facts({"name": "StructuredOutput", "input": {}}) is None
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/x/a.txt"}}) == ("Read", "read", "a.txt")


def test_a_stop_is_said_as_the_owner_knows_it():
    assert plain_stop("stopped by the kill switch") == "The kill switch was used"
    assert plain_stop("stopped by you") == "You stopped it"
    assert plain_stop("stopped: the project ran longer than 120 minutes") == "The project ran longer than 120 minutes"
    assert plain_outcome("Stopped: stopped on request", "stopped by the kill switch") == "The kill switch was used"
    assert plain_outcome("Stopped: stopped on request", "") == "It was stopped before it finished"
    assert plain_outcome("waiting task Describe the files did not finish") == "The step before it did not finish"
    assert plain_outcome("Done: it works") == "Done: it works", "a step's own words are shown as they are"


def test_the_done_card_of_a_stopped_step_links_to_its_project_and_says_who_stopped_it(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.start()
    rig.go(tasks["a1"])
    rig.sql("UPDATE projects SET status = 'stopped', stop_reason = 'stopped by the kill switch' WHERE id = ?", reservation.project_id)
    rig.finish(tasks["a1"], status="stopped", outcome="Stopped: stopped on request", handoff=False)
    [card] = [c for c in done_cards(rig) if c["task_id"] == tasks["a1"]]
    assert card["project_id"] == reservation.project_id and card["outcome"] == "The kill switch was used"
    assert "stopped on request" not in json.dumps(card)
    assert rig.t.row(tasks["a1"]).outcome == "Stopped: stopped on request", "the record keeps what the engine said"


def test_the_done_card_of_a_finished_step_links_and_keeps_its_words_and_an_ordinary_task_has_no_project(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], outcome="Done: the page is built")
    [card] = [c for c in done_cards(rig) if c["task_id"] == tasks["a1"]]
    assert card["project_id"] == reservation.project_id and card["outcome"] == "Done: the page is built"


def test_an_ordinary_run_has_no_project_key_on_its_done_card(db, settings, clock, events):
    from orchestrator.test_tasks import tenv_with
    from sutra_app.orchestrator.testing.fake_engine import FakeLauncher, ev
    t = tenv_with(db, settings, clock, events, nodes_v1=False, launcher=FakeLauncher({"*": [{"hold": True}]}))
    task = t.new("web", "A page")
    t.run(t.service.start_ready())
    t.write_events(task.id, ev("run.started", pid=t.row(task.id).pid, schema="events/1", mock=True, seed="none"))
    t.drain(task.id)
    t.write_events(task.id, ev("run.ended", status="stopped", outcome="Stopped: stopped on request"))
    t.drain(task.id)
    cards = [json.loads(r["card_json"]) for r in t.db.conn().execute("SELECT card_json FROM chat_messages WHERE kind = 'card'")]
    done = [c for c in cards if c.get("type") == "done"]
    assert done and all("project_id" not in c for c in done) and done[0]["outcome"] == "Stopped: stopped on request"


def test_the_grant_line_has_no_tools_none_beside_the_run_tools_and_keeps_the_app_tools_when_there_are_some():
    plain = intersect("worker", StepRequest(), "edit", "read").describe()
    assert "tools none" not in plain and plain.startswith("tiers 0,1; folder read; scope none; commands none; run_tools engine (")
    with_apps = intersect("worker", StepRequest(tool_profile="sutra"), "edit", "edit").describe()
    assert "tools sutra;" in with_apps
