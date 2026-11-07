"""The CLI file the owner chose in Settings (GAP-providers, bins.py; re-expresses the old app's test_provider_settings.py): checked when it
is written, stored privately, and ignored, not honoured, once the file has vanished."""
from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from sutra_app.connectors.bins import BINS_FILE, BinStore, check_path
from sutra_app.connectors.errors import InvalidRequestError

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX file modes; Windows keeps the installer's PATH")


def executable(path, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.fixture
def store(tmp_path):
    return BinStore(tmp_path / "data")


def test_a_chosen_file_is_stored_privately_and_read_back(store, tmp_path):
    claude = executable(tmp_path / "tools" / "claude")
    assert store.set("claude", str(claude)) == str(claude)
    path = tmp_path / "data" / "connectors" / BINS_FILE
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1, "bins": {"claude": str(claude)}}
    assert store.load() == {"claude": str(claude)}


def test_a_link_named_claude_to_a_file_with_another_name_is_accepted(store, tmp_path):
    target = executable(tmp_path / "share" / "claude" / "versions" / "2.1.308")          # the native installer's layout
    link = tmp_path / "bin" / "claude"
    link.parent.mkdir()
    link.symlink_to(target)
    assert store.set("claude", str(link)) == str(link)


def test_a_home_relative_path_is_the_owners_home(store, tmp_path):
    executable(tmp_path / "home" / ".volta" / "bin" / "codex")
    assert store.set("codex", "~/.volta/bin/codex", home=str(tmp_path / "home")) == str(tmp_path / "home" / ".volta" / "bin" / "codex")


@pytest.mark.parametrize(("make", "provider", "says"), [
    (lambda t: str(t / "nothing" / "claude"), "claude", "There is no file at"),
    (lambda t: str(executable(t / "x" / "claude", 0o644)), "claude", "cannot be run"),
    (lambda t: str((t / "dir" / "claude").mkdir(parents=True) or t / "dir" / "claude"), "claude", "is a folder"),
    (lambda t: str(executable(t / "x" / "rm")), "claude", "Choose the file named claude"),
    (lambda t: str(executable(t / "x" / "codex")), "claude", "Choose the file named claude"),
    (lambda t: "claude", "claude", "full path"),
    (lambda t: "bin/claude", "claude", "full path"),
    (lambda t: "/usr/bin/claude\n; rm -rf /", "claude", "full path of the claude command"),
    (lambda t: "/" + "a" * 1100 + "/claude", "claude", "full path of the claude command"),
    (lambda t: str(executable(t / "x" / "stub")), "stub", "has no command-line file"),
])
def test_a_path_that_cannot_be_the_command_is_refused_with_the_reason(store, tmp_path, make, provider, says):
    with pytest.raises(InvalidRequestError) as e:
        store.set(provider, make(tmp_path))
    assert says in e.value.user_message()
    assert store.stored() == {}                                                       # nothing was written


def test_a_stored_path_that_vanished_is_ignored_not_honoured(store, tmp_path):
    claude = executable(tmp_path / "tools" / "claude")
    store.set("claude", str(claude))
    claude.unlink()
    assert store.stored() == {"claude": str(claude)} and store.load() == {}


def test_clearing_forgets_only_that_provider(store, tmp_path):
    store.set("claude", str(executable(tmp_path / "a" / "claude")))
    store.set("codex", str(executable(tmp_path / "b" / "codex")))
    assert store.set("claude", None) is None
    assert list(store.stored()) == ["codex"]
    assert store.set("codex", "  ") is None                                           # an empty box forgets the choice too
    assert store.stored() == {}


def test_a_file_that_does_not_read_is_ignored(store, tmp_path):
    path = tmp_path / "data" / "connectors" / BINS_FILE
    path.parent.mkdir(parents=True)
    for body in ("{oops", json.dumps({"version": 1, "bins": {"stub": "/bin/sh"}}), json.dumps({"version": 1, "bins": {}, "x": 1})):
        path.write_text(body, encoding="utf-8")
        assert store.stored() == {} and store.load() == {}


def test_check_path_runs_nothing(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a process was started")))
    assert check_path("codex", str(executable(tmp_path / "codex"))) == str(tmp_path / "codex")


# ---- a file that was not written by `set` (QA security-privacy: a restored archive planted {"claude": "/bin/sh"}) ------------------------------

def plant(tmp_path, bins):
    path = tmp_path / "data" / "connectors" / BINS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "bins": bins}), encoding="utf-8")
    return path


@pytest.mark.parametrize(("provider", "planted"), [
    ("claude", "/bin/sh"), ("codex", "/usr/bin/env"), ("claude", "/bin/ls"), ("claude", "claude"), ("codex", "~/codex"), ("claude", "/bin/claude/../sh"),
])
def test_a_stored_path_check_path_would_refuse_is_never_loaded(store, tmp_path, provider, planted):
    plant(tmp_path, {provider: planted})
    assert store.stored() == {} and store.load() == {}


def test_only_the_planted_entry_is_dropped_and_a_later_set_does_not_write_it_back(store, tmp_path):
    codex = executable(tmp_path / "tools" / "codex")
    path = plant(tmp_path, {"claude": "/bin/sh", "codex": str(codex)})
    assert store.load() == {"codex": str(codex)}
    store.set("codex", str(codex))
    assert json.loads(path.read_text(encoding="utf-8"))["bins"] == {"codex": str(codex)}
