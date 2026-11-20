"""A path nobody owns (MAN-10, D303, D317): the host's folder watch names the paths a node changed; one that no writer of the project owns is a scope violation. The owner is asked (a card), the node
waits and the project starts nothing new; yes keeps the work, no sets it aside (quarantine: files kept, nothing handed on, dependants cancelled). Decide for me sets it aside."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.engine.host import handoff as host_handoff


@pytest.fixture
def rig(db, settings, clock, events, tmp_path):
    rig = PRig(db, settings, clock, events, max_runs=6, max_live=12, owner="edit")
    folder = tmp_path / "work"
    (folder / ".git").mkdir(parents=True)
    rig.projects._folder_of = lambda: str(folder)
    rig.projects._output_of = lambda dept: "edit" if dept in ("web", "sales", "ops") else "read"
    return rig


def two_writers(rig, **kw):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", ["a1"])], scope={"a1": ("site/",), "a2": ("docs/",), "a3": ("tests/",)}, **kw)
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 0) WHERE id = ?", reservation.project_id)
    rig.start()
    for ref in ("a1", "a2"):
        rig.go(tasks[ref])
    return reservation, tasks


def finish_with(rig, task_id, changes):
    rig.finish(task_id, override={"changes": changes}, files={"out.md": "done"})


def node(rig, ref):
    return rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = ?", ref).fetchone()


def test_a_path_another_writer_owns_is_not_a_violation_and_the_hand_off_goes_on(rig):
    reservation, tasks = two_writers(rig)
    finish_with(rig, tasks["a1"], ["site/index.html", "docs/readme.md"])                              # docs/ belongs to a2: no path is nobody's
    assert node(rig, "a1")["state"] == "done" and rig.audit("scope.violation") == [] and rig.sql("SELECT count(*) FROM approvals").fetchone()[0] == 0


def test_a_path_nobody_owns_holds_the_node_pauses_the_project_and_asks_with_a_card(rig):
    reservation, tasks = two_writers(rig)
    finish_with(rig, tasks["a1"], ["site/index.html", "secrets/notes.txt", "other/x.txt"])
    assert node(rig, "a1")["state"] == "awaiting_approval" and rig.project(reservation.project_id)["paused"] == 1
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    assert asked.request["kind"] == "scope_violation" and asked.request["count"] == 2 and asked.request["paths"] == ["secrets/notes.txt", "other/x.txt"] and asked.tier == 2
    [card] = rig.projects.approval_cards(reservation.project_id)
    assert card.options == ["allow_once", "deny"] and "Keep its work?" in card.question and "secrets/notes.txt" in card.question
    assert rig.t.status(tasks["a3"]) == "queued" and rig.start() == []                                # nothing new starts while paused; a3 waits for a1 anyway
    assert [r["action"] for r in rig.audit("scope.violation")] == ["scope.violation"] and rig.store.messages(reservation.project_id) == []      # nothing was handed on yet


def test_yes_keeps_the_work_hands_it_on_and_the_project_starts_again(rig):
    reservation, tasks = two_writers(rig)
    finish_with(rig, tasks["a1"], ["elsewhere/x.txt"])
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    snapshot = rig.t.run(rig.projects.answer(reservation.project_id, asked.id, "allow_once"))
    assert node(rig, "a1")["state"] == "done" and snapshot["project"]["paused"] is False and len(rig.store.messages(reservation.project_id)) == 1
    assert rig.t.status(tasks["a3"]) in ("queued", "starting", "running")


def test_no_sets_the_work_aside_keeps_its_files_hands_nothing_on_and_cancels_the_dependants(rig):
    reservation, tasks = two_writers(rig)
    finish_with(rig, tasks["a1"], ["elsewhere/x.txt"])
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    rig.t.run(rig.projects.answer(reservation.project_id, asked.id, "deny"))
    assert node(rig, "a1")["state"] == "failed" and "set aside" in node(rig, "a1")["failure_reason"] and rig.t.status(tasks["a3"]) == "cancelled"
    assert (rig.t.run_dir(tasks["a1"]) / "out.md").is_file() and rig.store.messages(reservation.project_id) == []             # its files stay; nothing was handed on
    assert [r["action"] for r in rig.audit("scope.quarantined")] == ["scope.quarantined"] and rig.project(reservation.project_id)["status"] == "running"
    assert rig.project(reservation.project_id)["paused"] == 0


def test_decide_for_me_sets_the_work_aside_at_once_audited_as_its_rule_and_never_keeps_it(rig):
    reservation, tasks = two_writers(rig, decide_for_me=True)
    finish_with(rig, tasks["a1"], ["elsewhere/x.txt"])
    assert node(rig, "a1")["state"] == "failed" and rig.store.approvals(reservation.project_id, status="open") == []
    [decided] = [r for r in rig.audit("gate.decided") if "scope_violation" in r["reason"]]
    assert "decided_by rule:decide_for_me" in decided["reason"] and decided["decision"] == "deny" and rig.project(reservation.project_id)["paused"] == 0


def test_a_neighbour_with_no_scope_cannot_run_with_it_so_a_step_that_ran_alone_answers_for_its_own_scope(rig):          # R2 (was: a writer with no scope makes every path owned)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("site/",)})          # a2 has no scope: the whole folder, so the lease keeps it behind a1
    rig.start()
    rig.go(tasks["a1"])
    assert rig.t.status(tasks["a2"]) == "queued"
    finish_with(rig, tasks["a1"], ["anywhere/x.txt"])
    assert node(rig, "a1")["state"] == "awaiting_approval" and [r["action"] for r in rig.audit("scope.violation")] == ["scope.violation"]


def test_the_host_builds_the_changes_list_from_its_own_folder_watch_and_skips_the_probe_file(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "out.md").write_text("x")
    assert "changes" not in host_handoff.build(run, "nd_" + "a" * 12, "done", "ok")                                       # git could not say: no key
    (run / "deliverable.json").write_text(json.dumps({"changes": {"files": [{"path": "site/a.html", "status": "new"}, {"path": ".sutra-probe-abcdef", "status": "new"}, {"path": "dir/.sutra-probe-1", "status": "new"}], "more": 0}}))
    assert host_handoff.build(run, "nd_" + "a" * 12, "done", "ok")["changes"] == ["site/a.html"]


def test_continue_cannot_lift_the_hold_and_a_step_that_follows_a_held_one_never_starts(rig):          # PB-1
    from sutra_app.orchestrator.errors import AppError
    reservation, tasks = two_writers(rig)
    finish_with(rig, tasks["a1"], ["site/index.html", "secrets/notes.txt"])
    pid = reservation.project_id
    assert node(rig, "a1")["state"] == "awaiting_approval" and rig.project(pid)["paused"] == 1
    with pytest.raises(AppError) as refused:
        rig.t.run(rig.projects.pause(pid, resume=True))                                                   # the owner's Continue
    assert refused.value.code == "busy" and "Answer that question first" in refused.value.message and rig.project(pid)["paused"] == 1
    rig.sql("UPDATE projects SET paused = 0 WHERE id = ?", pid)                                           # even with the flag cleared by any other way
    assert rig.start() == [] and rig.t.status(tasks["a3"]) == "queued"                                    # a3 follows a1, which is held: it is not handed a1's work
    [asked] = rig.store.approvals(pid, status="open")
    rig.t.run(rig.projects.answer(pid, asked.id, "allow_once"))
    assert node(rig, "a1")["state"] == "done" and rig.t.status(tasks["a3"]) in ("queued", "starting", "running")


def test_a_step_that_ran_alone_is_checked_against_its_own_scope_not_its_neighbours(rig):                       # R2
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], scope={"a1": ("site/",), "a2": ("docs/",)})
    rig.start()
    rig.go(tasks["a1"])                                                                                    # a2 waits for a1: a1 ran alone
    finish_with(rig, tasks["a1"], ["site/index.html", "docs/readme.md"])                                      # docs/ is a2's part, but a1 had no part in it
    assert node(rig, "a1")["state"] == "awaiting_approval"
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    assert asked.request["kind"] == "scope_violation" and asked.request["paths"] == ["docs/readme.md"]


def test_every_changed_path_up_to_the_cap_is_checked_not_only_the_first_hundred(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], scope={"a1": ("site/",), "a2": ("docs/",)})
    rig.start()
    rig.go(tasks["a1"])
    every = [f"site/f{i}.txt" for i in range(150)] + ["zzz/evil.sh"]                                          # the 151st path is the bad one; the hand-off names only the first 100
    rig.finish(tasks["a1"], override={"changes": every[:100], "changes_more": 51}, files={"changes.json": json.dumps({"schema": "changes/1", "files": every})})
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    assert asked.request["paths"] == ["zzz/evil.sh"] and node(rig, "a1")["state"] == "awaiting_approval" and rig.audit("scope.unchecked") == []


def test_a_list_cut_at_a_hundred_with_no_whole_list_says_the_rest_were_not_checked(rig):                        # G26
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], scope={"a1": ("site/",), "a2": ("docs/",)})
    rig.start()
    rig.go(tasks["a1"])
    finish_with(rig, tasks["a1"], [f"site/f{i}.txt" for i in range(100)])
    rig.sql("SELECT 1")
    assert node(rig, "a1")["state"] == "done"                                                              # no question is asked for what could not be seen


def test_a_writer_whose_changes_could_not_be_read_ends_done_and_the_audit_says_it_was_not_checked(rig):          # G26
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], scope={"a1": ("site/",), "a2": ("docs/",)})
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], files={"out.md": "done"})                                                      # no deliverable.json: git could not say
    assert node(rig, "a1")["state"] == "done" and rig.sql("SELECT count(*) FROM approvals").fetchone()[0] == 0
    [row] = rig.audit("scope.unchecked")
    assert "git could not say" in row["reason"] and row["node_id"] == node(rig, "a1")["id"] and "/" not in row["reason"].replace("and/or", "")
    rig.start()
    rig.go(tasks["a2"])
    finish_with(rig, tasks["a2"], [])                                                                      # a true "nothing changed" is not "unchecked"
    assert len(rig.audit("scope.unchecked")) == 1


def test_a_step_with_no_scope_of_its_own_is_said_to_be_unchecked(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], scope={"a2": ("docs/",)})
    rig.start()
    rig.go(tasks["a1"])
    finish_with(rig, tasks["a1"], ["anywhere/x.txt"])
    assert node(rig, "a1")["state"] == "done" and "not given its own part" in rig.audit("scope.unchecked")[0]["reason"]


def test_stopping_the_project_ends_a_step_held_for_a_question_and_so_does_a_sleep(rig):                        # PB-10
    reservation, tasks = two_writers(rig)
    finish_with(rig, tasks["a1"], ["site/index.html", "secrets/notes.txt"])
    assert node(rig, "a1")["state"] == "awaiting_approval"
    rig.t.run(rig.projects.stop(reservation.project_id))
    assert rig.project(reservation.project_id)["status"] == "stopped" and node(rig, "a1")["state"] == "cancelled" and "stopped" in node(rig, "a1")["failure_reason"]
    assert rig.sql("SELECT count(*) FROM agent_nodes WHERE state = 'awaiting_approval' AND project_id = ?", reservation.project_id).fetchone()[0] == 0


def test_a_closed_laptop_refusal_ends_the_held_step_too(rig):                                                  # PB-10
    reservation, tasks = two_writers(rig)
    finish_with(rig, tasks["a1"], ["site/index.html", "secrets/notes.txt"])
    rig.t.run(rig.projects.tick(now=1793786400 + 10))
    rig.t.run(rig.projects.tick(now=1793786400 + 4000))
    assert rig.project(reservation.project_id)["status"] == "stopped" and node(rig, "a1")["state"] == "cancelled"
