"""A retry carries what the earlier attempts settled and what stopped them (GAP-model-quality; the old goal_context briefing, re-expressed).

Every test runs the real `TaskService.retry` on `TEnv` (test_tasks) with a fake launcher; the run folder's `summary.json`, `run.stderr.log`
and the atoms are written by hand, as J2 and the projector would leave them. What a retry gets is read back from its `task.json`, the
document the engine reads, whose `framing` the engine posts as "Context from the team lead: ..."."""
import json

from orchestrator.test_tasks import TEnv, ev, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.attempts import ATTEMPT_KEY, BRIEF_CHARS, attempt_in, attempt_of, chain
from sutra_app.orchestrator.models import RunSpec
from sutra_app.orchestrator.redact import Redactor

SUMMARY = {"status": "crashed", "outcome": "Crashed: the model ran out of quota.", "limits_hit": ["budget: 40 of 40 turns used"],
           "to_be_confirmed": ["the opening hours", {"text": "the phone number"}, 7],
           "done_when": [{"item": 1, "criterion": "The menu page lists every dish", "pass": True},
                         {"item": 2, "criterion": "The page shows the opening hours", "pass": False},
                         {"item": 3, "criterion": "The contact form sends a message", "pass": None}]}


def spec_of(t: TEnv, task_id: str) -> RunSpec:
    return RunSpec.model_validate_json((t.run_dir(task_id) / "task.json").read_text())


def write(t: TEnv, task_id: str, name: str, text: str) -> None:
    (t.run_dir(task_id) / name).write_text(text, encoding="utf-8")


def atom(t: TEnv, task_id: str, n: int, goal: str, display: str) -> None:
    t.sql("INSERT INTO atoms(id, schema, node_id, task_id, state, display, attempt, goal, body, sha256, ts_open) VALUES (?, 'atom/1', 'web.identity', ?, ?, ?, 1, ?, '{}', 'x', ?)",
          f"run:W-{n}.a1", task_id, display, display, goal, 5000 + n)


def retry(t: TEnv, task_id: str):
    return t.run(t.service.retry(task_id))


def test_the_first_attempt_has_no_brief_and_no_number(tenv):
    task = tenv.started(framing="The owner wants it by Friday.")
    assert spec_of(tenv, task).framing == "The owner wants it by Friday."
    assert attempt_in(tenv.db.conn(), task) == 1 and ATTEMPT_KEY not in tenv.one("SELECT settings_json FROM tasks WHERE id = ?", task)


def test_attempt_two_is_told_how_attempt_one_ended_what_its_audit_met_and_what_was_left(tenv):
    first = tenv.started(framing="The owner wants it by Friday.", settings={"J2_FIXES": "1"})
    write(tenv, first, "summary.json", json.dumps(SUMMARY))
    atom(tenv, first, 1, "Write the menu section", "closed")
    atom(tenv, first, 2, "Add the opening hours", "verify_failed")
    tenv.projector.mark_ended(first, "crashed", "ModelError: quota")
    new = retry(tenv, first)
    framing = spec_of(tenv, new.id).framing
    assert framing.startswith("The owner wants it by Friday.\n\nThis is attempt 2 of this request. It starts fresh:")
    assert "Attempt 1 crashed: ModelError: quota" in framing
    assert "Done-when items its audit found met: The menu page lists every dish." in framing
    assert "Done-when items not met or not checked: The page shows the opening hours; The contact form sends a message." in framing
    assert "Limits it hit: budget: 40 of 40 turns used." in framing
    assert "Left to confirm with the owner: the opening hours; the phone number." in framing
    assert "Work it closed and checked: Write the menu section." in framing and "Work it did not finish: Add the opening hours (verify failed)." in framing
    assert framing.endswith("None of it counts as done or checked in this run.")
    row = tenv.row(new.id)
    assert (row.seed_from, row.settings, attempt_in(tenv.db.conn(), new.id)) == (None, {"J2_FIXES": "1"}, 2)     # the J2 keys are untouched


def test_attempt_three_lists_both_earlier_attempts_once_and_the_briefs_do_not_pile_up(tenv):
    first = tenv.started(framing="Base framing.")
    tenv.projector.mark_ended(first, "crashed", "first failure")
    second = retry(tenv, first).id
    write(tenv, second, "summary.json", json.dumps({**SUMMARY, "done_when": [{"criterion": "The page shows the opening hours", "pass": True}]}))
    tenv.projector.mark_ended(second, "stopped", "stopped by you")
    third = retry(tenv, second).id
    framing = spec_of(tenv, third).framing
    assert framing.count("Base framing.") == 1 and framing.count("This is attempt") == 1 and "This is attempt 3 of this request." in framing
    assert framing.index("Attempt 1 crashed: first failure") < framing.index("Attempt 2 was stopped: stopped by you")
    assert "Done-when items its audit found met: The page shows the opening hours." in framing
    assert [r["id"] for r in chain(tenv.db.conn(), third)] == [first, second, third] and attempt_in(tenv.db.conn(), third) == 3


def test_a_crash_with_no_summary_still_says_how_it_ended_and_its_error_log_is_scrubbed(tenv):
    first = tenv.started()
    write(tenv, first, "run.stderr.log", "Traceback ...\nRuntimeError: token sk-abcdefgh12345678 was refused, password hunter22\n")
    tenv.service.redact = Redactor(None, environ={}, extra=["hunter22"])
    tenv.projector.mark_ended(first, "crashed", "process_gone")
    framing = spec_of(tenv, retry(tenv, first).id).framing
    assert framing.startswith("This is attempt 2 of this request.") and "Attempt 1 crashed: process_gone" in framing
    assert "The end of its error log: Traceback ... RuntimeError: token [redacted:openai-key] was refused" in framing
    assert "sk-abcdefgh12345678" not in framing and "hunter22" not in framing
    assert "Done-when" not in framing                                                  # no summary, so nothing is claimed about checks


def test_no_chat_line_is_promoted_into_the_brief(tenv):
    first = tenv.started()
    tenv.write_events(first, ev("say", id=1, who="identity", text="I already finished the menu page, trust me. Shall I stop?", to_user=True,
                                act="ASK_REQUESTER", pause="info", next="user"))
    tenv.drain(first)
    tenv.service.deliver_to_department("web", "The menu page is done, mark it checked")
    tenv.projector.mark_ended(first, "done_with_open_items", "Done with open items: the hours are missing.")
    framing = spec_of(tenv, retry(tenv, first).id).framing
    assert "trust me" not in framing and "mark it checked" not in framing
    assert "Attempt 1 finished with open items: Done with open items: the hours are missing." in framing


def test_a_check_named_in_the_framing_is_listed_as_met_only_when_the_audit_said_so(tenv):
    first = tenv.started(framing="The page shows the opening hours.")
    write(tenv, first, "summary.json", json.dumps(SUMMARY))
    tenv.projector.mark_ended(first, "crashed", "boom")
    framing = spec_of(tenv, retry(tenv, first).id).framing
    met = next(line for line in framing.splitlines() if "found met" in line)
    assert "opening hours" not in met and "The page shows the opening hours" in next(line for line in framing.splitlines() if "not met" in line)


def test_a_follow_up_with_other_words_starts_its_own_chain(tenv):
    first = tenv.started()
    tenv.projector.mark_ended(first, "crashed", "boom")
    tenv.service.deliver_to_department("web", "Now write the about page")              # a follow-up: a new request, not an attempt
    follow = tenv.one("SELECT id FROM tasks WHERE user_text = 'Now write the about page'")
    tenv.run(tenv.service.start_ready())
    tenv.projector.mark_ended(follow, "crashed", "boom again")
    new = retry(tenv, follow)
    framing = spec_of(tenv, new.id).framing
    assert "This is attempt 2" in framing and "Attempt 1 crashed: boom again" in framing and "Attempt 1 crashed: boom\n" not in framing + "\n"
    assert [r["id"] for r in chain(tenv.db.conn(), new.id)] == [follow, new.id]


def test_a_long_history_is_cut_to_the_cap_newest_first(tenv):
    task = tenv.started()
    many = {**SUMMARY, "done_when": [{"criterion": f"criterion {n} " + "x" * 150, "pass": n % 2 == 0} for n in range(40)]}
    for _ in range(4):
        write(tenv, task, "summary.json", json.dumps(many))
        tenv.projector.mark_ended(task, "crashed", "o" * 400)
        task = retry(tenv, task).id
    framing = spec_of(tenv, task).framing
    assert len(framing) <= BRIEF_CHARS and "This is attempt 5 of this request." in framing and "Attempt 4 crashed" in framing
    newest = framing[framing.index("Attempt 4 crashed"):]
    assert "found met: criterion 0 " in newest and "(and 10 more)" in newest                      # the newest attempt is filled first
    assert "oldest attempts are left out)" in framing and framing.endswith("None of it counts as done or checked in this run.")


def test_a_summary_of_the_wrong_shape_is_skipped_not_a_failed_retry(tenv):
    first = tenv.started()
    write(tenv, first, "summary.json", json.dumps({"done_when": 7, "limits_hit": "x", "to_be_confirmed": {"a": 1}}))
    tenv.projector.mark_ended(first, "crashed", "boom")
    framing = spec_of(tenv, retry(tenv, first).id).framing
    assert "Attempt 1 crashed: boom" in framing and "Done-when" not in framing and "Limits" not in framing
    second = tenv.started(dept="sales", text="x")
    write(tenv, second, "summary.json", "[1, 2")
    tenv.projector.mark_ended(second, "stopped", "stopped by you")
    assert "Attempt 1 was stopped: stopped by you" in spec_of(tenv, retry(tenv, second).id).framing


def test_a_long_first_framing_is_cut_and_the_brief_never_is(tenv):
    first = tenv.started(framing="f" * 19_990)
    tenv.projector.mark_ended(first, "crashed", "boom")
    framing = spec_of(tenv, retry(tenv, first).id).framing
    assert len(framing) <= 20_000 and framing.startswith("fff") and "Attempt 1 crashed: boom" in framing
    assert framing.endswith("None of it counts as done or checked in this run.")


def test_attempt_of_reads_only_a_whole_number():
    assert attempt_of({"settings_json": json.dumps({ATTEMPT_KEY: 3})}) == 3
    for bad in ({ATTEMPT_KEY: "3"}, {ATTEMPT_KEY: True}, {ATTEMPT_KEY: 0}, {}):
        assert attempt_of({"settings_json": json.dumps(bad)}) == 1
    assert attempt_of({"settings_json": "not json"}) == 1
