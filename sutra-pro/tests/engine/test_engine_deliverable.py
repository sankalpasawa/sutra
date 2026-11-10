"""What a project run leaves for the owner (D135): the host records which file the run delivered and, from git, which files changed in the owner's working
folder while the team worked (`deliverable.json`, written before `run.ended`, never by an agent); the server posts both to the team's chat.

The mock runs here change nothing in a folder (offline mode reads and writes none), so a port that behaves like a builder with edit tools stands in: its first
builder call edits the folder. What is proved is the host's own reading: before and after, the list, the cases where nothing is said, and that the owner's folder
is only read."""
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from sutra_app.connectors.workdir import WorkFolder
from sutra_app.engine import llm
from sutra_app.engine.host import folder_watch as fw

from test_engine_host import GatePort, QUIET, Running, append_inbox, chat, events, j2, trace, wait_until   # noqa: F401  (fixtures and helpers)
from test_engine_project import BRIEF, TaggingPort

needs_git = pytest.mark.skipif(shutil.which("git") is None or fw.git_executable() is None, reason="git is not available here")
UPDATE = ("Check the details of the app in the repo and update README.md so that its first section matches the app: add the line "
          "'checked by the team' at the end of README.md, list what you changed, and say what you verified and what is left to do.")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return done.stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    folder = tmp_path / "owners-repo"
    (folder / "docs").mkdir(parents=True)
    (folder / "README.md").write_text("# The app\n", encoding="utf-8")
    (folder / "docs" / "NOTES.md").write_text("notes\n", encoding="utf-8")
    git(folder, "init", "-q", ".")
    git(folder, "add", ".")
    git(folder, "commit", "-q", "-m", "first")
    return folder


class EditingPort(llm.ScriptedPort):
    """J2's mock mode; the first call of a builder that may edit changes the owner's folder the way its tools would."""

    def __init__(self, *args, edits=(), **kw):
        super().__init__(*args, **kw)
        self.edits, self.fired = list(edits), False

    def complete(self, req, on_progress=None):
        if not self.fired and req.tag.function.startswith("W-") and req.tag.workspace == "edit":
            self.fired = True
            for edit in self.edits:
                edit()
        return super().complete(req, on_progress)


def run_project(run_dir, edits=(), brief=None):
    def make(*, sink, mock, task, paths):
        return EditingPort(usage_sink=sink, edits=edits)
    running = Running(run_dir, "--mock", make_port=make)
    assert running.wait(60) == 0
    return running


def deliverable(run_dir) -> dict:
    return json.loads((Path(run_dir) / "deliverable.json").read_text(encoding="utf-8"))


def append(path: Path, text: str):
    return lambda: path.open("a", encoding="utf-8").write(text)


# ---- the record, through the host ------------------------------------------------------------------------------------------------------------
@needs_git
def test_a_project_run_records_the_files_it_changed_in_the_owners_git_folder(j2, make_run_dir, data_dir, repo):
    WorkFolder(data_dir).set(str(repo), access="edit")
    edits = [append(repo / "README.md", "checked by the team\n"), lambda: (repo / "docs" / "NEW.md").write_text("new\n", encoding="utf-8"),
             lambda: (repo / "docs" / "NOTES.md").unlink()]
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir, edits)
    record = deliverable(run_dir)
    assert record["schema"] == "deliverable/1" and record["output"] == "project" and record["file"] == "project.md" and record["label"] == "Project work report"
    assert record["changes"] == {"files": [{"path": "README.md", "status": "modified"}, {"path": "docs/NEW.md", "status": "new"},
                                           {"path": "docs/NOTES.md", "status": "deleted"}], "more": 0}
    assert [t["data"] for t in trace(run_dir, "folder_watch.started")] == [{"entries": 0, "edit": True}]
    assert [t["data"] for t in trace(run_dir, "folder_watch.finished")] == [{"files": 3, "more": 0}]
    ended = events(run_dir)[-1]
    assert ended["t"] == "run.ended" and (run_dir / "deliverable.json").stat().st_mtime <= (run_dir / "events.jsonl").stat().st_mtime + 1


@needs_git
def test_git_looked_and_nothing_changed_is_an_answer_too(j2, make_run_dir, data_dir, repo):
    WorkFolder(data_dir).set(str(repo), access="edit")
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir)
    assert deliverable(run_dir)["changes"] == {"files": [], "more": 0}


@needs_git
def test_a_file_that_was_already_changed_before_the_run_and_changed_again_is_listed(j2, make_run_dir, data_dir, repo):
    (repo / "README.md").write_text("# The app\nowner's own edit\n", encoding="utf-8")                  # the owner's work in progress
    (repo / "scratch.txt").write_text("owner's scratch\n", encoding="utf-8")
    WorkFolder(data_dir).set(str(repo), access="edit")
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir, [append(repo / "README.md", "checked by the team\n")])
    assert deliverable(run_dir)["changes"]["files"] == [{"path": "README.md", "status": "modified"}]       # scratch.txt did not change: it is not listed


@needs_git
def test_the_paths_are_relative_to_the_working_folder_when_it_is_inside_a_bigger_repository(j2, make_run_dir, data_dir, repo):
    (repo / "app").mkdir()
    (repo / "app" / "main.py").write_text("print(1)\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "app")
    WorkFolder(data_dir).set(str(repo / "app"), access="edit")
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir, [append(repo / "app" / "main.py", "print(2)\n"), append(repo / "README.md", "outside the working folder\n")])
    assert deliverable(run_dir)["changes"]["files"] == [{"path": "main.py", "status": "modified"}]        # a change outside the folder is not the team's


@needs_git
def test_with_read_only_chosen_nothing_is_said_about_changes(j2, make_run_dir, data_dir, repo):
    WorkFolder(data_dir).set(str(repo), access="read")
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir)
    record = deliverable(run_dir)
    assert "changes" not in record and record["file"] == "project.md"
    assert not trace(run_dir, "folder_watch.finished")


def test_a_folder_that_is_not_a_git_work_tree_is_left_out_silently(j2, make_run_dir, data_dir, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    WorkFolder(data_dir).set(str(plain), access="edit")
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir, [lambda: (plain / "x.txt").write_text("x", encoding="utf-8")])
    assert "changes" not in deliverable(run_dir) and not trace(run_dir, "publish.error") and not trace(run_dir, "folder_watch.started")


def test_with_no_folder_the_record_names_the_file_and_no_changes(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    run_project(run_dir)
    record = deliverable(run_dir)
    assert record["file"] == "project.md" and "changes" not in record and not trace(run_dir, "publish.error")


@needs_git
def test_git_that_is_missing_is_left_out_silently(j2, make_run_dir, data_dir, repo, monkeypatch):
    WorkFolder(data_dir).set(str(repo), access="edit")
    monkeypatch.setattr(fw.shutil, "which", lambda name: None)
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir, [append(repo / "README.md", "x\n")])
    assert "changes" not in deliverable(run_dir) and not trace(run_dir, "publish.error")


def test_an_output_that_leaves_no_deliverable_writes_no_record_and_runs_no_git(j2, make_run_dir, data_dir, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fw, "git_executable", lambda: calls.append(1))
    run_dir = make_run_dir(user_text="build a florist site for Petal and Stem in Jaipur with bouquets, same-day delivery, wedding flowers, "
                                     "a contact form and opening hours, warm and simple, working well on phones", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    assert running.wait(60) == 0
    answerer.stop()
    assert json.loads((run_dir / "output.json").read_text())["output"] == "website"
    assert not (run_dir / "deliverable.json").exists() and calls == []


@needs_git
def test_the_watch_only_reads_the_owners_folder_and_writes_nothing_into_it(j2, make_run_dir, data_dir, repo):
    WorkFolder(data_dir).set(str(repo), access="edit")

    def tree():
        out = {}
        for root, dirs, files in os.walk(repo):
            for name in dirs + files:
                path = Path(root, name)
                info = path.lstat()
                out[str(path.relative_to(repo))] = (info.st_mtime_ns, info.st_size)
        return out
    before = tree()
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir)
    assert tree() == before                                     # not a file, not the index: git status took no lock and refreshed nothing
    assert (run_dir / "deliverable.json").is_file() and not (repo / "deliverable.json").exists()


@needs_git
def test_a_stopped_run_records_what_it_changed_before_it_stopped(j2, make_run_dir, data_dir, repo):
    WorkFolder(data_dir).set(str(repo), access="edit")
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    port = {}

    def make(*, sink, mock, task, paths):
        port["p"] = GatePort(usage_sink=sink)
        return port["p"]
    running = Running(run_dir, "--mock", make_port=make)
    wait_until(lambda: "p" in port and port["p"].waiting.is_set(), what="a request in flight")
    (repo / "README.md").write_text("# The app\nchanged before the stop\n", encoding="utf-8")        # what a builder had done by now
    append_inbox(run_dir, 1, "stop")
    assert running.wait() == 0
    assert events(run_dir)[-1]["status"] == "stopped"
    assert deliverable(run_dir)["changes"]["files"] == [{"path": "README.md", "status": "modified"}]


@needs_git
def test_the_run_is_not_held_up_by_a_git_that_hangs(j2, make_run_dir, data_dir, repo, monkeypatch):
    WorkFolder(data_dir).set(str(repo), access="edit")
    real = subprocess.run

    def slow(argv, *a, **kw):
        if "status" in argv:
            raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 1)
        return real(argv, *a, **kw)
    monkeypatch.setattr(fw.subprocess, "run", slow)
    run_dir = make_run_dir(user_text=UPDATE, settings=QUIET)
    run_project(run_dir)
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items") and "changes" not in deliverable(run_dir)
    assert not trace(run_dir, "publish.error")


# ---- the reading, as a unit ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("code,word", [("??", "new"), ("A ", "new"), ("AM", "new"), (" M", "modified"), ("M ", "modified"), ("MM", "modified"), ("T ", "modified"),
                                       ("UU", "modified"), (" D", "deleted"), ("D ", "deleted"), ("AD", "deleted")])
def test_a_porcelain_code_becomes_one_word(code, word):
    assert fw.status_word(code) == word and word in fw.STATUS_WORDS


def test_changes_between_two_snapshots_names_what_differs_and_how():
    before = {"kept.md": (" M", "sha1:a"), "again.md": (" M", "sha1:a"), "scratch.txt": ("??", "sha1:s"), "gone-untracked.txt": ("??", "sha1:g"),
              "restored.md": (" D", "gone"), "turns-deleted.md": (" M", "sha1:t")}
    after = {"kept.md": (" M", "sha1:a"), "again.md": (" M", "sha1:b"), "scratch.txt": ("??", "sha1:s2"), "created.md": ("??", "sha1:c"),
             "turns-deleted.md": (" D", "gone"), "added.md": ("A ", "sha1:d")}
    assert fw.changes_between(before, after) == [
        {"path": "added.md", "status": "new"}, {"path": "again.md", "status": "modified"}, {"path": "created.md", "status": "new"},
        {"path": "gone-untracked.txt", "status": "deleted"}, {"path": "restored.md", "status": "reverted"},
        {"path": "scratch.txt", "status": "modified"}, {"path": "turns-deleted.md", "status": "deleted"}]
    assert fw.changes_between({}, {}) == [] and fw.changes_between(after, after) == []


@needs_git
def test_a_snapshot_reads_untracked_files_one_by_one_and_fingerprints_the_content(repo):
    (repo / "docs" / "deeper").mkdir()
    (repo / "docs" / "deeper" / "a.md").write_text("a", encoding="utf-8")
    (repo / "docs" / "deeper" / "b.md").write_text("b", encoding="utf-8")
    exe = fw.git_executable()
    snap = fw.snapshot(exe, str(repo), 20)
    assert sorted(snap) == ["docs/deeper/a.md", "docs/deeper/b.md"] and {code for code, _ in snap.values()} == {"??"}
    first = snap["docs/deeper/a.md"][1]
    (repo / "docs" / "deeper" / "a.md").write_text("A", encoding="utf-8")
    assert fw.snapshot(exe, str(repo), 20)["docs/deeper/a.md"][1] != first and first.startswith("sha1:")


@needs_git
def test_a_snapshot_below_the_top_of_the_repository_names_paths_from_the_folder(repo):
    (repo / "docs" / "NOTES.md").write_text("changed\n", encoding="utf-8")
    snap = fw.snapshot(fw.git_executable(), str(repo / "docs"), 20)
    assert list(snap) == ["NOTES.md"]


@needs_git
def test_a_status_longer_than_the_limit_is_not_a_list_anyone_reads(repo, monkeypatch):
    for n in range(8):
        (repo / f"f{n}.txt").write_text(str(n), encoding="utf-8")
    monkeypatch.setattr(fw, "MAX_ENTRIES", 5)
    assert fw.snapshot(fw.git_executable(), str(repo), 20) is None


@needs_git
def test_only_the_first_hundred_files_are_named_and_the_rest_counted(repo, monkeypatch):
    watch = fw.FolderWatch.start(__import__("sutra_app.connectors.workdir", fromlist=["Folder"]).Folder(str(repo), edit=True))
    for n in range(130):
        (repo / f"n{n:03d}.txt").write_text(str(n), encoding="utf-8")
    got = watch.finish(True)
    assert len(got["files"]) == fw.LISTED_MAX == 100 and got["more"] == 30 and got["files"][0] == {"path": "n000.txt", "status": "new"}


@needs_git
def test_a_big_file_is_fingerprinted_by_size_and_time_not_read(repo, monkeypatch):
    monkeypatch.setattr(fw, "HASH_FILE_MAX", 10)
    (repo / "big.bin").write_bytes(b"x" * 100)
    snap = fw.snapshot(fw.git_executable(), str(repo), 20)
    assert snap["big.bin"][1].startswith("stat:100:")


def test_a_folder_with_no_dot_git_above_it_never_runs_git(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fw, "git_executable", lambda: calls.append(1) or "/usr/bin/git")
    plain = tmp_path / "plain"
    plain.mkdir()
    assert fw.FolderWatch.start(__import__("sutra_app.connectors.workdir", fromlist=["Folder"]).Folder(str(plain), edit=True)) is None and calls == []
    assert fw.FolderWatch.start(None) is None and fw.FolderWatch.start("") is None


@needs_git
def test_the_watch_says_nothing_when_the_owner_allowed_no_change_at_either_end(repo):
    from sutra_app.connectors.workdir import Folder
    watch = fw.FolderWatch.start(Folder(str(repo), edit=False))
    (repo / "README.md").write_text("changed", encoding="utf-8")
    assert watch.finish(False) is None
    assert watch.finish(True)["files"] == [{"path": "README.md", "status": "modified"}]        # the owner allowed changes meanwhile


def test_the_mac_stub_of_the_developer_tools_is_not_run_when_they_are_not_installed(monkeypatch):
    seen = []

    def fake_run(argv, **kw):
        seen.append(argv[0])
        return subprocess.CompletedProcess(argv, 2, b"", b"xcode-select: error")
    monkeypatch.setattr(fw.sys, "platform", "darwin")
    monkeypatch.setattr(fw.shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(fw.os.path, "realpath", lambda p: p)
    monkeypatch.setattr(fw.subprocess, "run", fake_run)
    assert fw.git_executable() is None and seen == ["xcode-select"]
    monkeypatch.setattr(fw.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"/Library/Developer/CommandLineTools\n", b""))
    assert fw.git_executable() == "/usr/bin/git"
    monkeypatch.setattr(fw.shutil, "which", lambda name: "/opt/homebrew/bin/git")
    assert fw.git_executable() == "/opt/homebrew/bin/git"                                # another git needs no check


@needs_git
def test_the_environment_of_git_carries_no_git_variable_of_this_process_and_no_fsmonitor(repo, monkeypatch):
    seen = {}
    real = subprocess.run

    def spy(argv, **kw):
        seen["argv"], seen["env"] = argv, kw.get("env")
        return real(argv, **kw)
    monkeypatch.setenv("GIT_DIR", str(repo / "elsewhere"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo / "elsewhere"))
    monkeypatch.setattr(fw.subprocess, "run", spy)
    assert fw.snapshot(fw.git_executable(), str(repo), 20) == {}
    assert "GIT_DIR" not in seen["env"] and "GIT_WORK_TREE" not in seen["env"] and seen["env"]["GIT_OPTIONAL_LOCKS"] == "0" and seen["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "--no-optional-locks" in seen["argv"] and "core.fsmonitor=false" in seen["argv"]

