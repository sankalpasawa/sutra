"""engine/runlist.py (J2 sync 4, D140): Run settings' run list and the build journey's stops, Sutra's own code since patch P13 was
retired. The logic is the one the patch held and the one J2's own server has (`run_row`, `run_list`, the inline `/api/changes`):
these tests pin it on small run folders made here, so a change of the readers or of a reply shape fails by name. The views that
serve it (`views.runlist`, `views.changes`) are tested with the real runs in test_engine_views.py."""
import json
import os
from pathlib import Path

import pytest

from sutra_app.engine import j2, runlist, views

LONG = "Brew Lab sells small-batch coffee to people who care. " + "A very long second sentence that goes on. " * 4


def make_run(runs: Path, name: str, *, chat=True, summary=None, goal=None, first_user="", meta_output=None) -> Path:
    """One run folder the way J2 leaves it: chat.jsonl (a meta row, then messages), summary.json, goal.json."""
    d = runs / name
    d.mkdir(parents=True)
    if chat:
        rows = []
        if meta_output is not None:
            rows.append({"meta": True, "output": meta_output})
        if first_user:
            rows.append({"who": "user", "text": first_user})
        rows.append({"who": "identity", "text": "hello"})
        (d / "chat.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    if summary is not None:
        (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    if goal is not None:
        (d / "goal.json").write_text(json.dumps(goal), encoding="utf-8")
    return d


@pytest.fixture
def runs(tmp_path) -> Path:
    base = tmp_path / "runs"
    base.mkdir()
    return base


# ---- run_row ------------------------------------------------------------------------------------------------------------
def test_a_row_has_exactly_the_six_keys_of_run_settings(runs):
    make_run(runs, "j2-20261104-100004", summary={"status": "done", "output_type": "website", "brief": "A cafe site"},
             goal={"site_name": "Brew Lab"})
    row = runlist.run_row("j2-20261104-100004", str(runs))
    assert row == {"id": "j2-20261104-100004", "title": "Brew Lab", "status": "done", "output": "website",
                   "when": "2026-11-04T10:00:04", "brief": "A cafe site"}
    assert list(row) == ["id", "title", "status", "output", "when", "brief"]


@pytest.mark.parametrize("status, expected", [("done", "done"), ("done_with_open_items", "done"), ("stopped", "stopped"),
                                              ("crashed", "stopped"), ("stuck", "stopped"), ("out_of_budget", "stopped"), ("", "stopped")])
def test_the_status_of_a_finished_run_is_done_or_stopped(runs, status, expected):
    make_run(runs, "j2-20261104-100004", summary={"status": status})
    assert runlist.run_row("j2-20261104-100004", str(runs))["status"] == expected


def test_a_run_without_a_summary_never_finished_unless_it_is_the_live_one_while_it_runs(runs):
    make_run(runs, "j2-20261104-100004")
    assert runlist.run_row("j2-20261104-100004", str(runs))["status"] == "stopped"
    assert runlist.run_row("j2-20261104-100004", str(runs), live_running=True)["status"] == "running"


def test_the_title_is_the_site_name_else_the_first_sentence_of_the_statement_else_the_run_id(runs):
    make_run(runs, "j2-20261104-100001", goal={"site_name": "  Brew Lab  ", "statement": "ignored."})
    make_run(runs, "j2-20261104-100002", goal={"statement": "Short statement. And a second one."})
    make_run(runs, "j2-20261104-100003", goal={"statement": LONG})
    make_run(runs, "j2-20261104-100004")
    names = ("j2-20261104-100001", "j2-20261104-100002", "j2-20261104-100003", "j2-20261104-100004")
    assert [runlist.run_row(n, str(runs))["title"] for n in names] == [
        "Brew Lab", "Short statement.", "Brew Lab sells small-batch coffee to people who care.", "j2-20261104-100004"]


def test_the_title_of_a_long_first_sentence_is_cut_at_70_characters_with_an_ellipsis(runs):
    sentence = "x" * 90 + ". Then more."
    make_run(runs, "j2-20261104-100004", goal={"statement": sentence})
    assert runlist.run_row("j2-20261104-100004", str(runs))["title"] == "x" * 70 + "…"


def test_the_output_is_the_type_the_run_ended_with_else_the_one_it_started_with(runs):
    make_run(runs, "j2-20261104-100001", summary={"output_type": "prd"}, meta_output="website")
    make_run(runs, "j2-20261104-100002", meta_output="website")
    make_run(runs, "j2-20261104-100003")
    names = ("j2-20261104-100001", "j2-20261104-100002", "j2-20261104-100003")
    assert [runlist.run_row(n, str(runs))["output"] for n in names] == ["prd", "website", ""]


def test_the_brief_is_the_summary_brief_else_the_first_user_message_cut_at_160(runs):
    make_run(runs, "j2-20261104-100001", summary={"brief": "From the summary"}, first_user="from the chat")
    make_run(runs, "j2-20261104-100002", first_user="y" * 200)
    make_run(runs, "j2-20261104-100003")
    names = ("j2-20261104-100001", "j2-20261104-100002", "j2-20261104-100003")
    assert [runlist.run_row(n, str(runs))["brief"] for n in names] == ["From the summary", "y" * 160, ""]


def test_when_comes_from_the_id_and_is_empty_for_an_id_without_a_timestamp(runs):
    make_run(runs, "j2-20261104-100004-7f3a")
    make_run(runs, "j2-notes")
    assert runlist.run_row("j2-20261104-100004-7f3a", str(runs))["when"] == "2026-11-04T10:00:04"
    assert runlist.run_row("j2-notes", str(runs))["when"] == ""


@pytest.mark.parametrize("name", ["", None, "../runs", "j2-../x", "run-20261104-100004", "j2-20261104-100004/chat.jsonl"])
def test_a_name_that_is_not_a_saved_run_id_is_not_a_run(runs, name):
    make_run(runs, "j2-20261104-100004")
    assert runlist.run_row(name, str(runs)) is None


def test_a_folder_without_a_chat_and_a_missing_folder_are_not_runs(runs):
    make_run(runs, "j2-20261104-100004", chat=False, summary={"status": "done"})
    assert runlist.run_row("j2-20261104-100004", str(runs)) is None
    assert runlist.run_row("j2-20261104-100005", str(runs)) is None


def test_a_torn_summary_and_a_torn_goal_read_as_empty_not_as_an_error(runs):
    d = make_run(runs, "j2-20261104-100004", first_user="Make a site")
    (d / "summary.json").write_text("{not json", encoding="utf-8")
    (d / "goal.json").write_text("[1, 2", encoding="utf-8")
    row = runlist.run_row("j2-20261104-100004", str(runs))
    assert (row["title"], row["status"], row["brief"]) == ("j2-20261104-100004", "stopped", "Make a site")


# ---- run_list -----------------------------------------------------------------------------------------------------------
def test_the_list_is_newest_first_by_when_and_skips_what_is_not_a_run(runs):
    make_run(runs, "j2-20261104-100004", summary={"status": "done"})
    make_run(runs, "j2-20261106-101500", summary={"status": "stopped"})
    make_run(runs, "j2-20261105-090000")
    make_run(runs, "j2-20261107-120000", chat=False)           # no chat: not a run
    (runs / "notes.txt").write_text("not a folder")
    (runs / "scratch").mkdir()
    body = runlist.run_list(str(runs))
    assert [r["id"] for r in body["runs"]] == ["j2-20261106-101500", "j2-20261105-090000", "j2-20261104-100004"]
    assert body["live"] == ""


def test_the_live_run_is_named_and_reads_running_only_when_the_caller_says_it_runs(runs):
    make_run(runs, "j2-20261104-100004", summary={"status": "done"})
    make_run(runs, "j2-20261105-090000", summary={"status": "done"})
    idle = runlist.run_list(str(runs), live="j2-20261105-090000", live_running=False)
    assert idle["live"] == "j2-20261105-090000" and {r["status"] for r in idle["runs"]} == {"done"}
    busy = runlist.run_list(str(runs), live="j2-20261105-090000", live_running=True)
    assert {r["id"]: r["status"] for r in busy["runs"]} == {"j2-20261105-090000": "running", "j2-20261104-100004": "done"}
    assert runlist.run_list(str(runs), live_running=True)["runs"][0]["status"] == "done"      # no live id: nothing can be running


def test_an_empty_or_missing_runs_folder_gives_an_empty_list(runs, tmp_path):
    assert runlist.run_list(str(runs)) == {"live": "", "runs": []}
    assert runlist.run_list(str(tmp_path / "does-not-exist"), live="j2-x") == {"live": "j2-x", "runs": []}


def test_no_runs_folder_means_j2s_own_which_is_read_when_the_function_is_called(runs, monkeypatch):
    make_run(runs, "j2-20261104-100004", summary={"status": "done"})
    monkeypatch.setattr(j2, "RUNS_DIR", str(runs))
    assert [r["id"] for r in runlist.run_list()["runs"]] == ["j2-20261104-100004"]
    monkeypatch.setattr(j2, "RUNS_DIR", str(runs / "other"))
    assert runlist.run_list()["runs"] == []


def test_the_list_is_read_only(runs):
    d = make_run(runs, "j2-20261104-100004", summary={"status": "done"})
    before = sorted((p.relative_to(runs).as_posix(), p.stat().st_mtime_ns) for p in runs.rglob("*"))
    runlist.run_list(str(runs))
    runlist.run_changes(str(d))
    assert sorted((p.relative_to(runs).as_posix(), p.stat().st_mtime_ns) for p in runs.rglob("*")) == before


# ---- run_changes --------------------------------------------------------------------------------------------------------
def test_a_change_file_gives_one_stop_per_change_request(runs):
    d = make_run(runs, "j2-20261104-100004")
    (d / "change.json").write_text(json.dumps([
        {"id": "c1", "request": "Add a map", "cycle": 2, "revise": ["a", "b"], "new": ["c"]},
        {"id": "c2", "request": None, "cycle": 3},
        "not a change", 7, None]), encoding="utf-8")
    assert runlist.run_changes(str(d)) == {"changes": [
        {"id": "c1", "request": "Add a map", "cycle": 2, "revise": 2, "new": 1},
        {"id": "c2", "request": "", "cycle": 3, "revise": 0, "new": 0}]}


@pytest.mark.parametrize("text", ["{not json", '{"a": 1}', "[1, 2]", "", "null", '"text"'])
def test_a_torn_or_foreign_change_file_reads_as_no_stops(runs, text):
    d = make_run(runs, "j2-20261104-100004")
    (d / "change.json").write_text(text, encoding="utf-8")
    assert runlist.run_changes(str(d)) == {"changes": []}


def test_no_change_file_no_folder_and_no_run_read_as_no_stops(runs, tmp_path):
    d = make_run(runs, "j2-20261104-100004")
    assert runlist.run_changes(str(d)) == {"changes": []}
    assert runlist.run_changes(str(tmp_path / "missing")) == {"changes": []}
    assert runlist.run_changes(None) == {"changes": []}
    assert runlist.run_changes("") == {"changes": []}


# ---- the module, the views and the vendored j2 ---------------------------------------------------------------------------------
def test_the_views_call_this_module_and_the_vendored_j2_has_no_copy(runs):
    d = make_run(runs, "j2-20261104-100004", summary={"status": "done", "output_type": "website"}, goal={"site_name": "Brew Lab"})
    ctx = views.RunCtx("saved", d.name, str(d), str(runs), None, views.MemoryPaths("l", "p"))
    assert json.loads(views.VIEWS["runlist"](ctx, {}).body) == runlist.run_list(str(runs), "", False)
    assert json.loads(views.VIEWS["changes"](ctx, {}).body) == runlist.run_changes(str(d)) == {"changes": []}
    assert not any(hasattr(j2, name) for name in ("run_row", "run_list", "run_changes"))


def test_the_module_imports_only_the_standard_library_and_the_vendored_j2():
    """No model, no server, no store: the standard library and the vendored j2 (for its readers) and nothing else."""
    import ast
    found = set()
    for node in ast.walk(ast.parse(Path(runlist.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found |= {f"{'.' * node.level}{node.module or ''} {a.name}".strip() for a in node.names}
    assert found == {"json", "os", "re", ". j2"}
