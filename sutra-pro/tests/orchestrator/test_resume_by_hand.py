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


def test_the_hint_names_the_command_of_this_install_the_apps_own_python_for_an_app_and_sutra_pro_otherwise(rig, capsys):
    from sutra_app.orchestrator.killswitch import resume_command
    bundle = "/Applications/Sutra Pro Beta.app/Contents/Resources/python/bin/python3"
    assert resume_command("/data/d", bundle) == f'"{bundle}" -I -B -m sutra_app nodes resume --data-dir "/data/d"'
    assert resume_command("/data/d", "C:\\Program Files\\Sutra Pro\\resources\\python\\python.exe").endswith('-m sutra_app nodes resume --data-dir "/data/d"')
    assert resume_command("/data/d", "/usr/bin/python3") == "sutra-pro nodes resume"
    from sutra_app.orchestrator.killswitch import resume_words
    assert resume_words(bundle) == "nodes resume --data-dir <this data folder>, run with the Python inside this app (-I -B -m sutra_app)"
    assert resume_words("/usr/bin/python3") == "sutra-pro nodes resume" and "/" not in resume_words(bundle).replace("-I -B -m sutra_app", "").replace("(", "").replace(")", "")
    command(rig, "kill")
    held = rig.switch.held()
    assert "kill switch is on" in held and "nodes resume" in held and "/Users" not in held and "/home" not in held and str(rig.t.settings.data_dir) not in held, held
    code = command(rig, "pause")
    out = capsys.readouterr().out
    assert code == 0 and "nodes resume" in out


def test_the_audit_row_is_written_before_the_marker_goes_so_a_failure_between_them_loses_nothing_and_writes_nothing_twice(rig, capsys, monkeypatch):
    """m-3: a crash or a database error after the app read the marker used to lose the row for good. Now the marker stays until the row is written, and a repeat finds the row and writes no second one."""
    command(rig, "kill")
    command(rig, "resume")
    marker = rig.switch.resume_marker()
    real = rig.control._audit_resume_once

    def broken(ref, removed):
        raise RuntimeError("the database said no")
    monkeypatch.setattr(rig.control, "_audit_resume_once", broken)
    rig.t.run(rig.control.enforce())                                                   # a failing audit never raises out of enforce (D416, r-3)
    assert marker.exists() and resumes(rig) == [], "the failure left the marker in place: nothing was lost"
    monkeypatch.setattr(rig.control, "_audit_resume_once", real)
    rig.t.run(rig.control.enforce())
    assert len(resumes(rig)) == 1 and not marker.exists()
    marker.write_text(marker.read_text() if marker.exists() else "", encoding="utf-8")
    command(rig, "kill")
    command(rig, "resume")
    text = marker.read_text()
    marker.write_text(text + text, encoding="utf-8")                                     # the same resume read twice (an unlink that did not happen): one row
    rig.t.run(rig.control.enforce())
    assert len(resumes(rig)) == 2


def test_a_resume_written_while_the_app_was_between_its_read_and_its_unlink_is_kept(rig, capsys):
    command(rig, "kill")
    command(rig, "resume")
    pending = rig.switch.pending_resumes()
    assert len(pending) == 1
    command(rig, "pause")
    command(rig, "resume")                                                                # appended after the read
    rig.switch.finish_resumes()
    assert rig.switch.resume_marker().exists(), "the newer resume is still there"
    rig.t.run(rig.control.enforce())
    assert len(resumes(rig)) == 1 and not rig.switch.resume_marker().exists()


def test_a_hand_made_kill_file_is_enforced_even_when_the_resume_audit_cannot_be_written(rig, capsys, monkeypatch):
    """r-3: the audit row used to come first, so a failing write kept a KILL file from being enforced on every tick (and failed the app's start while a stale marker stayed)."""
    reservation, tasks = running_steps(rig)
    command(rig, "pause")
    command(rig, "resume")                                                             # a marker is waiting for its row
    monkeypatch.setattr(rig.control, "_audit_resume_once", lambda ref, removed: (_ for _ in ()).throw(RuntimeError("the database is full")))
    (rig.switch.directory / "KILL").write_text("by hand\n")
    stopped = rig.t.run(rig.control.enforce())
    assert stopped >= 1 and {r["state"] for r in rig.sql("SELECT state FROM agent_nodes WHERE role = 'worker'")} == {"cancelled"}, "the kill was enforced first"
    assert rig.switch.resume_marker().exists() and resumes(rig) == []


def running_steps(rig):
    from orchestrator.test_reconcile_projects import running
    return running(rig, [("a1", "web", []), ("a2", "sales", [])])
