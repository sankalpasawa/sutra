"""The host's list of changed paths for a node (MAN-10, PB-4, G26) and what a hand-off does not hand on (G23): the whole list up to 5000 paths goes to the host's own `changes.json`, the hand-off names the first
100 and says how many more there are, and the host's own files (`tools.jsonl`, `changes.json`) are never listed as files of the step."""
import json

from sutra_app.engine.host import folder_watch, handoff
from sutra_app.orchestrator import tasks as orchestrator_tasks


def test_the_host_files_are_not_handed_on_and_the_run_folder_internals_stay_a_subset(tmp_path):                   # G23
    for name in ("report.md", "tools.jsonl", "changes.json", "handoff.json", "calls.jsonl"):
        (tmp_path / name).write_text("x")
    document = handoff.build(tmp_path, "nd_" + "a" * 12, "done", "ok")
    assert [f["path"] for f in document["files"]] == ["report.md"]
    assert orchestrator_tasks.RUN_FOLDER_INTERNALS <= handoff.NOT_HANDED_ON


def test_the_hand_off_names_the_first_hundred_and_counts_the_rest(tmp_path):
    rows = [{"path": f"site/f{i}.txt", "status": "new"} for i in range(100)]
    (tmp_path / "deliverable.json").write_text(json.dumps({"schema": "deliverable/1", "changes": {"files": rows, "more": 51}}))
    document = handoff.build(tmp_path, "nd_" + "a" * 12, "done", "ok")
    assert len(document["changes"]) == 100 and document["changes_more"] == 51
    (tmp_path / "deliverable.json").write_text(json.dumps({"schema": "deliverable/1", "changes": {"files": rows[:3], "more": 0}}))
    assert "changes_more" not in handoff.build(tmp_path, "nd_" + "a" * 12, "done", "ok")
    (tmp_path / "deliverable.json").write_text(json.dumps({"schema": "deliverable/1"}))                                    # git could not say: no list, and no claim of "nothing"
    assert "changes" not in handoff.build(tmp_path, "nd_" + "a" * 12, "done", "ok")


def test_a_node_gets_every_changed_path_up_to_the_cap_and_an_ordinary_run_the_answer_it_always_had(monkeypatch):
    before = {}
    after = {f"site/f{i}.txt": ("??", "x") for i in range(250)}
    monkeypatch.setattr(folder_watch, "snapshot", lambda exe, folder, timeout: after)
    watch = folder_watch.FolderWatch("/work", "git", before, True)
    plain = watch.finish(True)
    assert set(plain) == {"files", "more"} and len(plain["files"]) == 100 and plain["more"] == 150                            # flag off: exactly as before
    full = watch.finish(True, full=True)
    assert len(full["all"]) == 250 and full["all"][0] == "site/f0.txt"
