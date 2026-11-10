"""The two sides of a run's end agree (D135): what the engine host writes in `deliverable.json` is what the server's `read_deliverable` reads. The host side is
`test_engine_deliverable.py`, the server side `tests/orchestrator/test_deliverable_card.py`; this file runs the real host and reads its record with the real reader."""
from sutra_app.connectors.workdir import WorkFolder

from test_engine_deliverable import UPDATE, append, needs_git, repo, run_project   # noqa: F401  (fixtures and helpers)
from test_engine_host import QUIET, j2   # noqa: F401  (fixtures and helpers)
from test_engine_project import BRIEF


@needs_git
def test_what_the_host_writes_is_what_the_server_reads(j2, make_run_dir, data_dir, repo):
    from sutra_app.orchestrator.deliverable import read_deliverable
    WorkFolder(data_dir).set(str(repo), access="edit")
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir, [append(repo / "README.md", "checked by the team\n")])
    got = read_deliverable(run_dir)
    assert got is not None and (got.label, got.file, got.cut) == ("Project work report", "project.md", False)
    assert got.text == (run_dir / "project.md").read_text(encoding="utf-8").strip() and got.text.startswith("# ")
    assert [(f.path, f.status) for f in got.changes.files] == [("README.md", "modified")] and got.changes.more == 0


def test_a_run_with_no_folder_still_hands_the_server_its_report(j2, make_run_dir):
    from sutra_app.orchestrator.deliverable import read_deliverable
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    run_project(run_dir)
    got = read_deliverable(run_dir)
    assert got is not None and got.has_report and got.changes is None
