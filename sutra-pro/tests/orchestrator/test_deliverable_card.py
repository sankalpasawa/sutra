"""What a run left for the owner reaches the team's chat (D135): the engine host writes `deliverable.json` before `run.ended`; when the Projector applies
`run.ended` it posts ONE `deliverable` card to the team's chat (the report as the team wrote it, the files git saw change in the owner's folder, the link to the
whole report) and the done card in the org chat gets the same link. `TEnv` (test_tasks) runs the real Projector over a fake launcher; the files are written by hand."""
import json
import os

import pytest
from orchestrator.test_tasks import TEnv, ev, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.deliverable import RECORD_NAME, read_deliverable
from sutra_app.orchestrator.models import (DELIVERABLE_FILES_MAX, DELIVERABLE_TEXT_MAX, ChatMessageOut, DeliverableCard, DoneCard, DoneReport,
                                           DeliverableChanges)

REPORT = ("# The project\n\n## Findings\n\n- The settings page is `ui/pages/settings.html`.\n\n## Changes\n\n- `README.md`: added the line.\n\n"
          "## Confirmation\n\nRead README.md and `git diff`.\n\n## Open items\n\n- Nothing.\n\n## Outcome\n\nREADME.md now ends with the line.\n")
RECORD = {"schema": "deliverable/1", "output": "project", "label": "Project work report", "file": "project.md"}


def leave(folder, report=REPORT, **record):
    """What the host leaves in a run folder at the end of a run: the report and the record."""
    if report is not None:
        (folder / "project.md").write_text(report, encoding="utf-8")
    (folder / RECORD_NAME).write_text(json.dumps({**RECORD, **record}), encoding="utf-8")


def team_session(t: TEnv) -> str:
    return t.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")


def deliverables(t: TEnv) -> list:
    return [m for m in t.chats.messages(team_session(t)) if m.card is not None and m.card.type == "deliverable"]


def done_card(t: TEnv):
    return next(m.card for m in reversed(t.chats.messages("cs_org")) if m.card is not None and m.card.type == "done")


def finish(t: TEnv, task_id: str, status="done", outcome="Done: the project work report is workable."):
    t.write_events(task_id, ev("run.ended", status=status, outcome=outcome, at="2026-11-04T10:07:00Z"))
    t.drain(task_id)


# ---- the Projector ----------------------------------------------------------------------------------------------------------------------------
def test_a_finished_run_posts_one_card_to_the_teams_chat_with_the_report_the_files_and_the_link(tenv):
    task = tenv.started()
    leave(tenv.run_dir(task), changes={"files": [{"path": "README.md", "status": "modified"}, {"path": "docs/NEW.md", "status": "new"}], "more": 2})
    finish(tenv, task)
    posted = deliverables(tenv)
    assert len(posted) == 1
    message, row = posted[0], tenv.row(task)
    assert (message.role, message.who, message.kind, message.text) == ("agent", "sutra", "card", "")
    card = message.card
    assert isinstance(card, DeliverableCard) and (card.task_id, card.run_id, card.dept_id) == (task, row.run_id, "web")
    assert (card.label, card.file, card.cut) == ("Project work report", "project.md", False) and card.text == REPORT.strip()
    assert [(f.path, f.status) for f in card.changes.files] == [("README.md", "modified"), ("docs/NEW.md", "new")] and card.changes.more == 2
    assert message.task_id == task and message.session_id == team_session(tenv)


def test_the_done_card_in_the_org_chat_gets_the_link_to_the_report(tenv):
    task = tenv.started()
    leave(tenv.run_dir(task))
    finish(tenv, task)
    assert done_card(tenv).report == DoneReport(dept_id="web", run_id=tenv.row(task).run_id, label="Project work report")
    assert not [m for m in tenv.chats.messages("cs_org") if m.card is not None and m.card.type == "deliverable"]      # the report is the team's chat's, not the org chat's


def test_a_run_that_left_nothing_posts_nothing_and_its_done_card_keeps_the_shape_it_always_had(tenv):
    task = tenv.started()
    finish(tenv, task)
    assert deliverables(tenv) == [] and done_card(tenv).report is None
    assert "report" not in done_card(tenv).model_dump(mode="json")


def test_replaying_the_end_posts_nothing_more(tenv):
    task = tenv.started()
    leave(tenv.run_dir(task), changes={"files": [], "more": 0})
    finish(tenv, task)
    first = deliverables(tenv)[0].card
    tenv.sql("UPDATE tasks SET events_offset = 0 WHERE id = ?", task)
    tenv.drain(task)
    assert len(deliverables(tenv)) == 1 and deliverables(tenv)[0].card == first


def test_git_looked_and_nothing_changed_is_kept_as_an_empty_list_and_no_git_is_no_key(tenv):
    task = tenv.started()
    leave(tenv.run_dir(task), changes={"files": [], "more": 0})
    finish(tenv, task)
    card = deliverables(tenv)[0].card
    assert card.changes == DeliverableChanges(files=[], more=0) and card.model_dump(mode="json")["changes"] == {"files": [], "more": 0}
    other = tenv.started()
    leave(tenv.run_dir(other))                                                                    # the host could not read git: no `changes` in the record
    finish(tenv, other)
    silent = deliverables(tenv)[-1].card
    assert silent.changes is None and "changes" not in silent.model_dump(mode="json")


def test_a_run_that_stopped_before_the_report_still_tells_the_owner_which_files_it_changed(tenv):
    task = tenv.started()
    leave(tenv.run_dir(task), report=None, changes={"files": [{"path": "README.md", "status": "modified"}], "more": 0})
    finish(tenv, task, status="stopped", outcome="Stopped: stopped on request")
    card = deliverables(tenv)[0].card
    assert card.text == "" and card.file == "" and [f.path for f in card.changes.files] == ["README.md"]
    assert done_card(tenv).report is None                                                         # no report to open


def test_a_crashed_run_posts_the_card_and_the_crash_line_stays_the_last_line(tenv):
    task = tenv.started()
    leave(tenv.run_dir(task), report=None, changes={"files": [{"path": "a.md", "status": "new"}], "more": 0})
    finish(tenv, task, status="crashed", outcome="Crashed: boom")
    kinds = [(m.kind, m.card.type if m.card is not None else None) for m in tenv.chats.messages(team_session(tenv))]
    assert kinds[-2:] == [("card", "deliverable"), ("error", None)]


def test_a_run_with_no_report_and_nothing_changed_has_nothing_to_show(tenv):
    task = tenv.started()
    leave(tenv.run_dir(task), report=None, changes={"files": [], "more": 0})
    finish(tenv, task, status="stopped", outcome="Stopped: stopped on request")
    assert deliverables(tenv) == []


def test_a_team_run_by_the_server_alone_ending_has_no_record_and_posts_nothing(tenv):
    task = tenv.started()
    tenv.projector.mark_ended(task, "crashed", "the process is gone")
    assert deliverables(tenv) == [] and done_card(tenv).report is None


def test_every_run_has_its_own_card_in_the_same_team_chat(tenv):
    first = tenv.started()
    leave(tenv.run_dir(first), changes={"files": [], "more": 0})
    finish(tenv, first)
    second = tenv.started()
    leave(tenv.run_dir(second), report=REPORT.replace("README", "CHANGELOG"), changes={"files": [{"path": "CHANGELOG.md", "status": "modified"}], "more": 0})
    finish(tenv, second)
    posted = deliverables(tenv)
    assert [m.card.task_id for m in posted] == [first, second] and "CHANGELOG" in posted[1].card.text


# ---- reading the record --------------------------------------------------------------------------------------------------------------------
def test_the_report_is_cut_at_a_line_end_and_says_so(tmp_path):
    long = "## Findings\n\n" + "".join(f"- finding {i} in `src/module_{i}.py`\n" for i in range(3000))
    leave(tmp_path, report=long)
    got = read_deliverable(tmp_path)
    assert got.cut is True and len(got.text) <= DELIVERABLE_TEXT_MAX == 30_000 and got.text.endswith(".py`") and got.has_report


def test_a_short_report_is_whole_and_control_characters_are_dropped(tmp_path):
    leave(tmp_path, report="## Findings\r\n\r\n- one\x00\x1b[31m red\r\n")
    got = read_deliverable(tmp_path)
    assert got.cut is False and got.text == "## Findings\n\n- one[31m red"                      # the line ends are plain, the escape and the null are gone


@pytest.mark.parametrize("record", [
    "not json", "[]", "3", '{"schema": "other/1", "file": "project.md"}', '{"file": "project.md"}', '{"schema": "deliverable/1", "file": 5}',
])
def test_a_record_that_is_not_ours_is_no_deliverable(tmp_path, record):
    (tmp_path / "project.md").write_text(REPORT, encoding="utf-8")
    (tmp_path / RECORD_NAME).write_text(record, encoding="utf-8")
    assert read_deliverable(tmp_path) is None


@pytest.mark.parametrize("name", ["../project.md", "/etc/passwd", "sub/project.md", "project.txt", "project.md/..", ".md", "", " project.md", "a" * 90 + ".md"])
def test_the_report_is_a_plain_markdown_file_name_and_never_a_path(tmp_path, name):
    (tmp_path.parent / "project.md").write_text("outside\n", encoding="utf-8")
    (tmp_path / "project.md").write_text(REPORT, encoding="utf-8")
    leave(tmp_path, report=None, file=name, changes={"files": [{"path": "a", "status": "new"}], "more": 0})
    got = read_deliverable(tmp_path)
    assert got is not None and got.text == "" and got.file == ""                                  # only the changed file is left to show


def test_a_link_is_never_followed_for_the_report_or_the_record(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("not the team's\n", encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    try:
        os.symlink(outside / "secret.md", run / "project.md")
    except (OSError, NotImplementedError):
        pytest.skip("no symbolic links here")
    (run / RECORD_NAME).write_text(json.dumps(RECORD), encoding="utf-8")
    assert read_deliverable(run) is None                                                          # a linked report is no report, and there is nothing else to show
    (run / RECORD_NAME).unlink()
    os.symlink(outside / "secret.md", run / RECORD_NAME)
    assert read_deliverable(run) is None


def test_rows_that_are_not_a_path_and_a_known_status_are_dropped_and_the_rest_counted(tmp_path):
    rows = [{"path": f"f{i}.md", "status": "new"} for i in range(DELIVERABLE_FILES_MAX + 5)]
    leave(tmp_path, changes={"files": [1, {"path": "a"}, {"path": 5, "status": "new"}, {"path": "  ", "status": "new"}, {"path": "b", "status": "weird"}, *rows], "more": 7})
    got = read_deliverable(tmp_path)
    assert len(got.changes.files) == DELIVERABLE_FILES_MAX == 100 and got.changes.more == 7 + 5
    for odd in ('"changes": 3', '"changes": {"files": "x"}', '"changes": {"more": 2}', '"changes": null'):
        (tmp_path / RECORD_NAME).write_text('{"schema": "deliverable/1", "file": "project.md", ' + odd + "}", encoding="utf-8")
        assert read_deliverable(tmp_path).changes is None and read_deliverable(tmp_path).has_report


def test_a_record_too_big_to_be_ours_is_ignored(tmp_path):
    (tmp_path / "project.md").write_text(REPORT, encoding="utf-8")
    (tmp_path / RECORD_NAME).write_text(json.dumps({**RECORD, "pad": "x" * 500_000}), encoding="utf-8")
    assert read_deliverable(tmp_path) is None


def test_the_label_is_a_clean_line_and_has_a_default(tmp_path):
    leave(tmp_path, label="Project\x00 work\n  report")
    assert read_deliverable(tmp_path).label == "Project work report"
    leave(tmp_path, label="")
    assert read_deliverable(tmp_path).label == "Report"
    assert read_deliverable(tmp_path / "missing") is None


# ---- the wire shapes -------------------------------------------------------------------------------------------------------------------------
def test_a_deliverable_card_is_a_chat_card_with_the_keys_it_has_and_no_others():
    card = {"type": "deliverable", "task_id": "tsk_b7c8d9e0f1a2", "run_id": "j2-20261104-100004-7f3a", "dept_id": "web", "label": "Project work report",
            "file": "project.md", "text": "## Findings\n\nx", "cut": False}
    assert json.loads(DeliverableCard.model_validate(card).model_dump_json()) == card
    with_changes = {**card, "changes": {"files": [{"path": "README.md", "status": "modified"}], "more": 0}}
    assert json.loads(DeliverableCard.model_validate(with_changes).model_dump_json()) == with_changes
    message = {"id": 9, "session_id": "cs_0123456789ab", "role": "agent", "who": "sutra", "kind": "card", "text": "", "card": with_changes, "pause": None,
               "answered_by": None, "task_id": None, "state": "ok", "at": "2026-11-04T10:00:00Z"}
    assert ChatMessageOut.model_validate(message).model_dump(mode="json") == message
    for bad in ({**card, "text": "x" * (DELIVERABLE_TEXT_MAX + 1)}, {**card, "changes": {"files": [{"path": "a", "status": "renamed"}]}},
                {**card, "run_id": "../x"}, {**card, "extra": 1}):
        with pytest.raises(Exception):
            DeliverableCard.model_validate(bad)


def test_a_done_card_with_a_report_carries_it_and_one_without_does_not():
    old = {"type": "done", "task_id": "tsk_b7c8d9e0f1a2", "dept_name": "Content", "title": "Menu page copy", "status": "done", "outcome": "Done."}
    assert DoneCard.model_validate(old).model_dump(mode="json") == old
    linked = {**old, "report": {"dept_id": "web", "run_id": "j2-20261104-100004-7f3a", "label": "Project work report"}}
    assert json.loads(DoneCard.model_validate(linked).model_dump_json()) == linked
