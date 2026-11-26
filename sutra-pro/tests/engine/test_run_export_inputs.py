"""D451, FR-12: the files a run was GIVEN (`<run>/inputs/`: the project's files and the request's own) are never exported to the project's folder and never listed as a deliverable.

The same export code as test_export_to_folder (D428). Even a deliverable row that names a path under `inputs/` (a model writing the wrong path) exports nothing from there.
"""
from pathlib import Path

from test_engine_host import j2  # noqa: F401  (the J2 fixture the sibling file imports too)
from test_export_to_folder import manifest, write

from sutra_app.engine.host import export

ROWS = [{"file": "report.md", "form": "document"}, {"file": "inputs/knowledge/brand.md", "form": "document"}, {"file": "inputs/attached/spec.txt", "form": "agent"},
        {"file": "inputs", "form": "agent"}]


def test_no_path_under_inputs_is_a_deliverable_or_is_exported(tmp_path):
    run, folder = tmp_path / "run", tmp_path / "Project"
    folder.mkdir()
    write(run / "report.md", "# Report\n")
    write(run / "inputs" / "knowledge" / "brand.md", "BRAND-GUIDE")
    write(run / "inputs" / "attached" / "spec.txt", "the spec")
    assert export.deliverable_files(run, ROWS) == ["report.md"]
    result = export.export_run(run, folder, "j2-1", ROWS)
    assert result.new == ["report.md"] and not (folder / "inputs").exists()
    assert sorted(manifest(folder)["files"]) == ["report.md"]


def test_a_run_with_no_inputs_folder_exports_exactly_what_it_did(tmp_path):
    run, folder = tmp_path / "run", tmp_path / "Project"
    folder.mkdir()
    write(run / "report.md", "# Report\n")
    assert export.deliverable_files(run, [{"file": "report.md", "form": "document"}]) == ["report.md"]
