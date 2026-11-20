"""Write-scope leases (MAN-10, D260, D323): enforced for every project when the master flag is on, as rows. Two writers whose scopes overlap never run together (the later one waits, a delay and never
a cancel); disjoint scopes run together; a writer with no scope, or a team whose output is `auto`, holds the whole folder; a folder that is not a git repository means writers one at a time."""
import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

BASE = 1793786400


@pytest.fixture
def rig(db, settings, clock, events, tmp_path):
    rig = PRig(db, settings, clock, events, max_runs=6, max_live=12, owner="edit")
    folder = tmp_path / "work"
    (folder / ".git").mkdir(parents=True)
    rig.folder = folder
    rig.projects._folder_of = lambda: str(folder)
    rig.projects._output_of = lambda dept: "edit" if dept in ("web", "sales", "ops", "hr", "dev") else "read"
    return rig


def started(rig):
    return {s.task_id for s, *_ in rig.t.launcher.started}


def test_two_writers_with_overlapping_scopes_never_run_together_and_the_later_one_waits(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("site/",), "a2": ("site/pricing",)})
    rig.start()
    assert started(rig) == {tasks["a1"]} and "same part of your folder" in rig.detail(tasks["a2"])
    rig.go(tasks["a1"])
    assert rig.start() == []                                                                          # still waiting while a1 runs
    rig.finish(tasks["a1"])
    assert rig.start() == [tasks["a2"]]                                                               # a delay, never a cancel
    assert rig.t.status(tasks["a2"]) == "starting"


def test_writers_with_disjoint_scopes_run_together(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("site/",), "a2": ("docs/",)})
    rig.start()
    assert started(rig) == {tasks["a1"], tasks["a2"]}


def test_a_writer_with_no_scope_holds_the_whole_folder_and_runs_alone_among_writers_but_a_reader_runs_beside_it(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "legal", [])], scope={"a2": ("docs/",)})
    rig.start()
    assert tasks["a1"] in started(rig) and tasks["a2"] not in started(rig) and tasks["a3"] in started(rig)    # a1 has no scope; a3's team only reads
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"])
    assert tasks["a2"] in set(rig.start()) | started(rig)


def test_a_team_whose_output_is_auto_counts_as_a_possible_writer_with_the_whole_folder(rig):
    rig.projects._output_name = lambda dept: "auto" if dept == "legal" else ""
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "legal", [])], scope={"a1": ("site/",)})
    rig.start()
    assert started(rig) == {tasks["a1"]} and "same part of your folder" in rig.detail(tasks["a2"])


def test_a_folder_that_is_not_a_git_repository_means_writers_one_at_a_time(rig):
    (rig.folder / ".git").rmdir()
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("site/",), "a2": ("docs/",)})
    rig.start()
    assert started(rig) == {tasks["a1"]} and "one at a time" in rig.detail(tasks["a2"])


def test_the_lease_holds_across_projects_and_survives_a_restart_because_it_is_a_row(rig):
    first, one = rig.request([("a1", "web", []), ("a2", "legal", [])], scope={"a1": ("site/",)})
    rig.start()
    second, two = rig.request([("b1", "sales", []), ("b2", "legal", [])], request_id="req-2", scope={"b1": ("site/index.html",)})
    rig.start()
    assert one["a1"] in started(rig) and two["b1"] not in started(rig)
    assert "same part" in rig.projects.gate(rig.t.db.conn(), BASE, rig.t.row(two["b1"]))


def test_a_node_that_cannot_write_is_never_held_by_a_lease(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "legal", [])], scope={"a1": ("site/",)})
    rig.start()
    assert tasks["a2"] in started(rig)


def test_the_gate_reads_the_owners_folder_setting_once_in_a_moment_not_for_every_waiting_step(rig):             # PB-16
    reads = []
    original = rig.projects._folder_of

    def counting():
        reads.append(1)
        return original()
    rig.projects._folder_of = counting
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", [])], scope={"a1": ("site/",), "a2": ("docs/",), "a3": ("tests/",)})
    conn = rig.t.db.conn()
    for ref in ("a1", "a2", "a3", "a1", "a2"):
        rig.projects.gate(conn, 1793786400, rig.t.row(tasks[ref]))
    assert len(reads) == 1
