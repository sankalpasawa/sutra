"""`sutra-pro nodes resume` leaves an audit row (D384): the command only writes files, so it says what it removed in its marker and the running app writes the row when it sees it (or at its next
start). A look (status) and a resume that removed nothing leave none."""
import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.ops import cli
from sutra_app.orchestrator.killswitch import KILL_FILE, PAUSE_FILE


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def command(rig, *words):
    return cli.main(["nodes", *words, "--data-dir", str(rig.t.settings.data_dir)])


def resumes(rig):
    return [r for r in rig.audit() if r["action"] == "resume"]


def test_a_resume_by_hand_that_removed_files_is_one_audit_row_written_by_the_app(rig, capsys):
    assert command(rig, "kill", "--reason", "testing") == 0 and command(rig, "pause") == 0
    rig.t.run(rig.control.enforce())
    assert (rig.switch.directory / KILL_FILE).exists() and (rig.switch.directory / PAUSE_FILE).exists()
    assert command(rig, "resume") == 0
    assert resumes(rig) == [], "the command itself writes no database row: it only writes files"
    rig.t.run(rig.control.enforce())
    [row] = resumes(rig)
    assert row["actor"] == "owner" and row["decision"] == "n/a" and "resumed by hand with the command line" in row["reason"] and "KILL" in row["reason"] and "PAUSE" in row["reason"]
    rig.t.run(rig.control.enforce())
    assert len(resumes(rig)) == 1, "once"
    assert not rig.switch.resume_marker().exists()


def test_a_resume_that_found_nothing_and_a_status_leave_no_row(rig, capsys):
    assert command(rig, "status") == 0 and command(rig, "resume") == 0
    rig.t.run(rig.control.enforce())
    assert resumes(rig) == []


def test_a_resume_made_while_the_app_was_closed_is_audited_when_the_app_looks_next(rig, capsys):
    command(rig, "kill")
    command(rig, "resume")                                                            # no app looked in between
    assert rig.switch.resume_marker().exists()
    rig.t.run(rig.control.enforce())
    assert len(resumes(rig)) == 1


def test_a_status_run_between_the_resume_and_the_apps_look_does_not_eat_the_marker(rig, capsys):
    """Run 2: `nodes status` right after `nodes resume` took the marker in the command's own process, so the app never wrote the row. Only the app may take it."""
    command(rig, "kill")
    command(rig, "resume")
    marker = rig.switch.resume_marker()
    assert marker.exists()
    for _ in range(3):
        assert command(rig, "status") == 0
    assert marker.exists() and "removed: KILL" in marker.read_text(), "status only looks"
    command(rig, "pause")
    command(rig, "resume")
    command(rig, "status", "--json")
    assert marker.exists()
    rig.t.run(rig.control.enforce())
    assert not marker.exists()
    assert len(resumes(rig)) == 2, "one row for each resume, and the app wrote both"
