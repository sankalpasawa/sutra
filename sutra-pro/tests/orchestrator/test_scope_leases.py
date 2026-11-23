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


def test_scopes_that_differ_only_in_how_an_accent_is_written_are_the_same_place():                              # PB-17
    from sutra_app.orchestrator.grants import GrantError, normalize_scope, scopes_overlap
    nfc, nfd = "café/", "café/menu"
    assert scopes_overlap(normalize_scope([nfc]), normalize_scope([nfd])) and normalize_scope([nfc, "café/"]) == (nfc,)            # one place, once
    for bad in ("!notes", "a(b)", "site/(draft)", "x)"):
        with pytest.raises(GrantError) as refused:
            normalize_scope([bad])
        assert "bracket or an exclamation mark" in str(refused.value) and "parent folder" in str(refused.value) and "wild-card" not in str(refused.value)
    with pytest.raises(GrantError) as star:
        normalize_scope(["site/*"])
    assert "no wild-card" in str(star.value)


def test_a_link_inside_the_folder_leads_to_the_place_it_points_at_and_one_that_leaves_the_folder_is_the_whole_folder(tmp_path):
    from sutra_app.orchestrator.conductor import Conductor
    folder = tmp_path / "work"
    (folder / "docs").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    (folder / "site").symlink_to(folder / "docs")
    (folder / "escape").symlink_to(tmp_path / "outside")
    assert set(Conductor._resolved(str(folder), ("site/",))) == {"site/", "docs/"}
    assert Conductor._resolved(str(folder), ("escape/",)) == ()
    assert Conductor._resolved(str(folder), ("plain/",)) == ("plain/",) and Conductor._resolved(None, ("site/",)) == ("site/",) and Conductor._resolved(str(folder), ()) == ()


def test_a_writer_of_a_link_waits_for_the_writer_of_what_the_link_points_at(rig):
    (rig.folder / "docs").mkdir()
    (rig.folder / "site").symlink_to(rig.folder / "docs")
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("site/",), "a2": ("docs/",)})
    rig.start()
    assert len(rig.t.launcher.started) == 1                                                                    # they would have run together by their names; the link makes them one place


def test_a_link_to_another_drive_or_to_the_folder_itself_makes_the_scope_the_whole_folder(tmp_path, monkeypatch):          # N-6
    import os

    from sutra_app.orchestrator.conductor import Conductor
    folder = tmp_path / "work"
    (folder / "docs").mkdir(parents=True)
    (folder / "self").symlink_to(folder)
    assert Conductor._resolved(str(folder), ("self/",)) == ()                                                  # a link at the folder itself
    real = os.path.relpath
    monkeypatch.setattr(os.path, "relpath", lambda *a, **k: (_ for _ in ()).throw(ValueError("path is on mount 'C:', start on mount 'D:'")))     # what Windows says for another drive
    assert Conductor._resolved(str(folder), ("docs/",)) == ()
    monkeypatch.setattr(os.path, "relpath", real)
    assert Conductor._resolved(str(folder), ("docs/",)) == ("docs/",)


def test_the_links_of_the_steps_scopes_are_followed_before_the_start_transaction_not_inside_it(rig):           # N-6, PB-16
    from sutra_app.orchestrator.conductor import Conductor
    rig.t.service.before_prepare = rig.projects.conductor.warm_scopes
    depths = []
    real = Conductor._resolved

    def spying(folder, scope):
        depths.append(getattr(rig.t.db._local, "depth", 0))
        return real(folder, scope)
    Conductor._resolved = staticmethod(spying)
    try:
        reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], scope={"a1": ("site/",), "a2": ("docs/",)})
        rig.start()
    finally:
        Conductor._resolved = staticmethod(real)
    assert depths and set(depths) == {0}                                                                        # every look at a link was outside any transaction
    assert len(rig.t.launcher.started) == 2                                                                      # and the gate still did its work from the answers


def test_a_path_from_git_written_with_the_other_accent_form_is_covered_by_the_scope(rig):                       # N-10
    from sutra_app.orchestrator.conductor import _covers_path
    from sutra_app.orchestrator.grants import normalize_scope
    scope = normalize_scope(["caf\u00e9/"])                                                                    # the owner typed the accent as one letter ...
    assert _covers_path(scope, "cafe\u0301/menu.txt") and _covers_path(scope, "CAFE\u0301/Menu.txt")         # ... git reports it as a letter and a mark (macOS)
    assert not _covers_path(scope, "cafe/menu.txt") and not _covers_path(scope, "caf\u00e9s/menu.txt")
    assert _covers_path(("cafe\u0301/",), "caf\u00e9/menu.txt")                                              # and the other way round
