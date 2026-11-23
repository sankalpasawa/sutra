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


# ---- the card of an attempt the project replaced (D400, M-C, run 3) --------------------------------------------------------------------------------

def org_lines(rig):
    out = []
    for r in rig.sql("SELECT kind, text, card_json FROM chat_messages WHERE session_id = 'cs_org' ORDER BY id").fetchall():
        out.append((r["kind"], r["text"], json.loads(r["card_json"]) if r["card_json"] else None))
    return out


def test_a_graceful_quit_posts_no_stopped_card_for_the_attempt_the_project_restarts_and_the_next_card_links(rig):
    from orchestrator.test_reconcile_projects import engine_answers_the_stop, running
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    engine_answers_the_stop(rig, tasks)
    rig.t.run(rig.t.service.shutdown())
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["attempt"] == 2 and node["task_id"] != tasks["a1"] and rig.project(reservation.project_id)["status"] == "running"
    lines = org_lines(rig)
    stopped_cards = [c for kind, _, c in lines if c and c.get("type") == "done" and c["task_id"] == tasks["a1"]]
    assert stopped_cards == [], "no 'Your Web team stopped' for an attempt that starts again"
    notes = [text for kind, text, _ in lines if kind == "note" and "starts again" in text]
    assert len(notes) == 1 and "The app was closed" in notes[0] and f"/p/{reservation.project_id}" in notes[0] and "stopped on request" not in notes[0]
    rig.start()
    rig.go(node["task_id"])
    rig.finish(node["task_id"], outcome="Done: the page is built")
    [card] = [c for kind, _, c in org_lines(rig) if c and c.get("type") == "done" and c["task_id"] == node["task_id"]]
    assert card["project_id"] == reservation.project_id and card["outcome"] == "Done: the page is built"


def test_an_attempt_the_project_retries_has_a_link_and_no_stopped_card_either(rig):
    from orchestrator.test_reconcile_projects import running
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.finish(tasks["a1"], status="crashed", outcome="it really crashed", handoff=False)          # the project's one retry makes attempt 2
    assert rig.sql("SELECT attempt FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0] == 2
    lines = org_lines(rig)
    assert [c for _, _, c in lines if c and c.get("type") == "done" and c["task_id"] == tasks["a1"]] == []
    assert any(kind == "note" and "This try ended, so" in text and reservation.project_id in text for kind, text, _ in lines)


def test_a_step_whose_project_is_over_keeps_its_done_card_with_the_link(rig):
    from orchestrator.test_reconcile_projects import running
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET status = 'stopped', stop_reason = 'stopped by you' WHERE id = ?", reservation.project_id)
    rig.finish(tasks["a1"], status="stopped", outcome="Stopped: stopped on request", handoff=False)
    [card] = [c for _, _, c in org_lines(rig) if c and c.get("type") == "done" and c["task_id"] == tasks["a1"]]
    assert card["project_id"] == reservation.project_id and card["outcome"] == "You stopped it"


# ---- a step that waits for an answer to the engine's own question (D401, run 3 item 2) --------------------------------------------------------------

QUESTION = ("The same mistake in the closing notes came back twice. Do you want the team to keep working on those notes, or take the report as it is now?\n"
            "Option 1: keep working on the notes\nOption 2: take the report as it is now")


def ask_in_step(rig, task_id):
    session = rig.sql("SELECT id FROM chat_sessions WHERE kind = 'department' LIMIT 1").fetchone()[0]
    rig.sql("UPDATE tasks SET status = 'waiting_user' WHERE id = ?", task_id)
    rig.sql("INSERT INTO chat_messages(session_id, role, who, kind, text, task_id, state, at) VALUES (?, 'agent', 'Audit', 'question', ?, ?, 'ok', ?)", session, QUESTION, task_id, BASE + 9)
    return session


def test_the_snapshot_carries_the_question_a_waiting_step_asked_and_none_when_nothing_waits(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    assert rig.projects.snapshot(reservation.project_id)["questions"] == []
    rig.start()
    rig.go(tasks["a1"])
    session = ask_in_step(rig, tasks["a1"])
    [q] = rig.projects.snapshot(reservation.project_id)["questions"]
    node = rig.node_of(tasks["a1"])
    assert q["node_id"] == node["id"] and q["session_id"] == session and q["options"] == ["keep working on the notes", "take the report as it is now"]
    assert q["text"].startswith("The same mistake in the closing notes")
    rig.sql("UPDATE chat_messages SET answered_by = 1 WHERE kind = 'question'")
    assert rig.projects.snapshot(reservation.project_id)["questions"] == [], "an answered question is gone"


def test_decide_for_me_never_answers_an_engine_question_about_finishing_as_it_is():
    from sutra_app.orchestrator.gatekeeper import decide_for_me_answer
    for kind in ("question", "engine_question", "finish_as_is", "chat_question"):
        assert decide_for_me_answer(kind, None) is None, kind


# ---- the engine's "done with open items" in the owner's words (D402, run 3 item 3) -----------------------------------------------------------------

OPEN = ("Done with open items: shipped as is on the Requester's decision (the owner chose to finish). "
        "Still not workable: document rubric PJ-4 (NEEDS_REVISION) the closing notes repeat a mistake.")


def test_the_engines_open_items_sentence_is_said_in_plain_words():
    said = plain_outcome(OPEN)
    assert said == "Done, with some things still open. You chose to take it as it is. Still open: the closing notes repeat a mistake."
    for engine_word in ("rubric", "PJ-4", "NEEDS_REVISION", "Requester", "shipped as is"):
        assert engine_word not in said
    assert plain_outcome("Done with open items: shipped as is on the Requester's decision (x).") == "Done, with one thing still open. You chose to take it as it is."
    assert plain_outcome("Done with open items: Still not workable: site rubric W-2 (FAILED_CHECK)") == "Done, with one thing still open."
    assert plain_outcome("Done: everything is in") == "Done: everything is in" and plain_outcome("Done with some things left") == "Done with some things left"


def test_the_done_card_of_a_step_that_finished_with_open_items_says_it_plainly(rig):
    from orchestrator.test_reconcile_projects import running
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.finish(tasks["a1"], status="done_with_open_items", outcome=OPEN)
    [card] = [c for _, _, c in org_lines(rig) if c and c.get("type") == "done" and c["task_id"] == tasks["a1"]]
    assert card["outcome"].startswith("Done, with some things still open.") and "rubric" not in card["outcome"] and card["project_id"] == reservation.project_id
    assert rig.t.row(tasks["a1"]).outcome.startswith("Done with open items"), "the record keeps the engine's words"


# ---- a real short title, and the whole request on the page (D404, run 3 item 5) -----------------------------------------------------------------------

def test_a_project_title_is_a_whole_phrase_never_cut_inside_a_word_or_left_dangling():
    from sutra_app.orchestrator.textutil import project_title
    req = "Do two separate read-only jobs in this folder and change nothing. Step 1: list the files. Run them as two steps, one after the other, then give me both answers."
    assert project_title(req) == "Do two separate read-only jobs in this folder and change\u2026", "the first sentence is 63 characters: a clean cut, not 80 cut mid-sentence"
    assert project_title("Review every file in the folder. Then write the gaps.") == "Review every file in the folder"
    assert project_title("A page and a quote") == "A page and a quote"
    long = "Make a complete review of every file in the folder and write what each one is for and then what is missing from it and after that one"
    title = project_title(long)
    assert title.endswith("…") and len(title) <= 61 and not title[:-1].endswith((" and", " then", " after")) and long.startswith(title[:-1])
    assert project_title("x" * 100).endswith("…") and len(project_title("x" * 100)) <= 61
    assert project_title("  Tidy   up\nthe notes  ") == "Tidy up the notes"
    assert project_title("") == ""


def test_the_snapshot_carries_the_whole_request_for_the_page(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], request_id="req-5")
    rig.sql("INSERT INTO chat_messages(id, session_id, role, who, kind, text, state, at) VALUES (5, 'cs_org', 'user', 'user', 'text', ?, 'ok', ?)", "Do two jobs. Then the second. " * 5, BASE)
    assert rig.projects.snapshot(reservation.project_id)["request"].startswith("Do two jobs. Then the second.")
    assert rig.projects.snapshot(reservation.project_id)["request"] == "Do two jobs. Then the second. " * 5


def test_without_a_found_request_the_snapshot_says_nothing_rather_than_guessing(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], request_id="req-999")
    assert rig.projects.snapshot(reservation.project_id)["request"] == ""


# ---- the repository's own files are not a step's tool rows (D405, run 3 item 6) ----------------------------------------------------------------------

def test_a_read_inside_dot_git_is_no_tool_row_and_an_ordinary_file_still_is():
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/work/proj/.git/HEAD"}}) is None
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/work/proj/.git/COMMIT_EDITMSG"}}) is None
    assert tool_audit.facts({"name": "Glob", "input": {"path": "C:\\work\\proj\\.git\\refs"}}) is None
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/work/proj/.github/ci.yml"}}) == ("Read", "read", "ci.yml"), ".github is not .git"
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/work/proj/HEAD"}}) == ("Read", "read", "HEAD"), "a file of the owner's own called HEAD is a file"
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/work/proj/README.md"}}) == ("Read", "read", "README.md")
