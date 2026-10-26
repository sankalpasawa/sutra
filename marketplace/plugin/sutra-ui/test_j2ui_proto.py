"""test_j2ui_proto.py -- the prototype loader the j2ui tests share (test_fixtures/j2ui/proto.py; UI port step C0).

Named claims:
  C0-1  with the prototype present, its constants read at the pinned commit are the ones the port is built against: the
        nine map statuses, the fourteen legend rows, the page's sha256
  C0-2  without the prototype (J2_PROTOTYPE at an empty directory, or at nothing) every read skips with a reason instead
        of failing, so a machine with no prototype runs the gate green
  C0-3  the working tree is never read: a committed file read after the working copy was edited, or the repository
        was left dirty, is the committed one (checked on a repository of this test's own)
  C0-4  consts() reads a literal without running the file; load() refuses the modules that import the model client
"""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from test_fixtures.j2ui import proto

PAGE_SHA = "23549799903e98485f404872670c49e5735c7cc9962c19b42037b1bde5ebad0d"
STATUSES = ("filed", "done_unchecked", "running", "waiting", "waiting_on_you", "fault", "left_open", "not_made", "idle")


def _git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.test", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.test", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def little_repo(tmp_path, monkeypatch):
    """A repository of this test's own with one committed module; PIN is its commit."""
    r = tmp_path / "proto"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "m.py").write_text("COLORS = ('red', 'blue')\nTABLE = [{'k': 1}, {'k': 2}]\nBOOM = open('/nonexistent/never-run')\n", encoding="utf-8")
    (r / "pure.py").write_text("def twice(x):\n    return 2 * x\n", encoding="utf-8")
    (r / "j2_map.py").write_text("import llm\n", encoding="utf-8")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "one")
    sha = _git(r, "rev-parse", "HEAD")
    monkeypatch.setenv("J2_PROTOTYPE", str(r))
    monkeypatch.setattr(proto, "PIN", sha)
    return r


# ---- C0-1: the prototype as it is pinned -----------------------------------------------------------------------------
def test_c01_the_pinned_constants_and_page():
    if proto.skip_reason():
        pytest.skip(proto.skip_reason())
    assert tuple(proto.consts("j2_map.py", "STATUSES")) == STATUSES
    legend = proto.consts("j2_map.py", "LEGEND")
    assert len(legend) == 14 and [r["key"] for r in legend][:3] == ["function", "engine", "work"]
    assert set(proto.consts("j2_map.py", "NODE_KINDS")) >= {"person", "function", "engine", "work"}
    assert "asks" in proto.consts("j2_map.py", "EDGE_KINDS")
    assert proto.consts("j2_artifacts.py", "OPEN") == {"doc": "text", "data": "text", "page": "preview", "image": "image"}
    assert tuple(proto.consts("j2_board.py", "STATUSES")) == ("open", "answered", "unanswered", "refused")
    assert tuple(proto.consts("j2_board.py", "ROLES")) == ("function", "builder")
    page = proto.show("j2_ui.html")
    assert hashlib.sha256(page).hexdigest() == PAGE_SHA and page.count(b"\n") == 1724
    schema = proto.load("j2_schema")
    assert callable(getattr(schema, "run_views", None)), "the atom adapter is a pure module and loads"


# ---- C0-2: no prototype, a skip with a reason ------------------------------------------------------------------------
def test_c02_an_empty_directory_skips_every_read(tmp_path, monkeypatch):
    monkeypatch.setenv("J2_PROTOTYPE", str(tmp_path))
    assert "not a git checkout" in proto.skip_reason()
    for call in (lambda: proto.show("j2_ui.html"), lambda: proto.consts("j2_map.py", "STATUSES"), lambda: proto.load("j2_schema")):
        with pytest.raises(pytest.skip.Exception):
            call()


def test_c02_a_missing_directory_and_a_missing_commit_skip_with_their_reason(tmp_path, monkeypatch, little_repo):
    monkeypatch.setenv("J2_PROTOTYPE", str(tmp_path / "nope"))
    assert "not a directory" in proto.skip_reason()
    monkeypatch.setenv("J2_PROTOTYPE", str(little_repo))
    monkeypatch.setattr(proto, "PIN", "0" * 40)
    assert "pinned commit" in proto.skip_reason()
    with pytest.raises(pytest.skip.Exception):
        proto.show("m.py")


def test_c02_a_folder_inside_another_repository_is_not_the_prototype(little_repo, monkeypatch):
    inner = little_repo / "sub"
    inner.mkdir()
    monkeypatch.setenv("J2_PROTOTYPE", str(inner))
    assert "not a git checkout" in proto.skip_reason()


# ---- C0-3: git objects, never the working tree ------------------------------------------------------------------------
def test_c03_a_dirty_working_tree_changes_nothing(little_repo):
    assert proto.skip_reason() is None
    committed = proto.show("m.py")
    (little_repo / "m.py").write_text("COLORS = ('green',)\n", encoding="utf-8")        # edited, not committed
    (little_repo / "untracked.py").write_text("X = 1\n", encoding="utf-8")
    assert proto.show("m.py") == committed
    assert proto.consts("m.py", "COLORS") == ("red", "blue")
    with pytest.raises(FileNotFoundError):
        proto.show("untracked.py")


# ---- C0-4: literals only, nothing executed -----------------------------------------------------------------------------
def test_c04_consts_never_runs_the_file_and_load_refuses_the_model_client(little_repo):
    assert proto.consts("m.py", "TABLE") == [{"k": 1}, {"k": 2}]
    with pytest.raises(KeyError):
        proto.consts("m.py", "ABSENT")
    with pytest.raises(ValueError):
        proto.consts("m.py", "BOOM")                 # not a literal: refused, and open() never ran
    assert proto.load("pure").twice(21) == 42
    for name in ("j2_map", "j2_realization", "llm"):
        with pytest.raises(ValueError):
            proto.load(name)
