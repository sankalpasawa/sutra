"""D461: a run that stopped (artifacts.json written) and was resumed lists the deliverables it built after that file."""
import json
import os

from sutra_app.engine import j2_artifacts as A


def test_a_resumed_run_lists_deliverables_built_after_artifacts_json(tmp_path):
    d = str(tmp_path)
    open(os.path.join(d, "goal.json"), "w", encoding="utf-8").write("{}")
    A.write(d)                                                     # the run stopped here: the saved list has the charter only
    assert [r["file"] for r in json.load(open(os.path.join(d, "artifacts.json"), encoding="utf-8"))["rows"]] == ["goal.json"]
    open(os.path.join(d, "prd.md"), "w", encoding="utf-8").write("# PRD\n")      # the resumed run writes its document
    lst = A.listing(d)
    assert [(r["file"], r["saved"]) for r in lst["deliverables"]] == [("prd.md", False)]
    assert [(r["file"], r["saved"]) for r in lst["records"]] == [("goal.json", True)]
    assert A.served(d, "prd.md")                                   # and the Files pane can open it
    A.write(d)                                                     # the run ends: the saved list has it, once
    assert [(r["file"], r["saved"]) for r in A.listing(d)["deliverables"]] == [("prd.md", True)]


def test_a_finished_run_lists_its_saved_rows_only_once(tmp_path):
    d = str(tmp_path)
    open(os.path.join(d, "prd.md"), "w", encoding="utf-8").write("# PRD\n")
    A.write(d)
    assert [(r["file"], r["saved"]) for r in A.listing(d)["deliverables"]] == [("prd.md", True)]
