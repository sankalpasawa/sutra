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


def test_a_writer_that_owns_the_whole_folder_makes_every_path_owned(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("site/",)})                  # a2 has no scope: the whole folder
    rig.start()
    rig.go(tasks["a1"])
    finish_with(rig, tasks["a1"], ["anywhere/x.txt"])
    assert node(rig, "a1")["state"] == "done" and rig.audit("scope.violation") == []


def test_the_host_builds_the_changes_list_from_its_own_folder_watch_and_skips_the_probe_file(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "out.md").write_text("x")
    assert "changes" not in host_handoff.build(run, "nd_" + "a" * 12, "done", "ok")                                       # git could not say: no key
    (run / "deliverable.json").write_text(json.dumps({"changes": {"files": [{"path": "site/a.html", "status": "new"}, {"path": ".sutra-probe-abcdef", "status": "new"}, {"path": "dir/.sutra-probe-1", "status": "new"}], "more": 0}}))
    assert host_handoff.build(run, "nd_" + "a" * 12, "done", "ok")["changes"] == ["site/a.html"]
