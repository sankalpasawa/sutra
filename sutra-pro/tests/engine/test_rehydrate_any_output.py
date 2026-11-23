"""Named projects Phase 2, task 12 (R2.1, R2.7): a follow-up continues the last finished run of ANY output kind that has a charter and
workflows: project work (a single-file output) and a folder output (an app), not only a page or a document chain. A run that cannot be
continued still says why and starts fresh with the old files as reference."""
import json
from pathlib import Path

import pytest

from sutra_app.engine import rehydrate as rh

from test_engine_host import chat, j2, trace   # noqa: F401  (the J2 fixture)

FIRST = "j2-20261123-090000-aaaa"
SECOND = "j2-20261123-100000-bbbb"


def first_project_run(make_run_dir):
    from test_engine_project import BRIEF, QUIET, go
    run_dir = make_run_dir(run_id=FIRST, user_text=BRIEF, settings=QUIET)
    go(run_dir)
    assert json.loads((run_dir / "summary.json").read_text())["status"] in ("done", "done_with_open_items")
    return run_dir


def test_a_finished_project_run_is_continued_not_started_fresh(j2, make_run_dir):
    from test_engine_project import QUIET, go
    first = first_project_run(make_run_dir)
    second = make_run_dir(run_id=SECOND, user_text="Also check the settings page title.", settings=QUIET, seed_from=FIRST)
    go(second)
    assert not trace(second, "seed.refused"), trace(second, "seed.refused")
    assert [m for m in chat(second) if m["text"].startswith(f"Continuing from run {FIRST}")]
    assert (second / "project.md").is_file() and (second / "goal.json").is_file()
    record = json.loads((second / "output.json").read_text())
    assert (record["output"], record["rule"]) == ("project", "project") or record["rule"] == "followup"
    assert (first / "project.md").is_file()                              # the earlier run's folder is never written again


def test_check_source_accepts_a_single_output_run_and_lists_its_file(j2, make_run_dir):
    first = first_project_run(make_run_dir)
    found = rh.check_source(first)
    assert "project.md" in found["files"] and found["chain"] is None


def test_an_unfinished_run_is_still_refused(j2, make_run_dir):
    first = first_project_run(make_run_dir)
    summary = json.loads((first / "summary.json").read_text())
    summary["status"] = "stopped"
    (first / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(rh.RehydrateRefused, match="stopped before it finished"):
        rh.check_source(first)


def test_a_run_without_a_charter_is_still_refused(j2, make_run_dir):
    first = first_project_run(make_run_dir)
    (first / "goal.json").unlink()
    with pytest.raises(rh.RehydrateRefused, match="no charter"):
        rh.check_source(first)


def test_a_folder_output_run_is_continuable_with_its_whole_folder(j2, tmp_path, monkeypatch):
    """A folder output (form `agent`: an app a team built) continues too, with every file of its folder, configs included."""
    src = tmp_path / "src"
    for rel, text in {"pulse_app/main.py": "x", "pulse_app/config/pulse.json": "{}", "pulse_app/.env": "SECRET"}.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text)
    monkeypatch.setattr(rh, "_output_info", lambda kind, src=None: {"output": "folder", "folder": "pulse_app", "file": "pulse_app/*", "single": False})
    assert rh._continuable("pulse_app", src) is True
    assert rh._output_files(src, "pulse_app") == ["pulse_app/config/pulse.json", "pulse_app/main.py"]


def test_a_plain_document_without_its_chain_is_not_continuable(j2, monkeypatch):
    monkeypatch.setattr(rh, "_output_info", lambda kind, src=None: {"output": "file", "folder": None, "file": "prd.md", "single": False})
    assert rh._continuable("prd", None) is False
