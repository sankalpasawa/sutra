"""Named projects, task 9 (R1.12, R1.14, D428): a run that ended well copies its deliverables into its project's own folder, under the same
relative paths. Sutra's records (*.json, *.jsonl, site/, out/) stay in the run. `<folder>/.sutra/manifest.json` keeps the sha256 of what Sutra
last wrote: a file Sutra never wrote, or one changed since, is never overwritten, and the chat names it."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from sutra_app import oslayer
from sutra_app.connectors.workdir import WorkFolder
from sutra_app.engine.host import export, finish

from test_engine_host import j2   # noqa: F401  (the J2 fixture)

ROWS = [{"file": "prd.md", "form": "document"}, {"file": "pulse_app/main.py", "form": "agent"}, {"file": "pulse_app/config.py", "form": "agent"},
        {"file": "site/index.html", "form": "page"}, {"file": "goal.json", "form": "document"}]


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def run(tmp_path):
    d = tmp_path / "run"
    write(d / "prd.md", "# PRD v1\n")
    write(d / "prd.docx", "docx bytes")
    write(d / "pulse_app" / "main.py", "print('digest at 08:00')\n")
    write(d / "pulse_app" / "config.py", "TIME = '08:00'\n")
    write(d / "site" / "index.html", "<html></html>")
    write(d / "goal.json", "{}")
    return d


@pytest.fixture
def folder(tmp_path):
    f = tmp_path / "Pulse"
    f.mkdir()
    return f


def manifest(folder: Path) -> dict:
    return json.loads((folder / ".sutra" / "manifest.json").read_text(encoding="utf-8"))


def test_deliverable_files_skip_sutras_records(run):
    assert export.deliverable_files(run, ROWS) == ["prd.docx", "prd.md", "pulse_app/config.py", "pulse_app/main.py"]


def test_deliverables_go_to_the_folder_under_the_same_paths(run, folder):
    result = export.export_run(run, folder, "j2-1", ROWS)
    assert sorted(result.new) == ["prd.docx", "prd.md", "pulse_app/config.py", "pulse_app/main.py"]
    assert (folder / "pulse_app" / "main.py").read_text(encoding="utf-8") == "print('digest at 08:00')\n"
    assert not (folder / "site").exists() and not (folder / "goal.json").exists()
    body = manifest(folder)
    assert body["version"] == 1 and body["run_id"] == "j2-1" and sorted(body["files"]) == sorted(result.new)


def test_a_file_sutra_never_wrote_is_untouched(run, folder):
    write(folder / "prd.md", "the owner's own notes")
    result = export.export_run(run, folder, "j2-1", ROWS)
    assert (folder / "prd.md").read_text(encoding="utf-8") == "the owner's own notes"
    assert result.outside == ["prd.md"] and "prd.md" not in manifest(folder)["files"]


def test_a_file_changed_since_sutra_wrote_it_is_not_overwritten(run, folder):
    export.export_run(run, folder, "j2-1", ROWS)
    write(folder / "prd.md", "# PRD edited by hand\n")
    write(run / "prd.md", "# PRD v2\n")
    result = export.export_run(run, folder, "j2-2", ROWS)
    assert (folder / "prd.md").read_text(encoding="utf-8") == "# PRD edited by hand\n"
    assert result.outside == ["prd.md"]


def test_a_changed_deliverable_is_updated_and_an_unchanged_one_is_not_rewritten(run, folder):
    export.export_run(run, folder, "j2-1", ROWS)
    before = os.stat(folder / "pulse_app" / "main.py").st_mtime_ns
    write(run / "pulse_app" / "config.py", "TIME = '08:30'\n")
    result = export.export_run(run, folder, "j2-2", ROWS)
    assert result.updated == ["pulse_app/config.py"] and "pulse_app/main.py" in result.unchanged and result.new == []
    assert os.stat(folder / "pulse_app" / "main.py").st_mtime_ns == before
    assert (folder / "pulse_app" / "config.py").read_text(encoding="utf-8") == "TIME = '08:30'\n"


def test_a_locked_file_is_skipped_and_named(run, folder, monkeypatch):
    real = oslayer.replace

    def locked(src, dst):
        if str(dst).endswith("main.py"):
            raise PermissionError(13, "in use")
        return real(src, dst)

    monkeypatch.setattr(oslayer, "replace", locked)
    result = export.export_run(run, folder, "j2-1", ROWS)
    assert result.failed == ["pulse_app/main.py"] and "prd.md" in result.new
    assert not (folder / "pulse_app" / "main.py").exists() and "pulse_app/main.py" not in manifest(folder)["files"]
    assert not [p for p in folder.rglob("*.tmp")]


def test_a_path_that_leaves_the_folder_is_skipped(run, folder):
    result = export.export_run(run, folder, "j2-1", [{"file": "../escape.md", "form": "document"}, {"file": "prd.md", "form": "document"}])
    assert result.new == ["prd.docx", "prd.md"] and not (folder.parent / "escape.md").exists()


# ---- the finish step -------------------------------------------------------------------------------------------------------------

def host_for(run, data, dept="pulse"):
    lines = []
    return SimpleNamespace(task=SimpleNamespace(dept_id=dept, run_id="j2-1"), paths=SimpleNamespace(run_dir=run, data_dir=data, run_id="j2-1"),
                           run=SimpleNamespace(post=lambda who, text: lines.append((who, text))), stopping=None, lines=lines)


def test_the_step_saves_and_says_so(run, folder, tmp_path, monkeypatch):
    monkeypatch.setattr(export, "_rows", lambda run_dir, own=None: ROWS)
    data = tmp_path / "data"
    WorkFolder(data, dept_id="pulse").set(str(folder), access="edit")
    host = host_for(run, data)
    facts = export.step(host)
    assert facts["new"] == 4 and json.loads((run / "export.json").read_text())["folder"] == os.path.realpath(folder)
    assert host.lines == [("system", f"Saved to {os.path.realpath(folder)}: 4 files (4 new, 0 updated).")]


def test_the_step_names_files_changed_outside_sutra(run, folder, tmp_path, monkeypatch):
    monkeypatch.setattr(export, "_rows", lambda run_dir, own=None: ROWS)
    data = tmp_path / "data"
    WorkFolder(data, dept_id="pulse").set(str(folder), access="edit")
    write(folder / "prd.md", "mine")
    host = host_for(run, data)
    export.step(host)
    assert ("system", "Not updated: prd.md was changed outside Sutra") in host.lines


def test_a_vanished_folder_is_reported_not_made(run, folder, tmp_path, monkeypatch):
    monkeypatch.setattr(export, "_rows", lambda run_dir, own=None: ROWS)
    data = tmp_path / "data"
    WorkFolder(data, dept_id="pulse").set(str(folder), access="edit")
    gone = os.path.realpath(folder)
    folder.rmdir()
    host = host_for(run, data)
    with pytest.raises(finish.Skip):
        export.step(host)
    assert host.lines == [("system", f"Not saved: {gone} is not there any more")] and not os.path.exists(gone)


def test_a_read_only_project_folder_gets_nothing(run, folder, tmp_path):
    data = tmp_path / "data"
    WorkFolder(data, dept_id="pulse").set(str(folder), access="read")
    with pytest.raises(finish.Skip, match="may only read"):
        export.step(host_for(run, data))
    assert list(folder.iterdir()) == []


def test_a_team_without_its_own_folder_gets_nothing_even_with_an_app_wide_one(run, folder, tmp_path):
    data = tmp_path / "data"
    WorkFolder(data).set(str(folder), access="edit")
    with pytest.raises(finish.Skip, match="no project folder"):
        export.step(host_for(run, data))
    assert list(folder.iterdir()) == []


def test_a_stopped_run_writes_nothing(run, folder, tmp_path, monkeypatch):
    monkeypatch.setattr(export, "_rows", lambda run_dir, own=None: ROWS)
    data = tmp_path / "data"
    WorkFolder(data, dept_id="pulse").set(str(folder), access="edit")
    for status in ("stopped", "crashed"):
        assert finish.run_steps(host_for(run, data), status, (("export", export.step),)) == []
    assert list(folder.iterdir()) == [] and not (run / "export.json").exists()


def test_export_is_a_finish_step_before_the_catalog():
    """The catalog may wait 30 s for the library lock, and a step over the limit skips every later one: export must not be one of them."""
    names = [name for name, _ in finish.STEPS]
    assert "export" in names and names.index("export") < names.index("catalog")


# ---- a real (mock) run to Done ----------------------------------------------------------------------------------------------------

def test_a_finished_mock_run_writes_into_the_team_folder(j2, make_run_dir, data_dir, tmp_path):
    from test_engine_project import BRIEF, QUIET, chat, go
    team = tmp_path / "Pulse"
    team.mkdir()
    WorkFolder(data_dir, dept_id="web").set(str(team), access="edit")
    run_dir = make_run_dir(dept_id="web", user_text=BRIEF, settings=QUIET)
    go(run_dir)
    assert (team / "project.md").read_bytes() == (run_dir / "project.md").read_bytes()
    assert "project.md" in manifest(team)["files"]
    assert not [p for p in team.rglob("*.json") if ".sutra" not in p.parts]                # Sutra's records stay in the run
    record = json.loads((run_dir / "export.json").read_text())
    assert record["folder"] == os.path.realpath(team) and "project.md" in record["new"]
    assert [m for m in chat(run_dir) if m["text"].startswith(f"Saved to {os.path.realpath(team)}: ")]


# ---- a built app reaches the folder whole: nested files and its own configs (review: Important 2) --------------------------------

def test_a_folder_output_is_exported_whole_with_nested_files_and_configs(run, folder):
    write(run / "pulse_app" / "src" / "digest.py", "def digest(): ...\n")
    write(run / "pulse_app" / "config" / "pulse.json", '{"time": "08:00"}\n')
    write(run / "pulse_app" / "package.json", "{}\n")
    write(run / "pulse_app" / ".env", "SECRET=1\n")
    files = export.deliverable_files(run, [{"file": "pulse_app/main.py", "form": "agent"}])
    assert files == ["pulse_app/config.py", "pulse_app/config/pulse.json", "pulse_app/main.py", "pulse_app/package.json", "pulse_app/src/digest.py"]
    result = export.export_run(run, folder, "j2-1", [{"file": "pulse_app/main.py", "form": "agent"}])
    assert (folder / "pulse_app" / "config" / "pulse.json").read_text(encoding="utf-8") == '{"time": "08:00"}\n'
    assert not (folder / "pulse_app" / ".env").exists() and len(result.new) == 5


def test_a_folder_output_with_only_subfolders_is_found_from_its_type(run, monkeypatch):
    from sutra_app.engine import j2_artifacts
    write(run / "notes_app" / "lib" / "notes.py", "x = 1\n")
    monkeypatch.setattr(j2_artifacts, "listing", lambda d: {"deliverables": [], "records": []})
    monkeypatch.setattr(j2_artifacts, "load_types", lambda d=None: {"types": [{"name": "notes_app", "kind": "type", "form": "agent", "file": "notes_app/*"}]})
    assert export.deliverable_files(run, export._rows(run)) == ["notes_app/lib/notes.py"]


# ---- Phase 2, task 13 (R2.2 to R2.6): a follow-up starts from the folder and writes back only what changed -------------------------

def second_run(run, tmp_path):
    import shutil
    d = tmp_path / "run2"
    shutil.copytree(run, d)                                          # what rehydrate brought back from the earlier run
    return d


def test_a_follow_up_starts_from_the_owners_edit(run, folder, tmp_path):
    export.export_run(run, folder, "j2-1", ROWS)
    write(folder / "pulse_app" / "main.py", "print('digest at 08:30, edited by hand')\n")
    run2 = second_run(run, tmp_path)
    edited = export.import_from_folder(folder, run2, rebase=True)
    assert edited == ["pulse_app/main.py"]
    assert (run2 / "pulse_app" / "main.py").read_text(encoding="utf-8") == "print('digest at 08:30, edited by hand')\n"
    assert manifest(folder)["files"]["pulse_app/main.py"] == export._sha(folder / "pulse_app" / "main.py")


def test_files_sutra_never_wrote_are_never_read(run, folder, tmp_path):
    export.export_run(run, folder, "j2-1", ROWS)
    write(folder / "secret.txt", "the owner's own file")
    write(folder / "notes" / "todo.md", "mine")
    run2 = second_run(run, tmp_path)
    export.import_from_folder(folder, run2, rebase=True)
    assert not (run2 / "secret.txt").exists() and not (run2 / "notes").exists()


def test_a_read_only_folder_is_read_but_its_manifest_is_not_rewritten(run, folder, tmp_path):
    export.export_run(run, folder, "j2-1", ROWS)
    before = (folder / ".sutra" / "manifest.json").read_bytes()
    write(folder / "prd.md", "# PRD edited\n")
    run2 = second_run(run, tmp_path)
    assert export.import_from_folder(folder, run2, rebase=False) == ["prd.md"]
    assert (folder / ".sutra" / "manifest.json").read_bytes() == before


def test_only_changed_files_are_written_back_and_nothing_is_deleted(run, folder, tmp_path):
    export.export_run(run, folder, "j2-1", ROWS)
    write(folder / "pulse_app" / "main.py", "print('edited by hand')\n")
    write(folder / "keep.txt", "the owner's")
    run2 = second_run(run, tmp_path)
    export.import_from_folder(folder, run2, rebase=True)
    write(run2 / "pulse_app" / "config.py", "TIME = '08:30'\n")
    (run2 / "prd.docx").unlink()                                     # gone from the run: stays in the folder
    before = {p: export._sha(folder / p) for p in ("prd.md", "pulse_app/main.py", "prd.docx")}
    result = export.export_run(run2, folder, "j2-2", ROWS)
    assert result.updated == ["pulse_app/config.py"] and result.outside == [] and result.new == []
    assert {p: export._sha(folder / p) for p in before} == before
    assert (folder / "keep.txt").exists() and (folder / "prd.docx").exists()


def test_the_chat_names_the_changed_files():
    result = export.ExportResult(updated=["pulse_app/digest.py", "config/pulse.json"])
    assert "Changed in Pulse: pulse_app/digest.py, config/pulse.json" in export.lines("/w/Pulse", result, "Pulse")
